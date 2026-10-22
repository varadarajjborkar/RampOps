"""Synthetic end-to-end scenario used by the demo and the integration test.

Every product, customer, quantity and date below is invented.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import capacity, forecast, materials, pcn, ramp
from .masterdata import MasterDataRegistry
from .models import BomItem, Phase, Product, ValidationError

PLAN_START = date(2026, 11, 2)     # a Monday; week 0 of the plan calendar


def week_to_date(w: int) -> date:
    return PLAN_START + timedelta(weeks=w)


def make_products() -> dict[str, Product]:
    return {p.pid: p for p in [
        Product("PX650", "650V power MOSFET", 2400, 0.92, 0.96, 10, 3, [
            BomItem("silicon wafer blank", 1, "FE", 12),
            BomItem("copper leadframe", 1, "BE", 10),
            BomItem("mold compound (g)", 0.8, "BE", 6),
            BomItem("bond wire (m)", 0.05, "BE", 14)]),
        Product("PX1200", "1200V SiC MOSFET", 600, 0.78, 0.94, 12, 4, [
            BomItem("SiC wafer blank", 1, "FE", 20),
            BomItem("copper leadframe", 1, "BE", 10),
            BomItem("mold compound (g)", 1.4, "BE", 6)]),
        Product("GD30", "30V gate driver IC", 5200, 0.90, 0.97, 9, 3, [
            BomItem("silicon wafer blank", 1, "FE", 12),
            BomItem("QFN substrate", 1, "BE", 8),
            BomItem("bond wire (m)", 0.03, "BE", 14)]),
    ]}


def make_requests() -> list[forecast.SampleRequest]:
    R = forecast.SampleRequest
    return [
        R("Aster Motors", "PX650", 12000, 16, 1), R("Borealis Drives", "PX650", 8000, 16, 2),
        R("Cobalt Energy", "PX650", 30000, 20, 2), R("Delta Grid", "PX1200", 9000, 22, 1),
        R("Aster Motors", "PX1200", 14000, 22, 2), R("Eon Charge", "PX1200", 20000, 26, 3),
        R("Fjord Solar", "GD30", 25000, 18, 3), R("Borealis Drives", "GD30", 15000, 18, 2),
        R("Cobalt Energy", "GD30", 40000, 24, 3), R("Delta Grid", "PX650", 6000, 24, 3),
        R("Eon Charge", "PX650", 18000, 28, 4), R("Fjord Solar", "PX1200", 7000, 30, 2),
        R("Aster Motors", "GD30", 10000, 14, 1), R("Cobalt Energy", "PX1200", 11000, 34, 4),
    ]


def make_inventory() -> materials.Inventory:
    return materials.Inventory(
        on_hand={"silicon wafer blank": 40, "SiC wafer blank": 30, "copper leadframe": 60000,
                 "mold compound (g)": 90000, "bond wire (m)": 6000, "QFN substrate": 30000},
        inbound={"silicon wafer blank": [(6, 30)], "SiC wafer blank": [(14, 40)],
                 "copper leadframe": [(30, 120000)], "QFN substrate": [(20, 60000)],
                 "bond wire (m)": [(18, 8000)]})


def run_sample_planning() -> dict:
    products = make_products()
    reg = MasterDataRegistry()
    for p in products.values():
        rec = reg.create(p, package="TO-247" if p.pid.startswith("PX") else "QFN-24")
    reg.release("PX650", Phase.ENGINEERING_SAMPLES)
    reg.release("PX1200", Phase.ENGINEERING_SAMPLES)
    # GD30's master data is incomplete (no approved BOM yet): the release must be refused,
    # and sample requests for it must not be planned.
    approved_bom, products["GD30"].bom = products["GD30"].bom, []
    gd30_blockers = reg.blockers("GD30", Phase.ENGINEERING_SAMPLES)
    blocked = [r for r in make_requests() if not reg.is_plannable(r.pid)]
    products["GD30"].bom = approved_bom
    reg.release("GD30", Phase.ENGINEERING_SAMPLES)
    reqs = make_requests()
    orders = forecast.build_orders(reqs, products)
    book = capacity.SlotBook(fe_capacity=25, be_capacity=40000, horizon=80, fe_overrides={w: 0 for w in (10, 11)})
    bookings = capacity.book_all(orders, products, book)
    shortages = materials.check_readiness(orders, bookings, products, make_inventory())
    return {"products": products, "registry": reg, "requests": reqs, "orders": orders, "bookings": bookings,
            "book": book, "shortages": shortages, "blocked_before_release": blocked, "gd30_blockers": gd30_blockers}


def demand_profile(weeks: int = 26) -> list[int]:
    """Logistic S-curve from ~2k to ~40k units/week."""
    import math
    return [int(2000 + 38000 / (1 + math.exp(-(w - 12) / 3))) for w in range(weeks)]


def run_ramp() -> dict:
    demand = demand_profile()
    start, ceiling = 5000, 45000
    rate = ramp.required_ramp_rate(demand, start, ceiling)
    slow = ramp.simulate(demand, ramp.capacity_curve(len(demand), start, 1500, ceiling))
    fit = ramp.simulate(demand, ramp.capacity_curve(len(demand), start, rate, ceiling))
    gate = ramp.safe_launch_gate([0.88, 0.91, 0.93, 0.92], 0.92, 3.5, 4.0, 0)
    return {"demand": demand, "rate": rate, "slow": slow, "fit": fit, "gate": gate}


def run_pcn() -> dict:
    d = date(2026, 12, 1)
    p = pcn.Pcn("PCN-2026-014", "PX650", pcn.ChangeType.ASSEMBLY_SITE,
                "Move PX650 assembly from Site A to Site B (same package, same materials).",
                "R&C planner",
                [pcn.CustomerImpact("Aster Motors", 600_000), pcn.CustomerImpact("Borealis Drives", 250_000),
                 pcn.CustomerImpact("Cobalt Energy", 900_000), pcn.CustomerImpact("Delta Grid", 40_000)])
    p.qual_plan = [pcn.QualTest("TC", 3), pcn.QualTest("uHAST", 3), pcn.QualTest("HTSL", 3)]
    p.submit_for_review(d)
    first_error = None
    try:
        p.approve_qual_plan(d)
    except ValidationError as e:
        first_error = str(e)
    p.submit_for_review(d + timedelta(days=3))
    p.qual_plan.append(pcn.QualTest("MSL", 3))
    p.approve_qual_plan(d + timedelta(days=5))
    p.set_sample_strategy(400, d + timedelta(days=6))
    eff = p.distribute(d + timedelta(days=10))
    p.record_response("Aster Motors", "approved", d + timedelta(days=30))
    p.record_response("Borealis Drives", "info_request", d + timedelta(days=34))
    p.record_response("Cobalt Energy", "approved", d + timedelta(days=50))
    p.record_response("Delta Grid", "approved", d + timedelta(days=52))
    early_close_error = None
    try:
        p.close(d + timedelta(days=60))
    except ValidationError as e:
        early_close_error = str(e)
    p.record_response("Borealis Drives", "approved", d + timedelta(days=70))
    p.implemented = True
    p.close(eff)
    cut = 20
    bridge = pcn.bridge_plan(demand_profile(), cut, 6)
    return {"pcn": p, "first_error": first_error, "early_close_error": early_close_error,
            "bridge": bridge, "doc": pcn.render_pcn(p, "650V power MOSFET")}
