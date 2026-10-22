import { live } from "../api.js";
import { banner, slider } from "../controls.js";
import { barChart, disposeCharts, legend, lineChart, mount } from "../charts.js";
import { fmt, h, status } from "../dom.js";
import { state } from "../state.js";

const DEFAULTS = { weeks: 26, start: 5000, ceiling: 45000, rate: 1500, yield: 91, target_yield: 92, cover: 3.5, min_cover: 4, issues: 0 };

const query = (p) => ({
  weeks: p.weeks, start: p.start, ceiling: p.ceiling, rate: p.rate,
  yields: [p.yield, p.yield, p.yield].map((y) => y / 100).join(","),
  target_yield: p.target_yield / 100, cover: p.cover, min_cover: p.min_cover, issues: p.issues,
});

function tile(label, value, note) {
  return h("div", { class: "tile" }, h("span", { class: "label", text: label }), h("span", { class: "value" }, value), h("span", { class: "note", text: note }));
}

export function rampView() {
  const P = { ...DEFAULTS };
  let data = state.demo.ramp;
  const err = banner();
  const out = h("div", { class: "grid refetch" });
  const fetchRamp = live({
    path: "ramp",
    onData: (d) => {
      data = d;
      draw();
    },
    onError: err.show,
    busy: (b) => out.classList.toggle("busy", b),
  });
  const bind = (k) => (v) => {
    P[k] = v;
    fetchRamp(query(P));
  };
  const pct = (v) => `${v}%`;
  const S = {
    start: slider({ label: "Starting capacity (units / week)", min: 0, max: 20000, step: 500, value: P.start, format: fmt.n, onInput: bind("start") }),
    ceiling: slider({ label: "Capacity ceiling (units / week)", min: 10000, max: 80000, step: 1000, value: P.ceiling, format: fmt.n, onInput: bind("ceiling") }),
    rate: slider({ label: "Capacity added each week", min: 0, max: 5000, step: 100, value: P.rate, format: (v) => `+${fmt.n(v)}`, onInput: bind("rate") }),
    weeks: slider({ label: "Horizon (weeks)", min: 12, max: 52, step: 2, value: P.weeks, onInput: bind("weeks") }),
  };
  const G = {
    yield: slider({ label: "Yield, last 3 weeks (lowest)", min: 80, max: 99, value: P.yield, format: pct, onInput: bind("yield") }),
    target: slider({ label: "Target yield", min: 80, max: 99, value: P.target_yield, format: pct, onInput: bind("target_yield") }),
    cover: slider({ label: "Material cover (weeks)", min: 0, max: 10, step: 0.5, value: P.cover, onInput: bind("cover") }),
    issues: slider({ label: "Open critical issues", min: 0, max: 5, value: P.issues, onInput: bind("issues") }),
  };

  function draw() {
    disposeCharts();
    const d = data;
    const sc = d.scenario;
    const need = d.required;
    const weeks = d.demand.length;
    const series = [
      { name: "Demand", end: "Demand", color: "var(--s1)", values: d.demand },
      { name: `Your plan (+${fmt.n(d.params.rate)}/wk)`, end: "Your plan", color: "var(--s2)", values: sc.capacity },
      ...(need ? [{ name: `Minimum (+${fmt.n(d.required_rate)}/wk)`, end: "Minimum", color: "var(--s3)", values: need.capacity }] : []),
    ];
    const lineHost = h("div", { class: "chart" });
    const backHost = h("div", { class: "chart" });
    mount(lineHost, lineChart({ series, label: "Weekly demand against planned capacity", unit: " units" }));
    mount(backHost, barChart({
      values: sc.backlog, color: "var(--s2)", label: "Unmet demand carried forward each week",
      tip: (i) => ({ title: `Week ${i}`, rows: [{ color: "var(--s2)", value: fmt.n(sc.backlog[i]), label: "units in backlog" }] }),
    }));
    const gate = d.gate;

    out.replaceChildren(
      d.required_rate == null
        ? h("div", { class: "callout bad" }, h("p", { text: "Even jumping straight to the capacity ceiling cannot meet this demand. Raise the ceiling or lower the starting gap." }))
        : h("div", { class: "callout" }, h("p", null, h("b", { text: `Minimum pace: +${fmt.n(d.required_rate)} units a week. ` }), "Found by binary search over the weekly increase, as the smallest value that leaves no backlog at any point.")),
      h("div", { class: "grid cols-4" },
        tile("Demand served", fmt.pct(sc.service_level, 1), "your plan"),
        tile("Peak backlog", fmt.n(sc.peak_backlog), "units unmet at the worst week"),
        tile("Weeks in backlog", String(sc.weeks_in_backlog), `of ${weeks}`),
        tile("Safe-launch gate", status(gate.go ? "good" : "bad", gate.go ? "GO" : "NO-GO"), gate.go ? "yield, cover and issues all pass" : `${gate.reasons.length} blocker${gate.reasons.length > 1 ? "s" : ""}`),
      ),
      h("div", { class: "card" },
        h("h3", { text: "Demand and capacity" }),
        h("p", { class: "sub", text: "Where the capacity line sits under demand, customers wait. Hover or use the arrow keys to read any week." }),
        legend(series.map((s) => ({ color: s.color, label: s.name }))), lineHost),
      h("div", { class: "grid cols-2" },
        h("div", { class: "card" }, h("h3", { text: "Backlog from your plan" }), h("p", { class: "sub", text: "Units demanded but not yet shipped." }), backHost),
        h("div", { class: "card" },
          h("h3", { text: "Safe-launch gate" }),
          h("p", { class: "sub", text: "A go / no-go before taking the product from samples into ramp." }),
          gate.go ? h("p", null, status("good", "GO"), " Every criterion is met.") : h("ul", null, gate.reasons.map((r) => h("li", { text: r }))),
          h("p", { class: "muted", text: "Yield must meet target for three consecutive weeks, material cover must reach the minimum, and no critical issue may be open." })),
      ),
    );
  }

  const el = h("section", null,
    h("div", { class: "head" },
      h("h1", { text: "Ramp-up" }),
      h("p", { class: "lede", text: "Demand for a new product follows an S-curve. Capacity has to climb fast enough to meet it, without paying for capacity that sits idle. Set a ramp pace and see the backlog it would create." }),
    ),
    h("div", { class: "card" }, h("h3", { text: "Capacity plan" }), h("div", { class: "controls" }, S.start.el, S.ceiling.el, S.rate.el, S.weeks.el)),
    h("div", { class: "card" }, h("h3", { text: "Launch gate inputs" }), h("div", { class: "controls" }, G.yield.el, G.target.el, G.cover.el, G.issues.el), err.el),
    out,
  );
  draw();
  return el;
}
