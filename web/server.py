"""DR-Arena web app — leaderboard, drill-down, per-task explorer, KPIs.

Pages:
  /                    live leaderboard with per-agent drill-down
  /task/<task_id>      per-task explorer (prompt + per-task agent ranking)
  /how-it-works        plain-English explanation of scoring + Bradley-Terry Elo
  /contribute          how to add a DR framework, reproduce the leaderboard
  /audit               latest score-file audit (read-only)
  /compare             agent x LLM matrix (queued LLMs)
  /api/agent/<name>    per-agent JSON: pillars, best/worst tasks
  /api/leaderboard.json  machine-readable mirror of leaderboard_deep.json

Every request reads the leaderboard files fresh from disk so the UI tracks
the in-flight bulk run without a restart.

Run::

    python -m uvicorn web.server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEEP_DIR = ROOT / "data" / "results" / Path(os.environ.get("DEEP_RESULTS_DIR", "deep_v3"))
V4_DIR = ROOT / "data" / "results" / "deep_v4"
AUDIT_DIR = ROOT / "data" / "results" / "audit"
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
REPORTS_DIR = ROOT / "data" / "results" / "deep"  # markdown reports live here
DOCS_DIR = ROOT / "docs"
GITHUB_URL = "https://github.com/yibol9768-alt/deep-research-arena"

try:
    import markdown as _markdown  # type: ignore
    _MD_EXTS = ["tables", "fenced_code", "toc"]
except Exception:  # noqa: BLE001
    _markdown = None  # type: ignore
    _MD_EXTS = []

app = FastAPI(title="Deep-Research Arena", version="0.4.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def _load_leaderboard_json() -> dict:
    p = DEEP_DIR / "leaderboard_deep.json"
    if not p.exists():
        raise HTTPException(503, f"leaderboard JSON missing at {p} - run scripts/build_deep_leaderboard.py first")
    return json.loads(p.read_text(encoding="utf-8"))


def _leaderboard_mtime() -> str | None:
    p = DEEP_DIR / "leaderboard_deep.json"
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


_SCORE_NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d+)_matrix\.score\.json$")


def _list_score_files() -> list[Path]:
    if not DEEP_DIR.exists():
        return []
    return [p for p in DEEP_DIR.glob("*_matrix.score.json") if _SCORE_NAME_RE.match(p.name)]


def _pair_counts() -> dict[str, int]:
    """Count score JSONs per agent currently on disk (live, not from JSON)."""
    counts: dict[str, int] = defaultdict(int)
    for p in _list_score_files():
        m = _SCORE_NAME_RE.match(p.name)
        if m:
            counts[m.group(1)] += 1
    return dict(counts)


def _load_score_file(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ---------- KPI stats (cheap-but-cached) ---------------------------------

# Cache on (mtime, file count) so any new score JSON busts it.
def _stats_cache_key() -> tuple[float, int]:
    files = _list_score_files()
    if not files:
        return (0.0, 0)
    return (max(p.stat().st_mtime for p in files), len(files))


_STATS_KEY: tuple[float, int] | None = None
_STATS_VALUE: dict | None = None


def _compute_kpi_stats() -> dict:
    """Aggregate stats across every score JSON on disk.

    Returns counts that sell the rigor of the benchmark:
      - total_pairs: number of (agent, task) score files
      - total_chars: sum of answer_chars across all reports
      - est_tokens: total_chars / 4 (industry-standard rough char->token ratio)
      - unique_urls: number of distinct cited URLs across all reports
      - degenerate_filtered: count summed from leaderboard drop_stats
      - judge_calls: sum of judge invocations (checklist + analysis_depth + presentation + citation_alignment samples)
    """
    files = _list_score_files()
    total_chars = 0
    unique_urls: set[str] = set()
    judge_calls = 0
    degenerate = 0
    judge_errors = 0

    for p in files:
        s = _load_score_file(p)
        if not s:
            continue
        total_chars += int(s.get("answer_chars") or 0)
        # Citation alignment samples list cited URLs per pair
        samples = ((s.get("citation_alignment") or {}).get("details") or {}).get("samples") or []
        for sm in samples:
            u = sm.get("url")
            if u:
                unique_urls.add(u)
        # Each LLM-judged pillar = ~1 call per pair; checklist verdicts = 1 batched call
        for k in ("checklist", "analysis_depth", "presentation"):
            d = s.get(k) or {}
            details = d.get("details") if isinstance(d.get("details"), dict) else {}
            if isinstance(d, dict) and "judge_error" in d:
                if d.get("judge_error"):
                    judge_errors += 1
                judge_calls += 1
            elif "judge_error" in details:
                if details.get("judge_error"):
                    judge_errors += 1
                judge_calls += 1
        # Citation alignment also calls the judge per cited pair
        ca_details = (s.get("citation_alignment") or {}).get("details") or {}
        judge_calls += int(ca_details.get("total_pairs") or 0)

    # degenerate count from leaderboard drop_stats
    try:
        lb = _load_leaderboard_json()
        for ag, st in (lb.get("drop_stats") or {}).items():
            degenerate += int(st.get("degenerate") or 0)
    except HTTPException:
        pass

    est_tokens = total_chars // 4 if total_chars else 0
    return {
        "total_pairs": len(files),
        "total_chars": total_chars,
        "est_tokens": est_tokens,
        "unique_urls": len(unique_urls),
        "judge_calls": judge_calls,
        "judge_errors": judge_errors,
        "degenerate_filtered": degenerate,
    }


def _get_kpi_stats() -> dict:
    global _STATS_KEY, _STATS_VALUE  # noqa: PLW0603
    key = _stats_cache_key()
    if _STATS_VALUE is None or key != _STATS_KEY:
        _STATS_VALUE = _compute_kpi_stats()
        _STATS_KEY = key
    return _STATS_VALUE


# ---------- Per-agent drill-down -----------------------------------------

def _agent_score_files(agent: str) -> list[tuple[str, Path]]:
    """Return (task_id, path) for every score JSON belonging to `agent`."""
    out: list[tuple[str, Path]] = []
    for p in _list_score_files():
        m = _SCORE_NAME_RE.match(p.name)
        if not m:
            continue
        if m.group(1) != agent:
            continue
        task_id = f"dr_cross_deep_{m.group(2)}"
        out.append((task_id, p))
    return out


def _agent_drilldown(agent: str) -> dict:
    """Compose the drill-down payload for one agent.

    Pulls per-pillar Elo from leaderboard_deep.json, then reads every
    score JSON for the agent to find best/worst tasks by composite_v2.
    """
    lb = _load_leaderboard_json()
    pillar_elo = (lb.get("pillar_elo") or {}).get(agent) or {}
    elo_v2 = (lb.get("elo_v2_ci") or {}).get(agent) or {}

    # Pull per-task composite_v2 to rank.
    rows: list[dict] = []
    for task_id, p in sorted(_agent_score_files(agent)):
        s = _load_score_file(p)
        if not s:
            continue
        comp = (s.get("composite") or {})
        rows.append({
            "task_id": task_id,
            "composite_v2": comp.get("composite_v2"),
            "composite_v3": comp.get("composite_v3"),
            "url_coverage": (s.get("url_coverage") or {}).get("score"),
            "reachability": (s.get("url_reachability") or {}).get("score"),
            "checklist": (s.get("checklist") or {}).get("pass_rate"),
            "analysis_depth": (s.get("analysis_depth") or {}).get("score"),
            "presentation": (s.get("presentation") or {}).get("score"),
            "citation_alignment": (s.get("citation_alignment") or {}).get("score"),
            "answer_chars": s.get("answer_chars"),
            "answer_path": s.get("answer_path"),
        })

    # Sort: best (highest composite_v2 first) and worst (lowest first).
    scored = [r for r in rows if isinstance(r.get("composite_v2"), (int, float))]
    best = sorted(scored, key=lambda r: -r["composite_v2"])[:3]
    worst = sorted(scored, key=lambda r: r["composite_v2"])[:3]

    # Aggregate per-pillar means across all tasks for the bars (separate from
    # pillar Elo, which is the inter-agent ranking, not the absolute level).
    def _mean(key: str) -> float | None:
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        return round(sum(vals) / len(vals), 4) if vals else None

    pillar_means = {
        "url_coverage": _mean("url_coverage"),
        "reachability": _mean("reachability"),
        "checklist": _mean("checklist"),
        "citation_alignment": _mean("citation_alignment"),
        "analysis_depth": _mean("analysis_depth"),
        "presentation": _mean("presentation"),
    }

    return {
        "agent": agent,
        "elo_v2": elo_v2,
        "pillar_elo": pillar_elo,
        "pillar_means": pillar_means,
        "best_tasks": best,
        "worst_tasks": worst,
        "n_pairs": len(rows),
        "github_url": _AGENT_LINKS.get(agent, {}).get("github"),
        "paper_url": _AGENT_LINKS.get(agent, {}).get("paper"),
    }


# Curated metadata so drill-down can link to each agent's upstream project.
_AGENT_LINKS: dict[str, dict[str, str]] = {
    "camel-ai":            {"github": "https://github.com/camel-ai/camel"},
    "co-storm":            {"github": "https://github.com/stanford-oval/storm"},
    "deerflow":            {"github": "https://github.com/bytedance/deer-flow"},
    "dzhng":               {"github": "https://github.com/dzhng/deep-research"},
    "flowsearcher-ds":     {"github": "https://github.com/yibol9768-alt/deep-research-arena"},
    "gpt-researcher":      {"github": "https://github.com/assafelovic/gpt-researcher"},
    "ii-researcher":       {"github": "https://github.com/Intelligent-Internet/ii-researcher"},
    "langchain-odr":       {"github": "https://github.com/langchain-ai/open_deep_research"},
    "ldr":                 {"github": "https://github.com/LearningCircuit/local-deep-research"},
    "local-deep-researcher": {"github": "https://github.com/langchain-ai/local-deep-researcher"},
    "smolagents":          {"github": "https://github.com/huggingface/smolagents"},
    "storm":               {"github": "https://github.com/stanford-oval/storm",
                            "paper": "https://arxiv.org/abs/2402.14207"},
    "tongyi-dr":           {"github": "https://github.com/Alibaba-NLP/DeepResearch"},
    "qx-agents":           {"github": "https://github.com/qx-labs/agents-deep-research"},
}


# ---------- Per-task explorer --------------------------------------------

@lru_cache(maxsize=128)
def _load_task_config(task_id: str) -> dict:
    """Read data/tasks/.../<task_id>.json. Cached because configs are static."""
    p = TASKS_DIR / f"{task_id}.json"
    if not p.exists():
        raise HTTPException(404, f"task not found: {task_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _task_per_agent(task_id: str) -> list[dict]:
    """For a given task, return per-agent score rows sorted by composite_v2 desc."""
    rows: list[dict] = []
    for p in _list_score_files():
        m = _SCORE_NAME_RE.match(p.name)
        if not m:
            continue
        if f"dr_cross_deep_{m.group(2)}" != task_id:
            continue
        s = _load_score_file(p)
        if not s:
            continue
        comp = s.get("composite") or {}
        agent = m.group(1)
        rows.append({
            "agent": agent,
            "composite_v2": comp.get("composite_v2"),
            "composite_v3": comp.get("composite_v3"),
            "url_coverage": (s.get("url_coverage") or {}).get("score"),
            "reachability": (s.get("url_reachability") or {}).get("score"),
            "checklist": (s.get("checklist") or {}).get("pass_rate"),
            "answer_chars": s.get("answer_chars"),
            "answer_path": s.get("answer_path"),
        })
    rows.sort(key=lambda r: -(r["composite_v2"] or 0))
    return rows


# ---------- Summary for the index ----------------------------------------

def _summary(lb: dict) -> dict:
    elo_v2 = lb.get("elo_v2_ci") or {}
    ranked = sorted(elo_v2.items(), key=lambda kv: -kv[1].get("elo", 0))
    los = [v.get("elo_lo", v.get("elo", 0)) for v in elo_v2.values()] or [1000]
    his = [v.get("elo_hi", v.get("elo", 0)) for v in elo_v2.values()] or [1000]
    elo_min = min(los)
    elo_max = max(his)
    elo_span = max(1.0, elo_max - elo_min)
    pair_counts = _pair_counts()
    n_tasks_target = 57  # number of cross-site tasks

    # Build a {higher: {lower: significant?}} lookup so the rank chips can be
    # tinted "tied" when the gap to the next row is not statistically significant.
    sig_pairs = (lb.get("rank_significance_v2") or {}).get("adjacent_pairs") or []
    sig_lookup: dict[str, bool] = {}
    for pair in sig_pairs:
        # Mark BOTH agents in a non-significant pair as "tied" with the other.
        sig_lookup[f"{pair['higher']}__{pair['lower']}"] = bool(pair.get("significant"))

    return {
        "ranked": ranked,
        "n_runs": lb.get("n_runs", 0),
        "n_agents": len(elo_v2),
        "n_tasks": len(lb.get("tasks") or []),
        "n_tasks_target": n_tasks_target,
        "elo_min": elo_min,
        "elo_max": elo_max,
        "elo_span": elo_span,
        "sig": sig_pairs,
        "sig_lookup": sig_lookup,
        "pair_counts": pair_counts,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        lb = _load_leaderboard_json()
        ctx = _summary(lb)
        ctx["loaded"] = True
        ctx["error"] = None
    except HTTPException as e:
        ctx = {
            "ranked": [], "n_runs": 0, "n_agents": 0, "n_tasks": 0,
            "elo_min": 0, "elo_max": 0, "elo_span": 1, "sig": [], "sig_lookup": {},
            "pair_counts": {}, "n_tasks_target": 57,
            "loaded": False, "error": e.detail,
        }
    ctx.update({
        "request": request,
        "github_url": GITHUB_URL,
        "leaderboard_mtime": _leaderboard_mtime(),
        "kpis": _get_kpi_stats(),
    })
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works(request: Request):
    return templates.TemplateResponse(request, "how_it_works.html", {
        "request": request,
        "github_url": GITHUB_URL,
    })


@app.get("/compare", response_class=HTMLResponse)
async def compare(request: Request):
    n_runs = 0
    try:
        n_runs = _load_leaderboard_json().get("n_runs", 0)
    except HTTPException:
        pass
    return templates.TemplateResponse(request, "compare.html", {
        "request": request,
        "github_url": GITHUB_URL,
        "n_runs": n_runs,
    })


@app.get("/contribute", response_class=HTMLResponse)
async def contribute(request: Request):
    return templates.TemplateResponse(request, "contribute.html", {
        "request": request,
        "github_url": GITHUB_URL,
    })


# Keep /add as an alias of /contribute for any existing bookmarks.
@app.get("/add", response_class=HTMLResponse)
async def add_alias(request: Request):
    return await contribute(request)


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request):
    md_text: str | None = None
    mtime_str: str | None = None
    filename: str | None = None
    placeholder = "Run `python scripts/audit_dr_scores.py` to generate the audit report."

    if AUDIT_DIR.exists():
        candidates = sorted(
            AUDIT_DIR.glob("DR_SCORE_AUDIT_*.md"),
            key=lambda p: p.stat().st_mtime,
        )
        if candidates:
            latest = candidates[-1]
            md_text = latest.read_text(encoding="utf-8")
            mtime_str = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            filename = latest.name

    md_html: str | None = None
    if md_text and _markdown is not None:
        md_html = _markdown.markdown(md_text, extensions=_MD_EXTS)

    return templates.TemplateResponse(request, "audit.html", {
        "request": request,
        "md_text": md_text,
        "md_html": md_html,
        "mtime_str": mtime_str,
        "filename": filename,
        "placeholder": placeholder,
        "github_url": GITHUB_URL,
    })


def _load_v4_leaderboard() -> dict | None:
    """Read the v4 leaderboard JSON if it exists."""
    p = V4_DIR / "leaderboard_deep_v4.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_v4b_leaderboard() -> dict | None:
    """Read the v4b (sharpened + rebalanced) leaderboard JSON."""
    p = V4_DIR / "leaderboard_deep_v4b.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_v4c_leaderboard() -> dict | None:
    """Read the v4c (z-score variance-budgeted) leaderboard JSON."""
    p = V4_DIR / "leaderboard_deep_v4c.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _v4_rows() -> list[dict]:
    """Per-row v4 JSONs (one per agent x task)."""
    out: list[dict] = []
    if not V4_DIR.exists():
        return out
    for p in sorted(V4_DIR.glob("*_matrix.v4.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


@app.get("/v4", response_class=HTMLResponse)
async def v4_page(request: Request):
    """Experimental v4 leaderboard view.

    Shows the four new v4 pillars (source_diversity, perspective_balance,
    factual_exactness, internal_consistency) and the composite_v4 Elo
    ranking. Defends the truthfulness-gate methodology by showing the
    same head/tail as v2 while surfacing the agents that the four new
    dimensions reweighted.
    """
    lb = _load_v4_leaderboard()
    lb_v4b = _load_v4b_leaderboard()
    lb_v4c = _load_v4c_leaderboard()
    rows = _v4_rows()

    # Build per-agent table (v4 ranking).
    ranked: list[tuple[str, dict, dict]] = []   # (agent, elo, summary)
    summary_by_agent: dict[str, dict] = {}
    if lb:
        summary_by_agent = lb.get("per_agent") or {}
        for agent, e in (lb.get("elo") or {}).items():
            ranked.append((agent, e, summary_by_agent.get(agent, {})))
        ranked.sort(key=lambda t: -float(t[1].get("elo") or 0))

    # v4b ranking (sharpened-and-rebalanced).
    ranked_v4b: list[tuple[str, dict, dict]] = []
    v4b_summary: dict[str, dict] = {}
    if lb_v4b:
        v4b_summary = lb_v4b.get("per_agent") or {}
        for agent, e in (lb_v4b.get("elo") or {}).items():
            ranked_v4b.append((agent, e, v4b_summary.get(agent, {})))
        ranked_v4b.sort(key=lambda t: -float(t[1].get("elo") or 0))

    sig = lb.get("significance") if lb else []
    sig_v4b = lb_v4b.get("significance") if lb_v4b else []
    gap_cmp = lb_v4b.get("gap_comparison") if lb_v4b else {}

    # v4c ranking (z-score normalised — variance-budgeted).
    ranked_v4c: list[tuple[str, dict, dict]] = []
    v4c_per_agent: dict[str, dict] = {}
    v4c_pillar_stats: dict[str, dict] = {}
    sig_v4c_pairs: list[dict] = []
    if lb_v4c:
        v4c_per_agent = lb_v4c.get("per_agent") or {}
        v4c_pillar_stats = lb_v4c.get("pillar_stats") or {}
        for agent, e in (lb_v4c.get("elo_mean") or {}).items():
            ranked_v4c.append((agent, e, v4c_per_agent.get(agent, {})))
        ranked_v4c.sort(key=lambda t: -float(t[1].get("elo") or 0))
        sig_v4c_pairs = (lb_v4c.get("rank_significance") or {}).get("adjacent_pairs", [])

    # Three-way gap comparison: v4 / v4b / v4c min and mean adjacent gaps.
    def _adj_stats(ranking):
        gaps = [ranking[i][1]["elo"] - ranking[i + 1][1]["elo"]
                for i in range(len(ranking) - 1)]
        if not gaps:
            return {"min": 0.0, "mean": 0.0, "n_pairs": 0}
        return {"min": round(min(gaps), 1),
                "mean": round(sum(gaps) / len(gaps), 1),
                "n_pairs": len(gaps)}

    three_way_gaps = {
        "v4":  _adj_stats(ranked),
        "v4b": _adj_stats(ranked_v4b),
        "v4c": _adj_stats(ranked_v4c),
    }

    # Top |Δ| rows (the "v4 vs v2 disagreement" table).
    real_rows = [
        r for r in rows
        if float(r.get("v2_composite") or 0) > 0 or float(r.get("v4_composite") or 0) > 0
    ]
    real_rows.sort(key=lambda r: -abs(float(r.get("v4_minus_v2") or 0)))
    top_diff = real_rows[:10]

    mtime_str: str | None = None
    p = V4_DIR / "leaderboard_deep_v4.json"
    if p.exists():
        mtime_str = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    return templates.TemplateResponse(request, "v4.html", {
        "request": request,
        "github_url": GITHUB_URL,
        "loaded": lb is not None,
        "ranked": ranked,
        "ranked_v4b": ranked_v4b,
        "summary_by_agent": summary_by_agent,
        "v4b_summary": v4b_summary,
        "sig": sig,
        "sig_v4b": sig_v4b,
        "gap_cmp": gap_cmp,
        "top_diff": top_diff,
        "n_rows_total": (lb or {}).get("n_rows_total", 0),
        "n_rows_real":  (lb or {}).get("n_rows_real",  0),
        "n_battles":    (lb or {}).get("n_battles",    0),
        "formula":      (lb or {}).get("formula", ""),
        "v4b_loaded":   lb_v4b is not None,
        "v4c_loaded":   lb_v4c is not None,
        "ranked_v4c":   ranked_v4c,
        "v4c_per_agent": v4c_per_agent,
        "v4c_pillar_stats": v4c_pillar_stats,
        "sig_v4c_pairs": sig_v4c_pairs,
        "three_way_gaps": three_way_gaps,
        "v4c_n_rows":   (lb_v4c or {}).get("n_rows", 0),
        "v4c_formula":  (lb_v4c or {}).get("formula", ""),
        "mtime_str":    mtime_str,
    })


@app.get("/api/v4.json")
async def v4_api():
    """Machine-readable v4 leaderboard + per-row data."""
    lb = _load_v4_leaderboard()
    rows = _v4_rows()
    return JSONResponse({
        "leaderboard": lb or {},
        "rows": rows,
    })


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    md_text: str | None = None
    md_html: str | None = None
    mtime_str: str | None = None
    path = DOCS_DIR / "PROJECT_WRITEUP.md"
    if path.exists():
        md_text = path.read_text(encoding="utf-8")
        mtime_str = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        if _markdown is not None:
            md_html = _markdown.markdown(md_text, extensions=_MD_EXTS)
    return templates.TemplateResponse(request, "about.html", {
        "request": request,
        "github_url": GITHUB_URL,
        "md_text": md_text,
        "md_html": md_html,
        "mtime_str": mtime_str,
        "placeholder": "docs/PROJECT_WRITEUP.md is missing.",
    })


@app.get("/task/{task_id}", response_class=HTMLResponse)
async def task_explorer(request: Request, task_id: str):
    if not re.fullmatch(r"dr_cross_deep_\d{4}", task_id):
        raise HTTPException(400, f"bad task_id: {task_id}")
    cfg = _load_task_config(task_id)
    rows = _task_per_agent(task_id)

    # Surface the agent leaderboard in a chart-friendly normalized form.
    return templates.TemplateResponse(request, "task.html", {
        "request": request,
        "github_url": GITHUB_URL,
        "task_id": task_id,
        "cfg": cfg,
        "rows": rows,
        "n_scored": len(rows),
        "all_tasks": _all_task_ids(),
    })


def _all_task_ids() -> list[str]:
    if not TASKS_DIR.exists():
        return []
    return sorted(p.stem for p in TASKS_DIR.glob("dr_cross_deep_*.json"))


# ---------- API endpoints -------------------------------------------------

@app.get("/api/leaderboard.json")
async def api_leaderboard_json():
    return JSONResponse(_load_leaderboard_json())


@app.get("/api/leaderboard")
async def api_leaderboard_alias():
    return JSONResponse(_load_leaderboard_json())


@app.get("/api/agent/{agent}")
async def api_agent(agent: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", agent):
        raise HTTPException(400, f"bad agent name: {agent}")
    try:
        return JSONResponse(_agent_drilldown(agent))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"agent drill-down failed: {e}") from e


@app.get("/api/task/{task_id}")
async def api_task(task_id: str):
    if not re.fullmatch(r"dr_cross_deep_\d{4}", task_id):
        raise HTTPException(400, f"bad task_id: {task_id}")
    return JSONResponse({
        "task_id": task_id,
        "config": _load_task_config(task_id),
        "rows": _task_per_agent(task_id),
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=True)
