#!/usr/bin/env python3
"""Re-score existing runs with an added `evidence_density` pillar.

Reads:
  - data/results/final_<agent>_<task>.json     (existing composite+pillars)
  - data/results/final_<agent>_<task>.answer.md (agent output markdown)

Writes:
  - data/results/final_<agent>_<task>.ed.json  (same schema + evidence_density
                                                 pillar + recomputed composite)
  - data/results/arena_elo_ED.json             (new leaderboard raw)
  - data/results/LEADERBOARD_v3_ED.md          (new side-by-side leaderboard)

New weight scheme (from SCORING_REVIEW_2026-04-17.md §4):
    markdown_structure 0.05  (was 0.10 — demoted, too easy to pass)
    citation           0.15
    fact_kg            0.25  (was 0.30 — softened, oracle needs cleaning)
    llm_judge          0.20
    checklist          0.20
    evidence_density   0.10  (NEW)
    efficiency         0.05
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.compute_evidence_density import (
    count_unique_pdp_urls,
    count_unique_reddit_posts,
    meta_word_ratio,
    evidence_density_score,
)

RESULTS = ROOT / "data" / "results"

NEW_WEIGHTS = {
    # v3.1 weights aligned with DeepResearch Bench (ICLR 2026) FACT-style
    # methodology. Auto-scraped category-top-N oracle → diagnosed
    # anti-pattern by the 2025-2026 literature (DRBench, DRACO,
    # ResearchRubrics all moved off it). So we cut fact_kg recall weight
    # and lean on `citation` (ALCE-style URL-supports-claim) + the new
    # `evidence_density` pillar (= DeepResearch Bench's "Effective
    # Primary-Source Citations").
    "markdown_structure": 0.05,
    "citation":           0.20,   # ALCE F1 of cited URLs supporting claims
    "fact_kg":            0.15,   # Oracle v2 (filtered) now in use → restored
    "llm_judge":          0.20,   # DR Bench RACE 4-dim
    "checklist":          0.20,   # DRACO-style rubric
    "evidence_density":   0.15,   # = Effective Primary-Source Citations
    "efficiency":         0.05,
}

# Per-task "required evidence" thresholds (for normalising ED components).
# Tuned loosely; tasks with deeper breadth get a higher denominator.
TASK_REQUIREMENTS: dict[str, tuple[int, int]] = {
    "dr_cross_v3_0001": (6, 4),
    "dr_cross_v3_0005": (8, 4),
    "dr_cross_v3_0006": (7, 4),
    "dr_cross_v3_0007": (6, 4),
}
DEFAULT_REQ = (6, 4)


def rescore_one(final_json: Path) -> dict | None:
    answer_md = final_json.with_name(final_json.stem + ".answer.md")
    if not answer_md.exists():
        return None
    try:
        data = json.loads(final_json.read_text())
    except Exception:
        return None
    text = answer_md.read_text(encoding="utf-8", errors="ignore")
    task_id = data.get("task_id", "")

    pdps = count_unique_pdp_urls(text)
    posts = count_unique_reddit_posts(text)
    ratio, meta_w, total_w = meta_word_ratio(text)
    req_pdp, req_posts = TASK_REQUIREMENTS.get(task_id, DEFAULT_REQ)
    ed_score = evidence_density_score(pdps, posts, ratio,
                                       req_products=req_pdp,
                                       req_posts=req_posts)

    pillars = dict(data.get("pillars", {}))
    pillars["evidence_density"] = {
        "score": ed_score,
        "passed": ed_score >= 0.5,
        "details": {
            "unique_pdp_urls": pdps,
            "unique_reddit_posts": posts,
            "meta_word_ratio": round(ratio, 3),
            "meta_words": meta_w,
            "substance_words": int(total_w * (1 - ratio)),
            "total_words": total_w,
            "required_pdp": req_pdp,
            "required_posts": req_posts,
        },
    }

    new_composite = 0.0
    for name, w in NEW_WEIGHTS.items():
        p = pillars.get(name, {})
        score = p.get("score", 0) if isinstance(p, dict) else 0
        new_composite += w * float(score or 0)
    new_composite = round(new_composite, 3)

    data["pillars"] = pillars
    data["weights"] = NEW_WEIGHTS
    data["composite_old"] = data.get("composite")
    data["composite"] = new_composite

    out_path = final_json.with_suffix("")
    out_path = out_path.parent / (out_path.name + ".ed.json")
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def main() -> None:
    final_jsons = sorted(p for p in RESULTS.glob("final_*.json")
                         if not p.name.endswith(".ed.json"))
    print(f"Re-scoring {len(final_jsons)} runs with evidence_density pillar...")
    results = []
    print(f"{'agent':<22} {'task':<22} {'old':>6} {'new':>6} {'Δ':>7} "
          f"{'ED':>5} {'pdp':>4} {'red':>4}")
    for fj in final_jsons:
        d = rescore_one(fj)
        if not d:
            continue
        results.append(d)
        ed = d["pillars"]["evidence_density"]
        det = ed["details"]
        old = d.get("composite_old") or 0
        new = d["composite"]
        print(
            f"{d['agent']:<22} {d['task_id']:<22} "
            f"{old:>6.2f} {new:>6.2f} {new - old:>+7.2f} "
            f"{ed['score']:>5.2f} {det['unique_pdp_urls']:>4} "
            f"{det['unique_reddit_posts']:>4}"
        )

    # Per-agent aggregate
    from collections import defaultdict
    import statistics
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_agent[r["agent"]].append(r)
    print("\nPer-agent mean composite (old → new):")
    for a, lst in by_agent.items():
        old_mean = statistics.mean(r.get("composite_old") or 0 for r in lst)
        new_mean = statistics.mean(r["composite"] for r in lst)
        ed_mean = statistics.mean(r["pillars"]["evidence_density"]["score"] for r in lst)
        print(f"  {a:<22}  old={old_mean:.3f}   new={new_mean:.3f}   "
              f"Δ={new_mean - old_mean:+.3f}   mean_ED={ed_mean:.3f}")

    # Render new leaderboard using *.ed.json files
    # Use the existing renderer with a temporary swap — easier: inline
    from src.scoring.arena import (
        compute_elo, render_elo_table, compute_elo_from_battles,
        compute_elo_per_judge, per_pillar_elo, render_per_pillar_table,
    )
    comp_records = [{"task_id": r["task_id"], "agent": r["agent"],
                     "composite": float(r["composite"])} for r in results]
    comp_elo_new = compute_elo(comp_records, tie_eps=0.005)

    pillar_runs = [
        {"task_id": r["task_id"], "agent": r["agent"],
         "pillars": {k: v.get("score", 0) for k, v in r["pillars"].items()}}
        for r in results
    ]
    pillar_elo = per_pillar_elo(pillar_runs)

    # Real pairwise battles (same as before; judges haven't changed)
    battles = []
    for p in sorted(RESULTS.glob("pairwise_*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        bl = d.get("battles") if isinstance(d, dict) else d
        if isinstance(bl, list):
            for b in bl:
                if isinstance(b, dict):
                    b.setdefault("judge_model", d.get("judge_model") or p.stem)
                    battles.append(b)
    judge_elo = compute_elo_from_battles(battles) if battles else {}
    judge_per = compute_elo_per_judge(battles) if battles else {}

    md = [
        "# Deep Research Arena — v3.1 Leaderboard",
        "",
        f"*{len(results)} runs, {len(battles)} battles.  Composite v3.1 "
        "aligned with DeepResearch Bench (ICLR 2026) FACT methodology "
        "— `fact_kg` recall (auto-scraped category top-N oracle) demoted "
        "from 0.30 → 0.05, `citation` (ALCE-style URL-supports-claim) "
        "0.15 → 0.25, `evidence_density` (Effective Primary-Source "
        "Citations) 0.00 → 0.20.*",
        "",
        "**Known caveat**: golden triples for tasks 0005/0006/0007 contain "
        "category top-N items that violate task intent (e.g. a $607 printer "
        "in a $500 budget task). `fact_kg` pillar therefore carries minimal "
        "weight until oracle is rebuilt.",
        "",
        "## Weights (v3.1)",
        "",
        "| Pillar | Weight | Rationale |",
        "|---|---:|---|",
        "| markdown_structure | 0.05 | Words/paras/citations threshold (trivially met) |",
        "| citation | 0.25 | ALCE F1 — URL supports claim |",
        "| fact_kg | 0.05 | Demoted (oracle quality bug) |",
        "| llm_judge | 0.20 | RACE 4-dim (Comp/Depth/IF/Readability) |",
        "| checklist | 0.20 | DRACO-style per-task rubric |",
        "| evidence_density | 0.20 | Effective Primary-Source Citations (new) |",
        "| efficiency | 0.05 | Tokens/time/cost |",
        "",
        "## Headline — Composite-Elo v3.1",
        "",
        render_elo_table(comp_elo_new),
        "",
        "## Composite-Elo v3.1 vs Judge-Elo",
        "",
        "| Agent | Composite-Elo (v3.1) | Judge-Elo | Δ (Judge − Comp) |",
        "|---|---:|---:|---:|",
    ]
    all_agents = sorted(set(comp_elo_new) | set(judge_elo))
    rows = []
    for a in all_agents:
        ce = comp_elo_new.get(a, {}).get("elo")
        je = judge_elo.get(a, {}).get("elo")
        delta = je - ce if (ce is not None and je is not None) else None
        rows.append((a, ce, je, delta))
    rows.sort(key=lambda r: -(max((r[1] or 0), (r[2] or 0))))
    for a, ce, je, d in rows:
        ce_s = f"{ce:.1f}" if ce is not None else "—"
        je_s = f"{je:.1f}" if je is not None else "—"
        d_s = f"{d:+.1f}" if d is not None else "—"
        md.append(f"| {a} | {ce_s} | {je_s} | {d_s} |")

    md += [
        "",
        "## Per-pillar Elo (now includes `evidence_density`)",
        "",
        render_per_pillar_table(pillar_elo),
        "",
    ]

    out_md = RESULTS / "LEADERBOARD_v3_ED.md"
    out_md.write_text("\n".join(md))
    out_json = RESULTS / "arena_elo_ED.json"
    out_json.write_text(json.dumps({
        "composite_elo_new": comp_elo_new,
        "judge_elo_all": judge_elo,
        "judge_elo_per": judge_per,
        "pillar_elo": pillar_elo,
        "weights_new": NEW_WEIGHTS,
    }, indent=2, ensure_ascii=False))
    print(f"\nWrote {out_md}")
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()
