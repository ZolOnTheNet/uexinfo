# Plan de refactoring — uexinfo

> **Exécutant** : Vibe via MCP clive  
> **Priorité** : A=critique, B=important, C=nice-to-have

---

## A — Critique

### A1. Trois `_find_terminal` incompatibles

Trois implémentations indépendantes de la même logique :

| Fichier | Fonction | Logique |
|---|---|---|
| `cache/manager.py:272` | `find_terminal(name)` | exact match seul |
| `cli/commands/info.py:1878` | `_find_terminal(query, ctx, strong=bool)` | notation pointée + fuzzy + préfère Admin |
| `cli/commands/sync.py:18` | `_find_terminal(q, ctx)` | exact + LocationIndex + substring |

**Fix** : déplacer la version complète (`info.py`) dans `uexinfo/location/resolve.py` sous `find_terminal(query, ctx, strong=False)`. Mettre à jour les imports dans `go.py`, `trade.py`, `sync.py`, `info.py`.

### A2. Accès direct `ctx._price_cache._mem` dans sync.py

`sync.py:43-53` accède aux internals du cache (`._mem`, `.flush()`). Si `_price_cache` change de structure, ça casse silencieusement.

**Fix** : ajouter méthodes publiques `clear_prefix(prefix)` et `clear_all()` sur la classe du cache. Remplacer les accès directs dans sync.py.

---

## B — Important

### B1. Trois formatters de prix, deux formatters SCU

| Fichier | Fonction | Usage |
|---|---|---|
| `cli/commands/info.py:34` | `_price_fmt(value)` | format complet "1 234" |
| `cli/commands/info.py:41` | `_price_short(val)` | compact "1.2 M." |
| `display/formatter.py:51` | `fmt_auec(value)` | avec unité "1 234 aUEC" |
| `cli/commands/info.py:23` | `_scu(lo, hi)` | plage SCU |
| `display/formatter.py:58` | `fmt_scu(value)` | simple |

**Fix** : déplacer `_price_fmt`, `_price_short` dans `display/formatter.py` (renommer `price_fmt`, `price_short`). Supprimer les doublons. Mettre à jour les imports dans `info.py`, `trade.py`.

### B2. Couplage 17 imports `info.py` → `trade.py`

`trade.py` importe massivement depuis `info.py` : `_abbrev_name`, `_comm_code`, `_ensure_comm_codes`, `_price_short`, `_find_terminal`, `_dot_name`, etc.

**Fix** : extraire les helpers partagés vers `display/commodity.py` (formatage commodité) et `location/resolve.py` (résolution terminal). Découpler les deux commandes.

### B3. `UEXClient()` instancié sans cache dans nav.py et voyage.py

`nav.py:627,846,1443` et `voyage.py:1903` créent `UEXClient()` directement, sans passer par `ctx._price_cache`. Les données ne sont pas mises en cache → appels redondants possibles.

**Fix** : encapsuler dans des fonctions `_fetch_*` passant par `ctx._price_cache`, comme `info.py` le fait avec `_fetch_prices()`.

---

## C — Nice-to-have

### C1. Commandes sans documentation dans /help

| Commande | Fichier |
|---|---|
| `arriver/arrive/arrived` | `go.py:112` |
| `sync/resync` | `sync.py:76` |
| aliases `x/exp` | `explore.py:334` |
| `plan` | documenté dans help.py mais non implémenté |

**Fix** : ajouter les entrées manquantes dans `help.py:_COMMANDS`. Supprimer `plan` si absent.

### C2. `_abbrev_name` et `_comm_code` dans `display/commodity.py`

Ces fonctions sont définies dans `info.py` mais importées par `trade.py`. Les déplacer dans un module partagé évite l'import circulaire potentiel.

---

## Ordre d'exécution recommandé

```
A1 → A2 → B1 → B2 → B3 → C1 → C2
```

Chaque étape doit passer les tests existants (pytest) et ne pas modifier le comportement visible.

---

## Notes pour Vibe

- Ne pas modifier `api/`, `cache/models.py` (contrats publics stables)
- Chaque refactoring = commit séparé avec description claire
- Vérifier que `from uexinfo.cli.commands.info import _price_short` dans trade.py est mis à jour
- `_find_terminal` dans info.py a une logique "strong match" qui doit être préservée
