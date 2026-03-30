"""Tests pour les fonctions utilitaires du tableau de bord /voyage tb."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from uexinfo.models.voyage import Voyage, VoyageStep


# ── Import des fonctions testées ──────────────────────────────────────────────

from uexinfo.cli.commands.voyage import (
    _parse_step_number,
    _parse_departure,
    _infer_step_departure,
)


class TestParseStepNumber:
    def test_dash_n_format(self):
        assert _parse_step_number(["-2"]) == 2
        assert _parse_step_number(["-3"]) == 3
        assert _parse_step_number(["-1"]) == 1

    def test_integer_alone(self):
        assert _parse_step_number(["2"]) == 2
        assert _parse_step_number(["5"]) == 5

    def test_step_flag(self):
        assert _parse_step_number(["-step", "3"]) == 3
        assert _parse_step_number(["--step", "4"]) == 4

    def test_no_step_number(self):
        assert _parse_step_number([]) is None
        assert _parse_step_number(["Lorville"]) is None
        assert _parse_step_number(["list"]) is None

    def test_step_in_mixed_args(self):
        assert _parse_step_number(["Lorville", "-2"]) == 2
        assert _parse_step_number(["list", "-3"]) == 3


class TestParseDeparture:
    def test_simple_word(self):
        assert _parse_departure(["Lorville"]) == "Lorville"

    def test_underscore_becomes_space(self):
        assert _parse_departure(["Port_Tressler"]) == "Port Tressler"

    def test_skip_flags(self):
        assert _parse_departure(["--scu"]) is None
        assert _parse_departure(["--benef"]) is None

    def test_skip_reserved_words(self):
        assert _parse_departure(["list"]) is None
        assert _parse_departure(["compact"]) is None
        assert _parse_departure(["graph"]) is None

    def test_skip_numbers(self):
        assert _parse_departure(["2"]) is None

    def test_skip_dash_n(self):
        assert _parse_departure(["-2"]) is None

    def test_mixed_args_returns_first_non_skip(self):
        result = _parse_departure(["-2", "Lorville"])
        assert result == "Lorville"

    def test_no_departure(self):
        assert _parse_departure([]) is None
        assert _parse_departure(["-1", "--scu"]) is None


class TestInferStepDeparture:
    def _make_ctx(self, voyage, mm=None, vm=None):
        ctx = MagicMock()
        ctx.mission_manager = mm or MagicMock()
        ctx.voyage_manager = vm or MagicMock()
        return ctx

    def test_uses_explicit_departure(self):
        v = Voyage(id=1, name="test")
        step = v.get_or_create_step(1, departure="Lorville")
        mm = MagicMock()
        vm_mock = MagicMock()
        vm_mock.get_step_departure.return_value = "Lorville"
        ctx = self._make_ctx(v, mm, vm_mock)
        result = _infer_step_departure(v, 1, ctx)
        assert result == "Lorville"
        vm_mock.get_step_departure.assert_called_once_with(v, 1, mm)

    def test_uses_previous_step_when_no_explicit(self):
        v = Voyage(id=1, name="test", departure="Area18")
        mm = MagicMock()
        vm_mock = MagicMock()
        vm_mock.get_step_departure.return_value = "Area18"
        ctx = self._make_ctx(v, mm, vm_mock)
        result = _infer_step_departure(v, 2, ctx)
        assert result == "Area18"

    def test_returns_none_when_no_info(self):
        v = Voyage(id=1, name="test")
        mm = MagicMock()
        vm_mock = MagicMock()
        vm_mock.get_step_departure.return_value = None
        ctx = self._make_ctx(v, mm, vm_mock)
        result = _infer_step_departure(v, 1, ctx)
        assert result is None
