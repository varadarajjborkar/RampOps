"""Capacity planning and slot booking across frontend (wafer starts) and backend (units).

Orders are booked in priority order. Frontend wafers are placed at the ideal week,
pulled earlier by up to `max_pull_in` weeks if the ideal week is full, and pushed
later only as a last resort. Backend can only start once the last wafer is out of the fab.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .forecast import SHIP_BUFFER_WEEKS, BuildOrder
from .models import Product, ValidationError


@dataclass
class Booking:
    order_id: str
    fe_weeks: dict[int, int]
    be_weeks: dict[int, int]
    ship_week: int
    delay_weeks: int
    reasons: list[str] = field(default_factory=list)

    @property
    def on_time(self) -> bool:
        return self.delay_weeks <= 0


class SlotBook:
    def __init__(self, fe_capacity: int, be_capacity: int, horizon: int = 104,
                 fe_overrides: dict[int, int] | None = None,
                 be_overrides: dict[int, int] | None = None,
                 max_pull_in: int = 3, today: int = 0) -> None:
        if fe_capacity <= 0 or be_capacity <= 0:
            raise ValidationError("capacities must be positive")
        self.horizon, self.max_pull_in, self.today = horizon, max_pull_in, today
        self._fe_cap = {w: (fe_overrides or {}).get(w, fe_capacity) for w in range(horizon)}
        self._be_cap = {w: (be_overrides or {}).get(w, be_capacity) for w in range(horizon)}
        self.fe_used: dict[int, int] = {w: 0 for w in range(horizon)}
        self.be_used: dict[int, int] = {w: 0 for w in range(horizon)}

    def fe_free(self, w: int) -> int:
        return self._fe_cap[w] - self.fe_used[w]

    def be_free(self, w: int) -> int:
        return self._be_cap[w] - self.be_used[w]

    def _take(self, free, used: dict[int, int], weeks, need: int) -> dict[int, int]:
        placed: dict[int, int] = {}
        for w in weeks:
            if need <= 0:
                break
            if not 0 <= w < self.horizon:
                continue
            n = min(free(w), need)
            if n > 0:
                used[w] += n
                placed[w] = n
                need -= n
        if need > 0:
            raise ValidationError("planning horizon exhausted")
        return placed

    def book(self, order: BuildOrder, product: Product) -> Booking:
        reasons: list[str] = []
        lo = max(self.today, order.ideal_fe_start - self.max_pull_in)
        ideal = max(self.today, order.ideal_fe_start)
        if order.ideal_fe_start < self.today:
            reasons.append(f"need-by date leaves no time: ideal FE start is week {order.ideal_fe_start}, plan starts at week {self.today}")
        # Latest-first inside the allowed window, then forward past it.
        weeks = list(range(ideal, lo - 1, -1)) + list(range(ideal + 1, self.horizon))
        fe = self._take(self.fe_free, self.fe_used, weeks, order.wafers)
        last_fe = max(fe)
        if last_fe > ideal:
            reasons.append(f"FE capacity: wafers pushed to week {last_fe} (ideal {order.ideal_fe_start})")
        be_ready = last_fe + product.fe_cycle_weeks
        be_start = max(be_ready, order.ideal_be_start, self.today)
        be = self._take(self.be_free, self.be_used, range(be_start, self.horizon), order.units_planned)
        last_be = max(be)
        if min(be) > order.ideal_be_start:
            reasons.append(f"BE start slipped to week {min(be)} (ideal {order.ideal_be_start})")
        if last_be > min(be):
            reasons.append(f"BE capacity: build spread over weeks {min(be)}-{last_be}")
        ship = last_be + product.be_cycle_weeks + SHIP_BUFFER_WEEKS
        return Booking(order.order_id, fe, be, ship, ship - order.need_by, reasons)

    def utilisation(self) -> dict[str, float]:
        used_fe, used_be = sum(self.fe_used.values()), sum(self.be_used.values())
        cap_fe = sum(self._fe_cap[w] for w, u in self.fe_used.items() if u)
        cap_be = sum(self._be_cap[w] for w, u in self.be_used.items() if u)
        return {"fe": used_fe / cap_fe if cap_fe else 0.0, "be": used_be / cap_be if cap_be else 0.0}


def book_all(orders: list[BuildOrder], products: dict[str, Product], book: SlotBook) -> dict[str, Booking]:
    """Book orders by priority, then need-by date, then id (deterministic)."""
    result = {}
    for o in sorted(orders, key=lambda o: (o.priority, o.need_by, o.order_id)):
        result[o.order_id] = book.book(o, products[o.pid])
    return result
