"""Commande /refresh — mise à jour du cache."""
from __future__ import annotations

import json
import time
from pathlib import Path

import appdirs

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_info, print_ok


@register("refresh")
def cmd_refresh(args: list[str], ctx) -> None:
    sub = args[0].lower() if args else "all"

    if sub == "status":
        _status(ctx)
    elif sub in ("all", "static"):
        _refresh_static(ctx)
    elif sub == "prices":
        print_info("Les prix sont chargés à la demande — utilisez /trade pour des prix live.")
    elif sub == "sctrade":
        print_info("Intégration sc-trade.tools disponible en Phase 4.")
    else:
        print_error(f"Option inconnue : {sub}  (all | static | prices | sctrade | status)")


def _refresh_static(ctx) -> None:
    try:
        ctx.cache.load(force=True)
    except Exception as e:
        print_error(f"Erreur lors du refresh : {e}")


def _status(ctx) -> None:
    data_dir = Path(appdirs.user_data_dir("uexinfo"))
    entries = {
        "commodities.json": ("Commodités",  len(ctx.cache.commodities)),
        "terminals.json":   ("Terminaux",   len(ctx.cache.terminals)),
        "star_systems.json":("Systèmes",    len(ctx.cache.star_systems)),
        "planets.json":     ("Planètes",    len(ctx.cache.planets)),
    }
    from rich.table import Table
    t = Table(show_header=True, header_style=f"bold {C.UEX}", box=None, padding=(0, 2))
    t.add_column("Données")
    t.add_column("Âge",    justify="right")
    t.add_column("Entrées", justify="right")

    for fname, (label, count) in entries.items():
        path = data_dir / fname
        if path.exists():
            age = int(time.time() - path.stat().st_mtime)
            h, m = divmod(age // 60, 60)
            age_str = f"{h}h{m:02d}" if h else f"{m}min"
            color = C.WARNING if age > 86400 else C.SUCCESS
            t.add_row(label, f"[{color}]{age_str}[/{color}]", str(count))
        else:
            t.add_row(label, f"[{C.DIM}]absent[/{C.DIM}]", "[dim]—[/dim]")

    console.print(t)
    console.print(f"  [{C.DIM}]Répertoire : {data_dir}[/{C.DIM}]")
