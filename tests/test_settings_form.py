"""Réglages en formulaire : chaque champ s'enregistre par sa commande existante, et la
valeur relue est celle choisie ; la page ne peut envoyer qu'une valeur permise."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

import uexinfo.overlay.server  # noqa: F401  (enregistre les commandes, comme l'overlay)
import uexinfo.config.settings as settings
from uexinfo.cli.runner import run_command
from uexinfo.overlay import settings_form as sf


@pytest.fixture()
def ctx(uex_cache, monkeypatch, tmp_path):
    from uexinfo.data.cargo_grids import CargoGridManager
    from uexinfo.models.player import Player
    monkeypatch.setattr(settings, "save", lambda *a, **k: None)
    cache = SimpleNamespace(**vars(uex_cache), ttl_static=86400)
    return SimpleNamespace(cfg=deepcopy(settings.DEFAULT), cache=cache, player=Player(),
                           select_fn=None, _overlay_send_fn=None, debug_level=0,
                           cargo_grid_manager=CargoGridManager(config_dir=tmp_path))


def _sample(f):
    """Une valeur permise, différente de la valeur par défaut quand c'est possible."""
    if f["kind"] in ("choice",):
        return f["choices"][-1]["v"]
    if f["kind"] == "flags":
        return " ".join(c["v"] for c in f["choices"])
    if f["kind"] == "number":
        return str(f["max"]) if float(f["step"]).is_integer() else str(round(f["max"] - f["step"], 2))
    if f["kind"] == "words":
        return "Port_Tressler Lorville"
    if f["key"] == "overlay.hotkey":
        return "ctrl+shift+f9"
    return r"C:\Program Files\Mon Dossier"


@pytest.mark.parametrize("field", sf.fields(), ids=lambda f: f["key"])
def test_each_field_is_saved_by_its_command(field, ctx):
    value = _sample(field)
    line = sf.set_line(field["key"], value)
    assert line, f"{field['key']} : valeur refusée {value!r}"
    run_command(line, ctx)
    got = sf.values(ctx.cfg)[field["key"]]
    if field["kind"] == "number":
        assert float(got) == float(value), line
    else:
        assert got == value, line


@pytest.mark.parametrize("key", ["version.ptu", "scan.tesseract_exe", "voyage.calc.exclure",
                                 "voyage.calc.options"])
def test_empty_value_clears(key, ctx):
    run_command(sf.set_line(key, "x" if key != "voyage.calc.options" else "--boucle"), ctx)
    run_command(sf.set_line(key, ""), ctx)
    assert sf.values(ctx.cfg)[key] == ""


@pytest.mark.parametrize("key,value", [
    ("scan.mode", "n'importe"), ("overlay.opacity", "3"), ("scan.hour", "abc"),
    ("voyage.calc.options", "--rm"), ("inconnu.cle", "on"), ("scan.sc_log_path", 'a" ; /x'),
])
def test_page_cannot_send_unknown_values(key, value):
    assert sf.set_line(key, value) == ""


def test_schema_tabs_and_fields_are_well_formed():
    assert [t["id"] for t in sf.TABS] == ["ships", "overlay", "trade", "scan", "display"]
    keys = [f["key"] for f in sf.fields()]
    assert len(keys) == len(set(keys))
    for f in sf.fields():
        assert f["label"] and "{v}" in f["cmd"]
        if f["kind"] in ("choice", "flags"):
            assert all(c["v"] and c["t"] for c in f["choices"]), f["key"]


def test_unused_settings_are_not_offered():
    keys = {f["key"] for f in sf.fields()}
    assert not keys & {"trade.min_profit_per_scu", "trade.min_margin_percent", "trade.max_distance",
                       "trade.illegal_commodities", "sctrade.ttl", "voyage.calc.favoris"}


# ── Flotte ────────────────────────────────────────────────────────────────────
def test_fleet_add_set_cargo_remove(ctx):
    run_command(sf.ship_line("add", "Cutlass Black", {}), ctx)
    run_command(sf.ship_line("add", "MISC Freelancer MAX", {}), ctx)
    names = [s["name"] for s in sf.ships(ctx)]
    assert names == ["Drake Cutlass Black", "MISC Freelancer MAX"]
    assert sf.ships(ctx)[0]["active"]

    run_command(sf.ship_line("set", "MISC Freelancer MAX", {}), ctx)
    assert ctx.player.active_ship == "MISC Freelancer MAX"

    # Nom avec un « x » : reste un nom, pas une taille de conteneur
    run_command(sf.ship_line("cargo", "MISC Freelancer MAX", {"cargo": {"32": 2, "8": 1}, "scu": 72}), ctx)
    s = next(s for s in sf.ships(ctx) if s["name"] == "MISC Freelancer MAX")
    assert s["cargo"] == {"32": 2, "8": 1} and s["scu"] == 72

    # Plus aucun conteneur : la grille est effacée, la capacité gardée
    run_command(sf.ship_line("cargo", "MISC Freelancer MAX", {"cargo": {}, "scu": 66}), ctx)
    s = next(s for s in sf.ships(ctx) if s["name"] == "MISC Freelancer MAX")
    assert s["cargo"] == {} and s["scu"] == 66

    run_command(sf.ship_line("remove", "Drake Cutlass Black", {}), ctx)
    assert [s["name"] for s in sf.ships(ctx)] == ["MISC Freelancer MAX"]


@pytest.mark.parametrize("action,name,data", [
    ("rm", "x", {}), ("set", "", {}), ("set", 'a"b', {}),
    ("cargo", "x", {"cargo": {"7": 1}}), ("cargo", "x", {"cargo": {"32": -1}}),
])
def test_fleet_refuses_bad_actions(action, name, data):
    assert sf.ship_line(action, name, data) == ""
