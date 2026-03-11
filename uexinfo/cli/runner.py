"""Routage centralisé : normalize → parse → dispatch.

Utilisé par la boucle REPL (cli/main.py) ET par l'UI Textual (app.py)
afin d'éviter la duplication de logique.
"""
from __future__ import annotations

import shlex

from uexinfo.display.formatter import console
from uexinfo.display import colors as C


def normalize_command(line: str, known_commands: set[str]) -> str:
    """
    Normalise la saisie utilisateur : ajoute / si nécessaire.

    Logique :
    - Si commence par / ou @ : retourne tel quel
    - Si le premier mot est une commande connue : ajoute /
    - Sinon : recherche libre (retourne tel quel)
    """
    stripped = line.strip()
    if not stripped:
        return stripped

    # Déjà une commande ou @lieu
    if stripped.startswith("/") or stripped.startswith("@"):
        return stripped

    # Extraire le premier mot
    first_word = stripped.split()[0].lower() if stripped.split() else ""

    # Si c'est une commande connue, ajouter /
    if first_word in known_commands:
        return "/" + stripped

    # Sinon, recherche libre
    return stripped


def run_command(line: str, ctx) -> set[str]:
    """Normalize + parse + dispatch une ligne de saisie.

    Retourne le set des noms de commandes dispatchées.
    Exemples : {"help"}, {"player", "info"} pour @lieu, {"info"} pour recherche libre.
    """
    from uexinfo.cli.commands import dispatch, get_names
    from uexinfo.cli.parser import parse_line

    known_cmds = set(get_names())
    normalized = normalize_command(line.strip(), known_cmds)

    if ctx.debug_level >= 1:
        console.print(f"[{C.DIM}]DBG1 raw      = {line!r}[/{C.DIM}]")
        console.print(
            f"[{C.DIM}]DBG1 known    = {sorted(known_cmds)!r}[/{C.DIM}]"
            if ctx.debug_level >= 3
            else f"[{C.DIM}]DBG1 'help' in known = {'help' in known_cmds}[/{C.DIM}]"
        )
        console.print(f"[{C.DIM}]DBG1 normalized= {normalized!r}[/{C.DIM}]")

    if not normalized:
        return set()

    if normalized.startswith("@"):
        try:
            words = shlex.split(normalized)
        except ValueError:
            words = normalized.split()
        full_loc = " ".join(words)   # "@Port Tressler"
        dispatch("player", [full_loc], ctx)
        loc_name = full_loc[1:]      # "Port Tressler"
        if "." in loc_name:
            loc_name = loc_name.rsplit(".", 1)[-1]
        dispatch("info", [loc_name], ctx)
        return {"player", "info"}

    elif normalized.startswith("/"):
        cmd, args = parse_line(normalized)
        if ctx.debug_level >= 1:
            console.print(f"[{C.DIM}]DBG1 cmd      = {cmd!r}[/{C.DIM}]")
            console.print(f"[{C.DIM}]DBG1 args     = {args!r}[/{C.DIM}]")
        if cmd:
            if ctx.debug_level >= 1:
                console.print(f"[{C.DIM}]DBG1 dispatch → ('{cmd}', {args!r})[/{C.DIM}]")
            dispatch(cmd, args, ctx)
            return {cmd}

    else:
        # Recherche libre → /info
        try:
            words = shlex.split(normalized)
        except ValueError:
            words = normalized.split()
        if ctx.debug_level >= 1:
            console.print(f"[{C.DIM}]DBG1 fallback → dispatch('info', {words!r})[/{C.DIM}]")
        dispatch("info", words, ctx)
        return {"info"}

    return set()
