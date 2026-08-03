# To do
commande /ship en abrégé de /config ship

## Trade
refaire les trades : pas de bons objectifs

## Edition des scans

### Scans de commodités
le dernier tab fait sortir de l'édtion
les stocks ne sont pas correctement géré (max etc... ? -> Pas modifiable)

## /info 
n'est pas la commande par défaut : si pas de / devant et pas @ alors ajouter /info

## @ 
indique tout seul le lieu où se trouve le joueur. exemple @obituary => info sur obituary + changement
si dans le texte (texte avant donc) déclanche la selection d'un terminal ou d'un chemin vers le terminal

# extensions sympa


# si le texte saisie n'abouti pas, vérifier si celui-ci n' existe en commande (essayer avec / devant)

18x16c 3:30 min de chargement

arrivé new babbage : Int Spatioport : 23h06 23h13 dans le TDD

## [2026-07-28] Tournées d'achat multi-étapes (/voyage, /route, /nav)
Objectif : modéliser une vraie "tournée" d'achat/vente sur plusieurs terminaux (pas juste
un aller-retour A→B comme /trade). C'est en théorie le rôle de /voyage et /nav route,
mais la doc existante (docs/architecture.md, docs/commands.md) décrit un comportement
qui ne correspond pas forcément à ce qui est réellement implémenté aujourd'hui — à
vérifier commande par commande avant d'écrire quoi que ce soit de nouveau :
- Auditer /voyage et /nav route (code réel, pas la doc) : que font-ils vraiment
  aujourd'hui ? Multi-étapes possible ou seulement point à point ?
- Une fois l'écart doc/code clarifié, soit corriger la doc, soit compléter le code pour
  couvrir le cas "tournée d'achat" (plusieurs terminaux enchaînés, cargo qui se remplit/
  vide à chaque étape, calcul de bénéfice cumulé).
- Écrire un petit manuel utilisateur une fois le comportement stabilisé.

## [2026-07-28] Étude scmdb.net — missions comme alternative aux runs de commodités
Étudier https://scmdb.net/ (base communautaire des types de missions Star Citizen) pour
voir s'il est possible de proposer au joueur une MISSION adaptée (selon son niveau de
réputation/faction) plutôt qu'un simple run d'achat/revente de commodités — genre
"tu es à tel endroit avec tel cargo dispo, voici une mission qui rapporterait plus/aussi
bien qu'un trade classique". Nécessite d'abord de voir ce que scmdb.net expose
(structure des données, types de missions, disponibilité par système) avant de savoir
si c'est exploitable automatiquement ou juste consultable manuellement.

## [2026-08-01] Bouton "Choisir → créer mission" du bilan /trade à refaire
En ajoutant le champ SCU éditable par ligne au bilan /trade (achat/vente/bénéfice
recalculés en live), j'ai dû réécrire `showTradePick` (index.html) : l'ancienne version
cherchait des lignes commençant par "▶" pour y accrocher un bouton "Choisir" (crée une
mission via trade_chosen/_handle_trade_chosen), mais AUCUNE ligne du bilan /trade n'a
jamais commencé par "▶" — ce bouton n'est donc jamais apparu, probablement depuis son
ajout (code mort découvert, pas une régression de ce correctif). Je ne l'ai pas remis :
la nouvelle version fait un matching par code commodité (fiable, déjà utilisé par
showTerminalBuyPick) mais ne recrée pas le bouton. Si la fonctionnalité "transformer une
ligne de bilan en mission" est encore voulue, il faudra : (1) un bouton Choisir dans le
nouveau bloc injecté, (2) faire remonter le SCU édité au clic (`_handle_trade_chosen` ne
lit aujourd'hui que la quantité par défaut stockée côté serveur, pas une valeur éditée
côté client).

## [2026-08-01] Dédup ciblée : à généraliser à l'occasion, pas fait de façon exhaustive
Suite au bug ARC-L1/Nitrogen, j'ai cherché et fusionné les cas de logique dupliquée les
plus dangereux (ceux qui avaient déjà causé un bug réel ou pouvaient facilement en
recauser un) :
- nom court de terminal : 3 réimplémentations (info._loc, data_manager._loc_short,
  location.index._short_terminal_name) → 1 seule (formatter.terminal_short_name),
  les autres ne sont plus que des alias d'une ligne.
- choix de la "meilleure route" de vente pour une commodité : 3 réimplémentations dans
  info.py (_fetch_terminal_container_sizes, _pick_best_allowed_route,
  _find_best_allowed_from_prices), certaines se fiant au score brut UEX → 1 seule règle
  (info._route_rank_key : prix d'abord, distance à égalité).
- formatage de distance Gm/Mm : 6 réimplémentations (nav.py ×2, trade.py,
  voyage.py ×3) → 1 seule (formatter.fmt_distance_gm).
- côté overlay (index.html) : showTradePick et showTerminalBuyPick réimplémentaient
  chacune la recherche du tableau rendu par code commodité → factorisé dans
  _findTableByCodes ; _tbpRecalc/_tbpRecalcRow et _tbpChoose/_tbpChooseRow
  (deux fonctions identiques à un nom de paramètre près, avec une divergence — l'une
  plantait si le champ SCU était absent, l'autre non) → fusionnées en une seule.

Je n'ai PAS fait un audit ligne à ligne de tout le projet (index.html fait ~20 000
lignes) — juste une recherche ciblée (grep sur les patterns suspects : "score",
formules de distance, noms de fonctions très proches). Si un autre bug de ce genre
(résultat différent selon l'endroit du code qui fait le même calcul) réapparaît,
regarder d'abord s'il existe déjà une fonction équivalente ailleurs avant d'en écrire
une nouvelle.
