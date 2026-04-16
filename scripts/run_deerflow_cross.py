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
    "dr_cross_v3_0002",
    "dr_cross_v3_0003",
    "dr_cross_v3_0004",
]


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
    runner_script = f'''
import sys, os, json, asyncio
sys.path.insert(0, ".")

os.environ["OPENAI_API_KEY"] = "{os.environ.get('OPENAI_API_KEY', os.environ.get('GLM_API_KEY', ''))}"
os.environ["OPENAI_API_BASE"] = "{os.environ.get('OPENAI_API_BASE', 'http://35.220.164.252:3888/v1/')}"
os.environ["FAST_LLM_MODEL"] = "glm-5"
os.environ["SMART_LLM_MODEL"] = "glm-5"
os.environ["STRATEGIC_LLM_MODEL"] = "glm-5"

# Monkey-patch DeerFlow tools with our multi-site scrapers
import requests
from langchain_core.tools import tool

@tool
def multi_search(query: str) -> str:
    """Search across sandbox sites (shopping, reddit, gitlab). Returns combined results."""
    results = {{}}
    # Shopping
    try:
        r = requests.get("http://localhost:7770/catalogsearch/result/", params={{"q": query}}, timeout=20)
        results["shopping"] = {{"status": r.status_code, "url": r.url, "text": r.text[:2000]}}
    except: pass
    # GitLab
    try:
        r = requests.get("http://localhost:8023/api/v4/projects", params={{"search": query, "per_page": 5}}, timeout=20)
        results["gitlab"] = r.json() if r.ok else []
    except: pass
    # Reddit
    try:
        r = requests.get(f"http://localhost:9999/f/technology", timeout=20)
        results["reddit"] = {{"text": r.text[:2000]}}
    except: pass
    return json.dumps(results, ensure_ascii=False)[:8000]

@tool
def multi_browse(url: str) -> str:
    """Fetch any sandbox URL. Returns the page content."""
    try:
        r = requests.get(url, timeout=20, allow_redirects=True)
        return r.text[:5000]
    except Exception as e:
        return json.dumps({{"error": str(e)}})

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
    result = subprocess.run(
        [DEERFLOW_PYTHON, str(script_path)],
        cwd=str(DEERFLOW_ROOT),
        capture_output=True, text=True,
        timeout=600,
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
            print(f"  TIMEOUT after 300s")
            (ROOT / "data" / "results" / f"deerflow_{tid}.md").write_text("(DeerFlow timeout)")
        except Exception as e:
            print(f"  ERROR: {e}")
            (ROOT / "data" / "results" / f"deerflow_{tid}.md").write_text(f"(DeerFlow error: {e})")
    print(f"\n{'='*60}")
    print("All DeerFlow cross-site tasks complete")


if __name__ == "__main__":
    main()
