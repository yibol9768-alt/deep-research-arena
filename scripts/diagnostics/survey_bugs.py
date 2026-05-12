"""Survey all score JSONs in deep_v3/ for bug categories that warrant a
fix. Categories:

  J  judge_error in any of: checklist / analysis_depth / presentation /
     citation_alignment.judge.error  (any 1-3 of them — 3-of-3 are already
     filtered by leaderboard's _looks_degenerate)
  D  composite_v2=0 with chars > 5000 + cited > 0 + reach > 0 (real
     report with reachable URLs scored 0 — likely a sub-judge collapsing
     a pillar)
  E  empty answer (chars < 100) — typically runner failures, already
     filtered, but list for visibility
  R  runner-failure placeholder ("(<Agent> produced no report after Ns,
     exit=N)") — already filtered

Output: per-category counts, plus full list of pairs in J + D (the
ones we can re-run cheaply).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path("/opt/deep_reserch/data/results/deep_v3")
RUNNER_FAIL_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s\s*,\s*exit\s*=\s*\d+\s*\)",
    re.IGNORECASE,
)


def _gp(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def main() -> None:
    files = sorted(ROOT.glob("*_matrix.score.json"))
    cats: dict[str, list[str]] = defaultdict(list)
    judge_err_pairs: list[tuple[str, list[str]]] = []
    drift_pairs: list[str] = []

    for fp in files:
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            cats["parse-error"].append(fp.name)
            continue
        # Empty answer
        chars = d.get("answer_chars", 0) or 0
        if chars < 100:
            cats["E_empty"].append(fp.name)
            continue
        # Runner-failure placeholder
        ans_path = d.get("answer_path")
        if isinstance(ans_path, str):
            a = Path(ans_path)
            if not a.is_absolute():
                a = Path("/opt/deep_reserch") / a
            if a.exists():
                head = a.read_text(encoding="utf-8", errors="replace")[:300]
                if RUNNER_FAIL_RE.match(head.lstrip()):
                    cats["R_runner-fail"].append(fp.name)
                    continue
        # Judge errors
        errs = []
        for path, label in (
            (("checklist", "judge_error"), "checklist"),
            (("analysis_depth", "details", "judge_error"), "analysis_depth"),
            (("presentation", "details", "judge_error"), "presentation"),
            (("citation_alignment", "details", "judge", "error"), "citation_alignment"),
        ):
            v = _gp(d, *path)
            if v:
                errs.append(label)
        if errs:
            judge_err_pairs.append((fp.name, errs))
            cats[f"J{len(errs)}_judge"].append(fp.name)
        # Bias-suspect: composite_v2=0 with non-trivial real input
        c2 = _gp(d, "composite", "composite_v2")
        cited = _gp(d, "url_reachability", "details", "cited_total", default=0) or 0
        reach = _gp(d, "url_reachability", "score", default=0.0) or 0.0
        if (
            isinstance(c2, (int, float)) and c2 == 0.0
            and chars > 5000 and cited > 0 and reach > 0
        ):
            drift_pairs.append(fp.name)
            cats["D_zero-but-real"].append(fp.name)

    total = len(files)
    print(f"{'='*60}")
    print(f"Survey of {total} score JSONs in deep_v3/")
    print(f"{'='*60}")
    for cat in sorted(cats.keys()):
        print(f"  {cat:<22} {len(cats[cat]):>4}")
    clean = total - sum(len(v) for k, v in cats.items() if not k.startswith("D_"))
    print(f"  {'(clean)':<22} {clean:>4}")
    print()
    print(f"=== {len(judge_err_pairs)} pairs with judge_error (re-runnable) ===")
    for name, errs in judge_err_pairs[:20]:
        print(f"  {name:<60s} {','.join(errs)}")
    if len(judge_err_pairs) > 20:
        print(f"  ... (+{len(judge_err_pairs)-20} more)")
    print()
    print(f"=== {len(drift_pairs)} bias-suspects (composite_v2=0 despite real input) ===")
    for name in drift_pairs[:10]:
        print(f"  {name}")
    if len(drift_pairs) > 10:
        print(f"  ... (+{len(drift_pairs)-10} more)")


if __name__ == "__main__":
    main()
