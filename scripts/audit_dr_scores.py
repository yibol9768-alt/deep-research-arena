#!/usr/bin/env python3
"""Comprehensive audit of every Deep-Research score file.

Answers the user-facing question: "did we give the right Elo to each DR?"

Reads `data/results/deep_v3/<agent>__<task>_matrix.score.json` (or whichever
results dir is selected via `--results-dir` / `DEEP_RESULTS_DIR`), reuses the
same `_looks_degenerate` filter and composite formulas the leaderboard uses,
and writes a Markdown report under `data/results/audit/` with:

  * Summary panel: counts of files, kept rows, dropped rows, agents in / out
    of Elo, plus an overall verdict.
  * Table A: per-agent summary (one row per agent, sorted by leaderboard
    rank when the leaderboard JSON is reachable).
  * Table B: per-task coverage (agents scored / kept / missing, golden pool
    health).
  * Table C: anomaly list (composite outliers, reach=1 with no URLs cited,
    repeated-composite tells, judge_error inconsistencies, agent/task field
    mismatches).

Usage:
    python scripts/audit_dr_scores.py [--results-dir deep_v3] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_deep_leaderboard import _looks_degenerate, load_scores  # noqa: E402
from src.scoring.leaderboard_composites import (  # noqa: E402
    checklist_pass_rate,
    composite_v1,
    composite_v2_truthful,
    quality,
    spec_pass_fraction,
)


SCORE_RE = re.compile(r"^(.+?)__([a-z0-9_]+_\d+)_(\w+)\.score\.json$")
GOLDEN_DIR = ROOT / "data" / "golden" / "deep"
LEADERBOARD_JSON = ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep.json"
AUDIT_DIR = ROOT / "data" / "results" / "audit"

# Coverage thresholds for Table B status column.
TASK_OK_AGENTS = 7
GOLDEN_OK_URLS = 120
GOLDEN_OK_SOURCES = 3


def _cited_url_count(score: dict[str, Any]) -> int:
    """Best-effort cited-URL count for the reach=1 / no URL anomaly check."""
    reach = (score.get("url_reachability") or {}).get("details") or {}
    if "cited_total" in reach:
        return int(reach.get("cited_total") or 0)
    cov = (score.get("url_coverage") or {}).get("details") or {}
    return int(cov.get("cited_unique") or 0)


def _drop_reasons(score: dict[str, Any]) -> dict[str, int]:
    """Mirror the three buckets in `_looks_degenerate`. Returns a Counter
    keyed by `short`, `infra`, `judge_err`. A row that survives the filter
    contributes nothing here."""
    reasons: Counter[str] = Counter()
    if not _looks_degenerate(score):
        return reasons
    if score.get("answer_chars", 1) == 0:
        reasons["short"] += 1
        return reasons
    chars = score.get("answer_chars", 0)
    if chars and chars < 600:
        reach = (score.get("url_reachability") or {}).get("score") or 0
        ck = (score.get("checklist") or {}).get("pass_rate") or 0
        if reach == 0 and ck == 0:
            reasons["short"] += 1
            return reasons
    if (score.get("url_reachability") or {}).get("details", {}).get("infra_failure"):
        reasons["infra"] += 1
        return reasons
    reasons["judge_err"] += 1
    return reasons


def _golden_stats(task_id: str) -> tuple[int, int]:
    """Return (must_cite_count, distinct_source_count) for `task_id`,
    or (0, 0) if no golden file exists."""
    p = GOLDEN_DIR / f"{task_id}.json"
    if not p.exists():
        return (0, 0)
    try:
        gold = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return (0, 0)
    must_cite = gold.get("must_cite_urls") or []
    hosts: set[str] = set()
    for entry in must_cite:
        url = entry.get("url") if isinstance(entry, dict) else entry
        if not isinstance(url, str):
            continue
        host = urlparse(url).netloc
        if host:
            hosts.add(host)
    return (len(must_cite), len(hosts))


def _agent_rank_order() -> list[str]:
    """Pull agents in leaderboard rank order from leaderboard_deep.json
    when present; fall back to alphabetical."""
    if not LEADERBOARD_JSON.exists():
        return []
    try:
        lb = json.loads(LEADERBOARD_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []
    sig = lb.get("rank_significance_v2") or {}
    ordered = sig.get("ordered") or []
    if ordered:
        return list(ordered)
    elo = lb.get("elo_v2_ci") or {}
    return [a for a, _ in sorted(elo.items(), key=lambda kv: -float(kv[1].get("elo", 0)))]


def _load_all_rows(results_dir: Path) -> list[dict[str, Any]]:
    """Read every `<agent>__<task>_matrix.score.json` under `results_dir`,
    keeping rows that fail `_looks_degenerate` so the audit can describe
    them. Each row is `{agent, task_id, score, score_path, degenerate}`."""
    rows: list[dict[str, Any]] = []
    for p in sorted(results_dir.glob("*_matrix.score.json")):
        m = SCORE_RE.match(p.name)
        if not m:
            continue
        agent, task, sfx = m.groups()
        if sfx != "matrix":
            continue
        try:
            score = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"warn: skip {p.name}: {e}", file=sys.stderr)
            continue
        rows.append(
            {
                "agent": agent,
                "task_id": task,
                "score": score,
                "score_path": str(p.relative_to(ROOT)),
                "degenerate": _looks_degenerate(score),
            }
        )
    return rows


def _table_a(rows: list[dict[str, Any]], rank_order: list[str]) -> list[str]:
    """Per-agent summary, sorted by leaderboard rank."""
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_agent[r["agent"]].append(r)

    agents_in_rank = list(rank_order) + sorted(set(by_agent) - set(rank_order))
    md = [
        "## Table A: per-agent summary",
        "",
        "| agent | files | kept | dropped | mean v2 | median v2 | mean v1 | mean answer_chars | n(reach=0) | n(reach=1) | n(checklist judge_err) | drop reasons |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for agent in agents_in_rank:
        recs = by_agent.get(agent) or []
        if not recs:
            continue
        kept = [r for r in recs if not r["degenerate"]]
        dropped = [r for r in recs if r["degenerate"]]
        v2s = [composite_v2_truthful(r["score"]) for r in kept]
        v1s = [composite_v1(r["score"]) for r in kept]
        chars = [int(r["score"].get("answer_chars") or 0) for r in recs]
        n_reach0 = sum(1 for r in recs if ((r["score"].get("url_reachability") or {}).get("score") or 0) == 0)
        n_reach1 = sum(1 for r in recs if ((r["score"].get("url_reachability") or {}).get("score") or 0) >= 0.999)
        n_ck_err = sum(1 for r in recs if (r["score"].get("checklist") or {}).get("judge_error"))
        reasons: Counter[str] = Counter()
        for r in dropped:
            reasons.update(_drop_reasons(r["score"]))
        reason_str = ", ".join(f"{reasons.get(k, 0)} {k}" for k in ("short", "infra", "judge_err"))
        md.append(
            "| {agent} | {files} | {kept} | {drop} | {mv2} | {medv2} | {mv1} | {mch} | {r0} | {r1} | {ce} | {rs} |".format(
                agent=agent,
                files=len(recs),
                kept=len(kept),
                drop=len(dropped),
                mv2=f"{statistics.fmean(v2s):.3f}" if v2s else "—",
                medv2=f"{statistics.median(v2s):.3f}" if v2s else "—",
                mv1=f"{statistics.fmean(v1s):.3f}" if v1s else "—",
                mch=f"{statistics.fmean(chars):.0f}" if chars else "—",
                r0=n_reach0,
                r1=n_reach1,
                ce=n_ck_err,
                rs=reason_str,
            )
        )
    return md


def _table_b(rows: list[dict[str, Any]]) -> list[str]:
    """Per-task coverage: how many agents have a kept score for this task,
    plus golden-pool health."""
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)

    all_agents = sorted({r["agent"] for r in rows})
    md = [
        "## Table B: per-task coverage",
        "",
        "| task | agents_scored | agents_kept | agents_missing | golden_must_cite | golden_n_sources | status |",
        "|---|---:|---:|---|---:|---:|:---:|",
    ]
    for task_id in sorted(by_task):
        recs = by_task[task_id]
        scored = sorted({r["agent"] for r in recs})
        kept = sorted({r["agent"] for r in recs if not r["degenerate"]})
        missing = sorted(set(all_agents) - set(scored))
        n_must, n_sources = _golden_stats(task_id)
        cov_ok = len(kept) >= TASK_OK_AGENTS and n_must >= GOLDEN_OK_URLS and n_sources >= GOLDEN_OK_SOURCES
        status = "OK" if cov_ok else "WARN"
        md.append(
            "| {t} | {s} | {k} | {m} | {nm} | {ns} | {st} |".format(
                t=task_id,
                s=len(scored),
                k=len(kept),
                m=", ".join(missing) if missing else "—",
                nm=n_must,
                ns=n_sources,
                st=status,
            )
        )
    return md


def _table_c(rows: list[dict[str, Any]]) -> list[str]:
    """Anomalies: composite outliers, reach/url-count mismatches, repeated
    composites, judge_error inconsistencies, agent / task field problems."""
    anomalies: list[dict[str, Any]] = []

    # Per-agent composite outliers (>3 stdev from agent's median over kept rows).
    by_agent_kept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if not r["degenerate"]:
            by_agent_kept[r["agent"]].append(r)

    for agent, kept in by_agent_kept.items():
        comps = [composite_v2_truthful(r["score"]) for r in kept]
        if len(comps) < 4:
            continue
        med = statistics.median(comps)
        try:
            sd = statistics.stdev(comps)
        except statistics.StatisticsError:
            continue
        if sd <= 0:
            continue
        for r, c in zip(kept, comps):
            if abs(c - med) > 3 * sd:
                anomalies.append(
                    {
                        "agent": agent,
                        "task": r["task_id"],
                        "v2": c,
                        "reason": f"composite_v2 outlier: |c - median| = {abs(c - med):.3f} > 3*sd ({sd:.3f})",
                    }
                )

    # reach=1 with zero cited URLs (impossible).
    for r in rows:
        reach = (r["score"].get("url_reachability") or {}).get("score") or 0
        if reach >= 0.999 and _cited_url_count(r["score"]) == 0:
            anomalies.append(
                {
                    "agent": r["agent"],
                    "task": r["task_id"],
                    "v2": composite_v2_truthful(r["score"]),
                    "reason": "reach=1.0 but cited URL count is 0",
                }
            )

    # Same composite_v2 repeating across >=4 different tasks for one agent.
    for agent, kept in by_agent_kept.items():
        bucket: dict[float, list[str]] = defaultdict(list)
        for r in kept:
            c = round(composite_v2_truthful(r["score"]), 3)
            bucket[c].append(r["task_id"])
        for c, tasks in bucket.items():
            if len(set(tasks)) >= 4:
                for t in sorted(set(tasks)):
                    anomalies.append(
                        {
                            "agent": agent,
                            "task": t,
                            "v2": c,
                            "reason": f"composite_v2={c:.3f} repeats across {len(set(tasks))} tasks for {agent} (template/cache tell)",
                        }
                    )

    # judge_error on checklist with positive pass_rate (contradiction).
    for r in rows:
        ck = r["score"].get("checklist") or {}
        if ck.get("judge_error") and float(ck.get("pass_rate") or 0) > 0:
            anomalies.append(
                {
                    "agent": r["agent"],
                    "task": r["task_id"],
                    "v2": composite_v2_truthful(r["score"]),
                    "reason": f"checklist.judge_error set but pass_rate={ck.get('pass_rate')}",
                }
            )

    # agent field None / task field mismatch with filename.
    for r in rows:
        score = r["score"]
        if score.get("agent") is None and "agent" in score:
            anomalies.append(
                {
                    "agent": r["agent"],
                    "task": r["task_id"],
                    "v2": composite_v2_truthful(score),
                    "reason": "score.agent is None",
                }
            )
        embedded_task = score.get("task")
        if embedded_task and embedded_task != r["task_id"]:
            anomalies.append(
                {
                    "agent": r["agent"],
                    "task": r["task_id"],
                    "v2": composite_v2_truthful(score),
                    "reason": f"filename task={r['task_id']} but embedded task={embedded_task}",
                }
            )

    md = ["## Table C: anomalies", ""]
    if not anomalies:
        md.append("OK no anomalies")
        return md
    md += [
        "| agent | task | composite_v2 | reason |",
        "|---|---|---:|---|",
    ]
    for a in sorted(anomalies, key=lambda x: (x["agent"], x["task"], x["reason"])):
        md.append(f"| {a['agent']} | {a['task']} | {a['v2']:.3f} | {a['reason']} |")
    return md


def _summary_panel(
    rows: list[dict[str, Any]],
    results_dir: Path,
    rank_order: list[str],
) -> list[str]:
    total = len(rows)
    kept = [r for r in rows if not r["degenerate"]]
    dropped = total - len(kept)

    by_agent_total = Counter(r["agent"] for r in rows)
    by_agent_kept = Counter(r["agent"] for r in kept)
    in_elo = sorted(a for a, _ in by_agent_kept.most_common() if by_agent_kept[a] > 0)
    excluded = sorted(a for a in by_agent_total if by_agent_kept[a] == 0)

    if dropped == 0 and not excluded:
        verdict = "PASS"
    elif excluded or dropped > total * 0.3:
        verdict = "FAIL"
    else:
        verdict = "WARN"

    rank_note = ""
    if rank_order:
        rank_note = f" (rank order from leaderboard: {', '.join(rank_order)})"

    return [
        f"# Deep-Research score audit ({date.today().isoformat()})",
        "",
        f"Source directory: `{results_dir.relative_to(ROOT)}`{rank_note}",
        "",
        "## Summary",
        "",
        f"- Total score files: **{total}**",
        f"- Kept after degenerate filter: **{len(kept)}**",
        f"- Dropped: **{dropped}**",
        f"- Agents in Elo: {', '.join(in_elo) if in_elo else '(none)'}",
        f"- Agents excluded: {', '.join(excluded) if excluded else '(none)'}",
        f"- Verdict: **{verdict}**",
        "",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--results-dir",
        default=os.environ.get("DEEP_RESULTS_DIR", "deep_v3"),
        help="Subdirectory under data/results/ to audit (default: deep_v3, or DEEP_RESULTS_DIR env).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Override output path. Default: data/results/audit/DR_SCORE_AUDIT_<today>.md",
    )
    args = parser.parse_args()

    results_dir = ROOT / "data" / "results" / args.results_dir
    if not results_dir.exists():
        print(f"error: {results_dir} does not exist", file=sys.stderr)
        return 1

    # Make load_scores see the right directory. It honours DEEP_RESULTS_DIR
    # at import time, so we set it here for any indirect callers but rely on
    # `_load_all_rows` for the actual scan (it keeps degenerate rows so the
    # audit can describe them).
    os.environ["DEEP_RESULTS_DIR"] = str(results_dir.relative_to(ROOT)).replace(os.sep, "/")
    _ = load_scores  # keep the symbol referenced; the import is the contract

    rows = _load_all_rows(results_dir)
    if not rows:
        print(f"no *_matrix.score.json under {results_dir}", file=sys.stderr)
        return 1

    rank_order = _agent_rank_order()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else AUDIT_DIR / f"DR_SCORE_AUDIT_{date.today().isoformat()}.md"

    md: list[str] = []
    md += _summary_panel(rows, results_dir, rank_order)
    md += _table_a(rows, rank_order)
    md += ["", ""]
    md += _table_b(rows)
    md += ["", ""]
    md += _table_c(rows)
    md += [""]

    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"WROTE {out_path.relative_to(ROOT)}")
    print(
        f"  files={len(rows)} kept={sum(1 for r in rows if not r['degenerate'])} "
        f"dropped={sum(1 for r in rows if r['degenerate'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
