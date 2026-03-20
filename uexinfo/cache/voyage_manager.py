"""Gestion des voyages — stockage JSON, session, rétention."""
from __future__ import annotations

import json
import time
from pathlib import Path

import appdirs

from uexinfo.models.voyage import Voyage

DATA_FILE = Path(appdirs.user_data_dir("uexinfo")) / "voyages.json"


def _parse_retention(value) -> tuple[str, float | int]:
    """
    Retourne ('hours', n_heures) ou ('ps', n_sessions).
    Valeurs acceptées : 24, "24", "ps", "ps:3".
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ("hours", float(value))
    if isinstance(value, str):
        v = value.strip().lower()
        if v.startswith("ps"):
            n = int(v.split(":")[1]) if ":" in v else 1
            return ("ps", n)
        try:
            return ("hours", float(v))
        except ValueError:
            pass
    return ("hours", 24.0)


class VoyageManager:
    """Stocke et gère les voyages de l'utilisateur."""

    def __init__(self, retention=24) -> None:
        self.voyages: list[Voyage] = []
        self.active_id: int | None = None
        self._next_id: int = 1
        self._session_id: int = 1
        self._retention = retention
        self._load()

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not DATA_FILE.exists():
            return
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            self.voyages    = [Voyage.from_dict(v) for v in data.get("voyages", [])]
            self.active_id  = data.get("active_id")
            self._next_id   = data.get("next_id", 1)
            self._session_id = data.get("session_id", 1)
        except Exception:
            pass

    def save(self) -> None:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps({
                "voyages":    [v.to_dict() for v in self.voyages],
                "active_id":  self.active_id,
                "next_id":    self._next_id,
                "session_id": self._session_id,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Session ───────────────────────────────────────────────────────────────

    def on_session_end(self, tbc: bool = False) -> None:
        """Appelé à la fermeture du programme. tbc=True = /quit -tbc, pas de fin de session."""
        if not tbc:
            self._session_id += 1
            self._prune()
        self.save()

    def _prune(self) -> int:
        """Supprime les voyages expirés selon la rétention configurée."""
        mode, param = _parse_retention(self._retention)
        before = len(self.voyages)
        now = time.time()

        if mode == "hours":
            cutoff = now - param * 3600
            self.voyages = [v for v in self.voyages if v.created_at >= cutoff]
        else:  # ps
            cutoff_session = self._session_id - int(param)
            self.voyages = [v for v in self.voyages if v.session_id >= cutoff_session]

        # Corriger active_id si le voyage actif a été supprimé
        if self.active_id and not self.get(str(self.active_id)):
            self.active_id = None

        return before - len(self.voyages)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def new_voyage(self, name: str | None = None, departure: str | None = None) -> Voyage:
        v = Voyage(
            id=self._next_id,
            name=name or f"trajet-{self._next_id}",
            departure=departure,
            session_id=self._session_id,
        )
        self._next_id += 1
        self.voyages.append(v)
        self.active_id = v.id
        self.save()
        return v

    def get(self, id_or_name: str) -> Voyage | None:
        try:
            vid = int(id_or_name)
            return next((v for v in self.voyages if v.id == vid), None)
        except ValueError:
            q = id_or_name.lower()
            return next((v for v in self.voyages if v.name.lower() == q), None)

    def get_active(self) -> Voyage | None:
        if self.active_id is None:
            return None
        return next((v for v in self.voyages if v.id == self.active_id), None)

    def activate(self, id_or_name: str) -> Voyage | None:
        v = self.get(id_or_name)
        if v:
            self.active_id = v.id
            self.save()
        return v

    def deactivate(self) -> None:
        self.active_id = None
        self.save()

    def remove(self, id_or_name: str) -> bool:
        v = self.get(id_or_name)
        if not v:
            return False
        if self.active_id == v.id:
            self.active_id = None
        self.voyages.remove(v)
        self.save()
        return True

    def update(self, voyage: Voyage) -> None:
        for i, v in enumerate(self.voyages):
            if v.id == voyage.id:
                self.voyages[i] = voyage
                self.save()
                return

    # ── Gestion des missions dans un voyage ───────────────────────────────────

    def add_missions(self, voyage: Voyage, mission_ids: list[int]) -> int:
        """Ajoute les IDs manquants. Retourne le nombre ajouté."""
        added = 0
        for mid in mission_ids:
            if mid not in voyage.mission_ids:
                voyage.mission_ids.append(mid)
                added += 1
        if added:
            self.update(voyage)
        return added

    def remove_mission(self, voyage: Voyage, mission_id: int) -> bool:
        if mission_id in voyage.mission_ids:
            voyage.mission_ids.remove(mission_id)
            self.update(voyage)
            return True
        return False

    # ── Copie (fusion) ────────────────────────────────────────────────────────

    def copy_to(self, source: Voyage, target_id_or_name: str | None = None) -> Voyage:
        """
        Copie source vers target (fusion des mission_ids) ou vers un nouveau voyage.
        Retourne le voyage cible.
        """
        if target_id_or_name:
            target = self.get(target_id_or_name)
            if target:
                self.add_missions(target, source.mission_ids)
                return target

        # Créer un nouveau voyage copie
        new_name = f"{source.name}-copie"
        target = Voyage(
            id=self._next_id,
            name=new_name,
            mission_ids=list(source.mission_ids),
            departure=source.departure,
            arrival=source.arrival,
            session_id=self._session_id,
        )
        self._next_id += 1
        self.voyages.append(target)
        self.save()
        return target

    # ── Noms pour le vocab overlay ────────────────────────────────────────────

    def voyage_names(self) -> list[str]:
        return [v.name for v in self.voyages]
