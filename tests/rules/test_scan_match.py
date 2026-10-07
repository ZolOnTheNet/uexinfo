"""Quel « Pyro Gateway » a été scanné ? Prix UEX réels (octobre 2026) vs vrai scan Datarunner."""
from dataclasses import dataclass

from uexinfo.rules.scan_match import best_terminal, match_score

@dataclass(frozen=True)
class T:
    name: str


NYX = T("Admin - Pyro Gateway (Nyx)")
STANTON = T("Admin - Pyro Gateway (Stanton)")
# Ce que chaque gateway rachète chez UEX (extrait réel)
SELLS = {
    NYX: [{"commodity_name": n, "price_sell": p} for n, p in [
        ("Construction Materials", 12000), ("Distilled Spirits", 1900), ("Gold", 31000),
        ("Organics", 11000), ("Recycled Material Composite", 7100), ("Tin", 4000), ("Waste", 370)]],
    STANTON: [{"commodity_name": n, "price_sell": p} for n, p in [
        ("Construction Materials", 11500), ("Distilled Spirits", 1850), ("Medical Supplies", 3000),
        ("Quartz", 1500), ("Scrap", 900)]],
}
# Scan de vente lu dans le log Datarunner réel (tests/fixtures/datarunner/…pyro_gateway_nyx.log)
SCAN_SELL = [("Distilled Spirits", 1900), ("Recycled Material Composite", 7100), ("Construction Materials", 12000)]


def test_match_score():
    assert match_score(SCAN_SELL, SELLS[NYX], "sell") == (3, 0.0)
    hits, gap = match_score(SCAN_SELL, SELLS[STANTON], "sell")
    assert hits == 2 and gap < 0


def test_sell_scan_points_to_nyx_side():
    assert best_terminal([STANTON, NYX], SCAN_SELL, "sell", SELLS.get) is NYX


def test_undecidable_returns_none():
    same = {NYX: SELLS[NYX], STANTON: SELLS[NYX]}
    assert best_terminal([STANTON, NYX], SCAN_SELL, "sell", same.get) is None
    assert best_terminal([NYX], SCAN_SELL, "sell", SELLS.get) is None
