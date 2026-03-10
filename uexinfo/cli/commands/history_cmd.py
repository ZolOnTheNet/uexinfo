"""Commande /history — historique des commandes."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.cli import history as _hist
from uexinfo.display.formatter import console, print_warn, section
from uexinfo.display import colors as C


@register("history", "hist")
def cmd_history(args: list[str], ctx) -> None:
    sub = args[0].lower() if args else "list"

    if sub == "stats":
        s = _hist.stats()
        section("Historique")
        console.print(f"  [bold]Total commandes :[/bold] {s['total']}")
        console.print(f"  [bold]Uniques         :[/bold] {s['unique']}")
        console.print(f"  [bold]Taille fichier  :[/bold] {s['size_kb']} Ko")
        console.print(f"  [bold]Fichier         :[/bold] [{C.DIM}]{s.get('path', '—')}[/{C.DIM}]")
        return

    if sub == "clear":
        import appdirs
        from pathlib import Path
        p = Path(appdirs.user_data_dir("uexinfo")) / "history.jsonl"
        if p.exists():
            p.unlink()
        console.print(f"[green]✓  Historique effacé[/green]")
        return

    # list [n]
    try:
        n = int(args[0]) if args and args[0].isdigit() else 50
    except ValueError:
        n = 50

    entries = _hist.last_n(n)
    if not entries:
        print_warn("Historique vide.")
        return

    section(f"Historique — {len(entries)} dernières commandes")
    for i, cmd in enumerate(entries, 1):
        console.print(f"  [{C.DIM}]{i:4}[/{C.DIM}]  {cmd}")
