"""Références d'objets (décision D11) : désigner un objet par son type et son identifiant.

Une référence s'écrit `#type:id` dans une commande (`/info #commodity:42`) : le
résolveur la traite avant tout nom, sans aucune ressemblance. Les liens cliquables
de l'overlay portent la même référence (`[link=uex:type:id]…[/link]` dans le rendu
Rich), si bien qu'un nom affiché raccourci (« Amm…7 ») désigne toujours l'objet exact.

Identifiants : numéro UEX pour les objets UEX ; nom du nœud, espaces remplacés par
`_`, pour les nœuds du graphe de navigation (une référence ne contient jamais d'espace).
"""
from __future__ import annotations

from typing import Any

KINDS = ("system", "planet", "moon", "station", "city", "outpost",
         "terminal", "commodity", "vehicle", "node")
PLACE_KINDS = ("station", "city", "outpost")
LINK_SCHEME = "uex:"

# Famille affichée par l'overlay (menu contextuel) pour chaque type
LINK_TYPES = {
    "commodity": "commodity", "vehicle": "ship",
    **{k: "location" for k in ("system", "planet", "moon", "station", "city",
                               "outpost", "terminal", "node")},
}


def ref(kind: str, ident: Any) -> str:
    """Référence `type:id` (sans le `#`), ex. `terminal:251`, `node:Port_Tressler`."""
    return f"{kind}:{str(ident).replace(' ', '_')}"


def parse_ref(text: str | None) -> tuple[str, str] | None:
    """`#type:id` → (type, id) ; None si le texte n'est pas une référence."""
    t = (text or "").strip()
    if not t.startswith("#"):
        return None
    kind, sep, ident = t[1:].partition(":")
    kind = kind.strip().lower()
    if not sep or kind not in KINDS or not ident.strip():
        return None
    return kind, ident.strip()


def link(kind: str, ident: Any, text: str) -> str:
    """Markup Rich d'un lien vers l'objet : l'overlay le rend cliquable par sa référence."""
    return f"[link={LINK_SCHEME}{ref(kind, ident)}]{text}[/link]"


def parse_link(url: str | None) -> tuple[str, str] | None:
    """`uex:type:id` (lien Rich) → (type, id) ; None pour tout autre lien."""
    if not url or not url.startswith(LINK_SCHEME):
        return None
    return parse_ref("#" + url[len(LINK_SCHEME):])
