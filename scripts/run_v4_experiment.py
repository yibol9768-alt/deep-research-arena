"""Run v4 verifiers on existing DR reports and compare v2 vs v4 rankings.

Goal
~~~~
We already have ~397 scored runs in `data/results/deep_v3/`. This script
takes a curated subsample, runs the 4 new v4 verifiers on each
(source_diversity / perspective_balance / factual_exactness /
internal_consistency), and produces a comparison report showing whether
v4 truly separates good DR reports from bad ones, beyond what v2 alone
sees.

What it produces
~~~~~~~~~~~~~~~~
* `data/results/deep_v4/<agent>__<task>_matrix.v4.json` — per-run v4 add-on
* `data/results/deep_v4/V4_RUN_REPORT.md` — human-readable summary:
    - per-agent mean v2 vs v4
    - rank delta table (who moved up / down)
    - per-pillar means
    - examples where v4 disagrees with v2 (URL-true but problematic)

Sampling strategy
~~~~~~~~~~~~~~~~~
By default we run on 27 reports = 9 ranked agents × 3 representative
tasks (0001 / 0005 / 0010). Override with --tasks / --agents / --max.

Cost
~~~~
~50 LLM calls / report. Heavy verifiers use V4 Pro (call_judge_heavy),
light verifiers use V4 Flash (call_judge). At ~$0.005 / call avg, 27
reports ≈ 1300 calls ≈ $7.

Env required
~~~~~~~~~~~~
* JUDGE_PROVIDER=openai
* JUDGE_BASE_URL=http://localhost:8088/v1
* JUDGE_API_KEY=anything
* JUDGE_MODEL=deepseek-v4-flash
* JUDGE_MODEL_HEAVY=deepseek-v4-pro
* Sandbox up on 7770 / 9999 / 8090 (so factual_exactness can fetch pages)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.verifiers.source_diversity_verifier import SourceDiversityVerifier   # noqa: E402
from src.verifiers.perspective_balance_verifier import PerspectiveBalanceVerifier  # noqa: E402
from src.verifiers.factual_exactness_verifier import FactualExactnessVerifier  # noqa: E402
from src.verifiers.internal_consistency_verifier import InternalConsistencyVerifier  # noqa: E402
from src.scoring.leaderboard_composites import (  # noqa: E402
    composite_v2_truthful, composite_v4, composite_v4_weights,
)


SANDBOX_HOSTS = ["localhost:7770", "localhost:9999", "localhost:8090"]


# ---------------------------------------------------------------------------
# Resolve report + task spec paths
# ---------------------------------------------------------------------------

def _find_report_md(agent: str, task: str, results_root: Path) -> Path | None:
    """Locate the .md report that matches this scored run."""
    pat = f"{agent}__{task}_matrix.md"
    for d in [results_root / "deep_v3", results_root / "deep"]:
        p = d / pat
        if p.exists():
            return p
    return None


def _load_task_config(task: str, root: Path) -> dict:
    p = root / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{task}.json"
    if not p.exists():
        return {}
    cfg = json.loads(p.read_text())
    cfg.setdefault("sandbox_hosts", SANDBOX_HOSTS)
    return cfg


# ---------------------------------------------------------------------------
# Run one (agent, task) sample through v4 verifiers
# ---------------------------------------------------------------------------

def run_one(
    agent: str, task: str, results_root: Path, project_root: Path, out_dir: Path,
    *, skip_heavy: bool = False,
) -> dict | None:
    score_path = results_root / "deep_v3" / f"{agent}__{task}_matrix.score.json"
    if not score_path.exists():
        return None
    md_path = _find_report_md(agent, task, results_root)
    if not md_path:
        return None
    score = json.loads(score_path.read_text())
    answer = md_path.read_text(encoding="utf-8", errors="ignore")
    task_cfg = _load_task_config(task, project_root)

    out: dict = {
        "agent": agent, "task": task,
        "answer_chars": len(answer),
        "answer_path": str(md_path),
        "score_path":  str(score_path),
        "v2_composite": round(float(composite_v2_truthful(score)), 4),
        "v2_pillars": {
            "url_reachability":  (score.get("url_reachability") or {}).get("score"),
            "url_coverage":      (score.get("url_coverage")     or {}).get("score"),
            "checklist_pass":    (score.get("checklist")        or {}).get("pass_rate"),
            "quote_match":       (score.get("quote_match")      or {}).get("score"),
        },
    }
    print(f"\n[{agent} × {task}] running v4 verifiers...")
    t0 = time.time()
    try:
        sd = SourceDiversityVerifier().verify(task_config=task_cfg, answer=answer)
        out["source_diversity"] = {
            "score": sd.score, "passed": sd.passed, "details": sd.details,
        }
        print(f"  source_diversity     = {sd.score:.3f}")
    except Exception as exc:
        out["source_diversity_error"] = f"{type(exc).__name__}: {exc}"
        print(f"  source_diversity     ERROR: {exc}")

    try:
        pb = PerspectiveBalanceVerifier().verify(task_config=task_cfg, answer=answer)
        out["perspective_balance"] = {
            "score": pb.score, "passed": pb.passed, "details": pb.details,
        }
        print(f"  perspective_balance  = {pb.score:.3f}")
    except Exception as exc:
        out["perspective_balance_error"] = f"{type(exc).__name__}: {exc}"
        print(f"  perspective_balance  ERROR: {exc}")

    if not skip_heavy:
        try:
            fe = FactualExactnessVerifier(max_paragraphs=10, max_total_facts=25).verify(
                task_config=task_cfg, answer=answer,
            )
            out["factual_exactness"] = {
                "score": fe.score, "passed": fe.passed, "details": fe.details,
            }
            print(f"  factual_exactness    = {fe.score:.3f} "
                  f"({fe.details.get('total_facts', '?')} facts)")
        except Exception as exc:
            out["factual_exactness_error"] = f"{type(exc).__name__}: {exc}"
            print(f"  factual_exactness    ERROR: {exc}")

        try:
            ic = InternalConsistencyVerifier(max_pairs_per_cluster=8, max_total_pairs=40).verify(
                task_config=task_cfg, answer=answer,
            )
            out["internal_consistency"] = {
                "score": ic.score, "passed": ic.passed, "details": ic.details,
            }
            print(f"  internal_consistency = {ic.score:.3f} "
                  f"({ic.details.get('pairs_tested', 0)} pairs)")
        except Exception as exc:
            out["internal_consistency_error"] = f"{type(exc).__name__}: {exc}"
            print(f"  internal_consistency ERROR: {exc}")
    else:
        out["heavy_skipped"] = True

    # Compose v4 composite over the merged v2+v4 score dict.
    merged = dict(score)
    for key in ("source_diversity", "perspective_balance", "factual_exactness", "internal_consistency"):
        if key in out:
            merged[key] = out[key]
    out["v4_composite"] = round(float(composite_v4(merged)), 4)
    out["v4_minus_v2"] = round(out["v4_composite"] - out["v2_composite"], 4)
    out["elapsed_s"] = round(time.time() - t0, 1)
    print(f"  -> v2={out['v2_composite']:.3f}  v4={out['v4_composite']:.3f}  "
          f"Δ={out['v4_minus_v2']:+.3f}  ({out['elapsed_s']}s)")

    # Persist.
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{agent}__{task}_matrix.v4.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False),
    )
    return out


# ---------------------------------------------------------------------------
# Aggregation + report rendering
# ---------------------------------------------------------------------------

def _agent_summary(rows: list[dict]) -> dict[str, dict]:
    """Per-agent mean scores. Skips rows that errored on every v4 pillar."""
    out: dict[str, dict] = {}
    by_agent: dict[str, list[dict]] = {}
    for r in rows:
        by_agent.setdefault(r["agent"], []).append(r)
    for agent, lst in by_agent.items():
        n = len(lst)
        def avg(key_chain: tuple[str, ...]) -> float | None:
            vals: list[float] = []
            for r in lst:
                cur = r
                for k in key_chain:
                    if not isinstance(cur, dict) or k not in cur:
                        cur = None
                        break
                    cur = cur[k]
                if isinstance(cur, (int, float)):
                    vals.append(float(cur))
            return round(sum(vals) / len(vals), 4) if vals else None
        out[agent] = {
            "n_runs": n,
            "v2_mean":   avg(("v2_composite",)),
            "v4_mean":   avg(("v4_composite",)),
            "delta":     None,
            "sd_mean":   avg(("source_diversity",     "score")),
            "pb_mean":   avg(("perspective_balance",  "score")),
            "fe_mean":   avg(("factual_exactness",    "score")),
            "ic_mean":   avg(("internal_consistency", "score")),
        }
        if out[agent]["v2_mean"] is not None and out[agent]["v4_mean"] is not None:
            out[agent]["delta"] = round(out[agent]["v4_mean"] - out[agent]["v2_mean"], 4)
    return out


def _rank(by_agent: dict[str, dict], key: str) -> list[tuple[str, float]]:
    """Return [(agent, score), ...] sorted desc by key, skipping Nones."""
    pairs = [(a, d.get(key)) for a, d in by_agent.items()]
    pairs = [(a, s) for a, s in pairs if s is not None]
    pairs.sort(key=lambda t: -t[1])
    return pairs


def render_report(rows: list[dict]) -> str:
    by_agent = _agent_summary(rows)
    v2_rank = _rank(by_agent, "v2_mean")
    v4_rank = _rank(by_agent, "v4_mean")
    v2_pos = {a: i + 1 for i, (a, _) in enumerate(v2_rank)}
    v4_pos = {a: i + 1 for i, (a, _) in enumerate(v4_rank)}

    L = []
    L.append("# v4 Verifier Run Report\n")
    L.append(f"Sample size: {len(rows)} runs across {len(by_agent)} agents.\n")
    L.append("v4 composite weights:\n")
    L.append("```")
    for k, v in composite_v4_weights().items():
        L.append(f"  {k:25s}  {v}")
    L.append("```\n")

    L.append("## Per-agent mean scores\n")
    L.append("| Agent | n | v2 mean | v4 mean | Δ (v4-v2) | source_div | persp_bal | factual_ex | intl_cons |")
    L.append("|-------|---|---------|---------|-----------|------------|-----------|------------|-----------|")
    for a, d in sorted(by_agent.items(), key=lambda kv: -(kv[1]["v4_mean"] or -1)):
        def f(x): return f"{x:.3f}" if isinstance(x, float) else "—"
        L.append(
            f"| {a} | {d['n_runs']} | {f(d['v2_mean'])} | {f(d['v4_mean'])} | "
            f"{f(d['delta'])} | {f(d['sd_mean'])} | {f(d['pb_mean'])} | "
            f"{f(d['fe_mean'])} | {f(d['ic_mean'])} |"
        )
    L.append("")

    L.append("## v2 vs v4 rank changes\n")
    L.append("| Agent | v2 rank | v4 rank | Δ |")
    L.append("|-------|---------|---------|---|")
    movers: list[tuple[str, int]] = []
    for a in by_agent:
        if a in v2_pos and a in v4_pos:
            dlt = v2_pos[a] - v4_pos[a]
            movers.append((a, dlt))
    movers.sort(key=lambda t: -abs(t[1]))
    for a, dlt in movers:
        arrow = f"+{dlt}" if dlt > 0 else str(dlt)
        L.append(f"| {a} | {v2_pos.get(a, '—')} | {v4_pos.get(a, '—')} | {arrow} |")
    L.append("")

    L.append("## Where v4 disagrees most with v2 (top |Δ| at row level)\n")
    L.append("These rows are where the v4 composite differs most from v2 on the same report. Positive Δ means v4 rates higher than v2 (likely the report has good multi-perspective / diverse sourcing despite middling URL coverage); negative Δ means v4 rates lower (likely URL-true but factually wrong / one-sided / self-contradicting).\n")
    L.append("| Agent × Task | v2 | v4 | Δ | sd | pb | fe | ic |")
    L.append("|---|---|---|---|---|---|---|---|")
    rows_sorted = sorted(rows, key=lambda r: -abs(r.get("v4_minus_v2", 0.0)))[:12]
    for r in rows_sorted:
        def g(blob: dict | None) -> str:
            if not isinstance(blob, dict):
                return "—"
            s = blob.get("score")
            return f"{s:.2f}" if isinstance(s, (int, float)) else "—"
        L.append(
            f"| {r['agent']} × {r['task']} | "
            f"{r.get('v2_composite', 0):.2f} | {r.get('v4_composite', 0):.2f} | "
            f"{r.get('v4_minus_v2', 0):+.2f} | "
            f"{g(r.get('source_diversity'))} | {g(r.get('perspective_balance'))} | "
            f"{g(r.get('factual_exactness'))} | {g(r.get('internal_consistency'))} |"
        )
    L.append("")

    L.append("## Verdict — does v4 actually distinguish good DR from bad?\n")
    if v2_rank and v4_rank:
        top_v2 = v2_rank[0][0]
        top_v4 = v4_rank[0][0]
        bot_v2 = v2_rank[-1][0]
        bot_v4 = v4_rank[-1][0]
        same_head = top_v2 == top_v4
        same_tail = bot_v2 == bot_v4
        L.append(f"* v2 leader: **{top_v2}** | v4 leader: **{top_v4}** "
                 f"({'same' if same_head else 'different — v4 has redrawn the head'}).")
        L.append(f"* v2 tail: **{bot_v2}** | v4 tail: **{bot_v4}** "
                 f"({'same' if same_tail else 'different'}).")
    moved = [a for a, d in movers if abs(d) >= 2]
    L.append(f"* {len(moved)} agent(s) moved by ≥ 2 ranks between v2 and v4: {', '.join(moved) if moved else '(none)'}.")
    L.append("")

    L.append("## Pillar coverage diagnostics\n")
    def _coverage(key: str) -> int:
        return sum(1 for r in rows if isinstance(r.get(key), dict))
    L.append(f"* source_diversity   covered: {_coverage('source_diversity')} / {len(rows)}")
    L.append(f"* perspective_balance covered: {_coverage('perspective_balance')} / {len(rows)}")
    L.append(f"* factual_exactness   covered: {_coverage('factual_exactness')} / {len(rows)}")
    L.append(f"* internal_consistency covered: {_coverage('internal_consistency')} / {len(rows)}")

    return "\n".join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="camel-ai,flowsearcher-ds,smolagents,ldr,gpt-researcher,deerflow,ii-researcher,langchain-odr,storm")
    ap.add_argument("--tasks",  default="dr_cross_deep_0001,dr_cross_deep_0005,dr_cross_deep_0010")
    ap.add_argument("--max",    type=int, default=27, help="cap total runs (sample)")
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "results" / "deep_v4"))
    ap.add_argument("--report-name", default="V4_RUN_REPORT.md")
    ap.add_argument("--skip-heavy", action="store_true", help="run only zero-LLM and light pillars")
    ap.add_argument("--resume", action="store_true", help="skip rows that already have a v4.json")
    args = ap.parse_args()

    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    tasks  = [t.strip() for t in args.tasks.split(",")  if t.strip()]
    results_root = ROOT / "data" / "results"
    out_dir = Path(args.out_dir)

    print(f"agents: {agents}")
    print(f"tasks:  {tasks}")
    print(f"out:    {out_dir}")
    print(f"skip_heavy: {args.skip_heavy}")
    print(f"judge_model={os.environ.get('JUDGE_MODEL','(default)')}  "
          f"judge_model_heavy={os.environ.get('JUDGE_MODEL_HEAVY','(default)')}")

    rows: list[dict] = []
    n_run = 0
    for a in agents:
        for t in tasks:
            if n_run >= args.max:
                break
            out_path = out_dir / f"{a}__{t}_matrix.v4.json"
            if args.resume and out_path.exists():
                try:
                    rows.append(json.loads(out_path.read_text()))
                    print(f"[resume] {a} × {t}")
                except Exception:
                    pass
                n_run += 1
                continue
            r = run_one(a, t, results_root, ROOT, out_dir, skip_heavy=args.skip_heavy)
            if r:
                rows.append(r)
                n_run += 1
        if n_run >= args.max:
            break

    print(f"\n=== {len(rows)} runs complete; writing report ===")
    md = render_report(rows)
    (out_dir / args.report_name).write_text(md, encoding="utf-8")
    (out_dir / "v4_rows.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(f"wrote {out_dir / args.report_name}")
    print(f"wrote {out_dir / 'v4_rows.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
