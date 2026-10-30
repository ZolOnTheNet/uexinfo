"""Garde-fous du serveur WebSocket local : jeton de connexion et fichiers que la page peut ouvrir.

Le serveur écoute sur localhost, mais n'importe quelle page web ouverte dans un navigateur
peut s'y connecter. Seule la page de l'overlay connaît le jeton (inséré dans le HTML au
lancement) ; il est aussi écrit dans le dossier de config de l'utilisateur pour que la
relance suivante puisse demander à l'ancienne instance de se fermer.
"""
from __future__ import annotations

import hmac
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from uexinfo.config.settings import CONFIG_PATH

TOKEN_PATH = CONFIG_PATH.parent / "overlay.token"

# Fichiers que la page peut faire ouvrir (captures d'écran) : jamais un exécutable ni un script.
OPENABLE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".webp"})


def new_token(path: Path = TOKEN_PATH) -> str:
    """Jeton aléatoire de cette instance, écrit dans `path` (lu par la relance suivante)."""
    token = secrets.token_urlsafe(24)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")
    except OSError:
        pass                      # sans fichier, la relance ne pourra pas fermer cette instance
    return token


def read_token(path: Path = TOKEN_PATH) -> str:
    """Jeton de l'instance en cours, ou "" s'il n'y en a pas."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def token_ok(request_path: str, token: str) -> bool:
    """Vrai si l'URL de connexion (« /?t=… ») porte le bon jeton."""
    given = parse_qs(urlsplit(request_path).query).get("t", [""])[0]
    return bool(token) and hmac.compare_digest(given, token)


def openable(path: str) -> Path | None:
    """Chemin absolu si `path` est une image existante, sinon None."""
    if not path:
        return None
    p = Path(path).resolve()
    if p.suffix.lower() in OPENABLE_SUFFIXES and p.is_file():
        return p
    return None
