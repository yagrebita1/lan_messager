import os
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

# Thème clair imposé
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")


class AppWindow(ctk.CTk):
    def __init__(
        self,
        username="Y. Grégoire Bihina",
        handle="yagrebita",
        on_send_message=None,
        on_send_file=None,
    ):
        super().__init__()

        self.username = username
        self.handle = handle
        self.on_send_message = on_send_message
        self.on_send_file = on_send_file

        self.title("Messager LAN")
        self.geometry("1020x640")
        self.minsize(880, 540)
        self.configure(fg_color="#FFFFFF")

        # État initial vide (alimenté dynamiquement par core/discovery.py)
        self.peers = {}  # Format attendu : {"Pseudo": {"ip": "192.168.x.x", "online": True}}
        self.active_peer = None
        self.chat_history = {}
        self.peer_buttons = {}

        # Grille principale : Sidebar fixe (270px) + Zone de discussion extensible
        self.grid_columnconfigure(0, weight=0, minsize=270)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_chat_area()

        # Affichage initial des états vides
        self._refresh_peer_list()
        self._render_empty_chat_state()

    # ==========================================================
    # COLONNE DE GAUCHE : SIDEBAR CONTACTS & PROFIL
    # ==========================================================
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, width=270, corner_radius=0, fg_color="#F8FAFC"
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(2, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # Titre principal
        title_lbl = ctk.CTkLabel(
            self.sidebar,
            text="Messager LAN",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#1D63DC",
            anchor="w",
        )
        title_lbl.grid(row=0, column=0, padx=18, pady=(20, 12), sticky="ew")

        # Barre de recherche
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_peer_list())
        self.search_entry = ctk.CTkEntry(
            self.sidebar,
            textvariable=self.search_var,
            placeholder_text="🔍 Rechercher un pair...",
            height=36,
            corner_radius=8,
            fg_color="#E2E8F0",
            border_width=0,
            text_color="#1E293B",
        )
        self.search_entry.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="ew")

        # Zone des utilisateurs connectés (ou message si vide)
        self.peers_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", corner_radius=0
        )
        self.peers_frame.grid(row=2, column=0, padx=6, pady=0, sticky="nsew")
        self.peers_frame.grid_columnconfigure(0, weight=1)

        # Pied de profil utilisateur local
        footer = ctk.CTkFrame(self.sidebar, fg_color="#F1F5F9", corner_radius=0, height=68)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(1, weight=1)

        avatar_me = ctk.CTkLabel(
            footer,
            text=self.username[0].upper(),
            width=38,
            height=38,
            corner_radius=19,
            fg_color="#1D63DC",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        avatar_me.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=14)

        name_me = ctk.CTkLabel(
            footer,
            text=f"{self.username}  ●",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#0F172A",
            anchor="w",
        )
        name_me.grid(row=0, column=1, sticky="sw", pady=(12, 0))

        handle_me = ctk.CTkLabel(
            footer,
            text=self.handle,
            font=ctk.CTkFont(size=11),
            text_color="#64748B",
            anchor="w",
        )
        handle_me.grid(row=1, column=1, sticky="nw", pady=(0, 12))

    def _refresh_peer_list(self):
        for widget in self.peers_frame.winfo_children():
            widget.destroy()
        self.peer_buttons.clear()

        query = self.search_var.get().strip().lower()
        filtered_peers = {
            name: info
            for name, info in self.peers.items()
            if not query or query in name.lower()
        }

        # État vide dans la barre latérale si personne n'est connecté
        if not filtered_peers:
            empty_msg = (
                "Aucun résultat pour cette recherche."
                if self.peers
                else "Aucun pair en ligne.\n\nEn attente d'appareils sur le réseau local (UDP)..."
            )
            empty_lbl = ctk.CTkLabel(
                self.peers_frame,
                text=empty_msg,
                font=ctk.CTkFont(size=12),
                text_color="#64748B",
                wraplength=220,
                justify="center",
            )
            empty_lbl.grid(row=0, column=0, padx=12, pady=40, sticky="ew")
            return

        colors = ["#0EA5E9", "#10B981", "#F97316", "#6366F1"]
        for row_idx, (name, info) in enumerate(filtered_peers.items()):
            is_selected = name == self.active_peer
            bg_color = "#E2E8F0" if is_selected else "transparent"

            item = ctk.CTkFrame(
                self.peers_frame, fg_color=bg_color, corner_radius=8, height=50
            )
            item.grid(row=row_idx, column=0, padx=4, pady=3, sticky="ew")
            item.grid_columnconfigure(1, weight=1)

            avatar = ctk.CTkLabel(
                item,
                text=name[0].upper(),
                width=34,
                height=34,
                corner_radius=17,
                fg_color=colors[row_idx % len(colors)],
                text_color="#FFFFFF",
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            avatar.grid(row=0, column=0, padx=(10, 10), pady=8)

            lbl = ctk.CTkLabel(
                item,
                text=name,
                font=ctk.CTkFont(size=13, weight="bold" if is_selected else "normal"),
                text_color="#0F172A",
                anchor="w",
            )
            lbl.grid(row=0, column=1, sticky="ew")

            dot_color = "#10B981" if info.get("online", True) else "#94A3B8"
            dot = ctk.CTkLabel(
                item, text="●", font=ctk.CTkFont(size=12), text_color=dot_color
            )
            dot.grid(row=0, column=2, padx=(6, 12))

            for w in (item, avatar, lbl, dot):
                w.bind("<Button-1>", lambda e, n=name: self.select_peer(n))

            self.peer_buttons[name] = item

    # ==========================================================
    # ZONE DE DROITE : EN-TÊTE, DISCUSSION & BARRE D'ENVOI
    # ==========================================================
    def _build_chat_area(self):
        self.chat_container = ctk.CTkFrame(
            self, fg_color="#FFFFFF", corner_radius=0
        )
        self.chat_container.grid(row=0, column=1, sticky="nsew")
        self.chat_container.grid_rowconfigure(1, weight=1)
        self.chat_container.grid_columnconfigure(0, weight=1)

        # En-tête supérieur
        self.header = ctk.CTkFrame(
            self.chat_container, fg_color="#FFFFFF", corner_radius=0, height=68
        )
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)

        self.header_avatar = ctk.CTkLabel(
            self.header,
            text="?",
            width=40,
            height=40,
            corner_radius=20,
            fg_color="#CBD5E1",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.header_avatar.grid(row=0, column=0, rowspan=2, padx=(20, 12), pady=14)

        self.header_name = ctk.CTkLabel(
            self.header,
            text="Aucune connexion active",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#0F172A",
            anchor="w",
        )
        self.header_name.grid(row=0, column=1, sticky="sw", pady=(12, 0))

        self.header_status = ctk.CTkLabel(
            self.header,
            text="Hors ligne • En attente d'un destinataire",
            font=ctk.CTkFont(size=12),
            text_color="#64748B",
            anchor="w",
        )
        self.header_status.grid(row=1, column=1, sticky="nw", pady=(0, 12))

        sep_top = ctk.CTkFrame(self.chat_container, height=1, fg_color="#E2E8F0")
        sep_top.grid(row=0, column=0, sticky="sew")

        # Zone centrale de messages
        self.messages_scroll = ctk.CTkScrollableFrame(
            self.chat_container, fg_color="#FFFFFF", corner_radius=0
        )
        self.messages_scroll.grid(row=1, column=0, padx=16, pady=10, sticky="nsew")
        self.messages_scroll.grid_columnconfigure(0, weight=1)

        # Barre inférieure de saisie
        input_bar = ctk.CTkFrame(
            self.chat_container, fg_color="#FFFFFF", corner_radius=0, height=66
        )
        input_bar.grid(row=2, column=0, sticky="ew")
        input_bar.grid_columnconfigure(0, weight=1)

        sep_bot = ctk.CTkFrame(self.chat_container, height=1, fg_color="#E2E8F0")
        sep_bot.grid(row=2, column=0, sticky="new")

        entry_wrapper = ctk.CTkFrame(
            input_bar,
            fg_color="#F8FAFC",
            border_width=1,
            border_color="#CBD5E1",
            corner_radius=10,
            height=42,
        )
        entry_wrapper.grid(row=0, column=0, padx=(18, 10), pady=12, sticky="ew")
        entry_wrapper.grid_columnconfigure(0, weight=1)

        self.msg_entry = ctk.CTkEntry(
            entry_wrapper,
            placeholder_text="Sélectionnez un utilisateur pour écrire...",
            border_width=0,
            fg_color="transparent",
            text_color="#0F172A",
            font=ctk.CTkFont(size=13),
        )
        self.msg_entry.grid(row=0, column=0, padx=(10, 4), pady=4, sticky="ew")
        self.msg_entry.bind("<Return>", lambda e: self._handle_send_text())

        self.attach_btn = ctk.CTkButton(
            entry_wrapper,
            text="📎",
            width=32,
            height=30,
            fg_color="transparent",
            hover_color="#E2E8F0",
            text_color="#475569",
            font=ctk.CTkFont(size=16),
            command=self._handle_attach_file,
        )
        self.attach_btn.grid(row=0, column=1, padx=(0, 6), pady=4)

        self.send_btn = ctk.CTkButton(
            input_bar,
            text="Envoyer",
            width=96,
            height=42,
            corner_radius=10,
            fg_color="#1D63DC",
            hover_color="#1E40AF",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._handle_send_text,
        )
        self.send_btn.grid(row=0, column=1, padx=(0, 18), pady=12)

    # ==========================================================
    # GESTION DES ÉTATS VIDES & CONVERSATIONS ACTIVES
    # ==========================================================
    def _set_input_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.msg_entry.configure(
            state=state,
            placeholder_text="Écrire un message..."
            if enabled
            else "Sélectionnez un utilisateur pour écrire...",
        )
        self.attach_btn.configure(state=state)
        self.send_btn.configure(state=state)

    def _render_empty_chat_state(self):
        """Affiche l'écran d'accueil vide lorsqu'aucun pair n'est sélectionné."""
        self._set_input_enabled(False)
        for widget in self.messages_scroll.winfo_children():
            widget.destroy()

        empty_box = ctk.CTkFrame(
            self.messages_scroll,
            fg_color="#F8FAFC",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=14,
        )
        empty_box.grid(row=0, column=0, padx=60, pady=120, sticky="ew")

        title = ctk.CTkLabel(
            empty_box,
            text="Bienvenue sur Messager LAN",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#0F172A",
        )
        title.pack(padx=24, pady=(24, 8))

        desc = ctk.CTkLabel(
            empty_box,
            text="Aucune discussion active pour le moment.\n"
            "Dès qu'un appareil apparaît dans la liste de gauche, cliquez dessus pour "
            "échanger des messages instantanés ou transférer des fichiers vérifiés SHA-256.",
            font=ctk.CTkFont(size=13),
            text_color="#64748B",
            wraplength=420,
            justify="center",
        )
        desc.pack(padx=24, pady=(0, 24))

    def select_peer(self, peer_name):
        if peer_name not in self.peers:
            return
        self.active_peer = peer_name
        self._refresh_peer_list()
        self._set_input_enabled(True)

        info = self.peers[peer_name]
        self.header_avatar.configure(text=peer_name[0].upper(), fg_color="#10B981")
        self.header_name.configure(text=f"{peer_name}  ●")
        self.header_status.configure(
            text=f"Connecté en P2P ({info.get('ip', 'LAN')})"
        )
        self._render_messages()

    def _render_messages(self):
        for widget in self.messages_scroll.winfo_children():
            widget.destroy()

        history = self.chat_history.get(self.active_peer, [])
        if not history:
            no_msg = ctk.CTkLabel(
                self.messages_scroll,
                text=f"Début de votre échange P2P avec {self.active_peer}.\nEnvoyez un premier message ou joignez un fichier.",
                font=ctk.CTkFont(size=13),
                text_color="#64748B",
                justify="center",
            )
            no_msg.grid(row=0, column=0, pady=140, sticky="ew")
            return

        for idx, item in enumerate(history):
            if item["type"] == "text":
                self._add_text_bubble(idx, item["text"], item["is_me"])
            elif item["type"] == "file":
                self._add_file_card(
                    idx,
                    item["filename"],
                    item["size_str"],
                    item.get("progress", 1.0),
                    item.get("verified", True),
                    item["is_me"],
                )

    def _add_text_bubble(self, row, text, is_me):
        wrapper = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        wrapper.grid(row=row, column=0, pady=6, sticky="ew")

        bubble_bg = "#1D63DC" if is_me else "#E2E8F0"
        text_col = "#FFFFFF" if is_me else "#0F172A"
        side = "right" if is_me else "left"

        bubble = ctk.CTkFrame(wrapper, fg_color=bubble_bg, corner_radius=14)
        bubble.pack(side=side, padx=8)

        lbl = ctk.CTkLabel(
            bubble,
            text=text,
            text_color=text_col,
            font=ctk.CTkFont(size=13),
            wraplength=430,
            justify="left",
        )
        lbl.pack(padx=14, pady=10)

    def _add_file_card(self, row, filename, size_str, progress, verified, is_me):
        wrapper = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        wrapper.grid(row=row, column=0, pady=8, sticky="ew")

        side = "right" if is_me else "left"
        card = ctk.CTkFrame(
            wrapper,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            corner_radius=12,
            width=360,
        )
        card.pack(side=side, padx=8)
        card.grid_columnconfigure(1, weight=1)

        icon_lbl = ctk.CTkLabel(
            card, text="📄", font=ctk.CTkFont(size=24), text_color="#475569"
        )
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=(12, 4))

        name_lbl = ctk.CTkLabel(
            card,
            text=filename,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#0F172A",
            anchor="w",
        )
        name_lbl.grid(row=0, column=1, columnspan=2, padx=(0, 14), pady=(12, 0), sticky="w")

        size_lbl = ctk.CTkLabel(
            card,
            text=size_str,
            font=ctk.CTkFont(size=11),
            text_color="#64748B",
            anchor="w",
        )
        size_lbl.grid(row=1, column=1, columnspan=2, padx=(0, 14), pady=(0, 6), sticky="w")

        bar = ctk.CTkProgressBar(
            card,
            width=250,
            height=8,
            corner_radius=4,
            progress_color="#10B981",
            fg_color="#E2E8F0",
        )
        bar.set(progress)
        bar.grid(row=2, column=0, columnspan=2, padx=(14, 8), pady=4, sticky="ew")

        pct_lbl = ctk.CTkLabel(
            card,
            text=f"{int(progress * 100)}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#0F172A",
        )
        pct_lbl.grid(row=2, column=2, padx=(0, 14), pady=4)

        badge_text = (
            "✔  Transfert réussi • Vérifié SHA-256"
            if verified
            else "⏳ Transfert en cours..."
        )
        badge_color = "#10B981" if verified else "#64748B"
        badge = ctk.CTkLabel(
            card,
            text=badge_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=badge_color,
            anchor="w",
        )
        badge.grid(row=3, column=0, columnspan=3, padx=14, pady=(2, 12), sticky="w")

    # ==========================================================
    # MÉTHODES PUBLIQUES POUR L'INTÉGRATION RÉSEAU
    # ==========================================================
    def _handle_send_text(self):
        if not self.active_peer:
            return
        text = self.msg_entry.get().strip()
        if not text:
            return
        self.msg_entry.delete(0, "end")
        self.append_message(self.active_peer, text, is_me=True)

        if self.on_send_message:
            target_ip = self.peers[self.active_peer]["ip"]
            self.on_send_message(target_ip, self.active_peer, text)

    def _handle_attach_file(self):
        if not self.active_peer:
            return
        file_path = filedialog.askopenfilename(title="Choisir un fichier à envoyer")
        if not file_path:
            return
        filename = os.path.basename(file_path)
        size_kb = max(0.1, os.path.getsize(file_path) / 1024)
        self.append_file(
            self.active_peer,
            filename,
            f"{size_kb:.1f} KB",
            progress=1.0,
            verified=True,
            is_me=True,
        )

        if self.on_send_file:
            target_ip = self.peers[self.active_peer]["ip"]
            self.on_send_file(target_ip, file_path)

    def append_message(self, peer_name, text, is_me=False):
        self.chat_history.setdefault(peer_name, []).append(
            {"type": "text", "text": text, "is_me": is_me}
        )
        if peer_name == self.active_peer:
            self._render_messages()

    def append_file(
        self, peer_name, filename, size_str, progress=1.0, verified=True, is_me=False
    ):
        self.chat_history.setdefault(peer_name, []).append(
            {
                "type": "file",
                "filename": filename,
                "size_str": size_str,
                "progress": progress,
                "verified": verified,
                "is_me": is_me,
            }
        )
        if peer_name == self.active_peer:
            self._render_messages()

    def update_online_peers(self, peers_dict):
        """Appelée par core/discovery.py pour mettre à jour la liste des pairs."""
        self.peers = {
            name: {"ip": ip, "online": True} for name, ip in peers_dict.items()
        }
        for name in self.peers:
            self.chat_history.setdefault(name, [])

        # Si le pair actif s'est déconnecté, repasser à l'état vide
        if self.active_peer and self.active_peer not in self.peers:
            self.active_peer = None
            self.header_avatar.configure(text="?", fg_color="#CBD5E1")
            self.header_name.configure(text="Aucune connexion active")
            self.header_status.configure(text="Hors ligne • En attente d'un destinataire")
            self._render_empty_chat_state()

        self._refresh_peer_list()


if __name__ == "__main__":
    app = AppWindow()
    app.mainloop()