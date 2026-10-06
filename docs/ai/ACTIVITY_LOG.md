# Journal d'activité — Claude

> Une entrée par session ou étape notable, la plus récente en haut.
> Format : date — branche — ce qui a été fait — état des tests — suite prévue.

## 2026-10-06 (suite 5) — `/evolution` codé, début du refactoring

**Décisions reçues :** spécification de `/evolution` validée ; les réponses sont mémorisées par majeur.mineur ; les choix proposés pour D2 sont acceptés (pas de facteur cargaison, pas de colonne côté achat) ; feu vert pour le refactoring.

**Fait :**
- `/evolution` (`/scevolution`) :
  - `cache/evolution.py` : mémoire des versions et surveillance ;
  - la question s'affiche dans le runner, une fois par session ;
  - branchement dans le serveur (au démarrage : référence des ID et contrôle si la surveillance est active) ;
  - aide et complétion.
- `PriceCache` : la constante `SC_VERSION = "4.6"` est supprimée. Une entrée liée à l'univers reste valable sauf après un changement d'univers déclaré.
- Nettoyage :
  - scripts de debug déplacés dans `scripts/dev/` ;
  - `testpaths = tests` ;
  - `uex_scraper.py` et les méthodes mortes de sc-trade supprimés ;
  - `requirements.txt` aligné sur `pyproject.toml`.
- A2 : `PriceCache.delete_keys`, que `sync.py` utilise désormais (plus d'accès à `_mem`).

**Valeurs modifiées (signalées) :**
- La question n'est posée qu'en **montée** de version majeur.mineur. Un retour à une version plus ancienne (bascule PTU vers LIVE) ne la déclenche pas : choix de ma part, à confirmer.
- Les entrées de cache déjà taguées « 4.6 » restent valables tant qu'aucun changement d'univers n'est déclaré.

**Tests :** 109 réussis.

**Suite :** D6, le résolveur de noms unique (règles a, b, c à confirmer), puis B1/B2 (découpage d'`info.py`) et B3 (`UEXClient` derrière le cache).

## 2026-10-06 (suite 4) — D2 codé, règles D3

**Décisions reçues :** H = 1 h ; N = 7 jours ; option c ; un patch ne déclenche pas la question ; commande `/evolution` (`/scevolution`) à prévoir.

**Fait :**
- `uexinfo/rules/risk.py` : `sell_risk` remplace les deux anciennes formules. `/trade` et `/info` l'utilisent.
- `uexinfo/rules/version.py` : parsing de version, question au changement majeur.mineur, marqueur vX.Y, choix de la donnée la plus récente, surveillance de 7 jours. Ces règles ne sont pas encore branchées.
- Spécification de `/evolution` dans `ETUDES_RISQUE_VERSION.md` §C.

**Valeurs modifiées (signalées) :**
- Le risque affiché par `/trade` et `/info` change : formule unique à demi-vie.
- `/info` ne tient plus compte de la fraîcheur du prix d'achat (avant, elle pesait 30 %).
- `/trade` ne tient plus compte de la part de cargaison invendable (avant, elle pesait 70 %).
- Statut 6 : il donne maintenant 83 dans le risque (interpolation linéaire). Les quantités restent au défaut 0,5.

**Tests :** 93 réussis.

**En attente :** prise en compte de la cargaison et colonne côté achat (D2) ; spécification de `/evolution` (D3) ; D4, D5, D6.

## 2026-10-06 (suite 3) — D1 corrigé, études D2 et D3

**Fait :**
- **D1 :** création de `uexinfo/rules/` (règles métier pures). `stock.py` contient `buy_quantity` et `sell_quantity`. `trade.py` les utilise, et le repli « qty = 0 → cargo plein » est supprimé. 13 tests ajoutés.
- **D2 :** recherche web sur les cycles de stock (paliers de 8-10 min environ, réassort lent et variable, aucun chiffre officiel). Proposition d'une formule à demi-vie.
- **D3 :** étude version et univers (détection automatique, version sur chaque donnée, question au joueur, mode surveillance par comparaison des ID UEX).
- Le tout dans `docs/ai/ETUDES_RISQUE_VERSION.md`.

**Valeurs modifiées :** stock d'achat « Out » donne maintenant 0 SCU au lieu du cargo complet (validé par l'utilisateur). Aucun autre coefficient n'a changé.

**Tests :** 58 réussis.

**En attente :** H, cargo et côté achat (D2) ; N, option (c) et niveau de patch (D3) ; D4, D5, D6.

## 2026-10-06 (suite 2) — réponses de l'utilisateur sur l'audit

**Fait :**
- Créé `docs/ai/DECISIONS.md`, le registre des décisions métier (D1 à D6).
- Vérifié auprès de l'API UEX (`commodities_status`) : il y a 7 statuts de stock, et le 6 vaut « Very High » (72-85 %).
- Les prix UEX portent `game_version = 4.10.1`.
- `ttl_prices` n'a jamais été branché.
- Recensé une vingtaine de procédures de reconnaissance de noms.

**En attente :** réponses sur D2, D3, D4, D5 et D6. Aucun code modifié.

## 2026-10-06 (suite) — mission Stelliverse, étape 1 : audit

**Demande :** mission « améliorer uexinfo en s'inspirant de Stelliverse » (consignes dans `docs/ai/MISSION_STELLIVERSE.md`).

**Fait :** audit en lecture seule, dans `docs/ai/AUDIT_2026-10-06.md`. Aucun code modifié.

**Points saillants :**
- Deux formules de risque divergentes (`trade.py` et `info.py`).
- `qty == 0 → cargo complet` dans `/trade` : un stock « Out » donne un cargo plein.
- `SC_VERSION = "4.6"` est probablement périmée.
- `ttl_prices` est affiché mais jamais utilisé.
- Les seuils de correspondance floue diffèrent selon les modules.
- Les tests ne couvrent que les voyages. Aucune fixture `Game.log`.

**Tests :** `pytest tests` donne 45 réussis.

**En attente :** validation de l'audit par l'utilisateur avant l'étape 2. GitLab Stelliverse est accessible.

## 2026-10-06 — `claude/github-cloud-session-link-lq35n2`

**Demande :** refactoriser le projet selon ses objectifs principaux. Étape 1 : formuler les objectifs, créer des notes de navigation et ce journal.

**Fait :**
- Relu le code, les docs (`REFACTORING_PLAN.md`, `TODO_zol.md`, `bilan1_analyseFonctionnement.md`, `CONSIGNES_*`) et l'historique git.
- Vérifié l'état du plan de refactoring : A1, A2, B1, B2 et B3 sont tous encore à faire.
- Créé `docs/ai/NOTES.md` (objectifs O1 à O5, carte du code, dette) et ce journal.
- Ajouté un pointeur vers ces fichiers dans `CLAUDE.md` et corrigé la taille d'`index.html` (~4 400 lignes, pas ~20 000).

**Tests :** `pytest tests` donne 45 réussis. Le `pytest` nu échoue, car il collecte `scripts/test_*.py`.

**Suite proposée (à valider par l'utilisateur) :** voir la section « Plan de refactoring » de la réponse du 2026-10-06, reprise dans `NOTES.md` §4.
