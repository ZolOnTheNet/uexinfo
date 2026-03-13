"""Cache de prix UEX persistant sur disque.

Remplace ctx._price_cache (dict en mémoire) par un store disque avec :
  - Persistance entre sessions
  - Métadonnées : âge, version du jeu, fréquence d'usage
  - TTL adaptatif : données consultées fréquemment → rafraîchies plus souvent
  - Marquage version : distances et tailles de cargo ne périment qu'au changement de version SC

Interface dict-compatible pour ne pas modifier les call sites existants :
  cache.get(key)                → (ts_float, data) | None
  cache[key] = (ts, data)       → stocke sur disque
  key in cache                  → vérifie existence et validité
  cache.copy_entry(src, dst)    → copie un enregistrement
  cache.clear()                 → vide tout
  cache.age_str(key)            → "2h", "3j", "2 mois"
  cache.weekly_count(key)       → nb consultations sur 7 jours
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import appdirs

# ── Configuration ─────────────────────────────────────────────────────────────

# Version du jeu Star Citizen — données version-spécifiques ne périment qu'ici
SC_VERSION = "4.6"

_CACHE_FILE = Path(appdirs.user_data_dir("uexinfo")) / "price_cache.json"

# Préfixes de clés dont les données dépendent de la version du jeu (pas du temps)
_VERSION_TAGGED = ("cs_", "rd_", "vp_", "vr_")

# TTL de base pour données marché (prix), en secondes
_TTL_DAILY    =  4 * 3600   # consulté très souvent  (≥ 7×/semaine) → 4h
_TTL_FREQUENT = 12 * 3600   # consulté souvent       (≥ 3×/semaine) → 12h
_TTL_NORMAL   = 24 * 3600   # consulté parfois       (≥ 1×/semaine) → 24h
_TTL_RARE     = 72 * 3600   # consulté rarement                     → 3j


def _is_version_tagged(key: str) -> bool:
    return any(key.startswith(p) for p in _VERSION_TAGGED)


def _adaptive_ttl(entry: dict) -> float:
    """TTL adaptatif basé sur la fréquence de consultation (7 derniers jours)."""
    now = time.time()
    week_ago = now - 7 * 86400
    weekly = sum(1 for t in entry.get("query_times", []) if t > week_ago)
    if weekly >= 7:
        return _TTL_DAILY
    if weekly >= 3:
        return _TTL_FREQUENT
    if weekly >= 1:
        return _TTL_NORMAL
    return _TTL_RARE


# ── Classe principale ──────────────────────────────────────────────────────────

class PriceCache:
    """Cache de prix UEX persistant, remplace ctx._price_cache."""

    def __init__(self):
        self._mem: dict = {}   # clé → {data, fetched_at, game_version, query_times}
        self._dirty = False
        self._loaded = False

    # ── Persistence ───────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if _CACHE_FILE.exists():
            try:
                with open(_CACHE_FILE, encoding="utf-8") as f:
                    self._mem = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._mem = {}

    def flush(self) -> None:
        """Sauvegarde sur disque si des changements ont eu lieu."""
        if not self._dirty:
            return
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._mem, f, ensure_ascii=False)
            self._dirty = False
        except OSError:
            pass

    def _save(self) -> None:
        """Flush immédiat (utilisé après chaque écriture critique)."""
        self._dirty = True
        self.flush()

    # ── Validation d'une entrée ───────────────────────────────────────────────

    def _is_valid(self, key: str, entry: dict) -> bool:
        if not entry or "data" not in entry:
            return False
        fetched_at = entry.get("fetched_at", 0)
        if _is_version_tagged(key):
            return entry.get("game_version") == SC_VERSION
        return (time.time() - fetched_at) < _adaptive_ttl(entry)

    # ── Interface dict-compatible ─────────────────────────────────────────────

    def get(self, key: str) -> tuple[float, list] | None:
        """Retourne (fetched_at, data) si valide, None sinon."""
        self._ensure_loaded()
        entry = self._mem.get(key)
        if not entry or not self._is_valid(key, entry):
            return None
        self._record_query(key)
        return entry["fetched_at"], entry["data"]

    def __contains__(self, key: str) -> bool:
        self._ensure_loaded()
        entry = self._mem.get(key)
        return bool(entry and self._is_valid(key, entry))

    def __setitem__(self, key: str, value: tuple[float, list]) -> None:
        """Stocke (ts, data) — interface compatible avec l'ancien dict."""
        self._ensure_loaded()
        ts, data = value
        entry = self._mem.get(key, {})
        entry.update({
            "data": data,
            "fetched_at": time.time(),   # toujours time.time() pour la persistance
            "game_version": SC_VERSION,
            "query_times": entry.get("query_times", []),
        })
        self._mem[key] = entry
        self._save()

    def __getitem__(self, key: str) -> tuple[float, list]:
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    def copy_entry(self, src: str, dst: str) -> None:
        """Copie un enregistrement sous une autre clé (sans re-fetch)."""
        self._ensure_loaded()
        if src in self._mem and dst not in self._mem:
            self._mem[dst] = dict(self._mem[src])
            self._save()

    def clear(self) -> None:
        """Vide le cache mémoire ET disque (utilisé par /refresh prices)."""
        self._ensure_loaded()
        self._mem.clear()
        self._dirty = True
        self.flush()

    # ── Fréquence d'usage ─────────────────────────────────────────────────────

    def _record_query(self, key: str) -> None:
        entry = self._mem.get(key)
        if not entry:
            return
        now = time.time()
        times = [t for t in entry.get("query_times", []) if t > now - 30 * 86400]
        times.append(now)
        entry["query_times"] = times
        self._dirty = True   # flush différé (pas critique)

    def weekly_count(self, key: str) -> int:
        """Nombre de consultations sur les 7 derniers jours."""
        self._ensure_loaded()
        entry = self._mem.get(key, {})
        week_ago = time.time() - 7 * 86400
        return sum(1 for t in entry.get("query_times", []) if t > week_ago)

    # ── Affichage ─────────────────────────────────────────────────────────────

    def age_str(self, key: str) -> str:
        """Âge lisible de la donnée : '5 min', '2h', '3j', '2 mois', 'v4.6'."""
        self._ensure_loaded()
        entry = self._mem.get(key)
        if not entry:
            return ""
        if _is_version_tagged(key):
            v = entry.get("game_version", "?")
            return f"v{v}"
        fetched_at = entry.get("fetched_at", 0)
        if not fetched_at:
            return ""
        age = time.time() - fetched_at
        if age < 3600:
            return f"{int(age // 60)} min"
        if age < 86400:
            return f"{int(age // 3600)}h"
        if age < 30 * 86400:
            return f"{int(age // 86400)}j"
        if age < 365 * 86400:
            return f"{int(age // (30 * 86400))} mois"
        return f"{int(age // (365 * 86400))} an(s)"

    def ttl_str(self, key: str) -> str:
        """Prochain rafraîchissement prévu : '3h 12 min', 'v4.6 (permanent)'."""
        self._ensure_loaded()
        entry = self._mem.get(key)
        if not entry:
            return ""
        if _is_version_tagged(key):
            return f"v{SC_VERSION} (permanent)"
        fetched_at = entry.get("fetched_at", 0)
        ttl = _adaptive_ttl(entry)
        remaining = ttl - (time.time() - fetched_at)
        if remaining <= 0:
            return "expiré"
        if remaining < 3600:
            return f"{int(remaining // 60)} min"
        return f"{int(remaining // 3600)}h {int((remaining % 3600) // 60)} min"
