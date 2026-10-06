"""Fixtures partagées : vrai sous-ensemble de données UEX (tests/fixtures/uex, octobre 2026)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_UEX = Path(__file__).parent / "fixtures" / "uex"


def _load(name):
    return json.loads((_UEX / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def uex_cache():
    from uexinfo.cache.manager import CacheManager as CM
    return SimpleNamespace(
        terminals=[CM._parse_terminal(d) for d in _load("terminals")],
        commodities=[CM._parse_commodity(d) for d in _load("commodities")],
        vehicles=CM._parse_vehicles(_load("vehicles")),
        star_systems=[CM._parse_star_system(d) for d in _load("star_systems")],
        planets=[CM._parse_planet(d) for d in _load("planets")],
        moons=[], orbits=[], outposts=[],
        space_stations=[CM._parse_space_station(d) for d in _load("space_stations")],
        cities=[CM._parse_city(d) for d in _load("cities")],
        transport_graph=None,
    )
