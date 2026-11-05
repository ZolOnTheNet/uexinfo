"""Meilleur lot de contrats de transport pour une soute (rules/cargo_lot.py)."""
from uexinfo.rules.cargo_lot import LotItem, best_lot


def _it(title, reward, scu, exact=True, container=None, pickups=("Seraphim Station",)):
    return LotItem(key=(title, reward), title=title, reward=reward, scu=scu, exact=exact,
                   container=container, pickups=list(pickups))


# offres lues le 05/11 (montants et SCU du journal)
OFFERS = [
    _it("Cargo Transfer from Shuttered Facility", 188250, 29),
    _it("Junior Rank - Small Cargo Haul", 67000, 19),
    _it("Junior Rank - Small Cargo Haul", 55750, 19),
    _it("Rookie Rank - Direct Medium Cargo Haul", 50750, 111),
    _it("Rookie Rank - Direct Extra Small Cargo Haul", 49750, 10),
    _it("Rookie Rank - Small Cargo Haul", 42000, 8),
    _it("Rookie Rank - Direct Small Cargo Haul", 34750, 11),
]


def test_best_lot_fills_hold_for_max_reward():
    lot = best_lot(OFFERS, 96)
    assert lot.scu <= 96
    # tout sauf la Direct Medium (111 SCU > 96) : 7 offres → 6 tiennent (96 SCU)
    assert lot.scu == 96 and lot.reward == 188250 + 67000 + 55750 + 49750 + 42000 + 34750
    assert [why for _, why in lot.left_out] == ["111 SCU, plus que la soute (96)"]


def test_small_hold_keeps_best_combination():
    lot = best_lot(OFFERS, 40)
    assert lot.scu <= 40
    assert {i.title for i in lot.items} == {"Cargo Transfer from Shuttered Facility", "Rookie Rank - Direct Extra Small Cargo Haul"}


def test_contract_limit_and_container():
    many = [_it(f"O{i}", 1000 + i, 1) for i in range(12)]
    assert len(best_lot(many, 100).items) == 10                     # 10 contrats acceptés au plus
    assert len(best_lot(many, 100, max_count=3).items) == 3
    big = [_it("Grosses caisses", 90000, 32, container=8), _it("Petites", 20000, 8, container=2)]
    lot = best_lot(big, 64, max_container=4)
    assert [i.title for i in lot.items] == ["Petites"]
    assert "caisses de 8 SCU" in lot.left_out[0][1]


def test_unknown_scu_or_reward_left_out_and_estimate_flag():
    lot = best_lot([_it("Sans SCU", 50000, None), _it("Sans montant", 0, 10),
                    _it("Estimée", 30000, 16, exact=False)], 32)
    assert [i.title for i in lot.items] == ["Estimée"] and lot.estimated
    assert len(lot.left_out) == 2
