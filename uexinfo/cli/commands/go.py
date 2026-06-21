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


# ── Priorité trading ───────────────────────────────────────────────────────────

_TRADING_SVCS = {"admin", "tdd", "trade"}


def _tp(t) -> int:
    """Trading priority : 0 = TDD, 1 = Admin/Trade, 2 = autres."""
    if " - " not in t.name:
        return 2
    svc = t.name.split(" - ")[0].strip().lower()
    if svc == "tdd":
        return 0
    if svc in _TRADING_SVCS:
        return 1
    return 2


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
        ctx.player.location = ""
        ctx.player.destination = ""
        ctx.player.location_id = 0
        ctx.player.destination_id = 0
        _save_player(ctx)
        print_ok("Position et destination réinitialisées")
        return

    if sub in ("clear-dest", "cleardest", "dest-clear"):
        ctx.player.destination = ""
        ctx.player.destination_id = 0
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
        ctx.player.location_id = _lookup_terminal_id(resolved, ctx)
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
        ctx.player.destination_id = _lookup_terminal_id(resolved, ctx)
        _save_player(ctx)
        print_ok(f"Destination : {resolved}")

    else:
        name = " ".join(args)
        resolved = _resolve(name, ctx)
        if resolved is None:
            return
        ctx.player.location = resolved
        ctx.player.location_id = _lookup_terminal_id(resolved, ctx)
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

    Quand plusieurs terminaux correspondent au même lieu, préfère automatiquement
    le terminal de trading (TDD > Admin/Trade > autres) sans afficher de picker.
    Un picker n'est affiché que si deux terminaux ont la même priorité (vraie ambiguïté).
    """
    from uexinfo.cache.data_manager import _loc_short
    q = name.lower().strip().replace("_", " ")

    # Match exact sur code ou nom complet (non ambigu)
    for t in ctx.cache.terminals:
        if t.code.lower() == q or t.name.lower() == q:
            return t.name

    # Candidats :
    # - loc court == q  (ex: "orison" → Orison Municipal Services)
    # - loc_tail == q et loc != q  (ex: "tdd - orison" → tail="orison")
    # - loc court commence par q  (ex: "seraph" pour "seraphim station")
    # - q commence par loc court  (ex: q="cru-l5 admin" pour loc="cru-l5")
    candidates = []
    seen_locs: set[str] = set()
    for t in ctx.cache.terminals:
        loc = _loc_short(t.name).lower()
        loc_tail = loc.rsplit(" - ", 1)[-1]
        if (loc == q or (loc_tail == q and loc != q)
                or loc.startswith(q) or q.startswith(loc + " ")):
            if loc not in seen_locs:
                seen_locs.add(loc)
                candidates.append(t)

    if len(candidates) == 1:
        return candidates[0].name

    if len(candidates) > 1:
        # Préférence automatique selon la priorité de trading :
        # TDD (0) > Admin/Trade (1) > autres (2)
        # Si le meilleur niveau est unique → retour direct sans picker.
        # Si plusieurs candidats ont le même niveau minimal → picker.
        best_prio = min(_tp(t) for t in candidates)
        best = [t for t in candidates if _tp(t) == best_prio]
        if len(best) == 1:
            return best[0].name

        # Vraie ambiguïté (ex: deux TDD dans des systèmes différents) → picker
        from uexinfo.cli.selector import SelectItem, pick
        items = [
            SelectItem(label=_loc_short(t.name), value=t, meta=t.star_system_name or "")
            for t in best[:20]
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
    ctx.player.location_id = ctx.player.destination_id
    ctx.player.destination = ""
    ctx.player.destination_id = 0
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
        ctx.player.destination_id = 0
        _save_player(ctx)
        print_ok("Destination effacée")
        return
    name = " ".join(args)
    resolved = _resolve(name, ctx)
    if resolved is None:
        return
    ctx.player.destination = resolved
    ctx.player.destination_id = _lookup_terminal_id(resolved, ctx)
    _save_player(ctx)
    print_ok(f"Destination : {resolved}")
