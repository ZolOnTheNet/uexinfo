"""Contrats pris et chemin (cli/circuit.py) — offres fictives, vrai réseau de transport."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uexinfo.models.player import Player
from uexinfo.models.transport_network import TransportGraph
from uexinfo.ocr.contract_watch import Offer, OffersBoard

GRAPH = Path(__file__).parents[1] / "uexinfo" / "data" / "transport_network.json"


@pytest.fixture(scope="module")
def graph():
    return TransportGraph.from_json(json.loads(GRAPH.read_text(encoding="utf-8")))


@pytest.fixture()
def ctx(graph, uex_cache, monkeypatch, tmp_path):
    """Contexte minimal ; missions, voyages, offres et choix de lieux dans un dossier temporaire."""
    from uexinfo.cache import mission_manager, place_aliases, voyage_manager
    monkeypatch.setattr(mission_manager, "DATA_FILE", tmp_path / "missions.json")
    monkeypatch.setattr(voyage_manager, "DATA_FILE", tmp_path / "voyages.json")
    monkeypatch.setattr(place_aliases, "_STORE_FILE", tmp_path / "place_aliases.json")
    cache = SimpleNamespace(**{**vars(uex_cache), "transport_graph": graph})
    return SimpleNamespace(cache=cache, player=Player(), select_fn=None, cfg={},
                           mission_manager=mission_manager.MissionManager(),
                           voyage_manager=voyage_manager.VoyageManager(),
                           offers_board=OffersBoard(tmp_path / "offres.json"))


def offer(title, reward, legs):
    o = Offer(title=title, reward=reward, recognized=True, seen_at=1.0,
              legs=[{"commodity": c, "scu": n, "pickup": a, "drop": b} for c, n, a, b in legs])
    return o


SERAPHIM = "Seraphim Station above Crusader"
TRESSLER = "Port Tressler at MicroTech"


def test_notice_title_strips_xp_and_blueprint():
    from uexinfo.cli.circuit import notice_title
    assert notice_title("Contract Accepted: [BP] Rookie Rank - Direct Medium Cargo Haul 50 / 200 exp.") == \
        ("accepted", "Rookie Rank - Direct Medium Cargo Haul")
    assert notice_title("Contract Complete: Alliance Aid: Small Supply of Research Resource") == \
        ("complete", "Alliance Aid: Small Supply of Research Resource")
    assert notice_title("New Objective: Deliver 0/95 SCU of Carbon to Ruin Station") is None


def test_accepted_notice_takes_the_offer_and_route_follows(ctx):
    from uexinfo.cli import circuit
    o = offer("Rookie Rank - Direct Medium Cargo Haul", 48_000, [("Carbon", 16, SERAPHIM, TRESSLER)])
    ctx.offers_board.offers[o.key] = o
    msg = circuit.contract_notice(ctx, "Contract Accepted: Rookie Rank - Direct Medium Cargo Haul 50 exp.")
    assert "mission #" in msg and o.mission_id
    v = ctx.voyage_manager.get_active()
    assert v.name == circuit.CIRCUIT_NAME and v.mission_ids == [o.mission_id]
    m = ctx.mission_manager.get(str(o.mission_id))
    assert m.objectives[0].source_ref == "node:Seraphim"            # lieu relié une fois (D11)

    res = circuit.compute(ctx)
    assert [s.node for s in res["route"].stops] == ["Seraphim", "Port Tressler"]
    assert circuit.next_step(ctx) == "Seraphim : charger 16 SCU"
    # second « Contract Accepted » (relance, partage) : pas de doublon
    assert circuit.contract_notice(ctx, "Contract Accepted: Rookie Rank - Direct Medium Cargo Haul") is None

    # arrivée ailleurs que le prochain arrêt : rien ne bouge
    assert circuit.arrived(ctx, "Port Tressler", "Stanton") is None
    # arrivée à Seraphim : l'arrêt est fait, la cargaison est à bord
    done = circuit.arrived(ctx, "Seraphim Station", "Stanton")
    assert done.startswith("✔ Arrêt fait à Seraphim")
    assert m.objectives[0].progress == "picked"
    assert circuit.next_step(ctx) == "Port Tressler : livrer 16 SCU"
    assert "Chemin terminé" in circuit.arrived(ctx, "Port Tressler", "Stanton")
    assert circuit.next_step(ctx) == ""

    msg = circuit.contract_notice(ctx, "Contract Complete: Rookie Rank - Direct Medium Cargo Haul")
    assert "terminé" in msg and v.mission_ids == []
    assert not ctx.offers_board.offers


def test_unknown_offer_is_reported_not_invented(ctx):
    from uexinfo.cli import circuit
    msg = circuit.contract_notice(ctx, "Contract Accepted: Experienced Hauler Needed for Direct Large Shipment")
    assert "pas lu dans les offres" in msg
    assert ctx.voyage_manager.get_active() is None


def test_take_button_and_capacity(ctx):
    from uexinfo.cli import circuit
    a = offer("Contrat A", 60_000, [("Gold", 32, SERAPHIM, TRESSLER)])
    b = offer("Contrat B", 50_000, [("Iron", 32, SERAPHIM, TRESSLER)])
    for o in (a, b):
        ctx.offers_board.offers[o.key] = o
        circuit.take_offer(ctx, o, ask=False)
    from uexinfo.models.player import Ship
    ctx.player.ships = [Ship(name="Petit", scu=40)]
    ctx.player.active_ship = "Petit"
    route = circuit.compute(ctx)["route"]
    # 64 SCU pour 40 : deux allers
    assert [s.node for s in route.stops] == ["Seraphim", "Port Tressler", "Seraphim", "Port Tressler"]
    assert all(s.cargo_after <= 40 for s in route.stops)
    # les offres prises ne sont plus candidates du meilleur lot
    assert ctx.offers_board.lot_items(2.0) == []


def test_pickup_found_by_commodity():
    from uexinfo.ocr.contract_watch import _pickup_for
    from uexinfo.models.mission_result import ParsedObjective as P
    collects = [P("collect", "Gold", location="Seraphim Station"), P("collect", "Iron", location="Port Tressler")]
    assert _pickup_for(P("deliver", "Gold (1 200/scu)", 8, "Everus Harbor"), collects) == "Seraphim Station"
    assert _pickup_for(P("deliver", "Waste", 8, "Everus Harbor"), collects) is None
    assert _pickup_for(P("deliver", "Waste", 8, "Everus Harbor"), collects[:1]) == "Seraphim Station"


def test_commands_print_the_route(ctx):
    import uexinfo.cli.commands.mission as M
    o = offer("Contrat A", 60_000, [("Gold", 24, SERAPHIM, TRESSLER)])
    ctx.offers_board.offers[o.key] = o
    with M.console.capture() as cap:
        M.cmd_mission(["offres", "prendre", "1"], ctx)
        M.cmd_mission(["pris"], ctx)
        M.cmd_mission(["route"], ctx)
        M.cmd_mission(["route", "suivant"], ctx)
    out = cap.get()
    # (les messages print_ok passent par la console du formateur, remplacée par d'autres tests)
    assert "à charger" in out
    assert "Seraphim" in out and "Port Tressler" in out and "⏱" in out
    assert o.mission_id and ctx.mission_manager.get(str(o.mission_id)).objectives[0].progress == "picked"
