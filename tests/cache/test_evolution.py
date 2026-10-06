"""/evolution — mémoire des versions et surveillance (décision D3)."""
from types import SimpleNamespace

from uexinfo.cache.evolution import EvolutionStore, collect_ids

DAY = 86400


def test_first_version_opens_no_question(tmp_path):
    s = EvolutionStore(tmp_path / "e.json")
    assert s.observe_version("4.10.1") is False
    assert s.pending == ""


def test_patch_does_not_ask_minor_does(tmp_path):
    s = EvolutionStore(tmp_path / "e.json")
    s.observe_version("4.10.0")
    assert s.observe_version("4.10.1") is False
    assert s.observe_version("4.11.0") is True
    assert s.pending == "4.11"


def test_answer_non_is_remembered_for_the_minor_version(tmp_path):
    p = tmp_path / "e.json"
    s = EvolutionStore(p)
    s.observe_version("4.10.0"); s.observe_version("4.11.0")
    s.answer(changed=False, now=0)
    assert s.pending == "" and s.universe_version is None and not s.watching(0)
    s = EvolutionStore(p)                       # relu depuis le disque
    s.observe_version("4.10.9"); s.observe_version("4.11.2")
    assert s.pending == ""                      # 4.11 déjà répondu
    s.observe_version("4.12.0")
    assert s.pending == "4.12"


def test_answer_oui_starts_7_day_watch(tmp_path):
    s = EvolutionStore(tmp_path / "e.json")
    s.observe_version("4.11.0")
    s.answer(changed=True, now=0)
    assert s.universe_version == "4.11.0"
    assert s.watching(6 * DAY) and not s.watching(7 * DAY)


def test_check_detects_new_location_and_extends_watch(tmp_path):
    s = EvolutionStore(tmp_path / "e.json")
    s.observe_version("4.11.0")
    assert s.check({"terminals": [1, 2]}, now=0) == {"added": {}, "removed": {}}   # référence
    s.answer(changed=True, now=0)
    diff = s.check({"terminals": [1, 2, 3]}, now=5 * DAY)
    assert diff["added"] == {"terminals": [3]}
    assert s.watching(11 * DAY) and not s.watching(12 * DAY)


def test_collect_ids_skips_empty():
    cache = SimpleNamespace(terminals=[SimpleNamespace(id=5), SimpleNamespace(id=2)], cities=[])
    assert collect_ids(cache) == {"terminals": [5, 2]}


def test_price_cache_respects_universe_version(tmp_path, monkeypatch):
    from uexinfo.cache import price_cache as pc
    monkeypatch.setattr(pc, "CACHE_FILE", tmp_path / "p.json", raising=False)
    cache = pc.PriceCache.__new__(pc.PriceCache)
    pc.PriceCache.__init__(cache)
    cache._loaded = True
    cache._mem = {}
    cache.current_version = "4.6"
    cache._save = lambda: None
    cache["rd_1"] = (0, [{"d": 1}])
    assert cache.get("rd_1") is not None          # aucun changement déclaré
    cache.universe_version = "4.11.0"
    assert cache.get("rd_1") is None              # produit avant le changement
    cache.current_version = "4.11.0"
    cache["rd_1"] = (0, [{"d": 2}])
    assert cache.get("rd_1")[1] == [{"d": 2}]
