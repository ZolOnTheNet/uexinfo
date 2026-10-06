"""Versions de Star Citizen et changements d'univers (décision D3).

- Seul un changement majeur.mineur (4.10 → 4.11) pose la question « l'univers
  a-t-il changé ? » ; un patch (4.10.0 → 4.10.1) ne la pose pas.
- Une donnée d'une version plus ancienne reste utilisable, avec un marqueur
  « vX.Y », tant qu'il n'existe rien de plus récent (option c).
- Mode surveillance : actif tant que moins de WATCH_DAYS jours se sont écoulés
  depuis le dernier changement constaté (ou depuis son déclenchement).
"""
from __future__ import annotations

import re

WATCH_DAYS = 7  # D3 : durée du mode surveillance sans changement

_VER_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """'4.10.1' → (4, 10, 1) ; 'Alpha 4.10' → (4, 10, 0) ; illisible → None."""
    m = _VER_RE.search(text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def universe_question_needed(old: str | None, new: str | None) -> bool:
    """True si majeur.mineur diffère (patch ignoré). Version illisible ⇒ False."""
    a, b = parse_version(old), parse_version(new)
    if a is None or b is None:
        return False
    return a[:2] != b[:2]


def version_marker(data_version: str | None, current: str | None) -> str:
    """Marqueur à afficher pour une donnée d'une version majeur.mineur plus ancienne."""
    d, c = parse_version(data_version), parse_version(current)
    if d is None or c is None or d[:2] >= c[:2]:
        return ""
    return f"v{d[0]}.{d[1]}"


def pick_by_version(entries: list[dict], key: str = "sc_version") -> dict | None:
    """Option c : garde l'entrée de la version la plus récente (illisible = la plus ancienne)."""
    if not entries:
        return None
    return max(entries, key=lambda e: parse_version(e.get(key)) or (-1, -1, -1))


def watch_active(started_at: float, last_change_at: float | None, now: float) -> bool:
    """Surveillance active tant que < WATCH_DAYS jours depuis le dernier événement."""
    ref = max(started_at, last_change_at or 0.0)
    return now - ref < WATCH_DAYS * 86400
