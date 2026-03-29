"""Tableaux Rich adaptatifs — colonnes flexibles proportionnelles à la console.

Usage ::

    from uexinfo.display.adaptive import ColSpec, adaptive_table

    tbl = adaptive_table([
        ColSpec("#",          width=3,  justify="right", style="dim"),
        ColSpec("Nom",        flex=1,   style="bold"),      # ← flexible
        ColSpec("Départ",     flex=1,   style="cyan"),      # ← flexible, même poids
        ColSpec("Récompense", width=12, justify="right"),   # ← fixe
    ], row_styles=["", "on grey7"])

Colonnes avec ``flex > 0`` se partagent l'espace restant proportionnellement.
Colonnes avec ``width > 0`` ont une largeur fixe (``flex`` ignoré).

Le calcul suppose ``padding=(0, 1)`` (défaut Rich / uexinfo), soit 2 chars
de marge par colonne (1 gauche + 1 droite).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any

from rich.table import Table


@dataclass
class ColSpec:
    """Spécification d'une colonne pour :func:`adaptive_table`."""
    header:   str
    flex:     int  = 0      # poids proportionnel (0 = colonne fixe)
    width:    int  = 0      # largeur fixe si flex == 0
    min_flex: int  = 8      # plancher en mode flex
    style:    str  = ""
    justify:  str  = "left"
    no_wrap:  bool = False


def _console_width() -> int:
    """Largeur de la console courante (fallback 80)."""
    try:
        from uexinfo.display.formatter import console as _con  # noqa: PLC0415
        w = _con.width
        if w and w > 20:
            return w
    except Exception:
        pass
    return shutil.get_terminal_size((80, 24)).columns


def flex_widths(
    specs:          list[ColSpec],
    padding:        tuple[int, int] = (0, 1),
    console_width:  int | None = None,
) -> dict[str, int]:
    """Calcule la largeur de chaque colonne flexible.

    Retourne un dict ``{header: width}`` pour les colonnes flex uniquement.
    Les colonnes fixe (``width > 0``) ne sont pas dans le résultat.
    """
    w = console_width or _console_width()
    pad_per_col = padding[1] * 2          # 1 gauche + 1 droite

    n_cols    = len(specs)
    fixed_sum = sum(s.width for s in specs if s.width > 0)
    flex_cols = [s for s in specs if s.flex > 0]

    # Espace disponible pour le *contenu* des colonnes flexibles
    # (total - contenu fixe - padding de toutes les colonnes)
    available = w - fixed_sum - n_cols * pad_per_col
    available = max(available, sum(s.min_flex for s in flex_cols))

    total_weight = sum(s.flex for s in flex_cols) or 1
    result: dict[str, int] = {}
    allocated = 0

    for i, s in enumerate(flex_cols):
        if i == len(flex_cols) - 1:
            # Dernière colonne flex : prend le reste pour absorber les arrondis
            result[s.header] = max(s.min_flex, available - allocated)
        else:
            col_w = max(s.min_flex, int(available * s.flex / total_weight))
            result[s.header] = col_w
            allocated += col_w

    return result


def adaptive_table(
    specs:          list[ColSpec],
    padding:        tuple[int, int] = (0, 1),
    row_styles:     list[str] | None = None,
    console_width:  int | None = None,
    **table_kw:     Any,
) -> Table:
    """Crée un :class:`rich.table.Table` avec des largeurs adaptées à la console.

    Les colonnes ``flex > 0`` se partagent l'espace disponible après que les
    colonnes fixes et les marges aient été soustraites de la largeur totale.
    """
    widths = flex_widths(specs, padding=padding, console_width=console_width)

    kw: dict[str, Any] = {"show_header": True, "box": None, "padding": padding}
    if row_styles is not None:
        kw["row_styles"] = row_styles
    kw.update(table_kw)

    tbl = Table(**kw)
    for s in specs:
        if s.flex > 0:
            w = widths[s.header]
            tbl.add_column(
                s.header,
                style    = s.style,
                justify  = s.justify,
                max_width = w,
                min_width = s.min_flex,
                no_wrap  = s.no_wrap,
            )
        else:
            tbl.add_column(
                s.header,
                style   = s.style,
                justify = s.justify,
                width   = s.width or None,
                no_wrap = s.no_wrap,
            )
    return tbl
