"""Engineering sample forecast (ESFC) and backward build scheduling.

Weeks are integers on a plan calendar (week 0 = plan start / "today").
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from .models import Product, ValidationError

ES_OVERBUILD = 0.10      # extra units built to cover test loss / scrap on engineering lots
SHIP_BUFFER_WEEKS = 1    # final test release, packing and transport


@dataclass(frozen=True)
class SampleRequest:
    customer: str
    pid: str
    qty: int
    need_by: int
    priority: int = 3     # 1 = highest

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValidationError("qty must be positive")
        if not 1 <= self.priority <= 5:
            raise ValidationError("priority must be 1..5")


@dataclass
class BuildOrder:
    order_id: str
    pid: str
    customers: tuple[str, ...]
    qty_requested: int
    units_planned: int
    wafers: int
    need_by: int
    ideal_fe_start: int
    ideal_be_start: int
    priority: int


def esfc(requests: list[SampleRequest]) -> dict[tuple[str, int], int]:
    """Consolidate sample requests: total quantity per (product, need-by week)."""
    total: dict[tuple[str, int], int] = defaultdict(int)
    for r in requests:
        total[(r.pid, r.need_by)] += r.qty
    return dict(total)


def plan_build(product: Product, qty: int, need_by: int) -> tuple[int, int, int, int]:
    """Return (units_planned, wafers, ideal_fe_start, ideal_be_start) for a delivery."""
    units = math.ceil(round(qty * (1 + ES_OVERBUILD), 6))   # round: 810*1.1 is 891.0000000000001 in floats
    wafers = math.ceil(units / product.good_units_per_wafer)
    be_start = need_by - SHIP_BUFFER_WEEKS - product.be_cycle_weeks
    fe_start = be_start - product.fe_cycle_weeks
    return units, wafers, fe_start, be_start


def build_orders(requests: list[SampleRequest], products: dict[str, Product]) -> list[BuildOrder]:
    """Turn consolidated requests into build orders (one per product and need-by week)."""
    groups: dict[tuple[str, int], list[SampleRequest]] = defaultdict(list)
    for r in requests:
        if r.pid not in products:
            raise ValidationError(f"request for unknown product {r.pid}")
        groups[(r.pid, r.need_by)].append(r)
    orders = []
    for n, ((pid, need_by), reqs) in enumerate(sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])), 1):
        qty = sum(r.qty for r in reqs)
        units, wafers, fe0, be0 = plan_build(products[pid], qty, need_by)
        orders.append(BuildOrder(
            order_id=f"B{n:03d}", pid=pid,
            customers=tuple(sorted({r.customer for r in reqs})),
            qty_requested=qty, units_planned=units, wafers=wafers, need_by=need_by,
            ideal_fe_start=fe0, ideal_be_start=be0,
            priority=min(r.priority for r in reqs),
        ))
    return orders
