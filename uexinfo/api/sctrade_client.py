"""Client sc-trade.tools — Phase 4 (stub)."""
from __future__ import annotations


class SCTradeClient:
    """Accès aux données sc-trade.tools (affichées en orange).

    Phase 4 : implémentation via API interne XHR ou Playwright.
    """

    BASE_URL = "https://sc-trade.tools"

    def get_commodity(self, slug: str) -> dict | None:
        """Retourne les données de prix pour une commodité, ou None."""
        raise NotImplementedError("sc-trade.tools — Phase 4 non implémentée")
