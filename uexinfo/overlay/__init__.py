"""Package overlay — console HTML/WebSocket par-dessus Star Citizen.

Point d'entrée : run_overlay(hotkey, port)
Architecture :
  - server.py  : serveur WebSocket asyncio (exécute les commandes CLI)
  - static/index.html : interface HTML + CSS + JS (ANSI → HTML, barre de statut,
                        complétion, historique, clics sur les mots, menu contextuel)
"""
from __future__ import annotations

import ctypes
import os
import signal
import sys
import threading
import time


def _force_focus(title: str = "UEXInfo") -> None:
    """Force le focus OS sur la fenêtre PyWebView (Windows uniquement).

    SetForegroundWindow est bloqué par Windows quand l'appelant n'est pas
    l'app au premier plan. L'astuce classique : simuler un appui Alt pour
    débloquer le verrou, puis SetForegroundWindow.
    """
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return
        # Débloquer le vol de focus via Alt simulé
        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)            # Alt ↓
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)  # Alt ↑
    except Exception:
        pass


def _parse_hotkey(hotkey_str: str) -> str:
    """Convertir 'alt+shift+u' → '<alt>+<shift>+u' (format pynput)."""
    parts = []
    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        if part in ("alt", "alt_l", "alt_r"):
            parts.append("<alt>")
        elif part in ("shift", "shift_l", "shift_r"):
            parts.append("<shift>")
        elif part in ("ctrl", "ctrl_l", "ctrl_r", "control"):
            parts.append("<ctrl>")
        elif part in ("win", "super", "cmd"):
            parts.append("<cmd>")
        elif len(part) == 1:
            parts.append(part)
        else:
            parts.append(f"<{part}>")
    return "+".join(parts)


def _load_html(port: int) -> str:
    """Lire index.html et injecter le port WebSocket."""
    from pathlib import Path
    html_path = Path(__file__).parent / "static" / "index.html"
    html = html_path.read_text(encoding="utf-8")
    return html.replace("__WS_PORT__", str(port))


class _WindowApi:
    """API JS exposée à PyWebView pour déplacer la fenêtre frameless."""

    def __init__(self) -> None:
        self._win = None

    def set_window(self, win) -> None:
        self._win = win

    def move(self, x: int, y: int) -> None:
        if self._win:
            try:
                self._win.move(int(x), int(y))
            except Exception:
                pass

    def resize(self, w: int, h: int) -> None:
        if self._win:
            try:
                self._win.resize(max(200, int(w)), max(200, int(h)))
            except Exception:
                pass


def run_overlay(hotkey: str | None = None, port: int | None = None) -> None:
    """Point d'entrée du mode overlay (appelé par __main__.py --overlay)."""

    # ── Vérifier les dépendances optionnelles ────────────────────────────────
    try:
        import webview
        from pynput import keyboard
    except ImportError as e:
        missing = str(e).split("'")[1] if "'" in str(e) else str(e)
        print(f"[overlay] Dépendance manquante : {missing}")
        print("  pip install pywebview pynput")
        print("  ou : pip install -e \".[overlay]\"")
        sys.exit(1)

    try:
        import websockets  # noqa: F401
    except ImportError:
        print("[overlay] Dépendance manquante : websockets")
        print("  pip install websockets")
        print("  ou : pip install -e \".[overlay]\"")
        sys.exit(1)

    # ── Config ────────────────────────────────────────────────────────────────
    try:
        from uexinfo.config.settings import load as _load
        cfg    = _load()
        ov_cfg = cfg.get("overlay", {})
    except Exception:
        ov_cfg = {}

    hotkey    = hotkey or ov_cfg.get("hotkey", "alt+shift+u")
    port      = port   or ov_cfg.get("port", 8090)
    width     = ov_cfg.get("width",    500)
    height    = ov_cfg.get("height",   880)
    frameless = ov_cfg.get("frameless", True)    # True = titlebar HTML + drag JS

    print(f"[overlay] Démarrage — ws://localhost:{port}  hotkey: {hotkey}")

    # ── 1. Démarrer le serveur WebSocket ─────────────────────────────────────
    # L'import de server.py redirige console AVANT les commandes → doit être
    # le tout premier import uexinfo après les modules stdlib/tiers.
    from uexinfo.overlay.server import OverlayServer
    server = OverlayServer()
    server.init_context()
    server.start_background(host="localhost", port=port)

    # Attendre que le serveur soit prêt
    time.sleep(0.4)
    print("[overlay] Serveur WebSocket prêt.")

    # ── 2. Créer la fenêtre PyWebView ────────────────────────────────────────
    html = _load_html(port)
    print(f"[overlay] frameless={frameless}  transparent={frameless}  {width}×{height}", flush=True)
    api = _WindowApi()
    window = webview.create_window(
        title="UEXInfo",
        html=html,
        frameless=frameless,
        transparent=frameless,      # transparence seulement si frameless
        background_color="#0A0C12", # fond sombre immédiat, évite le flash blanc
        on_top=True,
        width=width,
        height=height,
        y=40,
        js_api=api,
    )
    api.set_window(window)

    # ── 3. Hotkey global toggle show/hide ────────────────────────────────────
    visible = True
    _lock   = threading.Lock()

    def toggle():
        nonlocal visible
        with _lock:
            if visible:
                window.hide()
            else:
                window.show()
                _force_focus()
                threading.Timer(
                    0.12,
                    lambda: window.evaluate_js("document.getElementById('cmd-input').focus()")
                ).start()
            visible = not visible

    pynput_hk = _parse_hotkey(hotkey)
    print(f"[overlay] Hotkey : {hotkey}  ({pynput_hk})")
    listener = keyboard.GlobalHotKeys({pynput_hk: toggle})
    listener.start()

    # ── 4. Nettoyage à la fermeture ───────────────────────────────────────────
    def _shutdown():
        print("[overlay] _shutdown() — sauvegarde + os._exit(0)", flush=True)
        listener.stop()
        if server.ctx and server.ctx.cache.transport_graph.has_unsaved_changes:
            try:
                server.ctx.cache.save_transport_graph()
                print("[overlay] Graphe sauvegardé.", flush=True)
            except Exception as e:
                print(f"[overlay] Erreur sauvegarde : {e}", flush=True)
        os._exit(0)

    def on_closing():
        print("[overlay] on_closing() → _shutdown", flush=True)
        threading.Thread(target=_shutdown, daemon=False).start()

    window.events.closing += on_closing

    # Ctrl+C dans le terminal
    def _sigint(sig, frame):
        print("[overlay] SIGINT reçu → _shutdown", flush=True)
        _shutdown()

    signal.signal(signal.SIGINT, _sigint)

    # ── 5. Lancer PyWebView (bloquant) ────────────────────────────────────────
    def _transparency_fix():
        """Double toggle au démarrage pour forcer le rendu transparent."""
        time.sleep(0.8)   # attendre que la fenêtre soit pleinement rendue
        print("[overlay] transparency_fix : toggle × 2", flush=True)
        toggle()           # cache
        time.sleep(0.10)
        toggle()           # ré-affiche → transparence + focus

    threading.Thread(target=_transparency_fix, daemon=True).start()

    print(f"[overlay] Fenêtre ouverte — {hotkey} pour afficher/masquer.", flush=True)
    webview.start()
    print("[overlay] webview.start() retourné → _shutdown", flush=True)
    _shutdown()
