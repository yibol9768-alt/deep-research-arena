#!/usr/bin/env python3
"""Build the v3 deep-tier leaderboard.

Clone of `scripts/build_deep_leaderboard.py` adapted for the v3 scoring
composite (`composite_v3_softfloor`) introduced by Workstream A on
2026-05-21.

Key differences from the v2 builder:

  * Computes `composite_v3_softfloor` (never zeroes — `reach_soft × Q`).
  * Per-pillar Elo for ALL 8 dimensions (6 quality + reach + quote_match)
    rather than the 5 v2 pillars.
  * Top-level JSON keys for `weights_v3`, `human_alignment` (placeholder
    for Workstream D), and `per_agent_profile` carrying
    `{url_veracity_pct, depth_avg, rigor_avg, style_avg, checklist_pass_rate,
    coverage_pct}` so the frontend leaderboard can render the v3 columns
    without recomputing.
  * **`--dry-run` is the default and the only supported mode in this
    worktree.** We are NOT on the benchmark host (which lives at
    `westd:/opt/deep_reserch`); the verifiers cannot reach the sandbox
    from here. The script generates clearly-labelled synthetic placeholder
    scores so Workstream E (frontend) has a schema to build against.
    Real runs happen later on the bench host with `--dry-run` removed.

Output: `data/results/deep_v3/leaderboard_deep_v3.json`. The v2 file
`leaderboard_deep.json` in the same directory is NOT overwritten.

Usage:
    python3 scripts/build_deep_leaderboard_v3.py            # dry-run (default)
    python3 scripts/build_deep_leaderboard_v3.py --dry-run  # explicit
    python3 scripts/build_deep_leaderboard_v3.py --real     # bench-host only
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.arena import (
    compute_elo_with_ci,
    rank_significance_test,
    per_pillar_elo,
    Record,
    _battles_for_task,
)
from src.scoring.leaderboard_composites import (
    WEIGHTS_V3,
    composite_v2_truthful,
    composite_v3_softfloor,
    composite_v3_breakdown,
)


DEEP_V3_DIR = ROOT / "data" / "results" / "deep_v3"
V2_INPUT = DEEP_V3_DIR / "leaderboard_deep.json"
OUT_JSON = DEEP_V3_DIR / "leaderboard_deep_v3.json"


# Schema version stamped on every dry-run output. Workstream E keys off this
# so it can warn loudly if the production pipeline ever publishes a dry-run
# leaderboard to the live site.
SCHEMA_VERSION = "v3-dryrun-2026-05-21"


# ---------------------------------------------------------------------------
# Mock score generation (dry-run only)
# ---------------------------------------------------------------------------

def _mock_dim_score(rng: random.Random, mean: float, jitter: float = 0.12) -> float:
    """Sample a synthetic dim score in [0, 1] roughly centred on `mean`.

    Used only in --dry-run mode. Real scores come from the verifiers on
    the bench host.
    """
    v = rng.gauss(mean, jitter)
    return max(0.0, min(1.0, v))


def _synthesize_score_for_agent_task(
    rng: random.Random,
    agent: str,
    task_id: str,
    v2_elo_hint: float | None = None,
) -> dict:
    """Synthesize a single per-(agent, task) score dict in the shape that
    composite_v3_softfloor expects. Stronger v2-Elo agents get higher mean
    scores so the dry-run leaderboard is at least *internally plausible*.
    """
    # Map v2 Elo into a 0..1 strength signal. 1100-1400 → 0.5-0.85 mean.
    if v2_elo_hint is None:
        strength = 0.5
    else:
        strength = max(0.2, min(0.9, (v2_elo_hint - 700) / 700.0))

    # Per-dim mean perturbed by agent identity so per-agent profiles differ.
    name_seed = abs(hash(agent)) % 1000 / 1000.0
    profile = {
        "coverage":  strength + 0.05 * (name_seed - 0.5),
        "depth":     strength + 0.05 * ((name_seed * 1.3) % 1.0 - 0.5),
        "rigor":     strength + 0.05 * ((name_seed * 1.7) % 1.0 - 0.5),
        "style":     strength + 0.05 * ((name_seed * 2.1) % 1.0 - 0.5),
        "checklist": strength + 0.05 * ((name_seed * 2.5) % 1.0 - 0.5),
        "spec":      strength + 0.05 * ((name_seed * 2.9) % 1.0 - 0.5),
    }

    score = {
        # Score-shaped fields used by composite_v3 helpers.
        "coverage":   _mock_dim_score(rng, profile["coverage"]),
        "depth":      _mock_dim_score(rng, profile["depth"]),
        "rigor":      _mock_dim_score(rng, profile["rigor"]),
        "style":      _mock_dim_score(rng, profile["style"]),
        "checklist":  _mock_dim_score(rng, profile["checklist"]),
        "spec":       _mock_dim_score(rng, profile["spec"]),
        "quote_match": {"score": _mock_dim_score(rng, strength)},
        "url_reachability": {"score": _mock_dim_score(rng, strength)},
        # Marker so anyone inspecting the JSON immediately sees these are not real measurements.
        "synthetic_placeholder": True,
        "synthetic_origin": "build_deep_leaderboard_v3.py --dry-run",
    }
    return score


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _load_v2_for_hints() -> tuple[dict, list[str], list[str]]:
    """Read the existing v2 leaderboard for agent / task lists and Elo hints.

    Returns (elo_v2_by_agent, agents_sorted, tasks_sorted). Missing file
    falls back to a minimal default so the dry-run still produces output.
    """
    if not V2_INPUT.exists():
        return {}, ["agent_a", "agent_b", "agent_c"], [f"dr_cross_deep_{i:04d}" for i in range(1, 11)]
    raw = json.loads(V2_INPUT.read_text(encoding="utf-8"))
    elo_v2 = raw.get("elo_v2_ci") or {}
    agents = sorted(raw.get("agents") or list(elo_v2.keys()))
    tasks = sorted(raw.get("tasks") or [f"dr_cross_deep_{i:04d}" for i in range(1, 11)])
    return elo_v2, agents, tasks


def _build_dry_run() -> dict:
    """Produce a full v3 leaderboard dict using synthetic placeholder scores.

    The schema mirrors what Workstream E will consume. Every numeric field
    that would come from a real verifier run is marked
    `"synthetic_placeholder": true` on the per-row payload.
    """
    rng = random.Random(20260521)
    elo_v2_by_agent, agents, tasks = _load_v2_for_hints()

    # Synthesize per-(agent, task) score JSONs.
    rows: list[dict] = []
    for agent in agents:
        v2_elo = (elo_v2_by_agent.get(agent) or {}).get("elo")
        for task_id in tasks:
            score = _synthesize_score_for_agent_task(rng, agent, task_id, v2_elo_hint=v2_elo)
            rows.append({
                "agent": agent,
                "task_id": task_id,
                "score": score,
            })

    # Compute composites.
    records_v3: list[dict] = []
    records_v2: list[dict] = []
    pillar_records: list[dict] = []

    for r in rows:
        s = r["score"]
        c3 = composite_v3_softfloor(s)
        c2 = composite_v2_truthful({
            # Map our v3 score-dict back into the v2-expected shape so we can
            # also compute v2 on the same synthetic rows (useful for the
            # Spearman comparison documented in SCORING_V3_DIFF.md).
            "url_coverage":     {"score": s["coverage"]},
            "checklist":        {"pass_rate": s["checklist"]},
            "markdown_spec":    {"words_ok": True, "citations_ok": True, "paragraphs_ok": True} if s["spec"] >= 0.66 else {},
            "url_reachability": s["url_reachability"],
        })
        records_v3.append({"task_id": r["task_id"], "agent": r["agent"], "composite": c3})
        records_v2.append({"task_id": r["task_id"], "agent": r["agent"], "composite": c2})

        pillars = {
            "coverage":      float(s["coverage"]),
            "depth":         float(s["depth"]),
            "rigor":         float(s["rigor"]),
            "style":         float(s["style"]),
            "checklist":     float(s["checklist"]),
            "spec":          float(s["spec"]),
            "reachability":  float(s["url_reachability"]["score"]),
            "quote_match":   float(s["quote_match"]["score"]),
        }
        pillar_records.append({"task_id": r["task_id"], "agent": r["agent"], "pillars": pillars})

    # Synthesise battles from composite_v3 for Elo.
    by_task_v3 = defaultdict(list)
    for rec in records_v3:
        by_task_v3[rec["task_id"]].append(Record(**rec))
    synth_battles_v3 = []
    for task_id, recs in by_task_v3.items():
        for a, b, sa in _battles_for_task(recs, tie_eps=0.005):
            synth_battles_v3.append({
                "task": task_id, "a1": a, "a2": b,
                "agent_winner": a if sa == 1.0 else (b if sa == 0.0 else "tie"),
            })

    elo_v3_ci = compute_elo_with_ci(synth_battles_v3, n_resamples=200)
    sig_v3 = rank_significance_test(synth_battles_v3, n_permutations=200)
    pillar = per_pillar_elo(pillar_records)

    # Per-agent profile (rolled-up dim averages).
    per_agent_profile: dict[str, dict] = {}
    by_agent_rows: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_agent_rows[r["agent"]].append(r)
    for agent, ags in by_agent_rows.items():
        n = len(ags) or 1
        def _avg(key: str) -> float:
            return sum(float(a["score"][key]) for a in ags) / n
        def _avg_dict(key: str) -> float:
            return sum(float((a["score"].get(key) or {}).get("score") or 0) for a in ags) / n
        per_agent_profile[agent] = {
            "coverage_pct":       round(_avg("coverage"), 4),
            "depth_avg":          round(_avg("depth"), 4),
            "rigor_avg":          round(_avg("rigor"), 4),
            "style_avg":          round(_avg("style"), 4),
            "checklist_pass_rate": round(_avg("checklist"), 4),
            "url_veracity_pct":   round(_avg_dict("quote_match"), 4),
            "reachability_pct":   round(_avg_dict("url_reachability"), 4),
            "synthetic_placeholder": True,
        }

    # Spearman v2-vs-v3 (computed on the same synthetic rows so reviewers
    # see *how* to compute it on real data later).
    spearman = _spearman(records_v2, records_v3)

    output = {
        "_schema_version": SCHEMA_VERSION,
        "_dry_run": True,
        "_dry_run_notice": (
            "All scores below are synthetic placeholders generated by "
            "build_deep_leaderboard_v3.py for schema-only consumption by "
            "Workstream E (frontend). Real runs happen on westd/WSL "
            "/opt/deep_reserch with the verifiers wired to the live sandbox."
        ),
        "weights_v3": dict(WEIGHTS_V3),
        "composite_formula": (
            "composite_v3 = (0.5 + 0.5 * quote_match) * "
            "sum(w_d * score_d for d in [coverage, depth, rigor, style, checklist, spec])"
        ),
        "elo_v3_ci": elo_v3_ci,
        "rank_significance_v3": sig_v3,
        "pillar_elo": pillar,
        "per_agent_profile": per_agent_profile,
        "human_alignment": {
            "status": "placeholder",
            "note": (
                "Awaiting Workstream D pairwise human-preference data. Once "
                "scripts/fit_weights_v3.py emits a fitted weight vector, "
                "this key will hold Spearman / Kendall between fitted-v3 and "
                "raw human prefs."
            ),
            "spearman_v2_vs_v3_dry_run": spearman,
            "n_human_judgements": 0,
        },
        "n_runs": len(rows),
        "agents": agents,
        "tasks": tasks,
    }
    return output


def _spearman(records_a: list[dict], records_b: list[dict]) -> float | None:
    """Compute Spearman ρ between two record lists keyed on (agent, task).

    Uses ranks-of-composite, not raw composite, so it's robust to v2 / v3
    being on different scales. Returns None if there are fewer than 3
    overlapping rows (not enough signal).
    """
    by_a = {(r["agent"], r["task_id"]): r["composite"] for r in records_a}
    by_b = {(r["agent"], r["task_id"]): r["composite"] for r in records_b}
    common = sorted(set(by_a) & set(by_b))
    if len(common) < 3:
        return None
    vals_a = [by_a[k] for k in common]
    vals_b = [by_b[k] for k in common]

    def _rank(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        for r_idx, idx in enumerate(order):
            ranks[idx] = float(r_idx + 1)
        return ranks

    ra = _rank(vals_a)
    rb = _rank(vals_b)
    n = len(common)
    d2 = sum((ra[i] - rb[i]) ** 2 for i in range(n))
    return round(1.0 - (6.0 * d2) / (n * (n * n - 1)), 6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Use synthetic placeholder scores (default — required on this host).",
    )
    parser.add_argument(
        "--real",
        dest="dry_run",
        action="store_false",
        help="Run the real verifiers (only valid on the bench host).",
    )
    args = parser.parse_args()

    if not args.dry_run:
        print(
            "ERROR: --real mode is intentionally not implemented in this "
            "worktree. Real verifier runs happen on the bench host "
            "(westd / WSL /opt/deep_reserch). This worktree only owns the "
            "scoring code; the per-run score JSONs come from there.",
            file=sys.stderr,
        )
        return 2

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_dry_run()
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"WROTE {OUT_JSON.relative_to(ROOT)}  (dry-run, {payload['n_runs']} synthetic rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
