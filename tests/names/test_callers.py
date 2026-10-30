"""Les commandes choisissent un objet selon D11 : un candidat sûr est accepté ;
plusieurs candidats, ou une faute de frappe, donnent une liste au joueur ; la
position et la destination se retrouvent par leur identifiant."""
from types import SimpleNamespace

import pytest


class Picker:
    """select_fn de test : mémorise chaque liste proposée et choisit l'élément `index`
    (None = le joueur annule)."""

    def __init__(self, index=0):
        self.index, self.calls = index, []

    def __call__(self, items, title="", mode="multi", confirm_label=""):
        self.calls.append((title, [it.label for it in items]))
        return None if self.index is None else [items[self.index]]


@pytest.fixture()
def ctx(uex_cache):
    from uexinfo.models.player import Player
    return SimpleNamespace(cache=uex_cache, player=Player(), select_fn=None)


def test_unique_candidate_is_accepted_without_asking(ctx):
    from uexinfo.cli.commands.info import _find_terminal
    ctx.select_fn = Picker()
    assert _find_terminal("seraphim station above crusader", ctx).name == "Admin - Seraphim"
    assert ctx.select_fn.calls == []


def test_several_trade_terminals_give_a_list(ctx):
    from uexinfo.cli.commands.info import _find_terminal
    ctx.select_fn = Picker(index=1)
    assert _find_terminal("area 18", ctx).name == "IO North Tower - Area 18"
    assert ctx.select_fn.calls[0][1] == ["TDD - Trade and Development Division - Area 18",
                                         "IO North Tower - Area 18"]


def test_homonyms_give_a_list(ctx):
    from uexinfo.cli.commands.info import _find_terminal_candidates
    names = {t.name for t in _find_terminal_candidates("nyx gateway", ctx)}
    assert names == {"Admin - Nyx Gateway (Pyro)", "Admin - Nyx Gateway (Stanton)"}


def test_typo_is_proposed_never_applied(ctx):
    from uexinfo.cli.commands.info import _find_vehicle
    assert _find_vehicle("cutlas blak", ctx) is None          # personne pour choisir : rien d'appliqué
    ctx.select_fn = Picker()
    assert _find_vehicle("cutlas blak", ctx).name == "Cutlass Black"
    assert "Vouliez-vous dire" in ctx.select_fn.calls[0][0]


def test_cancel_gives_nothing(ctx):
    from uexinfo.cli.commands.info import _find_terminal
    ctx.select_fn = Picker(index=None)
    assert _find_terminal("area 18", ctx) is None


def test_background_lookup_never_asks(ctx):
    from uexinfo.cli.commands.info import _find_commodity
    ctx.select_fn = Picker()
    assert _find_commodity("e'tam", ctx, ask=False).name == "E'tam"
    assert _find_commodity("ship ammunition - size", ctx, ask=False) is None   # plusieurs tailles
    assert ctx.select_fn.calls == []


def test_go_keeps_the_chosen_object_and_its_id(ctx):
    from uexinfo.cli.commands.go import _place, _resolve
    t = _resolve("arc-l1", ctx)
    assert _place(t) == ("Admin - ARC-L1", t.id)
    assert _place(_resolve("hurston", ctx)) == ("Hurston", 0)


def test_unknown_place_is_refused(ctx):
    from uexinfo.cli.commands.go import _resolve
    assert _resolve("qqqqqqqqqq", ctx) is None


def test_sync_find_terminal(ctx):
    from uexinfo.cli.commands.sync import _find_terminal
    assert _find_terminal("port_tressler", ctx).name == "Admin - Port Tressler"


# ── Signalé : « je choisis Seraphim Station, il doit comprendre » ──────────────
@pytest.mark.parametrize("query", ["Seraphim Station", "seraphim_station", "@Seraphim_Station", "Seraphim"])
def test_place_always_gives_trading_terminal(ctx, query):
    from uexinfo.cli.commands.go import _resolve
    from uexinfo.cli.commands.player import _resolve_location
    assert _resolve(query.lstrip("@"), ctx).name == "Admin - Seraphim"
    name, tid = _resolve_location(query, ctx)
    assert tid == 259


# ── Règle 1 : la position se retrouve par son identifiant ────────────────────
def test_position_is_found_by_id_not_by_name(ctx):
    from uexinfo.cli.choose import position_terminal
    ctx.player.set_location("nom affiché sans rapport", 259)
    assert position_terminal(ctx).name == "Admin - Seraphim"


def test_old_position_without_id_is_read_once_and_exactly(ctx):
    from uexinfo.cli.choose import position_terminal
    ctx.player.set_location("Admin - Seraphim", 0)
    assert position_terminal(ctx).id == 259 and ctx.player.location_id == 259
    ctx.player.set_location("seraph", 0)          # pas un nom exact : rien n'est deviné
    assert position_terminal(ctx) is None


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


def test_term_sys_cell_no_duplicate_system():
    import re
    from uexinfo.cli.commands.info import _term_sys_cell
    strip = lambda x: re.sub(r"\[/?[^\]]*\]", "", x)  # noqa: E731
    assert strip(_term_sys_cell({"terminal_name": "Admin - Pyro Gateway (Stanton)",
                                 "star_system_name": "Stanton"}, maxlen=40)) == "Pyro Gateway (Stanton)"
    assert strip(_term_sys_cell({"terminal_name": "Admin - Seraphim",
                                 "star_system_name": "Stanton"}, maxlen=40)) == "Seraphim  (Stanton)"


# ── D9 : sans /select, /info n'applique aucun filtre système ──────────────────
def test_default_system_filter_comes_only_from_select(uex_cache):
    from types import SimpleNamespace
    from uexinfo.cli.commands.info import _default_system_filter
    ctx = SimpleNamespace(cfg={}, cache=uex_cache)
    assert _default_system_filter(ctx, "stanton") is None                 # /select clear
    ctx.cfg = {"filters": {"system": {"include": ["Pyro"], "exclude": []}}}
    assert _default_system_filter(ctx, "stanton") == ["pyro"]
    ctx.cfg = {"filters": {"system": {"include": [], "exclude": ["Pyro"]}}}
    assert set(_default_system_filter(ctx, "stanton")) == {"stanton", "nyx"}


# ── Signalé le 2026-10-30 ─────────────────────────────────────────────────────
def test_ship_add_vehicle_lookup_accepts_quiet(ctx):
    """/ship add MISC_Hull_B : le relais de config.py transmet `quiet` (TypeError avant)."""
    from uexinfo.cli.commands.config import _find_vehicle
    v = _find_vehicle("Cutlass Black", ctx, quiet=True)
    assert v is not None and v.name == "Cutlass Black"
    assert _find_vehicle("qqqqqqqq", ctx, quiet=True) is None


def test_clicked_command_is_shown_with_object_name(ctx):
    """Un clic envoie « /dest #station:… » : on affiche le nom, on exécute la référence."""
    from uexinfo.cli.choose import display_line
    t = next(t for t in ctx.cache.terminals if t.name == "Admin - Port Tressler")
    assert display_line(f"/dest #station:{t.id_space_station}", ctx) == "/dest Port Tressler"
    assert display_line(f"/info #terminal:{t.id}", ctx) == "/info Admin - Port Tressler"
    assert display_line("/note #3 et #truc:1", ctx) == "/note #3 et #truc:1"   # pas des références


# ── Flotte du joueur : un ajout, une recherche (D11, signalé le 2026-10-30) ───
@pytest.fixture()
def fleet_ctx(ctx, monkeypatch):
    import uexinfo.config.settings as settings
    monkeypatch.setattr(settings, "save", lambda *a, **k: None)
    ctx.cfg = {}
    from uexinfo.cli.commands.config import _add_ship
    _add_ship("Cutlass Black", ctx)
    return ctx


def test_ship_found_by_short_or_full_name(fleet_ctx):
    from uexinfo.cli.commands.config import _pick_ship
    assert [s.name for s in fleet_ctx.player.ships] == ["Drake Cutlass Black"]
    for q in ("Drake Cutlass Black", "cutlass black", "Cutlass_Black".replace("_", " "), "cutlass"):
        assert _pick_ship(q, fleet_ctx).name == "Drake Cutlass Black"
    assert _pick_ship("qqqqqq", fleet_ctx, quiet=True) is None


def test_player_ship_add_and_set_use_the_same_rules(fleet_ctx):
    from uexinfo.cli.commands.player import cmd_player
    cmd_player(["ship", "add", "Cutlass_Black", "50"], fleet_ctx)          # déjà là : pas de doublon
    assert len(fleet_ctx.player.ships) == 1
    cmd_player(["ship", "scu", "cutlass", "50"], fleet_ctx)
    assert fleet_ctx.player.ships[0].scu == 50
    fleet_ctx.player.active_ship = ""
    cmd_player(["ship", "set", "cutlass_black"], fleet_ctx)
    assert fleet_ctx.player.active_ship == "Drake Cutlass Black"
