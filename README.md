# RampOps

A small, dependency-free Python toolkit that models how a semiconductor-style product goes from
**engineering samples to volume ramp**, and how a **product change** is notified to customers.
It exists to practise the planning logic behind NPI sample management, ramp-up and
change management, not to replace an ERP/MRP system.

> **All data in this repository is synthetic.** Products, customers, lead times, yields and policy
> values (required qualification tests, 90-day notice, sample tiers) are invented defaults,
> modelled loosely on common industry practice and fully configurable.

## What it does

| Area | Module | Behaviour |
|---|---|---|
| Product master data | `masterdata.py` | Phase-gated releases (Concept → Samples → Qualification → Ramp → Volume). A phase is released only when its required fields and gate criteria are met; planning refuses products that have not been released. |
| Engineering sample forecast (ESFC) | `forecast.py` | Consolidates customer sample requests, then back-schedules wafer starts and assembly starts from need-by dates using yield, die per wafer, cycle times and an overbuild allowance. |
| Capacity & slot booking | `capacity.py` | Books frontend (wafers/week) and backend (units/week) slots in priority order, with pull-in, maintenance weeks, spill-over and an explained delay for every late order. |
| Material readiness | `materials.py` | Explodes the BOM against booked builds, time-phases stock and inbound supply, and reports shortages with the latest order-by week and an expedite flag. |
| Ramp-up | `ramp.py` | Simulates capacity vs. demand with backlog, finds the minimum weekly ramp rate that avoids backlog, and runs a go/no-go safe-launch gate (yield, material cover, open issues). |
| Change management | `pcn.py` | Guarded PCN state machine: qualification-plan review, customer sample strategy, distribution with notice period, customer responses, closure checks, audit trail, generated PCN document, and a cutover/bridge-stock heuristic against demand. |

## Run it

```bash
python -m rampops demo --out report.md      # end-to-end synthetic scenario
pip install pytest && pytest -q             # 65 tests
```

## Design notes

* Everything is deterministic: same inputs, same plan. Booking order is priority, then need-by date, then id.
* Rules are data, not code paths (`REQUIRED_TESTS`, `MIN_LOTS`, `DEFAULT_NOTICE_DAYS`, `GATE_CHECKS`).
* Invalid states raise `ValidationError` with the reason; nothing fails silently.
* A property-style test books 40 random orders and asserts no slot is ever over capacity and every wafer and unit is placed exactly once.
* Writing the tests caught a real bug: `810 * 1.10` is `891.0000000000001` in floating point, so `ceil` overbuilt by a unit. Quantities are now rounded before `ceil`.

## Limitations

Single-site, single-level BOM, integer weeks, no cost or yield learning-curve model, no ERP integration.
