"""Arrivée, hangar, posé, départ (gamelog/presence.py) et position suivie par l'overlay.

Game.log RÉEL (LIVE 4.10, 2026-10-30) : apparition à Seraphim, arrivée à Baijini Point en Avenger
(petit hangar), Taurus sorti, départ vers Terra Gateway (hangar moyen), vente. Extrait anonymisé :
tests/fixtures/gamelog/live_4.10_baijini_terra.log.
"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from uexinfo.gamelog.events import GameEvent, recognize, recognize_all
from uexinfo.gamelog.follow import read_lines
from uexinfo.gamelog.presence import PresenceTracker
from uexinfo.names import place_trade_terminal

LIVE = Path(__file__).parent.parent / "fixtures" / "gamelog" / "live_4.10_baijini_terra.log"


def _run(events):
    t = PresenceTracker()
    return [(n.ts.strftime("%H:%M:%S"), n.text) for n in t.feed(events) + t.flush()]


def test_real_session():
    assert _run(recognize_all(read_lines(LIVE))) == [
        ("20:32:17", "📍 Apparition à Seraphim Station"),
        ("22:40:17", "📍 Arrivée à Baijini Point"),
        ("22:40:44", "🅷 Hangar attribué à Baijini Point (hangar petit)"),
        ("22:41:35", "⬇ Posé à Baijini Point"),
        ("23:48:57", "🛫 Départ de Baijini Point"),
        ("23:51:45", "📍 Arrivée à Terra Gateway"),
        ("23:52:41", "🅷 Hangar attribué à Terra Gateway (hangar moyen)"),
        ("23:53:56", "⬇ Posé à Terra Gateway"),
    ]


def test_new_recognizers_on_real_lines():
    kinds = {e.kind for e in recognize_all(read_lines(LIVE))}
    assert {"place_zone", "landing_request", "ship_elevator"} <= kinds


T0 = datetime(2026, 10, 31, 12, 0, 0)


def _ev(kind, s, **data):
    return GameEvent(kind, T0 + timedelta(seconds=s), kind, data, True)


def test_departure_request_is_not_a_hangar():
    # « Hangar Request Completed » longtemps après l'arrivée : ouverture du hangar pour partir.
    t = PresenceTracker()
    out = t.feed([_ev("place_zone", 0, **{"from": 0, "to": 7}), _ev("near_location", 0, loc_code="RR_CRU_LEO"),
                  _ev("landing_request", 900, text="Hangar Request Completed", hangar=True),
                  _ev("place_zone", 960, **{"from": 7, "to": 0})])
    assert [n.kind for n in out] == ["arrival", "departure"]


def test_repeated_zone_lines_and_learned_code():
    # Les lignes « -> [0] » se répètent en vol ; un identifiant appris nomme l'arrivée sans inventaire.
    t = PresenceTracker(known_codes={7: "RR_ARC_LEO"})
    out = t.feed([_ev("place_zone", 0, **{"from": 0, "to": 7}),
                  _ev("place_zone", 30, **{"from": 7, "to": 0}),
                  _ev("place_zone", 31, **{"from": 7, "to": 0}),
                  _ev("place_zone", 200, **{"from": 7, "to": 9})])
    out += t.flush(T0 + timedelta(seconds=300))
    assert [(n.kind, n.place) for n in out] == [
        ("arrival", "Baijini Point"), ("departure", "Baijini Point"), ("arrival", "")]


def test_pad_and_landing_request_wording():
    ev = recognize('<2026-10-31T12:00:00.000Z> [Notice] <SHUDEvent_OnNotification> '
                   'Added notification "Landing Request Completed: " [5] to queue.')
    assert ev.kind == "landing_request" and ev.data["hangar"] is False
    contract = recognize('<2026-10-31T12:00:00.000Z> [Notice] <SHUDEvent_OnNotification> '
                         'Added notification "Contract Accepted: Haul cargo" [6] to queue.')
    assert contract.kind == "notification"


def _t(tid, name, station="", city="", system="Stanton", kind="commodity"):
    return SimpleNamespace(id=tid, name=name, type=kind, space_station_name=station, city_name=city,
                           star_system_name=system, is_available=1, is_cargo_center=0)


TERMINALS = [
    _t(251, "Admin - Terra Gateway (Stanton)", station="Terra Gateway (Stanton)"),
    _t(763, "Admin - Terra Gateway (Nyx)", station="Terra Gateway (Nyx)", system="Nyx"),
    _t(12, "TDD - Trade and Development Division - Area 18", city="Area 18"),
    _t(13, "Pharmacy - Area 18", city="Area 18", kind="item"),
    _t(27, "Admin - GrimHEX", station="Green Imperial Housing Exchange"),
]


@pytest.mark.parametrize("place, system, tid", [
    ("Terra Gateway", "Stanton", 251), ("Terra Gateway", "Nyx", 763),
    ("Area18", "Stanton", 12), ("Grim HEX", "Stanton", 27), ("Hurston", "Stanton", None),
])
def test_place_trade_terminal(place, system, tid):
    t = place_trade_terminal(TERMINALS, place, system)
    assert (t.id if t else None) == tid


def test_overlay_follows_arrival(monkeypatch):
    from uexinfo.config import settings
    from uexinfo.gamelog import reader
    from uexinfo.models.player import Player
    from uexinfo.overlay.server import OverlayServer

    monkeypatch.setattr(settings, "save", lambda cfg: None)
    monkeypatch.setattr(reader, "load_zone_codes", lambda: {})
    monkeypatch.setattr(reader, "save_zone_codes", lambda codes: None)
    sent = []
    srv = OverlayServer()
    srv.ctx = SimpleNamespace(cfg={"gamelog": {}}, cache=SimpleNamespace(terminals=TERMINALS), player=Player())

    async def capture(msg):
        sent.append(json.loads(msg))
    srv._broadcast_raw = capture
    monkeypatch.setattr("uexinfo.cli.choose.position_terminal", lambda ctx: None)

    lines = [l for l in read_lines(LIVE) if l[1:20] >= "2026-10-30T23:48"]
    asyncio.run(srv._presence_update(lines))
    texts = [m["text"] for m in sent]
    assert "📍 Arrivée à Terra Gateway" in texts
    assert "   Position : Admin - Terra Gateway (Stanton)" in texts
    assert (srv.ctx.player.location, srv.ctx.player.location_id) == ("Admin - Terra Gateway (Stanton)", 251)
