"""Meilleur lot de contrats de transport pour un vaisseau (règle pure, testée).

Parmi les offres lues (`ocr/contract_watch.OffersBoard`), choisir celles qui rapportent le plus
en tenant dans la soute : somme des SCU ≤ capacité, au plus `max_count` contrats (le jeu en
accepte 10 à la fois), caisses de la mission pas plus grandes que la plus grande caisse que le
vaisseau peut charger. Sac à dos 0/1 sur les SCU (programmation dynamique).

SCU d'une offre : le total des livraisons lu dans le détail (exact) ; sinon le maximum du
catalogue scmdb (`scu_max`, estimé, pris au plus grand pour ne jamais dépasser la soute).
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_CONTRACTS = 10          # contrats acceptés à la fois dans le jeu (« ACCEPTED (0/10) »)


@dataclass
class LotItem:
    """Une offre candidate."""
    key: tuple
    title: str
    reward: int
    scu: int | None             # SCU retenus pour la soute (exact ou estimé), None si inconnus
    exact: bool = False         # SCU lus dans le détail de l'offre
    container: int | None = None  # plus grande caisse de la mission (SCU)
    pickups: list[str] = field(default_factory=list)
    drops: list[str] = field(default_factory=list)

    @property
    def per_scu(self) -> float:
        """aUEC par SCU transporté."""
        return self.reward / self.scu if self.scu else 0.0


@dataclass
class Lot:
    """Résultat : offres choisies, totaux, et offres écartées avec leur raison."""
    items: list[LotItem]
    capacity: int
    left_out: list[tuple[LotItem, str]] = field(default_factory=list)

    @property
    def scu(self) -> int:
        """SCU occupés par le lot."""
        return sum(i.scu or 0 for i in self.items)

    @property
    def reward(self) -> int:
        """Gain total du lot."""
        return sum(i.reward for i in self.items)

    @property
    def estimated(self) -> bool:
        """Vrai si au moins une offre du lot a des SCU estimés (catalogue, détail non lu)."""
        return any(not i.exact for i in self.items)

    @property
    def pickups(self) -> list[str]:
        """Lieux de collecte du lot, sans doublon, dans l'ordre d'apparition."""
        return list(dict.fromkeys(p for i in self.items for p in i.pickups))


def best_lot(items: list[LotItem], capacity: int, max_count: int = MAX_CONTRACTS,
             max_container: int | None = None) -> Lot:
    """Lot au gain maximal tenant dans `capacity` SCU, `max_count` contrats au plus.

    À gain égal, le lot qui occupe le moins de SCU. `max_container` : plus grande caisse
    chargeable par le vaisseau (None = pas de contrôle).
    """
    left_out: list[tuple[LotItem, str]] = []
    cands: list[LotItem] = []
    for it in items:
        if not it.reward:
            left_out.append((it, "montant inconnu"))
        elif not it.scu:
            left_out.append((it, "SCU inconnus (clique l'offre pour lire son détail)"))
        elif max_container and it.container and it.container > max_container:
            left_out.append((it, f"caisses de {it.container} SCU, le vaisseau en charge {max_container} au plus"))
        elif it.scu > capacity:
            left_out.append((it, f"{it.scu} SCU, plus que la soute ({capacity})"))
        else:
            cands.append(it)

    cap, kmax = max(0, int(capacity)), max(0, int(max_count))
    # best[k][c] = (gain, scu, indices) avec k contrats et c SCU au plus
    best = [[(0, 0, ())] * (cap + 1) for _ in range(kmax + 1)]
    for idx, it in enumerate(cands):
        w, v = int(it.scu), int(it.reward)
        for k in range(kmax, 0, -1):
            prev, row = best[k - 1], best[k]
            for c in range(cap, w - 1, -1):
                g, s, sel = prev[c - w]
                cand = (g + v, s + w, sel + (idx,))
                cur = row[c]
                if cand[0] > cur[0] or (cand[0] == cur[0] and cand[1] < cur[1]):
                    row[c] = cand
    top = max((best[k][cap] for k in range(kmax + 1)), key=lambda t: (t[0], -t[1]))
    chosen = [cands[i] for i in top[2]]
    for it in cands:
        if it not in chosen:
            left_out.append((it, "ne tient plus dans la soute (ou 10 contrats déjà)"))
    chosen.sort(key=lambda i: -i.per_scu)
    return Lot(chosen, cap, left_out)
