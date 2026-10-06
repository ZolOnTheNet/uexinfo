"""Mémoire des versions SC et des changements d'univers (décision D3, /evolution).

Fichier : <données utilisateur>/evolution.json
  last_seen_version  dernière version SC observée (prix UEX, config…)
  universe_version   version à partir de laquelle l'univers est considéré changé
                     (None = jamais déclaré → distances/conteneurs toujours valables)
  answers            {"4.10": "oui"|"non"} — question posée une fois par majeur.mineur
  pending            majeur.mineur en attente de réponse ("" sinon)
  watch_started_at / last_change_at   mode surveillance (WATCH_DAYS jours)
  known_ids          {catégorie: [id UEX]} — référence pour détecter les ajouts
  last_diff / last_check_at           résultat de la dernière comparaison
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from uexinfo.rules.version import (
    diff_ids, minor_key, universe_question_needed, watch_active,
)

# Catégories d'entités UEX comparées (attribut de CacheManager)
WATCHED_CATEGORIES = ("terminals", "space_stations", "outposts", "cities",
                      "planets", "moons", "orbits", "star_systems")

_DEFAULT = {
    "last_seen_version": "",
    "universe_version": None,
    "answers": {},
    "pending": "",
    "watch_started_at": None,
    "last_change_at": None,
    "known_ids": {},
    "last_diff": {"added": {}, "removed": {}},
    "last_check_at": None,
}


class EvolutionStore:
    def __init__(self, path: Path | str | None = None):
        if path is None:
            from uexinfo.cache.manager import DATA_DIR
            path = DATA_DIR / "evolution.json"
        self.path = Path(path)
        self.state = dict(_DEFAULT)
        self._load()

    # ── Persistance ──────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.state.update({k: data[k] for k in _DEFAULT if k in data})
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    # ── Version ──────────────────────────────────────────────────────────────
    @property
    def current_version(self) -> str:
        return self.state["last_seen_version"]

    @property
    def universe_version(self) -> str | None:
        return self.state["universe_version"]

    @property
    def pending(self) -> str:
        return self.state["pending"]

    def observe_version(self, version: str) -> bool:
        """Enregistre une version observée. True si une question vient d'être ouverte."""
        if not version or version == self.state["last_seen_version"]:
            return False
        old = self.state["last_seen_version"]
        self.state["last_seen_version"] = version
        opened = False
        mk = minor_key(version)
        if old and universe_question_needed(old, version) and mk not in self.state["answers"]:
            self.state["pending"] = mk
            opened = True
        self.save()
        return opened

    def answer(self, changed: bool, now: float | None = None) -> None:
        """Réponse du joueur pour la version courante (« Je ne sais pas » = changed=True)."""
        now = time.time() if now is None else now
        mk = minor_key(self.current_version)
        if mk:
            self.state["answers"][mk] = "oui" if changed else "non"
        self.state["pending"] = ""
        if changed:
            self.state["universe_version"] = self.current_version or self.state["universe_version"]
            self.state["watch_started_at"] = now
        else:
            self.state["watch_started_at"] = None
        self.save()

    # ── Surveillance ─────────────────────────────────────────────────────────
    def watching(self, now: float | None = None) -> bool:
        started = self.state["watch_started_at"]
        if started is None:
            return False
        now = time.time() if now is None else now
        return watch_active(started, self.state["last_change_at"], now)

    def watch_days_left(self, now: float | None = None) -> float:
        if not self.watching(now):
            return 0.0
        now = time.time() if now is None else now
        ref = max(self.state["watch_started_at"], self.state["last_change_at"] or 0.0)
        from uexinfo.rules.version import WATCH_DAYS
        return max(0.0, WATCH_DAYS - (now - ref) / 86400)

    def check(self, current_ids: dict[str, list[int]], now: float | None = None) -> dict:
        """Compare les ID UEX courants à la référence et met la référence à jour.

        Un ajout ou un retrait relance la surveillance et déclare l'univers changé
        à la version courante (les distances/conteneurs seront re-téléchargés).
        """
        now = time.time() if now is None else now
        diff = diff_ids(self.state["known_ids"], current_ids)
        self.state["known_ids"] = {k: sorted(v) for k, v in current_ids.items()}
        self.state["last_diff"] = diff
        self.state["last_check_at"] = now
        if diff["added"] or diff["removed"]:
            self.state["last_change_at"] = now
            if self.current_version:
                self.state["universe_version"] = self.current_version
        self.save()
        return diff


def collect_ids(cache) -> dict[str, list[int]]:
    """ID UEX par catégorie depuis un CacheManager (catégories vides ignorées)."""
    out: dict[str, list[int]] = {}
    for cat in WATCHED_CATEGORIES:
        items = getattr(cache, cat, None) or []
        ids = [int(i.id) for i in items if getattr(i, "id", None)]
        if ids:
            out[cat] = ids
    return out
