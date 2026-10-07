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
    ("4.11", "4.10", False),       # retour en arrière (PTU → LIVE) : pas de question
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


from uexinfo.rules.version import diff_ids, entry_valid_for_universe, minor_key


def test_minor_key():
    assert minor_key("4.10.1") == "4.10"
    assert minor_key(None) == ""


@pytest.mark.parametrize("entry,universe,expected", [
    ("4.6", None, True),        # aucun changement déclaré : tout reste valable
    ("4.6", "4.10.1", False),   # produit avant le changement d'univers
    ("4.10.1", "4.10.1", True),
    ("4.11", "4.10.1", True),
    ("", "4.10", False),        # version inconnue après un changement : re-télécharger
])
def test_entry_valid_for_universe(entry, universe, expected):
    assert entry_valid_for_universe(entry, universe) is expected


def test_diff_ids():
    old = {"terminals": [1, 2, 3]}
    new = {"terminals": [2, 3, 4], "cities": [9]}
    assert diff_ids(old, new) == {"added": {"terminals": [4]}, "removed": {"terminals": [1]}}


# ── D10 : nettoyer sans trou — version courante ou, au pire, la précédente ────
from uexinfo.rules.version import kept_versions, keep_recent_rows


def test_kept_versions_current_and_previous_present():
    assert kept_versions("4.10.1", ["4.10.1", "4.9.2", "4.8.3"]) == {(4, 10), (4, 9)}
    # la « précédente » est la plus récente présente sous la courante (ici 4.8)
    assert kept_versions("4.10.1", ["4.10.1", "4.8.3"]) == {(4, 10), (4, 8)}
    # jour du patch : UEX n'a encore que des 4.10 → on garde 4.10 (pas de trou)
    assert kept_versions("4.11.0", ["4.10.1", "4.9.2"]) == {(4, 11), (4, 10)}
    assert kept_versions(None, ["4.9", "4.10.1"]) == {(4, 10), (4, 9)}


def test_keep_recent_rows():
    rows = [{"p": 1, "game_version": "4.10.1"}, {"p": 2, "game_version": "4.9.0"},
            {"p": 3, "game_version": "4.8.3"}, {"p": 4}]
    assert [r["p"] for r in keep_recent_rows(rows, "4.10.1")] == [1, 2, 4]
    assert keep_recent_rows([], "4.10") == []
