"""Tests pour VoyageManager — gestion des étapes."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from uexinfo.models.voyage import Voyage, VoyageStep


def _make_manager():
    """Crée un VoyageManager sans persistance disque (en mémoire)."""
    from uexinfo.cache.voyage_manager import VoyageManager
    vm = VoyageManager.__new__(VoyageManager)
    vm.voyages = []
    vm.active_id = None
    vm._next_id = 1
    vm._session_id = 1
    vm._retention = 24
    return vm


def _make_voyage(mission_ids=None) -> Voyage:
    v = Voyage(id=1, name="test")
    if mission_ids:
        v.mission_ids = list(mission_ids)
    return v


class TestAddMissionToStep:
    def test_add_creates_step_if_needed(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        added = vm.add_mission_to_step(v, mission_id=10, step_number=1, departure="Lorville")
        assert added is True
        assert len(v.steps) == 1
        assert v.steps[0].number == 1
        assert 10 in v.steps[0].mission_ids

    def test_add_syncs_flat_ids(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        vm.add_mission_to_step(v, 10, 1)
        vm.add_mission_to_step(v, 20, 1)
        vm.add_mission_to_step(v, 30, 2)
        assert set(v.mission_ids) == {10, 20, 30}

    def test_add_duplicate_returns_false(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        vm.add_mission_to_step(v, 10, 1)
        result = vm.add_mission_to_step(v, 10, 1)  # déjà présent
        assert result is False


class TestMoveMission:
    def test_move_between_steps(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        vm.add_mission_to_step(v, 10, 1)
        ok = vm.move_mission(v, mission_id=10, from_step=1, to_step=2)
        assert ok is True
        assert 10 not in v.steps[0].mission_ids
        step2 = v.get_step(2)
        assert step2 is not None
        assert 10 in step2.mission_ids

    def test_move_nonexistent_returns_false(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        ok = vm.move_mission(v, mission_id=99, from_step=1, to_step=2)
        assert ok is False

    def test_move_syncs_flat_ids(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        vm.add_mission_to_step(v, 10, 1)
        vm.move_mission(v, 10, from_step=1, to_step=2)
        assert 10 in v.mission_ids  # toujours dans le voyage


class TestCompactSteps:
    def test_compact_removes_empty_steps(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        v.get_or_create_step(1)  # vide
        vm.add_mission_to_step(v, 10, 2)
        v.get_or_create_step(3)  # vide
        n = vm.compact_steps(v)
        assert n == 2
        assert len(v.steps) == 1

    def test_compact_renumbers(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        vm.add_mission_to_step(v, 10, 1)
        v.get_or_create_step(2)  # vide
        vm.add_mission_to_step(v, 20, 3)
        vm.compact_steps(v)
        # Après compact : étape 1 (missions [10]) et étape 2 (missions [20])
        assert [s.number for s in v.steps] == [1, 2]

    def test_compact_no_empty(self):
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        vm.add_mission_to_step(v, 10, 1)
        n = vm.compact_steps(v)
        assert n == 0


class TestGetStepDeparture:
    def test_explicit_step_departure(self):
        """Le lieu de départ explicite de l'étape est prioritaire."""
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        step = v.get_or_create_step(1, departure="Lorville")
        mm = MagicMock()
        result = vm.get_step_departure(v, 1, mm)
        assert result == "Lorville"

    def test_global_departure_fallback(self):
        """Fallback sur le départ global du voyage."""
        vm = _make_manager()
        v = _make_voyage()
        v.departure = "Area18"
        vm.voyages = [v]
        v.get_or_create_step(1)  # sans departure explicite
        mm = MagicMock()
        result = vm.get_step_departure(v, 1, mm)
        assert result == "Area18"

    def test_infer_from_previous_step_destinations(self):
        """Départ déduit des destinations de l'étape précédente."""
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]

        # Étape 1 : missions qui vont à "GrimHEX"
        mock_mission = MagicMock()
        mock_mission.all_destinations = ["GrimHEX", "GrimHEX", "GrimHEX"]

        step1 = v.get_or_create_step(1, departure="Lorville")
        step1.mission_ids = [10]
        v.get_or_create_step(2)  # sans departure explicite

        mm = MagicMock()
        mm.get = MagicMock(return_value=mock_mission)

        result = vm.get_step_departure(v, 2, mm)
        assert result == "GrimHEX"

    def test_returns_none_when_no_info(self):
        """Retourne None si aucune info disponible."""
        vm = _make_manager()
        v = _make_voyage()
        vm.voyages = [v]
        v.get_or_create_step(1)
        mm = MagicMock()
        result = vm.get_step_departure(v, 1, mm)
        assert result is None
