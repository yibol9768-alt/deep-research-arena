#!/usr/bin/env python3
"""Select a per-task REFERENCE report for RACE-style reference-anchored scoring.

This is eval problem #3 (reference-anchored quality). The leaderboard's quality
number is normally a peer round-robin pairwise battle. RACE-style scoring instead
judges every agent AGAINST a single high-quality reference report per task and
uses the win-rate vs that reference (Arena-Hard style).

This script picks the reference. For each task that has at least one real matrix
report on disk (``data/results/deep/<agent>__<task>_matrix.md``), the REFERENCE
is the report with the highest STORED grounding, read from
``data/results/deep_v3/<agent>__<task>_matrix.score.json``. "Highest grounding"
is a lexicographic key:

    1. quote_match.score   (citation fidelity; primary)
    2. must_cite_recall    (url_coverage.details.must_cite_recall; tie-break)

We DO NOT generate a fresh gold report here: the reference is the best EXISTING
grounded report, which is a pragmatic anchor. A separately-generated gold
reference is a known follow-up (tracked as a box item), not done here.

Output: ``data/reference_reports/manifest.json`` mapping

    {task_id: {"agent": ..., "path": <abs report path>, "grounding": {...}}}

where ``grounding`` records the deciding numbers so the choice is auditable.
Paths are stored repo-relative (matching the ``answer_path`` convention in the
stored score JSON) so the manifest is portable and committable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Repo root so default paths resolve regardless of CWD.
_REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPORT_DIR = _REPO_ROOT / "data" / "results" / "deep"
DEFAULT_SCORE_DIR = _REPO_ROOT / "data" / "results" / "deep_v3"
DEFAULT_OUT = _REPO_ROOT / "data" / "reference_reports" / "manifest.json"

# <agent>__<task_id>_matrix.md  (only matrix reports; smoke runs are warm-up).
_MATRIX_RE = re.compile(r"^(?P<agent>.+?)__(?P<task>.+?)_matrix\.md$")


def discover_reports(report_dir: Path) -> dict[str, dict[str, Path]]:
    """Return {task_id: {agent: md_path}} for every real matrix report on disk.

    Never fabricates entries. Tasks/agents with no file simply do not appear.
    """
    out: dict[str, dict[str, Path]] = defaultdict(dict)
    for p in sorted(Path(report_dir).glob("*_matrix.md")):
        m = _MATRIX_RE.match(p.name)
        if not m:
            continue
        out[m.group("task")][m.group("agent")] = p
    return {t: dict(a) for t, a in out.items()}


def score_path_for(score_dir: Path, agent: str, task: str) -> Path:
    return Path(score_dir) / f"{agent}__{task}_matrix.score.json"


def _store_path(path: Path) -> str:
    """Render ``path`` repo-relative when inside the repo, else absolute.

    Matches the ``answer_path`` convention in the stored score JSON so the
    manifest stays portable and committable.
    """
    p = Path(path).resolve()
    try:
        return str(p.relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


def _load_score_json(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def grounding_key(score_json: dict) -> dict[str, float]:
    """Extract the deciding grounding numbers from a stored score JSON.

    Returns a dict with ``quote_match_score`` (primary) and ``must_cite_recall``
    (tie-break). Missing fields default to 0.0 so a report whose score JSON lacks
    them simply ranks last rather than crashing the selection.
    """
    qm = float((score_json.get("quote_match") or {}).get("score") or 0.0)
    cov = (score_json.get("url_coverage") or {}).get("details") or {}
    recall = float(cov.get("must_cite_recall") or 0.0)
    return {"quote_match_score": qm, "must_cite_recall": recall}


def select_reference_for_task(
    agents_to_paths: dict[str, Path],
    score_dir: Path,
    task: str,
) -> dict[str, Any] | None:
    """Pick the highest-grounding agent for one task.

    Prefers highest ``quote_match.score`` then highest ``must_cite_recall``.
    An agent whose score JSON is missing is treated as grounding (0.0, 0.0) so
    it can still be the reference if it is the ONLY report for the task (better
    a known-weak anchor than no anchor), but it always loses to a scored peer.
    Returns ``None`` only when the task has no reports at all.
    """
    best: dict[str, Any] | None = None
    best_tuple: tuple[float, float] | None = None
    # Deterministic agent order for stable tie-breaking on identical numbers.
    for agent in sorted(agents_to_paths):
        path = agents_to_paths[agent]
        sj = _load_score_json(score_path_for(score_dir, agent, task))
        if sj is None:
            g = {"quote_match_score": 0.0, "must_cite_recall": 0.0, "score_json_missing": True}
        else:
            g = grounding_key(sj)
        key = (g["quote_match_score"], g["must_cite_recall"])
        if best_tuple is None or key > best_tuple:
            best_tuple = key
            best = {"agent": agent, "path": _store_path(path), "grounding": g}
    return best


def build_manifest(
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    score_dir: Path = DEFAULT_SCORE_DIR,
) -> dict[str, dict[str, Any]]:
    """Return {task_id: {agent, path, grounding}} selecting one reference/task."""
    reports = discover_reports(report_dir)
    manifest: dict[str, dict[str, Any]] = {}
    for task in sorted(reports):
        ref = select_reference_for_task(reports[task], score_dir, task)
        if ref is not None:
            manifest[task] = ref
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--report-dir", type=str, default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--score-dir", type=str, default=str(DEFAULT_SCORE_DIR))
    p.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    args = p.parse_args(argv)

    manifest = build_manifest(
        report_dir=Path(args.report_dir),
        score_dir=Path(args.score_dir),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print("=" * 64)
    print("REFERENCE selection (RACE-style reference-anchored scoring)")
    print("=" * 64)
    print(f"Report dir: {args.report_dir}")
    print(f"Score dir:  {args.score_dir}")
    print(f"Tasks with a reference: {len(manifest)}")
    for task in sorted(manifest):
        ref = manifest[task]
        g = ref["grounding"]
        print(
            f"  - {task}: {ref['agent']}  "
            f"(quote={g.get('quote_match_score')}, recall={g.get('must_cite_recall')})"
        )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
