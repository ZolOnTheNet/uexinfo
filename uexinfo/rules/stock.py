"""Quantités achetables / vendables selon le statut de stock UEX.

Statuts UEX (endpoint commodities_status) : 1 Out (0-14 %), 2 Very Low, 3 Low,
4 Medium, 5 High, 6 Very High (72-85 %), 7 Max (86-100 %).
Statut 6 (Very High) : 85 % achetable / 15 % vendable (décision D5).
Un statut inconnu retombe sur DEFAULT_MULT.
"""
from __future__ import annotations

# Part de la cargaison achetable selon le stock du terminal d'achat.
BUY_STOCK_MULT = {1: 0.0, 2: 0.2, 3: 0.4, 4: 0.6, 5: 0.8, 6: 0.85, 7: 1.0}
# Part de la cargaison vendable selon le stock du terminal de vente
# (stock vide = le terminal absorbe tout, stock plein = il n'absorbe rien).
SELL_STOCK_MULT = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.2, 6: 0.15, 7: 0.0}
DEFAULT_MULT = 0.5


def buy_quantity(ship_cargo: int, status_buy: int) -> int:
    """SCU achetables. Stock « Out » (1) au terminal d'achat ⇒ 0 (décision D1)."""
    return int(ship_cargo * BUY_STOCK_MULT.get(status_buy, DEFAULT_MULT))


def sell_quantity(qty: int, status_sell: int) -> int:
    """SCU vendables. Stock « Out » (1) au terminal de vente ⇒ toute la cargaison."""
    return int(qty * SELL_STOCK_MULT.get(status_sell, DEFAULT_MULT))
