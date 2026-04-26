# UEXInfo — Liste exhaustive des commandes CLI

> Toutes les commandes commencent par `/` (espaces/tabulations tolérés en préfixe)
> Autocomplétion disponible via `Tab`
> Aide contextuelle : `/help <commande>`

---

## Syntaxe générale

```
/commande [sous-commande] [argument] [--option valeur]
```

---

## /help — Aide

**Décorateur :** `@register("help", "h", "?")`

**Sous-commandes :**
- `/help` : Aide générale
- `/help <commande>` : Aide sur une commande spécifique

---

## /config — Configuration

**Décorateur :** `@register("config", "c")`

**Sous-commandes :**
- `/config` : Afficher la configuration actuelle
- `/config ship add <nom>` : Ajouter un vaisseau disponible
- `/config ship remove <nom>` : Retirer un vaisseau
- `/config ship set <nom>` : Définir le vaisseau actif
- `/config ship cargo <nom> <scu>` : Définir le cargo SCU d'un vaisseau
- `/config trade profit <aUEC>` : Profit minimum par SCU
- `/config trade margin <pct>` : Marge minimale en %
- `/config trade illegal on|off` : Autoriser les commodités illégales
- `/config cache ttl <secondes>` : TTL du cache prix
- `/config cache clear` : Vider tout le cache
- `/config scan mode ocr|log|confirm` : Mode de scan
- `/config scan tesseract <path>` : Chemin tesseract.exe
- `/config scan logpath <path>` : Chemin app.log SC-Datarunner
- `/config scan screenshots <path>` : Dossier screenshots SC
- `/config scan auto_ocr on|off` : OCR automatique dès détection
- `/config scan hour <n>` : Fenêtre /mission scan en heures
- `/config scan session_gap <min>` : Gap entre sessions en minutes
- `/config close normal|dblclick` : Comportement du bouton ✕ de l'overlay
- `/config clock on|off` : Horloge en fond de l'overlay
- `/config cmdhistory <n>` : Nombre de commandes+résultats conservés
- `/config player` : Afficher la config joueur

---

## /ship — Gestion des vaisseaux

**Décorateur :** `@register("ship", "sh")`

**Sous-commandes :**
- `/ship list` : Lister les vaisseaux configurés
- `/ship add <nom>` : Ajouter un ou plusieurs vaisseaux
- `/ship remove <nom>` : Retirer un vaisseau
- `/ship set <nom>` : Définir le vaisseau actif
- `/ship cargo <nom>` : Afficher les grilles cargo du vaisseau
- `/ship cargo <nom> <32xN> [16xN] …` : Définir les grilles (particulier)
- `/ship cargo <nom> --all <32xN> [16xN] …` : Définir les grilles (général)
- `/ship cargo <nom> --all` : Afficher la config générale du modèle
- `/ship cargo <nom> --clear` : Effacer l'override général du modèle

---

## /go — Position courante et destination

**Décorateur :** `@register("go", "g", "lieu")`

**Sous-commandes :**
- `/go` : Afficher position courante et destination
- `/go <lieu>` : Définir la position courante
- `/go from <lieu>` : Définir le point de départ
- `/go to <lieu>` : Définir la destination
- `/go clear` : Réinitialiser position et destination

---

## /lieu — Alias de /go

**Décorateur :** `@register("lieu")`

---

## /arriver — Commande non documentée

**Décorateur :** `@register("arriver", "arriv├®", "arrive", "arrived")`

---

## /dest — Destination

**Décorateur :** `@register("dest", "d")`

**Sous-commandes :**
- `/dest` : Afficher la destination courante
- `/dest <lieu>` : Définir la destination
- `/dest clear` : Effacer la destination
- `/dest effacer` : Alias de clear

---

## /select — Filtres actifs

**Décorateur :** `@register("select", "sel")`

**Sous-commandes :**
- `/select` : Afficher les filtres actifs
- `/select <type> <nom>` : Raccourci ajout de filtre
- `/select add <type> <nom>` : Ajouter un filtre
- `/select remove <type> <nom>` : Retirer un filtre
- `/select clear [type]` : Supprimer les filtres

---

## /player — Gestion du joueur

**Décorateur :** `@register("player", "p")`

**Sous-commandes :**
- `/player info` : État joueur (vaisseau, position, dest)
- `/player ship add <nom> [scu]` : Ajouter un vaisseau
- `/player ship set <nom>` : Vaisseau actif
- `/player ship scu <nom> <n>` : Capacité cargo en SCU
- `/player ship remove <nom>` : Supprimer un vaisseau
- `/player @<lieu>` : Définir la position courante
- `/player dest @<lieu>` : Définir la destination

---

## /scan — Scanner un terminal

**Décorateur :** `@register("scan", "s")`

**Sous-commandes :**
- `/scan` : Dernier screenshot Star Citizen (OCR)
- `/scan ecran` : Capture la fenêtre SC en direct (ou presse-papiers)
- `/scan screen` : Alias de /scan ecran
- `/scan screenshot <fichier>` : Scanner un fichier image directement
- `/scan log` : Lire TOUS les scans du log SC-Datarunner
- `/scan log new` : Lire uniquement les nouveaux scans (incrémental)
- `/scan log reset` : Remettre l'offset à 0
- `/scan status` : Afficher le dernier résultat
- `/scan history [n]` : Historique des n derniers scans

---

## /auto — Contrôle des automatisations

**Décorateur :** `@register("auto")`

**Sous-commandes :**
- `/auto` : Afficher l'état des automatisations
- `/auto log on|off` : Activer/désactiver la lecture auto du log
- `/auto signal.scan on|off` : Activer/désactiver le signalement des nouveaux scans
- `/auto log.accept on|off` : Activer/désactiver la validation auto des valeurs log

---

## /undo — Annuler le dernier scan

**Décorateur :** `@register("undo")`

---

## /trade — Recherche commerciale

**Décorateur :** `@register("trade", "t")`

**Sous-commandes :**
- `/trade` : Résumé buy+sell pour une commodité
- `/trade buy <commodité>` : Où acheter une commodité
- `/trade sell <commodité>` : Où vendre une commodité
- `/trade <commodité>` : Résumé buy+sell pour une commodité
- `/trade from <terminal>` : Bilan au départ d'un terminal
- `/trade to <terminal>` : Bilan vers un terminal destination
- `/trade best` : Meilleures routes (position courante)
- `/trade best --profit` : Trier par profit total
- `/trade best --roi` : Trier par ROI
- `/trade best --scu <n>` : Pour n SCU de cargo
- `/trade compare <commodité>` : Comparer UEX et sc-trade.tools
- `/trade sctrade` : Utilise sc-trade.tools pour trouver les meilleures routes

---

## /route — Routes commerciales

**Décorateur :** `@register("route", "itineraire", "itin├®raire", "chemin")`

**Sous-commandes :**
- `/route` : Routes depuis position courante
- `/route from <terminal>` : Routes depuis un terminal
- `/route to <terminal>` : Routes vers une destination
- `/route --commodity <nom>` : Filtrer sur une commodité
- `/route --min-profit <aUEC>` : Profit minimum total
- `/route --scu <n>` : Taille cargo

---

## /plan — Plan de vol multi-étapes

**Décorateur :** Non implémenté

---

## /info — Informations détaillées

**Décorateur :** `@register("info", "i", "?")`

**Sous-commandes :**
- `/info <lieu>` : Recherche libre (terminal, commodité, vaisseau)
- `/info terminal <nom>` : Détail d'un terminal
- `/info commodity <nom>` : Détail d'une commodité
- `/info ship <nom>` : Fiche vaisseau (achat, location, cargo)
- `/info list [filtre]` : Liste des commodités (tri alphabétique)
- `/info list -p+ [filtre]` : Tri par prix croissant
- `/info list -p- [filtre]` : Tri par prix décroissant
- `/info list -b+ [filtre]` : Tri par bénéfice croissant
- `/info list -b- [filtre]` : Tri par bénéfice décroissant

---

## /explore — Navigation hiérarchique

**Décorateur :** `@register("explore", "x", "exp")`

**Sous-commandes :**
- `/explore` : Liste des catégories navigables
- `/explore <système>` : Planètes et corps dans le système
- `/explore <sys>.<corps>` : Lieux (stations, villes…)
- `/explore <sys>.<corps>.<lieu>` : Terminaux et infos du lieu
- `/explore ship` : Fabricants de vaisseaux
- `/explore ship.<fabricant>` : Vaisseaux d'un fabricant
- `/explore commodity` : Catégories de commodités
- `/explore commodity.<catégorie>` : Commodités de la catégorie

---

## /nav — Réseau de transport

**Décorateur :** `@register("nav", "navigation", "n", "qt", "quantum")`

**Sous-commandes :**
- `/nav` : Stats générales (nœuds, routes, jump points)
- `/nav info` : Identique à /nav seul
- `/nav nodes [système]` : Lister les nœuds, filtrable par système
- `/nav edges [lieu]` : Lister les routes, filtrable par nœud de départ
- `/nav jumps` : Lister les jump points inter-systèmes
- `/nav route <de> <vers>` : Calcul du plus court chemin QT entre deux lieux
- `/nav add-route <de> <vers> <Gm> [type]` : Ajouter une route manuellement
- `/nav add-jump <nom> <sys1> <sys2> <entrée> <sortie> [S|M|L]` : Ajouter un jump point
- `/nav remove-route <de> <vers>` : Supprimer une route
- `/nav remove-jump <nom>` : Supprimer un jump point
- `/nav save` : Sauvegarder les modifications
- `/nav raz` : Réinitialiser depuis le fichier source
- `/nav populate` : Interroge l'API UEX pour toutes les commodités achetables et importe automatiquement les distances entre terminaux dans le graphe

---

## /mission — Catalogue de missions

**Décorateur :** `@register("mission", "m")`

**Sous-commandes :**
- `/mission list` : Catalogue validé
- `/mission scan` : OCR récents → sélection
- `/mission scan all` : Toute la screenshot_db
- `/mission scan today` : Captures depuis minuit
- `/mission scan terminal` : Terminaux scannés dans la base
- `/mission add` : Depuis le dernier /scan
- `/mission add <fichier.jpg>` : Scanner un screenshot directement
- `/mission add <nom> ...` : Saisie manuelle avec mots-clés
- `/mission edit <id> ...` : Modifier une mission du catalogue
- `/mission remove <id>` : Supprimer du catalogue

---

## /dev — Mode développeur

**Décorateur :** `@register("dev")`

**Sous-commandes :**
- `/dev` : Statut du mode dev et de la DB
- `/dev on|off` : Activer/désactiver le mode dev (persisté)
- `/dev scan import <dossier>` : Importer tous les screenshots d'un dossier
- `/dev scan import <dossier> all` : Réimporter même les fichiers déjà traités
- `/dev scan clear` : Vider la screenshot_db
- `/dev db` : Statistiques et contenu de la screenshot_db
- `/dev db list [n]` : Lister les n dernières entrées
- `/dev calc.missions` : Matrice missions : départ × destination × distance

---

## /debug — Niveau de trace interne

**Décorateur :** `@register("debug")`

**Sous-commandes :**
- `/debug` : Afficher le niveau de trace actuel
- `/debug <0-5>` : Définir le niveau (0 = off, 5 = max)

---

## /voyage — Planification de voyages

**Décorateur :** `@register("voyage", "v")`

**Sous-commandes :**
- `/voyage` : Afficher le voyage actif (ou la liste)
- `/voyage on` : Activer le dernier voyage ou en créer un
- `/voyage off` : Désactiver (voyage conservé)
- `/voyage new [nom]` : Créer un nouveau voyage et l'activer
- `/voyage list` : Missions du voyage actif
- `/voyage list --trajets` : Liste de tous les voyages
- `/voyage add [m1 m2 ...]` : Ajouter des missions au voyage actif
- `/voyage remove <m>` : Retirer une mission
- `/voyage clear` : Vider toutes les missions du voyage
- `/voyage name <nom>` : Renommer le voyage actif
- `/voyage copy [n|nom]` : Copier/fusionner vers un autre voyage
- `/voyage accept` : Valider + analyser, désactiver le voyage
- `/voyage later` : Sauvegarder sans analyser, désactiver
- `/voyage cancel` : Annuler les modifications

---

## /refresh — Mise à jour du cache

**Décorateur :** `@register("refresh", "r", "rf")`

**Sous-commandes :**
- `/refresh` : Rafraîchir le cache prix (TTL expiré)
- `/refresh all` : Forcer le refresh complet (statique + prix)
- `/refresh static` : Rafraîchir données statiques
- `/refresh prices` : Rafraîchir les prix uniquement
- `/refresh sctrade` : Rafraîchir données sc-trade.tools
- `/refresh status` : Afficher l'état du cache

---

## /history — Historique des commandes

**Décorateur :** `@register("history", "hist")`

**Sous-commandes :**
- `/history [n]` : Afficher les n dernières commandes
- `/history stats` : Statistiques
- `/history clear` : Effacer l'historique

---

## /= — Calculatrice

**Décorateur :** `@register("=", "calc", "calculette", "calcul")`

**Sous-commandes :**
- `= <expression>` : Calculer une expression arithmétique

---

## /exit — Quitter

**Décorateur :** Non implémenté

**Sous-commandes :**
- `/exit`
- `/quit`
- `/bye`

---

## /sync — Synchronisation

**Décorateur :** `@register("sync", "resync")`

---

## /resync — Alias de /sync

**Décorateur :** Non implémenté

---

*Liste exhaustive des commandes — uexinfo v0.1*
