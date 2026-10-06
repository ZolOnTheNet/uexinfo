"""Reconnaissance de noms — UNE seule procédure pour tout le projet (décision D6).

Systèmes, planètes, lunes, stations, villes, avant-postes, terminaux,
commodités, vaisseaux, nœuds du graphe de navigation.

    from uexinfo.names import resolve, get_index
    r = resolve(ctx, "lorville", kinds={"terminal"})
    r.best, r.ambiguous, r.candidates
"""
from uexinfo.names.normalize import norm
from uexinfo.names.resolver import (
    EXACT, FUZZY, PREFIX, SUBSTRING, THRESHOLDS,
    Entity, Match, NameIndex, Resolution, build_index, get_index, graph_index, match_text,
    resolve, terminal_priority,
)

__all__ = [
    "norm", "EXACT", "PREFIX", "SUBSTRING", "FUZZY", "THRESHOLDS",
    "Entity", "Match", "NameIndex", "Resolution", "build_index", "get_index",
    "resolve", "terminal_priority", "graph_index", "match_text",
]
