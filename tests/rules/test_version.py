"""Décision D3 (docs/ai/DECISIONS.md) — versions SC et changement d'univers."""
import pytest

from uexinfo.rules.version import (
    parse_version, pick_by_version, universe_question_needed, version_marker, watch_active,
)


@pytest.mark.parametrize("text,expected", [
    ("4.10.1", (4, 10, 1)), ("4.10", (4, 10, 0)), ("Alpha 4.9.2-live", (4, 9, 2)),
    ("", None), (None, None), ("abc", None),
])
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize("old,new,expected", [
    ("4.10.0", "4.10.1", False),   # patch : pas de question
    ("4.10.1", "4.11.0", True),    # mineur : question
    ("4.9", "4.10", True),         # 4.9 → 4.10 n'est pas un tri alphabétique
    ("4.10", "5.0", True),
    (None, "4.10", False),
])
def test_universe_question_needed(old, new, expected):
    assert universe_question_needed(old, new) is expected


@pytest.mark.parametrize("data,current,expected", [
    ("4.9.2", "4.10.1", "v4.9"),
    ("4.10.0", "4.10.1", ""),      # même majeur.mineur : pas de marqueur
    ("4.10", "4.10", ""),
    (None, "4.10", ""),
])
def test_version_marker(data, current, expected):
    assert version_marker(data, current) == expected


def test_pick_by_version_prefers_newest():
    rows = [{"sc_version": "4.9", "p": 1}, {"sc_version": "4.10.1", "p": 2}, {"p": 3}]
    assert pick_by_version(rows)["p"] == 2
    assert pick_by_version([{"p": 3}, {"sc_version": "4.8", "p": 4}])["p"] == 4
    assert pick_by_version([]) is None


def test_watch_lasts_7_days_after_last_change():
    day = 86400
    assert watch_active(0, None, 6 * day) is True
    assert watch_active(0, None, 7 * day) is False
    assert watch_active(0, 5 * day, 11 * day) is True   # un changement relance les 7 jours
