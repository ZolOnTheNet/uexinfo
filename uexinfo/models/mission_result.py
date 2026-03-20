"""Modèle résultat de scan mission (écran Contrats)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedObjective:
    """Objectif de mission parsé structurellement depuis l'OCR."""
    kind: str                      # "collect" | "deliver" | "unknown"
    commodity: str | None = None   # ex. "Quartz"
    quantity_scu: int | None = None  # total SCU extrait de "0/53 SCU" → 53
    location: str | None = None    # terminal de collecte ou destination
    location_hint: str | None = None  # "above Crusader", "above ArcCorp"
    raw: str = ""                  # texte brut original (debug / correction)

    @property
    def full_location(self) -> str:
        """Localisation complète : 'Seraphim Station above Crusader'."""
        if self.location and self.location_hint:
            return f"{self.location} above {self.location_hint}"
        return self.location or ""


@dataclass
class MissionResult:
    """Données extraites d'un screenshot de l'écran Contrats."""
    title: str = ""
    tab: str = ""                    # OFFERS | ACCEPTED | HISTORY
    reward: int = 0                  # aUEC
    contract_availability: str = ""
    contracted_by: str = ""
    details: str = ""                # texte complet zone Details
    objectives: list[str] = field(default_factory=list)           # lignes brutes
    parsed_objectives: list[ParsedObjective] = field(default_factory=list)  # structuré
    blue_text: list[str] = field(default_factory=list)  # liens importants (lieux, menaces)
    mission_list: list[tuple[str, int]] = field(default_factory=list)  # (titre, récompense k)
    source: str = "ocr"
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def all_sources(self) -> list[str]:
        """Tous les lieux de collecte (Collect)."""
        return [o.location for o in self.parsed_objectives
                if o.kind == "collect" and o.location]

    @property
    def all_destinations(self) -> list[str]:
        """Toutes les destinations de livraison (Deliver)."""
        return [o.location for o in self.parsed_objectives
                if o.kind == "deliver" and o.location]

    @property
    def total_scu(self) -> float:
        """SCU total des objectifs Deliver."""
        return sum(o.quantity_scu for o in self.parsed_objectives
                   if o.kind == "deliver" and o.quantity_scu)

    def to_mission_kwargs(self) -> dict:
        """Retourne les kwargs pour créer un Mission depuis ce MissionResult."""
        from uexinfo.models.mission import MissionObjective as MO
        objs = []
        for o in self.parsed_objectives:
            if o.kind in ("collect", "deliver"):
                objs.append(MO(
                    commodity=o.commodity,
                    source=o.location if o.kind == "collect" else None,
                    destination=o.location if o.kind == "deliver" else None,
                    quantity_scu=float(o.quantity_scu) if o.quantity_scu else None,
                ))
        # Fusionner collect + deliver par commodité quand possible
        merged = _merge_objectives(objs)
        return {
            "name": self.title,
            "reward_uec": self.reward,
            "objectives": merged,
            "source_raw": "ocr",
        }


def _merge_objectives(objs) -> list:
    """Fusionne les objectifs Collect et Deliver de même commodité."""
    from uexinfo.models.mission import MissionObjective as MO
    # Regrouper par commodité
    by_commodity: dict[str | None, list] = {}
    for o in objs:
        key = (o.commodity or "").lower()
        by_commodity.setdefault(key, []).append(o)

    result = []
    for items in by_commodity.values():
        sources = [o.source for o in items if o.source]
        dests   = [o.destination for o in items if o.destination]
        qty     = sum(o.quantity_scu for o in items if o.quantity_scu)
        # Prendre la première commodité non-None
        commodity = next((o.commodity for o in items if o.commodity), None)
        if len(dests) <= 1:
            result.append(MO(
                commodity=commodity,
                source=sources[0] if sources else None,
                destination=dests[0] if dests else None,
                quantity_scu=qty or None,
            ))
        else:
            # Plusieurs destinations : un objectif par destination
            for dest in dests:
                result.append(MO(
                    commodity=commodity,
                    source=sources[0] if sources else None,
                    destination=dest,
                    quantity_scu=None,  # SCU par destination inconnu sans info précise
                ))
    return result
