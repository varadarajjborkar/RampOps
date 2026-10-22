// Thin client for the RampOps JSON API.

export class ApiError extends Error {}

export async function get(path, params, signal) {
  const qs = params ? `?${new URLSearchParams(params)}` : "";
  const res = await fetch(`/api/${path}${qs}`, { signal });
  let data;
  try {
    data = await res.json();
  } catch {
    throw new ApiError(`Unexpected response (${res.status})`);
  }
  if (!res.ok) throw new ApiError(data.error || res.statusText);
  return data;
}

/**
 * Debounced, cancellable query. Newer calls abort older ones, so a fast slider never shows a stale answer.
 * `busy(true|false)` lets the caller dim the previous render while the next one loads.
 */
export function live({ path, wait = 180, onData, onError, busy }) {
  let timer;
  let ctl;
  return (params) => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      ctl?.abort();
      const mine = (ctl = new AbortController());
      busy(true);
      try {
        const data = await get(path, params, mine.signal);
        if (ctl === mine) {
          onError(null);
          onData(data, params);
        }
      } catch (e) {
        if (e.name !== "AbortError" && ctl === mine) onError(e.message);
      } finally {
        if (ctl === mine) busy(false);
      }
    }, wait);
  };
}

/** The baseline scenario. Uses the request boot.js already started, falling back to a fresh one. */
export async function demo() {
  const early = window.__demo;
  window.__demo = null;
  if (early) {
    try {
      const res = await early;
      if (res?.ok) return await res.json();
    } catch {
      // fall through to a normal request, which reports a proper error
    }
  }
  return get("demo");
}
