"""Liste des contrats du mobiGlas : mots OCR RÉELS (captures du 2026-10-20, 2560×1440, traduction
Stelliverse active) → cartes. Le jeu de test contient les mots lus et leurs positions, pas les images :
ni Tesseract ni captures ne sont nécessaires."""
import json
from pathlib import Path

import pytest

from uexinfo.ocr.contract_list import cards_from_words, parse_reward

FX = Path(__file__).parents[1] / "fixtures" / "ocr" / "contract_list_words_2026-10-20.json"


@pytest.fixture(scope="module")
def shots():
    data = json.loads(FX.read_text(encoding="utf-8"))
    return [cards_from_words(d["words"], d["panel_w"]) for d in data.values()]


@pytest.mark.parametrize("token, value", [("124k", 124000), ("42k", 42000), ("1.5k", 1500),
                                          ("¤60k", 60000), ("6m", None), ("48s", None), ("EXP.", None)])
def test_parse_reward(token, value):
    assert parse_reward(token) == value


def test_card_count(shots):
    # 1re capture : en-tête « RSI DISCOVERY EVENT 27 » + 7 cartes ; 2e : 8 cartes
    assert [len(s) for s in shots] == [8, 8]


def test_xp_read_from_titles(shots):
    assert [c.xp for c in shots[0][1:]] == [255, 183, 486, 417, 125, 167, 313]
    assert [c.xp for c in shots[1]] == [417, 333, 146, 313, 625, 669, 354, 417]


def test_title_and_contractor_split(shots):
    supply = next(c for c in shots[1] if "SUPPLY HAUL" in c.title)
    assert supply.title == "RSI DISC. MONTH: IMPORTANT SUPPLY HAUL"
    assert supply.contractor == "COVALEX"
    assert supply.reward == 124000


def test_card_cut_at_top_is_one_card(shots):
    """« Orange Lvl. - » en haut de l'écran et « Neutralize Threats » sur la ligne suivante."""
    first = shots[1][0]
    assert first.title == "RSI DISC. MONTH: ORANGE LVL. - NEUTRALIZE THREATS"
    assert first.reward == 179000


def test_timer_not_taken_for_reward(shots):
    clear = next(c for c in shots[0] if "CLEAR HOSTILES" in c.title)
    assert clear.reward is None          # « 6m 48s » lu, « 56k » non lu : pas de confusion
    assert clear.timer.startswith("6m")
