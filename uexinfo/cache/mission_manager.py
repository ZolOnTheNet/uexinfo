"""Gestion du groupe de missions actif — stockage JSON + analyse des synergies."""
from __future__ import annotations

import json
from pathlib import Path

import appdirs

from uexinfo.models.mission import Mission, MissionObjective

DATA_FILE = Path(appdirs.user_data_dir("uexinfo")) / "missions.json"


class MissionManager:
    """Stocke et analyse un groupe de missions en cours."""

    def __init__(self) -> None:
        self.missions: list[Mission] = []
        self._next_id: int = 1
        self._load()

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not DATA_FILE.exists():
            return
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            self.missions = [Mission.from_dict(m) for m in data.get("missions", [])]
            self._next_id = data.get("next_id", 1)
        except Exception:
            pass

    def save(self) -> None:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps({
                "missions": [m.to_dict() for m in self.missions],
                "next_id":  self._next_id,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, mission: Mission) -> Mission:
        mission.id = self._next_id
        self._next_id += 1
        self.missions.append(mission)
        self.save()
        return mission

    def get(self, id_or_name: str) -> Mission | None:
        try:
            mid = int(id_or_name)
            return next((m for m in self.missions if m.id == mid), None)
        except ValueError:
            q = id_or_name.lower()
            return next((m for m in self.missions if q in m.name.lower()), None)

    def remove(self, id_or_name: str) -> bool:
        m = self.get(id_or_name)
        if not m:
            return False
        self.missions.remove(m)
        self.save()
        return True

    def clear(self) -> int:
        n = len(self.missions)
        self.missions.clear()
        self._next_id = 1
        self.save()
        return n

    def update(self, mission: Mission) -> None:
        for i, m in enumerate(self.missions):
            if m.id == mission.id:
                self.missions[i] = mission
                self.save()
                return

    # ── Synergies ─────────────────────────────────────────────────────────────

    def synergies(self, mission: Mission) -> list[str]:
        """Synergies avec toutes les autres missions du catalogue."""
        others = [m for m in self.missions if m.id != mission.id]
        return self._compute_synergies(mission, others)

    def synergies_for_voyage(self, mission: Mission, mission_ids: list[int]) -> list[str]:
        """Synergies avec les autres missions d'un voyage précis."""
        others = [m for m in self.missions
                  if m.id != mission.id and m.id in mission_ids]
        return self._compute_synergies(mission, others)

    def _compute_synergies(self, mission: Mission, others: list) -> list[str]:
        if not others:
            return []
        flags: list[str] = []
        m_srcs = set(mission.all_sources)
        m_dsts = set(mission.all_destinations)
        for o in others:
            o_srcs = set(o.all_sources)
            o_dsts = set(o.all_destinations)
            if m_srcs & o_srcs:
                flags.append("⊙")
            if m_dsts & o_dsts:
                flags.append("⊕")
            if m_dsts & o_srcs or m_srcs & o_dsts:
                flags.append("⇄")
        return list(dict.fromkeys(flags))

    # ── Résumé ────────────────────────────────────────────────────────────────

    def selected_totals(self) -> tuple[int, float, int]:
        """Retourne (nb_missions, total_scu, total_reward) des missions sélectionnées."""
        sel = [m for m in self.missions if m.is_selected]
        return len(sel), sum(m.total_scu for m in sel), sum(m.reward_uec for m in sel)
