"""Parsing des lignes de commande /xxx."""
from __future__ import annotations

import shlex


def parse_line(line: str) -> tuple[str, list[str]]:
    """Parse une ligne commençant par /.

    Retourne (nom_commande, liste_args) ou ("", []) si invalide.
    """
    stripped = line.strip()
    if not stripped.startswith("/"):
        return "", []

    rest = stripped[1:].strip()
    if not rest:
        return "", []

    try:
        parts = shlex.split(rest)
    except ValueError:
        parts = rest.split()

    if not parts:
        return "", []

    return parts[0].lower(), parts[1:]
