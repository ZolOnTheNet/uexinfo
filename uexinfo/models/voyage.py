"""Modèle de données pour les voyages Star Citizen."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Voyage:
    """Un voyage = ensemble de missions formant un itinéraire global."""

    id: int
    name: str                        # Défaut : "trajet-{id}"
    mission_ids: list[int] = field(default_factory=list)  # IDs ordonnés (catalogue)
    departure: str | None = None     # Point de départ (défaut : position joueur)
    arrival: str | None = None       # Point d'arrivée désiré
    created_at: float = field(default_factory=time.time)
    session_id: int = 0              # Session lors de la création
    notes: str | None = None

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "mission_ids": self.mission_ids,
            "departure":   self.departure,
            "arrival":     self.arrival,
            "created_at":  self.created_at,
            "session_id":  self.session_id,
            "notes":       self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Voyage":
        return cls(
            id=d.get("id", 0),
            name=d.get("name", ""),
            mission_ids=d.get("mission_ids", []),
            departure=d.get("departure"),
            arrival=d.get("arrival"),
            created_at=d.get("created_at", time.time()),
            session_id=d.get("session_id", 0),
            notes=d.get("notes"),
        )

    @property
    def default_name(self) -> str:
        return f"trajet-{self.id}"
