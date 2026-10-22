"""Smoke-test a running RampOps instance (local server, Vercel preview or production).

    python scripts/smoke.py http://127.0.0.1:8000
    python scripts/smoke.py https://your-deployment.vercel.app --headers

Checks status codes and payload shape for every endpoint, prints response time and size, and with
--headers also asserts the security headers a deployed site must send. Exit code 1 on any failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

REQUIRED_HEADERS = ("content-security-policy", "strict-transport-security", "x-content-type-options",
                    "permissions-policy", "cross-origin-opener-policy")

CHECKS = [
    ("/", 200, lambda b: b"<title>" in b),
    ("/api/health", 200, lambda b: json.loads(b)["status"] == "ok"),
    ("/api/demo", 200, lambda b: {"plan", "ramp", "pcn"} <= set(json.loads(b))),
    ("/api/plan?fe_capacity=20", 200, lambda b: json.loads(b)["summary"]["orders"] == 11),
    ("/api/ramp?rate=900", 200, lambda b: json.loads(b)["required_rate"] == 1704),
    ("/api/pcn", 200, lambda b: json.loads(b)["state"] == "CLOSED"),
    ("/api/qualcheck?tests=TC:3", 200, lambda b: json.loads(b)["ok"] is False),
    ("/api/bridge?cutover=20", 200, lambda b: json.loads(b)["recommend_defer"] is True),
    ("/api/report", 200, lambda b: b.startswith(b"# RampOps demo report")),
    ("/api/plan?fe_capacity=0", 400, lambda b: "error" in json.loads(b)),
    ("/api/nope", 404, lambda b: "error" in json.loads(b)),
]


def fetch(url: str) -> tuple[int, dict, bytes, float]:
    req = urllib.request.Request(url, headers={"User-Agent": "rampops-smoke/1"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body, status, headers = r.read(), r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        body, status, headers = e.read(), e.code, {k.lower(): v for k, v in e.headers.items()}
    return status, headers, body, (time.perf_counter() - t0) * 1000


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", help="base URL, for example http://127.0.0.1:8000")
    ap.add_argument("--headers", action="store_true", help="also require the production security headers")
    args = ap.parse_args(argv)
    base, failures = args.base.rstrip("/"), 0
    print(f"{'path':<32} {'status':>6} {'ms':>7} {'bytes':>8}  result")
    for path, want, check in CHECKS:
        status, headers, body, ms = fetch(base + path)
        problems = []
        if status != want:
            problems.append(f"expected {want}")
        else:
            try:
                if not check(body):
                    problems.append("payload check failed")
            except (ValueError, KeyError, TypeError) as e:
                problems.append(f"bad payload ({type(e).__name__})")
        if args.headers and status == 200:
            problems += [f"missing {h}" for h in REQUIRED_HEADERS if h not in headers]
        failures += bool(problems)
        print(f"{path:<32} {status:>6} {ms:>7.0f} {len(body):>8}  {'ok' if not problems else '; '.join(problems)}")
    print("\nall checks passed" if not failures else f"\n{failures} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
