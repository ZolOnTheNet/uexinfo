"""Tests pour les modèles VoyageStep et Voyage."""
from __future__ import annotations

import pytest
from uexinfo.models.voyage import Voyage, VoyageStep


class TestVoyageStep:
    def test_to_dict(self):
        step = VoyageStep(number=1, departure="Lorville", mission_ids=[10, 20])
        d = step.to_dict()
        assert d["number"] == 1
        assert d["departure"] == "Lorville"
        assert d["mission_ids"] == [10, 20]
        assert d["empty_display_count"] == 0

    def test_from_dict(self):
        d = {"number": 2, "departure": "GrimHEX", "mission_ids": [5], "empty_display_count": 1}
        step = VoyageStep.from_dict(d)
        assert step.number == 2
        assert step.departure == "GrimHEX"
        assert step.mission_ids == [5]
        assert step.empty_display_count == 1

    def test_from_dict_defaults(self):
        step = VoyageStep.from_dict({})
        assert step.number == 1
        assert step.departure is None
        assert step.mission_ids == []
        assert step.empty_display_count == 0

    def test_roundtrip(self):
        step = VoyageStep(number=3, departure="Port Tressler", mission_ids=[1, 2, 3])
        assert VoyageStep.from_dict(step.to_dict()).departure == "Port Tressler"


class TestVoyageMigration:
    def test_migration_old_format_creates_step1(self):
        """Ancien format sans 'steps' → créer étape 1 automatiquement."""
        d = {
            "id": 1,
            "name": "trajet-1",
            "mission_ids": [10, 20, 30],
        }
        v = Voyage.from_dict(d)
        assert len(v.steps) == 1
        assert v.steps[0].number == 1
        assert v.steps[0].mission_ids == [10, 20, 30]

    def test_new_format_with_steps(self):
        """Nouveau format avec steps → pas de migration."""
        d = {
            "id": 2,
            "name": "trajet-2",
            "steps": [
                {"number": 1, "departure": "Area18", "mission_ids": [1]},
                {"number": 2, "departure": "GrimHEX", "mission_ids": [2, 3]},
            ],
            "mission_ids": [1, 2, 3],
        }
        v = Voyage.from_dict(d)
        assert len(v.steps) == 2
        assert v.steps[0].departure == "Area18"
        assert v.steps[1].mission_ids == [2, 3]

    def test_empty_voyage_no_steps(self):
        """Voyage vide → pas d'étapes créées."""
        d = {"id": 3, "name": "vide", "mission_ids": []}
        v = Voyage.from_dict(d)
        assert len(v.steps) == 0


class TestVoyageAllMissionIds:
    def test_all_mission_ids_with_steps(self):
        v = Voyage(id=1, name="test")
        v.steps = [
            VoyageStep(number=1, mission_ids=[1, 2]),
            VoyageStep(number=2, mission_ids=[3, 4]),
        ]
        assert v.all_mission_ids == [1, 2, 3, 4]

    def test_all_mission_ids_dedup(self):
        v = Voyage(id=1, name="test")
        v.steps = [
            VoyageStep(number=1, mission_ids=[1, 2]),
            VoyageStep(number=2, mission_ids=[2, 3]),  # 2 est en double
        ]
        ids = v.all_mission_ids
        assert ids.count(2) == 1  # dédupliqué
        assert set(ids) == {1, 2, 3}

    def test_all_mission_ids_fallback_flat(self):
        """Sans étapes → utilise mission_ids plat."""
        v = Voyage(id=1, name="test", mission_ids=[5, 6, 7])
        assert v.all_mission_ids == [5, 6, 7]


class TestVoyageGetOrCreateStep:
    def test_get_existing_step(self):
        v = Voyage(id=1, name="test")
        step = VoyageStep(number=1, mission_ids=[10])
        v.steps = [step]
        found = v.get_step(1)
        assert found is step

    def test_get_nonexistent_step_returns_none(self):
        v = Voyage(id=1, name="test")
        assert v.get_step(99) is None

    def test_create_step_if_not_exists(self):
        v = Voyage(id=1, name="test")
        step = v.get_or_create_step(1, departure="Lorville")
        assert len(v.steps) == 1
        assert step.number == 1
        assert step.departure == "Lorville"

    def test_get_or_create_idempotent(self):
        v = Voyage(id=1, name="test")
        s1 = v.get_or_create_step(1, "A")
        s2 = v.get_or_create_step(1, "B")  # ne doit pas recréer
        assert s1 is s2
        assert len(v.steps) == 1

    def test_steps_sorted_after_create(self):
        v = Voyage(id=1, name="test")
        v.get_or_create_step(3)
        v.get_or_create_step(1)
        v.get_or_create_step(2)
        assert [s.number for s in v.steps] == [1, 2, 3]

    def test_next_step_number(self):
        v = Voyage(id=1, name="test")
        assert v.next_step_number() == 1
        v.get_or_create_step(1)
        v.get_or_create_step(3)
        assert v.next_step_number() == 4
