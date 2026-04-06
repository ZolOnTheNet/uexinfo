# Plan : Full HTML+JS Overlay — Stratégie graphique

> **But** : L'overlay HTML+JS est l'interface principale et unique (plus de double affichage).
> L'ANSI/Rich reste uniquement pour le mode `--cli` explicite (encapsulé dans `else`).
> Objectif graphique : boutons pour les actions, tableaux interactifs, navigation par clic.
>
> **Exécutant** : Vibe (Mistral) via MCP clive — tâches mécaniques ciblées.
> **Orchestrateur** : Claude — validation, intégration, tests.
>
> **Principe** : Ne pas faire en deux étapes ce qui peut se faire en une.
> Chaque commande migrée envoie directement son message JSON structuré (pas de passage intermédiaire ANSI).

---

## Contexte technique

### Ce qui existe déjà

| Mécanisme | Fichier | Rôle |
|---|---|---|
| Capture ANSI | `overlay/server.py` `_exec_sync()` | Redirige `console` vers StringIO, envoie l'ANSI comme message `output` |
| Message `output` | `index.html` handler | Affiche l'ANSI brut dans `#console-output` (fonctionne mais non interactif) |
| `trade_pick` | server.py + JS `showTradePick()` | Boutons "→ Voyage" sur résultats trade bilan |
| `terminal_buy_pick` | server.py + JS `showTerminalBuyPick()` | SCU input + profit + "→ Voyage" sur achats terminaux |
| `scan_log_inline` | server.py + JS `appendScanInline()` | Formulaire inline éditable pour scans OCR/log |
| `mission_*` | server.py + JS | Catalogue, édition, actions missions |
| `voyage_calc_result` | server.py + JS | Résultats calcul voyage avec boutons |
| `loc_abbrevs` | server.py + JS | Noms de lieux cliquables |

### Ce qui manque (ANSI pur, non interactif)

| Commande | Volume | Problème concret |
|---|---|---|
| `/info` (vues hors achat) | 2173 lignes, 80+ appels | Tableau sell, scan section, commodity list → ANSI pur |
| `/trade buy/sell` | 50+ appels | Listes achat/vente → ANSI pur |
| `/nav` | 1587 lignes, 96+ appels | Route complète → ANSI pur |
| `/player` | 10+ appels | Fiche joueur/vaisseau → ANSI pur |
| `/explore` | 33+ appels | Arbre géo, vaisseaux → ANSI pur |
| `/config` | 101+ appels | Menus config → ANSI pur (basse priorité) |

---

## Principes d'implémentation

1. **Dual path** : chaque commande détecte `overlay_active` (via `ctx.cfg.get("overlay","enabled")=="true"` ou `getattr(ctx, "overlay_ws", None)`) et envoie un message JSON structuré **au lieu** (pas en plus) de l'ANSI.
2. **Message JSON → HTML** : le JS reçoit un objet structuré et génère du HTML riche (tableaux, boutons, inputs).
3. **ANSI fallback** conservé pour `--cli` : les `console.print()` existants ne sont pas supprimés, juste court-circuités en mode overlay.
4. **Helper `_send_overlay(ctx, msg_type, payload)`** : fonction utilitaire à ajouter dans `overlay/server.py` (ou `display/overlay_send.py`) pour envoyer depuis les commandes sans import circulaire.

---

## Phase 1 — Helper d'envoi overlay depuis les commandes

**Fichier** : `uexinfo/display/overlay_send.py` (nouveau)

**Tâche Vibe** :
```
Crée uexinfo/display/overlay_send.py avec une fonction thread-safe :

  def send_overlay(ctx, msg_type: str, payload: dict) -> None

- ctx.overlay_send_queue est une asyncio.Queue (None si pas d'overlay).
- Si la queue existe, appelle ctx.overlay_send_queue.put_nowait({"type": msg_type, **payload})
- Sinon, no-op silencieux.
- Pas d'import de server.py (éviter circulaire).

Dans overlay/server.py, dans __init__ de OverlayServer :
- Crée self.send_queue = asyncio.Queue()
- Ajoute ctx.overlay_send_queue = self.send_queue après ctx init
- Ajoute une coroutine _drain_queue() qui consomme la queue et broadcast sur tous les WS connectés
- Lance _drain_queue() dans run()
```

---

## Phase 2 — `/info` vues vente et liste commodités

### 2a — Vue "Vendre ici" (`_show_sell_detailed` dans info.py)

Actuellement : tableau Rich ANSI.
Cible : message `terminal_sell_pick` identique à `terminal_buy_pick` mais côté vente.

**Tâche Vibe** :
```
Dans uexinfo/cli/commands/info.py, fonction _show_sell_detailed() :

1. Après construction du tableau Rich existant (conserver), ajouter un bloc
   conditionnel `if getattr(ctx, "overlay_send_queue", None):`.

2. Construire entries = liste de dicts :
   { "name": str, "code": str, "price": int, "stock": str,
     "sizes": str, "idx": int }
   (même structure que last_terminal_buy_entries)

3. Stocker dans ctx.last_terminal_sell_entries = {"terminal": term_name, "tid": tid, "entries": entries}

4. Appeler send_overlay(ctx, "terminal_sell_pick", {"terminal": term_name, "entries": entries})

Dans index.html :

5. Ajouter handler pour "terminal_sell_pick" → appelle showTerminalSellPick(data)

6. showTerminalSellPick() : identique à showTerminalBuyPick() mais libellé "▲ Vendre sur place",
   colonne SCU avec input, profit négatif = couleur rouge.
   Bouton "→ Voyage (vente)" envoie message terminal_sell_chosen.

Dans overlay/server.py :

7. Handler "terminal_sell_chosen" : même logique que _handle_terminal_buy_chosen()
   mais type vente (MissionObjective.type = "sell").
```

### 2b — Section scan dans `/info` (`_show_scan_section`)

Actuellement : tableau Rich ANSI dans le terminal.
Cible : le formulaire `scan_log_inline` est déjà utilisé pour les nouveaux scans ; ici c'est le réaffichage des scans persistés.

**Tâche Vibe** :
```
Dans uexinfo/cli/commands/info.py, fonction _show_scan_section() :

1. Après construction du tableau Rich (conserver), si overlay_send_queue présent :

2. Construire rows depuis ScanPriceStore().get_rows(terminal_key) :
   [{"name": str, "code": str, "price": int, "quantity": int|None,
     "stock_status": int, "timestamp": int}]

3. send_overlay(ctx, "scan_persisted", {
       "terminal": terminal_name,
       "terminal_id": tid,
       "rows": rows
   })

Dans index.html :

4. Handler "scan_persisted" → appendScanPersisted(data)

5. appendScanPersisted() : affiche un tableau non-éditable (readonly) avec
   les données persistées, bouton "✏ Modifier" qui transforme en formulaire
   scan_log_inline (réutiliser appendScanInline existant).
```

### 2c — `/info list` (liste commodités)

**Tâche Vibe** :
```
Dans uexinfo/cli/commands/info.py, handler cmd_info_list() :

1. Après affichage Rich, si overlay :
   send_overlay(ctx, "commodity_list", {
       "rows": [{"name", "code", "buy_best", "sell_best", "spread", "illegal"}],
       "filters": {"sort": str, "min_buy": int, "max_buy": int, ...}
   })

Dans index.html :

2. Handler "commodity_list" → showCommodityList(data)

3. showCommodityList() : tableau HTML avec colonnes Nom, Code, Achat min, Vente max,
   Spread. Clic sur une ligne → envoie commande "info <name>" via submitCmd().
```

---

## Phase 3 — `/trade buy` et `/trade sell`

### 3a — `/trade buy <commodity>` et `/trade sell <commodity>`

**Tâche Vibe** :
```
Dans uexinfo/cli/commands/trade.py :

1. Dans _cmd_trade_buy() et _cmd_trade_sell(), après la boucle Rich :
   Si overlay :
   send_overlay(ctx, "trade_terminals", {
       "mode": "buy"|"sell",
       "commodity": name,
       "entries": [
           {"terminal": str, "system": str, "price": int,
            "stock": str, "sizes": str, "dist_gm": float|None, "idx": int}
       ]
   })

Dans index.html :

2. Handler "trade_terminals" → showTradeTerminals(data)

3. showTradeTerminals() : tableau HTML trié par prix.
   Mode "buy" : prix croissant, bouton "→ Aller acheter" envoie go_terminal.
   Mode "sell" : prix décroissant, bouton "→ Aller vendre" envoie go_terminal.
   Clic terminal → envoie "info <terminal>" via submitCmd().
```

---

## Phase 4 — `/nav` route

**Tâche Vibe** :
```
Dans uexinfo/cli/commands/nav.py :

1. Dans _display_route(), après Rich, si overlay :
   send_overlay(ctx, "nav_route", {
       "origin": str, "dest": str,
       "waypoints": [{"name": str, "type": str, "dist_gm": float,
                      "dist_mm": float|None, "gate": str|None}],
       "total_gm": float, "jumps": int
   })

Dans index.html :

2. Handler "nav_route" → showNavRoute(data)

3. showNavRoute() : tableau avec waypoints numérotés, distances,
   indicateurs visuels (gate ⬡, QD ◆, atterrissage ▼).
   Total en bas. Bouton "→ Définir destination" sur chaque waypoint.
```

---

## Phase 5 — `/player`

**Tâche Vibe** :
```
Dans uexinfo/cli/commands/player.py :

1. Dans _show_player_info() et _show_ship_list(), si overlay :
   send_overlay(ctx, "player_info", {
       "name": str, "location": str, "destination": str,
       "active_ship": {"name": str, "scu": int, "pad": str},
       "ships": [{"name": str, "scu": int, "pad": str, "active": bool}]
   })

Dans index.html :

2. Handler "player_info" → showPlayerInfo(data)

3. showPlayerInfo() : carte joueur avec vaisseau actif mis en avant,
   liste vaisseaux avec bouton "Activer" (envoie player_set_ship).
```

---

## Phase 6 — Nettoyage et détection overlay

### 6a — Détecter le mode overlay dans les commandes

**Tâche Vibe** :
```
Dans uexinfo/cli/main.py ou AppContext :

1. Ajouter propriété helper sur AppContext :
   @property
   def overlay_active(self) -> bool:
       return getattr(self, "overlay_send_queue", None) is not None

2. Remplacer tous les `getattr(ctx, "overlay_send_queue", None)` par `ctx.overlay_active`
   dans info.py, trade.py, nav.py, player.py.
```

### 6b — Supprimer les `console.print` redondants en mode overlay

**Tâche Vibe** :
```
Pour chaque bloc modifié dans les phases 2-5 :

Pattern à appliquer systématiquement :

    if ctx.overlay_active:
        send_overlay(ctx, msg_type, payload)
    else:
        # code Rich existant inchangé
        console.print(table)

NE PAS supprimer le code Rich — il reste pour --cli.
Juste encapsuler dans `else`.
```

---

## Phase 7 — `/explore` (optionnel, basse priorité)

**Tâche Vibe** :
```
Dans uexinfo/cli/commands/explore.py :

1. _explore_geo() → send_overlay "explore_geo" avec arbre JSON {systems, bodies, terminals}
2. _explore_ships() → send_overlay "explore_ships" avec liste vaisseaux
3. _explore_commodities() → send_overlay "explore_commodities" avec liste

Dans index.html :
4. Chaque handler génère un arbre/tableau HTML cliquable.
   Clic sur terminal → submitCmd("info <terminal>")
   Clic sur vaisseau → submitCmd("player ship <name>")
```

---

## Ordre d'exécution recommandé

```
Phase 1  → helper send_overlay (prérequis de tout)
Phase 2a → terminal_sell_pick (symétrique de buy, déjà fait côté JS)
Phase 2b → scan_persisted (réaffichage scans enregistrés)
Phase 3  → trade buy/sell (très utilisé)
Phase 2c → commodity list
Phase 4  → nav route
Phase 5  → player info
Phase 6  → nettoyage détection
Phase 7  → explore (optionnel)
```

---

## Tests à faire après chaque phase

1. Lancer `uexinfo` (mode overlay par défaut)
2. Tester la commande en overlay → vérifier rendu HTML
3. Lancer `uexinfo --cli`
4. Tester la même commande → vérifier que l'ANSI fonctionne toujours
5. Vérifier dans la console du navigateur qu'aucun message JSON malformé n'est reçu

---

## Notes pour Vibe

- **Ne jamais supprimer** le code Rich existant — encapsuler dans `else`.
- **Ne pas toucher** à `api/`, `cache/`, `config/` (logique métier intouchable).
- Toujours utiliser les constantes de `display/colors.py` pour les styles CSS inline.
- Les noms de commodités : toujours passer par `_abbrev_name(name, code=cc)` pour la cohérence.
- `ctx.overlay_send_queue` peut être `None` : toujours vérifier `ctx.overlay_active` avant d'envoyer.
- Format timestamps : Unix → `"màj DD Mon YYYY HH:MM"` (helper `_fmt_ts()` existe dans info.py).
