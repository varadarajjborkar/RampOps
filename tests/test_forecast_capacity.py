import random
import pytest
from rampops import capacity, forecast
from rampops.models import BomItem, Product, ValidationError


def P(pid="P1", dpw=1000, fe=0.9, be=0.9, fec=10, bec=3):
    return Product(pid, pid, dpw, fe, be, fec, bec, [BomItem("m", 1, "BE", 4)])


def test_esfc_aggregates_by_product_and_week():
    R = forecast.SampleRequest
    got = forecast.esfc([R("a", "P1", 100, 5), R("b", "P1", 50, 5), R("a", "P1", 10, 6), R("a", "P2", 1, 5)])
    assert got == {("P1", 5): 150, ("P1", 6): 10, ("P2", 5): 1}


def test_plan_build_math():
    units, wafers, fe0, be0 = forecast.plan_build(P(), 810, need_by=20)
    assert units == 891                     # 810 * 1.10
    assert wafers == 2                      # 891 / (1000*.9*.9=810) -> 1.1 -> 2
    assert be0 == 20 - 1 - 3 and fe0 == be0 - 10


def test_request_validation():
    with pytest.raises(ValidationError):
        forecast.SampleRequest("a", "P", 0, 1)
    with pytest.raises(ValidationError):
        forecast.SampleRequest("a", "P", 1, 1, priority=9)


def test_build_orders_group_and_priority():
    R = forecast.SampleRequest
    orders = forecast.build_orders([R("a", "P1", 100, 20, 3), R("b", "P1", 50, 20, 1), R("c", "P1", 5, 30)], {"P1": P()})
    assert len(orders) == 2
    assert orders[0].customers == ("a", "b") and orders[0].priority == 1 and orders[0].qty_requested == 150


def test_unknown_product_rejected():
    with pytest.raises(ValidationError):
        forecast.build_orders([forecast.SampleRequest("a", "ZZ", 1, 5)], {"P1": P()})


def order(oid="B1", pid="P1", wafers=5, units=1000, need=30, prio=3, fe0=16, be0=26):
    return forecast.BuildOrder(oid, pid, ("c",), units, units, wafers, need, fe0, be0, prio)


def test_on_time_booking_matches_ideal():
    b = capacity.SlotBook(10, 5000).book(order(), P())
    assert b.on_time and b.fe_weeks == {16: 5} and b.be_weeks == {26: 1000} and b.ship_week == 30 and not b.reasons


def test_pull_in_when_ideal_week_full():
    sb = capacity.SlotBook(10, 5000, max_pull_in=3)
    sb.fe_used[16] = 8                       # only 2 free in the ideal week
    b = sb.book(order(wafers=5), P())
    assert b.fe_weeks == {16: 2, 15: 3} and b.on_time


def test_push_later_when_window_full_causes_delay():
    sb = capacity.SlotBook(10, 5000, max_pull_in=1)
    for w in (15, 16):
        sb.fe_used[w] = 10
    b = sb.book(order(wafers=5), P())
    assert b.fe_weeks == {17: 5} and b.delay_weeks == 1
    assert any("FE capacity" in r for r in b.reasons)


def test_maintenance_override_blocks_week():
    sb = capacity.SlotBook(10, 5000, fe_overrides={16: 0}, max_pull_in=2)
    assert 16 not in sb.book(order(), P()).fe_weeks


def test_be_spreads_across_weeks():
    b = capacity.SlotBook(10, 400).book(order(units=1000), P())
    assert b.be_weeks == {26: 400, 27: 400, 28: 200}
    assert b.ship_week == 28 + 3 + 1 and b.delay_weeks == 2


def test_no_time_left_is_flagged():
    b = capacity.SlotBook(10, 5000, today=0).book(order(fe0=-4, be0=6, need=10), P())
    assert min(b.fe_weeks) == 0 and any("no time" in r for r in b.reasons)
    assert b.delay_weeks > 0


def test_horizon_exhausted():
    with pytest.raises(ValidationError):
        capacity.SlotBook(1, 1, horizon=30).book(order(wafers=100), P())


def test_priority_wins_scarce_slots():
    sb = capacity.SlotBook(5, 5000, max_pull_in=0)
    lo, hi = order("LO", prio=5), order("HI", prio=1)
    res = capacity.book_all([lo, hi], {"P1": P()}, sb)
    assert res["HI"].on_time and not res["LO"].on_time


def test_invalid_capacity():
    with pytest.raises(ValidationError):
        capacity.SlotBook(0, 10)


def test_utilisation_reports_used_weeks():
    sb = capacity.SlotBook(10, 1000)
    sb.book(order(wafers=5, units=500), P())
    assert sb.utilisation() == {"fe": 0.5, "be": 0.5}


def test_random_load_never_exceeds_capacity():
    rnd = random.Random(7)
    sb = capacity.SlotBook(12, 3000, horizon=120, fe_overrides={20: 0, 21: 0})
    orders = []
    for i in range(40):
        need = rnd.randint(18, 60)
        units, wafers, fe0, be0 = forecast.plan_build(P(), rnd.randint(500, 9000), need)
        orders.append(forecast.BuildOrder(f"R{i}", "P1", ("c",), units, units, wafers, need, fe0, be0, rnd.randint(1, 5)))
    res = capacity.book_all(orders, {"P1": P()}, sb)
    assert all(sb.fe_used[w] <= sb._fe_cap[w] and sb.be_used[w] <= sb._be_cap[w] for w in range(120))
    for o in orders:                          # every wafer and unit is placed exactly once
        assert sum(res[o.order_id].fe_weeks.values()) == o.wafers
        assert sum(res[o.order_id].be_weeks.values()) == o.units_planned
        assert 20 not in res[o.order_id].fe_weeks and 21 not in res[o.order_id].fe_weeks
