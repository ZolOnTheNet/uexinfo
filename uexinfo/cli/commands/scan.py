"""Commande /scan — scanner les terminaux commerciaux."""
from __future__ import annotations

import math
from pathlib import Path

from uexinfo.cli.commands import register
from uexinfo.models.scan_result import ScanResult
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, print_info, make_table, section
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


def _resolve_uex(sc_name: str, commodities: list, commodity_id: int = 0):
    """Résout un nom OCR vers un Commodity UEX.

    Priorité :
    1. Correspondance exacte par commodity_id (si fourni)
    2. Correspondance exacte par nom (insensible à la casse)
    3. Fuzzy WRatio ≥ 85 (évite les faux positifs comme GOLD ↔ GOLDEN MEDMON)
    """
    if not commodities:
        return None

    # 1. Lookup par ID (le plus fiable — SC-Datarunner l'a déjà résolu)
    if commodity_id:
        for c in commodities:
            if c.id == commodity_id:
                return c

    if not sc_name:
        return None

    sc_up = sc_name.upper()
    names = [c.name.upper() for c in commodities]

    # 2. Correspondance exacte insensible à la casse
    if sc_up in names:
        return commodities[names.index(sc_up)]

    # 3. Fuzzy WRatio (global, symétrique) — pas partial_ratio qui retourne 100
    #    pour des sous-chaînes comme GOLD dans GOLDEN MEDMON
    try:
        from rapidfuzz import process, fuzz
        r = process.extractOne(sc_up, names, scorer=fuzz.WRatio, score_cutoff=85)
        if r:
            return commodities[names.index(r[0])]
    except ImportError:
        import difflib
        m = difflib.get_close_matches(sc_up, names, n=1, cutoff=0.75)
        if m:
            return commodities[names.index(m[0])]
    return None





def _fetch_terminal_uex_prices(result: ScanResult, ctx) -> dict[str, tuple[int, float]]:
    """Prix UEX spécifiques au terminal pour les commodités du scan.

    Retourne {commodity_name_lower: (price, date_modified_unix)}.
    Utilise _price_cache de ctx.  Retourne {} si ambigu ou indisponible.
    """
    import time
    from uexinfo.api.uex_client import UEXClient, UEXError

    name_lower = result.terminal.lower()
    is_sell    = result.mode == "sell"
    price_key  = "price_sell" if is_sell else "price_buy"

    # Terminal exact dans le cache ?
    matches = [
        t for t in ctx.cache.terminals
        if t.name.rsplit(" - ", 1)[-1].strip().lower() == name_lower
    ]
    terminal = matches[0] if len(matches) == 1 else None

    def _fetch(key: str, **kwargs) -> list[dict]:
        cached = ctx._price_cache.get(key)
        if cached:
            _ts, data = cached
            return data
        client = UEXClient()
        try:
            data = client.get_prices(**kwargs)
        except UEXError:
            return []
        ctx._price_cache[key] = (time.time(), data)
        return data

    rows = (_fetch(f"t{terminal.id}", id_terminal=terminal.id) if terminal
            else _fetch(f"tl_{name_lower}", terminal_name=name_lower))

    # Si plusieurs terminaux dans la réponse → ambigu, on ne peut pas attribuer
    term_names = {r.get("terminal_name") for r in rows if r.get(price_key)}
    if len(term_names) > 1:
        return {}

    result_map: dict[str, tuple[int, float]] = {}
    for r in rows:
        price = r.get(price_key)
        cname = (r.get("commodity_name") or "").lower()
        if price and cname:
            try:
                mdate = float(r.get("date_modified") or 0)
            except (TypeError, ValueError):
                mdate = 0.0
            result_map[cname] = (int(price), mdate)
    return result_map


def _display_scan(result: ScanResult, ctx) -> None:
    """Affiche un ScanResult en table Rich avec comparaison UEX terminale."""
    is_sell    = result.mode == "sell"
    mode_label = f"[yellow]VENTE[/yellow]" if is_sell else f"[cyan]ACHAT[/cyan]"
    valid_badge = (
        f"  [bold green]✓ validé UEX[/bold green]" if result.validated
        else f"  [{C.DIM}]en attente[/{C.DIM}]"
    ) if result.source == "log" else ""
    console.print(
        f"\n[bold cyan]{result.terminal}[/bold cyan]"
        f"  [{C.DIM}]{result.timestamp.strftime('%H:%M:%S')}"
        f"  source={result.source}[/{C.DIM}]  {mode_label}{valid_badge}"
    )

    if not result.commodities:
        print_warn("Aucune commodité dans ce scan.")
        return

    # Prix UEX spécifiques à ce terminal (vide si ambigu/indisponible)
    uex_term = _fetch_terminal_uex_prices(result, ctx)
    has_term  = bool(uex_term)

    price_color  = C.PROFIT if is_sell else C.UEX
    uex_hdr      = ("UEX vente" if is_sell else "UEX achat") + f"/{C.SCU}"
    delta_hdr    = "Δ UEX term" if has_term else ("Δ moy vente" if is_sell else "Δ moy achat")

    cols = [
        ("Commodité",        C.LABEL,    "left"),
        ("Stock",            C.NEUTRAL,  "left"),
        (f"Qté {C.SCU}",    C.NEUTRAL,  "right"),
        (f"Scanné/{C.SCU}", C.UEX,      "right"),
        (uex_hdr,            price_color,"right"),
        (delta_hdr,          C.NEUTRAL,  "right"),
        (f"Marge/{C.SCU}",  C.NEUTRAL,  "right"),
    ]
    t = make_table(*cols)

    scan_ts = result.timestamp.timestamp()

    for sc in result.commodities:
        uex_c = _resolve_uex(sc.name, ctx.cache.commodities, sc.commodity_id)

        if uex_c:
            code_tag     = f"  [{C.DIM}][{uex_c.code}][/{C.DIM}]" if uex_c.code else ""
            display_name = f"{uex_c.name}{code_tag}"
        else:
            display_name = sc.name

        # Prix UEX global (moyenne commodité)
        uex_buy_avg  = (uex_c.price_buy  if uex_c else 0) or 0
        uex_sell_avg = (uex_c.price_sell if uex_c else 0) or 0

        # Prix UEX terminal-spécifique
        lookup_key = (uex_c.name if uex_c else sc.name).lower()
        term_entry = uex_term.get(lookup_key) or uex_term.get(sc.name.lower())
        uex_term_price, uex_term_date = term_entry if term_entry else (0, 0.0)

        # Référence pour delta : terminal si dispo, sinon moyenne globale
        if has_term and uex_term_price:
            uex_ref = uex_term_price
        else:
            uex_ref = uex_sell_avg if is_sell else uex_buy_avg

        # Correction facteur-10 OCR
        price = sc.price
        if price and uex_ref:
            ratio = price / uex_ref
            if ratio >= 10:
                exp = round(math.log10(ratio))
                corrected = round(price / (10 ** exp))
                if uex_ref * 0.5 <= corrected <= uex_ref * 2:
                    price = corrected

        qty_str   = str(sc.quantity) if sc.quantity is not None else f"[{C.DIM}]—[/{C.DIM}]"
        stock_str = _stock_bar(sc.stock_status, sc.stock)

        # Prix scanné : si 0 et scan validé → OCR a raté, l'utilisateur a corrigé avant soumission
        # On affiche "corrigé" et on utilise le prix UEX comme référence
        price_corrected = False
        if not price and result.validated and uex_term_price:
            price = uex_term_price
            price_corrected = True

        if price:
            raw = f"{price:,} {C.AUEC}".replace(",", "\u202f")
            price_str = (
                f"[{C.DIM}]~{raw}[/{C.DIM}]"  # approximatif (corrigé par UEX)
                if price_corrected else raw
            )
        else:
            price_str = f"[{C.DIM}]?[/{C.DIM}]"  # OCR raté, pas de référence UEX

        # Colonne UEX terminal
        if uex_term_price:
            scan_newer = scan_ts > uex_term_date if uex_term_date else False
            uex_t_str  = f"{uex_term_price:,} {C.AUEC}".replace(",", "\u202f")
            # Grisé si le scan est plus récent et le prix diffère (scan prime sur UEX)
            if scan_newer and not price_corrected and price and price != uex_term_price:
                uex_t_str = f"[{C.DIM}]{uex_t_str}[/{C.DIM}]"
        else:
            uex_t_str = f"[{C.DIM}]—[/{C.DIM}]"

        # Delta % vs référence
        if uex_ref and price:
            delta_pct = (price - uex_ref) / uex_ref * 100
            sign  = "+" if delta_pct >= 0 else ""
            if is_sell:
                good = delta_pct > 5
                bad  = delta_pct < -5
            else:
                good = delta_pct < -5
                bad  = delta_pct > 5
            color     = C.PROFIT if good else C.LOSS if bad else C.NEUTRAL
            delta_str = f"[{color}]{sign}{delta_pct:.0f}%[/{color}]"
        else:
            delta_str = f"[{C.DIM}]—[/{C.DIM}]"

        # Marge (vs prix moyen opposé)
        uex_opp = uex_buy_avg if is_sell else uex_sell_avg
        if uex_opp and price:
            margin = (price - int(uex_opp)) if is_sell else (int(uex_opp) - price)
            sign   = "+" if margin >= 0 else ""
            color  = C.PROFIT if margin > 0 else C.LOSS
            margin_str = f"[{color}]{sign}{margin:,} aUEC[/{color}]".replace(",", "\u202f")
        else:
            margin_str = f"[{C.DIM}]—[/{C.DIM}]"

        t.add_row(display_name, stock_str, qty_str, price_str, uex_t_str, delta_str, margin_str)

    console.print(t)
    if has_term:
        console.print(f"[{C.DIM}]  Δ UEX term = vs prix UEX spécifique à ce terminal[/{C.DIM}]")
    console.print(f"[{C.DIM}]  Ctrl+↑ pour éditer[/{C.DIM}]")

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
        results = _scan_log(ctx, log_path=None)
        return results[-1] if results else None
    elif mode == "ocr":
        return _scan_screenshot_latest(ctx)
    elif mode == "confirm":
        # Mode hybride : log en premier, puis OCR pour confirmer
        results = _scan_log(ctx, log_path=None)
        if results:
            return results[-1]
        return _scan_screenshot_latest(ctx)
    else:
        print_error(f"Mode inconnu : {mode}")
        return None


def _resolve_log_path(path_args: list[str], ctx) -> Path | None:
    """Résout le chemin du fichier log depuis les args ou la config.

    Retourne None (avec message d'erreur) si le chemin est invalide.
    Retourne None silencieusement si aucun arg et aucune config (le parser utilisera _DEFAULT_LOG).
    """
    if path_args:
        p = Path(" ".join(path_args).strip("\"'"))
        if not p.is_file():
            print_error(f"Fichier log introuvable : {p}")
            return None
        return p
    sc_log = ctx.cfg.get("scan", {}).get("sc_log_path", "")
    if sc_log:
        p = Path(sc_log)
        if not p.is_file():
            print_error(f"sc_log_path n'est pas un fichier : {p}")
            return None
        return p
    return None  # LogParser utilisera _DEFAULT_LOG


def _scan_log(ctx, log_path: Path | None, full: bool = False) -> list[ScanResult]:
    """Lit le log SC-Datarunner.

    full=False → parse_new() : uniquement les nouvelles lignes depuis le dernier offset.
    full=True  → parse_all() : relit tout le fichier sans modifier l'offset.
    """
    from uexinfo.ocr.log_parser import LogParser, _DEFAULT_LOG
    try:
        parser = LogParser(log_path)
        # Vérifier que le fichier existe à chaque appel (pas seulement au démarrage)
        effective_path = parser.log_path
        if not effective_path.is_file():
            print_warn(f"Fichier log introuvable : {effective_path}")
            console.print(
                f"[{C.DIM}]Configurez le chemin avec : /config scan logpath <chemin>[/{C.DIM}]"
            )
            return []
        # Marquer le log comme "vu" même si aucun nouveau scan (évite le clignotement permanent)
        try:
            ctx.log_last_mtime = effective_path.stat().st_mtime
        except OSError:
            pass
        results = parser.parse_all() if full else parser.parse_new()
        if not results:
            if full:
                print_warn(f"Aucun scan trouvé dans le log.")
            else:
                print_warn(f"Aucun nouveau scan dans le log. (offset: {parser.get_offset()} octets)")
                console.print(f"[{C.DIM}]Utilisez /scan log pour tout relire depuis le début.[/{C.DIM}]")
            return results

        # Pour les scans validés (soumis à UEX), remplacer les données OCR brutes
        # par les prix UEX frais qui reflètent les corrections faites dans SC-Datarunner.
        refreshed = 0
        for r in results:
            if r.validated:
                if _refresh_validated_from_uex(r, ctx):
                    refreshed += 1
        if refreshed:
            console.print(
                f"[{C.DIM}]  {refreshed} scan(s) validé(s) rechargés depuis l'API UEX "
                f"(données post-correction).[/{C.DIM}]"
            )

        # ── Centraliser dans ScreenshotDB (clés synthétiques "log_…") ────────
        for r in results:
            _upsert_to_db(r, None, ctx)

        return results
    except Exception as e:
        print_error(f"Erreur lecture log : {e}")
        return []


def check_log_auto(ctx) -> list[ScanResult]:
    """Vérifie si le fichier log a changé (mtime) et lit les nouveaux scans.

    Respecte les flags /auto :
    - auto.log        : si False, retourne [] sans rien faire
    - auto.log_accept : si True, stocke dans ctx.last_scan/scan_history
    - auto.signal_scan: si False, traite silencieusement et retourne []

    Retourne les nouveaux ScanResult à afficher (vide si rien ou signal_scan=off).
    """
    from uexinfo.ocr.log_parser import LogParser, _DEFAULT_LOG

    auto_cfg = ctx.cfg.get("auto", {})
    if not auto_cfg.get("log", True):
        return []

    log_path_str = ctx.cfg.get("scan", {}).get("sc_log_path", "")
    log_path = Path(log_path_str) if log_path_str else _DEFAULT_LOG

    if not log_path.is_file():
        return []

    try:
        mtime = log_path.stat().st_mtime
    except OSError:
        return []

    if mtime <= ctx.log_last_mtime:
        return []

    ctx.log_last_mtime = mtime

    try:
        results = LogParser(log_path).parse_new()
    except Exception:
        return []

    if auto_cfg.get("log_accept", True):
        for r in results:
            ctx.last_scan = r
            ctx.scan_history.append(r)

    return results if auto_cfg.get("signal_scan", True) else []


def check_screenshots_auto(ctx) -> list[Path]:
    """Détecte les nouveaux screenshots SC depuis le dernier check.

    Respecte auto.signal_scan.  Retourne [] si signal_scan=off ou aucun nouveau.
    Premier appel : initialise le timestamp sans retourner de fichiers.
    """
    import time

    auto_cfg = ctx.cfg.get("auto", {})
    if not auto_cfg.get("signal_scan", True):
        return []

    sc_dir = _screenshots_dir(ctx)
    if not sc_dir.is_dir():
        return []

    now = time.time()
    last_ts = ctx.screenshots_last_seen_ts

    if last_ts == 0.0:
        # Premier check : initialisation silencieuse
        ctx.screenshots_last_seen_ts = now
        return []

    ctx.screenshots_last_seen_ts = now

    try:
        new_files = sorted(
            (p for p in sc_dir.iterdir()
             if p.suffix.lower() in _IMAGE_SUFFIXES
             and p.stat().st_mtime > last_ts),
            key=lambda p: p.stat().st_mtime,
        )
    except OSError:
        return []

    return new_files


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

    # Mémoriser le timestamp du fichier le plus récent traité + marquer comme "vu"
    if images:
        import time as _time
        ctx._last_scan_mtime = max(p.stat().st_mtime for p in images)
        ctx.screenshots_last_seen_ts = _time.time()

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


def _refresh_validated_from_uex(result: ScanResult, ctx) -> bool:
    """Pour un scan log validé, remplace les données OCR brutes par les prix UEX actuels.

    SC-Datarunner envoie les prix corrigés à UEX juste avant de logger la soumission.
    L'API UEX reflète immédiatement ces prix → on les récupère et on remplace le scan.
    Retourne True si le refresh a réussi et a produit des données.
    """
    from uexinfo.api.uex_client import UEXClient, UEXError
    import time

    if not result.terminal:
        return False

    name_lower = result.terminal.lower()
    is_sell    = result.mode == "sell"
    price_key  = "price_sell" if is_sell else "price_buy"

    # Trouver l'ID terminal dans le cache
    matches = [
        t for t in (ctx.cache.terminals or [])
        if t.name.rsplit(" - ", 1)[-1].strip().lower() == name_lower
    ]
    terminal = matches[0] if len(matches) == 1 else None

    cache_key = f"uex_refresh_{name_lower}_{result.mode}"
    cached = ctx._price_cache.get(cache_key)
    if cached:
        _ts, rows = cached
    else:
        try:
            client = UEXClient()
            if terminal:
                rows = client.get_prices(id_terminal=terminal.id)
            else:
                rows = client.get_prices(terminal_name=name_lower)
        except UEXError:
            return False
        ctx._price_cache[cache_key] = (time.time(), rows)

    if not rows:
        return False

    # Construire un dict {commodity_name_lower: (price, qty, stock_status)}
    price_map: dict[str, tuple[int, int, int]] = {}
    for r in rows:
        price = r.get(price_key)
        cname = (r.get("commodity_name") or "").lower()
        if price and cname:
            qty = int(r.get("scu_buy") or r.get("scu_sell") or 0)
            status = int(r.get("status_buy") or r.get("status_sell") or 0)
            price_map[cname] = (int(price), qty, status)

    if not price_map:
        return False

    # Mettre à jour les commodités du scan avec les données UEX fraîches
    updated = 0
    for sc in result.commodities:
        key = sc.name.lower()
        if key in price_map:
            uex_price, uex_qty, uex_status = price_map[key]
            sc.price = uex_price
            if uex_qty:
                sc.quantity = uex_qty
            if uex_status:
                sc.stock_status = uex_status
            updated += 1

    return updated > 0


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

    # ScanResult : affiner le nom du terminal + mémoriser le chemin image
    if isinstance(result, ScanResult):
        result.image_path = str(image_path)
        if ctx.location_index:
            raw = result.terminal
            _refine_terminal(result, ctx.location_index)
            if result.terminal != raw:
                print_info(f"Terminal : {raw!r} → {result.terminal!r}")

    # ── Centraliser dans ScreenshotDB ────────────────────────────────────────
    if result is not None:
        _upsert_to_db(result, image_path, ctx)

    return result


def _upsert_to_db(result, image_path: "Path | None", ctx) -> None:
    """Insère le résultat OCR dans la ScreenshotDB (créée si absente du contexte)."""
    try:
        from uexinfo.cache.screenshot_db import ScreenshotDB
        db = getattr(ctx, "screenshot_db", None)
        if db is None:
            db = ScreenshotDB()
            ctx.screenshot_db = db
        gap = ctx.cfg.get("scan", {}).get("session_gap", 60)
        db.upsert_from_result(result, image_path, gap_minutes=gap)
        db.save()
    except Exception:
        pass  # La DB est optionnelle — ne jamais bloquer le scan


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

    # Objectifs structurés (si disponibles)
    if result.parsed_objectives:
        console.print(f"\n  [bold]Objectifs principaux[/bold]")
        for o in result.parsed_objectives:
            if o.kind == "collect":
                loc = f"[{C.UEX}]{o.location}[/{C.UEX}]" if o.location else "[dim]?[/dim]"
                console.print(
                    f"    [cyan]◇[/cyan] [dim]Collect[/dim]"
                    f"  [{C.LABEL}]{o.commodity or '?'}[/{C.LABEL}]"
                    f"  [dim]depuis[/dim] {loc}"
                )
            elif o.kind == "deliver":
                loc = f"[{C.UEX}]{o.location}[/{C.UEX}]" if o.location else "[dim]?[/dim]"
                hint = f"  [dim](above {o.location_hint})[/dim]" if o.location_hint else ""
                scu = f"  [{C.DIM}]{o.quantity_scu} SCU[/{C.DIM}]" if o.quantity_scu else ""
                console.print(
                    f"    [cyan]◇[/cyan] [dim]Deliver[/dim]"
                    f"  [{C.LABEL}]{o.commodity or '?'}[/{C.LABEL}]"
                    f"{scu}"
                    f"  [dim]→[/dim] {loc}{hint}"
                )
            else:
                console.print(f"    [cyan]◇[/cyan] {o.raw}")
    elif result.objectives:
        # Fallback : lignes brutes si le parser structuré n'a rien extrait
        console.print(f"\n  [bold]Objectifs principaux[/bold]")
        for obj in result.objectives:
            console.print(f"    [cyan]◇[/cyan] {obj}")

    # Hint → catalogue
    if result.parsed_objectives:
        console.print(f"  [{C.DIM}]/mission add  pour ajouter au catalogue[/{C.DIM}]")

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
    # Persister dans la base locale des prix scannés
    from uexinfo.models.scan_result import ScanResult
    if isinstance(result, ScanResult) and result.commodities:
        from uexinfo.cache.scan_prices import ScanPriceStore
        try:
            ScanPriceStore().save_result(result)
        except OSError:
            pass


def _display_result(result, ctx) -> None:
    """Dispatch vers le bon affichage selon le type de résultat."""
    from uexinfo.models.mission_result import MissionResult
    if isinstance(result, MissionResult):
        _display_mission(result)
    else:
        _display_scan(result, ctx)


def _run_debug_on(ctx, image_path: Path) -> None:
    """Lance le debug OCR sur un seul fichier image (factorisation)."""
    from uexinfo.ocr.engine import TesseractEngine
    cfg_scan = ctx.cfg.get("scan", {})
    exe = Path(cfg_scan["tesseract_exe"]) if cfg_scan.get("tesseract_exe") else None
    try:
        engine = TesseractEngine(exe=exe)
    except RuntimeError as e:
        print_error(str(e))
        return

    screen_type = engine.detect_screen_type(image_path)
    console.print(
        f"\n[bold]Debug OCR[/bold] — [{C.DIM}]{image_path.name}[/{C.DIM}]"
        f"  Type détecté : [cyan]{screen_type}[/cyan]"
    )

    if screen_type == "mission":
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
        console.print(f"\n[bold]Terminal (zone haut-gauche) :[/bold]")
        for tl in engine.debug_terminal(image_path):
            console.print(f"  {tl}")
        console.print(f"\n[bold]Commodités (panneau droit) :[/bold]")
        lines = engine.debug_lines(image_path)
        for i, line in enumerate(lines):
            console.print(f"  [{C.DIM}]{i:3}[/{C.DIM}]  {line}")
        console.print(f"\n[{C.DIM}]{len(lines)} lignes extraites[/{C.DIM}]")


def _debug_list_images(ctx) -> None:
    """Affiche la liste des images de scan disponibles (non-interactif)."""
    import datetime
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
    section("Images de scan disponibles")
    for p in images[:50]:
        ts = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        sz = p.stat().st_size // 1024
        console.print(
            f"  [{C.LABEL}]{p.name}[/{C.LABEL}]"
            f"  [{C.DIM}]{ts}  {sz} Ko[/{C.DIM}]"
        )
    console.print(
        f"\n[{C.DIM}]{len(images)} fichier(s) · "
        f"/scan debug <nom>  pour analyser  ·  "
        f"/scan debug selected  pour sélectionner plusieurs[/{C.DIM}]"
    )


def _debug_select(ctx, mode: str) -> None:
    """Ouvre le sélecteur d'images pour /scan debug list|selected."""
    import datetime
    from uexinfo.cli.selector import SelectItem

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

    items = [
        SelectItem(
            label    = p.name,
            value    = p,
            meta     = (
                datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                + f"  {p.stat().st_size // 1024} Ko"
            ),
        )
        for p in images[:50]
    ]

    title = (
        "Debug OCR — choisir une image"
        if mode == "single"
        else "Debug OCR — sélectionner les images"
    )
    from uexinfo.cli.selector import pick
    chosen = pick(ctx, items, title=title, mode=mode)

    if not chosen:
        print_warn("Annulé." if chosen is None else "Aucune image sélectionnée.")
        return

    for item in chosen:
        _run_debug_on(ctx, item.value)


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

    # /scan log [all|reset|<fichier>]
    if sub == "log":
        # Sous-commandes spéciales
        sub2 = args[1].lower() if len(args) >= 2 else ""

        if sub2 == "reset":
            from uexinfo.ocr.log_parser import LogParser
            log_path = _resolve_log_path(args[2:], ctx)
            LogParser(log_path).reset_offset()
            console.print(f"[dim]Offset log remis à 0 — prochain /scan log relira depuis le début.[/dim]")
            return

        if sub2 == "undo":
            from uexinfo.ocr.log_parser import LogParser
            log_path = _resolve_log_path(args[2:], ctx)
            parser = LogParser(log_path)
            ok = parser.undo_offset()
            if not ok:
                print_warn("Aucune lecture précédente à annuler (pas de prev_offset).")
                return
            # Retirer les scans log récents de l'historique (jusqu'au dernier non-log ou début)
            before = len(ctx.scan_history)
            while ctx.scan_history and ctx.scan_history[-1].source == "log":
                ctx.scan_history.pop()
            removed = before - len(ctx.scan_history)
            ctx.last_scan = ctx.scan_history[-1] if ctx.scan_history else None
            console.print(
                f"[dim]Offset restauré — {removed} scan(s) log retiré(s) de l'historique. "
                f"Relancez /scan log pour relire.[/dim]"
            )
            return

        # /scan log new  → incrémental depuis le dernier offset (auto-check)
        # /scan log [all] → lit TOUT le fichier (défaut) puis avance l'offset à la fin
        incremental = (sub2 == "new")
        full        = not incremental   # "all" ou "" → tout lire
        raw_args    = args[2:] if sub2 in ("all", "new") else (
                          args[1:] if sub2 not in ("", "all", "new") else [])
        log_path = _resolve_log_path(raw_args, ctx)
        sc_log_configured = bool(ctx.cfg.get("scan", {}).get("sc_log_path", "")) or bool(raw_args)
        if log_path is None and sc_log_configured:
            return  # erreur de chemin → message déjà affiché

        results = _scan_log(ctx, log_path=log_path, full=full)

        # Après un parse_all explicite, avancer l'offset pour que l'auto-check
        # ne retraite pas les mêmes scans lors des prochaines commandes.
        if full:
            from uexinfo.ocr.log_parser import LogParser
            LogParser(log_path).advance_to_end()

        for result in results:
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

    # /scan debug <fichier>|list|selected  — debug OCR
    if sub == "debug":
        sub2 = args[1].lower() if len(args) >= 2 else ""

        # /scan debug list — liste non-interactive des images disponibles
        if sub2 == "list":
            _debug_list_images(ctx)
            return

        # /scan debug selected — sélecteur multi : plusieurs images → debug
        if sub2 == "selected":
            _debug_select(ctx, mode="multi")
            return

        # /scan debug <fichier>
        if len(args) < 2:
            print_error("Usage : /scan debug <fichier|list|selected>")
            return
        raw = " ".join(args[1:]).strip("\"'")
        image_path = _resolve_image_path(raw, ctx)
        if not image_path.exists():
            print_error(f"Fichier introuvable : {image_path}  (cherché aussi dans {_screenshots_dir(ctx)})")
            return
        _run_debug_on(ctx, image_path)
        return

    print_error(f"Sous-commande inconnue : {sub}  —  /scan [list|ecran|screenshot|log|status|history|debug]")
