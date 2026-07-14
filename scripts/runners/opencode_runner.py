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
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .evidence_fallback import (
    error_stub,
    fallback_enabled,
    is_weak_report,
    keep_or_stub,
    synthesize_report,
)
from . import _egress

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
AGENT_NAME = "opencode"

# Workstream C — strict-sandbox eligibility.
# OpenCode's `permission.bash` block in opencode.json is the shell-command
# gate. Every run receives an allowlist scoped to its exact SHIM ORIGIN plus
# the report editor. Anything else, including a bare
# `curl http://localhost:7770/...` (on-box but bypassing the shim's
# record_fetch), `curl https://en.wikipedia.org`, `wget`, `nslookup`, `node -e
# 'fetch(...)'` — is auto-rejected by opencode itself. Only the strict path
# converges fetch: this lane is fetch-observable ONLY when strict_sandbox=True.
STRICT_SANDBOX_ELIGIBLE = True

# Floor at 1800s: the Qwen3-8B full run set OPENCODE_TIMEOUT=360, which timed out
# 36/55 opencode tasks (a local 8B doing 20+ tool calls needs far more). Honour an
# operator override only when it raises the ceiling, never below the safe floor.
DEFAULT_TIMEOUT_S = max(1800, int(os.environ.get("OPENCODE_TIMEOUT", "1800") or "1800"))
# Unified default, identical for every lane (see scripts/runners/_budget.py):
# None = no native self-abort, the no-progress watchdog terminates a stall.
try:
    from . import _budget
except ImportError:  # run as a bare script rather than a package module
    import _budget  # type: ignore
DEFAULT_NATIVE_TIMEOUT_S = _budget.native_timeout_default()
# No "5090" default: that literal parses as the decimal IPv4 0.0.19.226 and
# burned ~150s per connect attempt (claudecode_runner learned this first).
# The remote path is opt-in; unset means fail fast with a clear message.
SSH_HOST = os.environ.get("OPENCODE_SSH_HOST", os.environ.get("CLAUDE_CODE_SSH_HOST", "")).strip()
REMOTE_DIR_WIN = os.environ.get("OPENCODE_REMOTE_DIR", "C:/tools/opencode_runner")
# opencode model format: "provider/model".  Default routes to ds_proxy → DeepSeek
# V4 flash for cost parity with the rest of the benchmark.  The "ds-shim"
# provider is defined inline in the driver via env+config injection.
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "ds-shim/deepseek-v4-flash")
# Legacy opencode-only base-URL knob. Kept for backward compatibility, but the
# effective base URL is now resolved by `_resolve_llm_base_url` (see below):
# a bare *default* here no longer silently outranks the harness-wired
# DS_PROXY_URL (the clamp proxy on the box).
OPENCODE_DS_PROXY = os.environ.get("OPENCODE_DS_PROXY", "http://localhost:8100/v1")

# Output-token seatbelt. The box fronts its local vLLM (--max-model-len 40960)
# with a clamp proxy that caps max_tokens, but a request that reaches vLLM
# directly (clamp bypassed) inherits opencode's default max_tokens (~32000):
# prompt(8961) + 32000 = 40961 > 40960 → HTTP 400. So we *also* cap the model's
# output tokens in the generated opencode.json (`limit.output`), independent of
# any proxy. Use the protocol-wide cap; the former 3840 default gave this lane
# less than half the output budget available to every other framework.
OPENCODE_MAX_OUTPUT_TOKENS_DEFAULT = 8192
# Context window opencode should assume for the inline ds-shim model. Matches
# the box vLLM --max-model-len; larger-context backbones (GLM, DeepSeek) are
# only conservatively trimmed by this, never broken, for these ~9k-token tasks.
OPENCODE_CONTEXT_LIMIT_DEFAULT = 40960


def _resolve_llm_base_url(proxy_url: str | None) -> str:
    """Resolve the OpenAI-compatible base URL the opencode ds-shim provider
    should target, in precedence order:

      1. OPENCODE_LLM_BASE_URL (env): explicit opencode-only override.
      2. OPENCODE_DS_PROXY (env, explicit): the long-standing opencode knob.
         `glm_oneagent.sh` sets it to $DS_PROXY_URL, so GLM/CCR keep working.
      3. proxy_url argument: the canonical DS_PROXY_URL the harness wires in.
         On the box this is the max_tokens *clamp* proxy.
      4. DS_PROXY_URL (env): same source, for out-of-harness calls.
      5. http://localhost:8100/v1: last-resort default.

    Why: the module-level OPENCODE_DS_PROXY *default* (:8088, the non-clamping
    ds_proxy) used to be baked into the PowerShell invocation and thus
    unconditionally outranked the harness-wired proxy_url. A box that pointed
    DS_PROXY_URL at the clamp (:8002) was therefore silently bypassed and
    opencode hit vLLM (:8001) with an unclamped max_tokens (the HTTP 400 seen
    in the smoke). Only an *explicit* OPENCODE_DS_PROXY now outranks proxy_url.
    """
    for cand in (
        os.environ.get("OPENCODE_LLM_BASE_URL"),
        os.environ.get("OPENCODE_DS_PROXY"),
        proxy_url,
        os.environ.get("DS_PROXY_URL"),
    ):
        if cand:
            return cand
    return "http://localhost:8100/v1"


def _resolve_output_cap() -> int:
    """Max output tokens to write into the generated opencode config. Defaults
    to OPENCODE_MAX_OUTPUT_TOKENS_DEFAULT (8192); overridable via
    OPENCODE_MAX_OUTPUT_TOKENS for larger-context backbones."""
    try:
        v = int(os.environ.get("OPENCODE_MAX_OUTPUT_TOKENS", "") or OPENCODE_MAX_OUTPUT_TOKENS_DEFAULT)
    except (TypeError, ValueError):
        v = OPENCODE_MAX_OUTPUT_TOKENS_DEFAULT
    return max(1, v)


def _resolve_context_limit() -> int:
    """Context window opencode should assume for the inline model. Defaults to
    OPENCODE_CONTEXT_LIMIT_DEFAULT (40960); overridable via
    OPENCODE_CONTEXT_LIMIT."""
    try:
        v = int(os.environ.get("OPENCODE_CONTEXT_LIMIT", "") or OPENCODE_CONTEXT_LIMIT_DEFAULT)
    except (TypeError, ValueError):
        v = OPENCODE_CONTEXT_LIMIT_DEFAULT
    return max(1, v)


def _shim_curl_patterns(shim_url: str) -> list[str]:
    """Exact OpenCode bash patterns for the configured shim origin.

    Formal workers rewrite the shim from localhost to their veth gateway. A
    hardcoded localhost allowlist therefore rejects every legitimate search.
    """
    parsed = urlsplit(str(shim_url or ""))
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError(f"shim_url must be a plain HTTP URL: {shim_url!r}")
    port = parsed.port or 80
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    origin = f"http://{host}:{port}"
    return [
        f"curl {origin}*",
        f"curl -s {origin}*",
        f"curl -X POST {origin}*",
        f"curl -s -X POST {origin}*",
    ]


def _native_timeout(timeout_s):
    # Unified native timeout. Default identical to every lane (DRA_WALL_CLOCK_S);
    # OPENCODE_NATIVE_TIMEOUT_S still overrides. The old hard 420s default was a
    # per-lane wall clock; None (unlimited) defers termination to the shared
    # no-progress watchdog and the outer subprocess cap.
    configured = _budget.resolve_native_timeout("OPENCODE_NATIVE_TIMEOUT_S")
    if configured is None:
        return timeout_s
    if timeout_s is None:
        return max(60, int(configured))
    return max(60, min(int(timeout_s), int(configured)))


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
  [string]$EgressProxyUrl,
  [int]$MaxOutputTokens = 8192,
  [int]$ContextLimit = 40960,
  [int]$StrictSandbox = 0
)
$ErrorActionPreference = 'Continue'
if ($EgressProxyUrl) {
  $env:HTTP_PROXY = $EgressProxyUrl
  $env:HTTPS_PROXY = $EgressProxyUrl
  $env:ALL_PROXY = $EgressProxyUrl
  $env:NO_PROXY = ''
}

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
# `permission` is mandatory so opencode's shell tool rejects anything that is
# not a shim curl and every file-inspection tool stays disabled. OpenCode 1.16
# rejects the retired `commands.allowed` key as an invalid configuration.
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
        'deepseek-v4-flash' = @{ name = 'DeepSeek V4 Flash'; limit = @{ context = $ContextLimit; output = $MaxOutputTokens } }
        'deepseek-chat'     = @{ name = 'DeepSeek Chat';     limit = @{ context = $ContextLimit; output = $MaxOutputTokens } }
      }
    }
  }
}
# Capability enforcement is mandatory, not an optional diagnostic mode. Build
# the patterns from the exact runtime origin because formal workers replace
# localhost with their veth gateway.
$shimOrigin = ([Uri]$ShimUrl).GetLeftPart([System.UriPartial]::Authority).TrimEnd('/')
$bashRules = [ordered]@{'*' = 'deny'}
$bashRules["curl $shimOrigin*"] = 'allow'
$bashRules["curl -s $shimOrigin*"] = 'allow'
$bashRules["curl -X POST $shimOrigin*"] = 'allow'
$bashRules["curl -s -X POST $shimOrigin*"] = 'allow'
$ocConfigObj['permission'] = [ordered]@{
  '*' = 'deny'
  'edit' = 'allow'
  'bash' = $bashRules
  'external_directory' = 'deny'
}
$ocConfig = $ocConfigObj | ConvertTo-Json -Depth 10
$ocConfigPath = Join-Path $WorkDir 'opencode.json'
# Write WITHOUT BOM — opencode's JSONC parser rejects the BOM.
[System.IO.File]::WriteAllText($ocConfigPath, $ocConfig, (New-Object System.Text.UTF8Encoding $false))
$env:OPENCODE_CONFIG = $ocConfigPath
$env:OPENAI_API_KEY  = 'anything-proxy-uses-server-key'

Push-Location $WorkDir

$intent = Get-Content -Raw -Path $IntentPath

$modelID = $Model
if ($modelID.Contains('/')) {
  $modelID = $modelID.Split('/')[-1]
}
# Seatbelt: cap output tokens (and declare the context window) so a request
# that reaches vLLM directly (clamp proxy bypassed) can never exceed
# --max-model-len. See _resolve_output_cap / _resolve_context_limit.
$ocConfigObj.provider.'ds-shim'.models[$modelID] = @{ name = $modelID; limit = @{ context = $ContextLimit; output = $MaxOutputTokens } }
$ocConfig = $ocConfigObj | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ocConfigPath, $ocConfig, (New-Object System.Text.UTF8Encoding $false))

$systemPrompt = @"
You are a deep research agent.  You have NO direct internet access. Use the
benchmark search shim for search and page reads.

To search, use the shell tool (Windows PowerShell / cmd — `head`/`tail` are NOT available):
  curl -s -X POST $ShimUrl/search -H 'content-type: application/json' -d '{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}'

To fetch and read a page returned by search, use the shell tool. Route it
through the shim's /fetch so the read is recorded; a bare curl of the site URL
is rejected by the command allowlist:
  curl -s "$ShimUrl/fetch?url=<sandbox URL>"

OUTPUT INSTRUCTIONS (read carefully — the harness reads ONLY this file):

  Write the task response to:
      $InnerReport
  using the write file tool.  This path is INSIDE your workspace; do NOT use any
  other path (writes to parents of the workspace are auto-rejected).
  Do NOT print the report inline as your final message — the harness reads the
  file, not the message.

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


def _opencode_config(
    model_id: str,
    base_url: str,
    *,
    strict_sandbox: bool,
    shim_url: str = "http://localhost:8081",
    max_output_tokens: int | None = None,
    context_limit: int | None = None,
) -> dict:
    # Seatbelt: cap output tokens (and declare the context window) on every
    # inline model so a request that reaches vLLM directly (clamp proxy
    # bypassed) can never blow past --max-model-len. Independent of any proxy.
    out_cap = max_output_tokens if max_output_tokens is not None else _resolve_output_cap()
    ctx_lim = context_limit if context_limit is not None else _resolve_context_limit()
    _limit = {"context": ctx_lim, "output": out_cap}
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "ds-shim": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "DeepSeek (ds_proxy shim)",
                "options": {
                    "baseURL": base_url,
                    "apiKey": "anything-proxy-uses-server-key",
                },
                "models": {
                    "deepseek-v4-flash": {"name": "DeepSeek V4 Flash", "limit": dict(_limit)},
                    "deepseek-chat": {"name": "DeepSeek Chat", "limit": dict(_limit)},
                    model_id: {"name": model_id, "limit": dict(_limit)},
                },
            }
        },
    }
    # OpenCode 1.16 uses `permission`; `commands.allowed` is rejected as an
    # unrecognized key. Deny every tool by default, then admit only report
    # editing and the four exact shim-curl prefixes. The working directory is
    # a fresh per-run scratch, so edit cannot expose benchmark files.
    cfg["permission"] = {
        "*": "deny",
        "edit": "allow",
        "bash": {
            "*": "deny",
            **{pattern: "allow" for pattern in _shim_curl_patterns(shim_url)},
        },
        "external_directory": "deny",
    }
    return cfg


def _build_full_prompt(
    intent: str,
    *,
    shim_url: str,
    shopping_url: str,
    reddit_url: str,
    wikipedia_url: str,
    report_path: Path,
) -> str:
    return f"""[SYSTEM INSTRUCTIONS - read first, follow strictly]
You are a deep research agent. You have no internet access. Use the benchmark
search shim for search and page reads.

Search the sandbox:
  curl -s -X POST {shim_url}/search -H 'content-type: application/json' \\
       -d '{{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}}'

Read a page the search returned:
  curl -s '{shim_url}/fetch?url=<sandbox URL>'

Any other command, host, or tool is rejected.

OUTPUT INSTRUCTIONS:
Write the task response to:
  {report_path}

After writing the file, your final text response should be only:
REPORT_WRITTEN


[TASK]
{intent}
"""


async def _run_local_opencode(
    *,
    intent: str,
    opencode_model: str,
    shim_url: str,
    base_url: str,
    timeout_s: int,
    strict_sandbox: bool,
) -> str:
    opencode_bin = shutil.which("opencode")
    if not opencode_bin:
        raise FileNotFoundError("opencode")

    model_id = opencode_model.split("/", 1)[1] if "/" in opencode_model else opencode_model

    def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: an opencode failure must surface as the framework's
        # own (missing) output, never as a harness-ghostwritten report. In
        # benchmark mode we save an honest error stub; the evidence writer runs
        # only under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return synthesize_report(
                intent,
                model_id,
                shim_url,
                base_url,
                min_chars=4500,
                min_urls=5,
            )
        return error_stub("opencode", phase, reason)
    shopping_url = os.environ.get("SHOPPING", "http://localhost:17770")
    reddit_url = os.environ.get("REDDIT", "http://localhost:9999")
    wikipedia_url = os.environ.get("WIKIPEDIA", "http://localhost:8090")

    with tempfile.TemporaryDirectory(prefix="opencode_runner_") as tmp:
        workdir = Path(tmp)
        report_path = workdir / "report.md"
        config_path = workdir / "opencode.json"
        stdout_path = workdir / "stdout.log"
        # `strict_sandbox=False` here silently disabled the shell-command
        # allowlist on the lane's PRIMARY local path, while the Windows path ran
        # with the gate on. Honour the caller's flag.
        cfg = _opencode_config(
            model_id,
            base_url,
            strict_sandbox=strict_sandbox,
            shim_url=shim_url,
        )
        config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        report_path.write_text("", encoding="utf-8")
        # The harness used to run the searches itself (`_prefetch_sandbox_evidence`)
        # and paste the results into the prompt, so this lane was not doing
        # agentic retrieval at all: it was summarising a corpus we handed it.
        # Removed 2026-07-08 (fairness audit). opencode now searches the shim
        # through its own shell tool, like every other lane.
        prompt = _build_full_prompt(
            intent,
            shim_url=shim_url,
            shopping_url=shopping_url,
            reddit_url=reddit_url,
            wikipedia_url=wikipedia_url,
            report_path=report_path,
        )
        env = {**os.environ}
        env["OPENCODE_CONFIG"] = str(config_path)
        env["OPENAI_API_KEY"] = "anything-proxy-uses-server-key"
        _egress.scrub_or_apply(env)

        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        opencode_bin,
                        "run",
                        "--model", opencode_model,
                        "--format", "default",
                        "--dir", str(workdir),
                        prompt,
                    ],
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                    timeout=_native_timeout(timeout_s),
                    env=env,
                ),
            )
        except subprocess.TimeoutExpired:
            logger.warning("opencode native path exceeded %ss", _native_timeout(timeout_s))
            return _degrade(
                "native", f"native path exceeded {_native_timeout(timeout_s)}s timeout"
            )
        stdout_path.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
        report = report_path.read_text(encoding="utf-8", errors="replace").lstrip("﻿").strip()
        stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
        if not report:
            return _degrade(
                "write",
                "opencode did not write the requested report file; "
                f"stdout tail={stdout_text[-500:]}",
            )
        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("opencode native report weak/empty")
            # Weak-but-real output is opencode's own report: save it verbatim
            # (the scorer judges quality); stub only genuinely empty/stub output.
            return keep_or_stub("opencode", "write", "native report weak/under-threshold", report)
        return report


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
        proxy_url: OpenAI-compatible base URL for the LLM backbone. This is the
            harness-wired DS_PROXY_URL (on the box, the max_tokens *clamp*
            proxy). Used as the default ds-shim `baseURL` unless
            OPENCODE_LLM_BASE_URL / OPENCODE_DS_PROXY overrides it. See
            `_resolve_llm_base_url`.
        timeout_s: hard timeout for the remote subprocess.
        strict_sandbox: when True, the per-run `opencode.json` includes a
            `permission.bash` whitelist that admits only sandbox-local
            curl commands plus read-only file utilities. Anything else
            is rejected by opencode's own command gate — the soft prompt
            is no longer the gate.
    """
    # Caller may pass a bare "deepseek-v4-flash" or the full "ds-shim/deepseek-v4-flash"
    # form. Both map to the per-run ds-shim provider defined in the driver.
    if model and "/" in model:
        opencode_model = model
    elif model:
        opencode_model = f"ds-shim/{model}"
    else:
        opencode_model = OPENCODE_MODEL

    # Resolve the LLM endpoint the ds-shim provider targets. Defaults to the
    # harness-wired proxy_url (the clamp proxy on the box) unless an explicit
    # OPENCODE_LLM_BASE_URL / OPENCODE_DS_PROXY overrides it. See
    # _resolve_llm_base_url for the full precedence and the bug it fixes.
    base_url = _resolve_llm_base_url(proxy_url)
    out_cap = _resolve_output_cap()
    ctx_lim = _resolve_context_limit()

    def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: an opencode failure must surface as the framework's
        # own (missing) output, never as a harness-ghostwritten report. In
        # benchmark mode we save an honest error stub; the evidence writer runs
        # only under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return synthesize_report(
                intent,
                opencode_model.split("/", 1)[1] if "/" in opencode_model else opencode_model,
                shim_url,
                base_url,
                min_chars=4500,
                min_urls=5,
            )
        return error_stub("opencode", phase, reason)

    if os.environ.get("OPENCODE_USE_WINDOWS", "0") != "1" and shutil.which("opencode"):
        try:
            return await _run_local_opencode(
                intent=intent,
                opencode_model=opencode_model,
                shim_url=shim_url,
                base_url=base_url,
                timeout_s=timeout_s,
                strict_sandbox=strict_sandbox,
            )
        except Exception as e:
            logger.warning("local opencode failed, falling back to Windows SSH: %s", e)
            if _egress.enforced() and not _egress.remote_enforced():
                raise RuntimeError(
                    "local opencode failed and the Windows fallback has no "
                    "attested route to the bracketed egress door"
                ) from e

    if not SSH_HOST:
        raise RuntimeError(
            "local opencode is unavailable and OPENCODE_SSH_HOST is unset; "
            "the remote path is opt-in. Set it to an ssh alias, never a bare "
            "port number."
        )

    if _egress.enforced() and not _egress.remote_enforced():
        raise RuntimeError(
            "opencode Windows mode requires DRA_REMOTE_EGRESS_PROXY and "
            "DRA_REMOTE_EGRESS_ENFORCED=1 after remote isolation preflight"
        )

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

    shopping_url = os.environ.get("SHOPPING", "http://localhost:17770")
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
            f'-DsProxyUrl "{base_url}" '
            f'-EgressProxyUrl "{_egress.remote_proxy()}" '
            f'-MaxOutputTokens {out_cap} -ContextLimit {ctx_lim} '
            f'-StrictSandbox {1 if strict_sandbox else 0}'
        )
        if strict_sandbox:
            logger.info("opencode: strict-sandbox permission.bash allowlist active")

        t0 = time.time()
        proc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["ssh",
                 "-o", "ServerAliveInterval=30",
                 "-o", "ServerAliveCountMax=40",
                 SSH_HOST, ps_cmd],
                capture_output=True, text=True, timeout=_native_timeout(timeout_s),
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

        if not report:
            return _degrade(
                "write",
                "opencode did not write the requested report file; "
                f"stdout tail={stdout_text[-500:]}",
            )

        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("opencode ssh report weak/empty")
            # Weak-but-real output is opencode's own report: save it verbatim
            # (the scorer judges quality); stub only genuinely empty/stub output.
            return keep_or_stub("opencode", "write", "native report weak/under-threshold", report)

        logger.info("opencode completed in %.0fs, report=%d chars",
                    elapsed, len(report))
        return report

    except subprocess.TimeoutExpired:
        logger.error("opencode native path exceeded %ds", _native_timeout(timeout_s))
        return _degrade(
            "native", f"native path exceeded {_native_timeout(timeout_s)}s timeout"
        )
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
    parser.add_argument("intent", nargs="?", default="")
    parser.add_argument("--model", default=OPENCODE_MODEL)
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--proxy-url", default="http://localhost:8100/v1")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--output", "-o")
    parser.add_argument("--strict-sandbox", action="store_true", default=False)
    parser.add_argument(
        "--dry-run-config",
        action="store_true",
        default=False,
        help="Print the resolved base_url + generated opencode.json for --model "
             "and exit, without contacting opencode or the 5090 box. Use to "
             "verify endpoint/token-cap wiring workstation-side.",
    )
    args = parser.parse_args()

    if args.dry_run_config:
        _model = args.model
        if _model and "/" in _model:
            _oc_model = _model
        elif _model:
            _oc_model = f"ds-shim/{_model}"
        else:
            _oc_model = OPENCODE_MODEL
        _model_id = _oc_model.split("/", 1)[1] if "/" in _oc_model else _oc_model
        _base = _resolve_llm_base_url(args.proxy_url)
        _cfg = _opencode_config(_model_id, _base, strict_sandbox=args.strict_sandbox)
        print(f"# backbone (model arg): {_model!r}")
        print(f"# opencode model string: {_oc_model!r}  (model_id={_model_id!r})")
        print(f"# resolved ds-shim base_url: {_base}")
        print(f"# output-token cap (limit.output): {_resolve_output_cap()}")
        print(f"# context limit (limit.context): {_resolve_context_limit()}")
        print("# --- generated opencode.json ---")
        print(json.dumps(_cfg, indent=2))
        raise SystemExit(0)

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
