"""Re-run AnalysisDepthVerifier on every score file and recompute composite.

Fast variant of rescore_partial.py — only touches analysis_depth + composite.
Used after the _extract_domain fix landed (sandbox URLs were collapsing to
"localhost", killing Tier A multi-domain checks).
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from scripts.score_deep_answer import _composite, _markdown_spec_score  # noqa: E402
from src.verifiers.analysis_depth_verifier import AnalysisDepthVerifier  # noqa: E402


def rescore(score_path: Path) -> dict:
    t0 = time.time()
    sd = json.loads(score_path.read_text())

    candidates = []
    if sd.get("answer_path"):
        candidates.append(ROOT / sd["answer_path"])
    candidates.append(score_path.parent / score_path.name.replace(".score.json", ".md"))
    md_name = score_path.name.replace(".score.json", ".md")
    for d in ("data/results/deep", "data/results/deep_v3", "data/results/deep_reports"):
        candidates.append(ROOT / d / md_name)
    answer_path = next((p for p in candidates if p.exists()), None)
    if answer_path is None:
        return {"file": score_path.name, "skipped": "answer_md_missing", "old_ad": (sd.get("analysis_depth") or {}).get("score", 0.0), "new_ad": None, "dt": 0.0}
    answer = answer_path.read_text(errors="ignore")

    task_id = sd.get("task")
    task_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{task_id}.json"
    task_cfg = json.loads(task_path.read_text())

    try:
        v = AnalysisDepthVerifier()
        r = v.verify(task_config=task_cfg, answer=answer)
        new_ad = {"score": r.score, "passed": r.passed, "details": r.details}
    except Exception as e:
        new_ad = {"score": 0.0, "passed": False, "details": {"error": str(e)[:200]}}

    ad_score = new_ad["score"]
    old_ad_score = (sd.get("analysis_depth") or {}).get("score", 0.0)
    sd["analysis_depth"] = new_ad

    reach = sd.get("url_reachability", {}).get("score", 0.0)
    qm = sd.get("quote_match", {}).get("score", 0.0)
    url_cov = sd.get("url_coverage", {}).get("score", 0.0)
    spec = sd.get("markdown_spec") or _markdown_spec_score(answer, {})
    ck_pr = (sd.get("checklist") or {}).get("pass_rate", 0.0)
    nli = (sd.get("claim_nli") or {}).get("score", 0.0)
    cit_align = (sd.get("citation_alignment") or {}).get("score", 0.0) if isinstance(sd.get("citation_alignment"), dict) else 0.0
    pres = (sd.get("presentation") or {}).get("score", 0.0) if isinstance(sd.get("presentation"), dict) else 0.0

    sd["composite"] = _composite(
        reachability=reach, quote_match=qm, claim_nli=nli, url_cov=url_cov,
        checklist_pass_rate=ck_pr, spec=spec,
        citation_alignment=cit_align, analysis_depth=ad_score, presentation=pres,
    )
    score_path.write_text(json.dumps(sd, indent=2, ensure_ascii=False))
    return {"file": score_path.name, "old_ad": old_ad_score, "new_ad": ad_score, "dt": round(time.time()-t0, 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", help="single score file (default: all *_matrix.score.json)")
    args = ap.parse_args()
    if args.score:
        files = [Path(args.score)]
    else:
        files = sorted(Path(ROOT / "data/results/deep").glob("*_matrix.score.json"))
        files = [f for f in files if ".preFix" not in f.name]
    print(f"rescoring {len(files)} files")
    skipped = 0
    for f in files:
        meta = rescore(f)
        if meta.get("skipped"):
            skipped += 1
            continue
        print(f"  {meta['file']:<60} ad: {meta['old_ad']:.3f} -> {meta['new_ad']:.3f}  ({meta['dt']:.1f}s)", flush=True)
    print(f"DONE (skipped {skipped} with missing .md)")
