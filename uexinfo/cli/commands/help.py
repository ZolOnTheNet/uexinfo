"""Commande /help."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.display.formatter import console, section
from uexinfo.display import colors as C

_COMMANDS = {
    "help":    "Aide générale ou /help <commande>",
    "config":  "Configuration : vaisseaux, préférences, trade, scan",
    "ship":    "Raccourci /config ship — gérer les vaisseaux configurés",
    "go":      "Définir la position courante ou destination",
    "lieu":    "Alias de /go",
    "select":  "Filtres actifs (système, planète, station, terminal…)",
    "player":  "Gérer le joueur : vaisseau, position, destination",
    "scan":    "Scanner un terminal (OCR screenshot ou log SC-Datarunner)",
    "auto":    "Contrôle des automatisations (log, signalement, validation)",
    "undo":    "Annuler le dernier scan",
    "trade":   "Recherche de commodités et opportunités de trading",
    "route":   "Calcul de routes commerciales rentables",
    "plan":    "Plan de vol multi-étapes",
    "info":    "Détail d'un terminal ou d'une commodité",
    "explore": "Navigation hiérarchique : systèmes, vaisseaux, commodités",
    "nav":     "Réseau de transport : nœuds, routes QT, jump points, itinéraires",
    "mission": "Catalogue de missions de livraison (add, edit, remove, list)",
    "voyage":  "Planification de voyages — groupe de missions à accomplir",
    "refresh": "Rafraîchir le cache (prix, données statiques)",
    "dest":    "Définir ou effacer la destination  (/dest clear pour effacer)",
    "=":       "Calculatrice  (/calc — ex: = 16x6  = 100/3  = (12+8)*5)",
    "exit":    "Quitter l'application  (/quit et /bye aussi)",
}

_DETAILS = {
    "player": (
        "/player info                      État joueur (vaisseau, position, dest)\n"
        "/player ship add <nom> [scu]      Ajouter un vaisseau\n"
        "/player ship set <nom>            Vaisseau actif\n"
        "/player ship scu <nom> <n>        Capacité cargo en SCU\n"
        "/player ship remove <nom>         Supprimer un vaisseau\n"
        "/player @<lieu>                   Définir la position courante\n"
        "/player dest @<lieu>              Définir la destination\n\n"
        "@<lieu>  Ex: @gaslight   @stanton.hurston.lorville\n"
        "         Tab après @ pour compléter."
    ),
    "scan": (
        "/scan                        Dernier screenshot Star Citizen (OCR)\n"
        "/scan ecran                  Capture la fenêtre SC en direct (ou presse-papiers)\n"
        "/scan screen                 Alias de /scan ecran\n"
        "/scan screenshot <fichier>   Scanner un fichier image directement\n"
        "/scan log                    Lire les nouveaux scans du log SC-Datarunner\n"
        "/scan log all                Relire tout le log depuis le début\n"
        "/scan log reset              Remettre l'offset à 0 (prochaine lecture = tout)\n"
        "/scan status                 Afficher le dernier résultat\n"
        "/scan history [n]            Historique des n derniers scans (défaut 5)\n\n"
        "Lecture automatique du log :\n"
        "  Si sc_log_path est défini et SC-Datarunner est actif, le log est surveillé\n"
        "  en permanence.  Avant chaque /info, les nouvelles entrées sont lues\n"
        "  silencieusement.  Après les autres commandes, les nouveaux scans sont\n"
        "  affichés automatiquement.  Contrôler avec : auto log on|off\n\n"
        "Nouveaux screenshots :\n"
        "  Si sc_screenshots_dir est défini, les nouveaux fichiers SC sont signalés\n"
        "  après chaque commande.  Contrôler avec : auto signal.scan on|off\n\n"
        "Priorité /scan ecran : fenêtre SC → presse-papiers → dernier screenshot\n\n"
        "Les prix issus d'un scan joueur sont fiables (non en italique) et\n"
        "restent prioritaires sur UEX tant qu'aucune mise à jour plus récente n'existe."
    ),
    "auto": (
        "auto                         Afficher l'état des automatisations\n"
        "auto log on|off              Activer/désactiver la lecture auto du log\n"
        "auto signal.scan on|off      Activer/désactiver le signalement des nouveaux scans\n"
        "auto log.accept on|off       Activer/désactiver la validation auto des valeurs log\n\n"
        "Fonctionnement :\n"
        "  auto log on       → le log SC-Datarunner est surveillé (mtime).\n"
        "                      Avant /info : mise à jour silencieuse de ctx.last_scan.\n"
        "                      Après les autres commandes : affichage des nouveaux scans.\n"
        "  auto signal.scan  → signale aussi les nouveaux screenshots SC détectés.\n"
        "  auto log.accept   → si off, les scans sont affichés mais non stockés en\n"
        "                      historique (confirmation manuelle requise).\n\n"
        "Note : Le / est optionnel — 'auto log on' fonctionne sans /."
    ),
    "undo": (
        "undo                         Annuler le dernier scan (log, screenshot ou OCR)\n\n"
        "Supprime le scan de l'historique et remet ctx.last_scan au scan précédent.\n"
        "Utile si SC-Datarunner a capturé une erreur ou une mauvaise valeur."
    ),
    "ship": (
        "/ship list                     Lister les vaisseaux configurés\n"
        "/ship add <nom>[, <nom2>, …]   Ajouter un ou plusieurs vaisseaux\n"
        "/ship remove <nom>             Retirer un vaisseau\n"
        "/ship set <nom>                Définir le vaisseau actif\n"
        "/ship cargo <nom> <scu>        Définir la capacité cargo en SCU\n\n"
        "Alias direct de /config ship — Tab pour compléter les noms de vaisseaux.\n"
        "Exemples :\n"
        "  /ship add Drake_Cutlass_Black\n"
        "  /ship set Drake_Cutlass_Black\n"
        "  /ship cargo Drake_Cutlass_Black 46\n"
        "  /ship list"
    ),
    "config": (
        "/config                               Afficher la configuration\n"
        "/config ship add <nom>[, <nom2>, …]   Ajouter un ou plusieurs vaisseaux\n"
        "/config ship remove <nom>             Retirer un vaisseau\n"
        "/config ship set <nom>                Définir le vaisseau actif\n"
        "/config ship cargo <nom> <scu>        Définir le cargo en SCU\n"
        "/config trade profit <aUEC>           Profit minimum par SCU\n"
        "/config trade margin <pct>            Marge minimale en %\n"
        "/config trade illegal on|off          Autoriser les commodités illégales\n"
        "/config cache ttl <secondes>          TTL du cache statique\n"
        "/config cache clear                   Vider le cache\n"
        "/config scan mode ocr|log|confirm     Mode de scan\n"
        "/config scan tesseract <path>         Chemin tesseract.exe\n"
        "/config scan logpath <path>           Chemin app.log SC-Datarunner\n"
        "/config scan screenshots <path>       Dossier screenshots SC\n"
        "/config close normal|dblclick         Comportement du bouton ✕ de l'overlay\n"
        "/config player                        Afficher la config joueur\n\n"
        "/help config close  → détail du comportement de fermeture"
    ),
    "config close": (
        "/config close normal|dblclick\n\n"
        "  Contrôle le comportement du bouton ✕ de la fenêtre overlay.\n\n"
        "  normal    (défaut)\n"
        "    Un clic sur ✕ ferme définitivement l'overlay.\n"
        "    Équivalent à taper /quit.\n\n"
        "  dblclick\n"
        "    Un clic sur ✕ masque la fenêtre (comme la hotkey alt+shift+u).\n"
        "    Un double-clic sur ✕ ferme définitivement.\n"
        "    Utile quand on bascule souvent entre Star Citizen et l'overlay.\n\n"
        "  Note : le mode bouton ✕ OS (frameless=false) fonctionne de la même\n"
        "  façon : 1er clic sur la croix native → masquer ; 2e clic < 500ms → fermer.\n\n"
        "  Exemples :\n"
        "    /config close dblclick    Activer le mode double-clic\n"
        "    /config close normal      Revenir au comportement classique\n\n"
        "  Le changement est effectif au prochain lancement de l'overlay."
    ),
    "explore": (
        "/explore                         Liste des catégories navigables\n"
        "/explore <système>               Planètes et corps dans le système\n"
        "/explore <sys>.<corps>           Lieux (stations, villes…)\n"
        "/explore <sys>.<corps>.<lieu>    Terminaux et infos du lieu\n"
        "/explore ship                    Fabricants de vaisseaux\n"
        "/explore ship.<fabricant>        Vaisseaux d'un fabricant\n"
        "/explore commodity               Catégories de commodités\n"
        "/explore commodity.<catégorie>   Commodités de la catégorie\n\n"
        "Navigation par point, Tab complétion à chaque niveau.\n"
        "Exemples :\n"
        "  /explore stanton\n"
        "  /explore stanton.hurston.lorville\n"
        "  /explore pyro.bloom\n"
        "  /explore ship.anvil\n"
        "  /explore commodity.metal"
    ),
    "info": (
        "/info <nom>                  Recherche libre (terminal, commodité, vaisseau)\n"
        "/info terminal <nom>         Détail d'un terminal (lieu, système…)\n"
        "/info commodity <nom>        Détail d'une commodité (prix UEX, flags…)\n"
        "/info ship <nom>             Fiche vaisseau (achat, location, cargo)\n\n"
        "Filtres système (commodités) :\n"
        "  /info --all <commodité>          Tous les systèmes\n"
        "  /info --Nyx,Pyro <commodité>     Filtrer sur Nyx et Pyro\n"
        "  /info --Cur,Nyx <commodité>      Système courant + Nyx\n\n"
        "Exemples :\n"
        "  /info GrimHEX\n"
        "  /info Laranite\n"
        "  /info --all Copper\n"
        "  /info ship Cutlass Black\n"
        "  /info terminal Area 18"
    ),
    "go": (
        "/go                    Afficher position et destination\n"
        "/go <lieu>             Définir la position courante\n"
        "/go from <lieu>        Définir le point de départ\n"
        "/go to <lieu>          Définir la destination\n"
        "/go clear              Réinitialiser\n\n"
        "<lieu> = nom de terminal, station, ville, planète, système"
    ),
    "select": (
        "/select                          Afficher les filtres actifs\n"
        "/select <type> <nom>             Raccourci ajout de filtre\n"
        "/select add <type> <nom>         Ajouter un filtre\n"
        "/select remove <type> <nom>      Retirer un filtre\n"
        "/select clear [type]             Supprimer les filtres\n\n"
        "Types : system | planet | station | terminal | city | outpost"
    ),
    "refresh": (
        "/refresh               Rafraîchir les prix (si TTL expiré)\n"
        "/refresh all           Forcer le refresh complet\n"
        "/refresh static        Données statiques uniquement\n"
        "/refresh prices        Prix uniquement\n"
        "/refresh sctrade       Données sc-trade.tools\n"
        "/refresh status        État du cache (âge, nombre d'entrées)"
    ),
    "trade": (
        "/trade buy <commodité>           Où acheter\n"
        "/trade sell <commodité>          Où vendre\n"
        "/trade <commodité>               Résumé buy + sell\n"
        "/trade best                      Meilleures routes (position courante)\n"
        "/trade best --profit             Trier par profit total\n"
        "/trade best --roi                Trier par ROI\n"
        "/trade best --scu <n>            Pour n SCU de cargo\n"
        "/trade compare <commodité>       Comparer UEX et sc-trade.tools"
    ),
    "nav": (
        "/nav                             Stats du réseau (nœuds, routes, jump points)\n"
        "/nav info                        Idem — même chose que /nav seul\n"
        "/nav nodes [système]             Lister les nœuds (filtrable par système)\n"
        "/nav edges [lieu]                Lister les routes (filtrable par nœud)\n"
        "/nav jumps                       Lister les jump points inter-systèmes\n"
        "/nav route <de> <vers>           Calculer le plus court chemin QT\n"
        "/nav add-route <de> <vers> <Gm> [type]   Ajouter une route manuellement\n"
        "/nav add-jump <nom> <sys1> <sys2> <entrée> <sortie> [S|M|L]\n"
        "                                 Ajouter un jump point\n"
        "/nav remove-route <de> <vers>    Supprimer une route\n"
        "/nav remove-jump <nom>           Supprimer un jump point\n"
        "/nav save                        Sauvegarder les modifications\n"
        "/nav raz                         Réinitialiser depuis le fichier source\n\n"
        "Types de route : quantum (défaut) | ground | landing | jump\n\n"
        "Exemples :\n"
        "  /nav route GrimHEX Area18\n"
        "  /nav route Lorville to Port Tressler\n"
        "  /nav nodes stanton\n"
        "  /nav add-route GrimHEX \"Port Tressler\" 1.8 quantum\n"
        "  /nav add-jump Stanton-Pyro stanton pyro \"Aaron Halo\" \"Pyro Gateway\" L\n\n"
        "Aliases : /navigation /n /qt /quantum\n"
        "Les modifications ne sont pas sauvegardées automatiquement — pensez à /nav save.\n\n"
        "/nav populate\n"
        "  Interroge l'API UEX pour toutes les commodités achetables et importe\n"
        "  automatiquement les distances entre terminaux dans le graphe.\n"
        "  ~60 requêtes, couvre la majorité des terminaux actifs.\n"
        "  Aliases : /nav peupler  /nav enrichir  /nav remplir"
    ),
    "dest": (
        "/dest                   Afficher la destination courante\n"
        "/dest <lieu>            Définir la destination (Tab pour compléter)\n"
        "/dest clear             Effacer la destination\n"
        "/dest effacer           Alias de clear\n\n"
        "Aliases : /d\n"
        "Pour effacer les deux (position + destination) : /go clear"
    ),
    "=": (
        "= <expression>               Calculer une expression arithmétique\n\n"
        "Opérateurs :\n"
        "  +  -  *  /    addition, soustraction, multiplication, division\n"
        "  x  X          alias de *  (ex: 16x6 = 96)\n"
        "  //            division entière  (ex: 17//3 = 5)\n"
        "  %             modulo / reste  (ex: 17%3 = 2)\n"
        "  ( )           parenthèses\n\n"
        "Décimales : point ou virgule  (ex: 1,5 * 4 = 6)\n\n"
        "Exemples :\n"
        "  = 16x6              → 96\n"
        "  = 100 / 3           → 33.3333\n"
        "  = (12 + 8) * 5      → 100\n"
        "  = 46 * 450 - 12000  → 8 700\n"
        "  = 1234 % 7          → 2\n\n"
        "Alias : /calc  /calculette  /calcul\n"
        "Le / est optionnel — '= 16x6' fonctionne sans /."
    ),
    "route": (
        "/route                           Routes depuis position courante\n"
        "/route from <terminal>           Routes depuis un terminal\n"
        "/route to <terminal>             Routes vers une destination\n"
        "/route --commodity <nom>         Filtrer sur une commodité\n"
        "/route --min-profit <aUEC>       Profit minimum\n"
        "/route --scu <n>                 Taille cargo"
    ),
    "mission": (
        "/mission list                 Catalogue de toutes les missions\n"
        "/mission add                  Depuis le dernier scan (/scan d'abord)\n"
        "/mission add <fichier.jpg>    Scanner un screenshot de contrat directement\n"
        "/mission add <nom> ...        Saisie manuelle avec mots-clés\n"
        "/mission edit <id> ...        Modifier une mission existante\n"
        "/mission remove <id>          Supprimer une mission du catalogue\n\n"
        "Alias : /m\n"
        "/help mission add    → syntaxe complète de l'ajout manuel\n"
        "/help mission edit   → modifier nom, récompense, objectifs\n\n"
        "Icônes dans la liste :\n"
        "  ⏱  au moins un objectif avec délai (TDD, shop, delay)\n"
        "  ⊙  synergies : même départ que d'autres missions du voyage\n"
        "  ⊕  synergies : même arrivée\n"
        "  ⇄  synergies : mission relais (destination = départ d'une autre)"
    ),
    "mission add": (
        "/mission add\n"
        "  Depuis le dernier scan OCR (faire /scan ou /scan ecran avant)\n\n"
        "/mission add <fichier.jpg>\n"
        "  Scanne directement un screenshot de contrat de livraison\n\n"
        "/mission add <nom> reward:<aUEC>\n"
        "    [obj:<commodité> from:<source> to:<dest> scu:<n> [tdd|shop|delay:<r>]]+\n\n"
        "  Paramètres :\n"
        "    <nom>           Nom libre de la mission (avant le premier ':')\n"
        "    reward:<n>      Récompense en aUEC  (ex: reward:50000 ou reward:50k)\n"
        "    obj:<commod>    Nom de la commodité à livrer (démarre un objectif)\n"
        "    from:<lieu>     Terminal ou station de collecte\n"
        "    to:<dest>       Terminal ou station de livraison\n"
        "    scu:<n>         Quantité en SCU\n"
        "    tdd             Objectif nécessite le Terminal de Distribution\n"
        "    shop            Objectif nécessite un achat en boutique\n"
        "    delay:<raison>  Délai libre (ex: delay:48h)\n"
        "    note:<texte>    Note libre sur l'objectif\n\n"
        "  Plusieurs objectifs dans la même mission : répéter obj: ... :\n\n"
        "  Exemples :\n"
        "    /mission add \"Livraison Quant\" reward:50000 \\\n"
        "        obj:Quantainium from:HUR-L2 to:GrimHEX scu:12 tdd\n\n"
        "    /mission add Parcours reward:120k \\\n"
        "        obj:Laranite from:ARC-L1 to:Port_Tressler scu:8 \\\n"
        "        obj:Agricium from:Lorville to:Area18 scu:4\n\n"
        "    /mission add Mission_simple reward:30000 \\\n"
        "        obj:Copper from:Daymar to:GrimHEX scu:16"
    ),
    "mission edit": (
        "/mission edit <id> [clés...]\n\n"
        "  Modifie une mission existante. <id> = numéro ou nom de mission.\n\n"
        "  Clés disponibles :\n"
        "    name:<nom>      Renommer la mission\n"
        "    reward:<aUEC>   Modifier la récompense\n"
        "    obj:<commod>    Ajouter un objectif (même syntaxe que add)\n"
        "    from:<lieu>     Source du dernier obj: en cours\n"
        "    to:<dest>       Destination du dernier obj:\n"
        "    scu:<n>         Quantité SCU du dernier obj:\n"
        "    tdd / shop      Contrainte de délai sur le dernier obj:\n"
        "    delay:<raison>  Délai libre sur le dernier obj:\n\n"
        "  Note : edit ajoute les nouveaux objectifs aux existants.\n"
        "  Pour remplacer complètement, supprimer et recréer la mission.\n\n"
        "  Exemples :\n"
        "    /mission edit 3 reward:75000\n"
        "    /mission edit 3 name:\"Nouveau nom\"\n"
        "    /mission edit 3 obj:Agricium from:Lorville to:GrimHEX scu:8"
    ),
    "mission remove": (
        "/mission remove <id>\n\n"
        "  Supprime une mission du catalogue.\n"
        "  <id> = numéro affiché dans /mission list ou nom partiel.\n\n"
        "  Exemples :\n"
        "    /mission remove 3\n"
        "    /mission remove \"Livraison Quant\""
    ),
    "mission list": (
        "/mission list\n\n"
        "  Affiche le catalogue complet avec pour chaque mission :\n"
        "    # — identifiant · Nom · Départ → Arrivée · Distance QT\n"
        "    SCU total · Récompense · Synergies avec d'autres missions\n\n"
        "  Icône ⏱ : un objectif comporte un délai (TDD, shop, delay)\n"
        "  Syn : symboles de synergie entre missions du même voyage\n"
        "    ⊙ même départ  ⊕ même arrivée  ⇄ mission relais\n\n"
        "  Puis utilisez /voyage pour regrouper et planifier les missions."
    ),
    "voyage": (
        "/voyage                  Afficher le voyage actif (ou la liste)\n"
        "/voyage on               Activer le dernier voyage ou en créer un\n"
        "/voyage off              Désactiver (voyage conservé)\n"
        "/voyage new [nom]        Créer un nouveau voyage et l'activer\n"
        "/voyage list             Missions du voyage actif\n"
        "/voyage list --trajets   Liste de tous les voyages\n"
        "/voyage add [m1 m2 ...]  Ajouter des missions au voyage actif\n"
        "/voyage remove <m>       Retirer une mission\n"
        "/voyage clear            Vider toutes les missions du voyage\n"
        "/voyage name <nom>       Renommer le voyage actif\n"
        "/voyage copy [n|nom]     Copier/fusionner vers un autre voyage\n"
        "/voyage accept           Valider + analyser, désactiver le voyage\n"
        "/voyage later            Sauvegarder sans analyser, désactiver\n"
        "/voyage cancel           Annuler les modifications\n\n"
        "Adressage d'un voyage précis :\n"
        "  /voyage 2 list         Par numéro\n"
        "  /voyage -n2 list       Flag -n\n"
        "  /voyage MonVoyage add  Par nom\n\n"
        "Alias : /v\n"
        "/help voyage add     → ajouter des missions en détail\n"
        "/help voyage new     → créer et nommer un voyage\n"
        "/help voyage accept  → valider et analyser un voyage"
    ),
    "voyage new": (
        "/voyage new [nom]\n\n"
        "  Crée un nouveau voyage et l'active immédiatement.\n"
        "  Si aucun nom n'est fourni, un nom automatique est généré.\n"
        "  Le départ est initialisé à la position courante du joueur.\n\n"
        "  Exemples :\n"
        "    /voyage new\n"
        "    /voyage new \"Tournée Hurston\"\n"
        "    /voyage new Mission_du_jour\n\n"
        "  Après création, ajoutez des missions avec /voyage add."
    ),
    "voyage add": (
        "/voyage add [m1 m2 ...]\n\n"
        "  Ajoute une ou plusieurs missions au voyage actif.\n"
        "  <m> = identifiant (#) ou nom de mission affiché dans /mission list.\n\n"
        "  Sans argument : affiche le catalogue avec les missions déjà incluses.\n\n"
        "  Exemples :\n"
        "    /voyage add 1\n"
        "    /voyage add 1 2 3\n"
        "    /voyage add \"Livraison Quant\"\n\n"
        "  Pour adresser un voyage précis :\n"
        "    /voyage 2 add 1 3    → ajouter au voyage #2\n"
        "    /voyage -n2 add 1    → même chose avec flag -n\n\n"
        "  Si aucun voyage n'est actif : /voyage on  ou  /voyage new"
    ),
    "voyage remove": (
        "/voyage remove <m>\n\n"
        "  Retire une ou plusieurs missions du voyage actif.\n"
        "  <m> = identifiant ou nom de mission.\n\n"
        "  Exemples :\n"
        "    /voyage remove 2\n"
        "    /voyage remove 2 5"
    ),
    "voyage accept": (
        "/voyage accept\n\n"
        "  Valide le voyage actif :\n"
        "    1. Affiche le détail des missions\n"
        "    2. Analyse le voyage (lieux, SCU total, récompense, vaisseau suggéré)\n"
        "    3. Désactive le voyage (conservé dans la liste)\n\n"
        "  Utilisez /voyage accept quand vous avez terminé de planifier\n"
        "  et êtes prêt à exécuter les missions.\n\n"
        "  /voyage later  → sauvegarder sans analyser (pour reprendre plus tard)\n"
        "  /voyage off    → désactiver sans rien changer"
    ),
    "voyage list": (
        "/voyage list              Missions du voyage actif (détail)\n"
        "/voyage list --trajets    Tous les voyages (vue synthèse)\n"
        "/voyage                   Identique à /voyage list\n\n"
        "  Vue synthèse (--trajets) : #, nom, missions, SCU, récompense, départ→arrivée\n"
        "  Vue détail : liste des missions avec départ, arrivée, distance, SCU, tags\n\n"
        "  Tags de synergies dans la vue détail :\n"
        "    ⊙  même départ qu'une autre mission du voyage\n"
        "    ⊕  même arrivée qu'une autre mission\n"
        "    ⇄  mission relais (dest d'une = source d'une autre)\n"
        "  ⏱  objectif avec contrainte de temps (TDD, shop, delay)"
    ),
}


@register("help", "h", "?")
def cmd_help(args: list[str], ctx) -> None:
    if args:
        # Essayer d'abord "cmd sub" (ex: "mission add"), puis "cmd" seul
        topic = args[0].lstrip("/").lower()
        sub_topic = f"{topic} {args[1].lower()}" if len(args) >= 2 else ""
        if sub_topic and sub_topic in _DETAILS:
            section(f"Aide — /{sub_topic}")
            console.print(_DETAILS[sub_topic])
        elif topic in _DETAILS:
            section(f"Aide — /{topic}")
            console.print(_DETAILS[topic])
        elif topic in _COMMANDS:
            console.print(f"[{C.LABEL}]/{topic}[/{C.LABEL}]  {_COMMANDS[topic]}")
        else:
            console.print(f"[{C.WARNING}]Pas d'aide pour « {' '.join(args)} »[/{C.WARNING}]")
        return

    section("UEXInfo — Commandes")
    from rich.table import Table
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style=f"bold {C.UEX}", no_wrap=True)
    t.add_column(style=C.NEUTRAL)
    for cmd, desc in _COMMANDS.items():
        t.add_row(f"/{cmd}", desc)
    console.print(t)
    console.print(
        f"\n[{C.DIM}]Tab = autocomplétion  │  ↑↓ = historique  │  /help <cmd> = aide détaillée[/{C.DIM}]"
    )
