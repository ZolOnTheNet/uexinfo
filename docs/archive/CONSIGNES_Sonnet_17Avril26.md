# CONSIGNES — Revue de code et plan de tests
**Date :** 17 avril 2026 — Claude Sonnet 4.6

---

## 1. Architecture cible

UEXInfo est un **overlay in-game** (PyWebView + WebSocket) qui émule un CLI :
le joueur tape une commande, le résultat s'affiche dessous en HTML/JS réactif.

```
┌──────────────────────────────────────────────────┐
│  Overlay PyWebView (frameless, transparent)       │
│  ┌──────────────────────────────────────────────┐ │
│  │  Zone de sortie (HTML/ANSI→HTML réactif)     │ │
│  │  - Mots cliquables (info, menu contextuel)   │ │
│  │  - Boutons d'action injectés dynamiquement   │ │
│  │  - Code couleur par source de données        │ │
│  ├──────────────────────────────────────────────┤ │
│  │  Barre de saisie + complétion inline/dropdown│ │
│  │  Ctrl+Espace = assistance contextuelle       │ │
│  ├──────────────────────────────────────────────┤ │
│  │  Barre de statut (pos, ship, dest, missions) │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### Principes fondamentaux

1. **Émulation CLI** — commande → résultat dessous, pas de navigation de pages
2. **Interface évoluée** — boutons d'action, menus contextuels, formulaires inline
3. **Assistance à la saisie** — Ctrl+Espace = aide/complétion contextuelle
4. **Tout est HTML/JS** — pas de post-traitement ANSI côté Python pour l'affichage final
5. **Données multi-sources** — UEX Corp (cyan), sc-trade.tools (orange), scan joueur (vert ★)
6. **Cache intelligent** — TTL adaptatif, fallback sur cache périmé, scan joueur prioritaire
7. **Nommage approximatif** — `new_babbage` = `new babbage` = `stanton.microtech.new_babbage`

---

## 2. Constats de la revue de code

### 2.1 Aide multi-niveaux — PARTIEL

**État actuel :**
- `/cmd help` → redirigé vers `/help cmd` (via dispatcher, `__init__.py:22-25`) ✓
- `/help cmd subcmd` → lookup dans `_DETAILS["cmd subcmd"]` ✓
- Mais **`/cmd subcmd help`** n'est PAS géré uniformément :
  - Seul `/voyage calc help` le fait (voyage.py:81)
  - Les autres commandes ignorent `help` en position finale

**Consigne :**
- Le dispatcher doit aussi intercepter `args[-1] == "help"` et rediriger :
  `/trade sell help` → `/help trade sell`
- Chaque commande doit au minimum reconnaître `help`/`aide`/`?` en dernière position d'args
- Les sous-commandes manquantes dans `_DETAILS` doivent être ajoutées (trade buy, trade sell, nav route, etc.)

### 2.2 Gestion des espaces — CORRECT mais fragile

**État actuel :**
- `shlex.split(posix=False)` découpe les arguments ✓
- Chaque commande reconstruit via `" ".join(args[n:])` ✓
- `replace("_", " ")` appliqué partout ✓

**Consigne :**
- La reconstruction `" ".join()` est dupliquée dans chaque commande — factoriser dans un helper
- Les arguments entre guillemets (`"Port Tressler"`) sont supportés via shlex ✓
- Le stockage utilise les espaces (pas les underscores) ✓

### 2.3 Système de désignation (nommage pointé) — PARTIEL

**État actuel :**
- `LocationIndex.search()` supporte la notation pointée (`stanton.grim`) ✓
- Underscore → espace partout ✓
- Prefixe → correspondance exacte seulement (pas fuzzy sur le préfixe)
- `@local`, `@dest` → expansion dans nav/route/player ✓

**Limites identifiées :**
- `stanton.new_babbage` cherche le préfixe `stanton` exact, puis fuzzy sur `new_babbage` ✓
- Mais `babbage.admin` ne fonctionne PAS (pas de recherche inversée service→location)
- Le terminal Admin/TDD est préféré par `_trading_priority()` dans info.py ✓
- `MFR_ABBREV` dans completer_data.py est incomplet (manque consolidated, etc.)

**Consigne :**
- Le système pointé doit permettre de résoudre dans les deux sens :
  `new_babbage.admin` = `admin.new_babbage` = `stanton.microtech.new_babbage`
- Par défaut, sans précision de service, c'est Admin ou TDD qui est retourné
- Ajouter les abréviations manquantes dans `MFR_ABBREV`

### 2.4 Couche données — FONCTIONNELLE mais dispersée

**État actuel :**
- Cache statique 24h (CacheManager) ✓
- Cache prix adaptatif 4h-72h (PriceCache) ✓
- Fallback : API → cache périmé → scan joueur ✓
- Code couleur : cyan (UEX), orange (sc-trade/cache offline), vert ★ (scan joueur) ✓

**Problèmes :**
- `_fetch_prices()` est dupliquée/dispersée dans info.py — pas de DataManager centralisé
- `ctx._api_offline` est géré manuellement dans des emplacements épars
- SCTradeClient n'est PAS intégré dans la chaîne de fallback
- Pas de retry/circuit breaker
- `SC_VERSION = "4.6"` codé en dur

**Consigne :**
- Créer un `DataManager` qui encapsule : UEXClient + SCTradeClient + PriceCache + ScanPriceStore
- Le DataManager gère l'état offline et les fallbacks de manière centralisée
- Le code couleur est déterminé par la source effective, pas par le command handler

### 2.5 Frontend (index.html) — FONCTIONNEL, monolithique

**État actuel :**
- ANSI→HTML complet (16 couleurs + 256 + RGB) ✓
- Complétion inline + dropdown (Tab, Ctrl+Espace, debounce 250ms) ✓
- Boutons d'action injectés (trade pick, terminal buy, mission, voyage) ✓
- Historique : 200 en JS, 500 sur disque — **incohérence**

**Problèmes :**
- Fichier monolithique de 3500 lignes (HTML + CSS + JS)
- Ctrl+Espace fait la même chose que Tab — pas d'assistance contextuelle distincte
- L'historique n'est pas configurable par le joueur
- Pas de stockage des résultats des N dernières commandes

**Consigne :**
- **Historique configurable** : `/config cmdhistory <n>` pour définir le nombre de commandes+résultats conservés (défaut 5)
- **Ctrl+Espace** doit afficher une aide contextuelle (pas juste la complétion) :
  - Si le champ est vide → liste des commandes avec description
  - Si une commande est tapée → aide de cette commande + sous-commandes
  - Si une sous-commande est tapée → aide spécifique
- Envisager à terme de séparer le JS dans un fichier dédié

### 2.6 Server WebSocket (server.py) — FONCTIONNEL, complexe

**État actuel :**
- Exécution des commandes dans un thread executor ✓
- Streaming de la sortie par chunks de 400ms ✓
- Annulation par double-Esc ✓
- Gestion de la complétion côté serveur ✓

**Problèmes :**
- 1554 lignes — très dense
- Shutdown brutal via `os._exit(0)` — risque de perte de données
- La logique de complétion (1114-1266) devrait être dans un module séparé

**Consigne :**
- Extraire la logique de complétion dans un module `overlay/completer.py`
- Implémenter un shutdown gracieux (flush des caches avant exit)

### 2.7 Sortie tout-HTML — À AMÉLIORER

**État actuel :**
- La sortie des commandes passe par Rich (Python) → ANSI → conversion HTML côté JS
- Certains éléments sont déjà en HTML natif (missions, voyage calc)

**Consigne :**
- À terme, éliminer le double-encodage ANSI→HTML
- Les commandes devraient produire directement du HTML structuré
- Le parser ANSI→HTML (index.html:1145-1225) reste en fallback pour la rétrocompatibilité
- Les boutons d'action, tableaux interactifs, formulaires doivent être en HTML natif dès la source

---

## 3. Plans de test fonctionnels

### TEST-01 : Aide à tous les niveaux

**Objectif :** Vérifier que l'aide fonctionne à chaque profondeur de commande.

| # | Saisie | Résultat attendu |
|---|--------|-------------------|
| 1 | `/help` | Liste de toutes les commandes avec description |
| 2 | `/help trade` | Aide détaillée de `/trade` |
| 3 | `/help trade buy` | Aide spécifique de `/trade buy` |
| 4 | `/trade help` | Même résultat que `/help trade` |
| 5 | `/trade buy help` | Même résultat que `/help trade buy` |
| 6 | `/trade sell help` | Aide spécifique de `/trade sell` |
| 7 | `/mission help` | Aide de `/mission` |
| 8 | `/mission scan help` | Aide de `/mission scan` |
| 9 | `/config help` | Aide de `/config` |
| 10 | `/config ship help` | Aide de `/config ship` |
| 11 | `/nav route help` | Aide de `/nav route` |
| 12 | `/help inexistant` | Message "Pas d'aide pour « inexistant »" |

**Statut actuel :** Tests 4 passent (dispatcher redirect). Tests 5, 6, 8, 10, 11 échouent (pas de détection de `help` en position finale d'args).

### TEST-02 : Assistance contextuelle à la saisie (Ctrl+Espace)

**Objectif :** Vérifier que Ctrl+Espace fournit une aide adaptée au contexte de saisie.

| # | Contenu du champ | Ctrl+Espace → résultat attendu |
|---|------------------|--------------------------------|
| 1 | *(vide)* | Liste des commandes principales avec description courte |
| 2 | `/trade` | Sous-commandes de trade (buy, sell, best, compare, from, to) |
| 3 | `/trade buy` | "Commodité attendue" + liste des commodités |
| 4 | `/go to` | "Terminal attendu" + liste des terminaux |
| 5 | `/info` | Types disponibles (terminal, commodity, ship) + recherche libre |
| 6 | `/ship` | Sous-commandes (list, add, set, cargo, remove) |
| 7 | `/config` | Sous-commandes (ship, trade, cache, scan, clock, hotkey) |
| 8 | `@` | Liste des terminaux (complétion de lieu) |

**Statut actuel :** Ctrl+Espace déclenche la complétion standard (même chose que Tab). Pas d'aide contextuelle distincte.

### TEST-03 : Fallback données sans UEX

**Objectif :** Vérifier que l'application reste utilisable quand uexcorp.space ne répond pas.

| # | Scénario | Résultat attendu |
|---|----------|-------------------|
| 1 | UEX down, cache frais (<24h) | Données statiques OK, prix OK, pas d'indication offline |
| 2 | UEX down, cache prix périmé | Prix affichés en **orange** avec mention "cache local" |
| 3 | UEX down, cache statique périmé | Données statiques chargées avec warning "⚠ données en cache" |
| 4 | UEX down, aucun cache | Message d'erreur clair, pas de crash |
| 5 | UEX down, données scan joueur | Prix scan affichés en vert ★, prioritaires |
| 6 | UEX revient après panne | Retour automatique aux données fraîches (cyan) au prochain fetch |
| 7 | sc-trade.tools down | Pas d'erreur, données UEX seules (pas d'orange) |
| 8 | Les deux down, cache dispo | Fonctionne en mode dégradé, tout en orange |

**Statut actuel :** Les tests 1-6 devraient passer (fallback implémenté dans info.py). Tests 7-8 à vérifier (SCTradeClient pas dans la chaîne de fallback).

### TEST-04 : Reconnaissance des noms (désignation)

**Objectif :** Vérifier que le système pointé et le fuzzy matching fonctionnent.

| # | Saisie | Résultat attendu |
|---|--------|-------------------|
| 1 | `/info new_babbage` | Info sur New Babbage (underscore → espace) |
| 2 | `/info New Babbage` | Même résultat (espace direct) |
| 3 | `/info new babbage` | Même résultat (minuscules) |
| 4 | `/info stanton.microtech.new_babbage` | Même résultat (notation pointée complète) |
| 5 | `/info stanton.new` | New Babbage (préfixe fuzzy) |
| 6 | `/go to port_tressler` | Position définie sur Port Tressler |
| 7 | `/trade buy copper` | Affiche les prix du Copper (insensible à la casse) |
| 8 | `/info rsi.hermes` | Fiche du vaisseau Mercury Star Runner (notation mfr.ship) |
| 9 | `@Area_18` | Position = Area 18, info du terminal Admin |
| 10 | `/info cutlass` | Fiche du Cutlass Black (préfixe) |
| 11 | `/go to grim` | Position = GrimHEX (préfixe) |
| 12 | `/info admin.area_18` | Info sur le terminal Admin - Area 18 |

**Statut actuel :** Tests 1-4, 6-7, 9-11 devraient passer. Test 5 dépend du fuzzy. Test 8 dépend de MFR_ABBREV. Test 12 dépend de la notation service.lieu.

### TEST-05 : Historique des commandes et résultats

**Objectif :** Vérifier la conservation et restitution de l'historique commandes+résultats.

| # | Action | Résultat attendu |
|---|--------|-------------------|
| 1 | Exécuter 5 commandes | Les 5 sont dans l'historique (↑/↓ pour naviguer) |
| 2 | `/config cmdhistory 3` | Seules les 3 dernières commandes+résultats sont conservées |
| 3 | `/config cmdhistory 10` | Les 10 dernières commandes+résultats conservées |
| 4 | Flèche ↑ dans le champ vide | Rappelle la dernière commande |
| 5 | Flèche ↑↑ | Rappelle l'avant-dernière commande |
| 6 | Taper du texte, puis ↑, puis ↓ | Le texte initial est restauré |
| 7 | Redémarrer l'overlay | L'historique des commandes est restauré depuis le disque |
| 8 | Résultats scrollables | Les résultats des N dernières commandes restent visibles en scrollant |

**Statut actuel :** Tests 1, 4-7 passent (historique commandes existant). Tests 2-3 échouent (pas de config cmdhistory). Test 8 partiellement (les résultats sont dans le DOM mais pas délimités par commande).

### TEST-06 : Sortie HTML/JS réactive

**Objectif :** Vérifier que l'affichage est interactif et réactif.

| # | Action | Résultat attendu |
|---|--------|-------------------|
| 1 | `/info Area_18` | Mots cliquables dans la sortie (terminaux, commodités) |
| 2 | Clic gauche sur un nom de terminal | Exécute `/info <terminal>` |
| 3 | Clic droit sur un nom de commodité | Menu contextuel (acheter, vendre, info) |
| 4 | `/trade buy Copper` | Bouton "Choisir" sur chaque ligne de résultat |
| 5 | Clic sur "Choisir" | Exécute l'action de trade correspondante |
| 6 | `/mission list` | Tableau HTML avec boutons éditer/supprimer |
| 7 | Clic sur "Éditer" dans mission | Ouvre le formulaire d'édition inline |
| 8 | Resize de la fenêtre | Le contenu s'adapte (responsive) |
| 9 | Les couleurs indiquent la source | Cyan=UEX, Orange=sc-trade/cache, Vert★=scan |

**Statut actuel :** Tests 1-7 devraient passer (implémentés). Test 8 partiel (adaptive.py gère la largeur). Test 9 partiellement (code couleur en place mais pas systématique).

---

## 4. Refactorisations prioritaires

### Priorité 1 — Aide multi-niveaux complète

**Fichier :** `uexinfo/cli/commands/__init__.py`

Modifier `dispatch()` pour intercepter `help` en dernière position :

```python
def dispatch(name: str, args: list[str], ctx) -> None:
    # /cmd help → /help cmd
    if args and args[0].lower() in ("help", "aide", "?"):
        dispatch("help", [name] + args[1:], ctx)
        return
    # /cmd subcmd help → /help cmd subcmd
    if len(args) >= 2 and args[-1].lower() in ("help", "aide", "?"):
        dispatch("help", [name] + args[:-1], ctx)
        return
```

Compléter `_DETAILS` dans help.py pour les sous-commandes manquantes.

### Priorité 2 — Historique commandes+résultats configurable

**Fichiers :** `overlay/server.py`, `overlay/static/index.html`, `cli/commands/config.py`

- Ajouter `/config cmdhistory <n>` (défaut 5)
- Côté JS : conserver les N derniers blocs commande+résultat dans un tableau dédié
- Permettre la consultation via `/history` (affiche les N derniers avec résultats)

### Priorité 3 — Ctrl+Espace = aide contextuelle

**Fichier :** `overlay/static/index.html`

Distinguer Ctrl+Espace de Tab :
- Tab = complétion (comportement actuel)
- Ctrl+Espace = aide contextuelle (affiche description + sous-commandes + types attendus)

### Priorité 4 — DataManager centralisé

**Nouveau fichier :** `uexinfo/data/manager.py`

Encapsuler la logique dispersée dans info.py :
- `fetch_prices(terminal, ctx)` → API → cache → stale → scan
- `fetch_commodity_info(name, ctx)` → UEX → sc-trade
- Gestion centralisée de `_api_offline`
- Code couleur déterminé par la source effective

### Priorité 5 — Sortie HTML native (progressive)

Migrer progressivement les commandes de Rich/ANSI vers HTML structuré :
1. Les commandes qui ont déjà des boutons (trade, mission, voyage) en premier
2. Les commandes info/exploration ensuite
3. Garder le parser ANSI→HTML en fallback

---

## 5. Règles de code

### Nommage et espaces
- Les noms sont stockés avec des **espaces** (pas d'underscores)
- `replace("_", " ")` est appliqué à toute saisie utilisateur
- La notation pointée (`system.planet.terminal`) est supportée pour la navigation
- Par défaut, c'est le terminal Admin ou TDD qui est retourné
- Les guillemets permettent de grouper : `"Port Tressler"`

### Code couleur (display/colors.py)
- **Cyan** (`C.UEX`) — données UEX Corp fraîches
- **Orange** (`C.SCTRADE`) — données sc-trade.tools OU cache UEX périmé
- **Vert ★** (`C.PROFIT` + bold) — données scan joueur confirmées
- **Rouge** (`C.LOSS`) — perte, rupture de stock

### Commandes
- Toute commande doit avoir une entrée dans `_COMMANDS` (aide courte) ET `_DETAILS` (aide longue)
- Les sous-commandes doivent aussi avoir leur entrée `_DETAILS["cmd subcmd"]`
- Le `/` est optionnel : `trade` = `/trade`
- `exit`, `bye`, `quit` ferment l'overlay

### Tests
- Les tests fonctionnels sont dans `scripts/test_*.py`
- Ils testent le flux complet (saisie → résultat) sans mock de l'API quand possible
- Pour les tests offline, simuler l'absence de réponse UEX et vérifier le fallback
