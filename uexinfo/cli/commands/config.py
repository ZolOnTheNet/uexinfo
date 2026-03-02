"""Commande /config."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section


@register("ship")
def cmd_ship(args: list[str], ctx) -> None:
    _ship(args, ctx)


@register("config")
def cmd_config(args: list[str], ctx) -> None:
    if not args:
        _show(ctx.cfg)
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
    else:
        print_error(f"Sous-commande inconnue : {sub}  (/help config)")


# ── Affichage ────────────────────────────────────────────────────────────────

def _show(cfg: dict) -> None:
    section("Configuration")
    ships = cfg.get("ships", {})
    current = ships.get("current", "")
    available = ships.get("available", [])
    cargo = cfg.get("cargo", {})
    pos = cfg.get("position", {})
    trade = cfg.get("trade", {})
    cache_cfg = cfg.get("cache", {})
    scan = cfg.get("scan", {})
    player = cfg.get("player", {})

    console.print(f"  [bold]Vaisseau actif :[/bold] [{C.UEX}]{current or '(non défini)'}[/{C.UEX}]")
    if available:
        for s in available:
            scu = cargo.get(s, "?")
            marker = "  ◄ actif" if s == current else ""
            console.print(f"    [{C.UEX}]{s}[/{C.UEX}]  [{C.DIM}]{scu} SCU{marker}[/{C.DIM}]")
    console.print(f"  [bold]Position :[/bold]    [{C.UEX}]{pos.get('current') or '(non définie)'}[/{C.UEX}]")
    console.print(f"  [bold]Destination :[/bold] [{C.UEX}]{pos.get('destination') or '(non définie)'}[/{C.UEX}]")
    console.print(f"  [bold]Profit min/SCU :[/bold] {trade.get('min_profit_per_scu', 0)} aUEC")
    console.print(f"  [bold]Marge min :[/bold]     {trade.get('min_margin_percent', 0)} %")
    console.print(f"  [bold]Illégal :[/bold]       {'oui' if trade.get('illegal_commodities') else 'non'}")
    console.print(f"  [bold]TTL cache :[/bold]     {cache_cfg.get('ttl_static', 86400)}s statique  /  {cache_cfg.get('ttl_prices', 300)}s prix")
    console.print(f"  [bold]scan.mode :[/bold]        {scan.get('mode', 'ocr')}  [{C.DIM}](ocr|log|confirm)[/{C.DIM}]")
    console.print(f"  [bold]scan.tesseract :[/bold]   {scan.get('tesseract_exe') or '(auto)'}  [{C.DIM}](moteur OCR pour lire les screenshots)[/{C.DIM}]")
    console.print(f"  [bold]scan.logpath :[/bold]     {scan.get('sc_log_path') or '(non défini)'}")
    console.print(f"  [bold]scan.screenshots :[/bold] {scan.get('sc_screenshots_dir') or '(non défini)'}")
    console.print(f"  [bold]player.active_ship :[/bold] {player.get('active_ship') or '—'}")
    console.print(f"  [bold]player.location :[/bold]    {player.get('location') or '—'}")


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


# ── Ship ─────────────────────────────────────────────────────────────────────

def _ship(args: list[str], ctx) -> None:
    if not args:
        print_error("Usage: /config ship list|add|remove|set|cargo <...>")
        return

    sub = args[0].lower()
    rest = args[1:]
    ships = ctx.cfg.setdefault("ships", {})
    available: list = ships.setdefault("available", [])
    cargo: dict = ctx.cfg.setdefault("cargo", {})

    if sub == "list":
        if not available:
            print_warn("Aucun vaisseau configuré — /config ship add <nom>")
            return
        section("Vaisseaux configurés")
        current = ships.get("current", "")
        for s in available:
            scu = cargo.get(s, "?")
            marker = f"  [{C.SUCCESS}]◄ actif[/{C.SUCCESS}]" if s == current else ""
            console.print(f"  [{C.UEX}]{s}[/{C.UEX}]  [{C.DIM}]{scu} SCU[/{C.DIM}]{marker}")
        return

    if sub == "add":
        raw = " ".join(rest).replace("_", " ")
        if not raw:
            print_error("Spécifie un ou plusieurs noms de vaisseau (séparés par des virgules)")
            return
        names = [n.strip() for n in raw.split(",") if n.strip()] if "," in raw else [raw]
        for name in names:
            vehicle = _find_vehicle(name, ctx)
            # Utiliser le nom canonique (avec fabricant) si trouvé dans le cache
            canon = vehicle.name_full if vehicle else name
            if canon in available:
                print_warn(f"{canon} déjà dans la liste")
                continue
            available.append(canon)
            if not ships.get("current"):
                ships["current"] = canon
            # Sauvegarder le SCU depuis le cache véhicule
            if vehicle and vehicle.scu:
                cargo[canon] = vehicle.scu
            info = f"  [{C.DIM}]{vehicle.scu} SCU · pad {vehicle.pad_type}[/{C.DIM}]" if vehicle else ""
            if not vehicle:
                info = f"  [{C.WARNING}]vaisseau non trouvé dans le cache — SCU à configurer manuellement[/{C.WARNING}]"
            print_ok(f"Vaisseau ajouté : {canon}{info}")
        settings.save(ctx.cfg)

    elif sub == "remove":
        name = " ".join(rest)
        if name in available:
            available.remove(name)
            cargo.pop(name, None)
            if ships.get("current") == name:
                ships["current"] = available[0] if available else ""
            settings.save(ctx.cfg)
            print_ok(f"Vaisseau retiré : {name}")
        else:
            print_error(f"Vaisseau introuvable : {name}")

    elif sub == "set":
        name = " ".join(rest)
        if name in available:
            ships["current"] = name
            settings.save(ctx.cfg)
            print_ok(f"Vaisseau actif : {name}")
        else:
            print_error(f"{name} n'est pas dans la liste — ajoutez-le avec /config ship add")

    elif sub == "cargo":
        if len(rest) < 2:
            print_error("Usage: /config ship cargo <nom> <scu>")
            return
        try:
            scu = int(rest[-1])
            name = " ".join(rest[:-1])
        except ValueError:
            print_error("Le nombre de SCU doit être un entier")
            return
        if name not in available:
            print_error(f"Vaisseau introuvable : {name}")
            return
        cargo[name] = scu
        settings.save(ctx.cfg)
        print_ok(f"{name} → {scu} SCU")

    else:
        print_error(f"Sous-commande inconnue : {sub}")


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
            print_ok(f"Profit min/SCU : {val} aUEC")
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
        _show(ctx.cfg)
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
        ctx.cfg["scan"]["tesseract_exe"] = args[1]
        settings.save(ctx.cfg)
        print_ok(f"tesseract_exe = {args[1]}")

    elif key == "logpath":
        if len(args) < 2:
            print_error("Usage: /config scan logpath <path>")
            return
        ctx.cfg["scan"]["sc_log_path"] = args[1]
        settings.save(ctx.cfg)
        print_ok(f"sc_log_path = {args[1]}")

    elif key == "screenshots":
        if len(args) < 2:
            print_error("Usage: /config scan screenshots <path>")
            return
        ctx.cfg["scan"]["sc_screenshots_dir"] = args[1]
        settings.save(ctx.cfg)
        print_ok(f"sc_screenshots_dir = {args[1]}")

    else:
        print_error(f"Sous-clé inconnue : {key}  (mode|tesseract|logpath|screenshots)")


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
            f"{s['name']} ({s['scu']} SCU)" if s.get("scu") else s["name"]
            for s in ships
        )
        console.print(f"  [bold]ships :[/bold]       {ship_list}")
    console.print(f"  [{C.DIM}]Modifier via /player ship add|set|scu|remove[/{C.DIM}]")
