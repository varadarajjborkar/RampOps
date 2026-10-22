// Shared client state. `demo` is the baseline scenario; `plan` follows the Builds what-if controls
// so the Materials tab always agrees with what the Builds tab shows.

export const state = {
  demo: null,
  plan: null,
  planParams: { fe_capacity: 25, be_capacity: 40000, max_pull_in: 3, shutdown_start: 10, shutdown_len: 2 },
};

export const planQuery = (p) => ({
  fe_capacity: p.fe_capacity,
  be_capacity: p.be_capacity,
  max_pull_in: p.max_pull_in,
  maintenance: Array.from({ length: p.shutdown_len }, (_, i) => p.shutdown_start + i).join(","),
});

export const productIndex = (plan) => Object.fromEntries(plan.products.map((p, i) => [p.pid, i]));
export const colourOf = (plan) => {
  const idx = productIndex(plan);
  return (pid) => `var(--s${(idx[pid] ?? 0) + 1})`;
};
