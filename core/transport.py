"""
Module : core/transport.py
Description : Gestion des communications réseau fiables (TCP) pour la messagerie décentralisée.
Rôle : Écoute les connexions entrantes (serveur) et transmet les messages/fichiers (client).
"""

import socket       # Fournit l'interface système pour créer des sockets réseau (TCP/UDP)
import threading    # Permet d'exécuter plusieurs tâches en parallèle (ex: écouter sans bloquer)
import json         # Permet de sérialiser les dictionnaires Python en chaînes de texte structurées
import struct       # Permet d'empaqueter la taille des données en octets binaires fixes (Framing)
import os           # Permet d'interagir avec le système de fichiers (taille, lecture par blocs)

# =====================================================================
# FONCTIONS UTILITAIRES : ENVOI ET RÉCEPTION STRUCTURÉS (FRAMING TCP)
# =====================================================================

def send_payload(sock: socket.socket, data_bytes: bytes) -> None:
    """
    Envoie des données sur un socket TCP en les préfixant par leur taille sur 4 octets.
    
    Format du paquet envoyé :
    [ 4 octets : longueur N (format binaire réseau Big-Endian) ] + [ N octets : données ]
    """
    # 1. On calcule la taille totale des données en octets
    payload_length = len(data_bytes)
    
    # 2. 'struct.pack(">I", payload_length)' convertit cet entier en exactement 4 octets.
    #    '>' signifie Big-Endian (norme standard réseau).
    #    'I' signifie unsigned int (entier non signé sur 4 octets, jusqu'à 4 Go).
    header = struct.pack(">I", payload_length)
    
    # 3. 'sendall' s'assure que la totalité des octets (en-tête + données) est transmise
    sock.sendall(header + data_bytes)


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """
    Lit précisément 'num_bytes' octets depuis le socket TCP.
    
    Pourquoi cette fonction est nécessaire ?
    En TCP, 'sock.recv(N)' peut renvoyer MOINS de N octets si le réseau est lent.
    Cette fonction boucle jusqu'à avoir récupéré l'intégralité des octets demandés.
    """
    buffer = bytearray()
    
    while len(buffer) < num_bytes:
        # On calcule combien d'octets il nous manque encore
        remaining = num_bytes - len(buffer)
        
        # On lit un bloc disponible sur le réseau
        chunk = sock.recv(remaining)
        
        # Si chunk est vide, l'autre machine a coupé la connexion brutalement
        if not chunk:
            raise ConnectionError("La connexion a été fermée par le pair distant.")
            
        buffer.extend(chunk)
        
    return bytes(buffer)

# =====================================================================
# CLASSE SERVEUR : ÉCOUTE ET RÉCEPTION DES MESSAGES EN ARRIÈRE-PLAN
# =====================================================================

class TransportServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 5000, on_message_received=None):
        """
        Initialise le serveur de transport TCP.
        
        :param host: L'adresse d'écoute ("0.0.0.0" signifie écouter sur toutes les interfaces réseau).
        :param port: Le port TCP réservé pour la messagerie (par défaut 5000).
        :param on_message_received: Une fonction de rappel (callback) appelée quand un message arrive.
        """
        self.host = host
        self.port = port
        self.on_message_received = on_message_received
        
        # Drapeau pour savoir si le serveur doit continuer à tourner ou s'arrêter proprement
        self.is_running = False
        
        # Le socket principal du serveur
        self.server_socket = None
        
        # Le thread qui gérera l'écoute sans bloquer le reste de l'application
        self.listen_thread = None

    def start(self):
        """Démarre le serveur dans un thread en arrière-plan."""
        self.is_running = True
        
        # 1. Création du socket : IPv4 (AF_INET) et protocole TCP (SOCK_STREAM)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # 2. Option de réutilisation d'adresse : permet de relancer le serveur immédiatement sans attendre
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 3. Association du socket à l'adresse IP et au port choisis
        self.server_socket.bind((self.host, self.port))
        
        # 4. Activation du mode écoute (file d'attente maximale de 5 connexions simultanées)
        self.server_socket.listen(5)
        
        # 5. Démarrage de la boucle d'écoute dans un thread indépendant
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()
        print(f"[SERVEUR] En écoute sur le port {self.port}...")

    def _listen_loop(self):
        """Boucle infinie qui attend et accepte chaque connexion entrante."""
        while self.is_running:
            try:
                # 'accept()' est bloquant : il attend qu'un pair se connecte
                client_sock, client_addr = self.server_socket.accept()
                
                # Pour chaque ami qui se connecte, on lance un thread dédié pour traiter son message
                client_handler = threading.Thread(
                    target=self._handle_client, 
                    args=(client_sock, client_addr), 
                    daemon=True
                )
                client_handler.start()
                
            except OSError:
                # Se produit normalement lorsque le serveur est arrêté (fermeture du socket)
                break

    def _handle_client(self, client_sock: socket.socket, client_addr: tuple):
        """Prend en charge la réception du message d'un pair précis."""
        ip, port = client_addr
        try:
            # 1. On lit d'abord les 4 premiers octets pour connaître la taille du message
            raw_header = recv_exact(client_sock, 4)
            payload_length = struct.unpack(">I", raw_header)[0]
            
            # 2. On lit le nombre exact d'octets annoncé par l'en-tête
            raw_data = recv_exact(client_sock, payload_length)
            
            # 3. On décode les octets reçus (texte JSON encodé en UTF-8)
            message_text = raw_data.decode("utf-8")
            message_dict = json.loads(message_text)
            
            # 4. Si une fonction de traitement a été fournie, on lui passe le message et l'IP de l'expéditeur
            if self.on_message_received:
                self.on_message_received(message_dict, ip)
            else:
                # Affichage par défaut dans le terminal pour nos tests
                print(f"[REÇU de {ip}]: {message_dict}")
                
        except Exception as e:
            print(f"[ERREUR] Échec de réception depuis {ip}: {e}")
        finally:
            # Toujours fermer la connexion avec ce client une fois le message traité
            client_sock.close()

    def stop(self):
        """Arrête proprement le serveur."""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        print("[SERVEUR] Serveur arrêté.")
# =====================================================================
# CLASSE SERVEUR : ÉCOUTE ET RÉCEPTION DES MESSAGES EN ARRIÈRE-PLAN
# =====================================================================

class TransportServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 5000, on_message_received=None):
        """
        Initialise le serveur de transport TCP.
        
        :param host: L'adresse d'écoute ("0.0.0.0" signifie écouter sur toutes les interfaces réseau).
        :param port: Le port TCP réservé pour la messagerie (par défaut 5000).
        :param on_message_received: Une fonction de rappel (callback) appelée quand un message arrive.
        """
        self.host = host
        self.port = port
        self.on_message_received = on_message_received
        
        # Drapeau pour savoir si le serveur doit continuer à tourner ou s'arrêter proprement
        self.is_running = False
        
        # Le socket principal du serveur
        self.server_socket = None
        
        # Le thread qui gérera l'écoute sans bloquer le reste de l'application
        self.listen_thread = None

    def start(self):
        """Démarre le serveur dans un thread en arrière-plan."""
        self.is_running = True
        
        # 1. Création du socket : IPv4 (AF_INET) et protocole TCP (SOCK_STREAM)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # 2. Option de réutilisation d'adresse : permet de relancer le serveur immédiatement sans attendre
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 3. Association du socket à l'adresse IP et au port choisis
        self.server_socket.bind((self.host, self.port))
        
        # 4. Activation du mode écoute (file d'attente maximale de 5 connexions simultanées)
        self.server_socket.listen(5)
        
        # 5. Démarrage de la boucle d'écoute dans un thread indépendant
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()
        print(f"[SERVEUR] En écoute sur le port {self.port}...")

    def _listen_loop(self):
        """Boucle infinie qui attend et accepte chaque connexion entrante."""
        while self.is_running:
            try:
                # 'accept()' est bloquant : il attend qu'un pair se connecte
                client_sock, client_addr = self.server_socket.accept()
                
                # Pour chaque ami qui se connecte, on lance un thread dédié pour traiter son message
                client_handler = threading.Thread(
                    target=self._handle_client, 
                    args=(client_sock, client_addr), 
                    daemon=True
                )
                client_handler.start()
                
            except OSError:
                # Se produit normalement lorsque le serveur est arrêté (fermeture du socket)
                break

    def _handle_client(self, client_sock: socket.socket, client_addr: tuple):
        """Prend en charge la réception du message d'un pair précis."""
        ip, port = client_addr
        try:
            # 1. On lit d'abord les 4 premiers octets pour connaître la taille du message
            raw_header = recv_exact(client_sock, 4)
            payload_length = struct.unpack(">I", raw_header)[0]
            
            # 2. On lit le nombre exact d'octets annoncé par l'en-tête
            raw_data = recv_exact(client_sock, payload_length)
            
            # 3. On décode les octets reçus (texte JSON encodé en UTF-8)
            message_text = raw_data.decode("utf-8")
            message_dict = json.loads(message_text)
            
            # 4. Si une fonction de traitement a été fournie, on lui passe le message et l'IP de l'expéditeur
            if self.on_message_received:
                self.on_message_received(message_dict, ip)
            else:
                # Affichage par défaut dans le terminal pour nos tests
                print(f"[REÇU de {ip}]: {message_dict}")
                
        except Exception as e:
            print(f"[ERREUR] Échec de réception depuis {ip}: {e}")
        finally:
            # Toujours fermer la connexion avec ce client une fois le message traité
            client_sock.close()

    def stop(self):
        """Arrête proprement le serveur."""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        print("[SERVEUR] Serveur arrêté.")
# =====================================================================
# CLASSE CLIENT : CONNEXION ET ENVOI DE MESSAGES À UN AUTRE PAIR
# =====================================================================

class TransportClient:
    def __init__(self, default_port: int = 5000, timeout: float = 5.0):
        """
        Initialise le client d'envoi TCP.
        
        :param default_port: Port TCP cible où écoute l'autre machine (5000 par défaut).
        :param timeout: Temps d'attente maximum en secondes avant d'abandonner si la machine ne répond pas.
        """
        self.default_port = default_port
        self.timeout = timeout

    def send_message(self, target_ip: str, message_payload: dict, target_port: int = None) -> bool:
        """
        Établit une connexion TCP vers un pair distant et lui expédie un dictionnaire de données.
        
        :param target_ip: Adresse IP du pair destinataire (ex: "192.168.1.45" ou "127.0.0.1").
        :param message_payload: Données du message sous forme de dictionnaire Python.
        :param target_port: Port d'écoute du pair (utilise default_port si non spécifié).
        :return: True si l'envoi a réussi, False en cas d'erreur de communication.
        """
        port = target_port or self.default_port
        
        # 1. On transforme le dictionnaire Python en texte JSON, puis en octets binaires UTF-8
        json_string = json.dumps(message_payload)
        data_bytes = json_string.encode("utf-8")
        
        # 2. Utilisation d'un bloc 'with' pour s'assurer que le socket sera toujours fermé proprement
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                # Définit un délai limite pour ne pas figer l'application si l'IP cible n'existe pas
                sock.settimeout(self.timeout)
                
                # Établissement de la poignée de main TCP (3-Way Handshake : SYN, SYN-ACK, ACK)
                sock.connect((target_ip, port))
                
                # Envoi des données préfixées par les 4 octets de taille via notre fonction utilitaire
                send_payload(sock, data_bytes)
                
                print(f"[CLIENT] Message envoyé avec succès à {target_ip}:{port}")
                return True
                
        except socket.timeout:
            print(f"[CLIENT ERREUR] Délai d'attente dépassé pour se connecter à {target_ip}:{port}")
            return False
        except ConnectionRefusedError:
            print(f"[CLIENT ERREUR] Connexion refusée par {target_ip}:{port} (le pair est injoignable ou le serveur n'est pas lancé)")
            return False
        except Exception as e:
            print(f"[CLIENT ERREUR] Échec d'envoi vers {target_ip}:{port} -> {e}")
            return False
# =====================================================================
# BANC D'ESSAI INTERACTIF : SÉPARATION SERVEUR / CLIENT SUR 2 TERMINAUX
# =====================================================================

if __name__ == "__main__":
    import time
    import sys

    print("=== TEST MANUEL MULTI-TERMINAL (core/transport.py) ===")
    print("1. Lancer comme SERVEUR (Écouteur)")
    print("2. Lancer comme CLIENT (Émetteur)")
    choix = input("Choisissez le rôle (1 ou 2) : ").strip()

    if choix == "1":
        # RÔLE DU SERVEUR : reste allumé et écoute en continu
        server = TransportServer(host="0.0.0.0", port=5000)
        server.start()
        print("\n[SERVEUR PRÊT] En attente de messages... (Appuyez sur Ctrl+C pour arrêter)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
            print("\n[SERVEUR] Arrêt demandé.")

    elif choix == "2":
        # RÔLE DU CLIENT : demande un message et l'expédie
        client = TransportClient(default_port=5000)
        ip_cible = input("Entrez l'IP du serveur (appuyez sur Entrée pour 127.0.0.1) : ").strip() or "127.0.0.1"
        
        while True:
            texte = input("\nVotre message (ou 'exit' pour quitter) : ").strip()
            if texte.lower() == "exit":
                break
            
            paquet = {
                "type": "chat_message",
                "sender": "yagrebita",
                "content": texte,
                "timestamp": time.time()
            }
            client.send_message(ip_cible, paquet)
            
        print("[CLIENT] Déconnexion.")
    else:
        print("[ERREUR] Choix invalide. Tapez 1 ou 2.")