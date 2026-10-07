"""Décision D2 (docs/ai/DECISIONS.md) — risque de stock à la vente, demi-vie 1 h."""
import pytest

from uexinfo.rules.risk import age_hours, sell_risk


@pytest.mark.parametrize("status,age,expected", [
    # Out : tend vers 0 si frais, vers 50 si vieux
    (1, 0, 0), (1, 0.5, 15), (1, 1, 25), (1, 2, 38), (1, 4, 47),
    # Max : tend vers 100 si frais, vers 50 si vieux
    (7, 0, 100), (7, 0.5, 85), (7, 1, 75), (7, 2, 62), (7, 4, 53),
    # Moyen : toujours 50
    (4, 0, 50), (4, 3, 50),
])
def test_sell_risk_reference_table(status, age, expected):
    assert sell_risk(status, age) == expected


def test_status_6_between_high_and_max():
    assert sell_risk(5, 0) == 67
    assert sell_risk(6, 0) == 83


@pytest.mark.parametrize("status,age", [(0, 0), (8, 0), (7, None), (1, None)])
def test_unknown_gives_50(status, age):
    assert sell_risk(status, age) == 50


def test_age_hours():
    assert age_hours(None) is None
    assert age_hours(0) is None
    assert age_hours(1000, now=1000 + 5400) == 1.5
