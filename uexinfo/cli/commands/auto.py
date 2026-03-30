"""Commande /auto — contrôle des automatisations."""
from __future__ import annotations

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display.formatter import console, print_ok, print_error
from uexinfo.display import colors as C

# Mapping option → clé cfg["auto"]
_OPTIONS: dict[str, tuple[str, str]] = {
    "log":          ("log",         "Lecture automatique du log SC-Datarunner"),
    "signal.scan":  ("signal_scan", "Signalement des nouveaux scans/screenshots"),
    "log.accept":   ("log_accept",  "Validation automatique des valeurs du log"),
}


def _on_off(val: str) -> bool | None:
    if val.lower() in ("on", "1", "oui", "yes", "true"):
        return True
    if val.lower() in ("off", "0", "non", "no", "false"):
        return False
    return None


def _show_help() -> None:
    from uexinfo.display.formatter import section
    from uexinfo.display import colors as C
    section("Aide — /auto")
    console.print(
        f"[bold]Usage :[/bold]\n"
        f"  [bold {C.UEX}]/auto[/bold {C.UEX}]                      Afficher l'état des automatisations\n"
        f"  [bold {C.UEX}]/auto log on|off[/bold {C.UEX}]            Lecture automatique du log SC-Datarunner\n"
        f"  [bold {C.UEX}]/auto signal.scan on|off[/bold {C.UEX}]    Signalement des nouveaux scans/screenshots\n"
        f"  [bold {C.UEX}]/auto log.accept on|off[/bold {C.UEX}]     Validation automatique des valeurs du log\n\n"
        f"[{C.DIM}]Options : {', '.join(_OPTIONS)}[/{C.DIM}]"
    )


@register("auto")
def cmd_auto(args: list[str], ctx) -> None:
    """Automatisations : lecture log, signalement scans."""
    auto_cfg = ctx.cfg.setdefault("auto", {})

    if args and args[0] in ("help", "?", "--help"):
        _show_help()
        return

    # /auto  →  afficher l'état
    if not args:
        _show_status(auto_cfg)
        return

    option = args[0].lower()

    # /auto <option> [on|off]
    if option in _OPTIONS:
        key, label = _OPTIONS[option]
        if len(args) < 2:
            state = auto_cfg.get(key, True)
            _print_state(option, label, state)
            return
        val = _on_off(args[1])
        if val is None:
            print_error(f"Valeur invalide : {args[1]!r}  →  on | off")
            return
        auto_cfg[key] = val
        settings.save(ctx.cfg)
        _print_state(option, label, val)
        return

    print_error(
        f"Option inconnue : {option!r}\n"
        f"Options disponibles : {', '.join(_OPTIONS)}"
    )


def _show_status(auto_cfg: dict) -> None:
    from rich.table import Table
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style=f"bold {C.LABEL}", no_wrap=True)
    t.add_column(style=C.NEUTRAL)
    t.add_column()
    for opt, (key, label) in _OPTIONS.items():
        state = auto_cfg.get(key, True)
        badge = f"[bold green]ON[/bold green]" if state else f"[dim]OFF[/dim]"
        t.add_row(f"auto {opt}", badge, f"[{C.DIM}]{label}[/{C.DIM}]")
    console.print()
    console.print(t)
    console.print(
        f"\n[{C.DIM}]Usage : auto <option> on|off"
        f"  ·  Options : {', '.join(_OPTIONS)}[/{C.DIM}]"
    )


def _print_state(option: str, label: str, state: bool) -> None:
    badge = "[bold green]ON[/bold green]" if state else "[dim]OFF[/dim]"
    console.print(f"[{C.LABEL}]auto {option}[/{C.LABEL}]  {badge}  [{C.DIM}]{label}[/{C.DIM}]")
