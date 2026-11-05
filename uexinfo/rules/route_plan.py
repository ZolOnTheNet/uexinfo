"""Chemin le plus court en temps pour livrer des contrats de transport (règle pure, testée).

Chaque livraison (`Leg`) se charge à un lieu et se livre à un autre : charger avant de livrer,
jamais plus de cargaison que la soute. Le chemin compte le **temps**, pas la distance seule :
vol quantique (distance / vitesse QT), un temps fixe par arrêt (atterrir, hangar, décoller ;
3 min par défaut, `[contracts] stop_minutes`), et la manutention (8 SCU par voyage de chariot,
25 s chacun : 190 SCU ≈ 10 min, chiffres de `/voyage`). Une station de plus coûte souvent plus
cher que quelques Gm.

Un même lieu peut revenir dans le chemin (A charge à X pour Y, B charge à Y pour X). À chaque
arrêt on livre tout ce qui est à bord pour ce lieu, puis on charge ce qui tient. Recherche
exhaustive avec élagage (borne : temps de manutention restant), plafonnée à `budget` essais ;
au-delà, le meilleur chemin trouvé est gardé et signalé comme approché.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

QD_SPEED_GM_PER_S = 0.2341     # même valeur que models/transport_network.py (mesurée, SC 4.x)
STOP_S = 180.0                 # temps fixe d'un arrêt (validé par le joueur le 2026-11-05)
SCU_PER_TRIP = 8               # SCU par voyage de chariot
TRIP_S = 25.0                  # secondes par voyage de chariot
UNKNOWN_S = 1800.0             # trajet inconnu : compté 30 min, et signalé


def handling_s(scu: float) -> float:
    """Temps pour charger (ou décharger) `scu` SCU."""
    return math.ceil(max(0.0, scu) / SCU_PER_TRIP) * TRIP_S if scu else 0.0


@dataclass
class Leg:
    """Une livraison : `scu` SCU de `commodity` chargés à `pickup`, livrés à `drop` (nœuds).
    `pickup` None : déjà à bord."""
    key: object
    label: str
    drop: str
    pickup: str | None = None
    scu: float = 0.0
    commodity: str = ""


@dataclass
class Stop:
    """Un arrêt du chemin : livraisons puis chargements à `node`."""
    node: str
    unload: list[Leg] = field(default_factory=list)
    load: list[Leg] = field(default_factory=list)
    travel_s: float | None = None      # vol depuis l'arrêt précédent (None : trajet inconnu)
    distance_gm: float | None = None
    handle_s: float = 0.0              # arrêt + manutention
    cargo_after: float = 0.0

    def load_order(self, stops: list["Stop"]) -> list[Leg]:
        """Chargements dans l'ordre où les mettre en soute : ce qui sera livré en dernier d'abord."""
        when = {id(l): i for i, s in enumerate(stops) for l in s.unload}
        return sorted(self.load, key=lambda l: -when.get(id(l), 0))


@dataclass
class Route:
    """Résultat : arrêts dans l'ordre, temps, livraisons écartées et pourquoi."""
    stops: list[Stop]
    start: str | None
    end: str | None = None
    end_travel_s: float | None = None
    left_out: list[tuple[Leg, str]] = field(default_factory=list)
    exhaustive: bool = True

    @property
    def flight_s(self) -> float:
        """Temps de vol (trajets inconnus comptés `UNKNOWN_S`)."""
        legs = [s.travel_s for s in self.stops] + ([self.end_travel_s] if self.end else [])
        return sum(UNKNOWN_S if t is None else t for t in legs)

    @property
    def handle_s(self) -> float:
        """Arrêts et manutention."""
        return sum(s.handle_s for s in self.stops)

    @property
    def total_s(self) -> float:
        """Durée totale estimée."""
        return self.flight_s + self.handle_s

    @property
    def unknown(self) -> bool:
        """Vrai si un trajet du chemin n'a pas de distance connue."""
        return any(s.travel_s is None for s in self.stops) or (bool(self.end) and self.end_travel_s is None)


def plan(start: str | None, legs: list[Leg], distance: Callable[[str, str], float | None],
         capacity: float = math.inf, end: str | None = None, stop_s: float = STOP_S,
         qd_speed: float = QD_SPEED_GM_PER_S, budget: int = 30_000) -> Route:
    """Chemin le plus rapide qui fait toutes les livraisons `legs`, depuis `start` (None : au
    premier arrêt), en finissant à `end` (None : où l'on veut). `distance(a, b)` : Gm, None
    si inconnue."""
    left_out: list[tuple[Leg, str]] = []
    todo: list[Leg] = []
    for l in legs:
        if not l.drop:
            left_out.append((l, "lieu de livraison à préciser"))
        elif l.scu > capacity:
            left_out.append((l, f"{l.scu:g} SCU, plus que la soute ({capacity:g})"))
        elif l.pickup and l.pickup == l.drop:
            left_out.append((l, "chargée et livrée au même lieu"))
        else:
            todo.append(l)
    # livraisons de même départ et même arrivée : un seul bloc (tant qu'il tient dans la soute),
    # le calcul ne les distingue pas et en devient bien plus court
    groups: list[list[Leg]] = []
    for l in todo:
        g = next((g for g in groups if (g[0].pickup, g[0].drop) == (l.pickup, l.drop)
                  and sum(x.scu for x in g) + l.scu <= capacity + 1e-6), None)
        if g is None:
            groups.append([l])
        else:
            g.append(l)
    members = groups
    todo = [Leg(key=tuple(x.key for x in g), label=g[0].label, drop=g[0].drop, pickup=g[0].pickup,
                scu=sum(x.scu for x in g)) for g in groups]
    n = len(todo)
    full = (1 << n) - 1
    work_of = [sum(handling_s(x.scu) for x in g) for g in members]
    aboard0 = sum(1 << i for i, l in enumerate(todo) if not l.pickup)

    memo_d: dict[tuple, float | None] = {}

    def dist(a, b):
        """Distance en Gm, mémorisée (le graphe est lent)."""
        if a == b:
            return 0.0
        k = (a, b)
        if k not in memo_d:
            memo_d[k] = distance(a, b)
        return memo_d[k]

    def fly(a, b) -> float:
        """Secondes de vol de a à b ; trajet inconnu : `UNKNOWN_S`."""
        if a is None:
            return 0.0
        d = dist(a, b)
        return UNKNOWN_S if d is None else d / qd_speed

    def visit(node, picked, done, cargo):
        """Livre puis charge à `node` → (picked, done, cargo, livrées, chargées, manutention)."""
        unload = [i for i in range(n) if picked >> i & 1 and not done >> i & 1 and todo[i].drop == node]
        for i in unload:
            done |= 1 << i
            cargo -= todo[i].scu
        load = []
        for i in sorted((i for i in range(n) if not picked >> i & 1 and todo[i].pickup == node),
                        key=lambda i: -todo[i].scu):
            if cargo + todo[i].scu <= capacity + 1e-6:
                picked |= 1 << i
                cargo += todo[i].scu
                load.append(i)
        work = sum(handling_s(x.scu) for i in unload + load for x in members[i])
        return picked, done, cargo, unload, load, (stop_s + work) if (unload or load) else 0.0

    def remaining_work(picked, done) -> float:
        """Manutention encore à faire : borne basse du temps restant."""
        return sum(work_of[i] * ((not picked >> i & 1) + (not done >> i & 1)) for i in range(n))

    best = {"t": math.inf, "path": []}
    seen: dict[tuple, float] = {}
    tries = [0]

    def candidates(picked, done, cargo):
        """Lieux où un arrêt fait avancer : une livraison à bord, ou un chargement qui tient."""
        out = set()
        for i in range(n):
            if picked >> i & 1:
                if not done >> i & 1:
                    out.add(todo[i].drop)
            elif cargo + todo[i].scu <= capacity + 1e-6 or any(
                    picked >> j & 1 and not done >> j & 1 and todo[j].drop == todo[i].pickup for j in range(n)):
                out.add(todo[i].pickup)
        return out

    def search(cur, picked, done, cargo, t, path):
        """Essaie chaque arrêt suivant, le plus proche d'abord ; garde le chemin le plus rapide."""
        tries[0] += 1
        if done == full:
            total = t + (fly(cur, end) if end and cur != end else 0.0)
            if total < best["t"]:
                best["t"], best["path"] = total, list(path)
            return
        if tries[0] > budget or t + remaining_work(picked, done) >= best["t"]:
            return
        state = (cur, picked, done)
        if seen.get(state, math.inf) <= t:
            return
        seen[state] = t
        for node in sorted(candidates(picked, done, cargo), key=lambda x: fly(cur, x)):
            p2, d2, c2, unload, load, work = visit(node, picked, done, cargo)
            if not unload and not load:
                continue
            path.append((node, unload, load, work, c2))
            search(node, p2, d2, c2, t + fly(cur, node) + work, path)
            path.pop()

    if n:
        search(start, aboard0, 0, sum(l.scu for l in todo if not l.pickup), 0.0, [])
    if n and not best["path"]:
        left_out.extend((l, "aucun ordre possible (soute trop petite pour enchaîner)") for l in todo)

    stops: list[Stop] = []
    prev = start
    for node, unload, load, work, cargo in best["path"]:
        d = dist(prev, node) if prev is not None else None
        stops.append(Stop(node=node, unload=[x for i in unload for x in members[i]],
                          load=[x for i in load for x in members[i]],
                          travel_s=(0.0 if prev is None else (None if d is None else d / qd_speed)),
                          distance_gm=d, handle_s=work, cargo_after=round(cargo, 3)))
        prev = node
    end_t = None
    if end and stops and prev != end:
        d = dist(prev, end)
        end_t = None if d is None else d / qd_speed
    elif end:
        end_t = 0.0
    return Route(stops, start, end if stops else None, end_t, left_out, exhaustive=tries[0] <= budget)


def fmt_duration(s: float) -> str:
    """« 41 min », « 1 h 05 », « < 1 min »."""
    m = round(s / 60)
    if m < 1:
        return "< 1 min"
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"
