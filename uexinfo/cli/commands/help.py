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
    "refresh": "Rafraîchir le cache (prix, données statiques)",
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
        "/config player                        Afficher la config joueur"
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
    "route": (
        "/route                           Routes depuis position courante\n"
        "/route from <terminal>           Routes depuis un terminal\n"
        "/route to <terminal>             Routes vers une destination\n"
        "/route --commodity <nom>         Filtrer sur une commodité\n"
        "/route --min-profit <aUEC>       Profit minimum\n"
        "/route --scu <n>                 Taille cargo"
    ),
}


@register("help", "h", "?")
def cmd_help(args: list[str], ctx) -> None:
    if args:
        topic = args[0].lstrip("/").lower()
        if topic in _DETAILS:
            section(f"Aide — /{topic}")
            console.print(_DETAILS[topic])
        elif topic in _COMMANDS:
            console.print(f"[{C.LABEL}]/{topic}[/{C.LABEL}]  {_COMMANDS[topic]}")
        else:
            console.print(f"[{C.WARNING}]Pas d'aide pour « {topic} »[/{C.WARNING}]")
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
