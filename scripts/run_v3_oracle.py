"""Run a v3 deep-research Oracle and dump:
  - the oracle's markdown report → data/results/oracle_v3_<task_id>.md
  - the KG triples (oracle writes them itself) → data/golden/<task_id>.json

Usage:
    SHOPPING=http://localhost:7770 REDDIT=http://localhost:9999 \
        python scripts/run_v3_oracle.py dr_shop_v3_0001
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import PlaywrightRunner  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_v3_oracle.py <task_id>", file=sys.stderr)
        return 2
    tid = sys.argv[1]

    if tid.startswith("dr_shop_v3"):
        site, oracle_pkg = "shopping", "envs.shopping.oracle_dr_v3"
    elif tid.startswith("dr_red_v3"):
        site, oracle_pkg = "reddit", "envs.reddit.oracle_dr_v3"
    else:
        print(f"unknown v3 task prefix: {tid}", file=sys.stderr)
        return 2

    cfg_path = ROOT / "data" / "tasks" / "deep_research" / site / f"{tid}.json"
    cfg = json.loads(cfg_path.read_text())

    mod = importlib.import_module(f"{oracle_pkg}.{tid}_oracle")
    runner = PlaywrightRunner(headless=True, timeout_ms=90_000)
    cfg_resolved = runner.resolve(cfg)

    from playwright.sync_api import sync_playwright
    import time as _time
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(60_000)
        # Make page.goto resilient to intermittent SSH-tunnel drops: retry
        # ERR_CONNECTION_REFUSED up to 5 times with 2s back-off so the
        # keep_tunnel.sh helper has a chance to re-establish before we
        # abort. This dramatically improves long-running oracle stability.
        _orig_goto = page.goto
        def _retrying_goto(url, **kw):
            last_err = None
            for attempt in range(5):
                try:
                    return _orig_goto(url, **kw)
                except Exception as e:
                    msg = str(e)
                    if "CONNECTION_REFUSED" in msg or "ERR_NETWORK_CHANGED" in msg or "Connection closed" in msg:
                        last_err = e
                        _time.sleep(2)
                        continue
                    raise
            raise last_err  # type: ignore
        page.goto = _retrying_goto  # type: ignore
        page.goto(cfg_resolved["start_url"])
        page.wait_for_load_state("domcontentloaded")
        md = mod.oracle(page, cfg_resolved)
        browser.close()

    out_dir = ROOT / "data" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_md = out_dir / f"oracle_v3_{tid}.md"
    out_md.write_text(md or "")

    import re
    words = len((md or "").split())
    paragraphs = sum(1 for line in (md or "").split("\n") if line.strip().startswith("#") or len(line.strip()) > 60)
    links = re.findall(r"\[[^\]]+\]\([^)]+\)", md or "")
    golden_path = ROOT / "data" / "golden" / f"{tid}.json"
    n_triples = 0
    if golden_path.exists():
        n_triples = len(json.loads(golden_path.read_text()))

    print(f"=== {tid} ===")
    print(f"  words:   {words} (target ≥ {cfg.get('markdown_spec',{}).get('min_words', 500)})")
    print(f"  paras:   ~{paragraphs} (target ≥ {cfg.get('markdown_spec',{}).get('min_paragraphs', 3)})")
    print(f"  md links: {len(links)} (target ≥ {cfg.get('markdown_spec',{}).get('min_citations', 5)})")
    print(f"  triples: {n_triples}")
    print(f"  saved:   {out_md.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
