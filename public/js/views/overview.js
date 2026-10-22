import { fmt, h, status } from "../dom.js";
import { state } from "../state.js";

const STAGES = [
  ["builds", "Master data", "Phase gates decide what may be planned"],
  ["builds", "Sample forecast", "Requests become build orders"],
  ["builds", "Capacity booking", "Fab and assembly slots, by priority"],
  ["materials", "Material check", "Is everything on hand in time?"],
  ["ramp", "Ramp-up", "Match capacity to demand, gate the launch"],
  ["change", "Change control", "Notify customers of a product change"],
];

function tile(label, value, note) {
  return h("div", { class: "tile" }, h("span", { class: "label", text: label }), h("span", { class: "value" }, value), note && h("span", { class: "note", text: note }));
}

export function overviewView() {
  const { plan, ramp, pcn } = state.demo;
  const late = plan.orders.filter((o) => !o.on_time);
  const expedite = plan.shortages.filter((s) => s.expedite);
  const gate = ramp.gate;

  const reads = [
    late.length
      ? `${late.length} of ${plan.summary.orders} sample builds ship late (${[...new Set(late.map((o) => `${o.delay_weeks}w`))].join(", ")}). First cause: ${late[0].reasons[0] || "capacity"}.`
      : "Every sample build ships on time.",
    `${plan.blocked.requests} ${plan.blocked.pid} requests were held back by the master-data gate (${plan.blocked.reasons.join("; ")}).`,
    plan.shortages.length
      ? `${plan.shortages.length} materials run short; ${expedite.length ? `${expedite.map((s) => s.material).join(", ")} must be expedited because the order-by week has already passed` : "none need expediting"}.`
      : "No material shortages.",
    ramp.required_rate == null
      ? "Demand cannot be met even at the capacity ceiling."
      : `Capacity must grow by at least ${fmt.n(ramp.required_rate)} units a week to avoid any backlog. A slower +${fmt.n(ramp.params.rate)}/wk plan serves ${fmt.pct(ramp.scenario.service_level, 1)} of demand.`,
    `PCN ${pcn.pcn_id} was rejected once for a missing qualification test and blocked once from closing early. Both guardrails fired as designed.`,
  ];

  return h("section", null,
    h("div", { class: "head" },
      h("h1", { text: "From engineering samples to volume ramp" }),
      h("p", { class: "lede", text: "RampOps models how a new semiconductor product gets sample builds into customers' hands, ramps capacity to meet demand, and notifies customers when something changes. Everything below is computed live from synthetic data by a small Python engine." }),
    ),
    h("div", { class: "hero" },
      h("div", { class: "big" }, `${plan.summary.on_time}`, h("small", { text: ` of ${plan.summary.orders}` })),
      h("p", { class: "lede", text: "sample builds ship by their customer's need-by week in the baseline plan" }),
    ),
    h("div", { class: "grid cols-4" },
      tile("Frontend utilisation", fmt.pct(plan.summary.utilisation.fe), "wafer starts, weeks in use"),
      tile("Backend utilisation", fmt.pct(plan.summary.utilisation.be), "assembly units, weeks in use"),
      tile("Material shortages", String(plan.shortages.length), expedite.length ? `${expedite.length} need expediting` : "none urgent"),
      tile("Minimum ramp rate", ramp.required_rate == null ? "n/a" : `+${fmt.n(ramp.required_rate)}/wk`, "no backlog at this pace"),
      tile("Safe-launch gate", status(gate.go ? "good" : "bad", gate.go ? "GO" : "NO-GO"), gate.go ? "all criteria met" : gate.reasons[0]),
      tile("Change notice", `${pcn.notice_days} days`, `effective ${pcn.effective_date}`),
      tile("Held-back requests", String(plan.blocked.requests), `${plan.blocked.pid}: master data incomplete`),
      tile("PCN state", pcn.state, pcn.pcn_id),
    ),
    h("div", { class: "card" },
      h("h3", { text: "The planner's read" }),
      h("p", { class: "sub", text: "Generated from the baseline numbers above." }),
      h("ul", null, reads.map((r) => h("li", { text: r }))),
    ),
    h("div", null,
      h("h2", { text: "How the pieces fit" }),
      h("p", { class: "lede", text: "Each stage feeds the next. Open one to change its inputs and watch the answer move." }),
    ),
    h("div", { class: "flow" }, STAGES.map(([view, title, blurb]) => h("a", { href: `#${view}` }, h("b", { text: title }), h("span", { text: blurb })))),
  );
}
