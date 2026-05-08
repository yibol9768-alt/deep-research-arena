"""Re-score a single answer file by re-running ONLY the fixed verifiers.

Preserves existing url_coverage / url_reachability / quote_match / markdown_spec
from the existing score.json (those need the sandbox HTTP services on westd).
Re-runs:
  - checklist  (score_deep_answer._judge_checklist, fixed)
  - claim_nli  (ClaimNLIVerifier, fixed)
And recomputes the composite block.

Original score.json is backed up to <name>.preFix.bak (idempotent — does not
overwrite an existing backup).

Usage:
    python3 scripts/rescore_partial.py \
        --score data/results/deep/storm__dr_cross_deep_0001_matrix.score.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from scripts.score_deep_answer import (  # noqa: E402
    _composite, _judge_checklist, _markdown_spec_score,
)
from src.verifiers.claim_nli_verifier import ClaimNLIVerifier  # noqa: E402
from src.verifiers.analysis_depth_verifier import AnalysisDepthVerifier  # noqa: E402
from src.verifiers.presentation_verifier import PresentationVerifier  # noqa: E402

CHECKLIST_DIRS = [
    ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / "checklists_deep.json",
    ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / "checklists.json",
    ROOT / "data" / "tasks" / "deep_research" / "shopping" / "checklists_v3.json",
    ROOT / "data" / "tasks" / "deep_research" / "reddit" / "checklists_v3.json",
]


def _load_checklists() -> dict:
    merged = {}
    for p in CHECKLIST_DIRS:
        try:
            merged.update(json.loads(p.read_text()))
        except Exception:
            continue
    return merged


def rescore(score_path: Path, *, skip_nli: bool = False) -> dict:
    import time
    t0 = time.time()
    sd = json.loads(score_path.read_text())
    answer_path_str = sd.get("answer_path", "")
    answer_path = ROOT / answer_path_str
    if not answer_path.exists():
        # Try as absolute or in same dir
        answer_path = score_path.with_suffix("").with_suffix(".md")
        if not answer_path.exists():
            answer_path = score_path.parent / score_path.name.replace(".score.json", ".md")
    answer = answer_path.read_text(errors="ignore") if answer_path.exists() else ""

    task_id = sd.get("task")
    task_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{task_id}.json"
    task_cfg = json.loads(task_path.read_text())

    reach_score = sd.get("url_reachability", {}).get("score", 0.0)

    # --- Re-run checklist (with reachability cross-check) ---
    cls = _load_checklists()
    items = cls.get(task_id, [])
    print(f"  [checklist] starting (n={len(items)} items, reach={reach_score:.3f})...", flush=True)
    new_checklist = _judge_checklist(items, answer, task_id, reachability=reach_score)
    new_pass_rate = new_checklist.get("pass_rate", 0.0)
    downgr = new_checklist.get("grounding_downgrades", 0)
    print(f"  [checklist] pass_rate={new_pass_rate:.3f}  via={'skip' if new_checklist.get('skipped_judge') else 'judge'}  fab_downgrades={downgr}  dt={time.time()-t0:.1f}s", flush=True)

    # --- Re-run NLI ---
    if skip_nli:
        new_nli = sd.get("claim_nli", {"score": 0.0, "details": {}})
        nli_score = new_nli.get("score", 0.0)
    else:
        t_nli = time.time()
        print(f"  [nli] starting (max_calls=8)...", flush=True)
        try:
            v = ClaimNLIVerifier(theta=0.80, max_calls=8)
            r = v.verify(task_config=task_cfg, answer=answer)
            new_nli = {"score": r.score, "passed": r.passed, "details": r.details}
            nli_score = r.score
        except Exception as e:
            new_nli = {"score": 0.0, "passed": False, "details": {"error": str(e)[:200]}}
            nli_score = 0.0
        print(f"  [nli] score={nli_score:.3f}  evaluated={(new_nli.get('details') or {}).get('claims_evaluated','?')}  dt={time.time()-t_nli:.1f}s", flush=True)

    # --- analysis_depth (LLM-only, runs locally) ---
    t_ad = time.time()
    print(f"  [analysis_depth] starting...", flush=True)
    try:
        v = AnalysisDepthVerifier()
        r = v.verify(task_config=task_cfg, answer=answer)
        new_ad = {"score": r.score, "passed": r.passed, "details": r.details}
        ad_score = r.score
    except Exception as e:
        new_ad = {"score": 0.0, "passed": False, "details": {"error": str(e)[:200]}}
        ad_score = 0.0
    print(f"  [analysis_depth] score={ad_score:.3f}  dt={time.time()-t_ad:.1f}s", flush=True)

    # --- presentation (LLM-only, runs locally) ---
    t_p = time.time()
    print(f"  [presentation] starting...", flush=True)
    try:
        v = PresentationVerifier()
        r = v.verify(task_config=task_cfg, answer=answer)
        new_pres = {"score": r.score, "passed": r.passed, "details": r.details}
        pres_score = r.score
    except Exception as e:
        new_pres = {"score": 0.0, "passed": False, "details": {"error": str(e)[:200]}}
        pres_score = 0.0
    print(f"  [presentation] score={pres_score:.3f}  dt={time.time()-t_p:.1f}s", flush=True)

    # --- Recompute composite ---
    reach = reach_score
    qm = sd.get("quote_match", {}).get("score", 0.0)
    url_cov = sd.get("url_coverage", {}).get("score", 0.0)
    spec = sd.get("markdown_spec") or _markdown_spec_score(answer, {})
    # citation_alignment requires HTTP probe of localhost sandbox — only
    # works on westd. Preserve any prior value here; otherwise 0.0.
    cit_align = (sd.get("citation_alignment") or {}).get("score", 0.0) if isinstance(sd.get("citation_alignment"), dict) else 0.0

    new_composite = _composite(
        reachability=reach,
        quote_match=qm,
        claim_nli=nli_score,
        url_cov=url_cov,
        checklist_pass_rate=new_pass_rate,
        spec=spec,
        citation_alignment=cit_align,
        analysis_depth=ad_score,
        presentation=pres_score,
    )

    # Preserve fields, replace the relevant blocks
    sd_new = dict(sd)
    sd_new["checklist"] = new_checklist
    sd_new["claim_nli"] = new_nli
    sd_new["analysis_depth"] = new_ad
    sd_new["presentation"] = new_pres
    sd_new["composite"] = new_composite
    sd_new["rescore_meta"] = {
        "fix": "v2_full_rescore_with_ad_pres_and_fab_guard",
        "old_checklist_pass_rate": sd.get("checklist", {}).get("pass_rate"),
        "old_claim_nli_score": (sd.get("claim_nli") or {}).get("score"),
        "old_composite_v3": (sd.get("composite") or {}).get("composite_v3"),
        "old_composite_v2": (sd.get("composite") or {}).get("composite_score"),
        "new_checklist_pass_rate": new_pass_rate,
        "new_claim_nli_score": nli_score,
        "new_analysis_depth": ad_score,
        "new_presentation": pres_score,
        "new_composite_v3": new_composite["composite_v3"],
        "new_composite_v2": new_composite["composite_score"],
    }

    # Backup once
    bak = score_path.with_suffix(".preFix.bak")
    if not bak.exists():
        shutil.copy2(score_path, bak)
    score_path.write_text(json.dumps(sd_new, indent=2, ensure_ascii=False))
    return sd_new["rescore_meta"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", required=True, help="path to a *.score.json")
    ap.add_argument("--skip-nli", action="store_true", help="skip NLI re-run (faster smoke)")
    args = ap.parse_args()
    meta = rescore(Path(args.score), skip_nli=args.skip_nli)
    print(json.dumps(meta, indent=2))
