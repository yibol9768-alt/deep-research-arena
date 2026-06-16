#!/usr/bin/env python3
"""Closed-world scorer (CLOSED_WORLD_REDESIGN.md section 7-8, 10).

Runs the decidable closed-world layers over deep-research reports and merges the
results into the per-report score JSON so build_real_leaderboard picks up the new
grounding pillar:

  * GROUNDING (section 7) -- always. Reachability + claim support against the
    frozen sandbox. With --use-llm the claim-support verdict is the self-hosted
    vLLM (Qwen3-8B); load-bearing stays deterministic. Falls back to token
    overlap if the server is down.
  * COMPLETENESS (section 8) -- when the task carries a DB-derived relevant_set.

Run ON the box (my5090) where the sandbox (localhost:7770/9999/8090) and the vLLM
(127.0.0.1:8000) are local. From elsewhere, open ssh -L tunnels first.

Single:  python3 scripts/score_closed_world.py --report data/results/deep/X__T_matrix.md --task T --use-llm
Batch:   python3 scripts/score_closed_world.py --batch data/results/deep --use-llm
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.verifiers.grounding_verifier import GroundingVerifier  # noqa: E402
from src.verifiers.completeness_verifier import CompletenessVerifier  # noqa: E402

TASK_DIRS = [
    ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep",
    ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep_v2",
    ROOT / "data" / "tasks" / "deep_research" / "cross_site",
]

_FNAME_RE = re.compile(r"^(?P<agent>.+?)__(?P<task>dr_[a-z0-9_]+?)_(?P<variant>matrix|smoke|run\d*)\.md$")


def _remap_pairs() -> dict[str, str]:
    """Sandbox host:port remap for fetching. Reports cite the canonical ports
    (shopping 7770), but a revived box sandbox may serve them elsewhere
    (e.g. shopping on 17770). Configure via CW_SANDBOX_REMAP="a=b,c=d".
    """
    import os
    raw = os.environ.get("CW_SANDBOX_REMAP", "localhost:7770=localhost:17770")
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            a, b = pair.split("=", 1)
            out[a.strip()] = b.strip()
    return out


def make_remapping_fetcher(max_workers: int = 4):
    """Fetcher for GroundingVerifier that rewrites cited URLs to the live
    sandbox ports before fetching, but keys results by the ORIGINAL URL so the
    report-to-page matching is unchanged."""
    import concurrent.futures
    import os
    from src.verifiers.quote_match_verifier import _fetch as _qm_fetch
    remap = _remap_pairs()
    timeout = float(os.environ.get("CW_FETCH_TIMEOUT", "8"))
    retries = int(os.environ.get("CW_FETCH_RETRIES", "2"))

    def _fetch_one(u: str):
        fu = u
        for a, b in remap.items():
            if a in fu:
                fu = fu.replace(a, b)
        return u, _qm_fetch(fu, timeout=timeout, retries=retries)

    def fetch(urls: list[str]) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            for u, txt in ex.map(_fetch_one, urls):
                out[u] = txt
        return out

    return fetch


def load_task(task_id: str) -> dict:
    for d in TASK_DIRS:
        p = d / f"{task_id}.json"
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
    return {"task_id": task_id, "sites": ["shopping", "reddit", "wikipedia"]}


def score_one(report_path: Path, task_id: str, *, gamma: float, k_star: int | None,
              use_llm: bool, completeness_only: bool = False) -> dict:
    answer = report_path.read_text(errors="replace")
    task = load_task(task_id)

    out: dict = {}
    if not completeness_only:
        gv = GroundingVerifier(gamma=gamma, k_star=k_star, use_llm=use_llm,
                               fetch_fn=make_remapping_fetcher())
        g = gv.verify(task_config=task, answer=answer)
        out["grounding"] = {"score": g.score, "passed": g.passed, "details": g.details}

    # Completeness only when a DB-derived relevant_set is wired on the task.
    has_rs = bool((task.get("completeness") or {}).get("relevant_set")
                  or (task.get("completeness") or {}).get("golden_path")
                  or (task.get("golden") or {}).get("relevant_set_path"))
    if has_rs:
        c = CompletenessVerifier().verify(task_config=task, answer=answer)
        out["completeness"] = {"score": c.score, "passed": c.passed, "details": c.details}
    return out


def merge_into_score_json(report_path: Path, pillars: dict) -> Path | None:
    sj_path = report_path.with_suffix(".score.json")
    existing = {}
    if sj_path.exists():
        try:
            existing = json.loads(sj_path.read_text())
        except Exception:
            existing = {}
        bak = report_path.with_suffix(".score.cwbak.json")
        if not bak.exists():
            bak.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    existing.update(pillars)
    sj_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    return sj_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ap.add_argument("--task")
    ap.add_argument("--batch", help="directory of <agent>__<task>_<variant>.md reports")
    ap.add_argument("--variant", default="matrix", help="only score this variant in batch mode")
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--k-star", type=int, default=None)
    ap.add_argument("--use-llm", action="store_true", help="use vLLM judge for claim support")
    ap.add_argument("--no-merge", action="store_true", help="print only, do not write score JSON")
    ap.add_argument("--limit", type=int, default=0, help="batch: cap number of reports (0=all)")
    ap.add_argument("--skip-scored", action="store_true",
                    help="batch: skip reports whose .score.json already has a grounding pillar (resume)")
    ap.add_argument("--completeness-only", action="store_true",
                    help="only (re)compute completeness; keep the existing grounding pillar (no LLM/fetch)")
    args = ap.parse_args()

    if args.report and args.task:
        pillars = score_one(Path(args.report), args.task,
                            gamma=args.gamma, k_star=args.k_star, use_llm=args.use_llm,
                            completeness_only=args.completeness_only)
        print(json.dumps(pillars, indent=2)[:2500])
        if not args.no_merge:
            sj = merge_into_score_json(Path(args.report), pillars)
            print(f"merged -> {sj}")
        return 0

    if args.batch:
        bdir = Path(args.batch)
        reports = []
        for p in sorted(bdir.glob("*.md")):
            m = _FNAME_RE.match(p.name)
            if m and m.group("variant") == args.variant:
                reports.append((p, m.group("agent"), m.group("task")))
        if args.limit:
            reports = reports[: args.limit]
        print(f"scoring {len(reports)} reports (variant={args.variant}, use_llm={args.use_llm})")
        rows = []
        for i, (p, agent, task) in enumerate(reports, 1):
            if args.skip_scored:
                sj = p.with_suffix(".score.json")
                if sj.exists():
                    try:
                        ex = json.loads(sj.read_text())
                        if isinstance(ex.get("grounding"), dict) and ex["grounding"].get("score") is not None:
                            print(f"[{i}/{len(reports)}] {agent} {task} SKIP (already scored)", flush=True)
                            continue
                    except Exception:
                        pass
            try:
                pillars = score_one(p, task, gamma=args.gamma, k_star=args.k_star,
                                    use_llm=args.use_llm, completeness_only=args.completeness_only)
                if not args.no_merge:
                    merge_into_score_json(p, pillars)
                gd = (pillars.get("grounding") or {}).get("details") or {}
                cd = (pillars.get("completeness") or {}).get("details") or {}
                rows.append((agent, task, gd.get("grounding"), cd.get("completeness")))
                gpart = (f"G={(gd.get('grounding') or 0.0):.3f} reach={(gd.get('reach_rate') or 0.0):.2f} "
                         f"cited={gd.get('n_citations') or 0}") if gd else ""
                cpart = (f"compl={(cd.get('completeness') or 0.0):.3f} "
                         f"({cd.get('surfaced_count')}/{cd.get('relevant_total')})") if cd else ""
                print(f"[{i}/{len(reports)}] {agent:<16} {task:<22} {gpart} {cpart}", flush=True)
            except Exception as e:
                print(f"[{i}/{len(reports)}] {agent} {task} ERROR {e}", flush=True)
        # compact per-agent means (grounding + completeness)
        from collections import defaultdict
        gagg, cagg = defaultdict(list), defaultdict(list)
        for agent, _t, g, c in rows:
            if g is not None:
                gagg[agent].append(g)
            if c is not None:
                cagg[agent].append(c)
        print("\n=== per-agent means ===")
        for agent in sorted(set(gagg) | set(cagg)):
            gv, cv = gagg.get(agent, []), cagg.get(agent, [])
            gm = f"grounding={sum(gv)/len(gv):.3f}" if gv else ""
            cm = f"completeness={sum(cv)/len(cv):.3f}" if cv else ""
            print(f"  {agent:<18} n={max(len(gv), len(cv))}  {gm}  {cm}")
        return 0

    ap.error("provide --report+--task or --batch")
    return 2


if __name__ == "__main__":
    sys.exit(main())
