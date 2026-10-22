from datetime import date, timedelta
import pytest
from rampops import pcn, scenario
from rampops.__main__ import main
from rampops.models import ValidationError
from rampops.pcn import ChangeType, CustomerImpact, Pcn, PcnState, QualTest

D = date(2027, 1, 4)


def make(ct=ChangeType.ASSEMBLY_SITE, plan=None, customers=None):
    p = Pcn("PCN-1", "P1", ct, "desc", "me", customers or [CustomerImpact("A", 800), CustomerImpact("B", 200)])
    p.qual_plan = plan if plan is not None else [QualTest(n, 3) for n in ("TC", "uHAST", "HTSL", "MSL")]
    return p


def to_notice(p):
    p.submit_for_review(D); p.approve_qual_plan(D); p.set_sample_strategy(1000, D); return p.distribute(D)


def test_illegal_transition():
    p = make()
    with pytest.raises(ValidationError, match="illegal"):
        p.distribute(D)


def test_qual_gaps_and_return_to_draft():
    p = make(plan=[QualTest("TC", 3)])
    p.submit_for_review(D)
    with pytest.raises(ValidationError, match="missing test HTSL"):
        p.approve_qual_plan(D)
    assert p.state is PcnState.DRAFT and "returned" in p.log[-1][3]


def test_min_lots_enforced():
    p = make(plan=[QualTest("TC", 1), QualTest("uHAST", 3), QualTest("HTSL", 3), QualTest("MSL", 3)])
    assert p.qual_plan_gaps() == ["TC: 1 lot(s), need 3"]


def test_material_change_needs_fewer_tests_and_datasheet_none():
    assert make(ChangeType.MATERIAL, [QualTest("TC", 1), QualTest("uHAST", 1), QualTest("MSL", 1)]).qual_plan_gaps() == []
    assert make(ChangeType.DATASHEET, []).qual_plan_gaps() == []


def test_notice_period_is_90_days_by_default():
    p = make(); eff = to_notice(p)
    assert eff == D + timedelta(days=90) and p.state is PcnState.NOTICE_PERIOD


def test_custom_notice_period():
    p = make(); p.notice_days = 60
    assert to_notice(p) == D + timedelta(days=60)


def test_sample_tiers():
    alloc, flags = pcn.sample_strategy([CustomerImpact("big", 800), CustomerImpact("mid", 150), CustomerImpact("small", 20)], 1000)
    assert alloc == {"big": 150, "mid": 75, "small": 30} and not flags


def test_sample_pool_scaling_and_flag():
    cs = [CustomerImpact("a", 500), CustomerImpact("b", 500)]
    alloc, flags = pcn.sample_strategy(cs, 200)
    assert sum(alloc.values()) <= 200 and not flags
    alloc, flags = pcn.sample_strategy(cs, 4)
    assert flags


def test_sample_pool_too_small_blocks_approval():
    p = make(); p.submit_for_review(D); p.approve_qual_plan(D)
    with pytest.raises(ValidationError, match="cannot cover"):
        p.set_sample_strategy(3, D)
    assert p.state is PcnState.SAMPLE_STRATEGY


def test_response_validation():
    p = make()
    with pytest.raises(ValidationError):
        p.record_response("Z", "approved", D)
    with pytest.raises(ValidationError):
        p.record_response("A", "maybe", D)


def test_cannot_close_with_open_items_or_unimplemented():
    p = make(); eff = to_notice(p)
    p.record_response("A", "approved", D); p.record_response("B", "objection", D)
    p.implemented = True
    with pytest.raises(ValidationError, match="open objection"):
        p.close(eff)
    p.record_response("B", "approved", D); p.implemented = False
    with pytest.raises(ValidationError, match="not yet implemented"):
        p.close(eff)
    p.implemented = True; p.close(eff)
    assert p.state is PcnState.CLOSED


def test_silence_is_deemed_acceptance_only_after_notice_period():
    p = make(); eff = to_notice(p); p.implemented = True
    with pytest.raises(ValidationError, match="no response yet"):
        p.close(eff - timedelta(days=1))
    p.close(eff)


def test_cannot_close_before_notice_period_state():
    with pytest.raises(ValidationError):
        make().close(D)


def test_cancel_and_terminal_states():
    p = make(); p.submit_for_review(D); p._move(PcnState.CANCELLED, D)
    with pytest.raises(ValidationError):
        p.submit_for_review(D)


def test_render_contains_key_facts():
    p = make(); to_notice(p)
    txt = pcn.render_pcn(p, "Widget")
    for needle in ("PCN-1", "Widget", str(D + timedelta(days=90)), "MSL (3 lots)", "A: 150 units"):
        assert needle in txt


def test_bridge_plan():
    demand = [10] * 10 + [100] * 2 + [10] * 10
    b = pcn.bridge_plan(demand, 8, 6)
    assert b["bridge_stock_units"] == 10 * 2 + 200 + 10 * 2 and b["recommend_defer"] and b["peak_weeks_in_window"] == [10, 11]
    assert not pcn.bridge_plan(demand, 14, 4)["recommend_defer"]
    with pytest.raises(ValidationError):
        pcn.bridge_plan(demand, 99, 4)


# ---- integration ------------------------------------------------------------
def test_scenario_is_deterministic_and_consistent():
    a, b = scenario.run_sample_planning(), scenario.run_sample_planning()
    assert {k: v.ship_week for k, v in a["bookings"].items()} == {k: v.ship_week for k, v in b["bookings"].items()}
    assert len(a["blocked_before_release"]) == 4 and a["gd30_blockers"] == ["missing master data: bom"]
    assert any(s.expedite_required for s in a["shortages"])


def test_scenario_ramp_and_pcn():
    r = scenario.run_ramp()
    assert r["rate"] == 1704 and r["fit"].service_level == 1.0 and r["fit"].peak_backlog == 0
    assert r["slow"].peak_backlog > 0 and not r["gate"][0]
    c = scenario.run_pcn()
    assert c["bridge"]["recommend_defer"]
    assert c["pcn"].state is PcnState.CLOSED and "MSL" in c["first_error"] and "info_request" in c["early_close_error"]


def test_cli_writes_report(tmp_path):
    out = tmp_path / "r.md"
    assert main(["demo", "--out", str(out)]) == 0
    text = out.read_text()
    assert "Sample builds" in text and "Product Change Notification" in text
