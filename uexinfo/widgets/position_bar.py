"""Widget PositionBar — position courante + vaisseau actif."""
from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Label, Select, Static

from uexinfo.display import colors as C

if TYPE_CHECKING:
    from uexinfo.app import UexInfoApp


class PositionBar(Static):
    """Barre horizontale dockée en haut : position courante + vaisseau sélectionné."""

    class PositionChanged(Message):
        def __init__(self, terminal: str) -> None:
            self.terminal = terminal
            super().__init__()

    class ShipChanged(Message):
        def __init__(self, ship_name: str, scu: int) -> None:
            self.ship_name = ship_name
            self.scu = scu
            super().__init__()

    def compose(self):
        with Horizontal(id="pos-bar-inner"):
            yield Label("Pos : ", classes="bar-label")
            yield Select(
                options=[],
                prompt="Sélectionner un terminal...",
                id="position-select",
                allow_blank=True,
            )
            yield Label("  Vaisseau : ", classes="bar-label")
            yield Select(
                options=[],
                prompt="Sélectionner un vaisseau...",
                id="ship-select",
                allow_blank=True,
            )
            yield Label("", id="cargo-label")

    def on_context_ready(self) -> None:
        """Appelé par app.py une fois le contexte initialisé."""
        self._populate_terminals()
        self._populate_ships()

    def sync_from_context(self) -> None:
        """Resynchronise les Select depuis ctx.player (après @location ou /player)."""
        app: UexInfoApp = self.app  # type: ignore[assignment]
        ctx = app.ctx
        if ctx is None:
            return
        loc = ctx.player.location or ""
        if loc:
            sel = self.query_one("#position-select", Select)
            # Ajouter au Select si absent (lieu hors cache comme Pyro)
            current_values = {v for _, v in sel._options} if hasattr(sel, "_options") else set()
            if loc not in current_values:
                try:
                    opts = list(sel._options) + [(loc, loc)]
                    sel.set_options(opts)
                except Exception:
                    pass
            try:
                sel.value = loc
            except Exception:
                pass
        ship = ctx.player.active_ship or ""
        if ship:
            sel = self.query_one("#ship-select", Select)
            try:
                sel.value = ship
                self._update_cargo_label(ship)
            except Exception:
                pass

    def _populate_terminals(self) -> None:
        app: UexInfoApp = self.app  # type: ignore[assignment]
        ctx = app.ctx
        if ctx is None:
            return

        terminals = sorted(ctx.cache.terminals, key=lambda t: t.name)
        options = [(t.name, t.name) for t in terminals]

        current = ctx.player.location or ""
        # Ajouter le lieu courant s'il n'est pas dans le cache (ex: Pyro)
        if current and current not in {v for _, v in options}:
            options.insert(0, (current, current))

        sel = self.query_one("#position-select", Select)
        sel.set_options(options)

        if current:
            try:
                sel.value = current
            except Exception:
                pass

    def _populate_ships(self) -> None:
        app: UexInfoApp = self.app  # type: ignore[assignment]
        ctx = app.ctx
        if ctx is None:
            return

        ships = ctx.player.ships
        if not ships:
            return

        options = [
            (f"{s.name} ({s.scu} SCU)" if s.scu else s.name, s.name)
            for s in ships
        ]
        sel = self.query_one("#ship-select", Select)
        sel.set_options(options)

        active = ctx.player.active_ship
        if active:
            try:
                sel.value = active
                self._update_cargo_label(active)
            except Exception:
                pass

    def _update_cargo_label(self, ship_name: str) -> None:
        app: UexInfoApp = self.app  # type: ignore[assignment]
        ctx = app.ctx
        if ctx is None:
            return
        ship = next((s for s in ctx.player.ships if s.name == ship_name), None)
        label = self.query_one("#cargo-label", Label)
        if ship and ship.scu:
            label.update(f"  {ship.scu} {C.SCU}")
        else:
            label.update(f"  — {C.SCU}")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return

        if event.select.id == "position-select":
            terminal = str(event.value)
            app: UexInfoApp = self.app  # type: ignore[assignment]
            if app.ctx:
                app.ctx.player.location = terminal
            self.post_message(self.PositionChanged(terminal))

        elif event.select.id == "ship-select":
            ship_name = str(event.value)
            self._update_cargo_label(ship_name)
            app: UexInfoApp = self.app  # type: ignore[assignment]
            if app.ctx:
                app.ctx.player.active_ship = ship_name
                ship = next(
                    (s for s in app.ctx.player.ships if s.name == ship_name), None
                )
                scu = ship.scu if ship else 0
                self.post_message(self.ShipChanged(ship_name, scu))
