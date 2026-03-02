"""Commande /scan — scanner les terminaux commerciaux."""
from __future__ import annotations

import math
from pathlib import Path

from uexinfo.cli.commands import register
from uexinfo.models.scan_result import ScanResult
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, print_info, make_table
from uexinfo.display import colors as C

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
        ("Qté SCU",   C.NEUTRAL, "right"),
        ("Prix/SCU",  C.UEX,     "right"),
        (delta_hdr,   C.NEUTRAL, "right"),
        ("Marge/SCU", C.NEUTRAL, "right"),
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
            f"{price:,} aUEC".replace(",", "\u202f") if price
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

    # Conseil qualité : si la majorité des prix sont illisibles
    missing = sum(1 for sc in result.commodities if not sc.price)
    if missing > 0 and missing >= len(result.commodities) // 2:
        print_warn(
            f"{missing}/{len(result.commodities)} prix illisibles — "
            "refaites le screenshot (terminal bien centré, interface stable)"
        )


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
    from uexinfo.ocr.watcher import ScreenshotWatcher, SC_DEFAULT_DIR
    sc_dir_str = ctx.cfg.get("scan", {}).get("sc_screenshots_dir", "")
    sc_dir = Path(sc_dir_str) if sc_dir_str else SC_DEFAULT_DIR

    watcher = ScreenshotWatcher(sc_dir)
    latest = watcher.latest_screenshot()
    if not latest:
        print_warn(f"Aucun screenshot dans : {sc_dir}")
        return None

    return _scan_image_file(ctx, latest)


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


def _scan_image_file(ctx, image_path: Path) -> ScanResult | None:
    from uexinfo.ocr.engine import TesseractEngine
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
        return result
    except RuntimeError as e:
        print_error(str(e))
        return None


def _store_result(ctx, result: ScanResult) -> None:
    ctx.last_scan = result
    ctx.scan_history.append(result)
    if len(ctx.scan_history) > 20:
        ctx.scan_history = ctx.scan_history[-20:]


@register("scan")
def cmd_scan(args: list[str], ctx) -> None:
    if not args:
        # Dernier screenshot du dossier Star Citizen
        result = _scan_screenshot_latest(ctx)
        if result:
            _store_result(ctx, result)
            _display_scan(result, ctx)
        return

    sub = args[0].lower()

    # /scan ecran | /scan screen — capture fenêtre SC ou presse-papiers
    if sub in ("ecran", "screen"):
        result = _scan_game_window(ctx)
        if result:
            _store_result(ctx, result)
            _display_scan(result, ctx)
        return

    # /scan screenshot <fichier>
    if sub == "screenshot":
        if len(args) < 2:
            print_error("Usage : /scan screenshot <fichier>")
            return
        image_path = Path(args[1])
        if not image_path.exists():
            print_error(f"Fichier introuvable : {image_path}")
            return
        result = _scan_image_file(ctx, image_path)
        if result:
            _store_result(ctx, result)
            _display_scan(result, ctx)
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
        _display_scan(ctx.last_scan, ctx)
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
            _display_scan(result, ctx)
        return

    # /scan debug <fichier>  — affiche les lignes OCR brutes pour diagnostic
    if sub == "debug":
        if len(args) < 2:
            print_error("Usage : /scan debug <fichier>")
            return
        image_path = Path(args[1])
        if not image_path.exists():
            print_error(f"Fichier introuvable : {image_path}")
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
        console.print(f"\n[bold]Lignes OCR brutes[/bold] — [{C.DIM}]{image_path.name}[/{C.DIM}]")
        lines = engine.debug_lines(image_path)
        for i, line in enumerate(lines):
            console.print(f"  [{C.DIM}]{i:3}[/{C.DIM}]  {line}")
        console.print(f"\n[{C.DIM}]{len(lines)} lignes extraites[/{C.DIM}]")
        return

    print_error(f"Sous-commande inconnue : {sub}  —  /scan [ecran|screenshot|log|status|history|debug]")
