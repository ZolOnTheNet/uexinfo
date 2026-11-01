"""Journal du programme : ce qui est fait, commandes tapées, boutons cliqués, réponses, évènements.

Un fichier par jour dans le dossier des données d'uexinfo (`logs/uexinfo.log`, puis
`uexinfo.log.2026-11-01`…), gardé `[log] days` jours (7 par défaut). Tous les modules qui
écrivent avec `logging.getLogger(__name__)` (nom en `uexinfo.…`) y aboutissent. Texte seul :
jamais d'image (les captures du mode scan restent en mémoire).
"""
from __future__ import annotations

import html
import logging
import re
from pathlib import Path

log = logging.getLogger("uexinfo")


def log_dir() -> Path:
    """Dossier des journaux (`<données uexinfo>/logs`)."""
    import appdirs
    return Path(appdirs.user_data_dir("uexinfo")) / "logs"


def setup(days: int = 7) -> Path | None:
    """Ouvre le journal (une seule fois) ; chemin du fichier, ou None s'il n'a pu être ouvert."""
    from logging.handlers import TimedRotatingFileHandler
    try:
        path = log_dir() / "uexinfo.log"
        if any(getattr(h, "baseFilename", "") == str(path) for h in log.handlers):
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        h = TimedRotatingFileHandler(path, when="midnight", backupCount=max(1, int(days)),
                                     encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
        return path
    except Exception:
        return None


def path() -> Path | None:
    """Fichier du journal ouvert, ou None."""
    for h in log.handlers:
        if getattr(h, "baseFilename", ""):
            return Path(h.baseFilename)
    return None


def text_of(markup: str, limit: int = 3000) -> str:
    """Texte lisible d'une réponse HTML ou ANSI (balises et couleurs retirées), coupé à `limit`."""
    t = re.sub(r"\x1b\[[0-9;]*m", "", markup or "")
    t = re.sub(r"<(br|/tr|/p|/div|/h\d|/li)\b[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"</t[dh]>", " | ", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = "\n".join(l.rstrip() for l in t.splitlines() if l.strip())
    return t if len(t) <= limit else t[:limit] + f"\n… ({len(t) - limit} caractères de plus)"
