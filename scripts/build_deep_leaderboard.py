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
# Runner-failure placeholder pattern: e.g.
#   "(DeerFlow produced no report after 1256s, exit=1)"
#   "(STORM produced no report after 600s, exit=137)"
# These mean the agent crashed; any markdown that follows is stdout-tail
# noise, not a real research report. Without this filter, the scorer happily
# extracts URLs and checklist passes from the stdout dump, producing a
# composite_v2 ~0.02-0.05 that pollutes Elo with phantom failures.
_RUNNER_FAILURE_PREFIX_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s\s*,\s*exit\s*=\s*\d+\s*\)",
    re.IGNORECASE,
)
# A second class of runner-error placeholder produced by qx-agents (and
# friends) when the framework itself raises a Python exception mid-run.
# Examples:
#   "(qx-agents error: ValidationError: 2 validation errors for KnowledgeGapOutput..."
#   "(qx-agents error: IndexError: list index out of range)"
#   "(qx stderr: Traceback (most recent call last):..."
# Some of these escape the chars<600 filter because they include a long
# Python traceback. Drop them.
_RUNNER_EXCEPTION_PREFIX_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+(error|stderr)\s*:",
    re.IGNORECASE,
)


def _looks_degenerate(d: dict) -> bool:
    """Detect a score whose underlying answer/scoring was unusable.

    Four patterns excluded from leaderboard battles:
      1. Runner-error placeholder text (qx_runner / storm_runner /
         ldr_runner produce identical short strings on failure).
      2. Sandbox infrastructure failure during scoring (every probe
         returned 5xx or network error — agent didn't fabricate, our
         sandbox was down).
      3. Judge total-failure: checklist + analysis_depth + presentation
         all errored (so the LLM-judged components have no signal).
      4. Runner-failure placeholder followed by stdout tail (e.g.
         ``(DeerFlow produced no report after 1256s, exit=1)``). These
         pass the chars-threshold filter because the stdout tail is long,
         but the agent crashed and the report content is meaningless.
    Including any of these in Bradley-Terry battles distorts ratings.
    """
    if d.get("answer_chars", 1) == 0:
        return True
    chars = d.get("answer_chars", 0)
    if chars and chars < 600:
        reach = (d.get("url_reachability") or {}).get("score") or 0
        ck = (d.get("checklist") or {}).get("pass_rate") or 0
        if reach == 0 and ck == 0:
            return True
    if (d.get("url_reachability") or {}).get("details", {}).get("infra_failure"):
        return True
    ck_err = (d.get("checklist") or {}).get("judge_error")
    ad_err = ((d.get("analysis_depth") or {}).get("details") or {}).get("judge_error")
    pres_err = ((d.get("presentation") or {}).get("details") or {}).get("judge_error")
    if ck_err and ad_err and pres_err:
        return True
    # Runner-failure placeholder check: read the answer.md head and look for
    # ``(<Agent> produced no report after Ns, exit=N)`` as the leading line.
    ans_path = d.get("answer_path")
    if isinstance(ans_path, str):
        a = Path(ans_path)
        if not a.is_absolute():
            a = ROOT / a
        if a.exists():
            try:
                head = a.read_text(encoding="utf-8", errors="replace")[:300]
                head_stripped = head.lstrip()
                if _RUNNER_FAILURE_PREFIX_RE.match(head_stripped):
                    return True
                if _RUNNER_EXCEPTION_PREFIX_RE.match(head_stripped):
                    return True
            except Exception:
                pass
    return False


def load_scores(
    suffix: str = "matrix",
    *,
    drop_degenerate: bool = True,
    return_drop_stats: bool = False,
):
    """Load every <agent>__<task>_<suffix>.score.json.

    Pass ``return_drop_stats=True`` to also receive per-agent drop counts so
    callers can show *why* an agent has no Elo entry (silent exclusion is the
    most common way Bradley-Terry rankings end up wrong — an agent with all
    runs marked degenerate disappears from the leaderboard with no audit trail).
    """
    out: list[dict] = []
    n_dropped = 0
    drop_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"degenerate": 0, "load_error": 0, "kept": 0, "total": 0})
    for p in sorted(DEEP_RESULTS.glob(f"*_{suffix}.score.json")):
        m = SCORE_RE.match(p.name)
        if not m:
            continue
        agent, task, sfx = m.groups()
        if sfx != suffix:
            continue
        drop_stats[agent]["total"] += 1
        try:
            # encoding='utf-8' is REQUIRED — Path.read_text() defaults to the OS
            # locale (cp1252 on en-US Windows, cp936 on zh-CN Windows). Several
            # score JSONs contain non-ASCII characters (Chinese task intents,
            # quoted spans) and would silently fail under the OS default,
            # dropping perfectly valid rows from the Elo computation. This bug
            # would make the leaderboard read agent X but not agent Y on
            # Windows but agree with Linux runs — exactly the kind of "Elo wrong
            # because of our fault" failure we want to prevent.
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"warn: skip {p.name}: {e}", file=sys.stderr)
            drop_stats[agent]["load_error"] += 1
            continue
        if drop_degenerate and _looks_degenerate(d):
            n_dropped += 1
            drop_stats[agent]["degenerate"] += 1
            continue
        drop_stats[agent]["kept"] += 1
        out.append({
            "agent": agent,
            "task_id": task,
            "score": d,
            "score_path": str(p.relative_to(ROOT)),
        })
    if n_dropped:
        print(f"dropped {n_dropped} runner-placeholder rows (set drop_degenerate=False to include)", file=sys.stderr)
    if return_drop_stats:
        return out, dict(drop_stats)
    return out


# Composite formulas live in src/scoring/leaderboard_composites.py so
# every analysis script (this leaderboard, scoring_ablation, review_analyses)
# scores against the same definition. Three different "v2"s used to coexist
# and silently disagree by ~10-30% on the same agent/task.
from src.scoring.leaderboard_composites import (
    composite_v1, composite_v2_truthful,
    spec_pass_fraction as _spec_pass_fraction,
    checklist_pass_rate as _checklist_pass_rate,
)


def main() -> int:
    rows, drop_stats = load_scores(suffix="matrix", return_drop_stats=True)
    if not rows:
        print(f"no *_matrix.score.json under {DEEP_RESULTS}", file=sys.stderr)
        return 1

    print(f"loaded {len(rows)} (agent, task) score files")

    # Surface agents that produced score files but ended up with zero kept rows
    # — these are silently excluded from Elo today. Common cause: a runner that
    # always emits a short "(<agent> produced no report)" placeholder, scored,
    # then dropped by `_looks_degenerate`. Without this report you see "9 OSS
    # DR agents" in the leaderboard with no clue that a 10th had every run
    # filtered out.
    excluded = {a: s for a, s in drop_stats.items() if s["kept"] == 0 and s["total"] > 0}
    partial = {a: s for a, s in drop_stats.items() if 0 < s["kept"] < s["total"]}

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

    if excluded or partial:
        md += [
            "",
            "## Excluded / partially-dropped agents (audit trail)",
            "",
            "*Agents whose score files were filtered by `_looks_degenerate` (short placeholders, infra failures, etc.). Excluded agents do **not** appear in the Elo table above; without this section they would vanish silently and a reader would assume the framework was never benchmarked.*",
            "",
            "| Agent | Files on disk | Kept | Dropped (degenerate) | Load errors | Status |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for a in sorted(excluded.keys()):
            s = excluded[a]
            md.append(f"| {a} | {s['total']} | {s['kept']} | {s['degenerate']} | {s['load_error']} | ❌ excluded — every run filtered out |")
        for a in sorted(partial.keys()):
            s = partial[a]
            md.append(f"| {a} | {s['total']} | {s['kept']} | {s['degenerate']} | {s['load_error']} | ⚠️ partial — some runs dropped |")

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

    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps({
        "elo_v2_ci": elo_v2_ci,
        "elo_v1_ci": elo_v1_ci,
        "rank_significance_v2": sig_v2,
        "pillar_elo": pillar,
        "n_runs": len(rows),
        "agents": agents,
        "tasks": tasks,
        "drop_stats": drop_stats,
        "excluded_agents": sorted(excluded.keys()),
    }, indent=2), encoding="utf-8")
    print(f"WROTE {OUT_MD.relative_to(ROOT)}")
    print(f"WROTE {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
