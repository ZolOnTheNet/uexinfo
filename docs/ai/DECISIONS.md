# Décisions métier — validées par l'utilisateur

> Une ligne par décision. Toute valeur listée ici doit être fixée par un test au moment où elle est codée.
> Statut : ✅ décidé · ❓ question ouverte · 🔧 codé + testé

| # | Sujet | Décision / question | Statut |
|---|---|---|---|
| D1 | `/trade` : stock d'achat « Out » | Stock « Out » au terminal d'achat ⇒ **on ne peut rien acheter** (qté 0). Le repli `qty = cargo` (`trade.py:566`) est un bug. À l'inverse, un stock « Out » au terminal de **vente** ⇒ on peut vendre **toute** la cargaison (déjà le cas : `inv_mult[1] = 1.0`). | ✅ |
| D2 | Formule du risque | Deux formules coexistent. L'utilisateur veut **les règles** avant de choisir (voir la réponse du 2026-10-06). | ❓ |
| D3 | Version de SC | Chaque donnée stockée doit garder **la version SC dont elle provient**. Version actuelle : **4.10** (UEX renvoie `game_version = 4.10.1`). La constante `SC_VERSION = "4.6"` est fausse. | ✅ principe, ❓ comportement sur une donnée ancienne |
| D4 | `ttl_prices = 300` | Ajouté en avril 2026 (`f94a8a9`) mais **jamais branché**. Le but (ne pas solliciter UEX trop souvent) est déjà rempli par le TTL adaptatif de `PriceCache`. | ❓ supprimer ou brancher |
| D5 | Statut de stock 6 | UEX définit 7 statuts ; le **6 = « Very High Inventory » (72-85 %)**. Le code l'oublie dans toutes ses tables, il tombe donc sur la valeur par défaut. | ❓ coefficients |
| D6 | Reconnaissance des noms | **Une seule procédure** pour reconnaître station, planète, lune, ville, avant-poste, terminal, système, commodité, vaisseau, nœud du graphe. C'est le moteur du refactoring. | ✅ principe, ❓ règles |
