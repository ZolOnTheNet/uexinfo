"""Commande /nav — gestion du réseau de transport (jump points, routes QT)."""
from __future__ import annotations

from rich.table import Table

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.models.transport_network import EdgeType, JumpPoint, LocationNode, NodeType, RouteEdge

# Sous-commandes explicites — tout le reste est interprété comme une route
_SUBCOMMANDS = frozenset({
    "info",
    "nodes", "noeuds", "noeud", "node",
    "edges", "edge", "liaisons", "liaison", "aretes", "arete", "arêtes", "arête",
    "jumps", "jump", "sauts", "saut",
    "route", "itineraire", "itinéraire", "chemin",
    "add-route", "ajouter-route", "ajouter-liaison", "add-liaison",
    "add-jump", "ajouter-saut", "ajouter-jump",
    "remove-route", "supprimer-route", "supprimer-liaison",
    "remove-jump", "supprimer-saut", "supprimer-jump",
    "save", "sauvegarder", "enregistrer",
    "raz", "reset", "reinitialiser", "réinitialiser",
    "populate", "peupler", "remplir", "enrichir",
})


@register("nav", "navigation", "n", "qt", "quantum")
def cmd_nav(args: list[str], ctx) -> None:
    """Gestion du réseau de transport interstellaire."""
    # Filtrer --req pour la détection de la sous-commande
    real_args = [a for a in args if a != "--req"]

    if not real_args or real_args[0].lower() not in _SUBCOMMANDS:
        # /nav [args…]  →  calculateur de routes (mode par défaut)
        _find_route(args, ctx)
        return

    sub = real_args[0].lower()

    if sub == "info":
        _show_info(ctx)
    elif sub in ("nodes", "noeuds", "noeud", "node"):
        _list_nodes(real_args[1:], ctx)
    elif sub in ("edges", "edge", "liaisons", "liaison", "aretes", "arete", "arêtes", "arête"):
        _list_edges(real_args[1:], ctx)
    elif sub in ("jumps", "jump", "sauts", "saut"):
        _list_jumps(ctx)
    elif sub in ("route", "itineraire", "itinéraire", "chemin"):
        _find_route(args[1:], ctx)  # on passe args complets avec --req éventuel
    elif sub in ("add-route", "ajouter-route", "ajouter-liaison", "add-liaison"):
        _add_route(real_args[1:], ctx)
    elif sub in ("add-jump", "ajouter-saut", "ajouter-jump"):
        _add_jump(real_args[1:], ctx)
    elif sub in ("remove-route", "supprimer-route", "supprimer-liaison"):
        _remove_route(real_args[1:], ctx)
    elif sub in ("remove-jump", "supprimer-saut", "supprimer-jump"):
        _remove_jump(real_args[1:], ctx)
    elif sub in ("save", "sauvegarder", "enregistrer"):
        _save_graph(ctx)
    elif sub in ("raz", "reset", "reinitialiser", "réinitialiser"):
        _reset_graph(ctx)
    elif sub in ("populate", "peupler", "remplir", "enrichir"):
        _populate_graph(real_args[1:], ctx)
    else:
        print_error(f"Sous-commande inconnue : {sub}  (/help nav)")


# ── Info & stats ───────────────────────────────────────────────────────────────

def _show_info(ctx) -> None:
    """Affiche les stats du réseau de transport."""
    graph = ctx.cache.transport_graph
    section("Réseau de transport")

    n_nodes = len(graph.nodes)
    n_edges = len([e for e in graph.edges if e.edge_type != EdgeType.JUMP])
    n_jumps = len(graph.jump_points)

    systems = {}
    for node in graph.nodes.values():
        systems.setdefault(node.system, 0)
        systems[node.system] += 1

    console.print(f"  [bold]Nœuds :[/bold]       {n_nodes}  [{C.DIM}](terminaux, stations, villes)[/{C.DIM}]")
    console.print(f"  [bold]Routes :[/bold]      {n_edges // 2}  [{C.DIM}](bidirectionnelles)[/{C.DIM}]")
    console.print(f"  [bold]Jump points :[/bold] {n_jumps}  [{C.DIM}](passerelles inter-systèmes)[/{C.DIM}]")
    console.print()

    if systems:
        console.print(f"[bold {C.LABEL}]Systèmes couverts :[/bold {C.LABEL}]")
        for sys, count in sorted(systems.items()):
            console.print(f"  [{C.UEX}]{sys}[/{C.UEX}]  [{C.DIM}]{count} lieux[/{C.DIM}]")

    console.print()
    console.print(f"[{C.DIM}]/nav <dest>        route depuis votre position[/{C.DIM}]")
    console.print(f"[{C.DIM}]/nav <de> <vers>   route explicite[/{C.DIM}]")
    console.print(f"[{C.DIM}]/nav --req          fetcher les distances manquantes depuis UEX[/{C.DIM}]")
    console.print(f"[{C.DIM}]/nav nodes, /nav edges, /nav jumps   explorer le réseau[/{C.DIM}]")

    if graph.has_unsaved_changes:
        console.print()
        console.print(
            f"[{C.WARNING}]⊕  {graph._unsaved_changes} modification(s) non sauvegardée(s)  "
            f"—  utilisez /nav save[/{C.WARNING}]"
        )


# ── Nodes ──────────────────────────────────────────────────────────────────────

def _list_nodes(args: list[str], ctx) -> None:
    graph = ctx.cache.transport_graph
    system_filter = args[0].lower() if args else None

    nodes = list(graph.nodes.values())
    if system_filter:
        nodes = [n for n in nodes if n.system.lower() == system_filter]

    if not nodes:
        print_warn(f"Aucun nœud trouvé{' dans ' + system_filter if system_filter else ''}")
        return

    section(f"Nœuds — {nodes[0].system if system_filter else 'Tous systèmes'}")

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Nom", style=C.LABEL)
    tbl.add_column("Type", style=C.DIM)
    tbl.add_column("Système", style=C.UEX)
    tbl.add_column("Voisins", style=C.NEUTRAL, justify="right")

    for node in sorted(nodes, key=lambda n: (n.system, n.name)):
        neighbors = graph.get_neighbors(node.name)
        tbl.add_row(node.name, node.type.value, node.system, str(len(neighbors)))

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(nodes)} nœuds[/{C.DIM}]")


# ── Edges ──────────────────────────────────────────────────────────────────────

def _list_edges(args: list[str], ctx) -> None:
    graph = ctx.cache.transport_graph
    node_filter = " ".join(args).strip() if args else None

    edges = graph.edges
    if node_filter:
        edges = [e for e in edges if node_filter.lower() in e.from_node.lower()]

    seen = set()
    unique_edges = []
    for e in edges:
        key = tuple(sorted([e.from_node, e.to_node]))
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    if not unique_edges:
        print_warn(f"Aucune route trouvée{' depuis ' + node_filter if node_filter else ''}")
        return

    section(f"Routes — {node_filter or 'Toutes'}")

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("De", style=C.LABEL)
    tbl.add_column("", style=C.DIM)
    tbl.add_column("Vers", style=C.LABEL)
    tbl.add_column("Distance", style=C.UEX, justify="right")
    tbl.add_column("Type", style=C.DIM)

    for edge in sorted(unique_edges, key=lambda e: e.from_node):
        dist_str = f"{edge.distance_gm:.1f} Gm" if edge.distance_gm >= 1 else f"{edge.distance_gm * 1000:.0f} Mm"
        tbl.add_row(edge.from_node[:20], "↔", edge.to_node[:20], dist_str, edge.edge_type.value)

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(unique_edges)} routes[/{C.DIM}]")


# ── Jump points ────────────────────────────────────────────────────────────────

def _list_jumps(ctx) -> None:
    graph = ctx.cache.transport_graph
    jumps = list(graph.jump_points.values())

    if not jumps:
        print_warn("Aucun jump point configuré")
        console.print(f"[{C.DIM}]Utilisez /nav add-jump pour en ajouter[/{C.DIM}]")
        return

    section("Jump points")

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Nom", style=C.LABEL)
    tbl.add_column("", style=C.DIM)
    tbl.add_column("Systèmes", style=C.UEX)
    tbl.add_column("Taille", style=C.NEUTRAL, justify="center")
    tbl.add_column("État", style=C.SUCCESS)

    for jp in sorted(jumps, key=lambda j: j.name):
        status_color = C.SUCCESS if jp.is_active else C.DIM
        tbl.add_row(
            jp.name, "⇨", f"{jp.from_system} ↔ {jp.to_system}",
            jp.size, f"[{status_color}]{'✓' if jp.is_active else '✗'}[/{status_color}]"
        )

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(jumps)} jump points[/{C.DIM}]")


# ── Route finding ──────────────────────────────────────────────────────────────

def _find_route(args: list[str], ctx) -> None:
    """Calcule le chemin entre deux lieux.

    Syntaxes :
      /nav                       → toutes destinations du système courant
      /nav <dest>                → de @local vers <dest>
      /nav <de> <vers>           → route explicite
      /nav @local <vers>         → alias position courante
      /nav @dest <vers>          → alias destination courante
      /nav ... --req             → force requête UEX pour distances manquantes
    """
    force_req = "--req" in args
    args = [a for a in args if a != "--req"]

    graph = ctx.cache.transport_graph

    # ── Cas 0 : aucun argument → toutes destinations depuis @local ────────────
    if not args:
        loc = (getattr(ctx.player, "location", None) or "").strip()
        if not loc:
            _show_info(ctx)
            console.print()
            console.print(f"[{C.DIM}]💡 Conseil : /go <lieu> pour définir votre position, puis /nav[/{C.DIM}]")
            return

        from_node = _resolve_node(loc, graph)
        if not from_node and force_req:
            from_node = _auto_add_from_uex(loc, graph, ctx)
        if not from_node:
            print_warn(f"Position [{C.LABEL}]{loc}[/{C.LABEL}] absente du graphe")
            console.print(f"[{C.DIM}]→ /nav --req   pour fetcher les distances UEX[/{C.DIM}]")
            console.print(f"[{C.DIM}]→ /nav populate  pour enrichir tout le graphe[/{C.DIM}]")
            return

        if force_req:
            _fetch_missing_distances(from_node, graph, ctx)
        _show_system_destinations(from_node, graph, ctx)
        return

    # Normaliser : underscores → espaces, puis expander @local/@dest
    args_exp = [_expand_alias(a.replace("_", " "), ctx) for a in args]

    # ── Cas 1 : un seul argument → de @local vers args[0] ────────────────────
    if len(args_exp) == 1:
        loc = (getattr(ctx.player, "location", None) or "").strip()
        if not loc:
            print_error("Position non définie — utilisez /go <lieu>")
            return
        from_loc = loc
        to_loc   = args_exp[0]

        from_node = _resolve_node(loc, graph)
        if not from_node:
            from_node = _auto_add_from_uex(loc, graph, ctx)
        to_node = _resolve_node(to_loc, graph)
        if not to_node:
            to_node = _auto_add_from_uex(to_loc, graph, ctx)

    # ── Cas 2+ : split heuristique (logique existante) ────────────────────────
    else:
        from_node, to_node = None, None
        from_loc = to_loc = ""

        if "to" in [a.lower() for a in args]:
            idx = next(i for i, a in enumerate(args) if a.lower() == "to")
            from_loc = " ".join(args_exp[:idx]).strip()
            to_loc   = " ".join(args_exp[idx + 1:]).strip()
            from_node = _resolve_node(from_loc, graph)
            to_node   = _resolve_node(to_loc, graph)
        else:
            # Essayer de droite à gauche
            for split in range(len(args_exp) - 1, 0, -1):
                fl = " ".join(args_exp[:split]).strip()
                tl = " ".join(args_exp[split:]).strip()
                fn = _resolve_node(fl, graph)
                tn = _resolve_node(tl, graph)
                if fn and tn:
                    from_node, to_node = fn, tn
                    from_loc, to_loc = fl, tl
                    break
            # Puis de gauche à droite
            if not from_node:
                for split in range(1, len(args_exp)):
                    fl = " ".join(args_exp[:split]).strip()
                    tl = " ".join(args_exp[split:]).strip()
                    fn = _resolve_node(fl, graph)
                    tn = _resolve_node(tl, graph)
                    if fn and tn:
                        from_node, to_node = fn, tn
                        from_loc, to_loc = fl, tl
                        break
            # Fallback milieu
            if not from_node:
                mid = len(args_exp) // 2
                from_loc = " ".join(args_exp[:mid]).strip()
                to_loc   = " ".join(args_exp[mid:]).strip()
                from_node = _resolve_node(from_loc, graph)
                to_node   = _resolve_node(to_loc, graph)

    # ── Auto-enrichissement UEX si nœuds introuvables ─────────────────────────
    if not from_node:
        from_node = _auto_add_from_uex(from_loc, graph, ctx)
        if not from_node:
            print_error(f"Lieu de départ introuvable : {from_loc!r}")
            _show_candidates(from_loc, graph)
            return
    if not to_node:
        to_node = _auto_add_from_uex(to_loc, graph, ctx)
        if not to_node:
            print_error(f"Lieu d'arrivée introuvable : {to_loc!r}")
            _show_candidates(to_loc, graph)
            return

    # ── Fetch optionnel avant calcul ──────────────────────────────────────────
    if force_req:
        _fetch_missing_distances(from_node, graph, ctx)

    _display_route(from_node, to_node, graph)


def _display_route(from_node: str, to_node: str, graph) -> None:
    """Affiche le résultat d'un calcul de route Dijkstra."""
    result = graph.find_shortest_path(from_node, to_node)

    if not result:
        print_warn(f"Aucune route trouvée entre {from_node} et {to_node}")
        console.print(f"[{C.DIM}]→ /nav --req {from_node} {to_node}  pour fetcher via UEX[/{C.DIM}]")
        return

    section(f"Route — {from_node} → {to_node}")
    console.print(f"  [bold]Distance totale :[/bold] [{C.UEX}]{result.total_distance:.1f} Gm[/{C.UEX}]")
    console.print(f"  [bold]Durée estimée :[/bold]   [{C.NEUTRAL}]{result.duration_formatted}[/{C.NEUTRAL}]")
    if result.jump_points:
        console.print(f"  [bold]Jump points :[/bold]     [{C.WARNING}]{len(result.jump_points)}[/{C.WARNING}]")

    console.print(f"\n[bold {C.LABEL}]Étapes :[/bold {C.LABEL}]")
    for i, seg in enumerate(result.segments, 1):
        icon = "⇨" if seg["type"] == "jump" else "→"
        type_label = "[bold yellow]JUMP[/bold yellow]" if seg["type"] == "jump" else "QT"
        dist_str = (
            f"{seg['distance_gm']:.1f} Gm"
            if seg['distance_gm'] >= 1
            else f"{seg['distance_gm'] * 1000:.0f} Mm"
        )
        console.print(
            f"  [{C.DIM}]{i}.[/{C.DIM}] "
            f"[{C.LABEL}]{seg['from'][:18]}[/{C.LABEL}]  "
            f"[{C.DIM}]{icon}[/{C.DIM}]  "
            f"[{C.LABEL}]{seg['to'][:18]}[/{C.LABEL}]  "
            f"[{C.UEX}]{dist_str:>8}[/{C.UEX}]  "
            f"[{C.DIM}][{type_label}][/{C.DIM}]"
        )

    if result.jump_points:
        console.print(f"\n[{C.WARNING}]⚠  Cette route traverse {len(result.jump_points)} jump point(s)[/{C.WARNING}]")


def _show_system_destinations(from_node: str, graph, ctx) -> None:
    """Affiche toutes les destinations du système courant en multi-colonnes."""
    node = graph.nodes.get(from_node)
    system = node.system if node else "Unknown"

    sys_nodes = graph.get_nodes_in_system(system)
    if not sys_nodes:
        print_warn(f"Aucun nœud connu dans le système {system!r}")
        console.print(f"[{C.DIM}]→ /nav populate  pour enrichir le graphe depuis UEX[/{C.DIM}]")
        return

    # Dijkstra unique depuis from_node
    all_dists = graph.find_all_distances(from_node)

    entries = []
    for n in sys_nodes:
        if n.name == from_node:
            continue
        dist = all_dists.get(n.name)
        entries.append((n.name, dist, n.type))

    known   = sorted([(nm, d, t) for nm, d, t in entries if d is not None], key=lambda x: x[1])
    unknown = sorted([(nm, d, t) for nm, d, t in entries if d is None],     key=lambda x: x[0])
    all_entries = known + unknown

    if not all_entries:
        print_warn(f"Aucune destination dans {system!r}")
        return

    section(f"Destinations depuis {from_node}  [{system}]")
    console.print(
        f"[{C.DIM}]@local = [bold]{from_node}[/bold]  ·  "
        f"{len(known)}/{len(all_entries)} distances connues[/{C.DIM}]"
    )
    if unknown:
        console.print(
            f"[{C.DIM}]-?- = distance inconnue  ·  /nav --req pour les fetcher[/{C.DIM}]"
        )
    console.print()

    # Mise en page multi-colonnes
    col_width = 34   # nom ~22 + dist ~10 + padding 2
    n_cols = max(1, min(4, (console.width - 4) // col_width))

    tbl = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    for _ in range(n_cols):
        tbl.add_column(max_width=22, no_wrap=True)
        tbl.add_column(width=9, justify="right", no_wrap=True)

    for i in range(0, len(all_entries), n_cols):
        row_entries = all_entries[i:i + n_cols]
        cells: list[str] = []
        for nm, dist, ntype in row_entries:
            if ntype in (NodeType.STATION, NodeType.LAGRANGE):
                nc = f"[{C.UEX}]{nm[:21]}[/{C.UEX}]"
            elif ntype == NodeType.CITY:
                nc = f"[bold white]{nm[:21]}[/bold white]"
            elif ntype in (NodeType.PLANET, NodeType.MOON):
                nc = f"[{C.LABEL}]{nm[:21]}[/{C.LABEL}]"
            else:
                nc = f"[{C.DIM}]{nm[:21]}[/{C.DIM}]"

            if dist is not None:
                dc = f"[{C.UEX}]{dist:.1f}[/{C.UEX}][{C.DIM}]Gm[/{C.DIM}]"
            else:
                dc = f"[{C.DIM}]-?-[/{C.DIM}]"

            cells.extend([nc, dc])

        # Compléter la dernière ligne
        while len(cells) < n_cols * 2:
            cells.extend(["", ""])

        tbl.add_row(*cells)

    console.print(tbl)
    console.print()
    console.print(
        f"[{C.DIM}]/nav <dest>       route complète  ·  "
        f"/nav --req       fetcher distances manquantes[/{C.DIM}]"
    )


# ── Fetch distances UEX ────────────────────────────────────────────────────────

def _fetch_missing_distances(from_node: str, graph, ctx) -> None:
    """Interroge UEX pour récupérer les distances depuis from_node.

    Identifie les terminaux associés au nœud, fait une requête par terminal,
    et injecte les nouvelles arêtes (minimise les appels API).
    """
    from uexinfo.api.uex_client import UEXClient, UEXError

    node = graph.nodes.get(from_node)

    # 1. Trouver les terminaux UEX correspondant au nœud
    terminals = _get_terminals_for_node(from_node, node, ctx)

    if not terminals:
        print_warn(f"Aucun terminal UEX trouvé pour {from_node!r}")
        console.print(f"[{C.DIM}]Astuce : /nav populate  pour enrichir tout le graphe[/{C.DIM}]")
        return

    console.print(
        f"[{C.DIM}]↻ Requête UEX — {len(terminals)} terminal(aux) pour "
        f"[bold]{from_node}[/bold]...[/{C.DIM}]"
    )

    client = UEXClient()
    edges_added = 0
    seen_dests: set[str] = set()

    for terminal in terminals[:5]:  # max 5 requêtes par lieu
        try:
            routes = client.get_routes(id_terminal_origin=terminal.id)
        except UEXError as e:
            console.print(f"[{C.WARNING}]⚠ UEX : {e}[/{C.WARNING}]")
            continue

        for r in routes:
            dest = (
                r.get("destination_terminal_name") or
                r.get("terminal_name_destination") or ""
            ).strip()
            dist = r.get("distance")
            if not dest or dist is None or dest in seen_dests:
                continue
            seen_dests.add(dest)

            dest_node = _resolve_node_uex(dest, graph)
            if dest_node and dest_node != from_node:
                added = graph.add_or_update_route(
                    from_node=from_node,
                    to_node=dest_node,
                    distance_gm=float(dist),
                    edge_type=EdgeType.QUANTUM,
                    source="uex",
                )
                if added:
                    edges_added += 1

    if edges_added > 0:
        print_ok(f"{edges_added} liaison(s) UEX ajoutée(s) depuis {from_node}")
        console.print(f"[{C.DIM}]/nav save  pour conserver[/{C.DIM}]")
    else:
        console.print(f"[{C.DIM}]Aucune nouvelle liaison trouvée[/{C.DIM}]")


def _get_terminals_for_node(node_name: str, node, ctx) -> list:
    """Retourne les terminaux UEX correspondant à un nœud du graphe."""
    # 1. Via id_terminal dans les métadonnées
    if node:
        id_terminal = node.metadata.get("id_terminal")
        if id_terminal:
            for t in ctx.cache.terminals:
                if t.id == id_terminal:
                    return [t]

    # 2. Par correspondance de nom
    loc_lower = node_name.lower().strip()
    result = []
    seen_ids: set[int] = set()

    for t in ctx.cache.terminals:
        if t.id in seen_ids:
            continue
        terminal_loc = t.name.rsplit(" - ", 1)[-1].strip().lower()
        if (
            terminal_loc == loc_lower
            or t.name.lower() == loc_lower
            or loc_lower in terminal_loc
            or (t.orbit_name or "").lower() == loc_lower
            or (t.city_name or "").lower() == loc_lower
            or (t.space_station_name or "").lower() == loc_lower
        ):
            result.append(t)
            seen_ids.add(t.id)

    return result


# ── Add route ──────────────────────────────────────────────────────────────────

def _add_route(args: list[str], ctx) -> None:
    if len(args) < 3:
        print_error("Usage: /nav add-route <de> <vers> <distance_gm> [quantum|ground]")
        return

    from_loc = args[0]
    to_loc = args[1]
    try:
        distance = float(args[2])
    except ValueError:
        print_error("Distance invalide (nombre attendu)")
        return

    edge_type_str = args[3].lower() if len(args) > 3 else "quantum"
    try:
        edge_type = EdgeType(edge_type_str)
    except ValueError:
        print_error(f"Type invalide : {edge_type_str}  (quantum|jump|ground|landing)")
        return

    graph = ctx.cache.transport_graph

    if from_loc not in graph.nodes:
        print_error(f"Nœud introuvable : {from_loc}")
        return
    if to_loc not in graph.nodes:
        print_error(f"Nœud introuvable : {to_loc}")
        return

    edge = RouteEdge(
        from_node=from_loc,
        to_node=to_loc,
        distance_gm=distance,
        edge_type=edge_type,
        source="manual",
    )
    graph.add_edge(edge, bidirectional=True)

    print_ok(f"Route ajoutée : {from_loc} ↔ {to_loc}  ({distance:.1f} Gm)")
    console.print(f"[{C.DIM}]Utilisez /nav save pour sauvegarder[/{C.DIM}]")


# ── Add jump ───────────────────────────────────────────────────────────────────

def _add_jump(args: list[str], ctx) -> None:
    if len(args) < 5:
        print_error("Usage: /nav add-jump <nom> <sys1> <sys2> <entrée> <sortie> [size]")
        return

    name = args[0]
    from_sys = args[1]
    to_sys = args[2]
    entry = args[3]
    exit_loc = args[4]
    size = args[5].upper() if len(args) > 5 else "L"

    if size not in ("S", "M", "L"):
        print_error("Taille invalide (S, M, ou L)")
        return

    graph = ctx.cache.transport_graph
    jp = JumpPoint(
        name=name, from_system=from_sys, to_system=to_sys,
        entry_location=entry, exit_location=exit_loc, size=size,
    )
    graph.add_jump_point(jp)

    print_ok(f"Jump point ajouté : {name}  ({from_sys} ↔ {to_sys})")
    console.print(f"[{C.DIM}]Utilisez /nav save pour sauvegarder[/{C.DIM}]")


# ── Remove ─────────────────────────────────────────────────────────────────────

def _remove_route(args: list[str], ctx) -> None:
    if len(args) < 2:
        print_error("Usage: /nav remove-route <de> <vers>")
        return

    from_loc, to_loc = args[0], args[1]
    graph = ctx.cache.transport_graph

    graph.edges = [
        e for e in graph.edges
        if not ((e.from_node == from_loc and e.to_node == to_loc) or
                (e.from_node == to_loc   and e.to_node == from_loc))
    ]
    graph._adjacency.clear()
    for edge in graph.edges:
        graph._adjacency.setdefault(edge.from_node, []).append(edge)

    print_ok(f"Route supprimée : {from_loc} ↔ {to_loc}")
    console.print(f"[{C.DIM}]Utilisez /nav save pour sauvegarder[/{C.DIM}]")


def _remove_jump(args: list[str], ctx) -> None:
    if not args:
        print_error("Usage: /nav remove-jump <nom>")
        return

    name = args[0]
    graph = ctx.cache.transport_graph

    if name not in graph.jump_points:
        print_error(f"Jump point introuvable : {name}")
        return

    del graph.jump_points[name]
    graph.edges = [e for e in graph.edges if name not in e.notes]
    graph._adjacency.clear()
    for edge in graph.edges:
        graph._adjacency.setdefault(edge.from_node, []).append(edge)

    print_ok(f"Jump point supprimé : {name}")
    console.print(f"[{C.DIM}]Utilisez /nav save pour sauvegarder[/{C.DIM}]")


# ── Save & reset ───────────────────────────────────────────────────────────────

def _save_graph(ctx) -> None:
    ctx.cache.save_transport_graph()
    print_ok("Graphe de transport sauvegardé dans uexinfo/data/transport_network.json")
    console.print(f"[{C.DIM}]Pensez à commiter ce fichier avec git[/{C.DIM}]")


def _reset_graph(ctx) -> None:
    print_warn("Cette action supprimera toutes les modifications non sauvegardées")
    ctx.cache.load_transport_graph()
    print_ok("Graphe réinitialisé depuis le fichier source")


# ── Populate ───────────────────────────────────────────────────────────────────

def _populate_graph(args: list[str], ctx) -> None:
    """Peuple le graphe de transport avec les distances depuis l'API UEX."""
    from uexinfo.api.uex_client import UEXClient, UEXError
    from uexinfo.models.transport_network import EdgeType, LocationNode, NodeType

    graph = ctx.cache.transport_graph
    client = UEXClient(timeout=20)

    _term_sys: dict[str, str] = {
        t.name: (t.star_system_name or "Unknown")
        for t in ctx.cache.terminals
    }

    section("Populate — distances depuis UEX Corp")
    console.print(f"[{C.DIM}]Récupération des commodités...[/{C.DIM}]")
    try:
        commodities = client.get_commodities()
    except UEXError as e:
        print_error(f"UEX inaccessible : {e}")
        return

    buyable = [c for c in commodities if c.get("is_buyable") == 1]
    console.print(
        f"  [{C.NEUTRAL}]{len(buyable)} commodités achetables[/{C.NEUTRAL}]  "
        f"[{C.DIM}]— {len(commodities)} total[/{C.DIM}]"
    )
    console.print()

    seen_pairs: set[tuple[str, str]] = set()
    nodes_added    = 0
    routes_added   = 0
    routes_updated = 0
    errors         = 0
    total          = len(buyable)

    for i, commodity in enumerate(buyable, 1):
        cid   = commodity.get("id")
        cname = commodity.get("name", "?")

        if i == 1 or i % 5 == 0 or i == total:
            console.print(f"  [{C.DIM}][{i}/{total}][/{C.DIM}]  [{C.LABEL}]{cname}[/{C.LABEL}]")

        try:
            routes = client.get_routes(id_commodity=cid)
        except UEXError:
            errors += 1
            continue

        for r in routes:
            origin = (r.get("terminal_name_origin") or r.get("origin_terminal_name") or "").strip()
            dest   = (r.get("terminal_name_destination") or r.get("destination_terminal_name") or "").strip()
            dist   = r.get("distance")

            if not origin or not dest or dist is None:
                continue

            dist_f = max(float(dist), 0.001)
            pair = tuple(sorted([origin, dest]))
            already_known = pair in seen_pairs
            seen_pairs.add(pair)

            sys_o = _term_sys.get(origin) or (r.get("star_system_name_origin") or "").strip() or "Unknown"
            sys_d = _term_sys.get(dest)   or (r.get("star_system_name_destination") or "").strip() or "Unknown"

            if origin not in graph.nodes:
                graph.add_node(LocationNode(name=origin, type=NodeType.TERMINAL, system=sys_o,
                                            metadata={"source": "uex_populate"}))
                nodes_added += 1
            if dest not in graph.nodes:
                graph.add_node(LocationNode(name=dest, type=NodeType.TERMINAL, system=sys_d,
                                            metadata={"source": "uex_populate"}))
                nodes_added += 1

            if already_known:
                continue

            added = graph.add_or_update_route(
                from_node=origin, to_node=dest, distance_gm=dist_f,
                edge_type=EdgeType.QUANTUM, source="uex",
            )
            if added:
                routes_added += 1
            else:
                routes_updated += 1

    fixed = 0
    for node in graph.nodes.values():
        if node.system == "Unknown":
            sys_from_cache = _term_sys.get(node.name)
            if sys_from_cache and sys_from_cache != "Unknown":
                node.system = sys_from_cache
                fixed += 1

    console.print()
    print_ok(
        f"{routes_added} routes ajoutées  ·  "
        f"{nodes_added} nouveaux nœuds  ·  "
        f"{len(seen_pairs)} paires de terminaux couvertes"
    )
    if routes_updated:
        console.print(f"  [{C.DIM}]{routes_updated} routes existantes confirmées (inchangées)[/{C.DIM}]")
    if fixed:
        console.print(f"  [{C.DIM}]{fixed} nœud(s) 'Unknown' corrigés depuis le cache[/{C.DIM}]")
    if errors:
        console.print(f"  [{C.WARNING}]{errors} commodité(s) ignorée(s) (erreur réseau)[/{C.WARNING}]")
    console.print()
    console.print(
        f"[{C.DIM}]Total nœuds dans le graphe : [bold]{len(graph.nodes)}[/bold]  ·  "
        f"Utilisez [{C.LABEL}]/nav save[/{C.LABEL}] pour sauvegarder[/{C.DIM}]"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _expand_alias(query: str, ctx) -> str:
    """Expande @local et @dest en noms de lieux réels du joueur."""
    ql = query.lower().strip()
    if ql in ("@local", "@ici", "@here", "@pos", "@loc"):
        return (getattr(ctx.player, "location", None) or "").strip() or query
    if ql in ("@dest", "@destination", "@d"):
        return (getattr(ctx.player, "destination", None) or "").strip() or query
    return query


def _resolve_node(query: str, graph) -> str | None:
    """Résout un nom de nœud — insensible à la casse, underscores, fuzzy."""
    q = query.lower().replace("_", " ").strip()
    if not q:
        return None

    node_names = list(graph.nodes.keys())

    for name in node_names:
        if name.lower() == q:
            return name

    matches = [n for n in node_names if n.lower().startswith(q)]
    if len(matches) == 1:
        return matches[0]

    matches = [n for n in node_names if q in n.lower()]
    if len(matches) == 1:
        return matches[0]

    try:
        from rapidfuzz import process, fuzz
        best = process.extractOne(q, [n.lower() for n in node_names],
                                  scorer=fuzz.WRatio, score_cutoff=70)
        if best:
            return node_names[[n.lower() for n in node_names].index(best[0])]
    except ImportError:
        import difflib
        m = difflib.get_close_matches(q, [n.lower() for n in node_names], n=1, cutoff=0.65)
        if m:
            return node_names[[n.lower() for n in node_names].index(m[0])]

    return None


def _auto_add_from_uex(query: str, graph, ctx) -> str | None:
    """Cherche le lieu dans le cache UEX, interroge les routes, enrichit le graphe."""
    from uexinfo.api.uex_client import UEXClient, UEXError
    from uexinfo.models.transport_network import LocationNode, NodeType

    q = query.lower().replace("_", " ").strip()
    if not q:
        return None

    terminal = None
    best_score = 0

    try:
        from rapidfuzz import fuzz
        for t in ctx.cache.terminals:
            score = fuzz.WRatio(q, t.name.lower())
            if score > best_score and score >= 72:
                best_score, terminal = score, t
    except ImportError:
        import difflib
        names = [t.name for t in ctx.cache.terminals]
        m = difflib.get_close_matches(q, [n.lower() for n in names], n=1, cutoff=0.65)
        if m:
            terminal = next(t for t in ctx.cache.terminals if t.name.lower() == m[0])

    if not terminal:
        return None

    node_name = terminal.name
    console.print(
        f"[{C.DIM}]↻ Terminal UEX : [bold]{node_name}[/bold] — récupération des distances...[/{C.DIM}]"
    )

    if node_name not in graph.nodes:
        graph.add_node(LocationNode(
            name=node_name,
            type=NodeType.TERMINAL,
            system=terminal.star_system_name or "Stanton",
            metadata={"id_terminal": terminal.id, "source": "uex_auto"},
        ))

    edges_added = 0
    try:
        client = UEXClient()
        routes = client.get_routes(id_terminal_origin=terminal.id)

        seen_dest: dict[str, float] = {}
        for r in routes:
            dest = r.get("destination_terminal_name", "")
            dist = r.get("distance")
            if dest and dist is not None and dest not in seen_dest:
                seen_dest[dest] = float(dist)

        for dest_name, dist_gm in seen_dest.items():
            dest_node = _resolve_node_uex(dest_name, graph)
            if dest_node and dest_node != node_name:
                added = graph.add_or_update_route(
                    from_node=node_name,
                    to_node=dest_node,
                    distance_gm=dist_gm,
                    edge_type=EdgeType.QUANTUM,
                    source="uex",
                )
                if added:
                    edges_added += 1

    except UEXError as e:
        console.print(f"[{C.WARNING}]⚠ UEX inaccessible : {e}[/{C.WARNING}]")

    if edges_added > 0:
        console.print(
            f"[{C.SUCCESS}]✓ {edges_added} liaison(s) UEX ajoutée(s) vers {node_name}[/{C.SUCCESS}]  "
            f"[{C.DIM}]— /nav save pour conserver[/{C.DIM}]"
        )
    else:
        console.print(f"[{C.WARNING}]⚠ Nœud créé mais aucune liaison connue[/{C.WARNING}]")

    return node_name


def _resolve_node_uex(uex_terminal_name: str, graph) -> str | None:
    """Résout un nom de terminal UEX vers un nœud du graphe."""
    node_names = list(graph.nodes.keys())

    def _strict_resolve(q: str) -> str | None:
        ql = q.lower().strip()
        if len(ql) < 4:
            return None
        for n in node_names:
            if n.lower() == ql:
                return n
        matches = [n for n in node_names if n.lower().startswith(ql)]
        if len(matches) == 1:
            return matches[0]
        matches = [n for n in node_names if ql in n.lower() and len(ql) >= 5]
        if len(matches) == 1:
            return matches[0]
        try:
            from rapidfuzz import process, fuzz
            best = process.extractOne(ql, [n.lower() for n in node_names],
                                      scorer=fuzz.WRatio, score_cutoff=85)
            if best:
                return node_names[[n.lower() for n in node_names].index(best[0])]
        except ImportError:
            pass
        return None

    if " - " in uex_terminal_name:
        parts = [p.strip() for p in uex_terminal_name.split(" - ")]
        for part in reversed(parts[1:]):
            found = _strict_resolve(part)
            if found:
                return found
        for n in node_names:
            if n.lower() == uex_terminal_name.lower():
                return n
        return None

    return _resolve_node(uex_terminal_name, graph)


def _show_candidates(query: str, graph) -> None:
    q = query.lower().replace("_", " ").strip()
    node_names = list(graph.nodes.keys())
    suggestions = [n for n in node_names if q[:3] in n.lower()] if len(q) >= 3 else []

    if suggestions:
        console.print(f"[{C.DIM}]Nœuds proches :[/{C.DIM}]")
        for s in suggestions[:6]:
            console.print(f"  [{C.LABEL}]{s}[/{C.LABEL}]")
    else:
        _show_nodes_hint(graph)


def _show_nodes_hint(graph) -> None:
    node_names = sorted(graph.nodes.keys())
    if not node_names:
        console.print(f"[{C.DIM}]Aucun nœud dans le réseau — utilisez /nav add-route[/{C.DIM}]")
        return
    console.print(f"[{C.DIM}]Nœuds disponibles ({len(node_names)}) :[/{C.DIM}]")
    for name in node_names[:15]:
        node = graph.nodes[name]
        sys_label = f"  [{C.DIM}]{node.system}[/{C.DIM}]" if hasattr(node, "system") else ""
        console.print(f"  [{C.LABEL}]{name}[/{C.LABEL}]{sys_label}")
    if len(node_names) > 15:
        console.print(f"  [{C.DIM}]… et {len(node_names) - 15} autres — /nav nodes[/{C.DIM}]")
