"""Commande /nav — gestion du réseau de transport (jump points, routes QT)."""
from __future__ import annotations

from rich.table import Table

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.models.transport_network import EdgeType, JumpPoint, LocationNode, NodeType, RouteEdge


@register("nav", "navigation", "n", "qt", "quantum")
def cmd_nav(args: list[str], ctx) -> None:
    """Gestion du réseau de transport interstellaire."""
    if not args:
        _show_info(ctx)
        return

    sub = args[0].lower()

    if sub == "info":
        _show_info(ctx)
    elif sub == "nodes":
        _list_nodes(args[1:], ctx)
    elif sub == "edges":
        _list_edges(args[1:], ctx)
    elif sub in ("jumps", "jump"):
        _list_jumps(ctx)
    elif sub == "route":
        _find_route(args[1:], ctx)
    elif sub == "add-route":
        _add_route(args[1:], ctx)
    elif sub == "add-jump":
        _add_jump(args[1:], ctx)
    elif sub == "remove-route":
        _remove_route(args[1:], ctx)
    elif sub == "remove-jump":
        _remove_jump(args[1:], ctx)
    elif sub == "save":
        _save_graph(ctx)
    elif sub == "raz":
        _reset_graph(ctx)
    else:
        print_error(f"Sous-commande inconnue : {sub}  (/help nav)")


# ── Info & stats ───────────────────────────────────────────────────────────────

def _show_info(ctx) -> None:
    """Affiche les stats du réseau de transport."""
    graph = ctx.cache.transport_graph
    section("Réseau de transport")

    # Stats générales
    n_nodes = len(graph.nodes)
    n_edges = len([e for e in graph.edges if e.edge_type != EdgeType.JUMP])  # Sans doublons jump
    n_jumps = len(graph.jump_points)

    # Décompte par système
    systems = {}
    for node in graph.nodes.values():
        systems.setdefault(node.system, 0)
        systems[node.system] += 1

    console.print(f"  [bold]Nœuds :[/bold]       {n_nodes}  [{C.DIM}](terminaux, stations, villes)[/{C.DIM}]")
    console.print(f"  [bold]Routes :[/bold]      {n_edges // 2}  [{C.DIM}](bidirectionnelles)[/{C.DIM}]")
    console.print(f"  [bold]Jump points :[/bold] {n_jumps}  [{C.DIM}](passerelles inter-systèmes)[/{C.DIM}]")
    console.print()

    # Systèmes
    if systems:
        console.print(f"[bold {C.LABEL}]Systèmes couverts :[/bold {C.LABEL}]")
        for sys, count in sorted(systems.items()):
            console.print(f"  [{C.UEX}]{sys}[/{C.UEX}]  [{C.DIM}]{count} lieux[/{C.DIM}]")

    console.print()
    console.print(f"[{C.DIM}]Utilisez /nav nodes, /nav edges, /nav jumps pour explorer le réseau[/{C.DIM}]")
    console.print(f"[{C.DIM}]Utilisez /nav route <de> <vers> pour calculer un itinéraire[/{C.DIM}]")

    # Indiquer s'il y a des modifications non sauvegardées
    if graph.has_unsaved_changes:
        console.print()
        console.print(
            f"[{C.WARNING}]⊕  {graph._unsaved_changes} modification(s) non sauvegardée(s)  "
            f"—  utilisez /nav save[/{C.WARNING}]"
        )


# ── Nodes ──────────────────────────────────────────────────────────────────────

def _list_nodes(args: list[str], ctx) -> None:
    """Liste les nœuds, filtrable par système."""
    graph = ctx.cache.transport_graph
    system_filter = args[0].lower() if args else None

    nodes = list(graph.nodes.values())
    if system_filter:
        nodes = [n for n in nodes if n.system.lower() == system_filter]

    if not nodes:
        print_warn(f"Aucun nœud trouvé{' dans ' + system_filter if system_filter else ''}")
        return

    section(f"Nœuds — {nodes[0].system if system_filter else 'Tous systèmes'}")

    # Table
    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Nom", style=C.LABEL)
    tbl.add_column("Type", style=C.DIM)
    tbl.add_column("Système", style=C.UEX)
    tbl.add_column("Voisins", style=C.NEUTRAL, justify="right")

    for node in sorted(nodes, key=lambda n: (n.system, n.name)):
        neighbors = graph.get_neighbors(node.name)
        tbl.add_row(
            node.name,
            node.type.value,
            node.system,
            str(len(neighbors))
        )

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(nodes)} nœuds[/{C.DIM}]")


# ── Edges ──────────────────────────────────────────────────────────────────────

def _list_edges(args: list[str], ctx) -> None:
    """Liste les arêtes, filtrable par nœud source."""
    graph = ctx.cache.transport_graph
    node_filter = " ".join(args).strip() if args else None

    edges = graph.edges
    if node_filter:
        edges = [e for e in edges if node_filter.lower() in e.from_node.lower()]

    # Filtrer les doublons (ne garder qu'une direction)
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

    # Table
    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("De", style=C.LABEL)
    tbl.add_column("", style=C.DIM)
    tbl.add_column("Vers", style=C.LABEL)
    tbl.add_column("Distance", style=C.UEX, justify="right")
    tbl.add_column("Type", style=C.DIM)

    for edge in sorted(unique_edges, key=lambda e: e.from_node):
        dist_str = f"{edge.distance_gm:.1f} Gm" if edge.distance_gm >= 1 else f"{edge.distance_gm * 1000:.0f} Mm"
        tbl.add_row(
            edge.from_node[:20],
            "↔",
            edge.to_node[:20],
            dist_str,
            edge.edge_type.value
        )

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(unique_edges)} routes[/{C.DIM}]")


# ── Jump points ────────────────────────────────────────────────────────────────

def _list_jumps(ctx) -> None:
    """Liste tous les jump points."""
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
        status = "✓" if jp.is_active else "✗"
        status_color = C.SUCCESS if jp.is_active else C.DIM
        tbl.add_row(
            jp.name,
            "⇨",
            f"{jp.from_system} ↔ {jp.to_system}",
            jp.size,
            f"[{status_color}]{status}[/{status_color}]"
        )

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(jumps)} jump points[/{C.DIM}]")


# ── Route finding ──────────────────────────────────────────────────────────────

def _find_route(args: list[str], ctx) -> None:
    """Calcule le plus court chemin entre deux lieux."""
    if len(args) < 2:
        print_error("Usage: /nav route <de> <vers>")
        return

    # Parser "from X to Y" ou "X Y"
    if "to" in args:
        idx = args.index("to")
        from_loc = " ".join(args[:idx])
        to_loc = " ".join(args[idx + 1:])
    else:
        from_loc = args[0]
        to_loc = " ".join(args[1:])

    graph = ctx.cache.transport_graph

    # Résoudre les noms
    from_node = _resolve_node(from_loc, graph)
    to_node = _resolve_node(to_loc, graph)

    if not from_node:
        print_error(f"Lieu de départ introuvable : {from_loc}")
        return
    if not to_node:
        print_error(f"Lieu d'arrivée introuvable : {to_loc}")
        return

    # Calculer le chemin
    result = graph.find_shortest_path(from_node, to_node)

    if not result:
        print_warn(f"Aucune route trouvée entre {from_node} et {to_node}")
        return

    # Afficher le résultat
    section(f"Route — {from_node} → {to_node}")

    console.print(f"  [bold]Distance totale :[/bold] [{C.UEX}]{result.total_distance:.1f} Gm[/{C.UEX}]")
    console.print(f"  [bold]Durée estimée :[/bold]   [{C.NEUTRAL}]{result.duration_formatted}[/{C.NEUTRAL}]")
    if result.jump_points:
        console.print(f"  [bold]Jump points :[/bold]     [{C.WARNING}]{len(result.jump_points)}[/{C.WARNING}]")

    console.print(f"\n[bold {C.LABEL}]Étapes :[/bold {C.LABEL}]")
    for i, seg in enumerate(result.segments, 1):
        icon = "⇨" if seg["type"] == "jump" else "→"
        type_label = "[bold yellow]JUMP[/bold yellow]" if seg["type"] == "jump" else "QT"
        dist_str = f"{seg['distance_gm']:.1f} Gm" if seg['distance_gm'] >= 1 else f"{seg['distance_gm'] * 1000:.0f} Mm"

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


# ── Add route ──────────────────────────────────────────────────────────────────

def _add_route(args: list[str], ctx) -> None:
    """Ajoute une route entre deux nœuds."""
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

    # Vérifier que les nœuds existent
    if from_loc not in graph.nodes:
        print_error(f"Nœud introuvable : {from_loc}  — Ajoutez-le d'abord avec /nav add-node")
        return
    if to_loc not in graph.nodes:
        print_error(f"Nœud introuvable : {to_loc}")
        return

    # Créer l'arête
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
    """Ajoute un jump point."""
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

    # Créer le jump point
    jp = JumpPoint(
        name=name,
        from_system=from_sys,
        to_system=to_sys,
        entry_location=entry,
        exit_location=exit_loc,
        size=size,
    )
    graph.add_jump_point(jp)

    print_ok(f"Jump point ajouté : {name}  ({from_sys} ↔ {to_sys})")
    console.print(f"[{C.DIM}]Utilisez /nav save pour sauvegarder[/{C.DIM}]")


# ── Remove ─────────────────────────────────────────────────────────────────────

def _remove_route(args: list[str], ctx) -> None:
    """Supprime une route."""
    if len(args) < 2:
        print_error("Usage: /nav remove-route <de> <vers>")
        return

    from_loc = args[0]
    to_loc = args[1]
    graph = ctx.cache.transport_graph

    # Supprimer les deux directions
    removed = 0
    graph.edges = [
        e for e in graph.edges
        if not ((e.from_node == from_loc and e.to_node == to_loc) or
                (e.from_node == to_loc and e.to_node == from_loc))
    ]
    # Reconstruire l'adjacence
    graph._adjacency.clear()
    for edge in graph.edges:
        graph._adjacency.setdefault(edge.from_node, []).append(edge)

    print_ok(f"Route supprimée : {from_loc} ↔ {to_loc}")
    console.print(f"[{C.DIM}]Utilisez /nav save pour sauvegarder[/{C.DIM}]")


def _remove_jump(args: list[str], ctx) -> None:
    """Supprime un jump point."""
    if not args:
        print_error("Usage: /nav remove-jump <nom>")
        return

    name = args[0]
    graph = ctx.cache.transport_graph

    if name not in graph.jump_points:
        print_error(f"Jump point introuvable : {name}")
        return

    # Supprimer le jump point
    del graph.jump_points[name]

    # Supprimer les arêtes associées
    graph.edges = [e for e in graph.edges if name not in e.notes]
    # Reconstruire l'adjacence
    graph._adjacency.clear()
    for edge in graph.edges:
        graph._adjacency.setdefault(edge.from_node, []).append(edge)

    print_ok(f"Jump point supprimé : {name}")
    console.print(f"[{C.DIM}]Utilisez /nav save pour sauvegarder[/{C.DIM}]")


# ── Save & reset ───────────────────────────────────────────────────────────────

def _save_graph(ctx) -> None:
    """Sauvegarde le graphe dans le fichier source."""
    ctx.cache.save_transport_graph()
    print_ok("Graphe de transport sauvegardé dans uexinfo/data/transport_network.json")
    console.print(f"[{C.DIM}]Pensez à commiter ce fichier avec git[/{C.DIM}]")


def _reset_graph(ctx) -> None:
    """Réinitialise le graphe."""
    print_warn("Cette action supprimera toutes les modifications non sauvegardées")
    # TODO: demander confirmation via AskUserQuestion
    ctx.cache.load_transport_graph()
    print_ok("Graphe réinitialisé depuis le fichier source")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_node(query: str, graph) -> str | None:
    """Résout un nom de nœud (recherche flexible)."""
    q = query.lower().strip()

    # Exact match
    if q in graph.nodes:
        return q
    for name in graph.nodes:
        if name.lower() == q:
            return name

    # Partial match
    matches = [name for name in graph.nodes if q in name.lower()]
    if len(matches) == 1:
        return matches[0]

    return None
