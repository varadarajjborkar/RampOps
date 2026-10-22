import { demo } from "./api.js";
import { disposeCharts } from "./charts.js";
import { h } from "./dom.js";
import { state } from "./state.js";
import { buildsView } from "./views/builds.js";
import { changeView } from "./views/change.js";
import { materialsView } from "./views/materials.js";
import { overviewView } from "./views/overview.js";
import { rampView } from "./views/ramp.js";

const VIEWS = { overview: overviewView, builds: buildsView, materials: materialsView, ramp: rampView, change: changeView };
const TITLES = { overview: "Overview", builds: "Sample builds", materials: "Materials", ramp: "Ramp-up", change: "Change control" };
const main = document.getElementById("view");

function render() {
  // Own-property check: `in` is also true for inherited keys such as "constructor" and "__proto__".
  const wanted = location.hash.slice(1);
  const name = Object.hasOwn(VIEWS, wanted) ? wanted : "overview";
  document.querySelectorAll("#nav a").forEach((a) => {
    if (a.dataset.view === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  document.title = `${TITLES[name]} · RampOps`;
  disposeCharts();
  main.replaceChildren(VIEWS[name]());
}

function initTheme() {
  const btn = document.getElementById("theme");
  const root = document.documentElement;
  const read = () => { try { return localStorage.getItem("theme"); } catch { return null; } };
  const write = (v) => { try { localStorage.setItem("theme", v); } catch { /* private mode: fine */ } };
  const dark = () => (root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  if (read()) root.dataset.theme = read();
  const label = () => { btn.textContent = dark() ? "Light mode" : "Dark mode"; };
  btn.addEventListener("click", () => {
    root.dataset.theme = dark() ? "light" : "dark";
    write(root.dataset.theme);
    label();
  });
  label();
}

async function start() {
  initTheme();
  try {
    state.demo = await demo();
    state.plan = state.demo.plan;
    document.getElementById("version").textContent = `v${state.demo.version}`;
    render();
    addEventListener("hashchange", () => { render(); main.focus({ preventScroll: true }); scrollTo(0, 0); });
  } catch (e) {
    main.replaceChildren(h("div", { class: "callout bad" }, h("p", { text: `Could not load the plan: ${e.message}. Try reloading.` })));
  }
}

start();
