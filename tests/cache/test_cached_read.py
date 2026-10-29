"""Lecture UEX unique avec cache (D11, base « lecture sur UEX avec mise en cache »)."""
from types import SimpleNamespace

import pytest

from uexinfo.api.uex_client import UEXError
from uexinfo.cache import data_manager
from uexinfo.cache.data_manager import DataManager


class FakeCache:
    """Cache de prix minimal : `fresh` et `stale` séparés, écritures mémorisées."""

    def __init__(self, fresh=None, stale=None):
        self.fresh, self.stale, self.written = fresh or {}, stale or {}, {}

    def get(self, key):
        return self.fresh.get(key)

    def get_stale(self, key):
        return self.stale.get(key)

    def __setitem__(self, key, value):
        self.written[key] = value


class FakeClient:
    def __init__(self, result=None, error=False):
        self.result, self.error, self.calls = result, error, []

    def get_routes(self, **params):
        self.calls.append(params)
        if self.error:
            raise UEXError("hors ligne")
        return self.result


@pytest.fixture()
def client(monkeypatch):
    c = FakeClient(result=[{"distance": 12}])
    monkeypatch.setattr(data_manager, "shared_client", lambda: c)
    return c


def test_fresh_cache_avoids_api(client):
    ctx = SimpleNamespace(_price_cache=FakeCache(fresh={"k": (1.0, [{"x": 1}])}))
    assert DataManager.cached("k", "get_routes", ctx, id_terminal_origin=5) == [{"x": 1}]
    assert client.calls == []


def test_api_result_is_cached(client):
    ctx = SimpleNamespace(_price_cache=FakeCache())
    assert DataManager.cached("k", "get_routes", ctx, id_terminal_origin=5) == [{"distance": 12}]
    assert client.calls == [{"id_terminal_origin": 5}]
    assert ctx._price_cache.written["k"][1] == [{"distance": 12}]
    assert ctx._api_offline is False


def test_api_down_falls_back_to_stale_then_empty(client):
    client.error = True
    ctx = SimpleNamespace(_price_cache=FakeCache(stale={"k": (1.0, [{"old": 1}])}))
    assert DataManager.cached("k", "get_routes", ctx) == [{"old": 1}]
    assert ctx._api_offline is True
    ctx = SimpleNamespace(_price_cache=FakeCache())
    assert DataManager.cached("k", "get_routes", ctx, warn=False) == []


def test_shared_client_is_unique():
    from uexinfo.api.uex_client import shared_client
    assert shared_client() is shared_client()
