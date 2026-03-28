"""Affichage centralisé des noms de lieux — CLI, TUI et overlay.

Point d'entrée unique pour formater les noms de lieux avec troncature
contrôlée.  Alimente un registre global abbrev→complet utilisé par
l'overlay pour rendre les noms abrégés cliquables.

Usage
-----
    from uexinfo.display.loc import loc_display
    txt = loc_display("Faithful Dream Station", max_chars=20)
    # → "Faithful Dream"  (registre: "Faithful Dream" → "Faithful Dream Station")

Overlay
-------
    Après chaque commande, le serveur appelle flush_abbrevs() et envoie
    le message {type:'loc_abbrevs', map:{...}} au client JS.  Le JS
    annote les noms abrégés dans l'output et les rend cliquables :
    clic → nom complet inséré dans la zone de saisie.

Input
-----
    resolve_cmd_line(line) résout les tokens abrégés (avec ou sans '*')
    avant exécution, en s'appuyant sur le registre.
"""
from __future__ import annotations

import re
import threading

# ── Regex de nettoyage des suffixes génériques ────────────────────────────

SUFFIX_RE = re.compile(
    r"\s+(Station|Harbor|Port|Hub|Base|Outpost|Settlement|Colony|"
    r"City|Center|Centre|Landing|Platform|Relay)\b.*$",
    re.IGNORECASE,
)

# ── Registre global abbrev → nom complet ──────────────────────────────────
# Persistant : grossit au fil des commandes, jamais vidé.
# flush_abbrevs() en retourne une copie pour l'overlay.

_abbrev_map: dict[str, str] = {}
_abbrev_lock = threading.Lock()


# ── Helpers internes ──────────────────────────────────────────────────────

def _canonical_short(name: str) -> str:
    """Forme courte sémantique d'un nom de lieu.

    - Code de point Lagrange/Stanton : 'MIC-L2 Long Forest Station' → 'MIC-L2'
    - Sinon : 2 premiers mots après suppression du suffixe générique.
      'Faithful Dream Station' → 'Faithful Dream'
      'Everus Harbor'          → 'Everus Harbor'   (≤ 2 mots, conservé)
    """
    m = re.match(r"^([A-Z]{2,4}-[A-Z]\d+)", name)
    if m:
        return m.group(1)
    cleaned = SUFFIX_RE.sub("", name).strip()
    words = cleaned.split()
    return " ".join(words[:2]) if len(words) > 2 else cleaned


def _register(abbrev: str, full: str) -> None:
    """Enregistre une abréviation → nom complet dans le registre."""
    with _abbrev_lock:
        _abbrev_map[abbrev] = full


# ── API publique ──────────────────────────────────────────────────────────

def loc_display(name: str, max_chars: int = 20, short: bool = True) -> str:
    """Formate un nom de lieu pour affichage (CLI, TUI, overlay).

    Parameters
    ----------
    name:
        Nom complet du lieu (ex: "Faithful Dream Station").
    max_chars:
        Largeur max disponible en caractères.
    short:
        True  → forme courte sémantique (HUR-L1, "Faithful Dream").
        False → nom complet, pas de raccourci sémantique.

    Returns
    -------
    Chaîne de longueur ≤ max_chars.
    - Forme courte sémantique si elle tient (et est différente du nom complet).
    - Sinon troncature forcée avec suffixe '*' (nom complet dans le registre).
    Les abréviations (sémantiques ET forcées) sont enregistrées pour l'overlay.
    """
    if not name:
        return "—"

    candidate = _canonical_short(name) if short else name

    if len(candidate) <= max_chars:
        if candidate != name:
            _register(candidate, name)
        return candidate

    # Troncature forcée nécessaire
    truncated = candidate[:max_chars - 1] + "*"
    _register(truncated, name)
    return truncated


def flush_abbrevs() -> dict[str, str]:
    """Retourne une copie du registre abbrev→complet pour l'overlay.

    Ne vide PAS le registre (les abréviations restent disponibles
    pour resolve_cmd_line() lors de la prochaine commande).
    """
    with _abbrev_lock:
        return dict(_abbrev_map)


def resolve_cmd_line(line: str) -> str:
    """Résout les abréviations connues dans une ligne de commande.

    Remplace les tokens abrégés (sémantiques OU force-tronqués avec '*')
    par leur nom complet.  Exemples :
        '/go Faithful Dream'   → '/go Faithful Dream Station'
        '/info Faithful*'      → '/info Faithful Dream Station'

    Le tri décroissant par longueur évite les substitutions partielles
    (ex: "HUR-L1" avant "HUR" si les deux sont dans le registre).
    """
    with _abbrev_lock:
        if not _abbrev_map:
            return line
        for abbrev in sorted(_abbrev_map, key=len, reverse=True):
            if abbrev in line:
                line = line.replace(abbrev, _abbrev_map[abbrev])
    return line
