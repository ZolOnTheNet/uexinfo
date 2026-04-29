"""Renderer HTML natif — convertit les renderables Rich en HTML structuré.

Pas de round-trip ANSI → les spans suivent les frontières de markup, sans
fragmentation. Les termes du vocabulaire restent dans un seul nœud texte →
l'annotateur JS peut les trouver et les rendre cliquables.

Styles sémantiques produits (classes CSS à définir dans index.html) :
  s-uex, s-sctrade, s-profit, s-loss, s-warn, s-ok, s-dim, s-bold, s-label
"""
from __future__ import annotations

import html as _html_mod
import io
from typing import Any

from rich.text import Text as RichText
from rich.table import Table as RichTable
from rich.rule import Rule as RichRule


# ── Console de rendu (muette, pour Text.render()) ─────────────────────────────

_RENDER_CONSOLE: Any = None


def _render_console():
    global _RENDER_CONSOLE
    if _RENDER_CONSOLE is None:
        from rich.console import Console
        _RENDER_CONSOLE = Console(
            file=io.StringIO(),
            force_terminal=False,
            highlight=False,
            width=200,
            markup=True,
        )
    return _RENDER_CONSOLE


# ── Mapping style Rich → classe CSS sémantique ────────────────────────────────

_COLOR_TO_PLAIN: dict[str, str] = {
    "cyan":         "s-uex",
    "orange1":      "s-sctrade",
    "green":        "s-ok",
    "red":          "s-loss",
    "yellow":       "s-warn",
    "white":        "",
    "bright_white": "s-bold",
}
_COLOR_TO_BOLD: dict[str, str] = {
    "cyan":         "s-uex",
    "orange1":      "s-sctrade",
    "green":        "s-profit",
    "red":          "s-loss",
    "yellow":       "s-warn",
}
_STR_MAP: dict[str, str] = {
    "dim":              "s-dim",
    "italic dim":       "s-dim",
    "bold":             "s-bold",
    "bold white":       "s-bold",
    "bright_white":     "s-bold",
    **{f"bold {k}": v  for k, v in _COLOR_TO_BOLD.items()},
    **{f"italic {k}": v for k, v in _COLOR_TO_PLAIN.items()},
    **{k: v            for k, v in _COLOR_TO_PLAIN.items()},
}


def _style_to_css(style: Any) -> str:
    """Convertit un style Rich (str ou objet Style) en classe CSS sémantique."""
    if not style:
        return ""

    if isinstance(style, str):
        return _STR_MAP.get(style.strip().lower(), "")

    # Objet Style Rich
    try:
        dim  = style.dim  is True
        bold = style.bold is True
        if dim:
            return "s-dim"
        color_name = ""
        if style.color:
            color_name = (style.color.name or "").lower()
        if not bold and not color_name:
            return ""
        if bold and color_name:
            return _COLOR_TO_BOLD.get(color_name, "s-bold")
        if color_name:
            return _COLOR_TO_PLAIN.get(color_name, "")
        return "s-bold"
    except Exception:
        pass
    return ""


def _esc(text: str) -> str:
    return _html_mod.escape(text, quote=False)


# ── Rich Text → HTML inline ────────────────────────────────────────────────────

def _text_to_inline_html(text: RichText) -> str:
    """Convertit un objet Rich Text en fragment HTML inline."""
    rc = _render_console()
    parts: list[str] = []
    for seg in text.render(rc):
        if not seg.text:
            continue
        esc = _esc(seg.text)
        css = _style_to_css(seg.style) if seg.style else ""
        if css:
            parts.append(f'<span class="{css}">{esc}</span>')
        else:
            parts.append(esc)
    return "".join(parts)


def _markup_to_inline_html(markup: str) -> str:
    """Parse une chaîne markup Rich et retourne du HTML inline."""
    if not markup:
        return ""
    text = RichText.from_markup(markup)
    return _text_to_inline_html(text)


def _cell_to_html(cell: Any) -> str:
    """Convertit le contenu d'une cellule de tableau en HTML inline."""
    if cell is None:
        return ""
    if isinstance(cell, str):
        return _markup_to_inline_html(cell)
    if isinstance(cell, RichText):
        return _text_to_inline_html(cell)
    try:
        return _esc(str(cell))
    except Exception:
        return ""


# ── Rich Table → HTML table ───────────────────────────────────────────────────

_JUSTIFY: dict[str, str] = {
    "left": "left", "right": "right", "center": "center", "full": "left",
}


def _table_to_html(table: RichTable) -> str:
    """Convertit un objet Rich Table en élément <table class='rt'>.

    Rich stocke les cellules dans column._cells (une liste par colonne),
    pas dans row.cells.
    """
    columns = table.columns
    num_rows = len(table.rows)

    aligns: list[str] = []
    col_classes: list[str] = []
    thead_cells: list[str] = []

    for col in columns:
        align = _JUSTIFY.get(str(col.justify or "left").lower(), "left")
        aligns.append(align)
        col_css = _style_to_css(col.style or "")
        col_classes.append(col_css)
        hdr_css = _style_to_css(col.header_style or "") or col_css
        hdr = _esc(str(col.header or ""))
        attr = f' class="{hdr_css}"' if hdr_css else ""
        thead_cells.append(f'<th{attr} style="text-align:{align}">{hdr}</th>')

    rows_html: list[str] = []
    for row_idx in range(num_rows):
        tds: list[str] = []
        for col_idx, col in enumerate(columns):
            align   = aligns[col_idx]
            col_css = col_classes[col_idx]
            cells   = getattr(col, "_cells", [])
            cell    = cells[row_idx] if row_idx < len(cells) else ""
            cell_html = _cell_to_html(cell)
            attr = f' class="{col_css}"' if col_css else ""
            tds.append(f'<td{attr} style="text-align:{align}">{cell_html}</td>')
        row = table.rows[row_idx]
        row_css = _style_to_css(getattr(row, "style", None) or "")
        tr_attr = f' class="{row_css}"' if row_css else ""
        rows_html.append(f'<tr{tr_attr}>{"".join(tds)}</tr>')

    thead = f'<thead><tr>{"".join(thead_cells)}</tr></thead>'
    tbody = f'<tbody>{"".join(rows_html)}</tbody>'
    title_html = ""
    if getattr(table, "title", None):
        title_html = f'<div class="rt-title">{_markup_to_inline_html(str(table.title))}</div>'
    caption_html = ""
    if getattr(table, "caption", None):
        caption_html = f'<div class="rt-caption">{_markup_to_inline_html(str(table.caption))}</div>'
    return f'{title_html}<table class="rt">{thead}{tbody}</table>{caption_html}'


# ── Dispatch par type ──────────────────────────────────────────────────────────

def _to_blocks(obj: Any) -> list[str]:
    """Convertit un renderable Rich en liste de blocs HTML (chaque bloc = une string)."""
    if obj is None:
        return ['<div class="line">&nbsp;</div>']

    if isinstance(obj, RichTable):
        return [_table_to_html(obj)]

    if isinstance(obj, RichRule):
        title_html = ""
        if obj.title:
            if isinstance(obj.title, RichText):
                title_html = _text_to_inline_html(obj.title)
            else:
                title_html = _markup_to_inline_html(str(obj.title))
        if title_html:
            return [f'<div class="section-title">{title_html}</div>']
        return ['<hr class="rule">']

    if isinstance(obj, RichText):
        plain = obj.plain
        if not plain or not plain.strip():
            return ['<div class="line">&nbsp;</div>']
        inline = _text_to_inline_html(obj)
        return [f'<div class="line">{inline}</div>']

    if isinstance(obj, str):
        stripped = obj.strip()
        if not stripped:
            return ['<div class="line">&nbsp;</div>']
        # Peut contenir plusieurs lignes (ex : messages multi-lignes)
        lines_out = []
        for raw_line in obj.splitlines():
            if not raw_line.strip():
                lines_out.append('<div class="line">&nbsp;</div>')
            else:
                lines_out.append(f'<div class="line">{_markup_to_inline_html(raw_line)}</div>')
        return lines_out or ['<div class="line">&nbsp;</div>']

    # Autres renderables (Panel, Padding…) : fallback via str()
    try:
        s = str(obj)
        if not s.strip():
            return ['<div class="line">&nbsp;</div>']
        return [f'<div class="line">{_esc(s)}</div>']
    except Exception:
        return []


# ── API publique ───────────────────────────────────────────────────────────────

def rich_renderables_to_html(renderables: list[Any]) -> str:
    """Convertit une liste de renderables Rich en HTML structuré.

    Retourne un bloc HTML avec des éléments de niveau bloc
    (<div class="line">, <table class="rt">, <hr class="rule">, etc.)
    séparés par des sauts de ligne — compatible avec appendHtml() dans index.html.
    """
    blocks: list[str] = []
    for obj in renderables:
        blocks.extend(_to_blocks(obj))
    return "\n".join(blocks)
