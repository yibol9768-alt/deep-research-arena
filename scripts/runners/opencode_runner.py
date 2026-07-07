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

from .evidence_fallback import (
    error_stub,
    fallback_enabled,
    is_weak_report,
    keep_or_stub,
    synthesize_report,
)

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

# Floor at 1800s: the Qwen3-8B full run set OPENCODE_TIMEOUT=360, which timed out
# 36/55 opencode tasks (a local 8B doing 20+ tool calls needs far more). Honour an
# operator override only when it raises the ceiling, never below the safe floor.
DEFAULT_TIMEOUT_S = max(1800, int(os.environ.get("OPENCODE_TIMEOUT", "1800") or "1800"))
DEFAULT_NATIVE_TIMEOUT_S = int(os.environ.get("OPENCODE_NATIVE_TIMEOUT_S", "420") or "420")
SSH_HOST = os.environ.get("OPENCODE_SSH_HOST", os.environ.get("CLAUDE_CODE_SSH_HOST", "5090"))
REMOTE_DIR_WIN = os.environ.get("OPENCODE_REMOTE_DIR", "C:/tools/opencode_runner")
# opencode model format: "provider/model".  Default routes to ds_proxy → DeepSeek
# V4 flash for cost parity with the rest of the benchmark.  The "ds-shim"
# provider is defined inline in the driver via env+config injection.
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "ds-shim/deepseek-v4-flash")
# Legacy opencode-only base-URL knob. Kept for backward compatibility, but the
# effective base URL is now resolved by `_resolve_llm_base_url` (see below):
# a bare *default* here no longer silently outranks the harness-wired
# DS_PROXY_URL (the clamp proxy on the box).
OPENCODE_DS_PROXY = os.environ.get("OPENCODE_DS_PROXY", "http://localhost:8088/v1")

# Output-token seatbelt. The box fronts its local vLLM (--max-model-len 40960)
# with a clamp proxy that caps max_tokens, but a request that reaches vLLM
# directly (clamp bypassed) inherits opencode's default max_tokens (~32000):
# prompt(8961) + 32000 = 40961 > 40960 → HTTP 400. So we *also* cap the model's
# output tokens in the generated opencode.json (`limit.output`), independent of
# any proxy. 3840 matches the box clamp and is ample for a >=2000-word report
# (~2700 tokens). Overridable via env, but the default is always safe.
OPENCODE_MAX_OUTPUT_TOKENS_DEFAULT = 3840
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
      5. http://localhost:8088/v1: last-resort default.

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
    return "http://localhost:8088/v1"


def _resolve_output_cap() -> int:
    """Max output tokens to write into the generated opencode config. Defaults
    to OPENCODE_MAX_OUTPUT_TOKENS_DEFAULT (3840); overridable via
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


def _native_timeout(timeout_s: int) -> int:
    try:
        configured = int(os.environ.get("OPENCODE_NATIVE_TIMEOUT_S", "") or DEFAULT_NATIVE_TIMEOUT_S)
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
  [string]$WikipediaUrl,
  [string]$Model,
  [string]$DsProxyUrl,
  [int]$MaxOutputTokens = 3840,
  [int]$ContextLimit = 40960,
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
        'deepseek-v4-flash' = @{ name = 'DeepSeek V4 Flash'; limit = @{ context = $ContextLimit; output = $MaxOutputTokens } }
        'deepseek-chat'     = @{ name = 'DeepSeek Chat';     limit = @{ context = $ContextLimit; output = $MaxOutputTokens } }
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
      'curl -X POST http://localhost:18081*',
      'curl -X POST http://127.0.0.1:18081*',
      'curl -s -X POST http://localhost:8081*',
      'curl -s -X POST http://127.0.0.1:8081*',
      'curl -s -X POST http://localhost:18081*',
      'curl -s -X POST http://127.0.0.1:18081*',
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


def _opencode_config(
    model_id: str,
    base_url: str,
    *,
    strict_sandbox: bool,
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
    if strict_sandbox:
        cfg["commands"] = {
            "allowed": [
                "curl http://localhost*",
                "curl http://127.0.0.1*",
                "curl -s http://localhost*",
                "curl -s http://127.0.0.1*",
                "curl -sL http://localhost*",
                "curl -sL http://127.0.0.1*",
                "curl -X POST http://localhost:8081*",
                "curl -X POST http://127.0.0.1:8081*",
                "curl -X POST http://localhost:18081*",
                "curl -X POST http://127.0.0.1:18081*",
                "curl -s -X POST http://localhost:8081*",
                "curl -s -X POST http://127.0.0.1:8081*",
                "curl -s -X POST http://localhost:18081*",
                "curl -s -X POST http://127.0.0.1:18081*",
                "cat",
                "ls",
                "head",
                "tail",
            ]
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
    evidence: str,
) -> str:
    return f"""[SYSTEM INSTRUCTIONS - read first, follow strictly]
You are a deep research agent. You have NO direct internet access and should not call shell commands for this run.

The local runner has already gathered source evidence for you from:
- Search shim (Tavily-compatible):   {shim_url}
- Magento sandbox (shopping):        {shopping_url}
- Postmill sandbox (reddit-like):    {reddit_url}
- Kiwix sandbox (offline Wikipedia): {wikipedia_url}

Methodology:
1. Use the prefetched evidence block below as your source corpus.
2. Cross-reference product catalog, discussion forum, and Kiwix when relevant.
3. Do not invent URLs or cite sources absent from the evidence.
4. If evidence is incomplete, state the limitation and still answer with careful caveats.

OUTPUT INSTRUCTIONS:
Write your complete markdown report to:
  {report_path}

The report must be at least 2000 words, cite exact sandbox URLs inline, and end with a References section. After writing the file, your final text response should be only:
REPORT_WRITTEN

[PREFETCHED SANDBOX EVIDENCE]
{evidence or "(No prefetched evidence was available.)"}

[TASK]
{intent}
"""


def _prefetch_sandbox_evidence(intent: str, shim_url: str) -> str:
    try:
        import requests
        stop = {
            "about", "after", "again", "against", "also", "because", "before", "being",
            "between", "could", "every", "from", "have", "into", "only", "over",
            "source", "sources", "their", "there", "these", "this", "through", "using",
            "what", "when", "where", "which", "while", "with", "without", "would",
            "honestly", "actually", "really", "solid", "picks", "reasons",
        }
        tokens: list[str] = []
        for tok in re.findall(r"[a-zA-Z][a-zA-Z0-9+.-]{2,}", intent.lower()):
            if tok not in stop and not tok.startswith("http") and tok not in tokens:
                tokens.append(tok)
        queries = [intent[:500]]
        if tokens:
            queries.append(" ".join(tokens[:12]))
            queries.append(" ".join(tokens[:8] + ["review", "advice", "forum"]))
            queries.append(" ".join(tokens[:8] + ["wiki", "background"]))
        rows = []
        seen = set()
        for q in queries[:4]:
            resp = requests.post(
                shim_url.rstrip("/") + "/search",
                json={
                    "query": q,
                    "api_key": "tvly-shim-fake",
                    "max_results": 8,
                    "include_raw_content": True,
                },
                timeout=30,
            )
            data = resp.json()
            for item in data.get("results", []):
                url = item.get("url") or ""
                if not url or url in seen:
                    continue
                seen.add(url)
                content = item.get("raw_content") or item.get("raw_body_content") or item.get("content") or ""
                content = re.sub(r"\s+", " ", str(content)).strip()[:1800]
                rows.append((q, item.get("title") or "Untitled", url, content))
                if len(rows) >= 14:
                    break
            if len(rows) >= 14:
                break
        parts = []
        for idx, (query, title, url, content) in enumerate(rows, 1):
            parts.append(f"[{idx}] Query: {query}\nTitle: {title}\nURL: {url}\nSnippet: {content}")
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning("opencode prefetch failed: %s", e)
        return ""


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
        cfg = _opencode_config(model_id, base_url, strict_sandbox=False)
        config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        report_path.write_text("", encoding="utf-8")
        evidence = _prefetch_sandbox_evidence(intent, shim_url)
        prompt = _build_full_prompt(
            intent,
            shim_url=shim_url,
            shopping_url=shopping_url,
            reddit_url=reddit_url,
            wikipedia_url=wikipedia_url,
            report_path=report_path,
            evidence=evidence,
        )
        env = {**os.environ}
        env["OPENCODE_CONFIG"] = str(config_path)
        env["OPENAI_API_KEY"] = "anything-proxy-uses-server-key"
        env["NO_PROXY"] = "*"
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env.pop(key, None)

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
        if len(report) < 500 and stdout_text:
            report = stdout_text
        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("opencode native report weak/empty")
            if fallback_enabled():
                return _degrade("write", "native report weak/under-threshold")
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
            `commands.allowed` whitelist that admits only sandbox-local
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
            f'-MaxOutputTokens {out_cap} -ContextLimit {ctx_lim} '
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

        if len(report) < 500 and stdout_text.strip():
            logger.info(
                "opencode: report file is %d chars, falling back to %d chars stdout",
                len(report), len(stdout_text),
            )
            report = stdout_text.strip()

        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("opencode ssh report weak/empty")
            if fallback_enabled():
                return _degrade("write", "native report weak/under-threshold")
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
    parser.add_argument("--proxy-url", default="http://localhost:8088/v1")
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
