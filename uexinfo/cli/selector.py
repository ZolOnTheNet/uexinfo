"""Sélecteur interactif générique — TUI prompt_toolkit.

Usage ::

    from uexinfo.cli.selector import ListSelector, SelectItem

    items = [SelectItem(label="foo.jpg", value=path, meta="12 Ko")]
    sel = ListSelector(items, title="Choisir un screenshot", mode="multi")
    chosen = sel.run()   # list[SelectItem] ou None si annulé

Modes
-----
``multi``  : checkboxes + [Tous] [Aucun] + [Annuler] [Valider]
             Retourne la liste des éléments cochés (peut être vide).

``single`` : curseur ▶ + Entrée pour confirmer
             Retourne une liste à un élément.

Touches
-------
↑ / ↓  — déplacer le curseur
Espace  — cocher/décocher (mode multi)
Entrée  — valider (si focus sur item en mode single, ou sur bouton Valider)
a / F2  — [Tous] (mode multi)
n / F3  — [Aucun] (mode multi)
Tab     — passer aux boutons
Échap   — annuler
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style


# ── Modèle ────────────────────────────────────────────────────────────────────

@dataclass
class SelectItem:
    """Un élément de la liste.

    label    — texte affiché (colonne principale)
    value    — valeur retournée (Path, str, objet…)
    meta     — info secondaire facultative (date, taille, id…)
    selected — état initial de la case à cocher
    """
    label:    str
    value:    Any
    meta:     str  = ""
    selected: bool = False


# ── Sélecteur ─────────────────────────────────────────────────────────────────

_STYLE = Style.from_dict({
    "title":      "bold cyan",
    "item":       "",
    "item.focus": "bg:#2a4a6a bold",
    "check.on":   "bold green",
    "check.off":  "",
    "meta":       "dim",
    "bar":        "bg:#1a1a1a",
    "btn":        "bg:#333333",
    "btn.focus":  "bg:#0055aa bold",
    "hint":       "dim",
    "separator":  "dim",
})

_BTN_CANCEL = "annuler"
_BTN_ALL    = "tous"
_BTN_NONE   = "aucun"
_BTN_OK     = "valider"


class ListSelector:
    """Sélecteur TUI générique basé sur prompt_toolkit."""

    def __init__(
        self,
        items:  list[SelectItem],
        title:  str = "",
        mode:   str = "multi",     # "multi" | "single"
        height: int | None = None, # hauteur max visible (None = auto)
    ) -> None:
        if mode not in ("multi", "single"):
            raise ValueError("mode doit être 'multi' ou 'single'")

        self._items  = list(items)
        self._title  = title
        self._mode   = mode
        self._height = height or 18   # nb lignes visibles par défaut

        # Curseur sur les items
        self._cursor = 0
        # Offset de défilement
        self._scroll = 0

        # Focus général : "list" | "cancel" | "all" | "none" | "ok"
        self._focus: str = "list"

        # Résultat : None = annulé
        self._result: list[SelectItem] | None = None
        self._done = False

        self._app: Application | None = None

    # ── Propriétés ───────────────────────────────────────────────────────────

    @property
    def _visible_height(self) -> int:
        return min(self._height, len(self._items))

    def _clamp_scroll(self) -> None:
        h = self._visible_height
        if self._cursor < self._scroll:
            self._scroll = self._cursor
        elif self._cursor >= self._scroll + h:
            self._scroll = self._cursor - h + 1

    # ── Actions ───────────────────────────────────────────────────────────────

    def _move(self, delta: int) -> None:
        if not self._items:
            return
        self._cursor = max(0, min(len(self._items) - 1, self._cursor + delta))
        self._clamp_scroll()

    def _toggle(self) -> None:
        if self._items and self._mode == "multi":
            self._items[self._cursor].selected = not self._items[self._cursor].selected

    def _select_all(self) -> None:
        for it in self._items:
            it.selected = True

    def _select_none(self) -> None:
        for it in self._items:
            it.selected = False

    def _confirm(self) -> None:
        if self._mode == "multi":
            self._result = [it for it in self._items if it.selected]
        else:
            if self._items:
                self._result = [self._items[self._cursor]]
        self._done = True

    def _cancel(self) -> None:
        self._result = None
        self._done = True

    # ── Rendu ─────────────────────────────────────────────────────────────────

    def _render(self) -> list[tuple[str, str]]:
        ft: list[tuple[str, str]] = []

        # Titre
        if self._title:
            ft.append(("class:title", f" {self._title} \n"))
        ft.append(("class:separator", "─" * 60 + "\n"))

        if not self._items:
            ft.append(("class:meta", " (liste vide)\n"))
        else:
            visible = self._items[self._scroll : self._scroll + self._visible_height]
            for rel, item in enumerate(visible):
                abs_idx = self._scroll + rel
                focused = (abs_idx == self._cursor) and self._focus == "list"

                row_style = "class:item.focus" if focused else "class:item"

                if self._mode == "multi":
                    check = "[✓]" if item.selected else "[ ]"
                    check_style = "class:check.on" if item.selected else "class:check.off"
                    ft.append((row_style, " "))
                    ft.append((check_style, check))
                else:
                    arrow = " ▶ " if focused else "   "
                    ft.append((row_style, arrow))

                label_pad = item.label.ljust(38)
                ft.append((row_style, f" {label_pad}"))

                if item.meta:
                    ft.append(("class:meta", f"  {item.meta}"))

                ft.append(("", "\n"))

            # Indicateur de défilement
            total = len(self._items)
            if total > self._visible_height:
                shown_end = self._scroll + self._visible_height
                ft.append(("class:hint", f" … {shown_end}/{total}\n"))

        # Barre d'actions
        ft.append(("class:separator", "─" * 60 + "\n"))
        ft.append(("class:bar", " "))

        if self._mode == "multi":
            for btn_id, label in ((_BTN_ALL, " [Tous] "), (_BTN_NONE, " [Aucun] ")):
                style = "class:btn.focus" if self._focus == btn_id else "class:btn"
                ft.append((style, label))
                ft.append(("class:bar", "  "))

        ft.append(("class:bar", "  "))

        for btn_id, label in ((_BTN_CANCEL, " [Annuler] "), (_BTN_OK, " [Valider] ")):
            style = "class:btn.focus" if self._focus == btn_id else "class:btn"
            ft.append((style, label))
            ft.append(("class:bar", " "))

        ft.append(("class:bar", "\n"))

        hint = (
            "↑↓ naviguer  Espace cocher  a=Tous  n=Aucun  Tab=boutons  Entrée=valider  Échap=annuler"
            if self._mode == "multi"
            else "↑↓ naviguer  Entrée=sélectionner  Échap=annuler"
        )
        ft.append(("class:hint", f" {hint}\n"))

        return ft

    # ── Bindings ──────────────────────────────────────────────────────────────

    def _make_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            if self._focus == "list":
                self._move(-1)

        @kb.add("down")
        def _(event):
            if self._focus == "list":
                self._move(1)

        @kb.add("space")
        def _(event):
            if self._focus == "list":
                self._toggle()

        @kb.add("a")
        def _(event):
            if self._mode == "multi":
                self._select_all()
                self._focus = "list"

        @kb.add("n")
        def _(event):
            if self._mode == "multi":
                self._select_none()
                self._focus = "list"

        @kb.add("f2")
        def _(event):
            if self._mode == "multi":
                self._select_all()

        @kb.add("f3")
        def _(event):
            if self._mode == "multi":
                self._select_none()

        @kb.add("tab")
        def _(event):
            """Cycle : list → (all →) (none →) cancel → ok → list."""
            order: list[str] = ["list"]
            if self._mode == "multi":
                order += [_BTN_ALL, _BTN_NONE]
            order += [_BTN_CANCEL, _BTN_OK]
            idx = order.index(self._focus) if self._focus in order else 0
            self._focus = order[(idx + 1) % len(order)]

        @kb.add("s-tab")
        def _(event):
            """Cycle inverse."""
            order: list[str] = ["list"]
            if self._mode == "multi":
                order += [_BTN_ALL, _BTN_NONE]
            order += [_BTN_CANCEL, _BTN_OK]
            idx = order.index(self._focus) if self._focus in order else 0
            self._focus = order[(idx - 1) % len(order)]

        @kb.add("enter")
        def _(event):
            if self._focus == "list":
                if self._mode == "single":
                    self._confirm()
                else:
                    # En mode multi, Entrée sur un item = cocher/décocher
                    self._toggle()
            elif self._focus == _BTN_OK:
                self._confirm()
            elif self._focus == _BTN_CANCEL:
                self._cancel()
            elif self._focus == _BTN_ALL:
                self._select_all()
                self._focus = "list"
            elif self._focus == _BTN_NONE:
                self._select_none()
                self._focus = "list"
            if self._done and self._app:
                self._app.exit()

        @kb.add("escape")
        def _(event):
            self._cancel()
            if self._app:
                self._app.exit()

        return kb

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def run(self) -> list[SelectItem] | None:
        """Lance le TUI et retourne la sélection, ou None si annulé."""
        kb = self._make_bindings()

        control = FormattedTextControl(
            lambda: to_formatted_text(self._render()),
            focusable=True,
        )
        window = Window(content=control, wrap_lines=False)
        layout = Layout(window)

        self._app = Application(
            layout       = layout,
            key_bindings = kb,
            style        = _STYLE,
            full_screen  = False,
            mouse_support= False,
        )
        self._app.run()
        return self._result


# ── Helper universel ──────────────────────────────────────────────────────────

def pick(
    ctx,
    items:          list[SelectItem],
    title:          str = "",
    mode:           str = "multi",
    confirm_label:  str = "",
) -> list[SelectItem] | None:
    """Sélectionne dans une liste — overlay si disponible, sinon TUI terminal.

    Retourne la liste des items sélectionnés, ou None si annulé.
    En mode overlay, délègue à ``ctx.select_fn`` injecté par le serveur.
    """
    select_fn = getattr(ctx, "select_fn", None)
    if callable(select_fn):
        return select_fn(items, title=title, mode=mode, confirm_label=confirm_label)
    return ListSelector(items, title=title, mode=mode).run()
