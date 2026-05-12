"""Tongyi DeepResearch runner for the deep-research benchmark.

Integrates Alibaba-NLP/DeepResearch (Tongyi-DeepResearch-30B-A3B) against
our sandbox as a subprocess.  The Tongyi agent is a ReAct loop built on
the qwen_agent framework with five tools: Search, Visit, Scholar,
PythonInterpreter, and FileParser.

Instead of running the 30B MoE model locally (which requires ~60GB VRAM
in bf16 -- too much for the RTX 5090's 32GB), we redirect the OpenAI
client in react_agent.py to our ds_proxy (DeepSeek V4 flash).  The
system prompt and tool format are generic enough for any instruction-
following model.

Configuration approach (all via runtime patching in the driver script):
  - LLM: OpenAI client pointed at ds_proxy (localhost:8088/v1) instead
         of a local vLLM server.
  - Search: Serper API replaced with a shim-compatible implementation
         that POSTs to our Tavily-compatible sandbox shim.
  - Visit: Jina.ai replaced with direct HTTP fetch + LLM summarization
         via ds_proxy (sandbox URLs are localhost, no Jina needed).
  - Scholar: Disabled (returns empty -- sandbox has no Google Scholar).
  - Python: Disabled (returns error -- sandbox has no SandboxFusion).
  - FileParser: Disabled.

The driver script is generated at runtime, written to the repo dir,
and executed as a subprocess in the .venv-tongyi venv.

Architecture:
  1. Write a driver script that replaces tools and configures the LLM
  2. Run the driver in .venv-tongyi Python with cwd=inference/
  3. Parse the report from stdout sentinel markers

Dependencies on westd:
  - /opt/deep_reserch/third_party/tongyi-deep-research/ (cloned repo)
  - /opt/deep_reserch/.venv-tongyi/ (venv with qwen-agent, openai, etc.)
  - Sandbox services (shim:8081, shopping:7770, reddit:9999, wiki:8090)
  - ds_proxy on localhost:8088

Usage (standalone test):
    python3 scripts/runners/tongyi_runner.py \\
        "Compare headphone prices across stores" \\
        --model deepseek-v4-flash \\
        --shim-url http://localhost:8081 \\
        --proxy-url http://localhost:8088/v1
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from ._runner_lock import runner_exclusive_lock

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
TONGYI_ROOT = ROOT / "third_party" / "tongyi-deep-research"
TONGYI_INFERENCE = TONGYI_ROOT / "inference"
TONGYI_PYTHON = str(ROOT / ".venv-tongyi" / "bin" / "python")

# Generous timeout: the ReAct loop can run many turns with slow models.
DEFAULT_TIMEOUT_S = 1800

# Max LLM calls per run (Tongyi default is 100, we cap at 50 for benchmark).
MAX_LLM_CALLS = 50

# Max tokens for context window management.
MAX_CONTEXT_TOKENS = 100000


def _build_driver_script(
    intent: str,
    shim_url: str,
    proxy_url: str,
    model: str,
    api_key: str = "anything",
) -> str:
    """Build the Python driver script that runs inside .venv-tongyi.

    This script is executed with cwd=TONGYI_INFERENCE so that
    ``from prompt import *`` resolves to Tongyi's own modules.

    The script replaces the tools and LLM configuration without modifying
    the original source files.  It reimplements the ReAct loop from
    react_agent.py with our sandbox-compatible tools.

    Key adaptations:
      1. Search tool: replaced to POST to our Tavily-compatible shim
         instead of google.serper.dev.
      2. Visit tool: replaced to fetch sandbox URLs directly (no Jina.ai)
         and summarize via ds_proxy LLM.
      3. Scholar tool: returns "no results" (sandbox has no Scholar).
      4. LLM client: pointed at ds_proxy instead of local vLLM.
      5. Token counting: uses tiktoken instead of local HF tokenizer.
    """
    # Write intent to a temp file to avoid string escaping issues with long intents
    # The driver script reads it from this path.
    intent_file = str(Path(TONGYI_ROOT) / "inference" / "_benchmark_intent.txt")
    Path(intent_file).write_text(intent, encoding="utf-8")

    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated Tongyi DeepResearch driver for benchmark.\"\"\"
        import os, sys, json, json5, time, re, random
        from datetime import datetime

        # Purge proxy env vars to prevent leaking to sandbox requests
        for _pv in list(os.environ):
            if _pv.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy','ftp_proxy'):
                del os.environ[_pv]
        os.environ['NO_PROXY'] = '*'

        # Prevent HuggingFace downloads
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'

        from openai import OpenAI
        import requests as _req
        import tiktoken

        # ----------------------------------------------------------------
        # Config
        # ----------------------------------------------------------------
        PROXY_URL = '{proxy_url}'
        SHIM_URL = '{shim_url}'
        MODEL = '{model}'
        API_KEY = '{api_key}'
        MAX_LLM_CALLS = {MAX_LLM_CALLS}
        MAX_CONTEXT_TOKENS = {MAX_CONTEXT_TOKENS}

        # Import Tongyi's system prompt
        sys.path.insert(0, '.')
        from prompt import SYSTEM_PROMPT, EXTRACTOR_PROMPT

        # ----------------------------------------------------------------
        # LLM client (pointed at ds_proxy)
        # ----------------------------------------------------------------
        _client = OpenAI(api_key=API_KEY, base_url=PROXY_URL, timeout=600.0)

        def call_llm(messages, max_retries=5):
            for attempt in range(max_retries):
                try:
                    resp = _client.chat.completions.create(
                        model=MODEL,
                        messages=messages,
                        stop=["\\n<tool_response>", "<tool_response>"],
                        temperature=0.7,
                        max_tokens=8192,
                    )
                    content = resp.choices[0].message.content
                    if content and content.strip():
                        return content.strip()
                except Exception as e:
                    print(f"LLM call attempt {{attempt+1}} failed: {{e}}", flush=True)
                if attempt < max_retries - 1:
                    sleep_t = min(2 ** attempt + random.uniform(0, 1), 30)
                    time.sleep(sleep_t)
            return "Error: LLM call failed after retries."

        def call_llm_summarize(messages, max_retries=3):
            \"\"\"Summarize content via LLM (for visit tool).\"\"\"
            for attempt in range(max_retries):
                try:
                    resp = _client.chat.completions.create(
                        model=MODEL,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=4096,
                    )
                    content = resp.choices[0].message.content
                    if content and content.strip():
                        return content.strip()
                except Exception as e:
                    if attempt == max_retries - 1:
                        return ""
            return ""

        # ----------------------------------------------------------------
        # Token counting (tiktoken instead of local HF tokenizer)
        # ----------------------------------------------------------------
        _encoding = tiktoken.get_encoding("cl100k_base")

        def count_tokens(messages):
            total = 0
            for m in messages:
                total += len(_encoding.encode(m.get('content', '')))
            return total

        # ----------------------------------------------------------------
        # Tool: Search (via our Tavily-compatible shim)
        # ----------------------------------------------------------------
        def tool_search(params):
            \"\"\"Search using the sandbox shim (Tavily-compatible).\"\"\"
            query = params.get('query', '')
            if isinstance(query, list):
                queries = query
            elif isinstance(query, str):
                queries = [query]
            else:
                return "Error: query must be a string or list of strings."

            all_results = []
            for i, q in enumerate(queries):
                try:
                    resp = _req.post(
                        f'{{SHIM_URL}}/search',
                        json={{'query': q, 'max_results': 10, 'include_raw_content': False}},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    results = data.get('results', [])
                    formatted = []
                    for j, r in enumerate(results, 1):
                        title = r.get('title', 'No title')
                        link = r.get('url', '')
                        snippet = r.get('content', 'No snippet')
                        formatted.append(
                            f"{{j}}. [{{title}}]({{link}})\\n"
                            f"   Snippet: {{snippet}}"
                        )
                    if formatted:
                        all_results.append(f"Results for query '{{q}}':\\n" + "\\n".join(formatted))
                    else:
                        all_results.append(f"No results found for query '{{q}}'.")
                except Exception as e:
                    all_results.append(f"Search error for '{{q}}': {{e}}")
            return "\\n\\n---\\n\\n".join(all_results)

        # ----------------------------------------------------------------
        # Tool: Visit (direct fetch + LLM summarization)
        # ----------------------------------------------------------------
        def tool_visit(params):
            \"\"\"Visit a URL, fetch content, and summarize via LLM.\"\"\"
            url = params.get('url', '')
            goal = params.get('goal', 'Extract useful information')

            if isinstance(url, list):
                parts = []
                for u in url:
                    parts.append(_visit_one(u, goal))
                return "\\n=======\\n".join(parts)
            else:
                return _visit_one(url, goal)

        def _visit_one(url, goal):
            \"\"\"Fetch and summarize a single URL.\"\"\"
            try:
                resp = _req.get(url, timeout=30, headers={{'User-Agent': 'Mozilla/5.0'}})
                if resp.status_code >= 400:
                    return f"Failed to access {{url}}: HTTP {{resp.status_code}}"
                text = resp.text
                # Strip HTML tags for a rough text extraction
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\\s+', ' ', text).strip()
                # Truncate to fit in LLM context
                if len(text) > 80000:
                    text = text[:80000]

                # Summarize via LLM using Tongyi's EXTRACTOR_PROMPT
                try:
                    extraction_prompt = EXTRACTOR_PROMPT.format(
                        webpage_content=text, goal=goal
                    )
                except Exception:
                    extraction_prompt = (
                        f"Extract information relevant to this goal: {{goal}}\\n\\n"
                        f"Content:\\n{{text[:60000]}}"
                    )

                msgs = [{{"role": "user", "content": extraction_prompt}}]
                raw = call_llm_summarize(msgs)

                if raw:
                    # Try to parse as JSON (Tongyi format)
                    try:
                        raw_clean = raw.replace('```json', '').replace('```', '').strip()
                        parsed = json.loads(raw_clean)
                        info = f"The useful information in {{url}} for user goal {{goal}} as follows:\\n\\n"
                        info += "Evidence in page:\\n" + str(parsed.get('evidence', '')) + "\\n\\n"
                        info += "Summary:\\n" + str(parsed.get('summary', '')) + "\\n\\n"
                        return info
                    except (json.JSONDecodeError, KeyError):
                        return f"Summary of {{url}} for goal '{{goal}}':\\n{{raw}}"
                else:
                    # Fall back to raw text snippet
                    return f"Content from {{url}} (raw, truncated):\\n{{text[:3000]}}"

            except Exception as e:
                return f"Error visiting {{url}}: {{e}}"

        # ----------------------------------------------------------------
        # Tool: Scholar (disabled -- sandbox has no Google Scholar)
        # ----------------------------------------------------------------
        def tool_scholar(params):
            return "Google Scholar is not available in this environment. Use the search tool instead."

        # ----------------------------------------------------------------
        # Tool: Python interpreter (disabled)
        # ----------------------------------------------------------------
        def tool_python(params):
            return "Python interpreter is not available in this environment."

        # ----------------------------------------------------------------
        # Tool: File parser (disabled)
        # ----------------------------------------------------------------
        def tool_file(params):
            return "File parser is not available in this environment."

        # ----------------------------------------------------------------
        # Tool dispatch
        # ----------------------------------------------------------------
        TOOL_MAP = {{
            'search': tool_search,
            'visit': tool_visit,
            'google_scholar': tool_scholar,
            'PythonInterpreter': tool_python,
            'parse_file': tool_file,
        }}

        def dispatch_tool(tool_name, tool_args):
            if tool_name in TOOL_MAP:
                return TOOL_MAP[tool_name](tool_args)
            return f"Error: Tool '{{tool_name}}' not found."

        # ----------------------------------------------------------------
        # Main ReAct loop (reimplemented from react_agent.py)
        # ----------------------------------------------------------------
        def today_date():
            return datetime.now().strftime("Today is %Y-%m-%d, %A.")

        question = open("{intent_file}", "r", encoding="utf-8").read().strip()
        system_prompt = SYSTEM_PROMPT + today_date()
        messages = [
            {{"role": "system", "content": system_prompt}},
            {{"role": "user", "content": question}},
        ]

        num_calls = MAX_LLM_CALLS
        start_time = time.time()

        print(f"[tongyi-dr] Starting ReAct loop, max_calls={{MAX_LLM_CALLS}}", flush=True)

        round_num = 0
        while num_calls > 0:
            # Timeout check (30 min)
            if time.time() - start_time > 1800:
                print("[tongyi-dr] Timeout reached (30 min)", flush=True)
                break

            round_num += 1
            num_calls -= 1

            content = call_llm(messages)
            print(f"[tongyi-dr] Round {{round_num}}: {{content[:300]}}", flush=True)

            # Strip any leaked tool_response
            if '<tool_response>' in content:
                content = content[:content.find('<tool_response>')]

            messages.append({{"role": "assistant", "content": content.strip()}})

            # Check for answer
            if '<answer>' in content and '</answer>' in content:
                print("[tongyi-dr] Answer found!", flush=True)
                break

            # Check for tool call
            if '<tool_call>' in content and '</tool_call>' in content:
                tool_block = content.split('<tool_call>')[1].split('</tool_call>')[0]
                try:
                    if 'python' in tool_block.lower() and '<code>' in content:
                        result = tool_python({{}})
                    else:
                        parsed = json5.loads(tool_block)
                        tool_name = parsed.get('name', '')
                        tool_args = parsed.get('arguments', {{}})
                        result = dispatch_tool(tool_name, tool_args)
                except Exception as e:
                    result = f"Error: Tool call parsing failed: {{e}}"

                result_msg = "<tool_response>\\n" + result + "\\n</tool_response>"
                messages.append({{"role": "user", "content": result_msg}})

            # Token count check
            token_count = count_tokens(messages)
            print(f"[tongyi-dr] Round {{round_num}}, tokens: {{token_count}}", flush=True)

            if token_count > MAX_CONTEXT_TOKENS:
                print(f"[tongyi-dr] Token limit reached: {{token_count}}", flush=True)
                messages.append({{
                    "role": "user",
                    "content": (
                        "You have reached the maximum context length. "
                        "Stop making tool calls and provide your final answer "
                        "based on all information gathered so far. "
                        "Format: <answer>your comprehensive answer</answer>"
                    ),
                }})
                content = call_llm(messages)
                messages.append({{"role": "assistant", "content": content.strip()}})
                break

            if num_calls <= 0:
                messages.append({{
                    "role": "user",
                    "content": (
                        "You have used all available tool calls. "
                        "Provide your final answer now. "
                        "Format: <answer>your comprehensive answer</answer>"
                    ),
                }})
                content = call_llm(messages)
                messages.append({{"role": "assistant", "content": content.strip()}})
                break

        # ----------------------------------------------------------------
        # Extract the final answer / report
        # ----------------------------------------------------------------
        elapsed = time.time() - start_time
        print(f"[tongyi-dr] Loop done after {{round_num}} rounds, {{elapsed:.0f}}s", flush=True)

        # Collect the full answer
        last_content = messages[-1].get('content', '') if messages else ''
        report = ''

        if '<answer>' in last_content and '</answer>' in last_content:
            report = last_content.split('<answer>')[1].split('</answer>')[0].strip()
        else:
            # No <answer> tags -- use the last assistant message as report
            for m in reversed(messages):
                if m.get('role') == 'assistant':
                    c = m.get('content', '')
                    if '<answer>' in c and '</answer>' in c:
                        report = c.split('<answer>')[1].split('</answer>')[0].strip()
                        break
                    elif len(c) > 200:
                        report = c
                        break

        if not report:
            report = "(Tongyi DeepResearch produced no answer)"

        # Emit the report
        print("===TONGYI_REPORT_START===", flush=True)
        print(report, flush=True)
        print("===TONGYI_REPORT_END===", flush=True)
    """)


def _extract_report(stdout: str) -> str:
    """Extract the report from the sentinel-delimited block in stdout."""
    start = "===TONGYI_REPORT_START==="
    end = "===TONGYI_REPORT_END==="
    si = stdout.find(start)
    ei = stdout.find(end)
    if si == -1 or ei == -1 or ei <= si:
        return ""
    return stdout[si + len(start):ei].strip()


# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/tongyi-dr__<task>_matrix.score.json
AGENT_NAME = "tongyi-dr"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Run Tongyi DeepResearch and return the markdown report.

    Args:
        intent: The research query / task description.
        model: OpenAI-compatible model name (e.g. "deepseek-v4-flash").
        shim_url: Tavily-compatible search shim (e.g. "http://localhost:8081").
        proxy_url: OpenAI-compatible LLM proxy (e.g. "http://localhost:8088/v1").
        timeout_s: Subprocess timeout in seconds.

    Returns:
        The research report as a string, or an error string prefixed with
        "(tongyi-dr ...)" on failure.
    """
    # Validate paths
    inference_dir = TONGYI_INFERENCE
    if not inference_dir.exists():
        return f"(tongyi-dr error: inference dir not found at {inference_dir})"
    tongyi_python = Path(TONGYI_PYTHON)
    if not tongyi_python.exists():
        return f"(tongyi-dr error: venv not found at {tongyi_python})"

    api_key = os.environ.get("OPENAI_API_KEY", "anything")

    # Write the driver script
    driver_code = _build_driver_script(intent, shim_url, proxy_url, model, api_key)
    driver_path = inference_dir / "_benchmark_driver.py"

    # Per-agent lock so parallel workers don't trample the shared driver path.
    _lock_cm = runner_exclusive_lock("tongyi-dr")
    _lock_cm.__enter__()

    try:
        driver_path.write_text(driver_code)

        # Build subprocess environment
        env = {**os.environ}

        # Remove proxy env vars
        for key in list(env.keys()):
            if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy',
                                'ftp_proxy', 'no_proxy'):
                del env[key]
        env["NO_PROXY"] = "*"

        # Disable HuggingFace downloads
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"

        # Set API env vars (used by Tongyi's visit tool's call_server)
        env["API_KEY"] = api_key
        env["API_BASE"] = proxy_url
        env["SUMMARY_MODEL_NAME"] = model

        logger.info(
            "Starting Tongyi DeepResearch: model=%s shim=%s proxy=%s",
            model, shim_url, proxy_url,
        )

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [TONGYI_PYTHON, str(driver_path)],
                cwd=str(inference_dir),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
            ),
        )
        elapsed = time.time() - t0

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            logger.warning(
                "Tongyi DR exited %d after %.0fs\nstderr tail: %s",
                proc.returncode, elapsed, stderr[-1500:],
            )

        # Extract the report
        report = _extract_report(stdout)

        if not report:
            logger.warning("No report extracted from Tongyi DR output")
            snippet = stdout[-2000:] if stdout else "(no stdout)"
            err_snippet = stderr[-1500:] if stderr else "(no stderr)"
            return (
                f"(tongyi-dr produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n"
                f"--- stdout tail ---\n{snippet}\n\n"
                f"--- stderr tail ---\n{err_snippet}"
            )

        logger.info(
            "Tongyi DR completed in %.0fs, report=%d chars",
            elapsed, len(report),
        )
        return report

    except subprocess.TimeoutExpired:
        logger.error("Tongyi DR timed out after %ds", timeout_s)
        return f"(tongyi-dr timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("Tongyi DR runner error")
        return f"(tongyi-dr error: {type(e).__name__}: {e})"
    finally:
        # Clean up driver script
        if driver_path.exists():
            driver_path.unlink(missing_ok=True)
        try:
            _lock_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("tongyi-dr lock release failed")


# ---------------------------------------------------------------------------
# CLI entry point for standalone testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Tongyi DeepResearch benchmark"
    )
    parser.add_argument("intent", help="Research query")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--proxy-url", default="http://localhost:8088/v1")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--output", "-o", help="Write report to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    report = asyncio.run(
        run(
            intent=args.intent,
            model=args.model,
            shim_url=args.shim_url,
            proxy_url=args.proxy_url,
            timeout_s=args.timeout,
        )
    )

    if args.output:
        Path(args.output).write_text(report)
        print(f"Report written to {args.output} ({len(report)} chars)")
    else:
        print(report)
