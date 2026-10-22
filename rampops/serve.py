"""Local dev server: static files from `public/` plus the same /api/* handler Vercel runs."""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .web import respond

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "public"


class DevHandler(SimpleHTTPRequestHandler):
    def _route(self) -> bool:
        if self.path.startswith("/api/") or self.path == "/api":
            respond(self)
            return True
        return False

    def do_GET(self) -> None:
        if not self._route():
            super().do_GET()

    def do_HEAD(self) -> None:
        if not self._route():
            super().do_HEAD()

    def _write_method(self) -> None:
        if not self._route():
            self.send_error(405)

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _write_method


def make_server(host: str = "127.0.0.1", port: int = 8000, directory: Path | str = DEFAULT_DIR) -> ThreadingHTTPServer:
    """Bind to loopback by default: this is a dev server, not something to expose."""
    return ThreadingHTTPServer((host, port), partial(DevHandler, directory=str(directory)))


def serve(host: str, port: int) -> None:
    with make_server(host, port) as srv:
        print(f"RampOps on http://{host}:{srv.server_address[1]}  (Ctrl+C to stop)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
