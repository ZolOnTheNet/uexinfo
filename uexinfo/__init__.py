"""uexinfo — overlay Star Citizen pour le trading, les missions et la navigation."""
# Numéro de version : « 0.0.1-<commit> » (version_string) — le commit avance à chaque envoi,
# le numéro à la main quand une étape est franchie.
__version__ = "0.0.1"


def build_id() -> str:
    """Commit git du code lancé (ex. « 447b485 »), ou « » hors dépôt git.

    Affiché au démarrage et dans la bannière : permet de vérifier que c'est bien
    la version récupérée (git pull) qui tourne, et pas une ancienne instance.
    """
    import subprocess
    from pathlib import Path
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
            capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def version_string() -> str:
    """Version complète affichée et journalisée : « 0.0.1-e5a69a6 » (« 0.0.1 » hors dépôt git)."""
    b = build_id()
    return f"{__version__}-{b}" if b else __version__
