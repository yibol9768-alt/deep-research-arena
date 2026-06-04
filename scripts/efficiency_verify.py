#!/usr/bin/env python3
"""Verify grounded citations for the efficiency experiment reports.

For each report data/results/deep/eff-*__<task>_matrix.md, extract every
http://localhost:* URL it cites, curl each (GET, count 200 vs non-200), and
compute a grounded-citation fraction = live_200 / n_cited. Merge with the
token/word/latency metrics from data/results/efficiency/efficiency.json and
write:
  - data/results/efficiency/efficiency.json  (augmented in place with the
    grounding fields per row)
  - data/results/efficiency/efficiency_table.md (the human-readable table)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EFF_JSON = ROOT / "data" / "results" / "efficiency" / "efficiency.json"
REPORT_DIR = ROOT / "data" / "results" / "deep"
TABLE_MD = ROOT / "data" / "results" / "efficiency" / "efficiency_table.md"

URL_RE = re.compile(r"https?://localhost:\d+[^\s)\]\"'>]*")


def _curl(url: str, timeout: float = 8.0) -> int:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def verify_report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    urls = []
    seen = set()
    for m in URL_RE.findall(text):
        u = m.rstrip(".,;")
        if u not in seen:
            seen.add(u)
            urls.append(u)
    live = 0
    checks = []
    for u in urls:
        code = _curl(u)
        if code == 200:
            live += 1
        checks.append({"url": u, "code": code})
    n = len(urls)
    return {
        "n_cited": n,
        "n_live_200": live,
        "grounded_frac": round(live / n, 3) if n else 0.0,
        "checks": checks,
    }


def main() -> int:
    data = json.loads(EFF_JSON.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    for r in rows:
        if "error" in r:
            r["n_cited"] = 0
            r["n_live_200"] = 0
            r["grounded_frac"] = 0.0
            continue
        rp = r.get("report_path")
        p = Path(rp) if rp else None
        if not p or not p.exists():
            # try to locate by naming convention
            safe = re.sub(r"[^a-z0-9.-]+", "-", r["model"].lower())
            p = REPORT_DIR / f"eff-{safe}__{r['task']}_matrix.md"
        if p.exists():
            v = verify_report(p)
            r["n_cited"] = v["n_cited"]
            r["n_live_200"] = v["n_live_200"]
            r["grounded_frac"] = v["grounded_frac"]
            r["citation_checks"] = v["checks"]
        else:
            r["n_cited"] = 0
            r["n_live_200"] = 0
            r["grounded_frac"] = 0.0
            r["verify_note"] = f"report not found: {p}"

    EFF_JSON.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")

    # Build the markdown table.
    hdr = ("| model | task | tokens_total (in/out) | words | n_cited | "
           "live_200 | grounded_frac | latency_s |")
    sep = ("|---|---|---|---|---|---|---|---|")
    lines = [hdr, sep]
    for r in rows:
        if "error" in r:
            lines.append(
                f"| {r['model']} | {r['task']} | ERROR | - | - | - | - | - |  "
                f"<!-- {r['error']} -->"
            )
            continue
        tt = r.get("tokens_total", 0)
        ti = r.get("tokens_in", 0)
        to = r.get("tokens_out", 0)
        lines.append(
            f"| {r['model']} | {r['task']} | {tt} ({ti}/{to}) | "
            f"{r.get('words', 0)} | {r.get('n_cited', 0)} | "
            f"{r.get('n_live_200', 0)} | {r.get('grounded_frac', 0.0)} | "
            f"{r.get('latency_s', 0)} |"
        )
    TABLE_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Also print a plain summary to stdout for the operator.
    print("=== EFFICIENCY + GROUNDING SUMMARY ===")
    for r in rows:
        if "error" in r:
            print(f"{r['model']:32} {r['task']:20} ERROR: {r['error']}")
            continue
        print(f"{r['model']:32} {r['task']:20} tok={r.get('tokens_total',0):6} "
              f"(in {r.get('tokens_in',0)}/out {r.get('tokens_out',0)}) "
              f"words={r.get('words',0):5} cited={r.get('n_cited',0):3} "
              f"live200={r.get('n_live_200',0):3} "
              f"grounded={r.get('grounded_frac',0.0):5} "
              f"lat={r.get('latency_s',0)}s")
    print(f"\nWrote {TABLE_MD}")
    print(f"Augmented {EFF_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
