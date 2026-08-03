"""DataManager — couche unifiée d'accès aux prix.

Centralise : UEXClient + PriceCache + ScanPriceStore + état offline.
Remplace les fonctions _fetch_prices/_terminal_prices/_commodity_prices
dispersées dans info.py.

Usage :
    from uexinfo.cache.data_manager import DataManager, Source
    rows, src = DataManager.terminal_prices(terminal, ctx)
    color = DataManager.color(src)

    # Clé canonique de store pour un terminal/lieu
    from uexinfo.cache.data_manager import canonical_terminal_key, all_terminal_keys
    key  = canonical_terminal_key("ARC-L4", ctx.cache.terminals)
    keys = all_terminal_keys("ARC-L4", ctx.cache.terminals)
"""
from __future__ import annotations

import re
import time

from uexinfo.api.uex_client import UEXClient, UEXError
from uexinfo.display import colors as C
from uexinfo.display.formatter import console


# ── Clé canonique de terminal ─────────────────────────────────────────────────

def _loc_short(name: str) -> str:
    """Extrait le nom court d'un terminal UEX ('Admin - ARC-L4' → 'ARC-L4').
    Alias de terminal_short_name (display.formatter) — seule implémentation,
    ne pas la réécrire ici ni ailleurs. TDD : préserve le préfixe.
    """
    from uexinfo.display.formatter import terminal_short_name
    return terminal_short_name(name)


def _terminal_matches(query: str, terminals: list) -> list:
    """Retourne les terminaux dont le nom, nom court, ID ou lieu structuré correspond à query."""
    q = query.strip().replace("_", " ").lower()
    if not q:
        return []

    # 1. Lieu structuré (station/ville) — insensible aux tirets internes du nom
    # du terminal. Un terminal comme "INS Jericho - Pyro Gateway" (vaisseau en
    # vente) n'a pas le suffixe système ("(Stanton)") que portent ses voisins
    # de service ("Admin - Pyro Gateway (Stanton)") — matcher sur le nom brut
    # du terminal (nom court = dernier segment après " - ") ferait à tort
    # gagner "INS Jericho" par égalité de chaîne exacte.
    station_matches = []
    for t in terminals:
        station = (getattr(t, "space_station_name", "") or getattr(t, "city_name", "") or "").lower().strip()
        if station and (station == q or station.startswith(q + " ")):
            station_matches.append(t)
    if station_matches:
        if len(station_matches) > 1:
            from uexinfo.location.index import _trading_priority
            best_prio = min(_trading_priority(t) for t in station_matches)
            station_matches = [t for t in station_matches if _trading_priority(t) == best_prio]
        return station_matches

    # 2. Fallback : nom court / nom complet / ID / space_station exact
    result = []
    for t in terminals:
        loc_key  = _loc_short(t.name).lower()
        full_key = t.name.lower()
        ss_key   = (getattr(t, "space_station_name", "") or "").lower().strip()
        if q in (loc_key, full_key, str(t.id)) or (ss_key and q == ss_key):
            result.append(t)
    return result


def canonical_terminal_key(query: str, terminals: list) -> str:
    """Clé canonique pour scan_prices.json à partir de n'importe quelle variante de nom.

    - ``str(t.id)``    si la query identifie UN terminal (ou un groupe dont on prend le principal)
    - ``"name:{q}"``   si non trouvé dans le cache (fallback)

    En cas d'ambiguïté (plusieurs terminaux au même lieu), priorité :
    Admin > TDD > cargo_center > premier trouvé.
    Rationale : un scan se passe à UN seul terminal ; Admin est le cas le plus fréquent,
    TDD pour New Babbage et certaines villes.
    """
    q = query.strip().replace("_", " ").lower()
    if not q:
        return "name:"
    matches = _terminal_matches(q, terminals)
    if not matches:
        return f"name:{q}"
    if len(matches) == 1:
        return str(matches[0].id)
    # Plusieurs terminaux au même lieu — heuristique de priorité
    for t in matches:
        if t.name.lower().startswith("admin"):
            return str(t.id)
    for t in matches:
        if "tdd" in t.name.lower():
            return str(t.id)
    for t in matches:
        if getattr(t, "is_cargo_center", 0):
            return str(t.id)
    return str(matches[0].id)


def all_terminal_keys(query: str, terminals: list) -> list[str]:
    """Toutes les clés (IDs) pertinentes pour un lieu — pour la lecture multi-source.

    Utile pour agréger les données scan quand plusieurs terminaux au même lieu
    ont été scannés séparément (admin un jour, TDD un autre).
    """
    q = query.strip().replace("_", " ").lower()
    matches = _terminal_matches(q, terminals)
    if not matches:
        return [f"name:{q}"]
    keys: list[str] = []
    for t in matches:
        k = str(t.id)
        if k not in keys:
            keys.append(k)
    return keys


class Source:
    API   = "api"     # données fraîches UEX Corp
    STALE = "stale"   # cache périmé (API offline)
    SCAN  = "scan"    # données joueur (scan confirmé)
    EMPTY = "empty"   # aucune donnée disponible


def _check_game_version(api_ver: str, ctx) -> None:
    """Compare la version détectée depuis l'API avec la config ; notifie si différente."""
    if not api_ver:
        return
    ver_cfg = ctx.cfg.get("version", {})
    active  = ver_cfg.get("active", "live")
    stored  = ver_cfg.get(active, "")
    if not stored:
        # Premier contact — enregistrer silencieusement
        ctx.cfg.setdefault("version", {})[active] = api_ver
        import uexinfo.config.settings as _settings
        _settings.save(ctx.cfg)
    elif api_ver != stored:
        ctx._version_notice = (stored, api_ver, active)


class DataManager:

    @staticmethod
    def fetch_prices(key: str, api_kwargs: dict, ctx) -> tuple[list[dict], str]:
        """Fetch prix avec chaîne de fallback : cache frais → API → cache périmé → vide.

        Retourne (data, source).  Met à jour ctx._api_offline.
        """
        cached = ctx._price_cache.get(key)
        if cached:
            _ts, data = cached
            ctx._api_offline = False
            return data, Source.API

        client = UEXClient()
        try:
            data = client.get_prices(**api_kwargs)
            # Ne pas mettre en cache les résultats vides : cela masquerait les
            # fallbacks suivants (ex: loc_tail après un tl_ infructueux).
            if data:
                ctx._price_cache[key] = (time.time(), data)
                if not ctx._version_notice:
                    _check_game_version(data[0].get("game_version", ""), ctx)
            ctx._api_offline = False
            return data, Source.API
        except UEXError as e:
            stale = ctx._price_cache.get_stale(key)
            if stale:
                _ts, data = stale
                ctx._api_offline = True
                return data, Source.STALE
            ctx._api_offline = True
            console.print(f"[{C.WARNING}]⚠  API : {e}[/{C.WARNING}]")
            return [], Source.EMPTY

    @staticmethod
    def terminal_prices(t, ctx) -> tuple[list[dict], str]:
        """Prix d'un terminal : fallback id → code → loc → slug, puis merge scan joueur."""
        def _slug(name: str) -> str:
            s = name.lower().replace(" - ", "-")
            s = re.sub(r"[^a-z0-9-]+", "-", s)
            return s.strip("-")

        rows, source = DataManager.fetch_prices(f"t{t.id}", {"id_terminal": t.id}, ctx)
        if not rows and t.code:
            rows, source = DataManager.fetch_prices(f"tc_{t.code}", {"terminal_code": t.code}, ctx)
        loc_q = _loc_short(t.name).lower()
        if not rows and loc_q:
            rows, source = DataManager.fetch_prices(f"tl_{loc_q}", {"terminal_name": loc_q}, ctx)
        # Si loc_q a un préfixe service ("tdd - seraphim station"), l'API UEX ne le reconnaît
        # pas — réessayer avec le nom de lieu seul ("seraphim station").
        if not rows and " - " in loc_q:
            loc_tail = loc_q.rsplit(" - ", 1)[-1].strip()
            if loc_tail and loc_tail != loc_q:
                rows, source = DataManager.fetch_prices(
                    f"tlt_{loc_tail}", {"terminal_name": loc_tail}, ctx
                )
        if not rows:
            slug = _slug(t.name)
            if slug and slug != loc_q:
                rows, source = DataManager.fetch_prices(f"ts_{slug}", {"terminal_name": slug}, ctx)

        # Fusionner données scan joueur (prioritaires sur UEX)
        from uexinfo.cache.scan_prices import ScanPriceStore
        loc_name  = _loc_short(t.name).lower()
        store_key = str(t.id) if t.id else f"name:{loc_name}"
        store     = ScanPriceStore()
        terminals = ctx.cache.terminals if (hasattr(ctx, "cache") and ctx.cache) else []

        # Version active pour filtrage des scans
        _ver_cfg   = ctx.cfg.get("version", {}) if hasattr(ctx, "cfg") else {}
        _sc_env    = _ver_cfg.get("active", "live")
        _sc_ver    = _ver_cfg.get(_sc_env, "")

        # Fusion principale (clé terminal précis)
        rows_merged = store.merge_into(rows, store_key, sc_version=_sc_ver, sc_env=_sc_env)

        ss_name = (getattr(t, "space_station_name", "") or "").lower().strip()
        alt_keys: list[str] = []
        seen: set[str] = {store_key}

        # 1) Terminaux frères (même lieu, service différent — ex: admin↔TDD même station)
        for sibling in terminals:
            if sibling.id == t.id:
                continue
            if _loc_short(sibling.name).lower() == loc_name:
                sib_key = str(sibling.id)
                if sib_key not in seen:
                    alt_keys.append(sib_key)
                    seen.add(sib_key)

        # 2) Legacy : variantes "name:" et nom de station → migrent vers store_key au premier accès
        for legacy in (f"name:{loc_name}", loc_name,
                       f"name:{ss_name}" if ss_name else None,
                       ss_name if ss_name else None):
            if legacy and legacy not in seen:
                alt_keys.append(legacy)
                seen.add(legacy)

        for alt_key in alt_keys:
            base     = rows_merged if rows_merged is not rows else rows
            rows_alt = store.merge_into(base, alt_key, sc_version=_sc_ver, sc_env=_sc_env)
            if rows_alt is not base:
                _migrate_store_key(store, alt_key, store_key)
                rows_merged = rows_alt

        if rows_merged is not rows:
            source = Source.SCAN

        return rows_merged, source

    @staticmethod
    def commodity_prices(c_id: int, ctx) -> tuple[list[dict], str]:
        """Prix d'une commodité par ID."""
        return DataManager.fetch_prices(f"c{c_id}", {"id_commodity": c_id}, ctx)

    @staticmethod
    def color(source: str) -> str:
        """Couleur Rich déterminée par la source effective des données."""
        if source == Source.STALE:
            return C.SCTRADE   # orange = cache périmé / UEX offline
        if source == Source.SCAN:
            return C.SUCCESS   # vert = données joueur confirmées
        return C.UEX           # cyan = données fraîches UEX Corp


def _migrate_store_key(store, old_key: str, new_key: str) -> None:
    """Déplace les entrées de old_key vers new_key dans le ScanPriceStore (silencieux).

    Ne migre pas si old_key est déjà un terminal ID numérique (déjà canonique).
    """
    try:
        if old_key == new_key or old_key.isdigit():
            return
        data = store._load()
        if old_key not in data:
            return
        existing = data.get(new_key, {})
        for cid_key, entry in data[old_key].items():
            if cid_key not in existing or entry.get("timestamp", 0) >= existing[cid_key].get("timestamp", 0):
                existing[cid_key] = entry
        data[new_key] = existing
        del data[old_key]
        store._write(data)
    except Exception:
        pass
