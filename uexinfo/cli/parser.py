"""Parsing des lignes de commande /xxx ou xxx."""
from __future__ import annotations

import shlex


def parse_line(line: str, known_commands: set[str] | None = None) -> tuple[str, list[str]]:
    """Parse une ligne de commande avec ou sans /.

    Args:
        line: ligne saisie par l'utilisateur
        known_commands: ensemble des commandes connues (optionnel)

    Retourne (nom_commande, liste_args) ou ("", []) si invalide.

    Comportement :
    - Si commence par "/" : toujours traiter comme commande
    - Sinon : vérifier si le premier mot est une commande connue
    - Si oui : traiter comme commande
    - Sinon : retourner ("", []) pour recherche libre
    """
    stripped = line.strip()
    if not stripped:
        return "", []

    # Si commence par /, retirer le /
    has_slash = stripped.startswith("/")
    if has_slash:
        rest = stripped[1:].strip()
        if not rest:
            return "", []
    else:
        rest = stripped

    # Parser les arguments
    try:
        # posix=False : conserve les backslashes (chemins Windows)
        parts = shlex.split(rest, posix=False)
        # posix=False conserve les guillemets entourants — on les retire
        parts = [p.strip("\"'") for p in parts]
    except ValueError:
        parts = rest.split()

    if not parts:
        return "", []

    first_word = parts[0].lower()

    # Si pas de /, vérifier si c'est une commande connue
    if not has_slash:
        if known_commands is None or first_word not in known_commands:
            # Pas une commande → recherche libre
            return "", []

    return first_word, parts[1:]
