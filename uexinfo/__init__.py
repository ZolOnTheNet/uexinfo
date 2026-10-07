__version__ = "0.1.0"


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
