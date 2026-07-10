"""Google Gemini CLI as a deep-research agent.

Architecture (mirrors `claudecode_runner.py`'s SSH-to-Windows pattern):

    runner (any host with ssh 5090)
        │  scp intent + ps1 driver
        │  ssh 5090 powershell -File driver.ps1
        ▼
    5090 Windows
        gemini --prompt <intent> --yolo --output-format text
            │  uses gemini's own OAuth-personal auth
            ▼
        Gemini API (model picked via -m or gemini's default)

Tooling lockdown (fairness with other DR baselines):
    - `--yolo` (or `--approval-mode yolo`) auto-approves all tool calls so the
      run is headless.
    - We pass `--output-format text` to get clean stdout (no streaming JSON).
    - The sandbox-only system prompt enumerates the four reachable endpoints
      (Magento 7770, Postmill 9999, Kiwix 8090, shim 8081) and instructs the
      model to drive them via `curl` through gemini-cli's shell tool.
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
AGENT_NAME = "gemini-cli"

# Standalone provider-specific CLI, not a shared-backbone comparative lane.
# gemini-cli authenticates to Gemini with its own OAuth session and cannot route
# the benchmark's DeepSeek/Qwen/GLM model through ds_proxy. Passing one of those
# names with ``-m`` either fails or selects a different provider-side model; it
# cannot produce an identity-probed framework x requested-backbone row.
BENCHMARK_ENABLED = False
BENCHMARK_DISABLED_REASON = "Gemini OAuth CLI cannot serve the requested shared backbone"

DEFAULT_TIMEOUT_S = 1800
# No "5090" default: that literal parses as the decimal IPv4 0.0.19.226 and
# burned ~150s per connect attempt (claudecode_runner learned this first).
# The remote path is opt-in; unset means fail fast with a clear message.
SSH_HOST = os.environ.get("GEMINI_CLI_SSH_HOST", os.environ.get("CLAUDE_CODE_SSH_HOST", "")).strip()
REMOTE_DIR_WIN = os.environ.get("GEMINI_CLI_REMOTE_DIR", "C:/tools/gemini_runner")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")  # empty → gemini-cli default


_PS_DRIVER_TEMPLATE = r"""param(
  [string]$IntentPath,
  [string]$ReportPath,
  [string]$StdoutPath,
  [string]$WorkDir,
  [string]$ShimUrl,
  [string]$ShoppingUrl,
  [string]$RedditUrl,
  [string]$WikipediaUrl,
  [string]$Model
)
$ErrorActionPreference = 'Continue'

$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
Set-Content -Path $ReportPath -Value '' -Encoding UTF8

Push-Location $WorkDir

$intent = Get-Content -Raw -Path $IntentPath

$systemPrompt = @"
You are a deep research agent.  You have NO direct internet access.

The ONLY network endpoints you can reach are:
- Search shim (Tavily-compatible):   $ShimUrl
- Magento sandbox (shopping):        $ShoppingUrl
- Postmill sandbox (reddit-like):    $RedditUrl
- Kiwix sandbox (offline Wikipedia): $WikipediaUrl

To search, use the shell tool:
  curl -s -X POST $ShimUrl/search -H 'content-type: application/json' -d '{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}'

To fetch and read a page returned by search, use the shell tool. Route it
through the shim's /fetch so the read is recorded:
  curl -s "$ShimUrl/fetch?url=<sandbox URL>"

OUTPUT INSTRUCTIONS (read carefully — the harness reads ONLY this file):

  Write your complete markdown report to:
      $ReportPath
  using the write_file tool.  Do NOT print the report inline as your final
  message — the harness reads the file, not the message.

The report MUST:
- Be a single self-contained markdown document.
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

# Gemini CLI non-interactive flags:
#   --prompt <text>           — non-interactive (headless) mode
#   --yolo                    — auto-approve all tool calls
#   --output-format text      — clean stdout (no streaming JSON)
#   --include-directories DIR — give gemini access to $WorkDir for file writes
#   -m <model>                — pick the model (empty = default)
#
# FETCH CANNOT BE FORCED HERE (honest limitation, FETCH_PATH_AUDIT §3):
# --yolo is required to stay headless (the only other approval modes, `default`
# and `auto_edit`, block on a prompt for every shell call and would stall the
# run). gemini-cli has no per-host command allowlist: `coreTools`/`excludeTools`
# can drop the native `google_web_search`/`web_fetch` tools (cutting off-box
# leakage) and can pin the shell tool to `run_shell_command(curl)`, but neither
# constrains the URL, so a bare `curl http://localhost:7770/...` still bypasses
# the shim's record_fetch. The /fetch recipe below is therefore advisory only.
# This lane's page reads are NOT shim-observable; config/lane_protocol.yaml MUST
# keep fetch_observable=false so the scorer marks pof available=false (never 0)
# rather than falsely accusing it of hallucinated grounding.
$geminiArgs = @(
  '--prompt', $fullPrompt,
  '--yolo',
  '--output-format', 'text',
  '--include-directories', $WorkDir
)
if ($Model -and $Model -ne '') {
  $geminiArgs = $geminiArgs + @('-m', $Model)
}

& gemini @geminiArgs 2>&1 | Set-Content -Path $StdoutPath -Encoding UTF8
$rc = $LASTEXITCODE

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
) -> str:
    """Run gemini-cli on the remote 5090 host and return the markdown report.

    Args:
        intent: research brief.
        model: gemini model name. We treat 'deepseek-v4-flash' as a sentinel
               meaning "use gemini's default" since gemini-cli doesn't natively
               route to DeepSeek.
        shim_url: sandbox shim URL, baked into the agent's system prompt.
        proxy_url: ignored.
        timeout_s: hard timeout for the remote subprocess.
    """
    if not SSH_HOST:
        raise RuntimeError(
            "GEMINI_CLI_SSH_HOST unset; the remote path is opt-in. Set it to the ssh "
            "alias (my5090), never a bare port number.")
    del proxy_url
    # This lane used to silently substitute its own model whenever the harness
    # asked for a DeepSeek-shaped one:
    #
    #     gemini_model = GEMINI_MODEL if (not model or "deepseek" in model.lower()) else model
    #
    # So a row labelled `gemini-cli x deepseek-v4-flash` was gemini-cli running
    # Gemini. The board would have compared a backbone against itself. This is
    # the same class of accident as the claude-code lane filing qwen3-8b output
    # under deepseek, and it branched on the backbone's NAME, which is why the
    # cross-backbone axis cannot mean anything while such branches exist.
    #
    # A lane that cannot serve the requested backbone must say so, not quietly
    # serve another one. The board then records an honest lane failure.
    gemini_model = model or GEMINI_MODEL
    if not gemini_model:
        raise ValueError("gemini-cli: no model requested and GEMINI_MODEL unset")

    job_id = uuid.uuid4().hex[:12]
    intent_remote = f"{REMOTE_DIR_WIN}/intent_{job_id}.txt"
    report_remote = f"{REMOTE_DIR_WIN}/report_{job_id}.md"
    stdout_remote = f"{REMOTE_DIR_WIN}/stdout_{job_id}.log"
    driver_remote = f"{REMOTE_DIR_WIN}/driver_{job_id}.ps1"
    workdir_remote = f"{REMOTE_DIR_WIN}/work_{job_id}"

    intent_local = Path(f"/tmp/gemini_intent_{job_id}.txt")
    report_local = Path(f"/tmp/gemini_report_{job_id}.md")
    stdout_local = Path(f"/tmp/gemini_stdout_{job_id}.log")
    driver_local = Path(f"/tmp/gemini_driver_{job_id}.ps1")

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
            f'-Model "{gemini_model}"'
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
                "gemini-cli ssh exited %d after %.0fs\nstderr tail: %s",
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
                "gemini-cli: report file is %d chars, falling back to %d chars stdout",
                len(report), len(stdout_text),
            )
            report = stdout_text.strip()

        if not report:
            return (
                f"(gemini-cli produced no report after {elapsed:.0f}s, "
                f"exit={proc.returncode})\n\n--- ssh stdout tail ---\n"
                f"{proc.stdout[-1500:]}\n\n--- ssh stderr tail ---\n"
                f"{proc.stderr[-1500:]}\n\n--- agent stdout tail ---\n"
                f"{stdout_text[-1500:]}"
            )

        logger.info("gemini-cli completed in %.0fs, report=%d chars",
                    elapsed, len(report))
        return report

    except subprocess.TimeoutExpired:
        logger.error("gemini-cli timed out after %ds", timeout_s)
        return f"(gemini-cli timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("gemini-cli runner error")
        return f"(gemini-cli error: {type(e).__name__}: {e})"
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
    parser = argparse.ArgumentParser(description="Run gemini-cli via 5090 SSH")
    parser.add_argument("intent")
    parser.add_argument("--model", default=GEMINI_MODEL)
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--proxy-url", default="http://localhost:8088/v1")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--output", "-o")
    args = parser.parse_args()
    out = asyncio.run(run(
        intent=args.intent, model=args.model,
        shim_url=args.shim_url, proxy_url=args.proxy_url,
        timeout_s=args.timeout,
    ))
    if args.output:
        Path(args.output).write_text(out)
        print(f"Report -> {args.output} ({len(out)} chars)")
    else:
        print(out)
