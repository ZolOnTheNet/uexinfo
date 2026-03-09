"""
Mode overlay — lance uexinfo dans une fenêtre transparente par-dessus le jeu.

Nécessite : pip install pywebview pynput textual-web
         ou : pip install -e ".[overlay]"

La fenêtre s'ouvre par-dessus Star Citizen (mode Borderless Windowed requis).
Le hotkey global (défaut: alt+shift+u) affiche/masque la fenêtre sans quitter.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
import urllib.request


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """Attendre que le serveur textual-web soit prêt (polling HTTP)."""
    url = f"http://localhost:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _parse_hotkey(hotkey_str: str) -> str:
    """Convertir 'alt+shift+u' en format pynput '<alt>+<shift>+u'."""
    modifiers = {"alt", "alt_l", "alt_r", "shift", "shift_l", "shift_r", "ctrl", "ctrl_l", "ctrl_r"}
    parts = []
    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        # Normalise les alias courants
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
            # Touche nommée (f1, enter, space, etc.)
            parts.append(f"<{part}>")
    return "+".join(parts)


def run_overlay(hotkey: str | None = None, port: int | None = None) -> None:
    """Point d'entrée du mode overlay."""

    # ── Vérifier les dépendances optionnelles ────────────────────────────────
    try:
        import webview
        from pynput import keyboard
    except ImportError as e:
        missing = str(e).split("'")[1] if "'" in str(e) else str(e)
        print(f"[overlay] Dépendance manquante : {missing}")
        print("Installez les dépendances overlay :")
        print("  pip install pywebview pynput textual-web")
        print("  ou : pip install -e \".[overlay]\"")
        sys.exit(1)

    # ── Lire la config (valeurs par défaut) ──────────────────────────────────
    try:
        from uexinfo.config.settings import load as load_cfg
        cfg = load_cfg()
        ov_cfg = cfg.get("overlay", {})
    except Exception:
        ov_cfg = {}

    # Les arguments CLI sont prioritaires sur la config
    hotkey = hotkey or ov_cfg.get("hotkey", "alt+shift+u")
    port   = port   or ov_cfg.get("port", 8090)
    width  = ov_cfg.get("width", 700)
    height = ov_cfg.get("height", 900)

    print(f"[overlay] Démarrage — hotkey: {hotkey}  port: {port}")

    # ── 1. Lancer textual-web en arrière-plan ────────────────────────────────
    textual_proc = subprocess.Popen(
        [
            sys.executable, "-m", "textual_web",
            "--command", f"{sys.executable} -m uexinfo",
            "--host", "localhost",
            "--port", str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    print(f"[overlay] Attente du serveur sur le port {port}…")
    if not _wait_for_server(port, timeout=20.0):
        print(f"[overlay] Erreur : le serveur n'a pas répondu dans le délai imparti.")
        textual_proc.terminate()
        sys.exit(1)
    print("[overlay] Serveur prêt.")

    # ── 2. Créer la fenêtre PyWebView ────────────────────────────────────────
    window = webview.create_window(
        title="uexinfo",
        url=f"http://localhost:{port}",
        frameless=True,
        transparent=True,
        on_top=True,
        width=width,
        height=height,
        y=50,
    )

    # ── 3. Hotkey global — toggle show/hide ──────────────────────────────────
    overlay_visible = True
    _lock = threading.Lock()

    def toggle_overlay():
        nonlocal overlay_visible
        with _lock:
            if overlay_visible:
                window.hide()
            else:
                window.show()
            overlay_visible = not overlay_visible

    pynput_hotkey = _parse_hotkey(hotkey)
    print(f"[overlay] Hotkey actif : {hotkey}  ({pynput_hotkey})")

    listener = keyboard.GlobalHotKeys({pynput_hotkey: toggle_overlay})
    listener.start()

    # ── 4. Nettoyage à la fermeture de la fenêtre ────────────────────────────
    def on_closing():
        listener.stop()
        textual_proc.terminate()
        try:
            textual_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            textual_proc.kill()

    window.events.closing += on_closing

    # ── 5. Lancer PyWebView (bloquant jusqu'à fermeture) ─────────────────────
    print(f"[overlay] Fenêtre ouverte — Appuyez sur {hotkey} pour afficher/masquer.")
    webview.start()
