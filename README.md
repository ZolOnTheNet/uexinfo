# UEXInfo

CLI interactif pour **Star Citizen** — interroge l'[API UEX Corp 2.0](https://uexcorp.space/api/2.0/)
pour trouver les meilleures opportunités de trading, planifier des routes et consulter
les informations de l'univers en temps réel.

Deux modes d'utilisation :
- **REPL** — terminal classique avec autocomplétion (prompt_toolkit)
- **TUI** — interface graphique dans le terminal (Textual), base du futur overlay in-game

---

## Prérequis

- **Python 3.11+**
- **Git**
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

### (Optionnel) Playwright — données sc-trade.tools

```bash
pip install -e ".[playwright]"
playwright install chromium
# Linux : playwright install-deps chromium
```

---

## Lancement

```bash
uexinfo              # Mode REPL (défaut)
uexinfo --tui        # Mode TUI (interface graphique terminal)
uexinfo -t           # Alias --tui
uexinfo --help       # Aide en ligne
uexinfo -?           # Alias --help

uexinfo-cli          # REPL explicite (rétro-compat)
uexinfo-tui          # TUI direct (raccourcis, scripts)
```

Au premier démarrage, les données statiques (terminaux, commodités, systèmes)
sont téléchargées et mises en cache dans `~/.uexinfo/`.

---

## Mode REPL

Interface en ligne de commande avec :
- **Tab / F2** — complétion contextuelle (commandes, terminaux, commodités, vaisseaux)
- **↑ ↓** — historique des commandes (persistant dans `~/.uexinfo/history.txt`)
- **Ctrl+↑** — ouvrir l'éditeur de scan interactif
- Saisie libre (sans `/`) → recherche `/info` automatique
- `@lieu` → se positionner et afficher les infos du terminal

```
> /ship add Cutlass_Black
> /ship set Cutlass_Black
> @Port_Tressler
> /trade
> exit
```

---

## Mode TUI

Interface graphique dans le terminal :
- **Tab / →** — accepte la suggestion inline
- **Ctrl+↓** — ouvre la liste déroulante de complétion (15 entrées max)
- **↑ ↓** — historique
- **F1** — aide
- **Ctrl+L** — vider l'affichage
- **Ctrl+Y** — copier tout l'affichage dans le presse-papiers
- **Clic gauche** — recherche `/info` sur le mot cliqué
- **Clic droit** — menu contextuel

> **Futur : overlay in-game** — le mode TUI est la base du prochain overlay
> superposé à Star Citizen (`uexinfo --tui` + `pip install -e ".[overlay]"`).
> Il permettra de consulter prix et routes sans quitter le jeu.

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
| `/arriver` | Arrivée : la destination devient la position |

### Vaisseau

| Commande | Description |
|----------|-------------|
| `/ship list` | Lister les vaisseaux avec grille cargo |
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
| `/trade best` | Meilleures routes (Phase 3) |
| `/trade compare <commodité>` | Comparer les prix (Phase 3) |

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
| `/explore <chemin>` | Navigation arborescente (ex: `ship.crusader.cutlass_black`) |

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
| `/scan log` | Lire le fichier Game.log |
| `/scan history` | Historique des scans |
| `/scan status` | Dernier scan en cours |
| **Ctrl+↑** (REPL) | Éditeur de scan interactif |

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
| `/select planet <nom>` | Filtrer sur une planète |
| `/select clear` | Effacer les filtres |
| `/history` | Historique des scans |
| `/undo` | Annuler la dernière action |
| `/help` | Aide détaillée |
| `exit` / `bye` | Quitter |

---

## Affichage

| Symbole | Signification |
|---------|--------------|
| `□` | SCU (Standard Cargo Unit) |
| `α` | aUEC (monnaie in-game) |

| Couleur | Source |
|---------|--------|
| Cyan | UEX Corp 2.0 (données primaires) |
| Orange | sc-trade.tools (données croisées) |
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
```

---

## Données et cache

- **Cache statique** (`~/.uexinfo/`) — terminaux, commodités, systèmes, véhicules (TTL 24h)
- **Cache prix** (`~/.uexinfo/price_cache.json`) — prix UEX Corp (TTL 5 min)
- **Historique** (`~/.uexinfo/history.txt`) — commandes REPL (500 entrées)
- **Graphe de transport** (`uexinfo/data/transport_network.json`) — distances entre nœuds

---

## Documentation

- [Architecture](docs/architecture.md)
- [API UEX 2.0](docs/api-uex.md)
- [Commandes CLI](docs/commands.md)

---

## Roadmap

- [x] REPL avec complétion contextuelle, historique, `@lieu`
- [x] `/info` — terminal, commodité, vaisseau (grilles cargo)
- [x] `/trade` — bilan route, achat/vente, packing par grille
- [x] `/scan` — OCR et lecture Game.log
- [x] `/nav` — réseau de transport, calcul de routes
- [x] TUI Textual avec suggestion inline et dropdown
- [x] Mode TUI (`--tui`), aide en ligne (`--help`, `-?`)
- [ ] Routes optimales `/trade best` (Phase 3)
- [ ] Overlay in-game `uexinfo --tui` superposé à Star Citizen (Phase 4)
- [ ] Intégration sc-trade.tools (données orange)

---

## Licence

MIT — voir [LICENSE](LICENSE)

---

*Projet non officiel — Star Citizen est une marque de Cloud Imperium Games.*
