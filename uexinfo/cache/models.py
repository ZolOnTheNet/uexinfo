"""Modèles de données (dataclasses) pour les entités UEX."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StarSystem:
    id: int
    name: str
    code: str = ""
    is_available: int = 1


@dataclass
class Planet:
    id: int
    name: str
    id_star_system: int = 0
    star_system_name: str = ""


@dataclass
class Terminal:
    id: int
    name: str
    code: str = ""
    type: str = ""
    id_star_system: int = 0
    star_system_name: str = ""
    planet_name: str = ""
    orbit_name: str = ""
    city_name: str = ""
    space_station_name: str = ""
    max_container_size: int = 0
    is_available: int = 1
    is_player_owned: int = 0
    has_loading_dock: int = 0
    has_docking_port: int = 0
    has_freight_elevator: int = 0
    is_refinery: int = 0

    @property
    def location(self) -> str:
        parts = [p for p in [
            self.star_system_name,
            self.planet_name,
            self.orbit_name,
            self.space_station_name or self.city_name,
        ] if p]
        return " / ".join(parts)

    @property
    def display_name(self) -> str:
        loc = self.location
        return f"{self.name}  [{loc}]" if loc else self.name


@dataclass
class Commodity:
    id: int
    name: str
    code: str = ""
    kind: str = ""
    weight_scu: float = 1.0
    price_buy: float = 0.0
    price_sell: float = 0.0
    is_buyable: int = 0
    is_sellable: int = 0
    is_illegal: int = 0
    is_available: int = 1
    is_refinable: int = 0
    is_extractable: int = 0
