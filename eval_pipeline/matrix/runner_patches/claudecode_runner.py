"""Claude Code CLI as a deep-research agent.

Architecture (local-first; per-backbone claude-code-router instances):

    runner
        │  claude --print ... (local subprocess)
        ▼
    claude CLI
        │  ANTHROPIC_BASE_URL=http://127.0.0.1:<port-for-backbone>
        ▼
    ccr (claude-code-router, ONE instance PER backbone, own HOME + config
         written/asserted by this runner)   --Anthropic→OpenAI translation-->
        │  http://127.0.0.1:8100/v1/chat/completions
        ▼
    unified LLM gateway (:8100)  --per-model policy + routing-->
        vLLM qwen3-8b / DashScope deepseek-v4-flash / bigmodel glm-4.7-flash

Why per-backbone ccr instances: until 2026-07-07 every claude-code run pointed
at ONE shared ccr on :3456 whose config.json was mutated over time, so the
lane's --backbone label said qwen/deepseek/glm while the actual model was
whatever :3456 happened to be configured with at that moment (the subset
"deepseek" passes were actually qwen3-8b). Now the requested backbone picks
its own dedicated port/HOME, the config is asserted before every run, and a
provenance line + sidecar record what was actually used.

An optional SSH/Windows path still exists but is DISABLED unless
CLAUDE_CODE_SSH_HOST is explicitly set (the old default "5090" parsed as the
decimal IPv4 0.0.19.226 and burned ~150s per fallback attempt).

Tooling lockdown (fairness with other DR baselines):
    - claude's native WebSearch + WebFetch are stripped via --disallowedTools
    - --append-system-prompt steers the model to issue
      `curl http://localhost:8081/search ...` via the Bash tool
    - The shim search/fetch recipes are supplied because the CLI has no native
      benchmark search tool. The corpus modalities are not enumerated, so the
      model receives no extra cross-source strategy beyond the shared task.
"""
from __future__ import annotations

import asyncio
import atexit
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .evidence_fallback import (
    error_stub,
    fallback_enabled,
    is_weak_report,
    keep_or_stub,
    synthesize_report,
)
from . import _egress

logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("DRA_REPO_ROOT") or Path(__file__).resolve().parents[2])
AGENT_NAME = "claude-code"

# Workstream C — strict-sandbox eligibility.
# claude-code supports `--allowed-tools` with argument patterns. Under
# strict_sandbox=True we replace the disallowlist (WebSearch / WebFetch /
# NotebookEdit) with a WHITELIST that admits only Read/Write/Edit/Glob/Grep
# plus Bash `curl` patterns scoped to the SHIM ORIGIN alone (:8081/:18081).
# This closes two gaps at once: `curl https://en.wikipedia.org/...` (off-box)
# AND `curl http://localhost:7770/...` (on-box but bypassing the shim's
# record_fetch). Only the strict path converges fetch; under the default OPEN
# policy Bash/curl is free, so this lane is fetch-observable ONLY when
# strict_sandbox=True.
STRICT_SANDBOX_ELIGIBLE = True

try:
    from . import _budget
except ImportError:  # run as a bare script rather than a package module
    import _budget  # type: ignore

DEFAULT_TIMEOUT_S = _budget.native_timeout_default()
# Unified default, identical for every lane (see scripts/runners/_budget.py):
# None = no native self-abort, the no-progress watchdog terminates a stall.
DEFAULT_NATIVE_TIMEOUT_S = _budget.native_timeout_default()
REMOTE_DIR_WIN = os.environ.get("CLAUDE_CODE_REMOTE_DIR", "C:/tools/cc_runner")


def _ssh_host() -> str:
    """SSH/Windows fallback host. EMPTY by default: the old default "5090"
    was parsed by ssh as the decimal IPv4 integer 5090 == 0.0.19.226, so every
    fallback attempt burned a ~150s connect timeout. The ssh path is now
    opt-in via an explicit CLAUDE_CODE_SSH_HOST."""
    return os.environ.get("CLAUDE_CODE_SSH_HOST", "").strip()


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


# ---------------------------------------------------------------------------
# Per-backbone CCR selection.
#
# Root cause of the 2026-07-07 subset mislabeling: this runner always pointed
# ANTHROPIC_BASE_URL at one shared ccr port whose config was mutated over
# time, with zero validation and zero provenance. Each backbone now gets its
# OWN ccr instance (own port, own HOME, config written idempotently by this
# runner), the config is read back and asserted before every run, and the
# actually-used router is recorded to stdout + a .provenance.json sidecar.
# ---------------------------------------------------------------------------

def _gateway_chat_url(proxy_url: str | None = None) -> str:
    """Resolve the exact gateway used by the CCR provider at call time."""
    raw = (
        os.environ.get("CLAUDE_CODE_GATEWAY_URL")
        or proxy_url
        or os.environ.get("DS_PROXY_URL")
        or "http://127.0.0.1:8100/v1"
    ).rstrip("/")
    if raw.endswith("/chat/completions"):
        return raw
    return raw + "/chat/completions"


CCR_HOME_BASE = Path(
    os.environ.get("CLAUDE_CODE_CCR_HOME_BASE")
    or (Path(os.environ.get("HOME", "/tmp")) / ".dra-ccr-homes")
)

_BACKBONE_CCR_PORTS = {
    "qwen3-8b": 3461,
    "deepseek-v4-flash": 3462,
    "glm-4.7-flash": 3463,
}
_UNKNOWN_PORT_BASE = 3470
_UNKNOWN_PORT_SPAN = 20


def _port_for_backbone(model: str) -> int:
    port = _BACKBONE_CCR_PORTS.get(model)
    if port is not None:
        return port
    # Unknown backbone: stable hash into 3470-3489 so the same label always
    # lands on the same port (and never on another backbone's port).
    digest = hashlib.sha256(model.encode("utf-8")).hexdigest()
    return _UNKNOWN_PORT_BASE + int(digest, 16) % _UNKNOWN_PORT_SPAN


def _ccr_home_for_backbone(
    model: str,
    gateway_chat_url: str | None = None,
) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", model) or "unknown"
    if gateway_chat_url:
        # Every matrix attempt owns a short-lived cell proxy on a new port.
        # Reusing the old model-only HOME makes CCR v3 retain a SQLite route to
        # the dead prior proxy.  Bind the HOME to the exact route while keeping
        # the model label human-readable; no existing SQLite is edited.
        route = hashlib.sha256(
            str(gateway_chat_url).rstrip("/").encode("utf-8")
        ).hexdigest()[:16]
        safe = f"{safe}--{route}"
    return CCR_HOME_BASE / safe


def _ccr_config_path(home: Path) -> Path:
    return home / ".claude-code-router" / "config.json"


def _ccr_sqlite_path(home: Path) -> Path:
    return home / ".claude-code-router" / "config.sqlite"


def _effective_ccr_config_path(home: Path) -> Path | None:
    json_path = _ccr_config_path(home)
    sqlite_path = _ccr_sqlite_path(home)
    if json_path.is_file():
        return json_path
    if sqlite_path.is_file():
        return sqlite_path
    return None


def _build_ccr_config(
    model: str,
    port: int,
    gateway_chat_url: str | None = None,
) -> dict:
    """Desired ccr config for one backbone: a single 'gateway' provider that
    forwards to the unified :8100 LLM gateway, every Router route pinned to
    this backbone, and the maxtoken transformer preserved (clamp 8192, the
    same semantics the qwen lane used on the old :3457 instance)."""
    route = f"gateway,{model}"
    return {
        "LOG": False,
        "LOG_LEVEL": "info",
        "HOST": "127.0.0.1",
        "PORT": port,
        "APIKEY": "anything",
        "API_TIMEOUT_MS": 600000,
        "Providers": [
            {
                "name": "gateway",
                "api_base_url": gateway_chat_url or _gateway_chat_url(),
                "api_key": "anything",
                "models": [model],
                "transformer": {"use": [["maxtoken", {"max_tokens": 8192}]]},
            }
        ],
        "Router": {
            "default": route,
            "background": route,
            "think": route,
            "longContext": route,
            "longContextThreshold": 60000,
            "webSearch": route,
        },
    }


def _ccr_for_backbone(
    model: str,
    gateway_chat_url: str | None = None,
) -> tuple[str, Path | None]:
    """Return (base_url, ccr_home) for this backbone's dedicated ccr.

    CLAUDE_CODE_LOCAL_CCR_URL / CLAUDE_CODE_CCR_URL stay the highest priority
    as an explicit user escape hatch, but an override is logged loudly and
    recorded in provenance, because with an override the runner cannot verify
    which model actually sits behind the URL (ccr_home is None then)."""
    for var in ("CLAUDE_CODE_LOCAL_CCR_URL", "CLAUDE_CODE_CCR_URL"):
        override = (os.environ.get(var) or "").strip()
        if override:
            logger.warning(
                "[claude-code] %s=%s overrides per-backbone ccr selection for "
                "backbone=%s; the model behind this URL is NOT verified",
                var, override, model,
            )
            print(
                f"[claude-code] ccr env override {var}={override} "
                f"backbone={model} (model identity unverified)",
                flush=True,
            )
            return override, None
    return (
        f"http://127.0.0.1:{_port_for_backbone(model)}",
        _ccr_home_for_backbone(model, gateway_chat_url),
    )


def _read_ccr_config(cfg_path: Path) -> dict:
    try:
        if cfg_path.suffix == ".sqlite":
            connection = sqlite3.connect(
                f"file:{cfg_path}?mode=ro", uri=True, timeout=5
            )
            try:
                row = connection.execute(
                    "SELECT value_json FROM app_config WHERE key = ?",
                    ("default",),
                ).fetchone()
            finally:
                connection.close()
            if row is None:
                raise RuntimeError(
                    f"CCR v3 sqlite config has no app_config/default row: {cfg_path}"
                )
            value = json.loads(str(row[0]))
        else:
            value = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"CCR config is not an object: {cfg_path}")
        return value
    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"unreadable ccr config at {cfg_path}: {e}") from e


def _config_routes_model(
    cfg: dict,
    model: str,
    gateway_chat_url: str | None = None,
) -> bool:
    providers = cfg.get("Providers") or cfg.get("providers") or []
    models: list[str] = []
    endpoints: list[str] = []
    for p in providers:
        if isinstance(p, dict):
            models.extend(p.get("models") or [])
            endpoints.append(str(p.get("api_base_url") or "").rstrip("/"))
    default = _router_default(cfg, model)
    endpoint_ok = (
        gateway_chat_url is None
        or str(gateway_chat_url).rstrip("/") in endpoints
    )
    return model in models and default.endswith(f",{model}") and endpoint_ok


def _router_default(cfg: dict, model: str) -> str:
    """Resolve the effective default route for CCR v2 JSON or v3 SQLite."""
    router = cfg.get("Router") or cfg.get("router") or {}
    default = str(router.get("default", ""))
    if default:
        return default
    preferred = str(cfg.get("preferredProvider") or "")
    providers = cfg.get("Providers") or cfg.get("providers") or []
    matching = [
        row
        for row in providers
        if isinstance(row, dict)
        and str(row.get("name") or row.get("id") or "") == preferred
        and model in (row.get("models") or [])
    ]
    if len(matching) == 1:
        return f"{preferred},{model}"
    return ""


def _ensure_ccr_for_backbone(
    model: str,
    url: str,
    home: Path,
    gateway_chat_url: str | None = None,
) -> Path:
    """Bring up the per-backbone ccr WITHOUT ever touching anyone else's.

    - Port not listening: idempotently write our config under ``home`` and
      ``HOME=<home> ccr start``, then wait for the port.
    - Port listening: it must be OUR instance — ``home``'s config must exist,
      claim this port and route to this model. Anything else means a foreign
      process squats the port; fail loud instead of killing it (shared-box
      rule: never kill/restart existing processes)."""
    cfg_path = _ccr_config_path(home)
    gateway_chat_url = gateway_chat_url or _gateway_chat_url()
    desired = _build_ccr_config(
        model,
        _port_for_backbone(model),
        gateway_chat_url,
    )

    if _tcp_listening(url):
        effective_path = _effective_ccr_config_path(home)
        if effective_path is None:
            raise RuntimeError(
                f"port at {url} (backbone={model}) is already in use but "
                f"neither CCR JSON nor SQLite config exists under {home}: "
                "refusing to reuse or kill a foreign process"
            )
        try:
            current = _read_ccr_config(effective_path)
        except FileNotFoundError:
            raise RuntimeError(
                f"port at {url} (backbone={model}) is already in use but "
                f"{effective_path} does not exist: a process this runner does not "
                "own is squatting the port; refusing to reuse or kill it"
            )
        if (int(current.get("PORT") or 0) != int(desired["PORT"])
                or not _config_routes_model(current, model, gateway_chat_url)):
            raise RuntimeError(
                f"ccr at {url} (config {effective_path}) does not route to "
                f"backbone={model}; refusing to run mislabeled and refusing "
                "to kill the existing process — fix/stop it manually"
            )
        return effective_path

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    effective_path = _effective_ccr_config_path(home)
    if effective_path is not None and effective_path.suffix == ".sqlite":
        stale = _read_ccr_config(effective_path)
        stale_port = int(
            stale.get("PORT")
            or ((stale.get("gateway") or {}).get("port") or 0)
        )
        if stale_port != int(desired["PORT"]) or not _config_routes_model(
            stale, model, gateway_chat_url
        ):
            raise RuntimeError(
                f"existing CCR v3 config {effective_path} does not route to "
                f"backbone={model} at {gateway_chat_url}; refusing to mutate "
                "the SQLite database implicitly"
            )
    else:
        try:
            stale = _read_ccr_config(cfg_path)
        except Exception:
            stale = None
        if stale != desired:
            cfg_path.write_text(json.dumps(desired, indent=2) + "\n", encoding="utf-8")
    if not shutil.which("ccr"):
        raise RuntimeError("ccr executable not found")
    log_path = Path(os.environ.get("CLAUDE_CODE_CCR_START_LOG", "/tmp/claude_code_router_start.log"))
    env = {**os.environ, "HOME": str(home)}
    _egress.scrub_or_apply(env)
    with log_path.open("ab") as log:
        subprocess.Popen(
            ["ccr", "start"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    deadline = time.time() + 30
    while time.time() < deadline:
        if _tcp_listening(url):
            effective_path = _effective_ccr_config_path(home)
            if effective_path is None:
                raise RuntimeError(
                    f"ccr at {url} is listening but no owned config remains under {home}"
                )
            return effective_path
        time.sleep(0.5)
    raise RuntimeError(f"ccr (HOME={home}) did not start listening at {url}")


def _stop_owned_ccr(home: Path) -> None:
    """Stop only the route-specific CCR instance owned by this runner HOME."""
    executable = shutil.which("ccr")
    if not executable:
        logger.warning("[claude-code] cannot stop owned CCR: ccr not on PATH")
        return
    env = {**os.environ, "HOME": str(home)}
    _egress.scrub_or_apply(env)
    try:
        completed = subprocess.run(
            [executable, "stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            timeout=30,
            env=env,
        )
        if completed.returncode not in {0, 1}:
            logger.warning(
                "[claude-code] owned CCR stop returned %s for HOME=%s",
                completed.returncode,
                home,
            )
    except Exception:
        logger.exception("[claude-code] failed stopping owned CCR HOME=%s", home)


def _local_claude_environment(
    ccr_url: str,
    ccr_home: Path | None,
) -> dict[str, str]:
    """Build a clean local Claude environment bound to the owned CCR profile."""
    env = os.environ.copy()
    env.update(
        {
            "ANTHROPIC_BASE_URL": ccr_url,
            "ANTHROPIC_AUTH_TOKEN": "anything",
            "ANTHROPIC_API_KEY": "anything",
            "CLAUDE_CODE_SIMPLE": "1",
            "NO_COLOR": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "DO_NOT_TRACK": "1",
        }
    )
    if ccr_home is not None:
        config_dir = ccr_home / ".claude"
        env.update(
            {
                "HOME": str(ccr_home),
                "USERPROFILE": str(ccr_home),
                "XDG_CONFIG_HOME": str(ccr_home / ".config"),
                "XDG_DATA_HOME": str(ccr_home / ".local/share"),
                "XDG_CACHE_HOME": str(ccr_home / ".cache"),
                "XDG_STATE_HOME": str(ccr_home / ".local/state"),
                "CLAUDE_CONFIG_DIR": str(config_dir),
            }
        )
    _egress.scrub_or_apply(env)
    # The CCR listener lives inside this worker's network namespace. Sending
    # its loopback hop through the host egress proxy targets the host's
    # 127.0.0.1 instead and cannot reach the router. Exempt only numeric
    # loopback; sandbox page identities use localhost and remain proxied.
    env["NO_PROXY"] = "127.0.0.1"
    env["no_proxy"] = "127.0.0.1"
    return env


def _assert_ccr_model(cfg_path: Path | None, url: str, model: str) -> str | None:
    """Pre-run guard: read the config back and PROVE the router sends this
    lane's traffic to the labeled backbone. This assertion is what prevents a
    repeat of the 2026-07-07 subset mislabeling — do not remove it."""
    if cfg_path is None:
        return None  # env-override mode: unverifiable, already logged loudly
    try:
        cfg = _read_ccr_config(cfg_path)
    except FileNotFoundError:
        raise RuntimeError(f"ccr config missing at {cfg_path} for backbone={model}")
    default = _router_default(cfg, model)
    if not default.endswith(f",{model}"):
        raise RuntimeError(
            f"CCR at {url} routes default={default!r} but this lane expects "
            f"backbone={model!r} (config {cfg_path}); refusing to run mislabeled"
        )
    return default


def _emit_provenance(
    model: str,
    ccr_url: str,
    cfg_path: Path | None,
    router_default: str | None,
) -> None:
    """Record which router/backbone this run ACTUALLY used: one stdout line
    (grep-able in lane logs) plus a .provenance.json sidecar next to the final
    report (path exported by run_deep_task as DEEP_RUN_REPORT_PATH)."""
    print(
        f"[claude-code] router={ccr_url} backbone={model} "
        f"config={cfg_path if cfg_path else '(env-override, unverified)'}",
        flush=True,
    )
    report_path = (os.environ.get("DEEP_RUN_REPORT_PATH") or "").strip()
    if not report_path:
        logger.info("[claude-code] DEEP_RUN_REPORT_PATH unset; provenance sidecar skipped")
        return
    record = {
        "agent": AGENT_NAME,
        "backbone": model,
        "router_url": ccr_url,
        "config_path": str(cfg_path) if cfg_path else None,
        "config_router_default": router_default,
        "task": os.environ.get("_FLOWSEARCHER_TASK_ID") or None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        sidecar = Path(report_path).with_suffix(".provenance.json")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception:
        logger.exception("[claude-code] failed writing provenance sidecar")


def _remote_ccr_base_url(model: str) -> str:
    """CCR URL as seen from the (opt-in) SSH/Windows remote. Env override
    first; otherwise this host's LAN IP + the backbone's dedicated port."""
    configured = (os.environ.get("CLAUDE_CODE_CCR_URL") or "").strip()
    if configured:
        return configured
    port = _port_for_backbone(model)
    try:
        ips = subprocess.check_output(["hostname", "-I"], text=True, timeout=2).split()
        for ip in ips:
            if ip.startswith(("172.", "10.", "192.168.")):
                return f"http://{ip}:{port}"
    except Exception:
        pass
    return f"http://127.0.0.1:{port}"


def _tcp_listening(url: str, *, timeout_s: float = 1.0) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _native_timeout(timeout_s):
    # Unified native timeout. Default identical to every lane (DRA_WALL_CLOCK_S);
    # CLAUDE_CODE_NATIVE_TIMEOUT_S still overrides for single-run debugging. The
    # old hard 420s default was a per-lane wall clock that aborted slow-backbone
    # runs that were still making progress; None (unlimited) defers termination
    # to the shared no-progress watchdog and the outer subprocess cap.
    configured = _budget.resolve_native_timeout("CLAUDE_CODE_NATIVE_TIMEOUT_S")
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
  [string]$EgressProxyUrl
)
$ErrorActionPreference = 'Continue'
if ($EgressProxyUrl) {
  $env:HTTP_PROXY = $EgressProxyUrl
  $env:HTTPS_PROXY = $EgressProxyUrl
  $env:ALL_PROXY = $EgressProxyUrl
  $env:NO_PROXY = ''
}
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
You are a deep research agent.  You have NO direct internet access. Use the
benchmark search shim for search and page reads.

To search, use the Bash tool:
  curl -s -X POST $ShimUrl/search -H 'content-type: application/json' -d '{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}'

To fetch and read a page returned by search, use Bash (route it through the
shim's /fetch so the read is recorded; a bare curl of the site URL is blocked):
  curl -s "$ShimUrl/fetch?url=<sandbox URL>"

	OUTPUT INSTRUCTIONS (read carefully — the evaluator reads ONLY this file):

  Use the Write tool to save the task response to:
      $ReportPath

After the file write succeeds, your final text response should be ONLY:
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
# Only the shim origin (:8081 and its alt :18081) is admitted. Direct
# site curls (7770/17770/8090/9999) are DELETED: with them present a real
# `curl http://localhost:7770/...` bypassed record_fetch, so the page never
# hit the shim and the run showed FETCHED=empty -> pof=0 for a lane that had
# actually read the page (the false-accusation window, FETCH_PATH_AUDIT §0).
# 127.0.0.1 variants are dropped for the same reason (mount-namespace
# passthrough risk). Fetch now goes through `curl -s "$ShimUrl/fetch?url=..."`,
# which matches the `curl -s http://localhost:8081*` prefix below.
_TOOL_POLICY_STRICT = (
    "'--allowed-tools', "
    "'Write,Edit,"
    "Bash(curl http://localhost:8081*),"
    "Bash(curl http://localhost:18081*),"
    "Bash(curl http://127.0.0.1:8081*),"
    "Bash(curl http://127.0.0.1:18081*),"
    "Bash(curl -s http://localhost:8081*),"
    "Bash(curl -s http://localhost:18081*),"
    "Bash(curl -s http://127.0.0.1:8081*),"
    "Bash(curl -s http://127.0.0.1:18081*),"
    "Bash(curl -X POST http://localhost:8081*),"
    "Bash(curl -X POST http://localhost:18081*),"
    "Bash(curl -X POST http://127.0.0.1:8081*),"
    "Bash(curl -X POST http://127.0.0.1:18081*),"
    "Bash(curl -s -X POST http://localhost:8081*),"
    "Bash(curl -s -X POST http://localhost:18081*),"
    "Bash(curl -s -X POST http://127.0.0.1:8081*),"
    "Bash(curl -s -X POST http://127.0.0.1:18081*)',"
)


def _build_ps_driver(*, ccr_url: str, strict_sandbox: bool = False) -> str:
    policy = _TOOL_POLICY_STRICT
    return (
        _PS_DRIVER_TEMPLATE
        .replace("__CCR_URL__", ccr_url)
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
Use the benchmark search shim for search and page reads.

To search, use the Bash tool:
  curl -s -X POST {shim_url}/search -H 'content-type: application/json' -d '{{"query":"...","api_key":"tvly-shim-fake","max_results":10,"include_raw_content":true}}'

To fetch and read a page returned by search, use Bash (route it through the
shim's /fetch so the read is recorded; a bare curl of the site URL is blocked):
  curl -s "{shim_url}/fetch?url=<sandbox URL>"

You have a hard budget of 24 tool calls total. Do not repeat equivalent search
or page-extraction commands. By tool call 20, stop researching, synthesize from
the evidence already collected, and write the report. Writing a useful report
is mandatory even when some evidence remains incomplete.

	OUTPUT INSTRUCTIONS (read carefully - the evaluator reads ONLY this file):

  Use the Write tool to save the task response to:
      {report_path}

After the file write succeeds, your final text response should be ONLY:
  REPORT_WRITTEN

Begin now.  Do not ask for clarification - act on the brief alone.
"""


def _shim_bash_tools(shim_url: str) -> list[str]:
    parsed = urlparse(str(shim_url or ""))
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError(f"shim_url must be a plain HTTP URL: {shim_url!r}")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    origin = f"http://{host}:{parsed.port or 80}"
    return [
        f"Bash(curl {origin}*)",
        f"Bash(curl -s {origin}*)",
        f"Bash(curl -X POST {origin}*)",
        f"Bash(curl -s -X POST {origin}*)",
    ]


def _local_tool_policy_args(
    *,
    strict_sandbox: bool,
    shim_url: str = "http://localhost:8081",
) -> list[str]:
    # Mandatory capability boundary: report writes plus shim curl only. Read,
    # Glob, Grep and a general Bash would expose local answer-key files.
    return [
        "--allowed-tools",
        "Write",
        "Edit",
        *_shim_bash_tools(shim_url),
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
    def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: a claude-code failure must surface as the framework's
        # own (missing) output, never as a harness-ghostwritten report. In
        # benchmark mode we save an honest error stub; the evidence writer runs
        # only under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return synthesize_report(
                intent,
                model,
                shim_url,
                proxy_url,
                min_chars=4500,
                min_urls=5,
            )
        return error_stub("claude-code", phase, reason)

    if not shutil.which("claude"):
        return "(claude-code local unavailable: claude executable not found)"

    # Per-backbone router selection + hard pre-run identity assertion.
    gateway_chat_url = _gateway_chat_url(proxy_url)
    ccr_url, ccr_home = _ccr_for_backbone(model, gateway_chat_url)
    if ccr_home is None:
        # Env-override mode: never auto-start a shared router we do not own;
        # the URL must already be live and the operator owns its identity.
        if not _tcp_listening(ccr_url):
            raise RuntimeError(
                f"CLAUDE_CODE_(LOCAL_)CCR_URL override {ccr_url} is not "
                "listening; refusing to auto-start a router this runner "
                "does not own"
            )
        cfg_path = None
    else:
        cfg_path = _ensure_ccr_for_backbone(
            model,
            ccr_url,
            ccr_home,
            gateway_chat_url,
        )
        # The cell proxy is ephemeral, so this CCR route must not outlive the
        # one runner process.  atexit runs after the report/meta are sealed.
        atexit.register(_stop_owned_ccr, ccr_home)
    router_default = _assert_ccr_model(cfg_path, ccr_url, model)
    _emit_provenance(model, ccr_url, cfg_path, router_default)

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

        env = _local_claude_environment(ccr_url, ccr_home)

        cmd = [
            "claude",
            "--bare",
            "--print",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--add-dir",
            str(workdir),
            *_local_tool_policy_args(
                strict_sandbox=strict_sandbox,
                shim_url=shim_url,
            ),
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
            logger.warning("claude-code local path exceeded %ss", _native_timeout(timeout_s))
            return _degrade(
                "native", f"native path exceeded {_native_timeout(timeout_s)}s timeout"
            )

        elapsed = time.time() - t0
        stdout_text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        stdout_path.write_text(stdout_text, encoding="utf-8", errors="replace")
        raw_root = Path(os.environ.get("DEEP_RUN_OUT_DIR") or "")
        if raw_root.is_dir():
            shutil.copy2(stdout_path, raw_root / "claude-code-native.stdout.log")
        report = ""
        if report_path.exists():
            report = report_path.read_text(encoding="utf-8", errors="replace").lstrip("﻿").strip()
        if not report:
            return _degrade(
                "write",
                "claude-code did not write the requested report file; "
                f"stdout tail={stdout_text[-500:]}",
            )
        if proc.returncode != 0:
            logger.warning(
                "claude-code local exited %d after %.0fs; output tail: %s",
                proc.returncode,
                elapsed,
                stdout_text[-1500:],
            )
        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("claude-code local report weak/empty")
            # Weak-but-real output is claude-code's own report: save it verbatim
            # (the scorer judges quality); stub only genuinely empty/stub output.
            return keep_or_stub(
                "claude-code", "write", "native report weak/under-threshold", report
            )
        logger.info("claude-code local completed in %.0fs, report=%d chars", elapsed, len(report))
        return report


def _ssh(cmd: str, *, timeout_s: int = 60) -> subprocess.CompletedProcess:
    host = _ssh_host()
    if not host:
        raise RuntimeError("CLAUDE_CODE_SSH_HOST unset; ssh path is disabled")
    return subprocess.run(
        ["ssh",
         "-o", "ServerAliveInterval=30",
         "-o", "ServerAliveCountMax=20",
         host, cmd],
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
         str(local), f"{_ssh_host()}:{remote_win}"],
        check=True, capture_output=True, timeout=timeout_s,
        stdin=subprocess.DEVNULL,
    )


def _scp_down(remote_win: str, local: Path, *, timeout_s: int = 60) -> None:
    subprocess.run(
        ["scp", "-o", "ServerAliveInterval=30",
         f"{_ssh_host()}:{remote_win}", str(local)],
        check=True, capture_output=True, timeout=timeout_s,
        stdin=subprocess.DEVNULL,
    )


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: float | None = DEFAULT_TIMEOUT_S,
    strict_sandbox: bool = False,
) -> str:
    """Run claude-code locally (per-backbone ccr) and return the markdown report.

    Args:
        intent: research brief.
        model: the lane's backbone. Selects (and asserts) the dedicated
            claude-code-router instance for that backbone; a mismatch between
            the label and the router config raises instead of running.
        shim_url: sandbox shim URL, baked into the agent's system prompt.
        proxy_url: ignored — the per-backbone ccr forwards to the unified
            :8100 LLM gateway which owns upstream routing.
        timeout_s: hard timeout for the remote subprocess.
        strict_sandbox: when True, the PowerShell driver swaps claude-code's
            `--disallowedTools` flag for `--allowed-tools <whitelist>` that
            admits only Read/Write/Edit/Glob/Grep and Bash(curl <shim origin>).
            Closes both the off-box gap (``curl https://en.wikipedia.org/...``)
            and the on-box shim-bypass gap (``curl http://localhost:7770/...``),
            so every page read is recorded by the shim's /fetch.
    """
    def _degrade(phase: str, reason: str) -> str:
        # Fairness rule: a claude-code failure must surface as the framework's
        # own (missing) output, never as a harness-ghostwritten report. In
        # benchmark mode we save an honest error stub; the evidence writer runs
        # only under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE flag.
        if fallback_enabled():
            return synthesize_report(
                intent,
                model,
                shim_url,
                proxy_url,
                min_chars=4500,
                min_urls=5,
            )
        return error_stub("claude-code", phase, reason)

    # SSH/Windows path is OPT-IN: it exists only when CLAUDE_CODE_SSH_HOST is
    # explicitly set (no default host — the old "5090" default parsed as the
    # decimal IPv4 0.0.19.226 and wasted ~150s per fallback attempt).
    ssh_host = _ssh_host()
    use_windows = os.environ.get("CLAUDE_CODE_USE_WINDOWS") == "1"
    if use_windows and not ssh_host:
        logger.warning(
            "[claude-code] CLAUDE_CODE_USE_WINDOWS=1 but CLAUDE_CODE_SSH_HOST "
            "is unset; ssh/Windows path skipped, using local claude"
        )
        use_windows = False
    if use_windows and _egress.enforced() and not _egress.remote_enforced():
        raise RuntimeError(
            "claude-code Windows mode has no attested route to the bracketed "
            "egress door (set DRA_REMOTE_EGRESS_PROXY and "
            "DRA_REMOTE_EGRESS_ENFORCED=1 after remote isolation preflight)"
        )
    ssh_fallback_allowed = bool(ssh_host) and (
        os.environ.get("CLAUDE_CODE_NO_WINDOWS_FALLBACK") != "1"
    ) and (not _egress.enforced() or _egress.remote_enforced())

    if not use_windows:
        try:
            local_report = await _run_local_claude(
                intent,
                model,
                shim_url,
                proxy_url,
                timeout_s=timeout_s,
                strict_sandbox=strict_sandbox,
            )
            # Any completed local attempt is final, including an honest error
            # stub. Retrying the same framework on Windows after a model/runtime
            # failure gave this lane a second scored attempt. Only the explicit
            # pre-dispatch "executable unavailable" condition is a transport
            # fallback.
            if not local_report.startswith("(claude-code local unavailable:"):
                return local_report
            if not ssh_fallback_allowed:
                return local_report
        except Exception as e:
            logger.exception("claude-code local path failed")
            if not ssh_fallback_allowed:
                if not ssh_host:
                    logger.info(
                        "[claude-code] ssh fallback skipped: CLAUDE_CODE_SSH_HOST "
                        "unset (ssh path is default-disabled)"
                    )
                return _degrade("native", f"{type(e).__name__}: {e}")

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

    remote_ccr_url = _remote_ccr_base_url(model)
    _emit_provenance(model, remote_ccr_url, None, None)

    REMOTE_DIR_WSL.mkdir(parents=True, exist_ok=True)
    intent_wsl.write_text(intent, encoding="utf-8")
    driver_wsl.write_text(
        _build_ps_driver(ccr_url=remote_ccr_url, strict_sandbox=strict_sandbox),
        encoding="utf-8",
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
            f'-RedditUrl "{reddit_url}" -WikipediaUrl "{wikipedia_url}" '
            f'-EgressProxyUrl "{_egress.remote_proxy()}"'
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

        if not report:
            return _degrade(
                "write",
                "claude-code did not write the requested report file; "
                f"stdout tail={stdout_text[-500:]}",
            )

        if is_weak_report(report, min_chars=3000, min_urls=3):
            logger.warning("claude-code ssh report weak/empty")
            # Weak-but-real output is claude-code's own report: save it verbatim
            # (the scorer judges quality); stub only genuinely empty/stub output.
            return keep_or_stub(
                "claude-code", "write", "native report weak/under-threshold", report
            )

        logger.info("claude-code completed in %.0fs, report=%d chars",
                    elapsed, len(report))
        return report

    except subprocess.TimeoutExpired:
        logger.error("claude-code native path exceeded %ds", _native_timeout(timeout_s))
        return _degrade(
            "native", f"native path exceeded {_native_timeout(timeout_s)}s timeout"
        )
    except Exception as e:
        logger.exception("claude-code runner error")
        return _degrade("native", f"{type(e).__name__}: {e}")
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
    parser.add_argument("--proxy-url", default="http://localhost:8100/v1")
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
