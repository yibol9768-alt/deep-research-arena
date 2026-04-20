"""Run DeerFlow on cross-site tasks.

Runs each task as a subprocess inside the DeerFlow directory to avoid
src/ namespace collision between our project and DeerFlow.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEERFLOW_ROOT = ROOT / "third_party" / "deer-flow-v1"
DEERFLOW_PYTHON = str(DEERFLOW_ROOT / ".venv" / "bin" / "python")

# Load our .env
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

TASKS = [
    "dr_cross_v3_0001",
    "dr_cross_v3_0005",
    "dr_cross_v3_0006",
    "dr_cross_v3_0007",
]

_only = os.environ.get("DEERFLOW_ONLY_TASK")
if _only:
    TASKS = [_only if _only.startswith("dr_cross") else f"dr_cross_v3_{_only}"]


def _run_one_task(task_id: str):
    """Run DeerFlow for one task in a subprocess."""
    task_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site" / f"{task_id}.json"
    cfg = json.loads(task_path.read_text())
    out_path = ROOT / "data" / "results" / f"deerflow_{task_id}.md"

    sites = cfg.get("sites", ["shopping"])
    ms = cfg.get("markdown_spec", {})

    site_desc = {
        "shopping": f"Shopping (Magento): http://localhost:7770",
        "reddit": f"Reddit (Postmill): http://localhost:9999",
        "gitlab": f"GitLab: http://localhost:8023",
        "shopping_admin": f"Shopping Admin: http://localhost:7780",
    }
    sites_block = "\n".join(f"  - {site_desc.get(s, s)}" for s in sites)

    prompt = f"""{cfg['intent']}

## Available sandbox sites:
{sites_block}

## Research protocol (MANDATORY — override default researcher instructions):

**You are doing deep research, not surface search.** The search tools only give
you a listing overview — they are NOT sufficient on their own. You MUST drill
deeper into individual product / post pages.

1. **Shopping site**: after searching or browsing a category, you MUST call
   `crawl_tool` (= shop_browse) on **at least 6 individual product detail URLs**
   (ending in `.html` with a product slug, e.g.
   `sony-zx110nc-noise-cancelling-headphones.html`). Extract the exact price,
   star rating, and description from each PDP.
2. **Reddit site**: after listing a forum, you MUST `crawl_tool` on **at least
   4 individual post URLs** (form `/f/<board>/<id>/...`) and read the post body
   and top comments. Forum listing pages alone do NOT count.
3. Cite EVERY factual claim with a markdown link `[descriptive text](url)` —
   the URL must be a specific PDP or post URL you actually crawled, NOT the
   category/forum landing page.

**Do NOT write meta-commentary about tool failures, JavaScript rendering, or
extraction challenges.** The tools return full HTML. If a tool returns empty,
retry with a different URL. Do not include sections like "Methodology",
"Limitations", "Literature Review", "Survey Note", or "Future Research
Directions" — they waste words. Spend all words on actual product/forum
findings backed by crawled sources.

## Output requirements:
Write a **long-form markdown research report** (NOT JSON).
- Minimum {ms.get('min_words', 500)} words, {ms.get('min_paragraphs', 5)} paragraphs
- Include at least {ms.get('min_citations', 5)} inline citations as markdown links [text](url)
- Browse at least {ms.get('min_pages_browsed', 6)} distinct pages across the sites above
- Structure: introduction → findings per site → cross-site analysis → conclusion
- Every factual claim MUST have a citation linking to the sandbox page where you found it
"""

    # Write a self-contained runner script that runs inside DeerFlow's directory
    _escaped_prompt = prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    our_root = str(ROOT)
    runner_script = f'''
import sys, os, json, asyncio
sys.path.insert(0, ".")  # DeerFlow root first: src.* resolves to DeerFlow
# Our project root AFTER DeerFlow, so `integrations.*` imports us but `src.*`
# still picks DeerFlow's (we have src/ too, must not shadow)
sys.path.append("{our_root}")

# NOTE: API key / base URL / model come from .env in the parent shell
# (see scripts/run_deerflow_cross.py's env=). We deliberately do NOT
# override them here so operators can swap Coding-Plan vs general API
# at the .env layer without editing code.

# Rate-limit safety: serialise every openai chat-completions call and
# insert a sleep between calls. Defaults match a "slow & single" budget
# (one call at a time, 2 s gap). Tune via env vars.
import threading as _thr
import time as _time
_RATE_LOCK = _thr.Lock()
_LAST_CALL_T = [0.0]
_MIN_GAP = float(os.environ.get("OPENAI_MIN_GAP_S", "2.0"))
_RETRY_BASE = float(os.environ.get("OPENAI_RETRY_BASE_S", "15.0"))
_RETRY_MAX = int(os.environ.get("OPENAI_RETRY_MAX", "6"))

def _install_rate_limit():
    try:
        from openai.resources.chat.completions import completions as _comp
    except Exception:
        return
    _orig_create = _comp.Completions.create

    def _throttled(self, *a, **kw):
        for attempt in range(_RETRY_MAX + 1):
            with _RATE_LOCK:
                dt = _time.time() - _LAST_CALL_T[0]
                if dt < _MIN_GAP:
                    _time.sleep(_MIN_GAP - dt)
                try:
                    resp = _orig_create(self, *a, **kw)
                    _LAST_CALL_T[0] = _time.time()
                    return resp
                except Exception as e:
                    _LAST_CALL_T[0] = _time.time()
                    msg = str(e)
                    if ("429" in msg or "RateLimit" in msg or "rate_limit" in msg) and attempt < _RETRY_MAX:
                        backoff = _RETRY_BASE * (2 ** attempt)
                        print(f"[rate-limit attempt {{attempt+1}}] backoff {{backoff:.0f}}s: {{msg[:120]}}", flush=True)
                    else:
                        raise
            _time.sleep(backoff)
        # unreachable
        return _orig_create(self, *a, **kw)

    _comp.Completions.create = _throttled

_install_rate_limit()

_SHIM_URL = os.environ.get("DEERFLOW_SHIM_URL", "")

if _SHIM_URL:
    # Path B — ZERO-CODE integration via the sandbox search-API shim.
    # DeerFlow's default Tavily client is preserved; we only redirect
    # its base URL at the langchain-tavily layer. The shim serves
    # Tavily-schema responses backed by Magento + Postmill. The crawl
    # tool is ALSO routed through the shim's /extract (the only place
    # the shim surface needs to appear to the agent).
    os.environ.setdefault("TAVILY_API_KEY", "tvly-shim-fake")
    os.environ["SEARCH_API"] = "tavily"
    import langchain_tavily._utilities as _lt_util
    _lt_util.TAVILY_API_URL = _SHIM_URL
    try:
        import src.tools.tavily_search.tavily_search_api_wrapper as _tw
        _tw.TAVILY_API_URL = _SHIM_URL
    except Exception:
        pass

    # Crawl routing: replace crawl_tool with a thin client that POSTs to
    # the shim's /extract endpoint. No DeerFlow source code changes.
    import json as _json
    import requests as _req
    from langchain_core.tools import tool as _tool_dec

    @_tool_dec
    def _shim_crawl(url: str) -> str:
        \"\"\"Fetch a URL via the sandbox shim /extract endpoint.\"\"\"
        try:
            r = _req.post(
                f"{{_SHIM_URL}}/extract",
                json={{"urls": [url], "format": "markdown"}},
                timeout=30,
            )
            if r.status_code >= 400:
                return _json.dumps({{"error": f"status {{r.status_code}}", "url": url}})
            data = r.json()
            results = data.get("results") or []
            if not results:
                return _json.dumps({{"error": "no result", "url": url}})
            return _json.dumps(results[0], ensure_ascii=False)
        except Exception as e:
            return _json.dumps({{"error": str(e), "url": url}})

    import src.tools.crawl as _crawl_mod
    import src.graph.nodes as _nodes_mod
    _crawl_mod.crawl_tool = _shim_crawl
    _nodes_mod.crawl_tool = _shim_crawl

    print(f"[shim mode] TAVILY_API_URL={{_SHIM_URL}} ; crawl_tool -> shim /extract", flush=True)
else:
    # Path A — monkey-patch DeerFlow's search/crawl with our full
    # unified_adapter (historical path — kept for A/B comparison).
    from integrations.deerflow.unified_adapter import (
        multi_search, multi_browse,
        shop_search, shop_browse, shop_reviews,
        reddit_search, reddit_browse,
    )
    import src.tools.search as search_mod
    import src.tools.crawl as crawl_mod
    import src.graph.nodes as nodes_mod
    search_mod.get_web_search_tool = lambda *a, **kw: multi_search
    nodes_mod.get_web_search_tool = lambda *a, **kw: multi_search
    nodes_mod.crawl_tool = multi_browse
    crawl_mod.crawl_tool = multi_browse

from src.graph import build_graph
from src.config.configuration import get_recursion_limit

prompt = """{_escaped_prompt}"""

graph = build_graph()
initial_state = {{
    "messages": [{{"role": "user", "content": prompt}}],
    "auto_accepted_plan": True,
    "enable_background_investigation": False,
    "research_topic": prompt,
    "clarified_research_topic": prompt,
    "enable_clarification": False,
}}
config = {{
    "configurable": {{
        "thread_id": "dr-{task_id}",
        "max_plan_iterations": 1,
        "max_step_num": 6,
        "mcp_settings": {{"servers": {{}}}},
    }},
    "recursion_limit": get_recursion_limit(default=80),
}}

async def run():
    final_state = None
    async for s in graph.astream(input=initial_state, config=config, stream_mode="values"):
        final_state = s
        msgs = s.get("messages") or []
        if msgs:
            last = msgs[-1]
            role = getattr(last, "type", "") or getattr(last, "role", "")
            name = getattr(last, "name", "") or ""
            content = getattr(last, "content", "")
            preview = content if isinstance(content, str) else str(content)
            print(f"[{{role}}/{{name}}] {{preview[:300]}}")
    if final_state:
        rep = final_state.get("final_report") or final_state.get("reporter_output") or ""
        print(f"REPORT_LENGTH={{len(rep)}}")
        with open("{out_path}", "w") as f:
            f.write(rep or "(no report)")

asyncio.run(run())
'''

    script_path = ROOT / "data" / "results" / f"_deerflow_runner_{task_id}.py"
    script_path.write_text(runner_script)

    print(f"\n{'='*60}")
    print(f"DeerFlow: {task_id}")
    print(f"{'='*60}")

    t0 = time.time()
    # Runtime can be long when the LLM endpoint is rate-limited (the
    # openai rate-limit wrapper in runner_script sleeps + exponential
    # backoff). Give it a half-hour; still bounded.
    _timeout_s = int(os.environ.get("DEERFLOW_TASK_TIMEOUT_S", "1800"))
    result = subprocess.run(
        [DEERFLOW_PYTHON, str(script_path)],
        cwd=str(DEERFLOW_ROOT),
        capture_output=True, text=True,
        timeout=_timeout_s,
        env={**os.environ},
    )
    elapsed = time.time() - t0

    if result.returncode == 0:
        # Check output file
        if out_path.exists():
            content = out_path.read_text()
            print(f"  completed in {elapsed:.0f}s, report={len(content)} chars")
        else:
            print(f"  completed in {elapsed:.0f}s but no output file")
    else:
        print(f"  FAILED after {elapsed:.0f}s (exit {result.returncode})")
        stderr_last = (result.stderr or "")[-500:]
        print(f"  stderr: {stderr_last}")
        out_path.write_text(f"(DeerFlow error: exit {result.returncode})")

    # Cleanup temp script
    script_path.unlink(missing_ok=True)


def main():
    for tid in TASKS:
        try:
            _run_one_task(tid)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT")
            (ROOT / "data" / "results" / f"deerflow_{tid}.md").write_text("(DeerFlow timeout)")
        except Exception as e:
            print(f"  ERROR: {e}")
            (ROOT / "data" / "results" / f"deerflow_{tid}.md").write_text(f"(DeerFlow error: {e})")
    print(f"\n{'='*60}")
    print("All DeerFlow cross-site tasks complete")


if __name__ == "__main__":
    main()
