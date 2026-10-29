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


def _show_help() -> None:
    """Affiche l'aide de /go."""
    from uexinfo.display.formatter import section
    from uexinfo.display import colors as C
    from uexinfo.display.formatter import console
    section("Aide — /go")
    console.print(
        f"[bold]Usage :[/bold]\n"
        f"  [bold {C.UEX}]/go[/bold {C.UEX}]              Afficher position et destination\n"
        f"  [bold {C.UEX}]/go <lieu>[/bold {C.UEX}]        Définir la position courante\n"
        f"  [bold {C.UEX}]/go from <lieu>[/bold {C.UEX}]   Définir le point de départ\n"
        f"  [bold {C.UEX}]/go to <lieu>[/bold {C.UEX}]     Définir la destination\n"
        f"  [bold {C.UEX}]/go clear[/bold {C.UEX}]         Réinitialiser position et destination\n"
        f"  [bold {C.UEX}]@<lieu>[/bold {C.UEX}]           Raccourci pour définir la position\n"
        f"  [bold {C.UEX}]/arriver[/bold {C.UEX}]          Destination → position courante\n"
        f"  [bold {C.UEX}]/dest <lieu>[/bold {C.UEX}]      Raccourci pour définir la destination\n\n"
        f"[{C.DIM}]<lieu> = nom de terminal, station, ville, planète ou système[/{C.DIM}]"
    )


def _place(obj) -> tuple[str, int]:
    """(nom, id terminal) à enregistrer pour un lieu choisi ; id 0 pour une planète ou un système."""
    from uexinfo.cache.models import Terminal
    return obj.name, (obj.id if isinstance(obj, Terminal) else 0)


@register("go", "g", "lieu")
def cmd_go(args: list[str], ctx) -> None:
    """Définit la position courante ou destination."""
    if args and args[0] in ("help", "?", "--help"):
        _show_help()
        return
    if not args:
        _show(ctx.player)
        return

    sub = args[0].lower()

    if sub == "clear":
        ctx.player.clear_location()
        ctx.player.clear_destination()
        _save_player(ctx)
        print_ok("Position et destination réinitialisées")
        return

    if sub in ("clear-dest", "cleardest", "dest-clear"):
        ctx.player.clear_destination()
        _save_player(ctx)
        print_ok("Destination effacée")
        return

    if sub == "from":
        name = " ".join(args[1:])
        if not name:
            print_error("Spécifie un lieu")
            return
        obj = _resolve(name, ctx)
        if obj is None:
            return
        ctx.player.set_location(*_place(obj))
        _save_player(ctx)
        print_ok(f"Position : {obj.name}")

    elif sub == "to":
        name = " ".join(args[1:])
        if not name:
            print_error("Spécifie un lieu")
            return
        obj = _resolve(name, ctx)
        if obj is None:
            return
        ctx.player.set_destination(*_place(obj))
        _save_player(ctx)
        print_ok(f"Destination : {obj.name}")

    else:
        name = " ".join(args)
        obj = _resolve(name, ctx)
        if obj is None:
            return
        ctx.player.set_location(*_place(obj))
        _save_player(ctx)
        print_ok(f"Position : {obj.name}")


def _show(player) -> None:
    """Affiche position et destination du joueur."""
    curr = player.location or "(non définie)"
    dest = player.destination or "(non définie)"
    console.print(f"  [bold]Position :[/bold]    [{C.UEX}]{curr}[/{C.UEX}]")
    console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{dest}[/{C.UEX}]")


def _resolve(name: str, ctx):
    """Lieu désigné par `name` : terminal, planète ou système, choisi selon la règle 3 (D11).

    Terminaux, planètes et systèmes ensemble : le niveau de correspondance départage
    (« hurston » = la planète, pas « Hurston Dynamics Showcase »). Un nom de lieu donne
    ses terminaux de commerce ; un terminal sans commerce (boutique) est remplacé par
    celui de son lieu. Plusieurs candidats ⇒ liste. Un nom inconnu n'est jamais
    enregistré tel quel. Renvoie None si introuvable ou annulé.
    """
    from uexinfo.cache.models import Terminal
    from uexinfo.cli.choose import choose
    obj = choose(ctx, name, {"terminal", "planet", "system"}, what="Lieu")
    if not isinstance(obj, Terminal) or (obj.type or "") == "commodity":
        return obj
    return _trade_terminal_of(obj, ctx)


def _trade_terminal_of(t, ctx):
    """Terminal de commerce ouvert du lieu de la boutique `t` (liste s'il y en a
    plusieurs) ; `t` lui-même si le lieu n'en a aucun."""
    from uexinfo.cli.choose import decide
    from uexinfo.names import EXACT, Match, Resolution, get_index, terminal_group, terminal_priority
    key = terminal_group(t)
    same = sorted((x for x in ctx.cache.terminals or []
                   if (x.type or "") == "commodity" and getattr(x, "is_available", 1) != 0
                   and terminal_group(x) == key), key=terminal_priority)
    if not same:
        return t
    idx = get_index(ctx)
    r = Resolution([Match(e, EXACT, 100.0) for x in same if (e := idx.by_ref("terminal", x.id))])
    return decide(ctx, r, t.name, title="Terminal de commerce") if r.matches else t


@register("arriver", "arrivé", "arrive", "arrived")
def cmd_arriver(args: list[str], ctx) -> None:
    """Le joueur est arrivé : la destination devient la position actuelle."""
    dest = (ctx.player.destination or "").strip()
    if not dest:
        print_error("Aucune destination définie — utilisez /go to <terminal>.")
        return
    ctx.player.set_location(dest, ctx.player.destination_id)
    ctx.player.clear_destination()
    _save_player(ctx)
    print_ok(f"Arrivé à : {dest}")


@register("dest", "d")
def cmd_dest(args: list[str], ctx) -> None:
    """Raccourci : /dest <lieu> = /go to <lieu>  ;  /dest clear = effacer"""
    if not args:
        dest = ctx.player.destination or "(non définie)"
        console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{dest}[/{C.UEX}]")
        return
    if args[0].lower() in ("clear", "effacer", "raz", "reset", "vider"):
        ctx.player.clear_destination()
        _save_player(ctx)
        print_ok("Destination effacée")
        return
    name = " ".join(args)
    obj = _resolve(name, ctx)
    if obj is None:
        return
    ctx.player.set_destination(*_place(obj))
    _save_player(ctx)
    print_ok(f"Destination : {obj.name}")
