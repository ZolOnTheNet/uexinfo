"""Client REST pour l'API UEX Corp 2.0."""
from __future__ import annotations

import requests

BASE_URL = "https://uexcorp.space/api/2.0"
TIMEOUT = 15


class UEXError(Exception):
    pass


class UEXClient:
    def __init__(self, timeout: int = TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "uexinfo-cli/0.1",
            "Accept": "application/json",
        })

    def _get(self, endpoint: str, params: dict | None = None) -> list:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        try:
            r = self.session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            body = r.json()
        except requests.exceptions.ConnectionError:
            raise UEXError("Impossible de joindre uexcorp.space — vérifiez votre connexion")
        except requests.exceptions.Timeout:
            raise UEXError(f"Timeout ({self.timeout}s) — {endpoint}")
        except requests.exceptions.HTTPError as e:
            raise UEXError(f"HTTP {r.status_code} — {endpoint}") from e
        except Exception as e:
            raise UEXError(f"Erreur inattendue : {e}") from e

        if body.get("status") != "ok":
            raise UEXError(f"API error: {body.get('message', 'unknown')}")
        return body.get("data") or []

    # ── Données statiques ─────────────────────────────────────────────────

    def get_commodities(self) -> list[dict]:
        return self._get("commodities")

    def get_terminals(self) -> list[dict]:
        return self._get("terminals")

    def get_star_systems(self) -> list[dict]:
        return self._get("star_systems")

    def get_planets(self) -> list[dict]:
        return self._get("planets")

    def get_factions(self) -> list[dict]:
        return self._get("factions")

    # ── Données dynamiques (prix) ─────────────────────────────────────────

    def get_prices(
        self,
        id_commodity: int | None = None,
        id_terminal: int | None = None,
    ) -> list[dict]:
        if not id_commodity and not id_terminal:
            raise UEXError("id_commodity ou id_terminal requis")
        params: dict = {}
        if id_commodity:
            params["id_commodity"] = id_commodity
        if id_terminal:
            params["id_terminal"] = id_terminal
        return self._get("commodities_prices", params)

    def get_routes(self, id_terminal_origin: int) -> list[dict]:
        return self._get("commodities_routes", {"id_terminal_origin": id_terminal_origin})
