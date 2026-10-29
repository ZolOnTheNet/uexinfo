"""Décision D6 — une seule procédure de reconnaissance de noms (données UEX réelles)."""
import pytest

from uexinfo.names import EXACT, FUZZY, PREFIX, THRESHOLDS, build_index, norm


@pytest.fixture(scope="module")
def idx(uex_cache):
    return build_index(uex_cache)


def name(o):
    return getattr(o, "name", o)


# ── Normalisation ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("New_Babbage", "new babbage"), ("E’tam", "e'tam"), ("  Área   18 ", "area 18"),
    ("ARC-L1", "arc-l1"), (None, ""),
    ("Pyro Gateway(Nyx)", "pyro gateway (nyx)"), ("Pyro Gateway ( Nyx )", "pyro gateway (nyx)"),
])
def test_norm(raw, expected):
    assert norm(raw) == expected


# ── a. Seuils ─────────────────────────────────────────────────────────────────
def test_thresholds():
    assert THRESHOLDS == {"input": 70, "ocr": 60}


# ── c. Lieu → ses terminaux de commerce (D11 : plusieurs ⇒ liste, principal en tête)
@pytest.mark.parametrize("query,expected", [
    ("arc-l1", "Admin - ARC-L1"),
    ("seraphim station above crusader", "Admin - Seraphim"),
    ("tressler", "Admin - Port Tressler"),
])
def test_place_with_one_trade_terminal_gives_it(idx, query, expected):
    r = idx.resolve(query, kinds={"terminal"})
    assert not r.ambiguous
    assert name(r.best) == expected


@pytest.mark.parametrize("query,expected", [
    ("area 18", ["TDD - Trade and Development Division - Area 18", "IO North Tower - Area 18"]),
    ("Area_18", ["TDD - Trade and Development Division - Area 18", "IO North Tower - Area 18"]),
    ("new babbage", ["TDD - Trade and Development Division - Commons - New Babbage",
                     "MicroTech Planetary Services - Commons - New Babbage"]),
    ("lorville", ["Admin - L19 Residences - Metro Center - Lorville",
                  "CBD - Central Business District - Lorville"]),
])
def test_place_with_several_trade_terminals_gives_list(idx, query, expected):
    r = idx.resolve(query, kinds={"terminal"})
    assert r.ambiguous
    assert [name(o) for o in r.candidates] == expected


def test_terminal_code_and_full_name_are_exact(idx):
    assert name(idx.resolve("TDNEW", kinds={"terminal"}).best).startswith("TDD - ")
    r = idx.resolve("CBD - Central Business District - Lorville", kinds={"terminal"})
    assert name(r.best) == "CBD - Central Business District - Lorville"
    assert r.matches[0].level == EXACT


def test_dotted_place_service(idx):
    r = idx.resolve("lorville.admin", kinds={"terminal"})
    assert name(r.best) == "Admin - L19 Residences - Metro Center - Lorville"
    r = idx.resolve("stanton.lorville")
    assert name(r.best) == "Lorville" and not r.ambiguous


# ── b. Égalité ⇒ ambiguïté (liste proposée au joueur) ─────────────────────────
def test_homonym_gateways_are_ambiguous(idx):
    r = idx.resolve("nyx gateway", kinds={"terminal"})
    assert r.ambiguous
    assert {name(o) for o in r.candidates} == {"Admin - Nyx Gateway (Pyro)", "Admin - Nyx Gateway (Stanton)"}


def test_commodity_family_is_ambiguous(idx):
    r = idx.resolve("ship ammunition", kinds={"commodity"})
    assert r.ambiguous
    assert all(name(o).startswith("Ship Ammunition - Size") for o in r.candidates)


# ── Tous types d'entités ──────────────────────────────────────────────────────
@pytest.mark.parametrize("query,kinds,expected", [
    ("New_Babbage", {"city"}, "New Babbage"),
    ("hurston", None, "Hurston"),
    ("tressler", None, "Port Tressler"),
    ("e’tam", {"commodity"}, "E'tam"),
    ("cutlass black", {"vehicle"}, "Drake Cutlass Black"),
])
def test_entities(idx, query, kinds, expected):
    o = idx.resolve(query, kinds=kinds).best
    assert expected in (name(o), getattr(o, "name_full", None))


def test_vehicle_manufacturer_abbrev(idx):
    r = idx.resolve("drak.cutlass", kinds={"vehicle"})
    assert r.matches[0].level == PREFIX
    assert all("Drake" in o.name_full for o in r.candidates)


# ── Flou (dernier recours) ────────────────────────────────────────────────────
@pytest.mark.parametrize("query,kinds,expected", [
    ("larnite", {"commodity"}, "Laranite"),
    ("cutlas blak", {"vehicle"}, "Cutlass Black"),
])
def test_fuzzy(idx, query, kinds, expected):
    r = idx.resolve(query, kinds=kinds)
    assert r.matches[0].level == FUZZY
    assert name(r.best) == expected


def test_fuzzy_place_collapses_to_station(idx):
    r = idx.resolve("baijni")
    assert name(r.best) == "Baijini Point" and not r.ambiguous


def test_min_level_disables_fuzzy(idx):
    assert idx.resolve("larnite", kinds={"commodity"}, min_level=PREFIX).best is None


def test_unknown(idx):
    assert idx.resolve("zzzzqqq").best is None


def test_paren_without_space(idx):
    # Signalé par l'utilisateur : « Pyro Gateway(Nyx) » ne trouvait aucun terminal.
    r = idx.resolve("Pyro Gateway(Nyx)", kinds={"terminal"})
    assert name(r.best) == "Admin - Pyro Gateway (Nyx)" and not r.ambiguous


def test_gateway_base_name_is_ambiguous_and_closed_terminals_last(idx):
    # « pyro gateway » : les deux gateways homonymes (Stanton, Nyx) — pas le terminal
    # fermé « INS Jericho - Pyro Gateway » (is_available=0).
    r = idx.resolve("pyro gateway", kinds={"terminal"})
    assert r.ambiguous
    assert {name(o) for o in r.candidates} == {"Admin - Pyro Gateway (Nyx)", "Admin - Pyro Gateway (Stanton)"}
    r = idx.resolve("pyro gateway", kinds={"terminal"}, prefer_system="Stanton")
    assert name(r.best) == "Admin - Pyro Gateway (Stanton)"


# ── D11 : références #type:id, jamais réinterprétées ─────────────────────────
def test_ref_gives_exact_object(idx, uex_cache):
    # Le cas signalé : « Amm…7 » affiché doit ouvrir Ship Ammunition - Size 7, pas
    # la famille « Ship Ammunition » ni une autre taille.
    c = next(c for c in uex_cache.commodities if c.name == "Ship Ammunition - Size 7")
    r = idx.resolve(f"#commodity:{c.id}")
    assert r.best is c and r.matches[0].level == EXACT and not r.ambiguous
    t = next(t for t in uex_cache.terminals if t.name == "CBD - Central Business District - Lorville")
    assert idx.resolve(f"#terminal:{t.id}", kinds={"terminal"}).best is t


def test_unknown_or_malformed_ref_gives_nothing(idx):
    assert idx.resolve("#commodity:999999").matches == []
    assert idx.resolve("#terminal:51", kinds={"commodity"}).matches == []
    # Pas une référence : « #3 » (numéro de note) reste une saisie ordinaire
    from uexinfo.names import parse_ref
    assert parse_ref("#3") is None and parse_ref("#truc:1") is None


def test_place_ref_where_terminal_expected(idx, uex_cache):
    t = next(t for t in uex_cache.terminals if t.name == "Admin - Port Tressler")
    r = idx.resolve(f"#station:{t.id_space_station}", kinds={"terminal"})
    assert [name(o) for o in r.candidates] == ["Admin - Port Tressler"]
    # et un terminal là où un lieu est attendu → son lieu
    r = idx.resolve(f"#terminal:{t.id}", kinds={"station"})
    assert r.best.id == t.id_space_station


def test_node_ref_and_link_roundtrip():
    from uexinfo.names import Entity, NameIndex, link, parse_link, ref
    idx = NameIndex([Entity("node", "Port Tressler", "Port Tressler", "N")])
    assert ref("node", "Port Tressler") == "node:Port_Tressler"
    assert idx.resolve("#node:Port_Tressler").best == "N"
    assert parse_link("uex:node:Port_Tressler") == ("node", "Port_Tressler")
    assert link("commodity", 7, "Amm…7") == "[link=uex:commodity:7]Amm…7[/link]"


def test_star_suffix_means_truncated_name(idx):
    r = idx.resolve("Port Tress*", kinds={"terminal"})
    assert name(r.best) == "Admin - Port Tressler"


def test_node_ref_where_terminal_expected(idx):
    # Un lien de nœud du graphe (« Port Tressler ») ouvert par /info ou /go :
    # les terminaux de ce lieu exact, jamais un nom approchant.
    from uexinfo.names import Entity
    idx2 = type(idx)(idx.entities + [Entity("node", "Port Tressler", "Port Tressler", None,
                                            keys=("port tressler",))])
    r = idx2.resolve("#node:Port_Tressler", kinds={"terminal", "commodity", "vehicle"})
    assert [name(o) for o in r.candidates] == ["Admin - Port Tressler"]


def test_link_renders_reference_span():
    from uexinfo.display.render_html import _markup_to_inline_html
    html = _markup_to_inline_html("[cyan]x [link=uex:commodity:207]Ship Amm… S7[/link][/cyan]")
    assert 'class="cw" data-ref="commodity:207" data-type="commodity"' in html
    assert "Ship Amm… S7" in html
