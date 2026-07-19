# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**uexinfo** — Overlay Star Citizen pour le trading, les missions et la navigation. Interroge l'API UEX Corp 2.0 et sc-trade.tools (données communauté), lit les logs de SC-Datarunner et fait de l'OCR sur les captures d'écran du jeu pour suivre automatiquement les prix, le stock, la position du joueur et les missions.

> Historique : le projet a démarré comme REPL terminal (`prompt_toolkit`), puis une migration vers une UI Textual a été construite (`docs/TEXTUAL_MIGRATION.md`) **puis entièrement retirée**. L'architecture actuelle (voir ci-dessous) est un overlay web PyWebView — c'est la seule interface qui existe aujourd'hui. `docs/architecture.md`, `docs/commands.md` et `docs/TEXTUAL_MIGRATION.md` décrivent des états antérieurs du projet et ne doivent **pas** être pris comme référence sans vérifier contre le code.

## Commands

```bash
# Installer en mode éditable (activer le venv d'abord)
pip install -e .

# Lancer l'overlay (seul point d'entrée)
python -m uexinfo
# ou après install :
uexinfo

# Lancer les tests
pytest
```

Pas de Makefile ni de CI configurée.

## Architecture

L'app est un **overlay PyWebView** : une fenêtre transparente/toujours-au-dessus pilotée par un serveur WebSocket local, avec un frontend HTML/JS unique (`static/index.html`, ~20 000 lignes). Il n'y a plus de boucle REPL terminal ni d'UI Textual — les deux ont été supprimées.

### Layer map

| Layer | Location | Rôle |
|---|---|---|
| Point d'entrée | `uexinfo/__main__.py` | Boot, vérifie les dépendances (webview/pynput/websockets), lance l'overlay |
| Overlay | `uexinfo/overlay/` | `server.py` (serveur WebSocket, exécute les commandes, pousse le statut), `static/index.html` (UI, JS) |
| État partagé | `uexinfo/cli/context.py` | `AppContext` — config, cache, player, historique de scan, etc. Instancié une fois, partagé entre toutes les commandes et le serveur overlay |
| Routage commande | `uexinfo/cli/runner.py` | `normalize_command` → `parser.py` → `dispatch()` |
| Parser | `uexinfo/cli/parser.py` | `/cmd args` → `(name, [args])` via `shlex` |
| Registre de commandes | `uexinfo/cli/commands/__init__.py` | Décorateur `@register` + `dispatch()` |
| Commandes | `uexinfo/cli/commands/*.py` | Un fichier par commande (23 commandes enregistrées) |
| Sélecteur interactif | `uexinfo/cli/selector.py` | Picker de désambiguïsation (terminaux homonymes, etc.), rendu côté overlay |
| Client API UEX | `uexinfo/api/uex_client.py` | REST → UEX Corp 2.0 (`https://uexcorp.space/api/2.0`), 11 endpoints |
| Client sc-trade | `uexinfo/api/sctrade_client.py` | REST JSON public sc-trade.tools (données communauté, affichées en orange) |
| Cache statique | `uexinfo/cache/manager.py` | Fetch → parse → sauvegarde JSON dans le dossier data utilisateur (`appdirs`), TTL 24h |
| Cache prix | `uexinfo/cache/price_cache.py`, `uexinfo/cache/data_manager.py` | Cache prix UEX (TTL adaptatif) + fusion avec les scans joueur |
| Scans joueur | `uexinfo/cache/scan_prices.py` | Stockage persistant des prix/stocks scannés, prioritaires sur UEX à l'affichage |
| Données modèles | `uexinfo/cache/models.py` | Dataclasses : `StarSystem`, `Planet`, `Moon`, `Orbit`, `SpaceStation`, `Outpost`, `City`, `Terminal`, `Vehicle`, `Commodity`, `Faction` |
| Config | `uexinfo/config/settings.py` | Lecture/écriture `config.toml` (dossier config utilisateur) |
| Réseau de transport | `uexinfo/models/transport_network.py` | Graphe Dijkstra (nœuds/arêtes), `uexinfo/data/transport_network.json` |
| Location | `uexinfo/location/index.py` | `LocationIndex` — résolution fuzzy de lieux, complétion `@lieu` |
| OCR / logs | `uexinfo/ocr/` | `engine.py` (Tesseract sur screenshots), `log_parser.py` (log SC-Datarunner) |
| Modèles métier | `uexinfo/models/` | `player.py`, `scan_result.py`, `mission.py`, `voyage.py` |
| Display | `uexinfo/display/` | Console Rich partagée (`capturing_console.py` — capture les renderables pour rendu HTML, pas de vrai TTY), couleurs, formatters |

**Dossiers orphelins** : `uexinfo/screens/` et `uexinfo/widgets/` ne contiennent plus que du bytecode `__pycache__` — reliquat de la migration Textual abandonnée, plus aucun fichier source, plus aucune référence dans le code.

### Commandes réelles (23, via `@register`)

Trading & marché : `/trade`, `/info`, `/select`
Position & déplacement : `/go` (`lieu`), `/dest`, `/arriver`, `@<lieu>`
Navigation & routes : `/nav` (`navigation`, `qt`), `/route` (délègue à `/nav route`)
Missions & voyages : `/mission`, `/voyage`
Scan & suivi terrain : `/scan`, `/sync`, `/player`, `/auto`
Divers : `/note`, `/explore`, `/history`, `/undo`, `/calc` (`=`), `/ship`, `/config`, `/refresh`, `/help`, `/debug`

`/plan` (annoncé dans une ancienne roadmap) n'existe pas. `/trade best` (tri global des meilleures routes toutes commodités) n'est pas implémenté.

### Data flow (données statiques)

`CacheManager.load()` → vérifie l'âge du fichier vs TTL → si périmé, appelle `UEXClient` pour les 11 endpoints (commodités, terminaux, systèmes, planètes, vaisseaux, lunes, orbites, stations spatiales, avant-postes, villes, factions) → parse en dataclasses → sauvegarde JSON. En cas d'échec réseau, retombe sur le cache disque existant. Les endpoints secondaires (tout sauf commodités/terminaux/systèmes/planètes) sont **non-bloquants** : un échec sur `/orbits` n'empêche pas le chargement du reste.

Pour les prix (dynamiques), `DataManager.terminal_prices()` (`cache/data_manager.py`) fusionne les prix UEX avec les scans joueur (`ScanPriceStore`), ces derniers étant prioritaires et marqués `★` à l'affichage.

### Réseau de transport / calcul de route

`TransportGraph` (Dijkstra + cache de chemins) ne couvre aujourd'hui que **Nyx, Stanton, Pyro** — c'est la couverture complète du jeu en l'état actuel (les autres systèmes ne sont pas encore jouables). `/nav populate` interroge l'API UEX live et enrichit automatiquement le graphe avec les nouveaux terminaux/routes qu'elle retourne — c'est le mécanisme à relancer quand CIG ajoute un système jouable. Aucune contrainte de carburant/autonomie de saut n'est modélisée dans le calcul de route à ce jour.

### Couleurs (Rich)

- **cyan** (`C.UEX`) — données UEX Corp
- **orange1** (`C.SCTRADE`) — **double usage à connaître** : données croisées sc-trade.tools *ou* indicateur générique « cache local / API UEX hors-ligne » selon le contexte. Ambiguïté connue, pas encore résolue — ne pas supposer qu'un texte orange vient forcément de sc-trade.tools.
- **bold green/red** (`C.PROFIT`/`C.LOSS`) — profit / perte
- **★** — donnée confirmée par un scan joueur (prioritaire sur UEX/sc-trade)

Toujours utiliser les constantes de `uexinfo/display/colors.py`, jamais de couleurs brutes.

## Ajouter une nouvelle commande

1. Créer `uexinfo/cli/commands/macommande.py`
2. Utiliser le décorateur `@register("macommande", "alias")` (`commands/__init__.py`)
3. Signature : `def handle(args: list[str], ctx: AppContext) -> None`
4. Importer le module dans `commands/__init__.py`
5. Si la commande a des sous-commandes/arguments à compléter, les ajouter à `uexinfo/cli/completer_data.py`

## Code mort connu (à supprimer ou implémenter, pas à imiter)

- `uexinfo/api/uex_scraper.py` — scraper du site uexcorp.space (missions, distances, raffinerie, grilles cargo), stub intégral (`NotImplementedError` partout), jamais importé.
- `SCTradeClient.commodity_items()` / `.ships()` — définies, jamais appelées (seuls `crowdsource_listings`/`crowdsource_for_commodity` sont utilisés).
- `uexinfo/screens/`, `uexinfo/widgets/` — vides (reliquat Textual), ne rien y ajouter.

## Known issues

- Warning d'encodage Windows quand `CacheManager` imprime `✓` sur une console non-UTF8 (inoffensif).
