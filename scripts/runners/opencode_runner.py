"""sst/opencode CLI as a deep-research agent.

Architecture (mirrors `claudecode_runner.py`'s SSH-to-Windows pattern):

    runner (any host with ssh 5090)
        │  scp intent + ps1 driver
        │  ssh 5090 powershell -File driver.ps1
        ▼
    5090 Windows
        opencode run --prompt <intent + system> --model openai/<model>
            │  uses opencode's auth (multi-provider; defaults to OpenAI)
            ▼
        OpenAI API (or whatever provider opencode is configured for)

Tooling lockdown (fairness with other DR baselines):
    - `opencode run` is the non-interactive entrypoint.
    - `--format default` keeps stdout human-readable (we extract from $StdoutPath).
    - The sandbox-only system prompt enumerates the four reachable endpoints
      (Magento 7770, Postmill 9999, Kiwix 8090, shim 8081) and instructs the
      model to drive them via `curl` through opencode's shell tool.
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
AGENT_NAME = "opencode"

# Workstream C — strict-sandbox eligibility.
# OpenCode's `commands.allowed` block in opencode.json is the only available
# shell-command gate. Under strict_sandbox=True we inject an allowlist of
# command prefixes (`curl http://localhost*`, `curl http://127.0.0.1*`,
# plus the read-only utilities the agent uses to walk reports). Anything
# else — `curl https://en.wikipedia.org`, `wget`, `nslookup`, `node -e
# 'fetch(...)'` — is auto-rejected by opencode itself. The soft prompt
# (`You have no direct internet access`) is no longer the gate.
STRICT_SANDBOX_ELIGIBLE = True

DEFAULT_TIMEOUT_S = 1800
SSH_HOST = os.environ.get("OPENCODE_SSH_HOST", os.environ.get("CLAUDE_CODE_SSH_HOST", "5090"))
REMOTE_DIR_WIN = os.environ.get("OPENCODE_REMOTE_DIR", "C:/tools/opencode_runner")
# opencode model format: "provider/model".  Default routes to ds_proxy → DeepSeek
# V4 flash for cost parity with the rest of the benchmark.  The "ds-shim"
# provider is defined inline in the driver via env+config injection.
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "ds-shim/deepseek-v4-flash")
OPENCODE_DS_PROXY = os.environ.get("OPENCODE_DS_PROXY", "http://localhost:8088/v1")


_PS_DRIVER_TEMPLATE = r"""param(
  [string]$IntentPath,
  [string]$ReportPath,
  [string]$StdoutPath,
  [string]$WorkDir,
  [string]$ShimUrl,
  [string]$ShoppingUrl,
  [string]$RedditUrl,
  [string]$WikipediaUrl,
  [string]$Model,
  [string]$DsProxyUrl,
  [int]$StrictSandbox = 0
)
$ErrorActionPreference = 'Continue'

$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

# opencode auto-rejects writes outside its --dir workspace, so we point the
# model at an *in-workdir* report path and copy it back out at the end.
$InnerReport = Join-Path $WorkDir 'report.md'
Set-Content -Path $InnerReport -Value '' -Encoding UTF8
Set-Content -Path $ReportPath  -Value '' -Encoding UTF8

# Write a per-run opencode config that defines a "ds-shim" provider pointing
# at ds_proxy → DeepSeek V4 flash.  $OPENCODE_CONFIG overrides the default
# config path so the user's machine-wide config is not touched.
#
# Workstream C: when -StrictSandbox 1 is passed, also inject a
# `commands.allowed` whitelist so opencode's shell tool rejects anything
# that isn't a sandbox-local curl or a read-only file utility. Without
# this block the only gate is the soft system prompt, which is not a real
# gate. Reference: https://opencode.ai/docs/config (`commands.allowed`).
$ocConfigObj = @{
  '$schema'  = 'https://opencode.ai/config.json'
  provider   = @{
    'ds-shim' = @{
      npm     = '@ai-sdk/openai-compatible'
      name    = 'DeepSeek (ds_proxy shim)'
      options = @{
        baseURL = $DsProxyUrl
        apiKey  = 'anything-proxy-uses-server-key'
      }
      models  = @{
        'deepseek-v4-flash' = @{ name = 'DeepSeek V4 Flash' }
        'deepseek-chat'     = @{ name = 'DeepSeek Chat' }
      }
    }
  }
}
if ($StrictSandbox -eq 1) {
  $ocConfigObj['commands'] = @{
    allowed = @(
      'curl http://localhost*',
      'curl http://127.0.0.1*',
      'curl -s http://localhost*',
      'curl -s http://127.0.0.1*',
      'curl -sL http://localhost*',
      'curl -sL http://127.0.0.1*',
      'curl -X POST http://localhost:8081*',
      'curl -X POST http://127.0.0.1:8081*',
      'cat',
      'ls',
      'head',
      'tail'
    )
  }
}
$ocConfig = $ocConfigObj | ConvertTo-Json -Depth 10
$ocConfigPath = Join-Path $WorkDir 'opencode.json'
# Write WITHOUT BOM — opencode's JSONC parser rejects the BOM.
[System.IO.File]::WriteAllText($ocConfigPath, $ocConfig, (New-Object System.Text.UTF8Encoding $false))
$env:OPENCODE_CONFIG = $ocConfigPath
$env:OPENAI_API_KEY  = 'anything-proxy-uses-server-key'

Push-Location $WorkDir

$intent = Get-Content -Raw -Path $IntentPath

$systemPrompt = @"
You are a deep research agent.  You have NO direct internet access.

The ONLY network endpoints you can reach are:
- Search shim (Tavily-compatible):   $ShimUrl
- Magento sandbox (shopping):        $ShoppingUrl
- Postmill sandbox (reddit-like):    $RedditUrl
- Kiwix sandbox (offline Wikipedia): $WikipediaUrl

To search, use the shell tool (Windows PowerShell / cmd — `head`/`tail` are NOT available):
  curl -s -X POST $ShimUrl/search -H 'content-type: application/json' -d '{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}'

To fetch a page returned by search, use the shell tool — just `curl` the URL,
the agent transport already caps output length, do NOT pipe through `head`:
  curl -s -L '<sandbox URL>'

Methodology:
1. Issue MULTIPLE search queries covering different angles of the task.
2. For each promising result, fetch the page to extract specifics (prices, specs, quotes, dates).
3. Cross-reference between Magento (products), Postmill (discussions), and Kiwix (encyclopedic background).
4. Aim for >= 20 distinct sandbox URLs cited across all three sources.

OUTPUT INSTRUCTIONS (read carefully — the harness reads ONLY this file):

  Write your complete markdown report to:
      $InnerReport
  using the write file tool.  This path is INSIDE your workspace; do NOT use any
  other path (writes to parents of the workspace are auto-rejected).
  Do NOT print the report inline as your final message — the harness reads the
  file, not the message.

The report MUST:
- Be at least 2000 words.
- Cite every factual claim inline as [anchor text](sandbox URL pointing at $ShoppingUrl / $RedditUrl / $WikipediaUrl).
- Draw evidence from ALL THREE sandbox sources.
- End with a "References" section listing every cited URL.
- Start immediately with the report body (no preface, no chain-of-thought).

After writing the file, your final text response should be ONLY:
  REPORT_WRITTEN

Begin now.  Do not ask for clarification — act on the brief alone.
"@

$fullPrompt = @"
[SYSTEM INSTRUCTIONS — read first, follow strictly]
$systemPrompt

[TASK]
$intent
"@

# opencode run flags:
#   run <message>             — non-interactive
#   --model <provider/model>  — backbone
#   --format default          — clean stdout (json variant emits structured events)
#   --dir <workdir>           — set opencode's working directory
$opencodeArgs = @(
  'run',
  '--model', $Model,
  '--format', 'default',
  '--dir', $WorkDir,
  $fullPrompt
)

& opencode @opencodeArgs 2>&1 | Set-Content -Path $StdoutPath -Encoding UTF8
$rc = $LASTEXITCODE

# Copy the in-workdir report back out to the path the runner expects.
if (Test-Path $InnerReport) {
  $content = Get-Content -Raw -Path $InnerReport -ErrorAction SilentlyContinue
  if ($content -and $content.Length -gt 0) {
    Set-Content -Path $ReportPath -Value $content -Encoding UTF8
  }
}

Pop-Location
exit $rc
"""


def _build_ps_driver() -> str:
    return _PS_DRIVER_TEMPLATE


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
    """Run opencode on the remote 5090 host and return the markdown report.

    Args:
        intent: research brief.
        model: model string in opencode's "provider/model" format. If a bare
               model name (e.g. 'deepseek-v4-flash') is passed, falls back to
               OPENCODE_MODEL env (default 'openai/gpt-5.5').
        shim_url: sandbox shim URL, baked into the agent's system prompt.
        proxy_url: ignored.
        timeout_s: hard timeout for the remote subprocess.
        strict_sandbox: when True, the per-run `opencode.json` includes a
            `commands.allowed` whitelist that admits only sandbox-local
            curl commands plus read-only file utilities. Anything else
            is rejected by opencode's own command gate — the soft prompt
            is no longer the gate.
    """
    del proxy_url
    # Caller may pass a bare "deepseek-v4-flash" or the full "ds-shim/deepseek-v4-flash"
    # form. Both map to the per-run ds-shim provider defined in the driver.
    if model and "/" in model:
        opencode_model = model
    elif model:
        opencode_model = f"ds-shim/{model}"
    else:
        opencode_model = OPENCODE_MODEL

    job_id = uuid.uuid4().hex[:12]
    intent_remote = f"{REMOTE_DIR_WIN}/intent_{job_id}.txt"
    report_remote = f"{REMOTE_DIR_WIN}/report_{job_id}.md"
    stdout_remote = f"{REMOTE_DIR_WIN}/stdout_{job_id}.log"
    driver_remote = f"{REMOTE_DIR_WIN}/driver_{job_id}.ps1"
    workdir_remote = f"{REMOTE_DIR_WIN}/work_{job_id}"

    intent_local = Path(f"/tmp/oc_intent_{job_id}.txt")
    report_local = Path(f"/tmp/oc_report_{job_id}.md")
    stdout_local = Path(f"/tmp/oc_stdout_{job_id}.log")
    driver_local = Path(f"/tmp/oc_driver_{job_id}.ps1")

    intent_local.write_text(intent, encoding="utf-8")
    driver_local.write_text(_build_ps_driver(), encoding="utf-8")

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
            f'-RedditUrl "{reddit_url}" -WikipediaUrl "{wikipedia_url}" '
            f'-Model "{opencode_model}" '
            f'-DsProxyUrl "{OPENCODE_DS_PROXY}" '
            f'-StrictSandbox {1 if strict_sandbox else 0}'
        )
        if strict_sandbox:
            logger.info("opencode: strict-sandbox commands.allowed allowlist active")

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
                "opencode ssh exited %d after %.0fs\nstderr tail: %s",
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

        if len(report) < 500 and stdout_text.strip():
            logger.info(
                "opencode: report file is %d chars, falling back to %d chars stdout",
                len(report), len(stdout_text),
            )
            report = stdout_text.strip()

        if not report:
            return (
                f"(opencode produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n--- ssh stdout tail ---\n"
                f"{proc.stdout[-1500:]}\n\n--- ssh stderr tail ---\n"
                f"{proc.stderr[-1500:]}\n\n--- agent stdout tail ---\n"
                f"{stdout_text[-1500:]}"
            )

        logger.info("opencode completed in %.0fs, report=%d chars",
                    elapsed, len(report))
        return report

    except subprocess.TimeoutExpired:
        logger.error("opencode timed out after %ds", timeout_s)
        return f"(opencode timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("opencode runner error")
        return f"(opencode error: {type(e).__name__}: {e})"
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
    parser = argparse.ArgumentParser(description="Run opencode via 5090 SSH")
    parser.add_argument("intent")
    parser.add_argument("--model", default=OPENCODE_MODEL)
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
