"""Modèle de données pour les missions Star Citizen."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MissionObjective:
    """Un objectif dans une mission (livraison, escorte, etc.)."""

    commodity: str | None = None       # Commodité à transporter
    source: str | None = None          # Lieu de départ : nom du nœud, ou texte brut à préciser
    destination: str | None = None     # Lieu d'arrivée : nom du nœud, ou texte brut à préciser
    quantity_scu: float | None = None  # Volume SCU
    time_cost: str | None = None       # Pénalité : "tdd", "shop", texte libre
    notes: str | None = None           # Texte libre (type élimination, investigation…)
    # Référence du lieu (« node:<nom> », décision D11), posée une seule fois à l'enregistrement ;
    # None = texte pas encore relié à un lieu (« à préciser »), jamais deviné ensuite.
    source_ref: str | None = None
    destination_ref: str | None = None

    def to_dict(self) -> dict:
        """Dictionnaire pour le JSON, sans les champs vides."""
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> "MissionObjective":
        """Recrée l'objectif depuis le JSON, en ignorant les clés inconnues."""
        valid = {f for f in ("commodity", "source", "destination",
                              "quantity_scu", "time_cost", "notes",
                              "source_ref", "destination_ref")}
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
        """Lieux de départ des objectifs, sans doublon, dans l'ordre."""
        return list(dict.fromkeys(o.source for o in self.objectives if o.source))

    @property
    def all_destinations(self) -> list[str]:
        """Lieux d'arrivée des objectifs, sans doublon, dans l'ordre."""
        return list(dict.fromkeys(o.destination for o in self.objectives if o.destination))

    @property
    def unresolved_places(self) -> list[str]:
        """Lieux écrits mais pas encore reliés à un lieu du graphe (à préciser), sans doublon."""
        out: list[str] = []
        for o in self.objectives:
            for text, r in ((o.source, o.source_ref), (o.destination, o.destination_ref)):
                if text and not r and text not in out:
                    out.append(text)
        return out

    def place_refs(self) -> dict[str, str]:
        """Nom affiché → référence, pour chaque lieu relié de la mission."""
        refs: dict[str, str] = {}
        for o in self.objectives:
            for text, r in ((o.source, o.source_ref), (o.destination, o.destination_ref)):
                if text and r:
                    refs[text] = r
        return refs

    @property
    def total_scu(self) -> float:
        """Volume total à transporter, en SCU."""
        return sum(o.quantity_scu or 0 for o in self.objectives)

    def to_dict(self) -> dict:
        """Dictionnaire pour le JSON (`missions.json`)."""
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
        """Recrée la mission depuis le JSON."""
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
