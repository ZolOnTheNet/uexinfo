"""Commande /select — filtres actifs."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section

_VALID = ("system", "planet", "station", "terminal", "city", "outpost")
_KEY = {t: t + "s" for t in _VALID}  # planet -> planets


def _show_help() -> None:
    from uexinfo.display.formatter import section
    from uexinfo.display import colors as C
    section("Aide — /select")
    console.print(
        f"[bold]Usage :[/bold]\n"
        f"  [bold {C.UEX}]/select[/bold {C.UEX}]                         Afficher les filtres actifs\n"
        f"  [bold {C.UEX}]/select add <type> <nom>[/bold {C.UEX}]         Ajouter un filtre\n"
        f"  [bold {C.UEX}]/select remove <type> <nom>[/bold {C.UEX}]      Retirer un filtre\n"
        f"  [bold {C.UEX}]/select clear [type][/bold {C.UEX}]             Supprimer les filtres (tous ou par type)\n"
        f"  [bold {C.UEX}]/select <type> <nom>[/bold {C.UEX}]             Raccourci ajout de filtre\n\n"
        f"[bold]Types valides :[/bold]\n"
        f"  [{C.UEX}]system[/{C.UEX}] | [{C.UEX}]planet[/{C.UEX}] | [{C.UEX}]station[/{C.UEX}] | [{C.UEX}]terminal[/{C.UEX}] | [{C.UEX}]city[/{C.UEX}] | [{C.UEX}]outpost[/{C.UEX}]\n\n"
        f"[{C.DIM}]Exemple : /select add system Stanton[/{C.DIM}]"
    )


@register("select", "sel")
def cmd_select(args: list[str], ctx) -> None:
    """Filtres actifs (système, planète, station, terminal…)."""
    filters = ctx.cfg.setdefault("filters", {})

    if args and args[0] in ("help", "?", "--help"):
        _show_help()
        return

    if not args:
        _show(filters)
        return

    sub = args[0].lower()

    if sub == "clear":
        ftype = args[1].lower() if len(args) > 1 else None
        if ftype:
            if ftype not in _VALID:
                print_error(f"Type inconnu : {ftype}  ({' | '.join(_VALID)})")
                return
            filters[_KEY[ftype]] = []
        else:
            for k in _KEY.values():
                filters[k] = []
        settings.save(ctx.cfg)
        print_ok("Filtres supprimés")

    elif sub == "add":
        if len(args) < 3:
            print_error("Usage: /select add <type> <nom>")
            return
        _add(filters, args[1].lower(), " ".join(args[2:]))
        settings.save(ctx.cfg)

    elif sub == "remove":
        if len(args) < 3:
            print_error("Usage: /select remove <type> <nom>")
            return
        _remove(filters, args[1].lower(), " ".join(args[2:]))
        settings.save(ctx.cfg)

    elif sub in _VALID:
        name = " ".join(args[1:])
        if not name:
            print_error(f"Spécifie un nom après '{sub}'")
            return
        _add(filters, sub, name)
        settings.save(ctx.cfg)

    else:
        print_error(f"Type inconnu : {sub}  ({' | '.join(_VALID)})")


def _add(filters: dict, ftype: str, name: str) -> None:
    if ftype not in _VALID:
        print_error(f"Type inconnu : {ftype}  ({' | '.join(_VALID)})")
        return
    lst = filters.setdefault(_KEY[ftype], [])
    if name not in lst:
        lst.append(name)
        print_ok(f"Filtre [{C.UEX}]{ftype}[/{C.UEX}] ajouté : {name}")
    else:
        print_warn(f"{name} est déjà dans les filtres {ftype}")


def _remove(filters: dict, ftype: str, name: str) -> None:
    if ftype not in _VALID:
        print_error(f"Type inconnu : {ftype}")
        return
    lst = filters.get(_KEY[ftype], [])
    if name in lst:
        lst.remove(name)
        print_ok(f"Filtre retiré : {name}")
    else:
        print_error(f"Filtre introuvable : {name}")


def _show(filters: dict) -> None:
    section("Filtres actifs")
    has_any = False
    labels = {"systems": "Systèmes", "planets": "Planètes", "stations": "Stations",
              "terminals": "Terminaux", "cities": "Villes", "outposts": "Avant-postes"}
    for key, label in labels.items():
        vals = filters.get(key, [])
        if vals:
            items = "  ".join(f"[{C.UEX}]{v}[/{C.UEX}]" for v in vals)
            console.print(f"  [bold]{label} :[/bold]  {items}")
            has_any = True
    if not has_any:
        console.print(f"  [{C.DIM}]Aucun filtre actif — /select <type> <nom> pour en ajouter[/{C.DIM}]")
