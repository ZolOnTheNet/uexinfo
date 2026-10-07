"""D10 — nettoyer la base sans trou : terminaux fermés écartés, version courante ou précédente."""
import json
from pathlib import Path
from types import SimpleNamespace

from uexinfo.cache.data_manager import clean_price_rows
from uexinfo.cache.manager import CacheManager, _flag

UEX = Path(__file__).parents[1] / "fixtures" / "uex"


def test_flag_keeps_zero():
    # bug corrigé : int(0 or 1) donnait 1, aucun terminal n'était jamais « fermé »
    assert _flag(0) == 0 and _flag("0") == 0 and _flag(None, default=1) == 1 and _flag(1) == 1


def test_closed_terminals_are_set_aside():
    raw = json.loads((UEX / "terminals.json").read_text(encoding="utf-8"))
    cm = CacheManager.__new__(CacheManager)
    cm.terminals = [CacheManager._parse_terminal(d) for d in raw]
    cm.closed_terminals = []
    cm._split_closed_terminals()
    names = {t.name for t in cm.terminals}
    closed = {t.name for t in cm.closed_terminals}
    assert "Admin - Seraphim" in names
    assert "INS Jericho - Pyro Gateway" in closed and "INS Jericho - Pyro Gateway" not in names
    assert all(t.is_available == 0 for t in cm.closed_terminals)


def test_clean_price_rows():
    ctx = SimpleNamespace(
        cache=SimpleNamespace(closed_terminals=[SimpleNamespace(id=257)]),
        evolution=SimpleNamespace(current_version="4.10.1"),
    )
    rows = [
        {"id_terminal": 259, "game_version": "4.10.1", "p": "courant"},
        {"id_terminal": 263, "game_version": "4.9.2", "p": "précédent"},   # gardé : pas de trou
        {"id_terminal": 264, "game_version": "4.8.3", "p": "trop vieux"},
        {"id_terminal": 257, "game_version": "4.10.1", "p": "terminal fermé"},
    ]
    assert [r["p"] for r in clean_price_rows(rows, ctx)] == ["courant", "précédent"]


def test_scans_survive_a_version_change(tmp_path, monkeypatch):
    from uexinfo.cache import scan_prices
    store = scan_prices.ScanPriceStore.__new__(scan_prices.ScanPriceStore)
    import time
    now = time.time()
    data = {"259": {
        "a": {"timestamp": now, "sc_version": "4.10.1", "sc_env": "live", "c": "courant"},
        "b": {"timestamp": now, "sc_version": "4.9.0", "sc_env": "live", "c": "précédent"},
        "c": {"timestamp": now, "sc_version": "4.8.0", "sc_env": "live", "c": "trop vieux"},
    }}
    store._load = lambda: data
    assert sorted(r["c"] for r in store.get_rows("259", sc_version="4.10.1")) == ["courant", "précédent"]
    # jour de patch : la config passe en 4.11, les scans 4.10 restent visibles
    assert [r["c"] for r in store.get_rows("259", sc_version="4.11.0")] == ["courant"]
