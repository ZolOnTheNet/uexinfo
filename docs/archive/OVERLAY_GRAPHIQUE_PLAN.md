# Plan — Console graphique overlay (TUI v2)

> Date : 2026-03-17
> Portée : refonte de l'interface Textual (`app.py` + widgets) pour obtenir
> une console graphique interactive utilisable en overlay sur Star Citizen.

---

## 1. Vision générale

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Zone de sortie (RichLog enrichi)                              [copier] │
│  ─ texte scrollable, copiable sans markup                               │
│  ─ mots-jeu soulignés, cliquables, menus contextuels                   │
│                                                                         │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  > _  [autocomplétion inline + dropdown Ctrl+Espace]                   │
├───────────────────┬──────────────────────────────────────┬─────────────┤
│ POS: Port Olisar  │ < │ DEST: Crusader - 3.2 Gm │ [Trade]│ V: Caterpillar / 576 SCU │
│ [ScanSC] [ScanLog]│                                      │ [⚙] [?] │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Composants à créer / refactorer

| Composant | Fichier | État | Priorité |
|-----------|---------|------|----------|
| RichLog enrichi (clickable, copiable) | `widgets/output.py` (nouveau) | À créer | P1 |
| PromptWidget amélioré | `widgets/prompt.py` | Refactor | P1 |
| StatusBar complète | `widgets/status_bar.py` | Refactor | P1 |
| Moteur de détection des mots-jeu | `widgets/word_classifier.py` | Nouveau | P1 |
| WordMenu enrichi | `widgets/word_menu.py` | Refactor | P2 |
| Panneau config | `widgets/config_panel.py` | Nouveau | P2 |
| Système i18n | `i18n/labels.json` + `i18n/__init__.py` | Nouveau | P3 |
| Commande `/config edit` | `cli/commands/config.py` | Ajout | P2 |
| App principale | `app.py` | Refactor | P1 |

---

## 3. Phase A — Zone de sortie enrichie (`widgets/output.py`)

### 3.1 Copie de texte épurée

- Ctrl+Y (existant) copie le contenu visible de RichLog.
- **Nouveau** : la copie strip tous les markups Rich (`[cyan]...[/cyan]`),
  les URLs (`https://...`) et les codes ANSI avant mise en presse-papier.
- Implémenter `_strip_for_clipboard(text: str) -> str` avec `re.sub`.

### 3.2 Mots cliquables dans la sortie

**Problème Textual** : `RichLog` ne supporte pas nativement le clic mot-par-mot.
**Solution** : remplacer `RichLog` par un widget `Static` ou `ScrollableContainer`
avec des `Label` Rich rendus ligne par ligne, ou patcher via `Markup` avec
des liens Textual (`[@click="..."]text[/@]`).

**Approche retenue** : `OutputView(ScrollView)` — widget personnalisé qui :
1. Reçoit des lignes `RichText` depuis le buffer console.
2. Passe chaque ligne dans `WordClassifier.annotate(line)` → markup Textual
   avec liens cliquables (`[@click]word[/@]`).
3. Ajoute la ligne en bas (auto-scroll).
4. Conserve un buffer texte brut parallèle pour la copie.

### 3.3 Soulignement discret

Les mots cliquables sont rendus avec `underline` Rich mais avec la couleur
`dim` pour ne pas agresser visuellement :
```
[dim underline]Port Olisar[/dim underline]
```
Seul le survol (hover Textual) accentue le style → `bold underline`.

---

## 4. Phase B — Classificateur de mots (`widgets/word_classifier.py`)

### 4.1 Catégories reconnues

| Catégorie | Source de données | Action clic gauche | Menu clic droit |
|-----------|-------------------|--------------------|-----------------|
| `commodity` | `ctx.cache.commodities` | `/info <commodity>` | Info · Trade buy · Trade sell |
| `terminal` | `ctx.cache.terminals` | `/info <terminal>` | Info · Go · Dest · Trade |
| `system` | `ctx.cache.star_systems` | `/info <system>` | Info · Go |
| `ship` (vaisseau joueur) | `ctx.player.ships` | `/player ship set <ship>` | Set courant · Info · Supprimer |
| `ship` (vaisseau jeu générique) | `ctx.cache.vehicles` | `/info ship <ship>` | Info |
| `command` | Liste des commandes | Exécute la commande | Aide |

### 4.2 Détection

```python
class WordClassifier:
    def annotate(self, rich_text: str, ctx: AppContext) -> str:
        """Retourne un markup Textual avec liens pour chaque mot reconnu."""
```

- Tokeniser la ligne en mots/phrases (NgramScanner, max 3 mots consécutifs).
- Pour chaque token : tester les catégories dans l'ordre (plus long match first).
- Si match → enrober dans `[@click="word_action(category, value)"]...[/@]`.
- Cas spécial **contexte** : si la sortie est listée depuis `/player ship list`,
  le clic sur un nom de vaisseau exécute directement `/player ship set`.

### 4.3 Action générique vs contextuelle

Le contexte est transmis via un paramètre `output_context: str | None` attaché
à chaque bloc de sortie (ex. `"player_ship_list"`, `"trade_sell"`, `None`).

```python
@dataclass
class OutputBlock:
    lines: list[str]
    context: str | None = None
```

---

## 5. Phase C — PromptWidget amélioré (`widgets/prompt.py`)

### État actuel (déjà implémenté)
- Historique ↑↓
- Inline suggestion (UexSuggester)
- Dropdown CompletionList (Ctrl+↓)
- Ctrl+Espace → ouvre CompletionList

### Améliorations requises

| Fonctionnalité | Détail |
|----------------|--------|
| Navigation dans le texte | ← → déjà gérés par `Input` Textual ; vérifier Home/End |
| Ctrl+Espace contextuel | Si curseur après un mot partiel : filtre la liste sur ce mot. Sinon : liste tous les sous-commandes/args possibles à cette position |
| Aide inline | Sous la zone de saisie, une ligne `[dim]hint[/dim]` affiche la syntaxe de la commande en cours (ex. `/trade buy <commodity> [terminal]`) |
| Tab simple | Si un seul candidat : complétion directe. Si plusieurs : ouvre dropdown |

### Ctrl+Espace — comportement détaillé

1. Parser la ligne jusqu'au curseur → position dans l'arbre de commande.
2. Extraire le préfixe partiel du token courant (peut être vide).
3. Interroger `UexSuggester.get_completions(context, prefix)`.
4. Afficher `CompletionList` avec le sous-ensemble filtré.
5. Si `prefix` vide et aucun contexte → afficher toutes les commandes.

---

## 6. Phase D — StatusBar complète (`widgets/status_bar.py`)

### Layout de la barre

```
[ POS: Port Olisar ] [ < ] [ DEST: Crusader Ind. — 3.2 Gm ] [ Trade ] [ V: Caterpillar / 576 SCU ] | [●ScanSC] [●ScanLog] | [⚙] [?]
```

### Éléments détaillés

#### 6.1 POS (position courante)
- Label cliquable → ouvre CompletionList filtrée sur terminaux/stations.
- Mise à jour via `ctx.player.location`.
- Format : `POS: <nom>` ou `POS: —` si non défini.

#### 6.2 Bouton `<` (copier dest → pos)
- Exécute `/go from <dest>` pour faire de la destination la position courante.
- Grisé si pas de destination.

#### 6.3 DEST (destination + distance)
- Label cliquable → ouvre CompletionList filtrée sur terminaux.
- Format : `DEST: <nom>` ou `DEST: <nom> — <x.x Gm>` si distance connue.
- Distance récupérée depuis le graphe de transport (`transport_graph.shortest_path`).

#### 6.4 Bouton `Trade`
- Exécute `/trade` avec les paramètres courants (position + vaisseau actif).
- Équivalent de `/trade best`.

#### 6.5 Vaisseau (V:)
- Format : `V: <nom> / <scu> SCU`.
- Cliquable → CompletionList avec la liste des vaisseaux du joueur.
- Sélection → `/player ship set <nom>`.

#### 6.6 Drapeaux (flags clignotants)

```python
@dataclass
class StatusFlag:
    key: str          # identifiant interne
    label: str        # label affiché (peut être traduit)
    active: bool      # clignote si True
    command: str      # commande à exécuter au clic
```

| Flag | Condition d'activation | Commande au clic |
|------|------------------------|------------------|
| ScanSC | `ctx.last_scan` nouveau depuis dernier affichage | `/scan` (analyse) |
| ScanLog | `ctx.log_last_mtime` changé | `/scan log` |

- Clignotement : basculer entre style `bold yellow` et `dim` toutes les 800 ms
  via un `set_interval` Textual.
- Clic → exécute la commande ET arrête le clignotement.

#### 6.7 Bouton Config (⚙)
- Ouvre le panneau de configuration (Phase E).

#### 6.8 Bouton Aide (?)
- Exécute `/help` dans la console.

---

## 7. Phase E — Panneau de configuration (`widgets/config_panel.py`)

### Déclencheurs
- Clic sur ⚙ dans la StatusBar.
- Commande `/config edit`.

### Structure du panneau (modal Textual)

```
┌─ Configuration UEXInfo ──────────────────────┐
│  Profil                                       │
│    Nom joueur : [_______________]             │
│    Vaisseau actif : [▼ Caterpillar       ]   │
│                                               │
│  Overlay                                      │
│    Transparence : [████░░░░] 85%             │
│    Hotkey : [alt+shift+u]                    │
│                                               │
│  Apparence                                    │
│    Police : [▼ Cascadia Code          ]      │
│    Taille : [14] px   Largeur : [80] cols    │
│    Hauteur : [30] lignes                     │
│                                               │
│  Trading                                      │
│    Profit min/SCU : [100] aUEC               │
│    Marge min : [5] %                         │
│    Distance max : [50] Gm                    │
│                                               │
│           [Annuler]  [Appliquer]             │
└───────────────────────────────────────────────┘
```

### Champs config mappés

| Champ UI | Clé config TOML | Type |
|----------|-----------------|------|
| Transparence | `overlay.opacity` | float 0.5–1.0 (slider) |
| Hotkey | `overlay.hotkey` | str (Input) |
| Largeur | `overlay.width` | int (px ou cols) |
| Hauteur | `overlay.height` | int (px ou lignes) |
| Police | `overlay.font_family` | str (Select) |
| Taille police | `overlay.font_size` | int |
| Profit min/SCU | `trade.min_profit_per_scu` | int |
| Marge min | `trade.min_margin_percent` | int |
| Distance max | `trade.max_distance` | float |
| Scan mode | `scan.mode` | Select (ocr/log/confirm) |

### Nouvelles clés config à ajouter à `settings.py`

```toml
[overlay]
font_family = "Cascadia Code"
font_size = 14
```

### Implémentation

- `ConfigPanel(ModalScreen)` — écran modal Textual.
- Charger `ctx.cfg` à l'ouverture, pré-remplir les champs.
- `[Appliquer]` → `save(cfg)` + notifier `app` pour appliquer les changements visuels
  (opacité via `pywebview.evaluate_js`, taille via `app.styles`).

---

## 8. Phase F — i18n (préparation, pas d'implémentation immédiate)

### Structure prévue

```
uexinfo/i18n/
├── __init__.py          # get_label(key, lang=None) -> str
├── labels_fr.json       # français (référence)
└── labels_en.json       # anglais
```

### Convention de clés

```json
{
  "status.pos": "POS",
  "status.dest": "DEST",
  "status.trade": "Trade",
  "status.ship": "V",
  "status.scan_sc": "ScanSC",
  "status.scan_log": "ScanLog",
  "status.config": "⚙",
  "status.help": "?",
  "menu.info": "Info",
  "menu.go": "Aller",
  "menu.dest": "Destination",
  "menu.ship_set": "Vaisseau courant",
  "menu.trade_buy": "Acheter",
  "menu.trade_sell": "Vendre",
  "config.title": "Configuration UEXInfo",
  "config.cancel": "Annuler",
  "config.apply": "Appliquer"
}
```

### Points d'intégration (à ne pas oublier lors des implémentations)

- Tous les labels de widgets doivent passer par `_L("clé")` (alias de `get_label`).
- Les labels de commandes CLI restent en dur (pas d'i18n pour le REPL).
- La langue est déterminée par `cfg["ui"]["lang"]` (défaut `"fr"`).

---

## 9. Ordre d'implémentation recommandé

```
Semaine 1 — Fondations
  ├─ A. OutputView (RichLog remplaçant)          → widgets/output.py
  ├─ B. WordClassifier (détection basique)       → widgets/word_classifier.py
  └─ C. StatusBar refactor (layout complet)      → widgets/status_bar.py

Semaine 2 — Interactivité
  ├─ D. WordMenu enrichi (5→8 actions)           → widgets/word_menu.py
  ├─ E. PromptWidget — Ctrl+Espace contextuel    → widgets/prompt.py
  └─ F. Actions contextuelles (ship list etc.)   → app.py

Semaine 3 — Config & polish
  ├─ G. ConfigPanel (modal)                      → widgets/config_panel.py
  ├─ H. /config edit                             → cli/commands/config.py
  ├─ I. Flags clignotants (ScanSC, ScanLog)      → widgets/status_bar.py
  └─ J. Nouvelles clés overlay dans settings.py → config/settings.py

Semaine 4 — i18n & intégration finale
  ├─ K. Squelette i18n                           → i18n/
  ├─ L. Tests manuels overlay PyWebView          → overlay.py
  └─ M. Mise à jour docs + CLAUDE.md
```

---

## 10. Contraintes et risques techniques

| Risque | Mitigation |
|--------|------------|
| `RichLog` ne supporte pas les liens Textual | Remplacer par `OutputView` custom (ScrollView + Labels) |
| Clignotement CPU avec beaucoup de flags | `set_interval` Textual (pas de threading manuel) |
| Copie sans markup : Rich ne fournit pas de strip simple | Regex sur `\[.*?\]` + filtre URL |
| Police configurable dans Textual | `app.styles.css` dynamique ou `tcss` avec variable CSS |
| Transparence PyWebView : JS `document.body.style.background` | Déjà dans overlay.py — étendre |
| Mots longs (3-grammes) : ambiguïté | Priorité longest match, index normalisé lowercase |

---

## 11. Fichiers à créer / modifier — récapitulatif

### Nouveaux fichiers
- `uexinfo/widgets/output.py` — OutputView (remplace RichLog)
- `uexinfo/widgets/word_classifier.py` — WordClassifier
- `uexinfo/widgets/config_panel.py` — ConfigPanel (ModalScreen)
- `uexinfo/i18n/__init__.py` — get_label()
- `uexinfo/i18n/labels_fr.json` — labels français

### Fichiers modifiés
- `uexinfo/app.py` — intégration OutputView, OutputBlock, actions contextuelles
- `uexinfo/widgets/status_bar.py` — layout complet + flags + boutons
- `uexinfo/widgets/prompt.py` — Ctrl+Espace contextuel, hint ligne
- `uexinfo/widgets/word_menu.py` — actions enrichies par catégorie
- `uexinfo/config/settings.py` — nouvelles clés `overlay.font_*`, `ui.lang`
- `uexinfo/styles/app.tcss` — styles OutputView, flags, config panel
- `uexinfo/cli/commands/config.py` — sous-commande `edit`

---

## 12. Dépendances supplémentaires potentielles

| Package | Usage | Déjà présent |
|---------|-------|--------------|
| `pyperclip` | Clipboard cross-platform (alternative à `pywin32`) | Non — à évaluer |
| `textual >= 0.80` | `ModalScreen`, `on_mount`, liens `[@click]` | Oui |
| `pywebview >= 5.0` | Transparence, overlay | Optionnel (déjà) |

> Note : Textual >= 0.80 supporte déjà les liens dans les `Label` via
> `[@click='handler']text[/@]`. Vérifier la version installée.
