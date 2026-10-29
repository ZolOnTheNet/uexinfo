"""Lieux des missions et des voyages (D11) : résolus une fois, retenus par référence."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uexinfo.models.mission import Mission, MissionObjective
from uexinfo.models.player import Player
from uexinfo.models.transport_network import TransportGraph

GRAPH = Path(__file__).parents[2] / "uexinfo" / "data" / "transport_network.json"


@pytest.fixture(scope="module")
def graph():
    return TransportGraph.from_json(json.loads(GRAPH.read_text(encoding="utf-8")))


@pytest.fixture(autouse=True)
def aliases(monkeypatch, tmp_path):
    """Choix mémorisés du joueur dans un fichier temporaire (jamais le vrai dossier)."""
    from uexinfo.cache import place_aliases
    monkeypatch.setattr(place_aliases, "_STORE_FILE", tmp_path / "place_aliases.json")
    return place_aliases


class Picker:
    """select_fn de test : mémorise les listes proposées et choisit l'élément `index`."""

    def __init__(self, index=0):
        self.index, self.calls = index, []

    def __call__(self, items, title="", mode="multi", confirm_label=""):
        self.calls.append((title, [it.label for it in items]))
        return None if self.index is None else [items[self.index]]


@pytest.fixture()
def ctx(graph, uex_cache):
    cache = SimpleNamespace(**{**vars(uex_cache), "transport_graph": graph})
    return SimpleNamespace(cache=cache, player=Player(), select_fn=None)


# ── Lecture d'un lieu écrit ──────────────────────────────────────────────────
def test_contract_phrasing_is_removed_and_sure_place_kept(graph):
    from uexinfo.names.places import place_lookup
    node, _ = place_lookup("Admin - Seraphim Station above Crusader", graph)
    assert node == "Seraphim"
    assert place_lookup("Port Tressler at MicroTech", graph)[0] == "Port Tressler"


def test_text_naming_the_whole_place_is_sure(graph):
    # Le nom complet du lieu figure en mots entiers dans le texte : il est nommé, pas deviné
    from uexinfo.names.places import place_lookup
    assert place_lookup("Port Tressler Medical Center", graph)[0] == "Port Tressler"


def test_typo_is_only_a_proposal(graph):
    from uexinfo.names import FUZZY
    from uexinfo.names.places import place_lookup
    node, r = place_lookup("Port Tresler", graph)
    assert node is None                                   # jamais retenu seul
    assert r.matches[0].entity.id == "Port Tressler" and r.matches[0].level == FUZZY


def test_typo_is_proposed_then_remembered(ctx, aliases):
    from uexinfo.cli.places import resolve_place
    assert resolve_place("Port Tresler", ctx, ask=False) is None
    ctx.select_fn = Picker()
    assert resolve_place("Port Tresler", ctx) == "Port Tressler"
    assert "Vouliez-vous dire" in ctx.select_fn.calls[0][0]
    # Même texte plus tard : le choix du joueur, sans redemander
    ctx.select_fn = Picker(index=None)
    assert resolve_place("Port Tresler", ctx, ask=False) == "Port Tressler"
    assert ctx.select_fn.calls == []


def test_homonym_gateways_listed_with_mission_system_first(ctx):
    from uexinfo.cli.places import ensure_mission_places
    m = Mission(id=1, name="m", objectives=[
        MissionObjective(source="Levski", destination="Pyro Gateway")])
    ctx.select_fn = Picker()
    assert ensure_mission_places(m, ctx) == []
    title, labels = ctx.select_fn.calls[0]
    assert labels[0] == "Pyro Gateway (Nyx)"                # Levski est dans Nyx
    o = m.objectives[0]
    assert (o.destination, o.destination_ref) == ("Pyro Gateway (Nyx)", "node:Pyro_Gateway_(Nyx)")


def test_unsure_place_stays_to_check_without_selector(ctx):
    from uexinfo.cli.places import ensure_mission_places, mission_node_map
    m = Mission(id=1, name="m", objectives=[
        MissionObjective(source="Seraphim", destination="Pyro Gateway")])
    assert ensure_mission_places(m, ctx, ask=False) == ["Pyro Gateway"]
    assert m.objectives[0].source_ref == "node:Seraphim"
    nodes = mission_node_map([m], ctx.cache.transport_graph)
    assert nodes == {"Seraphim": "Seraphim", "Pyro Gateway": None}   # jamais deviné


def test_place_refs_survive_json_roundtrip():
    m = Mission(id=3, name="m", objectives=[
        MissionObjective(source="Seraphim", source_ref="node:Seraphim", destination="x")])
    back = Mission.from_dict(json.loads(json.dumps(m.to_dict())))
    assert back.objectives[0].source_ref == "node:Seraphim"
    assert back.unresolved_places == ["x"] and back.place_refs() == {"Seraphim": "node:Seraphim"}


def test_mission_distance_uses_references(ctx):
    from uexinfo.cli.commands.voyage import _mission_distance
    m = Mission(id=1, name="m", objectives=[MissionObjective(
        source="Port Tressler", source_ref="node:Port_Tressler",
        destination="Lorville", destination_ref="node:Lorville")])
    assert _mission_distance(m, ctx) and _mission_distance(m, ctx) > 0
    m.objectives[0].destination_ref = None                    # lieu à préciser
    assert _mission_distance(m, ctx) is None


# ── Missions désignées par leur nom ───────────────────────────────────────────
def test_mission_lookup_never_takes_the_first():
    from uexinfo.cache.mission_manager import MissionManager
    mm = MissionManager.__new__(MissionManager)
    mm.missions = [Mission(id=1, name="Cargo Lorville"), Mission(id=2, name="Cargo Area 18"),
                   Mission(id=3, name="Cargo")]
    assert mm.get("2").id == 2
    assert mm.get("cargo").id == 3                            # nom exact
    assert mm.get("area").id == 2                             # une seule contient le texte
    assert mm.get("cargo l") .id == 1
    assert mm.get("car") is None and len(mm.find("car")) == 3  # plusieurs : à départager


# ── Filtres de voyage par identité ────────────────────────────────────────────
def test_place_area_contains_planet_and_system(ctx):
    from uexinfo.cli.places import area_ref, place_area
    area = place_area("Lorville", ctx)
    hurston = area_ref("Hurston", ctx, ask=False)
    stanton = area_ref("Stanton", ctx, ask=False)
    assert hurston in area and stanton in area
    assert area_ref("Pyro", ctx, ask=False) not in area


def test_mission_places_command_resolves_what_is_left(ctx):
    """/mission lieux : les lieux restés à préciser (ajout sans liste possible) sont départagés."""
    from uexinfo.cli.commands.mission import _cmd_places
    m = Mission(id=7, name="m", objectives=[MissionObjective(source="Levski", destination="Pyro Gateway")])
    saved = []
    ctx.mission_manager = SimpleNamespace(missions=[m], update=saved.append, find=lambda q: [m])
    ctx.select_fn = Picker()
    _cmd_places([], ctx)
    o = m.objectives[0]
    assert o.source_ref == "node:Levski" and o.destination_ref == "node:Pyro_Gateway_(Nyx)"
    assert saved == [m] and m.unresolved_places == []


def test_place_choices_can_be_forgotten(ctx, aliases):
    from uexinfo.cli.commands.config import _clear_place_choices
    aliases.remember("Port Tresler", "node:Port_Tressler")
    assert "1 choix" in _clear_place_choices(ctx)
    assert aliases.get("Port Tresler") is None
