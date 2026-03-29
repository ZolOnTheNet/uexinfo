"""Utilitaires partagés pour le scan batch de missions.

Utilisé par :
  - uexinfo/cli/commands/mission.py
  - uexinfo/overlay/server.py

Centralise : conversion ScreenshotEntry → MissionResult, détection des
missions déjà importées, calcul de distances source→destination.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uexinfo.cache.screenshot_db import ScreenshotEntry
    from uexinfo.cache.mission_manager import MissionManager
    from uexinfo.models.mission_result import MissionResult

# Préfixe source_raw pour les missions issues de la DB screenshots
OCR_PREFIX = "ocr:"


# ── Normalisation des noms de lieux OCR ───────────────────────────────────────

# Codes L-point : OCR confond S↔5, O↔0, I↔1 dans le suffixe numérique
# Exemples : "ARC-LS" → "ARC-L5", "HUR-LI" → "HUR-L1", "MIC-LO" → "MIC-L0"
_LNUM_FIX = re.compile(r'\b([A-Z]{2,3}-L)([SOI])\b')
_LNUM_MAP = {"S": "5", "O": "0", "I": "1"}

# Corrections orthographiques connues
_SPELLING_FIX: dict[str, str] = {
    "baljini":                 "Baijini",
    "baljini point":           "Baijini Point",
    "bafini point":            "Baijini Point",
    "beljinl point":           "Baijini Point",   # OCR noise
    "beljini point":           "Baijini Point",
    "seffini point":           "Baijini Point",   # OCR très dégradé
    "belpl":                   "Baijini Point",
    "seraphim station":        "Seraphim",
    "serephim station":        "Seraphim",
    "seraphim":                "Seraphim",
    "everus harbor i":         "Everus Harbor",
    "everus herbor":           "Everus Harbor",   # OCR noise
    "everus hertor":           "Everus Harbor",
    "yallow core station":     "Yellow Core Station",
    "yallow core":             "Yellow Core Station",
    "shallow frontier":        "Shallow Frontier Station",
    "shellow frontier":        "Shallow Frontier Station",   # OCR noise
    "shellow frontier stetion":"Shallow Frontier Station",
    "shallow fields":          "Shallow Fields Station",
    "shallow flekda":          "Shallow Fields Station",     # OCR noise
    "shallow flekda station":  "Shallow Fields Station",
    "sheliow fiekis":          "Shallow Fields Station",     # OCR très dégradé
    "sheliow fiekis station":  "Shallow Fields Station",
    "arc-l1":                  "ARC-L1",
    "arc-l2":                  "ARC-L2",
    "arc-l3":                  "ARC-L3",
    "arc-l4":                  "ARC-L4",
    "arc-l5":                  "ARC-L5",
    # Long Forest : formes courtes / chars parasites OCR (T, I, L en fin de mot)
    "long forest":             "Long Forest Station",
    "long forest station t":   "Long Forest Station",
    "long forest station i":   "Long Forest Station",
    "long forest station l":   "Long Forest Station",
    # Lively Pathway(s) Station — ARC-L2 (OCR variantes orthographiques)
    "lively pathway station":  "Lively Pathways Station",
    "lively pathway":          "Lively Pathways Station",
    "lively pathways":         "Lively Pathways Station",
    "livaly pathway station":  "Lively Pathways Station",
    "livaly pathways station": "Lively Pathways Station",
}

# Stations Covalex/L-point : noms complets non présents dans le graphe de navigation.
# Le graphe utilise uniquement le code L-point (ex: MIC-L2).
# Préfixer le nom permet à _resolve_graph_node de retrouver le nœud par troncature.
_STATION_LPOINT: dict[str, str] = {
    # Stations Covalex non nommées dans le graphe (uniquement le code L-point)
    # MicroTech
    "long forest station":       "MIC-L2",
    "shallow frontier station":  "MIC-L1",
    "high course station":       "MIC-L3",
    # Crusader
    "shallow fields station":    "CRU-L4",
    "green glade station":       "CRU-L3",
    # ArcCorp
    "lively pathways station":   "ARC-L5",
    "yellow core station":       "ARC-L1",
    # Nota : Seraphim, Everus Harbor, Baijini Point, Port Tressler sont
    # déjà des nœuds nommés dans le graphe — pas de préfixage nécessaire.
}

# Suffixes connus tronqués → complétion
_SUFFIX_COMPLETE: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bShallow\s+Fields\b',    re.IGNORECASE), "Shallow Fields Station"),
    (re.compile(r'\bShallow\s+Frontier\b',  re.IGNORECASE), "Shallow Frontier Station"),
    (re.compile(r'\bHigh\s+Course\b',       re.IGNORECASE), "High Course Station"),
    (re.compile(r'\bLivaly\s+Pathwer\w*\b', re.IGNORECASE), "Lively Pathways Station"),
    (re.compile(r'\bGreen\s+Glade\b',       re.IGNORECASE), "Green Glade Station"),
]

# Patterns pour récupérer le lien source depuis blue_text
# "XXX Station at ArcCorp's L2 Lagrange" ou "at MicroTech's L3 Lagrange point"
# "et" = OCR confusion de "at" fréquente
_RE_BLUE_AT_LAGRANGE = re.compile(
    r"(.+?)\s+(?:at|et)\s+(.+?)(?:'s?\s+L(\d)\s+[Ll]agr?\w*(?:\s+point)?)?\s*$",
    re.IGNORECASE,
)
# Continuation de ligne : "at Crusader's L4 Lagrange point" seul (début de ligne)
_RE_BLUE_AT_ONLY = re.compile(
    r"^(?:at|et)\s*(.+?)(?:'s?\s+L(\d)\s+[Ll]agr?\w*)?",
    re.IGNORECASE,
)
# "ArcCorp's L5 Lagrange point" sans "at" en début de ligne (83C pattern)
_RE_BLUE_PLANET_LPOINT = re.compile(
    r"^(.+?)'s?\s+L([SOI\d])\s+[Ll]agr",
    re.IGNORECASE,
)
# "Station above Planet" (ou "Station above" tronqué en fin de ligne)
_RE_BLUE_ABOVE = re.compile(
    r"^(.+?)\s+(?:above|sbove|shove|sbave|ahove|ahave)(?:\s+\w.*)?$",
    re.IGNORECASE,
)
# Bruit OCR à ignorer dans blue_text (durée, codes, entreprises, symboles seuls)
_RE_BLUE_NOISE = re.compile(
    r"^(?:\d+h|\d+m|[A-Z]{4,}\s+[A-Z]+\s+CONTRACTOR|COVALE|COWAL|COWLE|"
    r"CONTRACT\s+AVAIL|CONTRACTED|REWARD|[^A-Za-z]*$|.{1,3}$)",
    re.IGNORECASE,
)
_PLANET_CODE: dict[str, str] = {
    "arccorp":    "ARC",
    "arc":        "ARC",
    "hurston":    "HUR",
    "microtech":  "MIC",
    "micratech":  "MIC",   # OCR noise
    "crusader":   "CRU",
    "cruseder":   "CRU",   # OCR noise
    "pyro":       "PYR",
    "stanton":    "STA",
}


# Durée de contrat OCR → faux positif "lieu" : "1h 60m", "1n60m", "2h2m", "0h23m"…
_RE_DURATION = re.compile(r"^\d+[hn]\d+m?\s*$", re.IGNORECASE)


def normalize_location(name: str) -> str:
    """Normalise un nom de lieu provenant de l'OCR.

    Corrige :
    - Codes L-point avec lettre à la place du chiffre (ARC-LS → ARC-L5)
    - Orthographes fréquemment fautées (Baljini → Baijini)
    - Noms tronqués (Shallow Fields → Shallow Fields Station)
    - Retourne "" pour les durées parsées comme lieu ("1n60m", "2h2m"…)
    """
    if not name:
        return name

    # Durée de contrat → pas un lieu
    if _RE_DURATION.match(name.strip()):
        return ""

    # Correction digit/lettre dans code L-point
    fixed = _LNUM_FIX.sub(lambda m: m.group(1) + _LNUM_MAP[m.group(2)], name)

    # Corrections orthographiques (comparaison insensible à la casse)
    low = fixed.lower()
    for bad, good in _SPELLING_FIX.items():
        if low == bad:
            fixed = good
            break  # continuer vers _STATION_LPOINT pour le préfixage éventuel

    # Complétion de suffixes tronqués : remplace le motif par la forme complète,
    # sauf si le nom contient déjà le dernier mot du remplacement (ex: "Station").
    for pat, replacement in _SUFFIX_COMPLETE:
        suffix_word = replacement.split()[-1].lower()
        if pat.search(fixed) and not fixed.lower().endswith(suffix_word):
            new_fixed = pat.sub(replacement, fixed)
            if new_fixed != fixed:
                fixed = new_fixed
                break

    # Préfixage L-point : si le nom est une station Covalex connue sans préfixe,
    # ajouter le code L-point pour que _resolve_graph_node puisse le trouver.
    low2 = fixed.lower()
    for station_name, lpoint in _STATION_LPOINT.items():
        if low2 == station_name:
            fixed = f"{lpoint} {fixed}"
            break
        # Cas "MIC-L2 Long Forest Station" : déjà préfixé, ne rien faire
        if low2.endswith(station_name) and low2 != station_name:
            break

    return fixed


def recover_source_from_blue_text(
    blue_text: list[str],
    known_destinations: list[str] | None = None,
) -> str | None:
    """Tente de récupérer la station source depuis les hyperliens bleus OCR.

    Gère :
    - "Station at Planet's L<N> Lagrange" (une ou deux lignes, "at" ou "et")
    - "Planet's L<N> Lagrange" seul en début de ligne (sans "at")
    - "Station above Planet" quand la station n'est pas déjà une destination connue

    known_destinations : liste des lieux déjà identifiés comme destinations ;
    évite de retourner un faux positif "above".
    """
    lines = [l.strip() for l in blue_text if l.strip()]
    n = len(lines)
    dests_low = {normalize_location(d).lower() for d in (known_destinations or [])}

    def _is_noise(s: str) -> bool:
        return bool(_RE_BLUE_NOISE.match(s))

    def _extract(station_raw: str, planet_raw: str, lnum: str) -> str | None:
        station_raw = station_raw.strip()
        if _is_noise(station_raw):
            return None
        if len(station_raw) >= 4:
            return normalize_location(station_raw)
        for key, code in _PLANET_CODE.items():
            if key in planet_raw.lower():
                if lnum:
                    lnum_fixed = _LNUM_MAP.get(lnum.upper(), lnum)
                    return f"{code}-L{lnum_fixed}"
                break
        return None

    above_candidates: list[str] = []   # collectés en 2ème passe

    for i, line in enumerate(lines):
        # ── Motif complet "Station at/et Planet's L<N>" ──────────────────
        m = _RE_BLUE_AT_LAGRANGE.match(line)
        if m:
            result = _extract(m.group(1), m.group(2) or "", m.group(3) or "")
            if result:
                return result

        # ── "at/et ..." seul en début de ligne ───────────────────────────
        m_cont = _RE_BLUE_AT_ONLY.match(line)
        if m_cont:
            planet_raw = m_cont.group(1) or ""
            lnum       = m_cont.group(2) or ""
            for j in range(i - 1, max(i - 6, -1), -1):
                candidate = re.sub(r'\s+(?:at|et)\s*$', '', lines[j],
                                   flags=re.IGNORECASE).strip()
                if _is_noise(candidate):
                    continue
                result = _extract(candidate, planet_raw, lnum)
                if result:
                    return result

        # ── "Planet's L<N> Lagrange" sans "at" (83C pattern) ─────────────
        m_pl = _RE_BLUE_PLANET_LPOINT.match(line)
        if m_pl:
            planet_raw = m_pl.group(1) or ""
            lnum       = m_pl.group(2) or ""
            for j in range(i - 1, max(i - 6, -1), -1):
                candidate = lines[j].strip()
                if _is_noise(candidate):
                    continue
                result = _extract(candidate, planet_raw, lnum)
                if result:
                    return result

        # ── "Station above Planet" — candidat pour 2ème passe ────────────
        m_ab = _RE_BLUE_ABOVE.match(line)
        if m_ab:
            station_raw = m_ab.group(1).strip()
            if not _is_noise(station_raw):
                above_candidates.append(station_raw)

    # ── 2ème passe : "above" non-destinations ────────────────────────────
    for station_raw in above_candidates:
        norm = normalize_location(station_raw)
        if norm.lower() not in dests_low:
            return norm

    return None


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
    """Reconstruit un MissionResult depuis une ScreenshotEntry.data.

    Applique :
    - normalize_location() sur chaque lieu (correction OCR L-point, orthographe)
    - Déduplication des objectifs identiques (même kind+commodity+location)
    - Récupération de la station source depuis blue_text si aucun Collect trouvé
    """
    try:
        from uexinfo.models.mission_result import MissionResult, ParsedObjective
        data = entry.data or {}

        # ── Construire et dédupliquer les objectifs ───────────────────────────
        seen: set[tuple[Any, ...]] = set()
        objs: list[ParsedObjective] = []
        for o in data.get("objectives", []):
            loc  = normalize_location(o.get("location") or "")
            hint = normalize_location(o.get("location_hint") or "")
            key  = (o.get("kind", ""), o.get("commodity", ""), loc)
            if key in seen:
                continue
            seen.add(key)
            objs.append(ParsedObjective(
                kind          = o.get("kind", "unknown"),
                commodity     = o.get("commodity"),
                quantity_scu  = o.get("quantity_scu"),
                location      = loc or None,
                location_hint = hint or None,
                raw           = o.get("raw", ""),
            ))

        # ── Récupérer source manquante depuis blue_text ───────────────────────
        has_collect = any(obj.kind == "collect" for obj in objs)
        if not has_collect:
            blue  = data.get("blue_text", [])
            known_dsts = [obj.location for obj in objs
                          if obj.kind == "deliver" and obj.location]
            recovered = recover_source_from_blue_text(blue, known_dsts)
            if recovered:
                objs.insert(0, ParsedObjective(
                    kind      = "collect",
                    location  = recovered,
                    raw       = f"[blue_text] {recovered}",
                ))

        # Nettoyer le titre (préfixes parasites OCR : |, ,, . en début de chaîne)
        raw_title = data.get("title", "")
        clean_title = re.sub(r'^[^A-Za-z]+', '', raw_title).strip()

        # Corriger le reward si ≈ a été lu comme un chiffre parasite en tête
        reward = int(data.get("reward", 0) or 0)
        if reward > 250_000:
            candidate = int(str(reward)[1:]) if len(str(reward)) > 4 else reward
            if 1_000 <= candidate <= 250_000:
                reward = candidate

        return MissionResult(
            title                 = clean_title,
            tab                   = data.get("tab", ""),
            reward                = reward,
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

    # Retirer les suffixes de contexte connus :
    #   "above X"    → "Seraphim Station above Crusader" → "Seraphim Station"
    #   "at X"       → "Port Tressler at MicroTech"      → "Port Tressler"
    clean = re.sub(r"\s+above\s+.*$", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\s+at\s+.*$",    "", clean, flags=re.IGNORECASE).strip()

    node_names = list(graph.nodes.keys())

    def _match(q: str) -> str | None:
        """Cherche q dans les nœuds du graphe (exact → contient → préfixe)."""
        ql = q.lower().replace("_", " ")
        # 1. Match exact
        for n in node_names:
            if n.lower() == ql:
                return n
        # 2. Contient le terme
        candidates = [n for n in node_names if ql in n.lower()]
        if candidates:
            if len(candidates) == 1:
                return candidates[0]
            if system_hint:
                sh = system_hint.lower()
                preferred = [c for c in candidates if sh in c.lower()]
                if len(preferred) == 1:
                    return preferred[0]
                if preferred:
                    candidates = preferred
            return max(candidates, key=len)
        # 3. Premier token (code court : "CRU-L4")
        short = ql.split()[0]
        if len(short) >= 3:
            for n in node_names:
                if n.lower().startswith(short):
                    return n
        return None

    # Essai avec le nom nettoyé complet
    result = _match(clean)
    if result:
        return result

    # Fallback progressif : retirer un mot à la fois par la droite
    # "Port Tressler Medical Center" → "Port Tressler Medical" → "Port Tressler"
    words = clean.split()
    for n_words in range(len(words) - 1, 0, -1):
        candidate = " ".join(words[:n_words])
        result = _match(candidate)
        if result:
            return result

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
