"""Offres de contrats lues au clic (ocr/contract_watch.py) : partie pure, sans écran ni souris."""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from uexinfo.models.mission_result import MissionResult, ParsedObjective
from uexinfo.ocr.contract_watch import OffersBoard, changed, offers_tab_active, parse_timer, signature
from uexinfo.ocr.engine import _objective_sentences


def test_parse_timer():
    assert parse_timer("2h 11m") == 7860
    assert parse_timer("5m 20s") == 320
    assert parse_timer("11s") is None          # minutes perdues à la lecture
    assert parse_timer("") is None


def _screen(green: bool) -> Image.Image:
    img = Image.new("RGB", (2560, 1440), (24, 20, 19))
    d = ImageDraw.Draw(img)
    d.rectangle((878, 137, 1016, 183), fill=(58, 104, 89) if green else (45, 37, 32))   # bouton OFFERS
    return img


def test_offers_tab_active():
    assert offers_tab_active(_screen(True))
    assert not offers_tab_active(_screen(False))


def test_signature_changes_with_content():
    a, b = _screen(True), _screen(True)
    ImageDraw.Draw(b).rectangle((300, 300, 700, 900), fill=(230, 230, 230))
    box = (0.075, 0.14, 0.31, 0.835)
    assert not changed(signature(a, box), signature(_screen(True), box))
    assert changed(signature(a, box), signature(b, box))


def _result(title, reward, timer="2h 0m", bp=False, contract=None):
    card = SimpleNamespace(title=title.upper(), contractor="COVALEX", timer=timer, blueprint=bp)
    return SimpleNamespace(card=card, contract=contract, recognized=contract is not None,
                           reward=reward, xp=None)


def _contract(title, **kw):
    base = dict(title=title, blueprint=False, mission_type="Hauling - Stellar", rank="Rookie",
                scu_min=8, scu_max=16, container=4)
    base.update(kw)
    return SimpleNamespace(**base)


def test_board_merges_sorts_and_expires():
    b = OffersBoard()
    small = _contract("Rookie Rank - Small Cargo Haul")
    assert b.add_cards([_result("Rookie Rank - Small Cargo Haul", 42000, contract=small),
                        _result("Junior Rank - Small Cargo Haul", 67000, timer="5m 0s",
                                contract=_contract("Junior Rank - Small Cargo Haul", rank="Junior"))], 0) == 2
    # Même offre vue à la capture suivante (liste défilée) : pas de doublon.
    assert b.add_cards([_result("Rookie Rank - Small Cargo Haul", 42000, contract=small)], 30) == 0
    assert [o.reward for o in b.rows(60)] == [67000, 42000]
    assert [o.reward for o in b.rows(400)] == [42000]          # la seconde a expiré (5 min)
    assert b.rows(60)[1].scu_text == "8–16"


def test_board_detail_attaches_objectives():
    b = OffersBoard()
    b.add_cards([_result("RSI Disc. Month: Important Supply Haul", 124000,
                         contract=_contract("RSI Disc. Month: Important Supply Haul", scu_min=None, scu_max=None)),
                 _result("RSI Disc. Month: Important Supply Haul", 98000,
                         contract=_contract("RSI Disc. Month: Important Supply Haul"))], 0)
    detail = MissionResult(title="RSI Disc. Month: Important Supply Haul 625", reward=124000, parsed_objectives=[
        ParsedObjective("deliver", "Ship Decoy Countermeasures", 128, "NB Int. Spaceport on microTech"),
        ParsedObjective("collect", "Ship Decoy Countermeasures", None, "Seraphim Station"),
    ])
    o = b.add_detail(detail, 10)
    assert o is not None and o.reward == 124000                 # l'offre au même montant, pas l'autre
    assert o.objectives == ["128 SCU Ship Decoy Countermeasures → NB Int. Spaceport on microTech",
                            "collecte : Seraphim Station"]
    assert o.scu_text == "128"
    html = b.html(20)
    assert "Offres de contrats — 2" in html and "NB Int. Spaceport" in html
    assert b.add_detail(MissionResult(title=""), 10) is None    # « Please select a contract »


def test_objective_sentences_join_wrapped_lines():
    raw = ["9 Deliver 0/128 SCU of Ship Decoy Countermeasures to N8", "Int. Spaceport on microTech.",
           "© Collect Ship Decoy Countermeasures from", "Seraphim Station.", "ACCEPT OFFER"]
    assert _objective_sentences(raw) == [
        "Deliver 0/128 SCU of Ship Decoy Countermeasures to NB Int. Spaceport on microTech.",
        "Collect Ship Decoy Countermeasures from Seraphim Station."]


def test_stable_frame_waits_for_text_animation():
    # Le jeu écrit le texte progressivement : on lit la première image identique à la précédente.
    frames = [_screen(True) for _ in range(5)]
    for i, img in enumerate(frames[:3]):
        ImageDraw.Draw(img).rectangle((900, 300, 900 + 300 * (i + 1), 700), fill=(220, 220, 220))
    ImageDraw.Draw(frames[3]).rectangle((900, 300, 1800, 700), fill=(220, 220, 220))
    ImageDraw.Draw(frames[4]).rectangle((900, 300, 1800, 700), fill=(220, 220, 220))
    it = iter(frames)
    from uexinfo.ocr.contract_watch import stable_frame
    got = stable_frame(lambda: next(it), sleep=lambda s: None)
    assert got is frames[3]                       # 3e et 4e images identiques (texte complet)


def test_stable_frame_abandons_on_new_click_or_game_hidden():
    from uexinfo.ocr.contract_watch import stable_frame
    assert stable_frame(lambda: _screen(True), is_current=lambda: False, sleep=lambda s: None) is None
    assert stable_frame(lambda: None, sleep=lambda s: None) is None


def test_beep_once_page_fully_read():
    """Bip une fois la dernière image lue, pas entre deux images en attente ni sans lecture OCR."""
    import threading, time
    from uexinfo.ocr.contract_watch import ContractWatcher
    beeps = []
    w = ContractWatcher(None, None, lambda b: None, on_read=lambda: beeps.append(time.time()))
    w._listener = object()                  # mode actif sans écouter la souris
    w._last_seen = time.time()

    def fake_process(img, ts):
        w._did_read = img != "même page"
        time.sleep(0.05)
        return False
    w.process = fake_process
    for img in ("liste", "détail"):
        w._queue.put((img, time.time()))
    threading.Thread(target=w._work, daemon=True).start()
    time.sleep(0.4)
    assert len(beeps) == 1
    w._queue.put(("même page", time.time()))
    time.sleep(0.3)
    assert len(beeps) == 1
