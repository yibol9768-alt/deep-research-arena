"""Create the missing src/scoring/leaderboard_composites.py module that
build_deep_leaderboard.py expects to import. The module just exposes
helpers that read the already-computed composite values from a score
dict — keeping the leaderboard's source-of-truth aligned with what
score_deep_answer.py wrote.
"""

from pathlib import Path

CONTENT = '''"""Single source of truth for composite formulas used by the
leaderboard, ablation, and analysis scripts.

The score JSON files written by ``score_deep_answer.py`` already include
``composite.composite_v1``, ``composite.composite_v2``, etc. These helpers
just look them up so every analysis script reads the SAME number.
"""

from __future__ import annotations

from typing import Any


def composite_v1(score: dict) -> float:
    c = score.get("composite") or {}
    return float(c.get("composite_v1", 0.0) or 0.0)


def composite_v2_truthful(score: dict) -> float:
    c = score.get("composite") or {}
    return float(c.get("composite_v2", 0.0) or 0.0)


def composite_v3(score: dict) -> float:
    c = score.get("composite") or {}
    return float(c.get("composite_v3", 0.0) or 0.0)


def spec_pass_fraction(score: dict) -> float:
    c = score.get("composite") or {}
    if "spec_pass_fraction" in c:
        return float(c["spec_pass_fraction"] or 0.0)
    spec = score.get("markdown_spec") or {}
    flags = (spec.get("words_ok"), spec.get("citations_ok"), spec.get("paragraphs_ok"))
    if all(f is None for f in flags):
        return 0.0
    return sum(1 for f in flags if f) / 3.0


def checklist_pass_rate(score: dict) -> float:
    cl = score.get("checklist") or {}
    return float(cl.get("pass_rate", 0.0) or 0.0)


def url_coverage_score(score: dict) -> float:
    uc = score.get("url_coverage") or {}
    return float(uc.get("score", 0.0) or 0.0)


def reachability_score(score: dict) -> float:
    r = score.get("url_reachability") or {}
    return float(r.get("score", 0.0) or 0.0)
'''


def main() -> int:
    target = Path("/opt/deep_reserch/src/scoring/leaderboard_composites.py")
    if target.exists():
        print(f"already exists: {target}")
        return 0
    target.write_text(CONTENT)
    print(f"created {target} ({len(CONTENT)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
