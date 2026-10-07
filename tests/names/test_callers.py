"""Les anciennes fonctions de recherche délèguent toutes au résolveur unique (D6)."""
from types import SimpleNamespace

import pytest


@pytest.fixture()
def ctx(uex_cache):
    return SimpleNamespace(cache=uex_cache)


def test_info_find_terminal(ctx):
    from uexinfo.cli.commands.info import _find_terminal
    assert _find_terminal("area 18", ctx).name.startswith("TDD - ")
    assert _find_terminal("seraphim station above crusader", ctx).name == "Admin - Seraphim"
    # strong : pas de « contient » (ne pas écraser une commodité homonyme)
    assert _find_terminal("seraphim station above crusader", ctx, strong=True) is None


def test_info_find_terminal_candidates_homonyms(ctx):
    from uexinfo.cli.commands.info import _find_terminal_candidates
    names = {t.name for t in _find_terminal_candidates("nyx gateway", ctx)}
    assert names == {"Admin - Nyx Gateway (Pyro)", "Admin - Nyx Gateway (Stanton)"}


def test_info_find_commodity_and_vehicle(ctx):
    from uexinfo.cli.commands.info import _find_commodity, _find_vehicle
    assert _find_commodity("e'tam", ctx).name == "E'tam"
    assert _find_commodity("larnite", ctx) is None          # pas de flou ici (comme avant)
    assert _find_vehicle("cutlas blak", ctx).name == "Cutlass Black"


def test_sync_find_terminal(ctx):
    from uexinfo.cli.commands.sync import _find_terminal
    assert _find_terminal("port_tressler", ctx).name == "Admin - Port Tressler"


def test_go_resolve(ctx):
    from uexinfo.cli.commands.go import _resolve
    assert _resolve("arc-l1", ctx) == "Admin - ARC-L1"
    assert _resolve("hurston", ctx) == "Hurston"


# ── Signalé : « je choisis Seraphim Station, il doit comprendre » ──────────────
@pytest.mark.parametrize("query", ["Seraphim Station", "seraphim_station", "@Seraphim_Station", "Seraphim"])
def test_place_always_gives_trading_terminal(ctx, query):
    from uexinfo.cli.commands.go import _resolve
    from uexinfo.cli.commands.player import _resolve_location
    assert _resolve(query.lstrip("@"), ctx) == "Admin - Seraphim"
    name, tid = _resolve_location(query, ctx)
    assert tid == 259


def test_shop_terminal_maps_to_trading_terminal(uex_cache):
    from uexinfo.names import trading_terminal
    shop = next(t for t in uex_cache.terminals if t.name == "Landing Services - Seraphim Station")
    assert trading_terminal(uex_cache.terminals, shop).name == "Admin - Seraphim"
    admin = next(t for t in uex_cache.terminals if t.name == "Admin - Seraphim")
    assert trading_terminal(uex_cache.terminals, admin) is admin


def test_location_index_one_entry_per_station(uex_cache):
    from uexinfo.location.index import LocationIndex
    idx = LocationIndex(uex_cache)
    seraphim = [e for e in idx.search("seraphim", limit=20, types={"terminal"})
                if "seraphim" in e.full_path.lower()]
    assert [e.entity_id for e in seraphim] == [259]       # plus de « Seraphim Station » boutique


def test_overlay_completion_one_line_per_place_with_trading_terminal(uex_cache):
    # Signalé : pour « Seraphim Station », aucun Admin ni terminal de commerce proposé.
    from types import SimpleNamespace
    from uexinfo.overlay.server import OverlayServer
    srv = OverlayServer.__new__(OverlayServer)
    srv.ctx = SimpleNamespace(cache=uex_cache, player=SimpleNamespace(ships=[]))
    items = srv._dyn_typed("terminal", "seraph")
    assert [(c["value"], c["hint"]) for c in items] == [("Seraphim Station", "Admin - Seraphim · Stanton")]
