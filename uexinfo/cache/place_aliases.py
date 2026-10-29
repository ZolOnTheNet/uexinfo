"""Lieux choisis par le joueur pour un texte de mission (décision D11).

Quand le joueur départage un lieu (« Pyro Gateway » → Pyro Gateway (Nyx)), son choix est
gardé : le même texte, relu plus tard sur un autre contrat, donne le même lieu sans
redemander. Seul un choix du joueur est enregistré ici, jamais une déduction.
"""
from __future__ import annotations

import json
from pathlib import Path

import appdirs

from uexinfo.names.normalize import norm

_STORE_FILE = Path(appdirs.user_data_dir("uexinfo")) / "place_aliases.json"


def _load() -> dict[str, str]:
    """Contenu de `place_aliases.json` (texte normalisé → référence) ; vide s'il est absent ou illisible."""
    try:
        with open(_STORE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get(text: str) -> str | None:
    """Référence choisie auparavant par le joueur pour `text`, ou None."""
    return _load().get(norm(text)) if text else None


def remember(text: str, place_ref: str) -> None:
    """Retient que `text` désigne `place_ref` (choix du joueur)."""
    if not text or not place_ref:
        return
    data = _load()
    data[norm(text)] = place_ref
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear() -> int:
    """Oublie tous les choix ; renvoie leur nombre."""
    n = len(_load())
    if _STORE_FILE.exists():
        _STORE_FILE.unlink()
    return n
