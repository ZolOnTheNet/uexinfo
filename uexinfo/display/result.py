"""IR (Intermediate Representation) entre les commandes et les renderers.

Les commandes retournent un CommandResult au lieu d'appeler console.print().
Les renderers (HtmlRenderer, RichRenderer) consomment ce CommandResult.

Aucune dépendance vers Rich ou le WebSocket dans ce module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


# ── Styles sémantiques ────────────────────────────────────────────────────────
# Utilisés par les deux renderers — jamais de couleurs raw ici.

STYLES = frozenset({
    "",
    "dim", "bold",
    "uex",          # cyan — donnée UEX Corp
    "sctrade",      # orange — donnée sc-trade.tools
    "profit",       # bold green
    "loss",         # bold red
    "warn",         # yellow
    "error",        # bold red
    "ok",           # green
    "label",        # bold
    "age-ok",       # ≤1 jour
    "age-mid",      # 2-3 jours
    "age-old",      # ≥4 jours
})


# ── Éléments inline ───────────────────────────────────────────────────────────

@dataclass
class Span:
    """Texte avec style sémantique."""
    text:  str
    style: str = ""

    def to_dict(self) -> dict:
        return {"kind": "span", "text": self.text, "style": self.style}


@dataclass
class Term:
    """Terme vocabulary — cliquable, avec type et commande optionnelle.

    type : "location" | "commodity" | "ship" | "voyage"
    cmd  : commande exécutée au clic (ex: "/info Area 18") ; vide = tooltip seul
    """
    text:  str
    type:  str
    cmd:   str  = ""
    style: str  = ""

    def to_dict(self) -> dict:
        return {"kind": "term", "text": self.text, "type": self.type,
                "cmd": self.cmd, "style": self.style}


@dataclass
class Cmd:
    """Texte cliquable qui exécute une commande."""
    text:  str
    cmd:   str
    style: str = ""

    def to_dict(self) -> dict:
        return {"kind": "cmd", "text": self.text, "cmd": self.cmd, "style": self.style}


# Un élément inline est soit un str brut, soit un objet annoté.
Inline = Union[str, Span, Term, Cmd]


def inline_to_dict(el: Inline) -> dict:
    """Sérialise un élément inline en dict JSON."""
    if isinstance(el, str):
        return {"kind": "span", "text": el, "style": ""}
    return el.to_dict()


# ── Blocs ─────────────────────────────────────────────────────────────────────

@dataclass
class Text:
    """Paragraphe avec contenu inline mixé."""
    content: list[Inline]

    def to_dict(self) -> dict:
        return {"kind": "text", "content": [inline_to_dict(e) for e in self.content]}


@dataclass
class Section:
    """Titre de section."""
    title: str | list[Inline]

    def to_dict(self) -> dict:
        if isinstance(self.title, str):
            t = self.title
        else:
            t = [inline_to_dict(e) for e in self.title]
        return {"kind": "section", "title": t}


@dataclass
class Rule:
    """Séparateur horizontal."""
    def to_dict(self) -> dict:
        return {"kind": "rule"}


@dataclass
class Blank:
    """Ligne vide."""
    def to_dict(self) -> dict:
        return {"kind": "blank"}


@dataclass
class Column:
    header:  str
    style:   str  = ""
    width:   int  = 0        # 0 = auto
    align:   str  = "left"   # "left" | "right" | "center"
    no_wrap: bool = False

    def to_dict(self) -> dict:
        return {"header": self.header, "style": self.style,
                "width": self.width, "align": self.align, "no_wrap": self.no_wrap}


@dataclass
class Row:
    cells:     list[list[Inline] | str]
    style:     str  = ""
    is_header: bool = False

    def to_dict(self) -> dict:
        cells_out = []
        for cell in self.cells:
            if isinstance(cell, str):
                cells_out.append([{"kind": "span", "text": cell, "style": ""}])
            else:
                cells_out.append([inline_to_dict(e) for e in cell])
        return {"cells": cells_out, "style": self.style, "is_header": self.is_header}


@dataclass
class Table:
    columns:  list[Column]
    rows:     list[Row]
    title:    str = ""
    caption:  str = ""
    box:      str = "simple"   # "simple" | "rounded" | "heavy" | "none"

    def to_dict(self) -> dict:
        return {
            "kind":    "table",
            "title":   self.title,
            "caption": self.caption,
            "box":     self.box,
            "columns": [c.to_dict() for c in self.columns],
            "rows":    [r.to_dict() for r in self.rows],
        }


@dataclass
class Action:
    """Bouton d'action."""
    label: str
    cmd:   str
    style: str = ""   # "primary" | "secondary" | "danger"

    def to_dict(self) -> dict:
        return {"label": self.label, "cmd": self.cmd, "style": self.style}


@dataclass
class Actions:
    """Groupe de boutons inline."""
    items: list[Action]

    def to_dict(self) -> dict:
        return {"kind": "actions", "items": [a.to_dict() for a in self.items]}


Block = Union[Text, Section, Rule, Blank, Table, Actions]


def block_to_dict(b: Block) -> dict:
    return b.to_dict()


# ── CommandResult ─────────────────────────────────────────────────────────────

@dataclass
class CommandResult:
    """Résultat structuré d'une commande CLI.

    Retourné par les handlers à la place de console.print().
    Consommé par HtmlRenderer (overlay) ou RichRenderer (debug).
    """
    blocks:        list[Block] = field(default_factory=list)

    # Flags post-rendu
    status_update: bool        = False   # demande refresh barre de statut
    vocab_update:  bool        = False   # demande re-envoi du vocab

    # Messages WS additionnels (ex: position_update, trade_pick…)
    overlay_msgs:  list[dict]  = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "blocks":        [block_to_dict(b) for b in self.blocks],
            "status_update": self.status_update,
            "vocab_update":  self.vocab_update,
        }

    # ── Helpers de construction ───────────────────────────────────────────────

    def add(self, *blocks: Block) -> "CommandResult":
        """Ajoute des blocs et retourne self (chaînable)."""
        self.blocks.extend(blocks)
        return self

    def section(self, title: str | list[Inline]) -> "CommandResult":
        return self.add(Section(title))

    def text(self, *content: Inline) -> "CommandResult":
        return self.add(Text(list(content)))

    def rule(self) -> "CommandResult":
        return self.add(Rule())

    def blank(self) -> "CommandResult":
        return self.add(Blank())

    def table(self, columns: list[Column], rows: list[Row],
              title: str = "", caption: str = "", box: str = "simple") -> "CommandResult":
        return self.add(Table(columns=columns, rows=rows,
                              title=title, caption=caption, box=box))

    def actions(self, *items: Action) -> "CommandResult":
        return self.add(Actions(list(items)))
