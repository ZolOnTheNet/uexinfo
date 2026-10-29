#!/usr/bin/env bash
# Lance l'overlay UEXInfo sous Linux.
#
# Au premier lancement, prépare l'environnement Python (.venv) et installe les
# dépendances. Il les réinstalle si .venv est cassé (mise à jour de Python) ou si
# pyproject.toml a changé. Ensuite, il lance l'overlay.
#
# Usage (depuis n'importe quel dossier) :
#   scripts/uexinfolnx.sh                  lance l'overlay
#   scripts/uexinfolnx.sh --hotkey f9      options transmises à « python -m uexinfo »
#   scripts/uexinfolnx.sh --installer      prépare l'environnement sans lancer
#   scripts/uexinfolnx.sh --reinstaller    recrée l'environnement de zéro
#
# Prérequis système (Debian/Ubuntu) :
#   sudo apt install python3-venv python3-gi gir1.2-webkit2-4.1 tesseract-ocr
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
STAMP="$VENV/.uexinfo-installe"
SYS_PY="${PYTHON:-python3}"

erreur() { echo "✗ $*" >&2; exit 1; }
info()   { echo "→ $*"; }

mode=lancer
case "${1:-}" in
    --installer)   mode=installer;   shift ;;
    --reinstaller) mode=reinstaller; shift ;;
esac

# ── Prérequis système ────────────────────────────────────────────────────────
command -v "$SYS_PY" >/dev/null || erreur "python3 introuvable : sudo apt install python3 python3-venv"
"$SYS_PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || erreur "Python 3.11 ou plus requis (trouvé : $("$SYS_PY" --version))"
# La fenêtre PyWebView utilise WebKitGTK, fourni par le système (pas par pip).
"$SYS_PY" - <<'EOF' 2>/dev/null || erreur "WebKitGTK introuvable : sudo apt install python3-gi gir1.2-webkit2-4.1"
import gi
try:
    gi.require_version("WebKit2", "4.1")
except ValueError:
    gi.require_version("WebKit2", "4.0")
EOF
command -v tesseract >/dev/null \
    || echo "⚠ Tesseract absent : pas d'OCR des captures (sudo apt install tesseract-ocr)"

# ── Environnement Python ─────────────────────────────────────────────────────
# Un .venv sans pip, ou qui ne voit pas « gi » (paquets système), date d'une autre
# version de Python ou a été créé autrement : on le recrée.
venv_ok() {
    [ -x "$PY" ] && "$PY" -c 'import gi' 2>/dev/null && "$PY" -m pip --version >/dev/null 2>&1
}
if [ "$mode" = reinstaller ] || { [ -e "$VENV" ] && ! venv_ok; }; then
    info "Suppression de l'ancien environnement $VENV"
    rm -rf "$VENV"
fi
if [ ! -e "$VENV" ]; then
    info "Création de l'environnement Python ($("$SYS_PY" --version))"
    "$SYS_PY" -m venv --system-site-packages "$VENV" \
        || erreur "Création impossible : sudo apt install python3-venv"
fi
if [ ! -f "$STAMP" ] || [ "$ROOT/pyproject.toml" -nt "$STAMP" ]; then
    info "Installation des dépendances (pip install -e .)"
    "$PY" -m pip install --quiet --disable-pip-version-check -e "$ROOT"
    touch "$STAMP"
fi
"$PY" -c 'import webview, pynput, websockets' \
    || erreur "Dépendances incomplètes : relancer avec --reinstaller"

[ "$mode" = lancer ] || { info "Environnement prêt."; exit 0; }

# ── Lancement ────────────────────────────────────────────────────────────────
# Sous Wayland, la fenêtre passe par XWayland : « toujours au-dessus » et le
# raccourci global (pynput) ne fonctionnent qu'avec des fenêtres X11.
if [ "${XDG_SESSION_TYPE:-}" = wayland ]; then
    export GDK_BACKEND="${GDK_BACKEND:-x11}"
fi
cd "$ROOT"
exec "$PY" -m uexinfo "$@"
