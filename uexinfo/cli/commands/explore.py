"""Commande /explore — navigation hiérarchique des données (geo, vaisseaux, commodités)."""
from __future__ import annotations

from collections import defaultdict

from rich.table import Table

from uexinfo.cache.models import StarSystem, Terminal
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_warn, section


# ── Helpers ────────────────────────────────────────────────────────────────────

def _loc(name: str) -> str:
    return name.rsplit(" - ", 1)[-1].strip()


def _match(query: str, values) -> str | None:
    """Retourne la première valeur dont le nom (lowercase) commence par query."""
    q = query.lower()
    for v in values:
        if v.lower().startswith(q):
            return v
    return None


# ── Arbre géographique ─────────────────────────────────────────────────────────

def _geo_tree(ctx) -> dict:
    """
    {system_name: {body_name: {loc_name: [Terminal, ...]}}}
    body = planet_name OR orbit_name
    loc  = space_station_name OR city_name OR orbit_name (stripped service prefix)
    """
    tree: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for t in ctx.cache.terminals:
        sys  = t.star_system_name or "?"
        body = t.planet_name or t.orbit_name or t.star_system_name or "?"
        loc  = _loc(t.name)
        tree[sys][body][loc].append(t)
    return tree


# ── Niveaux d'affichage géo ────────────────────────────────────────────────────

def _show_root(ctx) -> None:
    section("Explorer")
    # Systèmes
    console.print(f"[bold {C.UEX}]Systèmes stellaires[/bold {C.UEX}]")
    for sys in sorted(ctx.cache.star_systems, key=lambda s: s.name):
        n_t = sum(1 for t in ctx.cache.terminals if t.star_system_name == sys.name)
        console.print(f"  [{C.UEX}]{sys.name.lower()}[/{C.UEX}]  [{C.DIM}]{n_t} terminaux[/{C.DIM}]")
    # Catégories virtuelles
    console.print()
    console.print(f"  [{C.UEX}]ship[/{C.UEX}]       [{C.DIM}]{len(ctx.cache.vehicles)} vaisseaux[/{C.DIM}]")
    console.print(f"  [{C.UEX}]commodity[/{C.UEX}]  [{C.DIM}]{len(ctx.cache.commodities)} commodités[/{C.DIM}]")
    console.print(f"\n[{C.DIM}]Navigation : /explore <chemin>  ex: /explore stanton.hurston.lorville[/{C.DIM}]")


def _show_system(sys_name: str, tree: dict, ctx) -> None:
    bodies = tree.get(sys_name, {})
    if not bodies:
        print_warn(f"Aucune donnée pour le système '{sys_name}'")
        return
    section(f"Système — {sys_name}")
    tbl = Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column(style=C.UEX, no_wrap=True)
    tbl.add_column(style=C.DIM, justify="right")
    tbl.add_column(style=C.DIM)
    for body, locs in sorted(bodies.items()):
        n_locs = len(locs)
        n_t    = sum(len(ts) for ts in locs.values())
        tbl.add_row(body.lower(), f"{n_locs} lieux", f"{n_t} terminaux")
    console.print(tbl)
    console.print(f"\n[{C.DIM}]→ /explore {sys_name.lower()}.<planète>[/{C.DIM}]")


def _show_body(sys_name: str, body_name: str, locs: dict, ctx) -> None:
    section(f"{sys_name} › {body_name}")
    tbl = Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column(style=C.UEX, no_wrap=True)
    tbl.add_column(style=C.DIM, justify="right")
    tbl.add_column(style=C.DIM)
    for loc, terminals in sorted(locs.items()):
        types = {t.type for t in terminals if t.type}
        type_str = " · ".join(sorted(types)) if types else "terminal"
        tbl.add_row(loc.lower(), f"{len(terminals)} terminaux", type_str)
    console.print(tbl)
    console.print(f"\n[{C.DIM}]→ /explore {sys_name.lower()}.{body_name.lower()}.<lieu>[/{C.DIM}]")


def _show_location(sys_name: str, body_name: str, loc_name: str, terminals: list[Terminal], ctx) -> None:
    # Si un seul terminal effectif → déléguer à /info
    from uexinfo.cli.commands.info import _show_terminal
    if len(terminals) == 1:
        _show_terminal(terminals[0], ctx)
        return

    section(f"{sys_name} › {body_name} › {loc_name}")
    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Terminal", style=C.NEUTRAL, no_wrap=True, min_width=20)
    tbl.add_column("Type",     style=C.DIM)
    tbl.add_column("Cargo max", style=C.DIM, justify="right")
    for t in sorted(terminals, key=lambda t: t.name):
        flags = []
        if t.has_loading_dock:  flags.append("dock")
        if t.has_docking_port:  flags.append("port")
        if t.has_freight_elevator: flags.append("fret")
        if t.is_refinery:       flags.append("raffinerie")
        if t.is_player_owned:   flags.append("[dim]joueur[/dim]")
        flag_str = " · ".join(flags)
        cargo = f"{t.max_container_size} SCU" if t.max_container_size else "—"
        tbl.add_row(t.name, flag_str or t.type or "—", cargo)
    console.print(tbl)
    console.print(f"\n[{C.DIM}]/info {loc_name} pour les prix du marché[/{C.DIM}]")


# ── Vaisseaux ──────────────────────────────────────────────────────────────────

def _mfr_slug(manufacturer: str) -> str:
    """Premier mot du fabricant, minuscules : 'Crusader Industries' → 'crusader'."""
    return manufacturer.lower().split()[0] if manufacturer else "autre"


def _search_ships(query: str, ctx) -> list:
    """Recherche multi-stratégie : fabricant → slug → sous-chaîne nom."""
    q = query.lower()
    vehicles = ctx.cache.vehicles

    # 1. Fabricant — prefix complet
    m = [v for v in vehicles if (v.manufacturer or "").lower().startswith(q)]
    if m:
        return m

    # 2. Fabricant — slug (premier mot) ex: "crusader" → "Crusader Industries"
    m = [v for v in vehicles if _mfr_slug(v.manufacturer).startswith(q)]
    if m:
        return m

    # 3. Nom complet — n'importe quel mot commence par q ("titan" → "Avenger Titan")
    m = [v for v in vehicles
         if any(w.startswith(q) for w in v.name_full.lower().split())]
    if m:
        return m

    # 4. Sous-chaîne partout dans le nom complet
    return [v for v in vehicles if q in v.name_full.lower()]


def _ship_table(vehicles: list) -> Table:
    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Vaisseau",  style=C.NEUTRAL, no_wrap=True, min_width=26)
    tbl.add_column("SCU",  style=C.UEX, justify="right")
    tbl.add_column("Éq.", style=C.DIM, justify="right")
    tbl.add_column("Pad",  style=C.DIM, justify="center")
    tbl.add_column("Rôles", style=C.DIM)
    for v in sorted(vehicles, key=lambda v: v.name_full):
        roles = []
        if v.is_cargo:         roles.append("cargo")
        if v.is_mining:        roles.append("mining")
        if v.is_salvage:       roles.append("salvage")
        if v.is_military:      roles.append("combat")
        if v.is_ground_vehicle: roles.append("ground")
        if v.is_concept:       roles.append("[dim]concept[/dim]")
        scu = str(v.scu) if v.scu else "—"
        tbl.add_row(v.name_full, scu, v.crew or "?", v.pad_type or "?",
                    " · ".join(roles) or "—")
    return tbl


def _show_ships_root(ctx) -> None:
    if not ctx.cache.vehicles:
        print_warn("Données vaisseaux non disponibles — lancez /refresh")
        return
    section("Vaisseaux")
    by_mfr: dict[str, list] = defaultdict(list)
    for v in ctx.cache.vehicles:
        by_mfr[v.manufacturer or "Autre"].append(v)
    tbl = Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column(style=C.UEX, no_wrap=True)
    tbl.add_column(style=C.DIM, justify="right")
    tbl.add_column(style=C.DIM)
    for mfr, ships in sorted(by_mfr.items()):
        slug = _mfr_slug(mfr)
        tbl.add_row(mfr, f"{len(ships)} vaisseaux", f"[dim]→ ship.{slug}[/dim]")
    console.print(tbl)
    console.print(f"\n[{C.DIM}]/explore ship.<fabricant|nom partiel>  ex: ship.anvil  ship.titan[/{C.DIM}]")


def _show_ships_query(query: str, ctx) -> None:
    matched = _search_ships(query, ctx)
    if not matched:
        print_warn(f"Aucun vaisseau pour '{query}'")
        return

    # Grouper par fabricant si plusieurs fabricants
    by_mfr: dict[str, list] = defaultdict(list)
    for v in matched:
        by_mfr[v.manufacturer or "?"].append(v)

    if len(by_mfr) == 1:
        mfr_label = list(by_mfr.keys())[0]
        section(f"Vaisseaux — {mfr_label}")
        console.print(_ship_table(matched))
    else:
        section(f"Vaisseaux — « {query} »  ({len(matched)} résultats)")
        for mfr, ships in sorted(by_mfr.items()):
            console.print(f"[bold {C.UEX}]{mfr}[/bold {C.UEX}]")
            console.print(_ship_table(ships))
            console.print()


# ── Commodités ─────────────────────────────────────────────────────────────────

def _show_commodities_root(ctx) -> None:
    section("Commodités")
    by_kind: dict[str, int] = defaultdict(int)
    for c in ctx.cache.commodities:
        by_kind[c.kind or "Autre"] += 1
    tbl = Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column(style=C.UEX, no_wrap=True)
    tbl.add_column(style=C.DIM, justify="right")
    for kind, count in sorted(by_kind.items()):
        tbl.add_row(kind, f"{count}")
    console.print(tbl)
    console.print(f"\n[{C.DIM}]→ /explore commodity.<catégorie>  ou  /explore commodity.<nom>[/{C.DIM}]")


def _show_commodities_kind(kind_query: str, rest: list[str], ctx) -> None:
    from uexinfo.cli.commands.info import _show_commodity, _find_commodity
    q = kind_query.lower()

    # Try as kind category first
    by_kind = [c for c in ctx.cache.commodities if (c.kind or "autre").lower().startswith(q)]
    if by_kind:
        if rest:
            # Drill into commodity name
            comm_q = rest[0].lower()
            found = next((c for c in by_kind if c.name.lower().startswith(comm_q)), None)
            if found:
                _show_commodity(found, ctx)
            else:
                print_warn(f"Commodité introuvable dans '{kind_query}' : '{rest[0]}'")
        else:
            section(f"Commodités — {by_kind[0].kind or kind_query}")
            for c in sorted(by_kind, key=lambda c: c.name):
                flags = []
                if c.is_illegal:     flags.append("[red]illégal[/red]")
                if c.is_refinable:   flags.append("raffinable")
                flag_str = "  " + " · ".join(flags) if flags else ""
                console.print(f"  [{C.NEUTRAL}]{c.name}[/{C.NEUTRAL}]  [{C.DIM}]{c.code}[/{C.DIM}]{flag_str}")
        return

    # Try as commodity name directly
    c = _find_commodity(kind_query, ctx)
    if c:
        _show_commodity(c, ctx)
        return

    print_warn(f"Catégorie ou commodité introuvable : '{kind_query}'")


# ── Navigateur géo ─────────────────────────────────────────────────────────────

def _explore_geo(sys_name: str, parts: list[str], ctx) -> None:
    tree = _geo_tree(ctx)

    # Find matching system (case-insensitive prefix)
    sys_key = _match(sys_name, tree.keys())
    if not sys_key:
        print_warn(f"Système introuvable : '{sys_name}'")
        return

    bodies = tree[sys_key]

    if not parts:
        _show_system(sys_key, tree, ctx)
        return

    # Level 2: body (planet/orbit)
    body_query = parts[0]
    body_key = _match(body_query, bodies.keys())

    if body_key and len(parts) == 1:
        _show_body(sys_key, body_key, bodies[body_key], ctx)
        return

    if body_key and len(parts) >= 2:
        locs = bodies[body_key]
        loc_query = parts[1]
        loc_key = _match(loc_query, locs.keys())
        if loc_key:
            _show_location(sys_key, body_key, loc_key, locs[loc_key], ctx)
            return
        print_warn(f"Lieu introuvable dans {sys_key} › {body_key} : '{loc_query}'")
        return

    # If body not found, try searching location name directly across all bodies
    for bname, locs in bodies.items():
        loc_key = _match(body_query, locs.keys())
        if loc_key:
            _show_location(sys_key, bname, loc_key, locs[loc_key], ctx)
            return

    print_warn(f"'{body_query}' introuvable dans {sys_key}")


# ── Commande principale ────────────────────────────────────────────────────────

@register("explore")
def cmd_explore(args: list[str], ctx) -> None:
    path = args[0] if args else ""
    # Normaliser les underscores en espaces dans chaque segment
    parts = [p.strip().replace("_", " ") for p in path.split(".") if p.strip()] if path else []

    if not parts:
        _show_root(ctx)
        return

    root = parts[0].lower()
    rest = parts[1:]

    if root == "ship":
        if not rest:
            _show_ships_root(ctx)
        elif len(rest) == 1:
            _show_ships_query(rest[0], ctx)
        else:
            # ship.crusader.m2 → filtrer d'abord par fabricant, puis par nom
            mfr_q, name_q = rest[0], rest[1]
            by_mfr = _search_ships(mfr_q, ctx)
            q2 = name_q.lower()
            refined = [v for v in by_mfr
                       if any(w.startswith(q2) for w in v.name_full.lower().split())
                       or q2 in v.name_full.lower()]
            if not refined:
                refined = _search_ships(name_q, ctx)  # fallback sans filtre fabricant
            if refined:
                by_mfr2: dict[str, list] = defaultdict(list)
                for v in refined:
                    by_mfr2[v.manufacturer or "?"].append(v)
                label = f"{rest[0]}.{rest[1]}"
                section(f"Vaisseaux — « {label} »  ({len(refined)} résultats)")
                for mfr, ships in sorted(by_mfr2.items()):
                    if len(by_mfr2) > 1:
                        console.print(f"[bold {C.UEX}]{mfr}[/bold {C.UEX}]")
                    console.print(_ship_table(ships))
                    if len(by_mfr2) > 1:
                        console.print()
            else:
                print_warn(f"Aucun vaisseau pour '{mfr_q}.{name_q}'")
        return

    if root == "commodity":
        if not rest:
            _show_commodities_root(ctx)
        else:
            _show_commodities_kind(rest[0], rest[1:], ctx)
        return

    # Geo: system navigation
    _explore_geo(root, rest, ctx)
