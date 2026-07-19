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
class Moon:
    id: int
    name: str
    code: str = ""
    id_star_system: int = 0
    star_system_name: str = ""
    id_planet: int = 0
    planet_name: str = ""
    id_orbit: int = 0
    orbit_name: str = ""
    id_faction: int = 0
    faction_name: str = ""
    is_available: int = 1


@dataclass
class Orbit:
    """Corps orbitaux, points de Lagrange, jump points."""
    id: int
    name: str
    code: str = ""
    id_star_system: int = 0
    star_system_name: str = ""
    is_lagrange: int = 0
    is_jump_point: int = 0
    is_asteroid: int = 0
    is_planet: int = 0
    is_star: int = 0
    is_man_made: int = 0
    is_available: int = 1


@dataclass
class SpaceStation:
    id: int
    name: str
    nickname: str = ""
    id_star_system: int = 0
    star_system_name: str = ""
    id_planet: int = 0
    planet_name: str = ""
    id_orbit: int = 0
    orbit_name: str = ""
    id_moon: int = 0
    id_faction: int = 0
    faction_name: str = ""
    is_available: int = 1
    is_landable: int = 0
    is_decommissioned: int = 0
    is_lagrange: int = 0
    is_jump_point: int = 0
    has_trade_terminal: int = 0
    has_habitation: int = 0
    has_refinery: int = 0
    has_cargo_center: int = 0
    has_clinic: int = 0
    has_food: int = 0
    has_shops: int = 0
    has_refuel: int = 0
    has_repair: int = 0
    has_gravity: int = 0
    pad_types: str = ""


@dataclass
class Outpost:
    id: int
    name: str
    nickname: str = ""
    id_star_system: int = 0
    star_system_name: str = ""
    id_planet: int = 0
    planet_name: str = ""
    id_orbit: int = 0
    orbit_name: str = ""
    id_moon: int = 0
    moon_name: str = ""
    id_faction: int = 0
    faction_name: str = ""
    is_available: int = 1
    is_landable: int = 0
    is_decommissioned: int = 0
    has_trade_terminal: int = 0
    has_habitation: int = 0
    has_refinery: int = 0
    has_cargo_center: int = 0
    has_clinic: int = 0
    has_food: int = 0
    has_shops: int = 0
    has_refuel: int = 0
    has_repair: int = 0
    has_gravity: int = 0
    pad_types: str = ""


@dataclass
class City:
    id: int
    name: str
    code: str = ""
    id_star_system: int = 0
    star_system_name: str = ""
    id_planet: int = 0
    planet_name: str = ""
    id_orbit: int = 0
    orbit_name: str = ""
    id_moon: int = 0
    moon_name: str = ""
    id_faction: int = 0
    faction_name: str = ""
    is_available: int = 1
    has_trade_terminal: int = 0
    has_habitation: int = 0
    has_refinery: int = 0
    has_clinic: int = 0
    has_food: int = 0
    has_shops: int = 0
    has_refuel: int = 0
    has_repair: int = 0
    wiki: str = ""


@dataclass
class Faction:
    id: int
    name: str
    wiki: str = ""
    is_piracy: int = 0
    is_bounty_hunting: int = 0
    ids_star_systems: str = ""
    ids_factions_friendly: str = ""
    ids_factions_hostile: str = ""


@dataclass
class Terminal:
    id: int
    name: str
    code: str = ""
    type: str = ""
    id_star_system: int = 0
    star_system_name: str = ""
    id_planet: int = 0
    planet_name: str = ""
    id_orbit: int = 0
    orbit_name: str = ""
    id_moon: int = 0
    id_city: int = 0
    city_name: str = ""
    id_space_station: int = 0
    space_station_name: str = ""
    id_outpost: int = 0
    id_poi: int = 0
    id_faction: int = 0
    max_container_size: int = 0
    is_available: int = 1
    is_player_owned: int = 0
    has_loading_dock: int = 0
    has_docking_port: int = 0
    has_freight_elevator: int = 0
    is_refinery: int = 0
    # Champs service (parsés depuis l'API)
    is_auto_load: int = 0
    is_habitation: int = 0
    is_medical: int = 0
    is_food: int = 0
    is_repair: int = 0
    is_refuel: int = 0
    is_cargo_center: int = 0
    is_shop_vehicle: int = 0
    # Métadonnées de site
    faction_name: str = ""
    company_name: str = ""
    displayname: str = ""
    nickname: str = ""

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
class Vehicle:
    id: int
    name: str           # court : "Cutlass Black"
    name_full: str      # complet : "Drake Cutlass Black"
    slug: str = ""
    id_company: int = 0
    manufacturer: str = ""
    scu: int = 0
    crew: str = "1"
    mass: int = 0
    width: float = 0.0
    height: float = 0.0
    length: float = 0.0
    fuel_quantum: int = 0
    fuel_hydrogen: int = 0
    pad_type: str = ""
    container_sizes: str = ""   # ex: "1,2,4,8,16,32"
    is_cargo: int = 0
    is_mining: int = 0
    is_salvage: int = 0
    is_military: int = 0
    is_concept: int = 0
    is_ground_vehicle: int = 0
    is_spaceship: int = 0
    is_exploration: int = 0
    is_medical: int = 0
    is_refinery: int = 0
    is_refuel: int = 0
    is_repair: int = 0
    is_scanning: int = 0
    is_racing: int = 0
    is_passenger: int = 0
    is_quantum_capable: int = 0
    url_photo: str = ""
    url_store: str = ""


@dataclass
class Commodity:
    id: int
    name: str
    code: str = ""
    kind: str = ""
    id_parent: int = 0
    weight_scu: float = 1.0
    price_buy: float = 0.0
    price_sell: float = 0.0
    is_buyable: int = 0
    is_sellable: int = 0
    is_illegal: int = 0
    is_available: int = 1
    is_refinable: int = 0
    is_extractable: int = 0
    is_harvestable: int = 0
    is_mineral: int = 0
    is_raw: int = 0
    is_refined: int = 0
    is_volatile_qt: int = 0
    is_volatile_time: int = 0
    is_inert: int = 0
    is_explosive: int = 0
    is_fuel: int = 0
    wiki: str = ""
