# DUAL_MODE_OVERLAY.md — Ajout du mode dual CLI/TUI/Overlay à uexinfo

## Prérequis

Ce document suppose que la migration Textual TUI décrite dans `docs/TEXTUAL_MIGRATION.md` est **terminée et fonctionnelle**. L'app Textual doit se lancer correctement avec `python -m uexinfo` avant de commencer ce travail.

---

## Objectif

Ajouter trois modes de lancement à uexinfo :

| Mode | Commande | Description |
|------|----------|-------------|
| **TUI** (défaut) | `python -m uexinfo` | App Textual dans le terminal |
| **CLI** | `python -m uexinfo --cli` | CLI original (prompt Rich interactif) |
| **Overlay** | `python -m uexinfo --overlay` | Fenêtre transparente par-dessus le jeu, toggle par hotkey |

**Principe clé** : le mode CLI original doit continuer à fonctionner exactement comme avant. C'est un fallback garanti. Ne rien casser.

---

## Étape 1 — Refactorer le point d'entrée `__main__.py`

Le `__main__.py` actuel lance soit le CLI soit le TUI. Il faut ajouter le parsing d'arguments :

```python
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        prog="uexinfo",
        description="Star Citizen Trade Assistant"
    )
    parser.add_argument(
        "--cli", 
        action="store_true",
        help="Mode CLI original (prompt interactif Rich)"
    )
    parser.add_argument(
        "--overlay", 
        action="store_true",
        help="Mode overlay transparent (PyWebView + hotkey toggle)"
    )
    parser.add_argument(
        "--hotkey",
        type=str,
        default="alt+shift+u",
        help="Hotkey pour toggle overlay (défaut: alt+shift+u)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8090,
        help="Port pour textual-web en mode overlay (défaut: 8090)"
    )
    args = parser.parse_args()

    if args.cli:
        # Lancer le CLI original — rien ne change ici
        from uexinfo.cli import run_cli  # adapter l'import selon la structure actuelle
        run_cli()
    elif args.overlay:
        # Lancer en mode overlay
        from uexinfo.overlay import run_overlay
        run_overlay(hotkey=args.hotkey, port=args.port)
    else:
        # Mode par défaut : Textual TUI
        from uexinfo.app import UexInfoApp
        app = UexInfoApp()
        app.run()

if __name__ == "__main__":
    main()
```

### Important — préserver le CLI original

Le code CLI actuel (prompt interactif, commandes `/trade`, `/go`, etc.) doit être **isolé dans un module** (ex: `uexinfo/cli.py` avec une fonction `run_cli()`). Si le CLI est actuellement directement dans `__main__.py`, il faut :

1. Extraire tout le code CLI dans `uexinfo/cli.py` → fonction `run_cli()`
2. S'assurer que `run_cli()` fonctionne exactement comme avant
3. Le `__main__.py` ne fait plus que du routing selon les arguments

---

## Étape 2 — Module overlay `uexinfo/overlay.py`

Ce module gère :
- Le lancement de textual-web en arrière-plan (sert l'app Textual en HTML)
- L'ouverture d'une fenêtre PyWebView transparente, borderless, always-on-top
- Un hotkey global pour show/hide la fenêtre
- La fermeture propre de tout quand on quitte

```python
"""
Mode overlay — lance uexinfo dans une fenêtre transparente par-dessus le jeu.
Utilise textual-web pour servir l'app en HTML + pywebview pour l'affichage.
"""
import subprocess
import threading
import time
import sys
import signal

def run_overlay(hotkey: str = "alt+shift+u", port: int = 8090):
    """Point d'entrée du mode overlay."""
    
    try:
        import webview
        from pynput import keyboard
    except ImportError:
        print("Mode overlay requiert pywebview et pynput.")
        print("Installation : pip install pywebview pynput textual-web")
        sys.exit(1)

    # --- 1. Lancer textual-web en arrière-plan ---
    textual_process = subprocess.Popen(
        [
            sys.executable, "-m", "textual_web",
            "--command", f"{sys.executable} -m uexinfo",
            "--host", "localhost",
            "--port", str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Attendre que le serveur soit prêt
    # TODO: améliorer avec un polling HTTP plutôt qu'un sleep fixe
    time.sleep(4)

    # --- 2. Créer la fenêtre overlay ---
    window = webview.create_window(
        title="uexinfo",
        url=f"http://localhost:{port}",
        frameless=True,
        transparent=True,
        on_top=True,
        width=700,
        height=900,
        # Position initiale — coin droit de l'écran
        x=None,  # Laisser None pour centrer, ou calculer screen_width - 700
        y=50,
    )

    # --- 3. Hotkey global toggle ---
    overlay_visible = True

    def toggle_overlay():
        nonlocal overlay_visible
        if overlay_visible:
            window.hide()
        else:
            window.show()
            window.on_top = True  # Re-forcer le on_top après show
        overlay_visible = not overlay_visible

    def parse_hotkey(hotkey_str: str):
        """Convertir 'alt+shift+u' en format pynput."""
        parts = hotkey_str.lower().split("+")
        keys = []
        for part in parts:
            part = part.strip()
            if part in ("alt", "alt_l"):
                keys.append("<alt>")
            elif part in ("shift", "shift_l"):
                keys.append("<shift>")
            elif part in ("ctrl", "ctrl_l"):
                keys.append("<ctrl>")
            else:
                keys.append(part)
        return "+".join(keys)

    pynput_hotkey = parse_hotkey(hotkey)
    
    hotkey_listener = keyboard.GlobalHotKeys({
        pynput_hotkey: toggle_overlay
    })
    hotkey_listener.start()

    # --- 4. Nettoyage à la fermeture ---
    def on_closing():
        hotkey_listener.stop()
        textual_process.terminate()
        textual_process.wait(timeout=5)

    window.events.closing += on_closing

    # --- 5. Lancer la boucle PyWebView (bloquant) ---
    print(f"uexinfo overlay démarré — hotkey: {hotkey}")
    print(f"Appuyez sur {hotkey} pour afficher/masquer l'overlay")
    webview.start()
```

---

## Étape 3 — Dépendances

Ajouter dans `requirements.txt` (en section optionnelle ou avec commentaire) :

```
# Mode overlay (optionnel — pip install pywebview pynput textual-web)
# pywebview>=5.0
# pynput>=1.7
# textual-web>=0.7.0
```

Ces dépendances ne sont PAS requises pour le mode TUI ou CLI — elles sont importées conditionnellement dans `overlay.py` avec un try/except.

Optionnellement, ajouter un extra dans `pyproject.toml` :

```toml
[project.optional-dependencies]
overlay = ["pywebview>=5.0", "pynput>=1.7", "textual-web>=0.7.0"]
```

Installation overlay : `pip install -e ".[overlay]"`

---

## Étape 4 — Configuration hotkey dans config.toml

Ajouter une section `[overlay]` dans le config TOML existant :

```toml
[overlay]
hotkey = "alt+shift+u"
port = 8090
width = 700
height = 900
opacity = 0.95
```

Le module `overlay.py` doit lire cette config via `core/config.py` si elle existe, sinon utiliser les valeurs par défaut.

Les arguments en ligne de commande (`--hotkey`, `--port`) sont prioritaires sur la config TOML.

---

## Étape 5 — Note sur Star Citizen

Le mode overlay fonctionne UNIQUEMENT si Star Citizen tourne en **Borderless Windowed** (pas en Fullscreen exclusif). C'est le mode recommandé par CIG de toute façon.

La fenêtre PyWebView se place par-dessus le jeu grâce au flag `on_top=True`. Quand elle est masquée via hotkey, elle n'intercepte plus aucun input — le jeu reçoit tous les clics et touches normalement.

---

## Résumé des fichiers à créer/modifier

| Fichier | Action |
|---------|--------|
| `uexinfo/__main__.py` | **Modifier** — ajouter argparse et routing 3 modes |
| `uexinfo/cli.py` | **Créer** (ou renommer) — isoler le CLI original dans ce module |
| `uexinfo/overlay.py` | **Créer** — module overlay PyWebView + hotkey |
| `requirements.txt` | **Modifier** — ajouter dépendances optionnelles overlay |
| `pyproject.toml` | **Modifier** — ajouter optional-dependencies overlay |
| `config.toml` (template) | **Modifier** — ajouter section [overlay] |

---

## Règles pour Claude Code

1. **NE PAS casser le mode TUI** — il doit continuer à fonctionner en `python -m uexinfo`
2. **NE PAS casser le CLI original** — `python -m uexinfo --cli` doit être identique au comportement pré-migration
3. **Imports conditionnels** — pywebview et pynput ne sont importés que dans overlay.py, avec un message d'erreur clair si manquants
4. **Tester les 3 modes** séparément après implémentation
5. **Ne pas modifier `core/`** — même règle que pour la migration Textual