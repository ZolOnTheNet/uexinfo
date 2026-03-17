"""StatusBar — barre de statut complète (Phase A).

Layout :
  [ POS: xxx ] [ < ] [ DEST: xxx — z Gm ] [ Trade ] [ V: xxx / n□ ]  ·  [●ScanSC] [●ScanLog]  |  [⚙] [?]
"""
from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from uexinfo.display import colors as C


# ── Messages émis vers l'App ──────────────────────────────────────────────────

class StatusBar(Widget):
    """Barre de statut interactive en bas de l'écran."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        layout: horizontal;
        background: $panel-darken-1;
        border-top: solid $panel-darken-2;
        padding: 0 1;
        align: left middle;
    }
    StatusBar Label {
        height: 1;
        padding: 0 0;
        content-align: left middle;
    }
    StatusBar .sb-sep {
        color: $panel-lighten-1;
        padding: 0 0;
    }
    StatusBar .sb-flag {
        padding: 0 1;
        min-width: 9;
        height: 1;
        border: none;
    }
    StatusBar .sb-flag.active {
        color: yellow;
        text-style: bold;
    }
    StatusBar .sb-flag.inactive {
        color: $text-muted;
    }
    StatusBar .sb-btn {
        height: 1;
        min-width: 3;
        border: none;
        padding: 0 1;
        background: transparent;
    }
    StatusBar .sb-pos {
        color: cyan;
        padding: 0 1;
    }
    StatusBar .sb-dest {
        color: $text;
        padding: 0 1;
    }
    StatusBar .sb-ship {
        color: cyan;
        padding: 0 1;
    }
    """

    # ── Messages ──────────────────────────────────────────────────────────────

    class CommandRequest(Message):
        """Demande d'exécution d'une commande."""
        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    # ── État interne ──────────────────────────────────────────────────────────

    _scan_sc_active: bool = False
    _scan_log_active: bool = False
    _blink_state: bool = False
    _blink_timer = None

    def compose(self) -> ComposeResult:
        yield Label("POS: —", id="sb-pos",   classes="sb-pos")
        yield Label(" < ",    id="sb-arrow",  classes="sb-sep")
        yield Label("DEST: —",id="sb-dest",  classes="sb-dest")
        yield Label("  ",     id="sb-spacer1",classes="sb-sep")
        yield Label("Trade",  id="sb-trade",  classes="sb-btn")
        yield Label("  ",     id="sb-spacer2",classes="sb-sep")
        yield Label("V: —",   id="sb-ship",  classes="sb-ship")
        yield Label("  ·  ",  id="sb-sep1",  classes="sb-sep")
        yield Label("ScanSC", id="sb-scan-sc",  classes="sb-flag inactive")
        yield Label(" ",      id="sb-sep2",  classes="sb-sep")
        yield Label("ScanLog",id="sb-scan-log", classes="sb-flag inactive")
        yield Label("  │  ",  id="sb-sep3",  classes="sb-sep")
        yield Label("⚙",      id="sb-config",classes="sb-btn")
        yield Label(" ",      id="sb-sep4",  classes="sb-sep")
        yield Label("?",      id="sb-help",  classes="sb-btn")

    def on_mount(self) -> None:
        self._blink_timer = self.set_interval(0.8, self._blink_tick)

    def on_click(self, event) -> None:
        widget_id = event.widget.id if hasattr(event.widget, "id") else ""
        if widget_id == "sb-arrow":
            self.post_message(self.CommandRequest("/dest transfer"))
        elif widget_id == "sb-trade":
            self.post_message(self.CommandRequest("/trade best"))
        elif widget_id == "sb-scan-sc" and self._scan_sc_active:
            self._scan_sc_active = False
            self._update_flags()
            self.post_message(self.CommandRequest("/scan"))
        elif widget_id == "sb-scan-log" and self._scan_log_active:
            self._scan_log_active = False
            self._update_flags()
            self.post_message(self.CommandRequest("/scan log"))
        elif widget_id == "sb-config":
            self.post_message(self.CommandRequest("/config"))
        elif widget_id == "sb-help":
            self.post_message(self.CommandRequest("/help"))

    # ── API publique ──────────────────────────────────────────────────────────

    def refresh_status(self, ctx) -> None:
        """Mettre à jour tous les labels depuis le contexte."""
        if ctx is None:
            return

        loc  = ctx.player.location or "—"
        dest = ctx.player.destination or "—"
        ship = ctx.player.active_ship or "—"

        cargo_total = 0
        if ctx.player.active_ship:
            for s in ctx.player.ships:
                if s.name == ctx.player.active_ship:
                    cargo_total = s.scu or 0
                    break

        # Distance destination depuis le graphe de transport
        dist_str = ""
        if ctx.player.location and ctx.player.destination and ctx.player.location != "—":
            try:
                graph = ctx.cache.transport_graph
                path_info = graph.shortest_path(ctx.player.location, ctx.player.destination)
                if path_info and path_info.total_distance:
                    dist_str = f" — {path_info.total_distance:.1f} Gm"
            except Exception:
                pass

        cargo_str = f"{cargo_total} {C.SCU}" if cargo_total else f"— {C.SCU}"

        self.query_one("#sb-pos",   Label).update(f"POS: {loc}")
        self.query_one("#sb-dest",  Label).update(f"DEST: {dest}{dist_str}")
        self.query_one("#sb-ship",  Label).update(f"V: {ship} / {cargo_str}")

        # Griser la flèche < si pas de destination
        arrow = self.query_one("#sb-arrow", Label)
        arrow.update(" ◄ " if ctx.player.destination and ctx.player.destination != "—" else " · ")

    def set_scan_sc(self, active: bool) -> None:
        """Activer/désactiver le flag ScanSC."""
        self._scan_sc_active = active
        self._update_flags()

    def set_scan_log(self, active: bool) -> None:
        """Activer/désactiver le flag ScanLog."""
        self._scan_log_active = active
        self._update_flags()

    # ── Clignotement ─────────────────────────────────────────────────────────

    def _blink_tick(self) -> None:
        self._blink_state = not self._blink_state
        self._update_flags()

    def _update_flags(self) -> None:
        sc_lbl  = self.query_one("#sb-scan-sc",  Label)
        log_lbl = self.query_one("#sb-scan-log", Label)

        # ScanSC
        if self._scan_sc_active:
            sc_lbl.remove_class("inactive")
            sc_lbl.add_class("active")
            sc_lbl.styles.color = "yellow" if self._blink_state else "dark_goldenrod"
            sc_lbl.styles.text_style = "bold" if self._blink_state else "none"
        else:
            sc_lbl.remove_class("active")
            sc_lbl.add_class("inactive")
            sc_lbl.styles.color = None
            sc_lbl.styles.text_style = None

        # ScanLog
        if self._scan_log_active:
            log_lbl.remove_class("inactive")
            log_lbl.add_class("active")
            log_lbl.styles.color = "yellow" if self._blink_state else "dark_goldenrod"
            log_lbl.styles.text_style = "bold" if self._blink_state else "none"
        else:
            log_lbl.remove_class("active")
            log_lbl.add_class("inactive")
            log_lbl.styles.color = None
            log_lbl.styles.text_style = None
