"""Vercel entrypoint. vercel.json rewrites every /api/<route> request here as /api/index?route=<route>."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rampops.web import ApiHandler as handler  # noqa: E402,F401  (Vercel looks for the name `handler`)
