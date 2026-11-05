# Plan de test en jeu — uexinfo 0.0.1

> Statut : **à jour au 2026-11-05** (version `0.0.1-<commit>`). À dérouler après chaque série de
> changements touchant le jeu ; les tests automatiques (`pytest`) ne remplacent pas ces essais.

Chaque test donne : **faire** (clavier *et* souris quand les deux existent), **attendu**, et la
**trace** à chercher dans le journal `…\AppData\Local\uexinfo\uexinfo\logs\uexinfo.log`.
Noter le résultat (✅ / ❌ + ce qui s'est passé) dans la colonne prévue, puis transmettre le
journal du jour en cas d'écart.

## 0. Préparation

| # | Faire | Attendu | Trace | Résultat |
|---|---|---|---|---|
| 0.1 | Lancer uexinfo | Bannière « UEXInfo v0.0.1-<commit> » ; console : chemin du journal | `démarrage d'uexinfo 0.0.1-…` | |
| 0.2 | Vérifier que le commit affiché est le dernier poussé (`git log -1`) | Même code | — | |
| 0.3 | Star Citizen en **fenêtré sans bordure** (`WindowMode=2`) | Capture possible par uexinfo | — | |

## 1. Position, morts, déconnexions (Game.log)

| # | Faire | Attendu | Trace | Résultat |
|---|---|---|---|---|
| 1.1 | Se connecter dans une station | « 📍 Apparition à … », position mise à jour en bas | `jeu (respawn)` | |
| 1.2 | Demander un hangar, sortir, se poser | « 🅷 Hangar attribué… », « ⬇ Posé à … » | `jeu (hangar)`, `jeu (landed)` | |
| 1.3 | Partir puis arriver dans une autre station | « 🛫 Départ de … », « 📍 Arrivée à … », position = terminal du lieu | `jeu (departure)`, `jeu (arrival)` | |
| 1.4 | Mourir (vaisseau détruit) puis se réveiller | « 💀 Mort … » en rouge, puis « 🏥 Réveil à … », position = lieu du réveil | `jeu (death)`, `jeu (regen)` | |
| 1.5 | (Si elle arrive) erreur 30000 ou autre déconnexion | « ⚠ Déconnexion du serveur (erreur … : explication) » | `jeu (disconnect)` | |

## 2. Solde

| # | Faire | Attendu | Trace | Résultat |
|---|---|---|---|---|
| 2.1 | Capture (Impr. écran) d'un terminal de marchandises | Barre d'état : « 11 350 555 ¤ » (sans ≈) ; survol : date de lecture | — | |
| 2.2 | Recevoir une récompense de mission | « ≈ » devant le solde, gain de session en vert | — | |
| 2.3 | Acheter puis revendre une marchandise, refaire une capture du terminal | Solde estimé proche, puis exact après la capture | — | |

## 3. Mode scan des offres

| # | Faire | Attendu | Trace | Résultat |
|---|---|---|---|---|
| 3.1 | Clic sur **Scan Mis.** (barre d'état) — ou `/mission offres on` | Bouton vert ; message « Mode scan … en marche » | `commande (bouton Scan Mis.)`, `mode scan des offres lancé`, `mode scan des offres lancé` | |
| 3.2 | Contrats › OFFERS, cliquer une offre, attendre le texte | Bip ; encart Offres : l'offre avec ses livraisons | `détail : carte surlignée N … → <offre>` | |
| 3.3 | Ouvrir Contrats › OFFERS, ouvrir une offre, appuyer sur **F9** | Bip **aigu** en ~0,7 s, même juste après la molette ; détail rattaché (bip **grave** si non reconnue : réappuyer) | `raccourci f9 à l'écoute`, `touche f9 : offre affichée capturée`, `lu en … après 0.0 s` | |
| 3.3b | Fermer le mobiGlas, monter dans le vaisseau, appuyer sur F9 | F9 baisse la puissance moteur (touche jamais retirée au jeu) ; pas de bip | `touche f9 ignorée : écran Contrats … non affiché` | |
| 3.4 | Appuyer deux fois sur F9 sur la même offre | Une seule ligne dans l'encart, mise à jour | deux `détail :` vers la même offre | |
| 3.5 | Faire défiler la liste à la molette | Nouvelles offres dans l'encart | `liste : N cartes, M reconnues` | |
| 3.6 | Offre au titre long / reflet sur le titre | Rattachée quand même (carte surlignée) | `carte surlignée N` ≠ aucune | |
| 3.7 | Clic sur **Scan Mis.** — ou `/mission offres off` | Bouton gris ; F9 n'est plus écouté | `mode scan des offres arrêté` | |
| 3.8 | Laisser le mode en marche 20 min hors de Contrats | Arrêt seul + message | `mode scan des offres arrêté` | |

Attention : l'overlay posé sur la liste des contrats est lu avec elle — le garder à côté.

Images de dépannage : les 30 dernières images lues sont dans `…\AppData\Local\uexinfo\uexinfo\logs\offres\` (nom repris au journal, « image gardée : … ») ; les joindre au journal en cas d’écart.

## 4. Meilleur lot

| # | Faire | Attendu | Trace | Résultat |
|---|---|---|---|---|
| 4.1 | Vaisseau actif choisi (V: en bas), une dizaine d'offres ouvertes | — | — | |
| 4.2 | Bouton **Meilleur lot** (encart Offres) — ou thème Missions › « Meilleur lot pour mon vaisseau » — ou `/mission offres lot` | Tableau : offres choisies, total, SCU libres, offres écartées et pourquoi | `commande (bouton Meilleur lot) : /mission offres lot` + réponse | |
| 4.3 | `/mission offres lot 32` (autre soute) | Lot recalculé pour 32 SCU | réponse | |
| 4.3b | Bouton **≤ 2 dest.** (encart) — ou thème Missions › « Meilleur lot, 2 destinations max » — ou `/mission offres lot dest 2` | Lot avec 2 lieux de livraison au plus ; ligne « Destinations : 2 — … » | réponse | |
| 4.4 | Offre jamais ouverte | SCU « ≤ N » (catalogue) et note en bas | — | |
| 4.5 | Bouton **Vider** — ou `/mission offres vider` | Encart vidé | `réponse à /mission offres vider` | |
| 4.6 | Vérifier en jeu que le lot proposé tient vraiment dans la soute | Oui | — | |

## 5. Divers

| # | Faire | Attendu | Trace | Résultat |
|---|---|---|---|---|
| 5.1 | `/scan log clear` quand ScanLog clignote sur un vieux log, puis relancer uexinfo | Voyant éteint, et toujours éteint après la relance | réponse | |
| 5.2 | Un bouton du mode souris, puis la même commande tapée | Même résultat | `commande (bouton …)` puis `commande (saisie)` | |
| 5.3 | `/mission offres aide` — ou thème Missions › « Aide des offres » | Déroulé de la moisson, commandes, réglages | réponse | |
| 5.4 | Lendemain : le journal de la veille est renommé `uexinfo.log.AAAA-MM-JJ` | 7 jours gardés | — | |
