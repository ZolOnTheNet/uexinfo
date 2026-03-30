"""Scraper direct du site web UEX Corp (complément à l'API REST 2.0).

Certaines données ne sont disponibles que sur le site web et non via l'API :
- Missions et récompenses
- Distances détaillées entre lieux
- Infos raffinerie (méthodes, durées, rendements)
- Grilles cargo détaillées par vaisseau

Stratégie :
- BeautifulSoup + requests en priorité (données HTML statiques)
- Playwright en fallback si les données sont chargées via XHR
- Cache JSON dans ~/.uexinfo/scraped/ avec TTL 24h
- Rate limiting : 1 req/s max
- Les URLs et sélecteurs doivent être testés et ajustés manuellement
  (voir docs/CONSIGNES_Sonnet_FinMars.md §8.4 pour les URLs connues)

NOTE : Ce module est un STUB. Les sélecteurs CSS et patterns XHR doivent
être identifiés en inspectant le site dans un navigateur, puis implémentés.
La Phase 1 de reconnaissance (§8.7) doit être faite avant d'implémenter
les méthodes réelles.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import appdirs
import requests

BASE_URL = "https://uexcorp.space"
TIMEOUT = 15
RATE_LIMIT_S = 1.0  # secondes entre requêtes
SCRAPE_CACHE_TTL = 86400  # 24h


class UEXScraperError(Exception):
    pass


class UEXScraper:
    """Accès aux données du site web UEX non disponibles via l'API REST."""

    _CACHE_DIR = Path(appdirs.user_data_dir("uexinfo")) / "scraped"

    def __init__(self, timeout: int = TIMEOUT):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "uexinfo-cli/0.1 (companion tool, not a bot)",
            "Accept": "text/html,application/xhtml+xml",
        })
        self.timeout = timeout
        self._last_request_ts: float = 0.0

    # ── Helpers HTTP ──────────────────────────────────────────────────────────

    def _rate_limit(self) -> None:
        """Attend si nécessaire pour respecter le rate limit."""
        elapsed = time.time() - self._last_request_ts
        if elapsed < RATE_LIMIT_S:
            time.sleep(RATE_LIMIT_S - elapsed)
        self._last_request_ts = time.time()

    def _get_html(self, path: str) -> str:
        """Récupère le HTML d'une page UEX."""
        self._rate_limit()
        url = f"{BASE_URL}/{path.lstrip('/')}"
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.text
        except requests.exceptions.ConnectionError:
            raise UEXScraperError(f"Connexion impossible à {BASE_URL}")
        except requests.exceptions.HTTPError as e:
            raise UEXScraperError(f"HTTP {r.status_code} — {path}") from e

    def _get_soup(self, path: str):
        """Récupère et parse une page HTML via BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise UEXScraperError("beautifulsoup4 requis : pip install beautifulsoup4")
        return BeautifulSoup(self._get_html(path), "html.parser")

    # ── Cache disque ──────────────────────────────────────────────────────────

    def _cache_path(self, key: str) -> Path:
        return self._CACHE_DIR / f"{key}.json"

    def _cache_load(self, key: str) -> dict | list | None:
        """Charge depuis le cache si valide (< TTL)."""
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if time.time() - data.get("_ts", 0) < SCRAPE_CACHE_TTL:
                return data.get("data")
        except Exception:
            pass
        return None

    def _cache_save(self, key: str, data: dict | list) -> None:
        """Sauvegarde dans le cache disque."""
        self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"_ts": time.time(), "data": data}
        self._cache_path(key).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def cache_clear(self, key: str | None = None) -> int:
        """Efface le cache (tous les fichiers ou un seul). Retourne le nb supprimés."""
        if key:
            p = self._cache_path(key)
            if p.exists():
                p.unlink()
                return 1
            return 0
        if not self._CACHE_DIR.exists():
            return 0
        n = 0
        for f in self._CACHE_DIR.glob("*.json"):
            f.unlink()
            n += 1
        return n

    # ── Missions ──────────────────────────────────────────────────────────────

    def get_missions(self, force: bool = False) -> list[dict]:
        """Liste des types de missions UEX avec récompenses et factions.

        NOTE : stub — sélecteurs CSS à identifier.
        URL probable : https://uexcorp.space/missions (à confirmer).
        Si les données sont chargées en XHR, intercepter via DevTools réseau.
        """
        if not force:
            cached = self._cache_load("missions")
            if cached is not None:
                return cached

        # TODO: implémenter après reconnaissance HTML/XHR du site
        # soup = self._get_soup("/missions")
        # Identifier les sélecteurs CSS des missions dans la page
        # ...
        raise NotImplementedError(
            "get_missions() non implémenté — Phase 1 de reconnaissance requise.\n"
            "Voir docs/CONSIGNES_Sonnet_FinMars.md §8.7 Phase 1."
        )

    def get_mission_detail(self, slug: str, force: bool = False) -> dict | None:
        """Détail d'une mission spécifique (récompense, faction, conditions).

        NOTE : stub — URL et sélecteurs à identifier.
        """
        cache_key = f"mission_{slug}"
        if not force:
            cached = self._cache_load(cache_key)
            if cached is not None:
                return cached
        raise NotImplementedError("get_mission_detail() non implémenté")

    # ── Distances / Lieux ─────────────────────────────────────────────────────

    def get_terminal_distances(self, terminal_slug: str, force: bool = False) -> list[dict]:
        """Distances depuis un terminal vers les autres terminaux (Gm).

        NOTE : stub — ces données peuvent être dans l'API /commodities_routes
        (champ 'distance'). Vérifier avant d'implémenter le scraping.
        URL probable : https://uexcorp.space/terminals/<slug>
        """
        cache_key = f"distances_{terminal_slug}"
        if not force:
            cached = self._cache_load(cache_key)
            if cached is not None:
                return cached
        raise NotImplementedError("get_terminal_distances() non implémenté")

    # ── Raffinerie ────────────────────────────────────────────────────────────

    def get_refinery_info(self, terminal_slug: str, force: bool = False) -> dict | None:
        """Infos raffinerie : méthodes (CORMACK, DIN-E, KAZEN…), durées, rendements.

        NOTE : stub — URL à confirmer.
        URL probable : https://uexcorp.space/refinery (à confirmer avec le user).
        """
        cache_key = f"refinery_{terminal_slug}"
        if not force:
            cached = self._cache_load(cache_key)
            if cached is not None:
                return cached
        raise NotImplementedError("get_refinery_info() non implémenté")

    # ── Grilles cargo ─────────────────────────────────────────────────────────

    def get_vehicle_cargo_grid(self, vehicle_slug: str, force: bool = False) -> dict | None:
        """Grille cargo détaillée d'un vaisseau (tailles de boîtes, positions).

        NOTE : stub — l'API /vehicles donne seulement le SCU total.
        URL probable : https://uexcorp.space/vehicles/<slug>
        """
        cache_key = f"cargo_grid_{vehicle_slug}"
        if not force:
            cached = self._cache_load(cache_key)
            if cached is not None:
                return cached
        raise NotImplementedError("get_vehicle_cargo_grid() non implémenté")

    # ── Événements ────────────────────────────────────────────────────────────

    def get_events(self, force: bool = False) -> list[dict]:
        """Événements en cours (Jumptown, NineTails Lockdown, etc.).

        NOTE : stub — URL à fournir par le user.
        """
        if not force:
            cached = self._cache_load("events")
            if cached is not None:
                return cached
        raise NotImplementedError("get_events() non implémenté — URL inconnue")
