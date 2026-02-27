# UEXInfo

CLI interactif pour **Star Citizen** — interroge l'[API UEX Corp 2.0](https://uexcorp.space/api/2.0/)
et croise les données avec [sc-trade.tools](https://sc-trade.tools) pour trouver les
meilleures opportunités de trading, planifier des routes commerciales et consulter
les informations de l'univers en temps réel.

```
> /trade sell Copper
COPPER — Meilleurs prix de vente
┌─ Terminal ──────────────────┬── Sell ──┬── Stock ─┐
│ Tram & Myers Mining         │ 1700 aUEC│  250 SCU │
│ Shubin Mining SAL-2         │ 1680 aUEC│  100 SCU │
└─────────────────────────────┴──────────┴──────────┘
  sc-trade.tools: 1695 aUEC  |  1682 aUEC
```

---

## Prérequis

- **Python 3.11+**
- **Git**
- Connexion internet

---

## Installation — Windows

### 1. Cloner le dépôt

Ouvrir **PowerShell** ou **Git Bash** :

```powershell
git clone https://github.com/ZolOnTheNet/uexinfo.git
cd uexinfo
```

### 2. Créer un environnement virtuel

```powershell
python -m venv .venv
.venv\Scripts\activate
```

> Le prompt change et affiche `(.venv)` — l'environnement est actif.

### 3. Installer les dépendances

```powershell
pip install -r requirements.txt
```

### 4. (Optionnel) Installer Playwright pour sc-trade.tools

Playwright est nécessaire pour récupérer les données de sc-trade.tools
(site en JavaScript). Cette étape est optionnelle — sans Playwright,
seules les données UEX seront disponibles.

```powershell
playwright install chromium
```

### 5. Lancer l'application

```powershell
python -m uexinfo
```

Ou, si un raccourci CLI est configuré :

```powershell
uexinfo
```

---

## Installation — Linux

### 1. Cloner le dépôt

```bash
git clone https://github.com/ZolOnTheNet/uexinfo.git
cd uexinfo
```

### 2. Créer un environnement virtuel

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. (Optionnel) Playwright

```bash
playwright install chromium
# Dépendances système si nécessaire :
playwright install-deps chromium
```

### 5. Lancer l'application

```bash
python -m uexinfo
```

---

## Premier lancement

Au premier démarrage, uexinfo télécharge et met en cache les données statiques
(terminaux, commodités, lieux) depuis l'API UEX. Cette opération prend
quelques secondes.

```
uexinfo v0.1 — Star Citizen Trade CLI
Mise à jour du cache... ████████████ 100%  (terminaux: 312, commodités: 87)
Tapez /help pour l'aide, /exit pour quitter.

>
```

---

## Utilisation rapide

```
/help                        Aide générale
/config ship add "Cutlass Black"
/config ship cargo "Cutlass Black" 46
/go from "Port Tressler"     Définir la position courante
/select planet Hurston        Filtrer sur Hurston
/trade best --scu 46          Meilleures routes pour 46 SCU
/trade sell Copper            Où vendre du Copper
/trade compare Gold           Comparer UEX et sc-trade.tools
/route from "Port Tressler"   Routes depuis Port Tressler
/info "Area 18 TDD"           Infos sur un terminal
/refresh                      Mettre à jour les prix
```

Toutes les commandes commencent par `/`. La touche `Tab` active l'autocomplétion.

Voir la [documentation des commandes](docs/commands.md) pour le détail complet.

---

## Configuration

Le fichier de configuration est créé automatiquement à
`%APPDATA%\uexinfo\config.toml` (Windows) ou `~/.uexinfo/config.toml` (Linux).

```toml
[ships]
available = ["Cutlass Black"]
current = "Cutlass Black"

[ship.cargo]
"Cutlass Black" = 46

[position]
current = "Port Tressler"

[trade]
min_profit_per_scu = 500
illegal_commodities = false
```

Éditable via `/config` dans le CLI ou directement dans le fichier.

---

## Données affichées

| Couleur       | Source                   |
|---------------|--------------------------|
| Cyan / Blanc  | UEX Corp 2.0 (données primaires) |
| **Orange**    | sc-trade.tools (données croisées) |
| Vert          | Profit positif / bon deal |
| Rouge         | Marge négative / indisponible |

---

## Documentation

- [Architecture](docs/architecture.md)
- [API UEX 2.0](docs/api-uex.md)
- [sc-trade.tools](docs/api-sctrade.md)
- [Commandes CLI](docs/commands.md)

---

## Roadmap

- [x] Architecture et documentation
- [ ] Squelette CLI + config + cache statique
- [ ] Commandes `/trade`, `/info`, `/go`, `/select`
- [ ] Routes et plans de vol `/route`, `/plan`
- [ ] Intégration sc-trade.tools (données orange)
- [ ] Autocomplétion contextuelle avancée

---

## Licence

MIT — voir [LICENSE](LICENSE)

---

*Projet non officiel — Star Citizen est une marque de Cloud Imperium Games.*
