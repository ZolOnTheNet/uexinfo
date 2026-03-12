"""Commande /scan — scanner les terminaux commerciaux."""
from __future__ import annotations

import math
from pathlib import Path

from uexinfo.cli.commands import register
from uexinfo.models.scan_result import ScanResult
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, print_info, make_table
from uexinfo.display import colors as C

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}

_STOCK_BARS = {
    1: "[dim]▒▒▒▒ Out[/dim]",
    2: "[red]▓░░░ Very Low[/red]",
    3: "[yellow]▓▓░░ Low[/yellow]",
    4: "[cyan]▓▓▓░ Medium[/cyan]",
    5: "[green]▓▓▓▓ High[/green]",
    6: "[green]▓▓▓▓ Very High[/green]",
    7: "[bold green]████ Max[/bold green]",
}


def _stock_bar(status: int, label: str) -> str:
    if status in _STOCK_BARS:
        return _STOCK_BARS[status]
    return label or str(status)


def _resolve_uex(sc_name: str, commodities: list):
    """Fuzzy-match un token OCR vers un Commodity UEX via partial_ratio."""
    if not commodities or not sc_name:
        return None
    names = [c.name.upper() for c in commodities]
    try:
        from rapidfuzz import process, fuzz
        r = process.extractOne(
            sc_name.upper(), names, scorer=fuzz.partial_ratio, score_cutoff=80,
        )
        if r:
            return commodities[names.index(r[0])]
    except ImportError:
        sc_up = sc_name.upper()
        # 1. Mot exact dans le nom UEX
        for c in commodities:
            if sc_up in [w.upper() for w in c.name.split()]:
                return c
        # 2. Correspondance approximative du nom complet
        import difflib
        m = difflib.get_close_matches(sc_up, names, n=1, cutoff=0.60)
        if m:
            return commodities[names.index(m[0])]
    return None


def _display_scan(result: ScanResult, ctx) -> None:
    """Affiche un ScanResult en table Rich avec comparaison UEX."""
    is_sell    = result.mode == "sell"
    mode_label = f"[yellow]VENTE[/yellow]" if is_sell else f"[cyan]ACHAT[/cyan]"
    console.print(
        f"\n[bold cyan]{result.terminal}[/bold cyan]"
        f"  [{C.DIM}]{result.timestamp.strftime('%H:%M:%S')}"
        f"  source={result.source}[/{C.DIM}]  {mode_label}"
    )

    if not result.commodities:
        print_warn("Aucune commodité dans ce scan.")
        return

    delta_hdr = "Δ vs moy vente" if is_sell else "Δ vs moy achat"
    t = make_table(
        ("Commodité",  C.LABEL,   "left"),
        ("Stock",      C.NEUTRAL, "left"),
        (f"Qté {C.SCU}",   C.NEUTRAL, "right"),
        (f"Prix/{C.SCU}",  C.UEX,     "right"),
        (delta_hdr,        C.NEUTRAL, "right"),
        (f"Marge/{C.SCU}", C.NEUTRAL, "right"),
    )

    for sc in result.commodities:
        uex_c = _resolve_uex(sc.name, ctx.cache.commodities)

        if uex_c:
            code_tag = f"  [{C.DIM}][{uex_c.code}][/{C.DIM}]" if uex_c.code else ""
            display_name = f"{uex_c.name}{code_tag}"
        else:
            display_name = sc.name

        uex_buy  = (uex_c.price_buy  if uex_c else 0) or 0
        uex_sell = (uex_c.price_sell if uex_c else 0) or 0
        uex_ref  = uex_sell if is_sell else uex_buy

        # Correction facteur-10 : l'OCR perd parfois le séparateur décimal
        # Ex. ¤6.438k/SCU → H643800020k/SCU → 643800020×1000 vs UEX 6438 → ÷10^8
        price = sc.price
        if price and uex_ref:
            ratio = price / uex_ref
            if ratio >= 10:
                exp = round(math.log10(ratio))
                corrected = round(price / (10 ** exp))
                if uex_ref * 0.5 <= corrected <= uex_ref * 2:
                    price = corrected

        qty_str   = str(sc.quantity) if sc.quantity is not None else f"[{C.DIM}]—[/{C.DIM}]"
        # Prix : ? = OCR a échoué (le prix devrait être là), — = pas de donnée UEX
        price_str = (
            f"{price:,} {C.AUEC}".replace(",", "\u202f") if price
            else f"[{C.DIM}]?[/{C.DIM}]"
        )
        stock_str = _stock_bar(sc.stock_status, sc.stock)

        if is_sell:
            delta_positive_is_good = True
            margin = (int(uex_buy) - price) * -1 if uex_buy and price else None
        else:
            delta_positive_is_good = False
            margin = (int(uex_sell) - price) if uex_sell and price else None

        if uex_ref and price:
            delta_pct = (price - uex_ref) / uex_ref * 100
            sign  = "+" if delta_pct >= 0 else ""
            good  = (delta_pct > 5) if delta_positive_is_good else (delta_pct < -5)
            bad   = (delta_pct < -5) if delta_positive_is_good else (delta_pct > 5)
            color = C.PROFIT if good else C.LOSS if bad else C.NEUTRAL
            delta_str = f"[{color}]{sign}{delta_pct:.0f}%[/{color}]"
        else:
            delta_str = f"[{C.DIM}]—[/{C.DIM}]"

        if margin is not None:
            sign  = "+" if margin >= 0 else ""
            color = C.PROFIT if margin > 0 else C.LOSS
            margin_str = f"[{color}]{sign}{margin:,} aUEC[/{color}]".replace(",", "\u202f")
        else:
            margin_str = f"[{C.DIM}]—[/{C.DIM}]"

        t.add_row(display_name, stock_str, qty_str, price_str, delta_str, margin_str)

    console.print(t)
    console.print(f"[{C.DIM}]  Ctrl+↑ pour éditer[/{C.DIM}]")

    # Conseil qualité : si la majorité des prix sont illisibles
    missing = sum(1 for sc in result.commodities if not sc.price)
    if missing > 0 and missing >= len(result.commodities) // 2:
        print_warn(
            f"{missing}/{len(result.commodities)} prix illisibles — "
            "refaites le screenshot (terminal bien centré, interface stable)"
        )


def _screenshots_dir(ctx) -> Path:
    """Retourne le dossier screenshots configuré (ou le défaut SC)."""
    from uexinfo.ocr.watcher import SC_DEFAULT_DIR
    sc_dir_str = ctx.cfg.get("scan", {}).get("sc_screenshots_dir", "")
    return Path(sc_dir_str) if sc_dir_str else SC_DEFAULT_DIR


def _resolve_image_path(raw: str, ctx) -> Path:
    """Résout un chemin image : absolu, relatif, ou nom seul → dossier screenshots."""
    p = Path(raw)
    if p.exists():
        return p
    # Nom seul (pas de séparateur de répertoire) → chercher dans le dossier screenshots
    if not p.parent.parts or str(p.parent) == ".":
        candidate = _screenshots_dir(ctx) / p.name
        if candidate.exists():
            return candidate
    return p  # retourne le chemin original (l'appelant gère l'erreur)


def _do_scan(ctx) -> ScanResult | None:
    """Déclenche un scan selon le mode configuré."""
    mode = ctx.cfg.get("scan", {}).get("mode", "ocr")

    if mode == "log":
        return _scan_log(ctx, log_path=None)
    elif mode == "ocr":
        return _scan_screenshot_latest(ctx)
    elif mode == "confirm":
        # Mode hybride : log en premier, puis OCR pour confirmer
        result = _scan_log(ctx, log_path=None)
        if result:
            return result
        return _scan_screenshot_latest(ctx)
    else:
        print_error(f"Mode inconnu : {mode}")
        return None


def _scan_log(ctx, log_path: Path | None) -> ScanResult | None:
    from uexinfo.ocr.log_parser import LogParser
    try:
        parser = LogParser(log_path)
        results = parser.parse_all()
        if not results:
            print_warn("Aucun scan trouvé dans le log.")
            return None
        return results[-1]
    except Exception as e:
        print_error(f"Erreur lecture log : {e}")
        return None


def _scan_screenshot_latest(ctx) -> ScanResult | None:
    """Scan le screenshot le plus récent (comportement historique)."""
    sc_dir = _screenshots_dir(ctx)
    from uexinfo.ocr.watcher import ScreenshotWatcher
    watcher = ScreenshotWatcher(sc_dir)
    latest = watcher.latest_screenshot()
    if not latest:
        print_warn(f"Aucun screenshot dans : {sc_dir}")
        return None
    return _scan_image_file(ctx, latest)


def _scan_screenshot_new(ctx, max_files: int = 5) -> list:
    """Scanne les screenshots nouveaux depuis le dernier scan (ou les max_files plus récents)."""
    sc_dir = _screenshots_dir(ctx)
    if not sc_dir.exists():
        print_warn(f"Dossier introuvable : {sc_dir}")
        return []

    images = sorted(
        (p for p in sc_dir.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not images:
        print_warn(f"Aucun screenshot dans : {sc_dir}")
        return []

    # Filtrer par rapport au dernier scan connu
    last_ts = getattr(ctx, "_last_scan_mtime", None)
    if last_ts is not None:
        new_images = [p for p in images if p.stat().st_mtime > last_ts]
        if new_images:
            images = new_images[:max_files]
        else:
            print_info("Aucun nouveau screenshot — affichage du plus récent.")
            images = images[:1]
    else:
        images = images[:max_files]

    results = []
    for img_path in reversed(images):   # ordre chronologique
        print_info(f"→ {img_path.name}")
        result = _scan_image_file(ctx, img_path)
        if result:
            results.append(result)

    # Mémoriser le timestamp du fichier le plus récent traité
    if images:
        ctx._last_scan_mtime = max(p.stat().st_mtime for p in images)

    return results


def _capture_sc_window():
    """Capture la fenêtre Star Citizen via win32gui. Retourne une PIL Image ou None."""
    try:
        import win32gui
        from PIL import ImageGrab

        found = []

        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and "Star Citizen" in win32gui.GetWindowText(hwnd):
                found.append(hwnd)

        win32gui.EnumWindows(_enum, None)
        if not found:
            return None

        rect = win32gui.GetWindowRect(found[0])
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w <= 0 or h <= 0:
            return None

        img = ImageGrab.grab(bbox=rect)
        print_info(f"Fenêtre SC capturée : {w}×{h} px")
        return img
    except ImportError:
        return None
    except Exception:
        return None


def _capture_clipboard():
    """Récupère une image depuis le presse-papiers. Retourne une PIL Image ou None."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        if img is not None:
            print_info("Image récupérée depuis le presse-papiers.")
        return img
    except Exception:
        return None


def _scan_game_window(ctx) -> ScanResult | None:
    """Capture la fenêtre SC, le presse-papiers, ou la dernière screenshot — dans cet ordre."""
    import tempfile

    image = _capture_sc_window()
    if image is None:
        image = _capture_clipboard()
    if image is None:
        print_warn("Fenêtre SC introuvable et presse-papiers vide — utilisation du dernier screenshot.")
        return _scan_screenshot_latest(ctx)

    tmp_path = Path(tempfile.mktemp(suffix=".png"))
    try:
        image.save(tmp_path, "PNG")
        return _scan_image_file(ctx, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _refine_terminal(result: ScanResult, location_index) -> None:
    """Affine le nom du terminal OCR par fuzzy match sur le LocationIndex."""
    raw = result.terminal
    if not raw:
        return
    hits = location_index.search(raw, limit=3, types={"terminal"})
    if not hits:
        return
    try:
        from rapidfuzz import fuzz
        best = max(hits, key=lambda h: fuzz.partial_ratio(raw.lower(), h.name.lower()))
        score = fuzz.partial_ratio(raw.lower(), best.name.lower())
        if score >= 55:
            result.terminal = best.name
    except ImportError:
        import difflib
        names = [h.name for h in hits]
        m = difflib.get_close_matches(raw, names, n=1, cutoff=0.4)
        if m:
            result.terminal = m[0]


def _scan_image_file(ctx, image_path: Path):
    """Scan OCR d'une image — retourne ScanResult ou MissionResult selon le type détecté."""
    from uexinfo.ocr.engine import TesseractEngine
    from uexinfo.models.scan_result import ScanResult
    from uexinfo.models.mission_result import MissionResult
    cfg_scan = ctx.cfg.get("scan", {})

    exe = Path(cfg_scan["tesseract_exe"]) if cfg_scan.get("tesseract_exe") else None
    try:
        engine = TesseractEngine(exe=exe)
    except RuntimeError as e:
        print_error(str(e))
        return None

    print_info(f"OCR → {image_path.name}")
    try:
        result = engine.extract_from_image(image_path)
    except RuntimeError as e:
        print_error(str(e))
        return None

    if isinstance(result, MissionResult):
        print_info("Type détecté : écran Contrats (mission)")
        return result

    # ScanResult : affiner le nom du terminal
    if result and ctx.location_index:
        raw = result.terminal
        _refine_terminal(result, ctx.location_index)
        if result.terminal != raw:
            print_info(f"Terminal : {raw!r} → {result.terminal!r}")

    return result


def _display_mission(result) -> None:
    """Affiche un MissionResult en Rich."""
    from uexinfo.display import colors as C
    from uexinfo.models.mission_result import MissionResult

    tab_color = {"OFFERS": "cyan", "ACCEPTED": "green", "HISTORY": "dim"}.get(
        result.tab.upper(), "cyan"
    )
    console.print(
        f"\n[bold]{result.title or '(titre illisible)'}[/bold]"
        f"  [{tab_color}]{result.tab or '?'}[/{tab_color}]"
        f"  [{C.DIM}]{result.timestamp.strftime('%H:%M:%S')}[/{C.DIM}]"
    )

    # Ligne infos
    reward_str = f"[bold green]¤ {result.reward:,}[/bold green]".replace(",", "\u202f") if result.reward else "—"
    console.print(
        f"  [dim]Récompense :[/dim] {reward_str}"
        f"   [dim]Dispo :[/dim] {result.contract_availability or '—'}"
        f"   [dim]Contractant :[/dim] [cyan]{result.contracted_by or '—'}[/cyan]"
    )

    # Objectifs
    if result.objectives:
        console.print(f"\n  [bold]Objectifs principaux[/bold]")
        for obj in result.objectives:
            console.print(f"    [cyan]◇[/cyan] {obj}")

    # Lieux/liens bleus
    if result.blue_text:
        console.print(f"\n  [bold]Lieux importants[/bold] [dim](texte bleu)[/dim]")
        for bt in result.blue_text:
            console.print(f"    [blue]{bt}[/blue]")

    # Liste missions panneau gauche
    if result.mission_list:
        console.print(f"\n  [bold]Autres offres disponibles[/bold]")
        t = make_table(
            ("Mission",     C.LABEL,   "left"),
            ("Récompense",  C.PROFIT,  "right"),
        )
        for title, amt in result.mission_list[:10]:
            amt_str = f"¤ {amt:,}".replace(",", "\u202f") if amt else "—"
            t.add_row(title, amt_str)
        console.print(t)

    console.print("")


def _store_result(ctx, result) -> None:
    ctx.last_scan = result
    ctx.scan_history.append(result)
    if len(ctx.scan_history) > 20:
        ctx.scan_history = ctx.scan_history[-20:]


def _display_result(result, ctx) -> None:
    """Dispatch vers le bon affichage selon le type de résultat."""
    from uexinfo.models.mission_result import MissionResult
    if isinstance(result, MissionResult):
        _display_mission(result)
    else:
        _display_scan(result, ctx)


@register("scan", "s")
def cmd_scan(args: list[str], ctx) -> None:
    if not args:
        # Nouveaux screenshots depuis le dernier scan (ou les 3 plus récents)
        results = _scan_screenshot_new(ctx, max_files=3)
        for result in results:
            _store_result(ctx, result)
            _display_result(result, ctx)
        return

    # /scan <n> — scanner les N plus récents
    if args[0].isdigit():
        n = max(1, min(int(args[0]), 20))
        results = _scan_screenshot_new(ctx, max_files=n)
        for result in results:
            _store_result(ctx, result)
            _display_result(result, ctx)
        return

    sub = args[0].lower()

    # /scan ecran | /scan screen — capture fenêtre SC ou presse-papiers
    if sub in ("ecran", "screen"):
        result = _scan_game_window(ctx)
        if result:
            _store_result(ctx, result)
            _display_result(result, ctx)
        return

    # /scan list — liste les fichiers images du dossier screenshots
    if sub == "list":
        sc_dir = _screenshots_dir(ctx)
        if not sc_dir.exists():
            print_error(f"Dossier introuvable : {sc_dir}")
            return
        images = sorted(
            (p for p in sc_dir.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not images:
            print_warn(f"Aucun fichier image dans : {sc_dir}")
            return
        from uexinfo.display import colors as C
        console.print(f"\n[bold]Screenshots[/bold]  [{C.DIM}]{sc_dir}[/{C.DIM}]")
        console.print(f"[{C.DIM}]Formats supportés : {', '.join(sorted(_IMAGE_SUFFIXES))}[/{C.DIM}]\n")
        import datetime
        for p in images[:30]:
            mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
            age   = mtime.strftime("%Y-%m-%d %H:%M")
            size  = p.stat().st_size // 1024
            console.print(
                f"  [{C.UEX}]{p.name}[/{C.UEX}]"
                f"  [{C.DIM}]{age}  {size} Ko[/{C.DIM}]"
            )
        if len(images) > 30:
            console.print(f"[{C.DIM}]  … et {len(images) - 30} autres[/{C.DIM}]")
        return

    # /scan screenshot <fichier>
    if sub == "screenshot":
        if len(args) < 2:
            print_error("Usage : /scan screenshot <fichier>")
            return
        raw = " ".join(args[1:]).strip("\"'")
        image_path = _resolve_image_path(raw, ctx)
        if not image_path.exists():
            print_error(f"Fichier introuvable : {image_path}")
            return
        result = _scan_image_file(ctx, image_path)
        if result:
            _store_result(ctx, result)
            _display_result(result, ctx)
        return

    # /scan log [<fichier>]
    if sub == "log":
        log_path = None
        if len(args) >= 2:
            log_path = Path(args[1])
            if not log_path.exists():
                print_error(f"Fichier log introuvable : {log_path}")
                return
        elif ctx.cfg.get("scan", {}).get("sc_log_path"):
            log_path = Path(ctx.cfg["scan"]["sc_log_path"])
        # sinon log_parser utilise le chemin auto-détecté

        result = _scan_log(ctx, log_path=log_path)
        if result:
            _store_result(ctx, result)
            _display_scan(result, ctx)
        return

    # /scan status
    if sub == "status":
        if ctx.last_scan is None:
            print_warn("Aucun scan effectué dans cette session.")
            return
        _display_result(ctx.last_scan, ctx)
        return

    # /scan history [n]
    if sub == "history":
        n = 5
        if len(args) >= 2:
            try:
                n = int(args[1])
            except ValueError:
                print_error("n doit être un entier")
                return
        if not ctx.scan_history:
            print_warn("Historique vide.")
            return
        for result in ctx.scan_history[-n:]:
            _display_result(result, ctx)
        return

    # /scan debug <fichier>  — affiche les lignes OCR brutes pour diagnostic
    if sub == "debug":
        if len(args) < 2:
            print_error("Usage : /scan debug <fichier>")
            return
        raw = " ".join(args[1:]).strip("\"'")
        image_path = _resolve_image_path(raw, ctx)
        if not image_path.exists():
            print_error(f"Fichier introuvable : {image_path}  (cherché aussi dans {_screenshots_dir(ctx)})")
            return
        from uexinfo.ocr.engine import TesseractEngine
        cfg_scan = ctx.cfg.get("scan", {})
        exe = Path(cfg_scan["tesseract_exe"]) if cfg_scan.get("tesseract_exe") else None
        try:
            engine = TesseractEngine(exe=exe)
        except RuntimeError as e:
            print_error(str(e))
            return
        from uexinfo.display import colors as C

        # Détection du type
        screen_type = engine.detect_screen_type(image_path)
        console.print(
            f"\n[bold]Debug OCR[/bold] — [{C.DIM}]{image_path.name}[/{C.DIM}]"
            f"  Type détecté : [cyan]{screen_type}[/cyan]"
        )

        if screen_type == "mission":
            # ── Debug mission ──────────────────────────────────────────────
            zones = engine.debug_mission(image_path)
            for zone_name, zone_text in zones.items():
                console.print(f"\n[bold]── {zone_name} ──[/bold]")
                if zone_text.strip():
                    for i, line in enumerate(zone_text.splitlines()):
                        if line.strip():
                            console.print(f"  [{C.DIM}]{i:3}[/{C.DIM}]  {line}")
                else:
                    console.print(f"  [{C.DIM}](vide)[/{C.DIM}]")
        else:
            # ── Debug terminal (existant) ──────────────────────────────────
            console.print(f"\n[bold]Terminal (zone haut-gauche) :[/bold]")
            term_lines = engine.debug_terminal(image_path)
            for tl in term_lines:
                console.print(f"  {tl}")

            console.print(f"\n[bold]Commodités (panneau droit) :[/bold]")
            lines = engine.debug_lines(image_path)
            for i, line in enumerate(lines):
                console.print(f"  [{C.DIM}]{i:3}[/{C.DIM}]  {line}")
            console.print(f"\n[{C.DIM}]{len(lines)} lignes extraites[/{C.DIM}]")
        return

    print_error(f"Sous-commande inconnue : {sub}  —  /scan [list|ecran|screenshot|log|status|history|debug]")
