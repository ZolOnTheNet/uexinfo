"""Gestion des voyages — stockage JSON, session, rétention."""
from __future__ import annotations

import json
import time
from pathlib import Path

import appdirs

from uexinfo.models.voyage import Voyage, VoyageStep

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

    # ── Gestion des étapes ─────────────────────────────────────────────────────

    def add_mission_to_step(self, voyage: Voyage, mission_id: int, step_number: int,
                            departure: str | None = None) -> bool:
        """Ajoute une mission à l'étape N (la crée si nécessaire). Retourne True si ajouté."""
        step = voyage.get_or_create_step(step_number, departure)
        if mission_id not in step.mission_ids:
            step.mission_ids.append(mission_id)
            # Sync mission_ids plat pour compatibilité
            self._sync_flat_ids(voyage)
            self.update(voyage)
            return True
        return False

    def move_mission(self, voyage: Voyage, mission_id: int,
                     from_step: int, to_step: int,
                     departure: str | None = None) -> bool:
        """Déplace une mission d'une étape à une autre. Retourne True si réussi."""
        src = voyage.get_step(from_step)
        if src is None or mission_id not in src.mission_ids:
            return False
        src.mission_ids.remove(mission_id)
        dst = voyage.get_or_create_step(to_step, departure)
        if mission_id not in dst.mission_ids:
            dst.mission_ids.append(mission_id)
        self._sync_flat_ids(voyage)
        self.update(voyage)
        return True

    def remove_step(self, voyage: Voyage, step_number: int) -> bool:
        """Supprime une étape (et ses missions du voyage). Retourne True si supprimée."""
        step = voyage.get_step(step_number)
        if step is None:
            return False
        voyage.steps.remove(step)
        self._sync_flat_ids(voyage)
        self.update(voyage)
        return True

    def compact_steps(self, voyage: Voyage) -> int:
        """Supprime les étapes vides et renumérote. Retourne le nb d'étapes supprimées."""
        empty = [s for s in voyage.steps if not s.mission_ids]
        for s in empty:
            voyage.steps.remove(s)
        # Renumérote
        for i, s in enumerate(voyage.steps, 1):
            s.number = i
        self._sync_flat_ids(voyage)
        self.update(voyage)
        return len(empty)

    def _sync_flat_ids(self, voyage: Voyage) -> None:
        """Synchronise mission_ids plat depuis les étapes."""
        voyage.mission_ids = voyage.all_mission_ids

    def get_step_departure(self, voyage: Voyage, step_number: int, mm) -> str | None:
        """Inférence du lieu de départ d'une étape.

        Ordre de priorité :
        1. Lieu de départ explicite de l'étape
        2. Destination majoritaire de l'étape précédente
        3. Point de départ global du voyage
        4. None (le caller affichera un avertissement)
        """
        step = voyage.get_step(step_number)
        if step and step.departure:
            return step.departure

        if step_number > 1:
            prev = voyage.get_step(step_number - 1)
            if prev and prev.mission_ids:
                # Destination la plus fréquente de l'étape précédente
                from collections import Counter
                dsts: list[str] = []
                for mid in prev.mission_ids:
                    m = mm.get(str(mid))
                    if m:
                        dsts.extend(m.all_destinations)
                if dsts:
                    return Counter(dsts).most_common(1)[0][0]

        return voyage.departure

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
