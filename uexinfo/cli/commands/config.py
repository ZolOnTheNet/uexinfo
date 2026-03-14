"""Commande /config."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section


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
            console.print(f"    [{C.UEX}]{s.name}[/{C.UEX}]  [{C.DIM}]{scu_str} SCU[/{C.DIM}]{marker}")
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

    # ── Trade / cache / scan ───────────────────────────────────────────────
    console.print(f"  [bold]Profit min/{C.SCU} :[/bold] {trade.get('min_profit_per_scu', 0)} {C.AUEC}")
    console.print(f"  [bold]Marge min :[/bold]     {trade.get('min_margin_percent', 0)} %")
    console.print(f"  [bold]Illégal :[/bold]       {'oui' if trade.get('illegal_commodities') else 'non'}")
    console.print(f"  [bold]TTL cache :[/bold]     {cache_cfg.get('ttl_static', 86400)}s statique  /  {cache_cfg.get('ttl_prices', 300)}s prix")
    console.print(f"  [bold]scan.mode :[/bold]        {scan.get('mode', 'ocr')}  [{C.DIM}](ocr|log|confirm)[/{C.DIM}]")
    console.print(f"  [bold]scan.tesseract :[/bold]   {scan.get('tesseract_exe') or '(auto)'}  [{C.DIM}](moteur OCR pour lire les screenshots)[/{C.DIM}]")
    console.print(f"  [bold]scan.logpath :[/bold]     {scan.get('sc_log_path') or '(non défini)'}")
    console.print(f"  [bold]scan.screenshots :[/bold] {scan.get('sc_screenshots_dir') or '(non défini)'}")


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
            console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]  [{C.DIM}]{scu_str} SCU[/{C.DIM}]{grid_str}{marker}")
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
                            f"[{C.DIM}]{v.scu} SCU · {v.pad_type}[/{C.DIM}]"
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
            info = f"  [{C.DIM}]{vehicle.scu} SCU · pad {vehicle.pad_type}[/{C.DIM}]" if vehicle else ""
            if not vehicle:
                info = f"  [{C.WARNING}]vaisseau non trouvé dans le cache — SCU à configurer manuellement[/{C.WARNING}]"
            print_ok(f"Vaisseau ajouté : {canon}{info}")
        _save_player(ctx)

    elif sub == "remove":
        name   = " ".join(rest)
        if not name:
            print_error("Usage : /ship remove <nom du vaisseau>")
            if ctx.player.ships:
                console.print(f"[{C.DIM}]Vaisseaux actuels :[/{C.DIM}]")
                for s in ctx.player.ships[:5]:
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]")
            return
        before = len(ctx.player.ships)
        ctx.player.ships = [s for s in ctx.player.ships if s.name.lower() != name.lower()]
        if len(ctx.player.ships) == before:
            print_error(f"Vaisseau introuvable : {name}")
            if ctx.player.ships:
                console.print(f"[{C.DIM}]Vaisseaux disponibles :[/{C.DIM}]")
                for s in ctx.player.ships[:5]:
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]")
            return
        if ctx.player.active_ship.lower() == name.lower():
            ctx.player.active_ship = ctx.player.ships[0].name if ctx.player.ships else ""
        _save_player(ctx)
        print_ok(f"Vaisseau retiré : {name}")

    elif sub in ("set", "select"):
        name  = " ".join(rest)
        if not name:
            print_error("Usage : /ship set <nom du vaisseau>")
            if ctx.player.ships:
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
            print_error("Usage : /ship cargo <nom> [--all|-a] [--clear|-c] [capacité] [32x<n>] ...")
            console.print(f"[{C.DIM}]Exemples :[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship cargo C2_Hercules[/{C.LABEL}]  [{C.DIM}](affiche config du vaisseau)[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship cargo C2_Hercules 32x10 16x4[/{C.LABEL}]  [{C.DIM}](modifie le vaisseau)[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship cargo \"Cutlass Black\" --all[/{C.LABEL}]  [{C.DIM}](affiche le modèle)[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship cargo Cutlass_Black -a 16x2 8x1[/{C.LABEL}]  [{C.DIM}](modifie le modèle)[/{C.DIM}]")
            console.print(f"  [{C.LABEL}]/ship cargo Cutlass_Black --clear[/{C.LABEL}]  [{C.DIM}](efface override modèle)[/{C.DIM}]")
            console.print(f"\n[{C.DIM}]Tailles acceptées : 1, 2, 4, 8, 16, 24, 32 SCU[/{C.DIM}]")
            console.print(f"[{C.DIM}]--all/-a : modifie le modèle (partagé) au lieu du vaisseau du joueur[/{C.DIM}]")
            console.print(f"[{C.DIM}]--clear/-c : efface l'override du modèle et revient aux données de base[/{C.DIM}]")
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
                console.print(f"  Capacité totale : [{C.UEX}]{total_scu} SCU[/{C.UEX}]")
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
            console.print(f"  Capacité : [{C.UEX}]{total_scu} SCU[/{C.UEX}]")
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
                for s in ctx.player.ships[:5]:
                    console.print(f"  [{C.UEX}]{s.name}[/{C.UEX}]")
            return

        # Si pas d'args : afficher la config du vaisseau
        if not remaining_args:
            console.print(f"[bold]{match.name}[/bold]  [{C.DIM}](votre vaisseau)[/{C.DIM}]")
            console.print(f"  Capacité totale : [{C.UEX}]{match.scu or '?'} SCU[/{C.UEX}]")
            if match.cargo_config:
                console.print(f"  Configuration : [{C.LABEL}]{format_cargo_config(match.cargo_config)}[/{C.LABEL}]")
            else:
                console.print(f"  Configuration : [{C.DIM}](aucune - utilisez le modèle par défaut)[/{C.DIM}]")
                # Afficher le modèle si disponible
                grid = ctx.cargo_grid_manager.get_grid(match.name)
                if grid:
                    total = calculate_total_scu(grid)
                    console.print(f"  [{C.DIM}]Modèle disponible : {format_cargo_config(grid)} = {total} SCU[/{C.DIM}]")
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
        console.print(f"  Capacité : [{C.UEX}]{match.scu} SCU[/{C.UEX}]")
        if match.cargo_config:
            config_str = format_cargo_config(match.cargo_config)
            calculated = calculate_total_scu(match.cargo_config)
            console.print(f"  Configuration : [{C.LABEL}]{config_str}[/{C.LABEL}]  [{C.DIM}]({calculated} SCU)[/{C.DIM}]")
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
