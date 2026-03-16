"""Point d'entrée — routing selon les arguments CLI."""
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="uexinfo",
        description=(
            "UEXInfo — CLI interactif Star Citizen\n"
            "Interroge l'API UEX Corp 2.0 pour les prix, routes et scans de trading.\n"
            "\n"
            "Sans argument : mode REPL (terminal interactif).\n"
            "Avec --tui    : mode TUI (interface graphique dans le terminal)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    parser.add_argument(
        "--tui", "-t",
        action="store_true",
        help="Lancer en mode TUI (interface graphique terminal Textual)",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Mode overlay transparent superposé à Star Citizen (Phase 4, expérimental)",
    )
    parser.add_argument(
        "--hotkey",
        type=str,
        default=None,
        metavar="TOUCHE",
        help="Hotkey pour basculer l'overlay (défaut : alt+shift+u)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Port pour textual-web en mode overlay (défaut : 8090)",
    )
    parser.add_argument(
        "-?",
        action="help",
        default=argparse.SUPPRESS,
        help="Affiche ce message d'aide (alias de --help / -h)",
    )
    args = parser.parse_args()

    if args.overlay:
        from uexinfo.overlay import run_overlay
        run_overlay(hotkey=args.hotkey, port=args.port)
    elif args.tui:
        from uexinfo.app import UexInfoApp
        UexInfoApp().run()
    else:
        from uexinfo.cli import run_cli
        run_cli()


main()
