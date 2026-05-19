"""Client sc-trade.tools — données communauté (accès public, sans token)."""
from __future__ import annotations

import requests


class SCTradeError(Exception):
    pass


class SCTradeClient:
    """Accès aux données publiques sc-trade.tools (affichées en orange, C.SCTRADE).

    Tous les endpoints utilisés sont publics — aucun token requis.
    """

    BASE_URL = "https://sc-trade.tools"

    def __init__(self, timeout: int = 15):
        self._timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        url = f"{self.BASE_URL}{path}"
        try:
            r = requests.get(url, headers={"Content-Type": "application/json"},
                             params=params, timeout=self._timeout)
        except requests.RequestException as e:
            raise SCTradeError(f"sc-trade.tools inaccessible: {e}") from e
        if not r.ok:
            raise SCTradeError(f"Erreur {r.status_code}: {r.text[:200]}")
        return r.json()

    # ── Endpoints publics ─────────────────────────────────────────────────────

    def commodity_items(self) -> list[dict]:
        """GET /api/commodity/items — liste des commodités."""
        return self._get("/api/commodity/items")

    def ships(self) -> list[dict]:
        """GET /api/ships — liste des vaisseaux."""
        return self._get("/api/ships")

    def crowdsource_listings(
        self,
        page: int = 0,
        size: int = 500,
        max_pages: int = 6,
    ) -> list[dict]:
        """GET /api/crowdsource/commodity-listings — prix communauté.

        Pagine automatiquement jusqu'à max_pages × size enregistrements.

        Chaque enregistrement :
          location (str)      — hiérarchie "system > station > shop"
          transaction (str)   — "BUYS" | "SELLS"  (du point de vue du terminal)
          commodity (str)     — nom de la commodité
          price (int)         — prix unitaire aUEC
          quantity (int)      — stock en SCU
          saturation (float)  — 0.0=vide … 1.0=plein
          timestamp (str)     — ISO 8601
        """
        all_records: list[dict] = []
        for p in range(max_pages):
            data = self._get(
                "/api/crowdsource/commodity-listings",
                params={"page": page + p, "size": size},
            )
            records = data.get("content", []) if isinstance(data, dict) else data
            all_records.extend(records)
            if isinstance(data, dict):
                total_pages = data.get("page", {}).get("totalPages", 1)
                if page + p + 1 >= total_pages:
                    break
            if len(records) < size:
                break
        return all_records

    def crowdsource_for_commodity(self, commodity_name: str) -> list[dict]:
        """Retourne tous les listings publics pour une commodité donnée."""
        target = commodity_name.lower().strip()
        records = self.crowdsource_listings(max_pages=8)
        return [r for r in records if r.get("commodity", "").lower() == target]
