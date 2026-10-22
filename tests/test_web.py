"""The JSON API: routing, input limits, payload shape and caching headers."""
import json

import pytest

from rampops import web


def get(path):
    status, headers, body = web.dispatch(path)
    return status, headers, json.loads(body)


def test_health():
    status, headers, data = get("/api/health")
    assert status == 200 and data["status"] == "ok"
    assert headers["Cache-Control"] == "no-store"


def test_route_can_come_from_path_or_rewrite_query():
    assert get("/api/health")[2]["status"] == "ok"
    assert get("/api/index?route=health")[2]["status"] == "ok"


def test_unknown_route_is_404():
    status, _, data = get("/api/nope")
    assert status == 404 and "unknown route" in data["error"]


def test_only_get_and_head_allowed():
    status, headers, body = web.dispatch("/api/health", method="POST")
    assert status == 405 and headers["Allow"] == "GET, HEAD"


def test_head_has_no_body():
    status, headers, body = web.dispatch("/api/health", method="HEAD")
    assert status == 200 and body == b"" and int(headers["Content-Length"]) > 0


def test_oversized_request_target_rejected():
    status, _, _ = get("/api/plan?x=" + "a" * 3000)
    assert status == 414


def test_demo_headline_numbers_match_the_cli_report():
    _, headers, data = get("/api/demo")
    plan = data["plan"]
    assert plan["summary"]["orders"] == 11 and plan["summary"]["on_time"] == 8
    assert data["ramp"]["required_rate"] == 1704
    assert data["ramp"]["gate"]["go"] is False
    assert data["pcn"]["state"] == "CLOSED"
    assert "s-maxage" in headers["Cache-Control"]


def test_plan_payload_shape():
    _, _, data = get("/api/plan")
    o = data["orders"][0]
    for key in ("order_id", "pid", "customers", "units", "wafers", "need_by", "ship_week", "delay_weeks",
                "on_time", "reasons", "fe_weeks", "be_weeks"):
        assert key in o
    assert len(data["capacity"]["fe_used"]) == data["capacity"]["horizon"]
    assert data["blocked"]["pid"] == "GD30" and data["blocked"]["requests"] == 4
    assert {s["material"] for s in data["shortages"]} >= {"SiC wafer blank"}


def test_plan_what_if_changes_the_result():
    base = get("/api/plan")[2]["summary"]
    tight = get("/api/plan?fe_capacity=12")[2]["summary"]
    assert tight["on_time"] <= base["on_time"]


def test_plan_maintenance_weeks_parsed_and_capped():
    status, _, data = get("/api/plan?maintenance=10,11,12")
    assert status == 200 and data["maintenance_weeks"] == [10, 11, 12]
    assert get("/api/plan?maintenance=" + ",".join(str(i) for i in range(30)))[0] == 400


@pytest.mark.parametrize("query", ["fe_capacity=0", "fe_capacity=abc", "fe_capacity=99999999", "be_capacity=-5",
                                   "max_pull_in=50", "maintenance=1,x", "maintenance=999"])
def test_plan_rejects_bad_inputs(query):
    status, _, data = get("/api/plan?" + query)
    assert status == 400 and data["error"]


def test_plan_reports_exhausted_horizon_instead_of_crashing():
    status, _, data = get("/api/plan?fe_capacity=1")
    assert status == 400 and "horizon" in data["error"]


def test_ramp_defaults_and_custom_rate():
    d = get("/api/ramp")[2]
    assert d["required_rate"] == 1704 and d["required"]["service_level"] == 1.0
    assert len(d["demand"]) == 26 == len(d["scenario"]["capacity"])
    slow = get("/api/ramp?rate=800")[2]["scenario"]
    assert slow["capacity"][1] - slow["capacity"][0] == 800
    assert slow["service_level"] < 1.0


def test_ramp_unreachable_ceiling_is_reported_not_failed():
    d = get("/api/ramp?ceiling=10000")[2]
    assert d["required_rate"] is None and d["required"] is None


def test_ramp_gate_inputs():
    d = get("/api/ramp?yields=0.95,0.95,0.95&cover=6&issues=0")[2]
    assert d["gate"] == {"go": True, "reasons": []}
    d = get("/api/ramp?issues=2")[2]
    assert any("critical" in r for r in d["gate"]["reasons"])


def test_ramp_rejects_bad_inputs():
    for q in ("weeks=2", "weeks=500", "yields=1.5", "start=60000", "rate=-1"):
        assert get("/api/ramp?" + q)[0] == 400, q


def test_pcn_lifecycle_payload():
    d = get("/api/pcn")[2]
    assert d["pcn_id"] == "PCN-2026-014" and d["state"] == "CLOSED"
    assert d["notice_days"] == 90 and d["effective_date"] == "2027-03-11"
    assert d["log"][0] == {"date": "2026-12-01", "from": "DRAFT", "to": "QUAL_REVIEW", "note": "submitted"}
    assert "missing test MSL" in d["first_error"]
    assert [s["name"] for s in d["states"]][0] == "DRAFT"


def test_qualcheck_flags_missing_tests_and_low_lots():
    d = get("/api/qualcheck?change_type=ASSEMBLY_SITE&tests=TC:3,uHAST:2")[2]
    assert d["ok"] is False
    assert "missing test HTSL" in d["gaps"] and "uHAST: 2 lot(s), need 3" in d["gaps"]
    assert d["required_tests"] == ["HTSL", "MSL", "TC", "uHAST"]


def test_qualcheck_complete_plan_and_dates():
    d = get("/api/qualcheck?change_type=MATERIAL&tests=TC:1,uHAST:1,MSL:1&notify=2026-12-01&notice_days=120")[2]
    assert d["ok"] and d["effective_date"] == "2027-03-31"


def test_qualcheck_datasheet_needs_nothing():
    assert get("/api/qualcheck?change_type=DATASHEET")[2]["ok"] is True


@pytest.mark.parametrize("query", ["change_type=BOGUS", "tests=TC", "tests=TC:x", "tests=TC:999", "notify=2026-13-45",
                                   "notice_days=9999", "tests=" + ",".join(f"T{i}:1" for i in range(40))])
def test_qualcheck_rejects_bad_inputs(query):
    assert get("/api/qualcheck?" + query)[0] == 400


def test_bridge_flags_peak_in_window():
    d = get("/api/bridge?cutover=20&transition=6")[2]
    assert d["recommend_defer"] is True and d["bridge_stock_units"] == 232294
    assert get("/api/bridge?cutover=2&transition=3")[2]["recommend_defer"] is False
    assert get("/api/bridge?cutover=99")[0] == 400


def test_report_is_markdown():
    status, headers, body = web.dispatch("/api/report")
    assert status == 200 and headers["Content-Type"].startswith("text/markdown")
    assert body.decode().startswith("# RampOps demo report")


def test_unexpected_errors_do_not_leak_details(monkeypatch):
    def boom(_q):
        raise RuntimeError("secret internals")

    monkeypatch.setitem(web.ROUTES, "boom", boom)
    status, _, data = get("/api/boom")
    assert status == 500 and "secret" not in json.dumps(data)


def test_security_headers_on_every_response():
    for path in ("/api/health", "/api/nope"):
        _, headers, _ = web.dispatch(path)
        assert headers["X-Content-Type-Options"] == "nosniff"
