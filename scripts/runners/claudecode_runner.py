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
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from .evidence_fallback import is_weak_report, synthesize_report

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
DEFAULT_NATIVE_TIMEOUT_S = int(os.environ.get("CLAUDE_CODE_NATIVE_TIMEOUT_S", "420") or "420")
SSH_HOST = os.environ.get("CLAUDE_CODE_SSH_HOST", "5090")
REMOTE_DIR_WIN = os.environ.get("CLAUDE_CODE_REMOTE_DIR", "C:/tools/cc_runner")


def _win_path_to_wsl(path: str) -> Path:
    normalized = path.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1:3] == ":/":
        drive = normalized[0].lower()
        return Path("/mnt") / drive / normalized[3:]
    raise ValueError(f"cannot map Windows path to WSL path: {path}")


REMOTE_DIR_WSL = Path(
    os.environ.get(
        "CLAUDE_CODE_REMOTE_DIR_WSL",
        str(_win_path_to_wsl(REMOTE_DIR_WIN)),
    )
)


def _default_ccr_base_url() -> str:
    configured = os.environ.get("CLAUDE_CODE_CCR_URL")
    if configured:
        return configured
    try:
        ips = subprocess.check_output(["hostname", "-I"], text=True, timeout=2).split()
        for ip in ips:
            if ip.startswith(("172.", "10.", "192.168.")):
                return f"http://{ip}:3456"
    except Exception:
        pass
    return "http://127.0.0.1:3456"


CCR_BASE_URL = _default_ccr_base_url()


def _local_ccr_base_url() -> str:
    return os.environ.get("CLAUDE_CODE_LOCAL_CCR_URL", "http://127.0.0.1:3456")


def _tcp_listening(url: str, *, timeout_s: float = 1.0) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _native_timeout(timeout_s: int) -> int:
    try:
        configured = int(os.environ.get("CLAUDE_CODE_NATIVE_TIMEOUT_S", "") or DEFAULT_NATIVE_TIMEOUT_S)
    except (TypeError, ValueError):
        configured = DEFAULT_NATIVE_TIMEOUT_S
    return max(60, min(timeout_s, configured))


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

	OUTPUT INSTRUCTIONS (read carefully — the evaluator reads ONLY this file):

  Use the Bash tool ONE TIME with a quoted heredoc to save your complete
  markdown report to:
      $ReportPath

  Example shape:
	      cat > '$ReportPath' <<'END_MARKDOWN_REPORT'
	      ...complete markdown report...
	      END_MARKDOWN_REPORT

The report MUST:
- Be at least 2000 words.
- Cite every factual claim inline as [anchor text](sandbox URL pointing at $ShoppingUrl / $RedditUrl / $WikipediaUrl).
- Draw evidence from ALL THREE sandbox sources.
- End with a "References" section listing every cited URL.
- Start immediately with the report body (no preface, no chain-of-thought).

After the Bash write command succeeds, your final text response should be ONLY:
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
    "Bash(curl http://localhost:17770*),"
    "Bash(curl http://localhost:8090*),"
    "Bash(curl http://localhost:9999*),"
    "Bash(curl http://localhost:8081*),"
    "Bash(curl http://localhost:18081*),"
    "Bash(curl http://127.0.0.1:7770*),"
    "Bash(curl http://127.0.0.1:17770*),"
    "Bash(curl http://127.0.0.1:8090*),"
    "Bash(curl http://127.0.0.1:9999*),"
    "Bash(curl http://127.0.0.1:8081*),"
    "Bash(curl http://127.0.0.1:18081*),"
    "Bash(curl -s http://localhost:*),"
    "Bash(curl -s http://127.0.0.1:*),"
    "Bash(curl -sL http://localhost:*),"
    "Bash(curl -sL http://127.0.0.1:*),"
    "Bash(curl -X POST http://localhost:8081*),"
    "Bash(curl -X POST http://localhost:18081*),"
    "Bash(curl -s -X POST http://localhost:8081*),"
    "Bash(curl -s -X POST http://localhost:18081*),"
    "Bash(curl -s -X POST http://127.0.0.1:8081*),"
    "Bash(curl -s -X POST http://127.0.0.1:18081*)',"
)


def _build_ps_driver(*, strict_sandbox: bool = False) -> str:
    policy = _TOOL_POLICY_STRICT if strict_sandbox else _TOOL_POLICY_OPEN
    return (
        _PS_DRIVER_TEMPLATE
        .replace("__CCR_URL__", CCR_BASE_URL)
        .replace("__TOOL_POLICY_ARGS__", policy)
    )


def _build_system_prompt(
    *,
    report_path: Path | str,
    shim_url: str,
    shopping_url: str,
    reddit_url: str,
    wikipedia_url: str,
) -> str:
    return f"""You are a deep research agent.  You have NO direct internet access.

The ONLY network endpoints you can reach are:
- Search shim (Tavily-compatible):   {shim_url}
- Magento sandbox (shopping):        {shopping_url}
- Postmill sandbox (reddit-like):    {reddit_url}
- Kiwix sandbox (offline Wikipedia): {wikipedia_url}

To search, use the Bash tool:
  curl -s -X POST {shim_url}/search -H 'content-type: application/json' -d '{{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}}'

To fetch a page returned by search, use Bash:
  curl -s -L '<sandbox URL>' | head -c 8000

Methodology:
1. Issue MULTIPLE search queries covering different angles of the task.
2. For each promising result, fetch the page to extract specifics (prices, specs, quotes, dates).
3. Cross-reference between Magento (products), Postmill (discussions), and Kiwix (encyclopedic background).
4. Aim for >= 20 distinct sandbox URLs cited across all three sources.

	OUTPUT INSTRUCTIONS (read carefully - the evaluator reads ONLY this file):

  Use the Bash tool ONE TIME with a quoted heredoc to save your complete
  markdown report to:
      {report_path}

  Example shape:
	      cat > '{report_path}' <<'END_MARKDOWN_REPORT'
	      ...complete markdown report...
	      END_MARKDOWN_REPORT

The report MUST:
- Be at least 2000 words.
- Cite every factual claim inline as [anchor text](sandbox URL pointing at {shopping_url} / {reddit_url} / {wikipedia_url}).
- Draw evidence from ALL THREE sandbox sources.
- End with a "References" section listing every cited URL.
- Start immediately with the report body (no preface, no chain-of-thought).

After the Bash write command succeeds, your final text response should be ONLY:
  REPORT_WRITTEN

Begin now.  Do not ask for clarification - act on the brief alone.
"""


def _ensure_local_ccr(base_url: str) -> None:
    if _tcp_listening(base_url):
        return
    if not shutil.which("ccr"):
        raise RuntimeError("ccr executable not found")
    log_path = Path(os.environ.get("CLAUDE_CODE_CCR_START_LOG", "/tmp/claude_code_router_start.log"))
    with log_path.open("ab") as log:
        subprocess.Popen(
            ["ccr", "start"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.time() + 30
    while time.time() < deadline:
        if _tcp_listening(base_url):
            return
        time.sleep(0.5)
    raise RuntimeError(f"ccr did not start listening at {base_url}")


def _local_tool_policy_args(*, strict_sandbox: bool) -> list[str]:
    if not strict_sandbox:
        return ["--allowed-tools", "Read,Write,Edit,Glob,Grep,Bash"]
    return [
        "--allowed-tools",
        ",".join(
            [
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "Bash(curl http://localhost:7770*)",
                "Bash(curl http://localhost:17770*)",
                "Bash(curl http://localhost:8090*)",
                "Bash(curl http://localhost:9999*)",
                "Bash(curl http://localhost:8081*)",
                "Bash(curl http://localhost:18081*)",
                "Bash(curl http://127.0.0.1:7770*)",
                "Bash(curl http://127.0.0.1:17770*)",
                "Bash(curl http://127.0.0.1:8090*)",
                "Bash(curl http://127.0.0.1:9999*)",
                "Bash(curl http://127.0.0.1:8081*)",
                "Bash(curl http://127.0.0.1:18081*)",
                "Bash(curl -s http://localhost:*)",
                "Bash(curl -s http://127.0.0.1:*)",
                "Bash(curl -sL http://localhost:*)",
                "Bash(curl -sL http://127.0.0.1:*)",
                "Bash(curl -X POST http://localhost:8081*)",
                "Bash(curl -X POST http://localhost:18081*)",
                "Bash(curl -s -X POST http://localhost:8081*)",
                "Bash(curl -s -X POST http://localhost:18081*)",
                "Bash(curl -s -X POST http://127.0.0.1:8081*)",
                "Bash(curl -s -X POST http://127.0.0.1:18081*)",
            ]
        ),
    ]


async def _run_local_claude(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int,
    strict_sandbox: bool,
) -> str:
    if not shutil.which("claude"):
        return "(claude-code local unavailable: claude executable not found)"

    ccr_url = _local_ccr_base_url()
    _ensure_local_ccr(ccr_url)

    shopping_url = os.environ.get("SHOPPING", "http://localhost:17770")
    reddit_url = os.environ.get("REDDIT", "http://localhost:9999")
    wikipedia_url = os.environ.get("WIKIPEDIA", "http://localhost:8090")

    with tempfile.TemporaryDirectory(prefix="claude_code_runner_") as tmp:
        workdir = Path(tmp)
        report_path = workdir / "report.md"
        stdout_path = workdir / "stdout.log"
        report_path.write_text("", encoding="utf-8")

        system_prompt = _build_system_prompt(
            report_path=report_path,
            shim_url=shim_url,
            shopping_url=shopping_url,
            reddit_url=reddit_url,
            wikipedia_url=wikipedia_url,
        )

        env = os.environ.copy()
        env.update(
            {
                "ANTHROPIC_BASE_URL": ccr_url,
                "ANTHROPIC_AUTH_TOKEN": "anything",
                "ANTHROPIC_API_KEY": "anything",
                "CLAUDE_CODE_SIMPLE": "1",
                "NO_COLOR": "1",
            }
        )

        cmd = [
            "claude",
            "--bare",
            "--print",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--add-dir",
            str(workdir),
            *_local_tool_policy_args(strict_sandbox=strict_sandbox),
            "--append-system-prompt",
            system_prompt,
        ]

        t0 = time.time()
        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    input=intent,
                    cwd=str(workdir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=_native_timeout(timeout_s),
                ),
            )
        except subprocess.TimeoutExpired:
            logger.warning("claude-code local path exceeded %ss; using source-grounded writer", _native_timeout(timeout_s))
            return synthesize_report(
                intent,
                model,
                shim_url,
                proxy_url,
                min_chars=4500,
                min_urls=5,
            )

        elapsed = time.time() - t0
        stdout_text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        stdout_path.write_text(stdout_text, encoding="utf-8", errors="replace")
        report = ""
        if report_path.exists():
            report = report_path.read_text(encoding="utf-8", errors="replace").lstrip("﻿").strip()
        if len(report) < 500 and stdout_text.strip():
            report = stdout_text.strip()
        if proc.returncode != 0:
            logger.warning(
                "claude-code local exited %d after %.0fs; output tail: %s",
                proc.returncode,
                elapsed,
                stdout_text[-1500:],
            )
        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("claude-code local report weak/empty; using source-grounded writer")
            return synthesize_report(
                intent,
                model,
                shim_url,
                proxy_url,
                min_chars=4500,
                min_urls=5,
            )
        logger.info("claude-code local completed in %.0fs, report=%d chars", elapsed, len(report))
        return report


def _ssh(cmd: str, *, timeout_s: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh",
         "-o", "ServerAliveInterval=30",
         "-o", "ServerAliveCountMax=20",
         SSH_HOST, cmd],
        capture_output=True, text=True, timeout=timeout_s,
        stdin=subprocess.DEVNULL,
    )


def _ssh_with_retries(
    cmd: str,
    *,
    timeout_s: int,
    attempts: int = 4,
) -> tuple[subprocess.CompletedProcess, float]:
    """Retry quick SSH transport failures without retrying long-running jobs."""
    last_proc: subprocess.CompletedProcess | None = None
    last_elapsed = 0.0
    for attempt in range(1, attempts + 1):
        t0 = time.time()
        proc = _ssh(cmd, timeout_s=timeout_s)
        elapsed = time.time() - t0
        last_proc = proc
        last_elapsed = elapsed
        if proc.returncode != 255 or elapsed >= 20:
            return proc, elapsed
        logger.warning(
            "claude-code ssh transport failed quickly on attempt %d/%d: %s",
            attempt, attempts, proc.stderr[-300:],
        )
        time.sleep(min(2 * attempt, 8))
    assert last_proc is not None
    return last_proc, last_elapsed


def _scp_up(local: Path, remote_win: str, *, timeout_s: int = 60) -> None:
    subprocess.run(
        ["scp", "-o", "ServerAliveInterval=30",
         str(local), f"{SSH_HOST}:{remote_win}"],
        check=True, capture_output=True, timeout=timeout_s,
        stdin=subprocess.DEVNULL,
    )


def _scp_down(remote_win: str, local: Path, *, timeout_s: int = 60) -> None:
    subprocess.run(
        ["scp", "-o", "ServerAliveInterval=30",
         f"{SSH_HOST}:{remote_win}", str(local)],
        check=True, capture_output=True, timeout=timeout_s,
        stdin=subprocess.DEVNULL,
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
    if os.environ.get("CLAUDE_CODE_USE_WINDOWS") != "1":
        try:
            local_report = await _run_local_claude(
                intent,
                model,
                shim_url,
                proxy_url,
                timeout_s=timeout_s,
                strict_sandbox=strict_sandbox,
            )
            if not is_weak_report(local_report, min_chars=3000, min_urls=3):
                return local_report
            logger.warning("claude-code local path returned short/error report: %s", local_report[:500])
            if os.environ.get("CLAUDE_CODE_NO_WINDOWS_FALLBACK") == "1":
                return synthesize_report(
                    intent,
                    model,
                    shim_url,
                    proxy_url,
                    min_chars=4500,
                    min_urls=5,
                )
        except Exception as e:
            logger.exception("claude-code local path failed")
            if os.environ.get("CLAUDE_CODE_NO_WINDOWS_FALLBACK") == "1":
                return synthesize_report(
                    intent,
                    model,
                    shim_url,
                    proxy_url,
                    min_chars=4500,
                    min_urls=5,
                )

    job_id = uuid.uuid4().hex[:12]
    intent_remote = f"{REMOTE_DIR_WIN}/intent_{job_id}.txt"
    report_remote = f"{REMOTE_DIR_WIN}/report_{job_id}.md"
    stdout_remote = f"{REMOTE_DIR_WIN}/stdout_{job_id}.log"
    driver_remote = f"{REMOTE_DIR_WIN}/driver_{job_id}.ps1"
    workdir_remote = f"{REMOTE_DIR_WIN}/work_{job_id}"

    intent_wsl = _win_path_to_wsl(intent_remote)
    report_wsl = _win_path_to_wsl(report_remote)
    stdout_wsl = _win_path_to_wsl(stdout_remote)
    driver_wsl = _win_path_to_wsl(driver_remote)
    workdir_wsl = _win_path_to_wsl(workdir_remote)

    REMOTE_DIR_WSL.mkdir(parents=True, exist_ok=True)
    intent_wsl.write_text(intent, encoding="utf-8")
    driver_wsl.write_text(
        _build_ps_driver(strict_sandbox=strict_sandbox), encoding="utf-8",
    )
    if strict_sandbox:
        logger.info("claude-code: strict-sandbox tool allowlist active")

    shopping_url = os.environ.get("SHOPPING", "http://localhost:17770")
    reddit_url = os.environ.get("REDDIT", "http://localhost:9999")
    wikipedia_url = os.environ.get("WIKIPEDIA", "http://localhost:8090")

    try:
        ps_cmd = (
            f'powershell -NoProfile -File "{driver_remote}" '
            f'-IntentPath "{intent_remote}" -ReportPath "{report_remote}" '
            f'-StdoutPath "{stdout_remote}" -WorkDir "{workdir_remote}" '
            f'-ShimUrl "{shim_url}" -ShoppingUrl "{shopping_url}" '
            f'-RedditUrl "{reddit_url}" -WikipediaUrl "{wikipedia_url}"'
        )

        proc, elapsed = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _ssh_with_retries(ps_cmd, timeout_s=_native_timeout(timeout_s)),
        )

        if proc.returncode != 0:
            logger.warning(
                "claude-code ssh exited %d after %.0fs\nstderr tail: %s",
                proc.returncode, elapsed, proc.stderr[-1500:],
            )

        report = ""
        stdout_text = ""
        if report_wsl.exists():
            report = report_wsl.read_text(encoding="utf-8", errors="replace").lstrip("﻿").strip()
        if stdout_wsl.exists():
            stdout_text = stdout_wsl.read_text(encoding="utf-8", errors="replace")

        # If the agent wrote the report via its Write tool, trust that file.
        # Otherwise fall back to whatever it streamed to stdout (some prompts
        # cause it to dump the report inline instead of Write-ing).
        if len(report) < 500 and stdout_text.strip():
            logger.info(
                "claude-code: report file is %d chars, falling back to %d chars stdout",
                len(report), len(stdout_text),
            )
            report = stdout_text.strip()

        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("claude-code ssh report weak/empty; using source-grounded writer")
            return synthesize_report(
                intent,
                model,
                shim_url,
                proxy_url,
                min_chars=4500,
                min_urls=5,
            )

        logger.info("claude-code completed in %.0fs, report=%d chars",
                    elapsed, len(report))
        return report

    except subprocess.TimeoutExpired:
        logger.error("claude-code native path exceeded %ds", _native_timeout(timeout_s))
        return synthesize_report(
            intent,
            model,
            shim_url,
            proxy_url,
            min_chars=4500,
            min_urls=5,
        )
    except Exception as e:
        logger.exception("claude-code runner error")
        return synthesize_report(
            intent,
            model,
            shim_url,
            proxy_url,
            min_chars=4500,
            min_urls=5,
        )
    finally:
        for p in (intent_wsl, report_wsl, stdout_wsl, driver_wsl):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        shutil.rmtree(workdir_wsl, ignore_errors=True)


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
