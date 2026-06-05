#!/usr/bin/env python3
"""Score the presentation (quality) axis for every report, in parallel.

The full scorer runs ~15 verifiers per report; the differentiated board only
needs presentation (the validated quality signal, length-residualized later).
This runs PresentationVerifier alone over all non-quarantine reports with a
thread pool so the judge calls overlap (the cache removed the Magento load that
made parallelism unsafe). Writes {agent, task, presentation, word_count}.

  set -a; . /root/.config/dra/judge.env; set +a
  python3 scripts/score_presentation_field.py --workers 8 \
     --out data/results/presentation_uniform.json
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "data" / "results" / "deep"
_LOCK = threading.Lock()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "data" / "results" / "presentation_uniform.json"))
    args = ap.parse_args(argv)

    from src.verifiers.presentation_verifier import PresentationVerifier
    pv = PresentationVerifier()
    manifest = json.loads((ROOT / "data/golden/deep_clean/_manifest.json").read_text())["tasks"]
    cfg = {"domain_aliases": {"__SHOPPING__": ["localhost:7770"],
                              "__REDDIT__": ["localhost:9999"],
                              "__WIKIPEDIA__": ["localhost:8090"]}}

    files = []
    for md in sorted(glob.glob(str(REPORTS / "*__dr_cross_deep_*_matrix.md"))):
        task = Path(md).name.split("__")[1].rsplit("_matrix", 1)[0]
        if (manifest.get(task) or {}).get("verdict") != "quarantine":
            files.append(md)

    rows = []
    done = [0]

    def score(md):
        name = Path(md).name
        agent = name.split("__")[0]; task = name.split("__")[1].rsplit("_matrix", 1)[0]
        text = Path(md).read_text(encoding="utf-8", errors="ignore")
        try:
            s = float(pv.verify(task_config=cfg, answer=text).score)
        except Exception:
            s = 0.0
        with _LOCK:
            rows.append({"agent": agent, "task": task, "presentation": round(s, 4),
                         "word_count": len(text.split())})
            done[0] += 1
            if done[0] % 100 == 0:
                print(f"  {done[0]}/{len(files)}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(score, files))

    Path(args.out).write_text(json.dumps({"rows": rows, "n": len(rows)}, indent=1))
    print(f"wrote {args.out} ({len(rows)} reports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
