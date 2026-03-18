"""Point d'entrée — routing selon les arguments CLI."""
import argparse
import sys


def _overlay_deps_available() -> bool:
    """Vérifie que les dépendances optionnelles de l'overlay sont installées."""
    try:
        import webview   # noqa: F401
        import pynput    # noqa: F401
        import websockets  # noqa: F401
        return True
    except ImportError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="uexinfo",
        description=(
            "UEXInfo — CLI interactif Star Citizen\n"
            "Interroge l'API UEX Corp 2.0 pour les prix, routes et scans de trading.\n"
            "\n"
            "Sans argument : mode overlay (avec fallback CLI si dépendances absentes).\n"
            "Avec --cli    : mode REPL terminal.\n"
            "Avec --tui    : mode TUI (interface graphique dans le terminal)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    parser.add_argument(
        "--cli", "-c",
        action="store_true",
        help="Forcer le mode REPL terminal (sans overlay)",
    )
    parser.add_argument(
        "--tui", "-t",
        action="store_true",
        help="Lancer en mode TUI (interface graphique terminal Textual)",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Mode overlay transparent superposé à Star Citizen (défaut si dépendances présentes)",
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
        help="Port WebSocket de l'overlay (défaut : 8090)",
    )
    parser.add_argument(
        "-?",
        action="help",
        default=argparse.SUPPRESS,
        help="Affiche ce message d'aide (alias de --help / -h)",
    )
    args = parser.parse_args()

    if args.tui:
        from uexinfo.app import UexInfoApp
        UexInfoApp().run()
    elif args.cli:
        from uexinfo.cli import run_cli
        run_cli()
    else:
        # Mode par défaut : overlay si dépendances disponibles, sinon CLI
        if _overlay_deps_available():
            from uexinfo.overlay import run_overlay
            run_overlay(hotkey=args.hotkey, port=args.port)
        else:
            print(
                "[uexinfo] Dépendances overlay manquantes → mode CLI.\n"
                "  Pour activer l'overlay : pip install -e \".[overlay]\"",
                file=sys.stderr,
            )
            from uexinfo.cli import run_cli
            run_cli()


main()
