"""Éditeur TUI /select edit <système> — cases à cocher pour filtres de lieux."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # AppContext n'est pas importé directement pour éviter les circulaires


def run_select_editor(system_query: str, ctx, filters: dict) -> None:
    """Lance un éditeur TUI plein-écran pour modifier les filtres du système.

    Affiche les lieux groupés par type (station/outpost/city).
    Chaque lieu a un état : ~ (inherit) | + (include) | - (exclude).
    Sauvegarde dans filters[cat]["include"] / filters[cat]["exclude"].
    """
    from prompt_toolkit import Application
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    from uexinfo.cli.commands.select import loc_name, is_destination_allowed, _cat_filter
    from uexinfo.display.formatter import terminal_category

    sys_query_lower = system_query.lower()

    # ── Collecter les lieux du système ────────────────────────────────────────
    if not ctx.cache or not ctx.cache.terminals:
        from uexinfo.display.formatter import print_error
        print_error("Cache vide — lancez /refresh d'abord")
        return

    system_name = system_query
    seen: dict[str, tuple] = {}  # loc_name → (terminal, cat)
    for t in ctx.cache.terminals:
        sname = (getattr(t, "star_system_name", None) or "").lower()
        if sys_query_lower not in sname and not sname.startswith(sys_query_lower):
            continue
        lname = loc_name(t)
        if not lname:
            continue
        if lname not in seen:
            cat = terminal_category(t)
            seen[lname] = (t, cat)
            if not system_name or system_name.lower() == sys_query_lower:
                system_name = getattr(t, "star_system_name", None) or system_query

    if not seen:
        from uexinfo.display.formatter import print_error
        print_error(f"Aucun lieu trouvé pour : {system_query}")
        return

    # ── Construire la liste d'items ──────────────────────────────────────────
    # Chaque item : {"lname": str, "cat": str, "state": "~"|"+"|"-"}
    # Groupes : station → outpost → city → other
    _GROUP_ORDER = ["station", "outpost", "city", "other"]
    _GROUP_LABELS = {
        "station": "STATIONS",
        "outpost": "AVANT-POSTES",
        "city":    "VILLES",
        "other":   "AUTRES",
    }

    groups: dict[str, list[dict]] = {g: [] for g in _GROUP_ORDER}

    for lname, (t, cat) in sorted(seen.items(), key=lambda x: x[0].lower()):
        cf = filters.get(cat, {})
        inc_names = [n.lower() for n in cf.get("include", [])]
        exc_names = [n.lower() for n in cf.get("exclude", [])]
        lname_lower = lname.lower()
        if lname_lower in inc_names:
            state = "+"
        elif lname_lower in exc_names:
            state = "-"
        else:
            state = "~"
        groups.get(cat, groups["other"]).append({
            "lname": lname,
            "cat":   cat,
            "state": state,
        })

    # Aplatir en liste d'items navigables (en insérant des séparateurs de groupe)
    items: list[dict] = []
    for gcat in _GROUP_ORDER:
        glist = groups[gcat]
        if glist:
            items.extend(glist)

    if not items:
        from uexinfo.display.formatter import print_error
        print_error("Aucun lieu navigable dans ce système")
        return

    # ── État navigateur ───────────────────────────────────────────────────────
    cursor = [0]
    cancelled = [False]

    # ── Rendu ──────────────────────────────────────────────────────────────────

    def _type_badge(cat: str) -> str:
        """Retourne le badge (+type) ou (-type) selon dest filter."""
        df = filters.get("dest", {})
        inc = df.get("include", [])
        exc = df.get("exclude", [])
        if inc and cat not in inc:
            return "(-type)"
        if cat in exc:
            return "(-type)"
        return "(+type)"

    def _render() -> FormattedText:
        result: list[tuple[str, str]] = []

        # Titre
        result.append(("bold", f"━━ Éditeur filtres — {system_name} ━━\n"))
        result.append(("", "  "))
        result.append(("italic", "Espace=cycle  ↑↓=nav  Ctrl+S=sauver  Échap=annuler"))
        result.append(("", "\n\n"))

        # Groupes
        cur_cat = None
        for i, item in enumerate(items):
            cat = item["cat"]
            if cat != cur_cat:
                cur_cat = cat
                badge = _type_badge(cat)
                badge_style = "ansigreen" if badge == "(+type)" else "ansired"
                result.append(("bold", f"  {_GROUP_LABELS.get(cat, cat.upper())}  "))
                result.append((badge_style, badge))
                result.append(("", "\n"))

            state = item["state"]
            lname = item["lname"]
            is_cur = (i == cursor[0])

            # Style de l'état
            if state == "+":
                st_style = "ansigreen bold"
                st_char  = "+"
            elif state == "-":
                st_style = "ansired bold"
                st_char  = "-"
            else:
                st_style = ""
                st_char  = "~"

            if is_cur:
                result.append(("reverse bold", f"    [{st_char}] {lname}"))
                result.append(("", "\n"))
            else:
                result.append(("", "    ["))
                result.append((st_style, st_char))
                result.append(("", f"] {lname}\n"))

        result.append(("", "\n"))
        return FormattedText(result)

    # ── Bindings clavier ──────────────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("s-tab")
    def _up(event):
        cursor[0] = max(0, cursor[0] - 1)

    @kb.add("down")
    @kb.add("tab")
    def _down(event):
        cursor[0] = min(len(items) - 1, cursor[0] + 1)

    @kb.add("space")
    def _cycle(event):
        item = items[cursor[0]]
        item["state"] = {"~": "+", "+": "-", "-": "~"}[item["state"]]

    @kb.add("c-s")
    def _save(event):
        event.app.exit(result=True)

    @kb.add("escape")
    def _cancel(event):
        cancelled[0] = True
        event.app.exit(result=False)

    # ── Application ──────────────────────────────────────────────────────────
    layout = Layout(
        Window(
            content=FormattedTextControl(lambda: _render(), focusable=True),
        )
    )

    app: Application = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
    )

    saved = app.run()

    if not saved or cancelled[0]:
        from uexinfo.display.formatter import print_warn
        print_warn("Édition annulée")
        return

    # ── Sauvegarder les changements ──────────────────────────────────────────
    # Collecter les changements par catégorie
    cat_changes: dict[str, list[dict]] = {}
    for item in items:
        cat = item["cat"]
        cat_changes.setdefault(cat, []).append(item)

    for cat, cat_items in cat_changes.items():
        cf = _cat_filter(filters, cat)
        inc = cf["include"]
        exc = cf["exclude"]
        for item in cat_items:
            lname = item["lname"]
            state = item["state"]
            # Normaliser : pour les catégories non-dest, conserver la casse originale
            lname_norm = lname

            if state == "+":
                # Ajouter à include, retirer de exclude
                if lname_norm not in inc:
                    inc.append(lname_norm)
                # Retirer en ignorant la casse
                to_remove = [x for x in exc if x.lower() == lname_norm.lower()]
                for x in to_remove:
                    exc.remove(x)
            elif state == "-":
                # Ajouter à exclude, retirer de include
                if lname_norm not in exc:
                    exc.append(lname_norm)
                to_remove = [x for x in inc if x.lower() == lname_norm.lower()]
                for x in to_remove:
                    inc.remove(x)
            else:
                # inherit : retirer des deux listes
                to_rem_inc = [x for x in inc if x.lower() == lname_norm.lower()]
                for x in to_rem_inc:
                    inc.remove(x)
                to_rem_exc = [x for x in exc if x.lower() == lname_norm.lower()]
                for x in to_rem_exc:
                    exc.remove(x)

    from uexinfo.display.formatter import print_ok
    n_changed = sum(
        1 for item in items if item["state"] != "~"
    )
    print_ok(f"Filtres sauvegardés ({n_changed} override(s))")
