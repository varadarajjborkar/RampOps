// Classic script, runs before the module graph loads: starts the one request every first paint needs
// so it overlaps with downloading and parsing the modules instead of waiting behind them.
window.__demo = fetch("/api/demo").catch(() => null);
