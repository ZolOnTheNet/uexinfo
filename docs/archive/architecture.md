# UEXInfo — Architecture Générale

> Application CLI Python pour consulter les données commerciales de Star Citizen
> via l'API UEX Corp 2.0 et le site sc-trade.tools.

---

## Vue d'ensemble

**uexinfo** est une application CLI interactive en Python, orientée Star Citizen,
permettant de :

- Interroger l'API UEX Corp 2.0 (données live : prix, stocks, routes)
- Scraper sc-trade.tools pour croiser les données (affichage en orange)
- Gérer un cache local des données statiques (commodités, terminaux, lieux)
- Planifier des routes commerciales (flight plans)
- Configurer son profil (vaisseaux, position courante, critères)

Le tout via une interface **REPL** (Read-Eval-Print Loop) avec autocomplétion avancée.

---

## Arborescence du projet

```
uexinfo/
├── docs/                          # Documentation du projet
│   ├── architecture.md            # Ce fichier
│   ├── api-uex.md                 # Référence API UEX 2.0
│   ├── api-sctrade.md             # Référence scraping sc-trade.tools
│   └── commands.md                # Manuel des commandes CLI
│
├── uexinfo/                       # Package principal
│   ├── __init__.py
│   ├── cli/                       # Couche interface utilisateur (REPL)
│   │   ├── __init__.py
│   │   ├── main.py                # Point d'entrée, boucle REPL
│   │   ├── completer.py           # Autocomplétion (readline / prompt_toolkit)
│   │   ├── parser.py              # Parsing des commandes /xxx
│   │   └── commands/              # Handlers de commandes
│   │       ├── __init__.py
│   │       ├── help.py            # /help
│   │       ├── config.py          # /config
│   │       ├── go.py              # /go, /lieu — position courante / destination
│   │       ├── select.py          # /select — filtres (stations, villes, planètes)
│   │       ├── trade.py           # /trade, /buy, /sell — requêtes commerciales
│   │       ├── route.py           # /route, /plan — plans de vol
│   │       └── info.py            # /info — infos sur un lieu / terminal / commodité
│   │
│   ├── api/                       # Clients API externes
│   │   ├── __init__.py
│   │   ├── uex_client.py          # Client REST UEX Corp 2.0
│   │   └── sctrade_client.py      # Scraper sc-trade.tools (BeautifulSoup)
│   │
│   ├── cache/                     # Gestion du cache local
│   │   ├── __init__.py
│   │   ├── manager.py             # Chargement / invalidation / refresh du cache
│   │   └── models.py              # Dataclasses pour les entités (Commodity, Terminal…)
│   │
│   ├── display/                   # Affichage terminal (Rich)
│   │   ├── __init__.py
│   │   ├── formatter.py           # Formatage des tableaux, listes, routes
│   │   └── colors.py              # Palette de couleurs (UEX=blanc/cyan, SCTrade=orange)
│   │
│   └── config/                    # Configuration utilisateur
│       ├── __init__.py
│       └── settings.py            # Lecture/écriture ~/.uexinfo/config.toml
│
├── data/                          # Données statiques cachées localement (JSON)
│   ├── commodities/               # commodities.json, categories.json
│   ├── locations/                 # star_systems, planets, moons, cities, outposts…
│   └── terminals/                 # terminals.json
│
├── tests/                         # Tests unitaires
│   └── ...
│
├── pyproject.toml                 # Dépendances et config du projet
├── requirements.txt               # Dépendances directes
└── README.md                      # Guide de démarrage rapide
```

---

## Flux de données

```
Utilisateur (REPL)
       │
       ▼
   cli/main.py  ─── parsing ──►  cli/parser.py
       │
       ├── /config, /go, /select  ──►  cli/commands/*.py
       │                                    │
       │                           ┌────────┴────────┐
       │                           ▼                 ▼
       │                    cache/manager.py   api/uex_client.py
       │                           │                 │
       │                    data/*.json        UEX Corp 2.0 API
       │                                       (REST, GET)
       │
       ├── requêtes commodités / routes
       │        │
       │        ├──►  api/uex_client.py       ──►  uexcorp.space/api/2.0/
       │        └──►  api/sctrade_client.py   ──►  sc-trade.tools (scraping)
       │
       └── affichage  ──►  display/formatter.py  (Rich, couleurs)
```

---

## Sources de données

### UEX Corp 2.0 API
- **URL base :** `https://uexcorp.space/api/2.0/`
- **Auth :** Aucune pour les GET publics
- **Format :** JSON `{ "status": "ok", "data": [...] }`
- **Couleur d'affichage :** blanc / cyan (couleur primaire)
- Voir [api-uex.md](api-uex.md) pour le détail des endpoints

### sc-trade.tools
- **URL :** `https://sc-trade.tools/commodities/<Nom>`
- **Méthode :** Scraping (SPA JS — via requêtes XHR interceptées ou API interne)
- **Couleur d'affichage :** **orange** (données croisées / comparatives)
- Voir [api-sctrade.md](api-sctrade.md) pour la stratégie de scraping

---

## Interface CLI — Principes

### Syntaxe
- Toutes les commandes commencent par `/` (avec espaces/tabulations tolérés en début de ligne)
- Format : `/commande [sous-commande] [arguments] [--options]`
- Autocomplétion via `Tab` sur les commandes, sous-commandes et valeurs connues

### Commandes principales

| Commande      | Description                                        |
|---------------|----------------------------------------------------|
| `/help`       | Aide générale ou `/help <commande>`                |
| `/config`     | Configuration : vaisseaux, préférences             |
| `/go`         | Définir la position courante ou destination        |
| `/lieu`       | Alias de `/go`                                     |
| `/select`     | Filtres actifs (stations, villes, planètes…)       |
| `/trade`      | Recherche de commodités achetables/vendables       |
| `/route`      | Calcul de routes commerciales rentables            |
| `/plan`       | Plan de vol multi-étapes                           |
| `/info`       | Détail d'un terminal / lieu / commodité            |
| `/refresh`    | Forcer le rafraîchissement du cache                |

Voir [commands.md](commands.md) pour le détail complet.

---

## Configuration utilisateur

Stockée dans `~/.uexinfo/config.toml` :

```toml
[profile]
username = ""         # Pseudo SC optionnel

[ships]
available = []        # Liste des vaisseaux disponibles ex: ["Cutlass Black", "Vulture"]
current = ""          # Vaisseau actif

[ship.cargo]
"Cutlass Black" = 46  # SCU de cargo par vaisseau

[position]
current = ""          # Terminal/lieu courant
destination = ""      # Destination visée

[filters]
systems = []          # Systèmes stellaires retenus
planets = []          # Planètes retenues
stations = []         # Stations retenues
terminals = []        # Terminaux retenus

[trade]
min_profit_per_scu = 0      # Profit minimum par SCU en aUEC
min_margin_percent = 0       # Marge minimale en %
max_distance = 0             # Distance max (0 = illimitée)
illegal_commodities = false  # Autoriser les commodités illégales

[cache]
ttl_static = 86400    # TTL données statiques en secondes (24h)
ttl_prices = 300      # TTL données de prix en secondes (5min)
```

---

## Dépendances Python

| Package          | Rôle                                           |
|------------------|------------------------------------------------|
| `requests`       | Appels HTTP vers l'API UEX                     |
| `prompt_toolkit` | REPL interactif avec autocomplétion avancée    |
| `rich`           | Affichage coloré, tableaux, progress bars      |
| `beautifulsoup4` | Parsing HTML pour sc-trade.tools               |
| `playwright`     | Rendu JS pour sc-trade.tools (SPA)             |
| `tomllib/tomli`  | Lecture configuration TOML                     |
| `dataclasses`    | Modèles de données                             |
| `appdirs`        | Chemins de config/cache multi-OS               |

---

## Couleurs d'affichage

| Source             | Couleur         | Usage                          |
|--------------------|-----------------|--------------------------------|
| UEX Corp (primaire)| Blanc / Cyan    | Prix, stocks, routes UEX       |
| sc-trade.tools     | **Orange**      | Données croisées comparatives  |
| Alertes            | Jaune           | Avertissements, stocks faibles |
| Erreurs            | Rouge           | Erreurs API, timeouts          |
| Succès / Profit    | Vert            | Profit positif, bon deal       |
| Perte              | Rouge           | Marge négative                 |

---

## Cache local

Les données **statiques** (commodités, terminaux, lieux) sont stockées localement
dans `data/` et rechargées selon le TTL configuré.
Les données **dynamiques** (prix live) sont requêtées à chaque usage ou selon TTL.

```
data/
├── commodities/
│   ├── commodities.json      # Liste complète des commodités
│   └── categories.json       # Catégories
├── locations/
│   ├── star_systems.json
│   ├── planets.json
│   ├── moons.json
│   ├── cities.json
│   ├── outposts.json
│   └── space_stations.json
└── terminals/
    └── terminals.json        # Tous les terminaux (avec flags)
```

---

## Roadmap

- [ ] **Phase 1** — Squelette CLI + config + cache statique
- [ ] **Phase 2** — Commandes `/trade`, `/info`, `/go`, `/select`
- [ ] **Phase 3** — Routes et plans de vol `/route`, `/plan`
- [ ] **Phase 4** — Intégration sc-trade.tools (données orange)
- [ ] **Phase 5** — Optimisations UX : autocomplétion riche, historique

---

*Document créé le 2026-02-27 — Projet uexinfo v0.1*
