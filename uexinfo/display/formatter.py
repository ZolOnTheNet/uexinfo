"""Helpers d'affichage Rich — console partagée."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich import box

from uexinfo.display import colors as C

# Instance console partagée par tous les modules
console = Console()


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


def profit_color(value: float) -> str:
    """Retourne la couleur Rich selon la valeur de profit."""
    if value > 0:
        return C.PROFIT
    if value < 0:
        return C.LOSS
    return C.NEUTRAL
