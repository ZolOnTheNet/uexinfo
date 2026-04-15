"""Données statiques de complétion — sous-commandes et hints.

Indépendant de prompt_toolkit et de AppContext.
Utilisé par overlay/server.py (_complete_sync).
"""
from __future__ import annotations

# ── Sous-commandes avec descriptions ──────────────────────────────────────────
# Format : {clé_contexte: [(sous-commande, description), ...]}
# La clé contexte est : "commande" ou "commande sous-commande" (profondeur 2)

SUBS: dict[str, list[tuple[str, str]]] = {
    "help": [],
    "config": [
        ("ship",                   "Gestion des vaisseaux"),
        ("trade",                  "Paramètres de trading"),
        ("cache",                  "Gestion du cache"),
        ("scan",                   "Configuration OCR/scan"),
        ("player",                 "Infos joueur"),
        ("uex",                    "Clé secrète API UEX Corp"),
        ("sctrade",                "Paramètres sc-trade.tools"),
        ("hotkey",                 "Hotkey overlay (alt+shift+u, ctrl+f3…)"),
        ("close",                  "Mode fermeture overlay (normal/dblclick)"),
        ("voyage.calc.nbsaut",     "Nb max de missions par voyage calc"),
        ("voyage.calc.prop",       "Nb de propositions (1=critère, ≥2=dist+benef+roi)"),
        ("voyage.calc.options",    "Options par défaut pour /voyage calc"),
        ("voyage.calc.gap_max",    "Transit ⚠ au-delà de N Gm (défaut 3)"),
        ("voyage.calc.favoris",    "Lieux à privilégier (liste)"),
        ("voyage.calc.exclure",    "Lieux à exclure systématiquement (liste)"),
    ],
    "config ship": [
        ("list",   "Liste vos vaisseaux"),
        ("add",    "Ajoute un vaisseau"),
        ("remove", "Retire un vaisseau"),
        ("set",    "Définit le vaisseau actif"),
        ("select", "Alias de set"),
        ("cargo",  "Configure les grilles cargo"),
    ],
    "config trade": [
        ("profit",  "Profit minimum (aUEC)"),
        ("margin",  "Marge minimum (%)"),
        ("illegal", "Inclure les commodités illégales"),
    ],
    "config cache": [
        ("ttl",   "Durée de vie du cache (secondes)"),
        ("clear", "Vider le cache"),
    ],
    "config scan": [
        ("mode",         "Mode de scan (ocr/log/confirm)"),
        ("tesseract",    "Chemin vers tesseract"),
        ("logpath",      "Chemin vers Game.log"),
        ("screenshots",  "Dossier screenshots"),
    ],
    "config scan mode": [
        ("ocr",     "Reconnaissance optique seule"),
        ("log",     "Lecture du fichier Game.log seule"),
        ("confirm", "OCR + confirmation log"),
    ],
    "config uex": [
        ("key", "Définit la clé secrète personnelle UEX Corp"),
    ],
    "go": [
        ("from", "Définit votre position actuelle"),
        ("to",   "Définit votre destination"),
        ("clear","Efface position et destination"),
    ],
    "lieu": [
        ("from",  "Définit votre position actuelle"),
        ("to",    "Définit votre destination"),
        ("clear", "Efface position et destination"),
    ],
    "select": [
        ("system",   "Filtre par système stellaire"),
        ("planet",   "Filtre par planète"),
        ("station",  "Filtre par station"),
        ("terminal", "Filtre par terminal"),
        ("city",     "Filtre par ville"),
        ("outpost",  "Filtre par avant-poste"),
        ("add",      "Ajoute un filtre"),
        ("remove",   "Retire un filtre"),
        ("clear",    "Efface tous les filtres"),
    ],
    "select add": [
        ("system",   "Ajoute un système au filtre"),
        ("planet",   "Ajoute une planète au filtre"),
        ("station",  "Ajoute une station au filtre"),
        ("terminal", "Ajoute un terminal au filtre"),
        ("city",     "Ajoute une ville au filtre"),
        ("outpost",  "Ajoute un avant-poste au filtre"),
    ],
    "select remove": [
        ("system",   "Retire un système du filtre"),
        ("planet",   "Retire une planète du filtre"),
        ("station",  "Retire une station du filtre"),
        ("terminal", "Retire un terminal du filtre"),
        ("city",     "Retire une ville du filtre"),
        ("outpost",  "Retire un avant-poste du filtre"),
    ],
    "player": [
        ("info", "Affiche vos informations"),
        ("ship", "Gestion des vaisseaux"),
        ("dest", "Affiche/modifie la destination"),
    ],
    "player ship": [
        ("add",    "Ajoute un vaisseau"),
        ("set",    "Définit le vaisseau actif"),
        ("select", "Alias de set"),
        ("scu",    "Modifie la capacité cargo"),
        ("remove", "Retire un vaisseau"),
    ],
    "scan": [
        ("ecran",      "Scan depuis une capture d'écran"),
        ("screen",     "Alias de 'ecran'"),
        ("screenshot", "Alias de 'ecran'"),
        ("log",        "Scan depuis le log SC-Datarunner"),
        ("status",     "Affiche l'état du dernier scan"),
        ("history",    "Historique des scans"),
        ("debug",      "Debug OCR brut sur un fichier ou dossier"),
    ],
    "scan log": [
        ("all",   "Relire tout le log depuis le début"),
        ("reset", "Remettre l'offset à 0"),
        ("undo",  "Annuler la dernière lecture et relire"),
    ],
    "scan debug": [
        ("list",     "Lister les images disponibles"),
        ("selected", "Sélecteur multi-images"),
        ("batch",    "Debug OCR sur tous les fichiers d'un dossier"),
    ],
    "trade": [
        ("buy",      "Meilleurs achats possibles"),
        ("sell",     "Meilleures ventes possibles"),
        ("best",     "Meilleures routes de trading"),
        ("compare",  "Compare les prix"),
        ("from",     "Bilan depuis un terminal spécifique"),
        ("to",       "Bilan vers un terminal spécifique"),
        ("sctrade",  "Routes via sc-trade.tools"),
    ],
    "trade sctrade": [
        ("--from",        "Terminal de départ (défaut : position joueur)"),
        ("--to",          "Terminal d'arrivée (défaut : destination joueur)"),
        ("--ship",        "Vaisseau (filtre SCU)"),
        ("--budget",      "Budget en aUEC"),
        ("--stops",       "Nombre max d'étapes"),
        ("--same-system", "Rester dans le même système stellaire"),
        ("--ss",          "Alias --same-system"),
    ],
    "trade buy":     [],  # dynamique : commodités
    "trade sell":    [],  # dynamique : commodités
    "trade compare": [],  # dynamique : commodités
    "trade from":    [],  # dynamique : terminaux
    "trade to":      [],  # dynamique : terminaux
    "trade best": [
        ("--profit", "Tri par profit total"),
        ("--roi",    "Tri par ROI (%)"),
        ("--margin", "Tri par marge (%)"),
        ("--scu",    "Tri par profit par SCU"),
    ],
    "trade sctrade": [
        ("--from",   "Lieu d'origine (défaut : position joueur)"),
        ("--to",     "Lieu de destination → itinéraire origin→dest"),
        ("--ship",   "Nom du vaisseau (défaut : vaisseau actif)"),
        ("--budget", "Budget en aUEC (ex: 500k)"),
        ("--stops",  "Nombre max d'escales (défaut : 3)"),
    ],
    "nav": [
        ("@local",        "Position courante du joueur"),
        ("@dest",         "Destination courante du joueur"),
        ("--req",         "Forcer requête UEX pour distances manquantes"),
        ("info",          "Infos sur le réseau de transport"),
        ("noeuds",        "Liste tous les nœuds (alias: nodes)"),
        ("nodes",         "Liste tous les nœuds"),
        ("liaisons",      "Liste toutes les routes (alias: edges)"),
        ("edges",         "Liste toutes les routes"),
        ("sauts",         "Liste les jump points (alias: jumps)"),
        ("jumps",         "Liste les jump points"),
        ("route",         "Calcule une route"),
        ("add-route",     "Ajoute une route manuelle"),
        ("add-jump",      "Ajoute un jump point"),
        ("remove-route",  "Retire une route"),
        ("remove-jump",   "Retire un jump point"),
        ("save",          "Sauvegarde le graphe"),
        ("raz",           "Réinitialise le graphe"),
        ("populate",      "Importe les distances depuis l'API UEX"),
        ("consolidate",   "Infère les distances manquantes"),
    ],
    "info": [
        ("terminal",  "Infos sur un terminal"),
        ("commodity", "Infos sur une commodité"),
        ("ship",      "Infos sur un vaisseau"),
        ("list",      "Liste des commodités"),
    ],
    "info list": [
        ("-p+", "Trier par prix croissant"),
        ("-p-", "Trier par prix décroissant"),
        ("-b+", "Trier par bénéfice croissant"),
        ("-b-", "Trier par bénéfice décroissant"),
    ],
    "info ship":  [],  # dynamique : vaisseaux
    "explore": [
        ("ship",      "Vaisseaux par fabricant / nom"),
        ("commodity", "Catégories de commodités"),
    ],
    "explore ship":      [],  # dynamique : vaisseaux
    "explore commodity": [],  # dynamique : commodités
    "refresh": [
        ("all",     "Rafraîchit tout"),
        ("static",  "Systèmes, terminaux, commodités"),
        ("prices",  "Prix UEX Corp"),
        ("sctrade", "Données sc-trade.tools"),
        ("status",  "Statuts des terminaux"),
    ],
    "mission": [
        ("list",   "Liste les missions du catalogue"),
        ("add",    "Ajoute une mission manuellement"),
        ("edit",   "Modifie une mission existante"),
        ("remove", "Supprime une mission du catalogue"),
        ("clear",  "Efface toutes les missions"),
        ("scan",   "Scanne des captures d'écran"),
        ("view",   "Affiche le détail d'une mission"),
    ],
    "auto": [
        ("log",         "Auto-lecture du log SC-Datarunner"),
        ("signal.scan", "Signalement des nouveaux screenshots"),
        ("log.accept",  "Validation automatique des valeurs du log"),
    ],
    "auto log":         [("on", "Activer"), ("off", "Désactiver")],
    "auto signal.scan": [("on", "Activer"), ("off", "Désactiver")],
    "auto log.accept":  [("on", "Activer"), ("off", "Désactiver")],
    "voyage": [
        ("on",      "Active un voyage ou en crée un"),
        ("off",     "Désactive le voyage courant"),
        ("new",     "Crée un nouveau voyage"),
        ("calc",    "Génère un voyage optimisé"),
        ("tb",      "Tableau de bord : missions par étape"),
        ("list",    "Missions du voyage actif"),
        ("add",     "Ajoute des missions"),
        ("remove",  "Retire une mission"),
        ("clear",   "Vide les missions"),
        ("name",    "Renomme le voyage actif"),
        ("copy",    "Copie/fusionne vers un autre voyage"),
        ("accept",  "Valide et analyse"),
        ("later",   "Sauvegarde sans analyser"),
        ("cancel",  "Annule les modifications"),
        ("delete",  "Supprime un voyage"),
    ],
    "voyage calc": [
        ("dist",  "Minimise la distance"),
        ("benef", "Maximise le bénéfice"),
        ("roi",   "Maximise le ROI (aUEC/Gm)"),
        ("all",   "Génère les 3 propositions"),
    ],
    "voyage tb": [
        ("list",    "Liste les étapes"),
        ("compact", "Supprime les étapes vides"),
        ("graph",   "Vue arbre des étapes"),
    ],
    "history": [],
    "undo":    [],
    "debug":   [],
    "dev": [
        ("on",          "Active le mode développeur"),
        ("off",         "Désactive le mode développeur"),
        ("scan import", "Importer tous les screenshots d'un dossier"),
        ("scan clear",  "Vider la screenshot_db"),
        ("db",          "Statistiques de la screenshot_db"),
        ("db list",     "Liste les dernières entrées DB"),
    ],
}

# ── Type d'élément dynamique attendu après le contexte ────────────────────────
# Valeurs : "location" | "terminal" | "commodity" | "vehicle" | "system" | "any" | None
NEXT_TYPE: dict[str, str | None] = {
    "go":                "location",
    "lieu":              "location",
    "dest":              "location",
    "nav":               "location",
    "info":              "any",        # terminal + commodity + vehicle
    "info terminal":     "terminal",
    "info commodity":    "commodity",
    "info ship":         "vehicle",
    "trade from":        "terminal",
    "trade to":          "terminal",
    "trade buy":         "commodity",
    "trade sell":        "commodity",
    "trade compare":     "commodity",
    "voyage tb":         "location",
    "voyage on":         None,
    "voyage add":        None,
    "explore":           "system",     # noms de systèmes stellaires
    "explore ship":      "vehicle",    # fabricants / noms de vaisseaux
    "explore commodity": "commodity",  # catégories + noms de commodités
}

# ── Abréviations fabricants → préfixe du nom complet ──────────────────────────
# Usage : completion dot-notation (RSI.hermes, ship.crusader) et lookup /info
# Le préfixe est le premier mot du nom du fabricant tel que retourné par l'API.
MFR_ABBREV: dict[str, str] = {
    "rsi":   "robert",    # Robert Space Industries
    "misc":  "musashi",   # Musashi Industrial & Starflight Concern
    "drak":  "drake",     # Drake Interplanetary
    "aegis": "aegis",     # Aegis Dynamics
    "crus":  "crusader",  # Crusader Industries
    "orig":  "origin",    # Origin Jumpworks
    "anvl":  "anvil",     # Anvil Aerospace
    "banu":  "banu",      # Banu
    "argo":  "argo",      # Argo Astronautics
    "tumb":  "tumbril",   # Tumbril Land Systems
    "gatac": "gatac",     # Gatac Manufacture
    "krig":  "kruger",    # Kruger Intergalactic
    "espr":  "esperia",   # Esperia
    "xian":  "xi",        # Xi'An
    "vncl":  "vanduul",   # Vanduul
}

# ── Descriptions courtes des commandes racines (pour hint) ────────────────────
CMD_HINTS: dict[str, str] = {
    "help":    "Aide sur les commandes",
    "h":       "Alias /help",
    "?":       "Alias /help",
    "config":  "Configuration de l'application",
    "go":      "Définir position / destination",
    "lieu":    "Alias /go",
    "dest":    "Définir la destination",
    "select":  "Filtres de localisation",
    "refresh": "Rafraîchir les données UEX",
    "player":  "Infos joueur et vaisseaux",
    "p":       "Alias /player",
    "scan":    "OCR / scan de captures d'écran",
    "s":       "Alias /scan",
    "info":    "Infos terminal, commodité, vaisseau",
    "explore": "Explorer les données de trading",
    "trade":   "Analyse de trading",
    "nav":     "Réseau de transport et navigation",
    "mission": "Catalogue de missions",
    "m":       "Alias /mission",
    "voyage":  "Planification de voyages",
    "v":       "Alias /voyage",
    "auto":    "Automatisations (log, scan…)",
    "history": "Historique des commandes",
    "undo":    "Annuler la dernière action",
    "debug":   "Niveau de trace (0-5)",
    "dev":     "Mode développeur / import screenshots",
    "quit":    "Quitter",
    "exit":    "Quitter",
    "bye":     "Quitter",
}
