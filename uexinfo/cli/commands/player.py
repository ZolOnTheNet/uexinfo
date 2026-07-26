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


def _resolve_location(token: str, ctx) -> tuple[str, int]:
    """Résout un token @lieu en (nom canonique, id terminal UEX ou 0).

    L'id n'est renvoyé que pour une entrée de type "terminal" (LocationIndex
    associe déjà entity_id=terminal.id, avec la priorité de trading TDD >
    Admin/Trade > autre déjà appliquée dans LocationIndex._build()) — un
    système/planète/station résolu n'a pas d'id terminal exploitable pour
    /trade, donc 0 (comme /go clear).
    """
    query = token.lstrip("@")
    entries = ctx.location_index.search(query, limit=1)
    if entries:
        entry = entries[0]
        return entry.name, (entry.entity_id if entry.type == "terminal" else 0)
    return query, 0  # fallback : utiliser tel quel, id inconnu


@register("player", "p")
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
        loc, loc_id = _resolve_location(" ".join(args), ctx)
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
        loc, loc_id = _resolve_location(" ".join(rest), ctx)
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
            # Vérifier doublon
            if any(s.name.lower() == name.lower() for s in ctx.player.ships):
                print_warn(f"Vaisseau déjà présent : {name}")
                return
            ctx.player.ships.append(Ship(name=name, scu=scu))
            _save_player(ctx)
            print_ok(f"Vaisseau ajouté : {name}" + (f" ({scu} {C.SCU})" if scu else ""))

        elif action in ("set", "select"):
            if len(args) < 3:
                print_error("Usage : /player ship set <nom>")
                return
            name = " ".join(args[2:]).replace("_", " ")
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
            try:
                scu = int(args[-1])
            except ValueError:
                print_error("SCU doit être un entier")
                return
            name = " ".join(args[2:-1]).replace("_", " ")
            match = next((s for s in ctx.player.ships if s.name.lower() == name.lower()), None)
            if match is None:
                print_error(f"Vaisseau inconnu : {name}")
                return
            match.scu = scu
            _save_player(ctx)
            print_ok(f"{match.name} : {scu} {C.SCU}")

        elif action == "remove":
            if len(args) < 3:
                print_error("Usage : /player ship remove <nom>")
                return
            name = " ".join(args[2:]).replace("_", " ")
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
