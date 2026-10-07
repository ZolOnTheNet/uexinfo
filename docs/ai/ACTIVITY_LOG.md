# Journal d'activité — Claude

> Une entrée par session ou étape notable, la plus récente en haut.
> Format : date — branche — ce qui a été fait — état des tests — suite prévue.

## 2026-10-07 (suite 3) — pull refusé, instance masquée, filtre de `/info`

- Le `git pull` de l'utilisateur échouait à cause de modifications locales non commitées. Il tournait donc toujours sur `fd5089e` : d'où « Seraphim Station » et l'absence de trade. Je lui ai indiqué `git stash` puis `git pull`.
- PR #5 : une nouvelle instance ferme l'ancienne, restée masquée en arrière-plan. La version (commit) est affichée.
- PR #6 : plus de « Pyro Gateway (Stanton) (Stanton) ».
- **D9** : le filtre système de `/info` ne vient plus que de `/select`. Avant, le système du joueur servait de filtre par défaut. Vérifié sur données réelles : `/info RMC` montre Pyro Gateway (Nyx).
- À arbitrer : les terminaux fermés chez UEX (`is_available=0`, Platinum Bay / Dumper's Depot) apparaissent dans `/info` avec des prix vieux de plusieurs mois.

**Tests :** 173 réussis.

## 2026-10-07 (suite 2) — « je choisis Seraphim Station, il doit comprendre »

**Cause :**
- `LocationIndex` regroupait les terminaux par nom court. « Seraphim » (Admin) et « Seraphim Station » (Landing Services, Hot Dogs…) étaient donc deux lieux distincts.
- Choisir « Seraphim Station » enregistrait une boutique, sans aucun prix de marchandise.
- `/trade` réutilisait cet ID : « Aucune commodité commune ».

**Fait :**
- `names.terminal_group` (clé du lieu) et `names.trading_terminal` (terminal de commerce du même lieu, règle c).
- `LocationIndex` : une seule entrée par lieu, portée par le terminal de commerce principal.
- `@lieu` (player) et `/go`/`/dest` enregistrent toujours le terminal de commerce du lieu.
- `/trade` remplace une position ou destination déjà enregistrée sur une boutique par le terminal de commerce du lieu, et l'affiche.

**Vérifié :** sur les données UEX réelles, position « Landing Services - Seraphim Station » puis `/trade cargo 512` donnent Waste +87 % et RMC −6 %.

**Tests :** 170 réussis.

## 2026-10-07 (suite) — sortie : « Déconnecté — reconnexion dans 2s »

**Cause :** à la sortie (`/quit`, double-clic ✕), le serveur s'arrête, ce qui ferme le WebSocket. La page ne savait pas que la fermeture était voulue : elle affichait « Déconnecté » et tentait de se reconnecter.

**Fait :**
- `_quitting`, mis à vrai dès qu'une sortie est demandée ou que le message `quit` arrive : plus d'annonce ni de reconnexion.
- `_shutdown` : un minuteur de 3 s garantit `os._exit` même si la sauvegarde bloque.

**Non vérifié en vrai :** l'overlay graphique ne peut pas être lancé dans le cloud.

## 2026-10-07 — PR #1 fusionnée, port occupé, « aucun trade Seraphim → Pyro Gateway (Nyx) »

**Fait :**
- PR [ZolOnTheNet/uexinfo#1](https://github.com/ZolOnTheNet/uexinfo/pull/1) fusionnée dans `main`. La branche est repartie de `main`.
- **Port 8090 occupé** (`OSError 10048`) : l'overlay s'arrête maintenant avec un message clair. Avant, la nouvelle fenêtre se connectait à l'ancienne instance.
- **Trade Seraphim → Pyro Gateway (Nyx)** :
  - avec le nom correct, `/trade` trouve bien Waste (+87 %) et RMC (−6 %) ;
  - cause : « Pyro Gateway(Nyx) », sans espace avant la parenthèse, n'était reconnu nulle part ;
  - correction : `norm` remet un espace avant `(` ;
  - « pyro gateway » seul : ambiguïté entre Stanton et Nyx (le système du joueur est préféré), au lieu du terminal fermé « INS Jericho ».

**Valeurs modifiées (signalées) :** un terminal fermé chez UEX (`is_available=0`) passe après tous les terminaux ouverts dans la règle c.

**Tests :** 164 réussis.

## 2026-10-06 (suite 7) — statut 6, `/game`, migration des noms

**Décisions reçues :**
- Statut 6 : 85 % à l'achat, 15 % à la vente.
- Continuer la migration des noms.
- Le scan via log Datarunner n'est pas prioritaire (Datarunner lui-même a beaucoup de trous).
- Envie d'un lecteur de Game.log (`/game`) avec une touche ou un bouton pour sortir du suivi en direct.

**Fait :**
- **D5 :** statut 6 pris en compte partout : quantités, libellés, couleurs, barres. Avant, `/trade` affichait le niveau 6 comme une rupture (○○○○). La quantité de `/info` passe aussi par `rules/stock.buy_quantity`.
- **`/game` :**
  - `gamelog/lines.py`, `events.py` (parseur pur, pré-filtre puis regex), `state.py`, `follow.py` (tail incrémental) ;
  - `python -m uexinfo.gamelog <fichier> [--debug] [--all]` pour rejouer un log ;
  - `/game live` : panneau dans l'overlay, bouton ■ Arrêter, Échap ;
  - spécification clean-room dans `docs/ai/GAMELOG_SPEC.md` (faits relevés dans Stelliverse, aucun code repris) ;
  - fixture **synthétique** en attendant de vrais extraits.
- **Migration des noms (D6)** : `/nav`, `/route`, `/voyage`, missions, `/explore`, `/config`, `/player`. Ajout de `prefer_system`.

**Valeurs modifiées (signalées) :**
- `/nav` et les missions : en cas d'égalité, c'est maintenant le nom le plus court qui l'emporte, et le système du joueur en priorité. Avant, c'était le plus long ou le premier trouvé.
  - Exemples : « new » donne New Babbage (avant : HDMS-Pinewood) ; « area » donne Area 18.
  - « nyx gateway » donne la gateway du système du joueur.
  - « terra » donne Terra Mills Hydrofarm (avant : Terra Gateway).
- Les fautes de frappe dans les noms de mission sont mieux résolues (« Rayari Cantwell … Outposx » donne Cantwell, avant Anvik).

**Tests :** 160 réussis.

**Reste :** `scan._resolve_uex` et `ocr/engine` (OCR, non prioritaire), `LocationIndex.search` (complétion), puis vrais extraits de Game.log.

## 2026-10-06 (suite 6) — D4 supprimé, D6 résolveur unique

**Décisions reçues :**
- La question `/evolution` ne se pose qu'en montée de version (le PTU préfigure le LIVE).
- Il faudrait idéalement des jeux de données séparés pour LIVE et PTU (D7, à étudier).
- D6 : règles a, b et c acceptées.
- `ttl_prices` peut être supprimé.

**Fait :**
- D4 : `ttl_prices` supprimé de la configuration et de l'affichage.
- D6 : création de `uexinfo/names/`.
  - `norm` : une seule normalisation.
  - `NameIndex` : cascade exact > préfixe > contient > flou ; codes UEX en correspondance exacte seulement ; notation pointée ; abréviations de fabricants.
  - Règles a, b et c appliquées.
  - Fixtures de vraies données UEX dans `tests/fixtures/uex/`.
- Fonctions branchées sur le résolveur : `/info`, `/trade` (picker), `/go`, `/sync`, la clé canonique des scans, l'autopos des scans et `LocationIndex`.
- `CacheManager.find_*` (inutilisés) supprimés.

**Valeurs modifiées (signalées) :**
- **Priorité de terminal unique** : Admin > TDD > centre cargo > autre commerce > autre.
  - Avant, `/go` appliquait TDD > Admin, `info`/`location` mettaient Admin = TDD = Trade, et `data_manager` faisait Admin > TDD > cargo.
  - Aucun lieu UEX actuel n'a à la fois un Admin et un TDD, donc aucun effet visible aujourd'hui.
- **Seuils de ressemblance** : saisie 70, OCR 60.
  - `_find_vehicle` passe de 65 à 70.
  - Les modules OCR ne sont pas encore migrés.
- **Commodités** : « ship ammunition » donne maintenant une liste ambiguë (Size 1 à Size N) au lieu de Size 1 d'office. `_find_commodity` renvoie toujours la première.
- **`/go`** : terminaux, planètes et systèmes sont résolus ensemble (« hurston » donne la planète).
- **Lorville** : le terminal principal est « Admin - L19 Residences » (règle c), pas « CBD - Central Business District ». C'est inchangé par rapport à avant, mais à vérifier.

**Tests :** 142 réussis.

**Reste à migrer vers `names` :**
- `nav._resolve_node` et `_find_candidates`, `mission._resolve_graph_node`, `voyage._resolve_locs` ;
- `scan._resolve_uex` (OCR) et `ocr/engine` (fuzzy) ;
- `explore._match`, `config._find_vehicle`, `player._resolve_location`, `route._resolve_at`.

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
