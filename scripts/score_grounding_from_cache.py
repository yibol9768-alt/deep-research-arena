#!/usr/bin/env python3
"""Fast, judge-free grounding pass over every report, served from the cache.

The full scorer runs ~15 judge-based verifiers per report (slow). The truth-gate
only needs deterministic, judge-free signals: reachability + quote-match (both
read from the sandbox cache) + curated must-cite recall (local, from the cleaned
golden). This computes those for every report with NO judge calls and NO live
Magento fetches, so the whole field scores in seconds and the result is the
uniform, comparable grounding the leaderboard gate needs.

Run ON the box (needs the cache + reports):
  DRA_SANDBOX_CACHE=data/results/sandbox_cache.json \
  python3 scripts/score_grounding_from_cache.py --out data/results/grounding_uniform.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "data" / "results" / "deep"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "data" / "results" / "grounding_uniform.json"))
    ap.add_argument("--cache", default=os.environ.get("DRA_SANDBOX_CACHE"))
    args = ap.parse_args(argv)

    if not args.cache:
        print("ERROR: set DRA_SANDBOX_CACHE or --cache", file=sys.stderr)
        return 2
    os.environ["DRA_SANDBOX_CACHE"] = args.cache
    from src.verifiers.sandbox_http_cache import install
    install()  # all requests.get now served from the cache (instant)

    from src.verifiers.url_reachability_verifier import URLReachabilityVerifier
    from src.verifiers.quote_match_verifier import QuoteMatchVerifier
    from src.verifiers.golden_curate import curated_recall
    from src.verifiers.citation_format import canonicalize_url

    reach_v = URLReachabilityVerifier()
    quote_v = QuoteMatchVerifier()
    manifest = json.loads((ROOT / "data/golden/deep_clean/_manifest.json").read_text())["tasks"]
    _PORT_SRC = {"7770": "shopping", "9999": "forum", "8090": "wiki"}

    def _src(u):
        m = re.search(r"://[^/]*:(\d+)/", u or "")
        return _PORT_SRC.get(m.group(1)) if m else None

    def _curated(report_text, task_id, valid_sources):
        for sub in ("deep_clean", "deep"):
            gp = ROOT / "data" / "golden" / sub / f"{task_id}.json"
            if gp.exists():
                break
        else:
            return None
        try:
            mc = json.loads(gp.read_text()).get("must_cite_urls") or []
            if valid_sources is not None:
                mc = [e for e in mc if _src(e.get("url", "")) in valid_sources]
            if not mc:
                return None
            urls = re.findall(r'https?://localhost:\d+/[^\s)\]"\'>]+', report_text)
            cited = {canonicalize_url(u) for u in urls}
            return float(curated_recall(cited, mc, k=12))
        except Exception:
            return None

    task_cfg_base = {"domain_aliases": {"__SHOPPING__": ["localhost:7770"],
                                        "__REDDIT__": ["localhost:9999"],
                                        "__WIKIPEDIA__": ["localhost:8090"]}}

    rows = []
    files = sorted(glob.glob(str(REPORTS / "*__dr_cross_deep_*_matrix.md")))
    for i, md in enumerate(files):
        name = Path(md).name
        agent = name.split("__")[0]
        task = name.split("__")[1].rsplit("_matrix", 1)[0]
        if (manifest.get(task) or {}).get("verdict") == "quarantine":
            continue
        text = Path(md).read_text(encoding="utf-8", errors="ignore")
        cfg = dict(task_cfg_base)
        try:
            reach = reach_v.verify(task_config=cfg, answer=text).score
        except Exception:
            reach = 0.0
        try:
            quote = quote_v.verify(task_config=cfg, answer=text).score
        except Exception:
            quote = 0.0
        vs = set((manifest.get(task) or {}).get("valid_sources") or []) or None
        cr = _curated(text, task, vs)
        rows.append({"agent": agent, "task": task, "reachability": round(reach, 4),
                     "quote_match": round(quote, 4),
                     "curated_recall": round(cr, 4) if cr is not None else None})
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(files)} scored", flush=True)

    Path(args.out).write_text(json.dumps({"rows": rows, "n": len(rows)}, indent=1))
    print(f"wrote {args.out} ({len(rows)} reports, judge-free, from cache)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
