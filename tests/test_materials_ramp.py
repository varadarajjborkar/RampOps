import pytest
from rampops import capacity, forecast, materials, ramp
from rampops.models import BomItem, Product, ValidationError


def setup(wafers=4, units=4000):
    p = Product("P1", "p", 1000, 0.9, 0.9, 10, 3, [BomItem("blank", 1, "FE", 12), BomItem("lf", 1, "BE", 8)])
    o = forecast.BuildOrder("B1", "P1", ("c",), units, units, wafers, 30, 16, 26, 3)
    b = capacity.SlotBook(10, 10000).book(o, p)
    return p, o, {"B1": b}


def test_requirements_quantities_fe_per_wafer_be_per_unit():
    p, o, bk = setup()
    req = materials.requirements([o], bk, {"P1": p})
    assert req["blank"] == {16: (4.0, {"B1"})} and req["lf"] == {26: (4000.0, {"B1"})}


def test_no_shortage_when_stock_covers():
    p, o, bk = setup()
    inv = materials.Inventory({"blank": 10, "lf": 5000})
    assert materials.check_readiness([o], bk, {"P1": p}, inv) == []


def test_shortage_and_order_by_date():
    p, o, bk = setup()
    s = materials.check_readiness([o], bk, {"P1": p}, materials.Inventory({"blank": 10, "lf": 1000}))
    assert len(s) == 1 and s[0].material == "lf"
    assert s[0].first_short_week == 26 and s[0].peak_deficit == 3000 and s[0].order_by_week == 18
    assert not s[0].expedite_required and s[0].affected_orders == ["B1"]


def test_inbound_before_need_week_fixes_shortage_but_late_inbound_does_not():
    p, o, bk = setup()
    ok = materials.Inventory({"blank": 10, "lf": 0}, {"lf": [(25, 4000)]})
    late = materials.Inventory({"blank": 10, "lf": 0}, {"lf": [(27, 4000)]})
    assert materials.check_readiness([o], bk, {"P1": p}, ok) == []
    assert materials.check_readiness([o], bk, {"P1": p}, late)[0].first_short_week == 26


def test_expedite_when_order_by_in_past():
    p, o, bk = setup()
    inv = materials.Inventory({"blank": 0, "lf": 9999})     # blank first needed in week 16, lead time 12 -> order by week 4
    s = materials.check_readiness([o], bk, {"P1": p}, inv, today=3)
    assert s[0].order_by_week == 4 and not s[0].expedite_required
    assert materials.check_readiness([o], bk, {"P1": p}, inv, today=5)[0].expedite_required


# ---- ramp ----------------------------------------------------------------
def test_capacity_curve_caps_at_ceiling():
    assert ramp.capacity_curve(5, 100, 50, 220) == [100, 150, 200, 220, 220]


def test_capacity_curve_validation():
    with pytest.raises(ValidationError):
        ramp.capacity_curve(3, 500, 10, 100)


def test_backlog_carries_and_clears():
    r = ramp.simulate([100, 100, 100, 50], [60, 100, 150, 150])
    assert [x.backlog for x in r.rows] == [40, 40, 0, 0] and r.cleared and r.peak_backlog == 40
    assert r.service_level == pytest.approx((60 + 100 + 100 + 50) / 350)
    assert r.weeks_in_backlog == 2


def test_length_mismatch():
    with pytest.raises(ValidationError):
        ramp.simulate([1, 2], [1])


def test_required_rate_is_minimal_and_sufficient():
    demand = [int(1000 + 300 * w) for w in range(20)]
    rate = ramp.required_ramp_rate(demand, 1000, 10000)
    assert ramp.simulate(demand, ramp.capacity_curve(20, 1000, rate, 10000)).peak_backlog == 0
    assert ramp.simulate(demand, ramp.capacity_curve(20, 1000, rate - 1, 10000)).peak_backlog > 0


def test_required_rate_none_when_ceiling_too_low():
    assert ramp.required_ramp_rate([100, 5000], 100, 1000) is None


def test_required_rate_tolerates_backlog():
    d = [100, 400, 400]
    assert ramp.required_ramp_rate(d, 100, 500, max_backlog=150) < ramp.required_ramp_rate(d, 100, 500)


def test_gate_go():
    assert ramp.safe_launch_gate([.8, .93, .94, .95], .92, 5, 4, 0) == (True, [])


def test_gate_reports_every_reason():
    ok, why = ramp.safe_launch_gate([.9, .95], .92, 2, 4, 2)
    assert not ok and len(why) == 3
