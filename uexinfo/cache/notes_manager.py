"""Stockage persistant des notes joueur par lieu."""
from __future__ import annotations

import json
import time
from pathlib import Path

import appdirs

_STORE_FILE = Path(appdirs.user_data_dir("uexinfo")) / "notes.json"


class NoteStore:
    """Lit/écrit les notes par lieu dans un fichier JSON persistant."""

    def _load(self) -> dict:
        if _STORE_FILE.exists():
            try:
                with open(_STORE_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"next_id": 1, "notes": []}

    def _write(self, data: dict) -> None:
        _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, location: str, message: str) -> int:
        """Ajoute une note. Retourne son ID."""
        data = self._load()
        note_id = data.get("next_id", 1)
        data.setdefault("notes", []).append({
            "id":        note_id,
            "location":  location,
            "message":   message,
            "timestamp": time.time(),
        })
        data["next_id"] = note_id + 1
        self._write(data)
        return note_id

    def get(self, note_id: int) -> dict | None:
        for n in self._load().get("notes", []):
            if n["id"] == note_id:
                return dict(n)
        return None

    def update(self, note_id: int, *, message: str | None = None, location: str | None = None) -> bool:
        data = self._load()
        for n in data.get("notes", []):
            if n["id"] == note_id:
                if message is not None:
                    n["message"]   = message
                    n["timestamp"] = time.time()
                if location is not None:
                    n["location"] = location
                self._write(data)
                return True
        return False

    def delete_by_id(self, note_id: int) -> bool:
        data = self._load()
        notes = data.get("notes", [])
        new_notes = [n for n in notes if n["id"] != note_id]
        if len(new_notes) == len(notes):
            return False
        data["notes"] = new_notes
        self._write(data)
        return True

    def delete_by_location(self, location: str) -> int:
        data = self._load()
        notes = data.get("notes", [])
        loc_lo = location.lower().strip()
        new_notes = [n for n in notes if n["location"].lower().strip() != loc_lo]
        count = len(notes) - len(new_notes)
        if count:
            data["notes"] = new_notes
            self._write(data)
        return count

    def list_all(self) -> list[dict]:
        return sorted(
            self._load().get("notes", []),
            key=lambda n: (n["location"].lower(), n["id"]),
        )

    def list_by_location(self, location: str) -> list[dict]:
        loc_lo = location.lower().strip()
        return [n for n in self.list_all() if n["location"].lower().strip() == loc_lo]
