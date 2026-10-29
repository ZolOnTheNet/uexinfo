"""Point d'entrée — overlay uniquement."""
import sys


def _print_ocr_status() -> None:
    """Affiche au démarrage d'où vient Tesseract (copie fournie, système ou absent)."""
    try:
        from uexinfo.ocr.engine import ocr_status
        s = ocr_status()
    except Exception:
        return

    mode = s["mode"]
    if mode == "bundled":
        label = "\033[32mbundlé\033[0m"
        detail = f"(tesseract + modèle eng_sc : {s['tesseract_exe'].parent.parent})"
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
        if not s["bundled_exe"] and not s["version"]:
            print("  ! tesseract introuvable (ni bundlé ni sur PATH)", flush=True)
    elif mode == "system":
        if not s["bundled_exe"]:
            print("  ! tesseract.exe absent de extprg/tesseract/ (voir LISEZMOI.txt)", flush=True)
        if not s["bundled_data"]:
            print(f"  ! modèle eng_sc.traineddata absent : {s['tessdata_dir']}", flush=True)


def main() -> None:
    """Lit les options (`--hotkey`, `--port`), vérifie les dépendances de l'overlay et le lance."""
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
