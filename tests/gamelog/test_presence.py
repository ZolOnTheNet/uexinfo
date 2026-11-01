"""Arrivée, hangar, posé, départ (gamelog/presence.py) et position suivie par l'overlay.

Game.log RÉEL (LIVE 4.10, 2026-10-30) : apparition à Seraphim, arrivée à Baijini Point en Avenger
(petit hangar), Taurus sorti, départ vers Terra Gateway (hangar moyen), vente. Extrait anonymisé :
tests/fixtures/gamelog/live_4.10_baijini_terra.log.

Morts (2026-10-19) : vaisseau détruit dans le hangar de CRU-L1, puis mort à pied à HDMS-Hahn ;
deux réveils à Seraphim Station. Extrait anonymisé : tests/fixtures/gamelog/live_4.10_morts_seraphim.log.
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
DEATHS = Path(__file__).parent.parent / "fixtures" / "gamelog" / "live_4.10_morts_seraphim.log"


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


def test_deaths_real_session():
    out = _run(recognize_all(read_lines(DEATHS)))
    assert out[2:15] == [
        ("18:52:14", "📍 Arrivée à CRU-L1 Ambitious Dream Station"),
        ("18:52:56", "🅷 Hangar attribué à CRU-L1 Ambitious Dream Station (hangar moyen)"),
        # le crash éjecte le pilote (« ClearDriver ») : pas un atterrissage
        ("18:53:50", "💀 Mort à CRU-L1 Ambitious Dream Station (vaisseau détruit)"),
        ("18:54:14", "🏥 Réveil à Seraphim Station"),
        ("19:01:13", "🛫 Départ de Seraphim Station"),
        ("19:02:27", "📍 Arrivée à CRU-L1 Ambitious Dream Station"),
        ("19:02:51", "🅷 Hangar attribué à CRU-L1 Ambitious Dream Station (hangar moyen)"),
        ("19:08:08", "⬇ Posé à CRU-L1 Ambitious Dream Station"),
        ("19:32:22", "🛫 Départ de CRU-L1 Ambitious Dream Station"),
        ("19:37:11", "📍 Arrivée à HDMS-Hahn"),
        ("19:38:03", "⬇ Posé à HDMS-Hahn"),
        # mort à pied : aucune cause écrite, la réapparition sans écran de chargement la révèle
        ("19:42:03", "💀 Mort à HDMS-Hahn"),
        ("19:42:05", "🏥 Réveil à Seraphim Station"),
    ]
    # Reconnexion (écran de chargement) : apparition, pas une mort.
    assert ("19:55:02", "📍 Apparition à Seraphim Station") in out
    assert sum(text.startswith("💀") for _, text in out) == 2


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


def test_arena_commander_death_ignored():
    # Depuis le menu, sans « Join PU » : Arena Commander, les morts et réapparitions n'y comptent pas.
    t = PresenceTracker(player="JOUEUR")
    out = t.feed([_ev("menu", 0, reason="OnLobbyPostGameUnload"), _ev("loading_screen", 1), _ev("spawn", 5),
                  _ev("player_dead", 60, name="JOUEUR", ship_destroyed=True), _ev("spawn", 80)])
    assert out == []


def test_other_actor_death_ignored():
    npc = _ev("player_dead", 10, name="PU_Pilots-Human-Pirate-Pilot_Light_200000017034", ship_destroyed=True)
    assert PresenceTracker().feed([npc]) == []                           # pseudo inconnu : PNJ reconnu
    other = _ev("player_dead", 10, name="EQUIPIER", ship_destroyed=True)
    assert PresenceTracker(player="JOUEUR").feed([other]) == []
    assert [n.text for n in PresenceTracker().feed([other])] == ["💀 Mort (vaisseau détruit)"]


def test_death_on_foot_then_regen_with_known_zone():
    # Zone de Seraphim déjà apprise : le réveil attend « Spawned! » (quelques ms) avant d'être annoncé.
    t = PresenceTracker(known_codes={7: "RR_CRU_LEO"})
    out = t.feed([_ev("shard", 0, shard="pub"), _ev("loading_screen", 1), _ev("spawn", 30),
                  _ev("place_zone", 600, **{"from": 0, "to": 7}), _ev("spawn", 600.005),
                  _ev("near_location", 602, loc_code="RR_CRU_LEO")])
    assert [n.text for n in out] == ["💀 Mort", "🏥 Réveil à Seraphim Station"]
    assert t.phase == "landed"


def _t(tid, name, station="", city="", system="Stanton", kind="commodity"):
    return SimpleNamespace(id=tid, name=name, type=kind, space_station_name=station, city_name=city,
                           star_system_name=system, is_available=1, is_cargo_center=0)


TERMINALS = [
    _t(251, "Admin - Terra Gateway (Stanton)", station="Terra Gateway (Stanton)"),
    _t(763, "Admin - Terra Gateway (Nyx)", station="Terra Gateway (Nyx)", system="Nyx"),
    _t(12, "TDD - Trade and Development Division - Area 18", city="Area 18"),
    _t(13, "Pharmacy - Area 18", city="Area 18", kind="item"),
    _t(27, "Admin - GrimHEX", station="Green Imperial Housing Exchange"),
    _t(301, "Admin - Seraphim Station", station="Seraphim Station"),
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


def test_overlay_follows_regen(monkeypatch):
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

    # uexinfo lancé en cours de partie : la session déjà lue est rejouée sans annonce.
    seen = [l for l in read_lines(DEATHS) if l[1:20] < "2026-10-19T19:30"]
    lines = [l for l in read_lines(DEATHS) if "2026-10-19T19:30" <= l[1:20] <= "2026-10-19T19:43"]
    asyncio.run(srv._presence_update(lines, seen))
    texts = [m["text"] for m in sent]
    assert texts[-3:] == ["💀 Mort à HDMS-Hahn", "🏥 Réveil à Seraphim Station",
                          "   Position : Admin - Seraphim Station"]
    assert srv.ctx.player.location_id == 301


def test_zone_label_hides_stale_or_redundant_place():
    from uexinfo.models.player import Player
    from uexinfo.overlay.server import OverlayServer
    srv = OverlayServer()
    srv.ctx = SimpleNamespace(cache=SimpleNamespace(terminals=TERMINALS))
    p = Player(location="Admin - Seraphim Station", location_id=301, zone="Baijini Point",
               zone_ts=1000.0, shard_ts=2000.0)
    assert srv._zone_label(p) == ""                     # départ de route QT d'une session précédente
    p.zone_ts = 3000.0
    assert srv._zone_label(p) == "Baijini Point"        # lieu récent, différent de la position
    p.zone = "Seraphim Station"
    assert srv._zone_label(p) == ""                     # le lieu même de la position


def test_disconnect_30000_real_lines():
    lines = [
        '<2026-10-31T16:53:41.141Z> [Notice] <Channel Process Disconnection> cause=30000 reason="CNetChannel::'
        'InactivityTimerCallback connection has timed out (timeSinceRecv 30.000011 > net_inactivitytimeout 30.000000)" '
        'frame=442112 isRemote=0 map="megamap" [Team_Network][Network]',
        '<2026-10-31T16:53:41.145Z> [CSessionManager::RequestFrontEnd] Started - RequestFrontEndReason="OnLobbyPostGameUnload"!',
        '<2026-10-31T16:53:41.155Z> [Notice] <Error Popup Opened> errorCode=30000 [Team_UI][Disconnection]',
    ]
    t = PresenceTracker(known_codes={7: "RR_CRU_LEO"})
    t.feed([_ev("place_zone", 0, **{"from": 0, "to": 7}), _ev("near_location", 1, loc_code="RR_CRU_LEO")])
    out = t.feed(recognize_all(lines))
    assert [n.text for n in out] == [
        "⚠ Déconnexion du serveur (erreur 30000 : le serveur ne répond plus depuis 30 s (serveur ou réseau))"]
    assert t.phase == "away"


def test_disconnect_unknown_code_uses_reason():
    t = PresenceTracker()
    out = t.feed([_ev("disconnect", 0, cause=30010, reason="Remote Disconnect - Nub destroyed"),
                  _ev("error_popup", 5, code=60016)])
    assert [n.text for n in out] == ["⚠ Déconnexion du serveur (erreur 60016 : Nub destroyed)"]


def test_normal_exit_not_announced():
    t = PresenceTracker()
    assert t.feed([_ev("disconnect", 0, cause=30016, reason="Remote Disconnect - Player requested disconnect")]) == []
