"""Product Change Notification (PCN) workflow: a guarded state machine with an audit trail.

Policy values (required tests, lot counts, notice period) are configurable defaults
loosely modelled on common industry practice; they are not a statement of any
company's actual process.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from .models import ValidationError


class ChangeType(Enum):
    FAB_SITE = "fab site / wafer process change"
    ASSEMBLY_SITE = "assembly site change"
    DIE_SHRINK = "die shrink"
    MATERIAL = "assembly material change"
    DATASHEET = "datasheet-only update"


class PcnState(Enum):
    DRAFT = "draft"
    QUAL_REVIEW = "qualification plan review"
    SAMPLE_STRATEGY = "sample strategy"
    APPROVED = "approved for release"
    DISTRIBUTED = "distributed to customers"
    NOTICE_PERIOD = "customer notice period"
    CLOSED = "closed"
    CANCELLED = "cancelled"


REQUIRED_TESTS = {
    ChangeType.FAB_SITE: {"HTOL", "TC", "uHAST", "HTSL", "ESD", "LU"},
    ChangeType.DIE_SHRINK: {"HTOL", "TC", "uHAST", "ESD", "LU"},
    ChangeType.ASSEMBLY_SITE: {"TC", "uHAST", "HTSL", "MSL"},
    ChangeType.MATERIAL: {"TC", "uHAST", "MSL"},
    ChangeType.DATASHEET: set(),
}
MIN_LOTS = {ChangeType.FAB_SITE: 3, ChangeType.DIE_SHRINK: 3, ChangeType.ASSEMBLY_SITE: 3,
            ChangeType.MATERIAL: 1, ChangeType.DATASHEET: 0}
DEFAULT_NOTICE_DAYS = 90

_TRANSITIONS = {
    PcnState.DRAFT: {PcnState.QUAL_REVIEW, PcnState.CANCELLED},
    PcnState.QUAL_REVIEW: {PcnState.SAMPLE_STRATEGY, PcnState.DRAFT, PcnState.CANCELLED},
    PcnState.SAMPLE_STRATEGY: {PcnState.APPROVED, PcnState.CANCELLED},
    PcnState.APPROVED: {PcnState.DISTRIBUTED, PcnState.CANCELLED},
    PcnState.DISTRIBUTED: {PcnState.NOTICE_PERIOD},
    PcnState.NOTICE_PERIOD: {PcnState.CLOSED},
    PcnState.CLOSED: set(),
    PcnState.CANCELLED: set(),
}


@dataclass(frozen=True)
class QualTest:
    name: str
    lots: int
    samples_per_lot: int = 77


@dataclass
class CustomerImpact:
    customer: str
    annual_units: int


@dataclass
class Pcn:
    pcn_id: str
    pid: str
    change_type: ChangeType
    description: str
    owner: str
    customers: list[CustomerImpact]
    notice_days: int = DEFAULT_NOTICE_DAYS
    state: PcnState = PcnState.DRAFT
    qual_plan: list[QualTest] = field(default_factory=list)
    sample_alloc: dict[str, int] = field(default_factory=dict)
    notify_date: date | None = None
    responses: dict[str, str] = field(default_factory=dict)   # customer -> approved / objection / info_request
    implemented: bool = False
    log: list[tuple[date, str, str, str]] = field(default_factory=list)

    # -- helpers ---------------------------------------------------------
    def _move(self, new: PcnState, on: date, note: str = "") -> None:
        if new not in _TRANSITIONS[self.state]:
            raise ValidationError(f"{self.pcn_id}: illegal transition {self.state.name} -> {new.name}")
        self.log.append((on, self.state.name, new.name, note))
        self.state = new

    @property
    def effective_date(self) -> date | None:
        return self.notify_date + timedelta(days=self.notice_days) if self.notify_date else None

    # -- workflow steps --------------------------------------------------
    def submit_for_review(self, on: date) -> None:
        self._move(PcnState.QUAL_REVIEW, on, "submitted")

    def qual_plan_gaps(self) -> list[str]:
        gaps = []
        have = {t.name: t for t in self.qual_plan}
        for name in sorted(REQUIRED_TESTS[self.change_type]):
            if name not in have:
                gaps.append(f"missing test {name}")
            elif have[name].lots < MIN_LOTS[self.change_type]:
                gaps.append(f"{name}: {have[name].lots} lot(s), need {MIN_LOTS[self.change_type]}")
        return gaps

    def approve_qual_plan(self, on: date) -> None:
        gaps = self.qual_plan_gaps()
        if gaps:
            self._move(PcnState.DRAFT, on, "returned: " + "; ".join(gaps))
            raise ValidationError(f"{self.pcn_id}: qualification plan rejected: " + "; ".join(gaps))
        self._move(PcnState.SAMPLE_STRATEGY, on, "qual plan accepted")

    def set_sample_strategy(self, pool: int, on: date) -> dict[str, int]:
        self.sample_alloc, flags = sample_strategy(self.customers, pool)
        if flags:
            raise ValidationError(f"{self.pcn_id}: " + "; ".join(flags))
        self._move(PcnState.APPROVED, on, f"samples allocated: {sum(self.sample_alloc.values())} of {pool}")
        return self.sample_alloc

    def distribute(self, on: date) -> date:
        self.notify_date = on
        self._move(PcnState.DISTRIBUTED, on, f"notified {len(self.customers)} customer(s)")
        self._move(PcnState.NOTICE_PERIOD, on, f"effective {self.effective_date}")
        return self.effective_date

    def record_response(self, customer: str, status: str, on: date) -> None:
        if customer not in {c.customer for c in self.customers}:
            raise ValidationError(f"{customer} is not on {self.pcn_id}")
        if status not in ("approved", "objection", "info_request"):
            raise ValidationError("status must be approved, objection or info_request")
        self.responses[customer] = status
        self.log.append((on, self.state.name, "RESPONSE", f"{customer}: {status}"))

    def open_items(self, on: date) -> list[str]:
        items = []
        for c in self.customers:
            r = self.responses.get(c.customer)
            if r in ("objection", "info_request"):
                items.append(f"{c.customer}: open {r}")
            elif r is None and (self.effective_date is None or on < self.effective_date):
                items.append(f"{c.customer}: no response yet (notice period runs to {self.effective_date})")
        return items

    def close(self, on: date) -> None:
        if self.state is not PcnState.NOTICE_PERIOD:
            raise ValidationError(f"{self.pcn_id}: can only close from NOTICE_PERIOD")
        problems = self.open_items(on)
        if not self.implemented:
            problems.append("change not yet implemented")
        if problems:
            raise ValidationError(f"{self.pcn_id}: cannot close: " + "; ".join(problems))
        self._move(PcnState.CLOSED, on, "all customers resolved")


def sample_strategy(customers: list[CustomerImpact], pool: int) -> tuple[dict[str, int], list[str]]:
    """Tier customer samples by volume share; scale down if the pool is short."""
    total = sum(c.annual_units for c in customers) or 1

    def tier(c: CustomerImpact) -> int:
        share = c.annual_units / total
        return 150 if share >= 0.20 else 75 if share >= 0.05 else 30

    want = {c.customer: tier(c) for c in customers}
    need = sum(want.values())
    if need <= pool:
        return want, []
    scale = pool / need
    alloc = {k: max(5, math.floor(v * scale)) for k, v in want.items()}
    flags = []
    if sum(alloc.values()) > pool:
        flags.append(f"sample pool of {pool} cannot cover even minimum allocations")
    return alloc, flags


def render_pcn(p: Pcn, product_name: str) -> str:
    """Customer-facing notification text."""
    tests = ", ".join(f"{t.name} ({t.lots} lots)" for t in p.qual_plan) or "none required"
    samples = "\n".join(f"- {c}: {n} units" for c, n in sorted(p.sample_alloc.items())) or "- on request"
    return (
        f"# Product Change Notification {p.pcn_id}\n\n"
        f"**Product:** {product_name} ({p.pid})  \n"
        f"**Change:** {p.change_type.value}  \n"
        f"**Notification date:** {p.notify_date}  \n"
        f"**Earliest implementation:** {p.effective_date} ({p.notice_days}-day notice)  \n"
        f"**Owner:** {p.owner}\n\n"
        f"## Description\n{p.description}\n\n"
        f"## Qualification plan\n{tests}\n\n"
        f"## Samples available\n{samples}\n\n"
        f"Please acknowledge, or raise questions or objections, before {p.effective_date}.\n"
    )


def bridge_plan(demand: list[int], cutover_week: int, transition_weeks: int, peak_quantile: float = 0.9) -> dict:
    """Heuristic demand-management check for a change cutover.

    Bridge stock = units of the old version to build ahead to cover the transition window.
    Flags the cutover when it lands in a peak-demand window.
    """
    if not 0 <= cutover_week < len(demand):
        raise ValidationError("cutover week outside demand horizon")
    window = demand[cutover_week:cutover_week + transition_weeks]
    ranked = sorted(demand)
    threshold = ranked[min(len(ranked) - 1, int(peak_quantile * len(ranked)))]
    peaks = [cutover_week + i for i, d in enumerate(window) if d > threshold]
    return {"bridge_stock_units": sum(window), "peak_weeks_in_window": peaks,
            "recommend_defer": bool(peaks), "peak_threshold": threshold}
