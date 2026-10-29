"""Affichage centralisé des noms de lieux, avec troncature contrôlée.

Usage
-----
    from uexinfo.display.loc import loc_display
    txt = loc_display("Faithful Dream Station", max_chars=20)
    # → "Faithful Dream"

Un nom raccourci n'est jamais relu pour retrouver le lieu : pour le rendre
cliquable, l'appelant l'entoure d'un lien vers l'objet (`uexinfo.names.link`,
décision D11). L'ancien registre abréviation → nom complet, qui réécrivait aussi
les commandes tapées, a été retiré (il transformait « Faithful Dream Station »
en « Faithful Dream Station Station »).
"""
from __future__ import annotations

import re

# ── Regex de nettoyage des suffixes génériques ────────────────────────────

SUFFIX_RE = re.compile(
    r"\s+(Station|Harbor|Port|Hub|Base|Outpost|Settlement|Colony|"
    r"City|Center|Centre|Landing|Platform|Relay)\b.*$",
    re.IGNORECASE,
)

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
    - Sinon troncature forcée avec suffixe '*' (« Faithful* » se tape aussi
      comme début de nom, voir `uexinfo.names`).
    """
    if not name:
        return "—"

    candidate = _canonical_short(name) if short else name

    if len(candidate) <= max_chars:
        return candidate

    # Troncature forcée nécessaire
    return candidate[:max_chars - 1] + "*"
