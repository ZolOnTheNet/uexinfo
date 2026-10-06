# Notes de travail Claude — uexinfo

> Mémo de navigation rapide, maintenu par Claude. À relire en début de session.
> Source de vérité = le code. Vérifié le 2026-10-06 (commit `fd5089e`).

## 1. Objectifs du projet (ma lecture)

**But :** un overlay Star Citizen qui aide le joueur à **gagner de l'aUEC sans quitter le jeu**.

| # | Objectif principal | Commandes / modules |
|---|---|---|
| O1 | **Trading** : où acheter, où vendre, quel profit, combien de SCU | `/trade`, `/info`, `/select`, `cache/data_manager.py`, `cache/price_cache.py` |
| O2 | **Position & navigation** : savoir où est le joueur et calculer la route | `/go`, `/dest`, `/arriver`, `@lieu`, `/nav`, `/route`, `models/transport_network.py`, `location/index.py` |
| O3 | **Missions & tournées** : enchaîner plusieurs étapes d'achat/vente ou missions | `/mission`, `/voyage`, `cache/mission_*.py`, `cache/voyage_manager.py`, `models/voyage.py` |
| O4 | **Collecte auto des données terrain** : prix/stock lus dans le jeu, prioritaires sur UEX | `/scan`, `/sync`, `/auto`, `ocr/`, `gamelog/`, `cache/scan_prices.py`, `cache/screenshot_db.py` |
| O5 | **Ergonomie in-game** : CLI émulé, complétion, mots cliquables, boutons | `overlay/server.py`, `overlay/static/index.html`, `cli/completer_data.py` |

**Contraintes transverses :**
- Données multi-sources fiables : scan joueur ★ > UEX (cyan) > sc-trade.tools (orange). Fonctionne hors ligne (cache périmé).
- Noms approximatifs acceptés partout (`new_babbage` = `New Babbage` = `stanton.microtech.new_babbage`).
- **Une seule implémentation par règle métier.** Les bugs passés venaient de calculs dupliqués.

## 2. Où trouver quoi (carte rapide)

| Je cherche… | Aller à |
|---|---|
| Boot / dépendances | `uexinfo/__main__.py` → `overlay/__init__.py:run_overlay` |
| Protocole WebSocket (types `cmd`, `complete`, `status`, `scan_confirm`…) | `overlay/server.py:_dispatch` (l.~300) |
| Exécution d'une commande | `server._handle_cmd` → `cli/runner.py` → `cli/commands/__init__.py:dispatch` |
| Complétion côté serveur | `server._complete_impl`, `_dyn_typed`, `_complete_dotted` + `cli/completer_data.py` |
| État global | `cli/context.py:AppContext` (`_price_cache`, `_overlay_send_fn`, `select_fn` injectés par le serveur) |
| Rendu Rich → HTML | `display/capturing_console.py`, `display/render_html.py`, `display/result.py` |
| Règles métier pures (testées) | `uexinfo/rules/` (`stock.py` quantités, `risk.py` risque D2, `version.py` versions D3) — décisions dans `docs/ai/DECISIONS.md` |
| Formatage (prix, SCU, distance, nom court terminal) | `display/formatter.py` (`fmt_distance_gm`, `terminal_short_name`) — **réutiliser** |
| Résolution terminal (la complète) | `cli/commands/info.py:_find_terminal` (l.~2284) |
| Classement des routes de vente | `info._route_rank_key` (prix puis distance) |
| Prix fusionnés UEX + scans | `cache/data_manager.py:terminal_prices`, `fetch_prices` (fallback : cache → API → périmé → vide) |
| TTL prix / version SC | `cache/price_cache.py` (`SC_VERSION`) |
| Graphe de transport | `uexinfo/data/transport_network.json` + `models/transport_network.py` |
| Logs Datarunner / Game.log | `ocr/log_parser.py`, `gamelog/{reader,parser,arrival}.py` |
| Données utilisateur | `~/.uexinfo/` (JSON caches, `config.toml`, `scan_prices.json`, `missions.json`, `voyages.json`) |

## 3. Taille des fichiers (points chauds du refactoring)

| Fichier | Lignes | Remarque |
|---|---|---|
| `cli/commands/info.py` | 2826 | fourre-tout : résolution terminaux, formatage, routes, fetch API |
| `cli/commands/voyage.py` | 2473 | |
| `overlay/server.py` | 1925 | protocole WS + logique métier (scan_confirm, sell_calc, complétion) |
| `cli/commands/scan.py` | 1908 | |
| `cli/commands/nav.py` | 1607 | |
| `cli/commands/config.py` | 1195 | |
| `overlay/static/index.html` | 4385 | ~140 fonctions JS (CLAUDE.md disait ~20 000 lignes : faux) |

Total Python : ~28 000 lignes.

## 4. Dette connue (état vérifié)

Mission en cours : `docs/ai/MISSION_STELLIVERSE.md` · Audit complet : `docs/ai/AUDIT_2026-10-06.md`.
Plan existant : `docs/REFACTORING_PLAN.md`. État au 2026-10-06 :
- **A1** : 3 `find_terminal` différents (`cache/manager.py:491`, `info.py:2284`, `sync.py:18`). **Pas fait.**
- **A2** : `sync.py:43` accède à `ctx._price_cache._mem`. **Pas fait.**
- **B1** : `_price_fmt`/`_price_short` toujours dans `info.py`. **Pas fait.**
- **B2** : `trade.py`, `explore.py`, `scan.py` importent des fonctions privées de `info.py`. **Pas fait.**
- **B3** : `UEXClient()` créé sans cache à 10 endroits (`info`, `nav`, `scan`, `sync`, `voyage`). **Pas fait.**
- Fait (commit `fd5089e`) : dédup du nom court de terminal, du classement de routes et de la distance Gm.
- `pytest` à la racine collecte aussi `scripts/test_*.py`, qui plantent. Utiliser `pytest tests`.
- Scripts isolés à la racine : `check_*.py`, `fix_iron_price.py`, `debug_help.py`, `output.txt`.
- Code mort : `api/uex_scraper.py`, `screens/`, `widgets/`, `SCTradeClient.commodity_items/ships`.

## 5. Environnement de test (session cloud)

```bash
pip install rich requests appdirs tomli-w rapidfuzz websockets   # pywebview ne s'installe pas ici
python -m pytest -q tests        # 93 tests OK au 2026-10-06
```
Impossible de lancer l'overlay graphique dans le conteneur. Valider par les tests et l'import des modules.
