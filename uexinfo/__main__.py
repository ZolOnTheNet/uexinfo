"""Point d'entrée — routing selon les arguments CLI."""
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="uexinfo",
        description="Star Citizen Trade Assistant",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Mode CLI original (prompt interactif Rich)",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Mode overlay transparent (PyWebView + hotkey toggle)",
    )
    parser.add_argument(
        "--hotkey",
        type=str,
        default=None,
        help="Hotkey pour toggle overlay (défaut: alt+shift+u)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port pour textual-web en mode overlay (défaut: 8090)",
    )
    args = parser.parse_args()

    if args.cli:
        from uexinfo.cli import run_cli
        run_cli()
    elif args.overlay:
        from uexinfo.overlay import run_overlay
        run_overlay(hotkey=args.hotkey, port=args.port)
    else:
        from uexinfo.app import UexInfoApp
        UexInfoApp().run()


main()
