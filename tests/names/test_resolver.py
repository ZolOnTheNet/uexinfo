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


# ── c. Lieu → terminal principal (Admin > TDD > centre cargo > commerce > autre)
@pytest.mark.parametrize("query,expected", [
    ("arc-l1", "Admin - ARC-L1"),
    ("area 18", "TDD - Trade and Development Division - Area 18"),
    ("Area_18", "TDD - Trade and Development Division - Area 18"),
    ("new babbage", "TDD - Trade and Development Division - Commons - New Babbage"),
    ("lorville", "Admin - L19 Residences - Metro Center - Lorville"),
    ("seraphim station above crusader", "Admin - Seraphim"),
    ("tressler", "Admin - Port Tressler"),
])
def test_place_gives_main_terminal(idx, query, expected):
    r = idx.resolve(query, kinds={"terminal"})
    assert not r.ambiguous
    assert name(r.best) == expected


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
