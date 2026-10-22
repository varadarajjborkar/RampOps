<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
  <img src="docs/assets/logo-light.svg" alt="RampOps: engineering samples to volume ramp" width="420">
</picture>

**Plan sample builds, ramp capacity to demand, and notify customers of product changes. In one small, fast, dependency-free toolkit.**

**[Live demo: rampops.vercel.app](https://rampops.vercel.app/)**

[![ci](https://github.com/varadarajjborkar/RampOps/actions/workflows/ci.yml/badge.svg)](https://github.com/varadarajjborkar/RampOps/actions/workflows/ci.yml)
[![codeql](https://github.com/varadarajjborkar/RampOps/actions/workflows/codeql.yml/badge.svg)](https://github.com/varadarajjborkar/RampOps/actions/workflows/codeql.yml)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab)
![dependencies](https://img.shields.io/badge/runtime%20dependencies-0-1baf7a)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

</div>

<p align="center"><img src="docs/assets/screenshot-builds.png" alt="The RampOps sample builds view: a timeline of build orders, capacity charts and what-if controls" width="880"></p>

## What is RampOps?

Before a new chip goes into mass production, a company hands a few thousand **engineering samples** to customers so they can design it in. Those samples have to be built in a factory that is already busy, from materials that take weeks to arrive. Later the product has to **ramp** from a trickle to millions of units, and if anything about it changes, every customer must be **formally notified** with enough notice.

Teams usually juggle this in spreadsheets. RampOps turns it into code you can run, test and question:

- *Can we ship these samples on time, and if not, why not?*
- *Will we run out of any material, and by when must we order it?*
- *How fast must capacity grow so no customer waits?*
- *Is this change notice complete, and is the timing safe?*

It is a learning and portfolio project, **not** an ERP. **All data is synthetic.** Every product, customer, lead time and policy value is invented and configurable.

## What you can do with it

| Area | What it answers | Try it |
|---|---|---|
| **Master data gates** | Which products are allowed to be planned at all? | A product with no approved bill of materials is refused |
| **Sample forecast** | What must be built, and when must wafers start? | Requests merge into build orders, back-scheduled from need-by dates |
| **Capacity booking** | Which orders fit, which slip, and why? | Drag fab capacity down and watch builds go late |
| **Material readiness** | What runs short, and when must we order? | Flags materials whose order-by week has already passed |
| **Ramp-up** | How fast must capacity grow? | Finds the minimum weekly increase that leaves no backlog |
| **Change control (PCN)** | Is this change notice valid and safely timed? | A state machine that rejects steps taken out of order |

<table>
<tr>
<td><img src="docs/assets/screenshot-ramp.png" alt="Ramp-up view: demand against capacity lines and backlog" width="430"></td>
<td><img src="docs/assets/screenshot-change.png" alt="Change control view: PCN lifecycle, qualification checker, audit trail" width="430"></td>
</tr>
</table>

## Architecture

The browser talks to one small Python function. That function validates the request, runs the planning engine and returns JSON. The engine has no dependencies and knows nothing about the web.

```mermaid
flowchart LR
  user(["Browser"])
  subgraph edge["Vercel"]
    cdn["Edge CDN<br/>static files and cached API responses"]
    fn["Python function<br/>api/index.py"]
  end
  subgraph app["rampops package"]
    web["web.py<br/>route, validate, serialise"]
    subgraph engine["Planning engine: pure Python"]
      md["masterdata"] --> fc["forecast"] --> cap["capacity"] --> mat["materials"]
      cap --> ramp["ramp"]
      pcn["pcn"]
    end
  end
  user -->|"HTML, CSS, JS"| cdn
  user -->|"GET /api/..."| cdn
  cdn -->|"cache miss"| fn
  fn --> web
  web --> engine
```

## System design

### Life of a what-if request

Every answer is a pure function of the query string: same inputs, same plan. That is a deliberate design choice, because it makes every response safe to cache at the edge.

```mermaid
sequenceDiagram
  participant B as Browser
  participant E as Edge cache
  participant F as Python function
  participant P as Planning engine
  B->>E: GET /api/plan?fe_capacity=20
  alt already cached
    E-->>B: 200 JSON from the edge
  else cache miss
    E->>F: forward request
    F->>F: range-check every parameter
    F->>P: run scenario with fe_capacity=20
    P-->>F: bookings and shortages
    F-->>E: JSON with s-maxage and stale-while-revalidate
    E-->>B: 200 JSON
  end
  Note over B: A newer slider move aborts the older request
```

### From request to ramp: how the engine flows

```mermaid
flowchart TD
  A["Customer sample requests"] --> G{"Master-data gate<br/>released to samples?"}
  G -- no --> H["Held back, reason reported"]
  G -- yes --> B["ESFC: consolidate by product and need-by week"]
  B --> C["Back-schedule: ship, assembly, then wafer starts"]
  C --> D["Slot booking by priority<br/>fab and assembly capacity, pull-in, shutdowns"]
  D --> E["Material check<br/>time-phased stock vs BOM"]
  D --> F["Ramp planner<br/>capacity curve vs demand"]
  F --> L{"Safe-launch gate"}
  E --> L
  L --> P["PCN workflow<br/>qual plan, samples, 90-day notice, audit trail"]
```

### Delivery pipeline

```mermaid
flowchart LR
  dev["dev branch"] -->|"push"| ci["CI: lint, tests py3.10 to 3.13, smoke, CodeQL"]
  dev -->|"push"| prev["Vercel preview deploy"]
  ci -->|"green, pull request"| main["main branch"]
  main -->|"merge"| prod["Vercel production deploy"]
```

### Key decisions

| Decision | Why |
|---|---|
| **Standard library only** | Nothing to install, nothing to patch, nothing to supply-chain attack. The function cold-starts fast. |
| **Deterministic planning** | Same inputs give the same plan, so tests are exact and edge caching is safe. |
| **Rules are data** | Required tests, notice days and gate checks live in tables. Change policy by editing a value, not by adding branches. |
| **Fail loudly** | Invalid input or an illegal state change raises an error with a human-readable reason. Nothing is swallowed. |
| **One serverless function** | A single entry point behind a rewrite means one cold start and one thing to secure. |
| **No build step for the UI** | Plain ES modules and hand-drawn SVG: no bundler, no framework, no third-party requests. |

## Tech stack

| Layer | Technology |
|---|---|
| Engine and API | Python 3.10+ standard library (`http.server` handler, dataclasses, enums) |
| Dashboard | Vanilla JavaScript ES modules, hand-built SVG charts, CSS custom properties for light and dark themes |
| Hosting | Vercel: static CDN plus one Python serverless function |
| Quality | pytest (120 tests), ruff, GitHub Actions matrix on Python 3.10 to 3.13, CodeQL, Dependabot |
| Security | Strict Content-Security-Policy, HSTS, bounded inputs, actions pinned to commit SHAs |

## Quick start

```bash
git clone https://github.com/varadarajjborkar/RampOps.git
cd RampOps

python -m rampops serve              # dashboard and API at http://127.0.0.1:8000
python -m rampops demo               # the same scenario as a text report
python -m rampops demo --out report.md

pip install pytest && pytest -q      # 120 tests
```

Needs Python 3.10 or newer. There is nothing else to install.

## API

All endpoints are `GET`, return JSON, and reject out-of-range input with a `400` and a readable reason.

| Endpoint | Purpose | Useful parameters |
|---|---|---|
| `/api/demo` | Plan, ramp and PCN in one round trip | none |
| `/api/plan` | Sample builds, capacity, shortages | `fe_capacity`, `be_capacity`, `max_pull_in`, `maintenance=10,11` |
| `/api/ramp` | Demand vs capacity, minimum pace, launch gate | `start`, `ceiling`, `rate`, `weeks`, `yields`, `cover`, `issues` |
| `/api/pcn` | The demo change notification and audit trail | none |
| `/api/qualcheck` | Is this qualification plan complete? | `change_type`, `tests=TC:3,uHAST:3`, `notify`, `notice_days` |
| `/api/bridge` | Cutover timing and bridge stock | `cutover`, `transition` |
| `/api/report` | The Markdown report | none |
| `/api/health` | Liveness | none |

```bash
curl "http://127.0.0.1:8000/api/qualcheck?change_type=ASSEMBLY_SITE&tests=TC:3,uHAST:3,HTSL:3"
# {"ok":false,"gaps":["missing test MSL"], ...}
```

## Project layout

```text
rampops/            the engine and API (stdlib only)
  models.py           Phase, Product, BomItem, ValidationError
  masterdata.py       phase-gated releases
  forecast.py         sample forecast and back-scheduling
  capacity.py         fab and assembly slot booking
  materials.py        BOM explosion and shortage check
  ramp.py             capacity curve, minimum pace, launch gate
  pcn.py              change-notification state machine
  scenario.py         the synthetic scenario
  web.py, serve.py    JSON API and local dev server
api/index.py        Vercel entry point
public/             the dashboard (HTML, CSS, ES modules)
tests/              120 tests, including API and CSP guards
scripts/smoke.py    smoke-test any running instance
```

## Quality and security

- **Tests:** unit tests for every module, an integration test of the full scenario, real-socket tests of the server, and guards that keep the dashboard compatible with its CSP.
- **CI:** lint, a four-version Python matrix, a smoke test over real HTTP, and one aggregate `ci-ok` check.
- **Security:** a strict CSP with no inline script or style, HSTS, bounded and validated input, a generic error body so internals never leak, and CodeQL scanning. See [SECURITY.md](SECURITY.md).
- **Check a deployment:** `python scripts/smoke.py https://your-deployment --headers` verifies status codes, payloads, latency and security headers.

## Limitations

Honest about scope: single site, single-level bill of materials, integer weeks, no cost or yield learning-curve model, no ERP integration. Policy values (such as the 90-day notice and required qualification tests) are illustrative defaults loosely modelled on common industry practice, not any company's actual process.

## Roadmap

- Multi-level BOM and substitute materials
- Wafer-start smoothing and lot-size rounding
- Last-time-buy and ramp-down scheduling
- CSV and JSON import for requests, inventory and demand

## Contributing

Work happens on `dev`; `main` is production. See [DEVELOPMENT.md](DEVELOPMENT.md) for conventions, commands and the commit style.

## License

[MIT](LICENSE)
