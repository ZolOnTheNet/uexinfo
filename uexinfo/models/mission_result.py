"""Modèle résultat de scan mission (écran Contrats)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MissionObjective:
    text: str
    is_primary: bool = True


@dataclass
class MissionResult:
    """Données extraites d'un screenshot de l'écran Contrats."""
    title: str = ""
    tab: str = ""                    # OFFERS | ACCEPTED | HISTORY
    reward: int = 0                  # aUEC
    contract_availability: str = ""
    contracted_by: str = ""
    details: str = ""                # texte complet zone Details
    objectives: list[str] = field(default_factory=list)
    blue_text: list[str] = field(default_factory=list)  # liens importants (lieux, menaces)
    mission_list: list[tuple[str, int]] = field(default_factory=list)  # (titre, récompense k)
    source: str = "ocr"
    timestamp: datetime = field(default_factory=datetime.now)
