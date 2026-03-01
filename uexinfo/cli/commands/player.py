"""Commande /player — gestion joueur, vaisseau, position."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.models.player import Ship
import uexinfo.config.settings as settings
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.display import colors as C


def _save_player(ctx) -> None:
    ctx.cfg["player"] = ctx.player.to_config()
    settings.save(ctx.cfg)


def _show_info(ctx) -> None:
    section("Joueur")
    p = ctx.player
    from rich.table import Table
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style=C.LABEL, no_wrap=True)
    t.add_column(style=C.NEUTRAL)

    t.add_row("[bold]Vaisseau actif[/bold]", p.active_ship or "[dim]—[/dim]")
    t.add_row("[bold]Position[/bold]", p.location or "[dim]—[/dim]")
    t.add_row("[bold]Destination[/bold]", p.destination or "[dim]—[/dim]")

    if p.ships:
        ship_list = ", ".join(
            f"{s.name} ({s.scu} SCU)" if s.scu else s.name
            for s in p.ships
        )
        t.add_row("[bold]Vaisseaux[/bold]", ship_list)

    console.print(t)


def _resolve_location(token: str, ctx) -> str:
    """Résout un token @lieu en nom canonique."""
    query = token.lstrip("@")
    entries = ctx.location_index.search(query, limit=1)
    if entries:
        return entries[0].name
    return query  # fallback : utiliser tel quel


@register("player")
def cmd_player(args: list[str], ctx) -> None:
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
        loc = _resolve_location(" ".join(args), ctx)
        ctx.player.location = loc
        _save_player(ctx)
        print_ok(f"Position : {loc}")
        return

    # /player dest @lieu
    if sub == "dest":
        rest = args[1:]
        if not rest or not rest[0].startswith("@"):
            print_error("Usage : /player dest @<lieu>")
            return
        loc = _resolve_location(" ".join(rest), ctx)
        ctx.player.destination = loc
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
                scu_str = f"  [{C.DIM}]{s.scu} SCU[/{C.DIM}]" if s.scu else ""
                console.print(f"{marker}[{C.LABEL}]{s.name}[/{C.LABEL}]{scu_str}")
            return

        action = args[1].lower()

        if action == "add":
            if len(args) < 3:
                print_error("Usage : /player ship add <nom> [scu]")
                return
            name = args[2]
            scu = 0
            if len(args) >= 4:
                try:
                    scu = int(args[3])
                except ValueError:
                    print_error("SCU doit être un entier")
                    return
            # Vérifier doublon
            if any(s.name.lower() == name.lower() for s in ctx.player.ships):
                print_warn(f"Vaisseau déjà présent : {name}")
                return
            ctx.player.ships.append(Ship(name=name, scu=scu))
            _save_player(ctx)
            print_ok(f"Vaisseau ajouté : {name}" + (f" ({scu} SCU)" if scu else ""))

        elif action == "set":
            if len(args) < 3:
                print_error("Usage : /player ship set <nom>")
                return
            name = args[2]
            match = next((s for s in ctx.player.ships if s.name.lower() == name.lower()), None)
            if match is None:
                print_error(f"Vaisseau inconnu : {name}")
                return
            ctx.player.active_ship = match.name
            _save_player(ctx)
            print_ok(f"Vaisseau actif : {match.name}")

        elif action == "scu":
            if len(args) < 4:
                print_error("Usage : /player ship scu <nom> <n>")
                return
            name = args[2]
            try:
                scu = int(args[3])
            except ValueError:
                print_error("SCU doit être un entier")
                return
            match = next((s for s in ctx.player.ships if s.name.lower() == name.lower()), None)
            if match is None:
                print_error(f"Vaisseau inconnu : {name}")
                return
            match.scu = scu
            _save_player(ctx)
            print_ok(f"{match.name} : {scu} SCU")

        elif action == "remove":
            if len(args) < 3:
                print_error("Usage : /player ship remove <nom>")
                return
            name = args[2]
            before = len(ctx.player.ships)
            ctx.player.ships = [s for s in ctx.player.ships if s.name.lower() != name.lower()]
            if len(ctx.player.ships) == before:
                print_error(f"Vaisseau introuvable : {name}")
                return
            if ctx.player.active_ship.lower() == name.lower():
                ctx.player.active_ship = ""
            _save_player(ctx)
            print_ok(f"Vaisseau supprimé : {name}")

        else:
            print_error(f"Action inconnue : {action}  —  add|set|scu|remove")
        return

    print_error(f"Sous-commande inconnue : {sub}  —  tapez /help player")
