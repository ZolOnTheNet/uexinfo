"""Reconnaissance de noms — UNE seule procédure pour tout le projet (décision D6).

Systèmes, planètes, lunes, stations, villes, avant-postes, terminaux,
commodités, vaisseaux, nœuds du graphe de navigation.

    from uexinfo.names import resolve, get_index
    r = resolve(ctx, "lorville", kinds={"terminal"})
    r.best, r.ambiguous, r.candidates

Choisir un objet à partir d'une saisie (accepter, lister ou proposer) : `uexinfo.cli.choose`.
Désigner un objet sans son nom : `#type:id` (`uexinfo.names.refs`).
"""
from uexinfo.names.normalize import norm
from uexinfo.names.refs import link, parse_link, parse_ref, ref
from uexinfo.names.resolver import (
    EXACT, FUZZY, PREFIX, SUBSTRING, THRESHOLDS,
    Entity, Match, NameIndex, Resolution, build_index, get_index, graph_index, match_text,
    resolve, terminal_group, terminal_priority, trading_terminal,
)

__all__ = [
    "norm", "EXACT", "PREFIX", "SUBSTRING", "FUZZY", "THRESHOLDS",
    "Entity", "Match", "NameIndex", "Resolution", "build_index", "get_index",
    "resolve", "terminal_priority", "terminal_group", "trading_terminal", "graph_index", "match_text",
    "ref", "parse_ref", "link", "parse_link",
]
