"""Commande /mission — catalogue de missions."""
from __future__ import annotations

import re
from pathlib import Path

from rich.table import Table

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.adaptive import ColSpec, adaptive_table
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.models.mission import Mission, MissionObjective

_SUBS = frozenset({
    "list", "add", "edit", "remove", "scan", "view", "+",
    "clear", "vider", "effacer",
    # alias français
    "liste", "ajouter", "modifier", "supprimer", "voir",
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

    elif sub in ("view", "voir"):
        _cmd_view(args[1:], ctx)

    elif sub == "+":
        _cmd_add_to_voyage(args[1:], ctx)

    elif sub in ("clear", "vider", "effacer"):
        _cmd_clear(ctx)

    elif sub == "scan":
        _cmd_scan_db(args[1:], ctx)


# ── Clear catalogue ───────────────────────────────────────────────────────────

def _cmd_clear(ctx) -> None:
    """Efface toutes les missions du catalogue (sans toucher à la DB screenshots)."""
    mm = ctx.mission_manager
    n = len(mm.missions)
    if n == 0:
        print_warn("Le catalogue est déjà vide.")
        return
    n_removed = mm.clear()
    print_ok(f"{n_removed} mission(s) effacée(s) du catalogue.")
    console.print(
        f"[{C.DIM}]La base de captures (scan) est inchangée — "
        f"/mission scan pour réimporter.[/{C.DIM}]"
    )


# ── Scan depuis la DB screenshots ─────────────────────────────────────────────

def _cmd_scan_db(args: list[str], ctx) -> None:
    """Lit la ScreenshotDB et affiche les missions capturées pour sélection."""
    import time

    db = getattr(ctx, "screenshot_db", None)
    if db is None:
        # CLI pur : instancier la DB localement (pas d'OcrWorker actif)
        try:
            from uexinfo.cache.screenshot_db import ScreenshotDB
            db = ScreenshotDB()
            ctx.screenshot_db = db
        except Exception as e:
            print_error(f"Impossible d'accéder à la base screenshots : {e}")
            return

    # Paramètre : "all", "today", ou rien (fenêtre scan.hour)
    scope = args[0].lower() if args else ""
    hours = ctx.cfg.get("scan", {}).get("hour", 2)

    if scope == "all":
        since = 0.0
        scope_label = "toute la base"
    elif scope == "today":
        from datetime import datetime
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        scope_label = "aujourd'hui"
    elif scope == "terminal":
        _show_terminal_scans(db, ctx)
        return
    else:
        since = time.time() - hours * 3600
        scope_label = f"{hours}h"

    missions = db.missions(since=since)
    pending  = [e for e in db.pending_entries() if e.file_mtime >= since]

    if not missions and not pending:
        print_warn(f"Aucune mission dans la DB ({scope_label})")
        console.print(f"[{C.DIM}]Les screenshots sont analysés automatiquement toutes les 10s.[/{C.DIM}]")
        console.print(f"[{C.DIM}]Config : /config scan.hour {hours}  /config scan.auto_ocr on[/{C.DIM}]")
        return

    # Overlay disponible ? → envoyer mission_scan_list
    select_fn = getattr(ctx, "select_fn", None)
    send_fn   = getattr(ctx, "_overlay_send_fn", None)
    if send_fn is not None:
        _send_mission_scan_list(send_fn, missions, pending, scope_label, ctx)
        return

    # CLI pur → affichage tableau + saisie
    _display_mission_scan_cli(missions, pending, scope_label, ctx)


def _send_mission_scan_list(send_fn, missions, pending, scope_label, ctx) -> None:
    """Envoie le message mission_scan_list à l'overlay."""
    from uexinfo.ocr.ocr_worker import category_label
    from uexinfo.cache.mission_scan import already_imported_set, compute_entry_distances

    mm = getattr(ctx, "mission_manager", None)
    imported = already_imported_set(mm) if mm else set()
    graph = ctx.cache.transport_graph

    items = []
    for e in missions:
        dist = compute_entry_distances(e, graph)
        items.append({
            "file":            e.file,
            "session_id":      e.session_id,
            "category":        e.category,
            "category_label":  category_label(e.category),
            "title":           e.title,
            "reward":          e.reward,
            "total_scu":       e.total_scu,
            "sources":         e.sources,
            "destinations":    e.destinations,
            "availability":    e.data.get("availability", ""),
            "contracted_by":   e.data.get("contracted_by", ""),
            "objectives":      e.data.get("objectives", []),
            "hour":            e.timestamp.strftime("%H:%M"),
            "errors":          e.errors,
            "already_imported": e.file in imported,
            "distances":       dist,
        })

    send_fn({
        "type":        "mission_scan_list",
        "scope":       scope_label,
        "n_missions":  len(missions),
        "n_pending":   len(pending),
        "items":       items,
    })


def _display_mission_scan_cli(missions, pending, scope_label, ctx) -> None:
    """Affichage CLI du tableau des missions + saisie sélection."""
    from uexinfo.ocr.ocr_worker import category_label

    if pending:
        console.print(f"[{C.WARNING}]⏳ {len(pending)} screenshot(s) en attente d'OCR...[/{C.WARNING}]")

    if not missions:
        print_warn(f"Aucune mission traitée ({scope_label})")
        return

    section(f"Missions détectées — {scope_label} — {len(missions)} screenshot(s)")

    tbl = Table(show_header=True, box=None, padding=(0, 1),
                row_styles=["", "on grey7"])
    tbl.add_column("#",          style=C.DIM,    width=3,  justify="right")
    tbl.add_column("Heure",      style=C.DIM,    width=5)
    tbl.add_column("Catégorie",  style=C.LABEL,  max_width=22)
    tbl.add_column("Titre",      style="bold",   max_width=38)
    tbl.add_column("SCU",        justify="right", width=5)
    tbl.add_column("Récompense", justify="right", width=12)
    tbl.add_column("Départ",     style=C.UEX,    max_width=20)
    tbl.add_column("→",          style=C.DIM,    width=1)
    tbl.add_column("Arrivée",    style=C.UEX,    max_width=20)

    for i, e in enumerate(missions, 1):
        scu_str    = f"{e.total_scu:.0f}{C.SCU}" if e.total_scu else "—"
        reward_str = f"{e.reward:,}".replace(",", " ") if e.reward else "—"
        srcs = ", ".join(e.sources[:2]) or "—"
        dsts = ", ".join(e.destinations[:2]) or "—"
        cat  = category_label(e.category)
        err  = f" [{C.WARNING}]⚠[/{C.WARNING}]" if e.errors else ""
        tbl.add_row(
            str(i), e.timestamp.strftime("%H:%M"), cat,
            e.title + err, scu_str, reward_str, srcs, "→", dsts,
        )

    console.print(tbl)
    console.print()

    # Saisie sélection
    console.print(f"[{C.LABEL}]Sélection[/{C.LABEL}] [{C.DIM}](ex: 1,3,5-8  ou  all  ou  Entrée pour annuler) :[/{C.DIM}] ", end="")
    try:
        raw = input().strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not raw or raw.lower() in ("n", "non", "annuler", "cancel", ""):
        return

    selected = _parse_selection(raw, len(missions))
    if not selected:
        print_warn("Aucune sélection valide")
        return

    console.print()
    console.print(f"[{C.DIM}]Ajouter au : [bold]catalogue[/bold] seulement (c)  ou  catalogue + [bold]voyage actif[/bold] (v) ?[/{C.DIM}] ", end="")
    try:
        dest = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        dest = "c"

    add_to_voyage = dest in ("v", "voyage")
    added = _add_selected_missions(missions, selected, add_to_voyage, ctx)
    console.print()
    if add_to_voyage and ctx.voyage_manager.get_active():
        v = ctx.voyage_manager.get_active()
        print_ok(f"{added} mission(s) ajoutée(s) au catalogue et au voyage « {v.name} »")
    else:
        print_ok(f"{added} mission(s) ajoutée(s) au catalogue")


def _parse_selection(raw: str, max_n: int) -> list[int]:
    """Parse '1,3,5-8' ou 'all' → liste d'indices 0-based."""
    if raw.lower() == "all":
        return list(range(max_n))
    indices = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                for n in range(int(a), int(b) + 1):
                    if 1 <= n <= max_n:
                        indices.append(n - 1)
            except ValueError:
                pass
        else:
            try:
                n = int(part)
                if 1 <= n <= max_n:
                    indices.append(n - 1)
            except ValueError:
                pass
    # dédupliquer en conservant l'ordre
    seen = set()
    return [i for i in indices if not (i in seen or seen.add(i))]


def _add_selected_missions(missions, indices: list[int], add_to_voyage: bool, ctx) -> int:
    """Ajoute les missions sélectionnées au catalogue (et éventuellement au voyage)."""
    from uexinfo.cache.mission_scan import entry_to_mission_result, source_raw_from_entry
    mm = ctx.mission_manager
    vm = ctx.voyage_manager
    added = 0

    for i in indices:
        if i >= len(missions):
            continue
        e = missions[i]
        # Reconstruire MissionResult depuis le dict data de la DB
        mr = entry_to_mission_result(e)
        if mr is None:
            print_warn(f"#{i+1} : données manquantes, ignoré")
            continue
        kwargs = mr.to_mission_kwargs()
        kwargs["source_raw"] = source_raw_from_entry(e)
        kwargs["scanned_at"] = e.file_mtime
        from uexinfo.models.mission import Mission
        m = Mission(id=0, **kwargs)
        mm.add(m)
        added += 1
        console.print(f"  [{C.SUCCESS}]✓[/{C.SUCCESS}] [{C.LABEL}]#{m.id}[/{C.LABEL}] {m.name}")

        if add_to_voyage:
            active = vm.get_active()
            if active:
                active.mission_ids.append(m.id)
                vm.update(active)

    return added


def _show_terminal_scans(db, ctx) -> None:
    """Affiche les terminaux scannés dans la DB."""
    from uexinfo.ocr.ocr_worker import category_label
    terminals = db.terminals()
    if not terminals:
        print_warn("Aucun terminal scanné dans la base")
        return
    section(f"Terminaux scannés — {len(terminals)} captures")
    tbl = Table(show_header=True, box=None, padding=(0, 1),
                row_styles=["", "on grey7"])
    tbl.add_column("Heure",    style=C.DIM,   width=8)
    tbl.add_column("Terminal", style=C.LABEL, max_width=30)
    tbl.add_column("Type",     style=C.DIM,   width=12)
    tbl.add_column("Commodités", justify="right", width=5)
    for e in terminals:
        n_comm = len(e.data.get("commodities", []))
        tbl.add_row(
            e.timestamp.strftime("%d/%m %H:%M"),
            e.data.get("terminal", e.file),
            category_label(e.category),
            str(n_comm),
        )
    console.print(tbl)


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

    # Colonnes fixes : # 3, Scan 16, Dist 6, SCU 5, Récompense 12, Syn 4 = 46
    # Colonnes flexibles : Nom / Départ / Arrivée — poids égaux (1/1/1)
    tbl = adaptive_table([
        ColSpec("#",          width=3,  justify="right", style=C.DIM),
        ColSpec("Scan",       width=16,                  style=C.DIM),
        ColSpec("Nom",        flex=1,   min_flex=12,     style=C.LABEL),
        ColSpec("Départ",     flex=1,   min_flex=10,     style=C.UEX),
        ColSpec("Arrivée",    flex=1,   min_flex=10,     style=C.UEX),
        ColSpec("Dist",       width=6,  justify="right"),
        ColSpec("SCU",        width=5,  justify="right"),
        ColSpec("Récompense", width=12, justify="right"),
        ColSpec("Syn",        width=4),
    ], row_styles=["", "on grey7"])

    graph = ctx.cache.transport_graph
    player = getattr(ctx, "player", None)
    player_loc = player.location if player and player.location else None
    player_node = _resolve_graph_node(player_loc, graph) if player_loc else None
    _dist_cache: dict = {}
    from datetime import datetime as _dt

    for m in mm.missions:
        scu_str    = f"{m.total_scu:.0f}{C.SCU}" if m.total_scu else "—"
        reward_str = f"{m.reward_uec // 1000}K{C.AUEC}" if m.reward_uec >= 1000 else f"{m.reward_uec}{C.AUEC}"
        tags       = " ".join(mm.synergies(m))

        # Date de scan + clé screenshot (ex: "8FE" depuis "ocr:ScreenShot-...-8FE.jpg")
        if m.scanned_at:
            scan_str = _dt.fromtimestamp(m.scanned_at).strftime("%d/%m %H:%M")
        elif m.source_raw == "manual":
            scan_str = "manuel"
        elif m.source_raw == "trade":
            scan_str = "trade"
        else:
            scan_str = "—"
        if m.source_raw and m.source_raw.startswith("ocr:"):
            _km = re.search(r'-([0-9A-Fa-f]{3,4})\.jpg$', m.source_raw)
            if _km:
                scan_str += f" {_km.group(1)}"

        srcs_parts = []
        for loc in m.all_sources[:3]:
            short = _short_loc(loc)
            d = _player_dist(player_node, loc, graph, _dist_cache) if player_node else None
            srcs_parts.append(f"{short} ({d})" if d else short)

        dsts_parts = []
        for loc in m.all_destinations[:3]:
            short = _short_loc(loc)
            d = _player_dist(player_node, loc, graph, _dist_cache) if player_node else None
            dsts_parts.append(f"{short} ({d})" if d else short)

        srcs_str = "\n".join(srcs_parts) if srcs_parts else "—"
        dsts_str = "\n".join(dsts_parts) if dsts_parts else "—"

        # Distance src→dst de la mission
        dist_str = "?"
        for src_loc in m.all_sources[:1]:
            for dst_loc in m.all_destinations[:1]:
                sn = _resolve_graph_node(src_loc, graph)
                dn = _resolve_graph_node(dst_loc, graph)
                if sn and dn:
                    try:
                        r = graph.find_shortest_path(sn, dn)
                        if r and r.total_distance is not None:
                            dist_str = _fmt_dist(r.total_distance)
                    except Exception:
                        pass

        has_delay = any(o.time_cost for o in m.objectives)
        name_display = m.name + (f" [{C.WARNING}]⏱[/{C.WARNING}]" if has_delay else "")

        tbl.add_row(
            str(m.id), scan_str,
            name_display, srcs_str, dsts_str,
            dist_str, scu_str, reward_str, tags,
        )

    player_hint = f" · depuis {_short_loc(player_loc)}" if player_loc else ""
    active_voyage = ctx.voyage_manager.get_active() if hasattr(ctx, "voyage_manager") else None

    overlay_fn = getattr(ctx, "_overlay_send_fn", None)
    if overlay_fn is not None:
        _send_mission_list_actions(overlay_fn, mm, ctx, active_voyage)
    else:
        console.print(tbl)
        if active_voyage:
            console.print(f"\n[{C.DIM}]{len(mm.missions)} mission(s){player_hint} · "
                          f"[bold {C.LABEL}]+<id>[/bold {C.LABEL}] [{C.DIM}]ajoute au voyage «[/{C.DIM}] "
                          f"[{C.LABEL}]{active_voyage.name}[/{C.LABEL}] [{C.DIM}]»[/{C.DIM}]")
            console.print(f"[{C.DIM}]  ex: /mission + 42  ou  /voyage mission add 42[/{C.DIM}]")
        else:
            console.print(f"\n[{C.DIM}]{len(mm.missions)} mission(s){player_hint} · /mission add <fichier> ou <nom> · /voyage pour planifier[/{C.DIM}]")



def _send_mission_list_actions(send_fn, mm, ctx, active_voyage=None) -> None:
    """Envoie le catalogue de missions à l'overlay pour affichage avec boutons d'action inline."""
    from datetime import datetime as _dt

    graph = ctx.cache.transport_graph
    player = getattr(ctx, "player", None)
    player_loc = player.location if player and player.location else None
    player_node = _resolve_graph_node(player_loc, graph) if player_loc else None
    _dist_cache: dict = {}

    # Résoudre les chemins absolus pour les screenshots
    try:
        from uexinfo.cache.screenshot_db import ScreenshotDB as _SDB
        _sdb = getattr(ctx, "screenshot_db", None) or _SDB()
    except Exception:
        _sdb = None

    items = []
    for m in mm.missions:
        scu_str    = f"{m.total_scu:.0f}" if m.total_scu else ""
        reward_str = f"{m.reward_uec // 1000}K" if m.reward_uec and m.reward_uec >= 1000 else str(m.reward_uec or 0)
        tags       = " ".join(mm.synergies(m))

        if m.scanned_at:
            scan_str = _dt.fromtimestamp(m.scanned_at).strftime("%d/%m %H:%M")
        elif m.source_raw == "manual":
            scan_str = "manuel"
        elif m.source_raw == "trade":
            scan_str = "trade"
        else:
            scan_str = "—"

        screenshot_key  = None
        screenshot_path = None
        if m.source_raw and m.source_raw.startswith("ocr:"):
            filename = m.source_raw[4:]
            km = re.search(r'-([0-9A-Fa-f]{3,4})\.jpg$', filename, re.IGNORECASE)
            if km:
                screenshot_key = km.group(1)
                scan_str += f" {screenshot_key}"
            if _sdb:
                try:
                    entry = _sdb.get(filename)
                    if entry and entry.path:
                        screenshot_path = entry.path
                except Exception:
                    pass

        srcs = list(m.all_sources[:3])
        dsts = list(m.all_destinations[:3])

        dist_str = ""
        for src_loc in m.all_sources[:1]:
            for dst_loc in m.all_destinations[:1]:
                sn = _resolve_graph_node(src_loc, graph)
                dn = _resolve_graph_node(dst_loc, graph)
                if sn and dn:
                    try:
                        r = graph.find_shortest_path(sn, dn)
                        if r and r.total_distance is not None:
                            dist_str = _fmt_dist(r.total_distance)
                    except Exception:
                        pass

        items.append({
            "id":              m.id,
            "name":            m.name or "",
            "scan":            scan_str,
            "scu":             scu_str,
            "reward":          reward_str,
            "sources":         srcs,
            "destinations":    dsts,
            "dist":            dist_str,
            "synergies":       tags,
            "has_delay":       any(o.time_cost for o in m.objectives),
            "screenshot_key":  screenshot_key,
            "screenshot_path": screenshot_path,
        })

    send_fn({
        "type":          "mission_actions_inline",
        "missions":      items,
        "active_voyage": active_voyage.name if active_voyage else None,
    })


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


from uexinfo.display.loc import loc_display as _loc_display


def _short_loc(name: str, max_chars: int = 20) -> str:
    """Code court d'un lieu — délègue à loc_display (alimente le registre overlay)."""
    return _loc_display(name, max_chars=max_chars, short=True)


def _fmt_dist(d_gm: float) -> str:
    """Distance compacte : 65.2 Gm → '65G',  0.012 Gm → '12M',  ~0 → 'ici'."""
    if d_gm < 0.0005:
        return "ici"
    if d_gm >= 1:
        return f"{d_gm:.0f}G"
    return f"{d_gm * 1000:.0f}M"


def _player_dist(player_node: str, loc_name: str, graph, cache: dict) -> str | None:
    """Retourne la distance formatée player_node → loc_name (avec cache)."""
    key = (player_node, loc_name)
    if key in cache:
        return cache[key]
    node = _resolve_graph_node(loc_name, graph)
    result_str = None
    if node:
        try:
            r = graph.find_shortest_path(player_node, node)
            if r and r.total_distance is not None:
                result_str = _fmt_dist(r.total_distance)
        except Exception:
            pass
    cache[key] = result_str
    return result_str


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
    all_missions = mm.missions
    if not all_missions:
        print_error("Aucune mission enregistrée")
        return

    # Parse args: no args → all, range "1-5", or list of IDs
    if not args:
        missions = all_missions
    else:
        refs: list[str] = []
        for a in args:
            iv = re.match(r"^(\d+)-(\d+)$", a)
            if iv:
                refs += [str(x) for x in range(int(iv.group(1)), int(iv.group(2)) + 1)]
            else:
                refs.append(a)
        missions = []
        for ref in refs:
            m = mm.get(ref)
            if m:
                missions.append(m)
            else:
                print_warn(f"Mission introuvable : {ref}")
        if not missions:
            return

    # Build location names from graph + LocationIndex
    loc_names: list[str] = []
    try:
        graph = ctx.cache.load_transport_graph()
        loc_names += list(graph.keys())
    except Exception:
        pass
    if ctx.location_index:
        for e in ctx.location_index._entries:
            n = e.name.strip()
            if n and n not in loc_names:
                loc_names.append(n)

    # Mode overlay : envoyer les données via WebSocket, pas de TUI terminal
    overlay_fn = getattr(ctx, "_overlay_send_fn", None)
    if overlay_fn is not None:
        # Résoudre les chemins absolus via ScreenshotDB
        try:
            from uexinfo.cache.screenshot_db import ScreenshotDB as _SDB
            _sdb = getattr(ctx, "screenshot_db", None) or _SDB()
        except Exception:
            _sdb = None

        def _mission_dict(m):
            d = {
                "id":           m.id,
                "name":         m.name or "",
                "reward":       m.reward_uec or 0,
                "scu":          m.total_scu or 0,
                "sources":      list(m.all_sources),
                "destinations": list(m.all_destinations),
                "screenshot_key":  None,
                "screenshot_path": None,
            }
            src = m.source_raw or ""
            if src.startswith("ocr:"):
                filename = src[4:]
                km = re.search(r"-([0-9A-Fa-f]{3,4})\.jpg", filename, re.IGNORECASE)
                if km:
                    d["screenshot_key"] = km.group(1)
                # Résoudre le chemin absolu
                if _sdb:
                    try:
                        entry = _sdb.get(filename)
                        if entry and entry.path:
                            d["screenshot_path"] = entry.path
                    except Exception:
                        pass
            return d

        overlay_fn({
            "type":           "mission_edit",
            "missions":       [_mission_dict(m) for m in missions],
            "location_names": loc_names,
        })
        return

    print_warn("Édition des missions uniquement disponible depuis l'overlay.")


# ── Remove ────────────────────────────────────────────────────────────────────

def _cmd_remove(args: list[str], ctx) -> None:
    mm = ctx.mission_manager
    if not args:
        print_error("Identifiant de mission manquant")
        return

    # Développer les intervalles  ex: "5-23" → ["5","6",...,"23"]
    refs: list[str] = []
    for a in args:
        iv = re.match(r"^(\d+)-(\d+)$", a)
        if iv:
            lo, hi = int(iv.group(1)), int(iv.group(2))
            if lo > hi:
                lo, hi = hi, lo
            refs.extend(str(i) for i in range(lo, hi + 1))
        else:
            refs.append(a)

    removed, not_found = 0, []
    for ref in refs:
        if mm.remove(ref):
            removed += 1
        else:
            not_found.append(ref)

    if removed:
        print_ok(f"{removed} mission(s) supprimée(s)")
    if not_found:
        if len(refs) == 1:
            print_error(f"Mission introuvable : {not_found[0]}")
        else:
            print_warn(f"Introuvable(s) : {', '.join(not_found)}")


# ── View ─────────────────────────────────────────────────────────────────────

def _cmd_view(args: list[str], ctx) -> None:
    """Affiche le détail d'une mission + distances croisées sources × destinations."""
    mm = ctx.mission_manager
    if not mm.missions:
        print_warn("Aucune mission dans le catalogue")
        return

    m = None
    if args:
        m = mm.get(args[0])
        if not m:
            print_error(f"Mission introuvable : {args[0]}")
            return
    else:
        # Picker
        section("Choisir une mission")
        for ms in mm.missions:
            src = _short_loc(ms.all_sources[0]) if ms.all_sources else "?"
            dst = _short_loc(ms.all_destinations[0]) if ms.all_destinations else "?"
            console.print(f"  [{C.LABEL}]{ms.id:3}[/{C.LABEL}]  [{C.DIM}]{ms.name}[/{C.DIM}]  {src} → {dst}")
        console.print(f"[{C.LABEL}]Numéro :[/{C.LABEL}] ", end="")
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            return
        m = mm.get(raw)
        if not m:
            print_error(f"Mission introuvable : {raw}")
            return

    graph = ctx.cache.transport_graph
    player = getattr(ctx, "player", None)
    player_loc = player.location if player and player.location else None
    player_node = _resolve_graph_node(player_loc, graph) if player_loc else None

    # ── En-tête mission ────────────────────────────────────────────────────
    section(f"Mission #{m.id} — {m.name}")
    reward_str = f"{m.reward_uec // 1000}K{C.AUEC}" if m.reward_uec >= 1000 else f"{m.reward_uec}{C.AUEC}"
    scu_str    = f"{m.total_scu:.0f}{C.SCU}" if m.total_scu else ""
    console.print(f"  [{C.LABEL}]Récompense:[/{C.LABEL}] {reward_str}" +
                  (f"   [{C.LABEL}]Fret:[/{C.LABEL}] {scu_str}" if scu_str else ""))

    sources      = m.all_sources      or []
    destinations = m.all_destinations or []

    if not sources and not destinations:
        console.print(f"  [{C.DIM}]Aucun objectif de transport.[/{C.DIM}]")
        return

    _dist_cache: dict = {}
    from_label = _short_loc(player_loc) if player_loc else "?"

    # ── Distance joueur → sources (ou destinations si pas de sources) ──────
    locs_for_player = sources if sources else destinations
    locs_label = "départs" if sources else "destinations"
    if player_node and locs_for_player:
        console.print()
        console.print(f"  [{C.LABEL}]Distance depuis {from_label} vers {locs_label} :[/{C.LABEL}]")
        for loc in locs_for_player:
            d = _player_dist(player_node, loc, graph, _dist_cache)
            console.print(f"    → [{C.UEX}]{_short_loc(loc)}[/{C.UEX}]  {d or '?'}")

    # ── Table croisée sources × destinations ──────────────────────────────
    if sources and destinations:
        console.print()

        matrix: dict[tuple, tuple[float | None, str]] = {}
        for src in sources:
            src_node = _resolve_graph_node(src, graph)
            for dst in destinations:
                dst_node = _resolve_graph_node(dst, graph)
                raw_d, fmt_d = None, "?"
                if src_node and dst_node:
                    try:
                        r = graph.find_shortest_path(src_node, dst_node)
                        if r and r.total_distance is not None:
                            raw_d = r.total_distance
                            fmt_d = _fmt_dist(raw_d)
                    except Exception:
                        pass
                matrix[(src, dst)] = (raw_d, fmt_d)

        raw_vals = [v[0] for v in matrix.values() if v[0] is not None]
        min_d = min(raw_vals) if raw_vals else None

        tbl = Table(show_header=True, box=None, padding=(0, 1))
        tbl.add_column("Départ \\ Arrivée", style=C.LABEL, min_width=12)
        for dst in destinations:
            tbl.add_column(_short_loc(dst), justify="right", min_width=8)

        for src in sources:
            row = [_short_loc(src)]
            for dst in destinations:
                raw_d, fmt_d = matrix[(src, dst)]
                is_min = (raw_d is not None and min_d is not None
                          and abs(raw_d - min_d) < 0.001)
                row.append(f"[bold green]{fmt_d}[/bold green]" if is_min else fmt_d)
            tbl.add_row(*row)

        console.print(tbl)


# ── Ajout rapide au voyage ────────────────────────────────────────────────────

def _cmd_add_to_voyage(args: list[str], ctx) -> None:
    """Ajoute une ou plusieurs missions au voyage actif."""
    vm = ctx.voyage_manager
    active = vm.get_active()
    if not active:
        print_warn("Aucun voyage actif — activez-en un avec /voyage on <id>")
        return

    mm = ctx.mission_manager
    if not args:
        print_error("Identifiant(s) de mission manquant(s)  ex: /mission + 42")
        return

    # Développer les intervalles
    refs: list[str] = []
    for a in args:
        iv = re.match(r"^(\d+)-(\d+)$", a)
        if iv:
            lo, hi = int(iv.group(1)), int(iv.group(2))
            if lo > hi:
                lo, hi = hi, lo
            refs.extend(str(i) for i in range(lo, hi + 1))
        else:
            refs.append(a)

    added, not_found = 0, []
    for ref in refs:
        m = mm.get(ref)
        if not m:
            not_found.append(ref)
            continue
        if m.id not in active.mission_ids:
            active.mission_ids.append(m.id)
            added += 1
        else:
            console.print(f"  [{C.DIM}]#{m.id} déjà dans le voyage[/{C.DIM}]")

    if added:
        vm.update(active)
        print_ok(f"{added} mission(s) ajoutée(s) au voyage « {active.name} »")
    if not_found:
        print_warn(f"Introuvable(s) : {', '.join(not_found)}")


# ── Aide ─────────────────────────────────────────────────────────────────────

def _show_help() -> None:
    section("Aide — /mission")
    lines = [
        ("list",             "Liste le catalogue de missions"),
        ("view [id]",        "Détail + distances croisées d'une mission"),
        ("add",              "Depuis le dernier scan (/scan d'abord)"),
        ("add <fichier>",    "Scanne directement un screenshot de contrat"),
        ("add <nom> ...",    "Saisie manuelle (voir ci-dessous)"),
        ("edit <id>",        "Modifie une mission existante"),
        ("remove <id|a-b>",  "Supprime une mission ou un intervalle (ex: 5-23)"),
        ("+ <id>",           "Ajoute la mission au voyage actif"),
        ("scan",             "Liste les missions des screenshots récents (DB OCR)"),
        ("scan all",         "Toute la base de screenshots"),
        ("scan today",       "Captures d'aujourd'hui"),
        ("scan terminal",    "Terminaux scannés"),
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
