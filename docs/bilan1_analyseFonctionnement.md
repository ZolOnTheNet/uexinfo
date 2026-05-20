# Bilan fonctionnel — uexinfo

*Analyse du fonctionnement interne : résolution de noms, cycle de vie des données, double traitement, déclenchement réseau, reset, données incomplètes, parallélisation.*

---

## 1. Résolution des noms saisis par l'utilisateur

### 1.1 Deux systèmes distincts

Il existe **deux chemins de résolution** selon le contexte :

| Contexte | Composant | Fichier |
|---|---|---|
| Lieux (planètes, stations, systèmes) | `LocationIndex` | `location/index.py` |
| Terminaux précis (pour les prix) | `CacheManager.find_terminal()` + `_terminal_matches()` | `cache/manager.py`, `cache/data_manager.py` |
| Nœuds graphe de transport (`/nav`) | `_resolve_node()` | `cli/commands/nav.py` |
| Commodités | `CacheManager.find_commodity()` | `cache/manager.py` |

### 1.2 LocationIndex — résolution fuzzy à 3 niveaux

`LocationIndex` est construit à l'initialisation depuis le `CacheManager`. Il indexe :
- **Systèmes** (`StarSystem`) → `full_path = "Stanton"`
- **Planètes** (`Planet`) → `full_path = "Stanton.Hurston"`
- **Terminaux** (dédupliqués par lieu) → `full_path = "Stanton.Hurston.Lorville.Admin"` après nettoyage du préfixe service (`"Admin - ARC-L4"` → `"ARC-L4"`)

**Stratégie de recherche** (`_search_ranked`, `index.py:115`) :

```
1. Préfixe exact (case-insensitive) sur le nom court
2. Sous-chaîne (case-insensitive) sur le nom court
3. Fuzzy : WRatio (rapidfuzz, score ≥ 40) ou difflib (cutoff 0.3) sur les non-trouvés
```

Support de la notation pointée : `"stanton.grim"` restreint d'abord le pool aux entrées dont le `full_path` commence par `"stanton"`, puis cherche `"grim"` dans ce sous-ensemble.

**Ce qui est retourné** : un `LocationEntry` contenant :
- `name` — nom court affiché (`"Lorville"`)
- `type` — `"system"` | `"planet"` | `"terminal"` | …
- `system` — système parent (`"Stanton"`)
- `full_path` — chemin complet pointé (`"Stanton.Hurston.Lorville"`)
- `entity_id` — **ID entier UEX** (utilisé ensuite pour les requêtes API)

### 1.3 Résolution de nœuds transport (`/nav`)

`_resolve_node()` (`nav.py:1368`) suit une logique propre en 4 niveaux car le graphe stocke ses nœuds par nom de lieu (pas par ID UEX) :

```
1. Correspondance exacte (case-insensitive)
2. Préfixe (préférence au plus long — le plus spécifique)
3. Sous-chaîne (préférence au plus long)
4. Fuzzy WRatio ≥ 70 (préférence au plus long)
```

En cas d'échec total, `_auto_add_from_uex()` (`nav.py:1419`) interroge l'API UEX (`get_routes()`) pour peupler le graphe à la volée.

### 1.4 Résolution de terminaux pour les prix

`_terminal_matches()` (`data_manager.py:42`) cherche par :
- nom UEX complet (ex: `"Admin - ARC-L4"`)
- nom court extrait (`"ARC-L4"`)
- `space_station_name`
- ID numérique en chaîne

Retourne une liste ; en cas d'ambiguïté (plusieurs terminaux au même lieu), `canonical_terminal_key()` applique une heuristique : **Admin > TDD > cargo_center > premier trouvé**.

---

## 2. Gestion de la base de données et cycle de vie des données

### 2.1 Deux couches de persistance distinctes

```
~/.uexinfo/                   ← AppData utilisateur (appdirs)
  commodities.json            ← données statiques UEX (TTL 24h, mtime fichier)
  terminals.json
  star_systems.json
  planets.json
  vehicles.json
  price_cache.json            ← PriceCache : prix marché (TTL adaptatif 4h–72h)
  missions.json               ← MissionManager
  voyages.json                ← VoyageManager
  scan_prices.json            ← ScanPriceStore (données joueur, pas d'expiration)
  config.toml

uexinfo/data/                 ← dans le code source (versionnée git)
  transport_network.json      ← graphe de transport (/nav)
```

### 2.2 CacheManager — données statiques

**Cycle de vie** :

```
Démarrage app
  └── load() [manager.py:46]
        ├── load_transport_graph()  ← toujours rechargé depuis le source
        ├── _is_expired("commodities") ? [TTL = mtime fichier > 86400s]
        │     NON → _load_from_disk()  (JSON → dataclasses en mémoire)
        │     OUI → _download()
        │             ├── UEXClient.get_commodities()
        │             ├── UEXClient.get_terminals()
        │             ├── UEXClient.get_star_systems()
        │             ├── UEXClient.get_planets()
        │             └── UEXClient.get_vehicles()
        │           Chaque réponse → _save() (JSON brut) + parse → dataclasses
        └── En cas d'échec téléchargement : fallback disk silencieux (avertissement jaune)
```

**Clé d'expiration** : seul le mtime de `commodities.json` est vérifié — les 5 fichiers sont considérés synchronisés.

**invalidate()** : supprime les 5 fichiers JSON + vide les listes en mémoire. Le graphe de transport n'est **pas** touché.

### 2.3 PriceCache — prix marché

Cache persistant JSON avec TTL **adaptatif** basé sur la fréquence d'usage (fenêtre 7 jours) :

| Fréquence | TTL |
|---|---|
| ≥ 7 requêtes/semaine | 4 h |
| ≥ 3 requêtes/semaine | 12 h |
| ≥ 1 requête/semaine | 24 h |
| < 1 requête/semaine | 72 h |

**Clés "version-taguées"** (`cs_`, `rd_`, `vp_`, `vr_`) : pas de TTL temporel, expirent uniquement si `game_version != SC_VERSION` (constante `"4.6"` dans `price_cache.py:29`). Typiquement : tailles de cargo, distances, vaisseaux.

**Chargement paresseux** : le fichier JSON n'est lu qu'au premier accès (`_ensure_loaded()`). Flush sur disque : immédiat après écriture (`_save()`), différé pour les lectures (`_dirty = True`).

### 2.4 Graphe de transport

Stocké dans `uexinfo/data/transport_network.json` (dans le dépôt git). Chargé à chaque démarrage, **jamais effacé par `/refresh`**. Sauvegarde explicite via `/nav save` ou `/nav populate`, avec écriture atomique par fichier temporaire + `os.replace()`.

---

## 3. Ce qui est traité de deux façons différentes

### 3.1 Données fraîches vs données périmées (mode offline)

`DataManager.fetch_prices()` (`data_manager.py:131`) implémente une chaîne de fallback :

```
1. PriceCache.get(key)          → fraîches (TTL OK)         Source.API   [cyan]
2. UEXClient.get_prices(...)    → appel réseau réel          Source.API   [cyan]
3. PriceCache.get_stale(key)    → périmées (API inaccessible) Source.STALE [orange]
4. []                           → aucune donnée             Source.EMPTY  [rouge]
```

Le flag `ctx._api_offline` est positionné à `True` dès qu'on tombe en fallback stale, ce qui modifie l'affichage.

### 3.2 Données temporelles vs données version-spécifiques

Dans `PriceCache._is_valid()` :
- **Prix marché** → expiration par TTL adaptatif (temps réel)
- **cs_\*, rd_\*, vp_\*, vr_\*** → expiration par changement de version SC uniquement

Ces deux logiques coexistent dans le même store JSON, distinguées uniquement par le préfixe de clé.

### 3.3 Données UEX officielles vs données inférées dans le graphe

Le graphe de transport attribue une priorité à chaque arête selon sa source :

| Source | Priorité | Signification |
|---|---|---|
| `manual` | 3 | Entré par l'utilisateur |
| `uex` | 2 | Route API officielle UEX |
| `calculated` | 1 | Calculé géométriquement |
| `consolidated` | 0 | Co-localisation inférée |

Source plus haute priorité remplace la précédente. Même priorité → timestamp plus récent gagne.

### 3.4 Scan joueur vs prix UEX

`DataManager.terminal_prices()` fusionne deux sources :
- **Prix UEX** (API ou cache) — source de base
- **Scan joueur** (`ScanPriceStore`) — prioritaires, écrasent les données UEX

Le scan est tagué `Source.SCAN` et affiché en vert. La migration automatique de clés (`_migrate_store_key`) normalise les anciennes clés `"name:xxx"` vers l'ID numérique.

### 3.5 Résolution de terminaux — clé unique vs clés multiples

- `canonical_terminal_key()` → **une seule clé** (pour écriture d'un scan)
- `all_terminal_keys()` → **toutes les clés** d'un lieu (pour lecture agrégée de scans multiples)

---

## 4. Quand une lecture déclenche une requête réseau

### 4.1 Données statiques

Une requête UEX est lancée si :
- Fichier `commodities.json` absent ou mtime > 24h
- `/refresh` (ou `/refresh all` / `/refresh static`) est explicitement appelé
- `CacheManager.load(force=True)` est invoqué

### 4.2 Prix

Une requête API `get_prices()` est lancée si :
- La clé n'est pas dans `PriceCache` (première consultation)
- La clé est dans `PriceCache` mais TTL dépassé (adaptatif 4h–72h)
- La clé est version-taguée et `game_version` ne correspond plus

Cas où la requête **n'est pas** lancée : clé présente et valide → retour cache immédiat.

### 4.3 Distances (`/nav`)

`_fetch_missing_distances()` (`nav.py`) lance des appels `get_routes()` lorsqu'un nœud graphe est trouvé mais ses distances ne sont pas connues. `/nav populate` boucle sur toutes les commodités achetables et fait autant de requêtes `get_routes()`.

### 4.4 sc-trade.tools (Phase 4 — non encore opérationnel)

Prévu : requête HTTP vers sc-trade.tools pour obtenir des listings de prix alternatifs, stockés sous clé `"sct_listings"` dans `PriceCache`. Actuellement : stub `sctrade` dans `/refresh` uniquement.

---

## 5. Comportement de la base de données lors d'un reset

### 5.1 Ce que `/refresh` efface selon l'option

| Option | Effacé | Conservé |
|---|---|---|
| `all` / `static` | 5 fichiers JSON statiques + mémoire | `price_cache.json`, scans, missions, voyages, graphe, config |
| `prices` | Tout `price_cache.json` (mémoire + disque) | Statiques, scans, missions, voyages, graphe, config |
| `sctrade` | Clé `"sct_listings"` seulement | Tout le reste |
| `status` | Rien (lecture seule) | — |

### 5.2 Ce qui n'est jamais effacé par `/refresh`

- `config.toml` — paramètres utilisateur
- `scan_prices.json` — prix scannés par le joueur (source la plus fiable)
- `missions.json` et `voyages.json` — historique missions/voyages
- `transport_network.json` — graphe de transport (effaçable seulement manuellement ou via `/nav reset`)

### 5.3 Reconstruction de l'index après refresh

`_refresh_static()` (`refresh.py:53`) appelle `load(force=True)` puis reconstruit explicitement `ctx.location_index = LocationIndex(ctx.cache)`. Sans cette ligne, les recherches fuzzy retourneraient les anciens résultats.

---

## 6. Requêtes envisagées pour les données actuellement incomplètes

### 6.1 Données manquantes identifiées

| Donnée | État actuel | Lacune |
|---|---|---|
| Tailles de cargo vaisseau | `container_sizes` dans Vehicle (ex: `"1/2/4/8/16/32"`) | Format brut, pas normalisé à l'affichage dans tous les contextes |
| Distances entre nœuds non UEX | Inférées par consolidation géographique | Approximatives, marquées `"estimated"` |
| Prix sc-trade.tools | Stub uniquement | Endpoint HTML non scrappé |
| Détails raffinerie | `is_refinable` présent mais pas les chaînes de raffinage | Pas d'endpoint UEX dédié |
| Disponibilité temps réel | `is_available` champ binaire | Pas de signal d'ouverture/fermeture dynamique |

### 6.2 Requêtes UEX envisagées (Phase 2–3)

- **`/commodities_prices?id_commodity=X`** — prix de toutes les stations pour une commodité (utilisé dans `/trade best`)
- **`/commodities_routes?id_terminal=X&id_commodity=Y`** — routes depuis un terminal (utilisé dans `/nav`)
- **`/commodities_routes?id_terminal_origin=X`** — toutes les routes depuis un terminal (peuplement graphe)

### 6.3 Requêtes sc-trade.tools envisagées (Phase 4)

Scraping prévu de `sc-trade.tools/trade` :
- Listings complets de prix (alternative à UEX, souvent plus frais)
- Données de profitabilité de routes calculées par le site
- Stockage sous préfixe `sct_` dans `PriceCache`

### 6.4 Correction rétroactive des nœuds estimés

Quand un nœud `"estimated"` ou `"consolidated"` reçoit une distance `"uex"` officielle via un appel API ultérieur, la logique de priorité du graphe (`source_priority`) remplace automatiquement l'estimation par la valeur officielle. Le nœud est mis à jour in-place via `add_or_update_route()`.

---

## 7. Parallélisation et correction rétroactive

### 7.1 Goulots d'étranglement séquentiels actuels

| Endroit | Opération | Séquentialité actuelle | Impact |
|---|---|---|---|
| `_download()` — `manager.py:105` | 5 fetches statiques (commodités, terminaux, systèmes, planètes, vaisseaux) | Boucle for séquentielle | ~5 requêtes × latence UEX |
| `/nav populate` — `nav.py:897` | 1 requête `get_routes()` par commodité achetable (~88) | Boucle for séquentielle | 88 requêtes × latence — principal bottleneck |
| `terminal_prices()` — `data_manager.py:169` | 4 tentatives de clés (id → code → loc → slug) | Séquentielles, s'arrêtent au premier résultat | Jusqu'à 4 requêtes si toutes ratent |
| `/nav` calcul distances — `nav.py:651` | Fetch distances pour 5 terminaux max | Boucle for séquentielle | 5 requêtes × latence |

### 7.2 Parallelisation proposée

**a) Téléchargement statique**

```python
# manager.py _download() — remplacement de la boucle for
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(fetch_fn): (key, label, parse_fn)
        for key, label, fetch_fn, parse_fn in steps
    }
    for future in as_completed(futures):
        key, label, parse_fn = futures[future]
        raw = future.result()
        # ... parse + save
```
Gain estimé : 5x sur la durée de `/refresh static`.

**b) Peuplement du graphe (`/nav populate`)**

```python
# nav.py _populate_graph()
with ThreadPoolExecutor(max_workers=8) as executor:
    futs = {executor.submit(client.get_routes, id_commodity=c.id): c for c in buyable}
    for future in as_completed(futs):
        routes = future.result()
        # intégration dans le graphe (thread-safe si verrouillé)
```
Gain estimé : 8–10x. Attention : nécessite un lock sur `transport_graph.add_or_update_route()`.

**c) Fallback prix terminal**

Actuellement séquentiel (id → code → loc → slug). En mode offline, les 4 tentatives sont lancées séquentiellement même si elles vont toutes échouer. Suggestion : lancer les 4 en parallèle et prendre le premier résultat non vide.

### 7.3 Principe de correction rétroactive

Le graphe de transport implémente déjà un mécanisme de correction rétroactive implicite via `source_priority`. Voici son extension potentielle :

**Correction d'un nœud estimé par données UEX ultérieures :**

```
État initial :
  CRU-L2 → (source="estimated", dist_to_Crusader=1.2 Gm)

Appel /nav populate plus tard :
  get_routes(id_commodity=42) retourne une route via CRU-L2
  add_or_update_route(CRU-L2, ..., source="uex")
  → source_priority["uex"]=2 > source_priority["estimated"]=0
  → distance mise à jour, source="uex"
  → nœud n'est plus affiché en "[dim]estim.[/dim]" mais en "[cyan]uex[/cyan]"
```

**Proposition — scan rétroactif :**
Quand un utilisateur confirme un scan à un terminal dont la distance était `estimated`, le système pourrait proposer d'appeler `get_routes()` pour ce terminal et corriger toutes les routes estimées le concernant. Ce serait déclenché automatiquement dans `ScanPriceStore.save_scan()` si le terminal correspondant est `estimated` dans le graphe.

**Proposition — propagation de correction :**
Un nœud co-localisé (même `full_path`) ayant sa distance corrigée pourrait propager la correction à ses voisins consolidés si la tolérance `tolerance_gm` est respectée. Cela consoliderait automatiquement des nœuds de même lieu qui avaient été inférés séparément.

---

## Synthèse

| Question | Réponse courte |
|---|---|
| Nom saisi → quoi ? | `LocationEntry` avec `entity_id` (ID UEX entier) |
| Résolution en N étapes ? | 3 (préfixe → sous-chaîne → fuzzy) pour lieux ; 4 pour nœuds graphe |
| TTL statique ? | 24h basé sur mtime fichier |
| TTL prix ? | Adaptatif 4h–72h ; version-tagué = jamais |
| Deux traitements différents | Prix fraîches/périmées ; version-tagué/TTL ; UEX/inféré ; joueur/API |
| Requête réseau déclenchée quand ? | Cache absent ou expiré, ou `/refresh` explicite |
| Reset efface quoi ? | Données statiques OU prix marché — jamais scans ni graphe ni config |
| Données incomplètes | Distances estimées, sc-trade.tools non scrappé, chaînes raffinerie |
| Parallélisable | Téléchargement statique (5x), populate graphe (8–10x), fallback prix |
| Correction rétroactive | Déjà présente via `source_priority` ; extensible au scan → corrige nœuds estimés |
