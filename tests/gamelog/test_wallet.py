"""Solde du joueur : lecture OCR du terminal et mouvements d'argent du Game.log (lignes réelles)."""
from datetime import datetime, timezone

from uexinfo.gamelog.events import recognize_all
from uexinfo.gamelog.wallet import WalletTracker, estimate
from uexinfo.models.player import Player
from uexinfo.ocr.balance import choose, parse_balance

_LINES = [
    '<2026-10-30T22:00:00.000Z> [Notice] <AccountLoginCharacterStatus_Character> Character: createdAt 1 - updatedAt 1 - geid 2 - accountId 3 - name Pilote - state STATE_CURRENT [Team_GameServices][Login]',
    '<2026-10-30T23:09:38.100Z> [Notice] <CEntityComponentCommodityUIProvider::SendCommodityBuyRequest> Sending SShopCommodityBuyRequest - playerId[2] shopId[8] shopName[SCShop_Admin_lt_base_g] kioskId[8] price[1512.000000] shopPricePerCentiSCU[1] resourceGUID[a] autoLoading[1] quantity[100.000000 cSCU] Cargo Box Data: boxSize[1.000000] | unitAmount[1] [Team_CoreGameplayFeatures][Shops][UI]',
    '<2026-10-30T23:09:38.900Z> [Error] <CEntityComponentCommodityUIProvider::RmToken_CommodityTransactionResponse> Commodity Transaction Response Error - playerId[2] result[AutoLoadStartFailed] type[Buying] [Team_CoreGameplayFeatures][Shops]',
    '<2026-10-30T23:34:32.000Z> [Notice] <CEntityComponentCommodityUIProvider::SendCommodityBuyRequest> Sending SShopCommodityBuyRequest - playerId[2] shopId[8] shopName[SCShop_Admin_lt_base_g] kioskId[8] price[337630.000000] shopPricePerCentiSCU[1] resourceGUID[a] autoLoading[0] quantity[11200.000000 cSCU] Cargo Box Data: boxSize[16.000000] | unitAmount[7] [Team_CoreGameplayFeatures][Shops][UI]',
    '<2026-10-30T23:56:44.793Z> [Notice] <CEntityComponentCommodityUIProvider::SendCommoditySellRequest> Sending SShopCommoditySellRequest - playerId[2] shopId[8] shopName[SCShop_Admin_lt_base_g] kioskId[8] amount[439642.000000] resourceGUID[a] autoLoading[0] quantity[112] transactionMode[ResourceContainer] Cargo Box Data:  [boxSize[16] | unitAmount[7]] [Team_CoreGameplayFeatures][Shops][UI]',
    '<2026-10-31T00:10:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Awarded 50250 aUEC: " [84] to queue. New queue size: 3, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-10-31T00:11:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Fined 500 UEC: " [85] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-10-31T00:12:00.000Z> [Notice] <CEntityComponentShopUIProvider::SendShopBuyRequest> Sending SShopBuyRequest - playerId[2] shopId[8] shopName[SCShop_H_Pharmacy_Levski] kioskId[8] client_price[795.000000] itemClassGUID[7] itemName[crlf_consumable_healing_01] quantity[3]  [Team_CoreGameplayFeatures][Shops][UI]',
]


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def test_movements_from_real_lines():
    w = WalletTracker()
    moves = w.feed(recognize_all(_LINES))
    # l'achat refusé de 1 512 est retiré ; la vente se lit dans amount[…] ; objet : prix total
    assert [(m.kind, m.amount) for m in moves] == [
        ("commodity_buy", -337630), ("commodity_sell", 439642), ("reward", 50250),
        ("fine", -500), ("item_buy", -795)]
    assert w.session_gain() == -337630 + 439642 + 50250 - 500 - 795


def test_estimate_adds_movements_after_reading():
    w = WalletTracker()
    w.feed(recognize_all(_LINES))
    read_at = _epoch("2026-10-31T00:05:00")             # après la vente, avant la récompense
    assert estimate(11_000_000, read_at, w) == (11_000_000 + 50250 - 500 - 795, True)
    assert estimate(11_000_000, _epoch("2026-10-31T01:00:00"), w) == (11_000_000, False)
    assert estimate(0, read_at, w) == (0, False)


def test_new_login_restarts_session():
    w = WalletTracker()
    w.feed(recognize_all(_LINES))
    w.feed(recognize_all([_LINES[0].replace("2026-10-30T22:00", "2026-10-31T10:00")]))
    assert w.session_gain() == 0


def test_parse_balance_real_ocr():
    # textes Tesseract réels (captures du 31/10, 06/10 et 05/08)
    assert parse_balance("CURRENT BALANCE: ¤\n¤11,369,305 AUEC .\nENTORY\n") == (11369305, [])
    assert parse_balance("CURRENT BALANCE: >\nm11,369,305 AUEC\n") == (11369305, [])
    assert parse_balance("CURRENT BALANCE: ¤\nH¤11,705,259 AUEC\n") == (11705259, [])
    assert parse_balance("CURRENT BALANCE: I \\\nH3.581.507 auec\n") == (3581507, [])
    # ¤ lu comme un chiffre : montants possibles
    assert parse_balance("CURRENT BALANCE ¤\n511,369,305 AUEC\n") == (None, [11369305, 1369305, 511369305])
    assert parse_balance("CURRENT BALANCE: ¤i ¤\n538,393,958 AUEC 2 \\\n")[1][:2] == [38393958, 8393958]
    # illisible
    assert parse_balance("CURRENT BALANCE: M\nHWug2stenaset WON\n") == (None, [])
    assert parse_balance("SHOP INVENTORY\n11,369,305\n") == (None, [])


def test_choose_uses_known_balance():
    assert choose(11369305, [], 0) == 11369305
    assert choose(None, [38393958, 8393958, 538393958], 8_390_000) == 8393958
    assert choose(None, [38393958, 8393958], 0) is None          # rien pour départager
    assert choose(None, [38393958], 8_390_000) is None           # trop loin du solde connu


def test_player_keeps_latest_capture():
    p = Player()
    assert p.read_balance(11705259, [], 100.0)
    assert not p.read_balance(9_000_000, [], 50.0)               # capture plus ancienne
    assert p.read_balance(None, [11369141, 1369141, 511369141], 200.0)
    assert (p.balance, p.balance_ts) == (11369141, 200.0)
    assert Player.from_config(p.to_config()).balance == 11369141
