"""Markdown report for the demo scenario."""
from __future__ import annotations

from . import scenario


def render() -> str:
    s, r, c = scenario.run_sample_planning(), scenario.run_ramp(), scenario.run_pcn()
    orders, bookings, products = s["orders"], s["bookings"], s["products"]
    late = [o for o in orders if not bookings[o.order_id].on_time]
    out = ["# RampOps demo report (synthetic data)\n"]
    out.append("## 1. Sample builds (ESFC -> wafer starts -> slots)\n")
    out.append(f"{len(s['requests'])} sample requests consolidated into {len(orders)} build orders; "
               f"{len(s['blocked_before_release'])} request(s) for GD30 were held back until its master data was complete "
               f"({'; '.join(s['gd30_blockers'])}). Frontend was shut for maintenance in weeks 10-11.\n")
    out.append("| Order | Product | Customers | Units | Wafers | Need-by | Ship | Delay | Notes |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for o in sorted(orders, key=lambda o: o.need_by):
        b = bookings[o.order_id]
        out.append(f"| {o.order_id} | {o.pid} | {', '.join(o.customers)} | {o.units_planned:,} | {o.wafers} | "
                   f"w{o.need_by} | w{b.ship_week} | {max(b.delay_weeks, 0)}w | {'; '.join(b.reasons) or 'on plan'} |")
    u = s["book"].utilisation()
    out.append(f"\nOn time: {len(orders) - len(late)}/{len(orders)}. "
               f"Utilisation of used weeks: frontend {u['fe']:.0%}, backend {u['be']:.0%}.\n")
    out.append("## 2. Material readiness\n")
    if s["shortages"]:
        out.append("| Material | First short | Peak deficit | Order by | Expedite | Orders hit |")
        out.append("|---|---|---|---|---|---|")
        for x in s["shortages"]:
            out.append(f"| {x.material} | w{x.first_short_week} | {x.peak_deficit:,.0f} | w{x.order_by_week} | "
                       f"{'YES' if x.expedite_required else 'no'} | {', '.join(x.affected_orders)} |")
    else:
        out.append("No shortages.")
    out.append("\n## 3. Ramp-up vs demand\n")
    out.append(f"Slow ramp (+1,500/wk): service level {r['slow'].service_level:.1%}, peak backlog "
               f"{r['slow'].peak_backlog:,}, backlog weeks {r['slow'].weeks_in_backlog}.  ")
    out.append(f"Minimum rate with zero backlog: +{r['rate']:,}/wk -> service level {r['fit'].service_level:.1%}.  ")
    ok, why = r["gate"]
    out.append(f"Safe-launch gate: {'GO' if ok else 'NO-GO'}" + (f" ({'; '.join(why)})" if why else "") + ".\n")
    out.append("## 4. Change management (PCN)\n")
    p = c["pcn"]
    out.append(f"{p.pcn_id}: {p.change_type.value}, state {p.state.name}, notified {p.notify_date}, effective {p.effective_date}.  ")
    out.append(f"First qual-plan review rejected: {c['first_error']}  ")
    out.append(f"Premature close blocked: {c['early_close_error']}  ")
    b = c["bridge"]
    out.append(f"Bridge stock {b['bridge_stock_units']:,} units; defer cutover: {b['recommend_defer']}.\n")
    out.append("### Audit trail\n")
    out += [f"- {d} {a} -> {b_} {n}".rstrip() for d, a, b_, n in p.log]
    out.append("\n---\n\n" + c["doc"])
    return "\n".join(out)
