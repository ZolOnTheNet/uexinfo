"""Commande /mission — catalogue de missions."""
from __future__ import annotations

from rich.table import Table

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.models.mission import Mission, MissionObjective

_SUBS = frozenset({
    "list", "add", "edit", "remove", "scan",
    # alias français
    "liste", "ajouter", "modifier", "supprimer",
})


@register("mission", "m")
def cmd_mission(args: list[str], ctx) -> None:
    """Catalogue de missions."""
    sub = args[0].lower() if args else ""

    if not sub or sub not in _SUBS:
        _show_help()
        return

    if sub in ("list", "liste"):
        _cmd_list(ctx)

    elif sub in ("add", "ajouter"):
        rest = args[1:]
        if not rest:
            # Sans arguments → tenter depuis le dernier scan
            _cmd_add_from_scan(ctx)
        else:
            _cmd_add(rest, ctx)

    elif sub in ("edit", "modifier"):
        _cmd_edit(args[1:], ctx)

    elif sub in ("remove", "supprimer"):
        _cmd_remove(args[1:], ctx)

    elif sub == "scan":
        print_warn("Scan de mission par screenshot — Phase 2 (non encore implémenté)")
        console.print(f"[{C.DIM}]Scannez d'abord : /scan <fichier>  puis /mission add pour ajouter.[/{C.DIM}]")


# ── Affichage liste ───────────────────────────────────────────────────────────

def _cmd_list(ctx) -> None:
    mm = ctx.mission_manager
    if not mm.missions:
        print_warn("Aucune mission dans le catalogue")
        console.print(f"[{C.DIM}]/mission add <nom> reward:<n> obj:<commodité> from:<source> to:<dest> scu:<n>[/{C.DIM}]")
        return

    section("Catalogue de missions")

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("#",          style=C.DIM,    width=3, justify="right")
    tbl.add_column("Nom",        style=C.LABEL,  max_width=24)
    tbl.add_column("Départ",     style=C.UEX,    max_width=16)
    tbl.add_column("→",          style=C.DIM,    width=1)
    tbl.add_column("Arrivée",    style=C.UEX,    max_width=16)
    tbl.add_column("Dist",       justify="right", width=7)
    tbl.add_column("SCU",        justify="right", width=4)
    tbl.add_column("Récompense", justify="right", width=12)
    tbl.add_column("Synergies",  width=6)

    graph = ctx.cache.transport_graph

    for m in mm.missions:
        srcs = ", ".join(m.all_sources[:2]) or "—"
        dsts = ", ".join(m.all_destinations[:2]) or "—"
        scu_str = f"{m.total_scu:.0f}□" if m.total_scu else "—"
        reward_str = f"{m.reward_uec:,}".replace(",", " ") + " aUEC"
        tags = " ".join(mm.synergies(m))

        # Distance via graphe
        dist_str = "?"
        if m.all_sources and m.all_destinations:
            try:
                result = graph.shortest_path(m.all_sources[0], m.all_destinations[0])
                if result:
                    d = result.total_distance
                    dist_str = f"{d:.1f}Gm" if d >= 1 else f"{d*1000:.0f}Mm"
            except Exception:
                pass

        has_delay = any(o.time_cost for o in m.objectives)
        name_display = m.name + (f" [{C.WARNING}]⏱[/{C.WARNING}]" if has_delay else "")

        tbl.add_row(
            str(m.id),
            name_display, srcs, "→", dsts,
            dist_str, scu_str, reward_str, tags,
        )

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(mm.missions)} mission(s) · /mission add pour ajouter · /voyage pour planifier[/{C.DIM}]")


# ── Add depuis dernier scan ───────────────────────────────────────────────────

def _cmd_add_from_scan(ctx) -> None:
    from uexinfo.models.mission_result import MissionResult
    last = ctx.last_scan
    if last is None:
        print_warn("Aucun scan disponible — faites d'abord /scan <fichier>")
        console.print(f"[{C.DIM}]Ou : /mission add <nom> reward:<n> obj:... pour saisie manuelle.[/{C.DIM}]")
        return
    if not isinstance(last, MissionResult):
        print_warn("Le dernier scan est un terminal de commerce, pas une mission")
        console.print(f"[{C.DIM}]Scannez un screenshot de l'écran Contrats.[/{C.DIM}]")
        return
    if not last.parsed_objectives:
        print_warn("Le scan ne contient pas d'objectifs parsés")
        console.print(f"[{C.DIM}]Utilisez /scan debug pour diagnostiquer l'image.[/{C.DIM}]")
        return

    kwargs = last.to_mission_kwargs()
    mm = ctx.mission_manager
    m = Mission(id=0, **kwargs)
    mm.add(m)

    reward_str = f"{m.reward_uec:,}".replace(",", " ")
    print_ok(f"Mission #{m.id} ajoutée depuis scan : {m.name}  [{C.DIM}]{reward_str} aUEC  {len(m.objectives)} objectif(s)[/{C.DIM}]")
    # Résumé des objectifs
    for o in last.parsed_objectives:
        if o.kind == "collect":
            console.print(f"  [{C.DIM}]↑ Collect {o.commodity} depuis {o.location}[/{C.DIM}]")
        elif o.kind == "deliver":
            hint = f" above {o.location_hint}" if o.location_hint else ""
            console.print(f"  [{C.DIM}]↓ Deliver {o.quantity_scu} SCU → {o.location}{hint}[/{C.DIM}]")


# ── Add ───────────────────────────────────────────────────────────────────────

def _cmd_add(args: list[str], ctx) -> None:
    mm = ctx.mission_manager
    if not args:
        _show_add_help()
        return

    # Premier token non-kv = nom de la mission
    name_parts = []
    rest = []
    for i, a in enumerate(args):
        if ":" in a or a.lower() in ("tdd", "shop"):
            rest = args[i:]
            break
        name_parts.append(a)

    if not name_parts:
        print_error("Nom de mission manquant")
        _show_add_help()
        return

    name = " ".join(name_parts)
    reward = 0
    objectives: list[MissionObjective] = []
    current: dict = {}

    for arg in rest:
        low = arg.lower()
        if low.startswith("reward:"):
            try:
                reward = int(arg[7:].replace(",", "").replace(" ", "").replace("k", "000"))
            except ValueError:
                print_warn(f"Récompense invalide : {arg[7:]}")
        elif low.startswith("obj:"):
            if current:
                objectives.append(MissionObjective(**current))
            current = {"commodity": arg[4:] or None}
        elif low.startswith("from:"):
            current["source"] = arg[5:] or None
        elif low.startswith("to:"):
            current["destination"] = arg[3:] or None
        elif low.startswith("scu:"):
            try:
                current["quantity_scu"] = float(arg[4:])
            except ValueError:
                print_warn(f"SCU invalide : {arg[4:]}")
        elif low in ("tdd", "shop"):
            current["time_cost"] = low
        elif low.startswith("delay:"):
            current["time_cost"] = arg[6:]
        elif low.startswith("note:"):
            current["notes"] = arg[5:]

    if current:
        objectives.append(MissionObjective(**current))

    m = Mission(id=0, name=name, reward_uec=reward, objectives=objectives, source_raw="manual")
    mm.add(m)

    reward_str = f"{reward:,}".replace(",", " ")
    print_ok(f"Mission #{m.id} ajoutée : {name}  [{C.DIM}]{reward_str} aUEC  {len(objectives)} objectif(s)[/{C.DIM}]")


# ── Edit ──────────────────────────────────────────────────────────────────────

def _cmd_edit(args: list[str], ctx) -> None:
    mm = ctx.mission_manager
    if not args:
        print_error("Identifiant de mission manquant")
        return

    m = mm.get(args[0])
    if not m:
        print_error(f"Mission introuvable : {args[0]}")
        return

    rest = args[1:]
    new_objs: list[MissionObjective] = []
    current: dict = {}

    for arg in rest:
        low = arg.lower()
        if low.startswith("reward:"):
            try:
                m.reward_uec = int(arg[7:].replace(",", "").replace(" ", "").replace("k", "000"))
            except ValueError:
                print_warn(f"Récompense invalide : {arg[7:]}")
        elif low.startswith("name:"):
            m.name = arg[5:]
        elif low.startswith("obj:"):
            if current:
                new_objs.append(MissionObjective(**current))
            current = {"commodity": arg[4:] or None}
        elif low.startswith("from:"):
            current["source"] = arg[5:] or None
        elif low.startswith("to:"):
            current["destination"] = arg[3:] or None
        elif low.startswith("scu:"):
            try:
                current["quantity_scu"] = float(arg[4:])
            except ValueError:
                pass
        elif low in ("tdd", "shop"):
            current["time_cost"] = low
        elif low.startswith("delay:"):
            current["time_cost"] = arg[6:]
        elif low.startswith("note:"):
            current["notes"] = arg[5:]

    if current:
        new_objs.append(MissionObjective(**current))

    if new_objs:
        m.objectives.extend(new_objs)

    mm.update(m)
    print_ok(f"Mission #{m.id} modifiée : {m.name}")


# ── Remove ────────────────────────────────────────────────────────────────────

def _cmd_remove(args: list[str], ctx) -> None:
    mm = ctx.mission_manager
    if not args:
        print_error("Identifiant de mission manquant")
        return
    if mm.remove(args[0]):
        print_ok(f"Mission supprimée : {args[0]}")
    else:
        print_error(f"Mission introuvable : {args[0]}")


# ── Aide ─────────────────────────────────────────────────────────────────────

def _show_help() -> None:
    section("Aide — /mission")
    lines = [
        ("list",        "Liste le catalogue de missions"),
        ("add",         "Ajoute une mission manuellement (voir ci-dessous)"),
        ("edit <id>",   "Modifie une mission existante"),
        ("remove <id>", "Supprime une mission du catalogue"),
        ("scan",        "Scan de mission par screenshot (Phase 2)"),
    ]
    for cmd, desc in lines:
        console.print(f"  [bold {C.LABEL}]/mission {cmd:<16}[/bold {C.LABEL}]  [{C.DIM}]{desc}[/{C.DIM}]")
    console.print()
    _show_add_help()
    console.print(f"  [{C.DIM}]Pour planifier un trajet, utilisez /voyage[/{C.DIM}]")


def _show_add_help() -> None:
    console.print(f"  [{C.DIM}]Syntaxe add :[/{C.DIM}]")
    console.print(f"  [bold {C.LABEL}]/mission add <nom> reward:<aUEC>[/bold {C.LABEL}]")
    console.print(f"  [bold {C.LABEL}]    [obj:<commodité> from:<source> to:<dest> scu:<n> [tdd|shop|delay:<r>]]+[/bold {C.LABEL}]")
    console.print()
    console.print(f"  [{C.DIM}]Exemple :[/{C.DIM}]")
    console.print(
        f"  [{C.LABEL}]/mission add \"Livraison Quant\" reward:50000 "
        f"obj:Quantainium from:HUR-L2 to:GrimHEX scu:12 tdd[/{C.LABEL}]"
    )
    console.print()
    console.print(f"  [{C.DIM}]time_cost : tdd = TDD requis · shop = achat boutique · delay:<raison> = libre[/{C.DIM}]")
    console.print(f"  [{C.DIM}]Synergies : ⊙ même départ · ⊕ même arrivée · ⇄ mission relais[/{C.DIM}]")
