"""Lieux des missions et des voyages (décision D11) : un texte → un nœud du graphe, sans deviner.

Le texte vient d'un contrat lu par OCR, d'une saisie ou du formulaire d'édition. Les
tournures de contrat sont d'abord retirées (« Admin - … », « … above Crusader »,
« … at MicroTech »), puis :
- un seul nœud trouvé par nom exact, début ou partie d'un seul nom : lieu sûr ;
- plusieurs nœuds aussi proches : liste à départager ;
- seulement des noms approchants, ou un nom retrouvé en retirant des mots à la fin du
  texte (« Port Tressler Medical Center ») : propositions, jamais retenues seules.
Le choix du joueur se fait dans `uexinfo.cli.places` ; le lieu retenu est gardé sous
sa référence `node:<nom>` et n'est plus jamais relu depuis le texte.
"""
from __future__ import annotations

import re

from uexinfo.names.normalize import norm
from uexinfo.names.refs import parse_ref, ref
from uexinfo.names.resolver import FUZZY, SUBSTRING, Match, Resolution, graph_index


def node_ref(name: str) -> str:
    """Référence d'un nœud du graphe : `node:<nom>`."""
    return ref("node", name)


def ref_node(place_ref: str | None, graph) -> str | None:
    """Nom du nœud désigné par une référence `node:<nom>`, s'il existe dans le graphe."""
    parsed = parse_ref("#" + place_ref) if place_ref else None
    if not parsed or parsed[0] != "node" or graph is None:
        return None
    e = graph_index(graph).by_ref("node", parsed[1])
    return e.id if e is not None else None


def clean_contract_place(text: str) -> str:
    """Retire les tournures de contrat autour du nom du lieu.

    « Admin - Seraphim » → « Seraphim » ; « Seraphim Station above Crusader » →
    « Seraphim Station » ; « Port Tressler at MicroTech » → « Port Tressler ».
    """
    clean = re.sub(r"^[A-Za-z]+ - ", "", text or "").strip()
    clean = re.sub(r"\s+above\s+.*$", "", clean, flags=re.IGNORECASE).strip()
    return re.sub(r"\s+at\s+.*$", "", clean, flags=re.IGNORECASE).strip()


def place_lookup(text: str, graph, system: str = "") -> tuple[str | None, Resolution]:
    """(nœud sûr ou None, candidats) pour le lieu écrit `text`.

    `system` (système du contexte, ex. celui des autres lieux de la mission) ne fait
    que classer les candidats : il ne choisit jamais à la place du joueur.
    """
    if not text or graph is None:
        return None, Resolution([])
    gi = graph_index(graph)
    query = text if parse_ref(text) else clean_contract_place(text)
    r = gi.resolve(query, kinds={"node"}, prefer_system=system)
    top = r.top
    if len(top) == 1 and top[0].level > FUZZY:
        return top[0].entity.id, r
    if r.matches and top[0].level > FUZZY:
        return None, r                       # plusieurs lieux aussi proches

    # Propositions : noms approchants, et le plus long début du texte qui désigne un lieu
    props: dict[int, Match] = {id(m.entity): m for m in r.matches}
    words = query.split()
    for n in range(len(words) - 1, 0, -1):
        rr = gi.resolve(" ".join(words[:n]), kinds={"node"}, min_level=SUBSTRING,
                        prefer_system=system)
        if rr.matches:
            for m in rr.matches:
                props.setdefault(id(m.entity), Match(m.entity, FUZZY, 100.0 * n / len(words)))
            break
    ps = norm(system)
    ordered = sorted(props.values(), key=lambda m: (-round(m.score, 1),
                                                    bool(ps) and ps not in m.entity.tokens,
                                                    m.entity.name))
    return None, Resolution(ordered)
