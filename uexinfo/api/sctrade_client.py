"""Client sc-trade.tools — routes commerciales et prix (données communauté)."""
from __future__ import annotations

import requests


class SCTradeError(Exception):
    pass


class SCTradeAuthError(SCTradeError):
    pass


class SCTradeClient:
    """Accès aux données sc-trade.tools (affichées en orange, C.SCTRADE).

    Token requis pour les endpoints /api/tools/* et /api/commodity/*/transactions.
    Endpoints publics (commodity items, ships) fonctionnent sans token.
    """

    BASE_URL = "https://sc-trade.tools"

    def __init__(self, token: str = "", timeout: int = 15):
        self._token   = token.strip()
        self._timeout = timeout

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _headers(self, auth: bool = True) -> dict:
        h = {"Content-Type": "application/json"}
        if auth and self._token:
            h["token"] = self._token
        return h

    def _get(self, path: str, auth: bool = False, params: dict | None = None) -> list | dict:
        url = f"{self.BASE_URL}{path}"
        try:
            r = requests.get(url, headers=self._headers(auth), params=params,
                             timeout=self._timeout)
        except requests.RequestException as e:
            raise SCTradeError(f"sc-trade.tools inaccessible: {e}") from e
        if r.status_code == 403:
            raise SCTradeAuthError("Token sc-trade.tools manquant ou invalide")
        if not r.ok:
            raise SCTradeError(f"Erreur {r.status_code}: {r.text[:200]}")
        return r.json()

    def _post(self, path: str, body: dict) -> list | dict:
        if not self._token:
            raise SCTradeAuthError(
                "Token sc-trade.tools requis — /config sctrade token <token>"
            )
        url = f"{self.BASE_URL}{path}"
        try:
            r = requests.post(url, headers=self._headers(auth=True),
                              json=body, timeout=self._timeout)
        except requests.RequestException as e:
            raise SCTradeError(f"sc-trade.tools inaccessible: {e}") from e
        if r.status_code == 403:
            raise SCTradeAuthError("Token sc-trade.tools manquant ou invalide")
        if r.status_code == 400:
            raise SCTradeError(f"Paramètres invalides: {r.text[:200]}")
        if not r.ok:
            raise SCTradeError(f"Erreur {r.status_code}: {r.text[:200]}")
        return r.json()

    # ── Endpoints publics ─────────────────────────────────────────────────────

    def commodity_items(self) -> list[dict]:
        """GET /api/commodity/items — liste des commodités (public)."""
        return self._get("/api/commodity/items", auth=False)

    def ships(self) -> list[dict]:
        """GET /api/ships — liste des vaisseaux (public)."""
        return self._get("/api/ships", auth=False)

    def crowdsource_listings(
        self,
        page: int = 0,
        size: int = 500,
        max_pages: int = 6,
    ) -> list[dict]:
        """GET /api/crowdsource/commodity-listings — prix communauté (public).

        Pagine automatiquement jusqu'à max_pages × size enregistrements.
        Retourne la liste plate de tous les enregistrements récupérés.

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
                auth=False,
                params={"page": page + p, "size": size},
            )
            records = data.get("content", []) if isinstance(data, dict) else data
            all_records.extend(records)
            # Arrêter si on a tout
            if isinstance(data, dict):
                total_pages = data.get("page", {}).get("totalPages", 1)
                if page + p + 1 >= total_pages:
                    break
            if len(records) < size:
                break
        return all_records

    def crowdsource_for_commodity(self, commodity_name: str) -> list[dict]:
        """Retourne tous les listings publics pour une commodité donnée.

        Charge les données par page jusqu'à trouver toutes les occurrences
        du nom de commodité (insensible à la casse).
        """
        target = commodity_name.lower().strip()
        # Charger assez de pages pour couvrir une commodité populaire
        records = self.crowdsource_listings(max_pages=8)
        return [r for r in records if r.get("commodity", "").lower() == target]

    # ── Endpoints avec token ──────────────────────────────────────────────────

    def commodity_transactions(self, name: str) -> list[dict]:
        """GET /api/commodity/items/{name}/transactions — prix par terminal."""
        return self._get(f"/api/commodity/items/{name}/transactions", auth=True)

    def trades(
        self,
        *,
        ship: str,
        investment: int,
        max_cargo_scu: int,
        min_security: int = 0,
        max_stops: int = 3,
        origin: str = "",
        profit_type: str = "time",
        avoid_hidden: bool = True,
        commodity_whitelist: list[str] | None = None,
        location_blacklist: list[str] | None = None,
    ) -> list[dict]:
        """POST /api/tools/trades — meilleures routes commerciales."""
        body: dict = {
            "investment":           investment,
            "ship":                 ship,
            "minSecurityLevel":     min_security,
            "supportedBoxSizeInScu": min(max_cargo_scu, 32),
            "maxStops":             max(1, min(max_stops, 5)),
            "profitType":           profit_type,
            "allowWaitTimes":       False,
            "avoidHiddenLocations": avoid_hidden,
            "smartFilters":         False,
            "locationNamesType":    "blacklist",
            "locationTypesType":    "blacklist",
            "factionNamesType":     "blacklist",
            "commodityNamesType":   "blacklist" if not commodity_whitelist else "whitelist",
            "commodityTypesType":   "blacklist",
            "locationNames":        location_blacklist or [],
            "locationTypes":        [],
            "factionNames":         [],
            "commodityNames":       commodity_whitelist or [],
            "commodityTypes":       [],
        }
        if origin:
            body["origin"] = origin
        return self._post("/api/tools/trades", body)

    def itinerary(
        self,
        *,
        origin: str,
        destination: str,
        ship: str,
        investment: int,
        max_cargo_scu: int,
        min_security: int = 0,
        max_stops: int = 3,
        allowable_detour: int = 25,
    ) -> list[dict]:
        """POST /api/tools/itinerary — route optimisée entre origin et destination."""
        body: dict = {
            "origin":               origin,
            "destination":          destination,
            "allowableDetour":      min(allowable_detour, 100),
            "investment":           investment,
            "ship":                 ship,
            "minSecurityLevel":     min_security,
            "supportedBoxSizeInScu": min(max_cargo_scu, 32),
            "maxStops":             max(1, min(max_stops, 5)),
            "profitType":           "time",
            "allowWaitTimes":       False,
            "avoidHiddenLocations": True,
            "smartFilters":         False,
            "locationNamesType":    "blacklist",
            "locationTypesType":    "blacklist",
            "factionNamesType":     "blacklist",
            "commodityNamesType":   "blacklist",
            "commodityTypesType":   "blacklist",
            "locationNames":        [],
            "locationTypes":        [],
            "factionNames":         [],
            "commodityNames":       [],
            "commodityTypes":       [],
        }
        return self._post("/api/tools/itinerary", body)
