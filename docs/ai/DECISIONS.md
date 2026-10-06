# Décisions métier — validées par l'utilisateur

> Une ligne par décision. Toute valeur listée ici doit être fixée par un test au moment où elle est codée.
> Statut : ✅ décidé · ❓ question ouverte · 🔧 codé + testé

| # | Sujet | Décision / question | Statut |
|---|---|---|---|
| D1 🔧 | `/trade` : stock d'achat « Out » | Stock « Out » au terminal d'achat ⇒ **on ne peut rien acheter** (qté 0). Le repli `qty = cargo` (`trade.py:566`) est un bug. À l'inverse, un stock « Out » au terminal de **vente** ⇒ on peut vendre **toute** la cargaison (déjà le cas : `inv_mult[1] = 1.0`). | ✅ |
| D2 🔧 | Formule du risque | Deux formules coexistent. Une **seule formule mixte** : tend vers 0 si Out, vers 100 si Max, vers 50 quand la donnée vieillit (plusieurs heures) ; sous 1 h la donnée vaut de plus en plus. Proposition : `docs/ai/ETUDES_RISQUE_VERSION.md` §A. **H = 1 h**. Codé : `rules/risk.py`. Pas de facteur cargaison, pas de colonne côté achat (choix proposés acceptés). | ✅ 🔧 |
| D3 🔧 | Version de SC | Chaque donnée stockée doit garder **la version SC dont elle provient**. Version actuelle : **4.10** (UEX renvoie `game_version = 4.10.1`). La constante `SC_VERSION = "4.6"` est fausse. CIG ajoute des lieux, UEX a du retard → étude `ETUDES_RISQUE_VERSION.md` §B. **N = 7 j**, **option c**, un **patch ne déclenche pas** la question, commande **`/evolution`** (`/scevolution`) pour la poser à la main. Règles : `rules/version.py`. Réponse mémorisée par majeur.mineur ; question seulement en **montée** de version (confirmé : le PTU préfigure le LIVE). | ✅ 🔧 |
| D4 🔧 | `ttl_prices = 300` | Ajouté en avril 2026 (`f94a8a9`) mais **jamais branché**. Le but (ne pas solliciter UEX trop souvent) est déjà rempli par le TTL adaptatif de `PriceCache`. **Supprimé.** | ✅ 🔧 |
| D5 | Statut de stock 6 | UEX définit 7 statuts ; le **6 = « Very High Inventory » (72-85 %)**. Le code l'oublie dans toutes ses tables, il tombe donc sur la valeur par défaut. | ❓ coefficients |
| D6 🔧 | Reconnaissance des noms | **Une seule procédure** pour reconnaître station, planète, lune, ville, avant-poste, terminal, système, commodité, vaisseau, nœud du graphe. **a** deux profils de seuil (saisie 70, OCR 60) ; **b** égalité ⇒ liste au joueur ; **c** lieu ⇒ terminal principal Admin > TDD > centre cargo > autre commerce > autre. Module `uexinfo/names/`. | ✅ 🔧 (migration en cours) |

**D1** codé dans `uexinfo/rules/stock.py`, testé dans `tests/rules/test_stock.py` (commit « fix(trade) »).
**D2** codé dans `uexinfo/rules/risk.py` (`tests/rules/test_risk.py`), utilisé par `/trade` et `/info`.
**D3** règles dans `uexinfo/rules/version.py` (`tests/rules/test_version.py`), pas encore branchées.
**D3** `/evolution` codé : `cache/evolution.py`, `cli/commands/evolution.py` (`tests/cache/test_evolution.py`).
| D7 | LIVE et PTU | « Techniquement, on devrait avoir deux jeux de données différents » (LIVE et PTU). | ❓ à étudier |
**D6** `uexinfo/names/` (`tests/names/`), branché sur `/info`, `/trade`, `/go`, `/sync`, scans, `LocationIndex`.
