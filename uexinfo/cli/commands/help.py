"""Commande /help."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.display.formatter import console, section
from uexinfo.display import colors as C

_COMMANDS = {
    "help":    "Aide générale ou /help <commande>",
    "config":  "Configuration : vaisseaux, préférences, trade",
    "go":      "Définir la position courante ou destination",
    "lieu":    "Alias de /go",
    "select":  "Filtres actifs (système, planète, station, terminal…)",
    "trade":   "Recherche de commodités et opportunités de trading",
    "route":   "Calcul de routes commerciales rentables",
    "plan":    "Plan de vol multi-étapes",
    "info":    "Détail d'un terminal / commodité / vaisseau",
    "refresh": "Rafraîchir le cache (prix, données statiques)",
    "exit":    "Quitter l'application",
}

_DETAILS = {
    "config": (
        "/config                          Afficher la configuration\n"
        "/config ship add <nom>           Ajouter un vaisseau\n"
        "/config ship remove <nom>        Retirer un vaisseau\n"
        "/config ship set <nom>           Définir le vaisseau actif\n"
        "/config ship cargo <nom> <scu>   Définir le cargo en SCU\n"
        "/config trade profit <aUEC>      Profit minimum par SCU\n"
        "/config trade margin <pct>       Marge minimale en %\n"
        "/config trade illegal on|off     Autoriser les commodités illégales\n"
        "/config cache ttl <secondes>     TTL du cache statique\n"
        "/config cache clear              Vider le cache"
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


@register("help")
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
