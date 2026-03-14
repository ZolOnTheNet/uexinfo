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

    if sub in ("info",):
        _show_info(ctx)
    elif sub in ("nodes", "noeuds", "noeud", "node"):
        _list_nodes(args[1:], ctx)
    elif sub in ("edges", "edge", "liaisons", "liaison", "aretes", "arete", "arêtes", "arête"):
        _list_edges(args[1:], ctx)
    elif sub in ("jumps", "jump", "sauts", "saut"):
        _list_jumps(ctx)
    elif sub in ("route", "itineraire", "itinéraire", "chemin"):
        _find_route(args[1:], ctx)
    elif sub in ("add-route", "ajouter-route", "ajouter-liaison", "add-liaison"):
        _add_route(args[1:], ctx)
    elif sub in ("add-jump", "ajouter-saut", "ajouter-jump"):
        _add_jump(args[1:], ctx)
    elif sub in ("remove-route", "supprimer-route", "supprimer-liaison"):
        _remove_route(args[1:], ctx)
    elif sub in ("remove-jump", "supprimer-saut", "supprimer-jump"):
        _remove_jump(args[1:], ctx)
    elif sub in ("save", "sauvegarder", "enregistrer"):
        _save_graph(ctx)
    elif sub in ("raz", "reset", "reinitialiser", "réinitialiser"):
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
        print_error("Usage: /nav route <de> [to] <vers>")
        console.print(f"[{C.DIM}]Conseil : utilisez 'to' pour les noms à espaces :[/{C.DIM}]")
        console.print(f"[{C.DIM}]  /nav route New_Babbage to Port_Tressler[/{C.DIM}]")
        console.print(f"[{C.DIM}]  /nav route New_Babbage Port_Tressler[/{C.DIM}]")
        _show_nodes_hint(ctx.cache.transport_graph)
        return

    graph = ctx.cache.transport_graph

    # Parser "from X to Y" ou "X Y" (underscores → espaces partout)
    args_norm = [a.replace("_", " ") for a in args]

    if "to" in [a.lower() for a in args]:
        # Trouver le "to" en ignorant la casse
        idx = next(i for i, a in enumerate(args) if a.lower() == "to")
        from_loc = " ".join(args_norm[:idx]).strip()
        to_loc   = " ".join(args_norm[idx + 1:]).strip()
        from_node = _resolve_node(from_loc, graph)
        to_node   = _resolve_node(to_loc, graph)
    else:
        # Pas de "to" : essayer toutes les coupures possibles
        # On cherche la première (depuis la droite) où les deux moitiés résolvent
        from_node, to_node = None, None
        from_loc = to_loc = ""
        for split in range(len(args_norm) - 1, 0, -1):
            fl = " ".join(args_norm[:split]).strip()
            tl = " ".join(args_norm[split:]).strip()
            fn = _resolve_node(fl, graph)
            tn = _resolve_node(tl, graph)
            if fn and tn:
                from_node, to_node = fn, tn
                from_loc, to_loc = fl, tl
                break
        # Si aucune coupure ne fonctionne, essayer depuis la gauche
        if not from_node:
            for split in range(1, len(args_norm)):
                fl = " ".join(args_norm[:split]).strip()
                tl = " ".join(args_norm[split:]).strip()
                fn = _resolve_node(fl, graph)
                tn = _resolve_node(tl, graph)
                if fn and tn:
                    from_node, to_node = fn, tn
                    from_loc, to_loc = fl, tl
                    break
        # Encore rien → résoudre chaque moitié séparément pour un meilleur message
        if not from_node:
            mid = len(args_norm) // 2
            from_loc = " ".join(args_norm[:mid]).strip()
            to_loc   = " ".join(args_norm[mid:]).strip()
            from_node = _resolve_node(from_loc, graph)
            to_node   = _resolve_node(to_loc, graph)

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
    """Résout un nom de nœud — insensible à la casse, underscores, fuzzy."""
    q = query.lower().replace("_", " ").strip()
    if not q:
        return None

    node_names = list(graph.nodes.keys())

    # 1. Match exact (insensible à la casse)
    for name in node_names:
        if name.lower() == q:
            return name

    # 2. Préfixe
    matches = [n for n in node_names if n.lower().startswith(q)]
    if len(matches) == 1:
        return matches[0]

    # 3. Sous-chaîne
    matches = [n for n in node_names if q in n.lower()]
    if len(matches) == 1:
        return matches[0]

    # 4. Fuzzy (rapidfuzz si disponible)
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
    """Cherche le lieu dans le cache UEX, interroge les routes, enrichit le graphe.

    Retourne le nom du nœud ajouté (ou trouvé), ou None si introuvable.
    """
    from uexinfo.api.uex_client import UEXClient, UEXError
    from uexinfo.models.transport_network import LocationNode, NodeType

    q = query.lower().replace("_", " ").strip()
    if not q:
        return None

    # ── 1. Chercher un terminal correspondant dans le cache UEX ──────────────
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

    # ── 2. Créer le nœud s'il n'existe pas déjà ─────────────────────────────
    if node_name not in graph.nodes:
        graph.add_node(LocationNode(
            name=node_name,
            type=NodeType.TERMINAL,
            system=terminal.star_system_name or "Stanton",
            metadata={"id_terminal": terminal.id, "source": "uex_auto"},
        ))

    # ── 3. Requête API : routes depuis ce terminal pour obtenir les distances ─
    edges_added = 0
    try:
        client = UEXClient()
        routes = client.get_routes(id_terminal_origin=terminal.id)

        # Dédupliquer par destination (une route par commodity → on veut une par dest)
        seen_dest: dict[str, float] = {}  # dest_name → distance_gm
        for r in routes:
            dest = r.get("destination_terminal_name", "")
            dist = r.get("distance")
            if dest and dist is not None and dest not in seen_dest:
                seen_dest[dest] = float(dist)

        # Ajouter les edges vers les nœuds déjà connus du graphe
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
        console.print(
            f"[{C.WARNING}]⚠ Nœud créé mais aucune liaison connue — route peut être incomplète[/{C.WARNING}]"
        )

    return node_name


def _resolve_node_uex(uex_terminal_name: str, graph) -> str | None:
    """Résout un nom de terminal UEX vers un nœud du graphe.

    Les terminaux UEX ont des préfixes service : "Admin - New Babbage",
    "TDD - Area 18", "Scrap - Rappel"...
    Le graphe peut avoir le nom complet ou juste la partie lieu.
    """
    node_names = list(graph.nodes.keys())

    def _strict_resolve(q: str) -> str | None:
        """Match exact ou sous-chaîne stricte — pas de fuzzy agressif."""
        ql = q.lower().strip()
        if len(ql) < 4:
            return None
        # Exact
        for n in node_names:
            if n.lower() == ql:
                return n
        # Préfixe
        matches = [n for n in node_names if n.lower().startswith(ql)]
        if len(matches) == 1:
            return matches[0]
        # Sous-chaîne stricte (q dans node ou node dans q — longueur minimale)
        matches = [n for n in node_names if ql in n.lower() and len(ql) >= 5]
        if len(matches) == 1:
            return matches[0]
        # Fuzzy serré (85)
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
        # Nom avec préfixe service ("Admin - X", "TDD - X"…)
        # parts[0] est le type de service (Admin, TDD, Scrap…) — ne pas l'utiliser
        # comme nom de lieu. On essaie parts[1:] du plus spécifique (fin) au début.
        parts = [p.strip() for p in uex_terminal_name.split(" - ")]
        for part in reversed(parts[1:]):   # skip parts[0] = service prefix
            found = _strict_resolve(part)
            if found:
                return found
        # Essai sur le nom complet seulement si le graphe stocke lui-même ce format
        # (ex: "Admin - Orbituary" est un nœud du graphe)
        for n in node_names:
            if n.lower() == uex_terminal_name.lower():
                return n
        return None

    # Nom sans préfixe : fuzzy normal
    return _resolve_node(uex_terminal_name, graph)


def _show_candidates(query: str, graph) -> None:
    """Affiche les nœuds proches du terme non résolu."""
    q = query.lower().replace("_", " ").strip()
    node_names = list(graph.nodes.keys())

    # Chercher des suggestions partielles
    suggestions = [n for n in node_names if q[:3] in n.lower()] if len(q) >= 3 else []

    if suggestions:
        console.print(f"[{C.DIM}]Nœuds proches :[/{C.DIM}]")
        for s in suggestions[:6]:
            console.print(f"  [{C.LABEL}]{s}[/{C.LABEL}]")
    else:
        _show_nodes_hint(graph)


def _show_nodes_hint(graph) -> None:
    """Affiche les nœuds disponibles."""
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
