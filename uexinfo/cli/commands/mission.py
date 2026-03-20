"""Commande /mission — catalogue de missions."""
from __future__ import annotations

import re
from pathlib import Path

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

_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"})


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
            _cmd_add_from_scan(ctx)
        elif _is_image(rest[0]):
            _cmd_add_from_file(rest[0], ctx)
        else:
            _cmd_add(rest, ctx)

    elif sub in ("edit", "modifier"):
        _cmd_edit(args[1:], ctx)

    elif sub in ("remove", "supprimer"):
        _cmd_remove(args[1:], ctx)

    elif sub == "scan":
        print_warn("Scan de mission par screenshot — Phase 2 (non encore implémenté)")
        console.print(f"[{C.DIM}]Workflow : /scan <fichier>  puis /mission add[/{C.DIM}]")
        console.print(f"[{C.DIM}]Ou directement : /mission add <fichier.jpg>[/{C.DIM}]")


def _is_image(path: str) -> bool:
    p = Path(path)
    return p.suffix.lower() in _IMAGE_EXTS or p.exists()


# ── Affichage liste ───────────────────────────────────────────────────────────

def _cmd_list(ctx) -> None:
    mm = ctx.mission_manager
    if not mm.missions:
        print_warn("Aucune mission dans le catalogue")
        console.print(f"[{C.DIM}]/mission add <nom> reward:<n> obj:<commodité> from:<source> to:<dest> scu:<n>[/{C.DIM}]")
        return

    section("Catalogue de missions")

    tbl = Table(show_header=True, box=None, padding=(0, 1),
                row_styles=["", f"on grey7"])
    tbl.add_column("#",          style=C.DIM,    width=3, justify="right")
    tbl.add_column("Nom",        style=C.LABEL,  max_width=45)
    tbl.add_column("Départ",     style=C.UEX,    max_width=18)
    tbl.add_column("→",          style=C.DIM,    width=1)
    tbl.add_column("Arrivée",    style=C.UEX,    max_width=18)
    tbl.add_column("Dist",       justify="right", width=7)
    tbl.add_column("SCU",        justify="right", width=5)
    tbl.add_column("Récompense", justify="right", width=12)
    tbl.add_column("Syn",        width=4)

    graph = ctx.cache.transport_graph

    for m in mm.missions:
        srcs = ", ".join(m.all_sources[:2]) or "—"
        dsts = ", ".join(m.all_destinations[:2]) or "—"
        scu_str = f"{m.total_scu:.0f}□" if m.total_scu else "—"
        reward_str = f"{m.reward_uec:,}".replace(",", " ") + " aUEC"
        tags = " ".join(mm.synergies(m))

        # Distance via graphe — résolution fuzzy des noms de lieux
        dist_str = "?"
        if m.all_sources and m.all_destinations:
            try:
                src_node = _resolve_graph_node(m.all_sources[0], graph)
                dst_node = _resolve_graph_node(m.all_destinations[0], graph)
                if src_node and dst_node:
                    result = graph.shortest_path(src_node, dst_node)
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
    console.print(f"\n[{C.DIM}]{len(mm.missions)} mission(s) · /mission add <fichier> ou <nom> · /voyage pour planifier[/{C.DIM}]")


def _resolve_graph_node(name: str, graph) -> str | None:
    """Résout un nom de lieu (potentiellement long) vers un nœud du graphe."""
    from uexinfo.cli.commands.nav import _resolve_node
    # Essayer le nom complet d'abord, puis les tokens les plus courts
    node = _resolve_node(name, graph)
    if node:
        return node
    # Extraire le code court : "MIC-L2 Long Forest Station" → "MIC-L2"
    short = re.split(r"\s+", name.strip())[0]
    return _resolve_node(short, graph)


# ── Add depuis dernier scan ───────────────────────────────────────────────────

def _cmd_add_from_scan(ctx) -> None:
    from uexinfo.models.mission_result import MissionResult
    last = ctx.last_scan
    if last is None:
        print_warn("Aucun scan disponible")
        console.print(f"[{C.DIM}]Usage : /mission add <fichier.jpg>  ou  /scan <fichier> puis /mission add[/{C.DIM}]")
        return
    if not isinstance(last, MissionResult):
        print_warn("Le dernier scan est un terminal de commerce, pas une mission")
        console.print(f"[{C.DIM}]Usage : /mission add <fichier.jpg> pour scanner directement[/{C.DIM}]")
        return
    _add_mission_result(last, ctx)


def _cmd_add_from_file(path_str: str, ctx) -> None:
    """Scanne un fichier image et ajoute la mission au catalogue."""
    from pathlib import Path as _Path
    p = _Path(path_str)
    if not p.exists():
        print_error(f"Fichier introuvable : {path_str}")
        return

    from uexinfo.cli.commands.scan import _scan_image_file
    from uexinfo.models.mission_result import MissionResult

    console.print(f"[{C.DIM}]Scan de {p.name}...[/{C.DIM}]")
    try:
        result = _scan_image_file(ctx, p)
    except Exception as e:
        print_error(f"Erreur OCR : {e}")
        return

    if result is None:
        print_error("OCR n'a rien extrait")
        return
    if not isinstance(result, MissionResult):
        print_warn(f"Ce screenshot ({p.name}) est un terminal de commerce, pas une mission")
        return

    ctx.last_scan = result
    _add_mission_result(result, ctx)


def _add_mission_result(mr, ctx) -> None:
    from uexinfo.models.mission_result import MissionResult
    if not mr.parsed_objectives:
        print_warn("Pas d'objectifs parsés dans ce scan")
        console.print(f"[{C.DIM}]Utilisez /scan debug <fichier> pour diagnostiquer.[/{C.DIM}]")
        return

    kwargs = mr.to_mission_kwargs()
    mm = ctx.mission_manager
    m = Mission(id=0, **kwargs)
    mm.add(m)

    reward_str = f"{m.reward_uec:,}".replace(",", " ")
    print_ok(f"Mission #{m.id} ajoutée : {m.name}  [{C.DIM}]{reward_str} aUEC  {len(m.objectives)} objectif(s)[/{C.DIM}]")
    for o in mr.parsed_objectives:
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
        ("list",             "Liste le catalogue de missions"),
        ("add",              "Depuis le dernier scan (/scan d'abord)"),
        ("add <fichier>",    "Scanne directement un screenshot de contrat"),
        ("add <nom> ...",    "Saisie manuelle (voir ci-dessous)"),
        ("edit <id>",        "Modifie une mission existante"),
        ("remove <id>",      "Supprime une mission du catalogue"),
        ("scan",             "Scan par screenshot (Phase 2)"),
    ]
    for cmd, desc in lines:
        console.print(f"  [bold {C.LABEL}]/mission {cmd:<20}[/bold {C.LABEL}]  [{C.DIM}]{desc}[/{C.DIM}]")
    console.print()
    _show_add_help()
    console.print(f"  [{C.DIM}]Pour planifier un trajet, utilisez /voyage[/{C.DIM}]")


def _show_add_help() -> None:
    console.print(f"  [{C.DIM}]Syntaxe add manuelle :[/{C.DIM}]")
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
