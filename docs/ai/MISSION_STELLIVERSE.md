# Mission : améliorer uexinfo en s'inspirant de Stelliverse

> Consignes de l'utilisateur, reçues le 2026-10-06. Elles font foi pour toute la mission.

## Règle de licence (non négociable)

Stelliverse (https://gitlab.com/drrakendu78/Stelliverse) est sous **PolyForm Strict 1.0.0**.
- **Interdit :** copier, traduire ou paraphraser son code (Rust, JS, structure des fonctions, noms internes, commentaires).
- **Autorisé :** les faits sur le jeu (formats de lignes du `Game.log`, emplacements de fichiers, API publiques, idées de fonctionnalités).
- Tout écrire à zéro (clean-room). Lire son code donne une spécification, jamais une implémentation.

## Règle des valeurs métier

- Ne jamais décider seul qu'une valeur est principale, secondaire, par défaut, un seuil ou à ignorer (prix, SCU, terminal, tri, filtre…).
- En cas d'ambiguïté : **poser la question avant de coder**.
- Toute valeur métier est fixée par un test (fixture → sortie attendue).
- Ne modifier aucune valeur existante sans le signaler explicitement dans le résumé.

## Étapes

1. **Audit en lecture seule** → `docs/ai/AUDIT_2026-10-06.md`. Attendre la validation.
2. **Connaissances tirées de Stelliverse** : liste priorisée (valeur, difficulté, dépendances Python). Attendre le choix.
3. **Implémentation feature par feature** :
   - parseur pur (sans I/O) séparé du watcher (tail du fichier) ;
   - tests pytest d'abord, avec de **vrais** extraits de `Game.log` dans `tests/fixtures/` (les demander, ne jamais en inventer) ;
   - mode `--replay fichier.log` ;
   - logs de debug activables (ligne matchée → événement produit) ;
   - un petit commit par feature.

## Annexe : faits sur le jeu (à revérifier sur de vrais logs)

- `Game.log` : `<install>\StarCitizen\LIVE\Game.log`, anciens logs dans `LIVE\logbackups\`. Version : `build_manifest.id`.
- Ligne : `<2026-08-07T23:45:07.970Z> [Notice] <Categorie> message…`
- Lecture incrémentale (seek), tolérante à la rotation et à l'absence du fichier. Pré-filtre par sous-chaîne avant les regex. Relire la fin au démarrage.
- Historique : trier les fichiers par **premier horodatage**, pas par nom.
- Commerce : `SendCommodityBuyRequest` / `SendCommoditySellRequest` (`amount`, `resourceGUID`, `quantity` dont l'unité, SCU ou cSCU, reste à vérifier). Objets : `SendStandardItemBuyRequest`.
- Hauling : `CreateMarker … missionId, generator name, contract` ; « Contract Accepted: » / « Nouvelle mission : » ; « New Objective: Deliver N/M SCU of X to Y » / « Nouvel objectif : Livrer N/M SCU de X à Y » ; `<EndMission> … MissionId … CompletionType`. Environ 14 % des contrats interstellaires ne donnent que le système de destination.
- Lieu : `<Player Selected Quantum Target - Local…>`, `<Quantum Drive Arrived…>`, `<Changing Solar System> … from A to B`.
- Session : `OnClientSpawned`, `EndSession` / `SystemQuit`, `AccountLoginCharacterStatus_Character`.
- Combat : `Actor Death`, `Vehicle Destruction` (destroy_level 1 ou 2), `FatalCollision`, Spawn Flow (hôpital).
- Inventaire : noms de catégorie qui changent selon les patchs, donc prévoir des alias.
- À ignorer : `OnEntityEnterZone` / `OnEntityLeaveZone` (spam).
- Autres sources : UEX `commodities_prices_all`, scmdb.net `merged-{version}.json`, `global.ini` FR, `Data.p4k` (`scdatatools`), OCR (`mss`, `winrt-Windows.Media.Ocr`, liste fermée de candidats).
- Pistes commerce : capacité du vaisseau, capital, stock et demande, distance et temps, routes en plusieurs étapes, profit réalisé tiré du `Game.log`.
