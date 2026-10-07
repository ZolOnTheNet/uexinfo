"""Game.log RÉEL (LIVE 4.10, 2026-10-07) : Seraphim Station → Nyx (Stanton Gateway → Pyro Gateway).

Extrait anonymisé (pseudo → JOUEUR, geid/accountId/IP remplacés) : tests/fixtures/gamelog/live_4.10_seraphim_nyx.log.
Contient une ligne en cp1252 (« Entrée ligne ») pour fixer la lecture tolérante à l'encodage.
"""
from pathlib import Path

import pytest

from uexinfo.gamelog.events import audit, recognize, recognize_all
from uexinfo.gamelog.follow import LogFollower, read_lines, tail_lines
from uexinfo.gamelog.state import build_state

LIVE = Path(__file__).parent.parent / "fixtures" / "gamelog" / "live_4.10_seraphim_nyx.log"


@pytest.fixture(scope="module")
def lines():
    return read_lines(LIVE)


@pytest.fixture(scope="module")
def events(lines):
    return recognize_all(lines)


def test_cp1252_line_decoded(lines):
    assert any("Entrée ligne" in l for l in lines)
    assert any("Entrée ligne" in l for l in tail_lines(LIVE, 40))


def test_follower_decodes_cp1252(tmp_path):
    p = tmp_path / "Game.log"
    p.write_bytes(b"")
    f = LogFollower(p)
    p.write_bytes("<2026-10-07T19:48:30.339Z> Entrée\n<2026-10-07T19:48:30.340Z> suite".encode("cp1252"))
    assert f.poll() == ["<2026-10-07T19:48:30.339Z> Entrée"]


def test_kinds_in_order(events):
    assert [e.kind for e in events] == [
        "build", "game_version", "environment", "login", "handle", "spawn", "shard",
        "zone", "spawn", "zone", "docking", "docking", "docking", "zone", "near_location",
        "ship_leave", "qt_target", "location", "qt_arrived", "near_location", "near_location",
        "qt_target", "location", "qt_arrived", "near_location", "ship_leave", "session_end",
    ]


def test_all_verified(events):
    assert all(e.verified for e in events)


def test_header(events):
    st = build_state(events)
    assert (st.game_version, st.build, st.environment) == ("4.10.193.11644", "12660092", "PUB")


def test_player_and_shard(events):
    st = build_state(events)
    assert st.player == "JOUEUR"
    assert st.shard == "pub_euw1b_12660092_260"


def test_qt_targets_with_vehicle(events):
    qt = [e.data for e in events if e.kind == "qt_target"]
    assert qt == [
        {"loc_id": "LOC_rs_ext_stan-magnus_jp1", "vehicle": "RSI Constellation Taurus"},
        {"loc_id": "rs_ext_nyx-pyro_jp1", "vehicle": "RSI Constellation Taurus"},
    ]


def test_qt_arrived_has_vehicle(events):
    arr = [e.data for e in events if e.kind == "qt_arrived"]
    assert arr == [{"vehicle": "RSI Constellation Taurus"}] * 2


def test_route_start_locations(events):
    assert [e.data["loc"] for e in events if e.kind == "location"] == ["Seraphim Station", "Stanton Gateway"]


def test_location_codes(events):
    assert [e.data["loc_code"] for e in events if e.kind == "near_location"] == [
        "RR_CRU_LEO", "RR_JP_StantonMagnus", "RR_JP_NyxCastra", "RR_JP_NyxPyro"]


def test_final_state(events):
    st = build_state(events)
    assert st.location == "Stanton Gateway"
    assert st.near_location == "RR_JP_NyxPyro"
    assert st.ship == "RSI Constellation Taurus"
    assert st.zone.startswith("Entered Crusader Industries Jurisdiction")


def test_medical_notification_not_a_zone(lines):
    med = next(l for l in lines if "Medical Bed" in l)
    assert recognize(med) is None


def test_audit_real_log_no_suspect(lines):
    rows = {r.kind: r for r in audit(lines)}
    assert not [r.kind for r in rows.values() if r.suspect]
    assert rows["qt_arrived"].recognized == 2


def test_audit_flags_changed_format():
    """Simule une mise à jour du jeu : marqueur conservé, texte changé."""
    changed = ["<2026-10-07T21:17:14.021Z> [Notice] <Player Selected Quantum Target - Local> "
               "Player has selected point as their destination"]
    rows = {r.kind: r for r in audit(changed)}
    assert rows["qt_target"].suspect
    assert rows["qt_target"].samples == changed


def test_vehicle_segment_optional():
    """Sans segment « | VEH[id] | », l'arrivée reste reconnue (sans vaisseau)."""
    ev = recognize("<2026-10-07T21:21:30.445Z> [Notice] <Quantum Drive Arrived - Arrived at Final Destination> "
                   "Quantum Drive has arrived at final destination")
    assert ev.kind == "qt_arrived" and ev.data == {}
