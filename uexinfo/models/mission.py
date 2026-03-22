"""Modèle de données pour les missions Star Citizen."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MissionObjective:
    """Un objectif dans une mission (livraison, escorte, etc.)."""

    commodity: str | None = None       # Commodité à transporter
    source: str | None = None          # Lieu de départ (brut ou résolu)
    destination: str | None = None     # Lieu d'arrivée (brut ou résolu)
    quantity_scu: float | None = None  # Volume SCU
    time_cost: str | None = None       # Pénalité : "tdd", "shop", texte libre
    notes: str | None = None           # Texte libre (type élimination, investigation…)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> "MissionObjective":
        valid = {f for f in ("commodity", "source", "destination",
                              "quantity_scu", "time_cost", "notes")}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class Mission:
    """Une mission à accomplir."""

    id: int
    name: str
    reward_uec: int = 0
    objectives: list[MissionObjective] = field(default_factory=list)
    is_selected: bool = True       # Incluse dans le calcul du voyage
    source_raw: str | None = None  # Origine (fichier scan, clipboard, manual)
    notes: str | None = None
    scanned_at: float | None = None  # Unix timestamp du scan/import

    @property
    def all_sources(self) -> list[str]:
        return list(dict.fromkeys(o.source for o in self.objectives if o.source))

    @property
    def all_destinations(self) -> list[str]:
        return list(dict.fromkeys(o.destination for o in self.objectives if o.destination))

    @property
    def total_scu(self) -> float:
        return sum(o.quantity_scu or 0 for o in self.objectives)

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "reward_uec":  self.reward_uec,
            "objectives":  [o.to_dict() for o in self.objectives],
            "is_selected": self.is_selected,
            "source_raw":  self.source_raw,
            "notes":       self.notes,
            "scanned_at":  self.scanned_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Mission":
        objs = [MissionObjective.from_dict(o) for o in d.get("objectives", [])]
        return cls(
            id=d.get("id", 0),
            name=d.get("name", ""),
            reward_uec=d.get("reward_uec", 0),
            objectives=objs,
            is_selected=d.get("is_selected", True),
            source_raw=d.get("source_raw"),
            notes=d.get("notes"),
            scanned_at=d.get("scanned_at"),
        )
