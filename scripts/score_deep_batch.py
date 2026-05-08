"""Score every *.md in data/results/deep/ for a given task and produce a
ranked leaderboard markdown table.

Usage:
    python3 scripts/score_deep_batch.py --task dr_cross_deep_0001
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Defaults to deep_v3 (the 10-agent corpus). Override with
# DEEP_RESULTS_DIR=data/results/deep to score the legacy 5-agent set.
RESULTS_DIR = ROOT / os.environ.get("DEEP_RESULTS_DIR", "data/results/deep_v3")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    task_glob = list(RESULTS_DIR.glob(f"*__{args.task}*.md"))
    if not task_glob:
        print(f"no results found for {args.task} under {RESULTS_DIR}", file=sys.stderr)
        return 1

    rows = []
    for md in sorted(task_glob):
        agent = md.stem.split(f"__{args.task}")[0]
        out_path = RESULTS_DIR / f"{md.stem}.score.json"
        print(f"\n--- scoring {md.name} ---")
        cmd = [
            sys.executable, str(ROOT / "scripts" / "score_deep_answer.py"),
            "--task", args.task, "--answer", str(md), "--out", str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
        if proc.returncode != 0:
            print(f"  ! score failed for {md.name}:\n{proc.stderr[-500:]}")
            continue
        score = json.loads(out_path.read_text())
        rows.append({
            "agent": agent,
            "url_score": score["url_coverage"]["score"],
            "url_pass":  score["url_coverage"]["passed"],
            "must_recall": score["url_coverage"]["details"]["must_cite_recall"],
            "checklist_pass_rate": score["checklist"].get("pass_rate", 0.0),
            "checklist_pass": score["checklist"].get("pass_count", 0),
            "checklist_total": len(score["checklist"].get("verdicts", [])),
            "spec_pass": score["markdown_spec"]["words_ok"]
                         and score["markdown_spec"]["citations_ok"]
                         and score["markdown_spec"]["paragraphs_ok"],
            "word_count": score["markdown_spec"]["word_count"],
            "citation_count": score["markdown_spec"]["citation_count"],
            "composite": score["composite"]["composite_score"],
            "answer_chars": score["answer_chars"],
            "judge": score.get("judge_identity", {}).get("model", "?"),
        })

    rows.sort(key=lambda r: -r["composite"])
    print(f"\n=== Leaderboard ({len(rows)} agents on {args.task}) ===")
    header = ["#", "agent", "composite", "url_score", "must_recall",
              "checklist", "words", "cites"]
    print(" | ".join(header))
    print("-" * 100)
    for i, r in enumerate(rows, 1):
        print(" | ".join(str(x) for x in [
            i, r["agent"][:28], f'{r["composite"]:.3f}', f'{r["url_score"]:.3f}',
            f'{r["must_recall"]:.3f}',
            f'{r["checklist_pass"]}/{r["checklist_total"]}',
            r["word_count"], r["citation_count"],
        ]))

    if args.out_md:
        lines = [f"# Deep-tier leaderboard — {args.task}", "",
                 f"Judge: {rows[0]['judge'] if rows else '?'}",
                 "",
                 "| # | Agent | Composite | URL coverage | Must-cite recall | Checklist | Words | Citations |",
                 "|---:|---|---:|---:|---:|---:|---:|---:|"]
        for i, r in enumerate(rows, 1):
            lines.append(f"| {i} | `{r['agent']}` | **{r['composite']:.3f}** | "
                         f"{r['url_score']:.3f} | {r['must_recall']:.3f} | "
                         f"{r['checklist_pass']}/{r['checklist_total']} | "
                         f"{r['word_count']} | {r['citation_count']} |")
        Path(args.out_md).write_text("\n".join(lines))
        print(f"\nwrote {args.out_md}")
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
