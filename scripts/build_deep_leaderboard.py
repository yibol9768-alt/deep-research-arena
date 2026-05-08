#!/usr/bin/env python3
"""Build deep-tier leaderboard from per-run score JSONs.

Reads `data/results/deep/<agent>__<task>_matrix.score.json` produced by
score_deep_answer.py / score_deep_batch.py, computes:

  composite_v1 (additive, legacy):
      0.40·url_coverage + 0.40·checklist + 0.20·spec
  composite_v2_truthful (multiplicative, primary):
      reachability · (0.40·url_coverage + 0.40·checklist + 0.20·spec)

Then computes Bradley-Terry / Arena Elo over composite_v2 and writes:
  - data/results/deep/LEADERBOARD_DEEP.md  — paper-ready
  - data/results/deep/leaderboard_deep.json — machine-readable

Usage: python3 scripts/build_deep_leaderboard.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
# Source dir override — defaults to deep_v3 (full 10-agent corpus the paper
# cites). The legacy deep/ directory only had the 5-agent subset; switching
# to deep_v3 picks up deerflow / ldr / ii-researcher / flowsearcher-ds /
# qx-agents alongside the original five.
DEEP_RESULTS = ROOT / os.environ.get(
    "DEEP_RESULTS_DIR", "data/results/deep_v3"
)
OUT_MD = DEEP_RESULTS / "LEADERBOARD_DEEP.md"
OUT_JSON = DEEP_RESULTS / "leaderboard_deep.json"

from src.scoring.arena import (
    compute_elo,
    compute_elo_with_ci,
    rank_significance_test,
    per_pillar_elo,
    render_elo_table_with_ci,
    render_per_pillar_table,
    Record,
    _battles_for_task,
)


SCORE_RE = re.compile(r"^(.+?)__([a-z0-9_]+_\d+)_(\w+)\.score\.json$")


_DEGENERATE_PREFIXES = ("(empty ", "(runner error", "(error", "(timeout", "(no output", "(qx-agents produced no report")


def _looks_degenerate(d: dict) -> bool:
    """Detect a score whose underlying answer was a runner error placeholder.

    qx_runner / storm_runner / ldr_runner all return a fixed-template
    string when their subprocess fails, and the harness writes it to .md
    verbatim. Including these in Bradley-Terry battles inflates "wins"
    against agents that didn't fail — the agent didn't actually compete.
    """
    if d.get("answer_chars", 1) == 0:
        return True
    # If url_reachability + checklist + analysis_depth are ALL zero AND
    # answer_chars is small, this is a placeholder, not a real failure.
    chars = d.get("answer_chars", 0)
    if chars and chars < 600:
        reach = (d.get("url_reachability") or {}).get("score") or 0
        ck = (d.get("checklist") or {}).get("pass_rate") or 0
        if reach == 0 and ck == 0:
            return True
    return False


def load_scores(suffix: str = "matrix", *, drop_degenerate: bool = True) -> list[dict]:
    """Load every <agent>__<task>_<suffix>.score.json."""
    out = []
    n_dropped = 0
    for p in sorted(DEEP_RESULTS.glob(f"*_{suffix}.score.json")):
        m = SCORE_RE.match(p.name)
        if not m:
            continue
        agent, task, sfx = m.groups()
        if sfx != suffix:
            continue
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            print(f"warn: skip {p.name}: {e}", file=sys.stderr)
            continue
        if drop_degenerate and _looks_degenerate(d):
            n_dropped += 1
            continue
        out.append({
            "agent": agent,
            "task_id": task,
            "score": d,
            "score_path": str(p.relative_to(ROOT)),
        })
    if n_dropped:
        print(f"dropped {n_dropped} runner-placeholder rows (set drop_degenerate=False to include)", file=sys.stderr)
    return out


def _spec_pass_fraction(spec: dict) -> float:
    """Spec pass fraction from the 3 boolean flags `score_deep_answer.py`
    writes — `markdown_spec` does not have a top-level `score` field, so
    earlier code reading `.score` was silently getting 0 for everyone."""
    if not isinstance(spec, dict):
        return 0.0
    flags = [bool(spec.get(k, False)) for k in ("words_ok", "citations_ok", "paragraphs_ok")]
    return sum(flags) / 3.0


def _checklist_pass_rate(ck: dict) -> float:
    """Checklist score lives under `pass_rate`, not `.score`. Be defensive
    against either spelling so old + new score files both work."""
    if not isinstance(ck, dict):
        return 0.0
    val = ck.get("pass_rate")
    if val is None:
        val = ck.get("score")
    return float(val or 0)


def composite_v1(s: dict) -> float:
    """Legacy additive composite (= score_deep_answer.py default 'composite')."""
    if "composite" in s and isinstance(s["composite"], (int, float)):
        return float(s["composite"])
    url = (s.get("url_coverage") or {}).get("score") or 0
    chk = _checklist_pass_rate(s.get("checklist") or {})
    spc = _spec_pass_fraction(s.get("markdown_spec") or {})
    return 0.40 * url + 0.40 * chk + 0.20 * spc


def composite_v2_truthful(s: dict) -> float:
    """Multiplicative composite gated by URL reachability."""
    url = (s.get("url_coverage")     or {}).get("score") or 0
    chk = _checklist_pass_rate(s.get("checklist") or {})
    spc = _spec_pass_fraction(s.get("markdown_spec") or {})
    reach = (s.get("url_reachability") or {}).get("score") or 0
    quality = 0.40 * url + 0.40 * chk + 0.20 * spc
    return float(reach) * float(quality)


def main() -> int:
    rows = load_scores(suffix="matrix")
    if not rows:
        print(f"no *_matrix.score.json under {DEEP_RESULTS}", file=sys.stderr)
        return 1

    print(f"loaded {len(rows)} (agent, task) score files")

    records_v2 = []
    records_v1 = []
    pillar_records = []
    for r in rows:
        s = r["score"]
        c2 = composite_v2_truthful(s)
        c1 = composite_v1(s)
        records_v2.append({"task_id": r["task_id"], "agent": r["agent"], "composite": c2})
        records_v1.append({"task_id": r["task_id"], "agent": r["agent"], "composite": c1})
        pillars = {
            "url_coverage":   (s.get("url_coverage")     or {}).get("score") or 0,
            "reachability":   (s.get("url_reachability") or {}).get("score") or 0,
            "checklist":      _checklist_pass_rate(s.get("checklist") or {}),
            "spec":           _spec_pass_fraction(s.get("markdown_spec") or {}),
            "quote_match":    (s.get("quote_match")      or {}).get("score") or 0,
        }
        pillar_records.append({"task_id": r["task_id"], "agent": r["agent"], "pillars": pillars})

    # Synthesize battles from composite_v2_truthful for Elo
    by_task_v2 = defaultdict(list)
    for r in records_v2:
        by_task_v2[r["task_id"]].append(Record(**r))
    synth_battles_v2 = []
    for task_id, recs in by_task_v2.items():
        for a, b, sa in _battles_for_task(recs, tie_eps=0.005):
            synth_battles_v2.append({"task": task_id, "a1": a, "a2": b,
                                      "agent_winner": a if sa == 1.0 else (b if sa == 0.0 else "tie")})

    # Same for v1
    by_task_v1 = defaultdict(list)
    for r in records_v1:
        by_task_v1[r["task_id"]].append(Record(**r))
    synth_battles_v1 = []
    for task_id, recs in by_task_v1.items():
        for a, b, sa in _battles_for_task(recs, tie_eps=0.005):
            synth_battles_v1.append({"task": task_id, "a1": a, "a2": b,
                                      "agent_winner": a if sa == 1.0 else (b if sa == 0.0 else "tie")})

    elo_v2_ci = compute_elo_with_ci(synth_battles_v2, n_resamples=1000)
    elo_v1_ci = compute_elo_with_ci(synth_battles_v1, n_resamples=1000)
    sig_v2 = rank_significance_test(synth_battles_v2, n_permutations=1000)
    pillar = per_pillar_elo(pillar_records)

    # ---- per-(agent, task) raw composite table (so user can spot reversals) ----
    by_at = {(r["agent"], r["task_id"]): r["composite"] for r in records_v2}
    by_at_v1 = {(r["agent"], r["task_id"]): r["composite"] for r in records_v1}
    agents = sorted({r["agent"] for r in records_v2})
    tasks  = sorted({r["task_id"] for r in records_v2})

    raw_table_v2 = ["| Agent | " + " | ".join(t.replace("dr_cross_deep_", "") for t in tasks) + " | mean |",
                    "|---|" + "---:|" * (len(tasks) + 1)]
    for a in agents:
        cells = []
        vals = []
        for t in tasks:
            v = by_at.get((a, t))
            if v is None:
                cells.append("—")
            else:
                cells.append(f"{v:.3f}")
                vals.append(v)
        mean = sum(vals) / len(vals) if vals else 0
        raw_table_v2.append(f"| {a} | " + " | ".join(cells) + f" | **{mean:.3f}** |")

    raw_table_v1 = ["| Agent | " + " | ".join(t.replace("dr_cross_deep_", "") for t in tasks) + " | mean |",
                    "|---|" + "---:|" * (len(tasks) + 1)]
    for a in agents:
        cells = []; vals = []
        for t in tasks:
            v = by_at_v1.get((a, t))
            if v is None:
                cells.append("—")
            else:
                cells.append(f"{v:.3f}")
                vals.append(v)
        mean = sum(vals) / len(vals) if vals else 0
        raw_table_v1.append(f"| {a} | " + " | ".join(cells) + f" | **{mean:.3f}** |")

    md = [
        f"# Deep-Tier Leaderboard ({len(tasks)} tasks × {len(agents)} OSS DR agents)",
        "",
        f"*Built from {len(rows)} run-score files in `{DEEP_RESULTS.relative_to(ROOT)}/*_matrix.score.json`. Backbone = DeepSeek-V4-flash (thinking off via westd ds_proxy:8088). Sandbox = Magento + Postmill + Kiwix on westd. Score files produced by `score_deep_answer.py`.*",
        "",
        "## Composite_v2_truthful (multiplicative, primary)",
        "",
        "*`composite_v2 = reachability · (0.40·url_coverage + 0.40·judge_pass + 0.20·spec)`. Reachability gate kills any agent with fabricated URLs regardless of fluency. **This is the headline ranking.***",
        "",
        render_elo_table_with_ci(elo_v2_ci),
        "",
        "### Rank significance (permutation, N=1000)",
        "",
        "| Higher | Lower | Gap (Elo) | p-value | Significant? |",
        "|---|---|---:|---:|---|",
    ]
    for pair in sig_v2.get("adjacent_pairs", []):
        md.append(f"| {pair['higher']} | {pair['lower']} | {pair['gap']} | {pair['p_value']} | {'✅' if pair['significant'] else '❌'} |")

    md += [
        "",
        "## Composite_v1 (additive, legacy) — for F6 reversal comparison",
        "",
        "*Same quality formula, **without** reachability gate. Used to demonstrate the F6 finding: ranking inverts under truthfulness gate.*",
        "",
        render_elo_table_with_ci(elo_v1_ci),
        "",
        "## Per-pillar Elo",
        "",
        render_per_pillar_table(pillar),
        "",
        "## Raw composite_v2 by (agent, task)",
        "",
        *raw_table_v2,
        "",
        "## Raw composite_v1 by (agent, task)",
        "",
        *raw_table_v1,
        "",
        "## Inputs",
        "",
        f"- {len(rows)} score files",
        f"- {len(agents)} agents: {', '.join(agents)}",
        f"- {len(tasks)} tasks: {', '.join(tasks)}",
        f"- battles synthesised from composite (tie_eps = 0.005)",
        "",
        "## Caveats",
        "",
        "1. Battles synthesised from composite, not real LLM-judge head-to-head — see `data/results/audit/HUMAN_URL_AUDIT.md` for human-graded URL truthfulness ground truth (separate axis).",
        "2. claim_nli pillar dropped per 2026-04-27 user decision; quote_match pillar retained as deterministic add-on.",
        "3. Tasks 0001/0002/0005 are Recommendation anchors; tasks 0003/0004/0006-0012 are V1 (Comparison/Debunking/Causal/Timeline/Enumeration) — task type may interact with agent-architecture suitability, see paper §5.",
    ]

    OUT_MD.write_text("\n".join(md) + "\n")
    OUT_JSON.write_text(json.dumps({
        "elo_v2_ci": elo_v2_ci,
        "elo_v1_ci": elo_v1_ci,
        "rank_significance_v2": sig_v2,
        "pillar_elo": pillar,
        "n_runs": len(rows),
        "agents": agents,
        "tasks": tasks,
    }, indent=2))
    print(f"WROTE {OUT_MD.relative_to(ROOT)}")
    print(f"WROTE {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
