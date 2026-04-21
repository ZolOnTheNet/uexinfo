"""Commande /select — filtres actifs (nouveau modèle v2)."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section

# ── Constantes ─────────────────────────────────────────────────────────────────

CATEGORIES = ("system", "dest", "station", "outpost", "city", "terminal", "planet")

# Items valides pour la catégorie "dest"
_DEST_ITEMS = ("station", "outpost", "city")


# ── Migration ──────────────────────────────────────────────────────────────────

def _migrate(filters: dict) -> None:
    """Migre l'ancien format vers le nouveau modèle v2 (in-place, silencieux)."""
    migrated = False

    # Ancien format : type_include / type_exclude → dest.include / dest.exclude
    if "type_include" in filters or "type_exclude" in filters:
        dest = filters.setdefault("dest", {"include": [], "exclude": []})
        for item in filters.pop("type_include", []):
            if item in _DEST_ITEMS and item not in dest["include"]:
                dest["include"].append(item)
        for item in filters.pop("type_exclude", []):
            if item in _DEST_ITEMS and item not in dest["exclude"]:
                dest["exclude"].append(item)
        migrated = True

    # Encore plus ancien : systems/stations/etc. listes plates → system.include / etc.
    _old_map = {
        "systems":   "system",
        "stations":  "station",
        "outposts":  "outpost",
        "cities":    "city",
        "terminals": "terminal",
        "planets":   "planet",
    }
    for old_key, cat in _old_map.items():
        if old_key in filters:
            cf = filters.setdefault(cat, {"include": [], "exclude": []})
            for item in filters.pop(old_key, []):
                if item and item not in cf["include"]:
                    cf["include"].append(item)
            migrated = True

    if migrated:
        # Sauvegarder silencieusement après migration
        try:
            settings.save_key("filters", filters)
        except Exception:
            pass


# ── Accès aux filtres ──────────────────────────────────────────────────────────

def _get_filters(ctx) -> dict:
    """Accède aux filtres depuis le contexte et migre si nécessaire."""
    filters = ctx.cfg.setdefault("filters", {})
    _migrate(filters)
    return filters


def _cat_filter(filters: dict, cat: str) -> dict:
    """Retourne le dict {include, exclude} d'une catégorie, crée si absent."""
    if cat not in filters or not isinstance(filters[cat], dict):
        filters[cat] = {"include": [], "exclude": []}
    cf = filters[cat]
    cf.setdefault("include", [])
    cf.setdefault("exclude", [])
    return cf


# ── Logique de filtrage ────────────────────────────────────────────────────────

def loc_name(t) -> str:
    """Retourne le nom de lieu canonique d'un terminal."""
    return (
        getattr(t, "space_station_name", None)
        or getattr(t, "outpost_name", None)
        or getattr(t, "city_name", None)
        or getattr(t, "name", "")
        or ""
    )


def _type_effective(cat: str, filters: dict) -> bool:
    """Indique si un type est autorisé globalement (hors overrides par nom).

    cat ∈ {"station", "outpost", "city"}.
    Regarde filters["dest"].
    """
    df = filters.get("dest", {})
    inc = df.get("include", [])
    exc = df.get("exclude", [])
    if inc and cat not in inc:
        return False
    if cat in exc:
        return False
    return True


def is_destination_allowed(t, filters: dict) -> bool:
    """Indique si un terminal est une destination autorisée selon les filtres.

    Priorité :
    1. Nom inclus explicitement → True (override)
    2. Nom exclu explicitement → False
    3. Système exclu → False
    4. Système non inclus (si liste non-vide) → False
    5. Type exclu (dest) → False
    6. Type non inclus (dest, si liste non-vide) → False
    7. Sinon → True
    """
    from uexinfo.display.formatter import terminal_category

    # Déterminer le nom de lieu et la catégorie
    lname = loc_name(t).lower()
    cat = terminal_category(t)  # 'station' | 'outpost' | 'city' | 'other'
    sys_name = (getattr(t, "star_system_name", None) or "").lower()

    # 1 & 2 — Override par nom (selon la catégorie du lieu)
    if cat in CATEGORIES:
        cf = filters.get(cat, {})
        inc_names = [n.lower() for n in cf.get("include", [])]
        exc_names = [n.lower() for n in cf.get("exclude", [])]
        if lname in inc_names:
            return True   # override : inclus explicitement
        if lname in exc_names:
            return False  # override : exclu explicitement

    # 3 & 4 — Filtre système
    sf = filters.get("system", {})
    sys_inc = [s.lower() for s in sf.get("include", [])]
    sys_exc = [s.lower() for s in sf.get("exclude", [])]
    if sys_name in sys_exc:
        return False
    if sys_inc and sys_name not in sys_inc:
        return False

    # 5 & 6 — Filtre type (dest)
    df = filters.get("dest", {})
    type_inc = [s.lower() for s in df.get("include", [])]
    type_exc = [s.lower() for s in df.get("exclude", [])]
    if cat in type_exc:
        return False
    if type_inc and cat not in type_inc:
        return False

    return True


# ── Parsing des items ──────────────────────────────────────────────────────────

def _parse_items(tokens: list[str]) -> list[tuple[str, bool]]:
    """Parse les tokens +nom / -nom / nom.

    Underscores → espaces.
    Retourne [(nom_normalisé, include), ...].
    """
    raw = " ".join(tokens).replace(",", " ")
    parts = [p.strip() for p in raw.split() if p.strip()]
    result = []
    for tok in parts:
        if tok.startswith("+"):
            include = True
            name = tok[1:]
        elif tok.startswith("-"):
            include = False
            name = tok[1:]
        else:
            include = True
            name = tok
        name = name.replace("_", " ").strip()
        if name:
            result.append((name, include))
    return result


# ── Affichage ──────────────────────────────────────────────────────────────────

def _show_cat(cat: str, cf: dict) -> None:
    """Affiche une catégorie de filtre."""
    inc = cf.get("include", [])
    exc = cf.get("exclude", [])
    if not inc and not exc:
        return
    parts = []
    if inc:
        items = "  ".join(f"[{C.SUCCESS}]+{v}[/{C.SUCCESS}]" for v in inc)
        parts.append(items)
    if exc:
        items = "  ".join(f"[{C.LOSS}]-{v}[/{C.LOSS}]" for v in exc)
        parts.append(items)
    cat_label = {
        "system":   "Systèmes",
        "dest":     "Types (dest)",
        "station":  "Stations",
        "outpost":  "Avant-postes",
        "city":     "Villes",
        "terminal": "Terminaux",
        "planet":   "Planètes",
    }.get(cat, cat)
    console.print(f"  [bold]{cat_label} :[/bold]  " + "   ".join(parts))


def _show(filters: dict) -> None:
    """Affiche tous les filtres actifs."""
    section("Filtres actifs")
    has_any = False
    for cat in CATEGORIES:
        cf = filters.get(cat, {})
        if isinstance(cf, dict) and (cf.get("include") or cf.get("exclude")):
            _show_cat(cat, cf)
            has_any = True
    if not has_any:
        console.print(f"  [{C.DIM}]Aucun filtre actif — /select help pour l'aide[/{C.DIM}]")


def _show_help() -> None:
    """Affiche l'aide complète de /select."""
    section("Aide — /select")
    console.print(
        f"[bold]━━ Syntaxe ━━[/bold]\n"
        f"  [{C.UEX}]/select[/{C.UEX}]                              Afficher tous les filtres actifs\n"
        f"  [{C.UEX}]/select <catégorie> [+|-]<item>...[/{C.UEX}]  Définir filtres pour une catégorie\n"
        f"  [{C.UEX}]/select show <système>[/{C.UEX}]              Statut ✓/✗ de chaque lieu\n"
        f"  [{C.UEX}]/select edit <système>[/{C.UEX}]              Éditeur TUI avec cases à cocher\n"
        f"  [{C.UEX}]/select clear [catégorie][/{C.UEX}]           Effacer tout ou une catégorie\n\n"

        f"[bold]━━ Catégories ━━[/bold]\n"
        f"  [{C.UEX}]system dest station outpost city terminal planet[/{C.UEX}]\n\n"

        f"  [{C.DIM}]Pour 'dest', les items valides sont :[/{C.DIM}] [{C.UEX}]station[/{C.UEX}] [{C.UEX}]outpost[/{C.UEX}] [{C.UEX}]city[/{C.UEX}]\n"
        f"  [{C.DIM}]Pour les autres, les items sont des noms de lieux.[/{C.DIM}]\n\n"

        f"[bold]━━ Préfixes ━━[/bold]\n"
        f"  [{C.SUCCESS}]+[/{C.SUCCESS}] = inclure   [{C.LOSS}]-[/{C.LOSS}] = exclure   sans préfixe = inclure\n"
        f"  Underscores dans les noms = espaces. Virgules autorisées.\n\n"

        f"[bold]━━ Priorité ━━[/bold]\n"
        f"  nom inclus > nom exclu > filtre système > filtre type (dest)\n\n"

        f"[bold]━━ Exemples ━━[/bold]\n"
        f"  [{C.DIM}]/select dest +station +outpost -city[/{C.DIM}]  → stations et outposts, pas villes\n"
        f"  [{C.DIM}]/select system Stanton -Nyx[/{C.DIM}]          → Stanton oui, Nyx non\n"
        f"  [{C.DIM}]/select station -MIC-L5[/{C.DIM}]              → cette station est exclue\n"
        f"  [{C.DIM}]/select city +New_Babbage[/{C.DIM}]            → New Babbage inclus même si city exclu\n"
        f"  [{C.DIM}]/select show Stanton[/{C.DIM}]                 → statut ✓/✗ de chaque lieu Stanton\n"
        f"  [{C.DIM}]/select edit Stanton[/{C.DIM}]                 → éditeur TUI Stanton\n"
        f"  [{C.DIM}]/select clear dest[/{C.DIM}]                   → effacer les filtres de type\n"
        f"\n"
        f"[bold]━━ Pourquoi filtrer ? ━━[/bold]\n"
        f"  Les stations se chargent/déchargent automatiquement (rapide).\n"
        f"  Les avant-postes requièrent un chargement manuel (~20 min).\n"
        f"  Les cités nécessitent d'atterrir et prendre le métro jusqu'au TDD.\n"
        f"  [{C.DIM}]Conseil : /select dest +station +outpost -city pour éviter les TDD.[/{C.DIM}]"
    )


# ── Sous-commande show ─────────────────────────────────────────────────────────

def _cmd_show(args: list[str], ctx, filters: dict) -> None:
    """/select show <système> — affiche le statut ✓/✗ de chaque lieu."""
    if not args:
        print_error("Usage : /select show <système>")
        return

    sys_query = " ".join(args).replace("_", " ").strip().lower()

    if not ctx.cache or not ctx.cache.terminals:
        print_error("Cache vide — lancez /refresh d'abord")
        return

    # Trouver les terminaux du système
    system_name = ""
    sys_terminals = []
    for t in ctx.cache.terminals:
        sname = (getattr(t, "star_system_name", None) or "").lower()
        if sys_query in sname or sname.startswith(sys_query):
            sys_terminals.append(t)
            if not system_name:
                system_name = getattr(t, "star_system_name", "") or sys_query.title()

    if not sys_terminals:
        print_error(f"Aucun terminal trouvé pour le système : {sys_query}")
        return

    section(f"Filtres — {system_name}")

    # Déduplication par loc_name (une entrée par lieu, pas par terminal)
    from uexinfo.display.formatter import terminal_category
    seen: dict[str, tuple] = {}  # loc_name → (t, cat)
    for t in sys_terminals:
        lname = loc_name(t)
        if not lname:
            continue
        if lname not in seen:
            cat = terminal_category(t)
            seen[lname] = (t, cat)

    # Grouper par type
    groups: dict[str, list[tuple[str, object, str]]] = {
        "station": [], "outpost": [], "city": [], "other": []
    }
    for lname, (t, cat) in sorted(seen.items()):
        groups.get(cat, groups["other"]).append((lname, t, cat))

    group_labels = {
        "station": "STATIONS",
        "outpost": "AVANT-POSTES",
        "city":    "VILLES",
        "other":   "AUTRES",
    }

    for gcat, items in groups.items():
        if not items:
            continue
        # Afficher le statut type global
        type_ok = _type_effective(gcat, filters)
        type_badge = f"[{C.SUCCESS}](+type)[/{C.SUCCESS}]" if type_ok else f"[{C.LOSS}](-type)[/{C.LOSS}]"
        console.print(f"\n  [bold]{group_labels[gcat]}[/bold]  {type_badge}")

        for lname, t, cat in items:
            allowed = is_destination_allowed(t, filters)
            lname_lower = lname.lower()

            # Déterminer si override explicite
            cf = filters.get(cat, {})
            inc_names = [n.lower() for n in cf.get("include", [])]
            exc_names = [n.lower() for n in cf.get("exclude", [])]
            if lname_lower in inc_names:
                badge = f" [{C.SUCCESS}](+explicite)[/{C.SUCCESS}]"
            elif lname_lower in exc_names:
                badge = f" [{C.LOSS}](-explicite)[/{C.LOSS}]"
            else:
                badge = ""

            if allowed:
                status = f"[{C.SUCCESS}][✓][/{C.SUCCESS}]"
            else:
                status = f"[{C.LOSS}][✗][/{C.LOSS}]"
            console.print(f"    {status} [{C.UEX}]{lname}[/{C.UEX}]{badge}")


# ── Sous-commande edit ─────────────────────────────────────────────────────────

def _cmd_edit(args: list[str], ctx, filters: dict) -> None:
    """/select edit <système> — éditeur TUI."""
    if not args:
        print_error("Usage : /select edit <système>")
        return
    sys_query = " ".join(args).replace("_", " ").strip()
    try:
        from uexinfo.cli.commands.select_editor import run_select_editor
        run_select_editor(sys_query, ctx, filters)
        settings.save(ctx.cfg)
    except ImportError as e:
        print_error(f"Éditeur TUI non disponible : {e}")
    except Exception as e:
        print_error(f"Erreur éditeur : {e}")


# ── Commande principale ────────────────────────────────────────────────────────

@register("select", "sel")
def cmd_select(args: list[str], ctx) -> None:
    """Filtres de destination (système, type, station, ville…)."""
    filters = _get_filters(ctx)

    if not args:
        _show(filters)
        return

    sub = args[0].lower()

    # Aide
    if sub in ("help", "?", "--help"):
        _show_help()
        return

    # Clear
    if sub == "clear":
        if len(args) > 1:
            cat = args[1].lower().rstrip("s")  # tolérer pluriel
            # Normaliser quelques alias
            _aliases = {"type": "dest", "types": "dest", "systems": "system",
                        "stations": "station", "outposts": "outpost",
                        "cities": "city", "terminals": "terminal", "planets": "planet"}
            cat = _aliases.get(cat, cat)
            if cat not in CATEGORIES:
                print_error(f"Catégorie inconnue : {cat}  ({' | '.join(CATEGORIES)})")
                return
            filters.pop(cat, None)
            settings.save(ctx.cfg)
            print_ok(f"Filtres [{C.UEX}]{cat}[/{C.UEX}] supprimés")
        else:
            for cat in CATEGORIES:
                filters.pop(cat, None)
            settings.save(ctx.cfg)
            print_ok("Tous les filtres supprimés")
        return

    # Show
    if sub == "show":
        _cmd_show(args[1:], ctx, filters)
        return

    # Edit
    if sub == "edit":
        _cmd_edit(args[1:], ctx, filters)
        return

    # Catégorie connue : /select <cat> [items...]
    # Normaliser quelques alias
    _cat_aliases = {
        "type": "dest", "types": "dest",
        "systems": "system", "stations": "station", "outposts": "outpost",
        "cities": "city", "terminals": "terminal", "planets": "planet",
    }
    cat = _cat_aliases.get(sub, sub)

    if cat not in CATEGORIES:
        print_error(f"Argument inconnu : {sub}  (utilisez /select help pour l'aide)")
        return

    if len(args) < 2:
        # Juste /select <cat> → afficher les filtres de cette catégorie
        cf = _cat_filter(filters, cat)
        _show_cat(cat, cf)
        return

    # Valider les items pour "dest"
    items = _parse_items(args[1:])
    if not items:
        print_error(f"Aucun item valide après '{cat}'")
        return

    if cat == "dest":
        for name, include in items:
            if name.lower() not in _DEST_ITEMS:
                print_error(
                    f"Item invalide pour 'dest' : {name!r}  "
                    f"(valides : {', '.join(_DEST_ITEMS)})"
                )
                return

    cf = _cat_filter(filters, cat)
    inc = cf["include"]
    exc = cf["exclude"]

    for name, include in items:
        name_norm = name.lower() if cat == "dest" else name
        if include:
            if name_norm not in inc:
                inc.append(name_norm)
            if name_norm in exc:
                exc.remove(name_norm)
        else:
            if name_norm not in exc:
                exc.append(name_norm)
            if name_norm in inc:
                inc.remove(name_norm)

    settings.save(ctx.cfg)
    _show_cat(cat, cf)
