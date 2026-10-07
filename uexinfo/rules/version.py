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
    """True si majeur.mineur augmente (patch ignoré). Retour à une version
    plus ancienne (bascule PTU/LIVE) ou version illisible ⇒ False."""
    a, b = parse_version(old), parse_version(new)
    if a is None or b is None:
        return False
    return b[:2] > a[:2]


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


def minor_key(text: str | None) -> str:
    """'4.10.1' → '4.10' (clé de mémorisation des réponses) ; illisible → ''."""
    v = parse_version(text)
    return f"{v[0]}.{v[1]}" if v else ""


def entry_valid_for_universe(entry_version: str | None, universe_version: str | None) -> bool:
    """Donnée liée à l'univers (distances, conteneurs…) encore valable ?

    Valable si aucun changement d'univers n'a été déclaré, ou si elle a été
    produite à partir de la version où l'univers a changé (ou après).
    """
    u = parse_version(universe_version)
    if u is None:
        return True
    e = parse_version(entry_version)
    return e is not None and e >= u


def diff_ids(old: dict[str, list[int]], new: dict[str, list[int]]) -> dict[str, dict[str, list[int]]]:
    """Compare des listes d'ID UEX par catégorie → {'added': {cat: [...]}, 'removed': {...}}.

    Une catégorie absente de `old` est une première observation, pas un ajout.
    """
    added: dict[str, list[int]] = {}
    removed: dict[str, list[int]] = {}
    for cat, ids in new.items():
        if cat not in old:
            continue
        a, b = set(old[cat]), set(ids)
        if b - a:
            added[cat] = sorted(b - a)
        if a - b:
            removed[cat] = sorted(a - b)
    return {"added": added, "removed": removed}


def _mm(text: str | None) -> tuple[int, int] | None:
    v = parse_version(text)
    return v[:2] if v else None


def kept_versions(current: str | None, present) -> set[tuple[int, int]]:
    """Versions majeur.mineur conservées (décision D10) : la courante et, au pire,
    la précédente PRÉSENTE dans les données — jamais de trou au changement de version,
    jamais plus vieux que la version d'avant.

    `current` illisible ⇒ la plus récente présente sert de version courante.
    """
    have = {m for m in (_mm(p) for p in present) if m}
    cur = _mm(current) or (max(have) if have else None)
    if cur is None:
        return set()
    older = [m for m in have if m < cur]
    return {cur, max(older)} if older else {cur}


def keep_recent_rows(rows: list[dict], current: str | None, key: str = "game_version") -> list[dict]:
    """Retire les lignes plus vieilles que la version précédente (D10).

    Une ligne sans version lisible est gardée (on ne peut pas la juger).
    """
    keep = kept_versions(current, (r.get(key) for r in rows))
    if not keep:
        return list(rows)
    return [r for r in rows if _mm(r.get(key)) is None or _mm(r.get(key)) in keep]
