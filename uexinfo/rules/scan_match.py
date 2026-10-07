"""Quel terminal homonyme a été scanné ? (« Pyro Gateway » côté Stanton ou côté Nyx)

SC-Datarunner ne donne que le nom affiché à l'écran, identique pour les
terminaux homonymes de systèmes différents. On compare donc le scan aux prix
UEX de chaque candidat. Pur, sans I/O.

Score = (nombre de marchandises scannées que le terminal propose dans ce mode,
         −écart de prix relatif moyen sur ces marchandises).
Le meilleur score l'emporte ; égalité stricte ⇒ None (on garde l'ordre du résolveur,
qui préfère déjà le système du joueur).
"""
from __future__ import annotations

from uexinfo.names import norm


def match_score(scanned: list[tuple[str, int]], rows: list[dict], mode: str) -> tuple[int, float]:
    key = "price_sell" if mode == "sell" else "price_buy"
    uex = {norm(r.get("commodity_name")): float(r.get(key) or 0) for r in rows if r.get(key)}
    hits, gaps = 0, []
    for name, price in scanned:
        ref = uex.get(norm(name))
        if ref is None:
            continue
        hits += 1
        if price and ref:
            gaps.append(abs(price - ref) / ref)
    return hits, -(sum(gaps) / len(gaps)) if gaps else 0.0


def best_terminal(candidates: list, scanned: list[tuple[str, int]], mode: str, prices_of) -> object | None:
    """Candidat dont les prix UEX collent le mieux au scan ; None si indécidable."""
    if len(candidates) < 2 or not scanned:
        return None
    scored = [(match_score(scanned, prices_of(t) or [], mode), i, t) for i, t in enumerate(candidates)]
    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    if scored[0][0] == scored[1][0]:
        return None
    return scored[0][2]
