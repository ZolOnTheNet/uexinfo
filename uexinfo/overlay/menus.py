"""Mode souris de l'overlay : catalogue des boutons (docs/PROPOSITION_MENUS_SOURIS.html).

Trois modes d'affichage, choisis par le bouton à côté de ⚙ ou par `/config mode` :
- console : la ligne de commande seule ;
- mixte   : la barre des thèmes au-dessus de la sortie, et la ligne de commande ;
- souris  : les boutons toujours ouverts, sans ligne de commande.

Un bouton envoie une commande qui existe déjà : boutons et saisie passent par le même
`dispatch`, il n'y a qu'une implémentation par fonction. Le catalogue est envoyé à la
page à la connexion (message `menus`) ; `tests/test_menus.py` vérifie que chaque
commande vise une commande enregistrée.

Premier pas : thèmes, groupes et commandes sans paramètre. Les boutons à paramètre
(listes de valeurs tirées du vocabulaire, saisie libre) et le minage viendront ensuite.
"""
from __future__ import annotations

MODES = ("console", "mixte", "souris")


def _run(label: str, cmd: str, note: str = "") -> dict:
    """Bouton qui exécute `cmd` au clic."""
    return {"label": label, "cmd": cmd, **({"note": note} if note else {})}


def _group(label: str, *kids: dict) -> dict:
    """Bouton qui ouvre un groupe de boutons."""
    return {"label": label, "kids": list(kids)}


THEMES: list[dict] = [
    {"id": "info", "label": "Info", "short": "Info.", "icon": "ⓘ", "kids": [
        _run("Ici (ma position)", "/info"),
        _run("Ma destination", "/info dest"),
        _run("Commodités", "/info list"),
        _group("Explorer",
               _run("Stanton", "/explore stanton"),
               _run("Pyro", "/explore pyro"),
               _run("Nyx", "/explore nyx"),
               _run("Commodités", "/explore commodity"),
               _run("Vaisseaux", "/explore ship")),
        _group("Position",
               _run("Je suis arrivé", "/arriver"),
               _run("Effacer la destination", "/dest clear"),
               _run("Réseau de transport", "/nav")),
        _group("Jeu",
               _run("État", "/game"),
               _run("Suivi en direct", "/game live"),
               _run("Évènements", "/game events")),
        _run("Mes notes", "/note"),
    ]},
    {"id": "trade", "label": "Trade", "short": "Trade", "icon": "$", "kids": [
        _run("Bilan position → destination", "/trade"),
        _run("Vendre ma cargaison", "/trade vendre", "Ouvre le formulaire de vente."),
        _run("Routes sc-trade", "/trade sctrade", "Données de la communauté."),
        _group("Relevés de prix",
               _run("Lire les captures", "/scan"),
               _run("Lire le log Datarunner", "/scan log"),
               _run("Synchroniser ma position", "/sync"),
               _run("Annuler le dernier scan", "/undo")),
        _group("Filtres",
               _run("Voir", "/select show"),
               _run("Tout effacer", "/select clear")),
    ]},
    {"id": "miss", "label": "Missions", "short": "Miss.", "icon": "◎", "kids": [
        _run("Mes missions", "/mission list"),
        _run("Offres du mobiGlas", "/mission offres"),
        _run("Missions capturées", "/mission scan"),
        _run("Ajouter depuis le scan", "/mission add"),
        _run("Lieux à préciser", "/mission lieux"),
        _group("Voyages",
               _run("Voyage actif", "/voyage"),
               _run("Mes voyages", "/voyage list"),
               _group("Calculer",
                      _run("Au bénéfice", "/voyage calc benef"),
                      _run("À la distance", "/voyage calc dist"),
                      _run("Au rendement (ROI)", "/voyage calc roi"),
                      _run("Tous les critères", "/voyage calc all")),
               _run("Accepter le calcul", "/voyage accept")),
    ]},
    {"id": "ship", "label": "Vaisseaux", "short": "Vaiss.", "icon": "✈", "kids": [
        _run("Ma flotte", "/ship list"),
        _run("Mon état", "/player"),
        _run("Par fabricant", "/explore ship"),
    ]},
    {"id": "sys", "label": "Réglages", "short": "Régl.", "icon": "⚙", "kids": [
        _run("Configuration", "/config"),
        _group("Rafraîchir",
               _run("Les prix", "/refresh prices"),
               _run("Les données", "/refresh all")),
        _run("Version et univers", "/evolution"),
        _run("Historique", "/history"),
        _run("Aide", "/help"),
    ]},
]


def commands(nodes: list[dict] | None = None) -> list[str]:
    """Toutes les commandes du catalogue (parcours en profondeur)."""
    out: list[str] = []
    for n in (THEMES if nodes is None else nodes):
        if "cmd" in n:
            out.append(n["cmd"])
        out += commands(n.get("kids", []))
    return out
