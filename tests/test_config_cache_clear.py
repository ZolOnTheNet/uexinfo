"""/config cache clear <type> : un seul type de données à la fois.

Régression : l'ancienne version faisait `rmtree` de tout le dossier utilisateur
(missions, voyages, scans, notes, historique) pour « vider le cache ».
"""
import json
from types import SimpleNamespace

import pytest

import uexinfo.cache.mission_manager as mission_manager
import uexinfo.cache.notes_manager as notes_manager
import uexinfo.cache.scan_prices as scan_prices
import uexinfo.cache.voyage_manager as voyage_manager
import uexinfo.cli.history as history
from uexinfo.cli.commands import config as config_cmd


@pytest.fixture
def data(tmp_path, monkeypatch):
    """Dossier utilisateur fictif, rempli d'un exemple de chaque type de données."""
    files = {
        "missions": tmp_path / "missions.json",
        "voyages": tmp_path / "voyages.json",
        "scans": tmp_path / "scan_prices.json",
        "notes": tmp_path / "notes.json",
        "historique": tmp_path / "history.jsonl",
    }
    monkeypatch.setattr(mission_manager, "DATA_FILE", files["missions"])
    monkeypatch.setattr(voyage_manager, "DATA_FILE", files["voyages"])
    monkeypatch.setattr(scan_prices, "_STORE_FILE", files["scans"])
    monkeypatch.setattr(notes_manager, "_STORE_FILE", files["notes"])
    monkeypatch.setattr(history, "_HISTORY_PATH", files["historique"])

    files["missions"].write_text(json.dumps({"missions": [], "next_id": 1}), encoding="utf-8")
    files["voyages"].write_text(json.dumps({"voyages": [], "active_id": None, "next_id": 1}), encoding="utf-8")
    files["scans"].write_text(json.dumps({"seraphim": {"agricium": {"price_buy": 1}}}), encoding="utf-8")
    files["notes"].write_text(json.dumps({"next_id": 2, "notes": [{"id": 1, "location": "Lorville", "message": "x"}]}),
                              encoding="utf-8")
    files["historique"].write_text('{"cmd": "/help"}\n{"cmd": "/trade"}\n', encoding="utf-8")

    ctx = SimpleNamespace(
        mission_manager=mission_manager.MissionManager(),
        voyage_manager=voyage_manager.VoyageManager(),
        last_scan="scan", scan_history=["scan"],
    )
    return files, ctx


def _snapshot(files):
    return {k: p.read_text(encoding="utf-8") if p.exists() else None for k, p in files.items()}


def test_without_type_deletes_nothing(data):
    files, ctx = data
    before = _snapshot(files)
    config_cmd._cache(["clear"], ctx)
    assert _snapshot(files) == before


def test_unknown_type_deletes_nothing(data):
    files, ctx = data
    before = _snapshot(files)
    config_cmd._cache(["clear", "tout"], ctx)
    assert _snapshot(files) == before


@pytest.mark.parametrize("kind", ["notes", "scans", "historique", "history"])
def test_clears_only_one_type(data, kind):
    files, ctx = data
    target = {"history": "historique"}.get(kind, kind)
    before = _snapshot(files)
    config_cmd._cache(["clear", kind], ctx)
    after = _snapshot(files)
    assert after[target] != before[target]
    assert {k: v for k, v in after.items() if k != target} == {k: v for k, v in before.items() if k != target}


def test_contents_after_clear(data):
    files, ctx = data
    config_cmd._cache(["clear", "notes"], ctx)
    config_cmd._cache(["clear", "scans"], ctx)
    config_cmd._cache(["clear", "historique"], ctx)
    assert json.loads(files["notes"].read_text(encoding="utf-8")) == {"next_id": 1, "notes": []}
    assert json.loads(files["scans"].read_text(encoding="utf-8")) == {}
    assert not files["historique"].exists()
    assert ctx.last_scan is None and ctx.scan_history == []


def test_missions_and_voyages(data):
    files, ctx = data
    config_cmd._cache(["clear", "voyages"], ctx)
    assert json.loads(files["voyages"].read_text(encoding="utf-8"))["voyages"] == []
    assert files["missions"].exists()
    config_cmd._cache(["clear", "missions"], ctx)
    assert json.loads(files["missions"].read_text(encoding="utf-8"))["missions"] == []
    assert files["notes"].exists()


def test_api_does_not_touch_user_data(data, monkeypatch):
    files, ctx = data
    calls = []
    monkeypatch.setattr("uexinfo.cli.commands.refresh._refresh_static", lambda c: calls.append("static"))
    ctx._price_cache = SimpleNamespace(clear=lambda: calls.append("prix"))
    before = _snapshot(files)
    config_cmd._cache(["clear", "api"], ctx)
    assert calls == ["prix", "static"]
    assert _snapshot(files) == before
