"""Écran Trade — achat/vente de commodités (Phase 2)."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Label, RadioButton, RadioSet, Static

if TYPE_CHECKING:
    from uexinfo.app import UexInfoApp

from uexinfo.cli.commands.info import (
    _commodity_prices,
    _find_commodity,
)
from uexinfo.cli.commands.trade import _is_active_buy, _is_active_sell


def _fmt_price(value) -> str:
    if not value:
        return "—"
    return f"{int(value):,}".replace(",", " ")


def _fmt_age(date_modified) -> str:
    if not date_modified:
        return "?"
    age_h = (time.time() - date_modified) / 3600
    if age_h < 1:
        return f"{int(age_h * 60)}m"
    if age_h < 24:
        return f"{age_h:.0f}h"
    return f"{age_h / 24:.0f}j"


class TradeScreen(Static):
    """Écran principal de trading : recherche commodité + buy/sell."""

    _mode: reactive[str] = reactive("both")
    _current_rows: list[dict]
    _commodity_name: str

    def __init__(self) -> None:
        super().__init__()
        self._current_rows = []
        self._commodity_name = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="trade-outer"):
            with Horizontal(id="trade-controls"):
                yield Input(
                    placeholder="Commodité (ex: Laranite, Gold, Titanium)...",
                    id="commodity-input",
                )
                with RadioSet(id="trade-mode"):
                    yield RadioButton("Achat + Vente", value=True, id="mode-both")
                    yield RadioButton("Achat", id="mode-buy")
                    yield RadioButton("Vente", id="mode-sell")
            with Horizontal(id="trade-content"):
                yield DataTable(id="trade-table", cursor_type="row", zebra_stripes=True)
                with Vertical(id="trade-detail"):
                    yield Label("── Détail ──", id="detail-title")
                    yield Static(
                        "Sélectionnez une commodité dans le champ de recherche,\n"
                        "puis cliquez sur un terminal pour voir le détail.",
                        id="detail-body",
                    )
        yield Label("", id="trade-status")

    def on_mount(self) -> None:
        table = self.query_one("#trade-table", DataTable)
        table.add_columns(
            "Terminal",
            "Système",
            "Achat/SCU",
            "Vente/SCU",
            "SCU dispo",
            "Fraîcheur",
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "commodity-input":
            return
        query = event.value.strip().replace("_", " ")
        if len(query) >= 2:
            self._load_commodity(query)
        else:
            self._clear_table()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "trade-mode":
            self._mode = ["both", "buy", "sell"][event.index]
            self._refresh_table()

    @work(thread=True, exclusive=True)
    def _load_commodity(self, query: str) -> None:
        """Chargement des prix en thread (UEXClient est synchrone)."""
        app: UexInfoApp = self.app  # type: ignore[assignment]
        if app.ctx is None:
            return

        c = _find_commodity(query, app.ctx)
        if c is None:
            self.call_from_thread(self._set_status, f"Aucune commodité pour « {query} »")
            self.call_from_thread(self._clear_table)
            return

        self.call_from_thread(self._set_status, f"Chargement des prix pour {c.name}…")
        rows = _commodity_prices(c.id, app.ctx)
        self.call_from_thread(self._update_table, c.name, rows)

    def _set_status(self, msg: str) -> None:
        self.query_one("#trade-status", Label).update(msg)

    def _update_table(self, commodity_name: str, rows: list[dict]) -> None:
        self._commodity_name = commodity_name
        self._current_rows = rows
        self._refresh_table()
        self.query_one("#detail-title", Label).update(
            f"── {commodity_name} ── {len(rows)} terminaux"
        )
        self._set_status("")

    def _refresh_table(self) -> None:
        table = self.query_one("#trade-table", DataTable)
        table.clear()

        mode = self._mode
        rows = list(self._current_rows)

        if mode == "buy":
            rows = [r for r in rows if _is_active_buy(r)]
            rows.sort(key=lambda r: r.get("price_buy") or 0)
        elif mode == "sell":
            rows = [r for r in rows if _is_active_sell(r)]
            rows.sort(key=lambda r: -(r.get("price_sell") or 0))
        else:
            rows = [r for r in rows if _is_active_buy(r) or _is_active_sell(r)]
            rows.sort(key=lambda r: r.get("terminal_name") or "")

        for r in rows[:80]:
            buy_p = r.get("price_buy") or 0
            sell_p = r.get("price_sell") or 0
            scu_buy = r.get("scu_buy") or 0
            scu_sell = r.get("scu_sell") or 0
            # Stock disponible selon le mode affiché
            scu_str = (
                f"{scu_buy}" if (mode == "buy" and scu_buy)
                else f"{scu_sell}" if (mode == "sell" and scu_sell)
                else f"↓{scu_buy} ↑{scu_sell}" if (scu_buy or scu_sell)
                else "—"
            )

            table.add_row(
                r.get("terminal_name") or "?",
                r.get("star_system_name") or "?",
                _fmt_price(buy_p),
                _fmt_price(sell_p),
                scu_str,
                _fmt_age(r.get("date_modified")),
                key=str(r.get("id_terminal") or id(r)),
            )

    def _clear_table(self) -> None:
        self.query_one("#trade-table", DataTable).clear()
        self._current_rows = []
        self._commodity_name = ""
        self.query_one("#detail-title", Label).update("── Détail ──")
        self.query_one("#detail-body", Static).update(
            "Saisissez au moins 2 caractères pour rechercher une commodité."
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Afficher le détail d'une ligne sélectionnée."""
        row_key = event.row_key.value if event.row_key else None
        if row_key is None:
            return

        row_data = next(
            (r for r in self._current_rows if str(r.get("id_terminal") or id(r)) == row_key),
            None,
        )
        if row_data is None:
            return

        self._show_detail(row_data)

    def _show_detail(self, r: dict) -> None:
        terminal = r.get("terminal_name") or "?"
        system = r.get("star_system_name") or "?"
        buy = r.get("price_buy") or 0
        sell = r.get("price_sell") or 0
        scu_buy = r.get("scu_buy") or 0
        scu_sell = r.get("scu_sell") or 0
        date_mod = r.get("date_modified")

        lines: list[str] = [
            f"[bold]{terminal}[/bold]",
            f"[dim]{system}[/dim]",
            "",
        ]

        if buy:
            lines.append(f"Achat  :  [cyan]{_fmt_price(buy)} aUEC/SCU[/cyan]")
            if scu_buy:
                lines.append(f"Stock  :  {scu_buy} SCU")
        else:
            lines.append("Achat  :  [dim]—[/dim]")

        if sell:
            lines.append(f"Vente  :  [green]{_fmt_price(sell)} aUEC/SCU[/green]")
            if scu_sell:
                lines.append(f"Demande:  {scu_sell} SCU")
        else:
            lines.append("Vente  :  [dim]—[/dim]")

        if buy and sell:
            margin = sell - buy
            color = "green" if margin > 0 else "red"
            lines += [
                "",
                f"Marge  :  [{color}]{margin:+,} aUEC/SCU[/{color}]",
            ]

            # Profit total selon vaisseau actif
            app: UexInfoApp = self.app  # type: ignore[assignment]
            if app.ctx and app.ctx.player.active_ship:
                ship = next(
                    (s for s in app.ctx.player.ships if s.name == app.ctx.player.active_ship),
                    None,
                )
                if ship and ship.scu:
                    profit = margin * ship.scu
                    color = "green" if profit > 0 else "red"
                    lines.append(
                        f"Profit ({ship.scu} SCU) : [{color}]{profit:+,} aUEC[/{color}]"
                    )

        if date_mod:
            lines += ["", f"[dim]màj : {_fmt_age(date_mod)}[/dim]"]

        self.query_one("#detail-body", Static).update("\n".join(lines))
