"""Éditeur interactif de scan — TUI prompt_toolkit plein-écran.

Lancement : Ctrl+↑ dans le REPL (main.py), ou programmatiquement via
    editor = ScanEditor(result, commodities)
    modified = editor.run()   # None si annulé
"""
from __future__ import annotations

from dataclasses import dataclass
from uexinfo.models.scan_result import ScannedCommodity, ScanResult

# ── Niveaux de stock ─────────────────────────────────────────────────────────

_STOCK: list[tuple[str, int]] = [
    ("?",         0),
    ("Out",       1),
    ("Very Low",  2),
    ("Low",       3),
    ("Medium",    4),
    ("High",      5),
    ("Very High", 6),
    ("Max",       7),
]
_N_STOCK = len(_STOCK)


def _stock_idx(sc: ScannedCommodity) -> int:
    s = sc.stock_status
    return s if 0 <= s < _N_STOCK else 0


# ── Modèle de ligne éditée ───────────────────────────────────────────────────

@dataclass
class _Row:
    enabled:   bool
    name:      str
    stock_idx: int   # index dans _STOCK
    qty:       str   # chaîne de chiffres
    price:     str   # chaîne de chiffres


# ── Éditeur ──────────────────────────────────────────────────────────────────

class ScanEditor:
    """Éditeur TUI plein-écran pour un ScanResult."""

    # Largeurs de colonnes : check, nom, stock, qté, prix
    _CW = (3, 26, 12, 6, 9)

    def __init__(self, result: ScanResult, commodities: list | None = None):
        self._source     = result
        self._terminal   = result.terminal
        self._mode       = result.mode          # "sell" | "buy"
        self._rows: list[_Row] = [
            _Row(
                enabled   = True,
                name      = sc.name,
                stock_idx = _stock_idx(sc),
                qty       = "" if sc.quantity is None else str(sc.quantity),
                price     = "" if not sc.price else str(sc.price),
            )
            for sc in result.commodities
        ]
        # Future : complétion des noms
        self._known: list[str] = [c.name for c in commodities] if commodities else []

        # Cellules dans l'ordre Tab :
        #  ("h","terminal") ("h","mode")
        #  ("r",i,"check") ("r",i,"name") ("r",i,"stock") ("r",i,"qty") ("r",i,"price")  × n
        #  ("f","cancel") ("f","save")
        self._cells: list[tuple] = self._build_cells()
        self._cursor: int = 0
        self._saved: ScanResult | None = None

    # ── Cellules ─────────────────────────────────────────────────────────────

    def _build_cells(self) -> list[tuple]:
        c: list[tuple] = [("h", "terminal"), ("h", "mode")]
        for i in range(len(self._rows)):
            c += [("r", i, "check"), ("r", i, "name"),
                  ("r", i, "stock"), ("r", i, "qty"), ("r", i, "price")]
        c += [("f", "cancel"), ("f", "save")]
        return c

    @property
    def _cell(self) -> tuple:
        return self._cells[self._cursor]

    def _move(self, delta: int) -> None:
        self._cursor = (self._cursor + delta) % len(self._cells)

    def _is_text_cell(self) -> bool:
        c = self._cell
        return c == ("h", "terminal") or (
            c[0] == "r" and c[2] in ("name", "qty", "price")
        )

    # ── Opérations d'édition ─────────────────────────────────────────────────

    def _type(self, ch: str) -> None:
        c = self._cell
        if c == ("h", "terminal"):
            self._terminal += ch
        elif c[0] == "r":
            row = self._rows[c[1]]
            if c[2] == "name":
                row.name += ch
            elif c[2] == "qty" and ch.isdigit():
                row.qty += ch
            elif c[2] == "price" and ch.isdigit():
                row.price += ch

    def _backspace(self) -> None:
        c = self._cell
        if c == ("h", "terminal"):
            self._terminal = self._terminal[:-1]
        elif c[0] == "r":
            row = self._rows[c[1]]
            if c[2] == "name":   row.name  = row.name[:-1]
            elif c[2] == "qty":  row.qty   = row.qty[:-1]
            elif c[2] == "price":row.price = row.price[:-1]

    def _clear(self) -> None:
        c = self._cell
        if c == ("h", "terminal"):
            self._terminal = ""
        elif c[0] == "r":
            row = self._rows[c[1]]
            if c[2] == "name":   row.name  = ""
            elif c[2] == "qty":  row.qty   = ""
            elif c[2] == "price":row.price = ""

    def _toggle(self) -> None:
        c = self._cell
        if c == ("h", "mode"):
            self._mode = "buy" if self._mode == "sell" else "sell"
        elif c[0] == "r" and c[2] == "check":
            self._rows[c[1]].enabled = not self._rows[c[1]].enabled
        elif c[0] == "r" and c[2] == "stock":
            r = self._rows[c[1]]
            r.stock_idx = (r.stock_idx + 1) % _N_STOCK

    # ── Sauvegarde ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        commodities = []
        for er in self._rows:
            if not er.enabled:
                continue
            label, status = _STOCK[er.stock_idx]
            commodities.append(ScannedCommodity(
                name         = er.name.strip(),
                stock        = label,
                stock_status = status,
                quantity     = int(er.qty)   if er.qty.strip().isdigit()   else None,
                price        = int(er.price) if er.price.strip().isdigit() else 0,
            ))
        self._saved = ScanResult(
            terminal    = self._terminal.strip() or self._source.terminal,
            commodities = commodities,
            source      = self._source.source,
            mode        = self._mode,
            timestamp   = self._source.timestamp,
        )

    # ── Rendu ────────────────────────────────────────────────────────────────

    def _render(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        W = 72
        cw = self._CW

        def a(st: str, tx: str) -> None:
            out.append((st, tx))

        def hr() -> None:
            a("class:sep", "  " + "─" * (W - 4) + "\n")

        def foc(cell: tuple) -> str:
            return "class:focused" if self._cell == cell else ""

        # Titre
        a("", "\n")
        ts = self._source.timestamp.strftime("%H:%M:%S")
        a("class:title", f"  Éditeur de scan  ·  {self._source.terminal}  ·  {ts}\n")
        hr()

        # Terminal + Mode
        if self._cell == ("h", "terminal"):
            term_disp = (self._terminal[:cw[1] - 1] + "▌").ljust(cw[1])
        else:
            term_disp = self._terminal[:cw[1]].ljust(cw[1])
        mode_str = " VENTE " if self._mode == "sell" else " ACHAT "
        a("class:lbl", "  Terminal : ")
        a(foc(("h", "terminal")), f" {term_disp} ")
        a("", "   ")
        a("class:lbl", "Mode : ")
        a(foc(("h", "mode")), f"[{mode_str}]")
        a("", "\n")
        hr()

        # En-tête
        a("class:hdr",
          f"  {'':3}  {'Commodité':<{cw[1]}}  {'Stock':<{cw[2]}}  "
          f"{'Qté':>{cw[3]}}  {'Prix/SCU':>{cw[4]}}\n")
        hr()

        # Lignes
        for i, row in enumerate(self._rows):
            # Nom
            if self._cell == ("r", i, "name"):
                name_val = (row.name[:cw[1] - 1] + "▌").ljust(cw[1])
            else:
                name_val = row.name[:cw[1]].ljust(cw[1])
            # Qté
            if self._cell == ("r", i, "qty"):
                qty_raw = (row.qty + "▌") if row.qty else "▌"
            else:
                qty_raw = row.qty if row.qty else "?"
            # Prix
            if self._cell == ("r", i, "price"):
                pri_raw = (row.price + "▌") if row.price else "▌"
            else:
                pri_raw = row.price if row.price else "?"

            chk   = "[X]" if row.enabled else "[ ]"
            stlbl = _STOCK[row.stock_idx][0]

            a("", "  ")
            a(foc(("r", i, "check")), chk)
            a("", "  ")
            a(foc(("r", i, "name")),  name_val)
            a("", "  ")
            a(foc(("r", i, "stock")), stlbl.ljust(cw[2]))
            a("", "  ")
            a(foc(("r", i, "qty")),   qty_raw.rjust(cw[3]))
            a("", "  ")
            a(foc(("r", i, "price")), pri_raw.rjust(cw[4]))
            a("", "\n")

        hr()

        # Aide
        a("class:help",
          "  Tab/→/Entrée: suiv  ←/Shift+Tab: préc  "
          "Espace: basculer  Ctrl+D: effacer  Échap: annuler\n")
        hr()

        # Boutons
        cancel_st = "class:btn_on" if self._cell == ("f", "cancel") else "class:btn"
        save_st   = "class:btn_on" if self._cell == ("f", "save")   else "class:btn"
        pad = " " * 18
        a("", "  ")
        a(cancel_st, "  Annuler  ")
        a("", pad)
        a(save_st,   "  MAJ DB  ")
        a("", "\n\n")

        return out

    # ── Lancement ────────────────────────────────────────────────────────────

    def run(self) -> ScanResult | None:
        """Lance l'éditeur. Retourne le ScanResult corrigé ou None si annulé."""
        from prompt_toolkit import Application
        from prompt_toolkit.layout import Layout, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.styles import Style

        kb = KeyBindings()
        is_text = Condition(lambda: self._is_text_cell())

        @kb.add("tab")
        @kb.add("right")
        def _next(event):
            self._move(+1)
            event.app.invalidate()

        @kb.add("s-tab")
        @kb.add("left")
        def _prev(event):
            self._move(-1)
            event.app.invalidate()

        @kb.add("enter")
        def _enter(event):
            c = self._cell
            if c == ("f", "cancel"):
                event.app.exit()
            elif c == ("f", "save"):
                self._save()
                event.app.exit()
            else:
                self._move(+1)
            event.app.invalidate()

        @kb.add("space")
        def _space(event):
            self._toggle()
            event.app.invalidate()

        @kb.add("escape")
        @kb.add("c-c")
        def _cancel(event):
            event.app.exit()

        @kb.add("c-d")
        def _del(event):
            self._clear()
            event.app.invalidate()

        @kb.add("<any>", filter=is_text)
        def _char(event):
            for kp in event.key_sequence:
                k = kp.key
                if len(k) == 1 and k.isprintable():
                    self._type(k)
            event.app.invalidate()

        @kb.add("backspace")
        def _bs(event):
            self._backspace()
            event.app.invalidate()

        control = FormattedTextControl(
            self._render, focusable=True, show_cursor=False,
        )
        layout = Layout(Window(content=control, wrap_lines=False))

        style = Style.from_dict({
            "title":   "bold cyan",
            "lbl":     "bold",
            "hdr":     "bold",
            "sep":     "dim",
            "help":    "dim italic",
            "focused": "bg:#3c3c3c bold",
            "btn":     "",
            "btn_on":  "reverse bold",
        })

        Application(
            layout       = layout,
            key_bindings = kb,
            style        = style,
            full_screen  = True,
            mouse_support= False,
        ).run()

        return self._saved
