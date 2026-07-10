"""OpenAI Codex CLI as a deep-research agent.

Architecture (mirrors `claudecode_runner.py`'s SSH-to-Windows pattern):

    runner (any host with ssh 5090)
        │  scp intent + ps1 driver
        │  ssh 5090 powershell -File driver.ps1
        ▼
    5090 Windows
        codex exec --dangerously-bypass-approvals-and-sandbox
                   --sandbox danger-full-access
                   --model <model>
                   <sandbox-only system prompt + intent>
            │  OPENAI_BASE_URL via codex's own auth (gpt-5.5 native by default)
            ▼
        OpenAI API (or whatever model codex routes to)

Tooling lockdown (fairness with other DR baselines):
    - codex's `exec` subcommand is non-interactive (no TUI, no approvals).
    - `--dangerously-bypass-approvals-and-sandbox` skips per-command approvals
      that would otherwise stall a headless run.
    - The sandbox-only prompt supplies the shim search/fetch recipes required
      by a CLI without a native benchmark search tool. It does not enumerate
      the scored corpus modalities.
    - The work dir is a clean per-job scratch directory so codex's read/write
      tools are scoped to it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.runners import _egress  # noqa: E402

AGENT_NAME = "codex"

DEFAULT_TIMEOUT_S = 1800
# No "5090" default: that literal parses as the decimal IPv4 0.0.19.226 and
# burned ~150s per connect attempt (claudecode_runner learned this first).
# The remote path is opt-in; unset means fail fast with a clear message.
SSH_HOST = os.environ.get("CODEX_SSH_HOST", os.environ.get("CLAUDE_CODE_SSH_HOST", "")).strip()
REMOTE_DIR_WIN = os.environ.get("CODEX_REMOTE_DIR", "C:/tools/codex_runner")
# Route through ds_proxy on my5090 localhost:8088 → DeepSeek V4 flash.
# Same backbone as the rest of the benchmark for cost parity.
CODEX_MODEL = os.environ.get("CODEX_MODEL", "deepseek-v4-flash")
CODEX_DS_PROXY = os.environ.get("CODEX_DS_PROXY", "http://localhost:8100/v1")


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
  [string]$EgressProxyUrl
)
$ErrorActionPreference = 'Continue'

# The SSH process does not inherit the launcher's environment. Recreate the
# canonical recording-door policy in the final Codex process explicitly.
if ($EgressProxyUrl) {
  $env:HTTP_PROXY = $EgressProxyUrl
  $env:HTTPS_PROXY = $EgressProxyUrl
  $env:ALL_PROXY = $EgressProxyUrl
  $env:NO_PROXY = ''
}

# Force codex to use the local ds_proxy → DeepSeek V4 flash for cost parity
# with the rest of the benchmark.  The OPENAI_API_KEY var is read by codex's
# OAI provider when it sees env_key="OPENAI_API_KEY" on the model provider.
$env:OPENAI_API_KEY = 'anything-proxy-uses-server-key'

# Pre-create the report file empty so codex's Write tool sees a path in an
# allowed directory.
$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
Set-Content -Path $ReportPath -Value '' -Encoding UTF8

# codex's working dir; -C sets the agent's working root.
Push-Location $WorkDir

$intent = Get-Content -Raw -Path $IntentPath

$systemPrompt = @"
You are a deep research agent.  You have NO direct internet access. Use the
benchmark search shim for search and page reads.

To search, use the shell tool:
  curl -s -X POST $ShimUrl/search -H 'content-type: application/json' -d '{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}'

To fetch and read a page returned by search, use the shell tool. Route it
through the shim's /fetch so the read is recorded:
  curl -s "$ShimUrl/fetch?url=<sandbox URL>"

OUTPUT INSTRUCTIONS (read carefully — the harness reads ONLY this file):

  Write the task response to:
      $ReportPath
  using the write/edit file tool.  Do NOT print the report inline as your
  final message — the harness reads the file, not the message.

After writing the file, your final text response should be ONLY:
  REPORT_WRITTEN

Begin now.  Do not ask for clarification — act on the brief alone.
"@

# Compose the full prompt: system prompt + intent.  codex's exec takes a single
# prompt arg, so we concatenate.  We prefix the system prompt with a marker
# so the model treats it as priority instructions.
$fullPrompt = @"
[SYSTEM INSTRUCTIONS — read first, follow strictly]
$systemPrompt

[TASK]
$intent
"@

# Codex non-interactive flags:
#   exec                                    — non-interactive mode
#   --dangerously-bypass-approvals-and-sandbox
#                                           — skip approval prompts (we are externally sandboxed)
#
# FETCH CANNOT BE FORCED HERE (honest limitation, FETCH_PATH_AUDIT §3):
# codex exec offers no per-command / per-host allowlist. Its only network
# control is the coarse `--sandbox` switch (read-only | workspace-write |
# danger-full-access), which is all-or-nothing: it can BLOCK all network or
# ALLOW all, but cannot route a page read THROUGH the shim. Worse, that sandbox
# is Seatbelt(macOS)/Landlock(Linux) only and is unsupported on the Windows box
# this driver targets, so it degrades to danger-full-access regardless. The
# /fetch recipe below is therefore advisory only: a disobedient model can still
# `curl http://localhost:7770/...` directly. Consequently this lane's page
# reads are NOT shim-observable; config/lane_protocol.yaml MUST keep
# fetch_observable=false so the scorer marks pof available=false (never 0),
# instead of falsely accusing it of hallucinated grounding.
#   -m <model>                              — pick the backbone (here: deepseek-v4-flash via shim)
#   -C <dir>                                — set codex's working root to $WorkDir
#   -c model_providers.deepseek.<...>=...   — define a custom OpenAI-compat provider
#                                             (dotted-key per-leaf form, not inline struct)
#   -c model_provider="deepseek"            — pick that provider for this run
$dsBase = '"' + $DsProxyUrl + '"'
$codexArgs = @(
  'exec',
  '--dangerously-bypass-approvals-and-sandbox',
  '-m', $Model,
  '-C', $WorkDir,
  '--skip-git-repo-check',
  '-c', ('model_providers.deepseek.name="DeepSeek"'),
  '-c', ('model_providers.deepseek.base_url=' + $dsBase),
  '-c', ('model_providers.deepseek.env_key="OPENAI_API_KEY"'),
  '-c', 'model_provider="deepseek"',
  $fullPrompt
)

& codex @codexArgs 2>&1 | Set-Content -Path $StdoutPath -Encoding UTF8
$rc = $LASTEXITCODE

Pop-Location
exit $rc
"""


def _build_ps_driver() -> str:
    return _PS_DRIVER_TEMPLATE


def _degenerate_marker(elapsed_s: float, returncode: int | None) -> str:
    """Recognized 'produced no report' marker.

    Format matches the leaderboard's ``_RUNNER_FAILURE_PREFIX_RE`` so that
    ``_looks_degenerate`` / ``is_degenerate_answer`` reliably exclude the run
    from URL coverage, analysis_depth, presentation scoring and the
    Bradley-Terry/Elo computation.
    """
    # The leaderboard's _RUNNER_FAILURE_PREFIX_RE requires ``exit=\d+`` (a
    # non-negative integer), so a missing/negative code must be normalized to a
    # non-negative sentinel or the marker would NOT be recognized as degenerate.
    rc = returncode if isinstance(returncode, int) and returncode >= 0 else 1
    return f"(codex produced no report after {elapsed_s:.0f}s, exit={rc})"


def _wrap_stdout_fallback(stdout_text: str, elapsed_s: float, returncode: int | None) -> str:
    """Wrap a raw 2>&1 stdout dump in the degenerate marker.

    The remote driver captures stdout via ``& codex @args 2>&1 | Set-Content``,
    so ``stdout_text`` is the merged stdout+stderr stream (chain-of-thought,
    tool-call logs, curl output, error traces), NOT a research report. When the
    agent fails to write the report file this dump must NOT be scored as a real
    report. Prefixing the recognized marker makes the leaderboard's degenerate
    filters drop it instead of feeding a crashed/empty run into scoring.
    """
    marker = _degenerate_marker(elapsed_s, returncode)
    return f"{marker}\n\n--- agent stdout tail (no report file written) ---\n{stdout_text.strip()}"


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
    """Run codex on the remote 5090 host and return the markdown report.

    Args:
        intent: research brief.
        model: codex model name (default = CODEX_MODEL env or 'gpt-5.5').  We pass
               this through; codex routes via its own auth (no shim rewrite).
        shim_url: sandbox shim URL, baked into the agent's system prompt.
        proxy_url: ignored — codex uses its own provider routing.
        timeout_s: hard timeout for the remote subprocess.
    """
    if not SSH_HOST:
        raise RuntimeError(
            "CODEX_SSH_HOST unset; the remote path is opt-in. Set it to the ssh "
            "alias (my5090), never a bare port number.")
    del proxy_url  # informational only — we read CODEX_DS_PROXY env / module const
    if _egress.enforced() and not _egress.remote_enforced():
        raise RuntimeError(
            "codex is an SSH lane: formal egress requires "
            "DRA_REMOTE_EGRESS_PROXY to reach the bracketed door plus "
            "DRA_REMOTE_EGRESS_ENFORCED=1 after remote bypass isolation passes"
        )
    # Pass model through; default = DeepSeek V4 flash via ds_proxy.
    codex_model = model or CODEX_MODEL

    job_id = uuid.uuid4().hex[:12]
    intent_remote = f"{REMOTE_DIR_WIN}/intent_{job_id}.txt"
    report_remote = f"{REMOTE_DIR_WIN}/report_{job_id}.md"
    stdout_remote = f"{REMOTE_DIR_WIN}/stdout_{job_id}.log"
    driver_remote = f"{REMOTE_DIR_WIN}/driver_{job_id}.ps1"
    workdir_remote = f"{REMOTE_DIR_WIN}/work_{job_id}"

    intent_local = Path(f"/tmp/codex_intent_{job_id}.txt")
    report_local = Path(f"/tmp/codex_report_{job_id}.md")
    stdout_local = Path(f"/tmp/codex_stdout_{job_id}.log")
    driver_local = Path(f"/tmp/codex_driver_{job_id}.ps1")

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
            f'-Model "{codex_model}" '
            f'-DsProxyUrl "{CODEX_DS_PROXY}" '
            f'-EgressProxyUrl "{_egress.remote_proxy()}"'
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
                "codex ssh exited %d after %.0fs\nstderr tail: %s",
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

        if not report and stdout_text.strip():
            # The report file is empty and all we have is the merged
            # 2>&1 stdout stream. This is NOT a research report (it is tool-call
            # logs, chain-of-thought, curl output, error traces), so we must not
            # let it be scored as one. Prefix the recognized degenerate marker
            # so the leaderboard's _looks_degenerate / is_degenerate_answer
            # filters exclude it from scoring and Elo, instead of returning a
            # bare stdout dump that frequently passes the chars/URL filters.
            logger.info(
                "codex: report file is empty, marking %d chars stdout as degenerate fallback",
                len(stdout_text),
            )
            report = _wrap_stdout_fallback(stdout_text, elapsed, proc.returncode)

        if not report:
            return (
                f"{_degenerate_marker(elapsed, proc.returncode)}\n\n"
                f"--- ssh stdout tail ---\n"
                f"{proc.stdout[-1500:]}\n\n--- ssh stderr tail ---\n"
                f"{proc.stderr[-1500:]}\n\n--- agent stdout tail ---\n"
                f"{stdout_text[-1500:]}"
            )

        logger.info("codex completed in %.0fs, report=%d chars",
                    elapsed, len(report))
        return report

    except subprocess.TimeoutExpired:
        logger.error("codex timed out after %ds", timeout_s)
        return f"(codex timeout after {timeout_s}s)"
    except Exception as e:
        logger.exception("codex runner error")
        return f"(codex error: {type(e).__name__}: {e})"
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
    parser = argparse.ArgumentParser(description="Run codex CLI via 5090 SSH")
    parser.add_argument("intent")
    parser.add_argument("--model", default=CODEX_MODEL)
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--proxy-url", default="http://localhost:8100/v1")
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
