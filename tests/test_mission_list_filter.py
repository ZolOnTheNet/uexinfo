"""/mission list suit le filtre de systèmes de /select (journal du 05/11 : en Pyro, seules
d'anciennes missions de Stanton s'affichaient, malgré /select system pyro)."""
from types import SimpleNamespace as NS

from uexinfo.cli.commands.mission import _visible_missions


def _graph():
    return NS(nodes={"Orbituary": NS(system="Pyro"), "Everus Harbor": NS(system="Stanton")})


def _mission(*places):
    return NS(all_sources=list(places[:1]), all_destinations=list(places[1:]))


def _ctx(include=(), exclude=()):
    return NS(cfg={"filters": {"system": {"include": list(include), "exclude": list(exclude)}}})


def test_include_pyro_hides_stanton_missions_and_keeps_unlinked():
    pyro, stanton, unknown = _mission("Orbituary", "Orbituary"), _mission("Everus Harbor"), _mission("Lieu ?")
    nodes = {"Orbituary": "Orbituary", "Everus Harbor": "Everus Harbor", "Lieu ?": None}
    shown, hidden = _visible_missions(_ctx(include=["pyro"]), [pyro, stanton, unknown], nodes, _graph())
    assert shown == [pyro, unknown] and hidden == 1


def test_no_filter_shows_everything():
    ms = [_mission("Orbituary"), _mission("Everus Harbor")]
    nodes = {"Orbituary": "Orbituary", "Everus Harbor": "Everus Harbor"}
    assert _visible_missions(_ctx(), ms, nodes, _graph()) == (ms, 0)


def test_exclude_stanton():
    ms = [_mission("Orbituary"), _mission("Everus Harbor")]
    nodes = {"Orbituary": "Orbituary", "Everus Harbor": "Everus Harbor"}
    assert _visible_missions(_ctx(exclude=["Stanton"]), ms, nodes, _graph()) == ([ms[0]], 1)
