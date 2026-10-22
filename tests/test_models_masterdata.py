import pytest
from rampops.masterdata import MasterDataRegistry
from rampops.models import BomItem, Phase, Product, ValidationError


def prod(**kw):
    base = dict(pid="P1", name="n", die_per_wafer=1000, fe_yield=0.9, be_yield=0.95, fe_cycle_weeks=10, be_cycle_weeks=3,
                bom=[BomItem("lf", 1, "BE", 8)])
    base.update(kw)
    return Product(**base)


def test_good_units_per_wafer():
    assert prod().good_units_per_wafer == pytest.approx(855.0)


@pytest.mark.parametrize("kw", [dict(die_per_wafer=0), dict(fe_yield=0), dict(fe_yield=1.2), dict(be_yield=-1),
                                dict(fe_cycle_weeks=0), dict(be_cycle_weeks=0)])
def test_product_validation(kw):
    with pytest.raises(ValidationError):
        prod(**kw)


@pytest.mark.parametrize("args", [("X", 1, "QQ", 1), ("X", 0, "BE", 1), ("X", 1, "BE", -1)])
def test_bom_validation(args):
    with pytest.raises(ValidationError):
        BomItem(*args)


def test_cannot_skip_phases():
    r = MasterDataRegistry(); r.create(prod(), package="TO-220")
    assert "one at a time" in r.blockers("P1", Phase.RAMP)[0]
    with pytest.raises(ValidationError):
        r.release("P1", Phase.QUALIFICATION)


def test_missing_fields_are_listed_and_block_release():
    r = MasterDataRegistry(); r.create(prod(bom=[]))
    b = r.blockers("P1", Phase.ENGINEERING_SAMPLES)
    assert "missing master data: package" in b and "missing master data: bom" in b
    with pytest.raises(ValidationError, match="package"):
        r.release("P1", Phase.ENGINEERING_SAMPLES)


def test_full_lifecycle_requires_each_gate():
    r = MasterDataRegistry(); r.create(prod(), package="TO-220")
    r.release("P1", Phase.ENGINEERING_SAMPLES)
    assert r.is_plannable("P1")
    assert any("samples shipped" in b for b in r.blockers("P1", Phase.QUALIFICATION))
    r.update("P1", qual_plan_ref="QP-1"); r.set_gate("P1", "samples_shipped")
    r.release("P1", Phase.QUALIFICATION)
    r.update("P1", target_weekly_units=1000, customers=["A"], safe_launch_gate_passed=True)
    assert r.blockers("P1", Phase.RAMP) == ["gate not met: qualification passed"]
    r.set_gate("P1", "qual_passed")
    r.release("P1", Phase.RAMP)
    r.update("P1", ramp_exit_report="R-1"); r.set_gate("P1", "ramp_targets_met")
    assert r.release("P1", Phase.VOLUME).phase is Phase.VOLUME
    assert [h[2] for h in r.get("P1").history] == ["CONCEPT", "ENGINEERING_SAMPLES", "QUALIFICATION", "RAMP", "VOLUME"]


def test_not_plannable_in_concept():
    r = MasterDataRegistry(); r.create(prod())
    assert not r.is_plannable("P1")


def test_duplicate_and_unknown():
    r = MasterDataRegistry(); r.create(prod())
    with pytest.raises(ValidationError):
        r.create(prod())
    with pytest.raises(ValidationError):
        r.get("nope")


def test_false_gate_flag_blocks():
    r = MasterDataRegistry(); r.create(prod(), package="x")
    r.release("P1", Phase.ENGINEERING_SAMPLES)
    r.update("P1", qual_plan_ref="q"); r.set_gate("P1", "samples_shipped"); r.release("P1", Phase.QUALIFICATION)
    r.update("P1", target_weekly_units=1, customers=["A"], safe_launch_gate_passed=False); r.set_gate("P1", "qual_passed")
    assert "missing master data: safe_launch_gate_passed" in r.blockers("P1", Phase.RAMP)
