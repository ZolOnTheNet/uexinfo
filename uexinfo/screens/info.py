"""Écran Info — terminal / commodité / vaisseau (Phase 4)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


class InfoScreen(Static):
    """Écran de consultation des données terminal et commodité."""

    def compose(self) -> ComposeResult:
        yield Static(
            "\n"
            "  [bold cyan]Info terminal / commodité[/bold cyan]\n\n"
            "  [dim]Phase 4 — à implémenter.[/dim]\n\n"
            "  Permettra de chercher un terminal ou une commodité\n"
            "  et d'afficher les données détaillées (prix, stock,\n"
            "  localisation, scan personnel).\n\n"
            "  [dim]En attendant, utilisez [bold]uexinfo-cli[/bold] (REPL Rich).[/dim]\n",
            id="info-placeholder",
        )
