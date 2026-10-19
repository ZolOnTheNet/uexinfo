"""Game.log RÉEL (LIVE 4.10, 2026-10-19) : Everus Harbor → CRU-L1, crash dans le hangar, mort,
réapparition à Seraphim, Hull B vers HDMS-Hahn (Magda), mort sans cause loggée, retour au menu,
reconnexion sur un autre shard.

Extrait anonymisé (pseudo → JOUEUR, équipier → EQUIPIER, geid/accountId/IP remplacés) :
tests/fixtures/gamelog/live_4.10_crash_cru_l1.log.
"""
from pathlib import Path

import pytest

from uexinfo.gamelog.events import audit, recognize_all
from uexinfo.gamelog.follow import read_lines
from uexinfo.gamelog.state import GameState, build_state

LIVE = Path(__file__).parent.parent / "fixtures" / "gamelog" / "live_4.10_crash_cru_l1.log"


@pytest.fixture(scope="module")
def events():
    return recognize_all(read_lines(LIVE))


def _state_at(events, hhmmss: str) -> GameState:
    """État après les événements jusqu'à l'heure UTC donnée (incluse)."""
    st = GameState()
    for ev in events:
        if ev.ts and ev.ts.strftime("%H:%M:%S") > hhmmss:
            break
        st.apply(ev)
    return st


def test_new_kinds_verified(events):
    kinds = {e.kind for e in events}
    assert {"menu", "crash", "player_dead", "down"} <= kinds
    assert all(e.verified for e in events)


def test_crash(events):
    crash = next(e for e in events if e.kind == "crash")
    assert crash.data == {"vehicle": "RSI Constellation Taurus GS",
                          "zone": "StreamingSOC_hangar_medfrnt_001_rest_occu", "player_pilot": True}


def test_only_body_item_marks_down(events):
    """Une ligne par objet mis en récupération : seul le corps produit un événement."""
    assert [e.ts.strftime("%H:%M:%S") for e in events if e.kind == "down"] == ["19:41:48"]


def test_menu_spawns_ignored(events):
    st = build_state(events)
    assert st.counts["spawn"] == 6          # 2 dans le menu (lancement, déconnexion) + 4 en jeu
    assert st.counts["menu"] == 2
    assert not st.in_menu
    assert st.session_start.strftime("%H:%M:%S") == "19:54:49"   # 1re apparition sur le nouveau shard


def test_two_deaths(events):
    st = build_state(events)
    assert st.deaths == 2                   # crash du Taurus + mort à HDMS-Hahn (confirmée par la réapparition)


def test_crash_and_death_counted_once():
    """Mort dans le vaisseau détruit puis objets en récupération : une seule mort."""
    st = GameState(player="JOUEUR")
    evs = recognize_all([
        "<2026-10-19T18:53:50.481Z> [Notice] <[ActorState] Dead> [ACTOR STATE] Actor 'JOUEUR' [1] ejected from zone 'X' [2] to zone 'Y' [3] due to previous zone being in a destroyed vehicle with detached interior.",
        "<2026-10-19T18:53:55.000Z> [Notice] <Adding non kept item [CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement]> Item 'body_01_noMagicPocket_1 - Class(body_01_noMagicPocket)'",
        "<2026-10-19T18:54:11.992Z> [CSessionManager::OnClientSpawned] Spawned!",
    ])
    for ev in evs:
        st.apply(ev)
    assert st.deaths == 1


def test_location_follows_jumps_and_respawns(events):
    assert _state_at(events, "18:48:44").location == "Everus Harbor"        # départ du saut
    st = _state_at(events, "18:51:34")                                      # arrivée du saut
    assert (st.location, st.qt_target) == ("CRU-L1 Ambitious Dream Station", "")
    st = _state_at(events, "18:53:50")                                      # crash : plus de vaisseau
    assert st.ship == "" and st.location == "CRU-L1 Ambitious Dream Station"
    assert _state_at(events, "18:54:14").location == "Seraphim Station"     # réapparition
    assert _state_at(events, "19:35:07").location == "Magda"                # Hull B arrivé
    assert _state_at(events, "19:37:11").location == "HDMS-Hahn"            # avant-poste
    assert _state_at(events, "19:42:05").location == "Seraphim Station"     # réapparition


def test_final_state(events):
    st = build_state(events)
    assert st.system == "Stanton"
    assert st.shard == "pub_ape1a_12881860_040"
    assert st.ship == "MISC Hull B"
    assert st.zone == "Entered Crusader Industries Jurisdiction"


def test_mission_notifications_cleaned(events):
    texts = [e.data["text"] for e in events if e.kind == "notification"]
    assert texts[0] == "Contract Accepted: RSI Disc. Month: Important Supply Haul 625 exp."
    assert texts[1] == "New Objective: Deliver 0/128 SCU of Ship Decoy Countermeasures to Teasa Spaceport"
    assert "Contract Shared: RSI Disc. Month: Procure Refined Iron 408 exp." in texts


def test_mission_end_real_line():
    """Vraie ligne (2026-10-19, contrat « Procure Refined Iron » terminé), anonymisée."""
    ev = recognize_all([
        "<2026-10-19T20:10:12.717Z> [Notice] <EndMission> Ending mission for player. "
        "MissionId[7cb9a79d-cb89-4499-b912-77f7710106cd] Player[JOUEUR] PlayerId[100000000001] "
        "CompletionType[Complete] Reason[Mission Ended] [Team_MissionFeatures][Missions]"])[0]
    assert ev.kind == "mission_end" and ev.verified
    assert ev.data == {"mission_id": "7cb9a79d-cb89-4499-b912-77f7710106cd", "completion": "Complete"}


def test_contract_failed_notification():
    """Vraie ligne (2026-10-19, « Defend Ship » échoué)."""
    ev = recognize_all([
        '<2026-10-19T20:19:30.512Z> [Notice] <SHUDEvent_OnNotification> Added notification '
        '"Contract Failed: RSI Disc. Month: Orange Lvl. - Defend Ship <EM4>208 exp.</EM4>: " [190] to queue. '
        'New queue size: 1, MissionId: [18f15049-0000-0000-0000-000000000000], ObjectiveId: [] '
        '[Team_CoreGameplayFeatures][Missions][Comms]'])[0]
    assert ev.kind == "notification"
    assert ev.data["text"] == "Contract Failed: RSI Disc. Month: Orange Lvl. - Defend Ship 208 exp."


def test_audit_no_suspect():
    rows = {r.kind: r for r in audit(read_lines(LIVE))}
    assert not [r.kind for r in rows.values() if r.suspect]
    assert rows["down"].recognized == 1
