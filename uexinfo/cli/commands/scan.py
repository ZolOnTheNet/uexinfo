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
            ctx._price_cache[key] = (time.time(), data)
            return data
        except UEXError:
            stale = ctx._price_cache.get_stale(key)
            if stale:
                return stale[1]
            return []

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


# ── Auto-position depuis scan ─────────────────────────────────────────────────

def _resolve_autopos_terminal(terminal_name: str, ctx) -> str:
    """Résout un nom de terminal vers un nom canonique avec disambiguation.

    Pour les gateways/jump-points présents dans plusieurs systèmes
    (ex: "Nyx Gateway" côté Stanton ET côté Nyx), on préfère le terminal
    dont star_system_name correspond au système actuel du joueur.
    """
    from uexinfo.location.index import _trading_priority

    if not terminal_name:
        return ""
    terminals = getattr(ctx.cache, "terminals", None) or []
    name_lo = terminal_name.lower().strip()

    # 1. Lieu structuré (station/ville) — insensible aux tirets internes du
    # nom du terminal. Certains terminaux (ex: vaisseaux en vente) ont un nom
    # du type "INS Jericho - Pyro Gateway" sans le suffixe système que portent
    # leurs voisins ("Admin - Pyro Gateway (Stanton)") : matcher sur le nom
    # brut du terminal ferait à tort gagner "INS Jericho" (correspondance
    # exacte accidentelle) au lieu du vrai terminal de service.
    exact = [
        t for t in terminals
        if (t.space_station_name or t.city_name or "").lower().startswith(name_lo)
    ]

    # 2. Fallback : correspondance exacte sur le nom du terminal
    if not exact:
        exact = [t for t in terminals if t.name.lower() == name_lo
                 or t.name.lower().endswith(f"- {name_lo}")]

    # 3. Correspondance partielle (le terminal contient le nom scanné)
    if not exact:
        exact = [t for t in terminals if name_lo in t.name.lower()]

    if not exact:
        return terminal_name  # inconnu : retourner tel quel

    if len(exact) > 1:
        # Préférer le terminal de commerce (Admin/TDD/Trade) parmi les
        # services d'une même station plutôt qu'un candidat arbitraire
        # (restaurant, vaisseau en vente, etc.).
        best_prio = min(_trading_priority(t) for t in exact)
        exact = [t for t in exact if _trading_priority(t) == best_prio]

    if len(exact) == 1:
        return exact[0].name

    # Plusieurs résultats de même priorité : préférer celui du système actuel du joueur
    player_sys = ""
    loc = (ctx.player.location or "").lower()
    if loc:
        # Correspondance exacte d'abord (le nom stocké par _apply_autopos est canonique)
        for t in terminals:
            if t.name.lower() == loc:
                player_sys = (t.star_system_name or "").lower()
                break
        if not player_sys:
            # Correspondance partielle (position abrégée ou sans préfixe service)
            for t in terminals:
                if loc in t.name.lower() or t.name.lower() in loc:
                    player_sys = (t.star_system_name or "").lower()
                    break
    if not player_sys:
        player_sys = ctx.cfg.get("player", {}).get("system", "").lower()

    if player_sys:
        same_sys = [t for t in exact if (t.star_system_name or "").lower() == player_sys]
        if same_sys:
            return same_sys[0].name

    return exact[0].name


def _apply_autopos(terminal_name: str, ctx) -> tuple[str, str] | None:
    """Propose une mise à jour auto-position (sans l'appliquer).

    Le scan peut être relu après coup (ex: pendant un saut quantique, une
    fois le joueur déjà parti) — la position n'est donc plus écrasée
    silencieusement. On émet une proposition [MàJ]/[Ign] côté overlay ;
    l'application réelle passe par /go (cf. showLocationConfirm côté client).

    Retourne (new_pos, old_pos) si une proposition a été émise, sinon None.
    """
    new_pos = _resolve_autopos_terminal(terminal_name, ctx)
    if not new_pos:
        return None
    old_pos = ctx.player.location or ""
    if new_pos == old_pos:
        return None

    # Notification console (proposition, pas encore appliquée)
    console.print(
        f"  [bold]Position détectée :[/bold] [{C.UEX}]{new_pos}[/{C.UEX}]"
        f"  [{C.DIM}]— en attente de confirmation[/{C.DIM}]"
        + (f"  [{C.DIM}](actuelle : {old_pos})[/{C.DIM}]" if old_pos else "")
    )

    # Message overlay (bandeau [MàJ]/[Ign])
    pending = getattr(ctx, "_overlay_msgs", None)
    if pending is None:
        ctx._overlay_msgs = []
        pending = ctx._overlay_msgs
    pending.append({
        "type":   "location_confirm",
        "new":    new_pos,
        "old":    old_pos,
        "source": "scan",  # scan OCR/log SC-Datarunner — distingue de gamelog (Game.log)
    })

    return new_pos, old_pos


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

    # Scans validés (soumis à UEX depuis SC-Datarunner) : les corrections faites
    # dans l'interface Datarunner avant l'envoi n'apparaissent jamais dans le log
    # (seul l'OCR brut y est écrit) — on récupère les prix UEX frais, qui les
    # reflètent déjà (même logique que _scan_log pour le mode manuel).
    for r in results:
        if r.validated:
            _refresh_validated_from_uex(r, ctx)

    if auto_cfg.get("log_accept", True):
        for r in results:
            _store_result(ctx, r)

    # Mode quick : mise à jour auto-position dès détection du changement de log
    if results and ctx.cfg.get("scan", {}).get("log", {}).get("autopos", "off") == "quick":
        last_terminal = next((r.terminal for r in reversed(results) if r.terminal), None)
        if last_terminal:
            _apply_autopos(last_terminal, ctx)

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


# Anti-doublon (secondes) pour _refresh_validated_from_uex — court exprès, cf. docstring.
_REFRESH_DEDUP_TTL = 60.0


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

    is_sell    = result.mode == "sell"
    price_key  = "price_sell" if is_sell else "price_buy"

    # Résolution structurée (space_station_name + priorité de trading), comme
    # _resolve_autopos_terminal — un match par simple nom de lieu ne trouve
    # parfois qu'un terminal restaurant/boutique sans aucune donnée de prix, si
    # le terminal Admin/commodité a un nom légèrement différent côté UEX (ex.
    # "Admin - Starlight Service" sans "Station", alors que le terminal détecté
    # par l'OCR est "Starlight Service Station").
    resolved_name = _resolve_autopos_terminal(result.terminal, ctx)
    name_lower = result.terminal.lower()
    terminal = next(
        (t for t in (ctx.cache.terminals or []) if t.name == resolved_name), None
    )

    # Anti-doublon court (60s), PAS le cache TTL adaptatif de ctx._price_cache
    # (4h à 3j) : ce dernier renverrait l'ancienne version si le même
    # terminal/mode est revalidé plus tard (bulk "valider tout" puis correction
    # ponctuelle sur une ligne, "MàJ", repérée après coup) — mais on veut quand
    # même éviter d'interroger l'API à chaque appel rapproché (même lot).
    cache_key = f"uex_refresh_{resolved_name.lower()}_{result.mode}"
    dedup = getattr(ctx, "_refresh_dedup", None)
    if dedup is None:
        ctx._refresh_dedup = {}
        dedup = ctx._refresh_dedup

    now = time.time()
    recent = dedup.get(cache_key)
    if recent and (now - recent[0]) < _REFRESH_DEDUP_TTL:
        rows = recent[1]
    else:
        try:
            client = UEXClient()
            if terminal:
                rows = client.get_prices(id_terminal=terminal.id)
            else:
                rows = client.get_prices(terminal_name=name_lower)
            dedup[cache_key] = (now, rows)
            ctx._price_cache[cache_key] = (now, rows)  # secours réseau uniquement (get_stale)
        except UEXError:
            stale = ctx._price_cache.get_stale(cache_key)
            rows = stale[1] if stale else []

    if not rows:
        return False

    # Construire un dict {commodity_name_lower: (price, qty, stock_status)}
    price_map: dict[str, tuple[int, int, int]] = {}
    for r in rows:
        price = r.get(price_key)
        cname = (r.get("commodity_name") or "").lower()
        if price and cname:
            if is_sell:
                qty    = int(r.get("scu_sell_max") or r.get("scu_sell") or 0)
                status = int(r.get("status_sell") or 0)
            else:
                qty    = int(r.get("scu_buy_max") or r.get("scu_buy") or 0)
                status = int(r.get("status_buy") or 0)
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


def _terminal_store_key(query: str, ctx) -> str:
    """Clé canonique pour scan_prices.json. Délègue à canonical_terminal_key."""
    from uexinfo.cache.data_manager import canonical_terminal_key
    terminals = ctx.cache.terminals if (ctx.cache) else []
    return canonical_terminal_key(query, terminals)


def _scan_resync(args: list[str], ctx) -> None:
    """/scan resync <terminal> — réconcilie les données scan avec l'API UEX.

    Pour chaque commodité dans le store scan du terminal :
    - Si l'API dit price_buy=0 mais le scan a price_buy → supprime price_buy (donnée invalide)
    - Si l'API dit price_sell=0 mais le scan a price_sell → supprime price_sell
    - Si plus aucun prix → supprime l'entrée entièrement
    """
    if not args:
        print_error("Usage : /scan resync <terminal>")
        return

    from uexinfo.cache.scan_prices import ScanPriceStore
    from uexinfo.api.uex_client import UEXClient, UEXError
    import time

    from uexinfo.cache.data_manager import all_terminal_keys
    term_raw  = " ".join(args).replace("_", " ").strip()
    term_key  = _terminal_store_key(term_raw, ctx)
    terminals = ctx.cache.terminals if ctx.cache else []

    store = ScanPriceStore()
    # Agréger les entrées de toutes les clés du lieu (loc:, terminal ID, frères)
    all_entries: dict[str, tuple[str, dict]] = {}  # cid_key → (stored_key, entry)
    for key in all_terminal_keys(term_raw, terminals):
        for ck, e in store.list_terminal(key).items():
            if ck not in all_entries:
                all_entries[ck] = (key, e)
    if not all_entries:
        print_warn(f"Aucune donnée scan pour «{term_key}».")
        return

    console.print(f"[{C.DIM}]Chargement des prix UEX pour {term_key}…[/{C.DIM}]")
    stale_key = f"tl_{term_key.lower()}"
    try:
        client = UEXClient()
        rows = client.get_prices(terminal_name=term_key)
        ctx._price_cache[stale_key] = (__import__("time").time(), rows)
    except UEXError:
        stale = ctx._price_cache.get_stale(stale_key)
        if stale:
            rows = stale[1]
            console.print(f"[orange1]API hors-ligne — prix du cache utilisés[/orange1]")
        else:
            print_error("API UEX inaccessible et aucune donnée cache pour ce terminal.")
            return

    # Index UEX par commodity_id et par nom
    uex_by_id:   dict[int, dict] = {}
    uex_by_name: dict[str, dict] = {}
    for r in rows:
        cid = int(r.get("id_commodity") or 0)
        if cid:
            uex_by_id[cid] = r
        cname = (r.get("commodity_name") or "").lower()
        if cname:
            uex_by_name[cname] = r

    removed = 0
    updated = 0
    now = time.time()

    for cid_key, (stored_tk, entry) in list(all_entries.items()):
        cid   = entry.get("commodity_id") or 0
        cname = (entry.get("commodity_name") or "").lower()
        uex_r = uex_by_id.get(cid) or uex_by_name.get(cname)

        fields_to_del = []

        if entry.get("price_buy"):
            if uex_r is None or not uex_r.get("price_buy"):
                fields_to_del.extend(["price_buy", "status_buy", "scu_buy"])

        if entry.get("price_sell"):
            if uex_r is None or not uex_r.get("price_sell"):
                fields_to_del.extend(["price_sell", "status_sell", "scu_sell_stock", "scu_sell_max"])

        if not fields_to_del:
            continue

        remaining_buy  = entry.get("price_buy")  if "price_buy"  not in fields_to_del else None
        remaining_sell = entry.get("price_sell") if "price_sell" not in fields_to_del else None
        display_name   = entry.get("commodity_name") or cid_key

        if remaining_buy or remaining_sell:
            store.delete_field(stored_tk, cid_key, *fields_to_del)
            console.print(
                f"  [{C.WARNING}]⚠[/{C.WARNING}]  [{C.NEUTRAL}]{display_name}[/{C.NEUTRAL}]"
                f"  [{C.DIM}]champs supprimés : {', '.join(f for f in fields_to_del if not f.startswith('s'))}[/{C.DIM}]"
            )
            updated += 1
        else:
            store.delete_entry(stored_tk, cid_key)
            console.print(
                f"  [{C.LOSS}]✗[/{C.LOSS}]  [{C.NEUTRAL}]{display_name}[/{C.NEUTRAL}]"
                f"  [{C.DIM}]supprimé (contradiction API)[/{C.DIM}]"
            )
            removed += 1

    if removed == 0 and updated == 0:
        print_ok(f"Données scan pour «{term_key}» cohérentes avec l'API UEX — rien à corriger.")
    else:
        print_ok(
            f"Resync {term_key} : {removed} supprimé(s), {updated} mis à jour"
            f" sur {len(all_entries)} entrée(s)."
        )


def _scan_edit(args: list[str], ctx) -> None:
    """/scan edit <terminal> [del <commodity>] | [<commodity> [prix=N] [qte=N] [stock=N]]

    Sans commodity → liste les entrées du terminal.
    Avec commodity seul → affiche l'entrée.
    Avec prix/qte/stock → modifie les valeurs.
    del <commodity> → supprime l'entrée.
    """
    if not args:
        print_error("Usage : /scan edit <terminal> [del|<commodity> [prix=N] [qte=N] [stock=N]]")
        return

    from uexinfo.cache.scan_prices import ScanPriceStore
    import time

    from uexinfo.cache.data_manager import all_terminal_keys
    store = ScanPriceStore()
    comm_args_start = 1

    term_raw = " ".join(args[:1])
    term_key = _terminal_store_key(term_raw, ctx)
    terminals = ctx.cache.terminals if ctx.cache else []
    merged: dict[str, tuple[str, dict]] = {}  # cid_key → (stored_tk, entry)
    for key in all_terminal_keys(term_raw, terminals):
        for ck, e in store.list_terminal(key).items():
            if ck not in merged:
                merged[ck] = (key, e)
    comm_args_start = 1
    # Vue plate des entrées pour la recherche par nom
    entries   = {ck: e for ck, (_, e) in merged.items()}
    rest      = args[comm_args_start:]

    # /scan edit <terminal>  → lister (overlay form si disponible, sinon CLI)
    if not rest:
        if not entries:
            print_warn(f"Aucune donnée scan pour «{term_key}».")
            return

        # Mode overlay : formulaire éditable
        if getattr(ctx, "_overlay_msgs", None) is not None or hasattr(ctx, "overlay_send_queue"):
            if not hasattr(ctx, "_overlay_msgs"):
                ctx._overlay_msgs = []
            comms = []
            for cid_key, (stored_tk, e) in merged.items():
                name = e.get("commodity_name") or cid_key
                if e.get("price_buy"):
                    comms.append({
                        "cid_key": cid_key, "stored_tk": stored_tk, "name": name,
                        "mode": "buy",  "price": e.get("price_buy", 0),
                        "stock_status": e.get("status_buy", 0),
                        "quantity": e.get("scu_buy"),
                        "timestamp": e.get("timestamp", 0),
                    })
                if e.get("price_sell"):
                    comms.append({
                        "cid_key": cid_key, "stored_tk": stored_tk, "name": name,
                        "mode": "sell", "price": e.get("price_sell", 0),
                        "stock_status": e.get("status_sell", 0),
                        "quantity": e.get("scu_sell_stock") if e.get("scu_sell_stock") is not None else e.get("scu_sell_max"),
                        "timestamp": e.get("timestamp", 0),
                    })
            comms.sort(key=lambda c: (0 if c["mode"] == "buy" else 1, c["name"].lower()))
            ctx._overlay_msgs.append({
                "type": "scan_edit_existing",
                "terminal": term_key,
                "terminal_display": term_key,
                "commodities": comms,
            })
            return

        # Fallback CLI
        all_keys_str = term_key
        console.print(f"\n[bold {C.UEX}]{all_keys_str}[/bold {C.UEX}]  [{C.DIM}]{len(entries)} entrée(s)[/{C.DIM}]")
        for cid_key, e in sorted(entries.items(), key=lambda x: x[1].get("commodity_name", x[0])):
            pb   = e.get("price_buy")  or 0
            ps   = e.get("price_sell") or 0
            ts   = e.get("timestamp", 0)
            age  = _fmt_age(ts) if ts else "?"
            name = e.get("commodity_name") or cid_key
            buy_str  = f"  A:[{C.UEX}]{pb:,}[/{C.UEX}]" if pb else ""
            sell_str = f"  V:[{C.PROFIT}]{ps:,}[/{C.PROFIT}]" if ps else ""
            console.print(f"  [{C.NEUTRAL}]{name:<28}[/{C.NEUTRAL}]{buy_str}{sell_str}  [{C.DIM}]{age}[/{C.DIM}]  [{C.DIM}]{cid_key}[/{C.DIM}]")
        return

    # /scan edit <terminal> del <commodity>
    if rest[0].lower() == "del":
        if len(rest) < 2:
            print_error("Usage : /scan edit <terminal> del <commodity>")
            return
        comm_q = " ".join(rest[1:]).replace("_", " ").lower()
        target_key = _find_scan_entry_key(entries, comm_q)
        if not target_key:
            print_error(f"Commodité «{comm_q}» introuvable dans les données de «{term_key}».")
            return
        stored_tk = merged[target_key][0]
        store.delete_entry(stored_tk, target_key)
        name = entries[target_key].get("commodity_name") or target_key
        print_ok(f"Supprimé : {name} @ {stored_tk}")
        return

    # /scan edit <terminal> <commodity> [prix=N] [qte=N] [stock=N]
    # Séparer le nom de commodité des paramètres key=val
    comm_words = []
    kv_args    = []
    for a in rest:
        if "=" in a:
            kv_args.append(a)
        else:
            comm_words.append(a)

    comm_q = " ".join(comm_words).replace("_", " ").lower()
    target_key = _find_scan_entry_key(entries, comm_q) if comm_q else None

    if not comm_q and not kv_args:
        print_error("Usage : /scan edit <terminal> <commodity> [prix=N] [qte=N] [stock=N]")
        return

    if comm_q and not target_key:
        print_error(f"Commodité «{comm_q}» introuvable dans les données de «{term_key}».")
        _scan_edit([" ".join(args[:comm_args_start])], ctx)   # relister
        return

    if not kv_args:
        # Afficher l'entrée
        e = entries[target_key]
        name = e.get("commodity_name") or target_key
        console.print(f"\n[bold {C.NEUTRAL}]{name}[/bold {C.NEUTRAL}]  [{C.DIM}]@ {term_key}[/{C.DIM}]")
        for k, v in sorted(e.items()):
            if k == "timestamp":
                console.print(f"  {k:<20} {_fmt_age(v)} ({v})")
            else:
                console.print(f"  {k:<20} {v}")
        return

    # Modifier les champs
    updates: dict = {}
    for kv in kv_args:
        key, _, val = kv.partition("=")
        key = key.lower().strip()
        val = val.strip()
        if key in ("prix", "price_buy"):
            try:
                updates["price_buy"] = int(val)
            except ValueError:
                print_error(f"prix invalide : {val}") ; return
        elif key in ("prix_vente", "sell", "price_sell"):
            try:
                updates["price_sell"] = int(val)
            except ValueError:
                print_error(f"prix_vente invalide : {val}") ; return
        elif key in ("qte", "qty", "quantity", "scu"):
            try:
                v = int(val)
                # Stocker dans scu_buy ou scu_sell_max selon ce qui existe
                e_cur = entries.get(target_key, {})
                if e_cur.get("price_buy"):
                    updates["scu_buy"] = v
                else:
                    updates["scu_sell_stock"] = v
            except ValueError:
                print_error(f"qte invalide : {val}") ; return
        elif key in ("stock", "status", "status_buy"):
            try:
                updates["status_buy"] = int(val)
            except ValueError:
                print_error(f"stock invalide : {val}") ; return
        elif key in ("stock_vente", "status_sell"):
            try:
                updates["status_sell"] = int(val)
            except ValueError:
                print_error(f"stock_vente invalide : {val}") ; return
        else:
            print_warn(f"Paramètre inconnu ignoré : {key}  (connus : prix, prix_vente, qte, stock, stock_vente)")

    if not updates:
        return

    updates["timestamp"] = time.time()
    stored_tk = merged[target_key][0]
    ok = store.update_entry(stored_tk, target_key, **updates)
    if ok:
        name = entries[target_key].get("commodity_name") or target_key
        chg = "  ".join(f"{k}={v}" for k, v in updates.items() if k != "timestamp")
        print_ok(f"Modifié : {name} @ {stored_tk}  →  {chg}")
    else:
        print_error("Échec de la mise à jour.")


def _find_scan_entry_key(entries: dict, query: str) -> str | None:
    """Trouve la clé d'une entrée dans le store par nom ou id (fuzzy)."""
    if not query:
        return None
    # Correspondance exacte par nom
    for k, e in entries.items():
        if (e.get("commodity_name") or "").lower() == query:
            return k
    # Correspondance partielle
    for k, e in entries.items():
        if query in (e.get("commodity_name") or "").lower():
            return k
    # Correspondance exacte par clé
    if query in entries:
        return query
    return None


def _fmt_age(ts: float) -> str:
    """Formate un timestamp Unix en âge lisible."""
    import time as _time
    delta = _time.time() - ts
    if delta < 3600:
        return f"{int(delta // 60)}min"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}j"


def _store_result(ctx, result) -> None:
    ctx.last_scan = result
    ctx.scan_history.append(result)
    if len(ctx.scan_history) > 20:
        ctx.scan_history = ctx.scan_history[-20:]
    from uexinfo.models.scan_result import ScanResult
    # Un scan "log" (SC-Datarunner) non encore validé (pas de "Data successfully
    # sent to API" vu) n'est qu'un brouillon OCR — potentiellement corrigé par
    # l'utilisateur avant envoi (ex: un chiffre mal lu). Ne PAS le persister dans
    # ScanPriceStore (prioritaire ★ sur UEX dans /info et /trade) tant qu'il n'est
    # pas confirmé, pour ne jamais faire passer une valeur provisoire/erronée
    # devant les données communauté UEX. Un scan OCR direct (source="ocr", pas de
    # Datarunner) n'a pas cette étape de validation externe — inchangé.
    is_unvalidated_log = result.source == "log" and not result.validated
    if isinstance(result, ScanResult) and result.commodities and not is_unvalidated_log:
        from uexinfo.cache.scan_prices import ScanPriceStore
        try:
            term_key   = _terminal_store_key(result.terminal, ctx)
            _ver_cfg   = ctx.cfg.get("version", {})
            _sc_env    = _ver_cfg.get("active", "live")
            _sc_ver    = _ver_cfg.get(_sc_env, "")
            ScanPriceStore().save_result(result, terminal_key=term_key,
                                         sc_version=_sc_ver, sc_env=_sc_env)
        except OSError:
            pass

    # scan.autopos : mise à jour auto-position sur tout scan (OCR ou log)
    if (isinstance(result, ScanResult)
            and result.terminal
            and ctx.cfg.get("scan", {}).get("autopos", "off") == "on"):
        _apply_autopos(result.terminal, ctx)


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


def _debug_batch(ctx, folder_str: str) -> None:
    """Lance le debug OCR sur tous les fichiers image d'un dossier."""
    if not folder_str:
        print_error("Usage : /scan debug batch <dossier>")
        return

    folder = Path(folder_str)
    if not folder.is_dir():
        candidate = _screenshots_dir(ctx).parent / folder_str
        if candidate.is_dir():
            folder = candidate
        else:
            print_error(f"Dossier introuvable : {folder_str}")
            return

    images = sorted(
        (p for p in folder.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES),
        key=lambda p: p.stat().st_mtime,
    )
    if not images:
        print_warn(f"Aucun fichier image dans : {folder}")
        return

    section(f"Debug batch — {len(images)} fichier(s) dans {folder.name}")
    for i, img_path in enumerate(images, 1):
        console.print(f"\n[bold][{i}/{len(images)}] {img_path.name}[/bold]")
        _run_debug_on(ctx, img_path)


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

        # Auto-position depuis log (mode on ou quick)
        log_autopos = ctx.cfg.get("scan", {}).get("log", {}).get("autopos", "off")  # clé: scan.log.autopos
        if results and log_autopos in ("on", "quick"):
            last_terminal = next((r.terminal for r in reversed(results) if r.terminal), None)
            if last_terminal:
                _apply_autopos(last_terminal, ctx)
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

        # /scan debug batch <dossier>
        if sub2 == "batch":
            folder_str = " ".join(args[2:]).strip("\"'") if len(args) >= 3 else ""
            _debug_batch(ctx, folder_str)
            return

        # /scan debug <fichier>
        if len(args) < 2:
            print_error("Usage : /scan debug <fichier|list|selected|batch>")
            return
        raw = " ".join(args[1:]).strip("\"'")
        image_path = _resolve_image_path(raw, ctx)
        if not image_path.exists():
            print_error(f"Fichier introuvable : {image_path}  (cherché aussi dans {_screenshots_dir(ctx)})")
            return
        _run_debug_on(ctx, image_path)
        return

    # /scan resync <terminal>
    if sub == "resync":
        _scan_resync(args[1:], ctx)
        return

    # /scan edit <terminal> [del <commodity>] | [<commodity> [prix=N] [qte=N] [stock=N]]
    if sub == "edit":
        _scan_edit(args[1:], ctx)
        return

    print_error(f"Sous-commande inconnue : {sub}  —  /scan [list|ecran|screenshot|log|status|history|debug|resync|edit]")
