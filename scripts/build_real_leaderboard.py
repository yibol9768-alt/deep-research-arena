#!/usr/bin/env python3
"""Build a REAL, non-synthetic deep-research leaderboard.

This replaces the synthetic placeholder produced by
``build_deep_leaderboard_v3.py --dry-run`` (which fabricated scores via
``_synthesize_score_for_agent_task`` and pinned claude-code/opencode to the
top). NOTHING here is synthesized: if an agent has no real report files it is
SKIPPED and logged, never invented.

Two orthogonal numbers per the redesign (docs/SCORING_REDESIGN.md), plus a gate:

  GROUNDING (deterministic, from stored pillars / simple_score)
    Per (agent, task) we read the real ``*.score.json`` and compute a grounding
    number. We prefer ``src.scoring.simple_score.grounding_score`` if it is
    importable at runtime; otherwise we fall back to
    ``0.5 * must_cite_recall + 0.5 * quote_match.score``. Reachable-but-non-
    golden citation VOLUME never helps: domain_balance, pool_coverage, and the
    cited>=N count gate are deliberately ignored.

  QUALITY (pairwise LLM judge, length-controlled)
    Per task we run ``pairwise_judge.battle(dimension=None)`` between agents'
    real reports (round-robin, or vs a fixed --reference agent), using the lite
    model (deepseek-v4-flash) with position-swap (battle already swaps). LENGTH
    CONTROL: both reports are truncated to the same word budget before judging
    so a longer report cannot win on length alone; per-report word counts are
    also recorded. All battle outcomes feed a Bradley-Terry rating
    (src.scoring.bradley_terry) with bootstrap CI.

  GATE
    Agents whose mean grounding is below --grounding-floor are flagged
    ``gated: True`` (truth-gate). Both ranked views are still emitted.

Output JSON marks ``synthetic_placeholder: false`` and ``source: "real"``.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

# Make ``src`` importable when run as a script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_REPORT_DIR = _REPO_ROOT / "data" / "results" / "deep"
DEFAULT_SCORE_DIR = _REPO_ROOT / "data" / "results" / "deep_v3"
DEFAULT_OUT = _REPO_ROOT / "data" / "results" / "real" / "leaderboard_real.json"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_GROUNDING_FLOOR = 0.30
DEFAULT_WORD_BUDGET = 1500

# Only matrix reports are scored (smoke runs are warm-up). Pattern:
#   <agent>__<task_id>_matrix.md
_MATRIX_RE = re.compile(r"^(?P<agent>.+?)__(?P<task>.+?)_matrix\.md$")


# --------------------------------------------------------------------------- #
# Discovery: build the (agent, task) work list from REAL files only.
# --------------------------------------------------------------------------- #
def discover_reports(report_dir: Path) -> dict[str, dict[str, Path]]:
    """Return {agent: {task_id: md_path}} for every real matrix report on disk.

    Never fabricates entries. Agents/tasks with no file simply do not appear.
    """
    out: dict[str, dict[str, Path]] = defaultdict(dict)
    for p in sorted(Path(report_dir).glob("*_matrix.md")):
        m = _MATRIX_RE.match(p.name)
        if not m:
            continue
        out[m.group("agent")][m.group("task")] = p
    return {a: dict(t) for a, t in out.items()}


def score_path_for(score_dir: Path, agent: str, task: str) -> Path:
    return Path(score_dir) / f"{agent}__{task}_matrix.score.json"


# --------------------------------------------------------------------------- #
# GROUNDING (deterministic).
# --------------------------------------------------------------------------- #
def _load_simple_score():
    """Import grounding_score from the sibling module if available (runtime)."""
    try:
        from src.scoring.simple_score import grounding_score  # type: ignore
        return grounding_score
    except Exception:
        return None


def _simple_score_from_json(fn, score_json: dict) -> float | None:
    """Try to drive ``simple_score.grounding_score`` from a stored score JSON.

    The sibling module's signature is not fixed across versions, so we attempt
    a couple of shapes and return None if none apply (caller then falls back).
    First try the simple ``fn(score_json)`` shape; if that raises, give up and
    let the deterministic fallback handle it. We do NOT synthesize cited pairs
    from the stored JSON, because the stored JSON does not retain per-claim
    (url, claim) support tuples; fabricating them would be exactly the kind of
    invented signal this redesign forbids.
    """
    try:
        val = fn(score_json)
    except Exception:
        return None
    # grounding_score may return a dict {"grounding": x, ...} or a float.
    if isinstance(val, dict):
        for k in ("grounding", "score", "grounding_score"):
            if k in val:
                return float(val[k])
        return None
    if val is None:
        return None
    return float(val)


def _fallback_grounding(score_json: dict) -> float:
    """0.5*must_cite_recall + 0.5*quote_match.score from stored pillars.

    Citation VOLUME (domain_balance / pool_coverage / cited counts) is ignored
    on purpose so flooding non-golden citations cannot inflate grounding.
    """
    cov = (score_json.get("url_coverage") or {}).get("details") or {}
    recall = float(cov.get("must_cite_recall") or 0.0)
    qm = float((score_json.get("quote_match") or {}).get("score") or 0.0)
    return 0.5 * recall + 0.5 * qm


def grounding_for(score_json: dict) -> tuple[float, str]:
    """Return (grounding in [0,1], source tag)."""
    fn = _load_simple_score()
    if fn is not None:
        val = _simple_score_from_json(fn, score_json)
        if val is not None:
            return max(0.0, min(1.0, val)), "simple_score"
    return max(0.0, min(1.0, _fallback_grounding(score_json))), "fallback_recall_quote"


def load_score_json(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def read_report_text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Invalid-capture detection (BUG C).
#
# Some runs do not produce a real report: STORM may write "(empty storm
# output)", a runner may crash and emit "(runner error: ...)", or the captured
# stdout is a Python traceback / a near-empty stub. Previously these were
# scored as a real (low) number ~19 and polluted the leaderboard as if the
# agent had genuinely written a weak report. They are CAPTURE FAILURES, not
# weak reports, so we exclude them into a separate `invalid_runs` bucket
# (distinct from `gated`): neither ranked nor counted as a real low score.
# --------------------------------------------------------------------------- #
MIN_REPORT_WORDS = 50

_INVALID_PREFIXES = (
    "(empty",          # "(empty storm output)"
    "(runner error",   # "(runner error: ...)"
    "(no article",     # "(no article produced)"
)
# Error markers various runners emit in lieu of a report.
_INVALID_SUBSTRINGS = (
    "(gpt-researcher produced empty output)",
    "(gpt-researcher error:",
    "(gpt-researcher produced no report",
    "(gpt-researcher timeout",
    "(gpt-researcher: missing venv",
    "(gpt-researcher: strict-sandbox refused",
    "(storm error:",
    "(empty storm output)",
)
_TRACEBACK_MARKER = "Traceback (most recent call last):"


def detect_invalid_report(text: str) -> str | None:
    """Return a reason string if ``text`` is an invalid capture, else None.

    Detects: empty/whitespace, ``(empty ...`` / ``(runner error ...`` /
    ``(no article ...`` stubs, embedded Python tracebacks, known per-runner
    error markers, and reports below ``MIN_REPORT_WORDS`` words.
    """
    s = (text or "").strip()
    if not s:
        return "empty_report"
    low = s.lower()
    for pref in _INVALID_PREFIXES:
        if low.startswith(pref):
            return f"capture_stub:{s[:60]}"
    for sub in _INVALID_SUBSTRINGS:
        if sub.lower() in low:
            return f"runner_error:{sub.strip('(').rstrip(':')}"
    if _TRACEBACK_MARKER in s:
        return "python_traceback"
    if word_count(s) < MIN_REPORT_WORDS:
        return f"too_short:{word_count(s)}_words"
    return None


# --------------------------------------------------------------------------- #
# QUALITY (pairwise) length control.
# --------------------------------------------------------------------------- #
def truncate_words(text: str, budget: int) -> str:
    """Truncate to the first ``budget`` whitespace-delimited words."""
    if budget is None or budget <= 0:
        return text
    words = text.split()
    if len(words) <= budget:
        return text
    return " ".join(words[:budget])


def word_count(text: str) -> int:
    return len(text.split())


# --------------------------------------------------------------------------- #
# Battle plan.
# --------------------------------------------------------------------------- #
def build_battle_plan(
    reports: dict[str, dict[str, Path]],
    agents: list[str],
    tasks: list[str],
    reference: str | None,
) -> list[dict[str, str]]:
    """List of {task, agent_a, agent_b} for agents that have a report on task.

    Round-robin by default; if ``reference`` is given, every other agent on a
    task battles only the reference (Arena-Hard style fixed baseline).
    """
    plan: list[dict[str, str]] = []
    for task in tasks:
        present = [a for a in agents if task in reports.get(a, {})]
        if reference:
            if reference not in present:
                continue
            for a in present:
                if a == reference:
                    continue
                plan.append({"task": task, "agent_a": a, "agent_b": reference})
        else:
            for a, b in combinations(present, 2):
                plan.append({"task": task, "agent_a": a, "agent_b": b})
    return plan


# --------------------------------------------------------------------------- #
# Main build.
# --------------------------------------------------------------------------- #
def build(
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    score_dir: Path = DEFAULT_SCORE_DIR,
    limit_tasks: int | None = None,
    limit_agents: int | None = None,
    agents_filter: list[str] | None = None,
    reference: str | None = None,
    grounding_floor: float = DEFAULT_GROUNDING_FLOOR,
    word_budget: int = DEFAULT_WORD_BUDGET,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    n_samples: int = 3,
    bootstrap: bool = True,
) -> dict[str, Any]:
    reports = discover_reports(report_dir)

    skipped: list[dict[str, str]] = []

    # ----- BUG C: drop invalid-capture (agent, task) reports -------------- #
    # A run whose report is "(empty storm output)", "(runner error: ...)", a
    # traceback, or a degenerate near-empty stub is a CAPTURE FAILURE, not a
    # weak report. We remove it from `reports` so it is never grounded,
    # battled, ranked, or counted as a real low score, and record it under
    # `invalid_runs` with the reason.
    invalid_runs: list[dict[str, str]] = []
    for a in list(reports.keys()):
        for task in list(reports[a].keys()):
            reason = detect_invalid_report(read_report_text(reports[a][task]))
            if reason is not None:
                invalid_runs.append({"agent": a, "task": task, "reason": reason})
                del reports[a][task]
        if not reports[a]:
            del reports[a]

    # Determine candidate agents.
    if agents_filter:
        candidates = list(agents_filter)
    else:
        candidates = sorted(reports.keys())

    included_agents: list[str] = []
    for a in candidates:
        if reports.get(a):
            included_agents.append(a)
        else:
            # NEVER fabricate: an agent with no real report files is skipped.
            skipped.append({"agent": a, "reason": "no real report files on disk"})

    included_agents = sorted(included_agents)
    if limit_agents is not None:
        dropped = included_agents[limit_agents:]
        included_agents = included_agents[:limit_agents]
        for a in dropped:
            skipped.append({"agent": a, "reason": "dropped by --limit-agents"})

    # Determine tasks (union across included agents).
    all_tasks = sorted({t for a in included_agents for t in reports.get(a, {})})
    if limit_tasks is not None:
        all_tasks = all_tasks[:limit_tasks]

    if reference and reference not in included_agents:
        # A reference with no reports cannot be used; fall back to round-robin.
        skipped.append({"agent": reference, "reason": "reference has no reports; round-robin used"})
        reference = None

    # ----- GROUNDING (deterministic) ----------------------------------- #
    grounding_vals: dict[str, list[float]] = defaultdict(list)
    grounding_missing: list[dict[str, str]] = []
    per_agent_tasks: dict[str, set] = defaultdict(set)
    grounding_sources: set[str] = set()
    for a in included_agents:
        for task in all_tasks:
            if task not in reports.get(a, {}):
                continue
            per_agent_tasks[a].add(task)
            sj = load_score_json(score_path_for(score_dir, a, task))
            if sj is None:
                grounding_missing.append({"agent": a, "task": task})
                continue
            val, src = grounding_for(sj)
            grounding_vals[a].append(val)
            grounding_sources.add(src)

    grounding_mean = {
        a: (sum(v) / len(v) if v else 0.0) for a, v in
        ((a, grounding_vals.get(a, [])) for a in included_agents)
    }

    # ----- Battle plan ------------------------------------------------- #
    plan = build_battle_plan(reports, included_agents, all_tasks, reference)

    summary = {
        "agents_included": included_agents,
        "agents_skipped": skipped,
        "n_tasks": len(all_tasks),
        "n_battles_planned": len(plan),
        "reference": reference or "(round-robin)",
        "word_budget": word_budget,
        "grounding_floor": grounding_floor,
        "model": model,
        "grounding_score_source": (
            "+".join(sorted(grounding_sources)) if grounding_sources else "n/a"
        ),
        "n_invalid_runs": len(invalid_runs),
    }

    if dry_run:
        return {
            "synthetic_placeholder": False,
            "source": "real",
            "mode": "dry-run",
            "summary": summary,
            "battle_plan": plan,
            "grounding_mean": {a: round(grounding_mean[a], 4) for a in included_agents},
            "invalid_runs": invalid_runs,
        }

    # ----- QUALITY (pairwise, length-controlled) ---------------------- #
    from src.scoring.pairwise_judge import battle as _battle
    from src.scoring import bradley_terry as bt

    # Cache truncated report text per (agent, task).
    text_cache: dict[tuple[str, str], str] = {}
    raw_words: dict[tuple[str, str], int] = {}

    def _report(agent: str, task: str) -> str:
        key = (agent, task)
        if key not in text_cache:
            full = read_report_text(reports[agent][task])
            raw_words[key] = word_count(full)
            text_cache[key] = truncate_words(full, word_budget)
        return text_cache[key]

    battles: list[dict] = []
    battle_log: list[dict] = []
    for item in plan:
        task, a, b = item["task"], item["agent_a"], item["agent_b"]
        ans_a = _report(a, task)
        ans_b = _report(b, task)
        res = _battle(
            task_intent=f"Deep research task: {task}",
            agent_a=a,
            answer_a=ans_a,
            agent_b=b,
            answer_b=ans_b,
            model=model,
            dimension=None,
            n_samples=n_samples,
        )
        winner = res.get("agent_winner", "tie")
        battles.append({"agent_a": a, "agent_b": b, "winner": winner})
        battle_log.append({
            "task": task,
            "agent_a": a,
            "agent_b": b,
            "winner": winner,
            "words_a": raw_words.get((a, task)),
            "words_b": raw_words.get((b, task)),
        })

    # ----- Bradley-Terry rating --------------------------------------- #
    quality: dict[str, dict[str, float]] = {}
    if battles:
        if bootstrap:
            ci = bt.bootstrap_ci(battles)
            for a in included_agents:
                row = ci.get(a)
                if row:
                    quality[a] = {
                        "quality_elo": row["elo"],
                        "ci_lo": row["lo"],
                        "ci_hi": row["hi"],
                        "ci_half_width": row["half_width"],
                    }
        else:
            elo = bt.fit_bradley_terry(battles)
            for a in included_agents:
                if a in elo:
                    quality[a] = {"quality_elo": round(elo[a], 1)}

    # ----- Assemble per-agent rows + GATE ----------------------------- #
    agent_rows: dict[str, dict[str, Any]] = {}
    n_battles_per_agent: dict[str, int] = defaultdict(int)
    for blog in battle_log:
        n_battles_per_agent[blog["agent_a"]] += 1
        n_battles_per_agent[blog["agent_b"]] += 1

    for a in included_agents:
        g = grounding_mean[a]
        q = quality.get(a, {})
        agent_rows[a] = {
            "agent": a,
            "quality_elo": q.get("quality_elo"),
            "quality_ci": (
                {"lo": q["ci_lo"], "hi": q["ci_hi"], "half_width": q["ci_half_width"]}
                if "ci_lo" in q else None
            ),
            "grounding": round(g, 4),
            "gated": bool(g < grounding_floor),
            "n_tasks": len(per_agent_tasks.get(a, set())),
            "n_battles": n_battles_per_agent.get(a, 0),
        }

    # Ranked views.
    by_quality = sorted(
        [r for r in agent_rows.values() if not r["gated"] and r["quality_elo"] is not None],
        key=lambda r: -r["quality_elo"],
    )
    by_grounding = sorted(agent_rows.values(), key=lambda r: -r["grounding"])

    return {
        "synthetic_placeholder": False,
        "source": "real",
        "mode": "real",
        "summary": summary,
        "agents": agent_rows,
        "ranked_by_quality_elo_gated": [r["agent"] for r in by_quality],
        "ranked_by_grounding": [r["agent"] for r in by_grounding],
        "battle_log": battle_log,
        "n_battles": len(battles),
        "grounding_missing": grounding_missing,
        "invalid_runs": invalid_runs,
    }


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit-tasks", type=int, default=None)
    p.add_argument("--limit-agents", type=int, default=None)
    p.add_argument("--agents", type=str, default=None, help="comma-separated agent allowlist")
    p.add_argument("--reference", type=str, default=None, help="fixed reference agent for pairwise (default round-robin)")
    p.add_argument("--grounding-floor", type=float, default=DEFAULT_GROUNDING_FLOOR)
    p.add_argument("--word-budget", type=int, default=DEFAULT_WORD_BUDGET)
    p.add_argument("--model", type=str, default=DEFAULT_MODEL)
    p.add_argument("--n-samples", type=int, default=3)
    p.add_argument("--no-bootstrap", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="build work list + count battles; NO judge calls")
    p.add_argument("--report-dir", type=str, default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--score-dir", type=str, default=str(DEFAULT_SCORE_DIR))
    p.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    return p.parse_args(argv)


def _print_summary(result: dict) -> None:
    s = result["summary"]
    print("=" * 64)
    print(f"REAL leaderboard build [{result['mode']}]  source={result['source']}  synthetic={result['synthetic_placeholder']}")
    print("=" * 64)
    print(f"Agents included ({len(s['agents_included'])}): {', '.join(s['agents_included']) or '(none)'}")
    if s["agents_skipped"]:
        print("Agents skipped (NOT fabricated):")
        for sk in s["agents_skipped"]:
            print(f"  - {sk['agent']}: {sk['reason']}")
    else:
        print("Agents skipped: (none)")
    inv = result.get("invalid_runs") or []
    if inv:
        print(f"Invalid-capture runs excluded (NOT ranked, NOT a low score): {len(inv)}")
        for ir in inv[:20]:
            print(f"  - {ir['agent']}__{ir['task']}: {ir['reason']}")
    print(f"Tasks: {s['n_tasks']}   Reference: {s['reference']}")
    print(f"Battles planned: {s['n_battles_planned']}   Word budget: {s['word_budget']}")
    print(f"Grounding floor: {s['grounding_floor']}   Grounding source: {s['grounding_score_source']}")
    gm = result.get("grounding_mean")
    if gm is not None:
        print("Grounding (mean) per agent:")
        for a in s["agents_included"]:
            print(f"  - {a}: {gm.get(a)}")
    if result["mode"] != "dry-run":
        print(f"Battles run: {result.get('n_battles')}")
        print("Ranked by quality_elo (gated):", result.get("ranked_by_quality_elo_gated"))
        print("Ranked by grounding:", result.get("ranked_by_grounding"))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    agents_filter = [a.strip() for a in args.agents.split(",") if a.strip()] if args.agents else None
    result = build(
        report_dir=Path(args.report_dir),
        score_dir=Path(args.score_dir),
        limit_tasks=args.limit_tasks,
        limit_agents=args.limit_agents,
        agents_filter=agents_filter,
        reference=args.reference,
        grounding_floor=args.grounding_floor,
        word_budget=args.word_budget,
        model=args.model,
        dry_run=args.dry_run,
        n_samples=args.n_samples,
        bootstrap=not args.no_bootstrap,
    )
    _print_summary(result)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
