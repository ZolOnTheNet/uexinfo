"""Commande /undo — annuler le dernier scan."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.display.formatter import console, print_warn
from uexinfo.display import colors as C


@register("undo")
def cmd_undo(args: list[str], ctx) -> None:
    """Supprime le dernier scan de l'historique et remet last_scan au précédent."""
    if not ctx.scan_history:
        print_warn("Aucun scan à annuler.")
        return

    removed = ctx.scan_history.pop()
    console.print(
        f"[{C.WARNING}]↩  Scan annulé[/{C.WARNING}] : "
        f"[bold]{removed.terminal}[/bold]"
        f"  [{C.DIM}]{removed.timestamp.strftime('%H:%M:%S')}  "
        f"source={removed.source}[/{C.DIM}]"
        f"  ({len(removed.commodities)} commodité{'s' if len(removed.commodities) != 1 else ''})"
    )

    # Remettre last_scan au scan précédent (ou None)
    ctx.last_scan = ctx.scan_history[-1] if ctx.scan_history else None
    if ctx.last_scan:
        console.print(
            f"[{C.DIM}]  Scan actif → {ctx.last_scan.terminal}"
            f"  {ctx.last_scan.timestamp.strftime('%H:%M:%S')}[/{C.DIM}]"
        )
    else:
        console.print(f"[{C.DIM}]  Aucun scan actif.[/{C.DIM}]")
