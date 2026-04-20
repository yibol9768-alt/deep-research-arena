"""GPT-5 family agent runner (gpt-5.4 / gpt-5-chat-latest / gpt-5 / gpt-5-mini).

Minimal tool-calling loop:
  search(query) -> top-5 results via shim /v1/search
  scrape(url)   -> body text via shim /v1/scrape
  finish(markdown_report) -> final report

Follows the same output conventions as scripts/run_gpt_researcher.py so the
rescore pipeline picks it up:
  data/results/<tag>_<task_id>.answer.md
  data/results/final_<tag>_<task_id>.json  (scored later by rescore_*)

Environment:
  OPENAI_BASE_URL   default http://35.164.11.19:3887/v1   (set to https://api.openai.com/v1 for official)
  OPENAI_API_KEY    proxy or official key (required)
  SHIM_URL          default http://localhost:8081         (on westd it's usually this)
  GPT5_MODEL        default gpt-5.4
  GPT5_TAG          default gpt5-react                    (name used in final_*.json / leaderboard)
  INPUT_CAP         default 200000
  OUTPUT_CAP        default 20000
  MAX_STEPS         default 12
  TASKS             comma-separated task_ids; default = 4 dr_cross_v3 baseline

Usage:
  python scripts/run_gpt5.py
  GPT5_MODEL=gpt-5-chat-latest GPT5_TAG=gpt5chat-react python scripts/run_gpt5.py
  TASKS=dr_cross_v3_0108,dr_cross_v3_0109 python scripts/run_gpt5.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.budget import TokenBudgetGuard, BudgetExceeded  # noqa: E402

BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://35.164.11.19:3887/v1").rstrip("/")
API_KEY = os.environ.get("OPENAI_API_KEY") or ""
SHIM = os.environ.get("SHIM_URL", "http://localhost:8081").rstrip("/")
MODEL = os.environ.get("GPT5_MODEL", "gpt-5.4")
TAG = os.environ.get("GPT5_TAG", "gpt5-react")
INPUT_CAP = int(os.environ.get("INPUT_CAP", "200000"))
OUTPUT_CAP = int(os.environ.get("OUTPUT_CAP", "20000"))
MAX_STEPS = int(os.environ.get("MAX_STEPS", "12"))

TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site"
OUT_DIR = ROOT / "data" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the sandboxed web (magento/postmill/wikipedia via shim). Returns top-5 {title,url,snippet}.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape",
            "description": "Fetch body text of a URL (via shim /v1/scrape). Use on results from search.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Submit final markdown research report. Include inline [text](url) citations for every factual claim.",
            "parameters": {
                "type": "object",
                "properties": {"markdown_report": {"type": "string"}},
                "required": ["markdown_report"],
            },
        },
    },
]


def _unwrap_markdown_json(content: str) -> str:
    """Some models (notably gpt-5-chat-latest) emit finish's arguments
    as JSON content with real newlines (invalid JSON for json.loads but
    readable). Extract the markdown_report value via substring scan."""
    s = content.strip()
    if not (s.startswith('{"markdown_report"') or s.startswith("{'markdown_report'")):
        return ""
    # Try real JSON first (works if model escaped newlines properly)
    try:
        obj = json.loads(s)
        v = obj.get("markdown_report") if isinstance(obj, dict) else None
        if isinstance(v, str) and v.strip():
            return v
    except Exception:
        pass
    # Fallback: take substring between "markdown_report":" and final "}
    import re
    m = re.search(r'"markdown_report"\s*:\s*"', s)
    if not m:
        return ""
    body = s[m.end():]
    # Strip trailing "} or " } etc.
    body = re.sub(r'"\s*\}\s*$', "", body)
    # Unescape any escaped quotes / backslashes
    body = body.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
    return body.strip()


def _shim_search(query: str) -> list[dict]:
    """Tavily-compatible: POST /search with {query, max_results}."""
    try:
        r = requests.post(
            f"{SHIM}/search",
            json={"query": query, "max_results": 5},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        # Slim each result to avoid blowing context: keep title/url/snippet.
        return [
            {
                "title": str(x.get("title", ""))[:140],
                "url": x.get("url", ""),
                "snippet": str(x.get("content") or x.get("snippet") or "")[:500],
            }
            for x in results
        ]
    except Exception as e:
        return [{"error": str(e)[:200]}]


def _shim_scrape(url: str) -> str:
    """Tavily-compatible: POST /extract with {urls:[url]}."""
    try:
        r = requests.post(
            f"{SHIM}/extract",
            json={"urls": [url]},
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return "[scrape: no content]"
        body = results[0].get("raw_content") or results[0].get("content") or ""
        return body[:8000]
    except Exception as e:
        return f"[scrape error: {e}]"


def _call_llm(messages: list[dict], guard: TokenBudgetGuard, force_tool: str | None = None) -> dict:
    guard.check_before_call()
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body: dict = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "max_tokens": min(3000, max(200, OUTPUT_CAP - guard.output_used)),
    }
    if force_tool:
        body["tool_choice"] = {"type": "function", "function": {"name": force_tool}}
    else:
        body["tool_choice"] = "auto"
    r = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=180)
    r.raise_for_status()
    data = r.json()
    guard.record_usage_obj(data.get("usage", {}))
    return data["choices"][0]["message"]


SYSTEM_PROMPT = """You are a deep-research agent. For the given task:

1. Use `search` to find relevant sources in the sandbox (magento shopping, postmill forum, wikipedia).
2. Use `scrape` to read page bodies of promising URLs.
3. Produce a markdown report with:
   - At least 800 words
   - At least 10 paragraphs
   - At least 8 inline citations in the form [descriptive text](http://...)
   - Concrete facts (prices, ratings, quotes) grounded in the scraped sources
4. Submit via `finish(markdown_report=...)`.

Only cite URLs you actually retrieved via search/scrape. Do not fabricate URLs.
You have a limited token budget; be efficient. Do not exceed 12 steps.
"""


def run_task(task_id: str) -> dict:
    cfg_path = TASKS_DIR / f"{task_id}.json"
    if not cfg_path.exists():
        return {"error": f"task not found: {task_id}"}
    cfg = json.loads(cfg_path.read_text())
    intent = cfg.get("intent") or cfg.get("description") or ""

    guard = TokenBudgetGuard(input_cap=INPUT_CAP, output_cap=OUTPUT_CAP)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Task {task_id}:\n{intent}"},
    ]

    t0 = time.time()
    final_report = ""
    capped = False
    trace: list[dict] = []

    for step in range(MAX_STEPS):
        try:
            msg = _call_llm(messages, guard)
        except BudgetExceeded as e:
            capped = True
            trace.append({"step": step, "event": "budget_exceeded", "detail": str(e)})
            break
        except Exception as e:
            trace.append({"step": step, "event": "llm_error", "detail": str(e)[:300]})
            break

        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # No tool call this turn. Might be an empty reply or plain markdown.
            content = msg.get("content") or ""
            trace.append({"step": step, "event": "no_tool_call",
                          "content_len": len(content),
                          "content_head": content[:120]})
            if len(content) >= 400:
                # Long plain reply. gpt-5-chat-latest sometimes emits the tool
                # call arguments as JSON content instead of a proper tool_call;
                # detect {"markdown_report":"..."} wrapping and unwrap.
                unwrapped = _unwrap_markdown_json(content)
                final_report = unwrapped or content
                break
            # Otherwise nudge the agent back on track.
            messages.append({
                "role": "user",
                "content": "Continue the research or call `finish(markdown_report=...)` with your final report now.",
            })
            continue

        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except Exception:
                args = {}
            trace.append({"step": step, "tool": name, "args_preview": str(args)[:200]})

            if name == "search":
                result = _shim_search(args.get("query", ""))
                content = json.dumps(result, ensure_ascii=False)[:4000]
            elif name == "scrape":
                content = _shim_scrape(args.get("url", ""))
            elif name == "finish":
                final_report = args.get("markdown_report", "")
                content = "accepted"
            else:
                content = f"[unknown tool: {name}]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": content,
            })

        if any(tc["function"]["name"] == "finish" for tc in tool_calls):
            break

    # Forced-finish fallback: if loop ended without `finish`, nudge agent
    # with a finish-only request using the context gathered so far.
    if not final_report and not capped:
        try:
            messages.append({
                "role": "user",
                "content": (
                    "You have exhausted the tool-call budget. Using the search/scrape "
                    "results gathered so far, call `finish` now with your best markdown "
                    "report. Do not call any other tool. If you truly cannot produce "
                    "a grounded report, call finish with a short statement explaining why."
                ),
            })
            msg = _call_llm(messages, guard, force_tool="finish")
            for tc in (msg.get("tool_calls") or []):
                if tc["function"]["name"] == "finish":
                    try:
                        args = json.loads(tc["function"]["arguments"] or "{}")
                        final_report = args.get("markdown_report", "")
                    except Exception:
                        pass
                    break
            if not final_report and msg.get("content"):
                final_report = msg["content"]
            trace.append({"step": "forced_finish", "got_report": bool(final_report),
                          "report_len": len(final_report or "")})
        except Exception as e:
            trace.append({"step": "forced_finish_error", "detail": str(e)[:200]})

    elapsed = time.time() - t0
    answer_path = OUT_DIR / f"{TAG}_{task_id}.answer.md"
    answer_path.write_text(final_report or "[empty — agent failed to finish]")

    # Minimal meta file; full pillar scoring happens in rescore_*.py.
    meta = {
        "agent": TAG,
        "task_id": task_id,
        "model": MODEL,
        "elapsed_s": round(elapsed, 2),
        "steps": len([t for t in trace if "tool" in t]),
        "budget_snapshot": guard.snapshot(),
        "capped": capped,
        "trace_len": len(trace),
        "trace_tail": trace[-10:],
        "answer_words": len((final_report or "").split()),
    }
    meta_path = OUT_DIR / f"{TAG}_{task_id}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return meta


def main() -> int:
    tasks_env = os.environ.get("TASKS", "")
    if tasks_env:
        tasks = [t.strip() for t in tasks_env.split(",") if t.strip()]
    else:
        tasks = [
            "dr_cross_v3_0001",
            "dr_cross_v3_0005",
            "dr_cross_v3_0006",
            "dr_cross_v3_0007",
        ]

    if not API_KEY:
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    print(f"model={MODEL} tag={TAG} base_url={BASE_URL}")
    print(f"budget: input_cap={INPUT_CAP} output_cap={OUTPUT_CAP} max_steps={MAX_STEPS}")
    print(f"tasks: {tasks}")

    summary = []
    for t in tasks:
        print(f"\n>>> {t}")
        m = run_task(t)
        print(f"    {m}")
        summary.append(m)

    summary_path = OUT_DIR / f"{TAG}_run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nsummary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
