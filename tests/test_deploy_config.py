"""Guards for the Vercel deployment contract, since there is no way to run Vercel in CI."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_vercel_entrypoint_exposes_handler():
    spec = importlib.util.spec_from_file_location("vercel_entry", ROOT / "api" / "index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from rampops.web import ApiHandler
    assert mod.handler is ApiHandler


def test_vercel_json_routes_api_and_locks_down_headers():
    cfg = json.loads((ROOT / "vercel.json").read_text())
    assert {"source": "/api/:route", "destination": "/api/index?route=:route"} in cfg["rewrites"]
    sent = {h["key"] for block in cfg["headers"] for h in block["headers"]}
    assert {"Content-Security-Policy", "Strict-Transport-Security", "X-Content-Type-Options",
            "Permissions-Policy", "Cross-Origin-Opener-Policy"} <= sent
    csp = next(h["value"] for b in cfg["headers"] for h in b["headers"] if h["key"] == "Content-Security-Policy")
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp and "frame-ancestors 'none'" in csp


def test_every_rewritten_route_exists():
    from rampops.web import ROUTES
    assert {"health", "demo", "plan", "ramp", "pcn", "qualcheck", "bridge"} <= set(ROUTES)
