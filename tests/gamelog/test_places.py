"""Codes de lieu du Game.log → nom affiché et système (relevés sur de vrais logs)."""
import pytest

from uexinfo.gamelog.places import place_label, system_of


@pytest.mark.parametrize("code, label, system", [
    ("RR_CRU_LEO", "Seraphim Station", "Stanton"),
    ("RR_HUR_LEO", "Everus Harbor", "Stanton"),
    ("RR_CRU_L1", "CRU-L1 Ambitious Dream Station", "Stanton"),
    ("LOC_RR_S2_L1", "CRU-L1 Ambitious Dream Station", "Stanton"),      # cible QT
    ("rs_ext_cru-leo1", "Seraphim Station", "Stanton"),
    ("RR_CRU_L2", "CRU-L2", "Stanton"),                                  # Lagrange non relevé
    ("OOC_Stanton_1c_Magda", "Magda", "Stanton"),
    ("Stanton1c_HurdynMining_HDMSHahn", "HDMS-Hahn", "Stanton"),
    ("Stanton2b_ArcCorpMining_Area141", "Daymar", "Stanton"),           # avant-poste : corps céleste
    ("Stanton4_NewBabbage", "New Babbage", "Stanton"),
    ("RR_P3_LEO", "Orbituary", "Pyro"),
    ("rs_ext_pyro3_l1", "Starlight Service Station", "Pyro"),
    ("Pyro2_Outpost_col_m_trdp_indy_001", "Monox", "Pyro"),
    ("RR_JP_PyroStanton", "Stanton Gateway", "Pyro"),                    # passerelle côté Pyro
    ("RR_JP_StantonPyro", "Pyro Gateway", "Stanton"),
    ("RR_JP_NyxPyro", "Pyro Gateway", "Nyx"),
    ("Nyx_Levski", "Levski", "Nyx"),
    ("GrimHEX", "Grim HEX", "Stanton"),
])
def test_known_codes(code, label, system):
    assert place_label(code) == label
    assert system_of(code) == system


@pytest.mark.parametrize("code", ["", "ObjectContainer_RestStop", "MISSION_QT_Beacon_9433063159502",
                                  "NavPoint_Dynamic_524995870260"])
def test_unknown_codes(code):
    assert place_label(code) == ""
    assert system_of(code) == ""
