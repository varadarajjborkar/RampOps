# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/varadarajjborkar/RampOps/security/advisories/new)
rather than a public issue. Include what you found, how to reproduce it and the impact you expect.
You can expect an acknowledgement within a few days.

## Scope

RampOps ships with synthetic data only and stores nothing: there are no accounts, no database and no
user-supplied content that is saved. The realistic attack surface is the public JSON API and the static
dashboard.

## What is in place

| Area | Control |
|---|---|
| Supply chain | No runtime dependencies. GitHub Actions are pinned to commit SHAs and kept current by Dependabot. CI uses a read-only token. |
| Input handling | Every API parameter is range-checked before it reaches the planner. Query fields, list lengths and request-target length are capped, so a request cannot demand unbounded work. |
| Errors | Domain errors return a readable `400`. Unexpected errors return a generic `500`; details go to the server log only. |
| Browser | Strict Content-Security-Policy (no inline script or style, same-origin only, `frame-ancestors 'none'`), HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP and CORP. |
| Rendering | All dynamic text is inserted with `textContent`; the codebase never uses `innerHTML`, and a test enforces it. |
| Methods | Only `GET` and `HEAD` are accepted; everything else returns `405`. |
| Analysis | CodeQL runs on pushes and pull requests to `main` and weekly. |

## Verifying a deployment

```bash
python scripts/smoke.py https://your-deployment.example --headers
```

This checks status codes, payload shape, response time and that every required security header is present.
