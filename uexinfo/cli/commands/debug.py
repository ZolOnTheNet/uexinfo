"""Commande /debug — contrôle du niveau de trace."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.display.formatter import console, print_error, print_ok, section
from uexinfo.display import colors as C


@register("debug")
def cmd_debug(args: list[str], ctx) -> None:
    """Contrôle le niveau de trace du REPL.

    /debug          Afficher le niveau actuel
    /debug <0-5>    Définir le niveau (0 = off, 5 = max)
    """
    if not args:
        level = getattr(ctx, "debug_level", 0)
        if level == 0:
            console.print(f"[{C.DIM}]Debug OFF (niveau 0)[/{C.DIM}]")
        else:
            console.print(f"[bold yellow]Debug ON — niveau {level}[/bold yellow]")
        return

    try:
        level = int(args[0])
    except ValueError:
        print_error("Usage : /debug <0-5>  (0 = off, 5 = traces maximales)")
        return

    if not 0 <= level <= 5:
        print_error("Le niveau doit être entre 0 et 5")
        return

    ctx.debug_level = level

    if level == 0:
        print_ok("Debug désactivé")
    else:
        _DESCRIPTIONS = {
            1: "traces principales (normalize, parse, dispatch)",
            2: "idem + infos complémentaires",
            3: "idem + liste des commandes connues",
            4: "idem + détails internes",
            5: "traces maximales",
        }
        desc = _DESCRIPTIONS.get(level, "traces actives")
        console.print(f"[bold yellow]Debug niveau {level} — {desc}[/bold yellow]")
        console.print(
            f"[{C.DIM}]Tapez votre commande puis observez les lignes DBG1.[/{C.DIM}]"
        )
        console.print(
            f"[{C.DIM}]Désactiver avec : /debug 0[/{C.DIM}]"
        )
