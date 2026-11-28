import os
import json
import socket
import struct
import threading
import time
from core.crypto_utils import (
    compute_sha256_file,
    verify_file_integrity,
    encrypt_payload,
    decrypt_payload,
)

HEADER_SIZE = 4          # 4 octets Big-Endian (>I) pour la taille de chaque trame
CHUNK_SIZE = 65536       # Blocs de 64 Ko pour le transfert de fichiers
DEFAULT_TCP_PORT = 55000


def _recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Lit exactement num_bytes depuis le socket TCP (gère la fragmentation réseau)."""
    buffer = bytearray()
    while len(buffer) < num_bytes:
        packet = sock.recv(num_bytes - len(buffer))
        if not packet:
            raise ConnectionError("Connexion fermée prématurément par le pair.")
        buffer.extend(packet)
    return bytes(buffer)


def send_frame(sock: socket.socket, raw_data: bytes, encrypt: bool = True) -> None:
    """Encapsule les données avec un en-tête de 4 octets Big-Endian et les envoie."""
    payload = encrypt_payload(raw_data) if encrypt else raw_data
    header = struct.pack(">I", len(payload))
    sock.sendall(header + payload)


def recv_frame(sock: socket.socket, decrypt: bool = True) -> bytes:
    """Lit l'en-tête de 4 octets puis extrait exactement la trame complète."""
    header = _recv_exact(sock, HEADER_SIZE)
    (payload_length,) = struct.unpack(">I", header)
    payload = _recv_exact(sock, payload_length)
    return decrypt_payload(payload) if decrypt else payload


class TransportServer:
    """Serveur TCP multi-clients écoutant les messages instantanés et les fichiers entrants."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_TCP_PORT,
        download_dir: str = "downloads",
        on_message_received=None,
        on_file_progress=None,
        on_file_received=None,
    ):
        self.host = host
        self.port = port
        self.download_dir = download_dir
        self.on_message_received = on_message_received
        self.on_file_progress = on_file_progress
        self.on_file_received = on_file_received

        os.makedirs(self.download_dir, exist_ok=True)
        self._server_socket = None
        self._running = False
        self._thread = None

    def start(self) -> None:
        """Démarre l'écoute TCP en arrière-plan (thread daemon)."""
        if self._running:
            return
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(10)
        self._running = True

        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        print(f"[TransportServer] En écoute sur {self.host}:{self.port}")

    def stop(self) -> None:
        """Arrête proprement le serveur TCP."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client_sock, addr = self._server_socket.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr[0]),
                    daemon=True,
                ).start()
            except OSError:
                break

    def _handle_client(self, client_sock: socket.socket, sender_ip: str) -> None:
        try:
            with client_sock:
                # 1. Lecture de la trame d'en-tête JSON (métadonnées du message ou du fichier)
                meta_bytes = recv_frame(client_sock)
                meta = json.loads(meta_bytes.decode("utf-8"))
                msg_type = meta.get("type")

                if msg_type == "chat_message":
                    if self.on_message_received:
                        self.on_message_received(meta, sender_ip)
                    else:
                        print(f"\n[{meta.get('sender', sender_ip)}] : {meta.get('content')}")

                elif msg_type == "file_transfer":
                    self._receive_file_stream(client_sock, meta, sender_ip)

        except Exception as e:
            print(f"[TransportServer] Erreur avec {sender_ip} : {e}")

    def _receive_file_stream(
        self, client_sock: socket.socket, meta: dict, sender_ip: str
    ) -> None:
        """Reçoit un fichier bloc par bloc et valide son empreinte SHA-256."""
        sender = meta.get("sender", sender_ip)
        filename = os.path.basename(meta.get("filename", "fichier_recu.bin"))
        file_size = int(meta.get("file_size", 0))
        expected_sha256 = meta.get("sha256", "")

        save_path = os.path.join(self.download_dir, filename)
        # Évite d'écraser un fichier existant portant le même nom
        if os.path.exists(save_path):
            base, ext = os.path.splitext(filename)
            save_path = os.path.join(self.download_dir, f"{base}_{int(time.time())}{ext}")

        received_bytes = 0
        with open(save_path, "wb") as f:
            while received_bytes < file_size:
                chunk = recv_frame(client_sock)
                if not chunk:
                    break
                f.write(chunk)
                received_bytes += len(chunk)

                if self.on_file_progress and file_size > 0:
                    progress = min(1.0, received_bytes / file_size)
                    self.on_file_progress(sender, filename, progress)

        # Contrôle final d'intégrité SHA-256
        verified = verify_file_integrity(save_path, expected_sha256)

        if self.on_file_received:
            self.on_file_received(
                sender=sender,
                sender_ip=sender_ip,
                filename=filename,
                save_path=save_path,
                file_size=file_size,
                verified=verified,
            )
        else:
            status = "VÉRIFIÉ SHA-256" if verified else "CORROMPU (SHA-256 invalide)"
            print(f"\n[Fichier reçu de {sender}] {filename} ({file_size} octets) -> {status}")


class TransportClient:
    """Client TCP chargé d'envoyer des messages et des fichiers découpés en blocs."""

    def __init__(self, sender_name: str = "yagrebita", port: int = DEFAULT_TCP_PORT):
        self.sender_name = sender_name
        self.port = port

    def send_message(self, target_ip: str, content: str, recipient: str = "") -> bool:
        """Envoie un message texte instantané à l'adresse IP cible."""
        payload = {
            "type": "chat_message",
            "sender": self.sender_name,
            "recipient": recipient,
            "content": content,
            "timestamp": time.time(),
        }
        try:
            with socket.create_connection((target_ip, self.port), timeout=5.0) as sock:
                send_frame(sock, json.dumps(payload).encode("utf-8"))
            return True
        except Exception as e:
            print(f"[TransportClient] Échec d'envoi du message vers {target_ip} : {e}")
            return False

    def send_file(
        self,
        target_ip: str,
        file_path: str,
        recipient: str = "",
        on_progress=None,
    ) -> dict:
        """
        Découpe un fichier en blocs de 64 Ko, calcule son SHA-256 et l'envoie via TCP.
        Retourne un dictionnaire avec le statut et l'empreinte SHA-256.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Fichier introuvable : {file_path}")

        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        sha256_hash = compute_sha256_file(file_path)

        meta = {
            "type": "file_transfer",
            "sender": self.sender_name,
            "recipient": recipient,
            "filename": filename,
            "file_size": file_size,
            "sha256": sha256_hash,
            "timestamp": time.time(),
        }

        try:
            with socket.create_connection((target_ip, self.port), timeout=10.0) as sock:
                # 1. Envoi des métadonnées + empreinte SHA-256
                send_frame(sock, json.dumps(meta).encode("utf-8"))

                # 2. Envoi du fichier bloc par bloc (64 Ko)
                sent_bytes = 0
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        send_frame(sock, chunk)
                        sent_bytes += len(chunk)

                        if on_progress and file_size > 0:
                            on_progress(min(1.0, sent_bytes / file_size))

            return {
                "success": True,
                "filename": filename,
                "file_size": file_size,
                "sha256": sha256_hash,
            }
        except Exception as e:
            print(f"[TransportClient] Échec du transfert de fichier vers {target_ip} : {e}")
            return {"success": False, "error": str(e)}


# ==========================================================
# MODE TEST INTERACTIF (Messages + Fichiers sur 2 PC ou local)
# ==========================================================
if __name__ == "__main__":
    print("=== TEST MOTEUR TRANSPORT TCP + SHA-256 ===")
    pseudo = input("Votre pseudo (ex: yagrebita) : ").strip() or "yagrebita"
    port = int(input("Port d'écoute (défaut 5000) : ").strip() or "5000")

    server = TransportServer(port=port)
    server.start()

    client = TransportClient(sender_name=pseudo, port=port)
    print("\nCommandes disponibles :")
    print("  1. Envoyer un message texte")
    print("  2. Envoyer un fichier (avec vérification SHA-256)")
    print("  3. Quitter\n")

    try:
        while True:
            choix = input("Choix (1/2/3) > ").strip()
            if choix == "1":
                ip = input("IP destinataire (ex: 127.0.0.1) : ").strip() or "127.0.0.1"
                msg = input("Message : ")
                if client.send_message(ip, msg):
                    print("✔ Message envoyé.")
            elif choix == "2":
                ip = input("IP destinataire (ex: 127.0.0.1) : ").strip() or "127.0.0.1"
                chemin = input("Chemin du fichier (ex: maquette.jpg) : ").strip()
                res = client.send_file(
                    ip,
                    chemin,
                    on_progress=lambda p: print(f"\rProgression : {int(p * 100)}%", end=""),
                )
                print()
                if res.get("success"):
                    print(f"✔ Fichier envoyé ! SHA-256 : {res['sha256']}")
            elif choix == "3":
                break
    finally:
        server.stop()