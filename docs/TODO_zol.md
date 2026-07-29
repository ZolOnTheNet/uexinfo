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
