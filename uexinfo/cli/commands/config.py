"""Commande /config."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, print_info, section


@register("ship", "sh")
def cmd_ship(args: list[str], ctx) -> None:
    _ship(args, ctx)


@register("config", "c")
def cmd_config(args: list[str], ctx) -> None:
    if not args:
        _show(ctx.cfg, ctx)
        return
    sub = args[0].lower()
    rest = args[1:]
    if sub == "ship":
        _ship(rest, ctx)
    elif sub == "trade":
        _trade(rest, ctx)
    elif sub == "cache":
        _cache(rest, ctx)
    elif sub == "scan":
        _scan(rest, ctx)
    elif sub == "player":
        _player_config(rest, ctx)
    elif sub == "close":
        _overlay_close(rest, ctx)
    elif sub == "clock":
        _clock(rest, ctx)
    elif sub in ("magasins", "restaurants", "services"):
        _display_toggle(sub, rest, ctx)
    elif sub == "uex":
        _uex_config(rest, ctx)
    elif sub == "sctrade":
        _sctrade_config(rest, ctx)
    elif sub in ("hotkey", "overlay.hotkey"):
        _hotkey(rest, ctx)
    elif sub == "cmdhistory":
        _cmdhistory(rest, ctx)
    elif "." in sub:
        _set_dotkey(sub, rest, ctx)
    else:
        print_error(f"Sous-commande inconnue : {sub}  (/help config)")


# ── Affichage ────────────────────────────────────────────────────────────────

def _show(cfg: dict, ctx=None) -> None:
    section("Configuration")
    trade     = cfg.get("trade", {})
    cache_cfg = cfg.get("cache", {})
    scan      = cfg.get("scan", {})

    # ── Vaisseaux & position (source unique : ctx.player) ─────────────────
    p = ctx.player if ctx else None
    if p:
        active = p.active_ship or ""
        console.print(f"  [bold]Vaisseau actif :[/bold] [{C.UEX}]{active or '(non défini)'}[/{C.UEX}]")
        for s in p.ships:
            scu_str = str(s.scu) if s.scu else "?"
            marker  = f"  [{C.SUCCESS}]◄ actif[/{C.SUCCESS}]" if s.name == active else ""
            console.print(f"    [{C.UEX}]{s.name}[/{C.UEX}]  [{C.DIM}]{scu_str} {C.SCU}[/{C.DIM}]{marker}")
        console.print(f"  [bold]Position :[/bold]    [{C.UEX}]{p.location or '(non définie)'}[/{C.UEX}]")
        console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{p.destination or '(non définie)'}[/{C.UEX}]")
    else:
        # Fallback si pas de contexte
        ships   = cfg.get("ships", {})
        current = ships.get("current", "")
        pos     = cfg.get("position", {})
        console.print(f"  [bold]Vaisseau actif :[/bold] [{C.UEX}]{current or '(non défini)'}[/{C.UEX}]")
        console.print(f"  [bold]Position :[/bold]    [{C.UEX}]{pos.get('current') or '(non définie)'}[/{C.UEX}]")
        console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{pos.get('destination') or '(non définie)'}[/{C.UEX}]")

    # ── Overlay ────────────────────────────────────────────────────────────
    ov = cfg.get("overlay", {})
    close_mode = ov.get("close", "normal")
    close_label = "normal (✕ ferme)" if close_mode == "normal" else "dblclick (✕ masque, double-clic ferme)"
    console.print(f"  [bold]overlay.close :[/bold]    {close_label}")
    console.print(f"  [bold]overlay.hotkey :[/bold]   {ov.get('hotkey', 'alt+shift+u')}")
    console.print(f"  [bold]overlay.opacity :[/bold]  {ov.get('opacity', 0.95)}")
    clock_val = ov.get("clock", True)
    console.print(f"  [bold]overlay.clock :[/bold]    {'on' if clock_val else 'off'}")
    console.print(f"  [bold]overlay.cmdhistory :[/bold] {ov.get('cmdhistory', 5)}  [{C.DIM}](commandes+résultats conservés)[/{C.DIM}]")

    # ── Trade / cache / scan ───────────────────────────────────────────────
    console.print(f"  [bold]Profit min/{C.SCU} :[/bold] {trade.get('min_profit_per_scu', 0)} {C.AUEC}")
    console.print(f"  [bold]Marge min :[/bold]     {trade.get('min_margin_percent', 0)} %")
    console.print(f"  [bold]Illégal :[/bold]       {'oui' if trade.get('illegal_commodities') else 'non'}")
    console.print(f"  [bold]TTL cache :[/bold]     {cache_cfg.get('ttl_static', 86400)}s statique  /  {cache_cfg.get('ttl_prices', 300)}s prix")
    console.print(f"  [bold]scan.mode :[/bold]         {scan.get('mode', 'ocr')}  [{C.DIM}](ocr|log|confirm)[/{C.DIM}]")
    console.print(f"  [bold]scan.tesseract :[/bold]    {scan.get('tesseract_exe') or '(auto)'}  [{C.DIM}](moteur OCR pour lire les screenshots)[/{C.DIM}]")
    console.print(f"  [bold]scan.logpath :[/bold]      {scan.get('sc_log_path') or '(non défini)'}")
    console.print(f"  [bold]scan.screenshots :[/bold]  {scan.get('sc_screenshots_dir') or '(non défini)'}")
    console.print(f"  [bold]scan.auto_ocr :[/bold]     {'on' if scan.get('auto_ocr', True) else 'off'}  [{C.DIM}](OCR auto dès détection d'un screenshot)[/{C.DIM}]")
    console.print(f"  [bold]scan.hour :[/bold]         {scan.get('hour', 2)}h  [{C.DIM}](fenêtre /mission scan)[/{C.DIM}]")
    console.print(f"  [bold]scan.session_gap :[/bold]  {scan.get('session_gap', 60)} min  [{C.DIM}](gap = nouvelle session)[/{C.DIM}]")

    # ── Affichage terminal ─────────────────────────────────────────────────
    disp = cfg.get("display", {})
    def _onoff(v, default=True): return f"[{C.SUCCESS}]on[/{C.SUCCESS}]" if (v if v is not None else default) else f"[{C.LOSS}]off[/{C.LOSS}]"
    console.print(f"  [bold]magasins :[/bold]     {_onoff(disp.get('magasins'))}  [{C.DIM}](magasins dans la vue terminal)[/{C.DIM}]")
    console.print(f"  [bold]restaurants :[/bold]  {_onoff(disp.get('restaurants'))}  [{C.DIM}](restaurants dans la vue terminal)[/{C.DIM}]")
    console.print(f"  [bold]services :[/bold]     {_onoff(disp.get('services'))}  [{C.DIM}](services dans la vue terminal)[/{C.DIM}]")

    # ── API UEX Corp ──────────────────────────────────────────────────────────
    api_cfg = cfg.get("api", {})
    uex_key = api_cfg.get("secret_key", "")
    uex_key_disp = f"[{C.SUCCESS}]***défini***[/{C.SUCCESS}]" if uex_key else f"[{C.LOSS}](non défini)[/{C.LOSS}]"
    console.print(f"  [bold]uex.key :[/bold]         {uex_key_disp}  [{C.DIM}](/config uex key <val>)[/{C.DIM}]")

    # ── sc-trade.tools ────────────────────────────────────────────────────────
    sct = cfg.get("sctrade", {})
    token_val = sct.get("token", "")
    token_disp = f"[{C.SUCCESS}]***défini***[/{C.SUCCESS}]" if token_val else f"[{C.LOSS}](non défini)[/{C.LOSS}]"
    console.print(f"  [bold]sctrade.token :[/bold]   {token_disp}  [{C.DIM}](/config sctrade token <val>)[/{C.DIM}]")
    console.print(f"  [bold]sctrade :[/bold]         {_onoff(sct.get('enabled', True))}  [{C.DIM}](/config sctrade on|off)[/{C.DIM}]")


# ── Affichage terminal (magasins / restaurants / services) ───────────────────

def _display_toggle(key: str, args: list[str], ctx) -> None:
    """Active/désactive l'affichage d'une section dans la vue terminal."""
    val_str = args[0].lower() if args else ""
    if val_str not in ("on", "off", "1", "0", "true", "false", "oui", "non"):
        disp = ctx.cfg.get("display", {})
        current = disp.get(key, True)
        print_info(f"{key} : {'on' if current else 'off'}  —  usage : /config {key} on|off")
        return
    enabled = val_str in ("on", "1", "true", "oui")
    ctx.cfg.setdefault("display", {})[key] = enabled
    settings.save(ctx.cfg)
    state = f"[{C.SUCCESS}]on[/{C.SUCCESS}]" if enabled else f"[{C.LOSS}]off[/{C.LOSS}]"
    console.print(f"  {key} → {state}  [{C.DIM}](sauvegardé)[/{C.DIM}]")


# ── UEX Corp API config ───────────────────────────────────────────────────────

def _uex_config(args: list[str], ctx) -> None:
    """Gestion de la clé secrète API UEX Corp.

    Usage :
      /config uex key <secret_key>   Définit la clé
      /config uex key                Affiche l'état
      /config uex                    Affiche l'état
    """
    api = ctx.cfg.setdefault("api", {})
    if not args or args[0].lower() in ("key",) and len(args) < 2:
        key = api.get("secret_key", "")
        state = "***défini***" if key else "(non défini)"
        print_info(f"uex.key: {state}")
        print_info("Usage: /config uex key <secret_key>")
        print_info("Clé disponible sur https://uexcorp.space (profil utilisateur)")
        return
    sub = args[0].lower()
    if sub == "key":
        api["secret_key"] = args[1].strip()
        settings.save(ctx.cfg)
        console.print(f"  uex.key → [{C.SUCCESS}]***sauvegardé***[/{C.SUCCESS}]  [{C.DIM}](relancer pour activer)[/{C.DIM}]")
    else:
        print_error(f"Sous-commande uex inconnue : {sub}  (key)")


# ── sc-trade.tools config ────────────────────────────────────────────────────

def _sctrade_config(args: list[str], ctx) -> None:
    sct = ctx.cfg.setdefault("sctrade", {})
    if not args:
        token_disp = "***défini***" if sct.get("token") else "(non défini)"
        state = "on" if sct.get("enabled", True) else "off"
        print_info(f"sctrade: {state}  token: {token_disp}")
        print_info("Usage: /config sctrade token <val> | on | off")
        return
    sub = args[0].lower()
    if sub == "token":
        if len(args) < 2:
            print_warn("Usage: /config sctrade token <valeur>")
            return
        sct["token"] = args[1].strip()
        settings.save(ctx.cfg)
        console.print(f"  sctrade.token → [{C.SUCCESS}]***sauvegardé***[/{C.SUCCESS}]")
    elif sub in ("on", "off", "1", "0", "true", "false"):
        sct["enabled"] = sub in ("on", "1", "true")
        settings.save(ctx.cfg)
        state = f"[{C.SUCCESS}]on[/{C.SUCCESS}]" if sct["enabled"] else f"[{C.LOSS}]off[/{C.LOSS}]"
        console.print(f"  sctrade → {state}  [{C.DIM}](sauvegardé)[/{C.DIM}]")
    else:
        print_error(f"Sous-commande sctrade inconnue: {sub}  (token | on | off)")


# ── Historique commandes+résultats ───────────────────────────────────────────

def _cmdhistory(args: list[str], ctx) -> None:
    ov = ctx.cfg.setdefault("overlay", {})
    if not args:
        n = ov.get("cmdhistory", 5)
        print_info(f"cmdhistory : {n}  —  nombre de commandes+résultats conservés dans l'overlay")
        print_info("Usage : /config cmdhistory <n>  (1–50)")
        return
    try:
        n = int(args[0])
    except ValueError:
        print_error("Usage : /config cmdhistory <n>  (1–50)")
        return
    if not 1 <= n <= 50:
        print_error("Valeur invalide : doit être entre 1 et 50")
        return
    ov["cmdhistory"] = n
    settings.save(ctx.cfg)
    console.print(f"  cmdhistory → [{C.SUCCESS}]{n}[/{C.SUCCESS}]  [{C.DIM}](sauvegardé — actif au prochain démarrage)[/{C.DIM}]")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_vehicle(name: str, ctx):
    """Cherche un vaisseau dans le cache par nom (flexible, ignore casse et underscores)."""
    q = name.replace("_", " ").lower().strip()
    vehicles = ctx.cache.vehicles or []
    for v in vehicles:
        if v.name_full.lower() == q or v.name.lower() == q:
            return v
    for v in vehicles:
        if v.name_full.lower().startswith(q):
            return v
    q_words = q.split()
    for v in vehicles:
        full = v.name_full.lower()
        if all(w in full for w in q_words):
            return v
    return None


def _save_player(ctx) -> None:
    ctx.cfg["player"] = ctx.player.to_config()
    settings.save(ctx.cfg)


# ── Ship ─────────────────────────────────────────────────────────────────────

def _ship(args: list[str], ctx) -> None:
    """Gestion vaisseaux via ctx.player (source unique de vérité)."""
    from uexinfo.models.player import Ship

    if not args or args[0].lower() == "list":
        if not ctx.player.ships:
            print_warn("Aucun vaisseau configuré — /config ship add <nom>")
            return
        from uexinfo.data.cargo_grids import format_cargo_config
        section("Vaisseaux configurés")
        for s in ctx.player.ships:
            scu_str  = str(s.scu) if s.scu else "?"
            marker   = f"  [{C.SUCCESS}]◄ actif[/{C.SUCCESS}]" if s.name == ctx.player.active_ship else ""
            grid     = s.cargo_config or ctx.cargo_grid_manager.get_grid(s.name) or {}
            grid_str = f"  [{C.LABEL}]{format_cargo_config(grid)}[/{C.LABEL}]" if grid else ""
            console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]  [{C.DIM}]{scu_str} {C.SCU}[/{C.DIM}]{grid_str}{marker}")
        return

    sub  = args[0].lower()
    rest = args[1:]

    if sub == "add":
        raw = " ".join(rest).replace("_", " ")
        if not raw:
            print_error("Usage : /ship add <nom du vaisseau>")
            console.print(f"[{C.DIM}]Exemples :[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship add Cutlass Black[/{C.LABEL}]")
            console.print(f"  [{C.LABEL}]/ship add Drake Cutlass Black[/{C.LABEL}]  [{C.DIM}](nom complet)[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship add \"C2 Hercules\"[/{C.LABEL}]  [{C.DIM}](avec guillemets si espaces)[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship add Cutlass, C2, Carrack[/{C.LABEL}]  [{C.DIM}](plusieurs à la fois)[/{C.DIM}]")

            # Suggérer quelques vaisseaux populaires du cache
            if ctx.cache.vehicles:
                popular = ["Cutlass", "Freelancer", "Constellation", "Carrack", "C2", "Caterpillar"]
                suggestions = []
                for keyword in popular:
                    matches = [v for v in ctx.cache.vehicles if keyword.lower() in v.name_full.lower()]
                    if matches:
                        suggestions.extend(matches[:2])  # Max 2 par type

                if suggestions[:5]:  # Limiter à 5 suggestions
                    console.print(f"\n[{C.DIM}]Vaisseaux populaires disponibles :[/{C.DIM}]")
                    for v in suggestions[:5]:
                        console.print(
                            f"  [{C.UEX}]{v.name_full}[/{C.UEX}]  "
                            f"[{C.DIM}]{v.scu} {C.SCU} · {v.pad_type}[/{C.DIM}]"
                        )
                    console.print(f"[{C.DIM}]Utilisez /explore ship pour voir tous les vaisseaux[/{C.DIM}]")
            return
        names = [n.strip() for n in raw.split(",") if n.strip()] if "," in raw else [raw]
        for name in names:
            vehicle = _find_vehicle(name, ctx)
            canon   = vehicle.name_full if vehicle else name
            if any(s.name == canon for s in ctx.player.ships):
                print_warn(f"{canon} déjà dans la liste")
                continue
            scu = vehicle.scu if vehicle else 0
            ctx.player.ships.append(Ship(name=canon, scu=scu))
            if not ctx.player.active_ship:
                ctx.player.active_ship = canon
            info = f"  [{C.DIM}]{vehicle.scu} {C.SCU} · pad {vehicle.pad_type}[/{C.DIM}]" if vehicle else ""
            if not vehicle:
                info = f"  [{C.WARNING}]vaisseau non trouvé dans le cache — SCU à configurer manuellement[/{C.WARNING}]"
            print_ok(f"Vaisseau ajouté : {canon}{info}")
        _save_player(ctx)

    elif sub == "remove":
        raw  = " ".join(rest).replace("_", " ").strip()
        if not raw:
            if not ctx.player.ships:
                print_warn("Aucun vaisseau configuré")
                return
            from uexinfo.cli.selector import SelectItem, pick
            items = [SelectItem(label=s.name, value=s.name) for s in ctx.player.ships]
            chosen = pick(ctx, items, title="Retirer un vaisseau", mode="single", confirm_label="Retirer")
            if chosen:
                raw = chosen[0].value
            else:
                print_error("Usage : /ship remove <nom du vaisseau>")
                console.print(f"[{C.DIM}]Vaisseaux actuels :[/{C.DIM}]")
                for s in ctx.player.ships:
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]")
                return
        # Chercher d'abord un nom exact dans la flotte (avec normalisation casse + dot-notation)
        raw_lower = raw.lower()
        match_name = next(
            (s.name for s in ctx.player.ships if s.name.lower() == raw_lower),
            None,
        )
        if match_name is None:
            # Essayer via _find_vehicle (gère la notation pointée ship.xxx / RSI.xxx)
            v = _find_vehicle(raw, ctx)
            canon_lower = (v.name_full if v else raw).lower()
            match_name = next(
                (s.name for s in ctx.player.ships if s.name.lower() == canon_lower),
                None,
            )
        if match_name is None:
            print_error(f"Vaisseau introuvable dans votre flotte : {raw}")
            if ctx.player.ships:
                console.print(f"[{C.DIM}]Vaisseaux disponibles :[/{C.DIM}]")
                for s in ctx.player.ships:
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]")
            return
        ctx.player.ships = [s for s in ctx.player.ships if s.name != match_name]
        if ctx.player.active_ship.lower() == match_name.lower():
            ctx.player.active_ship = ctx.player.ships[0].name if ctx.player.ships else ""
        _save_player(ctx)
        print_ok(f"Vaisseau retiré : {match_name}")

    elif sub in ("set", "select"):
        name  = " ".join(rest)
        if not name:
            if not ctx.player.ships:
                print_warn("Aucun vaisseau configuré — /ship add <nom>")
                return
            from uexinfo.cli.selector import SelectItem, pick
            items = [
                SelectItem(
                    label=s.name,
                    meta="◄ actif" if s.name == ctx.player.active_ship else "",
                    value=s.name,
                    selected=(s.name == ctx.player.active_ship),
                )
                for s in ctx.player.ships
            ]
            chosen = pick(ctx, items, title="Choisir le vaisseau actif", mode="single", confirm_label="Définir actif")
            if chosen:
                name = chosen[0].value
            else:
                console.print(f"[{C.DIM}]Vaisseaux disponibles :[/{C.DIM}]")
                for s in ctx.player.ships:
                    marker = f"  [{C.SUCCESS}]◄ actif[/{C.SUCCESS}]" if s.name == ctx.player.active_ship else ""
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]{marker}")
                return
        match = next((s for s in ctx.player.ships if s.name.lower() == name.lower()), None)
        if match is None:
            print_error(f"{name} n'est pas dans la liste")
            if ctx.player.ships:
                console.print(f"[{C.DIM}]Vaisseaux disponibles :[/{C.DIM}]")
                for s in ctx.player.ships:
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]")
            console.print(f"[{C.DIM}]Ajoutez-le d'abord avec /ship add <nom>[/{C.DIM}]")
            return
        ctx.player.active_ship = match.name
        _save_player(ctx)
        print_ok(f"Vaisseau actif : {match.name}")

    elif sub == "cargo":
        from uexinfo.data.cargo_grids import (
            parse_cargo_spec,
            format_cargo_config,
            calculate_total_scu,
            VALID_SIZES,
        )

        if not rest:
            if ctx.player.ships:
                from uexinfo.cli.selector import SelectItem, pick
                items = [SelectItem(label=s.name, value=s.name) for s in ctx.player.ships]
                chosen = pick(ctx, items, title="Vaisseau — configuration cargo", mode="single", confirm_label="Voir config")
                if chosen:
                    rest = [chosen[0].value]
                else:
                    print_error("Usage : /ship cargo <nom> [--all|-a] [--clear|-c] [capacité] [32x<n>] ...")
                    console.print(f"  [{C.LABEL}]/ship cargo C2_Hercules[/{C.LABEL}]  [{C.DIM}](affiche config)[/{C.DIM}]")
                    console.print(f"  [{C.LABEL}]/ship cargo C2_Hercules 32x10 16x4[/{C.LABEL}]  [{C.DIM}](modifie)[/{C.DIM}]")
                    return
            else:
                print_warn("Aucun vaisseau configuré — /ship add <nom>")
                return

        # Extraire le nom du vaisseau et les flags
        ship_name_parts = []
        remaining_args = []
        modify_model = False
        clear_override = False

        for i, arg in enumerate(rest):
            if arg in ("--all", "-a"):
                modify_model = True
                remaining_args = rest[i+1:]
                break
            elif arg in ("--clear", "-c", "--clear"):
                clear_override = True
                remaining_args = rest[i+1:]
                break
            elif "x" in arg.lower() or arg.isdigit():
                remaining_args = rest[i:]
                break
            ship_name_parts.append(arg)

        if not ship_name_parts:
            print_error("Spécifiez le nom du vaisseau")
            return

        name = " ".join(ship_name_parts).replace("_", " ")

        # ── Option --clear : effacer l'override du modèle ──────────────────
        if clear_override:
            if ctx.cargo_grid_manager.clear_grid(name):
                print_ok(f"Override du modèle effacé pour {name}")
                console.print(f"[{C.DIM}]Le modèle utilise maintenant les données de base du programme[/{C.DIM}]")
            else:
                print_error(f"Aucun override trouvé pour {name}")
            return

        # ── Mode --all : afficher ou modifier le MODÈLE ─────────────────────
        if modify_model:
            # Si pas d'args : afficher le modèle
            if not remaining_args:
                grid = ctx.cargo_grid_manager.get_grid(name)
                if grid is None:
                    print_error(f"Modèle introuvable : {name}")
                    console.print(f"[{C.DIM}]Ce vaisseau n'existe pas dans la base de données[/{C.DIM}]")
                    return

                console.print(f"[bold]Modèle : {name}[/bold]")
                total_scu = calculate_total_scu(grid)
                console.print(f"  Capacité totale : [{C.UEX}]{total_scu} {C.SCU}[/{C.UEX}]")
                if grid:
                    console.print(f"  Configuration : [{C.LABEL}]{format_cargo_config(grid)}[/{C.LABEL}]")
                else:
                    console.print(f"  Configuration : [{C.DIM}](aucune)[/{C.DIM}]")

                if ctx.cargo_grid_manager.has_override(name):
                    console.print(f"  [{C.WARNING}]⚠ Modifié par l'utilisateur (override actif)[/{C.WARNING}]")
                else:
                    console.print(f"  [{C.DIM}]Données de base du programme[/{C.DIM}]")
                return

            # Sinon : modifier le modèle
            cargo_specs: dict[int, int] = {}
            explicit_scu = None

            for arg in remaining_args:
                if arg.isdigit():
                    explicit_scu = int(arg)
                    continue

                parsed = parse_cargo_spec(arg)
                if parsed:
                    size, qty = parsed
                    cargo_specs[size] = qty
                else:
                    print_error(f"Argument invalide : {arg}")
                    console.print(f"[{C.DIM}]Format : <taille>x<quantité> (ex: 32x4)[/{C.DIM}]")
                    return

            if not cargo_specs:
                print_error("Spécifiez au moins une configuration cargo")
                console.print(f"[{C.DIM}]Exemple : 32x10 16x4[/{C.DIM}]")
                return

            # Sauvegarder le modèle
            ctx.cargo_grid_manager.set_grid(name, cargo_specs)
            total_scu = calculate_total_scu(cargo_specs)
            console.print(f"[bold]Modèle modifié : {name}[/bold]")
            console.print(f"  Capacité : [{C.UEX}]{total_scu} {C.SCU}[/{C.UEX}]")
            console.print(f"  Configuration : [{C.LABEL}]{format_cargo_config(cargo_specs)}[/{C.LABEL}]")
            print_ok("Modèle sauvegardé dans le fichier d'extension")
            return

        # ── Mode normal : afficher ou modifier le VAISSEAU du joueur ────────
        match = next((s for s in ctx.player.ships if s.name.lower() == name.lower()), None)
        if match is None:
            print_error(f"Vaisseau introuvable dans votre flotte : {name}")
            console.print(f"[{C.DIM}]Ajoutez-le d'abord avec /ship add <nom>[/{C.DIM}]")
            if ctx.player.ships:
                console.print(f"\n[{C.DIM}]Vaisseaux disponibles :[/{C.DIM}]")
                for s in ctx.player.ships:
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]")
            return

        # Si pas d'args : afficher la config du vaisseau
        if not remaining_args:
            console.print(f"[bold]{match.name}[/bold]  [{C.DIM}](votre vaisseau)[/{C.DIM}]")
            console.print(f"  Capacité totale : [{C.UEX}]{match.scu or '?'} {C.SCU}[/{C.UEX}]")
            if match.cargo_config:
                console.print(f"  Configuration : [{C.LABEL}]{format_cargo_config(match.cargo_config)}[/{C.LABEL}]")
            else:
                console.print(f"  Configuration : [{C.DIM}](aucune - utilisez le modèle par défaut)[/{C.DIM}]")
                # Afficher le modèle si disponible
                grid = ctx.cargo_grid_manager.get_grid(match.name)
                if grid:
                    total = calculate_total_scu(grid)
                    console.print(f"  [{C.DIM}]Modèle disponible : {format_cargo_config(grid)} = {total} {C.SCU}[/{C.DIM}]")
            return

        # Sinon : modifier le vaisseau
        cargo_specs: dict[int, int] = {}
        explicit_scu = None

        for arg in remaining_args:
            if arg.isdigit():
                explicit_scu = int(arg)
                continue

            parsed = parse_cargo_spec(arg)
            if parsed:
                size, qty = parsed
                cargo_specs[size] = qty
            else:
                print_error(f"Argument invalide : {arg}")
                console.print(f"[{C.DIM}]Format : <taille>x<quantité> (ex: 32x4)[/{C.DIM}]")
                return

        if not cargo_specs and explicit_scu is None:
            print_error("Spécifiez au moins une configuration cargo ou une capacité")
            console.print(f"[{C.DIM}]Exemples : 32x10 16x4  OU  696[/{C.DIM}]")
            return

        # Mettre à jour le vaisseau
        if cargo_specs:
            match.cargo_config = cargo_specs
            calculated_scu = calculate_total_scu(cargo_specs)
            match.scu = explicit_scu if explicit_scu is not None else calculated_scu
        elif explicit_scu is not None:
            match.scu = explicit_scu

        _save_player(ctx)

        # Affichage de confirmation
        console.print(f"[bold]{match.name}[/bold]  [{C.DIM}](votre vaisseau)[/{C.DIM}]")
        console.print(f"  Capacité : [{C.UEX}]{match.scu} {C.SCU}[/{C.UEX}]")
        if match.cargo_config:
            config_str = format_cargo_config(match.cargo_config)
            calculated = calculate_total_scu(match.cargo_config)
            console.print(f"  Configuration : [{C.LABEL}]{config_str}[/{C.LABEL}]  [{C.DIM}]({calculated} {C.SCU})[/{C.DIM}]")
        print_ok("Configuration cargo mise à jour")

    else:
        print_error(f"Sous-commande inconnue : {sub}")
        console.print(f"[{C.DIM}]Commandes disponibles :[/{C.DIM}]")
        console.print(f"  [{C.LABEL}]/ship list[/{C.LABEL}]              [{C.DIM}]Liste vos vaisseaux[/{C.DIM}]")
        console.print(f"  [{C.LABEL}]/ship add <nom>[/{C.LABEL}]         [{C.DIM}]Ajoute un vaisseau[/{C.DIM}]")
        console.print(f"  [{C.LABEL}]/ship set <nom>[/{C.LABEL}]         [{C.DIM}]Définit le vaisseau actif[/{C.DIM}]")
        console.print(f"  [{C.LABEL}]/ship cargo <nom> [specs][/{C.LABEL}] [{C.DIM}]Configure les grilles cargo[/{C.DIM}]")
        console.print(f"  [{C.LABEL}]/ship remove <nom>[/{C.LABEL}]      [{C.DIM}]Retire un vaisseau[/{C.DIM}]")


# ── Trade ────────────────────────────────────────────────────────────────────

def _trade(args: list[str], ctx) -> None:
    if len(args) < 2:
        print_error("Usage: /config trade profit|margin|illegal <valeur>")
        return
    key, val = args[0].lower(), args[1]
    trade = ctx.cfg.setdefault("trade", {})

    if key == "profit":
        try:
            trade["min_profit_per_scu"] = int(val)
            settings.save(ctx.cfg)
            print_ok(f"Profit min/{C.SCU} : {val} {C.AUEC}")
        except ValueError:
            print_error("Valeur entière attendue")

    elif key == "margin":
        try:
            trade["min_margin_percent"] = float(val)
            settings.save(ctx.cfg)
            print_ok(f"Marge min : {val} %")
        except ValueError:
            print_error("Valeur numérique attendue")

    elif key == "illegal":
        enabled = val.lower() in ("on", "oui", "true", "1", "yes")
        trade["illegal_commodities"] = enabled
        settings.save(ctx.cfg)
        print_ok(f"Commodités illégales : {'activées' if enabled else 'désactivées'}")

    else:
        print_error(f"Option inconnue : {key}  (profit|margin|illegal)")


# ── Cache ────────────────────────────────────────────────────────────────────

def _cache(args: list[str], ctx) -> None:
    if not args:
        print_error("Usage: /config cache ttl <secondes>  |  /config cache clear")
        return

    sub = args[0].lower()

    if sub == "clear":
        import shutil
        from pathlib import Path
        import appdirs
        data_dir = Path(appdirs.user_data_dir("uexinfo"))
        if data_dir.exists():
            shutil.rmtree(data_dir)
            data_dir.mkdir(parents=True)
        ctx.cache.commodities.clear()
        ctx.cache.terminals.clear()
        ctx.cache.star_systems.clear()
        ctx.cache.planets.clear()
        print_ok("Cache vidé")

    elif sub == "ttl":
        if len(args) < 2:
            print_error("Usage: /config cache ttl <secondes>")
            return
        try:
            ttl = int(args[1])
            ctx.cfg.setdefault("cache", {})["ttl_static"] = ttl
            ctx.cache.ttl_static = ttl
            settings.save(ctx.cfg)
            print_ok(f"TTL statique : {ttl}s ({ttl // 3600}h{(ttl % 3600) // 60:02d}min)")
        except ValueError:
            print_error("Valeur entière attendue (secondes)")

    else:
        print_error(f"Sous-commande inconnue : {sub}  (ttl|clear)")


# ── Scan ─────────────────────────────────────────────────────────────────────

def _scan(args: list[str], ctx) -> None:
    if not args:
        _show(ctx.cfg, ctx)
        return
    key = args[0].lower()

    if key == "mode":
        if len(args) < 2 or args[1].lower() not in ("ocr", "log", "confirm"):
            print_error("Usage: /config scan mode ocr|log|confirm")
            return
        ctx.cfg["scan"]["mode"] = args[1].lower()
        settings.save(ctx.cfg)
        print_ok(f"Mode de scan : {args[1].lower()}")

    elif key == "tesseract":
        if len(args) < 2:
            print_error("Usage: /config scan tesseract <path>")
            return
        path = " ".join(args[1:]).strip("\"'")
        ctx.cfg["scan"]["tesseract_exe"] = path
        settings.save(ctx.cfg)
        print_ok(f"tesseract_exe = {path}")

    elif key == "logpath":
        if len(args) < 2:
            print_error("Usage: /config scan logpath <path>")
            return
        path = " ".join(args[1:]).strip("\"'")
        ctx.cfg["scan"]["sc_log_path"] = path
        settings.save(ctx.cfg)
        print_ok(f"sc_log_path = {path}")

    elif key == "screenshots":
        if len(args) < 2:
            print_error("Usage: /config scan screenshots <path>")
            return
        path = " ".join(args[1:]).strip("\"'")
        ctx.cfg["scan"]["sc_screenshots_dir"] = path
        settings.save(ctx.cfg)
        print_ok(f"sc_screenshots_dir = {path}")

    elif key == "auto_ocr":
        if len(args) < 2:
            print_error("Usage: /config scan auto_ocr on|off")
            return
        enabled = args[1].lower() in ("on", "true", "oui", "1", "yes")
        ctx.cfg.setdefault("scan", {})["auto_ocr"] = enabled
        settings.save(ctx.cfg)
        print_ok(f"OCR automatique : {'activé' if enabled else 'désactivé'}")

    elif key == "hour":
        if len(args) < 2:
            print_error("Usage: /config scan hour <n>  — fenêtre de recherche en heures")
            return
        try:
            h = max(1, int(args[1]))
            ctx.cfg.setdefault("scan", {})["hour"] = h
            settings.save(ctx.cfg)
            print_ok(f"Fenêtre de recherche missions : {h}h")
        except ValueError:
            print_error("Valeur entière attendue (heures)")

    elif key == "session_gap":
        if len(args) < 2:
            print_error("Usage: /config scan session_gap <minutes>  — gap entre sessions")
            return
        try:
            gap = max(5, int(args[1]))
            ctx.cfg.setdefault("scan", {})["session_gap"] = gap
            settings.save(ctx.cfg)
            print_ok(f"Gap de session : {gap} min")
        except ValueError:
            print_error("Valeur entière attendue (minutes)")

    else:
        print_error(f"Sous-clé inconnue : {key}  (mode|tesseract|logpath|screenshots|auto_ocr|hour|session_gap)")


# ── Overlay close ────────────────────────────────────────────────────────────

def _overlay_close(args: list[str], ctx) -> None:
    if not args or args[0].lower() not in ("normal", "dblclick"):
        print_error("Usage : /config close normal|dblclick")
        console.print(f"  [{C.DIM}]normal   — ✕ ferme immédiatement la fenêtre[/{C.DIM}]")
        console.print(f"  [{C.DIM}]dblclick — ✕ masque la fenêtre ; double-clic sur ✕ = fermer[/{C.DIM}]")
        return
    mode = args[0].lower()
    ctx.cfg.setdefault("overlay", {})["close"] = mode
    settings.save(ctx.cfg)
    if mode == "normal":
        print_ok("Fermeture : mode normal (✕ ferme)")
    else:
        print_ok("Fermeture : mode dblclick (✕ masque · double-clic ferme)")
    console.print(f"[{C.DIM}]Effectif au prochain lancement de l'overlay.[/{C.DIM}]")


def _clock(args: list[str], ctx) -> None:
    if not args or args[0].lower() not in ("on", "off"):
        current = ctx.cfg.get("overlay", {}).get("clock", True)
        print_error("Usage : /config clock on|off")
        console.print(f"  [{C.DIM}]Valeur actuelle : {'on' if current else 'off'}[/{C.DIM}]")
        return
    enabled = args[0].lower() == "on"
    ctx.cfg.setdefault("overlay", {})["clock"] = enabled
    settings.save(ctx.cfg)
    if enabled:
        print_ok("Horloge de fond : activée")
    else:
        print_ok("Horloge de fond : désactivée")
    send_fn = getattr(ctx, "_overlay_send_fn", None)
    if send_fn:
        send_fn({"type": "set_clock", "value": enabled})


# ── Clés pointées génériques  (ex: voyage.calc.nbsaut) ───────────────────────

# Clés acceptées avec leur type attendu et description
_DOT_KEYS: dict[str, tuple[type, str]] = {
    "scan.autopos":        (str,   "Mise à jour auto-position depuis tout scan OCR/log (on|off)"),
    "scan.log.autopos":    (str,   "Mise à jour auto-position depuis log Datarunner (on|off|quick)"),
    "voyage.calc.nbsaut":  (int,   "Nb max de missions par proposition"),
    "voyage.calc.prop":    (int,   "Nb de propositions (1=critère seul, ≥2=dist+benef+roi)"),
    "voyage.calc.options": (str,   'Options par défaut (ex: "--boucle --station")'),
    "voyage.calc.gap_max": (float, "Transit ⚠ au-delà de N Gm (défaut 3.0)"),
    "voyage.calc.favoris": (list,  "Lieux à privilégier — valeurs séparées par des espaces"),
    "voyage.calc.exclure": (list,  "Lieux à exclure — valeurs séparées par des espaces"),
}


def _set_dotkey(key: str, args: list[str], ctx) -> None:
    """Lecture/écriture d'une clé de config en notation pointée."""
    if key not in _DOT_KEYS:
        print_error(f"Clé inconnue : {key}")
        console.print(f"  [{C.DIM}]Clés disponibles : {', '.join(_DOT_KEYS)}[/{C.DIM}]")
        return

    expected_type, desc = _DOT_KEYS[key]
    parts = key.split(".")

    # Lecture de la valeur actuelle (navigation dans le dict imbriqué)
    node = ctx.cfg
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    current = node.get(parts[-1])

    if not args:
        # Affichage seul
        console.print(f"  [bold]{key} :[/bold]  [{C.UEX}]{current!r}[/{C.UEX}]")
        console.print(f"  [{C.DIM}]{desc}[/{C.DIM}]")
        return

    # Écriture
    raw = " ".join(args)
    try:
        if expected_type is list:
            # Chaque argument = un élément de la liste
            value = [a.replace("_", " ") for a in args]
        elif expected_type is int:
            value = int(raw)
        elif expected_type is float:
            value = float(raw.replace(",", "."))
        else:
            value = raw
    except ValueError:
        print_error(f"Valeur invalide pour {key} (attendu {expected_type.__name__}) : {raw!r}")
        return

    node[parts[-1]] = value
    settings.save(ctx.cfg)
    print_ok(f"{key} = {value!r}")


# ── Overlay hotkey ───────────────────────────────────────────────────────────

# Modificateurs reconnus (format config → format pynput)
_HK_MODIFIERS = {"alt", "alt_l", "alt_r", "shift", "shift_l", "shift_r",
                 "ctrl", "ctrl_l", "ctrl_r", "control", "win", "super", "cmd"}

# Touches spéciales courantes
_HK_SPECIAL = {
    "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
    "esc","escape","tab","enter","return","space","backspace","delete",
    "home","end","pageup","pagedown","insert","pause","printscreen",
    "up","down","left","right","numlock","capslock","scrolllock",
}


def _validate_hotkey(raw: str) -> tuple[bool, str, str]:
    """Valide et parse une hotkey.

    Retourne (ok, pynput_str, message_erreur).
    pynput_str est vide si validation impossible.
    """
    from uexinfo.overlay import _parse_hotkey

    if not raw.strip():
        return False, "", "Combinaison vide"

    normalized = raw.lower().strip()
    parts = [p.strip() for p in normalized.split("+") if p.strip()]
    if not parts:
        return False, "", "Aucune touche détectée"

    mods    = [p for p in parts if p in _HK_MODIFIERS]
    regkeys = [p for p in parts if p not in _HK_MODIFIERS]

    warnings: list[str] = []

    if not mods:
        warnings.append("⚠ Aucun modificateur (alt/ctrl/shift) — risque de conflit clavier")
    if not regkeys:
        return False, "", "Aucune touche principale (ex: u, f3, esc…)"
    if len(regkeys) > 1:
        warnings.append(f"⚠ Plusieurs touches principales : {regkeys} — seule la première sera utilisée")

    # Conversion au format pynput
    pynput_str = _parse_hotkey(normalized)

    # Test pynput si disponible
    try:
        from pynput.keyboard import HotKey
        HotKey.parse(pynput_str)          # lève ValueError si invalide
    except ImportError:
        warnings.append("(pynput non disponible — test non effectué)")
    except Exception as e:
        return False, pynput_str, f"Format invalide pour pynput : {e}"

    msg = "\n".join(warnings) if warnings else ""
    return True, pynput_str, msg


def _hotkey(args: list[str], ctx) -> None:
    current = ctx.cfg.get("overlay", {}).get("hotkey", "alt+shift+u")

    if not args:
        from uexinfo.overlay import _parse_hotkey
        console.print(f"  [bold]overlay.hotkey :[/bold]  [{C.UEX}]{current}[/{C.UEX}]"
                      f"  [{C.DIM}]→ pynput : {_parse_hotkey(current)}[/{C.DIM}]")
        console.print(
            f"\n  [{C.LABEL}]Format :[/{C.LABEL}]\n"
            f"    [{C.DIM}]Séparateur : [bold]+[/bold]   Modificateurs : [bold]alt  ctrl  shift[/bold][/{C.DIM}]\n"
            f"    [{C.DIM}]Lettres   : [bold]a-z[/bold]  (minuscule)[/{C.DIM}]\n"
            f"    [{C.DIM}]Fonctions : [bold]f1-f12[/bold] (pas de chevrons, ex: [bold]alt+f3[/bold])[/{C.DIM}]\n"
            f"    [{C.DIM}]Spéciales : [bold]esc  tab  space  home  end  pageup  pagedown[/bold][/{C.DIM}]\n"
            f"\n  [{C.LABEL}]Exemples valides :[/{C.LABEL}]\n"
            f"    [{C.DIM}]alt+shift+u      ctrl+shift+x      alt+f3      ctrl+f9[/{C.DIM}]\n"
            f"\n  [{C.LABEL}]Exemples invalides :[/{C.LABEL}]\n"
            f"    [{C.DIM}]<F3>     (ne pas mettre de chevrons — tapez : [bold]f3[/bold])[/{C.DIM}]\n"
            f"    [{C.DIM}]F3       (sera interprété [bold]f3[/bold] — mais sans modificateur : risque de conflit)[/{C.DIM}]\n"
            f"    [{C.DIM}]Alt+F3   (majuscules acceptées mais converties en minuscule)[/{C.DIM}]\n"
            f"\n  [{C.DIM}]Usage : /config hotkey <combinaison>[/{C.DIM}]"
        )
        return

    new_hk = args[0].strip()
    # Nettoyer les chevrons si l'utilisateur les a tapés (ex: <F3> → f3)
    import re as _re
    new_hk = _re.sub(r"<([^>]+)>", r"\1", new_hk).lower()

    if not new_hk:
        print_error("Combinaison vide")
        return

    ok, pynput_str, msg = _validate_hotkey(new_hk)

    if not ok:
        print_error(f"Hotkey invalide : {msg}")
        console.print(
            f"  [{C.DIM}]Exemples : alt+shift+u  ·  ctrl+f3  ·  alt+f9[/{C.DIM}]\n"
            f"  [{C.DIM}]/config hotkey  pour voir les formats acceptés[/{C.DIM}]"
        )
        return

    # Avertissements non bloquants
    if msg:
        for line in msg.splitlines():
            console.print(f"  [{C.WARNING}]{line}[/{C.WARNING}]")

    ctx.cfg.setdefault("overlay", {})["hotkey"] = new_hk
    settings.save(ctx.cfg)
    print_ok(f"Hotkey enregistrée : [{C.UEX}]{new_hk}[/{C.UEX}]")
    if pynput_str:
        console.print(f"  [{C.DIM}]Format pynput : [bold]{pynput_str}[/bold][/{C.DIM}]")
    console.print(f"  [{C.DIM}]Effectif au prochain lancement de l'overlay.[/{C.DIM}]")
    console.print(f"  [{C.DIM}]Ou : uexinfo --hotkey {new_hk}  pour forcer au lancement.[/{C.DIM}]")


# ── Player config ─────────────────────────────────────────────────────────────

def _player_config(args: list[str], ctx) -> None:
    """Affiche la config joueur — modification via /player."""
    player = ctx.cfg.get("player", {})
    section("Configuration joueur")
    console.print(f"  [bold]username :[/bold]    {player.get('username') or '—'}")
    console.print(f"  [bold]active_ship :[/bold] {player.get('active_ship') or '—'}")
    console.print(f"  [bold]location :[/bold]    {player.get('location') or '—'}")
    console.print(f"  [bold]destination :[/bold] {player.get('destination') or '—'}")
    ships = player.get("ships", [])
    if ships:
        ship_list = ", ".join(
            f"{s['name']} ({s['scu']} {C.SCU})" if s.get("scu") else s["name"]
            for s in ships
        )
        console.print(f"  [bold]ships :[/bold]       {ship_list}")
    console.print(f"  [{C.DIM}]Modifier via /player ship add|set|scu|remove[/{C.DIM}]")
