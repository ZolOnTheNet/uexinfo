"""Catalogue de contrats et reconnaissance des cartes lues dans le mobiGlas.

Catalogue FICTIF, au format de scmdb.net : les données de scmdb (CC BY-NC-ND) ne sont jamais
versionnées. Seuls les titres affichés en jeu et lus sur les captures de l'utilisateur sont repris.
"""
import json
from pathlib import Path

import pytest

from uexinfo.cache.contract_catalog import ContractCatalog, normalize
from uexinfo.ocr.contract_list import ContractCard, cards_from_words

TOTAL, TRANSPORT, DEFENSE, COLLECTION = "t-total", "t-transport", "t-defense", "t-collection"
SCOPES = {
    TOTAL: {"eventName": "Iasi", "category": None},
    TRANSPORT: {"eventName": "Iasi", "category": "Transport"},
    DEFENSE: {"eventName": "Iasi", "category": "Defense"},
    COLLECTION: {"eventName": "Iasi", "category": "Collection"},
}


def contract(title, reward, cat, pts, split=False, name=""):
    tags = [{"tag": TOTAL, "count": pts, "splitPointsForParty": split}] if cat else []
    if cat:
        tags.append({"tag": cat, "count": pts, "splitPointsForParty": split})
    return {"title": title, "debugName": name or title, "rewardUEC": reward, "completionTags": tags}


EVENT = [
    ("UCM Order (S)", 30250, COLLECTION, 183, False), ("UCM Order (M)", 42250, COLLECTION, 255, True),
    ("UCM Order (L)", 101750, COLLECTION, 486, True), ("Courier Run (Exp. E)", 51500, TRANSPORT, 417, False),
    ("Eliminate Known Outlaw", 33750, DEFENSE, 125, False), ("Clear Hostiles from Site", 56750, DEFENSE, 167, False),
    ("Recover Package from Site", 60000, TRANSPORT, 313, False),
    ("Orange Lvl. - Neutralize Threats", 179000, DEFENSE, 417, False),
    ("Orange Lvl. - Conduct Security Sweep", 106000, DEFENSE, 333, False),
    ("Yellow Lvl. - Support Ship", 44750, DEFENSE, 146, False), ("Package Recovery (Exp. E)", 46000, TRANSPORT, 313, False),
    ("Important Supply Haul", 124000, TRANSPORT, 625, False), ("Procure Refined Beryl", 176500, COLLECTION, 669, False),
    ("Ling Small Haul", 66750, TRANSPORT, 354, False), ("Ling Supply Delivery", 78500, TRANSPORT, 417, False),
    ("Critical Refuel Request ([SHIP])", 33500, TRANSPORT, 271, False),
]
DATA = {
    "version": "4.10.2-live.test",
    "eventScopes": SCOPES,
    "contracts": [contract(f"RSI Disc. Month: {t}", r, c, p, s) for t, r, c, p, s in EVENT] + [
        contract("Package Recovery", 30000, None, 0),            # contrat ordinaire, titre voisin
        contract("CRITICAL REFUEL REQUEST: [SHIP]", 145250, None, 0),
        contract("@placeholder_title", 1, None, 0),              # clé non traduite : ignorée
    ],
}


@pytest.fixture(scope="module")
def cat():
    return ContractCatalog.from_scmdb(DATA)


def test_from_scmdb(cat):
    assert len(cat) == len(EVENT) + 2
    m = next(c for c in cat.contracts if c.title.endswith("UCM Order (M)"))
    assert m.points == {"Total": 255, "Collection": 255}
    assert (m.category, m.xp, m.split_party, m.event) == ("Collection", 255, True, "Iasi")


def test_normalize_drops_xp_and_markup():
    assert normalize("RSI Disc. Month: Important Supply Haul <EM4>625 exp.</EM4>") == \
        normalize("RS/ DISC. MONTH: IMPORTANT SUPPLY HAUL 625 EXP.")


@pytest.mark.parametrize("read, expected", [
    ("RSI DISC. MONTH: UCM ORBER (M)", "RSI Disc. Month: UCM Order (M)"),          # erreur d'OCR
    ("PROCURE REFINED BERYL", "RSI Disc. Month: Procure Refined Beryl"),            # préfixe absent
    ("RS/ DISC. MONTH: LING SUPPLY DELIVERY", "RSI Disc. Month: Ling Supply Delivery"),
])
def test_match(cat, read, expected):
    c, score = cat.match(read)
    assert c.title == expected and score >= 80


def test_placeholder_and_tie_break(cat):
    """« ([SHIP]) » remplacé par le vaisseau en jeu ; l'XP et le montant lus départagent."""
    c, score = cat.match("CRITICAL REFUEL REQUEST (ORIGIN 4001)", reward=33000, xp=271)
    assert c.title == "RSI Disc. Month: Critical Refuel Request ([SHIP])" and score == 100


def test_recognize_real_cards(cat):
    fx = Path(__file__).parents[1] / "fixtures" / "ocr" / "contract_list_words_2026-10-20.json"
    res = []
    for d in json.loads(fx.read_text(encoding="utf-8")).values():
        res += cat.recognize(cards_from_words(d["words"], d["panel_w"]))
    assert len(res) == 15                         # l'en-tête « RSI DISCOVERY EVENT » est écarté
    assert all(r.recognized for r in res)
    assert all(r.xp == r.card.xp for r in res)    # XP à l'écran = points du catalogue
    courier = next(r for r in res if "Courier" in r.contract.title)
    assert courier.reward_from_catalog and courier.reward == 51500


def test_fragment_merged_with_next(cat):
    cards = [ContractCard(title="RSI DISC. MONTH: ORANGE LVL. -", raw="a"),
             ContractCard(title="NEUTRALIZE THREATS", xp=417, contractor="FOXWELL", reward=179000, raw="b")]
    [r] = cat.recognize(cards)
    assert r.contract.title.endswith("Neutralize Threats") and r.reward == 179000


def test_unrecognized_card_is_kept(cat):
    cards = [ContractCard(title="CONTRAT INCONNU DU CATALOGUE", xp=100, contractor="X", reward=10000)]
    [r] = cat.recognize(cards)
    assert not r.recognized and r.card.title.startswith("CONTRAT")


def test_from_global_ini(tmp_path):
    ini = tmp_path / "global.ini"
    ini.write_text(
        "﻿iasi_Hauling_Supply_2_Title,P=RSI Disc. Month: Important Supply Haul <EM4>625 exp.</EM4>\n"
        "iasi_RecoverItem_E_Title_001=RSI Disc. Month: Package Recovery (Exp. E) <EM4>313 exp.</EM4>\n"
        "some_Title=Texte sans XP\n"
        "iasi_Hauling_Supply_2_Desc=Hiya\n", encoding="utf-8")
    cat = ContractCatalog.from_global_ini(ini)
    assert {c.title: c.xp for c in cat.contracts} == {
        "RSI Disc. Month: Important Supply Haul": 625, "RSI Disc. Month: Package Recovery (Exp. E)": 313}
