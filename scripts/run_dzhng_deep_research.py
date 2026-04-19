"""Drive dzhng/deep-research (Node.js + Firecrawl) via its HTTP API.

Our shim already exposes Firecrawl-compatible /v1/search + /v1/scrape,
so dzhng runs zero-code: we only set FIRECRAWL_BASE_URL + OPENAI_ENDPOINT.

dzhng's HTTP server (src/api.ts) is started separately with
`npm run api` on port 3051; this script fires one POST per task.

Env (set before invoking):
    DZHNG_API_URL=http://localhost:3051/api/generate-report
    # (the dzhng server itself reads FIRECRAWL_BASE_URL / OPENAI_* from .env.local)

Outputs:
    data/results/dzhng-deep-research_dr_cross_v3_<TASK>.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("DZHNG_API_URL", "http://localhost:3051/api/generate-report")
TASKS = [
    "dr_cross_v3_0001",
    "dr_cross_v3_0005",
    "dr_cross_v3_0006",
    "dr_cross_v3_0007",
]
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site"
OUT_DIR = ROOT / "data" / "results"


def _load_intent(task_id: str) -> str:
    cfg = json.loads((TASKS_DIR / f"{task_id}.json").read_text())
    return cfg.get("intent") or cfg.get("description") or ""


def _run_one(task_id: str) -> None:
    intent = _load_intent(task_id)
    print(f"\n{'='*60}\ndzhng-deep-research: {task_id}\n{'='*60}")
    t0 = time.time()
    try:
        r = requests.post(
            API,
            json={
                "query": intent,
                "breadth": int(os.environ.get("DZHNG_BREADTH", "2")),
                "depth": int(os.environ.get("DZHNG_DEPTH", "2")),
            },
            timeout=1800,
        )
        if r.status_code >= 400:
            report = f"(dzhng API HTTP {r.status_code}: {r.text[:500]})"
        else:
            # /api/generate-report returns the raw report as body, not JSON
            report = r.text
    except Exception as e:
        report = f"(dzhng error: {type(e).__name__}: {e})"
    elapsed = time.time() - t0
    out_path = OUT_DIR / f"dzhng-deep-research_{task_id}.md"
    out_path.write_text(report or "(empty)")
    print(f"Finished in {elapsed:.0f}s, {len(report)} chars → {out_path}")


def main() -> None:
    only = os.environ.get("DZHNG_ONLY_TASK")
    tasks = [only] if only else TASKS
    for t in tasks:
        try:
            _run_one(t)
        except Exception as e:
            print(f"Task {t} failed: {e}")


if __name__ == "__main__":
    main()
