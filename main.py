import socket
import threading
import tkinter as tk
from tkinter import simpledialog

from ui.app_window import AppWindow
from core.transport import TransportServer, TransportClient, DEFAULT_TCP_PORT
from core.discovery import PeerDiscovery, DISCOVERY_PORT


def ask_session_username() -> str:
    """Demande le pseudo au démarrage avant d'ouvrir la fenêtre principale."""
    root = tk.Tk()
    root.withdraw()
    default_name = socket.gethostname()
    pseudo = simpledialog.askstring(
        "Messager LAN - Identification",
        "Entrez votre pseudo sur le réseau local :",
        initialvalue=default_name,
        parent=root,
    )
    root.destroy()
    return (pseudo or default_name).strip()


def main():
    username = ask_session_username()
    handle = f"@{username.lower().replace(' ', '_')}"

    client = TransportClient(sender_name=username, port=DEFAULT_TCP_PORT)

    # Callbacks déclenchés par l'interface graphique (envoi dans un thread pour ne pas figer l'UI)
    def handle_ui_send_message(target_ip: str, recipient_name: str, text: str):
        threading.Thread(
            target=client.send_message,
            args=(target_ip, text, recipient_name),
            daemon=True,
        ).start()

    def handle_ui_send_file(target_ip: str, file_path: str):
        threading.Thread(
            target=client.send_file,
            args=(target_ip, file_path),
            daemon=True,
        ).start()

    # Création de la fenêtre principale (thème clair)
    app = AppWindow(
        username=username,
        handle=handle,
        on_send_message=handle_ui_send_message,
        on_send_file=handle_ui_send_file,
    )

    # Callbacks réseau -> mise à jour sécurisée de l'interface via app.after()
    def on_network_message(meta: dict, sender_ip: str):
        sender = meta.get("sender", sender_ip)
        content = meta.get("content", "")

        def _update():
            if sender not in app.peers:
                app.peers[sender] = {"ip": sender_ip, "online": True}
                app._refresh_peer_list()
            app.append_message(sender, content, is_me=False)

        app.after(0, _update)

    def on_network_file(sender: str, sender_ip: str, filename: str, save_path: str, file_size: int, verified: bool):
        size_kb = max(0.1, file_size / 1024)

        def _update():
            if sender not in app.peers:
                app.peers[sender] = {"ip": sender_ip, "online": True}
                app._refresh_peer_list()
            app.append_file(
                peer_name=sender,
                filename=filename,
                size_str=f"{size_kb:.1f} KB",
                progress=1.0,
                verified=verified,
                is_me=False,
            )

        app.after(0, _update)

    def on_peers_changed(peers_dict: dict):
        app.after(0, lambda: app.update_online_peers(peers_dict))

    # Démarrage des moteurs réseau (TCP + UDP)
    server = TransportServer(
        port=DEFAULT_TCP_PORT,
        on_message_received=on_network_message,
        on_file_received=on_network_file,
    )
    server.start()

    discovery = PeerDiscovery(
        username=username,
        tcp_port=DEFAULT_TCP_PORT,
        udp_port=DISCOVERY_PORT,
        on_peers_updated=on_peers_changed,
    )
    discovery.start()

    # Fermeture propre lors du clic sur la croix de la fenêtre
    def on_closing():
        discovery.stop()
        server.stop()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()