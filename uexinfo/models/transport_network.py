"""Modèles pour le réseau de transport interstellaire (jump points, routes QT)."""
from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    """Type de nœud dans le graphe."""
    TERMINAL = "terminal"
    STATION = "station"
    CITY = "city"
    PLANET = "planet"
    MOON = "moon"
    LAGRANGE = "lagrange"
    SYSTEM = "system"
    JUMP_POINT = "jump_point"


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
    metadata: dict = field(default_factory=dict)  # id_terminal, etc.

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, LocationNode) and self.name == other.name

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.value,
            "system": self.system,
            "coordinates": list(self.coordinates) if self.coordinates else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> LocationNode:
        return cls(
            name=d["name"],
            type=NodeType(d["type"]),
            system=d["system"],
            coordinates=tuple(d["coordinates"]) if d.get("coordinates") else None,
            metadata=d.get("metadata", {}),
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


class TransportGraph:
    """Graphe de transport de l'univers Star Citizen."""

    def __init__(self):
        self.nodes: dict[str, LocationNode] = {}
        self.edges: list[RouteEdge] = []
        self.jump_points: dict[str, JumpPoint] = {}
        self._adjacency: dict[str, list[RouteEdge]] = {}

    def add_node(self, node: LocationNode) -> None:
        """Ajoute un nœud au graphe."""
        self.nodes[node.name] = node
        if node.name not in self._adjacency:
            self._adjacency[node.name] = []

    def add_edge(self, edge: RouteEdge, bidirectional: bool = True) -> None:
        """Ajoute une arête au graphe."""
        self.edges.append(edge)
        self._adjacency.setdefault(edge.from_node, []).append(edge)

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

    def find_shortest_path(self, from_loc: str, to_loc: str,
                          max_jump_size: str = "L") -> PathResult | None:
        """Trouve le plus court chemin avec Dijkstra."""
        if from_loc not in self.nodes or to_loc not in self.nodes:
            return None

        # Dijkstra : (distance, nœud, chemin, segments)
        heap = [(0.0, from_loc, [from_loc], [])]
        visited = set()

        while heap:
            dist, current, path, segments = heapq.heappop(heap)

            if current in visited:
                continue
            visited.add(current)

            if current == to_loc:
                # Calcul de la durée totale et jump points
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

            # Explorer les voisins
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
                new_path = path + [edge.to_node]
                new_segments = segments + [{
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "distance_gm": edge.distance_gm,
                    "type": edge.edge_type.value,
                    "duration_sec": edge.duration_sec,
                    "notes": edge.notes,
                }]
                heapq.heappush(heap, (new_dist, edge.to_node, new_path, new_segments))

        return None  # Pas de chemin trouvé

    @staticmethod
    def _can_use_jump(jp_size: str, ship_size: str) -> bool:
        """Vérifie si un vaisseau peut utiliser un jump point."""
        sizes = {"S": 1, "M": 2, "L": 3}
        return sizes.get(ship_size, 3) <= sizes.get(jp_size, 3)

    def get_neighbors(self, location: str) -> list[tuple[str, float, str]]:
        """Retourne les voisins d'un nœud : [(nom, distance_gm, type)]."""
        neighbors = []
        for edge in self._adjacency.get(location, []):
            neighbors.append((edge.to_node, edge.distance_gm, edge.edge_type.value))
        return neighbors

    def to_json(self) -> dict:
        """Exporte le graphe en JSON."""
        return {
            "version": 2,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "jump_points": [jp.to_dict() for jp in self.jump_points.values()],
        }

    @classmethod
    def from_json(cls, data: dict) -> TransportGraph:
        """Importe le graphe depuis JSON."""
        graph = cls()

        # Charger les nœuds
        for n_data in data.get("nodes", []):
            node = LocationNode.from_dict(n_data)
            graph.add_node(node)

        # Charger les jump points
        for jp_data in data.get("jump_points", []):
            jp = JumpPoint.from_dict(jp_data)
            graph.jump_points[jp.name] = jp

        # Charger les arêtes (sans bidirectional pour éviter les doublons)
        for e_data in data.get("edges", []):
            edge = RouteEdge.from_dict(e_data)
            graph.edges.append(edge)
            graph._adjacency.setdefault(edge.from_node, []).append(edge)

        return graph
