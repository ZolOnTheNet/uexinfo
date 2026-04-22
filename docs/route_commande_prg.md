# Planification — commande `/route`

**Date :** 2026-04-22 (v2 — corrections utilisateur 22/04)  
**Statut :** À implémenter  
**Priorité :** Haute (remplace l'usage informel de `/trade sctrade`)

---

## Contexte

La commande `/trade sctrade` existe mais n'exploite pas bien sc-trade.tools.
L'endpoint `POST /api/tools/trades` (alias « route » dans le vocabulaire sc-trade.tools)
supporte plusieurs escales, un filtre commodités, et plusieurs critères d'optimisation.

L'endpoint `itinerary` (origin→destination fixe avec détour) n'est **pas** dans le périmètre
de cette commande et ne doit pas être exposé pour l'instant.

---

## Syntaxe de la commande

```
/route [from <terminal>]
       [to <terminal>[,<terminal>...]]
       [--commodity <nom>[,<nom>...]]
       [--scu <n>]
       [--cycle | -c | -b | --boucle]
       [--saut <n> | --hop <n> | -s <n> | -h <n>]
       [--benef | --roi | --short | --temps]
       [--delta <n>]
```

### `/route` seul → formulaire inline

Sans argument, affiche un formulaire interactif dans l'overlay (voir section UI ci-dessous)
avec tous les champs pré-remplis depuis la config et la position actuelle.

---

## Paramètres détaillés

| Paramètre | Alias | Description | Défaut |
|---|---|---|---|
| `from <terminal>` | — | Terminal de départ | `@local` (ctx.player.location) |
| `to <terminal,...>` | — | Terminal(aux) à visiter | `@dest` si défini, sinon route libre |
| `--commodity <n,...>` | `--comm` | Commodités prioritaires (filtre) | aucun filtre |
| `--scu <n>` | — | Override rapide du cargo disponible (SCU total) | vaisseau actif |
| `--cycle` | `-c`, `-b`, `--boucle` | Revenir au point de départ si possible | off |
| `--saut <n>` | `--hop`, `-s`, `-h` | Nombre max d'escales | `route.saut` (défaut 5) |
| `--benef` | — | Optimiser par bénéfice total | selon `route.rentabilite` |
| `--roi` | — | Optimiser par ROI (aUEC/SCU) | selon `route.rentabilite` |
| `--short` | `--temps` | Optimiser par distance/temps | selon `route.rentabilite` |
| `--delta <n>` | — | Détour acceptable en Gm pour un meilleur résultat | `route.delta` |

### Règles de résolution

- `@local` → `ctx.player.location`
- `@dest` → `ctx.player.destination`
- `to` : plusieurs terminaux séparés par des virgules ou des espaces
- Si `to` absent et `@dest` absent : route libre depuis `from` (laisse l'API choisir)
- `--cycle` : si l'API ne supporte pas nativement le retour, post-traitement côté client

---

## Annulation / arrêt

La commande peut être longue (requête réseau + calcul). **Double-Esc** pendant l'exécution :
- Popup/question dans l'overlay : **« Arrêter ici et garder les résultats »** ou **« Annuler »**
- Utilise le mécanisme double-Esc existant dans l'overlay
- Si arrêt : affiche les résultats partiels déjà reçus
- Si annulation : ne rien afficher, retour au prompt

---

## Gestion du cargo et des tailles de boîtes SCU

### Distinction `--scu` vs `supportedBoxSizeInScu`

`--scu` n'est **pas** `supportedBoxSizeInScu`. Ce sont deux notions différentes :

| Concept | Description |
|---|---|
| `--scu <n>` | Override rapide : « j'ai N SCU disponibles » (remplace le vaisseau actif pour ce calcul) |
| `supportedBoxSizeInScu` | Taille de la plus grande boîte acceptée par les grilles cargo du vaisseau (1/2/4/8/16/24/32 SCU) |

### Problème des tailles de boîtes

Les commodités en SC se vendent en boîtes de taille fixe (1, 2, 4, 8, 16, 24, 32 SCU).
Chaque terminal n'accepte que certaines tailles selon sa configuration.
Le vaisseau a des grilles de tailles données (ex: 4×8 SCU + 2×4 SCU = 40 SCU total).

**Ce que le logiciel doit faire** (sauf en mode `--short`/`--temps`) :

1. Connaître les tailles de boîtes acceptées par chaque terminal de la route
2. Connaître les grilles du vaisseau actif (ou du SCU override)
3. Calculer la combinaison de boîtes qui **maximise le remplissage** des grilles
4. Si aucune combinaison compatible : avertir et proposer la meilleure approximation
5. Transmettre à l'API la valeur correcte de `supportedBoxSizeInScu`
   (= plus grande boîte que le vaisseau peut accueillir dans ses grilles)

**En mode `--short`/`--temps`** : optimisation distance uniquement, pas de calcul de boîtes.

### Source des données tailles

- Vaisseau : `ctx.player.ships` → grilles cargo (`ScanPriceStore` ou modèle `Ship`)
- Terminal : données UEX (à vérifier si disponible) ou sc-trade.tools
- À investiguer : où trouver les tailles acceptées par terminal dans l'API UEX/sctrade

---

## Options de configuration

```
/config route.rentabilite roi|benef|dist|temp
    Critère d'optimisation par défaut.
    roi   = meilleur retour sur investissement (aUEC/SCU)
    benef = bénéfice total maximal
    dist  = route la plus courte (distance Gm)
    temp  = route la plus rapide (pour l'instant identique à dist)
    Défaut : roi

/config route.saut <n>
    Nombre max d'escales par défaut (≥1, pas de maximum imposé côté logiciel).
    SC-trade.tools a ses propres limites internes — elles s'appliquent côté serveur.
    Défaut : 5

/config route.delta <n>
    Distance en Gm acceptable pour un transit "à vide" vers un meilleur terminal.
    Exemple : 3.0 = accepte jusqu'à 3 Gm de détour.
    Défaut : 3.0
```

---

## Formulaire inline — UI overlay

### Objectif

`/route` sans argument ouvre un formulaire dans l'overlay, similaire à celui de
sc-trade.tools (côté web), avec tous les paramètres éditables avant de lancer le calcul.

### Structure du formulaire

```
┌─ Route commerciale ──────────────────────────────────────────────────┐
│  Départ     : [Area 18              ▾]   (autocomplete position)     │
│  Arrivée    : [                     ▾]   (optionnel, multi-valeurs)  │
│  Cargo      : [96] SCU   Vaisseau : [Freelancer MAX         ▾]       │
│  Escales    : [5 ] max   Retour   : [☐] boucle               │
│  Critère    : (●) ROI  (○) Bénéfice  (○) Distance/Temps             │
│  Delta      : [3.0] Gm                                               │
│                                                                       │
│  ┌─ Commodités ─────────────────┐  ┌─ Lieux ───────────────────────┐ │
│  │ [Seulement ▾] [Exclure ▾]   │  │ [Seulement ▾] [Exclure ▾]    │ │
│  │ ▶ Minéraux                   │  │ ▶ Stanton                     │ │
│  │   ☐ Aluminium                │  │   ▶ Hurston                   │ │
│  │   ☐ Titanium                 │  │     ☐ Lorville                │ │
│  │ ▶ Agricole                   │  │     ☐ HDMS-Lathan             │ │
│  │   ☐ Agricultural Supp.       │  │   ▶ ArcCorp                   │ │
│  │   ☐ Agricium                 │  │     ☐ Area 18                 │ │
│  │ ▶ Médical                    │  │ ▶ Pyro                        │ │
│  │   ...                        │  │   ...                         │ │
│  └──────────────────────────────┘  └───────────────────────────────┘ │
│                                                                       │
│           [Calculer]          [Annuler]                              │
└───────────────────────────────────────────────────────────────────────┘
```

### Comportement des listes filtre

- **Structure hiérarchique** : catégorie → commodité (pour commodités) ; système → station → terminal (pour lieux)
- **Clic sur catégorie** : déplie/replie les enfants
- **Toggle "Seulement" / "Exclure"** : bascule entre whitelist (ne garder que ces éléments) et blacklist (exclure ces éléments)
- **Sélection multiple** par cases à cocher
- **Sélection rapide** : clic sur une catégorie = cocher/décocher tous les enfants
- Par défaut : aucun filtre actif (tout inclus)

### Implémentation UI

Nouveau type de message WebSocket : `route_form`

```json
{
  "type": "route_form",
  "params": {
    "from": "Area 18",
    "to": [],
    "scu": 96,
    "ship": "Freelancer MAX",
    "saut": 5,
    "cycle": false,
    "critere": "roi",
    "delta": 3.0,
    "commodity_filter": { "mode": "none", "items": [] },
    "location_filter": { "mode": "none", "items": [] }
  },
  "commodity_tree": [
    { "category": "Minéraux", "items": ["Aluminium", "Titanium", ...] },
    ...
  ],
  "location_tree": [
    { "system": "Stanton", "stations": [
        { "name": "Lorville", "terminals": ["TDD - Area 18", "Admin - Lorville", ...] },
        ...
    ]},
    ...
  ]
}
```

Retour utilisateur (submit) : message `route_submit` avec les params remplis → déclenche `_execute_route`.

### Composant JS `route-form`

- Nouveau panneau `<div id="route-form-panel">` (comme `scan-overlay`)
- Rendu des arbres avec `<details>`/`<summary>` HTML natif (collapsible sans JS lourd)
- Toggle seulement/exclure : bouton `<select>` à 3 options (Aucun filtre / Seulement / Exclure)
- Les coches cochées sont envoyées dans `route_submit.commodity_filter.items` et `route_submit.location_filter.items`

---

## Aide `/help route` (texte à afficher)

```
/route — Calcule une route commerciale optimale via sc-trade.tools

Usage :
  /route                        Formulaire interactif complet
  /route [options]              Calcul direct

Paramètres :
  from <lieu>                   Départ  (défaut : @local = position actuelle)
  to <lieu>[,<lieu>...]         Terminaux à visiter  (défaut : @dest)
  --commodity <nom>[,<nom>...]  Commodités prioritaires
  --scu <n>                     Override cargo en SCU (remplace le vaisseau actif)
  --cycle | -c | --boucle       Revenir au point de départ si possible
  --saut <n> | --hop <n>        Max escales  (défaut : config route.saut = 5)
  --benef                       Critère : bénéfice total maximal
  --roi                         Critère : ROI maximal (aUEC/SCU)
  --short | --temps             Critère : distance/temps minimal
  --delta <n>                   Détour max en Gm pour un meilleur terminal

Annulation :
  Double-Esc pendant le calcul  Choix : garder résultats partiels ou annuler

Exemples :
  /route                                Formulaire avec valeurs courantes
  /route from Area18 --benef --saut 3   3 escales depuis Area18, max bénéfice
  /route to Lorville,HDMS-Lathan --roi  Passe par ces terminaux, ROI max
  /route --cycle --scu 96               Boucle avec 96 SCU disponibles

Configuration :
  /config route.rentabilite roi|benef|dist|temp   (défaut : roi)
  /config route.saut <n>                          (défaut : 5)
  /config route.delta <n>                         (défaut : 3.0 Gm)

Note : nécessite un token Patreon sc-trade.tools (/config sctrade token <token>).
```

---

## Architecture d'implémentation

### Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---|---|---|
| `uexinfo/cli/commands/route.py` | **Créer** | Handler `/route`, parser args, `_execute_route`, `_display_route_result` |
| `uexinfo/api/sctrade_client.py` | **Modifier** | Retirer `itinerary()` ; enrichir `trades()` : paramètres filtres + `supportedBoxSizeInScu` calculé |
| `uexinfo/cli/commands/__init__.py` | **Modifier** | Import module route |
| `uexinfo/cli/commands/config.py` | **Modifier** | Ajouter `route.rentabilite`, `route.saut`, `route.delta` dans `_DOT_KEYS` |
| `uexinfo/cli/completer_data.py` | **Modifier** | SUBS `route` + clés config |
| `uexinfo/overlay/static/index.html` | **Modifier** | Composant `route-form-panel` + handler `route_form`/`route_submit` |
| `docs/commands.md` | **Mettre à jour** | Section `/route` |

### Structure de `route.py`

```python
@register("route")
def cmd_route(args, ctx):
    if not args:
        _send_route_form(ctx)      # formulaire overlay
        return
    params = _parse_route_args(args, ctx)
    if params is None:
        return
    _execute_route(params, ctx)


def _parse_route_args(args, ctx) -> dict | None:
    """Parse CLI args et applique les defaults config."""
    ...

def _send_route_form(ctx):
    """Construit et envoie le message route_form à l'overlay."""
    # Construit commodity_tree depuis ctx.cache.commodities (par catégorie)
    # Construit location_tree depuis ctx.cache.star_systems + terminals
    # Envoie {"type": "route_form", "params": ..., "commodity_tree": ..., "location_tree": ...}
    ...

def _execute_route(params, ctx):
    """Appelle SCTradeClient + calcul tailles boîtes + affiche résultats."""
    # 1. Résoudre from/to → noms reconnus par sc-trade.tools
    # 2. Calculer supportedBoxSizeInScu depuis vaisseau + override --scu
    # 3. Appeler client.trades(...)
    # 4. Post-filtrage --delta si applicable
    # 5. Afficher
    ...

def _calc_box_size(scu_total: int, ship_grids: list[int]) -> int:
    """Retourne la plus grande taille de boîte acceptée par les grilles.
    Exemples de grilles : [32, 32, 8, 8] = ship pouvant prendre des boîtes de 32 SCU.
    Tailles standard SC : 1, 2, 4, 8, 16, 24, 32.
    """
    ...

def _display_route_result(routes: list[dict], params: dict) -> None:
    """Affiche les routes avec étapes dépliées."""
    ...
```

### Mapping paramètres → API sc-trade.tools (`POST /api/tools/trades`)

| Param `/route` | Champ API | Notes |
|---|---|---|
| `--scu` (override) | `supportedBoxSizeInScu` | **Calculé** depuis grilles vaisseau + override SCU total |
| `--saut` | `maxStops` | Transmis tel quel — SC-trade applique ses propres limites |
| `--benef` | `profitType: "profit"` | |
| `--roi` | `profitType: "time"` | Nom API pour ROI |
| `--short`/`--temps` | `profitType: "distance"` | À confirmer avec l'API |
| `--commodity` whitelist | `commodityNamesType: "whitelist"`, `commodityNames: [...]` | |
| `--commodity` blacklist | `commodityNamesType: "blacklist"`, `commodityNames: [...]` | |
| `from` | `origin` | Nom tel que reconnu par sc-trade.tools |
| `to` (whitelist lieux) | `locationNamesType: "whitelist"`, `locationNames: [...]` | À valider avec l'API |
| lieux exclus | `locationNamesType: "blacklist"`, `locationNames: [...]` | |
| `--cycle` | `returnToOrigin: true` | À confirmer si champ API existant |
| `--delta` | — | Post-filtrage côté client |

### Points à investiguer avant de coder

1. **`to` multi-terminaux** : `locationNames` en whitelist force-t-il le passage ou filtre-t-il seulement ? Tester API.
2. **`--cycle`** : champ API `returnToOrigin` ? Ou post-traitement (filtrer routes dont dernier stop = origin) ?
3. **`profitType: "distance"`** : valeur exacte à confirmer.
4. **Tailles de boîtes par terminal** : données disponibles dans l'API UEX/sctrade ? Sinon heuristique.
5. **Retour `route_submit` depuis formulaire** : gérer dans `server.py` comme `scan_edit_submit`.

### Affichage des résultats

```
─── Route 1 — Bénéfice : 48 200 α  ROI : 23%  Distance : 4.2 Gm  [3 escales] ───
  1. Area 18 → Lorville       Agricultural Supp.  96 SCU  +18 400 α  1.8 Gm
  2. Lorville → HDMS-Lathan   Medical Supplies    48 SCU  +29 800 α  2.4 Gm
  3. HDMS-Lathan → Area 18 ↩  (retour à vide)               —        0.8 Gm

─── Route 2 — Bénéfice : 41 500 α  ROI : 18%  Distance : 5.1 Gm  [2 escales] ───
  ...
```

Noms de terminaux annotés comme termes cliquables (vocab).

---

## Périmètre hors-scope (pour l'instant)

- `itinerary` (origin→destination fixe avec détour) : non discuté, ne pas implémenter
- Intégration dans `/voyage` : non utilisé
- Cache des résultats : requête fraîche à chaque appel (pas de TTL)
- Calcul de route offline (sans token sctrade) : hors-scope v1

---

## Ordre d'implémentation suggéré

1. Ajouter `route.rentabilite`, `route.saut`, `route.delta` dans `config.py` + `completer_data.py`
2. Retirer `itinerary()` de `sctrade_client.py`
3. Investiguer l'API (`to`/`cycle`/`profitType`/tailles boîtes) — tester avec token
4. Créer `route.py` : parser + `_execute_route` + affichage basique (sans formulaire)
5. Implémenter `_calc_box_size` et la logique SCU
6. Créer le composant formulaire `route-form-panel` dans `index.html`
7. Connecter `route_form` ↔ `route_submit` dans `server.py`
8. Tests complets avec token Patreon

---

*Document de planification — ne pas supprimer avant fin d'implémentation.*
