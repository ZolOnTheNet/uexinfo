"""Chemin le plus rapide pour des livraisons (rules/route_plan.py) — lieux fictifs sur une ligne."""
import math

from uexinfo.rules.route_plan import Leg, STOP_S, fmt_duration, handling_s, plan

POS = {"A": 0.0, "B": 10.0, "C": 20.0, "D": 30.0, "E": 40.0}


def line(a, b):
    """Distance en Gm entre deux lieux fictifs alignés ; None pour un lieu inconnu."""
    if a not in POS or b not in POS:
        return None
    return abs(POS[a] - POS[b])


def nodes(route):
    return [s.node for s in route.stops]


def test_handling_counts_cart_trips():
    assert handling_s(0) == 0
    assert handling_s(8) == 25
    assert handling_s(9) == 50
    assert handling_s(190) == 24 * 25           # ≈ 10 min


def test_pickup_comes_before_delivery_and_same_place_is_one_stop():
    legs = [Leg(1, "m1", pickup="B", drop="D", scu=16), Leg(2, "m2", pickup="B", drop="C", scu=8)]
    r = plan("A", legs, line)
    assert nodes(r) == ["B", "C", "D"]
    assert [l.key for l in r.stops[0].load] == [1, 2]
    assert r.stops[-1].cargo_after == 0
    # chargé en premier : ce qui est livré en dernier (D)
    assert [l.key for l in r.stops[0].load_order(r.stops)] == [1, 2]
    assert r.exhaustive and not r.left_out


def test_time_counts_stops_not_only_distance():
    # deux livraisons de B : une à C (proche), une à E ; une 3e à D ; tout sur la même ligne
    legs = [Leg(i, f"m{i}", pickup="B", drop=d, scu=8) for i, d in enumerate("CDE")]
    r = plan("A", legs, line)
    assert nodes(r) == ["B", "C", "D", "E"]
    flight = 40 / 0.2341
    work = 4 * STOP_S + 6 * 25
    assert math.isclose(r.total_s, flight + work, rel_tol=1e-6)


def test_capacity_forces_two_rounds():
    legs = [Leg(1, "m1", pickup="B", drop="C", scu=30), Leg(2, "m2", pickup="B", drop="C", scu=30)]
    r = plan("A", legs, line, capacity=40)
    assert nodes(r) == ["B", "C", "B", "C"]
    assert all(s.cargo_after <= 40 for s in r.stops)


def test_same_place_can_come_back_for_crossed_deliveries():
    legs = [Leg(1, "m1", pickup="B", drop="C", scu=8), Leg(2, "m2", pickup="C", drop="B", scu=8)]
    r = plan("A", legs, line)
    assert nodes(r) == ["B", "C", "B"]


def test_cargo_already_aboard_needs_no_pickup():
    r = plan("A", [Leg(1, "m1", drop="C", scu=8), Leg(2, "m2", pickup="B", drop="D", scu=8)], line)
    assert nodes(r) == ["B", "C", "D"]
    assert r.stops[0].cargo_after == 16


def test_end_place_is_added_to_the_time():
    legs = [Leg(1, "m1", pickup="B", drop="C", scu=8)]
    free = plan("A", legs, line)
    to_a = plan("A", legs, line, end="A")
    assert math.isclose(to_a.total_s - free.total_s, 20 / 0.2341)
    assert to_a.end == "A"


def test_too_big_or_unknown_legs_are_left_out_with_a_reason():
    legs = [Leg(1, "m1", pickup="B", drop="C", scu=100), Leg(2, "m2", pickup="B", drop="", scu=8),
            Leg(3, "m3", pickup="B", drop="C", scu=8)]
    r = plan("A", legs, line, capacity=64)
    assert nodes(r) == ["B", "C"]
    why = {l.key: w for l, w in r.left_out}
    assert "soute" in why[1] and "préciser" in why[2]


def test_unknown_distance_is_flagged():
    r = plan("A", [Leg(1, "m1", pickup="B", drop="Z", scu=8)], line)
    assert nodes(r) == ["B", "Z"]
    assert r.unknown


def test_many_legs_still_answer_within_budget():
    legs = [Leg(i, f"m{i}", pickup="ABCDE"[i % 5], drop="ABCDE"[(i * 3 + 1) % 5], scu=8) for i in range(14)]
    r = plan("A", legs, line, capacity=64, budget=5000)
    assert sum(len(s.unload) for s in r.stops) == len([l for l in legs if l.pickup != l.drop])


def test_fmt_duration():
    assert fmt_duration(20) == "< 1 min"
    assert fmt_duration(41 * 60) == "41 min"
    assert fmt_duration(65 * 60) == "1 h 05"
