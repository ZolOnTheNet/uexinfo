"""Commandes /go et /lieu."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok


@register("go", "lieu")
def cmd_go(args: list[str], ctx) -> None:
    pos = ctx.cfg.setdefault("position", {})

    if not args:
        _show(pos)
        return

    sub = args[0].lower()

    if sub == "clear":
        pos["current"] = ""
        pos["destination"] = ""
        settings.save(ctx.cfg)
        print_ok("Position et destination réinitialisées")
        return

    if sub == "from":
        name = " ".join(args[1:])
        if not name:
            print_error("Spécifie un lieu")
            return
        resolved = _resolve(name, ctx)
        pos["current"] = resolved
        settings.save(ctx.cfg)
        print_ok(f"Position : {resolved}")

    elif sub == "to":
        name = " ".join(args[1:])
        if not name:
            print_error("Spécifie un lieu")
            return
        resolved = _resolve(name, ctx)
        pos["destination"] = resolved
        settings.save(ctx.cfg)
        print_ok(f"Destination : {resolved}")

    else:
        name = " ".join(args)
        resolved = _resolve(name, ctx)
        pos["current"] = resolved
        settings.save(ctx.cfg)
        print_ok(f"Position : {resolved}")


def _show(pos: dict) -> None:
    curr = pos.get("current") or "(non définie)"
    dest = pos.get("destination") or "(non définie)"
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
