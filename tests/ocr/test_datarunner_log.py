"""Log SC-Datarunner-UEX RÉEL (07/10/2026, Pyro Gateway côté Nyx) — et résistance aux
changements de format (une mise à jour a ajouté `uex_name=`, ce qui cassait tout)."""
from pathlib import Path

import pytest

from uexinfo.ocr.log_parser import _group_scans, _parse_commodity_line, parse_terminal_line

LOG = Path(__file__).parents[1] / "fixtures" / "datarunner" / "app_2026-10-07_pyro_gateway_nyx.log"


@pytest.fixture(scope="module")
def scans():
    lines = LOG.read_text(encoding="utf-8").splitlines(keepends=True)
    results, *_ = _group_scans(lines)
    return results


def test_two_validated_scans(scans):
    assert [(s.terminal, s.mode, s.validated, len(s.commodities)) for s in scans] == [
        ("Pyro Gateway", "buy", True, 8),
        ("Pyro Gateway", "sell", True, 4),
    ]


def test_buy_values(scans):
    buy = {c.name: c for c in scans[0].commodities}
    c = buy["Ship Ammunition - Size 1"]
    assert (c.commodity_id, c.price, c.quantity, c.stock_status) == (201, 6868, 12000, 7)
    assert (c.name_confidence, c.quantity_confidence, c.stock_confidence, c.price_confidence) == (96, 99, 100, 95)
    assert buy["Quantum Fuel"].price == 1760


def test_sell_values_keep_low_confidence(scans):
    sell = {c.name: c for c in scans[1].commodities}
    rmc = sell["Recycled Material Composite"]
    assert (rmc.price, rmc.quantity, rmc.quantity_confidence) == (7100, 1248, 10)   # qty OCR douteuse
    assert sell["Construction Materials"].quantity == 61


def test_terminal_line_takes_canonical_name():
    line = "2026-10-07 23:56:23,714 - image_processing.data_extractor - INFO - Matched terminal: 'Pyro Gateway' -> Pyro Gateway"
    assert parse_terminal_line(line) == "Pyro Gateway"
    assert parse_terminal_line("x - image_processing.data_extractor - INFO - Matched terminal: 'Area 18'") == "Area 18"
    assert parse_terminal_line("x - image_processing.data_extractor - INFO - Matched terminal: GrimHEX") == "GrimHEX"


# ── Résistance aux futures mises à jour de Datarunner ─────────────────────────
BASE = ("2026-10-07 23:56:31,666 - image_processing.data_extractor - INFO - Extracted commodity: "
        "CommodityData({fields})")


@pytest.mark.parametrize("fields", [
    # format d'octobre 2026 (avec uex_name)
    "name=StrConfidence(value='Gold', confidence=90), id=33, uex_name='Gold', quantity=IntConfidence(value=250, confidence=99), "
    "stock=StrConfidence(value='max inventory', confidence=100), stock_status=IntConfidence(value=7, confidence=100), "
    "price=IntConfidence(value=31000, confidence=97), examined_words=5",
    # format précédent (sans uex_name)
    "name=StrConfidence(value='Gold', confidence=90), id=33, quantity=IntConfidence(value=250, confidence=99), "
    "stock=StrConfidence(value='max inventory', confidence=100), stock_status=IntConfidence(value=7, confidence=100), "
    "price=IntConfidence(value=31000, confidence=97), examined_words=5",
    # champs réordonnés + champ inconnu ajouté
    "price=IntConfidence(value=31000, confidence=97), new_field=FloatConfidence(value=1.5, confidence=3), id=33, "
    "stock_status=IntConfidence(value=7, confidence=100), name=StrConfidence(value='Gold', confidence=90), "
    "quantity=IntConfidence(value=250, confidence=99), stock=StrConfidence(value='max inventory', confidence=100)",
])
def test_commodity_line_format_variants(fields):
    c = _parse_commodity_line(BASE.format(fields=fields))
    assert (c.name, c.commodity_id, c.quantity, c.stock_status, c.price) == ("Gold", 33, 250, 7, 31000)
    assert c.price_confidence == 97


def test_none_values_and_apostrophes():
    c = _parse_commodity_line(BASE.format(fields=
        "name=StrConfidence(value='E\\'tam', confidence=80), id=30, quantity=IntConfidence(value=None, confidence=0), "
        "stock=StrConfidence(value='', confidence=0), stock_status=IntConfidence(value=None, confidence=0), "
        "price=IntConfidence(value=None, confidence=0)"))
    assert c.name == "E'tam" and c.quantity is None and c.price == 0 and c.stock_status == 0


def test_old_dict_format_still_read():
    line = ("2026-04-01 10:00:00,000 - image_processing.data_extractor - INFO - Extracted commodity: "
            "{'name': 'Gold', 'id': 33, 'quantity': 250, 'stock': 'max inventory', 'stock_status': 7, 'price': 31000}")
    c = _parse_commodity_line(line)
    assert (c.name, c.price) == ("Gold", 31000)


def test_unrelated_line_ignored():
    assert _parse_commodity_line("2026-10-07 - image_processing.data_extractor - INFO - Extracted commodity: Gold") is None


def test_reported_count_reveals_unlogged_corrections(scans):
    # Achats : 4 + 4 rapports envoyés = 8 marchandises lues → complet.
    assert scans[0].reported_count == 8 and not scans[0].log_incomplete
    # Ventes : 5 + 3 rapports envoyés (Waste, Tin, Organics, Gold ajoutés à la main
    # dans Datarunner) mais seulement 4 marchandises dans le log → incomplet.
    assert scans[1].reported_count == 8 and scans[1].log_incomplete
