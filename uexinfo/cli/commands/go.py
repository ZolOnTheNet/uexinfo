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


def _lookup_terminal_id(resolved_name: str, ctx) -> int:
    """Retourne l'ID du terminal dont le nom canonique correspond exactement, ou 0."""
    for t in ctx.cache.terminals:
        if t.name == resolved_name:
            return t.id
    return 0


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
        resolved = _resolve(name, ctx)
        if resolved is None:
            return
        ctx.player.set_location(resolved, _lookup_terminal_id(resolved, ctx))
        _save_player(ctx)
        print_ok(f"Position : {resolved}")

    elif sub == "to":
        name = " ".join(args[1:])
        if not name:
            print_error("Spécifie un lieu")
            return
        resolved = _resolve(name, ctx)
        if resolved is None:
            return
        ctx.player.set_destination(resolved, _lookup_terminal_id(resolved, ctx))
        _save_player(ctx)
        print_ok(f"Destination : {resolved}")

    else:
        name = " ".join(args)
        resolved = _resolve(name, ctx)
        if resolved is None:
            return
        ctx.player.set_location(resolved, _lookup_terminal_id(resolved, ctx))
        _save_player(ctx)
        print_ok(f"Position : {resolved}")


def _show(player) -> None:
    curr = player.location or "(non définie)"
    dest = player.destination or "(non définie)"
    console.print(f"  [bold]Position :[/bold]    [{C.UEX}]{curr}[/{C.UEX}]")
    console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{dest}[/{C.UEX}]")


def _resolve(name: str, ctx) -> str | None:
    """Résout un nom de lieu vers le nom canonique UEX (résolveur unique, uexinfo/names).

    Retourne le nom résolu, ou None si l'utilisateur a annulé la sélection.
    Retourne le nom brut si le lieu n'est pas dans le cache (Pyro, etc.).
    Un lieu donne son terminal principal (Admin > TDD > centre cargo) ; un picker
    n'est affiché qu'en cas de vraie égalité (ex: deux Nyx Gateway).
    """
    from uexinfo.cache.data_manager import _loc_short
    from uexinfo.names import SUBSTRING, resolve

    # Terminaux, planètes et systèmes ensemble : le niveau de correspondance
    # départage (« hurston » = la planète, pas « Hurston Dynamics Showcase »).
    r = resolve(ctx, name, kinds={"terminal", "planet", "system"}, min_level=SUBSTRING)
    if r.matches and not r.ambiguous:
        if r.matches[0].entity.kind == "terminal":
            from uexinfo.names import trading_terminal
            return trading_terminal(ctx.cache.terminals, r.best).name
        return r.best.name
    if r.ambiguous:
        from uexinfo.cli.selector import SelectItem, pick
        items = [
            SelectItem(label=_loc_short(t.name), value=t, meta=t.star_system_name or "")
            for t in r.candidates[:20]
        ]
        chosen = pick(ctx, items, title=f"Destination — «{name}»", mode="single")
        if chosen:
            return chosen[0].value.name
        # CLI : afficher la liste et demander de préciser
        console.print(f"[{C.WARNING}]Plusieurs lieux correspondent à «{name}» — précisez :[/{C.WARNING}]")
        for it in items:
            meta = f"  [{C.DIM}]{it.meta}[/{C.DIM}]" if it.meta else ""
            console.print(f"  [{C.UEX}]{it.label}[/{C.UEX}]{meta}")
        return None

    # Inconnu (Pyro, lieu perso) → accepter tel quel avec avertissement
    from uexinfo.display.formatter import print_warn
    print_warn(f"Lieu «{name}» non trouvé dans le cache — accepté tel quel")
    return name


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
    resolved = _resolve(name, ctx)
    if resolved is None:
        return
    ctx.player.set_destination(resolved, _lookup_terminal_id(resolved, ctx))
    _save_player(ctx)
    print_ok(f"Destination : {resolved}")
