"""Écran Routes — Phase 3 (stub)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


class RouteScreen(Static):
    """Écran de planification de routes commerciales."""

    def compose(self) -> ComposeResult:
        yield Static(
            "\n"
            "  [bold cyan]Routes commerciales[/bold cyan]\n\n"
            "  [dim]Phase 3 — à implémenter.[/dim]\n\n"
            "  Affichera les routes optimales triées par profit,\n"
            "  avec filtres système, distance et cargaison.\n",
            id="route-placeholder",
        )
