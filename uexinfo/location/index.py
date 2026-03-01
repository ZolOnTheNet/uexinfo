"""LocationIndex — résolution fuzzy de noms de lieux Star Citizen."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uexinfo.cache.manager import CacheManager

try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    _HAS_RAPIDFUZZ = False


@dataclass
class LocationEntry:
    name: str
    type: str           # "system"|"planet"|"moon"|"station"|"city"|"outpost"|"terminal"
    system: str         # nom du système parent
    full_path: str      # "Stanton.Hurston.Lorville" (séparateur ".")
    entity_id: int


class LocationIndex:
    def __init__(self, cache: "CacheManager"):
        self._entries: list[LocationEntry] = []
        self._build(cache)

    def _build(self, cache: "CacheManager") -> None:
        # StarSystems
        for sys in cache.star_systems:
            self._entries.append(LocationEntry(
                name=sys.name,
                type="system",
                system=sys.name,
                full_path=sys.name,
                entity_id=sys.id,
            ))

        # Planets
        for planet in cache.planets:
            self._entries.append(LocationEntry(
                name=planet.name,
                type="planet",
                system=planet.star_system_name,
                full_path=f"{planet.star_system_name}.{planet.name}",
                entity_id=planet.id,
            ))

        # Terminals — dédupliqués par lieu (sans préfixe service "Admin - ", "Shop - "…)
        seen_locs: set[str] = set()
        for t in cache.terminals:
            # "Admin - ARC-L1" → "ARC-L1"   "TDD - Trade … - Area 18" → "Area 18"
            loc_name = t.name.rsplit(" - ", 1)[-1].strip()
            if loc_name in seen_locs:
                continue
            seen_locs.add(loc_name)

            # Chemin géographique sans le nom du terminal
            geo_raw = [p.strip() for p in [
                t.star_system_name,
                t.planet_name,
                t.orbit_name,
                t.space_station_name or t.city_name,
            ] if p and p.strip()]

            # Dédupliquer les segments consécutifs identiques (ex: Bloom/Bloom)
            geo: list[str] = []
            for seg in geo_raw:
                if not geo or seg.lower() != geo[-1].lower():
                    geo.append(seg)

            # Ajouter loc_name seulement s'il est différent du dernier élément géo
            if not geo or geo[-1].lower() != loc_name.lower():
                geo.append(loc_name)

            self._entries.append(LocationEntry(
                name=loc_name,
                type="terminal",
                system=t.star_system_name,
                full_path=".".join(geo),
                entity_id=t.id,
            ))

    def search(
        self,
        query: str,
        limit: int = 10,
        types: set[str] | None = None,
    ) -> list[LocationEntry]:
        """Recherche de lieux : préfixe → sous-chaîne → fuzzy.

        Args:
            query: texte à chercher (supports dot-notation "stanton.grim")
            limit: nombre max de résultats
            types: filtre sur le type d'entrée {"terminal","planet","system",…}
        """
        pool = self._entries if not types else [e for e in self._entries if e.type in types]

        if not query:
            return pool[:limit]

        if "." in query:
            parts = query.split(".")
            last = parts[-1].lower()
            prefix_str = ".".join(parts[:-1]).lower()
            candidates = [e for e in pool if e.full_path.lower().startswith(prefix_str)] or pool
            return self._search_ranked(last, candidates, limit)
        else:
            return self._search_ranked(query.lower(), pool, limit)

    def _search_ranked(
        self, query: str, entries: list[LocationEntry], limit: int
    ) -> list[LocationEntry]:
        """Tri : préfixe du nom → sous-chaîne → fuzzy."""
        seen: set[int] = set()
        result: list[LocationEntry] = []

        def _add(e: LocationEntry) -> None:
            if id(e) not in seen:
                seen.add(id(e))
                result.append(e)

        # 1. Préfixe exact (case-insensitive)
        for e in entries:
            if e.name.lower().startswith(query):
                _add(e)

        if len(result) >= limit:
            return result[:limit]

        # 2. Sous-chaîne (case-insensitive)
        for e in entries:
            if query in e.name.lower():
                _add(e)

        if len(result) >= limit:
            return result[:limit]

        # 3. Fuzzy sur le reste
        remaining = [e for e in entries if id(e) not in seen]
        result.extend(self._fuzzy_search(query, remaining, limit - len(result)))
        return result[:limit]

    def _fuzzy_search(
        self, query: str, entries: list[LocationEntry], limit: int
    ) -> list[LocationEntry]:
        if not entries or limit <= 0:
            return []

        names = [e.name for e in entries]

        if _HAS_RAPIDFUZZ:
            results = _rf_process.extract(
                query, names, scorer=_rf_fuzz.WRatio, limit=limit, score_cutoff=40
            )
            seen: set[int] = set()
            out = []
            for _name, _score, idx in results:
                if idx not in seen:
                    seen.add(idx)
                    out.append(entries[idx])
            return out
        else:
            matches = difflib.get_close_matches(query, names, n=limit, cutoff=0.3)
            out = []
            seen_names: set[str] = set()
            for m in matches:
                for e in entries:
                    if e.name == m and e.name not in seen_names:
                        seen_names.add(e.name)
                        out.append(e)
                        break
            return out

    def all_names(self) -> list[str]:
        return [e.name for e in self._entries]
