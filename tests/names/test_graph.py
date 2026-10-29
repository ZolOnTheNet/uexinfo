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
    ("port_tressler", "Port Tressler"),
])
def test_resolve_node(graph, query, expected):
    from uexinfo.cli.commands.nav import _resolve_node
    assert _resolve_node(query, graph) == expected


class Picker:
    """select_fn de test : mémorise les listes proposées, choisit le premier élément."""

    def __init__(self):
        self.calls = []

    def __call__(self, items, title="", mode="multi", confirm_label=""):
        self.calls.append((title, [it.label for it in items]))
        return [items[0]]


def test_typo_is_proposed_never_applied(graph):
    from types import SimpleNamespace
    from uexinfo.cli.commands.nav import _pick_node, _resolve_node
    assert _resolve_node("Rayari Cantwell Research Outposx", graph) is None
    ctx = SimpleNamespace(select_fn=Picker())
    assert _pick_node("Rayari Cantwell Research Outposx", graph, ctx) == "Rayari Cantwell Research Outpost"
    assert "Vouliez-vous dire" in ctx.select_fn.calls[0][0]


@pytest.mark.parametrize("system,expected", [
    ("stanton", "Nyx Gateway (Stanton)"), ("Pyro", "Nyx Gateway (Pyro)"),
])
def test_homonym_gateways_give_a_list_player_system_first(graph, system, expected):
    from types import SimpleNamespace
    from uexinfo.cli.commands.nav import _pick_node, _resolve_node
    assert _resolve_node("nyx gateway", graph, system) is None        # jamais choisi seul
    ctx = SimpleNamespace(select_fn=Picker())
    assert _pick_node("nyx gateway", graph, ctx, system) == expected
    assert len(ctx.select_fn.calls[0][1]) == 2


def test_mission_scan_cleanup_and_hint(graph, monkeypatch, tmp_path):
    from uexinfo.cache import place_aliases
    from uexinfo.cache.mission_scan import _resolve_graph_node
    monkeypatch.setattr(place_aliases, "_STORE_FILE", tmp_path / "aliases.json")
    assert _resolve_graph_node("Admin - Seraphim Station above Crusader", graph) == "Seraphim"
    # Deux gateways homonymes : rien de sûr, le système ne fait que classer (D11)
    assert _resolve_graph_node("Pyro Gateway", graph, system_hint="Nyx") is None


def test_node_found_no_fuzzy(graph):
    from uexinfo.cli.commands.nav import _node_found
    assert _node_found("nyx gate", graph)
    assert not _node_found("zzz", graph)
    assert not _node_found("Rayari Cantwell Research Outposx", graph)


def test_player_node_by_terminal_id(graph, uex_cache):
    from types import SimpleNamespace
    from uexinfo.cli.commands.nav import _expand_alias, _player_node
    from uexinfo.models.player import Player
    cache = SimpleNamespace(**{**vars(uex_cache), "transport_graph": graph})
    ctx = SimpleNamespace(cache=cache, player=Player())
    ctx.player.set_location("nom affiché sans rapport", 259)        # Admin - Seraphim
    assert _player_node(ctx, graph) == "Seraphim"
    assert _expand_alias("@local", ctx) == "#node:Seraphim"
