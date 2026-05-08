"""Sanity baselines for the deep-research benchmark.

Each baseline exposes::

    async def run(intent, model, shim_url, proxy_url) -> str

matching the signature of scripts/runners/*_runner.py.
"""

from . import golden_dump, random, stuffer  # noqa: F401

# Convenience map for run_sanity.py.
BASELINES = {
    "random": random.run,
    "stuffer": stuffer.run,
    "golden_dump": golden_dump.run,
}

__all__ = ["BASELINES", "random", "stuffer", "golden_dump"]
