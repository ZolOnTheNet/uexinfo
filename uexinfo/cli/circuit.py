"""Contrats pris et chemin pour les livrer (décision du 2026-11-05).

Une offre lue par le mode scan (`ocr/contract_watch.OffersBoard`) devient, quand le contrat est
pris — notification « Contract Accepted » du Game.log, ou bouton « Pris » —, une mission du
**voyage actif** (créé au besoin : « Circuit du jour »), lieux reliés une fois à l'enregistrement
(D11). Le chemin (`rules/route_plan.py`) part de la position du joueur et compte le temps (vol,
arrêts, manutention). L'avancement est gardé sur chaque objectif (`progress` : « picked »,
« delivered ») : il avance à l'arrivée au prochain arrêt (Game.log) ou par `/mission route suivant`,
et « Contract Complete / Failed » retire le contrat du chemin.
"""
from __future__ import annotations

import re
import time

from uexinfo.names.places import node_ref, place_lookup, ref_node

CIRCUIT_NAME = "Circuit du jour"
_RE_NOTICE = re.compile(r"^\s*Contract (Accepted|Complete|Failed)\s*:\s*(.+)$", re.I)
_RE_XP = re.compile(r"\s*\d[\d\s]*(?:/\s*\d[\d\s]*)?\s*exp\.?\s*$", re.I)


# ── Tableau des offres ────────────────────────────────────────────────────────

def board(ctx):
    """Tableau des offres partagé (`ctx.offers_board`), relu du disque s'il n'existe pas encore :
    un contrat pris avant le premier mode scan de la session retrouve son offre."""
    b = getattr(ctx, "offers_board", None)
    if b is None:
        from uexinfo.ocr.contract_watch import OffersBoard, default_board_path
        b = OffersBoard(default_board_path())
        b.load(time.time())
        ctx.offers_board = b
    return b


def notice_title(text: str) -> tuple[str, str] | None:
    """(« accepted » | « complete » | « failed », titre) d'une notification de contrat du Game.log
    (« Contract Accepted: [BP] Rookie Rank - Direct Medium Cargo Haul 50 / 200 exp. ») ; None sinon."""
    m = _RE_NOTICE.match(text or "")
    if not m:
        return None
    title = re.sub(r"^\s*\[BP\]\s*", "", _RE_XP.sub("", m.group(2))).strip(" :")
    return m.group(1).lower(), title


# ── Contrats pris ─────────────────────────────────────────────────────────────

def circuit_voyage(ctx, create: bool = False):
    """Voyage actif ; sans voyage actif et `create` : un nouveau « Circuit du jour »."""
    vm = ctx.voyage_manager
    v = vm.get_active()
    if v is None and create:
        v = vm.new_voyage(CIRCUIT_NAME)
    return v


def take_offer(ctx, offer, ask: bool = True):
    """Offre prise → mission du voyage actif (lieux reliés, D11) ; renvoie (mission, lieux à préciser)."""
    from uexinfo.cli.places import ensure_mission_places
    from uexinfo.models.mission import Mission, MissionObjective
    objs = [MissionObjective(commodity=l.get("commodity") or None, source=l.get("pickup") or None,
                             destination=l.get("drop") or None,
                             quantity_scu=float(l["scu"]) if l.get("scu") else None)
            for l in offer.legs]
    m = Mission(id=0, name=offer.title, reward_uec=int(offer.reward or 0), objectives=objs,
                source_raw="offre", scanned_at=time.time())
    left = ensure_mission_places(m, ctx, ask=ask) if objs else []
    ctx.mission_manager.add(m)
    v = circuit_voyage(ctx, create=True)
    ctx.voyage_manager.add_missions(v, [m.id])
    offer.mission_id = m.id
    board(ctx).save()
    return m, left


def _circuit_missions(ctx, voyage=None) -> list:
    """Missions du voyage actif."""
    v = voyage or circuit_voyage(ctx)
    if v is None:
        return []
    mm = ctx.mission_manager
    return [m for m in (mm.get(str(i)) for i in v.mission_ids) if m]


def _find_mission(ctx, title: str):
    """Mission du voyage actif au titre `title` (pas encore livrée en entier) ; None sinon."""
    from rapidfuzz import fuzz
    from uexinfo.ocr.contract_watch import _norm
    t = _norm(title)
    best = [(fuzz.ratio(t, _norm(m.name)), m) for m in _circuit_missions(ctx)]
    best = [b for b in best if b[0] >= 88]
    return max(best, key=lambda b: b[0])[1] if best else None


def contract_notice(ctx, text: str) -> str | None:
    """Notification de contrat du Game.log → message pour la console (None : rien à dire)."""
    parsed = notice_title(text)
    if not parsed:
        return None
    kind, title = parsed
    if kind == "accepted":
        known = _find_mission(ctx, title)
        if known is not None and known.scanned_at and time.time() - known.scanned_at < 900 \
                and not any(o.progress for o in known.objectives):
            return None                         # déjà mis au chemin (bouton « Pris »)
        offer = board(ctx).find(title, time.time())
        if offer is None:
            return (f"📋 Contrat pris : {title} — pas lu dans les offres, absent du chemin "
                    "(ouvre l'offre en mode scan avant de la prendre, puis « Pris »).")
        m, left = take_offer(ctx, offer, ask=False)
        tail = f" Lieux à préciser : {', '.join(left)} (/mission lieux)." if left else ""
        if not offer.legs:
            tail += " Détail non lu : livraisons inconnues."
        return f"📋 Contrat pris : {title} → mission #{m.id}, ajoutée au chemin (/mission route).{tail}"
    m = _find_mission(ctx, title)
    if m is None:
        return None
    for o in m.objectives:
        o.progress = "delivered" if kind == "complete" else o.progress
    ctx.mission_manager.update(m)
    v = circuit_voyage(ctx)
    if v is not None:
        ctx.voyage_manager.remove_mission(v, m.id)
    b = board(ctx)
    for key, o in list(b.offers.items()):
        if o.mission_id == m.id:
            del b.offers[key]
    b.save()
    word = "terminé" if kind == "complete" else "échoué"
    return f"📋 Contrat {word} : {m.name} — retiré du chemin."


# ── Chemin ────────────────────────────────────────────────────────────────────

def route_legs(missions, graph):
    """Livraisons restantes des missions → (`Leg` du calcul, objectifs écartés et pourquoi)."""
    from uexinfo.rules.route_plan import Leg
    legs, skipped = [], []
    for m in missions:
        for i, o in enumerate(m.objectives):
            if o.progress == "delivered":
                continue
            drop = ref_node(o.destination_ref, graph) if o.destination_ref else None
            pick = ref_node(o.source_ref, graph) if o.source_ref else None
            if not drop:
                skipped.append((m, o, "lieu de livraison à préciser" if o.destination else "livraison inconnue"))
                continue
            if o.progress != "picked" and not pick:
                skipped.append((m, o, "lieu de collecte à préciser" if o.source else "lieu de collecte inconnu"))
                continue
            legs.append(Leg(key=(m.id, i), label=m.name, drop=drop,
                            pickup=None if o.progress == "picked" else pick,
                            scu=float(o.quantity_scu or 0), commodity=o.commodity or ""))
    return legs, skipped


def compute(ctx, end_at_destination: bool | None = None):
    """Chemin des contrats du voyage actif → dict (route, voyage, missions, skipped, capacity,
    start, ship) ; None sans voyage actif ou sans graphe."""
    from uexinfo.cli.commands.mission import _ship_hold
    from uexinfo.cli.commands.nav import _player_node
    from uexinfo.rules.route_plan import plan
    graph = ctx.cache.transport_graph
    v = circuit_voyage(ctx)
    if graph is None or v is None:
        return None
    if end_at_destination is None:
        end_at_destination = bool(getattr(ctx, "_route_end_dest", False))
    missions = _circuit_missions(ctx, v)
    legs, skipped = route_legs(missions, graph)
    start = _player_node(ctx, graph) or None
    end = (_player_node(ctx, graph, "destination") or None) if end_at_destination else None
    capacity, _box, ship = _ship_hold(ctx)
    try:
        stop_s = float(ctx.cfg.get("contracts", {}).get("stop_minutes", 3)) * 60
    except (TypeError, ValueError):
        stop_s = 180.0
    sig = (tuple((l.key, l.pickup, l.drop, l.scu) for l in legs), start, end, capacity, stop_s)
    cache = getattr(ctx, "_route_cache", None)
    if cache and cache[0] == sig:
        route = cache[1]
    else:
        def distance(a, b):
            """Distance du graphe en Gm, None si injoignable."""
            try:
                r = graph.find_shortest_path(a, b)
                return r.total_distance if r is not None else None
            except Exception:
                return None
        route = plan(start, legs, distance, capacity=capacity or float("inf"), end=end, stop_s=stop_s)
        ctx._route_cache = (sig, route)
    return {"route": route, "voyage": v, "missions": {m.id: m for m in missions}, "skipped": skipped,
            "capacity": capacity, "ship": ship, "start": start}


def advance(ctx, stop, missions: dict) -> None:
    """Arrêt fait : ses chargements sont à bord, ses livraisons livrées (enregistré)."""
    changed = set()
    for l, state in [(l, "picked") for l in stop.load] + [(l, "delivered") for l in stop.unload]:
        mid, idx = l.key
        m = missions.get(mid)
        if m is not None and idx < len(m.objectives):
            m.objectives[idx].progress = state
            changed.add(mid)
    for mid in changed:
        ctx.mission_manager.update(missions[mid])
    ctx._route_cache = None


def stop_summary(stop) -> str:
    """« livrer 32 SCU (2 contrats), charger 16 SCU »."""
    parts = []
    for word, legs in (("livrer", stop.unload), ("charger", stop.load)):
        if legs:
            scu = sum(l.scu for l in legs)
            n = len({l.key[0] for l in legs})
            parts.append(f"{word} {scu:g} SCU" + (f" ({n} contrats)" if n > 1 else ""))
    return ", ".join(parts)


def arrived(ctx, place: str, system: str = "") -> str | None:
    """Arrivée ou atterrissage lus au Game.log : si c'est le prochain arrêt, il est fait."""
    graph = ctx.cache.transport_graph
    if graph is None or not place:
        return None
    node, _r = place_lookup(place, graph, system)
    res = compute(ctx)
    if not node or res is None or not res["route"].stops:
        return None
    stop = res["route"].stops[0]
    if stop.node != node:
        return None
    advance(ctx, stop, res["missions"])
    msg = f"✔ Arrêt fait à {stop.node} : {stop_summary(stop)}."
    nxt = next_step(ctx)
    return msg + (f" ➜ Ensuite : {nxt}" if nxt else " Chemin terminé.")


def next_step(ctx) -> str:
    """Prochain arrêt pour la barre d'état (« Ruin Station : livrer 32 SCU ») ; « » sans chemin."""
    try:
        res = compute(ctx)
    except Exception:
        return ""
    if res is None or not res["route"].stops:
        return ""
    s = res["route"].stops[0]
    return f"{s.node} : {stop_summary(s)}"


def letters(route) -> dict:
    """Mission → lettre courte (A, B…) dans l'ordre où elle apparaît sur le chemin."""
    out: dict = {}
    for st in route.stops:
        for l in st.load + st.unload:
            out.setdefault(l.key[0], chr(ord("A") + len(out)) if len(out) < 26 else f"#{l.key[0]}")
    return out


def total_text(res) -> str:
    """« ⏱ 41 min (vol 22 min, arrêts et manutention 19 min) · 412 000 aUEC, 600 000 aUEC/h »."""
    from uexinfo.rules.route_plan import fmt_duration
    route = res["route"]
    text = (f"⏱ {fmt_duration(route.total_s)} (vol {fmt_duration(route.flight_s)}, "
            f"arrêts et manutention {fmt_duration(route.handle_s)})")
    reward = sum(m.reward_uec for m in res["missions"].values()
                 if any(o.progress != "delivered" for o in m.objectives))
    if reward and route.total_s:
        n = lambda v: f"{v:,}".replace(",", " ")
        text += f" · {n(reward)} aUEC, {n(round(reward / route.total_s * 3600))} aUEC/h"
    return text
