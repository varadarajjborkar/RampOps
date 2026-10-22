import { h } from "./dom.js";

let uid = 0;

/** Labelled range input with a live value readout. */
export function slider({ label, min, max, step = 1, value, format = String, onInput }) {
  const id = `f${++uid}`;
  const out = h("output", { for: id, text: format(value) });
  const input = h("input", { id, type: "range", min, max, step, value });
  input.value = value;
  input.addEventListener("input", () => {
    const v = Number(input.value);
    out.textContent = format(v);
    onInput(v);
  });
  return {
    el: h("div", { class: "field" }, h("label", { for: id }, label, out), input),
    set(v) {
      input.value = v;
      out.textContent = format(v);
    },
  };
}

export function numberField({ label, min, max, value, onInput }) {
  const id = `f${++uid}`;
  const input = h("input", { id, type: "number", min, max, step: 1 });
  input.value = value;
  input.addEventListener("input", () => onInput(Number(input.value)));
  return h("div", { class: "field" }, h("label", { for: id, text: label }), input);
}

export function banner() {
  const el = h("p", { class: "error", role: "alert", hidden: true });
  return {
    el,
    show(msg) {
      el.hidden = !msg;
      el.textContent = msg || "";
    },
  };
}
