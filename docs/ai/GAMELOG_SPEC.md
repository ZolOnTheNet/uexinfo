# Game.log — spécification des lignes exploitées

> Clean-room : ce document décrit des **faits sur le jeu** (format des lignes), rédigés à partir
> de nos propres observations et de faits relevés dans Stelliverse. Aucun code tiers n'est repris.
> Confiance : **V** = vérifié sur un vrai Game.log de l'utilisateur · **S** = relevé dans Stelliverse, **à confirmer** sur un vrai log.

## Format général

`<AAAA-MM-JJTHH:MM:SS.mmmZ> [Niveau] <Catégorie> message…` (V)
- Certaines lignes n'ont pas de `[Niveau]` ni de `<Catégorie>` : `[CSessionManager::OnClientSpawned] Spawned!`, `[VEHICLE SPAWN] …`.
- À ignorer (spam) : `OnEntityEnterZone`, `OnEntityLeaveZone`.
- Emplacement : `<install>\StarCitizen\LIVE\Game.log`, anciens logs dans `LIVE\logbackups\`. Le fichier est tronqué à chaque lancement.

## En-tête du fichier (V, LIVE 4.10, 2026-10-07)

| Ligne | Exemple |
|---|---|
| `BackupNameAttachment=" Build(<n>) …"` | `Build(12660092)` |
| `FileVersion: <x.y.z.w>` | `4.10.193.11644` (≠ `game_version` UEX `4.10.1`) |
| `[Trace] Environment:   <ENV>` | `PUB` en LIVE (valeur PTU non observée) |

Encodage : UTF-8 en général, mais certaines lignes sont en **cp1252** (`Entr\xe9e ligne`). Lecture : UTF-8, sinon cp1252.

## Événements

| Événement | Marqueur (sous-chaîne) | Données | Conf. |
|---|---|---|---|
| Connexion | `AccountLoginCharacterStatus_Character` | `name <pseudo>`, `geid <n>` | V (nom) |
| Pseudo | `<Legacy login response>` | `Handle[<pseudo>]` | V |
| Apparition | `[CSessionManager::OnClientSpawned] Spawned!` | — ; **aussi écrite dans le menu** : ne compte en jeu qu'après un `<Join PU>` | V |
| Menu principal | `[CSessionManager::RequestFrontEnd] Started` | `RequestFrontEndReason="ProcessBootRequest"` (lancement) ou `"OnLobbyPostGameUnload"` (déconnexion) | V |
| Shard | `<Join PU>` | `shard[…]` | V |
| Zone / juridiction | `SHUDEvent_OnNotification` + `Added notification "Entered …"` | texte, « : » final retiré | V |
| Notification de mission | `SHUDEvent_OnNotification` + « Contract Accepted: », « Contract Shared: », « Contract Complete: », « Contract Failed: », « New Objective: », « Nouvelle mission : », « Nouvel objectif : » | texte, balises `<EM4>…</EM4>` retirées ; `MissionId: [<uuid>]` en fin de ligne relie objectifs et contrat (non exploité) | V en anglais (2026-10-19) ; S en français |
| Départ de route QT | `Projected Start Location is X for route to destination` | lieu en clair | V |
| Cible QT | `Player has selected point <ID> as their destination` | ID interne (`LOC_rs_ext_stan-magnus_jp1`, `rs_ext_nyx-pyro_jp1`), **vaisseau** dans le segment `| <MODELE>_<id>[id]|` | V |
| Noms de route | `routing from A to B` | origine, destination en clair | V |
| Arrivée QT | `<Quantum Drive Arrived - Arrived at Final Destination>` … `OnQuantumDriveArrived` … `arrived at final destination` | vaisseau (segment `|…|`) ; **pas de lieu** : suivi ~5 ms après d'un `RequestLocationInventory` | V |
| Changement de système | `<Changing Solar System>` … `changing system from A to B` | A, B | S |
| Docking | `CDockingAnimatorComponent::OnSetCurrentState>` | — (noms de tube non fiables) | V |
| Vaisseau piloté | `<Vehicle Control Flow>` `SetDriver` … `requesting control token for '<MODELE>_<id>'` | modèle, id | S |
| Vaisseau quitté | `<Vehicle Control Flow>` `ClearDriver` … `releasing control token for '<MODELE>_<id>'` | modèle | V |
| Vaisseau sorti (ASOP) | `[VEHICLE SPAWN]` `OnVehicleSpawned <id> (<MODELE>_<id>) by player <geid>` | modèle | S |
| Lieu proche (inventaire) | `<RequestLocationInventory>` `Player[x] requested inventory for Location[<Code_Lieu>]` | code lieu → nom et système : `uexinfo/gamelog/places.py` (voir ci-dessous) | V |
| Achat de marchandise | `SendCommodityBuyRequest` | `shopName[…]`, `price[…]`, `quantity[N]` ou `quantity[N cSCU]`, `resourceGUID[…]` | S (unité à confirmer) |
| Vente de marchandise | `SendCommoditySellRequest` | idem | S |
| Achat d'objet | `SendStandardItemBuyRequest` | `shopName[…]`, `client_price[…]`, `itemName[…]`, `quantity[…]` | S |
| Fin de mission | `<EndMission>` `Ending mission for player. MissionId[…] Player[…] PlayerId[…] CompletionType[Complete] Reason[Mission Ended]` | identifiant, type de fin | V (2026-10-19) |
| Crash | `<FatalCollision>` `Fatal Collision occured for vehicle <MODELE>_<id> [Part: …, Zone: <zone>, PlayerPilot: 1]` | modèle, zone | V (35 fois sur 317 logs) |
| Mort en vaisseau détruit | `<[ActorState] Dead>` `Actor '<pseudo>' [geid] ejected from zone … due to previous zone being in a destroyed vehicle` | pseudo | V (39 fois, toujours cette forme) |
| À terre ou mort | `<Adding non kept item [CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement]> Item 'body_…'` | — ; une ligne par objet, seule `body_` compte. Suivie d'une apparition (12 à 33 s) = mort confirmée | V (83 fois) |
| Mort | `<Actor Death>` `CActor::Kill: '<victime>' … killed by '<tueur>' … damage type '<type>'` | victime, tueur, type | S — **jamais vu sur 317 logs** (2026-10-19) |
| Destruction de vaisseau | `<Vehicle Destruction>` `Vehicle '<MODELE>_<id>' … destroy level A to B` | modèle, niveaux | S — **jamais vu sur 317 logs** |
| Fin de session | `<SystemQuit>` (`EndSession` = anti-triche, ignoré) | — | V |

## Unités et identifiants

- `<MODELE>_<id>` : préfixe fabricant à 4 lettres + modèle, par exemple `DRAK_Cutlass_Black`, `RSI_Constellation_Phoenix`. Il se rapproche du vaisseau UEX via le résolveur de noms (`drak.cutlass black`).
- `quantity[100 cSCU]` correspond à 1 SCU (100 cSCU = 1 SCU), **à confirmer** sur un vrai achat.
- `Location[Stanton3_Area18]` est un code interne (système + numéro de planète + lieu), et non le nom affiché.

## Codes de lieu (V, 317 logs, 2026-10-19)

Table et règles : `uexinfo/gamelog/places.py`. Noms relevés en associant un code d'inventaire (ou une cible QT atteinte) au `Projected Start Location` qui suit.
- `RR_<HUR|CRU|ARC|MIC>_<LEO|L1…L5>` : aires de repos de Stanton (`RR_CRU_LEO` = Seraphim Station). Équivalents : `rs_ext_cru-leo1`, cible QT `LOC_RR_S<1-4>_L<n>` (S1 = Hurston … S4 = microTech).
- `RR_P<n>_…` : Pyro (`RR_P3_LEO` = Orbituary). `RR_JP_<A><B>` : passerelle **située dans A** (`RR_JP_PyroStanton` = Stanton Gateway, dans Pyro).
- `<Système><n><lettre>_…` : avant-poste ; le jeu n'affiche que le corps céleste (`Stanton1c` = Magda), sauf `HurdynMining_HDMS<Nom>` → `HDMS-<Nom>`.
- `OOC_<Système>_<n><lettre>_<Nom>` : corps céleste (cible QT).
- Non traduits : `ObjectContainer_RestStop` (générique, 3 stations différentes), `MISSION_QT_Beacon_…`, `NavPoint_Dynamic_…`.

## Non observés dans le log du 2026-10-07 (restent S)

`SetDriver`, `OnVehicleSpawned`, `SendCommodityBuyRequest`/`SellRequest`, `SendStandardItemBuyRequest`, `<Changing Solar System>` (aucune ligne lors du passage Stanton → Nyx par le point de saut), `routing from`, « Contract Accepted ».

## Autres lignes observées, non exploitées

- **`<Update Inventory Location>`** `Player [x] is changing location. Landing [a] -> [b]. Location [c] -> [d]` (V, 2026-10-22, sessions des 19 et 20/10) :
  `b ≠ 0` = **entrée dans la zone d'une station ou d'une ville** (même seconde que `RequestLocationInventory` → code du lieu : identifiant ↔ nom apprenable) ; `b = 0` = **sortie de la zone** (`a` garde le dernier lieu). En vol, `d` change de région (identifiants numériques). Réapparition : `Landing [0] -> [id]`. Ex. 1752411604 = Seraphim, 1510935576 = CRU-L1, 308639451 = Everus Harbor, 3170699229 = New Babbage, 1105811199 = Orison, 4005457614 = Lorville, 753506656 = HDMS-Hahn, 3196629118 = MIC-L4. **Non vérifié** : survol d'une station sans s'y arrêter.
- **Terminaux de commerce** (V, 317 logs) : `CEntityComponentCommodityUIProvider::LoadShopInventoryData` (ouverture de l'écran), `SendCommodityBuyRequest` / `SendCommoditySellRequest` avec `shopName[…]`, `shopId`, `kioskId`, `price[…]`, `shopPricePerCentiSCU[…]`, `quantity[N cSCU]` (100 cSCU = 1 SCU), `resourceGUID`. `shopName` identifie le type de terminal (`SCShop_CommEx_TDD_NewBabbage`, `TDD_SCShop-001`, `SCShop_Cargo_Office`…) mais `SCShop_Admin_lt_base_g` est un modèle partagé par de nombreuses stations : combiner avec la zone courante.
- Monte-charge : `CEntityComponentFreightElevatorUIProvider::FillUnstowRequest` (`Location: <id>`, `Entities`), vu une fois (2026-10-20, kiosque extérieur de Seraphim).

- `<Update Inventory Location>` `Landing [a] -> [b]. Location [c] -> [d]` : identifiants numériques seulement.
- `<GenerateLocationProperty>` : lieux proposés par les contrats (nom + code), pas la position du joueur.
  Réécrit à chaque rafraîchissement de la liste des contrats du mobiGlas, mais **seulement pour les contrats proposés qui ont des lieux tirés au sort** : toujours les mêmes quelle que soit la mission cliquée. Aussi écrit à la réception d'un contrat partagé et à l'acceptation. Contenu : nom interne (`contract: Iasi_DefendShip_Hard_0`, qui correspond au `debugName` de scmdb.net) et lieux candidats. Pas de titre, ni de récompense, ni de description (vérifié 2026-10-19).
- **Clic sur un contrat dans le mobiGlas : aucune ligne écrite** (vérifié 2026-10-19, séance de clics 22h44-22h47).
- Contrats acceptés, poussés par le serveur : `<ObjectiveUpserted>` (`mission_id`, `objective_id`, `state MISSION_OBJECTIVE_STATE_…`), `<CMissionLogEntry::UpdateActiveObjective>` (texte d'objectif, souvent avec des variables non résolues : `Go to ~mission(Location)`, ou `Ship Health:` toutes les 5 s pendant une défense de vaisseau), `<MissionEnded>` (`MISSION_STATE_COMPLETED|FAILED`), `<MissionShared>` (`ownerId`, `missionId`).
- `LoadShopInventoryData` … `shopName[SCShop_Admin_…] commodityName[…]` : ouverture d'un écran de shop (tailles de boîtes).

## Résistance aux changements de format

`/game stats` audite chaque reconnaisseur : lignes portant le marqueur / lignes reconnues. Marqueur vu mais **jamais** reconnu ⇒ alerte « format probablement changé » avec des exemples (`events.audit`). Le vaisseau est cherché à part (segment `|…|`) : s'il disparaît, l'événement reste reconnu.
