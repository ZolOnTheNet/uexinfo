"""Commande /player — gestion joueur, vaisseau, position."""
from __future__ import annotations

from uexinfo.cli.commands import register
import uexinfo.config.settings as settings
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.display import colors as C


def _save_player(ctx) -> None:
    """Recopie le joueur dans la configuration et l'enregistre."""
    ctx.cfg["player"] = ctx.player.to_config()
    settings.save(ctx.cfg)


def _show_info(ctx) -> None:
    """Affiche la fiche joueur : vaisseau actif, position, destination, contexte lu dans Game.log."""
    section("Joueur")
    p = ctx.player
    from rich.table import Table
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style=C.LABEL, no_wrap=True)
    t.add_column(style=C.NEUTRAL)

    t.add_row("[bold]Vaisseau actif[/bold]", p.active_ship or "[dim]—[/dim]")
    t.add_row("[bold]Position[/bold]", p.location or "[dim]—[/dim]")
    t.add_row("[bold]Destination[/bold]", p.destination or "[dim]—[/dim]")
    if p.zone:
        t.add_row("[bold]Lieu (Game.log)[/bold]", f"[{C.DIM}]{p.zone}[/{C.DIM}]")
    if p.zone_status:
        status_display = p.zone_status.rstrip(": ").strip()
        t.add_row("[bold]Statut[/bold]", f"[{C.DIM}]{status_display}[/{C.DIM}]")
    if p.shard:
        t.add_row("[bold]Shard[/bold]", f"[{C.DIM}]{p.shard}[/{C.DIM}]")

    if p.ships:
        ship_list = ", ".join(
            f"{s.name} ({s.scu} {C.SCU})" if s.scu else s.name
            for s in p.ships
        )
        t.add_row("[bold]Vaisseaux[/bold]", ship_list)

    console.print(t)


def _resolve_location(token: str, ctx) -> tuple[str, int] | None:
    """Résout un token @lieu en (nom affiché, id terminal UEX ou 0), comme /go.

    L'id n'est renvoyé que pour un terminal : une planète ou un système n'a pas
    d'id terminal exploitable pour /trade, donc 0. None si introuvable ou annulé
    (un nom inconnu n'est jamais enregistré tel quel, D11).
    Les underscores viennent de la complétion @lieu (« @TDD_-_Area_18 »).
    """
    query = token.lstrip("@").replace("_", " ")
    from uexinfo.cache.models import Terminal
    from uexinfo.cli.commands.go import _resolve
    from uexinfo.display.formatter import terminal_short_name
    obj = _resolve(query, ctx)   # même choix que /go (règle 3, D11) ; None si introuvable
    if obj is None:
        return None
    if isinstance(obj, Terminal):
        return terminal_short_name(obj.name), obj.id
    return obj.name, 0


@register("player", "p")
def cmd_player(args: list[str], ctx) -> None:
    """/player [info | ship | dest | @lieu] — fiche joueur, vaisseaux, position et destination."""
    if not args:
        _show_info(ctx)
        return

    sub = args[0].lower()

    # /player info
    if sub == "info":
        _show_info(ctx)
        return

    # /player @lieu  — définir position (supporte noms avec espaces)
    if sub.startswith("@"):
        place = _resolve_location(" ".join(args), ctx)
        if place is None:
            return
        loc, loc_id = place
        ctx.player.set_location(loc, loc_id)
        _save_player(ctx)
        print_ok(f"Position : {loc}")
        return

    # /player dest @lieu
    if sub == "dest":
        rest = args[1:]
        if not rest or not rest[0].startswith("@"):
            print_error("Usage : /player dest @<lieu>")
            return
        place = _resolve_location(" ".join(rest), ctx)
        if place is None:
            return
        loc, loc_id = place
        ctx.player.set_destination(loc, loc_id)
        _save_player(ctx)
        print_ok(f"Destination : {loc}")
        return

    # /player ship …
    if sub == "ship":
        if not args[1:]:
            # Lister les vaisseaux
            if not ctx.player.ships:
                print_warn("Aucun vaisseau configuré.")
                return
            for s in ctx.player.ships:
                marker = "[bold cyan]*[/bold cyan] " if s.name == ctx.player.active_ship else "  "
                scu_str = f"  [{C.DIM}]{s.scu} {C.SCU}[/{C.DIM}]" if s.scu else ""
                console.print(f"{marker}[{C.LABEL}]{s.name}[/{C.LABEL}]{scu_str}")
            return

        action = args[1].lower()

        if action == "add":
            if len(args) < 3:
                print_error("Usage : /player ship add <nom> [scu]")
                return
            rest = args[2:]
            scu = 0
            if len(rest) >= 2:
                try:
                    scu = int(rest[-1])
                    rest = rest[:-1]
                except ValueError:
                    pass
            name = " ".join(rest).replace("_", " ")
            # Même ajout que /ship add : vaisseau UEX reconnu, règle 3 (D11)
            from uexinfo.cli.commands.config import _add_ship
            if _add_ship(name, ctx, scu=scu):
                _save_player(ctx)

        elif action in ("set", "select"):
            if len(args) < 3:
                print_error("Usage : /player ship set <nom>")
                return
            name = " ".join(args[2:]).replace("_", " ")
            from uexinfo.cli.commands.config import _pick_ship
            match = _pick_ship(name, ctx)
            if match is None:
                return
            ctx.player.active_ship = match.name
            _save_player(ctx)
            print_ok(f"Vaisseau actif : {match.name}")

        elif action == "scu":
            if len(args) < 4:
                print_error("Usage : /player ship scu <nom> <n>")
                return
            try:
                scu = int(args[-1])
            except ValueError:
                print_error("SCU doit être un entier")
                return
            name = " ".join(args[2:-1]).replace("_", " ")
            from uexinfo.cli.commands.config import _pick_ship
            match = _pick_ship(name, ctx)
            if match is None:
                return
            match.scu = scu
            _save_player(ctx)
            print_ok(f"{match.name} : {scu} {C.SCU}")

        elif action == "remove":
            if len(args) < 3:
                print_error("Usage : /player ship remove <nom>")
                return
            name = " ".join(args[2:]).replace("_", " ")
            from uexinfo.cli.commands.config import _pick_ship
            match = _pick_ship(name, ctx)
            if match is None:
                return
            ctx.player.ships = [s for s in ctx.player.ships if s is not match]
            if ctx.player.active_ship == match.name:
                ctx.player.active_ship = ""
            _save_player(ctx)
            print_ok(f"Vaisseau supprimé : {match.name}")

        else:
            print_error(f"Action inconnue : {action}  —  add|set|scu|remove")
        return

    print_error(f"Sous-commande inconnue : {sub}  —  tapez /help player")
