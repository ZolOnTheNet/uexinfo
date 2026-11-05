"""Meilleur lot de contrats de transport pour un vaisseau (règle pure, testée).

Parmi les offres lues (`ocr/contract_watch.OffersBoard`), choisir celles qui rapportent le plus
en tenant dans la soute : somme des SCU ≤ capacité, au plus `max_destinations` lieux de livraison
distincts (le vrai coût d'un lot : plusieurs contrats vers la même station n'en font qu'une), au
plus 10 contrats (limite du jeu), caisses de la mission pas plus grandes que la plus grande caisse
que le vaisseau peut charger. Sac à dos 0/1 sur les SCU (programmation dynamique), refait pour
chaque groupe possible de destinations quand le plafond de destinations s'applique.

SCU d'une offre : le total des livraisons lu dans le détail (exact) ; sinon le maximum du
catalogue scmdb (`scu_max`, estimé, pris au plus grand pour ne jamais dépasser la soute).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations

MAX_CONTRACTS = 10          # contrats acceptés à la fois dans le jeu (« ACCEPTED (0/10) »)
_MAX_GROUPS = 2000          # groupes de destinations essayés au plus (au-delà : les plus fréquentes)


def place_key(name: str) -> str:
    """Lieu de livraison comparable malgré l'OCR : « Shallow Fields Station above Crusader's L4… »
    et « Shallow Fields above Crusader » → « shallow fields »."""
    base = re.split(r"\s+above\s+|\s+at\s+", name or "", maxsplit=1, flags=re.I)[0]
    base = re.sub(r"\bstation\b|[^\w\s-]", " ", base, flags=re.I)
    return " ".join(base.lower().split())


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

    @property
    def dest_keys(self) -> frozenset:
        """Destinations de l'offre ; inconnues (détail non lu) : une destination propre à l'offre."""
        keys = {place_key(d) for d in self.drops if place_key(d)}
        return frozenset(keys) if keys else frozenset({f"?{self.title}|{self.reward}"})


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

    @property
    def destinations(self) -> list[str]:
        """Lieux de livraison distincts du lot (nom lu le premier) ; « ? » par offre au détail non lu."""
        seen: dict[str, str] = {}
        for i in self.items:
            if not i.drops:
                seen[f"?{i.title}|{i.reward}"] = "?"
            for d in i.drops:
                seen.setdefault(place_key(d), d)
        return list(seen.values())


def _knapsack(cands: list[LotItem], cap: int, kmax: int) -> tuple[int, int, tuple]:
    """(gain, SCU, indices) du meilleur choix : SCU ≤ cap, kmax offres au plus ; à gain égal, le moins de SCU."""
    # même résultat, moins de calcul : pas plus d'offres que de candidates, pas plus de SCU que
    # leur total (une soute de 1 440 SCU pour 3 offres de 8 SCU : 24 colonnes au lieu de 1 441)
    kmax = min(kmax, len(cands))
    cap = min(cap, sum(int(it.scu) for it in cands))
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
    return max((best[k][cap] for k in range(kmax + 1)), key=lambda t: (t[0], -t[1]))


def best_lot(items: list[LotItem], capacity: int, max_count: int = MAX_CONTRACTS,
             max_container: int | None = None, max_destinations: int | None = None) -> Lot:
    """Lot au gain maximal tenant dans `capacity` SCU, `max_count` contrats au plus (limite du jeu)
    et `max_destinations` lieux de livraison distincts au plus (None = sans limite).

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
        elif max_destinations and len(it.dest_keys) > max_destinations:
            left_out.append((it, f"{len(it.dest_keys)} destinations à elle seule (plafond {max_destinations})"))
        else:
            cands.append(it)

    cap, kmax = max(0, int(capacity)), max(0, int(max_count))
    universe = sorted({k for it in cands for k in it.dest_keys},
                      key=lambda k: -sum(k in it.dest_keys for it in cands))
    if not max_destinations or len(universe) <= max_destinations:
        top = _knapsack(cands, cap, kmax)
        chosen = [cands[i] for i in top[2]]
    else:
        # chaque groupe de N destinations : les offres qui n'en sortent pas, puis le sac à dos
        n = max_destinations
        while n < len(universe) and _ncr(len(universe), n) > _MAX_GROUPS:
            universe = universe[:-1]                       # trop de lieux : les plus rares sont laissés
        top, chosen, done = (0, 0, ()), [], set()
        for group in combinations(universe, n):
            g = set(group)
            sub = [it for it in cands if it.dest_keys <= g]
            key = frozenset(id(it) for it in sub)
            if not sub or key in done:
                continue
            done.add(key)
            res = _knapsack(sub, cap, kmax)
            if (res[0], -res[1]) > (top[0], -top[1]):
                top, chosen = res, [sub[i] for i in res[2]]
    for it in cands:
        if it not in chosen:
            why = "ne tient plus dans la soute"
            if max_destinations:
                why += f" ou ajouterait trop de destinations (plafond {max_destinations})"
            left_out.append((it, why))
    chosen.sort(key=lambda i: -i.per_scu)
    return Lot(chosen, cap, left_out)


def _ncr(n: int, r: int) -> int:
    """Nombre de groupes de r éléments parmi n."""
    from math import comb
    return comb(n, r)
