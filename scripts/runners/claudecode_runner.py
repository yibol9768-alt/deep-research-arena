"""Claude Code CLI as a deep-research agent.

Architecture (SSH-driven, runner orchestrates from any host that can reach 5090):

    runner (any host with ssh 5090)
        │  scp intent + ps1 driver
        │  ssh 5090 powershell -File driver.ps1
        ▼
    5090 Windows
        claude.exe --print --disallowedTools WebSearch WebFetch
        --append-system-prompt <sandbox-only directive>
            │  ANTHROPIC_BASE_URL=http://127.0.0.1:3456
            ▼
        ccr (claude-code-router)   --Anthropic→OpenAI Chat translation-->
            │  http://127.0.0.1:8088/v1/chat/completions
            ▼
        ds_proxy  --inject thinking:disabled, strip <think>-->
            │  https://api.deepseek.com/v1
            ▼
        DeepSeek V4 flash

Tooling lockdown (fairness with other DR baselines):
    - claude's native WebSearch + WebFetch are stripped via --disallowedTools
    - --append-system-prompt steers the model to issue
      `curl http://localhost:8081/search ...` via the Bash tool
    - The three sandbox URLs (Magento 7770, Postmill 9999, Kiwix 8090) are
      enumerated explicitly in the system prompt so the model knows the only
      reachable network surface.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
AGENT_NAME = "claude-code"

# Workstream C — strict-sandbox eligibility.
# claude-code supports `--allowed-tools` with argument patterns. Under
# strict_sandbox=True we replace the disallowlist (WebSearch / WebFetch /
# NotebookEdit) with a WHITELIST that admits only Read/Write/Edit/Glob/Grep
# plus Bash patterns that match `curl http://localhost*` or
# `curl http://127.0.0.1*`. This closes the long-standing Bash-curl gap
# where the model could `curl https://en.wikipedia.org/...` from inside an
# otherwise locked-down session because Bash itself was implicitly allowed.
STRICT_SANDBOX_ELIGIBLE = True

DEFAULT_TIMEOUT_S = 1800
SSH_HOST = os.environ.get("CLAUDE_CODE_SSH_HOST", "5090")
REMOTE_DIR_WIN = os.environ.get("CLAUDE_CODE_REMOTE_DIR", "C:/tools/cc_runner")
CCR_BASE_URL = os.environ.get("CLAUDE_CODE_CCR_URL", "http://127.0.0.1:3456")


_PS_DRIVER_TEMPLATE = r"""param(
  [string]$IntentPath,
  [string]$ReportPath,
  [string]$StdoutPath,
  [string]$WorkDir,
  [string]$ShimUrl,
  [string]$ShoppingUrl,
  [string]$RedditUrl,
  [string]$WikipediaUrl
)
$ErrorActionPreference = 'Continue'
$env:ANTHROPIC_BASE_URL = '__CCR_URL__'
$env:ANTHROPIC_AUTH_TOKEN = 'anything'
$env:ANTHROPIC_API_KEY = 'anything'

# Pre-create the report file empty so claude's Write tool sees a path that
# exists in an allowed directory.  Force the parent directory too.
$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
Set-Content -Path $ReportPath -Value '' -Encoding UTF8

# Move into a clean WorkDir so claude's default Read/Write context is scoped
# there (not the user's home).
Push-Location $WorkDir

$intent = Get-Content -Raw -Path $IntentPath

$systemPrompt = @"
You are a deep research agent.  You have NO direct internet access.

The ONLY network endpoints you can reach are:
- Search shim (Tavily-compatible):   $ShimUrl
- Magento sandbox (shopping):        $ShoppingUrl
- Postmill sandbox (reddit-like):    $RedditUrl
- Kiwix sandbox (offline Wikipedia): $WikipediaUrl

To search, use the Bash tool:
  curl -s -X POST $ShimUrl/search -H 'content-type: application/json' -d '{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}'

To fetch a page returned by search, use Bash:
  curl -s -L '<sandbox URL>' | head -c 8000

Methodology:
1. Issue MULTIPLE search queries covering different angles of the task.
2. For each promising result, fetch the page to extract specifics (prices, specs, quotes, dates).
3. Cross-reference between Magento (products), Postmill (discussions), and Kiwix (encyclopedic background).
4. Aim for >= 20 distinct sandbox URLs cited across all three sources.

OUTPUT INSTRUCTIONS (read carefully — the harness reads ONLY this file):

  Use the Write tool ONE TIME to save your complete markdown report to:
      $ReportPath

The report MUST:
- Be at least 2000 words.
- Cite every factual claim inline as [anchor text](sandbox URL pointing at $ShoppingUrl / $RedditUrl / $WikipediaUrl).
- Draw evidence from ALL THREE sandbox sources.
- End with a "References" section listing every cited URL.
- Start immediately with the report body (no preface, no chain-of-thought).

After Write succeeds, your final text response should be ONLY:
  REPORT_WRITTEN

Begin now.  Do not ask for clarification — act on the brief alone.
"@

$claudeArgs = @(
  '--print',
  '--output-format', 'text',
  '--dangerously-skip-permissions',
  '--add-dir', $WorkDir,
  '--add-dir', $reportDir,
  __TOOL_POLICY_ARGS__
  '--append-system-prompt', $systemPrompt
)

# Pipe intent via stdin; capture claude's chat stdout separately from the
# actual report file the agent writes via its Write tool.
$intent | & claude @claudeArgs 2>&1 | Set-Content -Path $StdoutPath -Encoding UTF8
$rc = $LASTEXITCODE

Pop-Location
exit $rc
"""


# Workstream C: two tool-policy stanzas — picked based on `strict_sandbox`.
#
# OPEN policy (default, pre-Workstream-C behavior):
#   The classic disallowlist. Bans `WebSearch`, `WebFetch`, `NotebookEdit`
#   but leaves `Bash` (and therefore `curl <any-url>`) free. Comparable to
#   how every other DR baseline was previously configured.
#
# STRICT policy (Workstream C):
#   An ALLOWLIST. Only `Read`, `Write`, `Edit`, `Glob`, `Grep` and Bash
#   commands whose first arg matches a sandbox-localhost `curl` pattern
#   are permitted. Everything else (WebSearch, WebFetch, NotebookEdit, AND
#   any `Bash(curl https://...)`) is rejected by claude-code's own
#   tool-policy engine. Claude Code's `--allowed-tools` accepts argument
#   patterns of the form `Bash(<pattern>)`; we list every URL prefix the
#   sandbox can serve.
_TOOL_POLICY_OPEN = "'--disallowedTools', 'WebSearch', 'WebFetch', 'NotebookEdit',"
_TOOL_POLICY_STRICT = (
    "'--allowed-tools', "
    "'Read,Write,Edit,Glob,Grep,"
    "Bash(curl http://localhost:7770*),"
    "Bash(curl http://localhost:8090*),"
    "Bash(curl http://localhost:9999*),"
    "Bash(curl http://localhost:8081*),"
    "Bash(curl http://127.0.0.1:7770*),"
    "Bash(curl http://127.0.0.1:8090*),"
    "Bash(curl http://127.0.0.1:9999*),"
    "Bash(curl http://127.0.0.1:8081*),"
    "Bash(curl -s http://localhost:*),"
    "Bash(curl -sL http://localhost:*),"
    "Bash(curl -X POST http://localhost:8081*)',"
)


def _build_ps_driver(*, strict_sandbox: bool = False) -> str:
    policy = _TOOL_POLICY_STRICT if strict_sandbox else _TOOL_POLICY_OPEN
    return (
        _PS_DRIVER_TEMPLATE
        .replace("__CCR_URL__", CCR_BASE_URL)
        .replace("__TOOL_POLICY_ARGS__", policy)
    )


def _ssh(cmd: str, *, timeout_s: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh",
         "-o", "ServerAliveInterval=30",
         "-o", "ServerAliveCountMax=20",
         SSH_HOST, cmd],
        capture_output=True, text=True, timeout=timeout_s,
    )


def _scp_up(local: Path, remote_win: str, *, timeout_s: int = 60) -> None:
    subprocess.run(
        ["scp", "-o", "ServerAliveInterval=30",
         str(local), f"{SSH_HOST}:{remote_win}"],
        check=True, capture_output=True, timeout=timeout_s,
    )


def _scp_down(remote_win: str, local: Path, *, timeout_s: int = 60) -> None:
    subprocess.run(
        ["scp", "-o", "ServerAliveInterval=30",
         f"{SSH_HOST}:{remote_win}", str(local)],
        check=True, capture_output=True, timeout=timeout_s,
    )


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    strict_sandbox: bool = False,
) -> str:
    """Run claude-code on the remote 5090 host and return the markdown report.

    Args:
        intent: research brief.
        model: ignored — model is fixed in ccr config (deepseek-v4-flash by default).
        shim_url: sandbox shim URL, baked into the agent's system prompt.
        proxy_url: ignored — ccr is configured separately to talk to ds_proxy.
        timeout_s: hard timeout for the remote subprocess.
        strict_sandbox: when True, the PowerShell driver swaps claude-code's
            `--disallowedTools` flag for `--allowed-tools <whitelist>` that
            admits only Read/Write/Edit/Glob/Grep and Bash(curl <sandbox URL>).
            Closes the Bash-curl gap where the model could previously
            ``curl https://en.wikipedia.org/...`` despite WebSearch/WebFetch
            being banned.
    """
    del model, proxy_url  # informational only — wiring lives in ccr config

    job_id = uuid.uuid4().hex[:12]
    intent_remote = f"{REMOTE_DIR_WIN}/intent_{job_id}.txt"
    report_remote = f"{REMOTE_DIR_WIN}/report_{job_id}.md"
    stdout_remote = f"{REMOTE_DIR_WIN}/stdout_{job_id}.log"
    driver_remote = f"{REMOTE_DIR_WIN}/driver_{job_id}.ps1"
    workdir_remote = f"{REMOTE_DIR_WIN}/work_{job_id}"

    intent_local = Path(f"/tmp/cc_intent_{job_id}.txt")
    report_local = Path(f"/tmp/cc_report_{job_id}.md")
    stdout_local = Path(f"/tmp/cc_stdout_{job_id}.log")
    driver_local = Path(f"/tmp/cc_driver_{job_id}.ps1")

    intent_local.write_text(intent, encoding="utf-8")
    driver_local.write_text(
        _build_ps_driver(strict_sandbox=strict_sandbox), encoding="utf-8",
    )
    if strict_sandbox:
        logger.info("claude-code: strict-sandbox tool allowlist active")

    shopping_url = os.environ.get("SHOPPING", "http://localhost:7770")
    reddit_url = os.environ.get("REDDIT", "http://localhost:9999")
    wikipedia_url = os.environ.get("WIKIPEDIA", "http://localhost:8090")

    try:
        _ssh(
            f'powershell -NoProfile -Command "New-Item -ItemType Directory -Force '
            f'-Path {REMOTE_DIR_WIN} | Out-Null"',
            timeout_s=15,
        )

        _scp_up(intent_local, intent_remote)
        _scp_up(driver_local, driver_remote)

        ps_cmd = (
            f'powershell -NoProfile -File "{driver_remote}" '
            f'-IntentPath "{intent_remote}" -ReportPath "{report_remote}" '
            f'-StdoutPath "{stdout_remote}" -WorkDir "{workdir_remote}" '
            f'-ShimUrl "{shim_url}" -ShoppingUrl "{shopping_url}" '
            f'-RedditUrl "{reddit_url}" -WikipediaUrl "{wikipedia_url}"'
        )

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["ssh",
                 "-o", "ServerAliveInterval=30",
                 "-o", "ServerAliveCountMax=40",
                 SSH_HOST, ps_cmd],
                capture_output=True, text=True, timeout=timeout_s,
            ),
        )
        elapsed = time.time() - t0

        if proc.returncode != 0:
            logger.warning(
                "claude-code ssh exited %d after %.0fs\nstderr tail: %s",
                proc.returncode, elapsed, proc.stderr[-1500:],
            )

        report = ""
        stdout_text = ""
        try:
            _scp_down(report_remote, report_local)
            report = report_local.read_text(encoding="utf-8").lstrip("﻿").strip()
        except subprocess.CalledProcessError as e:
            logger.warning("scp report pull failed: %s",
                           (e.stderr or b"").decode("utf-8", errors="replace")[-300:])
        try:
            _scp_down(stdout_remote, stdout_local)
            stdout_text = stdout_local.read_text(encoding="utf-8", errors="replace")
        except subprocess.CalledProcessError:
            pass

        # If the agent wrote the report via its Write tool, trust that file.
        # Otherwise fall back to whatever it streamed to stdout (some prompts
        # cause it to dump the report inline instead of Write-ing).
        if len(report) < 500 and stdout_text.strip():
            logger.info(
                "claude-code: report file is %d chars, falling back to %d chars stdout",
                len(report), len(stdout_text),
            )
            report = stdout_text.strip()

        if not report:
            return (
                f"(claude-code produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n--- ssh stdout tail ---\n"
                f"{proc.stdout[-1500:]}\n\n--- ssh stderr tail ---\n"
                f"{proc.stderr[-1500:]}\n\n--- agent stdout tail ---\n"
                f"{stdout_text[-1500:]}"
            )

        logger.info("claude-code completed in %.0fs, report=%d chars",
                    elapsed, len(report))
        return report

    except subprocess.TimeoutExpired:
        logger.error("claude-code timed out after %ds", timeout_s)
        return f"(claude-code timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("claude-code runner error")
        return f"(claude-code error: {type(e).__name__}: {e})"
    finally:
        for p in (intent_local, report_local, stdout_local, driver_local):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            _ssh(
                f'powershell -NoProfile -Command "Remove-Item -Force -Recurse '
                f'{intent_remote},{report_remote},{stdout_remote},{driver_remote},'
                f'{workdir_remote} -ErrorAction SilentlyContinue"',
                timeout_s=15,
            )
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run claude-code via 5090 SSH")
    parser.add_argument("intent")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--proxy-url", default="http://localhost:8088/v1")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--output", "-o")
    parser.add_argument("--strict-sandbox", action="store_true", default=False)
    args = parser.parse_args()
    out = asyncio.run(run(
        intent=args.intent, model=args.model,
        shim_url=args.shim_url, proxy_url=args.proxy_url,
        timeout_s=args.timeout,
        strict_sandbox=args.strict_sandbox,
    ))
    if args.output:
        Path(args.output).write_text(out)
        print(f"Report -> {args.output} ({len(out)} chars)")
    else:
        print(out)
