"""Reconnaissance Game.log (parseur pur).

⚠ tests/fixtures/gamelog/format_reference.log est SYNTHÉTIQUE : lignes écrites d'après
les formats documentés (docs/ai/GAMELOG_SPEC.md), valeurs fictives. À compléter par de
vrais extraits fournis par l'utilisateur (/game extract) avant de valider les formats « S ».
"""
from pathlib import Path

import pytest

from uexinfo.gamelog.events import recognize, recognize_all
from uexinfo.gamelog.follow import LogFollower, read_lines
from uexinfo.gamelog.lines import parse_line
from uexinfo.gamelog.state import build_state

REF = Path(__file__).parent.parent / "fixtures" / "gamelog" / "format_reference.log"


@pytest.fixture(scope="module")
def events():
    return recognize_all(read_lines(REF))


def test_parse_line():
    ll = parse_line("<2026-10-01T18:00:00.100Z> [Notice] <Join PU> address[x] shard[s1]")
    assert ll.level == "Notice" and ll.category == "Join PU" and ll.message.startswith("address")
    assert parse_line("texte libre").ts is None


def test_kinds_in_order(events):
    assert [e.kind for e in events] == [
        "login", "shard", "spawn", "near_location", "ship_enter", "qt_target", "qt_arrived",
        "commodity_buy", "commodity_sell", "system_change", "notification", "zone",
        "mission_end", "death", "session_end",
    ]


def test_spam_ignored():
    assert recognize("<2026-10-01T18:01:10.000Z> [Notice] <OnEntityEnterZone> x") is None


def test_commodity_buy_details(events):
    buy = next(e for e in events if e.kind == "commodity_buy")
    assert buy.data["shop"] == "CRU_L5_SCShop-001"
    assert buy.data["price"] == 24000
    assert buy.data["scu"] == 20          # 2000 cSCU = 20 SCU
    assert not buy.verified               # format à confirmer sur un vrai log


def test_vehicle_and_target(events):
    qt = next(e for e in events if e.kind == "qt_target")
    assert qt.data == {"loc_id": "ObjectContainer_CRU_L5", "vehicle": "DRAK Cutlass Black"}


def test_state(events):
    st = build_state(events)
    assert st.player == "TestPilot"
    assert st.shard == "pub_euw1b_00000001_010"
    assert st.ship == "DRAK Cutlass Black"
    assert st.system == "Pyro"
    assert st.near_location == "Stanton2_Orison"
    assert st.zone == "Entered Pyro jurisdiction"
    assert len(st.trades) == 2 and len(st.missions) == 2
    assert st.deaths == 1


def test_debug_trace():
    seen = []
    recognize("<2026-10-01T18:01:00.000Z> [CSessionManager::OnClientSpawned] Spawned!", seen.append)
    assert seen and seen[0].startswith("[spawn]")


def test_follower_handles_growth_and_truncation(tmp_path):
    p = tmp_path / "Game.log"
    p.write_text("a\n", encoding="utf-8")
    f = LogFollower(p, from_end=True)
    assert f.poll() == []
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("b\nc")                    # « c » incomplète
    assert f.poll() == ["b"]
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("\n")
    assert f.poll() == ["c"]
    p.write_text("new\n", encoding="utf-8")   # relance du jeu : fichier tronqué
    assert f.poll() == ["new"]
    assert LogFollower(tmp_path / "absent.log").poll() == []
