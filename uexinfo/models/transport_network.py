"""Modèles pour le réseau de transport interstellaire (jump points, routes QT)."""
from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from enum import Enum

# ── Constantes de vitesse quantique ──────────────────────────────────────────
# Mesurée sur les routes UEX (SC 4.x, 2026-03) : 0.2341 ± 0.001 Gm/s
# Représente un vaisseau "standard" — ajustable par vaisseau dans /config
QD_SPEED_GM_PER_S: float = 0.2341   # Gm/s → ETA_sec = dist / QD_SPEED_GM_PER_S


def eta_from_distance(distance_gm: float,
                      qd_speed: float = QD_SPEED_GM_PER_S) -> float:
    """Retourne l'ETA en secondes pour un saut quantique (distance en Gm)."""
    if distance_gm <= 0 or qd_speed <= 0:
        return 0.0
    return distance_gm / qd_speed


def fmt_eta(distance_gm: float, qd_speed: float = QD_SPEED_GM_PER_S) -> str:
    """Formate l'ETA d'un saut QT en chaîne lisible ('2m 17s', '< 1m', '—')."""
    secs = eta_from_distance(distance_gm, qd_speed)
    if secs <= 0:
        return "—"
    if secs < 60:
        return "< 1m"
    m = int(secs // 60)
    s = int(secs % 60)
    return f"{m}m {s:02d}s" if s else f"{m}m"


class NodeType(Enum):
    """Type de nœud dans le graphe."""
    TERMINAL  = "terminal"
    STATION   = "station"
    CITY      = "city"
    PLANET    = "planet"
    MOON      = "moon"
    LAGRANGE  = "lagrange"
    SYSTEM    = "system"
    JUMP_POINT = "jump_point"
    OUTPOST   = "outpost"


class EdgeType(Enum):
    """Type d'arête (route) dans le graphe."""
    QUANTUM = "quantum"        # Vol QT dans le système
    JUMP = "jump"              # Passage par jump point
    GROUND = "ground"          # Transport terrestre
    LANDING = "landing"        # Atterrissage/décollage


@dataclass
class LocationNode:
    """Nœud du graphe : un lieu dans l'univers."""
    name: str
    type: NodeType
    system: str                # Nom du système stellaire
    coordinates: tuple[float, float, float] | None = None
    metadata: dict = field(default_factory=dict)
    # Champs v3 (base de données lieux)
    node_id: str = ""          # "type_code.uex_id"  ex: "3.11"
    nickname: str = ""         # Nom court UEX
    aliases: list = field(default_factory=list)
    type_code: int = -1        # 0=system 1=planet 2=moon 3=station 4=outpost 5=city
    uex_id: int = 0
    system_id: str = ""        # "0.68"
    parent_id: str | None = None
    is_dest: bool = False      # has_quantum_marker
    is_available: bool = True
    terminal_ids: list = field(default_factory=list)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, LocationNode) and self.name == other.name

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "type": self.type.value,
            "system": self.system,
            "coordinates": list(self.coordinates) if self.coordinates else None,
            "metadata": self.metadata,
        }
        # Champs v3 — seulement si remplis
        if self.node_id:
            d["id"]          = self.node_id
            d["nickname"]    = self.nickname
            d["aliases"]     = self.aliases
            d["type_code"]   = self.type_code
            d["uex_id"]      = self.uex_id
            d["system_id"]   = self.system_id
            d["parent_id"]   = self.parent_id
            d["is_dest"]     = self.is_dest
            d["is_available"] = self.is_available
            d["terminal_ids"] = self.terminal_ids
        return d

    @classmethod
    def from_dict(cls, d: dict) -> LocationNode:
        type_str = d.get("type", "terminal")
        try:
            node_type = NodeType(type_str)
        except ValueError:
            node_type = NodeType.TERMINAL
        return cls(
            name        = d["name"],
            type        = node_type,
            system      = d.get("system", ""),
            coordinates = tuple(d["coordinates"]) if d.get("coordinates") else None,
            metadata    = d.get("metadata", {}),
            # Champs v3
            node_id     = d.get("id", ""),
            nickname    = d.get("nickname", ""),
            aliases     = d.get("aliases", []),
            type_code   = d.get("type_code", -1),
            uex_id      = d.get("uex_id", 0),
            system_id   = d.get("system_id", ""),
            parent_id   = d.get("parent_id"),
            is_dest     = bool(d.get("is_dest", False)),
            is_available = bool(d.get("is_available", True)),
            terminal_ids = d.get("terminal_ids", []),
        )


@dataclass
class RouteEdge:
    """Arête du graphe : une route entre deux lieux."""
    from_node: str             # Nom du nœud source
    to_node: str               # Nom du nœud destination
    distance_gm: float         # Distance en gigamètres
    edge_type: EdgeType
    duration_sec: float = 0    # Temps estimé en secondes
    updated_at: float = field(default_factory=time.time)
    source: str = "manual"     # "manual", "uex", "calculated", "community"
    notes: str = ""            # Ex: "Via jump point Stanton-Pyro"

    @property
    def age_days(self) -> float:
        return (time.time() - self.updated_at) / 86400

    def to_dict(self) -> dict:
        return {
            "from": self.from_node,
            "to": self.to_node,
            "distance_gm": self.distance_gm,
            "type": self.edge_type.value,
            "duration_sec": self.duration_sec,
            "updated_at": self.updated_at,
            "source": self.source,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RouteEdge:
        return cls(
            from_node=d["from"],
            to_node=d["to"],
            distance_gm=d["distance_gm"],
            edge_type=EdgeType(d["type"]),
            duration_sec=d.get("duration_sec", 0),
            updated_at=d.get("updated_at", time.time()),
            source=d.get("source", "manual"),
            notes=d.get("notes", ""),
        )


@dataclass
class JumpPoint:
    """Jump point : passerelle entre deux systèmes."""
    name: str                  # Ex: "Stanton-Pyro Jump Point"
    from_system: str           # Ex: "Stanton"
    to_system: str             # Ex: "Pyro"
    entry_location: str        # Nom du nœud d'entrée (station proche)
    exit_location: str         # Nom du nœud de sortie
    size: str = "L"            # S, M, L (taille max vaisseau)
    is_active: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "from_system": self.from_system,
            "to_system": self.to_system,
            "entry": self.entry_location,
            "exit": self.exit_location,
            "size": self.size,
            "active": self.is_active,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> JumpPoint:
        return cls(
            name=d["name"],
            from_system=d["from_system"],
            to_system=d["to_system"],
            entry_location=d["entry"],
            exit_location=d["exit"],
            size=d.get("size", "L"),
            is_active=d.get("active", True),
            notes=d.get("notes", ""),
        )


@dataclass
class PathResult:
    """Résultat d'un calcul de chemin."""
    path: list[str]            # Liste des nœuds
    total_distance: float      # Distance totale en Gm
    total_duration: float      # Durée totale en secondes
    segments: list[dict]       # Détails de chaque segment
    jump_points: list[str]     # Jump points traversés

    @property
    def duration_formatted(self) -> str:
        """Retourne la durée au format 'XhYYm' ou 'XXm YYs'."""
        sec = int(self.total_duration)
        if sec >= 3600:
            h = sec // 3600
            m = (sec % 3600) // 60
            return f"{h}h{m:02d}m"
        elif sec >= 60:
            m = sec // 60
            s = sec % 60
            return f"{m}m {s:02d}s"
        else:
            return f"{sec}s"


def _precision_score(value: float) -> int:
    """Nombre de chiffres décimaux significatifs.

    59.0  → 0  (arrondi entier, peu précis)
    59.3  → 1
    59.25 → 2
    """
    s = f"{value:.10g}"          # retire les zéros de queue : 59.30 → "59.3"
    if "." in s:
        return len(s.split(".")[1])
    return 0


class TransportGraph:
    """Graphe de transport de l'univers Star Citizen."""

    def __init__(self):
        self.nodes: dict[str, LocationNode] = {}
        self.edges: list[RouteEdge] = []
        self.jump_points: dict[str, JumpPoint] = {}
        self._adjacency: dict[str, list[RouteEdge]] = {}
        self._unsaved_changes: int = 0
        # Métadonnées v3 préservées au chargement
        self._meta: dict = {}
        # Cache hiérarchique node_id → [noms enfants] (invalidé à chaque add_node)
        self._children_cache: dict | None = None
        # Cache résultats Dijkstra (from, to, max_jump_size) → PathResult | None
        self._path_cache: dict[tuple, "PathResult | None"] = {}

    def add_node(self, node: LocationNode) -> None:
        """Ajoute un nœud au graphe."""
        self.nodes[node.name] = node
        if node.name not in self._adjacency:
            self._adjacency[node.name] = []
        self._children_cache = None   # Invalider le cache hiérarchique
        self._path_cache.clear()      # Invalider le cache Dijkstra

    def add_edge(self, edge: RouteEdge, bidirectional: bool = True) -> None:
        """Ajoute une arête au graphe."""
        self.edges.append(edge)
        self._adjacency.setdefault(edge.from_node, []).append(edge)
        self._path_cache.clear()  # Invalider le cache Dijkstra

        if bidirectional:
            # Ajoute l'arête inverse
            reverse = RouteEdge(
                from_node=edge.to_node,
                to_node=edge.from_node,
                distance_gm=edge.distance_gm,
                edge_type=edge.edge_type,
                duration_sec=edge.duration_sec,
                updated_at=edge.updated_at,
                source=edge.source,
                notes=edge.notes,
            )
            self.edges.append(reverse)
            self._adjacency.setdefault(edge.to_node, []).append(reverse)

    def add_jump_point(self, jp: JumpPoint) -> None:
        """Ajoute un jump point (crée automatiquement les arêtes)."""
        self.jump_points[jp.name] = jp

        # Créer une arête de type JUMP
        edge = RouteEdge(
            from_node=jp.entry_location,
            to_node=jp.exit_location,
            distance_gm=0.001,  # Distance symbolique
            edge_type=EdgeType.JUMP,
            duration_sec=60,    # ~1 minute pour traverser
            source="jump_point",
            notes=f"Jump {jp.from_system} → {jp.to_system}",
        )
        self.add_edge(edge, bidirectional=True)

    def add_or_update_route(
        self,
        from_node: str,
        to_node: str,
        distance_gm: float,
        edge_type: EdgeType = EdgeType.QUANTUM,
        duration_sec: float = 0,
        source: str = "uex",
        notes: str = "",
        timestamp: float | None = None,
    ) -> bool:
        """Ajoute ou met à jour une route si les données sont plus récentes.

        Retourne True si le graphe a été modifié, False sinon.
        """
        if timestamp is None:
            timestamp = time.time()

        # Vérifier si les nœuds existent, sinon les créer (auto-découverte)
        if from_node not in self.nodes:
            self.add_node(LocationNode(
                name=from_node,
                type=NodeType.TERMINAL,  # Par défaut
                system="Unknown",
                metadata={"auto_discovered": True}
            ))
        if to_node not in self.nodes:
            self.add_node(LocationNode(
                name=to_node,
                type=NodeType.TERMINAL,
                system="Unknown",
                metadata={"auto_discovered": True}
            ))

        # Chercher si la route existe déjà (dans les deux sens)
        existing_forward = None
        existing_reverse = None

        for edge in self._adjacency.get(from_node, []):
            if edge.to_node == to_node:
                existing_forward = edge
                break

        for edge in self._adjacency.get(to_node, []):
            if edge.to_node == from_node:
                existing_reverse = edge
                break

        # Décider si on met à jour
        should_update = False

        # Priorité : manual > uex > calculated > consolidated (inféré)
        source_priority = {"manual": 3, "uex": 2, "calculated": 1, "community": 1,
                           "consolidated": 0}
        new_priority = source_priority.get(source, 1)

        if existing_forward:
            old_priority = source_priority.get(existing_forward.source, 1)
            new_prec = _precision_score(distance_gm)
            old_prec = _precision_score(existing_forward.distance_gm)
            # Mettre à jour si :
            # - Priorité supérieure (manual > uex > calculated)
            # - Même priorité ET (données plus récentes OU plus précises)
            if new_priority > old_priority or (
                new_priority == old_priority and (
                    timestamp > existing_forward.updated_at
                    or new_prec > old_prec
                )
            ):
                should_update = True
        else:
            should_update = True  # Nouvelle route

        if not should_update:
            return False  # Pas de modification

        # Supprimer les anciennes arêtes si elles existent
        if existing_forward or existing_reverse:
            self.edges = [
                e for e in self.edges
                if not (
                    (e.from_node == from_node and e.to_node == to_node) or
                    (e.from_node == to_node and e.to_node == from_node)
                )
            ]
            # Reconstruire l'adjacence
            self._adjacency.clear()
            for edge in self.edges:
                self._adjacency.setdefault(edge.from_node, []).append(edge)

        # Ajouter la nouvelle route
        new_edge = RouteEdge(
            from_node=from_node,
            to_node=to_node,
            distance_gm=distance_gm,
            edge_type=edge_type,
            duration_sec=duration_sec,
            updated_at=timestamp,
            source=source,
            notes=notes,
        )
        self.add_edge(new_edge, bidirectional=True)

        self._unsaved_changes += 1
        return True  # Graphe modifié

    def mark_saved(self) -> None:
        """Marque toutes les modifications comme sauvegardées."""
        self._unsaved_changes = 0

    @property
    def has_unsaved_changes(self) -> bool:
        """Retourne True s'il y a des modifications non sauvegardées."""
        return self._unsaved_changes > 0

    # ── Hiérarchie et propagation des distances ───────────────────────────────

    @property
    def _children_idx(self) -> dict[str, list[str]]:
        """Index node_id → [noms des enfants directs], construit lazily."""
        if self._children_cache is None:
            idx: dict[str, list[str]] = {}
            for name, node in self.nodes.items():
                if node.parent_id:
                    idx.setdefault(node.parent_id, []).append(name)
            self._children_cache = idx
        return self._children_cache

    def _descendants_of(self, node_name: str) -> set[str]:
        """Tous les descendants d'un nœud (BFS récursif via parent_id)."""
        result: set[str] = set()
        node = self.nodes.get(node_name)
        if node is None or not node.node_id:
            return result
        idx = self._children_idx
        queue = [node.node_id]
        visited: set[str] = set()
        while queue:
            nid = queue.pop()
            if nid in visited:
                continue
            visited.add(nid)
            for child_name in idx.get(nid, []):
                result.add(child_name)
                c = self.nodes.get(child_name)
                if c and c.node_id:
                    queue.append(c.node_id)
        return result

    def _node_group(self, node_name: str) -> set[str]:
        """Ensemble hiérarchique d'un nœud pour la propagation des distances.

        Algorithme :
          1. Remonter jusqu'au plus haut ancêtre qui n'est pas un système
             (type_code == 0).  Exemple : New Babbage → MicroTech (planète).
          2. Retourner cet ancêtre + TOUS ses descendants (récursif).

        Résultat pour 'New Babbage' : {MicroTech, New Babbage, HDMS-Anderson,
        Port Tressler, …} — tous ces nœuds sont à la même distance Gm des
        autres planètes/stations du système.
        """
        node = self.nodes.get(node_name)
        if node is None:
            return {node_name}

        # Trouver le plus haut ancêtre en dessous du niveau système
        top_name = node_name
        current_pid = node.parent_id
        visited_ids: set[str] = {node.node_id} if node.node_id else set()
        while current_pid and current_pid not in visited_ids:
            visited_ids.add(current_pid)
            parent = next((n for n in self.nodes.values() if n.node_id == current_pid), None)
            if parent is None or parent.type_code == 0:   # système → stop
                break
            top_name = parent.name
            current_pid = parent.parent_id

        # Groupe = ancêtre racine + tous ses descendants
        return {top_name} | self._descendants_of(top_name)

    def propagate_distances(
        self,
        from_node: str,
        to_node: str,
        distance_gm: float,
        source: str = "uex",
        timestamp: float | None = None,
        edge_type: "EdgeType | None" = None,
    ) -> int:
        """Ajoute/met à jour une route et propage aux nœuds hiérarchiquement liés.

        La route directe reçoit la source fournie.
        Les routes dérivées reçoivent source='calculated' (priorité basse) :
        elles ne remplaceront jamais une mesure directe plus précise.

        Exemple : propagate_distances('SM0-13', 'HUR-L1', 59.3)
          → met à jour SM0-13↔HUR-L1 (uex)
          → met à jour MicroTech↔HUR-L1, New Babbage↔HUR-L1,
             Port Tressler↔HUR-L1, etc. (calculated)

        Returns : nombre de routes modifiées.
        """
        if timestamp is None:
            timestamp = time.time()

        count = 0

        kw: dict = {"source": source, "timestamp": timestamp}
        if edge_type is not None:
            kw["edge_type"] = edge_type

        # Route directe (source fournie)
        if self.add_or_update_route(from_node, to_node, distance_gm, **kw):
            count += 1

        # Groupes hiérarchiques
        from_group = self._node_group(from_node)
        to_group   = self._node_group(to_node)

        kw_calc: dict = {"source": "calculated", "timestamp": timestamp}
        if edge_type is not None:
            kw_calc["edge_type"] = edge_type

        # Propager à toutes les combinaisons (sauf la directe déjà faite)
        for fn in from_group:
            for tn in to_group:
                if fn == tn:
                    continue
                if (fn == from_node and tn == to_node) or (fn == to_node and tn == from_node):
                    continue  # Déjà fait ci-dessus
                if self.add_or_update_route(fn, tn, distance_gm, **kw_calc):
                    count += 1

        return count

    def consolidate(self,
                    tolerance_gm: float = 1.0,
                    min_refs: int = 2,
                    timestamp: float | None = None) -> tuple[int, int]:
        """Consolide le graphe : infère les distances manquantes par co-localisation.

        Deux nœuds A et B sont considérés co-localisés si :
          dist(A, R) ≈ dist(B, R)  (±tolerance_gm) pour au moins `min_refs`
          nœuds de référence R communs AVEC des mesures directes (non consolidated).

        Pour chaque paire co-localisée (A, B) :
          - Si B n'a pas de mesure vers C mais A l'a → ajoute B↔C avec
            source='consolidated' (priorité 0 : tout mesure directe l'écrase).

        Les L-points (HUR-L1 ≠ HUR-L4) sont naturellement séparés : leurs
        distances aux mêmes références diffèrent → pas de faux groupement.

        Returns (routes_ajoutées, paires_co-localisées).
        """
        if timestamp is None:
            timestamp = time.time()

        # ── 1. Construire la carte des distances directes (hors consolidated) ──
        # dist_direct[A][B] = distance_gm (mesure non inférée)
        dist_direct: dict[str, dict[str, float]] = {}
        for node_name, adj_edges in self._adjacency.items():
            for edge in adj_edges:
                if edge.source != "consolidated":
                    dist_direct.setdefault(node_name, {})[edge.to_node] = edge.distance_gm

        node_names = list(self.nodes.keys())
        n = len(node_names)

        # ── 2. Trouver les paires co-localisées ───────────────────────────────
        coloc_pairs: list[tuple[str, str]] = []
        for i in range(n):
            a = node_names[i]
            refs_a = dist_direct.get(a, {})
            for j in range(i + 1, n):
                b = node_names[j]
                refs_b = dist_direct.get(b, {})
                # Voisins communs avec mesure directe dans les deux sens
                common = set(refs_a.keys()) & set(refs_b.keys())
                if len(common) < min_refs:
                    continue
                matching = sum(
                    1 for r in common
                    if abs(refs_a[r] - refs_b[r]) <= tolerance_gm
                )
                if matching >= min_refs:
                    coloc_pairs.append((a, b))

        # ── 3. Union-Find sur les paires co-localisées ────────────────────────
        parent = {n: n for n in node_names}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: str, y: str) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for a, b in coloc_pairs:
            union(a, b)

        # ── 4. Groupes → membres ──────────────────────────────────────────────
        from collections import defaultdict as _dd
        groups: dict[str, list[str]] = _dd(list)
        for name in node_names:
            groups[find(name)].append(name)

        # Ne garder que les groupes de taille ≥ 2
        coloc_groups = {rep: members for rep, members in groups.items() if len(members) >= 2}

        # ── 5. Pour chaque paire de groupes : meilleure distance connue ───────
        _PRIO = {"manual": 4, "player": 3, "uex": 2, "calculated": 1,
                 "community": 1, "consolidated": 0}
        # group_pair → (distance, source, ts)
        group_dist: dict[tuple[str, str], tuple[float, str, float]] = {}

        for node_name, adj_edges in self._adjacency.items():
            ga = find(node_name)
            for edge in adj_edges:
                gb = find(edge.to_node)
                if ga == gb:
                    continue
                key = (min(ga, gb), max(ga, gb))
                new_p = _PRIO.get(edge.source, 1)
                cur = group_dist.get(key)
                if cur is None:
                    group_dist[key] = (edge.distance_gm, edge.source, edge.updated_at)
                else:
                    cur_p = _PRIO.get(cur[1], 1)
                    if new_p > cur_p or (new_p == cur_p and edge.updated_at > cur[2]):
                        group_dist[key] = (edge.distance_gm, edge.source, edge.updated_at)

        # ── 6. Propager aux paires intra-groupe manquantes ────────────────────
        added = 0
        for (ga, gb), (dist, _src, _ts) in group_dist.items():
            members_a = groups[ga]   # inclut groupes de taille 1
            members_b = groups[gb]
            for na in members_a:
                for nb in members_b:
                    if na == nb:
                        continue
                    # Ne pas écraser une mesure directe (non consolidated)
                    existing = None
                    for e in self._adjacency.get(na, []):
                        if e.to_node == nb:
                            existing = e
                            break
                    if existing and existing.source != "consolidated":
                        continue
                    if self.add_or_update_route(
                        na, nb, dist,
                        edge_type=EdgeType.QUANTUM,
                        source="consolidated",
                        timestamp=timestamp,
                    ):
                        added += 1

        return added, len(coloc_pairs)

    def find_shortest_path(self, from_loc: str, to_loc: str,
                          max_jump_size: str = "L") -> PathResult | None:
        """Trouve le plus court chemin avec Dijkstra (résultat mis en cache)."""
        cache_key = (from_loc, to_loc, max_jump_size)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        result = self._dijkstra(from_loc, to_loc, max_jump_size)
        self._path_cache[cache_key] = result
        return result

    def _dijkstra(self, from_loc: str, to_loc: str,
                  max_jump_size: str = "L") -> PathResult | None:
        """Dijkstra interne — utiliser find_shortest_path (avec cache)."""
        if from_loc not in self.nodes or to_loc not in self.nodes:
            return None

        # Utilise un dict parent pour éviter de copier path/segments à chaque étape.
        # heap : (distance, compteur_tie_break, nœud)
        counter = 0
        heap: list[tuple[float, int, str]] = [(0.0, counter, from_loc)]
        best_dist: dict[str, float] = {from_loc: 0.0}
        # parent[node] = (parent_node, edge_dict)
        parent: dict[str, tuple[str, dict] | None] = {from_loc: None}
        visited: set[str] = set()

        while heap:
            dist, _, current = heapq.heappop(heap)

            if current in visited:
                continue
            visited.add(current)

            if current == to_loc:
                # Reconstruire le chemin depuis les parents
                path: list[str] = []
                segments: list[dict] = []
                node = to_loc
                while parent[node] is not None:
                    prev_node, edge_dict = parent[node]  # type: ignore[misc]
                    path.append(node)
                    segments.append(edge_dict)
                    node = prev_node
                path.append(from_loc)
                path.reverse()
                segments.reverse()

                total_duration = sum(s["duration_sec"] for s in segments)
                jump_points = [
                    s["notes"] for s in segments
                    if s["type"] == "jump"
                ]
                return PathResult(
                    path=path,
                    total_distance=dist,
                    total_duration=total_duration,
                    segments=segments,
                    jump_points=jump_points,
                )

            for edge in self._adjacency.get(current, []):
                if edge.to_node in visited:
                    continue

                # Filtrer par taille de jump point si applicable
                if edge.edge_type == EdgeType.JUMP:
                    jp_name = edge.notes.split("→")[0].strip().replace("Jump ", "")
                    jp = self.jump_points.get(jp_name)
                    if jp and not self._can_use_jump(jp.size, max_jump_size):
                        continue

                new_dist = dist + edge.distance_gm
                if edge.to_node in best_dist and new_dist >= best_dist[edge.to_node]:
                    continue

                best_dist[edge.to_node] = new_dist
                parent[edge.to_node] = (current, {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "distance_gm": edge.distance_gm,
                    "type": edge.edge_type.value,
                    "duration_sec": edge.duration_sec,
                    "notes": edge.notes,
                })
                counter += 1
                heapq.heappush(heap, (new_dist, counter, edge.to_node))

        return None  # Pas de chemin trouvé

    @staticmethod
    def _can_use_jump(jp_size: str, ship_size: str) -> bool:
        """Vérifie si un vaisseau peut utiliser un jump point."""
        sizes = {"S": 1, "M": 2, "L": 3}
        return sizes.get(ship_size, 3) <= sizes.get(jp_size, 3)

    def find_all_distances(self, from_loc: str) -> dict[str, float]:
        """Dijkstra complet depuis from_loc — retourne {node_name: distance_gm}.

        Contrairement à find_shortest_path, ne s'arrête pas sur une cible :
        tous les nœuds atteignables sont couverts en un seul passage.
        """
        if from_loc not in self.nodes:
            return {}

        heap: list[tuple[float, str]] = [(0.0, from_loc)]
        best: dict[str, float] = {from_loc: 0.0}
        visited: set[str] = set()

        while heap:
            d, current = heapq.heappop(heap)
            if current in visited:
                continue
            visited.add(current)
            for edge in self._adjacency.get(current, []):
                nd = d + edge.distance_gm
                if edge.to_node not in best or nd < best[edge.to_node]:
                    best[edge.to_node] = nd
                    heapq.heappush(heap, (nd, edge.to_node))

        return best

    def get_nodes_in_system(self, system: str) -> list[LocationNode]:
        """Retourne tous les nœuds d'un système stellaire donné."""
        sl = system.lower()
        return [n for n in self.nodes.values() if n.system.lower() == sl]

    def get_neighbors(self, location: str) -> list[tuple[str, float, str]]:
        """Retourne les voisins d'un nœud : [(nom, distance_gm, type)]."""
        neighbors = []
        for edge in self._adjacency.get(location, []):
            neighbors.append((edge.to_node, edge.distance_gm, edge.edge_type.value))
        return neighbors

    def find_node_by_alias(self, query: str) -> LocationNode | None:
        """Cherche un nœud par name, nickname ou alias (insensible à la casse)."""
        q = query.lower().strip()
        # Correspondance exacte sur le name
        if query in self.nodes:
            return self.nodes[query]
        # Correspondance insensible à la casse + nickname/aliases
        for node in self.nodes.values():
            if node.name.lower() == q:
                return node
            if node.nickname.lower() == q:
                return node
            if any(a.lower() == q for a in node.aliases):
                return node
        return None

    def to_json(self) -> dict:
        """Exporte le graphe en JSON (préserve les métadonnées v3)."""
        out = dict(self._meta)   # préserve version, generated_at, type_codes
        out["version"]     = self._meta.get("version", 3)
        out["nodes"]       = [n.to_dict() for n in self.nodes.values()]
        out["edges"]       = [e.to_dict() for e in self.edges]
        out["jump_points"] = [jp.to_dict() for jp in self.jump_points.values()]
        return out

    @classmethod
    def from_json(cls, data: dict) -> TransportGraph:
        """Importe le graphe depuis JSON (v2 et v3)."""
        graph = cls()

        # Préserver les métadonnées v3
        graph._meta = {
            k: v for k, v in data.items()
            if k not in ("nodes", "edges", "jump_points")
        }

        for n_data in data.get("nodes", []):
            node = LocationNode.from_dict(n_data)
            graph.add_node(node)

        for jp_data in data.get("jump_points", []):
            jp = JumpPoint.from_dict(jp_data)
            graph.jump_points[jp.name] = jp

        for e_data in data.get("edges", []):
            edge = RouteEdge.from_dict(e_data)
            graph.edges.append(edge)
            graph._adjacency.setdefault(edge.from_node, []).append(edge)

        return graph
