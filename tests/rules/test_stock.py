"""Décision D1 (docs/ai/DECISIONS.md) — quantités selon le statut de stock UEX."""
import pytest

from uexinfo.rules.stock import buy_quantity, sell_quantity


def test_buy_out_of_stock_gives_zero():
    # D1 : stock « Out » au terminal d'achat ⇒ rien à acheter (plus de repli cargo plein)
    assert buy_quantity(96, 1) == 0


@pytest.mark.parametrize("status,expected", [(2, 19), (3, 38), (4, 57), (5, 76), (7, 96)])
def test_buy_quantity_by_status(status, expected):
    assert buy_quantity(96, status) == expected


def test_buy_unknown_status_uses_default():
    # Statut 6 non encore tranché (D5) : comportement inchangé = 0.5
    assert buy_quantity(96, 6) == 48
    assert buy_quantity(96, 0) == 48


def test_sell_out_of_stock_sells_everything():
    # D1 : stock « Out » au terminal de vente ⇒ toute la cargaison
    assert sell_quantity(96, 1) == 96


@pytest.mark.parametrize("status,expected", [(2, 76), (3, 57), (4, 38), (5, 19), (7, 0)])
def test_sell_quantity_by_status(status, expected):
    assert sell_quantity(96, status) == expected
