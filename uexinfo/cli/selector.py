"""Sélecteur générique — délègue à l'overlay via ctx.select_fn.

Usage ::

    from uexinfo.cli.selector import SelectItem, pick

    items = [SelectItem(label="foo.jpg", value=path, meta="12 Ko")]
    chosen = pick(ctx, items, title="Choisir un screenshot", mode="multi")
    # Retourne list[SelectItem] ou None si annulé / non supporté
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SelectItem:
    """Un élément de sélection.

    label    — texte affiché
    value    — valeur retournée (Path, str, objet…)
    meta     — info secondaire facultative
    selected — état initial
    """
    label:    str
    value:    Any
    meta:     str  = ""
    selected: bool = False


def pick(
    ctx,
    items:          list[SelectItem],
    title:          str = "",
    mode:           str = "multi",
    confirm_label:  str = "",
) -> list[SelectItem] | None:
    """Sélectionne dans une liste via ctx.select_fn (overlay).

    Retourne la liste des items sélectionnés, ou None si annulé / non disponible.
    """
    select_fn = getattr(ctx, "select_fn", None)
    if callable(select_fn):
        return select_fn(items, title=title, mode=mode, confirm_label=confirm_label)
    return None
