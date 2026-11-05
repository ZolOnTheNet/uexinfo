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
    # Texte des objectifs (colonne de droite) écrit en 3 temps ; un halo bouge sur le titre et
    # au centre à chaque image (capture du 2026-11-01) : il ne doit pas empêcher la lecture.
    frames = [_screen(True) for _ in range(5)]
    for i, img in enumerate(frames):
        right = 1700 + 220 * min(i + 1, 3)
        ImageDraw.Draw(img).rectangle((1700, 400, right, 1000), fill=(220, 220, 220))
        ImageDraw.Draw(img).ellipse((1100 + 60 * i, 200, 1400 + 60 * i, 700), fill=(255, 255, 255))
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
    w = ContractWatcher(None, None, lambda b: None, on_read=lambda ok=True: beeps.append(time.time()))
    w._listener = object()                  # mode actif sans écouter la souris
    w._last_seen = time.time()

    def fake_process(img, ts, forced=False):
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


def _card(title, reward, top, bottom):
    from uexinfo.ocr.contract_list import ContractCard
    return ContractCard(title=title, reward=reward, top=top, bottom=bottom,
                        contractor="COVALEX INDEPENDENT CONTRACTORS")


def test_selected_card_is_the_green_one():
    from uexinfo.ocr.contract_watch import selected_card
    from uexinfo.ocr.contract_list import LIST_BOX
    img = _screen(True)
    x0, y0 = int(2560 * LIST_BOX[0]), int(1440 * LIST_BOX[1])
    cards = [_card("A", 42000, 10, 70), _card("B", 67000, 100, 160), _card("C", 50000, 190, 250)]
    d = ImageDraw.Draw(img)
    for c in cards:                                           # cartes grises (G − R ≈ 13)
        d.rectangle((x0, y0 + c.top, x0 + 400, y0 + c.bottom), fill=(40, 53, 60))
    d.rectangle((x0, y0 + 100, x0 + 400, y0 + 160), fill=(30, 66, 50))     # carte cliquée (≈ 36)
    assert selected_card(img, cards) == 1
    assert selected_card(_screen(True), cards) is None


def test_detail_goes_to_selected_card_despite_bad_reading():
    # capture du 01/11 19:43:12 : titre abîmé par le halo, 67 500 lu 87 500
    from uexinfo.cache.contract_catalog import RecognizedContract
    board = OffersBoard()
    cards = [_card("JUNIOR RANK SMALL CARGO HAUL", 67000, 0, 60),
             _card("JUNIOR RANK SMALL CARGO HAUL", 55000, 100, 160),
             _card("", 42000, 200, 260)]                          # titre illisible
    board.add_cards([RecognizedContract(c, None, 0.0) for c in cards], 0)
    ob = ParsedObjective(kind="deliver", commodity="Stims (5414aUEC/scu)", quantity_scu=4,
                         location="Beautiful Glen Station")
    detail = MissionResult(title="BP Junior Rank - Small Carao Haul", reward=87500, parsed_objectives=[ob])
    got = board.add_detail(detail, 0, selected=0)
    assert (got.reward, got.scu, got.objectives) == (67000, 4, ["4 SCU Stims → Beautiful Glen Station"])
    # carte sans titre lisible : l'offre prend le titre du détail
    got = board.add_detail(MissionResult(title="Rookie Rank - Small Cargo Haul", reward=42000,
                                         parsed_objectives=[ob]), 0, selected=2)
    assert (got.title, got.reward) == ("Rookie Rank - Small Cargo Haul", 42000)


def test_applog_text_of_html():
    from uexinfo.applog import text_of
    assert text_of("<table><tr><td>Iron</td><td>4&nbsp;SCU</td></tr></table>\x1b[32mok\x1b[0m") == "Iron | 4\xa0SCU |\nok"
    assert text_of("x" * 50, limit=10).startswith("xxxxxxxxxx\n…")


def test_hotkey_parse():
    from uexinfo.overlay import _Win32HotkeyListener
    assert _Win32HotkeyListener.parse("alt+shift+m") == ("m", 0x1 | 0x4)
    assert _Win32HotkeyListener.parse("F10") == ("f10", 0)
    assert _Win32HotkeyListener("m", None)._vk() == ord("M")
    assert _Win32HotkeyListener("f10", None)._vk() == 0x79


def test_hotkey_forces_detail_reread():
    # même offre lue deux fois au raccourci : relue (la dernière gagne), sans attendre de changement
    from uexinfo.ocr.contract_watch import ContractWatcher
    calls = []

    class Engine:
        tessdata_dir = "."

        def extract_mission(self, img, full):
            calls.append(full)
            return MissionResult(title="", reward=0)
    w = ContractWatcher(Engine(), None, lambda b: None)
    w._last_list = b"x"                                   # liste déjà lue, pas de molette
    img = _screen(True)
    w.process(img, 0)
    w.process(img, 1)                                      # image identique : rien à relire
    w.process(img, 2, forced=True)                         # raccourci : relu quand même
    assert calls == [False, False]


def test_card_reward_wins_over_detail_missing_a_digit():
    # journal du 05/11 : cartes 258k / 363k / 510k (= catalogue scmdb), détail lu 58 250 / 63 000 / 51 050
    from uexinfo.cache.contract_catalog import RecognizedContract
    for card_r, detail_r in ((258000, 58250), (363000, 63000), (510000, 51050)):
        board = OffersBoard()
        board.add_cards([RecognizedContract(_card("ROOKIE HAULER NEEDED", card_r, 0, 60), None, 0.0)], 0)
        got = board.add_detail(MissionResult(title="Rookie Hauler Needed", reward=detail_r), 0, selected=0)
        assert got.reward == card_r


def test_detail_reward_kept_when_close_to_card():
    from uexinfo.cache.contract_catalog import RecognizedContract
    board = OffersBoard()
    board.add_cards([RecognizedContract(_card("JUNIOR HAULER NEEDED", 215000, 0, 60), None, 0.0)], 0)
    got = board.add_detail(MissionResult(title="Junior Hauler Needed", reward=215250), 0, selected=0)
    assert got.reward == 215250


def test_selected_card_of_another_contract_is_not_used():
    # journal du 05/11 12:00:59 : détail « Junior … Small » rattaché à la carte « Rookie … Large »
    from uexinfo.cache.contract_catalog import RecognizedContract
    board = OffersBoard()
    board.add_cards([
        RecognizedContract(_card("Junior Hauler Needed for Small Shipment", 172000, 0, 60), None, 0.0),
        RecognizedContract(_card("Rookie Hauler Needed for Large Shipment", 523000, 0, 60), None, 0.0)], 0)
    got = board.add_detail(MissionResult(title="Junior Hauler Needed for Small Shipment 50 /",
                                         reward=172250), 0, selected=1)
    assert got.title.startswith("Junior") and got.reward == 172250


def test_damaged_title_still_uses_selected_card():
    from uexinfo.ocr.contract_watch import _other_title
    assert not _other_title("rookie hauler neded for small shipment 50", "rookie hauler needed for small shipment")
    assert not _other_title("rookie hauler needed for direct bulk shipmen", "rookie hauler needed for direct bulk shipment")
    assert _other_title("junior hauler needed for small shipment", "rookie hauler needed for large shipment")


def test_list_headers_are_not_offers():
    # « HAULING PLANETARY », texte de l'overlay : ni reconnus ni montant → pas d'offre
    from uexinfo.cache.contract_catalog import RecognizedContract
    board = OffersBoard()
    board.add_cards([RecognizedContract(_card("HAULING PLANETARY", None, 0, 0), None, 0.0),
                     RecognizedContract(_card("Rookie Hauler Needed", 63000, 0, 60), None, 0.0)], 0)
    assert len(board.offers) == 1 and len(board.cards) == 2


def test_hotkey_beeps_high_if_recognized_low_otherwise():
    import threading, time
    from uexinfo.ocr.contract_watch import ContractWatcher
    beeps = []
    w = ContractWatcher(None, None, lambda b: None, on_read=lambda ok=True: beeps.append(ok))
    w._listener = object()
    w._last_seen = time.time()

    def fake_process(img, ts, forced=False):
        w._last_offer = object() if img == "reconnue" else None
        return w._last_offer is not None
    w.process = fake_process
    threading.Thread(target=w._work, daemon=True).start()
    w._queue.put(("reconnue", time.time(), True))
    time.sleep(0.3)
    w._queue.put(("illisible", time.time(), True))
    time.sleep(0.3)
    assert beeps == [True, False]


def test_hotkey_beeps_before_list_reread():
    # journal du 05/11 : F9 après la molette attendait 2,6 s la relecture de la liste avant le bip
    import threading
    from uexinfo.cache.contract_catalog import RecognizedContract
    from uexinfo.ocr.contract_watch import ContractWatcher
    beeps, list_done = [], threading.Event()

    class Engine:
        tessdata_dir = "."

        def extract_mission(self, img, full):
            return MissionResult(title="Rookie Hauler Needed", reward=63000)
    w = ContractWatcher(Engine(), None, lambda b: None, on_read=lambda ok=True: beeps.append(list_done.is_set()))
    w.board.add_cards([RecognizedContract(_card("ROOKIE HAULER NEEDED", 63000, 0, 60), None, 0.0)], 0)
    w._last_list, w._scrolls = b"x", 1                     # molette depuis la dernière lecture

    def slow_list(img):
        list_done.wait(2)
        return []
    w._read_list = lambda img: (threading.Timer(0.3, list_done.set).start(), slow_list(img))[1]
    w.process(_screen(True), 1, forced=True)
    assert beeps == [False]                               # bip donné avant la fin de la liste
    assert w._last_offer is not None and w._early_beep


def test_keep_image_keeps_only_the_last(tmp_path):
    import time
    from PIL import Image
    from uexinfo.ocr.contract_watch import keep_image
    for i in range(5):
        keep_image(Image.new("RGB", (64, 36)), tmp_path, 3, f"offre-{i:02d}.jpg")
        time.sleep(0.15)
    assert [p.name for p in sorted(tmp_path.glob("*.jpg"))] == ["offre-02.jpg", "offre-03.jpg", "offre-04.jpg"]


def test_board_survives_restart(tmp_path):
    # « je viens de faire une moisson, tout est oublié » : le tableau est gardé sur disque
    from uexinfo.cache.contract_catalog import RecognizedContract
    path = tmp_path / "offres.json"
    board = OffersBoard(path)
    board.add_cards([RecognizedContract(_card("Rookie Hauler Needed", 63000, 0, 60), None, 0.0)], 100)
    board.add_detail(MissionResult(title="Rookie Hauler Needed", reward=63000), 100, selected=0)
    board.save()
    again = OffersBoard(path)
    assert again.load(200) == 1 and list(again.offers.values())[0].reward == 63000
    assert OffersBoard(path).load(100 + OffersBoard.KEEP_UNTIMED_S + 1) == 0   # trop vieille


def test_offers_from_here_and_to_destination_are_marked_first():
    # « offres doit indiquer les missions de là où on est et là où on veut aller »
    from uexinfo.ocr.contract_watch import Offer, _same_place
    board = OffersBoard()
    rich = Offer(title="Rich", reward=900000, pickups=["Checkmate Station above Pyro II"], drops=["Patch City"])
    here = Offer(title="Here", reward=200000, pickups=["Ruin Station above Pyro VI"], drops=["Checkmate"])
    both = Offer(title="Both", reward=100000, pickups=["Ruin Station"], drops=["Orbituary above Pyro III"])
    for o in (rich, here, both):
        board.offers[o.key] = o
    html = board.html(0, here="Ruin Station", there="Orbituary")
    assert html.index("Both") < html.index("Here") < html.index("Rich")      # les deux, puis un, puis montant
    assert "class='both'" in html and "★" in html and "⚑" in html
    assert _same_place("Ruin Station above Pyro VI", "Ruin Station")
    assert not _same_place("Ruin Station", "Orbituary")
    assert not _same_place("Pyro Gateway", "Pyro")                            # mot trop court : rien
