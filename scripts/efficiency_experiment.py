#!/usr/bin/env python3
"""Token-efficiency experiment: run several Qwen backbones as DR agents on the
same tasks under a FIXED protocol, recording token consumption per (model, task)
so the comparison is apples-to-apples, then we can correlate tokens vs grounding
and GLM-5.1-judged quality into an efficiency table.

Fixed protocol (identical for every model, so token differences reflect the
model, not a model-chosen number of rounds):
  1. one model call: generate N search queries for the task,
  2. shim search each query, collect the top hits,
  3. shim extract the top K unique URLs into snippets,
  4. one model call: write a cited markdown report from the snippets.
Tokens are summed across the two model calls (prompt + completion) per task.

Requires the sandbox shim (:8081) and DashScope/Bailian creds in the env:
  set -a; . /root/.config/dra/bailian.env; set +a
  python3 scripts/efficiency_experiment.py \
     --models qwen3-30b-a3b-instruct-2507,qwen3-32b,qwen-flash,qwen3-max \
     --tasks dr_cross_deep_0001,dr_cross_deep_0002 --shim http://localhost:8081
Outputs data/results/efficiency/efficiency.json and writes each report to
data/results/deep/eff-<model>__<task>_matrix.md for downstream judging.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "results" / "efficiency"
REPORT_DIR = ROOT / "data" / "results" / "deep"
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"


def _load_intent(task: str) -> str:
    """Real task intent (so qwen3 attempts the actual task, comparable to the
    other frameworks + scorable against the per-task goldens). Falls back to a
    generic instruction if the task JSON is missing."""
    p = TASKS_DIR / f"{task}.json"
    if p.exists():
        try:
            it = (json.loads(p.read_text(encoding="utf-8")).get("intent") or "").strip()
            if it:
                return it
        except Exception:
            pass
    return (f"Produce a grounded comparative deep-research report for task {task} "
            "using the sandbox sources (shopping, forum, wiki).")


def _http_json(url: str, payload: dict, timeout: float = 60.0, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _chat(base_url: str, key: str, model: str, messages: list[dict],
          max_tokens: int = 2000, timeout: float = 120.0) -> tuple[str, dict]:
    """One DashScope (OpenAI-compatible) chat call. Returns (text, usage)."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    low = model.lower()
    # Disable reasoning for thinking-capable models so tokens are not wasted.
    # NB: MiniMax rejects enable_thinking (HTTP 400) so it is intentionally excluded.
    if (low.startswith("glm") or "thinking" in low or low.startswith("qwen3")
            or low.startswith("deepseek-v4") or low.startswith("kimi")):
        body["extra_body"] = {"thinking": {"type": "disabled"}}
        body["enable_thinking"] = False
        body["thinking"] = {"type": "disabled"}
    d = _http_json(base_url.rstrip("/") + "/chat/completions", body, timeout=timeout,
                   headers={"Authorization": f"Bearer {key}"})
    ch = (d.get("choices") or [{}])[0].get("message", {})
    text = ch.get("content") or ""
    usage = d.get("usage") or {}
    return text, {"in": int(usage.get("prompt_tokens", 0)), "out": int(usage.get("completion_tokens", 0))}


def _shim_search(shim: str, query: str, max_results: int = 6) -> list[dict]:
    try:
        d = _http_json(shim.rstrip("/") + "/search", {"query": query, "max_results": max_results})
        return d.get("results") or d.get("hits") or []
    except Exception:
        return []


# The shim returns docker-internal hostnames (http://wiki:8080, http://reddit,
# http://shop:8080). Reports must cite the canonical sandbox form
# (localhost:8090/9999/7770) or grounding scores them zero. We canonicalize for
# the SNIPPETS/citations but keep the internal form for the extract call (the
# shim can only fetch internal names from inside its container).
_HOST_MAP = [
    (re.compile(r"^https?://wiki:8080"), "http://localhost:8090"),
    (re.compile(r"^https?://reddit(?::\d+)?(?=/|$)"), "http://localhost:9999"),
    (re.compile(r"^https?://shop(?::\d+)?(?=/|$)"), "http://localhost:7770"),
    (re.compile(r"^https?://(?:shopping|magento|onestopmarket)(?::\d+)?(?=/|$)"), "http://localhost:7770"),
]


def _canon_url(u: str) -> str:
    for pat, repl in _HOST_MAP:
        if pat.match(u or ""):
            return pat.sub(repl, u, count=1)
    return u


def _shim_extract(shim: str, url: str) -> str:
    try:
        d = _http_json(shim.rstrip("/") + "/extract", {"urls": [url]})
        res = d.get("results") or []
        if res:
            return (res[0].get("raw_content") or res[0].get("content") or "")[:3000]
    except Exception:
        pass
    return ""


def run_agent(task_intent: str, shim: str, base_url: str, key: str, model: str,
              n_queries: int = 4, k_pages: int = 8) -> dict:
    """Fixed-protocol DR run. Returns metrics + the report markdown."""
    t0 = time.time()
    tok_in = tok_out = calls = 0

    # Step 1: generate search queries.
    q_sys = ("You are a deep-research agent. Output ONLY a JSON array of "
             f"{n_queries} short web-search queries (strings) that together cover "
             "the task across shopping products, forum discussions, and "
             "encyclopedia background. No prose, just the JSON array.")
    text, u = _chat(base_url, key, model, [
        {"role": "system", "content": q_sys},
        {"role": "user", "content": task_intent},
    ], max_tokens=300, timeout=420.0)
    calls += 1; tok_in += u["in"]; tok_out += u["out"]
    m = re.search(r"\[.*\]", text, re.S)
    try:
        queries = [str(q) for q in json.loads(m.group(0))][:n_queries] if m else []
    except Exception:
        queries = []
    if not queries:
        queries = [task_intent[:80]]

    # Steps 2-3: search + extract. Cite the canonical localhost form; fetch via
    # the shim's internal form.
    seen: dict[str, str] = {}
    for q in queries:
        for hit in _shim_search(shim, q):
            raw = hit.get("url") or ""
            canon = _canon_url(raw)
            if canon and canon not in seen and len(seen) < k_pages:
                seen[canon] = _shim_extract(shim, raw)

    snippets = "\n\n".join(
        f"[{i+1}] {url}\n{(txt or '')[:1200]}" for i, (url, txt) in enumerate(seen.items())
    )

    # Step 4: write the cited report.
    w_sys = ("You are a deep-research agent. Write a thorough markdown research "
             "report answering the task. Cite sources inline as [label](URL), "
             "copying each URL EXACTLY, character-for-character, from the provided "
             "sources. Every valid URL starts with http://localhost:7770 (shopping), "
             "http://localhost:9999 (forum) or http://localhost:8090 (wiki). NEVER "
             "rewrite a URL to a public domain -- www.reddit.com, en.wikipedia.org, "
             "amazon.com or any other invented host counts as fabrication and scores "
             "zero. Cite ONLY the provided URLs; every nontrivial claim needs a "
             "citation.")
    text2, u2 = _chat(base_url, key, model, [
        {"role": "system", "content": w_sys},
        {"role": "user", "content": f"TASK:\n{task_intent}\n\nSOURCES:\n{snippets}\n\nWrite the report now."},
    ], max_tokens=4000, timeout=420.0)
    calls += 1; tok_in += u2["in"]; tok_out += u2["out"]

    cites = re.findall(r"\((https?://[^)\s]+)\)", text2)
    return {
        "report": text2,
        "tokens_in": tok_in, "tokens_out": tok_out, "tokens_total": tok_in + tok_out,
        "model_calls": calls, "n_queries": len(queries), "n_pages": len(seen),
        "words": len(text2.split()), "n_citations": len(set(cites)),
        "latency_s": round(time.time() - t0, 1),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", required=True, help="comma-separated DashScope model ids")
    ap.add_argument("--tasks", required=True, help="comma-separated task ids (dr_cross_deep_000X)")
    ap.add_argument("--shim", default=os.environ.get("SHIM_URL", "http://localhost:8081"))
    ap.add_argument("--out", default=str(OUT_DIR / "efficiency.json"))
    ap.add_argument("--force", action="store_true", help="re-run even if the report already exists")
    args = ap.parse_args(argv)

    base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("JUDGE_API_KEY") or ""
    if not key:
        print("ERROR: set DASHSCOPE_API_KEY (source bailian.env)", flush=True)
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for model in models:
        safe = re.sub(r"[^a-z0-9.-]+", "-", model.lower())
        for task in tasks:
            rp = REPORT_DIR / f"eff-{safe}__{task}_matrix.md"
            if rp.exists() and rp.stat().st_size > 500 and not args.force:
                print(f"[eff] {model} {task}: SKIP (exists)", flush=True)
                continue
            intent = _load_intent(task)
            try:
                r = run_agent(intent, args.shim, base_url, key, model)
            except Exception as e:
                print(f"[eff] {model} {task} FAILED: {type(e).__name__}: {e}", flush=True)
                rows.append({"model": model, "task": task, "error": f"{type(e).__name__}: {e}"})
                continue
            rp.write_text(r.pop("report"), encoding="utf-8")
            r.update({"model": model, "task": task, "report_path": str(rp)})
            rows.append(r)
            print(f"[eff] {model} {task}: tok={r['tokens_total']} (in {r['tokens_in']}/out {r['tokens_out']}) "
                  f"words={r['words']} cites={r['n_citations']} {r['latency_s']}s", flush=True)

    Path(args.out).write_text(json.dumps({"rows": rows}, indent=1) + "\n", encoding="utf-8")
    print(f"[eff] wrote {args.out} ({len(rows)} rows)", flush=True)
    # Efficiency table to stdout.
    ok = [r for r in rows if "error" not in r]
    if ok:
        print("\nmodel".ljust(34) + "task".ljust(22) + "tok_total".rjust(10) + "words".rjust(8) + "cites".rjust(7))
        for r in ok:
            print(f"{r['model']:34}{r['task']:22}{r['tokens_total']:10}{r['words']:8}{r['n_citations']:7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
