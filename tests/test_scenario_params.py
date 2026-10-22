"""The scenario runners accept what-if inputs; the defaults must reproduce the demo exactly."""
import pytest

from rampops import scenario
from rampops.models import ValidationError


def _ships(result):
    return {oid: b.ship_week for oid, b in result["bookings"].items()}


def test_planning_defaults_match_explicit_defaults():
    explicit = scenario.run_sample_planning(fe_capacity=25, be_capacity=40000, maintenance_weeks=(10, 11), max_pull_in=3)
    assert _ships(scenario.run_sample_planning()) == _ships(explicit)


def test_less_frontend_capacity_never_improves_on_time_count():
    base = scenario.run_sample_planning()
    tight = scenario.run_sample_planning(fe_capacity=12)

    def on_time(r):
        return sum(b.on_time for b in r["bookings"].values())

    assert on_time(tight) <= on_time(base)


def test_no_maintenance_shutdown_is_allowed():
    r = scenario.run_sample_planning(maintenance_weeks=())
    assert all(r["book"].fe_free(w) >= 0 for w in range(r["book"].horizon))


def test_planning_rejects_bad_capacity():
    with pytest.raises(ValidationError):
        scenario.run_sample_planning(fe_capacity=0)


def test_ramp_defaults_match_demo_numbers():
    r = scenario.run_ramp()
    assert r["rate"] == 1704
    assert r["fit"].service_level == 1.0


def test_ramp_accepts_custom_start_and_slow_rate():
    r = scenario.run_ramp(start=8000, slow_rate=800)
    assert r["slow"].rows[0].capacity == 8000
    assert r["slow"].rows[1].capacity == 8800


def test_ramp_unreachable_when_ceiling_below_demand():
    r = scenario.run_ramp(start=5000, ceiling=10000)
    assert r["rate"] is None
    assert r["fit"] is None
