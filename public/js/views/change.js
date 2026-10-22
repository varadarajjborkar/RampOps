import { banner, numberField, slider } from "../controls.js";
import { live } from "../api.js";
import { barChart, disposeCharts, mount } from "../charts.js";
import { fmt, h, status } from "../dom.js";
import { state } from "../state.js";

const TESTS = [
  ["HTOL", "High-temperature operating life"], ["TC", "Temperature cycling"], ["uHAST", "Unbiased humidity stress"],
  ["HTSL", "High-temperature storage life"], ["ESD", "Electrostatic discharge"], ["LU", "Latch-up"], ["MSL", "Moisture sensitivity level"],
];
const CHANGES = {
  FAB_SITE: "Fab site / wafer process change", ASSEMBLY_SITE: "Assembly site change", DIE_SHRINK: "Die shrink",
  MATERIAL: "Assembly material change", DATASHEET: "Datasheet-only update",
};

const logLine = (l) => (l.to === "RESPONSE" ? `Response: ${l.note}` : `${l.from} → ${l.to}${l.note ? `, ${l.note}` : ""}`);

function lifecycle(pcn) {
  const main = ["DRAFT", "QUAL_REVIEW", "SAMPLE_STRATEGY", "APPROVED", "DISTRIBUTED", "NOTICE_PERIOD", "CLOSED"];
  const label = Object.fromEntries(pcn.states.map((s) => [s.name, s.label]));
  const at = main.indexOf(pcn.state);
  return h("ol", { class: "steps" }, main.map((s, i) => h("li", { class: i < at ? "done" : i === at ? "now" : "", "aria-current": i === at ? "step" : false, text: label[s] })));
}

function qualCard() {
  const Q = { change_type: "ASSEMBLY_SITE", tests: { TC: 3, uHAST: 3, HTSL: 3 }, notify: "2026-12-11", notice_days: 90 };
  const verdict = h("div", { class: "grid refetch" });
  const err = banner();
  const run = live({
    path: "qualcheck", wait: 120, busy: (b) => verdict.classList.toggle("busy", b), onError: err.show,
    onData: (d) => {
      verdict.replaceChildren(
        d.ok ? h("div", { class: "callout good" }, h("p", null, status("good", "Plan accepted"), ` Moves on to sample strategy. Customers must be notified by ${d.notify_date}; the change can take effect from ${d.effective_date} (${d.notice_days}-day notice).`))
          : h("div", { class: "callout bad" }, h("p", null, status("bad", "Plan rejected"), " The PCN returns to draft:"), h("ul", null, d.gaps.map((g) => h("li", { text: g })))),
        h("p", { class: "muted", text: `${d.change_label} requires ${d.required_tests.length ? d.required_tests.join(", ") : "no qualification tests"}${d.min_lots ? `, at least ${d.min_lots} lot${d.min_lots > 1 ? "s" : ""} each` : ""}.` }),
      );
      for (const box of checks.querySelectorAll(".check")) box.classList.toggle("required", d.required_tests.includes(box.dataset.test));
    },
  });
  const ask = () => run({ change_type: Q.change_type, notify: Q.notify, notice_days: Q.notice_days, tests: Object.entries(Q.tests).map(([k, v]) => `${k}:${v}`).join(",") });

  const select = h("select", { id: "ct", onchange: (e) => { Q.change_type = e.target.value; ask(); } }, Object.entries(CHANGES).map(([k, v]) => h("option", { value: k, selected: k === Q.change_type, text: v })));
  const checks = h("div", { class: "checks" }, TESTS.map(([name, full]) => {
    const lots = h("input", { type: "number", min: 0, max: 50, "aria-label": `${name} lots` });
    lots.value = Q.tests[name] ?? 3;
    const box = h("input", { type: "checkbox", id: `t-${name}`, checked: name in Q.tests, "aria-label": `${name}: ${full}` });
    const sync = () => {
      if (box.checked) Q.tests[name] = Number(lots.value); else delete Q.tests[name];
      ask();
    };
    box.addEventListener("change", sync);
    lots.addEventListener("input", () => box.checked && sync());
    return h("label", { class: "check", "data-test": name, title: full }, box, h("span", { text: name }), lots);
  }));
  const date = h("input", { type: "date", id: "nd", min: "2000-01-01", max: "2100-12-31", oninput: (e) => { if (e.target.value) { Q.notify = e.target.value; ask(); } } });
  date.value = Q.notify;

  ask();
  return h("div", { class: "card" },
    h("h3", { text: "Qualification plan checker" }),
    h("p", { class: "sub", text: "Each change type has a set of required tests and a minimum lot count. Tick tests and set lots per test; the engine answers as the real review gate would." }),
    h("div", { class: "controls" },
      h("div", { class: "field" }, h("label", { for: "ct", text: "Change type" }), select),
      h("div", { class: "field" }, h("label", { for: "nd", text: "Customer notification date" }), date),
      numberField({ label: "Notice period (days)", min: 0, max: 365, value: Q.notice_days, onInput: (v) => { if (Number.isFinite(v)) { Q.notice_days = Math.min(365, Math.max(0, v)); ask(); } } }),
    ),
    h("p", { class: "sub", text: "Tests and lots (number to the right)" }), checks, err.el, verdict);
}

function bridgeCard() {
  const B = { cutover: 20, transition: 6 };
  let data = null;
  const host = h("div", { class: "chart" });
  const body = h("div", { class: "grid refetch" });
  const err = banner();
  const run = live({ path: "bridge", wait: 120, busy: (b) => body.classList.toggle("busy", b), onError: err.show, onData: (d) => { data = d; draw(); } });
  const ask = () => run(B);
  const bridge = state.demo.pcn.bridge;
  data = { ...bridge, cutover: B.cutover, transition: B.transition, demand: state.demo.ramp.demand };

  function draw() {
    disposeCharts();
    const d = data;
    const inWindow = (i) => i >= d.cutover && i < d.cutover + d.transition;
    mount(host, barChart({
      values: d.demand, color: "var(--s1)", label: "Weekly demand with the cutover window highlighted", mark: inWindow,
      threshold: { value: d.peak_threshold, label: "peak threshold" },
      tip: (i) => ({ title: `Week ${i}${inWindow(i) ? " (cutover window)" : ""}`, rows: [{ color: "var(--s1)", value: fmt.n(d.demand[i]), label: "units demanded" }] }),
    }));
    body.replaceChildren(
      d.recommend_defer
        ? h("div", { class: "callout warn" }, h("p", null, status("warn", "Defer the cutover"), ` The window includes peak-demand week${d.peak_weeks_in_window.length > 1 ? "s" : ""} ${d.peak_weeks_in_window.map((w) => `w${w}`).join(", ")}. Move it or build more bridge stock.`))
        : h("div", { class: "callout good" }, h("p", null, status("good", "Cutover window is clear"), " No week in the window is above the peak threshold.")),
      h("p", null, h("b", { text: `${fmt.n(d.bridge_stock_units)} units` }), " of the old version should be built ahead to cover the window."),
    );
  }

  const s1 = slider({ label: "Cutover week", min: 0, max: 25, value: B.cutover, format: fmt.week, onInput: (v) => { B.cutover = v; ask(); } });
  const s2 = slider({ label: "Transition length (weeks)", min: 1, max: 12, value: B.transition, onInput: (v) => { B.transition = v; ask(); } });
  const card = h("div", { class: "card" },
    h("h3", { text: "Cutover and bridge stock" }),
    h("p", { class: "sub", text: "A change should not land in a peak-demand window. Move the cutover and see whether the heuristic objects." }),
    h("div", { class: "controls" }, s1.el, s2.el), err.el, host, body);
  draw();
  return card;
}

export function changeView() {
  const p = state.demo.pcn;
  return h("section", null,
    h("div", { class: "head" },
      h("h1", { text: "Change control (PCN)" }),
      h("p", { class: "lede", text: "When a product changes (a new assembly site, a die shrink), customers get a Product Change Notification. The workflow is a strict state machine: it refuses steps taken out of order and records everything in an audit trail." }),
    ),
    h("div", { class: "card" },
      h("h3", { text: `${p.pcn_id}: ${p.change_label}` }),
      h("p", { class: "sub", text: p.description }),
      lifecycle(p),
      h("div", { class: "grid cols-2" },
        h("div", { class: "callout bad" }, h("p", null, h("b", { text: "Guardrail 1. " }), p.first_error), h("p", { class: "muted", text: "The qualification plan was missing a required test, so the PCN bounced back to draft." })),
        h("div", { class: "callout bad" }, h("p", null, h("b", { text: "Guardrail 2. " }), p.early_close_error), h("p", { class: "muted", text: "A customer still had an open question, so the PCN could not be closed early." })),
      ),
    ),
    h("div", { class: "grid cols-2" }, qualCard(), bridgeCard()),
    h("div", { class: "grid cols-2" },
      h("div", { class: "card" },
        h("h3", { text: "Audit trail" }),
        h("p", { class: "sub", text: "Every transition and customer response, in order." }),
        h("ol", { class: "timeline" }, p.log.map((l) => h("li", null, h("time", { datetime: l.date, text: l.date }), h("span", { text: logLine(l) })))),
      ),
      h("div", { class: "card" },
        h("h3", { text: "Customers" }),
        h("p", { class: "sub", text: `Notified ${p.notify_date}; effective ${p.effective_date} after a ${p.notice_days}-day notice.` }),
        h("div", { class: "scroll" }, h("table", null,
          h("thead", null, h("tr", null, ["Customer", "Annual units", "Samples", "Response"].map((t, i) => h("th", { class: i === 1 || i === 2 ? "num" : "", text: t })))),
          h("tbody", null, p.customers.map((c) => h("tr", null,
            h("td", { text: c.customer }), h("td", { class: "num", text: fmt.n(c.annual_units) }),
            h("td", { class: "num", text: p.sample_alloc[c.customer] ?? 0 }), h("td", { text: p.responses[c.customer] || "none" }),
          ))),
        )),
        h("p", { class: "muted", text: "Samples are tiered by each customer's share of volume (150, 75 or 30 units) and scaled down if the pool is short." }),
      ),
    ),
    h("div", { class: "card" },
      h("details", null, h("summary", { text: "Generated customer notification" }), h("pre", { class: "doc", text: p.document })),
    ),
  );
}
