"""Ramp-up planning: match a capacity ramp to customer demand and gate the launch."""
from __future__ import annotations

from dataclasses import dataclass

from .models import ValidationError


@dataclass
class RampRow:
    week: int
    demand: int
    capacity: int
    output: int
    backlog: int


@dataclass
class RampResult:
    rows: list[RampRow]

    @property
    def service_level(self) -> float:
        total = sum(r.demand for r in self.rows)
        served = sum(min(r.demand, r.capacity) for r in self.rows)
        return served / total if total else 1.0

    @property
    def peak_backlog(self) -> int:
        return max((r.backlog for r in self.rows), default=0)

    @property
    def weeks_in_backlog(self) -> int:
        return sum(1 for r in self.rows if r.backlog > 0)

    @property
    def cleared(self) -> bool:
        return bool(self.rows) and self.rows[-1].backlog == 0


def capacity_curve(weeks: int, start: int, weekly_increase: int, ceiling: int) -> list[int]:
    if min(start, weekly_increase, ceiling) < 0 or start > ceiling:
        raise ValidationError("invalid ramp parameters")
    return [min(start + weekly_increase * w, ceiling) for w in range(weeks)]


def simulate(demand: list[int], capacity: list[int]) -> RampResult:
    """Weekly supply vs demand; unmet demand carries forward as backlog."""
    if len(demand) != len(capacity):
        raise ValidationError("demand and capacity must cover the same weeks")
    rows, backlog = [], 0
    for w, (d, c) in enumerate(zip(demand, capacity)):
        out = min(c, d + backlog)
        backlog = d + backlog - out
        rows.append(RampRow(w, d, c, out, backlog))
    return RampResult(rows)


def required_ramp_rate(demand: list[int], start: int, ceiling: int, max_backlog: int = 0) -> int | None:
    """Smallest integer weekly capacity increase that keeps peak backlog <= max_backlog."""
    weeks = len(demand)
    lo, hi = 0, max(ceiling, 1)
    if simulate(demand, capacity_curve(weeks, start, hi, ceiling)).peak_backlog > max_backlog:
        return None     # even an instant jump to the ceiling is not enough
    while lo < hi:
        mid = (lo + hi) // 2
        if simulate(demand, capacity_curve(weeks, start, mid, ceiling)).peak_backlog <= max_backlog:
            hi = mid
        else:
            lo = mid + 1
    return lo


def safe_launch_gate(yield_history: list[float], target_yield: float, material_cover_weeks: float,
                     min_cover_weeks: float, open_critical_issues: int,
                     consecutive_weeks: int = 3) -> tuple[bool, list[str]]:
    """Go / no-go for taking a product from sample builds into ramp."""
    reasons = []
    recent = yield_history[-consecutive_weeks:]
    if len(recent) < consecutive_weeks:
        reasons.append(f"need {consecutive_weeks} weeks of yield data, have {len(recent)}")
    elif min(recent) < target_yield:
        reasons.append(f"yield {min(recent):.1%} below target {target_yield:.1%} in last {consecutive_weeks} weeks")
    if material_cover_weeks < min_cover_weeks:
        reasons.append(f"material cover {material_cover_weeks:.1f}w below minimum {min_cover_weeks:.1f}w")
    if open_critical_issues:
        reasons.append(f"{open_critical_issues} open critical issue(s)")
    return (not reasons, reasons)
