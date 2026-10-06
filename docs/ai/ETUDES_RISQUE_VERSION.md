# Études — risque de stock (D2) et changement d'univers (D3)

> 2026-10-06. Propositions **non codées**, en attente de validation.

## A. Risque de prendre une marchandise (D2)

### Ce que l'on sait des cycles de stock (recherche web)

- Pas de chiffre officiel de CIG. Les sources communautaires concordent :
  - prix et stocks évoluent par **paliers d'environ 8-10 min** par terminal (wiki starcitizen.tools, guide timesaver.gg 4.10.1) ; d'autres parlent de 5-15 min ;
  - le stock se reconstitue **lentement, palier après palier**, à un rythme qui **varie fortement selon le terminal et la marchandise** ;
  - « une vérification UEX d'il y a une heure est déjà périmée » (timesaver.gg) ;
  - une grosse vente fait chuter le prix local (saturation).
- Conclusion : 1 h correspond à environ 6 paliers. Au-delà de quelques heures, le statut observé ne dit presque plus rien.
- On pourra **calibrer avec tes propres scans**, qui ont un horodatage : mesurer comment un statut évolue d'un scan à l'autre sur un même terminal.

### Formule proposée (une seule, pour `/trade` et `/info`)

Elle s'applique au **statut de stock du terminal de vente** : risque de ne pas pouvoir écouler.

```
base(statut) = (statut - 1) / 6 × 100      Out=0  T.Bas=17  Bas=33  Moyen=50  Haut=67  T.Haut=83  Max=100
fiabilité(t) = 0,5 ^ (t / H)               t = âge de la donnée en heures, H = demi-vie
risque       = fiabilité × base + (1 - fiabilité) × 50
```

Avec **H = 1 h** (proposition) :

| Âge | 0 | 10 min | 30 min | 1 h | 2 h | 4 h |
|---|---|---|---|---|---|---|
| Fiabilité | 100 % | 89 % | 71 % | 50 % | 25 % | 6 % |
| Risque si **Out** | 0 | 5 | 15 | 25 | 38 | 47 |
| Risque si **Moyen** | 50 | 50 | 50 | 50 | 50 | 50 |
| Risque si **Max** | 100 | 95 | 85 | 75 | 62 | 53 |

- Sous 1 h, l'information garde plus de la moitié de son poids, et d'autant plus qu'elle est récente.
- Après plusieurs heures, le risque tend vers 50 % (on ne sait plus).
- Donnée sans date : âge infini, donc risque 50.
- Une donnée issue de ton scan (★) suit la même formule avec l'âge du scan.

### Questions

1. **H = 1 h** te convient ? (30 min serait plus sévère, 2 h plus indulgent.)
2. Faut-il ajouter la **taille de ta cargaison** ? L'ancienne formule de `/trade` comptait la part de la cargaison que la destination ne peut pas absorber.
3. Faut-il afficher à part la fraîcheur du **côté achat** (stock encore là à l'arrivée) ? Ce serait une colonne séparée, non mélangée au risque.

## B. Changement de version et d'univers (D3)

### Ce qui dépend de l'univers

| Donnée | Où | Porte-t-elle sa version ? |
|---|---|---|
| Lieux et terminaux (ID UEX) | cache statique `~/.uexinfo/*.json` | non (TTL 24 h) |
| Distances entre terminaux (`rd_`) | `PriceCache` | « 4.6 » en dur, donc faux |
| Tailles de conteneurs (`cs_`) | `PriceCache` | idem |
| Vaisseaux (`vp_`, `vr_`) | `PriceCache` | idem |
| Graphe de navigation (106 nœuds, 5 014 arêtes) | `uexinfo/data/transport_network.json` | non : `updated_at` et `source` seulement |
| Scans joueur | `scan_prices.json` | oui (`sc_version` de `/config`) |
| Prix UEX | API | oui (`game_version`, 4.10.1 aujourd'hui) |

### Proposition

1. **Version détectée automatiquement** dans cet ordre : `build_manifest.id` ou Game.log, puis `game_version` des prix UEX, puis `/config` en dernier recours. Plus aucune constante en dur.
2. **Chaque donnée stockée porte sa version**, arêtes du graphe comprises.
3. Au **changement de version**, l'overlay demande : « L'univers a-t-il changé (nouveaux lieux) ? Oui / Non / Je ne sais pas ».
   - **Non** : on garde distances et graphe, et on les rattache à la nouvelle version.
   - **Oui ou Je ne sais pas** : on passe en **mode surveillance**.
4. **Mode surveillance (automatique)**, parce que UEX met à jour avec retard :
   - à chaque rafraîchissement statique (24 h), on compare la liste des ID de lieux et de terminaux avec celle de la version précédente ;
   - un **nouvel ID** ajoute le lieu au graphe et ne recalcule **que les distances qui le touchent** ;
   - un **ID disparu** marque le lieu comme retiré, sans suppression ;
   - la surveillance s'arrête après N jours sans changement.
5. Les données d'une ancienne version restent affichées avec un marqueur « vX.Y » tant que rien de plus récent n'existe (option (c) de la question précédente, à confirmer).

### Questions

- Durée **N** du mode surveillance : 7 jours ?
- Confirmes-tu l'option (c) pour les anciennes données ?
- Un **changement de patch mineur** (4.10.0 → 4.10.1) doit-il aussi déclencher la question, ou seulement un changement majeur ou mineur (4.10 → 4.11) ?

## C. Commande `/evolution` (alias `/scevolution`) — proposition

Elle permet de déclarer un changement d'univers **sans attendre la détection automatique** (hotfix, ajout de lieux en cours de version, doute).

| Commande | Effet |
|---|---|
| `/evolution` | État : version détectée, version des données (graphe, distances, scans), surveillance active ou non (jours restants), derniers lieux ajoutés ou retirés constatés |
| `/evolution oui` | L'univers a changé : démarre ou relance la surveillance (7 j), compare tout de suite les ID UEX, recalcule les distances des nouveaux lieux |
| `/evolution non` | Rien n'a changé : rattache distances et graphe à la version courante, arrête la surveillance |
| `/evolution check` | Force une comparaison UEX maintenant, sans changer l'état de la surveillance |

La même question (Oui / Non / Je ne sais pas) apparaît automatiquement à chaque changement majeur.mineur. « Je ne sais pas » équivaut à `oui`.
