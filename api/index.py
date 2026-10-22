"""Vercel entrypoint. vercel.json rewrites every /api/<route> request here as /api/index?route=<route>."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rampops.web import ApiHandler  # noqa: E402


# This must be a literal `class handler`. Vercel decides whether api/index.py is a function by looking
# for that definition in the source; `from ... import ApiHandler as handler` is not recognised, and the
# deploy then succeeds with no function at all.
class handler(ApiHandler):
    """Vercel's Python runtime looks for a class named `handler`."""
