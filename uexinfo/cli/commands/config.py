"""Commande /config."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section


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


# ── Ship ─────────────────────────────────────────────────────────────────────

def _ship(args: list[str], ctx) -> None:
    if not args:
        print_error("Usage: /config ship add|remove|set|cargo <...>")
        return

    sub = args[0].lower()
    rest = args[1:]
    ships = ctx.cfg.setdefault("ships", {})
    available: list = ships.setdefault("available", [])
    cargo: dict = ctx.cfg.setdefault("cargo", {})

    if sub == "add":
        name = " ".join(rest)
        if not name:
            print_error("Spécifie un nom de vaisseau")
            return
        if name not in available:
            available.append(name)
            if not ships.get("current"):
                ships["current"] = name
            settings.save(ctx.cfg)
            print_ok(f"Vaisseau ajouté : {name}")
        else:
            print_warn(f"{name} est déjà dans la liste")

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
