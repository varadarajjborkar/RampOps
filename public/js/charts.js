// Hand-built SVG charts. Specs follow the project's chart rules: 2px lines, bars at most 24px thick with a
// 4px rounded data end, hairline grid, text in ink tokens (never the series colour), tooltips on hover AND focus.

import { fmt, h, svg } from "./dom.js";

const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) * (r1 - r0)) / (d1 - d0 || 1);

/** A y axis with whole-number steps: returns the top of the axis and its tick values. */
export function axisFor(maxValue) {
  const rough = (maxValue || 1) / 4;
  const p = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((v) => v >= rough);
  const top = Math.ceil((maxValue || 1) / step) * step;
  return { max: top, ticks: Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step) };
}

// -- tooltip ---------------------------------------------------------------------------------------

const tipEl = () => document.getElementById("tip");

/** `at` is {x, y} in client coordinates. Rows: {color?, value, label}. */
export function showTip(at, title, rows = []) {
  const tip = tipEl();
  tip.replaceChildren(
    h("div", { class: "t", text: title }),
    ...rows.map((r) => {
      const key = h("i");
      if (r.color) key.style.borderTopColor = r.color;
      else key.hidden = true;
      return h("div", { class: "r" }, key, h("b", { text: r.value }), h("span", { text: r.label }));
    }),
  );
  tip.hidden = false;
  const { width, height } = tip.getBoundingClientRect();
  let x = at.x + 14;
  let y = at.y + 14;
  if (x + width > window.innerWidth - 8) x = at.x - width - 14;
  if (y + height > window.innerHeight - 8) y = at.y - height - 14;
  tip.style.left = `${Math.max(8, x)}px`;
  tip.style.top = `${Math.max(8, y)}px`;
}

export const hideTip = () => {
  tipEl().hidden = true;
};

const centreOf = (el) => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
};

// -- responsive mounting ---------------------------------------------------------------------------

const live = new Set();

/** Draw into `host` at its current width and redraw when the width changes. */
export function mount(host, draw) {
  let width = 0;
  let current = draw;
  const run = () => {
    const w = Math.floor(host.clientWidth);
    if (w < 40) return;
    width = w;
    host.replaceChildren(current(w));
  };
  const ro = new ResizeObserver(() => {
    if (Math.floor(host.clientWidth) !== width) run();
  });
  ro.observe(host);
  const handle = {
    redraw(next) {
      if (next) current = next;
      width = 0;
      run();
    },
    stop: () => ro.disconnect(),
  };
  live.add(handle);
  run();
  return handle;
}

export function disposeCharts() {
  live.forEach((c) => c.stop());
  live.clear();
  hideTip();
}

export function legend(items) {
  return h(
    "ul",
    { class: "legend" },
    items.map((it) => {
      const key = h("i", { class: it.kind || "" });
      if (it.color && it.kind === "box") key.style.background = it.color;
      else if (it.color) key.style.borderTopColor = it.color;
      return h("li", null, key, it.label);
    }),
  );
}

// -- line chart with crosshair ---------------------------------------------------------------------

/**
 * series: [{name, color, values}] all the same length. opts.format formats y values.
 * Returns a draw(width) function for mount().
 */
export function lineChart({ series, xLabel = (i) => `w${i}`, height = 280, label, format = fmt.n, unit = "" }) {
  return (W) => {
    const narrow = W < 520;
    const m = { l: 46, r: narrow ? 12 : 104, t: 12, b: 28 };
    const iw = W - m.l - m.r;
    const ih = height - m.t - m.b;
    const n = series[0].values.length;
    const { max: yMax, ticks } = axisFor(Math.max(1, ...series.flatMap((s) => s.values)) * 1.02);
    const x = (i) => m.l + (n > 1 ? (i * iw) / (n - 1) : 0);
    const y = lin(0, yMax, m.t + ih, m.t);
    const root = svg("svg", { viewBox: `0 0 ${W} ${height}`, role: "img", "aria-label": label });

    for (const t of ticks) {
      root.append(
        svg("line", { class: "grid-line", x1: m.l, x2: W - m.r, y1: y(t), y2: y(t) }),
        svg("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", text: fmt.compact(t) }),
      );
    }
    const every = Math.max(1, Math.ceil(n / (narrow ? 6 : 12)));
    for (let i = 0; i < n; i += every) {
      root.append(svg("text", { x: x(i), y: height - 8, "text-anchor": "middle", text: xLabel(i) }));
    }
    root.append(svg("line", { class: "axis-line", x1: m.l, x2: W - m.r, y1: y(0), y2: y(0) }));

    let lastLabelY = -99;
    const ends = [...series].sort((a, b) => y(a.values[n - 1]) - y(b.values[n - 1]));
    for (const s of series) {
      const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
      root.append(svg("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }
    for (const s of series) {
      const ey = y(s.values[n - 1]);
      root.append(svg("circle", { cx: x(n - 1), cy: ey, r: 4, fill: s.color, stroke: "var(--surface)", "stroke-width": 2 }));
    }
    // Direct end labels only where they do not collide; the legend and tooltip carry the rest.
    if (!narrow) {
      for (const s of ends) {
        const ey = y(s.values[n - 1]);
        if (Math.abs(ey - lastLabelY) < 15) continue;
        lastLabelY = ey;
        root.append(svg("text", { class: "strong", x: x(n - 1) + 10, y: ey + 4, text: s.end || s.name }));
      }
    }

    // Crosshair + tooltip.
    const cross = svg("line", { class: "axis-line", x1: 0, x2: 0, y1: m.t, y2: m.t + ih, visibility: "hidden" });
    const dots = series.map((s) => svg("circle", { r: 4, fill: s.color, stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }));
    const hit = svg("rect", { class: "hit", x: m.l, y: m.t, width: iw, height: ih, tabindex: 0, role: "img", "aria-label": `${label}. Use left and right arrow keys to read each week.` });
    root.append(cross, ...dots, hit);

    const show = (i, at) => {
      cross.setAttribute("x1", x(i));
      cross.setAttribute("x2", x(i));
      cross.setAttribute("visibility", "visible");
      dots.forEach((d, k) => {
        d.setAttribute("cx", x(i));
        d.setAttribute("cy", y(series[k].values[i]));
        d.setAttribute("visibility", "visible");
      });
      showTip(at, xLabel(i), series.map((s) => ({ color: s.color, value: format(s.values[i]) + unit, label: s.name })));
    };
    const off = () => {
      cross.setAttribute("visibility", "hidden");
      dots.forEach((d) => d.setAttribute("visibility", "hidden"));
      hideTip();
    };
    const pick = (evt) => {
      const r = root.getBoundingClientRect();
      return Math.min(n - 1, Math.max(0, Math.round(((evt.clientX - r.left - m.l) / iw) * (n - 1))));
    };
    let kb = 0;
    hit.addEventListener("pointermove", (e) => show(pick(e), { x: e.clientX, y: e.clientY }));
    hit.addEventListener("pointerleave", off);
    hit.addEventListener("blur", off);
    hit.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      kb = Math.min(n - 1, Math.max(0, kb + (e.key === "ArrowRight" ? 1 : -1)));
      const r = root.getBoundingClientRect();
      show(kb, { x: r.left + x(kb), y: r.top + m.t + 20 });
    });
    return root;
  };
}

// -- bar chart (optionally with a capacity step line and a threshold) -------------------------------

/**
 * values: per-x numbers. cap: optional per-x capacity drawn as a step line. mark(i): true for emphasised bars.
 * tip(i): {title, rows}. threshold: {value, label}.
 */
export function barChart({ values, cap, color = "var(--s1)", xLabel = (i) => `w${i}`, tip, mark, threshold, height = 190, label, every }) {
  return (W) => {
    const m = { l: 46, r: 10, t: 14, b: 28 };
    const iw = W - m.l - m.r;
    const ih = height - m.t - m.b;
    const n = values.length;
    const { max: yMax, ticks } = axisFor(Math.max(1, ...values, ...(cap || []), threshold ? threshold.value : 0) * 1.05);
    const y = lin(0, yMax, m.t + ih, m.t);
    const band = iw / n;
    const bw = Math.max(2, Math.min(24, band - 2));
    const root = svg("svg", { viewBox: `0 0 ${W} ${height}`, role: "img", "aria-label": label });

    for (const t of ticks) {
      root.append(
        svg("line", { class: "grid-line", x1: m.l, x2: W - m.r, y1: y(t), y2: y(t) }),
        svg("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", text: fmt.compact(t) }),
      );
    }
    const step = every || Math.max(1, Math.ceil(n / Math.max(4, Math.floor(iw / 44))));
    for (let i = 0; i < n; i += step) {
      root.append(svg("text", { x: m.l + band * (i + 0.5), y: height - 8, "text-anchor": "middle", text: xLabel(i) }));
    }

    values.forEach((v, i) => {
      const cx = m.l + band * (i + 0.5);
      const x0 = cx - bw / 2;
      const top = y(v);
      const base = y(0);
      const r = Math.min(4, bw / 2, base - top);
      const emphasised = mark ? mark(i) : true;
      if (v > 0) {
        root.append(svg("path", {
          class: `mark${emphasised ? "" : " dim"}`,
          fill: color,
          d: `M${x0} ${base}V${top + r}Q${x0} ${top} ${x0 + r} ${top}H${x0 + bw - r}Q${x0 + bw} ${top} ${x0 + bw} ${top + r}V${base}Z`,
        }));
      }
    });
    root.append(svg("line", { class: "axis-line", x1: m.l, x2: W - m.r, y1: y(0), y2: y(0) }));

    if (cap) {
      const d = cap.map((c, i) => `${i ? "L" : "M"}${m.l + band * i} ${y(c)}L${m.l + band * (i + 1)} ${y(c)}`).join("");
      root.append(svg("path", { d, fill: "none", stroke: "var(--ink-2)", "stroke-width": 2, "stroke-linejoin": "round" }));
    }
    if (threshold) {
      const ty = y(threshold.value);
      root.append(
        svg("line", { x1: m.l, x2: W - m.r, y1: ty, y2: ty, stroke: "var(--ink-2)", "stroke-width": 1.5 }),
        svg("text", { class: "strong", x: W - m.r, y: ty - 5, "text-anchor": "end", text: threshold.label }),
      );
    }

    if (tip) {
      values.forEach((_, i) => {
        const rect = svg("rect", { class: "hit", x: m.l + band * i, y: m.t, width: band, height: ih, tabindex: 0, role: "img", "aria-label": tip(i).title });
        const open = (at) => showTip(at, tip(i).title, tip(i).rows);
        rect.addEventListener("pointermove", (e) => open({ x: e.clientX, y: e.clientY }));
        rect.addEventListener("pointerleave", hideTip);
        rect.addEventListener("focus", () => open(centreOf(rect)));
        rect.addEventListener("blur", hideTip);
        root.append(rect);
      });
    }
    return root;
  };
}

// -- build timeline ---------------------------------------------------------------------------------

/**
 * One row per build order: a bar from the first wafer start to shipment, a pin at the need-by week,
 * and a text status at the end of the row. shutdown: [weeks] shaded as a band.
 */
export function timelineChart({ orders, colorOf, shutdown = [], label }) {
  return (W) => {
    const narrow = W < 560;
    const rowH = 30;
    const m = { l: narrow ? 52 : 88, r: narrow ? 70 : 118, t: 20, b: 26 };
    const height = m.t + m.b + rowH * orders.length;
    const starts = orders.map((o) => Math.min(...o.fe_weeks.map(([w]) => w), o.ideal_fe_start));
    const first = Math.min(0, ...starts);
    const last = Math.max(...orders.map((o) => Math.max(o.ship_week, o.need_by))) + 1;
    const iw = W - m.l - m.r;
    const x = lin(first, last, m.l, m.l + iw);
    const root = svg("svg", { viewBox: `0 0 ${W} ${height}`, role: "img", "aria-label": label });

    const step = [1, 2, 4, 5, 10].find((s) => (last - first) / s <= (narrow ? 7 : 14)) || 10;
    for (let w = Math.ceil(first / step) * step; w <= last; w += step) {
      root.append(
        svg("line", { class: "grid-line", x1: x(w), x2: x(w), y1: m.t, y2: height - m.b }),
        svg("text", { x: x(w), y: height - 8, "text-anchor": "middle", text: `w${w}` }),
      );
    }
    for (const w of shutdown) {
      root.append(svg("rect", { x: x(w), y: m.t, width: Math.max(1, x(w + 1) - x(w)), height: orders.length * rowH, fill: "var(--band)" }));
    }
    if (shutdown.length) {
      root.append(svg("text", { x: x(shutdown[0]), y: m.t - 6, text: "fab shutdown" }));
    }

    orders.forEach((o, i) => {
      const cy = m.t + rowH * i + rowH / 2;
      const x0 = x(starts[i]);
      const x1 = x(o.ship_week);
      root.append(
        svg("text", { class: "strong", x: 4, y: cy + 4, text: o.order_id }),
        svg("rect", { class: "mark", x: x0, y: cy - 5, width: Math.max(3, x1 - x0), height: 10, rx: 4, fill: colorOf(o.pid) }),
        svg("line", { x1: x(o.need_by), x2: x(o.need_by), y1: cy - 11, y2: cy + 11, stroke: "var(--ink)", "stroke-width": 2 }),
        svg("circle", { cx: x1, cy, r: 4.5, fill: colorOf(o.pid), stroke: "var(--surface)", "stroke-width": 2 }),
        svg("text", { class: o.on_time ? "" : "strong", x: Math.max(x1, x(o.need_by)) + 10, y: cy + 4, text: o.on_time ? "on time" : `late +${o.delay_weeks}w` }),
      );
      if (!narrow) root.append(svg("text", { x: 38, y: cy + 4, text: o.pid }));
      const hit = svg("rect", { class: "hit", x: 0, y: m.t + rowH * i, width: W, height: rowH, tabindex: 0, role: "img", "aria-label": `${o.order_id} ${o.pid}: ${o.on_time ? "on time" : `late ${o.delay_weeks} weeks`}` });
      const open = (at) => showTip(at, `${o.order_id} · ${o.pid}`, [
        { value: `${fmt.n(o.units)} units`, label: `${o.wafers} wafers` },
        { value: `w${o.need_by}`, label: "customer need-by" },
        { value: `w${o.ship_week}`, label: o.on_time ? "ships on time" : `ships ${o.delay_weeks}w late` },
        ...o.reasons.map((r) => ({ value: "•", label: r })),
      ]);
      hit.addEventListener("pointermove", (e) => open({ x: e.clientX, y: e.clientY }));
      hit.addEventListener("pointerleave", hideTip);
      hit.addEventListener("focus", () => open(centreOf(hit)));
      hit.addEventListener("blur", hideTip);
      root.append(hit);
    });
    return root;
  };
}
