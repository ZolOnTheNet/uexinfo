"""Surveillance du dossier screenshots Star Citizen — Mode B."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

SC_DEFAULT_DIR = Path(
    "C:/Program Files/Roberts Space Industries/StarCitizen/LIVE/screenshots"
)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


class ScreenshotWatcher:
    def __init__(self, directory: Path, callback: Callable[[Path], None] | None = None):
        self.directory = directory
        self.callback = callback
        self._seen: set[Path] = set()
        # Initialiser avec les fichiers existants pour ne pas re-traiter l'historique
        if directory.exists():
            self._seen = {
                p for p in directory.iterdir()
                if p.suffix.lower() in _IMAGE_SUFFIXES
            }

    def poll(self) -> list[Path]:
        """Retourne les nouveaux fichiers image depuis le dernier appel."""
        if not self.directory.exists():
            return []

        new_files = []
        for p in sorted(self.directory.iterdir(), key=lambda x: x.stat().st_mtime):
            if p.suffix.lower() in _IMAGE_SUFFIXES and p not in self._seen:
                self._seen.add(p)
                new_files.append(p)
                if self.callback:
                    self.callback(p)

        return new_files

    def watch_once(self, timeout: float = 60.0, interval: float = 0.5) -> Path | None:
        """Attend le prochain screenshot (bloquant) et le retourne, ou None si timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new = self.poll()
            if new:
                return new[-1]
            time.sleep(interval)
        return None

    def latest_screenshot(self) -> Path | None:
        """Retourne le screenshot le plus récent du dossier, ou None."""
        if not self.directory.exists():
            return None
        images = [
            p for p in self.directory.iterdir()
            if p.suffix.lower() in _IMAGE_SUFFIXES
        ]
        if not images:
            return None
        return max(images, key=lambda p: p.stat().st_mtime)
