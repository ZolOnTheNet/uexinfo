"""Modèle de données pour les voyages Star Citizen."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class VoyageStep:
    """Une étape dans un voyage (groupe de missions depuis un même lieu)."""

    number: int                           # Numéro d'étape (1, 2, 3…)
    departure: str | None = None          # Lieu de départ (déduit ou explicite)
    mission_ids: list[int] = field(default_factory=list)
    empty_display_count: int = 0          # Compteur affichages vide (auto-purge à 3)

    def to_dict(self) -> dict:
        return {
            "number":              self.number,
            "departure":           self.departure,
            "mission_ids":         self.mission_ids,
            "empty_display_count": self.empty_display_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VoyageStep":
        return cls(
            number=d.get("number", 1),
            departure=d.get("departure"),
            mission_ids=d.get("mission_ids", []),
            empty_display_count=d.get("empty_display_count", 0),
        )


@dataclass
class Voyage:
    """Un voyage = ensemble de missions formant un itinéraire global."""

    id: int
    name: str                         # Défaut : "trajet-{id}"
    steps: list[VoyageStep] = field(default_factory=list)   # Étapes ordonnées
    # Compatibilité — mission_ids à plat (si pas d'étapes)
    mission_ids: list[int] = field(default_factory=list)
    departure: str | None = None      # Point de départ global
    arrival: str | None = None        # Point d'arrivée désiré
    created_at: float = field(default_factory=time.time)
    session_id: int = 0
    notes: str | None = None
    loop: bool = False                # --boucle : retour au départ inclus

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "steps":       [s.to_dict() for s in self.steps],
            "mission_ids": self.mission_ids,
            "departure":   self.departure,
            "arrival":     self.arrival,
            "created_at":  self.created_at,
            "session_id":  self.session_id,
            "notes":       self.notes,
            "loop":        self.loop,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Voyage":
        steps_data = d.get("steps", [])
        mission_ids = d.get("mission_ids", [])

        # Migration : ancien format sans steps → créer étape 1
        if not steps_data and mission_ids:
            steps = [VoyageStep(number=1, mission_ids=list(mission_ids))]
        else:
            steps = [VoyageStep.from_dict(s) for s in steps_data]

        return cls(
            id=d.get("id", 0),
            name=d.get("name", ""),
            steps=steps,
            mission_ids=mission_ids,
            departure=d.get("departure"),
            arrival=d.get("arrival"),
            created_at=d.get("created_at", time.time()),
            session_id=d.get("session_id", 0),
            notes=d.get("notes"),
            loop=d.get("loop", False),
        )

    @property
    def default_name(self) -> str:
        return f"trajet-{self.id}"

    @property
    def all_mission_ids(self) -> list[int]:
        """IDs de toutes les missions dans toutes les étapes."""
        if self.steps:
            seen = set()
            result = []
            for step in self.steps:
                for mid in step.mission_ids:
                    if mid not in seen:
                        seen.add(mid)
                        result.append(mid)
            return result
        return list(self.mission_ids)

    def get_step(self, number: int) -> VoyageStep | None:
        """Retourne l'étape numéro N, ou None."""
        return next((s for s in self.steps if s.number == number), None)

    def get_or_create_step(self, number: int, departure: str | None = None) -> VoyageStep:
        """Retourne l'étape N, la crée si elle n'existe pas."""
        step = self.get_step(number)
        if step is None:
            step = VoyageStep(number=number, departure=departure)
            self.steps.append(step)
            self.steps.sort(key=lambda s: s.number)
        return step

    def next_step_number(self) -> int:
        """Retourne le numéro de la prochaine étape à créer."""
        if not self.steps:
            return 1
        return max(s.number for s in self.steps) + 1
