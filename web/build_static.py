from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from web import server


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
DEFAULT_OUT = WEB_DIR / "dist"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _render(env: Environment, template_name: str, context: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = env.get_template(template_name).render(**context)
    out_path.write_text(html, encoding="utf-8")


def _base_context() -> dict:
    return {
        "github_url": server.GITHUB_URL,
        "request": None,
    }


def _index_context() -> dict:
    try:
        lb = server._load_leaderboard_json()
        ctx = server._summary(lb)
        ctx["loaded"] = True
        ctx["error"] = None
    except Exception as e:  # noqa: BLE001
        ctx = {
            "ranked": [],
            "n_runs": 0,
            "n_agents": 0,
            "n_tasks": 0,
            "elo_min": 0,
            "elo_max": 0,
            "elo_span": 1,
            "sig": [],
            "sig_lookup": {},
            "pair_counts": {},
            "n_tasks_target": 57,
            "loaded": False,
            "error": str(e),
        }
    ctx.update(
        {
            "leaderboard_mtime": server._leaderboard_mtime(),
            "kpis": server._get_kpi_stats(),
        }
    )
    return ctx


def _compare_context() -> dict:
    n_runs = 0
    try:
        n_runs = server._load_leaderboard_json().get("n_runs", 0)
    except Exception:  # noqa: BLE001
        pass
    return {"n_runs": n_runs}


def _markdown_page_context(path: Path, placeholder: str) -> dict:
    md_text = None
    md_html = None
    mtime_str = None
    if path.exists():
        md_text = path.read_text(encoding="utf-8")
        mtime_str = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        if server._markdown is not None:
            md_html = server._markdown.markdown(md_text, extensions=server._MD_EXTS)
    return {
        "md_text": md_text,
        "md_html": md_html,
        "mtime_str": mtime_str,
        "placeholder": placeholder,
    }


def _audit_context() -> dict:
    md_text = None
    md_html = None
    mtime_str = None
    filename = None
    placeholder = "Run `python scripts/audit_dr_scores.py` to generate the audit report."
    if server.AUDIT_DIR.exists():
        candidates = sorted(
            server.AUDIT_DIR.glob("DR_SCORE_AUDIT_*.md"),
            key=lambda p: p.stat().st_mtime,
        )
        if candidates:
            latest = candidates[-1]
            md_text = latest.read_text(encoding="utf-8")
            mtime_str = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            filename = latest.name
            if server._markdown is not None:
                md_html = server._markdown.markdown(md_text, extensions=server._MD_EXTS)
    return {
        "md_text": md_text,
        "md_html": md_html,
        "mtime_str": mtime_str,
        "filename": filename,
        "placeholder": placeholder,
    }


def _v4_context() -> dict:
    lb = server._load_v4_leaderboard()
    lb_v4b = server._load_v4b_leaderboard()
    lb_v4c = server._load_v4c_leaderboard()
    rows = server._v4_rows()

    ranked = []
    summary_by_agent = {}
    if lb:
        summary_by_agent = lb.get("per_agent") or {}
        for agent, e in (lb.get("elo") or {}).items():
            ranked.append((agent, e, summary_by_agent.get(agent, {})))
        ranked.sort(key=lambda t: -float(t[1].get("elo") or 0))

    ranked_v4b = []
    v4b_summary = {}
    if lb_v4b:
        v4b_summary = lb_v4b.get("per_agent") or {}
        for agent, e in (lb_v4b.get("elo") or {}).items():
            ranked_v4b.append((agent, e, v4b_summary.get(agent, {})))
        ranked_v4b.sort(key=lambda t: -float(t[1].get("elo") or 0))

    ranked_v4c = []
    v4c_per_agent = {}
    v4c_pillar_stats = {}
    sig_v4c_pairs = []
    if lb_v4c:
        v4c_per_agent = lb_v4c.get("per_agent") or {}
        v4c_pillar_stats = lb_v4c.get("pillar_stats") or {}
        for agent, e in (lb_v4c.get("elo_mean") or {}).items():
            ranked_v4c.append((agent, e, v4c_per_agent.get(agent, {})))
        ranked_v4c.sort(key=lambda t: -float(t[1].get("elo") or 0))
        sig_v4c_pairs = (lb_v4c.get("rank_significance") or {}).get("adjacent_pairs", [])

    def _adj_stats(ranking: list[tuple[str, dict, dict]]) -> dict:
        gaps = [
            ranking[i][1]["elo"] - ranking[i + 1][1]["elo"]
            for i in range(len(ranking) - 1)
        ]
        if not gaps:
            return {"min": 0.0, "mean": 0.0, "n_pairs": 0}
        return {
            "min": round(min(gaps), 1),
            "mean": round(sum(gaps) / len(gaps), 1),
            "n_pairs": len(gaps),
        }

    real_rows = [
        r
        for r in rows
        if float(r.get("v2_composite") or 0) > 0 or float(r.get("v4_composite") or 0) > 0
    ]
    real_rows.sort(key=lambda r: -abs(float(r.get("v4_minus_v2") or 0)))
    top_diff = real_rows[:10]

    mtime_str = None
    p = server.V4_DIR / "leaderboard_deep_v4.json"
    if p.exists():
        mtime_str = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "loaded": lb is not None,
        "ranked": ranked,
        "ranked_v4b": ranked_v4b,
        "summary_by_agent": summary_by_agent,
        "v4b_summary": v4b_summary,
        "sig": lb.get("significance") if lb else [],
        "sig_v4b": lb_v4b.get("significance") if lb_v4b else [],
        "gap_cmp": lb_v4b.get("gap_comparison") if lb_v4b else {},
        "top_diff": top_diff,
        "n_rows_total": (lb or {}).get("n_rows_total", 0),
        "n_rows_real": (lb or {}).get("n_rows_real", 0),
        "n_battles": (lb or {}).get("n_battles", 0),
        "formula": (lb or {}).get("formula", ""),
        "v4b_loaded": lb_v4b is not None,
        "v4c_loaded": lb_v4c is not None,
        "ranked_v4c": ranked_v4c,
        "v4c_per_agent": v4c_per_agent,
        "v4c_pillar_stats": v4c_pillar_stats,
        "sig_v4c_pairs": sig_v4c_pairs,
        "three_way_gaps": {
            "v4": _adj_stats(ranked),
            "v4b": _adj_stats(ranked_v4b),
            "v4c": _adj_stats(ranked_v4c),
        },
        "v4c_n_rows": (lb_v4c or {}).get("n_rows", 0),
        "v4c_formula": (lb_v4c or {}).get("formula", ""),
        "mtime_str": mtime_str,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(STATIC_DIR, out_dir / "static")

    env = _env()
    base = _base_context()

    _render(env, "index.html", {**base, **_index_context()}, out_dir / "index.html")
    _render(env, "how_it_works.html", base, out_dir / "how-it-works" / "index.html")
    _render(env, "compare.html", {**base, **_compare_context()}, out_dir / "compare" / "index.html")
    _render(env, "contribute.html", base, out_dir / "contribute" / "index.html")
    _render(env, "contribute.html", base, out_dir / "add" / "index.html")
    _render(env, "audit.html", {**base, **_audit_context()}, out_dir / "audit" / "index.html")
    _render(
        env,
        "about.html",
        {
            **base,
            **_markdown_page_context(
                server.DOCS_DIR / "PROJECT_WRITEUP.md",
                "docs/PROJECT_WRITEUP.md is missing.",
            ),
        },
        out_dir / "about" / "index.html",
    )

    v4_ctx = _v4_context()
    if v4_ctx["loaded"] or v4_ctx["v4b_loaded"] or v4_ctx["v4c_loaded"]:
        _render(env, "v4.html", {**base, **v4_ctx}, out_dir / "v4" / "index.html")

    all_tasks = server._all_task_ids()
    for task_id in all_tasks:
        _render(
            env,
            "task.html",
            {
                **base,
                "task_id": task_id,
                "cfg": server._load_task_config(task_id),
                "rows": server._task_per_agent(task_id),
                "n_scored": len(server._task_per_agent(task_id)),
                "all_tasks": all_tasks,
            },
            out_dir / "task" / task_id / "index.html",
        )
        _write_json(
            out_dir / "api" / "task" / f"{task_id}.json",
            {
                "task_id": task_id,
                "config": server._load_task_config(task_id),
                "rows": server._task_per_agent(task_id),
            },
        )

    _write_json(out_dir / "api" / "leaderboard.json", server._load_leaderboard_json())

    if v4_ctx["loaded"] or v4_ctx["v4b_loaded"] or v4_ctx["v4c_loaded"]:
        _write_json(
            out_dir / "api" / "v4.json",
            {
                "leaderboard": server._load_v4_leaderboard() or {},
                "rows": server._v4_rows(),
            },
        )

    lb = server._load_leaderboard_json()
    for agent in (lb.get("elo_v2_ci") or {}).keys():
        _write_json(out_dir / "api" / "agent" / f"{agent}.json", server._agent_drilldown(agent))

    (out_dir / "_headers").write_text(
        "/api/*\n"
        "  Content-Type: application/json; charset=utf-8\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a static export of the Deep Research Arena web app.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory for the static site.")
    args = parser.parse_args()
    build(args.out.resolve())
    print(f"Static site built at {args.out.resolve()}")


if __name__ == "__main__":
    main()
