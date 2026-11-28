import json
import socket
import threading
import time

DISCOVERY_PORT = 5001
BROADCAST_INTERVAL = 3.0   # Envoie une annonce toutes les 3 secondes
PEER_TIMEOUT = 10.0        # Considère un pair hors ligne après 10 secondes sans signal


class PeerDiscovery:
    """Service de découverte décentralisée des pairs sur le réseau local via UDP Broadcast."""

    def __init__(
        self,
        username: str,
        tcp_port: int = 5000,
        udp_port: int = DISCOVERY_PORT,
        on_peers_updated=None,
    ):
        self.username = username
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.on_peers_updated = on_peers_updated

        # Format interne : {"Pseudo": {"ip": "192.168.x.x", "tcp_port": 5000, "last_seen": timestamp}}
        self._peers = {}
        self._lock = threading.Lock()
        self._running = False

        self._send_sock = None
        self._recv_sock = None

    def start(self) -> None:
        """Démarre la diffusion UDP, l'écoute UDP et le nettoyage des pairs expirés."""
        if self._running:
            return
        self._running = True

        # Socket d'émission Broadcast
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Socket de réception sur toutes les interfaces (0.0.0.0)
        self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._recv_sock.bind(("0.0.0.0", self.udp_port))
        self._recv_sock.settimeout(1.0)

        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        print(f"[Discovery] Actif en UDP sur le port {self.udp_port} (Pseudo : {self.username})")

    def stop(self) -> None:
        """Envoie un signal de départ (BYE) et ferme les sockets UDP."""
        if not self._running:
            return
        self._running = False
        try:
            bye_msg = json.dumps({"type": "BYE", "username": self.username}).encode("utf-8")
            self._send_sock.sendto(bye_msg, ("255.255.255.255", self.udp_port))
        except OSError:
            pass

        for sock in (self._send_sock, self._recv_sock):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

    def get_online_peers(self) -> dict:
        """Retourne un dictionnaire simple {pseudo: ip} compatible avec AppWindow."""
        with self._lock:
            return {name: info["ip"] for name, info in self._peers.items()}

    def _notify_ui(self) -> None:
        if self.on_peers_updated:
            self.on_peers_updated(self.get_online_peers())

    def _broadcast_loop(self) -> None:
        """Annonce périodiquement sa présence à tout le sous-réseau local."""
        hello_payload = json.dumps(
            {
                "type": "HELLO",
                "username": self.username,
                "tcp_port": self.tcp_port,
            }
        ).encode("utf-8")

        while self._running:
            try:
                self._send_sock.sendto(hello_payload, ("255.255.255.255", self.udp_port))
            except OSError:
                pass
            time.sleep(BROADCAST_INTERVAL)

    def _listen_loop(self) -> None:
        """Écoute les paquets HELLO/BYE des autres machines du réseau local."""
        while self._running:
            try:
                data, addr = self._recv_sock.recvfrom(4096)
                sender_ip = addr[0]
                msg = json.loads(data.decode("utf-8"))

                peer_name = msg.get("username", "").strip()
                msg_type = msg.get("type")

                # Ignorer nos propres annonces
                if not peer_name or peer_name == self.username:
                    continue

                changed = False
                with self._lock:
                    if msg_type == "HELLO":
                        is_new = peer_name not in self._peers or self._peers[peer_name]["ip"] != sender_ip
                        self._peers[peer_name] = {
                            "ip": sender_ip,
                            "tcp_port": msg.get("tcp_port", 5000),
                            "last_seen": time.time(),
                        }
                        if is_new:
                            changed = True
                    elif msg_type == "BYE" and peer_name in self._peers:
                        del self._peers[peer_name]
                        changed = True

                if changed:
                    self._notify_ui()

            except socket.timeout:
                continue
            except Exception:
                continue

    def _cleanup_loop(self) -> None:
        """Supprime automatiquement les contacts silencieux depuis plus de PEER_TIMEOUT secondes."""
        while self._running:
            time.sleep(2.0)
            now = time.time()
            changed = False
            with self._lock:
                expired = [
                    name
                    for name, info in self._peers.items()
                    if (now - info["last_seen"]) > PEER_TIMEOUT
                ]
                for name in expired:
                    del self._peers[name]
                    changed = True

            if changed:
                self._notify_ui()


if __name__ == "__main__":
    pseudo = input("Pseudo pour le test UDP : ").strip() or "Moumine_Ali"
    discovery = PeerDiscovery(
        username=pseudo,
        on_peers_updated=lambda peers: print(f"[Pairs en ligne] {peers}"),
    )
    discovery.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        discovery.stop()