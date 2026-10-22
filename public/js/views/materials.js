import { fmt, h, productTag, status } from "../dom.js";
import { productIndex, state } from "../state.js";

export function materialsView() {
  const d = state.plan;
  const idx = productIndex(d);
  const urgent = d.shortages.filter((s) => s.expedite);

  return h("section", null,
    h("div", { class: "head" },
      h("h1", { text: "Material readiness" }),
      h("p", { class: "lede", text: "The bill of materials is exploded against the booked builds, then stock and inbound supply are projected week by week. A shortage shows the latest week a purchase order must be placed to land in time." }),
      h("p", { class: "muted", text: "Based on the current settings on the Sample builds tab." }),
    ),
    urgent.length
      ? h("div", { class: "callout bad" }, h("p", null, h("b", { text: `${urgent.length} material${urgent.length > 1 ? "s" : ""} must be expedited. ` }), `${urgent.map((s) => s.material).join(", ")} should already have been ordered. Supply has to be pulled in or the affected builds will slip.`))
      : h("div", { class: "callout good" }, h("p", { text: "No shortage needs an expedite under these settings." })),
    h("div", { class: "card" },
      h("h3", { text: "Shortages" }),
      d.shortages.length
        ? h("div", { class: "scroll" }, h("table", null,
          h("thead", null, h("tr", null, ["Material", "First short", "Peak deficit", "Order by", "Action", "Builds hit"].map((t, i) => h("th", { class: i >= 1 && i <= 3 ? "num" : "", text: t })))),
          h("tbody", null, d.shortages.map((s) => h("tr", null,
            h("td", { text: s.material }),
            h("td", { class: "num", text: fmt.week(s.first_short_week) }),
            h("td", { class: "num", text: fmt.n(s.peak_deficit) }),
            h("td", { class: "num", text: s.order_by_week < 0 ? `${s.order_by_week} (past)` : fmt.week(s.order_by_week) }),
            h("td", null, s.expedite ? status("bad", "Expedite") : status("warn", `Order by ${fmt.week(s.order_by_week)}`)),
            h("td", { class: "muted", text: s.orders.join(", ") }),
          ))),
        ))
        : h("p", { class: "muted", text: "No shortages." }),
    ),
    h("div", { class: "card" },
      h("h3", { text: "Bill of materials" }),
      h("p", { class: "sub", text: "Fab quantities are per wafer started; assembly quantities are per good unit." }),
      d.products.map((p) => h("details", null,
        h("summary", null, productTag(p.pid, idx[p.pid]), ` ${p.name}`),
        h("div", { class: "scroll" }, h("table", null,
          h("thead", null, h("tr", null, ["Material", "Stage", "Qty", "Lead time"].map((t, i) => h("th", { class: i >= 2 ? "num" : "", text: t })))),
          h("tbody", null, p.bom.map((b) => h("tr", null,
            h("td", { text: b.material }), h("td", { text: b.stage === "FE" ? "Fab (per wafer)" : "Assembly (per unit)" }),
            h("td", { class: "num", text: b.qty }), h("td", { class: "num", text: `${b.lead_time_weeks} wk` }),
          ))),
        )),
        h("p", { class: "muted", text: `${fmt.n(p.die_per_wafer)} die per wafer, fab yield ${fmt.pct(p.fe_yield)}, assembly yield ${fmt.pct(p.be_yield)}: about ${fmt.n(p.good_units_per_wafer)} good units per wafer.` }),
      )),
    ),
  );
}
