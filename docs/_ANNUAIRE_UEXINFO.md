# 📚 ANNUAIRE UEXINFO
*Guide de référence rapide : où est chaque fichier du projet, et à quoi il sert*

> Cet annuaire répond à « où est le fichier X ». Pour « où en est le chantier Y », voir `docs/ai/NOTES.md`.
> Pour « qu'est-ce qui a été fait et quand », voir `docs/ai/ACTIVITY_LOG.md`. Pour les règles métier validées, voir `docs/ai/DECISIONS.md`.
>
> **Maintenance :** à chaque création, suppression, déplacement ou changement de rôle d'un fichier, mettre à jour la ligne correspondante, puis la date ci-dessous.
> Dernière mise à jour : **2026-10-29** (183 fichiers suivis par git).

**Légende des statuts :**
✅ à jour, c'est une référence · ⚠️ en partie dépassé, à vérifier contre le code · 🗄️ historique (décrit un état passé) · 💀 code mort (jamais importé) · 🔒 local, hors git

---

## 🎯 **ACCÈS RAPIDE PAR BESOIN**

### Vous cherchez...

| Besoin | Fichier |
|---|---|
| **Comprendre le projet en 2 minutes** | `CLAUDE.md`, puis `docs/ai/NOTES.md` |
| **Lancer l'application** | `uexinfo/__main__.py` → `uexinfo/overlay/__init__.py:run_overlay` |
| **Liste de toutes les commandes** | `docs/_ALL_COMMANDS.md` (⚠️ avril) ; source exacte : les `@register` dans `uexinfo/cli/commands/` |
| **Ajouter une commande** | `CLAUDE.md` § « Ajouter une nouvelle commande » |
| **Protocole WebSocket overlay ↔ page** | `uexinfo/overlay/server.py` (`_dispatch`) |
| **L'interface (HTML/JS)** | `uexinfo/overlay/static/index.html` |
| **Reconnaître un nom (lieu, terminal, commodité…)** | `uexinfo/names/resolver.py` — **seul endroit autorisé** (décision D6) |
| **Prix fusionnés UEX + scans joueur** | `uexinfo/cache/data_manager.py` |
| **Règles métier (stock, risque, versions)** | `uexinfo/rules/` + `docs/ai/DECISIONS.md` |
| **Lire le Game.log** | `uexinfo/gamelog/` + `docs/ai/GAMELOG_SPEC.md` |
| **OCR des captures d'écran** | `uexinfo/ocr/engine.py` |
| **Contrats du mobiGlas (`/mission offres`)** | `uexinfo/ocr/contract_list.py` + `uexinfo/cache/contract_catalog.py` |
| **Calcul de route (graphe)** | `uexinfo/models/transport_network.py` + `uexinfo/data/transport_network.json` |
| **API UEX Corp (endpoints)** | `uexinfo/api/uex_client.py` + `docs/api-uex.md` |
| **Couleurs d'affichage** | `uexinfo/display/colors.py` |
| **Dette technique, code mort connu** | `docs/ai/NOTES.md` §4, `docs/ai/AUDIT_2026-10-06.md` |
| **Pistes à faire** | `docs/ai/NOTES.md` §6, `docs/TODO_zol.md` |
| **Prochaine grosse évolution d'interface** | `docs/PROPOSITION_MENUS_SOURIS.html` |
| **Documents dépassés** | `docs/archive/` |

---

## 📁 **STRUCTURE DES DOSSIERS**

```
uexinfo/                         (racine du dépôt)
├── CLAUDE.md                    ← consignes pour Claude Code (à jour)
├── README.md                    ← présentation utilisateur
├── pyproject.toml / requirements.txt
├── uexinfo/                     ← le code (package Python)
│   ├── __main__.py              ← point d'entrée
│   ├── overlay/                 ← fenêtre PyWebView + serveur WebSocket + page HTML
│   ├── cli/                     ← routage des commandes, contexte partagé, complétion
│   │   └── commands/            ← une commande par fichier
│   ├── api/                     ← clients UEX Corp et sc-trade.tools
│   ├── cache/                   ← caches disque, scans joueur, missions, voyages
│   ├── names/                   ← résolveur de noms unique (D6)
│   ├── rules/                   ← règles métier pures et testées
│   ├── gamelog/                 ← lecture du Game.log de Star Citizen
│   ├── ocr/                     ← Tesseract, log SC-Datarunner, captures
│   ├── models/                  ← dataclasses métier (joueur, voyage, réseau…)
│   ├── location/                ← index des lieux pour la complétion @lieu
│   ├── display/                 ← Rich → HTML, couleurs, formatage
│   ├── config/                  ← config.toml utilisateur
│   └── data/                    ← données embarquées (graphe, grilles cargo)
├── tests/                       ← pytest (+ fixtures réelles)
├── docs/                        ← documentation
│   ├── _ANNUAIRE_UEXINFO.md     ← VOUS ÊTES ICI
│   ├── ai/                      ← notes de travail de Claude (à jour)
│   └── archive/                 ← documents dépassés
├── scripts/                     ← utilitaires (génération du graphe, lanceurs Windows et Linux)
├── extprg/                      ← 🔒 programmes externes, presque tout hors git
└── .claude/                     ← réglages Claude Code du projet
```

---

## 🐍 **CODE — `uexinfo/`**

### Démarrage et overlay

| Fichier | Rôle |
|---|---|
| `__init__.py` | Version du package, `build_id()` (commit git en cours). |
| `__main__.py` | Point d'entrée unique : vérifie les dépendances (webview, pynput, websockets), lance l'overlay. |
| `overlay/__init__.py` | Fenêtre PyWebView transparente, raccourci clavier global (Win32, pynput hors Windows), presse-papiers, remplacement d'une instance déjà lancée, `run_overlay()`. |
| `overlay/server.py` | Serveur WebSocket : reçoit les commandes de la page, les exécute, renvoie le HTML ; complétion, statut, confirmation des scans, suivi Game.log. Importe toutes les commandes. |
| `overlay/static/index.html` | Toute l'interface (HTML + CSS + JS, ~4 400 lignes) : console, complétion, menus, mots cliquables, formulaires de scan. |

### Routage des commandes — `cli/`

| Fichier | Rôle |
|---|---|
| `cli/__init__.py` | Docstring du package seulement. |
| `cli/context.py` | `AppContext` : état global partagé (config, cache, joueur, historique de scans…), une seule instance. |
| `cli/runner.py` | Chaîne d'exécution : normalisation → `parser.py` → `dispatch()`. |
| `cli/parser.py` | Découpe `/cmd args` en `(nom, [args])` avec `shlex`. |
| `cli/selector.py` | Sélecteur générique (choix entre homonymes…), affiché par l'overlay via `ctx.select_fn`. |
| `cli/completer_data.py` | Données de complétion : sous-commandes et aides par commande. |
| `cli/history.py` | Historique persistant des commandes (`history.jsonl`). |

### Commandes — `cli/commands/`

| Fichier | Commandes (alias) | Rôle |
|---|---|---|
| `__init__.py` | — | Registre : décorateur `@register` et `dispatch()`. |
| `trade.py` | `/trade` (`t`) | Prix d'achat et de vente, cargo simulé, vente multi-commodités. |
| `info.py` | `/info` (`i`, `?`) | Fiche terminal, commodité ou vaisseau ; `/info list`. Le plus gros fichier (~2 600 lignes), point chaud du refactoring. |
| `select.py` | `/select` (`sel`) | Filtres actifs inclusifs/exclusifs par catégorie. |
| `go.py` | `/go` (`g`, `lieu`), `/dest` (`d`), `/arriver` | Position actuelle, destination, arrivée. |
| `nav.py` | `/nav` (`n`, `navigation`, `qt`, `quantum`) | Réseau de transport : routes QT, sauts, `/nav route`, `/nav populate`. |
| `mission.py` | `/mission` (`m`) | Catalogue de missions, groupe actif, `/mission offres` (contrats du mobiGlas). |
| `voyage.py` | `/voyage` (`v`) | Voyages multi-étapes (achat, vente, missions), tableau de bord. |
| `scan.py` | `/scan` (`s`) | Scan des terminaux (log SC-Datarunner, OCR), validation, édition. |
| `sync.py` | `/sync` (`resync`) | Resynchronisation forcée des prix d'un terminal. |
| `undo.py` | `/undo` | Annule le dernier scan. |
| `player.py` | `/player` (`p`) | Joueur, vaisseau, position. |
| `auto.py` | `/auto` | Active ou coupe les automatismes (position auto, suivi…). |
| `game.py` | `/game` (`gamelog`, `jeu`) | Lecteur du Game.log : état, événements, tail, recherche, statistiques, rejeu. |
| `evolution.py` | `/evolution` (`scevolution`) | Changement de version ou d'univers SC (décision D3). |
| `explore.py` | `/explore` (`x`, `exp`) | Navigation hiérarchique : géographie, vaisseaux, commodités. |
| `note.py` | `/note` (`notes`) | Notes personnelles par lieu ; `-e` ouvre le formulaire de l'overlay. |
| `history_cmd.py` | `/history` (`hist`) | Affiche l'historique des commandes. |
| `calc.py` | `/=` (`calc`, `calcul`) | Calculatrice. |
| `config.py` | `/config` (`c`), `/ship` (`sh`) | Configuration (vaisseaux, sc-trade, overlay, cache, `/config cache clear <type>`). |
| `refresh.py` | `/refresh` (`r`, `rf`) | Recharge les caches. |
| `debug.py` | `/debug` | Niveau de trace. |
| `help.py` | `/help` (`h`, `?`) | Aide multi-niveaux. L'alias `?` est écrasé par `info.py`. |

### API — `api/`

| Fichier | Rôle |
|---|---|
| `api/__init__.py` | Docstring du package seulement. |
| `api/uex_client.py` | Client REST UEX Corp 2.0 (11 endpoints : commodités, terminaux, prix, systèmes…). |
| `api/sctrade_client.py` | Client sc-trade.tools (JSON public, sans jeton), données communauté affichées en orange. |

### Caches et données persistantes — `cache/`

| Fichier | Rôle |
|---|---|
| `cache/__init__.py` | Docstring du package seulement. |
| `cache/manager.py` | Données statiques UEX : téléchargement, TTL 24 h, repli sur le disque si le réseau échoue. |
| `cache/models.py` | Dataclasses UEX : `StarSystem`, `Planet`, `Moon`, `Terminal`, `Commodity`, `Vehicle`… |
| `cache/price_cache.py` | Cache des prix UEX sur disque (TTL adaptatif). |
| `cache/data_manager.py` | Accès unifié aux prix : fusion UEX + scans joueur (★ prioritaires). |
| `cache/scan_prices.py` | Prix et stocks relevés par le joueur, persistants. |
| `cache/screenshot_db.py` | Base des captures d'écran déjà analysées. |
| `cache/mission_manager.py` | Groupe de missions actif, synergies. |
| `cache/mission_scan.py` | Outils partagés pour le scan de missions par lot. |
| `cache/contract_catalog.py` | Catalogue des contrats (copie locale scmdb.net, sinon `global.ini` du jeu) pour reconnaître les cartes lues. |
| `cache/voyage_manager.py` | Voyages : stockage JSON, session, rétention. |
| `cache/notes_manager.py` | Notes du joueur par lieu. |
| `cache/evolution.py` | Mémoire des versions SC et des changements d'univers (D3). |

### Noms — `names/` (décision D6)

| Fichier | Rôle |
|---|---|
| `names/__init__.py` | Point d'entrée `resolve()`. Toute recherche par nom passe par ici. |
| `names/normalize.py` | Normalisation unique des noms (saisie, OCR, UEX). |
| `names/resolver.py` | Résolveur : lieux, terminaux, commodités, vaisseaux, nœuds du graphe ; homonymes. |

### Règles métier — `rules/` (pures, sans I/O, chacune testée)

| Fichier | Rôle |
|---|---|
| `rules/__init__.py` | Présentation du package. |
| `rules/stock.py` | Quantités achetables/vendables selon le statut de stock UEX (D1, D5). |
| `rules/risk.py` | Risque de ne pas écouler au terminal de vente, demi-vie 1 h (D2). |
| `rules/version.py` | Versions SC et changements d'univers (D3). |
| `rules/scan_match.py` | Quel terminal homonyme a été scanné (Pyro Gateway côté Stanton ou Nyx). |

### Game.log — `gamelog/`

| Fichier | Rôle |
|---|---|
| `gamelog/__init__.py` | Présentation : lecture seule du Game.log. |
| `gamelog/__main__.py` | `python -m uexinfo.gamelog` : rejouer un Game.log sans le jeu ni l'overlay. |
| `gamelog/lines.py` | Découpage d'une ligne brute (pur). |
| `gamelog/events.py` | Reconnaissance des événements (pur). |
| `gamelog/state.py` | État du joueur déduit des événements : position, système, morts, menu (pur). |
| `gamelog/places.py` | Codes de lieu internes → nom affiché et système. Table **unique** (pur). |
| `gamelog/follow.py` | Lecture du fichier : dernières lignes, suivi incrémental, chemin. |
| `gamelog/parser.py` | Ancien extracteur d'événements, encore utilisé par la position automatique. |
| `gamelog/reader.py` | Ancien suivi incrémental, utilisé par le serveur overlay. |
| `gamelog/arrival.py` | Corrélation d'événements pour proposer une arrivée fiable (position automatique). |

### OCR et SC-Datarunner — `ocr/`

| Fichier | Rôle |
|---|---|
| `ocr/__init__.py` | Docstring du package seulement. |
| `ocr/engine.py` | Moteur Tesseract : lecture des terminaux et des écrans de mission. Cherche Tesseract d'abord dans `extprg/tesseract/`. |
| `ocr/contract_list.py` | Panneau des contrats du mobiGlas → cartes (titre, XP, donneur d'ordre, récompense). |
| `ocr/log_parser.py` | Lecture du log de SC-Datarunner (mode A). |
| `ocr/watcher.py` | Surveillance du dossier de captures (mode B). |
| `ocr/ocr_worker.py` | OCR en arrière-plan des captures. |

### Modèles — `models/`

| Fichier | Rôle |
|---|---|
| `models/__init__.py` | Docstring du package seulement. |
| `models/player.py` | `Player` et `Ship`. |
| `models/scan_result.py` | `ScanResult`, `ScannedCommodity`. |
| `models/mission.py` | Mission. |
| `models/mission_result.py` | Résultat du scan de l'écran Contrats. |
| `models/voyage.py` | `Voyage` et `VoyageStep`. |
| `models/transport_network.py` | Graphe de transport (Dijkstra, cache de chemins) : Stanton, Pyro, Nyx. |

### Lieux, affichage, config, données

| Fichier | Rôle |
|---|---|
| `location/__init__.py` | Docstring du package seulement. |
| `location/index.py` | `LocationIndex` : complétion `@lieu` par chemins pointés. |
| `display/__init__.py` | Docstring du package seulement. |
| `display/colors.py` | Palette Rich (UEX cyan, sc-trade orange, profit/perte). **Seule source des couleurs.** |
| `display/formatter.py` | Console partagée, formatage des prix, SCU, distances, nom court de terminal. |
| `display/capturing_console.py` | Console Rich qui capture les rendus au lieu d'écrire dans un terminal. |
| `display/render_html.py` | Rendu natif des objets Rich en HTML structuré. |
| `display/ansi_html.py` | Conversion des codes ANSI en HTML (ancienne voie, encore utilisée par le serveur). |
| `display/adaptive.py` | Tableaux à colonnes proportionnelles (missions, voyages). |
| `display/loc.py` | Affichage centralisé des noms de lieux. |
| `config/__init__.py` | Docstring du package seulement. |
| `config/settings.py` | Lecture/écriture de `config.toml`. |
| `data/transport_network.json` | Graphe de transport (nœuds, arêtes), enrichi par `/nav populate` et `scripts/generate_locations.py`. |
| `data/cargo_grids.py` | Grilles cargo des vaisseaux (tailles de conteneurs). |

---

## 🧪 **TESTS — `tests/`**

Lancer : `pytest` (276 tests réussis au 2026-10-22).

| Fichier | Ce qui est testé |
|---|---|
| `__init__.py`, `*/__init__.py` | Packages vides. |
| `conftest.py` | Fixtures partagées : sous-ensemble réel des données UEX (octobre 2026). |
| `test_config_cache_clear.py` | `/config cache clear <type>` n'efface qu'un type à la fois. |
| `test_dashboard.py` | Fonctions du tableau de bord `/voyage tb`. |
| `test_voyage_manager.py` | `VoyageManager` : gestion des étapes. |
| `test_voyage_model.py` | Modèles `Voyage` et `VoyageStep`. |
| `cache/test_cleanup.py` | Nettoyage de la base sans trou entre versions (D10). |
| `cache/test_contract_catalog.py` | Reconnaissance des contrats (catalogue **fictif**, aucune donnée scmdb). |
| `cache/test_evolution.py` | Mémoire des versions et surveillance (D3). |
| `gamelog/test_events.py` | Reconnaissance des événements. |
| `gamelog/test_places.py` | Codes de lieu → nom et système. |
| `gamelog/test_live_crash.py` | Vrai Game.log LIVE 4.10 : crash au hangar, mort. |
| `gamelog/test_live_extract.py` | Vrai Game.log LIVE 4.10 : Seraphim → Nyx. |
| `names/test_resolver.py` | Résolveur unique sur données UEX réelles (D6). |
| `names/test_callers.py` | Les anciennes fonctions de recherche délèguent toutes au résolveur. |
| `names/test_graph.py` | Nœuds du vrai graphe de navigation. |
| `ocr/test_contract_list.py` | Liste des contrats sur des mots OCR réels (20/10). |
| `ocr/test_datarunner_log.py` | Vrai log SC-Datarunner (Pyro Gateway côté Nyx). |
| `ocr/test_engine_paths.py` | Ordre de recherche de Tesseract. |
| `rules/test_stock.py` | D1 : quantités selon le statut de stock. |
| `rules/test_risk.py` | D2 : risque de stock, demi-vie 1 h. |
| `rules/test_version.py` | D3 : versions et changements d'univers. |
| `rules/test_scan_match.py` | Quel Pyro Gateway a été scanné. |

### Fixtures — `tests/fixtures/` (données réelles)

| Fichier | Contenu |
|---|---|
| `uex/cities.json`, `uex/commodities.json`, `uex/planets.json`, `uex/space_stations.json`, `uex/star_systems.json`, `uex/terminals.json`, `uex/vehicles.json` | Extraits réels de l'API UEX (octobre 2026), chargés par `conftest.py`. |
| `gamelog/format_reference.log` | Lignes de référence du format Game.log. |
| `gamelog/live_4.10_crash_cru_l1.log` | Game.log réel du 2026-10-19. |
| `gamelog/live_4.10_seraphim_nyx.log` | Game.log réel du 2026-10-07. |
| `datarunner/app_2026-10-07_pyro_gateway_nyx.log` | Log SC-Datarunner réel. |
| `ocr/contract_list_words_2026-10-20.json` | Mots OCR d'une vraie capture de la liste des contrats. |

---

## 📖 **DOCUMENTATION — `docs/`**

### Référence actuelle

| Fichier | Date | Statut | Contenu |
|---|---|---|---|
| `_ANNUAIRE_UEXINFO.md` | 2026-10-29 | ✅ | Ce fichier. |
| `ai/NOTES.md` | 2026-10-29 | ✅ | **À lire en premier** : objectifs, carte du code, dette vérifiée, pistes. |
| `ai/ACTIVITY_LOG.md` | 2026-10-29 | ✅ | Journal de chaque étape notable. |
| `ai/DECISIONS.md` | 2026-10-07 | ✅ | Décisions métier validées (D1 à D10). |
| `ai/AUDIT_2026-10-06.md` | 2026-10-06 | ✅ | Audit complet en lecture seule. |
| `ai/ETUDES_RISQUE_VERSION.md` | 2026-10-06 | ✅ | Études préalables aux décisions D2 (risque) et D3 (versions). |
| `ai/GAMELOG_SPEC.md` | 2026-10-19 | ✅ | Lignes du Game.log exploitées, formats confirmés. |
| `ai/MISSION_STELLIVERSE.md` | 2026-10-06 | ✅ | Consignes de la mission « s'inspirer de Stelliverse ». |
| `PROPOSITION_MENUS_SOURIS.html` | 2026-10-21 | ✅ | Proposition d'interface souris v2 (menus, fenêtres multiples, minage), en attente de réponses. |
| `scmdb_demande_autorisation.md` | 2026-10-22 | ✅ | Demande d'autorisation envoyée à scmdb.net, et suivi. |
| `TODO_zol.md` | 2026-08-03 | ✅ | Liste de choses à faire tenue par Zol. |
| `api-uex.md` | 2026-03-02 | ✅ | Référence de l'API UEX Corp 2.0 (endpoints, champs). |

### Utile mais en partie dépassé

| Fichier | Date | Statut | Contenu |
|---|---|---|---|
| `_ALL_COMMANDS.md` | 2026-04-26 | ⚠️ | Liste exhaustive des commandes ; manque `/game`, `/evolution`, `/mission offres`… |
| `bilan1_analyseFonctionnement.md` | 2026-05-20 | ⚠️ | Bilan : résolution de noms, cycle de vie des données, parallélisation. Une partie est corrigée depuis (résolveur D6). |
| `REFACTORING_PLAN.md` | 2026-04-06 | ⚠️ | Plan de refactoring ; son état est suivi dans `ai/NOTES.md` §4. |
| `route_commande_prg.md` | 2026-04-22 | ⚠️ | Plan d'une future commande `/route` (routes commerciales sc-trade.tools, sauts, SCU multi-taille). Pas implémentée. |
| `scan-ocr.md` | 2026-03-14 | ⚠️ | Décisions OCR : modes A (log Datarunner) et B (dossier de captures), toujours en place. |
| `etudes_missions.md` | 2026-03-22 | ⚠️ | Étude du système missions et voyages, implémenté depuis. |
| `grids_ships_study.md` | 2026-03-10 | ⚠️ | Étude des grilles cargo, implémentée dans `data/cargo_grids.py`. |
| `locations-stanton.md` | 2026-03-27 | ⚠️ | Catalogue des lieux de Stanton. |
| `COMPLETION_OVERLAY.md` | 2026-03-31 | ⚠️ | Spécification de la complétion Tab dans l'overlay. |
| `api-sctrade.md` | 2026-02-27 | ⚠️ | Stratégie de scraping (Playwright) ; aujourd'hui le client utilise un JSON public. |

### Archives — `docs/archive/`

| Fichier | Contenu |
|---|---|
| `README.md` | Pourquoi chaque fichier a été archivé. |
| `leChat_propositionAmelioration.md` | 20 pistes d'amélioration de Le Chat (Mistral), 2026-04-02. |
| `lechat_interface_simplifier.md` | Mode simplifié sous Textual par Le Chat, 2026-04-02. |
| `Suppr_ANSI_cli.md` | Plan de suppression de l'ANSI exécuté par Vibe (Mistral), remplacé par `CapturingConsole`. |
| `architecture.md` | Architecture du REPL d'origine (2026-02-27). |
| `commands.md` | Manuel des commandes du REPL (2026-03-14). |
| `TEXTUAL_MIGRATION.md` | Migration vers Textual, abandonnée et retirée (2026-03-09). |
| `DUAL_MODE_OVERLAY.md` | Mode dual CLI/TUI/overlay ; seul l'overlay reste (2026-03-09). |
| `OVERLAY_GRAPHIQUE_PLAN.md` | Plan « TUI v2 » de la console graphique (2026-03-17). |
| `scan-editor.md` | Éditeur de scan de l'époque REPL (2026-03-02). |
| `INFO_DIAG.md` | Transcription de la conversation de lancement du projet (2026-02-27). |
| `CONSIGNES_Sonnet_FinMars.md` | Consignes données à Claude Sonnet fin mars 2026. |
| `CONSIGNES_Sonnet_17Avril26.md` | Consignes de revue de code et plan de tests (17 avril 2026). |
| `command_result_schema.md` | Schéma `CommandResult` (2026-04-29), jamais adopté. |

---

## 🛠️ **SCRIPTS ET PROGRAMMES EXTERNES**

| Fichier | Rôle |
|---|---|
| `scripts/generate_locations.py` | Régénère `uexinfo/data/transport_network.json` depuis l'API UEX. |
| `scripts/uexinfogene.ps1` | ✅ Lanceur Windows portable : crée `.venv`, installe les dépendances au besoin, lance l'overlay. |
| `scripts/uexinfolnx.sh` | ✅ Lanceur Linux : même rôle ; vérifie WebKitGTK et Tesseract, force XWayland sous Wayland. |
| `scripts/uexinfo.ps1` | Lanceur Windows du poste personnel (`python -m uexinfo`), chemin de Python écrit en dur. |
| `extprg/SC-images/Mission_remisajour.ps1` | Recopie des captures de missions avec la date du jour, pour les tests. Seul fichier suivi de `extprg/SC-images/`. |

---

## ⚙️ **FICHIERS RACINE ET CONFIGURATION**

| Fichier | Rôle |
|---|---|
| `CLAUDE.md` | Consignes pour Claude Code : architecture actuelle, commandes, règles. ✅ |
| `README.md` | Présentation utilisateur (refonte « overlay uniquement » du 2026-04-17). ⚠️ |
| `pyproject.toml` | Paquet, dépendances, point d'entrée `uexinfo`, `testpaths = tests`. |
| `requirements.txt` | Dépendances pour `pip install -r`. |
| `.gitignore` | Exclut caches, venv, logs, `extprg/` (sauf exceptions), données utilisateur, fichiers temporaires NFS `.nfs*`. |
| `.claude/settings.json` | Permissions Claude Code du projet. |

---

## 🔒 **HORS DÉPÔT (LOCAL)**

| Emplacement | Contenu |
|---|---|
| `extprg/SC-Datarunner-UEX/` | Programme SC-Datarunner (exécutable, DLL, ~230 Mo) et son log lu par `/scan`. |
| `extprg/tesseract/` | Copie stable de Tesseract (~105 Mo), cherchée en premier par `ocr/engine.py`. Présente sur le poste Windows. |
| `extprg/SC-images/` | Captures d'écran de test. |
| `extprg/gamelogs/` | Sauvegardes datées de Game.log. |
| `.venv/` | Environnement virtuel Python. |
| `.claude/settings.local.json` | Réglages Claude Code personnels. |
| Dossier de données utilisateur (`~/.uexinfo/`, via `appdirs`) | `config.toml`, caches JSON UEX, `scan_prices.json`, `missions.json`, `voyages.json`, `history.jsonl`, notes, base des captures. |

---

## ⚠️ **ANOMALIES RELEVÉES PENDANT L'INVENTAIRE**

- Aucune en cours. Le code mort et les scripts de débogage relevés ont été supprimés le 2026-10-29.

---

## 📊 **STATISTIQUES (2026-10-29)**

| Élément | Nombre |
|---|---|
| Fichiers suivis par git | 183 |
| Fichiers Python du package `uexinfo/` | 94 |
| Commandes (`@register`) | 25, toutes chargées |
| Fichiers de tests | 21 (276 tests réussis au 2026-10-22) |
| Documents `docs/` | 36 (dont 14 dans `archive/`, 7 dans `ai/`) |

---

## 📝 **HISTORIQUE DE CET ANNUAIRE**

- **2026-10-29** : création. Inventaire complet des fichiers suivis par git, statut de chaque document, anomalies.
- **2026-10-29** (suite) : 9 documents historiques déplacés dans `docs/archive/`, `.claude/.nfs*` retirés de git, `cli/opts.py` supprimé.
- **2026-10-29** (suite) : docstrings ajoutées dans tout le code Python ; descriptions des `__init__.py` mises à jour.
- **2026-10-29** (suite) : code mort supprimé (`route.py`, `display/result.py`, `select_editor.py`), `scripts/dev/` et dossiers vides `data/` retirés, `command_result_schema.md` archivé.
- **2026-10-29** (suite) : lanceurs `scripts/uexinfogene.ps1` (Windows) et `scripts/uexinfolnx.sh` (Linux) ajoutés.
