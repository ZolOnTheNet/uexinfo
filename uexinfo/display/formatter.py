"""Helpers d'affichage Rich — console partagée."""
from __future__ import annotations

from rich.table import Table
from rich import box

from uexinfo.display import colors as C
from uexinfo.display.capturing_console import CapturingConsole

# Instance console partagée par tous les modules.
# CapturingConsole = drop-in de Rich Console avec highlight=False
# (évite la fragmentation ANSI sur les nombres) + capture des renderables.
console = CapturingConsole()


def print_error(msg: str) -> None:
    console.print(f"[{C.ERROR}]✗ {msg}[/{C.ERROR}]")


def print_ok(msg: str) -> None:
    console.print(f"[{C.SUCCESS}]✓ {msg}[/{C.SUCCESS}]")


def print_warn(msg: str) -> None:
    console.print(f"[{C.WARNING}]⚠ {msg}[/{C.WARNING}]")


def print_info(msg: str) -> None:
    console.print(f"[{C.DIM}]{msg}[/{C.DIM}]")


def section(title: str) -> None:
    console.print(f"\n[{C.TITLE}]{title}[/{C.TITLE}]")


def make_table(*columns: tuple[str, str, str], title: str = "") -> Table:
    """Crée une table Rich.

    columns: liste de (label, style, justify)
    """
    t = Table(
        title=title or None,
        box=box.SIMPLE_HEAD,
        header_style=f"bold {C.UEX}",
        border_style=C.DIM,
        show_lines=False,
    )
    for label, style, justify in columns:
        t.add_column(label, style=style, justify=justify)
    return t


def fmt_auec(value: float) -> str:
    """Formate un prix en aUEC lisible."""
    if value <= 0:
        return "[dim]—[/dim]"
    return f"{value:,.0f} {C.AUEC}".replace(",", " ")


def fmt_scu(value: float) -> str:
    """Formate une quantité SCU."""
    if value <= 0:
        return "[dim]—[/dim]"
    return f"{value:,.0f} {C.SCU}".replace(",", " ")


def fmt_distance_gm(d: float | None, space: bool = False) -> str:
    """Formate une distance en Gm, en Mm sous 1 Gm ("2.0 Gm" / "500 Mm").

    SEULE implémentation de cette règle dans le projet — elle a été
    réimplémentée séparément à six endroits (nav.py ×2, trade.py, voyage.py
    ×3 dont deux fonctions distinctes _fmt_dist/_fmt_dist_short identiques),
    avec un format légèrement différent selon l'endroit (espace ou non avant
    l'unité) : source d'incohérences d'affichage sans bénéfice réel.
    `space=True` insère un espace avant l'unité ("2.0 Gm" vs "2.0Gm").
    """
    if d is None:
        return "?"
    unit_sep = " " if space else ""
    if d >= 1:
        return f"{d:.1f}{unit_sep}Gm"
    return f"{d * 1000:.0f}{unit_sep}Mm"


def profit_color(value: float) -> str:
    """Retourne la couleur Rich selon la valeur de profit."""
    if value > 0:
        return C.PROFIT
    if value < 0:
        return C.LOSS
    return C.NEUTRAL


import re as _re
_TDD_RE = _re.compile(
    r"^TDD\s*-\s*Trade and Development(?:\s+Division)?\s*-\s*(.+)$",
    _re.IGNORECASE,
)

def shorten_terminal_name(name: str) -> str:
    """Abrège 'TDD - Trade and Development Division - Area 18' → 'TDD - Area 18'.
    Inchangé pour tout nom qui n'est pas un terminal TDD — c'est le contrat
    dont dépendent les appelants qui testent `shorten_terminal_name(x) != x`."""
    if not name:
        return name
    m = _TDD_RE.match(name)
    if m:
        return f"TDD - {m.group(1).strip()}"
    return name


def terminal_short_name(name: str) -> str:
    """Nom court d'affichage/de regroupement d'un terminal : préserve le
    préfixe TDD (seul cas où deux terminaux au même endroit doivent rester
    distincts, cf. shorten_terminal_name), sinon ne garde que le dernier
    segment après " - ".

    SEULE implémentation de cette règle dans le projet — ne pas la
    réécrire ailleurs. Elle l'a été trois fois par le passé (sous les noms
    _loc/_loc_short/_short_terminal_name), et l'une des copies avait "oublié"
    l'exception TDD : un terminal TDD perdait son préfixe, se retrouvait
    regroupé dans LocationIndex avec des boutiques sans rapport au même
    endroit, et la position du joueur se re-résolvait vers un magasin
    arbitraire au lieu du terminal de commerce visé (bug vérifié en vrai).
    """
    if not name:
        return name
    short = shorten_terminal_name(name)
    if short != name:
        return short
    return name.rsplit(" - ", 1)[-1].strip()


def terminal_category(t) -> str:
    """Retourne 'station' | 'outpost' | 'city' | 'other' selon le type de terminal."""
    if getattr(t, "space_station_name", None):
        return "station"
    if getattr(t, "outpost_name", None):
        return "outpost"
    if getattr(t, "city_name", None):
        return "city"
    return "other"
