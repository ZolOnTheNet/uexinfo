"""Lecture de Game.log (I/O) : dernières lignes, suivi incrémental, chemin du fichier.

Tolère l'absence du fichier et sa troncature (le jeu le vide à chaque lancement).
Lecture seule — jamais d'écriture dans le dossier du jeu.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

ENCODING = "utf-8"
# Vérifié (4.10, Windows FR) : le jeu écrit certaines lignes dans la page de code
# Windows (« Entr\xe9e ligne »), pas en UTF-8. On tente UTF-8, sinon cp1252.
FALLBACK_ENCODING = "cp1252"


def decode(data: bytes) -> str:
    try:
        return data.decode(ENCODING)
    except UnicodeDecodeError:
        return data.decode(FALLBACK_ENCODING, errors="replace")


def game_log_path(cfg: dict) -> Path | None:
    """Game.log de l'environnement actif (live/ptu) selon [gamelog] de config.toml."""
    gl = cfg.get("gamelog", {})
    env = cfg.get("version", {}).get("active", "live")
    install = gl.get(f"install_path_{env}", "") or gl.get("install_path_live", "")
    return Path(install) / "Game.log" if install else None


def read_lines(path: Path | str) -> list[str]:
    with open(path, "rb") as f:
        return [decode(l).rstrip("\r\n") for l in f]


def tail_lines(path: Path | str, n: int) -> list[str]:
    with open(path, "rb") as f:
        return [decode(l).rstrip("\r\n") for l in deque(f, maxlen=n)]


class LogFollower:
    """Suivi « tail -f » : `poll()` renvoie les lignes complètes ajoutées depuis l'appel précédent."""

    def __init__(self, path: Path | str, from_end: bool = True):
        self.path = Path(path)
        self.offset = 0
        self._partial = b""
        if from_end and self.path.is_file():
            self.offset = self.path.stat().st_size

    def poll(self) -> list[str]:
        if not self.path.is_file():
            return []
        size = self.path.stat().st_size
        if size < self.offset:            # fichier tronqué : nouvelle session de jeu
            self.offset, self._partial = 0, b""
        if size == self.offset:
            return []
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            chunk = f.read(size - self.offset)
        self.offset = size
        lines = (self._partial + chunk).split(b"\n")
        self._partial = lines.pop()      # dernière ligne peut-être incomplète
        return [decode(l).rstrip("\r") for l in lines]
