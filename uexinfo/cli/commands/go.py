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
        ctx.player.location = ""
        ctx.player.destination = ""
        _save_player(ctx)
        print_ok("Position et destination réinitialisées")
        return

    if sub in ("clear-dest", "cleardest", "dest-clear"):
        ctx.player.destination = ""
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
        ctx.player.location = resolved
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
        ctx.player.destination = resolved
        _save_player(ctx)
        print_ok(f"Destination : {resolved}")

    else:
        name = " ".join(args)
        resolved = _resolve(name, ctx)
        if resolved is None:
            return
        ctx.player.location = resolved
        _save_player(ctx)
        print_ok(f"Position : {resolved}")


def _show(player) -> None:
    curr = player.location or "(non définie)"
    dest = player.destination or "(non définie)"
    console.print(f"  [bold]Position :[/bold]    [{C.UEX}]{curr}[/{C.UEX}]")
    console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{dest}[/{C.UEX}]")


def _resolve(name: str, ctx) -> str | None:
    """Résout un nom de lieu vers le nom canonique UEX.

    Retourne le nom résolu, ou None si l'utilisateur a annulé la sélection.
    Retourne le nom brut si le lieu n'est pas dans le cache (Pyro, etc.).
    """
    from uexinfo.cache.data_manager import _loc_short
    q = name.lower().strip().replace("_", " ")

    # Match exact (nom complet, code ou nom court)
    for t in ctx.cache.terminals:
        if t.code.lower() == q or t.name.lower() == q or _loc_short(t.name).lower() == q:
            return t.name

    # Candidats : loc court préfixe de q, ou q préfixe de loc court,
    # ou loc court contenu dans q (ex: "seraphim" dans "seraphim station")
    candidates = []
    seen_locs: set[str] = set()
    for t in ctx.cache.terminals:
        loc = _loc_short(t.name).lower()
        if (loc.startswith(q) or q.startswith(loc + " ") or loc == q):
            if loc not in seen_locs:
                seen_locs.add(loc)
                candidates.append(t)

    if len(candidates) == 1:
        return candidates[0].name

    if len(candidates) > 1:
        from uexinfo.cli.selector import SelectItem, pick
        items = [
            SelectItem(label=_loc_short(t.name), value=t, meta=t.star_system_name or "")
            for t in candidates[:20]
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

    # Planètes et systèmes (match exact)
    for p in ctx.cache.planets:
        if p.name.lower() == q:
            return p.name
    for s in ctx.cache.star_systems:
        if s.name.lower() == q:
            return s.name

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
    ctx.player.location = dest
    ctx.player.destination = ""
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
        ctx.player.destination = ""
        _save_player(ctx)
        print_ok("Destination effacée")
        return
    name = " ".join(args)
    resolved = _resolve(name, ctx)
    if resolved is None:
        return
    ctx.player.destination = resolved
    _save_player(ctx)
    print_ok(f"Destination : {resolved}")
