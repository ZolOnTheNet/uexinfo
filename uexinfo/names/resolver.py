"""Résolveur de noms unique (D6).

Cascade, du plus sûr au moins sûr — chaque entité garde son meilleur niveau :
  EXACT      la saisie est égale à un nom, un code ou un alias
  PREFIX     un nom commence par la saisie
  SUBSTRING  la saisie est dans un nom, ou un nom (mot entier) est dans la saisie
  FUZZY      ressemblance ≥ seuil du profil (seulement si rien au-dessus)

Règles validées :
  a. deux profils de seuil : saisie joueur (« input ») et texte OCR (« ocr ») ;
  b. deux candidats aussi proches (même niveau, même score) ⇒ ambiguous=True,
     l'appelant propose la liste au joueur ;
  c. un lieu saisi là où un terminal est attendu ⇒ terminal principal du lieu :
     Admin > TDD > centre cargo > autre terminal de commerce > autre.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from uexinfo.names.normalize import norm

try:
    from rapidfuzz import fuzz as _fuzz

    def _similarity(a: str, b: str) -> float:
        return float(_fuzz.WRatio(a, b))
except ImportError:  # pragma: no cover
    import difflib

    def _similarity(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100

EXACT, PREFIX, SUBSTRING, FUZZY = 4, 3, 2, 1

# a. Seuils de ressemblance (0-100) — valeurs métier, fixées par tests/names
THRESHOLDS = {"input": 70, "ocr": 60}


# ── Entités ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Entity:
    kind: str                         # system|planet|moon|station|city|outpost|terminal|commodity|vehicle|node
    id: Any
    name: str
    obj: Any = field(default=None, compare=False, hash=False)
    keys: tuple[str, ...] = ()        # noms propres à l'entité (nom, nom court…)
    codes: tuple[str, ...] = ()       # codes UEX : correspondance EXACTE seulement
    loc_keys: tuple[str, ...] = ()    # noms du LIEU (terminal : station/ville) → règle c
    tokens: tuple[str, ...] = ()      # segments pour filtrer en notation pointée (système, planète, lieu…)
    dot_keys: tuple[str, ...] = ()    # noms acceptés en DERNIER segment pointé (service : « lorville.admin »)
    priority: int = 0                 # plus petit = préféré à égalité (règle c, achetable…)
    group: str = ""                   # terminaux d'un même lieu


@dataclass
class Match:
    entity: Entity
    level: int
    score: float
    via_location: bool = False


@dataclass
class Resolution:
    matches: list[Match]

    @property
    def best(self) -> Any:
        """Objet métier du meilleur candidat (None si aucun)."""
        return self.matches[0].entity.obj if self.matches else None

    @property
    def top(self) -> list[Match]:
        """Candidats à égalité avec le premier (même niveau, même score)."""
        if not self.matches:
            return []
        m0 = self.matches[0]
        tier = [m for m in self.matches if (m.level, round(m.score, 1)) == (m0.level, round(m0.score, 1))]
        # Le lieu lui-même et son terminal principal (trouvé par le nom du lieu)
        # désignent le même endroit : pas d'ambiguïté entre eux.
        if any(not m.via_location for m in tier):
            tier = [m for m in tier if not m.via_location]
        # Commodités : une fiche « parente » non achetable ne concurrence pas ses variantes.
        if any(m.entity.kind == "commodity" and m.entity.priority == 0 for m in tier):
            tier = [m for m in tier if not (m.entity.kind == "commodity" and m.entity.priority > 0)]
        return tier

    @property
    def ambiguous(self) -> bool:
        """b. Plusieurs candidats aussi proches ⇒ demander au joueur."""
        return len(self.top) > 1

    @property
    def candidates(self) -> list[Any]:
        return [m.entity.obj for m in self.top]

    def objects(self) -> list[Any]:
        return [m.entity.obj for m in self.matches]


# ── Règle c : terminal principal d'un lieu ───────────────────────────────────

def terminal_priority(t) -> int:
    """Admin=0 > TDD=1 > centre cargo=2 > autre terminal de commerce=3 > autre=4.
    Un terminal fermé (is_available=0 chez UEX) passe après tous les terminaux ouverts (+10)."""
    closed = 10 if getattr(t, "is_available", 1) == 0 else 0
    return closed + _service_priority(t)


def _service_priority(t) -> int:
    name = (getattr(t, "name", "") or "").lower()
    service = name.split(" - ", 1)[0].strip() if " - " in name else ""
    if service == "admin":
        return 0
    if service == "tdd":
        return 1
    if getattr(t, "is_cargo_center", 0) or "cargo center" in name:
        return 2
    if (getattr(t, "type", "") or "") == "commodity":
        return 3
    return 4


def terminal_group(t) -> str:
    """Clé du LIEU d'un terminal (système + station/ville/lieu) : tous les terminaux
    d'une même station partagent cette clé."""
    name = getattr(t, "name", "") or ""
    loc = name.rsplit(" - ", 1)[-1].strip() if " - " in name else ""
    place = getattr(t, "space_station_name", "") or getattr(t, "city_name", "") or ""
    return norm(f"{getattr(t, 'star_system_name', '') or ''}|{place or loc or name}")


def trading_terminal(terminals, t):
    """Terminal de commerce (type « commodity ») du même lieu que `t`, selon la règle c.

    Une position enregistrée peut désigner une boutique (« Landing Services -
    Seraphim Station », « Hot Dogs - … ») qui n'a aucun prix de marchandise :
    pour le commerce, c'est le terminal principal du lieu qui compte.
    Renvoie `t` inchangé s'il est déjà de commerce ou si le lieu n'en a aucun.
    """
    if t is None or (getattr(t, "type", "") or "") == "commodity":
        return t
    key = terminal_group(t)
    same = [x for x in terminals or [] if (getattr(x, "type", "") or "") == "commodity"
            and terminal_group(x) == key]
    return min(same, key=terminal_priority) if same else t


# ── Index ─────────────────────────────────────────────────────────────────────

def _uniq(items: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for it in items:
        n = norm(it)
        if n and n not in out:
            out.append(n)
    return tuple(out)


class NameIndex:
    def __init__(self, entities: Iterable[Entity] = ()):
        self.entities: list[Entity] = list(entities)

    def add(self, entity: Entity) -> None:
        self.entities.append(entity)

    # ── Recherche ─────────────────────────────────────────────────────────────
    def resolve(self, query: str, kinds: set[str] | None = None, profile: str = "input",
                min_level: int = FUZZY, limit: int = 20, prefer_system: str = "") -> Resolution:
        """`prefer_system` : à égalité, les entités de ce système passent devant
        (ex. « nyx gateway » vu depuis Stanton → Nyx Gateway (Stanton))."""
        q = norm(query)
        pool = [e for e in self.entities if not kinds or e.kind in kinds]
        if not q or not pool:
            return Resolution([])

        # Notation pointée : « stanton.lorville », « lorville.admin », « drak.cutlass »
        dotted = "." in q
        if dotted:
            *filters, last = [p.strip() for p in q.split(".")]
            filters = [_expand_filter(f) for f in filters if f]
            pool = [e for e in pool if all(any(f in tok for tok in e.tokens) for f in filters)]
            q = last
            if not q:
                return Resolution([Match(e, PREFIX, 100.0) for e in pool][:limit])

        best: dict[int, Match] = {}
        for e in pool:
            m = self._match_entity(q, e, dotted)
            if m and m.level >= min_level:
                best[id(e)] = m

        if not best and min_level <= FUZZY:
            threshold = THRESHOLDS.get(profile, THRESHOLDS["input"])
            for e in pool:
                own = max((_similarity(q, k) for k in e.keys), default=0.0)
                loc = max((_similarity(q, k) for k in e.loc_keys), default=0.0)
                score = max(own, loc)
                if score >= threshold:
                    best[id(e)] = Match(e, FUZZY, score, via_location=bool(e.loc_keys) and loc >= own)

        matches = _collapse_locations(list(best.values()))
        ps = norm(prefer_system)
        matches.sort(key=lambda m: (-m.level, -round(m.score, 1), m.via_location,
                                    bool(ps) and ps not in m.entity.tokens,
                                    m.entity.priority, len(m.entity.name)))
        return Resolution(matches[:limit])

    @staticmethod
    def _match_entity(q: str, e: Entity, dotted: bool) -> Match | None:
        if q in e.codes:
            return Match(e, EXACT, 100.0)
        found: Match | None = None
        own_keys = e.keys + (e.dot_keys if dotted else ())
        for keys, via_loc in ((own_keys, False), (e.loc_keys, True)):
            for k in keys:
                if k == q:
                    level = EXACT
                elif k.startswith(q):
                    level = PREFIX
                elif q in k or (len(k) >= 4 and f" {k} " in f" {q} "):
                    level = SUBSTRING
                else:
                    continue
                # À niveau égal, le nom du LIEU l'emporte : « tressler » désigne
                # Port Tressler, pas chacune des boutiques qui en portent le nom.
                if found is None or level > found.level or (level == found.level and via_loc):
                    found = Match(e, level, 100.0, via_loc)
        return found


def _strip_qualifier(name: str) -> str:
    """'Pyro Gateway (Nyx)' → 'Pyro Gateway' : le nom seul désigne aussi le lieu
    (homonymes départagés ensuite par la règle b ou le système du joueur)."""
    return name.split("(", 1)[0].strip() if "(" in name else ""


def _expand_filter(f: str) -> str:
    """Abréviations de fabricants (« drak » → « drake ») pour la notation pointée."""
    try:
        from uexinfo.cli.completer_data import MFR_ABBREV
    except Exception:  # pragma: no cover
        return f
    return MFR_ABBREV.get(f, f)


def _collapse_locations(matches: list[Match]) -> list[Match]:
    """c. Terminaux trouvés par le nom de leur LIEU : un seul par lieu, le principal."""
    keep: list[Match] = []
    by_group: dict[str, Match] = {}
    for m in matches:
        e = m.entity
        if e.kind == "terminal" and m.via_location and e.group:
            cur = by_group.get(e.group)
            if cur is None or (m.level, -e.priority) > (cur.level, -cur.entity.priority):
                by_group[e.group] = m
        else:
            keep.append(m)
    kept = {id(m.entity) for m in keep}
    keep.extend(m for m in by_group.values() if id(m.entity) not in kept)
    return keep


# ── Construction depuis le cache UEX ─────────────────────────────────────────

def build_index(cache, graph=None) -> NameIndex:
    from uexinfo.display.formatter import terminal_short_name

    idx = NameIndex()
    g = lambda o, a: getattr(o, a, "") or ""  # noqa: E731

    for s in getattr(cache, "star_systems", None) or []:
        idx.add(Entity("system", s.id, s.name, s, keys=_uniq([s.name]), codes=_uniq([g(s, "code")]),
                       tokens=_uniq([s.name])))
    for p in getattr(cache, "planets", None) or []:
        idx.add(Entity("planet", p.id, p.name, p, keys=_uniq([p.name]),
                       tokens=_uniq([g(p, "star_system_name"), p.name])))
    for m in getattr(cache, "moons", None) or []:
        idx.add(Entity("moon", m.id, m.name, m, keys=_uniq([m.name]),
                       tokens=_uniq([g(m, "star_system_name"), g(m, "planet_name"), m.name])))
    for kind, attr in (("station", "space_stations"), ("city", "cities"), ("outpost", "outposts")):
        for o in getattr(cache, attr, None) or []:
            idx.add(Entity(kind, o.id, o.name, o, keys=_uniq([o.name, g(o, "nickname")]),
                           tokens=_uniq([g(o, "star_system_name"), g(o, "planet_name"), o.name])))

    for t in getattr(cache, "terminals", None) or []:
        loc = t.name.rsplit(" - ", 1)[-1].strip() if " - " in t.name else ""
        place = g(t, "space_station_name") or g(t, "city_name")
        service = t.name.split(" - ", 1)[0].strip() if " - " in t.name else ""
        group = terminal_group(t)
        short = terminal_short_name(t.name)
        # Nom court propre au terminal seulement s'il garde son service (« TDD - Area 18 ») ;
        # sinon c'est un nom du lieu (« Baijini »), qui relève de la règle c.
        own_short = [short] if " - " in short else []
        idx.add(Entity(
            "terminal", t.id, t.name, t,
            keys=_uniq([t.name, *own_short]), codes=_uniq([g(t, "code")]),
            loc_keys=_uniq([loc, place, *([] if own_short else [short]),
                            *(_strip_qualifier(x) for x in (loc, place) if x)]),
            tokens=_uniq([g(t, "star_system_name"), g(t, "planet_name"), g(t, "orbit_name"),
                          place, loc, service]),
            dot_keys=_uniq([service]),
            priority=terminal_priority(t), group=group,
        ))

    for c in getattr(cache, "commodities", None) or []:
        base = c.name.split(" - ", 1)[0] if " - " in c.name else ""
        idx.add(Entity("commodity", c.id, c.name, c,
                       keys=_uniq([c.name, base]), codes=_uniq([g(c, "code")]),
                       priority=0 if getattr(c, "is_buyable", 0) else 1))

    for v in getattr(cache, "vehicles", None) or []:
        idx.add(Entity("vehicle", v.id, v.name_full or v.name, v,
                       keys=_uniq([v.name, v.name_full]),
                       tokens=_uniq(["ship", g(v, "manufacturer"), v.name, v.name_full])))

    graph = graph if graph is not None else getattr(cache, "transport_graph", None)
    for name, node in (getattr(graph, "nodes", None) or {}).items():
        idx.add(Entity("node", name, name, node, keys=_uniq([name]),
                       tokens=_uniq([getattr(node, "system", ""), name])))
    return idx


def get_index(ctx) -> NameIndex:
    """Index partagé, reconstruit seulement si les listes du cache ont changé."""
    cache = ctx.cache
    graph = getattr(cache, "transport_graph", None)
    sig = tuple(
        (id(lst), len(lst)) for lst in (
            getattr(cache, a, None) or [] for a in (
                "star_systems", "planets", "moons", "space_stations", "cities",
                "outposts", "terminals", "commodities", "vehicles"))
    ) + ((id(graph), len(getattr(graph, "nodes", {}) or {})),)
    cached = getattr(ctx, "_name_index", None)
    if cached is not None and cached[0] == sig:
        return cached[1]
    idx = build_index(cache, graph)
    try:
        ctx._name_index = (sig, idx)
    except AttributeError:  # pragma: no cover
        pass
    return idx


def resolve(ctx, query: str, kinds: set[str] | None = None, profile: str = "input",
            min_level: int = FUZZY, limit: int = 20, prefer_system: str = "") -> Resolution:
    return get_index(ctx).resolve(query, kinds=kinds, profile=profile, min_level=min_level,
                                  limit=limit, prefer_system=prefer_system)


_GRAPH_INDEXES: dict[int, tuple[int, NameIndex]] = {}


def graph_index(graph) -> NameIndex:
    """Index des seuls nœuds d'un graphe de navigation (réutilisé tant que le graphe ne change pas)."""
    nodes = getattr(graph, "nodes", None) or {}
    cached = _GRAPH_INDEXES.get(id(graph))
    if cached and cached[0] == len(nodes):
        return cached[1]
    idx = NameIndex(
        Entity("node", name, name, node, keys=_uniq([name]),
               tokens=_uniq([getattr(node, "system", ""), name]))
        for name, node in nodes.items()
    )
    _GRAPH_INDEXES[id(graph)] = (len(nodes), idx)
    return idx


def match_text(query: str, values: Iterable[str], min_level: int = PREFIX) -> str | None:
    """Même procédure appliquée à une simple liste de libellés (ex : arbre /explore)."""
    idx = NameIndex(Entity("text", v, v, v, keys=_uniq([v])) for v in values)
    return idx.resolve(query, min_level=min_level).best
