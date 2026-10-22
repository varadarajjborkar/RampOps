"""Core data model: product lifecycle phases, bill of materials, products."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Phase(IntEnum):
    CONCEPT = 0
    ENGINEERING_SAMPLES = 1
    QUALIFICATION = 2
    RAMP = 3
    VOLUME = 4
    EOL = 5


class ValidationError(ValueError):
    """Raised when data or a state transition violates a rule."""


@dataclass(frozen=True)
class BomItem:
    """One material line.

    stage "FE" (frontend / wafer fab): qty is per wafer started.
    stage "BE" (backend / assembly+test): qty is per good unit built.
    """
    material: str
    qty: float
    stage: str
    lead_time_weeks: int

    def __post_init__(self) -> None:
        if self.stage not in ("FE", "BE"):
            raise ValidationError(f"{self.material}: stage must be FE or BE")
        if self.qty <= 0 or self.lead_time_weeks < 0:
            raise ValidationError(f"{self.material}: bad qty or lead time")


@dataclass
class Product:
    pid: str
    name: str
    die_per_wafer: int
    fe_yield: float          # wafer-sort yield, 0..1
    be_yield: float          # assembly + final-test yield, 0..1
    fe_cycle_weeks: int
    be_cycle_weeks: int
    bom: list[BomItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.die_per_wafer <= 0:
            raise ValidationError("die_per_wafer must be positive")
        for label, y in (("fe_yield", self.fe_yield), ("be_yield", self.be_yield)):
            if not 0 < y <= 1:
                raise ValidationError(f"{label} must be in (0, 1]")
        if self.fe_cycle_weeks < 1 or self.be_cycle_weeks < 1:
            raise ValidationError("cycle times must be at least 1 week")

    @property
    def good_units_per_wafer(self) -> float:
        return self.die_per_wafer * self.fe_yield * self.be_yield
