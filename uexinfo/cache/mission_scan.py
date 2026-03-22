"""Utilitaires partagés pour le scan batch de missions.

Utilisé par :
  - uexinfo/cli/commands/mission.py
  - uexinfo/overlay/server.py

Centralise : conversion ScreenshotEntry → MissionResult, détection des
missions déjà importées, calcul de distances source→destination.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uexinfo.cache.screenshot_db import ScreenshotEntry
    from uexinfo.cache.mission_manager import MissionManager
    from uexinfo.models.mission_result import MissionResult

# Préfixe source_raw pour les missions issues de la DB screenshots
OCR_PREFIX = "ocr:"


# ── Source raw ────────────────────────────────────────────────────────────────

def source_raw_from_entry(entry: "ScreenshotEntry") -> str:
    """Retourne le source_raw canonique : 'ocr:<filename>'."""
    return f"{OCR_PREFIX}{entry.file}"


def file_from_source_raw(source_raw: str) -> str | None:
    """Extrait le nom de fichier depuis source_raw 'ocr:<filename>'."""
    if source_raw and source_raw.startswith(OCR_PREFIX):
        return source_raw[len(OCR_PREFIX):]
    return None


# ── Déduplication ─────────────────────────────────────────────────────────────

def is_already_imported(entry: "ScreenshotEntry", mm: "MissionManager") -> bool:
    """True si ce screenshot a déjà été importé dans le catalogue.

    Critères (par ordre de priorité) :
      1. source_raw == 'ocr:<entry.file>'
      2. Titre + récompense identiques à une mission existante
    """
    file_ref = source_raw_from_entry(entry)
    data     = entry.data or {}
    title    = data.get("title", "")
    reward   = data.get("reward", 0)

    for m in mm.missions:
        # Critère 1 : source file exact
        if m.source_raw and m.source_raw == file_ref:
            return True
        # Critère 2 : titre + récompense (import via autre méthode)
        if title and m.name == title and m.reward_uec == reward and reward > 0:
            return True
    return False


def already_imported_set(mm: "MissionManager") -> set[str]:
    """Ensemble des fichiers sources déjà importés (pour batch check)."""
    result = set()
    for m in mm.missions:
        f = file_from_source_raw(m.source_raw or "")
        if f:
            result.add(f)
    return result


# ── Reconstruction MissionResult ──────────────────────────────────────────────

def entry_to_mission_result(entry: "ScreenshotEntry") -> "MissionResult | None":
    """Reconstruit un MissionResult depuis une ScreenshotEntry.data."""
    try:
        from uexinfo.models.mission_result import MissionResult, ParsedObjective
        data = entry.data or {}
        objs = []
        for o in data.get("objectives", []):
            objs.append(ParsedObjective(
                kind          = o.get("kind", "unknown"),
                commodity     = o.get("commodity"),
                quantity_scu  = o.get("quantity_scu"),
                location      = o.get("location"),
                location_hint = o.get("location_hint"),
                raw           = o.get("raw", ""),
            ))
        return MissionResult(
            title                 = data.get("title", ""),
            tab                   = data.get("tab", ""),
            reward                = data.get("reward", 0),
            contract_availability = data.get("availability", ""),
            contracted_by         = data.get("contracted_by", ""),
            parsed_objectives     = objs,
            source                = "ocr",
        )
    except Exception:
        return None


# ── Calcul de distances ───────────────────────────────────────────────────────

def _resolve_graph_node(name: str, graph, system_hint: str | None = None) -> str | None:
    """Résout un nom de lieu vers un nœud du graphe (insensible casse, fuzzy).

    system_hint : système préféré pour désambiguïser les gateways (ex: "Stanton").
    Les gateways partagent le même nom de base dans plusieurs systèmes,
    ex: "Nyx Gateway (Stanton)" vs "Nyx Gateway (Pyro)".
    """
    if not name:
        return None

    # Retirer les préfixes service : "Admin - Seraphim" → "Seraphim"
    clean = re.sub(r"^[A-Za-z]+ - ", "", name).strip()

    # Retirer "above X" en fin : "Seraphim Station above Crusader" → "Seraphim Station"
    clean = re.sub(r"\s+above\s+\S+.*$", "", clean, flags=re.IGNORECASE).strip()

    q = clean.lower().replace("_", " ")
    node_names = list(graph.nodes.keys())

    # 1. Match exact
    for n in node_names:
        if n.lower() == q:
            return n

    # 2. Contient le terme → candidats
    candidates = [n for n in node_names if q in n.lower()]
    if candidates:
        if len(candidates) == 1:
            return candidates[0]
        # Ambiguïté (typique des gateways) :
        # a) Préférer le candidat dont le nom contient le system_hint
        if system_hint:
            sh = system_hint.lower()
            preferred = [c for c in candidates if sh in c.lower()]
            if len(preferred) == 1:
                return preferred[0]
            if preferred:
                candidates = preferred  # réduire le champ avant le fallback longueur
        # b) Fallback : le plus long (le plus spécifique)
        return max(candidates, key=len)

    # 3. Premier token (code court ex: "CRU-L4")
    short = q.split()[0]
    if len(short) >= 3:
        for n in node_names:
            if n.lower().startswith(short):
                return n

    return None


def _node_system(node_name: str, graph) -> str | None:
    """Retourne le système d'un nœud résolu, ou None."""
    node = graph.nodes.get(node_name)
    if node:
        return getattr(node, "system", None)
    return None


def _path_distance(graph, node_a: str, node_b: str) -> float | None:
    """Distance en Gm entre deux nœuds du graphe, None si non trouvé."""
    if not node_a or not node_b or node_a == node_b:
        return None
    try:
        result = graph.find_shortest_path(node_a, node_b)
        if result is not None and getattr(result, "total_distance", None) is not None:
            return round(result.total_distance, 2)
    except Exception:
        pass
    return None


def compute_mission_distances(
    sources: list[str],
    destinations: list[str],
    graph,
) -> dict:
    """Calcule les distances d'une mission (plusieurs sources → plusieurs destinations).

    Stratégie :
      - Résoudre chaque lieu en nœud graphe (avec désambiguïsation des gateways)
      - Distance inter-sources (s'il y en a plusieurs)
      - Distance source finale → chaque destination
      - total_gm = somme de tous les segments

    Désambiguïsation des gateways :
      Les gateways portent le même nom de base dans plusieurs systèmes.
      On résout d'abord les lieux non-ambigus pour déterminer le système
      dominant, puis on ré-résout les gateways avec ce system_hint.

    Retourne :
      {
        "segments":   [{"from": str, "to": str, "gm": float}],
        "total_gm":   float,
        "has_data":   bool,
      }
    """
    all_names = list(sources) + list(destinations)

    # ── Passe 1 : résolution sans hint ────────────────────────────────────────
    resolved1 = {n: _resolve_graph_node(n, graph) for n in all_names}

    # ── Dériver le system_hint depuis les nœuds non-gateway résolus ───────────
    system_counts: dict[str, int] = {}
    for name, node in resolved1.items():
        if node and "gateway" not in node.lower():
            sys = _node_system(node, graph)
            if sys:
                system_counts[sys] = system_counts.get(sys, 0) + 1
    system_hint = max(system_counts, key=system_counts.__getitem__) if system_counts else None

    # ── Passe 2 : ré-résoudre les gateways avec le hint ──────────────────────
    resolved: dict[str, str | None] = {}
    for name in all_names:
        node = resolved1[name]
        if node and "gateway" in node.lower() and system_hint:
            # Ré-résoudre avec le hint pour choisir le bon côté
            better = _resolve_graph_node(name, graph, system_hint=system_hint)
            resolved[name] = better if better else node
        else:
            resolved[name] = _resolve_graph_node(name, graph, system_hint=system_hint)

    # ── Calcul des segments ───────────────────────────────────────────────────
    segments: list[dict] = []
    src_nodes = [(s, resolved[s]) for s in sources]
    dst_nodes = [(d, resolved[d]) for d in destinations]

    # Distances inter-sources (si plusieurs collectes)
    for i in range(len(src_nodes) - 1):
        na = src_nodes[i][1]
        nb = src_nodes[i + 1][1]
        d  = _path_distance(graph, na, nb)
        if d is not None:
            segments.append({"from": src_nodes[i][0], "to": src_nodes[i + 1][0], "gm": d})

    # Distance source finale → chaque destination
    if src_nodes:
        last_src_name, last_src_node = src_nodes[-1]
        for dst_name, dst_node in dst_nodes:
            d = _path_distance(graph, last_src_node, dst_node)
            if d is not None:
                segments.append({"from": last_src_name, "to": dst_name, "gm": d})

    total = round(sum(s["gm"] for s in segments), 2)
    return {
        "segments":  segments,
        "total_gm":  total,
        "has_data":  bool(segments),
    }


def compute_entry_distances(entry: "ScreenshotEntry", graph) -> dict:
    """Calcule les distances d'une ScreenshotEntry mission."""
    return compute_mission_distances(
        entry.sources,
        entry.destinations,
        graph,
    )
