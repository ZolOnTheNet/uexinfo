"""DataManager — couche unifiée d'accès aux prix.

Centralise : UEXClient + PriceCache + ScanPriceStore + état offline.
Remplace les fonctions _fetch_prices/_terminal_prices/_commodity_prices
dispersées dans info.py.

Usage :
    from uexinfo.cache.data_manager import DataManager, Source
    rows, src = DataManager.terminal_prices(terminal, ctx)
    color = DataManager.color(src)
"""
from __future__ import annotations

import re
import time

from uexinfo.api.uex_client import UEXClient, UEXError
from uexinfo.display import colors as C
from uexinfo.display.formatter import console


class Source:
    API   = "api"     # données fraîches UEX Corp
    STALE = "stale"   # cache périmé (API offline)
    SCAN  = "scan"    # données joueur (scan confirmé)
    EMPTY = "empty"   # aucune donnée disponible


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
            ctx._price_cache[key] = (time.time(), data)
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
        def _loc(name: str) -> str:
            return name.rsplit(" - ", 1)[-1].strip()

        def _slug(name: str) -> str:
            s = name.lower().replace(" - ", "-")
            s = re.sub(r"[^a-z0-9-]+", "-", s)
            return s.strip("-")

        rows, source = DataManager.fetch_prices(f"t{t.id}", {"id_terminal": t.id}, ctx)
        if not rows and t.code:
            rows, source = DataManager.fetch_prices(f"tc_{t.code}", {"terminal_code": t.code}, ctx)
        if not rows:
            loc_q = _loc(t.name).lower()
            if loc_q:
                rows, source = DataManager.fetch_prices(f"tl_{loc_q}", {"terminal_name": loc_q}, ctx)
        if not rows:
            slug = _slug(t.name)
            loc_q2 = _loc(t.name).lower()
            if slug and slug != loc_q2:
                rows, source = DataManager.fetch_prices(f"ts_{slug}", {"terminal_name": slug}, ctx)

        # Fusionner données scan joueur (prioritaires sur UEX)
        from uexinfo.cache.scan_prices import ScanPriceStore
        store_key = str(t.id) if t.id else f"name:{_loc(t.name).lower()}"
        rows_merged = ScanPriceStore().merge_into(rows, store_key)
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
