"""StatusBar — barre de statut simple (Pos · Dest · Vaisseau · Cargo)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Label, Static


class StatusBar(Static):
    """Ligne unique : Pos · Dest · Vaisseau · Cargo restant/total."""

    def compose(self) -> ComposeResult:
        yield Label("", id="status-label", markup=True)

    def refresh_status(self, ctx) -> None:
        if ctx is None:
            return
        loc   = ctx.player.location or "—"
        dest  = ctx.player.destination or "—"
        ship  = ctx.player.active_ship or "—"

        cargo_total = 0
        if ctx.player.active_ship:
            for s in ctx.player.ships:
                if s.name == ctx.player.active_ship:
                    cargo_total = s.scu or 0
                    break

        cargo_str = f"{cargo_total} SCU" if cargo_total else "— SCU"

        text = (
            f"[dim]Pos:[/dim] [cyan]{loc}[/cyan]"
            f"   [dim]Dest:[/dim] {dest}"
            f"   [dim]Vaisseau:[/dim] {ship}"
            f"   [cyan]{cargo_str}[/cyan]"
        )
        self.query_one("#status-label", Label).update(text)
