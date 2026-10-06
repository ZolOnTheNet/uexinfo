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
