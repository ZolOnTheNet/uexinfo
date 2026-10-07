"""Risque de ne pas écouler une marchandise au terminal de vente (décision D2).

Le statut de stock observé pèse d'autant moins que la donnée vieillit
(paliers de réassort ~8-10 min, réassort lent et variable) :

    base(statut) = (statut - 1) / 6 × 100      Out=0 … Max=100
    fiabilité(t) = 0,5 ^ (t / HALF_LIFE_H)      t = âge en heures
    risque       = fiabilité × base + (1 - fiabilité) × 50

Statut inconnu ou donnée sans date ⇒ 50 (on ne sait rien).
"""
from __future__ import annotations

import time

HALF_LIFE_H = 1.0      # D2 : demi-vie validée par l'utilisateur
UNKNOWN_RISK = 50.0    # risque quand l'information n'apporte plus rien
_STATUS_MIN, _STATUS_MAX = 1, 7


def status_base_risk(status: int) -> float | None:
    """0 pour Out (1), 100 pour Max (7), linéaire entre. None si statut inconnu."""
    if not _STATUS_MIN <= status <= _STATUS_MAX:
        return None
    return (status - _STATUS_MIN) / (_STATUS_MAX - _STATUS_MIN) * 100


def reliability(age_h: float | None) -> float:
    """Poids de l'information selon son âge : 1 à 0 h, 0,5 à HALF_LIFE_H, → 0."""
    if age_h is None:
        return 0.0
    return 0.5 ** (max(0.0, age_h) / HALF_LIFE_H)


def sell_risk(status_sell: int, age_h: float | None) -> int:
    """Risque (0-100) de saturation au terminal de vente."""
    base = status_base_risk(status_sell)
    if base is None:
        return int(UNKNOWN_RISK)
    w = reliability(age_h)
    return round(w * base + (1 - w) * UNKNOWN_RISK)


def age_hours(ts, now: float | None = None) -> float | None:
    """Âge en heures d'un horodatage epoch (None/0 ⇒ None)."""
    if not ts:
        return None
    now = time.time() if now is None else now
    return (now - float(ts)) / 3600
