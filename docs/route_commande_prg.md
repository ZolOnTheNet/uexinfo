# Planification — commande `/route`

**Date :** 2026-04-22 (v3 — corrections utilisateur 22/04 après-midi)  
**Statut :** À implémenter  
**Priorité :** Haute (remplace l'usage informel de `/trade sctrade`)

---

## Contexte

La commande `/trade sctrade` existe mais n'exploite pas bien sc-trade.tools.
L'endpoint `POST /api/tools/trades` supporte plusieurs escales par appel,
mais uexinfo gérera lui-même le chaînage de plusieurs appels pour dépasser
la limite interne de l'API (voir section « Gestion des sauts »).

L'endpoint `itinerary` n'est **pas** dans le périmètre de cette commande.

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

Sans argument, affiche un formulaire interactif dans l'overlay (voir section UI)
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
| `--saut <n>` | `--hop`, `-s`, `-h` | Nombre max d'escales (géré par uexinfo) | `route.saut` (défaut 5) |
| `--benef` | — | Optimiser par bénéfice total | selon `route.rentabilite` |
| `--roi` | — | Optimiser par ROI (aUEC/SCU) | selon `route.rentabilite` |
| `--short` | `--temps` | Optimiser par distance/temps | selon `route.rentabilite` |
| `--delta <n>` | — | Détour acceptable en Gm pour un meilleur résultat | `route.delta` |

### Règles de résolution

- `@local` → `ctx.player.location`
- `@dest` → `ctx.player.destination`
- `to` : plusieurs terminaux séparés par virgules ou espaces
- Si `to` absent et `@dest` absent : route libre depuis `from`
- `--cycle` : si l'API ne supporte pas nativement le retour, post-traitement

---

## Gestion des sauts — appels multiples

**uexinfo n'impose aucun plafond sur `--saut`.** C'est uexinfo qui gère le découpage :

- Si `--saut` ≤ limite API : un seul appel `POST /api/tools/trades`
- Si `--saut` > limite API : uexinfo chaîne plusieurs appels :
  1. Appel 1 : `from` = départ, `maxStops` = limite API → retourne les meilleures escales
  2. Le dernier terminal de la meilleure route devient `from` pour l'appel suivant
  3. Répéter jusqu'à atteindre le nombre de sauts demandé ou l'arrivée forcée
  4. Assembler les tronçons en une route complète et calculer les totaux

Variante alternative : si sc-trade.tools ne donne pas de résultats utiles au-delà
de N sauts, basculer sur l'algorithme interne uexinfo (graphe + distances UEX).
Ce point est à trancher à l'implémentation selon la qualité des résultats API.

---

## Annulation / arrêt

**Double-Esc** pendant l'exécution (potentiellement longue si chaînage) :
- Popup : **« Arrêter ici et garder les résultats »** ou **« Annuler »**
- Arrêt : affiche les résultats partiels du dernier appel terminé
- Annulation : retour au prompt sans affichage

---

## Gestion du cargo et des tailles de boîtes SCU

### Distinction `--scu` vs `supportedBoxSizeInScu`

| Concept | Description |
|---|---|
| `--scu <n>` | Override rapide : « j'ai N SCU disponibles » (remplace vaisseau actif) |
| `supportedBoxSizeInScu` | Plus grande taille de boîte acceptée par les grilles (calculé par uexinfo) |

### Tailles de boîtes standard SC

`1 / 2 / 4 / 8 / 16 / 24 / 32 SCU` — les commodités ne se vendent qu'en boîtes de ces tailles.

### Ce que uexinfo calcule pour chaque leg de route

1. Tailles de boîtes disponibles au terminal d'achat et au terminal de vente
2. Grilles cargo du vaisseau (ou override `--scu`) → plus grande boîte admissible
3. Combinaison optimale de boîtes pour remplir les grilles **au maximum**
4. Si tailles incompatibles entre achat et vente : avertir, proposer la meilleure approche

### Combinaison multi-taille vs taille unique

En SC, charger **plusieurs tailles de boîtes simultanément prend plus de temps**,
car il faut attendre que les plus grandes soient chargées avant de compléter avec
les petites. Exemple :
- `16 SCU × 20 boîtes = 320 SCU` → ~14 min de chargement
- `8 SCU × 10 boîtes = 80 SCU`  → ~8 min supplémentaires
- Total multi-taille = ~22 min vs taille unique = ~14 min

**`--short` / `--temps`** : ne désactive **pas** le choix du SCU — désactive l'optimisation
**multi-taille**. En mode distance/temps, uexinfo choisit **une seule taille de boîte**
(la plus grande compatible) pour minimiser le temps de chargement, plutôt que de
combiner plusieurs tailles pour maximiser le remplissage.

**Autres modes** (`--roi`, `--benef`) : combinaison multi-taille autorisée pour
maximiser le cargo chargé.

### Source des données tailles

- Vaisseau : grilles cargo depuis `ctx.player.ships` (modèle `Ship`, champ `cargo_grids`)
- Terminal : à investiguer dans l'API UEX / sc-trade.tools (données box sizes par terminal)

---

## Options de configuration

```
/config route.rentabilite roi|benef|dist|temp
    Critère d'optimisation par défaut.
    roi   = meilleur retour sur investissement (aUEC/SCU)
    benef = bénéfice total maximal
    dist  = route la plus courte (distance Gm)
    temp  = route la plus rapide (= dist pour l'instant)
    Défaut : roi

/config route.saut <n>
    Nombre max d'escales par défaut (≥1, pas de maximum imposé par uexinfo).
    Uexinfo chaîne les appels API si n dépasse la limite interne de sc-trade.tools.
    Défaut : 5

/config route.delta <n>
    Distance en Gm acceptable pour un transit "à vide" vers un meilleur terminal.
    Exemple : 3.0 = accepte jusqu'à 3 Gm de détour.
    Défaut : 3.0
```

---

## Format d'affichage des résultats

### Format par leg (une ligne par trajet achat → vente)

Exemple réel fourni par l'utilisateur :

```
Waste  229α (4j) | HURL-5 → Everus Harbor | 450α (3j) | 13 Gm |
  512 SCU dispo  | 16-32 SCU demandables   | ×16 boîtes 32 SCU |
  +221α/SCU      | achat 117 248α          | vente 230 400α     | +113k α total
```

### Décodage des champs

| Champ | Exemple | Signification |
|---|---|---|
| Commodité | `Waste` | Nom de la commodité |
| Prix achat | `229α (4j)` | Prix unitaire aUEC/SCU, fraîcheur données (4 jours) |
| Route leg | `HURL-5 → Everus Harbor` | Terminal achat → terminal vente |
| Prix vente | `450α (3j)` | Prix unitaire aUEC/SCU, fraîcheur données (3 jours) |
| Distance | `13 Gm` | Distance QT entre les deux terminaux |
| SCU dispo | `512 SCU` | Stock connu disponible à l'achat |
| SCU demandables | `16-32` | Tailles de boîtes proposées par ce terminal |
| Formule SCU | `16×32 SCU` | Plan de chargement optimal (16 boîtes de 32 SCU) |
| Bénéfice/SCU | `+221α/SCU` | Marge unitaire (vente - achat) |
| Achat total | `117 248α` | 229 × 512 SCU |
| Vente total | `230 400α` | 450 × 512 SCU |
| Bénéfice total | `+113k α` | Profit net de ce leg |

### Format de résumé d'une route complète (multi-legs)

```
── Route 1 ── ROI 23%  +113k α  4.2 Gm total  [2 escales] ────────────────
  Leg 1 : Waste  229α(4j) | HURL-5 → Everus Harbor  450α(3j) | 13 Gm
          512 dispo · 16×32 SCU · +221α/scu · achat 117k · vente 230k · +113k
  Leg 2 : Stims  180α(1j) | Everus Harbor → Area 18  340α(2j) | 8 Gm
           64 dispo · 8×8 SCU  · +160α/scu · achat  11k · vente  22k · +10k
  Total : 2 legs · 21 Gm · achat 128k · vente 252k · +123k α
────────────────────────────────────────────────────────────────────────────
```

### Fraîcheur des données

`(Xj)` = données vieilles de X jours. Couleur :
- ≤1j : vert (frais)
- 2-3j : jaune (correct)
- ≥4j : orange/rouge (à vérifier en jeu)

---

## Formulaire inline — UI overlay

### Structure

```
┌─ Route commerciale ──────────────────────────────────────────────────┐
│  Départ     : [Area 18              ▾]   (autocomplete @local)       │
│  Arrivée    : [                     ▾]   (optionnel, multi-valeurs)  │
│  Cargo      : [96] SCU   Vaisseau : [Freelancer MAX         ▾]       │
│  Escales    : [5 ] max   Retour   : [☐] boucle                       │
│  Critère    : (●) ROI  (○) Bénéfice  (○) Distance/Temps             │
│  Delta      : [3.0] Gm   Multi-SCU : [☑] (décocher en mode temps)   │
│                                                                       │
│  ┌─ Commodités ─────────────────┐  ┌─ Lieux ───────────────────────┐ │
│  │ [Aucun filtre ▾]             │  │ [Aucun filtre ▾]              │ │
│  │   → Seulement / Exclure      │  │   → Seulement / Exclure       │ │
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

- **Hiérarchique** : catégorie→commodité ; système→station→terminal
- **Toggle filtre** : `[Aucun filtre ▾]` → bascule entre Aucun / Seulement / Exclure
- **Sélection multiple** par cases à cocher
- **Clic catégorie** = cocher/décocher tous les enfants
- **Multi-SCU** : case cochée par défaut, automatiquement décochée si critère = Temps

### Message WebSocket `route_form` → `route_submit`

```json
{
  "type": "route_form",
  "params": {
    "from": "Area 18", "to": [], "scu": 96, "ship": "Freelancer MAX",
    "saut": 5, "cycle": false, "critere": "roi", "delta": 3.0,
    "multi_scu": true,
    "commodity_filter": { "mode": "none", "items": [] },
    "location_filter":  { "mode": "none", "items": [] }
  },
  "commodity_tree": [{ "category": "Minéraux", "items": ["Aluminium", ...] }, ...],
  "location_tree":  [{ "system": "Stanton", "stations": [
    { "name": "Lorville", "terminals": ["Admin - Lorville", ...] }
  ]}, ...]
}
```

---

## Architecture d'implémentation

### Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---|---|---|
| `uexinfo/cli/commands/route.py` | **Créer** | Handler, parser, chaînage appels, `_calc_box_plan`, affichage |
| `uexinfo/api/sctrade_client.py` | **Modifier** | Retirer `itinerary()` ; enrichir `trades()` |
| `uexinfo/cli/commands/__init__.py` | **Modifier** | Import module route |
| `uexinfo/cli/commands/config.py` | **Modifier** | `route.rentabilite`, `route.saut`, `route.delta` dans `_DOT_KEYS` |
| `uexinfo/cli/completer_data.py` | **Modifier** | SUBS `route` + clés config |
| `uexinfo/overlay/static/index.html` | **Modifier** | Composant `route-form-panel`, `route_form`/`route_submit` |
| `uexinfo/overlay/server.py` | **Modifier** | Handler `route_submit` → déclenche `_execute_route` |

### Structure de `route.py`

```python
@register("route")
def cmd_route(args, ctx):
    if not args:
        _send_route_form(ctx)
        return
    params = _parse_route_args(args, ctx)
    if params:
        _execute_route(params, ctx)


def _execute_route(params, ctx):
    """Chaîne les appels API pour couvrir params['saut'] escales."""
    remaining = params['saut']
    current_from = params['from']
    all_legs = []
    while remaining > 0:
        batch = min(remaining, API_MAX_STOPS)
        routes = client.trades(origin=current_from, maxStops=batch, ...)
        best = _pick_best_route(routes, params['critere'])
        if not best:
            break
        all_legs.extend(best['stops'])
        current_from = best['stops'][-1]['terminal']
        remaining -= batch
        if params.get('to') and current_from in params['to']:
            break
    _display_route_result(all_legs, params)


def _calc_box_plan(
    scu_total: int,
    ship_grids: list[int],
    available_sizes: list[int],
    multi_scu: bool,
) -> list[tuple[int, int]]:
    """Retourne [(taille_boite, nb_boites), ...] pour maximiser le chargement.
    Si multi_scu=False : une seule taille (la plus grande compatible).
    """
    ...
```

### Mapping paramètres → API

| Param `/route` | Champ API | Notes |
|---|---|---|
| `--scu` (override) | `supportedBoxSizeInScu` | Calculé via `_calc_box_plan` |
| `--saut` (batch) | `maxStops` | Découpé par uexinfo si > limite API |
| `--benef` | `profitType: "profit"` | |
| `--roi` | `profitType: "time"` | Nom API pour ROI |
| `--short`/`--temps` | `profitType: "distance"` | À confirmer |
| `--commodity` whitelist | `commodityNamesType:"whitelist"`, `commodityNames:[...]` | |
| `from` | `origin` | Résolu vers nom sc-trade.tools |
| `to` whitelist | `locationNamesType:"whitelist"`, `locationNames:[...]` | À valider API |
| `--cycle` | `returnToOrigin: true` | À confirmer si champ API |
| `--delta` | — | Post-filtrage côté client |

### Points à investiguer avant de coder

1. **`to` multi-terminaux** : `locationNames` whitelist = forcer le passage ou filtrer ?
2. **`--cycle`** : champ API dédié ou post-traitement ?
3. **`profitType: "distance"`** : valeur exacte à confirmer
4. **Tailles boîtes par terminal** : disponibles dans l'API UEX/sctrade ?
5. **`API_MAX_STOPS`** : quelle est la vraie limite interne de sc-trade.tools ?

---

## Périmètre hors-scope

- `itinerary` : non implémenté
- Cache des résultats route
- Calcul offline (sans token)

---

## Ordre d'implémentation

1. Config + completer (`route.rentabilite`, `route.saut`, `route.delta`)
2. Retirer `itinerary()` de `sctrade_client.py`
3. Investiguer API (points 1-5 ci-dessus)
4. `route.py` : parser + appel simple + affichage basique
5. `_calc_box_plan` + logique SCU multi-taille
6. Chaînage multi-appels pour `--saut` > limite API
7. Formulaire `route-form-panel` overlay
8. Tests avec token Patreon

---

*Document de planification — ne pas supprimer avant fin d'implémentation.*
