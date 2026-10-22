"""Time-phased material readiness: do we have the material when a booked build needs it?"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .capacity import Booking
from .forecast import BuildOrder
from .models import Product


@dataclass
class Inventory:
    on_hand: dict[str, float] = field(default_factory=dict)
    inbound: dict[str, list[tuple[int, float]]] = field(default_factory=dict)   # material -> [(arrival week, qty)]


@dataclass
class Shortage:
    material: str
    first_short_week: int
    peak_deficit: float
    order_by_week: int          # latest week a PO must be placed to land in time
    expedite_required: bool     # order-by week is already in the past
    affected_orders: list[str]


def requirements(orders: list[BuildOrder], bookings: dict[str, Booking],
                 products: dict[str, Product]) -> dict[str, dict[int, tuple[float, set[str]]]]:
    """material -> week -> (quantity needed, order ids)."""
    need: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [0.0, set()]))
    for o in orders:
        b, p = bookings[o.order_id], products[o.pid]
        for item in p.bom:
            if item.stage == "FE":
                for w, wafers in b.fe_weeks.items():
                    cell = need[item.material][w]
                    cell[0] += item.qty * wafers
                    cell[1].add(o.order_id)
            else:
                for w, units in b.be_weeks.items():
                    cell = need[item.material][w]
                    cell[0] += item.qty * units
                    cell[1].add(o.order_id)
    return {m: {w: (c[0], c[1]) for w, c in weeks.items()} for m, weeks in need.items()}


def check_readiness(orders: list[BuildOrder], bookings: dict[str, Booking],
                    products: dict[str, Product], inv: Inventory, today: int = 0) -> list[Shortage]:
    lead = {i.material: i.lead_time_weeks for p in products.values() for i in p.bom}
    out: list[Shortage] = []
    for material, weeks in sorted(requirements(orders, bookings, products).items()):
        arrivals = defaultdict(float)
        for w, q in inv.inbound.get(material, []):
            arrivals[w] += q
        balance = inv.on_hand.get(material, 0.0)
        first, peak, affected = None, 0.0, set()
        for w in sorted(set(weeks) | set(arrivals)):
            balance += arrivals.get(w, 0.0)
            if w in weeks:
                qty, ids = weeks[w]
                balance -= qty
                if balance < -1e-9:
                    if first is None:
                        first = w
                    affected |= ids
            peak = max(peak, -balance)
        if first is not None:
            order_by = first - lead.get(material, 0)
            out.append(Shortage(material, first, round(peak, 2), order_by, order_by < today, sorted(affected)))
    return sorted(out, key=lambda s: (s.first_short_week, s.material))
