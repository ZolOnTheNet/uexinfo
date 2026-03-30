"""Parsing unifié des options CLI pour les commandes uexinfo."""
from __future__ import annotations


def parse_flags(args: list[str]) -> tuple[dict[str, str | bool], list[str]]:
    """Sépare flags (--xxx [valeur]) et arguments positionnels.

    Retourne (flags, positional) :
    - flags : dict {nom: True (booléen) | valeur (str)}
    - positional : liste des args sans --

    Exemples :
    >>> parse_flags(["buy", "copper", "--all", "--sys", "Stanton"])
    ({"all": True, "sys": "Stanton"}, ["buy", "copper"])

    >>> parse_flags(["roi", "--max:5", "--boucle"])
    ({"max": "5", "boucle": True}, ["roi"])
    """
    flags: dict[str, str | bool] = {}
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:]
            if ":" in key:
                k, v = key.split(":", 1)
                flags[k] = v
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                flags[key] = args[i + 1]
                i += 1
            else:
                flags[key] = True
        else:
            positional.append(a)
        i += 1
    return flags, positional


def get_flag(flags: dict, *names: str, default=None):
    """Récupère un flag par un ou plusieurs noms alternatifs."""
    for name in names:
        if name in flags:
            return flags[name]
    return default


def flag_bool(flags: dict, *names: str) -> bool:
    """Retourne True si un flag booléen est présent."""
    return any(name in flags for name in names)
