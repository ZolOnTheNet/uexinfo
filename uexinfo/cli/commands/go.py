"""Commandes /go et /lieu."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok


def _save_player(ctx) -> None:
    """Sauvegarde l'état du joueur dans la config."""
    ctx.cfg["player"] = ctx.player.to_config()
    settings.save(ctx.cfg)


@register("go", "g", "lieu")
def cmd_go(args: list[str], ctx) -> None:
    if not args:
        _show(ctx.player)
        return

    sub = args[0].lower()

    if sub == "clear":
        ctx.player.location = ""
        ctx.player.destination = ""
        _save_player(ctx)
        print_ok("Position et destination réinitialisées")
        return

    if sub == "from":
        name = " ".join(args[1:])
        if not name:
            print_error("Spécifie un lieu")
            return
        resolved = _resolve(name, ctx)
        ctx.player.location = resolved
        _save_player(ctx)
        print_ok(f"Position : {resolved}")

    elif sub == "to":
        name = " ".join(args[1:])
        if not name:
            print_error("Spécifie un lieu")
            return
        resolved = _resolve(name, ctx)
        ctx.player.destination = resolved
        _save_player(ctx)
        print_ok(f"Destination : {resolved}")

    else:
        name = " ".join(args)
        resolved = _resolve(name, ctx)
        ctx.player.location = resolved
        _save_player(ctx)
        print_ok(f"Position : {resolved}")


def _show(player) -> None:
    curr = player.location or "(non définie)"
    dest = player.destination or "(non définie)"
    console.print(f"  [bold]Position :[/bold]    [{C.UEX}]{curr}[/{C.UEX}]")
    console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{dest}[/{C.UEX}]")


def _resolve(name: str, ctx) -> str:
    """Résout un nom de lieu depuis le cache (terminal, ville…)."""
    t = ctx.cache.find_terminal(name)
    if t:
        return t.name
    # Recherche parmi les planètes
    for p in ctx.cache.planets:
        if p.name.lower() == name.lower():
            return p.name
    # Recherche parmi les systèmes
    for s in ctx.cache.star_systems:
        if s.name.lower() == name.lower():
            return s.name
    # Retourne tel quel si inconnu
    return name


@register("arriver", "arrivé", "arrive", "arrived")
def cmd_arriver(args: list[str], ctx) -> None:
    """Le joueur est arrivé : la destination devient la position actuelle."""
    dest = (ctx.player.destination or "").strip()
    if not dest:
        print_error("Aucune destination définie — utilisez /go to <terminal>.")
        return
    ctx.player.location = dest
    ctx.player.destination = ""
    _save_player(ctx)
    print_ok(f"Arrivé à : {dest}")


@register("dest", "d")
def cmd_dest(args: list[str], ctx) -> None:
    """Raccourci : /dest <lieu> = /go to <lieu>"""
    if not args:
        # Sans argument : afficher la destination actuelle
        dest = ctx.player.destination or "(non définie)"
        console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{dest}[/{C.UEX}]")
    else:
        # Avec argument : définir la destination
        name = " ".join(args)
        resolved = _resolve(name, ctx)
        ctx.player.destination = resolved
        _save_player(ctx)
        print_ok(f"Destination : {resolved}")
