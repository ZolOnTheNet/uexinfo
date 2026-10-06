# Game.log — spécification des lignes exploitées

> Clean-room : ce document décrit des **faits sur le jeu** (format des lignes), rédigés à partir
> de nos propres observations et de faits relevés dans Stelliverse. Aucun code tiers n'est repris.
> Confiance : **V** = vérifié sur un vrai Game.log de l'utilisateur · **S** = relevé dans Stelliverse, **à confirmer** sur un vrai log.

## Format général

`<AAAA-MM-JJTHH:MM:SS.mmmZ> [Niveau] <Catégorie> message…` (V)
- Certaines lignes n'ont pas de `[Niveau]` ni de `<Catégorie>` : `[CSessionManager::OnClientSpawned] Spawned!`, `[VEHICLE SPAWN] …`.
- À ignorer (spam) : `OnEntityEnterZone`, `OnEntityLeaveZone`.
- Emplacement : `<install>\StarCitizen\LIVE\Game.log`, anciens logs dans `LIVE\logbackups\`. Le fichier est tronqué à chaque lancement.

## Événements

| Événement | Marqueur (sous-chaîne) | Données | Conf. |
|---|---|---|---|
| Connexion | `AccountLoginCharacterStatus_Character` | `name <pseudo>`, `geid <n>` | V (nom) |
| Pseudo | `<Legacy login response>` | `Handle[<pseudo>]` | S |
| Apparition | `[CSessionManager::OnClientSpawned] Spawned!` | — | V |
| Shard | `<Join PU>` | `shard[…]` | V |
| Zone / juridiction | `SHUDEvent_OnNotification` + `Added notification "Entered …"` | texte | V |
| Notification de mission | `SHUDEvent_OnNotification` / `<UpdateNotificationItem>` + « Contract Accepted: », « New Objective: », « Nouvelle mission : », « Nouvel objectif : » | texte | S (V pour « Contract Accepted ») |
| Départ de route QT | `Projected Start Location is X for route to destination` | lieu en clair | V |
| Cible QT | `Player has selected point <ID> as their destination` | ID interne, **vaisseau** `<MODELE>_<id>[id]` dans la même ligne | V (cible) / S (vaisseau) |
| Noms de route | `routing from A to B` | origine, destination en clair | V |
| Arrivée QT | `<Quantum Drive Arrived` … `arrived at final destination` | vaisseau | S |
| Changement de système | `<Changing Solar System>` … `changing system from A to B` | A, B | S |
| Docking | `CDockingAnimatorComponent::OnSetCurrentState>` | — (noms de tube non fiables) | V |
| Vaisseau piloté | `<Vehicle Control Flow>` `SetDriver` … `requesting control token for '<MODELE>_<id>'` | modèle, id | S |
| Vaisseau quitté | `<Vehicle Control Flow>` `ClearDriver` … `releasing control token for '<MODELE>_<id>'` | modèle | S |
| Vaisseau sorti (ASOP) | `[VEHICLE SPAWN]` `OnVehicleSpawned <id> (<MODELE>_<id>) by player <geid>` | modèle | S |
| Lieu proche (inventaire) | `<RequestLocationInventory>` `Player[x] requested inventory for Location[<Code_Lieu>]` | code lieu (ex. `Stanton3_Area18`) | S |
| Achat de marchandise | `SendCommodityBuyRequest` | `shopName[…]`, `price[…]`, `quantity[N]` ou `quantity[N cSCU]`, `resourceGUID[…]` | S (unité à confirmer) |
| Vente de marchandise | `SendCommoditySellRequest` | idem | S |
| Achat d'objet | `SendStandardItemBuyRequest` | `shopName[…]`, `client_price[…]`, `itemName[…]`, `quantity[…]` | S |
| Fin de mission | `<EndMission>` | `MissionId[…]`, `CompletionType[…]`, `Reason[…]` | S |
| Mort | `<Actor Death>` `CActor::Kill: '<victime>' … killed by '<tueur>' … damage type '<type>'` | victime, tueur, type | S |
| Destruction de vaisseau | `<Vehicle Destruction>` `Vehicle '<MODELE>_<id>' … destroy level A to B` | modèle, niveaux | S |
| Fin de session | `<SystemQuit>` / `EndSession` | — | S |

## Unités et identifiants

- `<MODELE>_<id>` : préfixe fabricant à 4 lettres + modèle, par exemple `DRAK_Cutlass_Black`, `RSI_Constellation_Phoenix`. Il se rapproche du vaisseau UEX via le résolveur de noms (`drak.cutlass black`).
- `quantity[100 cSCU]` correspond à 1 SCU (100 cSCU = 1 SCU), **à confirmer** sur un vrai achat.
- `Location[Stanton3_Area18]` est un code interne (système + numéro de planète + lieu), et non le nom affiché.
