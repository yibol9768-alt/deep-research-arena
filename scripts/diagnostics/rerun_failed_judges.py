"""Re-run only the failed sub-judges for pairs with 1-2 judge_errors.

Reads score JSONs in data/results/deep_v3/, identifies pairs with exactly
1 or 2 (not 3-of-3) sub-judges errored, re-runs only those judges using
DeepSeek via ds_proxy, and patches the score JSON in place. Composites
(v2/v3/v1) get recomputed from the fresh judge output combined with the
existing pillars that didn't change.

Pairs with 3-of-3 judge errors are filtered out of Elo by the leaderboard
already, so we skip those (saves API calls).

Usage:
    python rerun_failed_judges.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, "/opt/deep_reserch")

from src.verifiers.checklist_verifier import ChecklistVerifier
from src.verifiers.analysis_depth_verifier import AnalysisDepthVerifier
from src.verifiers.presentation_verifier import PresentationVerifier

ROOT = Path("/opt/deep_reserch/data/results/deep_v3")
TASKS_DIR = Path("/opt/deep_reserch/data/tasks/deep_research/cross_site_deep")


def _gp(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _load_task_config(task_id: str) -> dict | None:
    p = TASKS_DIR / f"{task_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _recompute_composites(d: dict) -> None:
    """Mirror score_deep_answer.py composite math."""
    spec = d.get("markdown_spec", {}) or {}
    spec_pass_fraction = sum(
        bool(spec.get(k)) for k in ("words_ok", "citations_ok", "paragraphs_ok")
    ) / 3.0
    url_cov = (d.get("url_coverage") or {}).get("score", 0.0) or 0.0
    reach = (d.get("url_reachability") or {}).get("score", 0.0) or 0.0
    qm = (d.get("quote_match") or {}).get("score", 0.0) or 0.0
    nli = (d.get("claim_nli") or {}).get("score", 0.0) or 0.0
    cl_pass_rate = (d.get("checklist") or {}).get("pass_rate", 0.0) or 0.0
    cit_align = (d.get("citation_alignment") or {}).get("score", 0.0) or 0.0
    ad = (d.get("analysis_depth") or {}).get("score", 0.0) or 0.0
    pres = (d.get("presentation") or {}).get("score", 0.0) or 0.0

    quality = 0.4 * url_cov + 0.4 * cl_pass_rate + 0.2 * spec_pass_fraction
    qm_factor = 0.5 + 0.5 * qm
    nli_factor = 0.5 + 0.5 * nli
    truth = reach * qm_factor * nli_factor
    composite_v2 = truth * quality
    composite_v1 = reach * quality
    legacy = 0.5 * url_cov + 0.35 * cl_pass_rate + 0.15 * spec_pass_fraction
    grounding_gate = max(0.1, reach)
    raw_score = (
        0.20 * url_cov + 0.20 * qm + 0.20 * cl_pass_rate
        + 0.10 * spec_pass_fraction + 0.15 * cit_align
        + 0.10 * ad + 0.05 * pres
    )
    composite_v3 = grounding_gate * raw_score

    c = d.setdefault("composite", {})
    c["spec_pass_fraction"] = round(spec_pass_fraction, 4)
    c["quality_score"] = round(quality, 4)
    c["truth_factor"] = round(truth, 4)
    c["qm_factor"] = round(qm_factor, 4)
    c["nli_factor"] = round(nli_factor, 4)
    c["grounding_gate"] = round(grounding_gate, 4)
    c["raw_score_v3"] = round(raw_score, 4)
    c["citation_alignment"] = round(cit_align, 4)
    c["analysis_depth"] = round(ad, 4)
    c["presentation"] = round(pres, 4)
    c["composite_v3"] = round(composite_v3, 4)
    c["composite_score"] = round(composite_v2, 4)
    c["composite_v2"] = round(composite_v2, 4)
    c["composite_v1"] = round(composite_v1, 4)
    c["legacy_composite"] = round(legacy, 4)


def _read_answer(d: dict) -> str:
    p = d.get("answer_path")
    if not p:
        return ""
    a = Path(p)
    if not a.is_absolute():
        a = Path("/opt/deep_reserch") / a
    return a.read_text(encoding="utf-8", errors="replace") if a.exists() else ""


def fix_pair(score_path: Path, apply: bool) -> dict:
    d = json.loads(score_path.read_text(encoding="utf-8"))
    task_id = d.get("task")
    task_cfg = _load_task_config(task_id) if task_id else None
    if not task_cfg:
        return {"path": str(score_path), "error": "no task config"}
    answer = _read_answer(d)
    if not answer:
        return {"path": str(score_path), "error": "no answer.md"}

    fixed: list[str] = []

    if _gp(d, "checklist", "judge_error"):
        v = ChecklistVerifier()
        try:
            r = v.verify(task_config=task_cfg, answer=answer, page=None)
        except Exception as e:
            return {"path": str(score_path), "error": f"checklist re-run failed: {e}"}
        det = r.details if hasattr(r, "details") else {}
        new_cl = {
            "verdicts": det.get("verdicts", []),
            "pass_count": det.get("pass_count", 0),
            "fail_count": det.get("fail_count", 0),
            "unclear_count": det.get("unclear_count", 0),
            "pass_rate": r.score,
            "judge_error": None,
        }
        d["checklist"] = new_cl
        fixed.append("checklist")

    if _gp(d, "analysis_depth", "details", "judge_error"):
        v = AnalysisDepthVerifier()
        try:
            r = v.verify(task_config=task_cfg, answer=answer, page=None)
        except Exception as e:
            return {"path": str(score_path), "error": f"analysis_depth re-run failed: {e}"}
        d["analysis_depth"] = {"score": r.score, "passed": r.passed, "details": r.details}
        fixed.append("analysis_depth")

    if _gp(d, "presentation", "details", "judge_error"):
        v = PresentationVerifier()
        try:
            r = v.verify(task_config=task_cfg, answer=answer, page=None)
        except Exception as e:
            return {"path": str(score_path), "error": f"presentation re-run failed: {e}"}
        d["presentation"] = {"score": r.score, "passed": r.passed, "details": r.details}
        fixed.append("presentation")

    if not fixed:
        return {"path": str(score_path), "skipped": "no judge_error to fix"}

    old_v2 = (d.get("composite") or {}).get("composite_v2", 0.0)
    _recompute_composites(d)
    new_v2 = d["composite"]["composite_v2"]

    if apply:
        bak = score_path.with_suffix(".json.prejudgefix.bak")
        if not bak.exists():
            bak.write_text(score_path.read_text(encoding="utf-8"))
        score_path.write_text(json.dumps(d, indent=2, ensure_ascii=False))

    return {
        "path": str(score_path),
        "fixed_judges": fixed,
        "old_v2": round(old_v2, 4),
        "new_v2": round(new_v2, 4),
        "applied": apply,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write changes")
    args = ap.parse_args()

    files = sorted(ROOT.glob("*_matrix.score.json"))
    targets: list[Path] = []
    for fp in files:
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        errs = [
            p for p in (
                ("checklist", "judge_error"),
                ("analysis_depth", "details", "judge_error"),
                ("presentation", "details", "judge_error"),
            ) if _gp(d, *p)
        ]
        # 3-of-3 errors are filtered by leaderboard, but try re-running
        # anyway to capture any transient API hiccups.
        if 1 <= len(errs) <= 3:
            targets.append(fp)

    print(f"target pairs to re-judge: {len(targets)}")
    for fp in targets:
        r = fix_pair(fp, args.apply)
        if "error" in r:
            print(f"  ERR  {Path(r['path']).name}: {r['error']}")
            continue
        if "skipped" in r:
            print(f"  SKIP {Path(r['path']).name}: {r['skipped']}")
            continue
        applied = "[APPLIED]" if r["applied"] else "[DRY-RUN]"
        print(f"  {applied} {Path(r['path']).name}  judges={r['fixed_judges']}  "
              f"v2 {r['old_v2']:.4f}->{r['new_v2']:.4f}")
    if not args.apply:
        print("\ndry run — pass --apply to write changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
