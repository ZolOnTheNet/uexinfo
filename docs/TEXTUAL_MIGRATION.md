# TEXTUAL_MIGRATION.md — Plan de migration uexinfo CLI → Textual TUI

## Contexte projet

**uexinfo** est un CLI interactif Python pour Star Citizen qui agrège des données de trading depuis :
- **UEX Corp API 2.0** (données primaires)
- **sc-trade.tools** (données croisées via Playwright/Chromium headless)
- **Logs SC-Datarunner** (OCR terminal parsing)

Le projet utilise **Rich** pour l'affichage terminal, **TOML** pour la config, et un cache local pour les données statiques.

**Objectif** : Migrer la couche présentation du CLI interactif (prompt + Rich tables) vers une app **Textual** (TUI cliquable avec souris), tout en préservant intégralement la logique métier existante dans `core/`.

---

## Architecture cible

```
uexinfo/
├── app.py                  # Point d'entrée Textual App
├── screens/
│   ├── __init__.py
│   ├── trade.py            # Écran principal trade (sell/buy/compare)
│   ├── route.py            # Écran routes commerciales
│   └── info.py             # Écran info terminal/commodité
├── widgets/
│   ├── __init__.py
│   ├── position_bar.py     # Widget : sélection position + vaisseau courant
│   ├── price_table.py      # Widget : DataTable custom avec couleurs marge
│   ├── commodity_search.py # Widget : barre de recherche commodité
│   └── status_bar.py       # Widget : statut cache, fraîcheur données, erreurs
├── core/                   # Logique métier EXISTANTE — NE PAS MODIFIER
│   ├── uex_api.py          # Client API UEX Corp 2.0
│   ├── sctrade.py          # Scraper sc-trade.tools via Playwright
│   ├── datarunner.py       # Parser logs Datarunner
│   ├── cache.py            # Cache local données statiques
│   ├── config.py           # Gestion config TOML
│   ├── trade.py            # Calculs trading (marges, routes, best deals)
│   └── models.py           # Modèles de données (si existant)
├── styles/
│   └── app.tcss            # Stylesheet Textual
├── __main__.py             # Lanceur (remplace l'ancien point d'entrée CLI)
└── overlay.py              # (Phase future) Lanceur PyWebView overlay
```

> **RÈGLE ABSOLUE** : Le contenu du dossier `core/` ne doit PAS être modifié. 
> Toute la migration concerne uniquement la couche présentation.
> Si une fonction de `core/` retourne un objet Rich (Table, Text, etc.), 
> créer un adaptateur dans `widgets/` qui convertit vers un widget Textual.

---

## Phase 1 — App Textual de base

### 1.1 — Point d'entrée `__main__.py`

Remplacer le prompt CLI interactif par le lancement de l'app Textual :

```python
from uexinfo.app import UexInfoApp

def main():
    app = UexInfoApp()
    app.run()

if __name__ == "__main__":
    main()
```

### 1.2 — App principale `app.py`

Créer une app Textual avec :
- **Header** : titre "uexinfo" + version
- **Footer** : raccourcis clavier (q=quitter, r=refresh, tab=changer onglet)
- **TabbedContent** : 3 onglets — Trade, Routes, Info
- **Sidebar gauche** (ou barre horizontale top) : position courante + vaisseau courant (widgets Select)

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane
from textual.binding import Binding

from uexinfo.screens.trade import TradeScreen
from uexinfo.screens.route import RouteScreen
from uexinfo.screens.info import InfoScreen
from uexinfo.widgets.position_bar import PositionBar

class UexInfoApp(App):
    """UEXInfo — Star Citizen Trade Assistant"""
    
    CSS_PATH = "styles/app.tcss"
    TITLE = "uexinfo"
    SUB_TITLE = "Star Citizen Trade Assistant"
    
    BINDINGS = [
        Binding("q", "quit", "Quitter"),
        Binding("r", "refresh", "Refresh données"),
        Binding("d", "toggle_dark", "Thème sombre/clair"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield PositionBar()
        with TabbedContent():
            with TabPane("Trade", id="trade"):
                yield TradeScreen()
            with TabPane("Routes", id="routes"):
                yield RouteScreen()
            with TabPane("Info", id="info"):
                yield InfoScreen()
        yield Footer()

    def action_refresh(self) -> None:
        """Rafraîchir les données depuis les APIs"""
        # Appeler core/cache.py pour refresh
        # Puis mettre à jour les widgets affichés
        pass

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark
```

### 1.3 — Widget PositionBar `widgets/position_bar.py`

Barre horizontale en haut avec :
- **Select** dropdown : position courante (liste des terminaux depuis le cache)
- **Select** dropdown : vaisseau courant (depuis config TOML)
- **Label** : capacité cargo du vaisseau sélectionné
- **Label** : indicateur fraîcheur données (âge du dernier refresh)

Le widget doit :
- Lire la config TOML existante via `core/config.py` pour les vaisseaux et la position par défaut
- Lire le cache des terminaux via `core/cache.py` pour peupler le dropdown positions
- Émettre un message Textual quand la position ou le vaisseau change (pour que les écrans se mettent à jour)

```python
from textual.widgets import Static, Select, Label
from textual.containers import Horizontal
from textual.message import Message

class PositionBar(Static):
    
    class PositionChanged(Message):
        def __init__(self, terminal: str) -> None:
            self.terminal = terminal
            super().__init__()
    
    class ShipChanged(Message):
        def __init__(self, ship: str, cargo: int) -> None:
            self.ship = ship
            self.cargo = cargo
            super().__init__()

    def compose(self):
        with Horizontal(id="position-bar"):
            yield Select(
                options=self._get_terminals(),
                prompt="Position courante",
                id="position-select"
            )
            yield Select(
                options=self._get_ships(),
                prompt="Vaisseau",
                id="ship-select"
            )
            yield Label("-- SCU", id="cargo-label")
            yield Label("Cache: --", id="cache-age")

    def _get_terminals(self):
        """Charger la liste des terminaux depuis core/cache.py"""
        # TODO: appeler le cache existant
        # Retourner liste de tuples (label, value)
        return []

    def _get_ships(self):
        """Charger la liste des vaisseaux depuis core/config.py"""
        # TODO: lire config TOML existante
        return []
```

---

## Phase 2 — Écran Trade `screens/trade.py`

C'est l'écran principal. Il doit reproduire les fonctionnalités des commandes `/trade sell`, `/trade buy`, `/trade best`, `/trade compare`.

### Composants :

1. **Input** de recherche commodité (avec autocomplétion)
2. **DataTable** principal : colonnes triables par clic
   - Terminal, Buy/Sell price, Stock/Demand (SCU), Marge estimée, Source données (UEX/sc-trade), Fraîcheur
3. **Panneau détail** (affiché au clic sur une ligne) : détail de la route, profit total estimé pour la capa cargo actuelle
4. **Boutons radio** ou **Select** : mode Sell / Buy / Best / Compare

### Codes couleur (conserver la convention existante) :
- **Cyan / Blanc** : données UEX Corp
- **Orange** : données sc-trade.tools  
- **Vert** : profit positif / bon deal
- **Rouge** : marge négative / indisponible
- **Jaune** : données > 24h (fraîcheur douteuse)

### Interactions souris :
- **Clic colonne header** → trier la table
- **Clic ligne** → afficher détail route dans panneau latéral
- **Double-clic ligne** → définir comme destination dans l'écran Routes
- **Hover ligne** (si supporté) → highlight visuel

```python
from textual.screen import Screen
from textual.widgets import DataTable, Input, RadioSet, RadioButton, Static
from textual.containers import Horizontal, Vertical

class TradeScreen(Static):
    
    def compose(self):
        with Vertical():
            with Horizontal(id="trade-controls"):
                yield Input(placeholder="Rechercher commodité...", id="commodity-search")
                with RadioSet(id="trade-mode"):
                    yield RadioButton("Sell", value=True, id="mode-sell")
                    yield RadioButton("Buy", id="mode-buy")
                    yield RadioButton("Best routes", id="mode-best")
                    yield RadioButton("Compare", id="mode-compare")
            with Horizontal(id="trade-content"):
                yield DataTable(id="trade-table", cursor_type="row")
                yield Static("Sélectionnez une route", id="trade-detail")

    def on_mount(self) -> None:
        table = self.query_one("#trade-table", DataTable)
        table.add_columns(
            "Terminal", "Prix", "Stock (SCU)", 
            "Marge/SCU", "Source", "Fraîcheur"
        )
        # Charger les données initiales via core/trade.py
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Afficher le détail quand on clique sur une ligne"""
        detail = self.query_one("#trade-detail", Static)
        # Récupérer les données de la ligne sélectionnée
        # Calculer le profit total selon la capa cargo actuelle
        # Afficher dans le panneau détail
        pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filtrer les commodités en temps réel"""
        # Filtrer la DataTable selon le texte saisi
        pass
```

---

## Phase 3 — Écran Routes `screens/route.py`

Reproduit les commandes `/route` et `/plan`.

### Composants :
1. **Label** : "Depuis : [position courante]" (lié à PositionBar)
2. **DataTable** : routes triées par profit, avec colonnes Destination, Commodité, Prix achat, Prix vente, Marge/SCU, Profit total, Distance/Temps
3. **Filtre** : système (Stanton/Pyro), min profit, commodités illégales oui/non

---

## Phase 4 — Écran Info `screens/info.py`

Reproduit la commande `/info`.

### Composants :
1. **Input** : recherche terminal ou commodité
2. **Panneau résultat** : infos détaillées (localisation hiérarchique, prix buy/sell, stock, historique si dispo)

---

## Phase 5 — Stylesheet `styles/app.tcss`

Thème sombre inspiré du HUD Star Citizen :

```css
Screen {
    background: $surface;
}

#position-bar {
    dock: top;
    height: 3;
    background: $panel;
    padding: 0 1;
}

#trade-controls {
    height: 3;
    padding: 0 1;
}

#trade-table {
    width: 2fr;
}

#trade-detail {
    width: 1fr;
    border-left: solid $accent;
    padding: 1;
}

DataTable > .datatable--header {
    background: $accent;
    color: $text;
    text-style: bold;
}

/* Couleurs des sources de données */
.source-uex {
    color: cyan;
}

.source-sctrade {
    color: #ff8c00;
}

.profit-positive {
    color: $success;
}

.profit-negative {
    color: $error;
}

.data-stale {
    color: yellow;
}
```

---

## Phase future — Overlay PyWebView

Une fois le TUI Textual stable, la migration vers un overlay transparent se fait via :

### Fichier `overlay.py` :

```python
"""
Lanceur overlay — ouvre uexinfo dans une fenêtre transparente par-dessus le jeu.
Utilise textual-web pour servir l'app en HTML + pywebview pour l'affichage.
Nécessite: pip install pywebview textual-web
"""
import subprocess
import threading
import time
import webview

TEXTUAL_PORT = 8090

def start_textual_web():
    """Lance textual-web en arrière-plan"""
    subprocess.run([
        "textual-web", 
        "--command", "python -m uexinfo",
        "--host", "localhost",
        "--port", str(TEXTUAL_PORT)
    ])

def main():
    # Lancer textual-web en thread
    t = threading.Thread(target=start_textual_web, daemon=True)
    t.start()
    
    # Attendre que le serveur soit prêt
    time.sleep(3)
    
    # Ouvrir la fenêtre overlay
    webview.create_window(
        title="uexinfo overlay",
        url=f"http://localhost:{TEXTUAL_PORT}",
        frameless=True,
        transparent=True,
        on_top=True,
        width=700,
        height=900,
    )
    webview.start()

if __name__ == "__main__":
    main()
```

### Hotkey global (à ajouter quand overlay actif) :

```python
from pynput import keyboard

HOTKEY = keyboard.HotKey(
    keyboard.HotKey.parse('<alt>+<shift>+u'),
    toggle_overlay  # fonction qui show/hide la fenêtre webview
)
```

---

## Dépendances à ajouter

```
# requirements.txt — ajouter :
textual>=0.80.0
textual-web>=0.7.0      # phase overlay uniquement
pywebview>=5.0           # phase overlay uniquement  
pynput>=1.7              # phase overlay uniquement
```

---

## Règles impératives pour Claude Code

1. **NE PAS modifier les fichiers dans `core/`** — la logique métier est stable et testée
2. **Créer des adaptateurs** si les fonctions de `core/` retournent du Rich — ne pas modifier les retours
3. **Conserver la config TOML existante** — le TUI doit lire/écrire le même `config.toml`
4. **Conserver le cache existant** — le TUI utilise le même mécanisme de cache
5. **Tester en mode terminal standard** avant tout — Textual tourne nativement dans le terminal
6. **Garder les raccourcis clavier** en plus de la souris — les deux modes doivent coexister
7. **Gérer Playwright en arrière-plan** — le scraping sc-trade.tools ne doit jamais bloquer l'UI
8. **Commencer par l'écran Trade** — c'est le plus utilisé, les autres peuvent venir après
9. **Respecter les codes couleur existants** : cyan=UEX, orange=sc-trade, vert=profit+, rouge=profit-, jaune=données périmées
10. **Documenter les changements** dans le README existant (section TUI)