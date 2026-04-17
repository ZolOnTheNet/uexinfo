# UEXInfo

> **Projet en cours de développement actif — fonctionnalités instables, API en évolution.**

Overlay in-game pour **Star Citizen** — fenêtre semi-transparente superposée au jeu,
alimentée par l'[API UEX Corp 2.0](https://uexcorp.space/api/2.0/) et optionnellement
[sc-trade.tools](https://sc-trade.tools), pour consulter prix, routes et missions
sans quitter le cockpit.

---

## Comment ça fonctionne

L'overlay est une fenêtre **PyWebView** (Chromium embarqué) sans bordure, semi-transparente,
qui tourne par-dessus Star Citizen. Elle communique avec un serveur **WebSocket** local
qui exécute les commandes et renvoie l'affichage en HTML/ANSI.

- Hotkey configurable (`Alt+Shift+U` par défaut) pour afficher/masquer la fenêtre
- Saisie de commandes avec autocomplétion inline et dropdown
- Clic gauche sur un mot → `/info` automatique
- Clic droit → menu contextuel (acheter / vendre / aller à / définir vaisseau)
- Taille et position mémorisées entre les sessions

---

## Prérequis

- **Python 3.11+**
- **pywebview**, **pynput**, **websockets**, **rich** (installés automatiquement)
- (Optionnel) **Tesseract OCR** ou **SC-Datarunner** pour `/scan`
- Connexion internet

---

## Installation

### Windows

```powershell
git clone https://github.com/ZolOnTheNet/uexinfo.git
cd uexinfo
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

### Linux

```bash
git clone https://github.com/ZolOnTheNet/uexinfo.git
cd uexinfo
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Lancement

```bash
uexinfo              # Lance l'overlay (mode unique)
```

Au premier démarrage, les données statiques (terminaux, commodités, systèmes)
sont téléchargées et mises en cache dans `~/.uexinfo/`.

---

## Commandes

Le `/` est optionnel : `trade sell Copper` = `/trade sell Copper`.

### Position et navigation

| Commande | Description |
|----------|-------------|
| `@lieu` | Se positionner sur un terminal et afficher ses infos |
| `/go from <terminal>` | Définir la position actuelle |
| `/go to <terminal>` | Définir la destination |
| `/go clear` | Effacer position et destination |
| `/dest <terminal>` | Raccourci pour définir la destination |
| `/arriver` | La destination devient la position |

### Vaisseau

| Commande | Description |
|----------|-------------|
| `/ship list` | Lister les vaisseaux avec grilles cargo |
| `/ship add <nom>` | Ajouter un vaisseau |
| `/ship set <nom>` | Définir le vaisseau actif |
| `/ship cargo <nom> <scu>` | Configurer la capacité cargo |
| `/ship remove <nom>` | Supprimer un vaisseau |

### Trading

| Commande | Description |
|----------|-------------|
| `/trade` | Bilan achat→vente (position → destination) |
| `/trade from <orig> to <dest>` | Bilan sans modifier la position |
| `/trade to <dest>` | Bilan en gardant la position courante |
| `/trade buy <commodité>` | Meilleurs terminaux d'achat |
| `/trade sell <commodité>` | Meilleurs terminaux de vente |
| `/trade best` | Meilleures routes *(Phase 3 — non implémenté)* |
| `/trade compare <commodité>` | Comparer les prix *(Phase 3 — non implémenté)* |

Le bilan `/trade` affiche pour chaque commodité :
- Prix achat `A:` et vente `V:` par □ (SCU)
- Barre de stock, quantité, distance
- Découpage cargo optimal : `[ 8×32□  2×16□ ]`
- Profit total, profit/Gm

### Information

| Commande | Description |
|----------|-------------|
| `/info <nom>` | Infos sur un terminal, une commodité ou un vaisseau |
| `/info terminal <nom>` | Forcer la recherche terminal |
| `/info commodity <nom>` | Forcer la recherche commodité |
| `/info ship <nom>` | Fiche vaisseau (cargo, pad, fabricant) |
| `/explore <chemin>` | Navigation arborescente (ex : `ship.crusader.cutlass_black`) |

### Missions

| Commande | Description |
|----------|-------------|
| `/mission list` | Lister les missions actives |
| `/mission scan` | Détecter les missions depuis un screenshot |
| `/mission edit` | Éditer une mission |
| `/mission add` | Ajouter une mission manuellement |

### Voyage

| Commande | Description |
|----------|-------------|
| `/voyage new` | Créer un nouveau voyage |
| `/voyage calc` | Calculer le bilan du voyage |
| `/voyage list` | Lister les voyages |
| `/voyage on/off` | Activer/désactiver le suivi de voyage |

### Navigation stellaire

| Commande | Description |
|----------|-------------|
| `/nav route <départ> <arrivée>` | Calculer une route |
| `/nav populate` | Importer les distances depuis l'API UEX |
| `/nav info` | Infos sur le réseau de transport |
| `/nav add-route <a> <b> <dist>` | Ajouter une route manuelle |
| `/nav add-jump <sys_a> <sys_b>` | Ajouter un jump point |
| `/route from <a> to <b>` | Alias pour `/nav route` |

### Scan de terminal

| Commande | Description |
|----------|-------------|
| `/scan` ou `/scan ecran` | Scanner depuis un screenshot |
| `/scan log` | Lire le fichier Game.log (SC-Datarunner) |
| `/scan history` | Historique des scans |
| `/scan status` | État du dernier scan |

### Automatisation

| Commande | Description |
|----------|-------------|
| `/auto log on/off` | Lecture automatique du Game.log |
| `/auto signal.scan on/off` | Alerte nouveaux scans/screenshots |
| `/auto log.accept on/off` | Validation auto des valeurs log |

### Configuration

| Commande | Description |
|----------|-------------|
| `/config ship ...` | Gérer les vaisseaux |
| `/config trade profit <n>` | Profit minimum par □ (en α) |
| `/config trade illegal on/off` | Inclure les commodités illégales |
| `/config cache clear` | Vider le cache statique |
| `/config scan mode ocr/log/confirm` | Mode de scan |
| `/config scan logpath <chemin>` | Chemin vers Game.log |

### Divers

| Commande | Description |
|----------|-------------|
| `/refresh` | Rafraîchir les données (terminaux, prix…) |
| `/sync` | Forcer la resynchronisation des prix |
| `/select planet <nom>` | Filtrer sur une planète |
| `/select clear` | Effacer les filtres |
| `= <expression>` | Calculatrice rapide (ex : `= 16*46*500`) |
| `/history` | Historique des scans |
| `/undo` | Annuler la dernière action |
| `/help` | Aide détaillée |
| `exit` / `bye` | Fermer l'overlay |

---

## Sources de données

### UEX Corp 2.0 — source principale

Toutes les données sont issues de l'[API UEX Corp 2.0](https://uexcorp.space/api/2.0/).

- Terminaux, commodités, systèmes stellaires, planètes (cache 24h)
- Prix en temps réel (cache 5 min)
- Véhicules et vaisseaux

Affiché en **cyan** dans l'interface.

### sc-trade.tools — source complémentaire (optionnel)

Les données de [sc-trade.tools](https://sc-trade.tools) peuvent être croisées
pour valider les prix. Nécessite un token API (`/config sctrade token <token>`).
En l'absence de token, l'application fonctionne normalement avec UEX seul.

Affiché en **orange** dans l'interface.

---

## Affichage

| Symbole | Signification |
|---------|--------------|
| `□` | SCU (Standard Cargo Unit) |
| `α` | aUEC (monnaie in-game) |

| Couleur | Source |
|---------|--------|
| Cyan | UEX Corp 2.0 |
| Orange | sc-trade.tools |
| Vert | Profit positif / bon stock |
| Rouge | Perte / rupture de stock |

---

## Configuration

Fichier généré automatiquement à `%APPDATA%\uexinfo\config.toml` (Windows)
ou `~/.uexinfo/config.toml` (Linux).

```toml
[player]
location = "Port Tressler"
active_ship = "Cutlass Black"

[[player.ships]]
name = "Cutlass Black"
scu  = 46

[trade]
min_profit_per_scu = 500
illegal_commodities = false

[overlay]
hotkey = "alt+shift+u"
width  = 500
height = 880
```

---

## Données et cache

- **Cache statique** (`~/.uexinfo/`) — terminaux, commodités, systèmes, véhicules (TTL 24h)
- **Cache prix** (`~/.uexinfo/price_cache.json`) — prix UEX Corp (TTL 5 min)
- **Historique** (`~/.uexinfo/history.txt`) — commandes (500 entrées)
- **Graphe de transport** (`uexinfo/data/transport_network.json`) — distances entre nœuds
- **Base screenshots** (`~/.uexinfo/screenshot_db.json`) — résultats OCR

---

## État du développement

Projet **en développement actif**. Certaines fonctionnalités peuvent être instables
ou manquantes. Les contributions et retours sont les bienvenus.

- [x] Overlay PyWebView semi-transparent superposable à Star Citizen
- [x] Autocomplétion inline + dropdown (terminaux, commodités, vaisseaux)
- [x] `/info` — terminal, commodité, vaisseau (grilles cargo)
- [x] `/trade` — bilan route, achat/vente, découpage cargo
- [x] `/scan` — OCR screenshot et lecture Game.log (SC-Datarunner)
- [x] `/nav` — réseau QT, jump points, calcul de routes
- [x] `/mission` — catalogue de missions avec scan OCR
- [x] `/voyage` — tableau de bord multi-missions
- [x] Source UEX Corp 2.0 (données primaires)
- [ ] Routes optimales `/trade best` (Phase 3)
- [ ] Intégration complète sc-trade.tools (données orange)
- [ ] Résumé vocal / alertes sonores (Phase 4)

---

## Documentation

- [Architecture](docs/architecture.md)
- [API UEX 2.0](docs/api-uex.md)
- [Commandes](docs/commands.md)

---

## Licence

MIT — voir [LICENSE](LICENSE)

---

*Projet non officiel — Star Citizen est une marque de Cloud Imperium Games.*
