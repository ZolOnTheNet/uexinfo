"""Lieux des missions et des voyages, côté joueur (décision D11).

Un lieu de mission est relié une seule fois à un nœud du graphe, quand la mission est
enregistrée (scan, saisie, formulaire) : lieu sûr retenu, sinon liste ou proposition au
joueur (`uexinfo.names.places`), dont le choix est mémorisé (`cache/place_aliases.py`).
Ensuite, distances, ordre des étapes et boucle travaillent sur les références
(`mission_node_map`) ; un texte resté « à préciser » n'est jamais deviné
(`/mission lieux` le fait départager).
"""
from __future__ import annotations

from collections import Counter

from uexinfo.cache import place_aliases
from uexinfo.names import link, parse_ref
from uexinfo.names.places import node_ref, place_lookup, ref_node


def resolve_place(text: str, ctx, *, ask: bool = True, system: str = "", graph=None) -> str | None:
    """Nœud du graphe désigné par le lieu écrit `text`, selon la règle 3 (D11).

    Choix déjà fait par le joueur pour ce texte, sinon lieu sûr, sinon liste ou
    proposition (`ask`) dont le choix est mémorisé. None : rien de sûr (ou annulé).
    """
    graph = graph if graph is not None else ctx.cache.transport_graph
    known = ref_node(place_aliases.get(text), graph)
    if known:
        return known
    node, r = place_lookup(text, graph, system)
    if node or not r.matches or not ask:
        return node
    from uexinfo.cli.choose import decide
    chosen = decide(ctx, r, text, title="Lieu de mission")
    if chosen is None:
        return None
    place_aliases.remember(text, node_ref(chosen.name))
    return chosen.name


def _main_system(nodes, graph) -> str:
    """Système le plus fréquent parmi des nœuds (gateways exclues), ou ''."""
    systems = Counter(getattr(graph.nodes.get(n), "system", "") for n in nodes
                      if n and "gateway" not in n.lower())
    systems.pop("", None)
    return systems.most_common(1)[0][0] if systems else ""


def ensure_mission_places(m, ctx, *, ask: bool = True) -> list[str]:
    """Relie chaque lieu écrit de la mission `m` qui ne l'est pas encore ; renvoie ceux
    restés à préciser. Les lieux sûrs d'abord : leur système classe les listes proposées
    ensuite (une « Pyro Gateway » dans une mission de Nyx : celle de Nyx en tête)."""
    graph = ctx.cache.transport_graph
    if graph is None:
        return m.unresolved_places
    pending = [(o, attr) for o in m.objectives for attr in ("source", "destination")
               if getattr(o, attr) and not getattr(o, f"{attr}_ref")]
    if not pending:
        return []
    found: dict[str, str | None] = {
        text: resolve_place(text, ctx, ask=False, graph=graph)
        for text in dict.fromkeys(getattr(o, attr) for o, attr in pending)
    }
    known = [ref_node(r, graph) for r in m.place_refs().values()] + list(found.values())
    system = _main_system(known, graph)
    for text, node in found.items():
        if node is None and ask:
            found[text] = resolve_place(text, ctx, ask=True, system=system, graph=graph)
    for o, attr in pending:
        node = found.get(getattr(o, attr))
        if node:
            setattr(o, attr, node)
            setattr(o, f"{attr}_ref", node_ref(node))
    return m.unresolved_places


def mission_node_map(missions, graph) -> dict[str, str | None]:
    """Nom affiché → nœud du graphe, pour tous les lieux des missions, d'après leurs
    références seulement (un lieu à préciser donne None)."""
    nodes: dict[str, str | None] = {}
    for m in missions:
        for o in m.objectives:
            for text, r in ((o.source, o.source_ref), (o.destination, o.destination_ref)):
                if text and nodes.get(text) is None:
                    nodes[text] = ref_node(r, graph)
    return nodes


def player_place(ctx, graph=None) -> tuple[str | None, str | None]:
    """(nom du nœud, référence) de la position du joueur, retrouvée par identifiant."""
    from uexinfo.cli.commands.nav import _player_node
    graph = graph if graph is not None else ctx.cache.transport_graph
    node = _player_node(ctx, graph) if graph is not None else None
    return (node, node_ref(node)) if node else (None, None)


def place_link(name: str, place_ref: str | None, text: str | None = None) -> str:
    """Nom de lieu cliquable s'il est relié (le lien porte sa référence) ; sinon le texte
    suivi de « ? » : lieu à préciser, qu'aucun clic ne doit deviner."""
    from uexinfo.display import colors as C
    shown = name if text is None else text
    parsed = parse_ref("#" + place_ref) if place_ref else None
    if parsed:
        return link(parsed[0], parsed[1], shown)
    return f"{shown} [{C.WARNING}]?[/{C.WARNING}]"


def node_terminals(node: str, ctx) -> list:
    """Terminaux du lieu `node` (nom exact, D11) : ceux de commerce ouverts, sinon le principal."""
    from uexinfo.names import resolve
    if not node:
        return []
    r = resolve(ctx, "#" + node_ref(node), kinds={"terminal"})
    return [m.entity.obj for m in r.matches]


def refresh_places(ctx, missions=None) -> None:
    """Relie, sans rien demander, les lieux encore à préciser qui sont devenus sûrs
    (ancienne mission enregistrée avant D11, graphe enrichi depuis) ; enregistre si besoin."""
    mm = getattr(ctx, "mission_manager", None)
    if mm is None or ctx.cache.transport_graph is None:
        return
    changed = False
    for m in (missions if missions is not None else mm.missions):
        before = len(m.unresolved_places)
        if before and len(ensure_mission_places(m, ctx, ask=False)) < before:
            changed = True
    if changed:
        mm.save()


# Ce qu'un filtre de voyage peut désigner : un lieu UEX ou ce qui le contient
AREA_KINDS = {"system", "planet", "moon", "station", "city", "outpost"}
_AREA_ATTRS = (("station", "id_space_station"), ("city", "id_city"), ("outpost", "id_outpost"),
               ("moon", "id_moon"), ("planet", "id_planet"), ("system", "id_star_system"))


def place_area(node: str, ctx) -> set[str]:
    """Références du lieu `node` et de tout ce qui le contient (station ou ville, lune,
    planète, système), lues sur ses terminaux UEX : « passer par microTech » se vérifie
    par identité, jamais par un morceau de nom (D11)."""
    from uexinfo.names import ref
    out = {node_ref(node)}
    for t in node_terminals(node, ctx):
        for kind, attr in _AREA_ATTRS:
            v = getattr(t, attr, 0)
            if v:
                out.add(ref(kind, v))
    return out


def area_ref(text: str, ctx, *, ask: bool = True) -> str | None:
    """Référence du lieu, de la planète ou du système désigné par `text` (filtres
    `--to` et `--exclude`), selon la règle 3 ; None si introuvable, ambigu sans
    personne pour choisir (`ask=False`), ou annulé."""
    from uexinfo.cli.choose import decide
    from uexinfo.names import ref, resolve
    r = resolve(ctx, text, kinds=AREA_KINDS)
    if not r.matches:
        return None
    obj = decide(ctx, r, text, title="Lieu", ask=ask)
    e = next((m.entity for m in r.matches if m.entity.obj is obj), None) if obj is not None else None
    return ref(e.kind, e.id) if e is not None else None
