"""Nœuds du graphe de navigation réel (uexinfo/data/transport_network.json) — résolveur unique."""
import json
from pathlib import Path

import pytest

from uexinfo.models.transport_network import TransportGraph

GRAPH = Path(__file__).parents[2] / "uexinfo" / "data" / "transport_network.json"


@pytest.fixture(scope="module")
def graph():
    return TransportGraph.from_json(json.loads(GRAPH.read_text(encoding="utf-8")))


@pytest.mark.parametrize("query,expected", [
    ("area 18", "Area 18"), ("Area", "Area 18"), ("new", "New Babbage"),
    ("port_tressler", "Port Tressler"), ("Rayari Cantwell Research Outposx", "Rayari Cantwell Research Outpost"),
])
def test_resolve_node(graph, query, expected):
    from uexinfo.cli.commands.nav import _resolve_node
    assert _resolve_node(query, graph) == expected


@pytest.mark.parametrize("system,expected", [
    ("stanton", "Nyx Gateway (Stanton)"), ("Pyro", "Nyx Gateway (Pyro)"),
])
def test_homonym_gateway_prefers_player_system(graph, system, expected):
    from uexinfo.cli.commands.nav import _resolve_node
    assert _resolve_node("nyx gateway", graph, system) == expected


def test_mission_scan_cleanup_and_hint(graph):
    from uexinfo.cache.mission_scan import _resolve_graph_node
    assert _resolve_graph_node("Admin - Seraphim Station above Crusader", graph) == "Seraphim"
    assert _resolve_graph_node("Pyro Gateway", graph, system_hint="Nyx") == "Pyro Gateway (Nyx)"


def test_find_candidates_no_fuzzy(graph):
    from uexinfo.cli.commands.nav import _find_candidates
    assert "Nyx Gateway (Stanton)" in _find_candidates("nyx gate", graph)
    assert _find_candidates("zzz", graph) == []
