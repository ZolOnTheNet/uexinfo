"""Solde du joueur : lu à l'écran, tenu à jour entre deux lectures avec le Game.log.

Le Game.log n'écrit jamais le solde (vérifié sur 342 logs, 2026-11-01) : il n'écrit que des
mouvements — récompenses (« Awarded N aUEC »), amendes (« Fined N UEC »), demandes d'achat
et de vente de marchandises, achats d'objets. Une demande refusée est suivie, en moins d'une
seconde, d'une ligne `Commodity Transaction Response Error` : elle est alors retirée.

Le solde affiché par le terminal de marchandises (« CURRENT BALANCE ») est la référence
(`uexinfo/ocr/balance.py`) ; entre deux lectures, le solde est **estimé** (≈) en ajoutant les
mouvements écrits depuis. Des écarts restent possibles (assurance, réparation, carburant,
transfert entre joueurs, demande acceptée puis annulée sans ligne) : comparé le 31/10, une
vente de 439 642 aUEC demandée n'apparaissait pas dans le solde lu cinq minutes plus tard.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_REFUSAL_WINDOW = timedelta(seconds=3)      # refus écrit < 1 s après la demande (marge)

# Événements qui déplacent de l'argent : signe du mouvement
_SIGN = {"reward": 1, "fine": -1, "commodity_buy": -1, "commodity_sell": 1, "item_buy": -1}
_LABEL = {"reward": "récompense", "fine": "amende", "commodity_buy": "achat",
          "commodity_sell": "vente", "item_buy": "achat d'objet"}


@dataclass
class Movement:
    """Un mouvement d'argent lu dans le Game.log (`ts` : UTC sans fuseau, comme le Game.log)."""
    ts: datetime
    amount: float           # positif : reçu ; négatif : dépensé
    kind: str               # reward | fine | commodity_buy | commodity_sell | item_buy

    @property
    def epoch(self) -> float:
        """Heure du mouvement en secondes (époque Unix)."""
        return self.ts.replace(tzinfo=timezone.utc).timestamp()

    @property
    def label(self) -> str:
        """Nom du mouvement en français."""
        return _LABEL.get(self.kind, self.kind)


class WalletTracker:
    """Mouvements d'argent de la session, tirés des événements du Game.log."""

    def __init__(self):
        self.moves: list[Movement] = []
        self.session_start: datetime | None = None

    def feed(self, events) -> list[Movement]:
        """Ajoute les mouvements des événements ; renvoie ceux qui sont nouveaux et non refusés."""
        new: list[Movement] = []
        for ev in events:
            if ev.ts is None:
                continue
            if ev.kind == "login":
                # nouvelle session de jeu : le gain repart de zéro
                self.session_start = ev.ts
                self.moves.clear()
                new.clear()
            elif ev.kind == "trade_refused":
                want = "commodity_sell" if ev.data.get("selling") else "commodity_buy"
                for mv in reversed(self.moves):
                    if mv.kind == want and timedelta(0) <= ev.ts - mv.ts <= _REFUSAL_WINDOW:
                        self.moves.remove(mv)
                        if mv in new:
                            new.remove(mv)
                        break
            elif ev.kind in _SIGN:
                amount = float(ev.data.get("amount") or ev.data.get("price") or 0)
                if amount:
                    mv = Movement(ev.ts, _SIGN[ev.kind] * amount, ev.kind)
                    self.moves.append(mv)
                    new.append(mv)
        return new

    def since(self, epoch: float) -> float:
        """Somme des mouvements écrits après l'instant `epoch` (secondes, époque Unix)."""
        return sum(mv.amount for mv in self.moves if mv.epoch > epoch)

    def count_since(self, epoch: float) -> int:
        """Nombre de mouvements écrits après l'instant `epoch`."""
        return sum(1 for mv in self.moves if mv.epoch > epoch)

    def session_gain(self) -> float:
        """Gain de la session : ventes + récompenses − achats − amendes (mouvements lus)."""
        return sum(mv.amount for mv in self.moves)


def estimate(balance: int, balance_ts: float, tracker: WalletTracker | None) -> tuple[int, bool]:
    """Solde à afficher : (montant, estimé ?). Lu à l'écran, plus les mouvements écrits depuis."""
    if not balance:
        return 0, False
    if tracker is None or not tracker.count_since(balance_ts):
        return balance, False
    return round(balance + tracker.since(balance_ts)), True


def fmt(amount: float) -> str:
    """« 11 369 305 aUEC » (espaces fines entre milliers, signe pour un négatif)."""
    return f"{amount:,.0f} aUEC".replace(",", " ")
