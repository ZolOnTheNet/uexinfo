"""Éditeur interactif de missions — TUI prompt_toolkit plein-écran.

Usage :
    editor = MissionEditor(missions, location_names)
    saved_ids = editor.run(mm)   # liste des IDs modifiés (vide si annulé)
"""
from __future__ import annotations

from dataclasses import dataclass
from uexinfo.models.mission import Mission, MissionObjective


@dataclass
class _MRow:
    """État éditable d'une mission."""
    mission: Mission
    name:    str
    reward:  str
    scu:     str
    sources: list[str]
    dests:   list[str]
    saved:   bool = False


class MissionEditor:
    """Éditeur TUI plein-écran pour une liste de missions."""

    W = 82

    def __init__(
        self,
        missions: list[Mission],
        location_names: list[str] | None = None,
    ):
        self._rows: list[_MRow] = [
            _MRow(
                mission = m,
                name    = m.name or "",
                reward  = str(m.reward_uec) if m.reward_uec else "",
                scu     = str(int(m.total_scu)) if m.total_scu else "",
                sources = list(m.all_sources),
                dests   = list(m.all_destinations),
            )
            for m in missions
        ]
        self._loc_pool: list[str] = location_names or []
        self._cells: list[tuple] = self._build_cells()
        self._cursor: int = 0
        self._completions: list[str] = []
        self._comp_idx: int = -1
        self._draft: str | None = None
        self._result: list[int] = []
        self._refresh_completions()

    # ── Cellules ──────────────────────────────────────────────────────────────

    def _build_cells(self) -> list[tuple]:
        c: list[tuple] = []
        for i, row in enumerate(self._rows):
            c.append(("m", i, "name"))
            c.append(("m", i, "reward"))
            c.append(("m", i, "scu"))
            for j in range(len(row.sources)):
                c.append(("m", i, "src", j))
                c.append(("m", i, "src_del", j))
            c.append(("m", i, "src_add"))
            for j in range(len(row.dests)):
                c.append(("m", i, "dst", j))
                c.append(("m", i, "dst_del", j))
            c.append(("m", i, "dst_add"))
            c.append(("m", i, "save"))
        c += [("f", "cancel"), ("f", "save_all")]
        return c

    # ── Navigation ────────────────────────────────────────────────────────────

    @property
    def _cell(self) -> tuple:
        return self._cells[self._cursor]

    def _move(self, delta: int) -> None:
        if self._cells:
            self._cursor = (self._cursor + delta) % len(self._cells)
        self._draft = None
        self._refresh_completions()

    def _goto(self, target: tuple) -> None:
        try:
            self._cursor = self._cells.index(target)
        except ValueError:
            self._move(0)
        self._draft = None
        self._refresh_completions()

    def _is_text_cell(self) -> bool:
        c = self._cell
        return c[0] == "m" and c[2] in ("name", "reward", "scu", "src", "dst")

    def _is_loc_cell(self) -> bool:
        c = self._cell
        return c[0] == "m" and c[2] in ("src", "dst")

    # ── Complétion ────────────────────────────────────────────────────────────

    def _current_text(self) -> str:
        c = self._cell
        if c[0] != "m":
            return ""
        row = self._rows[c[1]]
        kind = c[2]
        if kind == "name":   return row.name
        if kind == "reward": return row.reward
        if kind == "scu":    return row.scu
        if kind == "src":    return row.sources[c[3]] if c[3] < len(row.sources) else ""
        if kind == "dst":    return row.dests[c[3]]   if c[3] < len(row.dests)   else ""
        return ""

    def _set_text(self, val: str) -> None:
        c = self._cell
        if c[0] != "m":
            return
        row = self._rows[c[1]]
        kind = c[2]
        if kind == "name":   row.name = val
        elif kind == "reward": row.reward = val
        elif kind == "scu":    row.scu = val
        elif kind == "src" and c[3] < len(row.sources): row.sources[c[3]] = val
        elif kind == "dst" and c[3] < len(row.dests):   row.dests[c[3]]   = val

    def _refresh_completions(self) -> None:
        if not self._is_loc_cell():
            self._completions = []
            self._comp_idx = -1
            return
        q = self._current_text().strip().lower()
        pool = self._loc_pool
        if not q:
            self._completions = pool[:6]
        else:
            pref = [n for n in pool if n.lower().startswith(q)]
            sub  = [n for n in pool if q in n.lower() and n not in pref]
            self._completions = (pref + sub)[:6]
        self._comp_idx = 0 if self._completions else -1

    def _comp_next(self) -> None:
        if not self._completions:
            return
        if self._draft is None:
            self._draft = self._current_text()
        self._comp_idx = (self._comp_idx + 1) % len(self._completions)
        self._set_text(self._completions[self._comp_idx])

    def _comp_prev(self) -> None:
        if not self._completions:
            return
        if self._comp_idx <= 0:
            self._comp_idx = -1
            if self._draft is not None:
                self._set_text(self._draft)
            self._draft = None
        else:
            self._comp_idx -= 1
            self._set_text(self._completions[self._comp_idx])

    def _accept_comp(self) -> None:
        if not self._completions:
            return
        if self._comp_idx < 0:
            self._comp_idx = 0
        self._set_text(self._completions[self._comp_idx])
        self._completions = []
        self._comp_idx = -1
        self._draft = None

    # ── Édition ───────────────────────────────────────────────────────────────

    def _type(self, ch: str) -> None:
        c = self._cell
        if c[0] != "m":
            return
        if self._comp_idx >= 0 and self._draft is not None:
            self._set_text(self._draft)
            self._draft = None
            self._comp_idx = -1
        kind = c[2]
        if kind in ("reward", "scu") and not (ch.isdigit() or ch in ",."):
            return
        self._set_text(self._current_text() + ch)
        self._refresh_completions()

    def _backspace(self) -> None:
        if self._comp_idx >= 0 and self._draft is not None:
            self._set_text(self._draft)
            self._draft = None
            self._comp_idx = -1
            self._refresh_completions()
            return
        self._set_text(self._current_text()[:-1])
        self._refresh_completions()

    def _clear(self) -> None:
        self._set_text("")
        self._draft = None
        self._comp_idx = -1
        self._refresh_completions()

    # ── Actions boutons ───────────────────────────────────────────────────────

    def _add_source(self, mi: int) -> None:
        self._rows[mi].sources.append("")
        self._cells = self._build_cells()
        self._goto(("m", mi, "src", len(self._rows[mi].sources) - 1))

    def _del_source(self, mi: int, j: int) -> None:
        row = self._rows[mi]
        if j < len(row.sources):
            row.sources.pop(j)
        self._cells = self._build_cells()
        self._goto(("m", mi, "src_add"))

    def _add_dest(self, mi: int) -> None:
        self._rows[mi].dests.append("")
        self._cells = self._build_cells()
        self._goto(("m", mi, "dst", len(self._rows[mi].dests) - 1))

    def _del_dest(self, mi: int, j: int) -> None:
        row = self._rows[mi]
        if j < len(row.dests):
            row.dests.pop(j)
        self._cells = self._build_cells()
        self._goto(("m", mi, "dst_add"))

    def _save_row(self, mi: int, mm) -> None:
        row  = self._rows[mi]
        m    = row.mission

        # Nom
        if row.name.strip():
            m.name = row.name.strip()

        # Récompense
        try:
            raw = row.reward.strip().replace(",", "").replace(" ", "")
            if raw:
                m.reward_uec = int(raw)
        except ValueError:
            pass

        # SCU total
        total_scu: float | None = None
        try:
            if row.scu.strip():
                total_scu = float(row.scu.replace(",", "."))
        except ValueError:
            pass

        # Reconstruire les objectifs
        srcs = [s.strip() for s in row.sources if s.strip()]
        dsts = [d.strip() for d in row.dests   if d.strip()]

        if srcs or dsts:
            # Préserver la commodité existante si possible
            existing_commodity = next(
                (o.commodity for o in m.objectives if o.commodity), None
            )
            n = max(len(srcs), len(dsts), 1)
            objs: list[MissionObjective] = []
            for k in range(n):
                src = srcs[k] if k < len(srcs) else None
                dst = dsts[k] if k < len(dsts) else None
                qty = total_scu if k == 0 else None
                objs.append(MissionObjective(
                    commodity    = existing_commodity,
                    source       = src,
                    destination  = dst,
                    quantity_scu = qty,
                ))
            m.objectives = objs
        elif total_scu is not None and m.objectives:
            m.objectives[0].quantity_scu = total_scu

        mm.update(m)
        row.saved = True
        if m.id not in self._result:
            self._result.append(m.id)

    def _save_all(self, mm) -> None:
        for i in range(len(self._rows)):
            self._save_row(i, mm)

    # ── Rendu ─────────────────────────────────────────────────────────────────

    def _comp_bar(self, indent: int = 16) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not self._completions:
            return out
        out.append(("class:comp_lbl", " " * indent))
        for idx, name in enumerate(self._completions):
            st = "class:comp_sel" if idx == self._comp_idx else "class:comp"
            out.append((st, f" {name[:28]} "))
        out.append(("class:comp_hint", "  ↓↑ Tab=ok"))
        out.append(("", "\n"))
        return out

    def _render(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        W = self.W

        def a(st: str, tx: str) -> None:
            out.append((st, tx))

        def hr() -> None:
            a("class:sep", "  " + "─" * (W - 4) + "\n")

        def foc(cell: tuple) -> str:
            return "class:focused" if self._cell == cell else ""

        def field(cell: tuple, val: str, w: int) -> None:
            active = self._cell == cell
            disp   = ((val[:w - 1] + "▌") if active else val[:w]).ljust(w)
            a(foc(cell), f" {disp} ")

        a("", "\n")
        a("class:title", f"  ✎ Éditeur de missions  ·  {len(self._rows)} mission(s)\n")
        hr()

        for i, row in enumerate(self._rows):
            m = row.mission
            # En-tête mission
            mark = "  [✓]" if row.saved else ""
            a("class:m_hdr", f"  #{m.id}  {row.name[:52]}{mark}\n")

            # Nom
            a("class:lbl", "  Nom       : ")
            field(("m", i, "name"), row.name, 52)
            a("", "\n")

            # Récompense + SCU
            a("class:lbl", "  Récompense: ")
            field(("m", i, "reward"), row.reward, 14)
            a("class:dim", " aUEC")
            a("class:lbl", "    SCU: ")
            field(("m", i, "scu"), row.scu, 8)
            a("", "\n")

            # Sources
            a("", "\n")
            if row.sources:
                for j, src in enumerate(row.sources):
                    a("class:lbl", f"  Départ {j+1:<2} : ")
                    field(("m", i, "src", j), src, 42)
                    a("", " ")
                    a(foc(("m", i, "src_del", j)), " × ")
                    a("", "\n")
                    if self._cell == ("m", i, "src", j):
                        out.extend(self._comp_bar(16))
            else:
                a("class:dim",  "  (aucun départ)\n")
            a("", "  ")
            a(foc(("m", i, "src_add")), " + Départ ")
            a("", "\n")

            # Destinations
            if row.dests:
                for j, dst in enumerate(row.dests):
                    a("class:lbl", f"  Arrivée {j+1:<2}: ")
                    field(("m", i, "dst", j), dst, 42)
                    a("", " ")
                    a(foc(("m", i, "dst_del", j)), " × ")
                    a("", "\n")
                    if self._cell == ("m", i, "dst", j):
                        out.extend(self._comp_bar(16))
            else:
                a("class:dim", "  (aucune arrivée)\n")
            a("", "  ")
            a(foc(("m", i, "dst_add")), " + Arrivée ")
            a("", "\n\n")

            # Bouton valider
            pad = max(0, W - 24)
            a("", " " * pad)
            a(foc(("m", i, "save")), f"  ✓ Valider #{m.id}  ")
            a("", "\n")

            hr()

        # Aide
        a("class:help",
          "  Tab/Entrée: suivant · Shift+Tab/←: précédent · ↓↑: complétion"
          " · Ctrl+D: effacer · Échap: annuler\n")
        hr()

        # Boutons globaux
        cancel_st = "class:btn_on" if self._cell == ("f", "cancel")   else "class:btn"
        saveal_st = "class:btn_on" if self._cell == ("f", "save_all") else "class:btn"
        a("", "  ")
        a(cancel_st, "  Annuler  ")
        a("", " " * max(0, W - 36))
        a(saveal_st, "  Sauvegarder tout  ")
        a("", "\n\n")

        return out

    # ── Lancement ─────────────────────────────────────────────────────────────

    def run(self, mm) -> list[int]:
        """Lance l'éditeur. Retourne les IDs des missions modifiées."""
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
        def _next(event):
            c = self._cell
            if c == ("f", "cancel"):
                event.app.exit(); return
            if c == ("f", "save_all"):
                self._save_all(mm)
                event.app.exit(); return
            if c[0] == "m":
                kind = c[2]
                mi   = c[1]
                if kind == "save":
                    self._save_row(mi, mm)
                    self._move(+1)
                    event.app.invalidate(); return
                if kind == "src_add":
                    self._add_source(mi)
                    event.app.invalidate(); return
                if kind == "dst_add":
                    self._add_dest(mi)
                    event.app.invalidate(); return
                if kind == "src_del":
                    self._del_source(mi, c[3])
                    event.app.invalidate(); return
                if kind == "dst_del":
                    self._del_dest(mi, c[3])
                    event.app.invalidate(); return
            if self._is_text_cell() and self._completions:
                self._accept_comp()
            self._move(+1)
            event.app.invalidate()

        @kb.add("s-tab")
        @kb.add("left")
        def _prev(event):
            self._move(-1)
            event.app.invalidate()

        @kb.add("right")
        def _right(event):
            c = self._cell
            if c[0] == "m" and c[2] not in ("name", "src", "dst"):
                self._move(+1)
            else:
                self._move(+1)
            event.app.invalidate()

        @kb.add("down")
        def _dn(event):
            if self._is_loc_cell() and self._completions:
                self._comp_next()
            else:
                self._move(+1)
            event.app.invalidate()

        @kb.add("up")
        def _up(event):
            if self._is_loc_cell() and self._completions:
                self._comp_prev()
            else:
                self._move(-1)
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
            "title":    "bold cyan",
            "m_hdr":    "bold yellow",
            "lbl":      "bold",
            "dim":      "dim",
            "sep":      "dim",
            "help":     "dim italic",
            "focused":  "bg:#3c3c3c bold",
            "btn":      "",
            "btn_on":   "reverse bold",
            "comp_lbl": "dim",
            "comp":     "dim",
            "comp_sel": "bg:#005f87 bold",
            "comp_hint":"dim italic",
        })

        Application(
            layout        = layout,
            key_bindings  = kb,
            style         = style,
            full_screen   = True,
            mouse_support = False,
        ).run()

        return self._result
