"""Gestion du cache local — données statiques UEX."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import appdirs
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from uexinfo.cache.models import (
    City, Commodity, Faction, Moon, Orbit, Outpost, Planet, SpaceStation,
    StarSystem, Terminal, Vehicle,
)
from uexinfo.models.transport_network import TransportGraph

APP_NAME = "uexinfo"
DATA_DIR = Path(appdirs.user_data_dir(APP_NAME))
PACKAGE_DIR = Path(__file__).parent.parent  # uexinfo/

_STATIC_FILES = {
    "commodities": "commodities.json",
    "terminals": "terminals.json",
    "star_systems": "star_systems.json",
    "planets": "planets.json",
    "vehicles": "vehicles.json",
    "moons": "moons.json",
    "orbits": "orbits.json",
    "space_stations": "space_stations.json",
    "outposts": "outposts.json",
    "cities": "cities.json",
    "factions": "factions.json",
}

_console = Console()


class CacheManager:
    def __init__(self, ttl_static: int = 86400):
        self.ttl_static = ttl_static
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.commodities: list[Commodity] = []
        self.terminals: list[Terminal] = []
        self.star_systems: list[StarSystem] = []
        self.planets: list[Planet] = []
        self.vehicles: list[Vehicle] = []
        self.moons: list[Moon] = []
        self.orbits: list[Orbit] = []
        self.space_stations: list[SpaceStation] = []
        self.outposts: list[Outpost] = []
        self.cities: list[City] = []
        self.factions: list[Faction] = []
        self.transport_graph: TransportGraph = TransportGraph()

    @property
    def is_loaded(self) -> bool:
        return bool(self.commodities or self.terminals)

    def load(self, force: bool = False) -> None:
        """Charge les données statiques, télécharge si expiré."""
        # Charger le graphe de transport (toujours depuis le code source)
        self.load_transport_graph()

        if not force and not self._is_expired("commodities"):
            self._load_from_disk()
            return
        try:
            self._download()
        except Exception as e:
            if self._has_disk_data():
                _console.print(f"[yellow]⚠ Téléchargement échoué ({e}) — données en cache utilisées[/yellow]")
                self._load_from_disk()
            else:
                raise

    def invalidate(self) -> None:
        """Supprime les fichiers de cache statique — force rechargement UEX au prochain accès."""
        for fname in _STATIC_FILES.values():
            path = DATA_DIR / fname
            if path.exists():
                path.unlink()
        self.commodities = []
        self.terminals   = []
        self.star_systems = []
        self.planets     = []
        self.vehicles    = []
        self.moons          = []
        self.orbits         = []
        self.space_stations = []
        self.outposts       = []
        self.cities         = []
        self.factions       = []

    def _is_expired(self, key: str) -> bool:
        path = DATA_DIR / _STATIC_FILES[key]
        if not path.exists():
            return True
        return (time.time() - path.stat().st_mtime) > self.ttl_static

    def _has_disk_data(self) -> bool:
        return any((DATA_DIR / f).exists() for f in _STATIC_FILES.values())

    def _download(self) -> None:
        from uexinfo.api.uex_client import UEXClient
        client = UEXClient()

        steps = [
            ("commodities", "Commodités",  client.get_commodities,       self._parse_commodity),
            ("terminals",   "Terminaux",   client.get_terminals,         self._parse_terminal),
            ("star_systems","Systèmes",    client.get_star_systems,      self._parse_star_system),
            ("planets",     "Planètes",    client.get_planets,           self._parse_planet),
            ("vehicles",    "Vaisseaux",   client.get_vehicles,          None),  # handled spécialement
            ("moons",          "Lunes",             client.get_moons,          self._parse_moon),
            ("orbits",         "Orbites",           client.get_orbits,         self._parse_orbit),
            ("space_stations", "Stations",          client.get_space_stations, self._parse_space_station),
            ("outposts",       "Avant-postes",      client.get_outposts,       self._parse_outpost),
            ("cities",         "Villes",            client.get_cities,         self._parse_city),
            ("factions",       "Factions",          client.get_factions,       self._parse_faction),
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description:<20}"),
            BarColumn(bar_width=30),
            TextColumn("[dim]{task.fields[count]}"),
            console=_console,
            transient=True,
        ) as progress:
            task = progress.add_task("Mise à jour cache UEX", total=len(steps), count="")
            for key, label, fetch_fn, parse_fn in steps:
                progress.update(task, description=label)
                # Champs secondaires (géographie fine + factions) : un échec ne doit
                # pas interrompre le chargement du cœur trading (commodités/terminaux).
                optional = key in ("vehicles", "moons", "orbits", "space_stations",
                                    "outposts", "cities", "factions")
                try:
                    raw = fetch_fn()
                except Exception as e:
                    progress.update(task, advance=1, count="échec")
                    if optional:
                        _console.print(f"[yellow]⚠ {label} non disponible : {e}[/yellow]")
                        continue
                    raise

                if key == "vehicles":
                    parsed = self._parse_vehicles(raw)
                    if not parsed and raw:
                        # Diagnostic : affiche les champs disponibles pour aider au debug
                        sample_keys = list(raw[0].keys())[:10] if raw else []
                        _console.print(
                            f"[yellow]⚠ Vaisseaux : 0 noms extraits sur {len(raw)} entrées. "
                            f"Champs API : {sample_keys}[/yellow]"
                        )
                else:
                    parsed = [parse_fn(d) for d in raw]

                self._save(key, raw)
                setattr(self, key, parsed)
                progress.update(task, advance=1, count=f"{len(parsed)} entrées")

        _console.print(
            f"[green]✓[/green] Cache mis à jour — "
            f"[cyan]{len(self.commodities)}[/cyan] commodités, "
            f"[cyan]{len(self.terminals)}[/cyan] terminaux"
        )

    def _load_from_disk(self) -> None:
        mapping = {
            "commodities": (self._parse_commodity,   "commodities"),
            "terminals":   (self._parse_terminal,    "terminals"),
            "star_systems":(self._parse_star_system, "star_systems"),
            "planets":     (self._parse_planet,      "planets"),
            "moons":          (self._parse_moon,          "moons"),
            "orbits":         (self._parse_orbit,         "orbits"),
            "space_stations": (self._parse_space_station, "space_stations"),
            "outposts":       (self._parse_outpost,       "outposts"),
            "cities":         (self._parse_city,          "cities"),
            "factions":       (self._parse_faction,       "factions"),
        }
        for key, (parse_fn, attr) in mapping.items():
            path = DATA_DIR / _STATIC_FILES[key]
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                setattr(self, attr, [parse_fn(d) for d in raw])
        # Vehicles — parsés différemment (déduplication)
        vpath = DATA_DIR / _STATIC_FILES["vehicles"]
        if vpath.exists():
            with open(vpath, encoding="utf-8") as f:
                raw = json.load(f)
            self.vehicles = self._parse_vehicles(raw)

    def _save(self, key: str, data: list) -> None:
        path = DATA_DIR / _STATIC_FILES[key]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    # ── Parsers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_vehicles(raw: list[dict]) -> list[Vehicle]:
        """Parse la liste de vaisseaux depuis l'endpoint /vehicles."""
        vehicles = []
        for d in raw:
            name_full = (d.get("name_full") or d.get("name") or "").strip()
            name      = (d.get("name") or name_full).strip()
            if not name:
                continue
            vehicles.append(Vehicle(
                id=int(d.get("id") or 0),
                name=name,
                name_full=name_full,
                slug=d.get("slug") or "",
                id_company=int(d.get("id_company") or 0),
                manufacturer=d.get("company_name") or "",
                scu=int(d.get("scu") or 0),
                crew=str(d.get("crew") or "1"),
                mass=int(d.get("mass") or 0),
                width=float(d.get("width") or 0),
                height=float(d.get("height") or 0),
                length=float(d.get("length") or 0),
                fuel_quantum=int(d.get("fuel_quantum") or 0),
                fuel_hydrogen=int(d.get("fuel_hydrogen") or 0),
                pad_type=d.get("pad_type") or "",
                container_sizes=d.get("container_sizes") or "",
                is_cargo=int(d.get("is_cargo") or 0),
                is_mining=int(d.get("is_mining") or 0),
                is_salvage=int(d.get("is_salvage") or 0),
                is_military=int(d.get("is_military") or 0),
                is_concept=int(d.get("is_concept") or 0),
                is_ground_vehicle=int(d.get("is_ground_vehicle") or 0),
                is_spaceship=int(d.get("is_spaceship") or 0),
                is_exploration=int(d.get("is_exploration") or 0),
                is_medical=int(d.get("is_medical") or 0),
                is_refinery=int(d.get("is_refinery") or 0),
                is_refuel=int(d.get("is_refuel") or 0),
                is_repair=int(d.get("is_repair") or 0),
                is_scanning=int(d.get("is_scanning") or 0),
                is_racing=int(d.get("is_racing") or 0),
                is_passenger=int(d.get("is_passenger") or 0),
                is_quantum_capable=int(d.get("is_quantum_capable") or 0),
                url_photo=d.get("url_photo") or "",
                url_store=d.get("url_store") or "",
            ))
        return sorted(vehicles, key=lambda v: v.name_full)

    @staticmethod
    def _parse_commodity(d: dict) -> Commodity:
        return Commodity(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            code=d.get("code") or "",
            kind=d.get("kind") or "",
            id_parent=int(d.get("id_parent") or 0),
            weight_scu=float(d.get("weight_scu") or 1.0),
            price_buy=float(d.get("price_buy") or 0),
            price_sell=float(d.get("price_sell") or 0),
            is_buyable=int(d.get("is_buyable") or 0),
            is_sellable=int(d.get("is_sellable") or 0),
            is_illegal=int(d.get("is_illegal") or 0),
            is_available=int(d.get("is_available") or 1),
            is_refinable=int(d.get("is_refinable") or 0),
            is_extractable=int(d.get("is_extractable") or 0),
            is_harvestable=int(d.get("is_harvestable") or 0),
            is_mineral=int(d.get("is_mineral") or 0),
            is_raw=int(d.get("is_raw") or 0),
            is_refined=int(d.get("is_refined") or 0),
            is_volatile_qt=int(d.get("is_volatile_qt") or 0),
            is_volatile_time=int(d.get("is_volatile_time") or 0),
            is_inert=int(d.get("is_inert") or 0),
            is_explosive=int(d.get("is_explosive") or 0),
            is_fuel=int(d.get("is_fuel") or 0),
            wiki=d.get("wiki") or "",
        )

    @staticmethod
    def _parse_terminal(d: dict) -> Terminal:
        return Terminal(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            code=d.get("code") or "",
            type=d.get("type") or "",
            id_star_system=int(d.get("id_star_system") or 0),
            star_system_name=d.get("star_system_name") or "",
            id_planet=int(d.get("id_planet") or 0),
            planet_name=d.get("planet_name") or "",
            id_orbit=int(d.get("id_orbit") or 0),
            orbit_name=d.get("orbit_name") or "",
            id_moon=int(d.get("id_moon") or 0),
            id_city=int(d.get("id_city") or 0),
            city_name=d.get("city_name") or "",
            id_space_station=int(d.get("id_space_station") or 0),
            space_station_name=d.get("space_station_name") or "",
            id_outpost=int(d.get("id_outpost") or 0),
            id_poi=int(d.get("id_poi") or 0),
            id_faction=int(d.get("id_faction") or 0),
            max_container_size=int(d.get("max_container_size") or 0),
            is_available=int(d.get("is_available") or 1),
            is_player_owned=int(d.get("is_player_owned") or 0),
            has_loading_dock=int(d.get("has_loading_dock") or 0),
            has_docking_port=int(d.get("has_docking_port") or 0),
            has_freight_elevator=int(d.get("has_freight_elevator") or 0),
            is_refinery=int(d.get("is_refinery") or 0),
            is_auto_load=int(d.get("is_auto_load") or 0),
            is_habitation=int(d.get("is_habitation") or 0),
            is_medical=int(d.get("is_medical") or 0),
            is_food=int(d.get("is_food") or 0),
            is_repair=int(d.get("is_repair") or 0),
            is_refuel=int(d.get("is_refuel") or 0),
            is_cargo_center=int(d.get("is_cargo_center") or 0),
            is_shop_vehicle=int(d.get("is_shop_vehicle") or 0),
            faction_name=d.get("faction_name") or "",
            company_name=d.get("company_name") or "",
            displayname=d.get("displayname") or "",
            nickname=d.get("nickname") or "",
        )

    @staticmethod
    def _parse_star_system(d: dict) -> StarSystem:
        return StarSystem(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            code=d.get("code") or "",
            is_available=int(d.get("is_available") or 1),
        )

    @staticmethod
    def _parse_planet(d: dict) -> Planet:
        return Planet(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            id_star_system=int(d.get("id_star_system") or 0),
            star_system_name=d.get("star_system_name") or "",
        )

    @staticmethod
    def _parse_moon(d: dict) -> Moon:
        return Moon(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            code=d.get("code") or "",
            id_star_system=int(d.get("id_star_system") or 0),
            star_system_name=d.get("star_system_name") or "",
            id_planet=int(d.get("id_planet") or 0),
            planet_name=d.get("planet_name") or "",
            id_orbit=int(d.get("id_orbit") or 0),
            orbit_name=d.get("orbit_name") or "",
            id_faction=int(d.get("id_faction") or 0),
            faction_name=d.get("faction_name") or "",
            is_available=int(d.get("is_available") or 1),
        )

    @staticmethod
    def _parse_orbit(d: dict) -> Orbit:
        return Orbit(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            code=d.get("code") or "",
            id_star_system=int(d.get("id_star_system") or 0),
            star_system_name=d.get("star_system_name") or "",
            is_lagrange=int(d.get("is_lagrange") or 0),
            is_jump_point=int(d.get("is_jump_point") or 0),
            is_asteroid=int(d.get("is_asteroid") or 0),
            is_planet=int(d.get("is_planet") or 0),
            is_star=int(d.get("is_star") or 0),
            is_man_made=int(d.get("is_man_made") or 0),
            is_available=int(d.get("is_available") or 1),
        )

    @staticmethod
    def _parse_space_station(d: dict) -> SpaceStation:
        return SpaceStation(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            nickname=d.get("nickname") or "",
            id_star_system=int(d.get("id_star_system") or 0),
            star_system_name=d.get("star_system_name") or "",
            id_planet=int(d.get("id_planet") or 0),
            planet_name=d.get("planet_name") or "",
            id_orbit=int(d.get("id_orbit") or 0),
            orbit_name=d.get("orbit_name") or "",
            id_moon=int(d.get("id_moon") or 0),
            id_faction=int(d.get("id_faction") or 0),
            faction_name=d.get("faction_name") or "",
            is_available=int(d.get("is_available") or 1),
            is_landable=int(d.get("is_landable") or 0),
            is_decommissioned=int(d.get("is_decommissioned") or 0),
            is_lagrange=int(d.get("is_lagrange") or 0),
            is_jump_point=int(d.get("is_jump_point") or 0),
            has_trade_terminal=int(d.get("has_trade_terminal") or 0),
            has_habitation=int(d.get("has_habitation") or 0),
            has_refinery=int(d.get("has_refinery") or 0),
            has_cargo_center=int(d.get("has_cargo_center") or 0),
            has_clinic=int(d.get("has_clinic") or 0),
            has_food=int(d.get("has_food") or 0),
            has_shops=int(d.get("has_shops") or 0),
            has_refuel=int(d.get("has_refuel") or 0),
            has_repair=int(d.get("has_repair") or 0),
            has_gravity=int(d.get("has_gravity") or 0),
            pad_types=d.get("pad_types") or "",
        )

    @staticmethod
    def _parse_outpost(d: dict) -> Outpost:
        return Outpost(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            nickname=d.get("nickname") or "",
            id_star_system=int(d.get("id_star_system") or 0),
            star_system_name=d.get("star_system_name") or "",
            id_planet=int(d.get("id_planet") or 0),
            planet_name=d.get("planet_name") or "",
            id_orbit=int(d.get("id_orbit") or 0),
            orbit_name=d.get("orbit_name") or "",
            id_moon=int(d.get("id_moon") or 0),
            moon_name=d.get("moon_name") or "",
            id_faction=int(d.get("id_faction") or 0),
            faction_name=d.get("faction_name") or "",
            is_available=int(d.get("is_available") or 1),
            is_landable=int(d.get("is_landable") or 0),
            is_decommissioned=int(d.get("is_decommissioned") or 0),
            has_trade_terminal=int(d.get("has_trade_terminal") or 0),
            has_habitation=int(d.get("has_habitation") or 0),
            has_refinery=int(d.get("has_refinery") or 0),
            has_cargo_center=int(d.get("has_cargo_center") or 0),
            has_clinic=int(d.get("has_clinic") or 0),
            has_food=int(d.get("has_food") or 0),
            has_shops=int(d.get("has_shops") or 0),
            has_refuel=int(d.get("has_refuel") or 0),
            has_repair=int(d.get("has_repair") or 0),
            has_gravity=int(d.get("has_gravity") or 0),
            pad_types=d.get("pad_types") or "",
        )

    @staticmethod
    def _parse_city(d: dict) -> City:
        return City(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            code=d.get("code") or "",
            id_star_system=int(d.get("id_star_system") or 0),
            star_system_name=d.get("star_system_name") or "",
            id_planet=int(d.get("id_planet") or 0),
            planet_name=d.get("planet_name") or "",
            id_orbit=int(d.get("id_orbit") or 0),
            orbit_name=d.get("orbit_name") or "",
            id_moon=int(d.get("id_moon") or 0),
            moon_name=d.get("moon_name") or "",
            id_faction=int(d.get("id_faction") or 0),
            faction_name=d.get("faction_name") or "",
            is_available=int(d.get("is_available") or 1),
            has_trade_terminal=int(d.get("has_trade_terminal") or 0),
            has_habitation=int(d.get("has_habitation") or 0),
            has_refinery=int(d.get("has_refinery") or 0),
            has_clinic=int(d.get("has_clinic") or 0),
            has_food=int(d.get("has_food") or 0),
            has_shops=int(d.get("has_shops") or 0),
            has_refuel=int(d.get("has_refuel") or 0),
            has_repair=int(d.get("has_repair") or 0),
            wiki=d.get("wiki") or "",
        )

    @staticmethod
    def _parse_faction(d: dict) -> Faction:
        return Faction(
            id=int(d.get("id") or 0),
            name=d.get("name") or "",
            wiki=d.get("wiki") or "",
            is_piracy=int(d.get("is_piracy") or 0),
            is_bounty_hunting=int(d.get("is_bounty_hunting") or 0),
            ids_star_systems=d.get("ids_star_systems") or "",
            ids_factions_friendly=d.get("ids_factions_friendly") or "",
            ids_factions_hostile=d.get("ids_factions_hostile") or "",
        )

    # ── Recherche ────────────────────────────────────────────────────────────

    def find_commodity(self, query: str) -> Commodity | None:
        q = query.lower().strip()
        for c in self.commodities:
            if c.code.lower() == q or c.name.lower() == q:
                return c
        # Partial match
        for c in self.commodities:
            if c.name.lower().startswith(q):
                return c
        return None

    def find_terminal(self, query: str) -> Terminal | None:
        q = query.lower().strip()
        for t in self.terminals:
            if t.code.lower() == q or t.name.lower() == q:
                return t
        for t in self.terminals:
            if t.name.lower().startswith(q):
                return t
        return None

    def search_terminals(self, query: str) -> list[Terminal]:
        q = query.lower().strip()
        return [t for t in self.terminals if q in t.name.lower()]

    def cache_age(self, key: str = "commodities") -> int | None:
        """Retourne l'âge du cache en secondes, None si absent."""
        path = DATA_DIR / _STATIC_FILES.get(key, f"{key}.json")
        if not path.exists():
            return None
        return int(time.time() - path.stat().st_mtime)

    def load_transport_graph(self) -> None:
        """Charge le graphe de transport depuis le fichier dans uexinfo/data/."""
        graph_path = PACKAGE_DIR / "data" / "transport_network.json"
        if not graph_path.exists():
            _console.print(f"[yellow]⚠  Graphe de transport introuvable : {graph_path}[/yellow]")
            return
        try:
            with open(graph_path, encoding="utf-8") as f:
                data = json.load(f)
            self.transport_graph = TransportGraph.from_json(data)
        except Exception as e:
            _console.print(f"[yellow]⚠  Erreur chargement graphe de transport : {e}[/yellow]")

    def save_transport_graph(self) -> None:
        """Sauvegarde le graphe de transport — écriture atomique via fichier temporaire.

        On écrit d'abord dans <file>.tmp, puis os.replace() remplace atomiquement
        le fichier cible. Si le process est tué pendant l'écriture, le .json original
        reste intact ; seul le .tmp est perdu.
        """
        graph_path = PACKAGE_DIR / "data" / "transport_network.json"
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = graph_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.transport_graph.to_json(), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, graph_path)   # atomique : le .json n'est remplacé qu'ici
            self.transport_graph.mark_saved()
        except Exception as e:
            _console.print(f"[red]✗  Erreur sauvegarde graphe de transport : {e}[/red]")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
