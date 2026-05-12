"""Re-run only the url_coverage verifier on existing score JSONs and patch
must_cite_hit / must_cite_recall / score in place. Then recompute composite
math from the NEW url_coverage value combined with the EXISTING judge-based
sub-scores (which the canonicaliser fix doesn't touch).

This is the fast fix for the Kiwix-URL-alias bug: the LLM judges don't change
because the answer.md content is the same, only the URL → golden matching
changed. So we save 5+ hours of LLM judge re-runs.

Usage:
    python rescore_url_coverage.py [--apply] <score.json> [<score.json>...]
    python rescore_url_coverage.py [--apply] --all-drifts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/deep_reserch")

from src.verifiers.url_coverage_verifier import URLCoverageVerifier  # noqa: E402

ROOT = Path("/opt/deep_reserch/data/results")
TASKS_DIR = Path("/opt/deep_reserch/data/tasks/deep_research/cross_site_deep")


def rescore(score_path: Path, apply: bool) -> dict:
    data = json.loads(score_path.read_text(encoding="utf-8"))
    task_id = data.get("task")
    if not task_id:
        return {"path": str(score_path), "error": "no task field"}

    # Load task config
    task_path = TASKS_DIR / f"{task_id}.json"
    if not task_path.exists():
        return {"path": str(score_path), "error": f"no task config {task_path}"}
    task_config = json.loads(task_path.read_text(encoding="utf-8"))

    # Load answer
    ans = data.get("answer_path")
    if not ans:
        return {"path": str(score_path), "error": "no answer_path"}
    a = Path(ans)
    if not a.is_absolute():
        a = Path("/opt/deep_reserch") / a
    if not a.exists():
        return {"path": str(score_path), "error": f"answer not on disk: {a}"}
    answer_md = a.read_text(encoding="utf-8", errors="replace")

    # Re-run url_coverage with patched canonicaliser
    v = URLCoverageVerifier()
    new = v.verify(task_config=task_config, answer=answer_md, page=None)
    new_uc = {
        "score": new.score,
        "passed": new.passed,
        "details": new.details,
    }
    old_uc = data.get("url_coverage", {})
    old_hit = (old_uc.get("details") or {}).get("must_cite_hit", 0)
    new_hit = (new.details or {}).get("must_cite_hit", 0)

    if old_hit == new_hit and abs(old_uc.get("score", 0) - new.score) < 1e-6:
        return {
            "path": str(score_path), "task": task_id, "delta": 0,
            "old_hit": old_hit, "new_hit": new_hit, "old_score": old_uc.get("score"),
            "new_score": new.score, "applied": False, "reason": "no change",
        }

    # Recompute composite math using the SAME formula as score_deep_answer.py.
    # The canonicaliser fix only changes url_cov; all other inputs (judges,
    # reachability, quote_match, claim_nli, spec_pass) are unchanged.
    c = data.get("composite", {}) or {}
    old_v2 = c.get("composite_v2")

    # Pull values that don't change
    grounding_gate = c.get("grounding_gate", 0.0)
    citation_alignment = c.get("citation_alignment", 0.0)
    analysis_depth = c.get("analysis_depth", 0.0)
    presentation = c.get("presentation", 0.0)
    spec_pass = c.get("spec_pass_fraction", 0.0)
    qm_factor = c.get("qm_factor", 0.0)
    nli_factor = c.get("nli_factor", 0.0)
    pass_rate = (data.get("checklist") or {}).get("pass_rate", 0.0)
    # quote_match score (not the qm_factor) — for v3 raw_score
    quote_match_score = (data.get("quote_match") or {}).get("score", 0.0)
    # reachability is the multiplier (qm_factor and nli_factor encode the
    # other 2 terms of truth = reachability * qm_factor * nli_factor)
    truth_old = c.get("truth_factor", 0.0)
    # truth_factor is unchanged — it has no url_cov dependency
    truth = truth_old

    # composite_v2 = truth * quality, quality = 0.4*url_cov + 0.4*checklist + 0.2*spec
    quality_new = 0.40 * new.score + 0.40 * pass_rate + 0.20 * spec_pass
    composite_v2_new = truth * quality_new

    # composite_v3 = grounding_gate * raw_score
    raw_score_v3 = (
        0.20 * new.score
        + 0.20 * quote_match_score
        + 0.20 * pass_rate
        + 0.10 * spec_pass
        + 0.15 * citation_alignment
        + 0.10 * analysis_depth
        + 0.05 * presentation
    )
    composite_v3_new = grounding_gate * raw_score_v3
    # composite_v1 = reachability * quality_new (reachability ~= grounding_gate / max-floor)
    # We didn't store reachability separately; back it out from the score JSON
    reachability = (data.get("url_reachability") or {}).get("score", grounding_gate)
    composite_v1_new = reachability * quality_new
    legacy_composite_new = 0.50 * new.score + 0.35 * pass_rate + 0.15 * spec_pass

    if apply:
        data["url_coverage"] = new_uc
        c["composite_v3"] = round(composite_v3_new, 4)
        c["composite_v2"] = round(composite_v2_new, 4)
        c["composite_v1"] = round(composite_v1_new, 4)
        c["composite_score"] = round(composite_v2_new, 4)
        c["legacy_composite"] = round(legacy_composite_new, 4)
        c["raw_score_v3"] = round(raw_score_v3, 4)
        c["quality_score"] = round(quality_new, 4)
        data["composite"] = c
        # Write a backup so we can revert if something looks wrong
        bak = score_path.with_suffix(".json.prekiwix.bak")
        if not bak.exists():
            bak.write_text(score_path.read_text(encoding="utf-8"))
        score_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return {
        "path": str(score_path),
        "task": task_id,
        "old_hit": old_hit,
        "new_hit": new_hit,
        "old_score_uc": old_uc.get("score"),
        "new_score_uc": new.score,
        "old_v2": old_v2,
        "new_v2": round(composite_v2_new, 4),
        "delta_v2": round(composite_v2_new - (old_v2 or 0.0), 4),
        "applied": apply,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write changes")
    ap.add_argument("--all-drifts", action="store_true", help="rescore every DRIFT pair")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()

    targets: list[Path] = []
    if args.all_drifts:
        # Use the verify_all_historical script's output to find DRIFT pairs
        from scripts.verify_all_historical import verify
        for fp in sorted((ROOT / "deep").glob("*_matrix.score.json")):
            r = verify(fp)
            if r.get("verdict") == "DRIFT":
                targets.append(fp)
        # Also check deep_v3 (current bulk run)
        for fp in sorted((ROOT / "deep_v3").glob("*_matrix.score.json")):
            r = verify(fp)
            if r.get("verdict") == "DRIFT":
                targets.append(fp)
        print(f"found {len(targets)} DRIFT pairs to rescore")
    else:
        for p in args.paths:
            targets.append(Path(p))

    summary = []
    for fp in targets:
        r = rescore(fp, args.apply)
        summary.append(r)
        if "error" in r:
            print(f"ERR  {fp.name}: {r['error']}")
        else:
            applied = "[APPLIED]" if r["applied"] else "[DRY-RUN]"
            print(
                f"{applied} {Path(r['path']).name}  "
                f"hit {r['old_hit']}->{r['new_hit']}  "
                f"uc {r['old_score_uc']:.4f}->{r['new_score_uc']:.4f}  "
                f"composite_v2 {r['old_v2']:.4f}->{r['new_v2']:.4f}  "
                f"(Δ={r['delta_v2']:+.4f})"
            )
    if args.apply:
        print(f"\napplied changes to {sum(1 for r in summary if r.get('applied'))} files")
    else:
        print(f"\ndry run — pass --apply to write changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
