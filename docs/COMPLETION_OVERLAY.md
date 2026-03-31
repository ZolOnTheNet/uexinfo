# Spécification — Complétion Tab dans l'Overlay

## 1. Objectif

Remplacer le stub minimal de `_complete_sync` (server.py) par un moteur de
complétion contextuel, riche et cohérent avec le fonctionnement de l'overlay.

L'ancien `completer.py` (prompt_toolkit, REPL) est une référence utile pour
les listes de sous-commandes et la logique de matching — **mais sa mécanique
(Completer, Document, Completion) ne s'applique pas à l'overlay**.

---

## 2. Comportement attendu

### 2.1 Déclenchement

| Situation | Comportement |
|---|---|
| Tab sans texte | Propose toutes les commandes, puis lieux, commodités, vaisseaux du joueur |
| Tab sur un mot partiel | Complète le préfixe commun ; affiche la liste filtrée |
| Ctrl+Echap | Ouvre/rouvre la liste même si vide |
| Echap | Ferme la liste sans modifier le texte |

### 2.2 Ordre de priorité des suggestions (sans texte)

1. Commandes (`/help`, `/voyage`, `/info`, …)
2. Lieux (terminaux, stations, planètes — via `LocationIndex`)
3. Commodités (`Laranite`, `Quantainium`, …)
4. Vaisseaux du joueur (`ctx.player.ships`)

### 2.3 Filtrage sur saisie partielle

Quand une partie d'un mot est tapée :

1. **Éléments dont le nom COMMENCE PAR** la saisie → affichés en premier
2. **Éléments CONTENANT** la saisie (sous-chaîne) → affichés ensuite
3. **Tab** complète le préfixe commun maximal des suggestions visibles
   (comportement bash/zsh)

Exemple : `Cuta` → `Cutlass Black` (préfixe), puis `Dragonfly Cutlass` (sous-chaîne).

### 2.4 Complétion contextuelle par commande

Quand la ligne commence par `/commande`, les suggestions changent :

| Ligne tapée | Suggestions proposées |
|---|---|
| `/voyage ` | sous-commandes voyage (`on`, `off`, `new`, `calc`, `tb`, …) |
| `/voyage calc ` | critères (`dist`, `benef`, `roi`, `all`) |
| `/voyage tb ` | sous-commandes tb (`list`, `compact`, `graph`) + lieux |
| `/info ` | terminaux + commodités + vaisseaux |
| `/go ` | lieux (LocationIndex, tous types) |
| `/nav ` | lieux |
| `/trade ` | sous-commandes trade (`buy`, `sell`, `best`, …) |
| `/trade buy ` | commodités |
| `/trade from ` | terminaux |
| `/config ` | clés de config (`ship`, `trade`, `scan`, `voyage.calc.nbsaut`, …) |
| `/scan ` | sous-commandes scan (`ecran`, `log`, `debug`, …) |
| `/player ` | sous-commandes player (`info`, `ship`, `dest`) |
| `/player ship ` | sous-commandes ship (`add`, `set`, `remove`, …) |
| `/explore ` | `ship`, `commodity` + noms de systèmes |
| `/mission ` | sous-commandes mission |

Règle générale : **chaque commande déclare ses sous-commandes et le type
d'élément attendu ensuite** (lieu, commodité, vaisseau, ou rien).

### 2.5 Affichage dans le dropdown

Chaque suggestion affiche :
- **Valeur** : le texte à insérer
- **Hint** : description courte (type, fabricant, système, description)

Exemple :

```
/voyage on        Activer un voyage ou en créer un
Cutlass Black     vaisseau · RSI · 46 SCU
Laranite          commodité · Minéral · extractable
Port Olisar       terminal · Stanton · Crusader
```

---

## 3. Architecture technique

### 3.1 Côté serveur — `overlay/server.py`

Remplacer `_complete_sync` par une version complète :

```python
def _complete_sync(self, text: str, cursor: int) -> list[dict]:
    """
    Retourne une liste de complétions pour le texte courant.
    Chaque item : {"value": str, "hint": str, "insert": str}
      - value   : texte complet affiché dans la liste
      - hint    : description courte (type, fabricant, etc.)
      - insert  : texte à insérer à la place du mot courant
    """
```

**Logique :**

```
1. Extraire le mot courant (de cursor en arrière jusqu'à un espace)
2. Extraire la commande racine (premier mot de la ligne)
3. Selon la commande racine + profondeur → charger les candidats
4. Filtrer : préfixe d'abord, puis sous-chaîne
5. Limiter à 40 suggestions
6. Calculer le préfixe commun et l'inclure dans la réponse
```

Réponse JSON enrichie :

```json
{
  "type": "completions",
  "common_prefix": "Cut",
  "items": [
    {"value": "Cutlass Black",  "hint": "vaisseau · RSI",   "insert": "Cutlass_Black"},
    {"value": "Cutlass Red",    "hint": "vaisseau · RSI",   "insert": "Cutlass_Red"},
    {"value": "Cutlass Steel",  "hint": "vaisseau · RSI",   "insert": "Cutlass_Steel"}
  ]
}
```

Le champ `insert` contient le texte à insérer (avec underscores pour les lieux/vaisseaux
si la commande l'exige).

### 3.2 Données utilisées côté serveur

| Source | Usage |
|---|---|
| `uexinfo.cli.commands.get_names()` | Noms des commandes enregistrées |
| `_SUBS_WITH_HELP` (à déplacer dans `cli/completer_data.py`) | Sous-commandes + hints statiques |
| `ctx.cache.terminals` | Complétion lieux (terminaux) |
| `ctx.cache.commodities` | Complétion commodités |
| `ctx.cache.vehicles` | Complétion vaisseaux |
| `ctx.location_index` | Complétion lieux fuzzy (`@xxx`) |
| `ctx.player.ships` | Vaisseaux du joueur en priorité |

### 3.3 Côté client — `overlay/static/index.html`

Le JS doit gérer :

**Déclenchement :**
- `Tab` → envoyer `{"type": "complete", "text": ..., "cursor": ...}` au WS
- `Ctrl+Echap` → même message, même si le champ est vide
- `Echap` → fermer le dropdown (sans WS)

**Réception des complétions :**
- Afficher le dropdown sous le champ de saisie
- Appliquer `common_prefix` immédiatement dans le champ si > saisie actuelle
  (complétion du préfixe commun, style bash)
- Si une seule suggestion → insérer directement, fermer le dropdown

**Navigation dans le dropdown :**
- `↑` / `↓` → sélectionner une suggestion
- `Tab` ou `Entrée` sur une suggestion → insérer `insert`, fermer le dropdown
- `Echap` → fermer le dropdown

**Format d'affichage :**

```
┌─────────────────────────────────────┐
│ /voyage on      Activer un voyage   │  ← sélectionné
│ /voyage off     Désactiver          │
│ /voyage new     Créer un voyage     │
│ /voyage calc    Voyage optimisé     │
└─────────────────────────────────────┘
```

---

## 4. Module `cli/completer_data.py` (nouveau)

Extraire de l'ancien `completer.py` la dict `_SUBS_WITH_HELP` dans un fichier
dédié, indépendant de prompt_toolkit :

```python
"""Données statiques de complétion — sous-commandes et hints."""

# Format : {commande: [(sous-commande, hint), ...]}
SUBS: dict[str, list[tuple[str, str]]] = {
    "voyage": [
        ("on",      "Activer un voyage ou en créer un"),
        ("off",     "Désactiver le voyage courant"),
        ("new",     "Créer un nouveau voyage"),
        ("calc",    "Générer un voyage optimisé"),
        ("tb",      "Tableau de bord : missions par étape"),
        ("list",    "Missions du voyage actif"),
        ("add",     "Ajouter des missions"),
        ("remove",  "Retirer une mission"),
        ("clear",   "Vider les missions"),
        ("name",    "Renommer le voyage"),
        ("copy",    "Copier vers un autre voyage"),
        ("accept",  "Valider et analyser"),
        ("later",   "Sauvegarder sans analyser"),
        ("cancel",  "Annuler les modifications"),
        ("delete",  "Supprimer un voyage"),
    ],
    "voyage calc": [
        ("dist",   "Minimiser la distance"),
        ("benef",  "Maximiser le bénéfice"),
        ("roi",    "Maximiser le ROI (aUEC/Gm)"),
        ("all",    "Générer les 3 propositions"),
    ],
    "voyage tb": [
        ("list",    "Liste les étapes"),
        ("compact", "Supprimer les étapes vides"),
        ("graph",   "Vue arbre des étapes"),
    ],
    # ... (reprendre _SUBS_WITH_HELP de l'ancien completer.py)
}

# Type d'élément attendu après la commande/sous-commande
# "location" | "commodity" | "vehicle" | "terminal" | None
NEXT_TYPE: dict[str, str] = {
    "go":          "location",
    "nav":         "location",
    "info":        "any",        # terminal + commodity + vehicle
    "trade from":  "terminal",
    "trade to":    "terminal",
    "trade buy":   "commodity",
    "trade sell":  "commodity",
    "voyage tb":   "location",
    "voyage on":   None,
    "voyage add":  None,
}
```

Ce module est importable sans dépendances lourdes (pas de prompt_toolkit, pas de ctx).

---

## 5. Plan d'implémentation

### Phase 1 — Données (30 min)
1. Créer `uexinfo/cli/completer_data.py` avec `SUBS` et `NEXT_TYPE`
   (reprendre `_SUBS_WITH_HELP` de l'ancien `completer.py` via git)
2. Ajouter les entrées manquantes : `voyage tb`, `mission`, `auto`, `debug`

### Phase 2 — Serveur (1h)
1. Réécrire `_complete_sync` dans `server.py` :
   - Parsing du contexte (commande racine, mot courant, profondeur)
   - Chargement des candidats selon contexte
   - Tri : préfixe d'abord, sous-chaîne ensuite
   - Calcul du `common_prefix`
2. Enrichir la réponse JSON avec `common_prefix` et `insert`

### Phase 3 — Client JS (1h)
1. Modifier la gestion de `Tab` dans `index.html`
2. Implémenter le dropdown de complétion (HTML/CSS/JS)
3. Gérer `Ctrl+Echap` (force ouverture) et `Echap` (fermeture)
4. Appliquer `common_prefix` automatiquement

---

## 6. Ce que l'on NE reprend PAS de l'ancien completer.py

- Les imports `prompt_toolkit` (Completer, Completion, Document) → inutilisés
- La classe `UEXCompleter(Completer)` → remplacée par `_complete_sync`
- La méthode `get_completions(document, complete_event)` → API prompt_toolkit
- La logique `/explore` avec hiérarchie `.` → peut être portée si besoin

## 7. Réutilisable de l'ancien completer.py

- `_SUBS_WITH_HELP` → devient `SUBS` dans `completer_data.py`
- `_complete_info_query` → logique portée dans `_complete_sync` (commodités,
  terminaux, vaisseaux avec préfixe puis sous-chaîne)
- `_complete_location` → portée dans `_complete_sync` pour les commandes
  attendant un lieu
