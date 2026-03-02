"""Éditeur interactif de scan — TUI prompt_toolkit plein-écran.

Lancement : Ctrl+↑ dans le REPL.
    editor = ScanEditor(result, commodities, location_index)
    modified = editor.run()   # None si annulé
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    qty:       str   # chiffres seulement
    price:     str   # chiffres seulement


# ── Éditeur ──────────────────────────────────────────────────────────────────

class ScanEditor:
    """Éditeur TUI plein-écran pour un ScanResult."""

    # Largeurs colonnes : check, nom, stock, qté, prix
    _CW = (3, 26, 12, 6, 9)

    def __init__(
        self,
        result: ScanResult,
        commodities: list | None = None,
        location_index=None,
    ):
        self._source   = result
        self._terminal = result.terminal
        self._mode     = result.mode          # "sell" | "buy"
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

        # Listes pour complétion
        self._commodity_names: list[str] = (
            [c.name for c in commodities] if commodities else []
        )
        self._terminal_names: list[str] = (
            [e.name for e in location_index.search("", limit=9999, types={"terminal"})]
            if location_index else []
        )

        # Cellules : ("h","terminal") ("h","mode")
        #             ("r",i,"check") ("r",i,"name") ("r",i,"stock") ("r",i,"qty") ("r",i,"price") × n
        #             ("f","cancel") ("f","save")
        self._cells: list[tuple] = self._build_cells()

        # Démarrer sur le nom de la première commodité pour aller vite
        self._cursor: int = 3 if self._rows else 0

        # État complétion
        self._completions: list[str] = []
        self._comp_idx: int = -1          # -1 = pas de sélection active (Tab prend le 1er)
        self._draft: str | None = None    # None = pas encore en navigation ; str = texte avant 1er ↓

        self._saved: ScanResult | None = None

        # Initialiser les complétion pour la cellule de départ
        self._refresh_completions()

    # ── Navigation ───────────────────────────────────────────────────────────

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
        self._draft = None
        self._refresh_completions()

    def _is_text_cell(self) -> bool:
        c = self._cell
        return c == ("h", "terminal") or (
            c[0] == "r" and c[2] in ("name", "qty", "price")
        )

    # ── Complétion ────────────────────────────────────────────────────────────

    def _current_text(self) -> str:
        c = self._cell
        if c == ("h", "terminal"):
            return self._terminal
        if c[0] == "r" and c[2] == "name":
            return self._rows[c[1]].name
        return ""

    def _pool(self) -> list[str]:
        c = self._cell
        if c == ("h", "terminal"):
            return self._terminal_names
        if c[0] == "r" and c[2] == "name":
            return self._commodity_names
        return []

    def _refresh_completions(self) -> None:
        q = self._current_text().strip().lower()
        pool = self._pool()
        if not pool:
            self._completions = []
            self._comp_idx = -1
            return
        if not q:
            # Pas de saisie : proposer les 6 premiers
            self._completions = pool[:6]
        else:
            prefix = [n for n in pool if n.lower().startswith(q)]
            substr = [n for n in pool if q in n.lower() and n not in prefix]
            self._completions = (prefix + substr)[:6]
        # Pré-sélectionner le premier (Tab l'accepte directement)
        self._comp_idx = 0 if self._completions else -1

    def _set_current_text(self, val: str) -> None:
        c = self._cell
        if c == ("h", "terminal"):
            self._terminal = val
        elif c[0] == "r" and c[2] == "name":
            self._rows[c[1]].name = val

    def _apply_completion(self) -> None:
        if 0 <= self._comp_idx < len(self._completions):
            self._set_current_text(self._completions[self._comp_idx])

    def _comp_next(self) -> None:
        if not self._completions:
            return
        # Save the draft before first navigation (None = not yet saved)
        if self._draft is None:
            self._draft = self._current_text()
        self._comp_idx = (self._comp_idx + 1) % len(self._completions)
        self._apply_completion()

    def _comp_prev(self) -> None:
        if not self._completions:
            return
        if self._comp_idx <= 0:
            self._comp_idx = -1
            if self._draft is not None:
                self._set_current_text(self._draft)
            self._draft = None
        else:
            self._comp_idx -= 1
            self._apply_completion()

    def _accept_completion(self) -> None:
        """Accepte la complétion courante (ou la première si aucune sélection)."""
        if not self._completions:
            return
        if self._comp_idx < 0:
            self._comp_idx = 0
        self._apply_completion()
        self._completions = []
        self._comp_idx = -1
        self._draft = None

    # ── Édition texte ─────────────────────────────────────────────────────────

    def _type(self, ch: str) -> None:
        # Si une complétion est appliquée, on reprend depuis le draft
        if self._comp_idx >= 0 and self._draft is not None:
            self._set_current_text(self._draft)
            self._draft = None
            self._comp_idx = -1

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
        self._refresh_completions()

    def _backspace(self) -> None:
        if self._comp_idx >= 0 and self._draft is not None:
            self._set_current_text(self._draft)
            self._draft = None
            self._comp_idx = -1
            self._refresh_completions()
            return

        c = self._cell
        if c == ("h", "terminal"):
            self._terminal = self._terminal[:-1]
        elif c[0] == "r":
            row = self._rows[c[1]]
            if c[2] == "name":    row.name  = row.name[:-1]
            elif c[2] == "qty":   row.qty   = row.qty[:-1]
            elif c[2] == "price": row.price = row.price[:-1]
        self._refresh_completions()

    def _clear(self) -> None:
        c = self._cell
        if c == ("h", "terminal"):
            self._terminal = ""
        elif c[0] == "r":
            row = self._rows[c[1]]
            if c[2] == "name":    row.name  = ""
            elif c[2] == "qty":   row.qty   = ""
            elif c[2] == "price": row.price = ""
        self._draft = None
        self._comp_idx = -1
        self._refresh_completions()

    def _toggle(self) -> None:
        c = self._cell
        if c == ("h", "mode"):
            self._mode = "buy" if self._mode == "sell" else "sell"
        elif c[0] == "r" and c[2] == "check":
            self._rows[c[1]].enabled = not self._rows[c[1]].enabled
        elif c[0] == "r" and c[2] == "stock":
            self._rows[c[1]].stock_idx = (self._rows[c[1]].stock_idx + 1) % _N_STOCK

    # ── Sauvegarde ────────────────────────────────────────────────────────────

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

    # ── Rendu ─────────────────────────────────────────────────────────────────

    def _render_comp_bar(self) -> list[tuple[str, str]]:
        """Ligne de complétion à insérer juste sous la cellule active."""
        out: list[tuple[str, str]] = []
        if not self._completions:
            return out
        cw = self._CW
        # Indentation pour aligner sous la colonne Nom (4 chars check + 2 espaces)
        out.append(("class:comp_lbl", "     "))
        for idx, name in enumerate(self._completions):
            if idx == self._comp_idx:
                out.append(("class:comp_sel", f" {name[:cw[1]]} "))
            else:
                out.append(("class:comp", f" {name[:cw[1]]} "))
            out.append(("", " "))
        out.append(("class:comp_hint", "  ↓↑ Tab=ok"))
        out.append(("", "\n"))
        return out

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

        # ── Titre ─────────────────────────────────────────────────────────
        a("", "\n")
        ts = self._source.timestamp.strftime("%H:%M:%S")
        a("class:title", f"  Scan  ·  {self._source.terminal}  ·  {ts}\n")
        hr()

        # ── Terminal + Mode ───────────────────────────────────────────────
        term_is_active = self._cell == ("h", "terminal")
        if term_is_active:
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

        # Complétion terminal juste sous la ligne terminal
        if term_is_active:
            out.extend(self._render_comp_bar())

        hr()

        # ── En-tête colonnes ──────────────────────────────────────────────
        a("class:hdr",
          f"  {'':3}  {'Commodité':<{cw[1]}}  {'Stock':<{cw[2]}}  "
          f"{'Qté':>{cw[3]}}  {'Prix/SCU':>{cw[4]}}\n")
        hr()

        # ── Lignes commodités ─────────────────────────────────────────────
        for i, row in enumerate(self._rows):
            name_active = self._cell == ("r", i, "name")

            if name_active:
                name_val = (row.name[:cw[1] - 1] + "▌").ljust(cw[1])
            else:
                name_val = row.name[:cw[1]].ljust(cw[1])

            qty_raw = (row.qty  + "▌") if self._cell == ("r", i, "qty")   else (row.qty  or "?")
            pri_raw = (row.price+ "▌") if self._cell == ("r", i, "price") else (row.price or "?")

            chk   = "[X]" if row.enabled else "[ ]"
            stlbl = _STOCK[row.stock_idx][0]

            # Grisé si non coché
            row_suf = "" if row.enabled else " class:disabled"

            a("", "  ")
            a(foc(("r", i, "check")),  chk)
            a("", "  ")
            a(foc(("r", i, "name")),   name_val)
            a("", "  ")
            a(foc(("r", i, "stock")),  stlbl.ljust(cw[2]))
            a("", "  ")
            a(foc(("r", i, "qty")),    qty_raw.rjust(cw[3]))
            a("", "  ")
            a(foc(("r", i, "price")),  pri_raw.rjust(cw[4]))
            a("", "\n")

            # Complétion inline sous la ligne du nom actif
            if name_active:
                out.extend(self._render_comp_bar())

        hr()

        # ── Aide ──────────────────────────────────────────────────────────
        a("class:help",
          "  Tab/Entrée: suiv (accepte complétion)  ↓↑: complétion  "
          "←/→/Shift+Tab: nav  Espace: basculer  Ctrl+D: effacer  Échap: annuler\n")
        hr()

        # ── Boutons ───────────────────────────────────────────────────────
        cancel_st = "class:btn_on" if self._cell == ("f", "cancel") else "class:btn"
        save_st   = "class:btn_on" if self._cell == ("f", "save")   else "class:btn"
        a("", "  ")
        a(cancel_st, "  Annuler  ")
        a("", " " * 18)
        a(save_st,   "  MAJ DB  ")
        a("", "\n\n")

        return out

    # ── Lancement ─────────────────────────────────────────────────────────────

    def run(self) -> ScanResult | None:
        from prompt_toolkit import Application
        from prompt_toolkit.layout import Layout, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.styles import Style

        kb = KeyBindings()
        is_text = Condition(lambda: self._is_text_cell())

        @kb.add("tab")
        @kb.add("enter")
        def _tab_enter(event):
            c = self._cell
            if c == ("f", "cancel"):
                event.app.exit()
                return
            if c == ("f", "save"):
                self._save()
                event.app.exit()
                return
            # Champ texte avec complétion → accepte et avance
            if self._is_text_cell() and self._completions:
                self._accept_completion()
            self._move(+1)
            event.app.invalidate()

        @kb.add("s-tab")
        @kb.add("left")
        def _prev(event):
            self._move(-1)
            event.app.invalidate()

        @kb.add("right")
        def _right(event):
            self._move(+1)
            event.app.invalidate()

        @kb.add("down")
        def _comp_down(event):
            if self._is_text_cell() and self._completions:
                self._comp_next()
                event.app.invalidate()

        @kb.add("up")
        def _comp_up(event):
            if self._is_text_cell():
                self._comp_prev()
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
            "title":     "bold cyan",
            "lbl":       "bold",
            "hdr":       "bold",
            "sep":       "dim",
            "help":      "dim italic",
            "focused":   "bg:#3c3c3c bold",
            "btn":       "",
            "btn_on":    "reverse bold",
            "comp_lbl":  "dim",
            "comp":      "dim",
            "comp_sel":  "bg:#005f87 bold",
            "comp_hint": "dim italic",
            "disabled":  "dim",
        })

        Application(
            layout        = layout,
            key_bindings  = kb,
            style         = style,
            full_screen   = True,
            mouse_support = False,
        ).run()

        return self._saved
