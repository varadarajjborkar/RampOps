"""JSON API over the planning core, used by the web dashboard.

`dispatch()` is a pure function from a request target to (status, headers, body); the
`ApiHandler` class adapts it to `http.server`, which is what Vercel's Python runtime and the
local dev server both speak. Everything here is stdlib only.

Every endpoint is deterministic (same query, same answer), so responses are safe to cache at the
edge. Every user-supplied number is range-checked before it reaches the planner, so a request can
never ask for unbounded work.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from collections.abc import Callable
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl, urlsplit

from . import __version__, pcn, report, scenario
from .models import ValidationError

MAX_TARGET_LEN = 2048
MAX_QUERY_FIELDS = 40

# Responses are deterministic functions of the URL, so the edge may keep them for an hour and
# serve a stale copy for a day while it refreshes in the background.
CACHE_PUBLIC = "public, max-age=60, s-maxage=3600, stale-while-revalidate=86400"
CACHE_NONE = "no-store"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class BadRequest(ValidationError):
    """A query parameter is missing, malformed or out of range."""


# -- query parsing ---------------------------------------------------------------------------

def _int(q: dict, name: str, default: int, lo: int, hi: int) -> int:
    raw = q.get(name)
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except ValueError:
        raise BadRequest(f"{name} must be a whole number") from None
    if not lo <= v <= hi:
        raise BadRequest(f"{name} must be between {lo:,} and {hi:,}")
    return v


def _float(q: dict, name: str, default: float, lo: float, hi: float) -> float:
    raw = q.get(name)
    if raw in (None, ""):
        return default
    try:
        v = float(raw)
    except ValueError:
        raise BadRequest(f"{name} must be a number") from None
    if not lo <= v <= hi:       # also rejects NaN, which compares false to everything
        raise BadRequest(f"{name} must be between {lo:g} and {hi:g}")
    return v


def _list(q: dict, name: str, convert: Callable[[str], object], default: tuple, max_items: int) -> tuple:
    raw = q.get(name)
    if raw is None:
        return default
    parts = [p for p in raw.split(",") if p.strip()]
    if len(parts) > max_items:
        raise BadRequest(f"{name} takes at most {max_items} values")
    try:
        return tuple(convert(p.strip()) for p in parts)
    except BadRequest:
        raise
    except ValueError:
        raise BadRequest(f"{name} has a malformed value") from None


def _date(q: dict, name: str, default: date) -> date:
    raw = q.get(name)
    if raw in (None, ""):
        return default
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        raise BadRequest(f"{name} must be an ISO date like 2026-12-11") from None
    if not date(2000, 1, 1) <= d <= date(2100, 12, 31):
        raise BadRequest(f"{name} must be between 2000 and 2100")
    return d


# -- serializers -----------------------------------------------------------------------------

def _plan_payload(fe_capacity: int, be_capacity: int, maintenance: tuple[int, ...], max_pull_in: int) -> dict:
    s = scenario.run_sample_planning(fe_capacity, be_capacity, maintenance, max_pull_in)
    orders, bookings, book = s["orders"], s["bookings"], s["book"]
    rows = []
    for o in sorted(orders, key=lambda o: (o.need_by, o.order_id)):
        b = bookings[o.order_id]
        rows.append({
            "order_id": o.order_id, "pid": o.pid, "customers": list(o.customers), "priority": o.priority,
            "qty_requested": o.qty_requested, "units": o.units_planned, "wafers": o.wafers,
            "need_by": o.need_by, "ideal_fe_start": o.ideal_fe_start, "ideal_be_start": o.ideal_be_start,
            "ship_week": b.ship_week, "delay_weeks": max(b.delay_weeks, 0), "on_time": b.on_time,
            "reasons": b.reasons, "fe_weeks": sorted(b.fe_weeks.items()), "be_weeks": sorted(b.be_weeks.items()),
        })
    weeks = range(book.horizon)
    util = book.utilisation()
    return {
        "params": {"fe_capacity": fe_capacity, "be_capacity": be_capacity, "max_pull_in": max_pull_in},
        "maintenance_weeks": list(maintenance),
        "plan_start": scenario.PLAN_START.isoformat(),
        "summary": {"requests": len(s["requests"]), "orders": len(orders),
                    "on_time": sum(r["on_time"] for r in rows),
                    "utilisation": {"fe": round(util["fe"], 4), "be": round(util["be"], 4)}},
        "orders": rows,
        "capacity": {"horizon": book.horizon,
                     "fe_used": [book.fe_used[w] for w in weeks],
                     "fe_cap": [book.fe_used[w] + book.fe_free(w) for w in weeks],
                     "be_used": [book.be_used[w] for w in weeks],
                     "be_cap": [book.be_used[w] + book.be_free(w) for w in weeks]},
        "shortages": [{"material": x.material, "first_short_week": x.first_short_week,
                       "peak_deficit": x.peak_deficit, "order_by_week": x.order_by_week,
                       "expedite": x.expedite_required, "orders": x.affected_orders} for x in s["shortages"]],
        "blocked": {"pid": "GD30", "requests": len(s["blocked_before_release"]), "reasons": s["gd30_blockers"]},
        "products": [{"pid": p.pid, "name": p.name, "die_per_wafer": p.die_per_wafer, "fe_yield": p.fe_yield,
                      "be_yield": p.be_yield, "fe_cycle_weeks": p.fe_cycle_weeks, "be_cycle_weeks": p.be_cycle_weeks,
                      "good_units_per_wafer": round(p.good_units_per_wafer, 1),
                      "bom": [{"material": i.material, "qty": i.qty, "stage": i.stage, "lead_time_weeks": i.lead_time_weeks}
                              for i in p.bom]} for p in s["products"].values()],
    }


def _ramp_payload(q: dict) -> dict:
    weeks = _int(q, "weeks", 26, 4, 104)
    start = _int(q, "start", 5000, 0, 1_000_000)
    ceiling = _int(q, "ceiling", 45000, 1, 1_000_000)
    rate = _int(q, "rate", 1500, 0, 1_000_000)
    yields = _list(q, "yields", float, (0.88, 0.91, 0.93, 0.92), 52)
    if any(not 0 < y <= 1 for y in yields):
        raise BadRequest("yields must be fractions between 0 and 1")
    target = _float(q, "target_yield", 0.92, 0.01, 1.0)
    cover = _float(q, "cover", 3.5, 0, 52)
    min_cover = _float(q, "min_cover", 4.0, 0, 52)
    issues = _int(q, "issues", 0, 0, 100)
    r = scenario.run_ramp(start, ceiling, rate, weeks, yields, target, cover, min_cover, issues)

    def curve(res):
        if res is None:
            return None
        return {"capacity": [x.capacity for x in res.rows], "output": [x.output for x in res.rows],
                "backlog": [x.backlog for x in res.rows], "service_level": round(res.service_level, 4),
                "peak_backlog": res.peak_backlog, "weeks_in_backlog": res.weeks_in_backlog, "cleared": res.cleared}

    go, reasons = r["gate"]
    return {"params": {"weeks": weeks, "start": start, "ceiling": ceiling, "rate": rate},
            "demand": r["demand"], "scenario": curve(r["slow"]), "required_rate": r["rate"],
            "required": curve(r["fit"]), "gate": {"go": go, "reasons": reasons}}


def _pcn_payload() -> dict:
    c = scenario.run_pcn()
    p = c["pcn"]
    return {
        "pcn_id": p.pcn_id, "pid": p.pid, "change_type": p.change_type.name, "change_label": p.change_type.value,
        "description": p.description, "owner": p.owner, "state": p.state.name,
        "notify_date": p.notify_date.isoformat(), "effective_date": p.effective_date.isoformat(),
        "notice_days": p.notice_days,
        "customers": [{"customer": x.customer, "annual_units": x.annual_units} for x in p.customers],
        "qual_plan": [{"name": t.name, "lots": t.lots} for t in p.qual_plan],
        "sample_alloc": p.sample_alloc, "responses": p.responses,
        "log": [{"date": d.isoformat(), "from": a, "to": b, "note": n} for d, a, b, n in p.log],
        "states": [{"name": s.name, "label": s.value} for s in pcn.PcnState],
        "first_error": c["first_error"], "early_close_error": c["early_close_error"],
        "bridge": c["bridge"], "document": c["doc"],
    }


def _qualcheck_payload(q: dict) -> dict:
    name = q.get("change_type", "ASSEMBLY_SITE")
    if name not in pcn.ChangeType.__members__:
        raise BadRequest("change_type must be one of " + ", ".join(pcn.ChangeType.__members__))
    kind = pcn.ChangeType[name]

    def test(token: str) -> pcn.QualTest:
        label, sep, lots = token.partition(":")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_-]{1,12}", label):
            raise ValueError(token)
        n = int(lots)
        if not 0 <= n <= 50:
            raise BadRequest("lots must be between 0 and 50")
        return pcn.QualTest(label, n)

    tests = _list(q, "tests", test, (), 20)
    notice = _int(q, "notice_days", pcn.DEFAULT_NOTICE_DAYS, 0, 365)
    notify = _date(q, "notify", date(2026, 12, 11))
    p = pcn.Pcn("PCN-CHECK", "-", kind, "what-if check", "dashboard", [], notice_days=notice)
    p.qual_plan = list(tests)
    gaps = p.qual_plan_gaps()
    return {"change_type": name, "change_label": kind.value, "required_tests": sorted(pcn.REQUIRED_TESTS[kind]),
            "min_lots": pcn.MIN_LOTS[kind], "gaps": gaps, "ok": not gaps, "notice_days": notice,
            "notify_date": notify.isoformat(), "effective_date": (notify + timedelta(days=notice)).isoformat()}


def _bridge_payload(q: dict) -> dict:
    demand = scenario.demand_profile()
    cutover = _int(q, "cutover", 20, 0, 1000)
    transition = _int(q, "transition", 6, 1, 52)
    b = pcn.bridge_plan(demand, cutover, transition)
    return {**b, "cutover": cutover, "transition": transition, "demand": demand}


# -- routes ----------------------------------------------------------------------------------

def _plan(q: dict) -> dict:
    maintenance = _list(q, "maintenance", int, (10, 11), 20)
    if any(not 0 <= w < 80 for w in maintenance):
        raise BadRequest("maintenance weeks must be between 0 and 79")
    return _plan_payload(_int(q, "fe_capacity", 25, 1, 100_000), _int(q, "be_capacity", 40000, 1, 10_000_000),
                         tuple(sorted(set(maintenance))), _int(q, "max_pull_in", 3, 0, 12))


def _demo(_q: dict) -> dict:
    return {"version": __version__, "plan": _plan({}), "ramp": _ramp_payload({}), "pcn": _pcn_payload()}


ROUTES: dict[str, Callable[[dict], dict]] = {
    "health": lambda _q: {"status": "ok", "version": __version__},
    "demo": _demo,
    "plan": _plan,
    "ramp": _ramp_payload,
    "pcn": lambda _q: _pcn_payload(),
    "qualcheck": _qualcheck_payload,
    "bridge": _bridge_payload,
}


# -- dispatch --------------------------------------------------------------------------------

def _response(status: int, body: bytes, content_type: str, cache: str, method: str, extra: dict | None = None):
    headers = {"Content-Type": content_type, "Content-Length": str(len(body)), "Cache-Control": cache,
               **SECURITY_HEADERS, **(extra or {})}
    return status, headers, b"" if method == "HEAD" else body


def _json(status: int, payload: dict, cache: str, method: str, extra: dict | None = None):
    body = json.dumps(payload, separators=(",", ":")).encode()
    return _response(status, body, "application/json; charset=utf-8", cache, method, extra)


def dispatch(target: str, method: str = "GET") -> tuple[int, dict, bytes]:
    """Handle one request target such as '/api/plan?fe_capacity=20'."""
    if method not in ("GET", "HEAD"):
        return _json(405, {"error": "method not allowed"}, CACHE_NONE, method, {"Allow": "GET, HEAD"})
    if len(target) > MAX_TARGET_LEN:
        return _json(414, {"error": "request target too long"}, CACHE_NONE, method)
    parts = urlsplit(target)
    try:
        q = dict(parse_qsl(parts.query, keep_blank_values=True, max_num_fields=MAX_QUERY_FIELDS))
    except ValueError:
        return _json(400, {"error": "too many query parameters"}, CACHE_NONE, method)
    # Behind the Vercel rewrite the route arrives as ?route=...; locally it is the last path segment.
    route = q.pop("route", None) or parts.path.rstrip("/").rsplit("/", 1)[-1]
    if route == "report":
        return _response(200, report.render().encode(), "text/markdown; charset=utf-8", CACHE_PUBLIC, method)
    fn = ROUTES.get(route)
    if fn is None:
        return _json(404, {"error": f"unknown route '{route[:40]}'"}, CACHE_NONE, method)
    try:
        return _json(200, fn(q), CACHE_NONE if route == "health" else CACHE_PUBLIC, method)
    except ValidationError as e:
        return _json(400, {"error": str(e)}, CACHE_NONE, method)
    except Exception:       # noqa: BLE001 - last-resort guard; details go to the server log, not the client
        traceback.print_exc(file=sys.stderr)
        return _json(500, {"error": "internal error"}, CACHE_NONE, method)


def respond(h: BaseHTTPRequestHandler) -> None:
    """Answer the request on `h` from the API."""
    status, headers, body = dispatch(h.path, h.command)
    h.send_response(status)
    for k, v in headers.items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)


class ApiHandler(BaseHTTPRequestHandler):
    """http.server adapter; Vercel's Python runtime looks for a class named `handler`."""

    def _serve(self) -> None:
        respond(self)

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _serve
