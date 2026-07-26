"""Tail incrémental de Game.log — lecture seule, jamais d'écriture ni de déplacement.

Même pattern d'état persisté (offset, détection de rotation) que
`uexinfo.ocr.log_parser.LogParser`, appliqué ici à Game.log au lieu du log
SC-Datarunner.
"""
from __future__ import annotations

import json
from pathlib import Path

import appdirs

from uexinfo.gamelog.parser import GameLogEvent, parse_lines

_STATE_FILE = Path(appdirs.user_data_dir("uexinfo")) / "game_log_state.json"


class GameLogTail:
    def __init__(self, log_path: Path | str):
        self.log_path = Path(log_path)

    def _load_state(self) -> dict:
        if _STATE_FILE.exists():
            try:
                with open(_STATE_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_state(self, offset: int, mtime: float) -> None:
        state = self._load_state()
        state[str(self.log_path)] = {"offset": offset, "mtime": mtime}
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)

    def reset_offset(self) -> None:
        self._save_state(0, 0.0)

    def parse_new(self) -> list[GameLogEvent]:
        """Lit les nouvelles lignes depuis le dernier offset et retourne les événements.

        Si le fichier a rétréci depuis le dernier appel (le jeu retruncate
        Game.log à chaque lancement, l'ancien contenu partant dans
        logbackups\\), on repart de 0 — c'est une nouvelle session.
        """
        if not self.log_path.is_file():
            return []

        entry = self._load_state().get(str(self.log_path), {})
        saved_offset = entry.get("offset", 0)

        stat = self.log_path.stat()
        current_size = stat.st_size

        if current_size < saved_offset:
            saved_offset = 0

        # Lecture partagée : Star Citizen garde le fichier ouvert en écriture en
        # continu pendant qu'on lit — ouverture standard en lecture seule, sans
        # verrou exclusif, ce qui est déjà le comportement par défaut de Python
        # sous Windows pour un accès en lecture seule.
        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            f.seek(saved_offset)
            new_lines = f.readlines()
            new_offset = f.tell()

        self._save_state(new_offset, stat.st_mtime)

        if not new_lines:
            return []
        return parse_lines(new_lines)

    def parse_all(self) -> list[GameLogEvent]:
        """Relit tout le fichier sans toucher l'offset persisté.

        Utilisé pour rattraper un signal qui ne se répète pas souvent (ex: le
        shard PU, écrit une seule fois par connexion) au (re)démarrage de
        l'app, quand l'offset incrémental a déjà dépassé sa dernière occurrence
        — sinon plus aucune valeur n'apparaît tant que le jeu ne se reconnecte
        pas une nouvelle fois.
        """
        if not self.log_path.is_file():
            return []
        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return parse_lines(lines)
