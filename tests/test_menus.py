"""Catalogue du mode souris : chaque bouton envoie une commande que l'overlay connaît."""
import shlex

import pytest

import uexinfo.overlay.server  # noqa: F401  (enregistre les commandes, comme l'overlay)
from uexinfo.cli.commands import get_names
from uexinfo.cli.completer_data import SUBS
from uexinfo.overlay import menus

# Arguments libres, absents des sous-commandes de la complétion
FREE_ARGS = {("explore", "stanton"), ("explore", "pyro"), ("explore", "nyx"), ("dest", "clear")}


@pytest.mark.parametrize("cmd", menus.commands())
def test_button_targets_a_registered_command(cmd):
    words = shlex.split(cmd)
    name = words[0].lstrip("/")
    assert name in get_names(), f"{cmd} : commande inconnue de l'overlay"
    if len(words) > 1 and (name, words[1]) not in FREE_ARGS:
        assert words[1] in {s for s, _ in SUBS.get(name, [])}, f"{cmd} : sous-commande inconnue"


def test_every_node_runs_or_opens_a_group():
    def walk(nodes):
        for n in nodes:
            assert n["label"]
            assert ("cmd" in n) != ("kids" in n), n["label"]
            if "kids" in n:
                assert n["kids"], f"groupe vide : {n['label']}"
                walk(n["kids"])
    walk(menus.THEMES)
    assert len({t["id"] for t in menus.THEMES}) == len(menus.THEMES)
