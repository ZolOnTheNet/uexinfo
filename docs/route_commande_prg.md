# Planification — commande `/route`

**Date :** 2026-04-22  
**Statut :** À implémenter  
**Priorité :** Haute (remplace l'usage informel de `/trade sctrade`)

---

## Contexte

La commande `/trade sctrade` existe mais n'exploite pas bien sc-trade.tools.
L'endpoint `POST /api/tools/trades` (alias « route » dans le vocabulaire sc-trade.tools)
supporte jusqu'à **5 escales**, un filtre commodités, et plusieurs critères d'optimisation.

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

Sans argument, affiche un petit formulaire dans la console (style scan-inline)
avec tous les champs pré-remplis depuis la config et la position actuelle.
L'utilisateur peut modifier puis valider.

---

## Paramètres détaillés

| Paramètre | Alias | Description | Défaut |
|---|---|---|---|
| `from <terminal>` | — | Terminal de départ | `@local` (ctx.player.location) |
| `to <terminal,...>` | — | Terminal(aux) à visiter | `@dest` si défini, sinon libre |
| `--commodity <n,...>` | `--comm` | Commodités prioritaires (filtre whitelist) | aucun filtre |
| `--scu <n>` | — | Capacité cargo disponible en SCU | vaisseau actif |
| `--cycle` | `-c`, `-b`, `--boucle` | Revenir au point de départ si possible | off |
| `--saut <n>` | `--hop`, `-s`, `-h` | Nombre max d'escales | `route.saut` (défaut 5) |
| `--benef` | — | Optimiser par bénéfice total | selon `route.rentabilite` |
| `--roi` | — | Optimiser par ROI (aUEC/SCU) | selon `route.rentabilite` |
| `--short` | `--temps` | Optimiser par distance/temps | selon `route.rentabilite` |
| `--delta <n>` | — | Distance acceptable (Gm) pour un saut "à vide" rentable | `route.delta` |

### Règles de résolution

- `@local` → `ctx.player.location`
- `@dest` → `ctx.player.destination`
- `to` avec plusieurs terminaux séparés par des virgules ou des espaces
- Si `to` n'est pas fourni et qu'il n'y a pas de `@dest` : route libre depuis `from`
- `--cycle` : si sc-trade.tools ne supporte pas le retour, on l'indique dans le résultat

---

## Options de configuration

```
/config route.rentabilite roi|benef|dist|temp
    Critère d'optimisation par défaut.
    roi   = meilleur retour sur investissement
    benef = bénéfice total maximal
    dist  = route la plus courte (distance)
    temp  = route la plus rapide (pour l'instant = dist)
    Défaut : roi

/config route.saut <n>
    Nombre max d'escales (sauts) par défaut.
    Valeurs acceptées : 1 et +, max 5 (limite API sc-trade.tools).
    Défaut : 5

/config route.delta <n>
    Distance en Gm acceptable pour un transit "à vide" vers un meilleur terminal.
    Exemple : 3.0 = accepte jusqu'à 3 Gm de détour.
    Défaut : 3.0
```

---

## Aide `/help route` (texte à afficher)

```
/route — Calcule une route commerciale optimale via sc-trade.tools

Usage :
  /route                        Formulaire interactif (tous les champs)
  /route [options]              Calcul direct avec options en ligne

Paramètres :
  from <lieu>                   Départ (défaut : @local = position actuelle)
  to <lieu>[,<lieu>...]         Terminaux à visiter (défaut : @dest)
  --commodity <nom>[,<nom>...]  Commodités prioritaires (whitelist)
  --scu <n>                     Cargo disponible en SCU (défaut : vaisseau actif)
  --cycle | -c | --boucle       Revenir au point de départ si possible
  --saut <n> | --hop <n>        Max escales (défaut : config route.saut, max 5)
  --benef                       Optimiser par bénéfice total
  --roi                         Optimiser par ROI (aUEC/SCU)
  --short | --temps             Optimiser par distance/temps
  --delta <n>                   Détour acceptable en Gm pour un meilleur résultat

Exemples :
  /route                                Formulaire avec valeurs courantes
  /route from Area18 --benef --saut 3   3 escales depuis Area18, max bénéfice
  /route to Lorville,HDMS-Lathan --roi  Passage par ces deux terminaux, ROI max
  /route --cycle --scu 96               Boucle, 96 SCU dispo

Configuration :
  /config route.rentabilite roi|benef|dist|temp
  /config route.saut <n>      (défaut : 5)
  /config route.delta <n>     (défaut : 3.0 Gm)

Note : nécessite un token Patreon sc-trade.tools (/config sctrade token <token>).
       Sans token : résultat dégradé ou indisponible.
```

---

## Architecture d'implémentation

### Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---|---|---|
| `uexinfo/cli/commands/route.py` | **Créer** | Handler `/route`, parser args, formulaire inline, appel `SCTradeClient.trades()`, affichage résultat |
| `uexinfo/api/sctrade_client.py` | **Modifier** | Retirer `itinerary()` ; enrichir `trades()` : paramètre `commodity_whitelist` déjà présent, ajouter `destination` optionnel et `return_to_origin` |
| `uexinfo/cli/commands/__init__.py` | **Modifier** | Import du module route |
| `uexinfo/cli/commands/config.py` | **Modifier** | Ajouter `route.rentabilite`, `route.saut`, `route.delta` dans `_DOT_KEYS` |
| `uexinfo/cli/completer_data.py` | **Modifier** | Ajouter SUBS pour `route` et les clés config |
| `docs/commands.md` | **Mettre à jour** | Section `/route` |

### Structure de `route.py`

```python
# ── /route ───────────────────────────────────────────────────────────────────

@register("route")
def cmd_route(args, ctx):
    if not args:
        _show_route_form(ctx)      # formulaire inline
        return
    params = _parse_route_args(args, ctx)
    if params is None:
        return
    _execute_route(params, ctx)


def _parse_route_args(args, ctx) -> dict | None:
    """Parse les arguments et applique les defaults config."""
    ...

def _show_route_form(ctx):
    """Affiche le formulaire inline avec les valeurs actuelles."""
    # Similaire à scan-inline : console.print + envoi d'un message overlay
    # type: "route_form" → index.html affiche un formulaire éditable
    ...

def _execute_route(params, ctx):
    """Appelle SCTradeClient.trades() et affiche les résultats."""
    ...

def _display_route_result(routes, params):
    """Affiche les routes en tableau Rich avec étapes dépliées."""
    # Chaque route : escale 1 → escale 2 → ... → retour ?
    # Colonnes : Escale | Acheter | Vendre | Bénéfice | Dist Gm | ROI
    ...
```

### Mapping paramètres → API sc-trade.tools (`POST /api/tools/trades`)

| Param `/route` | Champ API | Notes |
|---|---|---|
| `--scu` | `supportedBoxSizeInScu` | min(scu, 32) — limite API |
| `--saut` | `maxStops` | max(1, min(n, 5)) |
| `--benef` | `profitType: "profit"` | |
| `--roi` | `profitType: "time"` | c'est le nom API pour ROI |
| `--short`/`--temps` | `profitType: "distance"` | à vérifier avec l'API |
| `--commodity` | `commodityNames`, `commodityNamesType: "whitelist"` | |
| `from` | `origin` | nom du terminal tel que sc-trade.tools le reconnaît |
| `to` | `locationNames` + `locationNamesType: "whitelist"` | à valider avec l'API |
| `--cycle` | ? | À investiguer si l'API supporte le retour à l'origine |
| `--delta` | ? | Pas d'équivalent direct → post-filtrage côté client |

### Points à investiguer avant de coder

1. **`to` multi-terminaux** : est-ce que `locationNames` en whitelist force le passage par ces terminaux, ou c'est un filtre d'exclusion ? À tester avec l'API.
2. **`--cycle`** : l'API a-t-elle un champ `returnToOrigin` ? Sinon post-traitement.
3. **`profitType: "distance"`** : valeur exacte à confirmer (peut être `"distance"` ou autre).
4. **`--delta`** : n'existe pas côté API — post-filtrage : on accepte les résultats dont la distance de chaque saut ≤ `delta` Gm.
5. **Formulaire inline** : réutiliser le mécanisme `scan_log_inline` ou créer un `route_form` générique.

### Affichage des résultats

Chaque route retournée par l'API contient des `stops` (escales). Affichage visé :

```
Route 1 — Bénéfice : 48 200 α  ROI : 23%  Distance : 4.2 Gm  [3 escales]
  1. Area 18 → Lorville       Agricult. Supplies  96 SCU  +18 400 α  1.8 Gm
  2. Lorville → HDMS-Lathan   Medic. Supplies     48 SCU  +29 800 α  2.4 Gm
  3. HDMS-Lathan → Area 18 ↩  (retour à vide)              —         0.8 Gm
```

Les noms de terminaux sont annotés comme termes cliquables (vocab).

---

## Périmètre hors-scope (pour l'instant)

- `itinerary` (origin→destination fixe avec détour) : non discuté, non implémenté
- Intégration dans `/voyage` : le système voyage n'est pas utilisé
- Cache des résultats route : pas de TTL, requête fraîche à chaque appel

---

## Ordre d'implémentation suggéré

1. Ajouter `route.rentabilite`, `route.saut`, `route.delta` dans config + completer
2. Enrichir `SCTradeClient.trades()` si nécessaire (tester l'API `to`/`cycle`)
3. Créer `route.py` : parser + `_execute_route` + affichage basique
4. Ajouter le formulaire inline (`/route` sans args)
5. Tester avec un token Patreon

---

*Document de planification — ne pas supprimer avant fin d'implémentation.*
