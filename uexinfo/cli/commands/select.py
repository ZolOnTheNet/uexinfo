"""Commande /select — filtres actifs."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section

_VALID = ("system", "planet", "station", "terminal", "city", "outpost")
_KEY = {t: t + "s" for t in _VALID}  # planet -> planets

# Alias pluriels acceptés
_PLURAL = {t + "s": t for t in _VALID}

# Types de lieux (pour filtre +/-type)
_TYPES = ("station", "outpost", "city")


def _show_help() -> None:
    section("Aide — /select")
    console.print(
        f"[bold]━━ Filtres par nom ━━[/bold]\n"
        f"  [{C.UEX}]/select add <type> <nom>[/{C.UEX}]      Ajouter un lieu précis\n"
        f"  [{C.UEX}]/select remove <type> <nom>[/{C.UEX}]   Retirer un lieu\n"
        f"  [{C.UEX}]/select <type> <nom>[/{C.UEX}]          Raccourci ajout\n"
        f"  [{C.UEX}]/select clear [type][/{C.UEX}]          Supprimer les filtres\n\n"

        f"  Types de lieux : [{C.UEX}]system planet station terminal city outpost[/{C.UEX}]\n"
        f"  [{C.DIM}]Exemple : /select add system Stanton[/{C.DIM}]\n"
        f"  [{C.DIM}]Exemple : /select station Port Olisar[/{C.DIM}]\n\n"

        f"[bold]━━ Filtres par catégorie ━━[/bold]\n"
        f"  [{C.UEX}]/select +station +outpost -city[/{C.UEX}]   Inclure/exclure des catégories\n\n"

        f"  Catégories : [{C.UEX}]station[/{C.UEX}] | [{C.UEX}]outpost[/{C.UEX}] | [{C.UEX}]city[/{C.UEX}]\n"
        f"  Préfixe [{C.SUCCESS}]+[/{C.SUCCESS}] = inclure, préfixe [{C.LOSS}]-[/{C.LOSS}] = exclure\n"
        f"  Sans préfixe = inclure. Virgules autorisées.\n"
        f"  [{C.DIM}]Exemple : /select +station, +outpost, -city[/{C.DIM}]\n"
        f"  [{C.DIM}]Sans filtre catégorie : tous les types sont autorisés.[/{C.DIM}]\n"
        f"  [{C.DIM}]Avec +station : seules les stations sont autorisées.[/{C.DIM}]\n"
        f"  [{C.DIM}]Avec -city : toutes les catégories sauf les villes.[/{C.DIM}]\n\n"

        f"[bold]━━ Pourquoi filtrer ? ━━[/bold]\n"
        f"  Les stations se chargent/déchargent automatiquement (rapide).\n"
        f"  Les avant-postes requièrent un chargement manuel (~20 min) et sont\n"
        f"  risqués hors zone d'armistice.\n"
        f"  Les cités nécessitent d'atterrir, sortir du spatioport, prendre le métro.\n"
        f"  [{C.DIM}]Conseil : /select +station +outpost -city pour éviter les TDD.[/{C.DIM}]"
    )


def _parse_type_tokens(args: list[str]) -> list[tuple[str, bool]] | None:
    """Parse les tokens +/-type. Retourne [(type, include), ...] ou None si pas un filtre catégorie."""
    # Rejoindre et découper sur virgules et espaces
    raw = " ".join(args).replace(",", " ")
    tokens = [t.strip() for t in raw.split() if t.strip()]
    result = []
    for tok in tokens:
        if tok.startswith("+") or tok.startswith("-"):
            sign = tok[0] == "+"
            name = tok[1:].lower().rstrip("s")  # strip plural
        else:
            sign = True
            name = tok.lower().rstrip("s")
        if name not in _TYPES:
            return None  # un token n'est pas un type valide → pas un filtre catégorie
        result.append((name, sign))
    return result if result else None


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
            ftype = _PLURAL.get(ftype, ftype)
            if ftype not in _VALID and ftype not in ("type", "types"):
                print_error(f"Type inconnu : {ftype}  ({' | '.join(_VALID)} | type)")
                return
            if ftype in ("type", "types"):
                filters["type_include"] = []
                filters["type_exclude"] = []
            else:
                filters[_KEY[ftype]] = []
        else:
            for k in _KEY.values():
                filters[k] = []
            filters["type_include"] = []
            filters["type_exclude"] = []
        settings.save(ctx.cfg)
        print_ok("Filtres supprimés")
        return

    if sub == "add":
        if len(args) < 3:
            print_error("Usage: /select add <type> <nom>")
            return
        _add(filters, args[1].lower(), " ".join(args[2:]))
        settings.save(ctx.cfg)
        return

    if sub == "remove":
        if len(args) < 3:
            print_error("Usage: /select remove <type> <nom>")
            return
        _remove(filters, args[1].lower(), " ".join(args[2:]))
        settings.save(ctx.cfg)
        return

    # Filtre catégorie : tokens +/-type
    type_tokens = _parse_type_tokens(args)
    if type_tokens is not None:
        inc = filters.setdefault("type_include", [])
        exc = filters.setdefault("type_exclude", [])
        for name, include in type_tokens:
            if include:
                if name not in inc:
                    inc.append(name)
                if name in exc:
                    exc.remove(name)
            else:
                if name not in exc:
                    exc.append(name)
                if name in inc:
                    inc.remove(name)
        settings.save(ctx.cfg)
        _show_type_filters(inc, exc)
        return

    # Raccourci : /select <type> <nom>
    stype = _PLURAL.get(sub, sub)
    if stype in _VALID:
        name = " ".join(args[1:])
        if not name:
            print_error(f"Spécifie un nom après '{sub}'")
            return
        _add(filters, stype, name)
        settings.save(ctx.cfg)
        return

    print_error(f"Argument inconnu : {sub}  (utilisez /select help pour l'aide)")


def _add(filters: dict, ftype: str, name: str) -> None:
    ftype = _PLURAL.get(ftype, ftype)
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
    ftype = _PLURAL.get(ftype, ftype)
    if ftype not in _VALID:
        print_error(f"Type inconnu : {ftype}")
        return
    lst = filters.get(_KEY[ftype], [])
    if name in lst:
        lst.remove(name)
        print_ok(f"Filtre retiré : {name}")
    else:
        print_error(f"Filtre introuvable : {name}")


def _show_type_filters(inc: list[str], exc: list[str]) -> None:
    parts = []
    if inc:
        parts.append(f"[{C.SUCCESS}]Inclus :[/{C.SUCCESS}] " + "  ".join(f"[{C.UEX}]{t}[/{C.UEX}]" for t in inc))
    if exc:
        parts.append(f"[{C.LOSS}]Exclus :[/{C.LOSS}] " + "  ".join(f"[{C.UEX}]{t}[/{C.UEX}]" for t in exc))
    if parts:
        console.print("  Catégories → " + "   ".join(parts))
    else:
        console.print(f"  [{C.DIM}]Aucun filtre catégorie — tous les types autorisés[/{C.DIM}]")


def _show(filters: dict) -> None:
    section("Filtres actifs")
    has_any = False

    # Filtres catégorie
    inc = filters.get("type_include", [])
    exc = filters.get("type_exclude", [])
    if inc or exc:
        _show_type_filters(inc, exc)
        has_any = True

    # Filtres par nom
    labels = {"systems": "Systèmes", "planets": "Planètes", "stations": "Stations",
              "terminals": "Terminaux", "cities": "Villes", "outposts": "Avant-postes"}
    for key, label in labels.items():
        vals = filters.get(key, [])
        if vals:
            items = "  ".join(f"[{C.UEX}]{v}[/{C.UEX}]" for v in vals)
            console.print(f"  [bold]{label} :[/bold]  {items}")
            has_any = True

    if not has_any:
        console.print(f"  [{C.DIM}]Aucun filtre actif — /select help pour l'aide[/{C.DIM}]")
