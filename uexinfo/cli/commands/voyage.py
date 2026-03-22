"""Commande /voyage — planification de voyages (ensemble de missions)."""
from __future__ import annotations

from rich.table import Table

from uexinfo.cli.commands import register
from uexinfo.cli.selector import SelectItem, pick
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.models.voyage import Voyage

# Sous-commandes reconnues
_SUBS = frozenset({
    "on", "off", "new", "list", "name", "clear",
    "add", "remove", "copy", "accept", "later", "cancel",
    # alias français
    "activer", "désactiver", "nouveau", "liste",
    "renommer", "effacer", "ajouter", "retirer", "supprimer",
    "valider", "garder", "annuler",
    # flag --trajets
    "--trajets",
})


@register("voyage", "v")
def cmd_voyage(args: list[str], ctx) -> None:
    """Planification de voyages (ensemble de missions)."""
    vm = ctx.voyage_manager
    voyage, sub, rest = _resolve(args, ctx)

    if not sub:
        # /voyage sans args → liste ou info
        if voyage:
            _cmd_show(voyage, ctx)
        else:
            _cmd_list(ctx)
        return

    if sub in ("on", "activer"):
        # /voyage on <ref> → activer le voyage donné
        if voyage is None and rest:
            voyage = vm.get(rest[0])
            if voyage is None:
                print_warn(f"Voyage introuvable : {rest[0]}")
                return
        if voyage:
            vm.activate(str(voyage.id))
            print_ok(f"Voyage activé : [{C.UEX}]{voyage.name}[/{C.UEX}]")
        else:
            active = vm.get_active()
            if active:
                print_ok(f"Voyage déjà actif : [{C.UEX}]{active.name}[/{C.UEX}]")
            else:
                v = vm.new_voyage(departure=_player_loc(ctx))
                print_ok(f"Nouveau voyage créé et activé : [{C.UEX}]{v.name}[/{C.UEX}]")

    elif sub in ("off", "désactiver"):
        if not _require_active(vm):
            return
        vm.deactivate()
        print_ok("Voyage désactivé — conservé pour reprise ultérieure.")

    elif sub in ("new", "nouveau"):
        name = " ".join(rest) if rest else None
        v = vm.new_voyage(name=name, departure=_player_loc(ctx))
        print_ok(f"Nouveau voyage créé et activé : [{C.UEX}]{v.name}[/{C.UEX}]  "
                 f"[{C.DIM}](#{v.id})[/{C.DIM}]")

    elif sub in ("name", "renommer"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        if not rest:
            print_error("Nom manquant : /voyage name <nouveau_nom>")
            return
        old = target.name
        target.name = " ".join(rest)
        vm.update(target)
        print_ok(f"Renommé : {old} → [{C.UEX}]{target.name}[/{C.UEX}]")

    elif sub in ("list", "liste"):
        if "--trajets" in args or (voyage is None and vm.get_active() is None):
            _cmd_list(ctx)
        else:
            target = voyage or vm.get_active()
            if target:
                _cmd_show(target, ctx)
            else:
                _cmd_list(ctx)

    elif sub in ("clear", "effacer"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        n = len(target.mission_ids)
        target.mission_ids.clear()
        vm.update(target)
        print_ok(f"{n} mission(s) retirée(s) du voyage [{C.UEX}]{target.name}[/{C.UEX}]")

    elif sub in ("add", "ajouter"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        _cmd_add(rest, target, ctx)

    elif sub in ("remove", "retirer", "supprimer"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        _cmd_remove(rest, target, ctx)

    elif sub == "copy":
        source = voyage or vm.get_active()
        if not source:
            _no_active()
            return
        dest_ref = rest[0] if rest else None
        new_v = vm.copy_to(source, dest_ref)
        print_ok(f"Copié vers : [{C.UEX}]{new_v.name}[/{C.UEX}]  [{C.DIM}](#{new_v.id})[/{C.DIM}]")

    elif sub in ("accept", "valider"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        _cmd_show(target, ctx)
        _run_analysis(target, ctx)
        if not voyage:  # ne désactive que si c'était le voyage actif
            vm.deactivate()

    elif sub in ("later", "garder"):
        if vm.get_active():
            vm.deactivate()
            print_ok("Voyage sauvegardé. Reprenez avec /voyage on ou /voyage <nom>.")

    elif sub in ("cancel", "annuler"):
        # Recharge depuis le disque (état précédent)
        vm._load()
        print_warn("Modifications annulées — retour à la dernière sauvegarde.")

    else:
        _show_help()


# ── Résolution voyage + sous-commande ────────────────────────────────────────

def _resolve(args: list[str], ctx) -> tuple[Voyage | None, str, list[str]]:
    """
    Analyse les args :
      - Flag -n<ref> ou -n <ref> → voyage explicite
      - Premier token non-sous-commande correspondant à un voyage → voyage explicite
      - Token suivant (ou premier si voyage résolu) = sous-commande
    Retourne (voyage_cible | None, sous_commande | "", args_restants).
    """
    vm = ctx.voyage_manager
    voyage: Voyage | None = None
    cleaned = list(args)

    # Chercher -n flag
    i = 0
    while i < len(cleaned):
        a = cleaned[i]
        if a == "-n" and i + 1 < len(cleaned):
            voyage = vm.get(cleaned[i + 1])
            cleaned = cleaned[:i] + cleaned[i + 2:]
            break
        if a.startswith("-n") and len(a) > 2:
            voyage = vm.get(a[2:])
            cleaned = cleaned[:i] + cleaned[i + 1:]
            break
        i += 1

    if not cleaned:
        return voyage, "", []

    # Premier token : est-ce une référence de voyage ou une sous-commande ?
    first = cleaned[0].lower()
    if first not in _SUBS and voyage is None:
        candidate = vm.get(cleaned[0])
        if candidate:
            voyage = candidate
            cleaned = cleaned[1:]

    if not cleaned:
        return voyage, "", []

    sub = cleaned[0].lower()
    rest = cleaned[1:]

    if sub in _SUBS:
        return voyage, sub, rest

    # Pas reconnu
    return voyage, sub, rest


# ── Affichage liste de voyages ────────────────────────────────────────────────

def _cmd_list(ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager
    if not vm.voyages:
        print_warn("Aucun voyage enregistré")
        console.print(f"[{C.DIM}]/voyage new [nom]  pour créer un voyage[/{C.DIM}]")
        return

    section("Voyages")

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("#",        style=C.DIM,    width=3,  justify="right")
    tbl.add_column("*",        width=2)
    tbl.add_column("Nom",      style=C.LABEL,  max_width=18)
    tbl.add_column("Miss.",    justify="right", width=6)
    tbl.add_column("SCU",      justify="right", width=6)
    tbl.add_column("Récomp.",  justify="right", width=13)
    tbl.add_column("Départ",   style=C.UEX,    max_width=14)
    tbl.add_column("→",        style=C.DIM,    width=1)
    tbl.add_column("Arrivée",  style=C.UEX,    max_width=14)
    tbl.add_column("Session",  style=C.DIM,    width=7)

    for v in vm.voyages:
        is_active = v.id == vm.active_id
        bullet = f"[{'yellow' if is_active else C.DIM}]●[/{'yellow' if is_active else C.DIM}]"
        missions = [mm.get(str(mid)) for mid in v.mission_ids]
        missions = [m for m in missions if m]
        n_miss = len(missions)
        total_scu = sum(m.total_scu for m in missions)
        total_rew = sum(m.reward_uec for m in missions)
        rew_str = f"{total_rew:,}".replace(",", " ") + " aUEC"
        scu_str = f"{total_scu:.0f}□" if total_scu else "—"
        dep = v.departure or "—"
        arr = v.arrival or _infer_arrival(missions) or "—"

        tbl.add_row(
            str(v.id), bullet, v.name,
            f"{n_miss}m", scu_str, rew_str,
            dep, "→", arr,
            f"S{v.session_id}",
        )

    console.print(tbl)
    console.print(
        f"\n[{C.DIM}]Double-clic sur un nom → afficher  ·  "
        f"Clic droit → menu (Activer, Analyser…)[/{C.DIM}]"
    )
    console.print(f"[{C.DIM}]/voyage new  ·  /voyage <nom>  ·  /voyage on[/{C.DIM}]")


# ── Affichage missions d'un voyage ────────────────────────────────────────────

def _cmd_show(voyage: Voyage, ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager
    is_active = voyage.id == vm.active_id
    active_label = f"  [yellow]●[/yellow]" if is_active else ""

    dep = voyage.departure or "?"
    arr = voyage.arrival or _infer_arrival(
        [m for m in (mm.get(str(mid)) for mid in voyage.mission_ids) if m]
    ) or "?"

    section(f"Voyage : {voyage.name}{active_label}")
    console.print(
        f"  [{C.DIM}]Départ : [{C.UEX}]{dep}[/{C.UEX}]  →  Arrivée : [{C.UEX}]{arr}[/{C.UEX}][/{C.DIM}]"
    )

    if not voyage.mission_ids:
        print_warn("Aucune mission dans ce voyage")
        console.print(f"[{C.DIM}]/voyage add <id|nom>  pour ajouter des missions[/{C.DIM}]")
        return

    graph = ctx.cache.transport_graph

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("#",          style=C.DIM,    width=3,  justify="right")
    tbl.add_column("Nom",        style=C.LABEL,  max_width=22)
    tbl.add_column("Départ",     style=C.UEX,    max_width=16)
    tbl.add_column("→",          style=C.DIM,    width=1)
    tbl.add_column("Arrivée",    style=C.UEX,    max_width=16)
    tbl.add_column("Dist",       justify="right", width=7)
    tbl.add_column("SCU",        justify="right", width=4)
    tbl.add_column("Récompense", justify="right", width=12)
    tbl.add_column("Tags",       width=6)

    total_scu = 0.0
    total_rew = 0

    for mid in voyage.mission_ids:
        m = mm.get(str(mid))
        if not m:
            tbl.add_row(str(mid), f"[{C.WARNING}]mission #{mid} introuvable[/{C.WARNING}]",
                        "—", "→", "—", "—", "—", "—", "")
            continue

        srcs = ", ".join(m.all_sources[:2]) or "—"
        dsts = ", ".join(m.all_destinations[:2]) or "—"
        scu_str = f"{m.total_scu:.0f}□" if m.total_scu else "—"
        rew_str = f"{m.reward_uec:,}".replace(",", " ") + " aUEC"
        total_scu += m.total_scu
        total_rew += m.reward_uec

        # Synergies depuis manager
        tags = " ".join(mm.synergies_for_voyage(m, voyage.mission_ids))

        dist_str = "?"
        if m.all_sources and m.all_destinations:
            try:
                result = graph.find_shortest_path(m.all_sources[0], m.all_destinations[0])
                if result is not None and result.total_distance is not None:
                    d = result.total_distance
                    dist_str = f"{d:.1f}Gm" if d >= 1 else f"{d*1000:.0f}Mm"
            except Exception:
                pass

        has_delay = any(o.time_cost for o in m.objectives)
        name_label = m.name + (f" [{C.WARNING}]⏱[/{C.WARNING}]" if has_delay else "")

        tbl.add_row(str(mid), name_label, srcs, "→", dsts, dist_str, scu_str, rew_str, tags)

    console.print(tbl)

    rew_str = f"{total_rew:,}".replace(",", " ")
    console.print(
        f"\n[{C.DIM}]{len(voyage.mission_ids)} mission(s) · "
        f"[bold]{total_scu:.0f}[/bold] SCU · "
        f"[bold]{rew_str}[/bold] aUEC[/{C.DIM}]"
    )
    if is_active:
        console.print(
            f"[{C.DIM}]/voyage add <m>  ·  /voyage remove <m>  ·  "
            f"/voyage accept  ·  /voyage off[/{C.DIM}]"
        )


# ── Add missions ──────────────────────────────────────────────────────────────

def _cmd_add(args: list[str], voyage: Voyage, ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager

    if not args:
        if not mm.missions:
            print_warn("Catalogue vide — /mission add pour créer des missions")
            return
        items = [
            SelectItem(
                label    = f"#{m.id}  {m.name}",
                value    = m,
                meta     = (
                    "→".join(filter(None, m.all_sources[:1] + m.all_destinations[:1])) or "—"
                ) + f"  {m.reward_uec:,} aUEC",
                selected = m.id in voyage.mission_ids,
            )
            for m in mm.missions
        ]
        chosen = pick(ctx, items,
                      title=f"Missions → {voyage.name}",
                      mode="multi",
                      confirm_label="✓ Ajouter")
        if chosen is None:
            print_warn("Annulé.")
            return
        to_add = [it.value.id for it in chosen
                  if it.value.id not in voyage.mission_ids]
        if to_add:
            n = vm.add_missions(voyage, to_add)
            added_names = ", ".join(
                mm.get(str(mid)).name for mid in to_add if mm.get(str(mid))
            )
            print_ok(f"{n} mission(s) ajoutée(s) à [{C.UEX}]{voyage.name}[/{C.UEX}] : {added_names}")
        else:
            console.print(f"[{C.DIM}]Aucune nouvelle mission sélectionnée.[/{C.DIM}]")
        return

    added = []
    not_found = []
    for ref in args:
        m = mm.get(ref)
        if not m:
            not_found.append(ref)
            continue
        n = vm.add_missions(voyage, [m.id])
        if n:
            added.append(m.name)

    if added:
        print_ok(f"Ajouté(s) à [{C.UEX}]{voyage.name}[/{C.UEX}] : {', '.join(added)}")
    if not_found:
        print_warn(f"Mission(s) introuvable(s) : {', '.join(not_found)}")
    if not added and not not_found:
        console.print(f"[{C.DIM}]Toutes ces missions sont déjà dans le voyage.[/{C.DIM}]")


# ── Remove mission ────────────────────────────────────────────────────────────

def _cmd_remove(args: list[str], voyage: Voyage, ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager
    if not args:
        print_error("Identifiant de mission manquant")
        return
    for ref in args:
        m = mm.get(ref)
        if not m:
            print_warn(f"Mission introuvable : {ref}")
            continue
        if vm.remove_mission(voyage, m.id):
            print_ok(f"Retiré de [{C.UEX}]{voyage.name}[/{C.UEX}] : {m.name}")
        else:
            print_warn(f"{m.name} n'est pas dans ce voyage")


# ── Analyse TSP + distances ───────────────────────────────────────────────────

def _fmt_dist(d: float | None) -> str:
    if d is None:
        return "?"
    return f"{d:.1f}Gm" if d >= 1 else f"{d*1000:.0f}Mm"


def _path_dist(graph, a: str | None, b: str | None) -> float | None:
    """Distance entre deux nœuds résolus (None si injoignable)."""
    if not a or not b:
        return None
    if a == b:
        return 0.0
    try:
        r = graph.find_shortest_path(a, b)
        return r.total_distance if r is not None else None
    except Exception:
        return None


def _resolve_locs(raw_locs: list[str], graph) -> dict[str, str | None]:
    """Résout une liste de noms bruts en nœuds du graphe (fuzzy)."""
    from uexinfo.cache.mission_scan import _resolve_graph_node
    resolved: dict[str, str | None] = {}
    # Premier passage : résoudre les non-gateways pour dériver le system_hint
    from uexinfo.cache.mission_scan import _node_system
    system_counts: dict[str, int] = {}
    for loc in raw_locs:
        node = _resolve_graph_node(loc, graph)
        resolved[loc] = node
        if node and "gateway" not in (node or "").lower():
            sys = _node_system(node, graph)
            if sys:
                system_counts[sys] = system_counts.get(sys, 0) + 1
    system_hint = max(system_counts, key=system_counts.__getitem__) if system_counts else None
    # Second passage : gateways avec system_hint
    for loc in raw_locs:
        if resolved[loc] and "gateway" in resolved[loc].lower():
            resolved[loc] = _resolve_graph_node(loc, graph, system_hint=system_hint)
    return resolved


def _build_dist_matrix(
    graph,
    nodes: list[str | None],
) -> dict[tuple[str | None, str | None], float | None]:
    """Calcule toutes les distances pairwise entre les nœuds résolus."""
    matrix: dict[tuple[str | None, str | None], float | None] = {}
    for a in nodes:
        for b in nodes:
            if (a, b) in matrix:
                continue
            if a == b:
                matrix[(a, b)] = 0.0
            elif (b, a) in matrix:
                matrix[(a, b)] = matrix[(b, a)]
            else:
                matrix[(a, b)] = _path_dist(graph, a, b)
    return matrix


def _tsp_nearest_neighbor(
    start_node: str | None,
    missions: list,
    resolved: dict[str, str | None],
    dist: dict,
) -> tuple[list, float]:
    """Heuristique du plus proche voisin."""
    remaining = list(range(len(missions)))
    order: list[int] = []
    cur = start_node
    total = 0.0

    while remaining:
        best_i = None
        best_d = float("inf")
        for i in remaining:
            m = missions[i]
            src_raw = m.all_sources[0] if m.all_sources else None
            src = resolved.get(src_raw) if src_raw else None
            d = dist.get((cur, src))
            if d is None:
                d = float("inf")
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is None:
            best_i = remaining[0]
            best_d = 0.0
        order.append(best_i)
        remaining.remove(best_i)
        m = missions[best_i]
        src_raw = m.all_sources[0] if m.all_sources else None
        dst_raw = m.all_destinations[0] if m.all_destinations else None
        src = resolved.get(src_raw) if src_raw else None
        dst = resolved.get(dst_raw) if dst_raw else None
        total += best_d
        d_inner = dist.get((src, dst))
        total += d_inner if d_inner is not None else 0.0
        cur = dst or src
    return order, total


def _tsp_brute_force(
    start_node: str | None,
    missions: list,
    resolved: dict[str, str | None],
    dist: dict,
) -> tuple[list, float]:
    """Parcours exhaustif (≤8 missions)."""
    import itertools
    best_order = list(range(len(missions)))
    best_total = float("inf")

    for perm in itertools.permutations(range(len(missions))):
        total = 0.0
        cur = start_node
        for i in perm:
            m = missions[i]
            src_raw = m.all_sources[0] if m.all_sources else None
            dst_raw = m.all_destinations[0] if m.all_destinations else None
            src = resolved.get(src_raw) if src_raw else None
            dst = resolved.get(dst_raw) if dst_raw else None
            if src:
                total += dist.get((cur, src)) or 0.0
                cur = src
            if dst:
                total += dist.get((cur, dst)) or 0.0
                cur = dst
        if total < best_total:
            best_total = total
            best_order = list(perm)

    return best_order, best_total


def _active_ship(player):
    """Retourne le vaisseau actif du joueur (active_ship en priorité)."""
    if not player or not player.ships:
        return None
    if player.active_ship:
        for s in player.ships:
            if s.name.lower() == player.active_ship.lower():
                return s
    return None


def _run_analysis(voyage: Voyage, ctx) -> None:
    mm = ctx.mission_manager
    missions = [m for m in (mm.get(str(mid)) for mid in voyage.mission_ids) if m]
    if not missions:
        print_warn("Aucune mission à analyser")
        return

    section(f"Analyse — {voyage.name}")

    total_scu = sum(m.total_scu for m in missions)
    total_rew = sum(m.reward_uec for m in missions)
    rew_str = f"{total_rew:,}".replace(",", " ")

    # ── Vaisseau actif ────────────────────────────────────────────────────────
    player = ctx.player
    ship_scu = 0
    current_ship = _active_ship(player)
    if current_ship:
        ship_scu = current_ship.scu or 0
        if ship_scu < total_scu:
            print_warn(
                f"Vaisseau actif [{C.UEX}]{current_ship.name}[/{C.UEX}] "
                f"({ship_scu} SCU) insuffisant — {total_scu:.0f} SCU requis"
            )
        else:
            console.print(
                f"  [bold]Vaisseau :[/bold] [{C.UEX}]{current_ship.name}[/{C.UEX}]"
                f"  [{C.DIM}]{ship_scu} SCU — {total_scu:.0f} utilisés[/{C.DIM}]"
            )
    elif player and player.ships:
        suitable = [s for s in player.ships if (s.scu or 0) >= total_scu]
        if suitable:
            best_ship = min(suitable, key=lambda s: s.scu or 0)
            ship_scu = best_ship.scu or 0
            console.print(
                f"  [{C.DIM}]Aucun vaisseau actif — suggestion : "
                f"[/{C.DIM}][{C.UEX}]{best_ship.name}[/{C.UEX}]"
                f"  [{C.DIM}]({ship_scu} SCU)[/{C.DIM}]"
            )
        else:
            biggest = max(player.ships, key=lambda s: s.scu or 0)
            ship_scu = biggest.scu or 0
            print_warn(f"Aucun vaisseau assez grand ({total_scu:.0f} SCU requis)")
    else:
        print_warn("Aucun vaisseau configuré — /player ship <nom> <scu>")

    # ── Résolution des lieux + calcul des distances ───────────────────────────
    graph = ctx.cache.transport_graph
    if not graph:
        print_warn("Graphe de transport indisponible")
        return

    console.print(f"\n  [{C.DIM}]Résolution des lieux et calcul des distances…[/{C.DIM}]")

    start_raw = voyage.departure or (player.location if player else None) or ""
    raw_locs: list[str] = []
    if start_raw:
        raw_locs.append(start_raw)
    for m in missions:
        for loc in m.all_sources + m.all_destinations:
            if loc and loc not in raw_locs:
                raw_locs.append(loc)

    resolved = _resolve_locs(raw_locs, graph)

    # Afficher les résolutions non trouvées
    missing = [r for r in raw_locs if not resolved.get(r)]
    if missing:
        console.print(
            f"  [{C.WARNING}]Lieux non résolus dans le graphe : "
            f"{', '.join(missing)}[/{C.WARNING}]"
        )

    # Matrice de distances sur les nœuds résolus (dédupliqués)
    node_list = list(dict.fromkeys(v for v in resolved.values() if v))
    dist = _build_dist_matrix(graph, node_list)

    start_node = resolved.get(start_raw) if start_raw else None
    if not start_node and missions[0].all_sources:
        start_node = resolved.get(missions[0].all_sources[0])

    # ── TSP ───────────────────────────────────────────────────────────────────
    if len(missions) <= 8:
        order, tour_dist = _tsp_brute_force(start_node, missions, resolved, dist)
        algo = "exhaustif"
    else:
        order, tour_dist = _tsp_nearest_neighbor(start_node, missions, resolved, dist)
        algo = "heuristique"

    console.print(
        f"\n  [bold]Route optimisée[/bold] [{C.DIM}]({algo})[/{C.DIM}] ·"
        f" distance totale : [bold]{_fmt_dist(tour_dist)}[/bold]\n"
    )

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Étape", style=C.DIM, width=5, justify="right")
    tbl.add_column("Mission", style=C.LABEL, max_width=22)
    tbl.add_column("Départ", style=C.UEX, max_width=16)
    tbl.add_column("→", style=C.DIM, width=1)
    tbl.add_column("Arrivée", style=C.UEX, max_width=16)
    tbl.add_column("Trajet", justify="right", width=8)
    tbl.add_column("Leg", justify="right", width=8)
    tbl.add_column("SCU", justify="right", width=4)
    tbl.add_column("Récompense", justify="right", width=12)

    cur_node = start_node
    cumul = 0.0
    for step, i in enumerate(order, 1):
        m = missions[i]
        src_raw = m.all_sources[0] if m.all_sources else None
        dst_raw = m.all_destinations[0] if m.all_destinations else None
        src_node = resolved.get(src_raw) if src_raw else None
        dst_node = resolved.get(dst_raw) if dst_raw else None
        travel = dist.get((cur_node, src_node)) if cur_node and src_node else None
        leg    = dist.get((src_node, dst_node)) if src_node and dst_node else None
        cumul += (travel or 0.0) + (leg or 0.0)
        scu_s = f"{m.total_scu:.0f}□" if m.total_scu else "—"
        rew_s = f"{m.reward_uec:,}".replace(",", " ")
        tbl.add_row(
            str(step),
            m.name,
            src_raw or "—",
            "→",
            dst_raw or "—",
            _fmt_dist(travel),
            _fmt_dist(leg),
            scu_s,
            rew_s + " aUEC",
        )
        cur_node = dst_node or src_node

    console.print(tbl)
    console.print(
        f"\n  [{C.DIM}]{len(missions)} mission(s) · "
        f"[bold]{total_scu:.0f}[/bold] SCU · "
        f"[bold]{rew_str}[/bold] aUEC · "
        f"distance cumulée [bold]{_fmt_dist(cumul)}[/bold][/{C.DIM}]"
    )

    # ── Suggestions de rentabilité ────────────────────────────────────────────
    spare_scu = ship_scu - total_scu
    if spare_scu >= 1:
        _suggest_cargo(missions, order, spare_scu, resolved, dist, ctx)


def _suggest_cargo(missions: list, order: list[int], spare_scu: float,
                   resolved: dict, dist: dict, ctx) -> None:
    """Propose des cargaisons rentables pour remplir le SCU disponible."""
    try:
        from uexinfo.api.uex_client import UEXClient
        client = UEXClient(ctx.cfg.get("api_key", ""))
    except Exception:
        return

    console.print(f"\n  [bold]Cargo supplémentaire disponible :[/bold] [{C.DIM}]{spare_scu:.0f} SCU libres[/{C.DIM}]")

    # Collecter les legs du voyage optimisé (départ_leg, arrivée_leg)
    legs: list[tuple[str, str]] = []
    for i in order:
        m = missions[i]
        src = m.all_sources[0] if m.all_sources else None
        dst = m.all_destinations[0] if m.all_destinations else None
        if src and dst:
            legs.append((src, dst))

    if not legs:
        return

    # Pour chaque leg, chercher les meilleures routes commerciales
    suggestions: list[tuple[float, str, str, str, float, float]] = []
    # (profit_par_scu, commodity, from, to, buy_price, sell_price)

    cache = ctx.cache
    if not cache:
        return

    for from_loc, to_loc in legs[:3]:  # limiter aux 3 premiers legs
        from_terminals = _loc_terminals(from_loc, cache)
        to_terminals   = _loc_terminals(to_loc,   cache)
        if not from_terminals or not to_terminals:
            continue
        for ft in from_terminals[:2]:
            for tt in to_terminals[:2]:
                try:
                    prices = client.get_prices(terminal_name=ft.name)
                    buys = {p.commodity_name: p for p in prices if p.operation == "buy"}
                except Exception:
                    continue
                try:
                    prices2 = client.get_prices(terminal_name=tt.name)
                    sells = {p.commodity_name: p for p in prices2 if p.operation == "sell"}
                except Exception:
                    continue
                for name, bp in buys.items():
                    if name not in sells:
                        continue
                    sp = sells[name]
                    if not bp.price or not sp.price:
                        continue
                    profit = sp.price - bp.price
                    if profit > 0:
                        suggestions.append((profit, name, ft.name, tt.name, bp.price, sp.price))

    if not suggestions:
        console.print(f"  [{C.DIM}]Aucune opportunité commerciale détectée sur ces legs.[/{C.DIM}]")
        return

    suggestions.sort(reverse=True)
    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Commodité", style=C.LABEL, max_width=18)
    tbl.add_column("De", style=C.DIM, max_width=16)
    tbl.add_column("→", style=C.DIM, width=1)
    tbl.add_column("Vers", style=C.DIM, max_width=16)
    tbl.add_column("Profit/SCU", justify="right", width=10)
    tbl.add_column("Profit total", justify="right", width=12)

    seen: set[str] = set()
    shown = 0
    for profit, name, frm, to, buy, sell in suggestions:
        key = f"{name}|{frm}|{to}"
        if key in seen:
            continue
        seen.add(key)
        total_p = profit * spare_scu
        tp_str = f"{total_p:,.0f}".replace(",", " ") + " aUEC"
        pp_str = f"{profit:,.0f}".replace(",", " ") + " aUEC"
        tbl.add_row(name, frm, "→", to, pp_str, f"[bold {C.PROFIT}]{tp_str}[/bold {C.PROFIT}]")
        shown += 1
        if shown >= 5:
            break

    if shown:
        console.print(tbl)


def _loc_terminals(loc_name: str, cache) -> list:
    """Retourne les terminaux proches d'un lieu (par nom)."""
    name_l = loc_name.lower()
    return [
        t for t in (cache.terminals or [])
        if (t.name or "").lower() == name_l
        or name_l in (t.name or "").lower()
    ][:3]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _player_loc(ctx) -> str | None:
    return (getattr(ctx.player, "location", None) or "").strip() or None


def _infer_arrival(missions) -> str | None:
    """Déduit la destination finale depuis la dernière mission."""
    for m in reversed(missions):
        if m.all_destinations:
            return m.all_destinations[-1]
    return None


def _require_active(vm) -> bool:
    if not vm.get_active():
        print_warn("Aucun voyage actif")
        console.print(f"[{C.DIM}]/voyage on  ou  /voyage new  pour démarrer[/{C.DIM}]")
        return False
    return True


def _no_active() -> None:
    print_warn("Aucun voyage actif")
    from uexinfo.display.formatter import console as _c
    _c.print(f"[dim]/voyage on  ou  /voyage new  pour démarrer[/dim]")


# ── Aide ──────────────────────────────────────────────────────────────────────

def _show_help() -> None:
    section("Aide — /voyage")
    lines = [
        ("on",              "Active le dernier voyage ou en crée un nouveau"),
        ("off",             "Désactive le voyage courant (conservé)"),
        ("new [nom]",       "Crée un nouveau voyage + l'active"),
        ("<nom|n>",         "Active le voyage (ou /voyage <nom> list pour afficher)"),
        ("name <nom>",      "Renomme le voyage actif"),
        ("list [--trajets]","Missions du voyage actif, ou tous les voyages"),
        ("add [m1 m2...]",  "Ajoute des missions (catalogue) au voyage actif"),
        ("remove <m>",      "Retire une mission du voyage"),
        ("clear",           "Vide les missions du voyage actif"),
        ("copy [n|nom]",    "Copie/fusionne vers un autre voyage"),
        ("accept",          "Valide + analyse, désactive le voyage"),
        ("later",           "Sauvegarde sans analyse, désactive"),
        ("cancel",          "Annule les modifications (retour à la dernière sauvegarde)"),
    ]
    for cmd, desc in lines:
        console.print(f"  [bold {C.LABEL}]/voyage {cmd:<22}[/bold {C.LABEL}]  [{C.DIM}]{desc}[/{C.DIM}]")
    console.print()
    console.print(f"  [{C.DIM}]Adressage : /voyage 2 list   -n2 list   -n toto list[/{C.DIM}]")
    console.print(f"  [{C.DIM}]Alias : /v  ·  Double-clic = afficher  ·  Clic droit = Activer/Analyser…[/{C.DIM}]")
