import os
import sys
import math
import time
import random
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, simpledialog
import customtkinter as ctk

# Thème clair imposé
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# ==========================================================
# OUTILS GRAPHIQUES POUR L'ANIMATION D'ACCUEIL
# ==========================================================
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lerp_color(c1, c2, k):
    k = max(0.0, min(1.0, k))
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _rrect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _get_file_icon(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".mp3", ".wav", ".ogg", ".flac", ".m4a"}:
        return "🎵"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "🖼️"
    if ext in {".mp4", ".mkv", ".avi", ".mov"}:
        return "🎬"
    if ext in {".zip", ".rar", ".7z", ".tar", ".gz"}:
        return "📦"
    if ext in {".pdf", ".doc", ".docx", ".txt", ".md"}:
        return "📄"
    return "📁"


def _open_local_file(path: str):
    if not path or not os.path.exists(path):
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class AppWindow(ctk.CTk):
    def __init__(
        self,
        username="Y. Grégoire Bihina",
        handle="@yagrebita",
        on_send_message=None,
        on_send_file=None,
    ):
        super().__init__()

        self.username = username
        self.handle = handle
        self.on_send_message = on_send_message
        self.on_send_file = on_send_file

        self.title("Messager LAN — P2P Sécurisé")
        self.geometry("1100x680")
        self.minsize(920, 560)
        self.configure(fg_color="#FFFFFF")

        # État dynamique
        self.peers = {}          # {"Pseudo": {"ip": "192.168.x.x", "online": True}}
        self.active_peer = None
        self.chat_history = {}   # {"Pseudo": [items...]}
        self.unread_counts = {}  # {"Pseudo": int}
        self.file_widgets = {}   # {(peer_name, filename): {"bar": ..., "pct": ..., "badge": ...}}

        # État de la démo animée
        self._demo_token = 0          # change à chaque arrêt/redémarrage -> invalide les anciens callbacks
        self._demo_row = 0
        self._typing_wrapper = None

        # Grille principale : Sidebar (290px) + Zone de discussion extensible
        self.grid_columnconfigure(0, weight=0, minsize=290)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_chat_area()

        self._refresh_peer_list()
        self._render_empty_chat_state()

    # ==========================================================
    # COLONNE DE GAUCHE : SIDEBAR CONTACTS, RECHERCHE & PROFIL
    # ==========================================================
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, width=290, corner_radius=0, fg_color="#F8FAFC"
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(3, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # Séparateur vertical droit
        v_sep = ctk.CTkFrame(self.sidebar, width=1, fg_color="#E2E8F0")
        v_sep.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

        # En-tête de marque + bouton ajout manuel IP
        brand_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_row.grid(row=0, column=0, padx=18, pady=(20, 12), sticky="ew")
        brand_row.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(
            brand_row,
            text="Messager LAN",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#1D63DC",
            anchor="w",
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        add_ip_btn = ctk.CTkButton(
            brand_row,
            text="+ IP",
            width=48,
            height=28,
            corner_radius=8,
            fg_color="#E0E7FF",
            hover_color="#C7D2FE",
            text_color="#1D63DC",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._prompt_manual_peer,
        )
        add_ip_btn.grid(row=0, column=1, sticky="e")

        # Barre de recherche
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_peer_list())
        self.search_entry = ctk.CTkEntry(
            self.sidebar,
            textvariable=self.search_var,
            placeholder_text="🔍  Rechercher un pair...",
            height=38,
            corner_radius=10,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E2E8F0",
            text_color="#0F172A",
            font=ctk.CTkFont(size=13),
        )
        self.search_entry.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")

        # Sous-titre section contacts
        self.section_lbl = ctk.CTkLabel(
            self.sidebar,
            text="APPAREILS SUR LE RÉSEAU (0)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#64748B",
            anchor="w",
        )
        self.section_lbl.grid(row=2, column=0, padx=20, pady=(2, 6), sticky="ew")

        # Liste scrollable des pairs
        self.peers_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", corner_radius=0
        )
        self.peers_frame.grid(row=3, column=0, padx=8, pady=0, sticky="nsew")
        self.peers_frame.grid_columnconfigure(0, weight=1)

        # Carte profil utilisateur local en bas
        footer_border = ctk.CTkFrame(self.sidebar, height=1, fg_color="#E2E8F0")
        footer_border.grid(row=4, column=0, sticky="ew")

        footer = ctk.CTkFrame(self.sidebar, fg_color="#F1F5F9", corner_radius=0, height=72)
        footer.grid(row=5, column=0, sticky="ew")
        footer.grid_columnconfigure(1, weight=1)

        avatar_me = ctk.CTkLabel(
            footer,
            text=self.username[0].upper(),
            width=40,
            height=40,
            corner_radius=20,
            fg_color="#1D63DC",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        avatar_me.grid(row=0, column=0, rowspan=2, padx=(16, 12), pady=15)

        name_me = ctk.CTkLabel(
            footer,
            text=self.username,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#0F172A",
            anchor="w",
        )
        name_me.grid(row=0, column=1, sticky="sw", pady=(14, 0))

        status_me = ctk.CTkLabel(
            footer,
            text=f"● En ligne  •  {self.handle}",
            font=ctk.CTkFont(size=11),
            text_color="#10B981",
            anchor="w",
        )
        status_me.grid(row=1, column=1, sticky="nw", pady=(0, 14))

    def _prompt_manual_peer(self):
        ip = simpledialog.askstring(
            "Connexion directe P2P",
            "Entrez l'adresse IP locale du pair (ex: 192.168.43.1) :",
            parent=self,
        )
        if not ip or not ip.strip():
            return
        ip = ip.strip()
        name = simpledialog.askstring(
            "Nom du contact",
            "Entrez un nom pour cet appareil :",
            initialvalue=f"Pair_{ip.split('.')[-1]}",
            parent=self,
        )
        peer_name = (name or f"Pair_{ip.split('.')[-1]}").strip()
        self.peers[peer_name] = {"ip": ip, "online": True}
        self.chat_history.setdefault(peer_name, [])
        self.select_peer(peer_name)

    def _refresh_peer_list(self):
        for widget in self.peers_frame.winfo_children():
            widget.destroy()

        self.section_lbl.configure(
            text=f"APPAREILS SUR LE RÉSEAU ({len(self.peers)})"
        )

        query = self.search_var.get().strip().lower()
        filtered_peers = {
            name: info
            for name, info in self.peers.items()
            if not query or query in name.lower() or query in info.get("ip", "")
        }

        if not filtered_peers:
            empty_msg = (
                "Aucun appareil ne correspond à votre recherche."
                if self.peers
                else "Aucun pair détecté.\n\nEn attente d'annonces UDP sur le réseau local ou cliquez sur « + IP »."
            )
            empty_card = ctk.CTkFrame(
                self.peers_frame,
                fg_color="#FFFFFF",
                border_width=1,
                border_color="#E2E8F0",
                corner_radius=12,
            )
            empty_card.grid(row=0, column=0, padx=8, pady=24, sticky="ew")

            ctk.CTkLabel(
                empty_card,
                text="📡",
                font=ctk.CTkFont(size=24),
            ).pack(pady=(16, 4))

            ctk.CTkLabel(
                empty_card,
                text=empty_msg,
                font=ctk.CTkFont(size=12),
                text_color="#64748B",
                wraplength=215,
                justify="center",
            ).pack(padx=14, pady=(0, 16))
            return

        avatar_palette = ["#0EA5E9", "#10B981", "#F59E0B", "#6366F1", "#EC4899"]
        for row_idx, (name, info) in enumerate(filtered_peers.items()):
            is_selected = name == self.active_peer
            bg_color = "#EFF6FF" if is_selected else "transparent"
            border_col = "#BFDBFE" if is_selected else "#F8FAFC"

            item = ctk.CTkFrame(
                self.peers_frame,
                fg_color=bg_color,
                border_width=1,
                border_color=border_col,
                corner_radius=12,
                height=58,
            )
            item.grid(row=row_idx, column=0, padx=4, pady=3, sticky="ew")
            item.grid_columnconfigure(1, weight=1)

            avatar = ctk.CTkLabel(
                item,
                text=name[0].upper(),
                width=38,
                height=38,
                corner_radius=19,
                fg_color=avatar_palette[row_idx % len(avatar_palette)],
                text_color="#FFFFFF",
                font=ctk.CTkFont(size=14, weight="bold"),
            )
            avatar.grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=10)

            name_lbl = ctk.CTkLabel(
                item,
                text=name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#1D63DC" if is_selected else "#0F172A",
                anchor="w",
            )
            name_lbl.grid(row=0, column=1, sticky="sw", pady=(9, 0))

            ip_lbl = ctk.CTkLabel(
                item,
                text=info.get("ip", "LAN"),
                font=ctk.CTkFont(size=11),
                text_color="#64748B",
                anchor="w",
            )
            ip_lbl.grid(row=1, column=1, sticky="nw", pady=(0, 9))

            unread = self.unread_counts.get(name, 0)
            if unread > 0 and not is_selected:
                badge = ctk.CTkLabel(
                    item,
                    text=str(unread),
                    width=22,
                    height=22,
                    corner_radius=11,
                    fg_color="#1D63DC",
                    text_color="#FFFFFF",
                    font=ctk.CTkFont(size=11, weight="bold"),
                )
                badge.grid(row=0, column=2, rowspan=2, padx=(6, 12))
            else:
                dot = ctk.CTkLabel(
                    item,
                    text="●",
                    font=ctk.CTkFont(size=11),
                    text_color="#10B981",
                )
                dot.grid(row=0, column=2, rowspan=2, padx=(6, 14))

            for w in item.winfo_children() + [item]:
                w.bind("<Button-1>", lambda e, n=name: self.select_peer(n))

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
            self.chat_container, fg_color="#FFFFFF", corner_radius=0, height=72
        )
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)

        self.header_avatar = ctk.CTkLabel(
            self.header,
            text="?",
            width=42,
            height=42,
            corner_radius=21,
            fg_color="#E2E8F0",
            text_color="#64748B",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.header_avatar.grid(row=0, column=0, rowspan=2, padx=(24, 14), pady=15)

        self.header_name = ctk.CTkLabel(
            self.header,
            text="Aucune conversation sélectionnée",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#0F172A",
            anchor="w",
        )
        self.header_name.grid(row=0, column=1, sticky="sw", pady=(14, 0))

        self.header_status = ctk.CTkLabel(
            self.header,
            text="En attente d'un appareil sur le réseau local",
            font=ctk.CTkFont(size=12),
            text_color="#64748B",
            anchor="w",
        )
        self.header_status.grid(row=1, column=1, sticky="nw", pady=(0, 14))

        self.security_pill = ctk.CTkLabel(
            self.header,
            text="🔒  SHA-256 + Chiffrement LAN",
            fg_color="#F1F5F9",
            text_color="#475569",
            corner_radius=8,
            font=ctk.CTkFont(size=11, weight="bold"),
            padx=12,
            height=28,
        )
        self.security_pill.grid(row=0, column=2, rowspan=2, padx=24)

        sep_top = ctk.CTkFrame(self.chat_container, height=1, fg_color="#E2E8F0")
        sep_top.grid(row=0, column=0, sticky="sew")

        # Zone centrale de messages
        self.messages_scroll = ctk.CTkScrollableFrame(
            self.chat_container, fg_color="#F8FAFC", corner_radius=0
        )
        self.messages_scroll.grid(row=1, column=0, sticky="nsew")
        self.messages_scroll.grid_columnconfigure(0, weight=1)

        # Barre inférieure de saisie
        sep_bot = ctk.CTkFrame(self.chat_container, height=1, fg_color="#E2E8F0")
        sep_bot.grid(row=2, column=0, sticky="new")

        input_bar = ctk.CTkFrame(
            self.chat_container, fg_color="#FFFFFF", corner_radius=0, height=74
        )
        input_bar.grid(row=2, column=0, sticky="ew")
        input_bar.grid_columnconfigure(1, weight=1)

        self.attach_btn = ctk.CTkButton(
            input_bar,
            text="📎",
            width=42,
            height=42,
            corner_radius=12,
            fg_color="#F1F5F9",
            hover_color="#E2E8F0",
            text_color="#334155",
            font=ctk.CTkFont(size=18),
            command=self._handle_attach_file,
        )
        self.attach_btn.grid(row=0, column=0, padx=(20, 10), pady=16)

        entry_wrapper = ctk.CTkFrame(
            input_bar,
            fg_color="#F8FAFC",
            border_width=1,
            border_color="#CBD5E1",
            corner_radius=12,
            height=42,
        )
        entry_wrapper.grid(row=0, column=1, padx=(0, 10), pady=16, sticky="ew")
        entry_wrapper.grid_columnconfigure(0, weight=1)

        self.msg_entry = ctk.CTkEntry(
            entry_wrapper,
            placeholder_text="Sélectionnez un appareil à gauche pour démarrer...",
            border_width=0,
            fg_color="transparent",
            text_color="#0F172A",
            font=ctk.CTkFont(size=13),
        )
        self.msg_entry.grid(row=0, column=0, padx=14, pady=5, sticky="ew")
        self.msg_entry.bind("<Return>", lambda e: self._handle_send_text())

        self.send_btn = ctk.CTkButton(
            input_bar,
            text="Envoyer  ➤",
            width=112,
            height=42,
            corner_radius=12,
            fg_color="#1D63DC",
            hover_color="#1E40AF",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._handle_send_text,
        )
        self.send_btn.grid(row=0, column=2, padx=(0, 20), pady=16)

    # ==========================================================
    # GESTION DES ÉTATS VIDES & CONVERSATIONS ACTIVES
    # ==========================================================
    def _set_input_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.msg_entry.configure(
            state=state,
            placeholder_text=f"Écrire un message à {self.active_peer}..."
            if enabled
            else "Sélectionnez un appareil à gauche pour démarrer...",
        )
        self.attach_btn.configure(state=state)
        self.send_btn.configure(state=state)

    def _render_empty_chat_state(self):
        """Écran d'accueil : titre + démo de chat animée (fonctionne sans aucune connexion)."""
        self._set_input_enabled(False)
        self._stop_demo()
        self.file_widgets.clear()
        for widget in self.messages_scroll.winfo_children():
            widget.destroy()

        card = ctk.CTkFrame(
            self.messages_scroll,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=16,
        )
        card.grid(row=0, column=0, padx=60, pady=(24, 14), sticky="ew")

        ctk.CTkLabel(
            card,
            text="💬",
            font=ctk.CTkFont(size=30),
        ).pack(pady=(18, 4))

        ctk.CTkLabel(
            card,
            text="Messagerie Locale Instantanée & Transfert P2P",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#0F172A",
        ).pack(padx=24, pady=(0, 6))

        ctk.CTkLabel(
            card,
            text="Choisissez un appareil connecté dans la colonne de gauche pour envoyer des messages chiffrés "
            "ou partager des fichiers avec vérification automatique d'empreinte SHA-256.",
            font=ctk.CTkFont(size=13),
            text_color="#64748B",
            wraplength=440,
            justify="center",
        ).pack(padx=32, pady=(0, 10))

        ctk.CTkLabel(
            card,
            text="📴  Aperçu animé  •  100 % local, aucune connexion requise",
            fg_color="#EFF6FF",
            text_color="#1D63DC",
            corner_radius=8,
            font=ctk.CTkFont(size=11, weight="bold"),
            padx=12,
            height=26,
        ).pack(pady=(0, 18))

        self._start_demo()

    def select_peer(self, peer_name):
        if peer_name not in self.peers:
            return
        self._stop_demo()
        self.active_peer = peer_name
        self.unread_counts[peer_name] = 0
        self._refresh_peer_list()
        self._set_input_enabled(True)

        info = self.peers[peer_name]
        self.header_avatar.configure(
            text=peer_name[0].upper(), fg_color="#10B981", text_color="#FFFFFF"
        )
        self.header_name.configure(text=peer_name)
        self.header_status.configure(
            text=f"● Connecté en P2P  •  IP {info.get('ip', 'LAN')}",
            text_color="#10B981",
        )
        self.security_pill.configure(
            text="✔  Canal P2P Actif", fg_color="#ECFDF5", text_color="#059669"
        )
        self._render_messages()
        self.msg_entry.focus_set()

    def _scroll_to_bottom(self):
        self.update_idletasks()
        try:
            self.messages_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ==========================================================
    # ANIMATION D'ACCUEIL : deux appareils qui s'échangent des messages
    # (dessinée sur un Canvas, 100 % locale, aucune connexion requise)
    # ==========================================================
    ANIM_CYCLE = 8.0
    ANIM_FLIGHT = 1.5
    ANIM_EVENTS = [("A", "B", 1.0), ("B", "A", 5.0)]  # (émetteur, récepteur, début en s)
    ANIM_BLUE = "#1D63DC"
    ANIM_GREEN = "#10B981"

    def _stop_demo(self):
        """Arrête l'animation en cours (invalide les callbacks planifiés)."""
        self._demo_token += 1

    def _start_demo(self):
        token = self._demo_token

        stage = ctk.CTkFrame(
            self.messages_scroll,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#E2E8F0",
            corner_radius=16,
        )
        stage.grid(row=1, column=0, padx=60, pady=(0, 24), sticky="ew")

        self._anim_canvas = tk.Canvas(
            stage, height=270, bg="#FFFFFF", highlightthickness=0
        )
        self._anim_canvas.pack(fill="x", padx=12, pady=(12, 2))

        ctk.CTkLabel(
            stage,
            text="Messages et fichiers échangés directement entre appareils du réseau local",
            font=ctk.CTkFont(size=12),
            text_color="#64748B",
        ).pack(pady=(0, 14))

        rng = random.Random(11)
        self._particles = [
            (rng.random(), rng.uniform(12, 34), rng.random(), rng.uniform(2.0, 4.5))
            for _ in range(16)
        ]
        self._anim_t0 = time.monotonic()
        self._anim_tick(token)

    def _anim_tick(self, token):
        if token != self._demo_token:
            return
        c = self._anim_canvas
        try:
            if not c.winfo_exists():
                return
            self._draw_scene(c, time.monotonic() - self._anim_t0)
        except tk.TclError:
            return
        self.after(33, lambda: self._anim_tick(token))

    @staticmethod
    def _draw_typing(c, x, y, t):
        _rrect(c, x - 30, y - 15, x + 30, y + 15, 14, fill="#FFFFFF", outline="#CBD5E1")
        for i in (-1, 0, 1):
            dy = -4 * max(0.0, math.sin(t * 9 - i * 0.9))
            c.create_oval(
                x + i * 12 - 3.5, y + dy - 3.5, x + i * 12 + 3.5, y + dy + 3.5,
                fill="#64748B", outline="",
            )

    def _draw_scene(self, c, t):
        c.delete("all")
        W = max(320, c.winfo_width())
        H = int(c.cget("height"))
        ay = H * 0.6
        R = 36
        F = self.ANIM_FLIGHT
        nodes = {"A": (W * 0.2, ay), "B": (W * 0.8, ay)}
        colors = {"A": self.ANIM_BLUE, "B": self.ANIM_GREEN}
        icons = {"A": "💻", "B": "🖥️"}
        labels = {"A": "Votre appareil", "B": "Appareil du pair"}
        tt = t % self.ANIM_CYCLE

        # Particules flottantes en arrière-plan
        for fx, speed, phase, size in self._particles:
            y = H - ((t * speed + phase * H) % (H + 20)) + 10
            x = W * fx + 6 * math.sin(t * 0.8 + phase * 9)
            tw = 0.5 + 0.5 * math.sin(t * 1.3 + phase * 6.0)
            col = _lerp_color("#FFFFFF", "#BFDBFE", 0.3 + 0.7 * tw)
            c.create_oval(x - size, y - size, x + size, y + size, fill=col, outline="")

        # Lien réseau en pointillés animés
        ax, bx = nodes["A"][0], nodes["B"][0]
        c.create_line(
            ax + R + 8, ay, bx - R - 8, ay,
            fill="#CBD5E1", width=2, dash=(6, 6), dashoffset=int(t * 30) % 12,
        )
        mx = (ax + bx) / 2
        _rrect(c, mx - 96, ay + 22, mx + 96, ay + 48, 12, fill="#F1F5F9", outline="#E2E8F0")
        c.create_text(
            mx, ay + 35, text="🔒  SHA-256 • chiffré en LAN",
            fill="#475569", font=("Segoe UI", 9, "bold"),
        )

        # Petit "rebond" d'un appareil quand il reçoit
        bump = {"A": 0.0, "B": 0.0}
        for src, dst, start in self.ANIM_EVENTS:
            age = tt - (start + F)
            if 0 <= age < 0.35:
                bump[dst] = 5 * (1 - age / 0.35)

        # Appareils : anneaux ambiants + disque + icône
        for n, (nx, ny) in nodes.items():
            for k in range(3):
                ph = (t * 0.45 + k / 3) % 1
                rad = R + 4 + ph * 30
                col = _lerp_color(colors[n], "#FFFFFF", 0.35 + 0.65 * ph)
                c.create_oval(nx - rad, ny - rad, nx + rad, ny + rad, outline=col, width=2)
            r = R + bump[n]
            c.create_oval(nx - r, ny - r, nx + r, ny + r, fill=colors[n], outline="")
            c.create_oval(
                nx - r + 5, ny - r + 5, nx + r - 5, ny + r - 5,
                fill=_lerp_color(colors[n], "#FFFFFF", 0.12), outline="",
            )
            c.create_text(nx, ny, text=icons[n], font=("Segoe UI Emoji", 20), fill="#FFFFFF")
            c.create_text(
                nx, ny + R + 20, text=labels[n],
                fill="#64748B", font=("Segoe UI", 10, "bold"),
            )

        # Messages : saisie -> envoi -> arrivée
        for src, dst, start in self.ANIM_EVENTS:
            sx, sy = nodes[src]
            dx, dy = nodes[dst]
            col = colors[src]
            d = 1 if dx > sx else -1
            x0 = sx + d * (R + 14)
            x1 = dx - d * (R + 14)

            # 1) l'émetteur "écrit"
            if start - 0.9 <= tt < start:
                self._draw_typing(c, sx, sy - R - 36, t)

            # 2) onde d'envoi
            fl = tt - start
            if 0 <= fl < 0.5:
                rad = R + fl * 70
                c.create_oval(
                    sx - rad, sy - rad, sx + rad, sy + rad,
                    outline=_lerp_color(col, "#FFFFFF", fl / 0.5), width=2,
                )

            # 3) la bulle voyage en arc avec une traînée
            if start <= tt < start + F:
                p = _ease((tt - start) / F)
                for k in range(5, 0, -1):
                    pk = max(0.0, p - k * 0.035)
                    px = x0 + (x1 - x0) * pk
                    py = sy - 34 * math.sin(math.pi * pk)
                    rad = max(1, 6 - k)
                    c.create_oval(
                        px - rad, py - rad, px + rad, py + rad,
                        fill=_lerp_color(col, "#FFFFFF", 0.15 * k + 0.1), outline="",
                    )
                px = x0 + (x1 - x0) * p
                py = sy - 34 * math.sin(math.pi * p)
                _rrect(c, px - 23, py - 15, px + 23, py + 15, 12, fill=col, outline="")
                for i in (-1, 0, 1):
                    c.create_oval(
                        px + i * 10 - 3, py - 3, px + i * 10 + 3, py + 3,
                        fill="#FFFFFF", outline="",
                    )

            # 4) arrivée : onde + bulle reçue qui monte et s'efface
            age = tt - (start + F)
            if 0 <= age < 1.6:
                if age < 0.6:
                    rad = R + age * 80
                    c.create_oval(
                        dx - rad, dy - rad, dx + rad, dy + rad,
                        outline=_lerp_color(col, "#FFFFFF", age / 0.6), width=2,
                    )
                rise = _ease(age / 1.1)
                fade = _ease((age - 0.7) / 0.9)
                by = dy - R - 30 - 30 * rise
                _rrect(
                    c, dx - 38, by - 20, dx + 38, by + 20, 14,
                    fill=_lerp_color(col, "#FFFFFF", fade), outline="",
                )
                line_col = _lerp_color("#DBEAFE", "#FFFFFF", fade)
                c.create_line(dx - 26, by - 7, dx + 26, by - 7, fill=line_col, width=4, capstyle="round")
                c.create_line(dx - 26, by + 3, dx + 8, by + 3, fill=line_col, width=4, capstyle="round")
                c.create_text(dx + 24, by + 12, text="✓✓", fill=line_col, font=("Segoe UI", 8, "bold"))

    # ==========================================================
    # RENDU DES CONVERSATIONS RÉELLES
    # ==========================================================
    def _render_messages(self):
        self.file_widgets.clear()
        for widget in self.messages_scroll.winfo_children():
            widget.destroy()

        history = self.chat_history.get(self.active_peer, [])
        if not history:
            info_box = ctk.CTkFrame(
                self.messages_scroll,
                fg_color="#FFFFFF",
                border_width=1,
                border_color="#E2E8F0",
                corner_radius=12,
            )
            info_box.grid(row=0, column=0, padx=110, pady=130, sticky="ew")
            ctk.CTkLabel(
                info_box,
                text=f"Connexion établie avec {self.active_peer}.\nEnvoyez un message ou cliquez sur 📎 pour partager un fichier.",
                font=ctk.CTkFont(size=13),
                text_color="#64748B",
                justify="center",
            ).pack(padx=24, pady=24)
            return

        for idx, item in enumerate(history):
            if item["type"] == "text":
                self._add_text_bubble(
                    idx, item["text"], item["is_me"], item.get("time", "")
                )
            elif item["type"] == "file":
                self._add_file_card(
                    idx,
                    self.active_peer,
                    item["filename"],
                    item["size_str"],
                    item.get("progress", 1.0),
                    item.get("verified", True),
                    item["is_me"],
                    item.get("time", ""),
                    item.get("save_path", ""),
                )
        self._scroll_to_bottom()

    def _add_text_bubble(self, row, text, is_me, timestamp, pending=False):
        wrapper = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        wrapper.grid(row=row, column=0, padx=18, pady=5, sticky="ew")

        bubble_bg = "#1D63DC" if is_me else "#FFFFFF"
        border_w = 0 if is_me else 1
        text_col = "#FFFFFF" if is_me else "#0F172A"
        meta_col = "#DBEAFE" if is_me else "#94A3B8"
        side = "right" if is_me else "left"

        bubble = ctk.CTkFrame(
            wrapper,
            fg_color=bubble_bg,
            border_width=border_w,
            border_color="#E2E8F0",
            corner_radius=16,
        )
        bubble.pack(side=side, padx=4)

        lbl = ctk.CTkLabel(
            bubble,
            text=text,
            text_color=text_col,
            font=ctk.CTkFont(size=13),
            wraplength=460,
            justify="left",
        )
        lbl.pack(padx=14, pady=(10, 2), anchor="w")

        if is_me:
            meta_txt = f"{timestamp}  ✓" if pending else f"{timestamp}  ✓✓"
        else:
            meta_txt = timestamp
        meta_lbl = ctk.CTkLabel(
            bubble,
            text=meta_txt,
            text_color=meta_col,
            font=ctk.CTkFont(size=10),
        )
        meta_lbl.pack(padx=14, pady=(0, 7), anchor="e")
        return wrapper, meta_lbl

    def _add_file_card(
        self, row, peer_name, filename, size_str, progress, verified, is_me, timestamp, save_path=""
    ):
        wrapper = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        wrapper.grid(row=row, column=0, padx=18, pady=7, sticky="ew")

        side = "right" if is_me else "left"
        card = ctk.CTkFrame(
            wrapper,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            corner_radius=14,
            width=390,
        )
        card.pack(side=side, padx=4)
        card.grid_columnconfigure(1, weight=1)

        icon_box = ctk.CTkLabel(
            card,
            text=_get_file_icon(filename),
            width=44,
            height=44,
            corner_radius=10,
            fg_color="#EFF6FF",
            font=ctk.CTkFont(size=22),
        )
        icon_box.grid(row=0, column=0, rowspan=2, padx=(14, 12), pady=(14, 6))

        name_lbl = ctk.CTkLabel(
            card,
            text=filename,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#0F172A",
            anchor="w",
        )
        name_lbl.grid(row=0, column=1, padx=(0, 10), pady=(14, 0), sticky="w")

        size_lbl = ctk.CTkLabel(
            card,
            text=f"{size_str}  •  {timestamp}",
            font=ctk.CTkFont(size=11),
            text_color="#64748B",
            anchor="w",
        )
        size_lbl.grid(row=1, column=1, padx=(0, 10), pady=(0, 6), sticky="w")

        if save_path and os.path.exists(save_path):
            open_btn = ctk.CTkButton(
                card,
                text="Ouvrir",
                width=64,
                height=28,
                corner_radius=8,
                fg_color="#F1F5F9",
                hover_color="#E2E8F0",
                text_color="#1D63DC",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda p=save_path: _open_local_file(p),
            )
            open_btn.grid(row=0, column=2, rowspan=2, padx=(0, 14), pady=(14, 6))

        bar = ctk.CTkProgressBar(
            card,
            width=280,
            height=8,
            corner_radius=4,
            progress_color="#10B981",
            fg_color="#E2E8F0",
        )
        bar.set(progress)
        bar.grid(row=2, column=0, columnspan=2, padx=(14, 8), pady=6, sticky="ew")

        pct_lbl = ctk.CTkLabel(
            card,
            text=f"{int(progress * 100)}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#0F172A",
        )
        pct_lbl.grid(row=2, column=2, padx=(0, 14), pady=6, sticky="e")

        if verified and progress >= 1.0:
            badge_text = "✔  Transfert réussi • Vérifié SHA-256"
            badge_color = "#059669"
        elif progress >= 1.0 and not verified:
            badge_text = "✖  Erreur d'intégrité SHA-256"
            badge_color = "#DC2626"
        else:
            badge_text = "⏳ Transfert par blocs en cours..."
            badge_color = "#64748B"

        badge = ctk.CTkLabel(
            card,
            text=badge_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=badge_color,
            anchor="w",
        )
        badge.grid(row=3, column=0, columnspan=3, padx=14, pady=(2, 12), sticky="w")

        self.file_widgets[(peer_name, filename)] = {
            "bar": bar,
            "pct": pct_lbl,
            "badge": badge,
        }
        return wrapper

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
        size_bytes = os.path.getsize(file_path)
        size_str = (
            f"{size_bytes / (1024 * 1024):.2f} MB"
            if size_bytes >= 1024 * 1024
            else f"{max(0.1, size_bytes / 1024):.1f} KB"
        )
        self.append_file(
            self.active_peer,
            filename,
            size_str,
            progress=0.05,
            verified=False,
            is_me=True,
            save_path=file_path,
        )

        if self.on_send_file:
            target_ip = self.peers[self.active_peer]["ip"]
            self.on_send_file(target_ip, file_path)

    def update_file_progress(self, peer_name, filename, progress, verified=None):
        """Met à jour en direct la barre de progression d'une carte fichier."""
        history = self.chat_history.get(peer_name, [])
        for item in reversed(history):
            if item["type"] == "file" and item["filename"] == filename:
                item["progress"] = progress
                if verified is not None:
                    item["verified"] = verified
                break

        widgets = self.file_widgets.get((peer_name, filename))
        if widgets:
            widgets["bar"].set(progress)
            widgets["pct"].configure(text=f"{int(progress * 100)}%")
            if progress >= 1.0:
                is_ok = True if verified is None else verified
                widgets["badge"].configure(
                    text="✔  Transfert réussi • Vérifié SHA-256"
                    if is_ok
                    else "✖  Erreur d'intégrité SHA-256",
                    text_color="#059669" if is_ok else "#DC2626",
                )

    def append_message(self, peer_name, text, is_me=False):
        now_str = datetime.now().strftime("%H:%M")
        self.chat_history.setdefault(peer_name, []).append(
            {"type": "text", "text": text, "is_me": is_me, "time": now_str}
        )
        if peer_name == self.active_peer:
            self._render_messages()
        elif not is_me:
            self.unread_counts[peer_name] = self.unread_counts.get(peer_name, 0) + 1
            self._refresh_peer_list()

    def append_file(
        self,
        peer_name,
        filename,
        size_str,
        progress=1.0,
        verified=True,
        is_me=False,
        save_path="",
    ):
        now_str = datetime.now().strftime("%H:%M")
        self.chat_history.setdefault(peer_name, []).append(
            {
                "type": "file",
                "filename": filename,
                "size_str": size_str,
                "progress": progress,
                "verified": verified,
                "is_me": is_me,
                "time": now_str,
                "save_path": save_path,
            }
        )
        if peer_name == self.active_peer:
            self._render_messages()
        elif not is_me:
            self.unread_counts[peer_name] = self.unread_counts.get(peer_name, 0) + 1
            self._refresh_peer_list()

    def update_online_peers(self, peers_dict):
        """Appelée par core/discovery.py pour mettre à jour la liste des pairs."""
        self.peers = {
            name: {"ip": ip, "online": True} for name, ip in peers_dict.items()
        }
        for name in self.peers:
            self.chat_history.setdefault(name, [])

        if self.active_peer and self.active_peer not in self.peers:
            self.active_peer = None
            self.header_avatar.configure(
                text="?", fg_color="#E2E8F0", text_color="#64748B"
            )
            self.header_name.configure(text="Aucune conversation sélectionnée")
            self.header_status.configure(
                text="En attente d'un appareil sur le réseau local",
                text_color="#64748B",
            )
            self.security_pill.configure(
                text="🔒  SHA-256 + Chiffrement LAN",
                fg_color="#F1F5F9",
                text_color="#475569",
            )
            self._render_empty_chat_state()

        self._refresh_peer_list()


if __name__ == "__main__":
    app = AppWindow()
    app.mainloop()
