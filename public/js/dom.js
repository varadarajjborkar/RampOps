// Tiny DOM helpers. Text always goes through textContent, so data from the API can never inject markup.

const SVG_NS = "http://www.w3.org/2000/svg";
const PROPS = new Set(["value", "checked", "disabled", "selected"]);

function apply(el, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (PROPS.has(k) && !(el instanceof SVGElement)) el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
}

function append(el, kids) {
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  apply(el, attrs);
  return append(el, kids);
}

export function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  apply(el, attrs);
  return append(el, kids);
}

export const fmt = {
  n: (v) => Math.round(v).toLocaleString("en-US"),
  pct: (v, d = 0) => `${(v * 100).toFixed(d)}%`,
  week: (w) => `w${w}`,
  compact: (v) => (Math.abs(v) >= 1000 ? `${+(v / 1000).toFixed(1)}K` : String(Math.round(v))),
  signed: (v) => (v > 0 ? `+${fmt.n(v)}` : fmt.n(v)),
};

export function debounce(fn, ms) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

const ICONS = {
  good: "M4.6 8.3l2.3 2.3 4.6-4.9",
  warn: "M8 4.2v4.6M8 11v.6",
  bad: "M5.2 5.2l5.6 5.6M10.8 5.2l-5.6 5.6",
};

/** Status is always icon + label, never colour alone. */
export function status(kind, label) {
  const shape = kind === "warn"
    ? svg("path", { d: "M8 .8l8 14H0z" })
    : svg("circle", { cx: 8, cy: 8, r: 8 });
  const glyph = svg("path", { d: ICONS[kind], stroke: "#fff", "stroke-width": 2, "stroke-linecap": "round", fill: "none" });
  if (kind === "warn") glyph.setAttribute("stroke", "#1a1a19");
  return h("span", { class: `status ${kind}` }, svg("svg", { viewBox: "0 0 16 16", "aria-hidden": "true" }, shape, glyph), label);
}

export function productTag(pid, index) {
  return h("span", { class: `tag p${index}` }, h("i"), pid);
}
