"""DR-Arena web app — leaderboard + add-DR + smoke + playground.

The data layer is intentionally thin: every page reads the same JSON files
``build_deep_leaderboard.py`` and ``score_deep_answer.py`` already produce, so
nothing in this server can drift from the leaderboard the paper cites.

Run::

    python -m uvicorn web.server:app --host 0.0.0.0 --port 8000 --reload

Then open http://localhost:8000. The Windows machine running this is the same
one with LM Studio + a 5090 — `/playground` and `/smoke` both call into LM
Studio at ``http://127.0.0.1:1234/v1`` so anyone on the LAN can try the harness
without any cloud key.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEEP_DIR = ROOT / "data" / "results" / Path(os.environ.get("DEEP_RESULTS_DIR", "deep_v3"))
SMOKE_DIR = ROOT / "data" / "results" / "smoke"
SMOKE_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR = ROOT / "data" / "results" / "audit"

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen3.5-35b-a3b")

app = FastAPI(title="DR-Arena", version="0.1.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def _load_leaderboard() -> dict:
    """Read leaderboard_deep.json. Caller is responsible for re-running
    ``scripts/build_deep_leaderboard.py`` when score files change."""
    p = DEEP_DIR / "leaderboard_deep.json"
    if not p.exists():
        raise HTTPException(503, f"leaderboard JSON missing at {p} — run scripts/build_deep_leaderboard.py first")
    return json.loads(p.read_text(encoding="utf-8"))


def _load_score(agent: str, task: str) -> dict | None:
    p = DEEP_DIR / f"{agent}__{task}_matrix.score.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _agent_matrix(agent: str) -> list[dict]:
    """Per-task rows for one agent: [{task, composite_v2, composite_v1,
    pillars, answer_chars}]."""
    from src.scoring.leaderboard_composites import (
        composite_v1, composite_v2_truthful,
        spec_pass_fraction, checklist_pass_rate,
    )
    rows = []
    for p in sorted(DEEP_DIR.glob(f"{agent}__*_matrix.score.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # task id = filename slice between agent__ and _matrix.score.json
        stem = p.stem  # e.g. "camel-ai__dr_cross_deep_0001_matrix.score"
        task = stem.replace(f"{agent}__", "").replace("_matrix.score", "")
        c2 = composite_v2_truthful(d)
        c1 = composite_v1(d)
        rows.append({
            "task": task,
            "composite_v2": round(c2, 3),
            "composite_v1": round(c1, 3),
            "answer_chars": d.get("answer_chars", 0),
            "pillars": {
                "url_coverage":   round((d.get("url_coverage")     or {}).get("score") or 0, 3),
                "reachability":   round((d.get("url_reachability") or {}).get("score") or 0, 3),
                "checklist":      round(checklist_pass_rate(d.get("checklist") or {}), 3),
                "spec":           round(spec_pass_fraction(d.get("markdown_spec") or {}), 3),
                "quote_match":    round((d.get("quote_match") or {}).get("score") or 0, 3),
            },
        })
    return rows


def _featured_metrics(lb: dict) -> dict:
    """Pick the top performer per pillar — the four cards at the top of the
    page mirror artificialanalysis.ai's "Intelligence / Speed / Latency / Price"
    summary band."""
    pillars = lb.get("pillar_elo") or {}
    elo_v2 = lb.get("elo_v2_ci") or {}

    # Best Elo (overall winner)
    if elo_v2:
        top_elo = max(elo_v2.items(), key=lambda kv: kv[1].get("elo", 0))
        top_elo_card = {"label": "Top Elo", "agent": top_elo[0], "value": f"{top_elo[1].get('elo', 0):.0f}", "subtitle": "Composite_v2 (truthful)"}
    else:
        top_elo_card = {"label": "Top Elo", "agent": "—", "value": "—", "subtitle": ""}

    cards = [top_elo_card]
    for pillar_key, label in [
        ("url_coverage", "Top URL Coverage"),
        ("reachability", "Top Reachability"),
        ("checklist",    "Top Judge-Pass"),
    ]:
        scores = {a: v.get(pillar_key, 0) for a, v in pillars.items()}
        if scores:
            best = max(scores.items(), key=lambda kv: kv[1])
            cards.append({
                "label":    label,
                "agent":    best[0],
                "value":    f"{best[1]:.0f}",
                "subtitle": "per-pillar Elo",
            })
        else:
            cards.append({"label": label, "agent": "—", "value": "—", "subtitle": ""})
    return {"cards": cards}


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    lb = _load_leaderboard()
    elo_v2 = lb.get("elo_v2_ci") or {}
    elo_v1 = lb.get("elo_v1_ci") or {}
    pillar = lb.get("pillar_elo") or {}
    drop = lb.get("drop_stats") or {}
    excluded = set(lb.get("excluded_agents") or [])

    # Sort agents by composite_v2 Elo (descending).
    ranked_v2 = sorted(elo_v2.items(), key=lambda kv: -kv[1].get("elo", 0))
    ranked_v1 = sorted(elo_v1.items(), key=lambda kv: -kv[1].get("elo", 0))

    # Compute Elo range so we can draw a visual bar inside each row.
    elos = [v.get("elo", 0) for v in elo_v2.values()] or [1000]
    elo_min, elo_max = min(elos), max(elos)
    elo_span = max(1.0, elo_max - elo_min)

    # Audit trail rows: every agent that produced files but had any dropped.
    audit = []
    for a, s in sorted(drop.items()):
        if s.get("kept", 0) == s.get("total", 0):
            continue
        status = "excluded" if a in excluded else "partial"
        audit.append({"agent": a, **s, "status": status})

    sig = (lb.get("rank_significance_v2") or {}).get("adjacent_pairs", [])

    return templates.TemplateResponse("index.html", {
        "request": request,
        "n_runs": lb.get("n_runs", 0),
        "n_agents": len(elo_v2),
        "n_tasks": len(lb.get("tasks") or []),
        "tasks": lb.get("tasks") or [],
        "ranked_v2": ranked_v2,
        "ranked_v1": ranked_v1,
        "pillars_by_agent": pillar,
        "audit": audit,
        "sig": sig,
        "featured": _featured_metrics(lb),
        "elo_min": elo_min,
        "elo_max": elo_max,
        "elo_span": elo_span,
        "lm_studio_url": LM_STUDIO_URL,
        "lm_studio_model": LM_STUDIO_MODEL,
    })


@app.get("/agent/{name}", response_class=HTMLResponse)
async def agent_detail(request: Request, name: str):
    lb = _load_leaderboard()
    elo_v2 = (lb.get("elo_v2_ci") or {}).get(name)
    elo_v1 = (lb.get("elo_v1_ci") or {}).get(name)
    pillar = (lb.get("pillar_elo") or {}).get(name) or {}
    drop = (lb.get("drop_stats") or {}).get(name) or {}
    matrix = _agent_matrix(name)

    if not matrix and not elo_v2:
        raise HTTPException(404, f"no data for agent {name!r}")

    # Sort by task id ascending for a clean per-task view.
    matrix.sort(key=lambda r: r["task"])

    # Mean composite for the summary line.
    if matrix:
        mean_c2 = round(sum(r["composite_v2"] for r in matrix) / len(matrix), 3)
        mean_c1 = round(sum(r["composite_v1"] for r in matrix) / len(matrix), 3)
    else:
        mean_c2 = mean_c1 = 0.0

    return templates.TemplateResponse("agent.html", {
        "request": request,
        "name": name,
        "elo_v2": elo_v2,
        "elo_v1": elo_v1,
        "pillar": pillar,
        "drop": drop,
        "matrix": matrix,
        "mean_c2": mean_c2,
        "mean_c1": mean_c1,
    })


@app.get("/add", response_class=HTMLResponse)
async def add_dr(request: Request):
    return templates.TemplateResponse("add.html", {
        "request": request,
        "lm_studio_url": LM_STUDIO_URL,
        "lm_studio_model": LM_STUDIO_MODEL,
    })


@app.get("/smoke", response_class=HTMLResponse)
async def smoke_page(request: Request):
    """Show the latest smoke report inline + a button that triggers a fresh
    run via /api/smoke."""
    latest_md, latest_json = _latest_smoke()
    return templates.TemplateResponse("smoke.html", {
        "request": request,
        "latest_md": latest_md,
        "latest_json": latest_json,
        "lm_studio_url": LM_STUDIO_URL,
        "lm_studio_model": LM_STUDIO_MODEL,
    })


@app.get("/playground", response_class=HTMLResponse)
async def playground(request: Request):
    return templates.TemplateResponse("playground.html", {
        "request": request,
        "lm_studio_url": LM_STUDIO_URL,
        "lm_studio_model": LM_STUDIO_MODEL,
    })


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request):
    """Latest aggregate score-file audit. Read the most recent
    ``DR_SCORE_AUDIT_*.md`` from ``data/results/audit/`` (mtime sort) and
    render it inside a monospace pre block — the audit doc is structured
    markdown (tables, lists), and a fixed-width pre keeps tables aligned
    without needing a markdown-to-HTML dep."""
    md_text: str | None = None
    mtime_str: str | None = None
    filename: str | None = None
    placeholder = "Run `python scripts/audit_dr_scores.py` first to generate the audit report."

    if AUDIT_DIR.exists():
        candidates = sorted(
            AUDIT_DIR.glob("DR_SCORE_AUDIT_*.md"),
            key=lambda p: p.stat().st_mtime,
        )
        if candidates:
            latest = candidates[-1]
            md_text = latest.read_text(encoding="utf-8")
            mtime = datetime.fromtimestamp(latest.stat().st_mtime)
            mtime_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            filename = latest.name

    return templates.TemplateResponse("audit.html", {
        "request": request,
        "md_text": md_text,
        "mtime_str": mtime_str,
        "filename": filename,
        "placeholder": placeholder,
        "lm_studio_url": LM_STUDIO_URL,
        "lm_studio_model": LM_STUDIO_MODEL,
    })


# ---------------------------------------------------------------------------
# JSON / API routes
# ---------------------------------------------------------------------------

@app.get("/api/leaderboard")
async def api_leaderboard():
    """Raw leaderboard JSON — same file the paper analysis scripts read,
    exposed so that downstream tooling doesn't have to scrape the HTML page."""
    return JSONResponse(_load_leaderboard())


@app.get("/api/health")
async def api_health():
    """Ping LM Studio. Used by the frontend to render a green/red pill in the
    nav bar so users know whether the local backbone is up before they click
    Run on /smoke or send a /playground message."""
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            r = await client.get(LM_STUDIO_URL.rstrip("/") + "/models")
            r.raise_for_status()
            payload = r.json()
        return {
            "ok": True,
            "latency_ms": int((time.time() - t0) * 1000),
            "models": [m.get("id") for m in payload.get("data", [])],
            "active_model": LM_STUDIO_MODEL,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "latency_ms": int((time.time() - t0) * 1000)}


@app.post("/api/chat")
async def api_chat(request: Request):
    """Forward a single chat completion to LM Studio.

    Kept deliberately thin: we don't replicate /v1/chat/completions, just shim
    enough of it so the playground UI doesn't have to embed the API key. Body
    shape: {"messages": [...], "max_tokens": int?}.
    """
    body = await request.json()
    messages = body.get("messages") or []
    if not messages:
        raise HTTPException(400, "messages must be a non-empty list")
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": float(body.get("temperature", 0.3)),
        "max_tokens": int(body.get("max_tokens", 512)),
    }
    try:
        async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
            r = await client.post(
                LM_STUDIO_URL.rstrip("/") + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer lmstudio"},
            )
            r.raise_for_status()
            return JSONResponse(r.json())
    except httpx.HTTPError as e:
        raise HTTPException(502, f"LM Studio error: {e}") from e


@app.post("/api/smoke")
async def api_smoke():
    """Kick off ``scripts/smoke_test_drs.py`` as a subprocess. Streaming would
    be nicer but the script is short enough that a synchronous run keeps the
    UI logic simple — total wait ≈ 60-120s with 8 runners × short timeouts."""
    import subprocess
    cmd = [sys.executable, str(ROOT / "scripts" / "smoke_test_drs.py"), "--timeout", "60"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=900)
    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "smoke timed out after 15 min"}, status_code=504)

    md_path, _ = _latest_smoke()
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "log_tail": stdout.decode("utf-8", errors="replace")[-4000:],
        "report_path": str(md_path) if md_path else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_smoke() -> tuple[str | None, dict | None]:
    md_files = sorted(SMOKE_DIR.glob("smoke_*.md"))
    if not md_files:
        return None, None
    md_path = md_files[-1]
    json_path = md_path.with_suffix(".json")
    md = md_path.read_text(encoding="utf-8")
    js = None
    if json_path.exists():
        try:
            js = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            js = None
    return md, js


# ---------------------------------------------------------------------------
# Convenience entrypoint so `python web/server.py` Just Works.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=True)
