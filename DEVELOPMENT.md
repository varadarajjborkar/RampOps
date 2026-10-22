# Development guide

## What this project is
RampOps is a small, dependency-free Python toolkit (stdlib only; pytest and ruff for development) that models
how a semiconductor-style product goes from **engineering samples to volume ramp**, and how a **product change
(PCN)** is notified to customers. A JSON API and a static dashboard sit on top of it. It is a learning and
portfolio project, **not** an ERP/MRP system.

**All data is synthetic.** Products, customers, lead times, yields and policy values (required qualification
tests, 90-day notice, sample tiers) are invented, configurable defaults. Never present them as any real
company's process or numbers, and never add real company or customer data.

## Commands
```bash
python -m rampops demo                 # print the end-to-end synthetic report
python -m rampops demo --out report.md # write it to a file
python -m rampops serve                # dashboard + API on http://127.0.0.1:8000
pip install pytest ruff
pytest -q                              # all tests should pass
ruff check .                           # lint
python scripts/smoke.py http://127.0.0.1:8000   # smoke-test a running instance
```
Requires Python 3.10+. There are no runtime dependencies; do not add any without a strong reason.

## Layout
| Path | Responsibility |
|---|---|
| `rampops/models.py` | `Phase` enum, `BomItem`, `Product`, `ValidationError`. Input validation lives here. |
| `rampops/masterdata.py` | `MasterDataRegistry`: phase-gated releases. `REQUIRED_FIELDS` and `GATE_CHECKS` are data tables. `is_plannable()` blocks planning for unreleased products. |
| `rampops/forecast.py` | ESFC: `SampleRequest`, `esfc()`, `plan_build()`, `build_orders()`. Back-schedules wafer starts and assembly starts from need-by dates. |
| `rampops/capacity.py` | `SlotBook`: frontend (wafers/week) and backend (units/week) slot booking with pull-in, maintenance weeks, spill-over and delay reasons. `book_all()` books by priority. |
| `rampops/materials.py` | BOM explosion and time-phased shortage check (`check_readiness`) with order-by week and expedite flag. |
| `rampops/ramp.py` | Capacity-vs-demand simulation, `required_ramp_rate()` (binary search), `safe_launch_gate()`. |
| `rampops/pcn.py` | `Pcn` state machine, qualification-plan checks, sample strategy, PCN document renderer, `bridge_plan()` heuristic. |
| `rampops/scenario.py` | The synthetic scenario used by the demo, the API and the integration tests. Capacity and ramp levers are keyword arguments. |
| `rampops/report.py`, `__main__.py` | Markdown report and CLI. |
| `rampops/web.py` | JSON API: `dispatch()` is a pure function from request target to (status, headers, body); `ApiHandler` adapts it to `http.server`. |
| `rampops/serve.py` | Local dev server: static files from `public/` plus the same API handler. |
| `api/index.py` | Vercel entry point. `vercel.json` rewrites `/api/:route` to it. |
| `public/` | The dashboard: `index.html`, `css/`, ES modules in `js/` and `js/views/`. No build step. |
| `tests/` | pytest suites per module, plus `test_web.py`, `test_serve.py`, `test_deploy_config.py`, `test_public_assets.py`. |

## Conventions
- **Time is integer weeks** on a plan calendar (week 0 = plan start). Dates appear only in the PCN module and the scenario.
- **Deterministic**: same inputs give the same plan. Booking order is priority, then need-by week, then order id. Do not introduce randomness (the one random test uses a fixed seed). The API relies on this for edge caching.
- **Rules are data, not code paths**: `REQUIRED_TESTS`, `MIN_LOTS`, `DEFAULT_NOTICE_DAYS`, `REQUIRED_FIELDS`, `GATE_CHECKS`, `ES_OVERBUILD`, `SHIP_BUFFER_WEEKS`. Change policy by editing these, not by adding branches.
- **Fail loudly**: invalid input or illegal state transitions raise `ValidationError` with a human-readable reason. The API turns it into a `400` with that reason. Unexpected errors become a generic `500`; never leak internals.
- **Bound every API input**: each parameter has a range check in `web.py` before it reaches the planner.
- Frontend (FE) BOM quantities are **per wafer**; backend (BE) quantities are **per good unit**.
- Dashboard code: use `textContent` (never `innerHTML`), no inline script or style (the CSP forbids both), no third-party URLs.
- Keep type hints and short docstrings that explain *why*, not *what*.

## Gotchas
- Floating point: `810 * 1.10` is `891.0000000000001`, so `ceil()` overbuilt by one unit. `plan_build()` rounds before `ceil`. Keep that rounding if you touch quantity math.
- `bridge_plan()` flags peak weeks with a strict `>` against the quantile value, so a flat demand curve never flags a peak.
- The PCN notice period (90 days) and test lists are illustrative defaults, loosely modelled on common industry practice (for example JEDEC J-STD-046 style notice). Do not state them as a company's actual policy.
- `SlotBook` places FE wafers latest-first inside the pull-in window, then forward. Backend cannot start before the last wafer leaves the fab.
- `run_ramp()` returns `rate=None` and `fit=None` when even an instant jump to the ceiling cannot clear demand. Callers must handle it.
- Headless browsers enforce a minimum window width of about 500px, so a narrower screenshot crops a wider layout.

## Branches and releases
- `main` is production. Merging into it triggers the Vercel production deploy.
- `dev` is where work happens. Pushes to it get a Vercel preview deploy and run CI.
- Fix problems on `dev`, then open a pull request into `main` once CI is green.

## Commit style
Conventional commits with a body that explains *why*:

```
feat(api): add stdlib JSON API over the planning core

Short paragraph on the reason and the design choices, then a list of
anything a reviewer should know.
```
Types in use: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`. Keep each commit to one logical change and keep the test suite green at every commit.

## When you change something
1. Add or update a test in the matching `tests/` file first (the suites are small and fast).
2. Run `pytest -q` and `ruff check .`; everything must pass.
3. Run `python -m rampops demo` and check the report still reads sensibly. If headline numbers change (build counts, on-time count, ramp rate), update `README.md` and any place the numbers are quoted.
4. Look at the dashboard (`python -m rampops serve`) in light and dark mode.
5. Keep the README "Limitations" section honest: single site, single-level BOM, integer weeks, no cost model, no ERP integration.
