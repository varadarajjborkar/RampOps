"""Product master data with milestone-gated releases.

A product moves one phase at a time. Each phase has required master-data fields
and gate criteria; a milestone is only released when all of them are satisfied.
Planning code refuses to book builds for products that have not been released
to at least the engineering-samples phase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import Phase, Product, ValidationError

# Fields that must be populated before entering a phase (cumulative).
REQUIRED_FIELDS: dict[Phase, tuple[str, ...]] = {
    Phase.ENGINEERING_SAMPLES: ("package", "die_per_wafer", "fe_cycle_weeks", "be_cycle_weeks", "bom"),
    Phase.QUALIFICATION: ("fe_yield", "be_yield", "qual_plan_ref"),
    Phase.RAMP: ("target_weekly_units", "customers", "safe_launch_gate_passed"),
    Phase.VOLUME: ("ramp_exit_report",),
}

# Business gate checks beyond "field is filled": (key, human description).
GATE_CHECKS: dict[Phase, tuple[tuple[str, str], ...]] = {
    Phase.QUALIFICATION: (("samples_shipped", "engineering samples shipped to at least one customer"),),
    Phase.RAMP: (("qual_passed", "qualification passed"),),
    Phase.VOLUME: (("ramp_targets_met", "ramp targets met"),),
}


@dataclass
class MasterRecord:
    product: Product
    phase: Phase = Phase.CONCEPT
    attrs: dict = field(default_factory=dict)
    gates: dict = field(default_factory=dict)       # gate key -> bool
    history: list[tuple[str, str, str]] = field(default_factory=list)

    def value(self, name: str):
        if hasattr(self.product, name):
            v = getattr(self.product, name)
            return v if v not in (None, [], "") else None
        return self.attrs.get(name)


class MasterDataRegistry:
    def __init__(self) -> None:
        self._records: dict[str, MasterRecord] = {}

    def create(self, product: Product, **attrs) -> MasterRecord:
        if product.pid in self._records:
            raise ValidationError(f"{product.pid} already exists")
        rec = MasterRecord(product=product, attrs=dict(attrs))
        rec.history.append((_now(), "CREATED", Phase.CONCEPT.name))
        self._records[product.pid] = rec
        return rec

    def get(self, pid: str) -> MasterRecord:
        try:
            return self._records[pid]
        except KeyError:
            raise ValidationError(f"unknown product {pid}") from None

    def update(self, pid: str, **attrs) -> None:
        self.get(pid).attrs.update(attrs)

    def set_gate(self, pid: str, key: str, passed: bool = True) -> None:
        self.get(pid).gates[key] = passed

    def blockers(self, pid: str, target: Phase) -> list[str]:
        """Everything that currently prevents releasing `target` (empty = releasable)."""
        rec = self.get(pid)
        out: list[str] = []
        if target != rec.phase + 1:
            out.append(f"cannot jump from {rec.phase.name} to {target.name}; phases advance one at a time")
            return out
        for name in REQUIRED_FIELDS.get(target, ()):
            v = rec.value(name)
            if v in (None, False):
                out.append(f"missing master data: {name}")
        for key, desc in GATE_CHECKS.get(target, ()):
            if not rec.gates.get(key):
                out.append(f"gate not met: {desc}")
        return out

    def release(self, pid: str, target: Phase) -> MasterRecord:
        problems = self.blockers(pid, target)
        if problems:
            raise ValidationError(f"{pid} -> {target.name} blocked: " + "; ".join(problems))
        rec = self.get(pid)
        rec.history.append((_now(), rec.phase.name, target.name))
        rec.phase = target
        return rec

    def is_plannable(self, pid: str) -> bool:
        """Builds may only be planned once samples are released."""
        return self.get(pid).phase >= Phase.ENGINEERING_SAMPLES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
