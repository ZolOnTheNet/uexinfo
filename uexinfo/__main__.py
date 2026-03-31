"""Point d'entrée — overlay uniquement."""
import sys


def _print_ocr_status() -> None:
    try:
        from uexinfo.ocr.engine import ocr_status
        s = ocr_status()
    except Exception:
        return

    mode = s["mode"]
    if mode == "sc-datarunner":
        label = "\033[32mSC-Datarunner\033[0m"
        detail = "(tesseract bundlé + tessdata personnalisée)"
    elif mode == "system":
        label = "\033[33msystème\033[0m"
        detail = "(tesseract PATH — qualité OCR réduite)"
    else:
        label = "\033[31mindisponible\033[0m"
        detail = "(OCR désactivé — installer pytesseract + tesseract)"

    ver = f"  {s['version']}" if s.get("version") else ""
    print(f"[OCR] {label}{ver}  {detail}", flush=True)

    if mode == "unavailable":
        if not s["pytesseract"]:
            print("  ! pytesseract non installé : pip install pytesseract", flush=True)
        if not s["sc_datarunner_exe"] and not s["version"]:
            print("  ! tesseract introuvable (ni bundlé ni sur PATH)", flush=True)
    elif mode == "system":
        if not s["sc_datarunner_exe"]:
            print(f"  ! SC-Datarunner exe absent : {s['tesseract_exe']}", flush=True)
        if not s["sc_datarunner_data"]:
            print(f"  ! tessdata SC absent : {s['tessdata_dir']}", flush=True)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        prog="uexinfo",
        description="UEXInfo — Overlay Star Citizen\nInterroge l'API UEX Corp 2.0.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
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
        help="Affiche ce message d'aide",
    )
    args = parser.parse_args()

    _print_ocr_status()

    try:
        import webview   # noqa: F401
        import pynput    # noqa: F401
        import websockets  # noqa: F401
    except ImportError:
        print(
            "[uexinfo] Dépendances manquantes.\n"
            "  Installer : pip install -e .",
            file=sys.stderr,
        )
        sys.exit(1)

    from uexinfo.overlay import run_overlay
    run_overlay(hotkey=args.hotkey, port=args.port)


if __name__ == "__main__":
    main()
