import { banner, slider } from "../controls.js";
import { live } from "../api.js";
import { barChart, disposeCharts, legend, mount, timelineChart } from "../charts.js";
import { fmt, h, productTag, status } from "../dom.js";
import { colourOf, planQuery, productIndex, state } from "../state.js";

function tile(label, value, note) {
  return h("div", { class: "tile" }, h("span", { class: "label", text: label }), h("span", { class: "value" }, value), h("span", { class: "note", text: note }));
}

function capacityCard(title, sub, used, capAll, unit, weeksShown) {
  const host = h("div", { class: "chart" });
  const card = h("div", { class: "card" }, h("h3", { text: title }), h("p", { class: "sub", text: sub }),
    legend([{ kind: "box", color: "var(--s1)", label: "Booked" }, { color: "var(--ink-2)", label: "Capacity" }]), host);
  const u = used.slice(0, weeksShown);
  const c = capAll.slice(0, weeksShown);
  mount(host, barChart({
    values: u, cap: c, label: `${title}, weeks 0 to ${weeksShown - 1}`,
    tip: (i) => ({ title: `Week ${i}`, rows: [{ color: "var(--s1)", value: fmt.n(u[i]), label: `${unit} booked` }, { color: "var(--ink-2)", value: fmt.n(c[i]), label: c[i] === 0 ? "capacity (shut down)" : "capacity" }] }),
  }));
  return card;
}

export function buildsView() {
  const P = state.planParams;
  const err = banner();
  const out = h("div", { class: "grid refetch" });

  const fetchPlan = live({
    path: "plan",
    onData: (d) => {
      state.plan = d;
      draw(d);
    },
    onError: err.show,
    busy: (b) => out.classList.toggle("busy", b),
  });
  const go = () => fetchPlan(planQuery(P));
  const bind = (key) => (v) => {
    P[key] = v;
    go();
  };

  const ctl = {
    fe: slider({ label: "Fab capacity (wafer starts / week)", min: 4, max: 60, value: P.fe_capacity, onInput: bind("fe_capacity") }),
    be: slider({ label: "Assembly capacity (units / week)", min: 10000, max: 80000, step: 1000, value: P.be_capacity, format: fmt.n, onInput: bind("be_capacity") }),
    pull: slider({ label: "Pull-in window (weeks)", min: 0, max: 6, value: P.max_pull_in, onInput: bind("max_pull_in") }),
    ss: slider({ label: "Fab shutdown starts (week)", min: 0, max: 30, value: P.shutdown_start, format: fmt.week, onInput: bind("shutdown_start") }),
    sl: slider({ label: "Fab shutdown length (weeks)", min: 0, max: 8, value: P.shutdown_len, onInput: bind("shutdown_len") }),
  };
  const reset = h("button", { class: "btn", type: "button", text: "Reset to baseline", onclick: () => {
    Object.assign(P, { fe_capacity: 25, be_capacity: 40000, max_pull_in: 3, shutdown_start: 10, shutdown_len: 2 });
    ctl.fe.set(P.fe_capacity); ctl.be.set(P.be_capacity); ctl.pull.set(P.max_pull_in); ctl.ss.set(P.shutdown_start); ctl.sl.set(P.shutdown_len);
    go();
  } });

  function draw(d) {
    disposeCharts();
    const idx = productIndex(d);
    const colorOf = colourOf(d);
    const late = d.orders.filter((o) => !o.on_time);
    const shown = Math.min(d.capacity.horizon, Math.max(...d.orders.map((o) => o.ship_week)) + 2);

    const tlHost = h("div", { class: "chart" });
    mount(tlHost, timelineChart({ orders: d.orders, colorOf, shutdown: d.maintenance_weeks, label: "Build timeline: wafer start to shipment, with need-by pins" }));

    out.replaceChildren(
      h("div", { class: "grid cols-4" },
        tile("On time", `${d.summary.on_time} / ${d.summary.orders}`, late.length ? `${late.length} late` : "all builds on plan"),
        tile("Frontend utilisation", fmt.pct(d.summary.utilisation.fe), "of capacity in weeks used"),
        tile("Backend utilisation", fmt.pct(d.summary.utilisation.be), "of capacity in weeks used"),
        tile("Held back", String(d.blocked.requests), `${d.blocked.pid} requests, master data incomplete`),
      ),
      h("div", { class: "card" },
        h("h3", { text: "Build timeline" }),
        h("p", { class: "sub", text: "Each bar runs from the first wafer start to shipment. The black pin is the customer's need-by week; a bar that ends right of its pin is late." }),
        legend([...d.products.map((p) => ({ kind: "box", color: colorOf(p.pid), label: `${p.pid} ${p.name}` })), { kind: "pin", label: "need-by week" }]),
        tlHost,
      ),
      h("div", { class: "grid cols-2" },
        capacityCard("Fab wafer starts", "Weekly wafer starts booked against capacity. The line drops to zero in a shutdown.", d.capacity.fe_used, d.capacity.fe_cap, "wafers", shown),
        capacityCard("Assembly units", "Weekly units started in assembly and test. Assembly cannot start before the last wafer leaves the fab.", d.capacity.be_used, d.capacity.be_cap, "units", shown),
      ),
      h("div", { class: "callout warn" },
        h("p", null, h("b", { text: `${d.blocked.requests} ${d.blocked.pid} requests were not planned. ` }), `The master-data gate refused them: ${d.blocked.reasons.join("; ")}. Planning only accepts products released to the engineering-samples phase.`)),
      h("div", { class: "card" },
        h("h3", { text: "Build orders" }),
        h("p", { class: "sub", text: "The same data as the chart, with the reason for every delay." }),
        h("div", { class: "scroll" }, h("table", null,
          h("thead", null, h("tr", null, ["Order", "Product", "Customers", "Units", "Wafers", "Need-by", "Ships", "Status", "Why"].map((t, i) => h("th", { class: i >= 3 && i <= 6 ? "num" : "", text: t })))),
          h("tbody", null, d.orders.map((o) => h("tr", null,
            h("td", { text: o.order_id }),
            h("td", null, productTag(o.pid, idx[o.pid])),
            h("td", { text: o.customers.join(", ") }),
            h("td", { class: "num", text: fmt.n(o.units) }),
            h("td", { class: "num", text: o.wafers }),
            h("td", { class: "num", text: fmt.week(o.need_by) }),
            h("td", { class: "num", text: fmt.week(o.ship_week) }),
            h("td", null, o.on_time ? status("good", "On time") : status("bad", `+${o.delay_weeks}w late`)),
            h("td", { class: "muted", text: o.reasons.join("; ") || "On plan" }),
          ))),
        )),
      ),
    );
  }

  const el = h("section", null,
    h("div", { class: "head" },
      h("h1", { text: "Sample builds" }),
      h("p", { class: "lede", text: "Customer sample requests are consolidated, back-scheduled from their need-by dates through assembly and the fab, then booked into weekly capacity in priority order. Drag a control to ask a what-if." }),
    ),
    h("div", { class: "card" }, h("div", { class: "controls" }, ctl.fe.el, ctl.be.el, ctl.pull.el, ctl.ss.el, ctl.sl.el, reset), err.el),
    out,
  );
  draw(state.plan);
  return el;
}
