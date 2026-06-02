"""``run_code`` / ``run_bash`` providers: sandboxed compute over fetched data.

P1 acquisition tools #4 from ``docs/ACQUISITION_ROADMAP.md`` section 3 -- the
HIGHEST-RISK tools in the suite, so the security posture is uncompromisingly
**default-deny**: a snippet runs only when every guard can be established, and
the moment any guard cannot be enforced the runner REFUSES (``ok=False``) rather
than degrading to an unguarded execution.

The two tools share one module and one guarded runner:

* ``run_code`` -- runs agent-authored **Python** over already-fetched data.
* ``run_bash`` -- runs agent-authored **Bash** over already-fetched data.

Both compute a derived result (sum / sort / grep / count) from pages the agent
has ALREADY fetched, and the agent passes ``source_urls`` -- the page URL(s) the
computation is over.

Modality-agnostic reward (the COMPUTE-OVER-PAGES invariant)
-----------------------------------------------------------
The tool does NOT invent an ``exec://`` url. The computed stdout text is keyed
to the ``source_urls`` the agent supplied, so a later ``Cite(source_url)`` of the
underlying page still resolves ``r_resolve`` and the computed number feeds
``f1_claim`` exactly like a ``fetch`` of that page:

* ``snippets``     -> ``{u: rendered_stdout for u in source_urls}`` which the env
  folds into ``retrieved_snippets[canonicalize_url(u)]`` (the SAME slot
  ``_do_read`` writes).
* ``fetched_urls`` -> ``source_urls``; ``display`` -> stdout (+ a stderr tail);
  ``n_results`` -> 1; ``ok`` -> ``exit_code == 0 and not timed_out``.
* If NO ``source_urls`` are resolvable -> ``ToolResult(ok=False,
  error="exec_no_source_url")`` (NEVER lands orphan compute output).
* Read-only acquisition, so ``state_delta`` stays ``None`` (these are not
  P3 write-actions).

Security guards (default-deny)
------------------------------
PRODUCTION SEAM -- an :class:`Executor` Protocol ``run(lang, code, *, timeout_s,
cwd, env) -> ExecResult``. A production deployment injects a microVM executor
(E2B / gVisor / Firecracker) via ``ctx.extras["code_executor"]``; the clearly
marked seam below is where it plugs in. Tests inject a fake/echo executor so NO
untrusted code is ever run on the host in tests.

LOCAL GUARDED RUNNER (:class:`LocalGuardedRunner`) -- used ONLY for benign code
when no production executor is injected. It enforces, default-deny:

* **temp working dir** (``tempfile.mkdtemp``) as the only writable surface; the
  child is ``cwd``-confined and the snippet is pre-flight validated for host-fs
  escape (absolute paths / ``..`` / sensitive paths like ``/etc/passwd`` ->
  refused before launch).
* **scrubbed env** -- no host secrets / PATH leakage beyond a minimal allowlist.
* **network-lock** -- outbound sockets to any non-localhost host are blocked; the
  only permitted egress is ``127.0.0.1`` / ``localhost`` on the three sandbox
  ports ``{7770, 9999, 8090}``. Enforced in the child via a ``socket.connect``
  shim prelude (a connect() to anything else raises before any bytes leave). A
  static pre-flight also refuses snippets that name an obvious non-local host.
* **wall-clock timeout** -- ``subprocess`` ``timeout`` kills the process group on
  over-run (``timed_out=True``); **memory cap** via ``resource.setrlimit
  (RLIMIT_AS)`` in a ``preexec_fn`` (``resource`` imported lazily).

``subprocess`` / ``resource`` / ``socket`` / ``tempfile`` are imported lazily
inside ``.run`` / the runner, so ``import src.rl.tools_exec`` and
``provide_tools()`` succeed on a plain ``python3`` with nothing installed.

Provider-discovery contract: ``provide_tools() -> [RunCodeTool(), RunBashTool()]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from src.rl.tools import ToolContext, ToolResult


# ---------------------------------------------------------------------------
# Guard configuration
# ---------------------------------------------------------------------------
# Wall-clock timeout (seconds): default + a hard ceiling no task can exceed.
_DEFAULT_TIMEOUT_S = 5.0
_HARD_TIMEOUT_S = 30.0
_HARD_TIMEOUT_S_INT = int(_HARD_TIMEOUT_S)

# Address-space (virtual memory) cap for the child, bytes. RLIMIT_AS.
_DEFAULT_MEM_BYTES = 256 * 1024 * 1024  # 256 MiB
_HARD_MEM_BYTES = 1024 * 1024 * 1024  # 1 GiB

# Stdout/stderr truncation so a runaway print cannot bloat the grounding store.
_MAX_OUTPUT_CHARS = 20_000

# The ONLY network egress the sandbox permits: localhost on the three corpus
# ports. Anything else is blocked in-child and refused at pre-flight.
_ALLOWED_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})
_ALLOWED_PORTS: frozenset[int] = frozenset({7770, 9999, 8090})

# Host-fs paths a snippet must never touch (pre-flight static refusal). The cwd
# confinement + the connect shim are the real enforcement; this is a cheap first
# line that rejects the obvious escapes before we even spawn a process.
_FORBIDDEN_PATH_TOKENS: tuple[str, ...] = (
    "/etc/passwd",
    "/etc/shadow",
    "/etc/hosts",
    "/root/",
    "/home/",
    "/proc/",
    "/sys/",
    "~/",
    "/.ssh",
    "/.aws",
    "/.config",
    "/var/",
)

# Obvious non-local network targets a snippet must never name (pre-flight). The
# in-child connect() shim is the authoritative block; this refuses the snippet
# statically so we do not even launch it.
_FORBIDDEN_NET_TOKENS: tuple[str, ...] = (
    "8.8.8.8",
    "1.1.1.1",
    "example.com",
    "google.com",
    "https://",
    "http://example",
    "0.0.0.0:53",
    ".com",
    ".net",
    ".org",
    ".io",
)

# Minimal env allowlist: the child inherits NOTHING from the host except a
# scrubbed, fixed PATH and a benign locale. No secrets, no tokens, no proxies.
_SCRUBBED_ENV: dict[str, str] = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "HOME": "",  # overwritten with the temp cwd by the runner
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    # Explicitly blank any proxy so the child cannot reach a host egress proxy.
    "http_proxy": "",
    "https_proxy": "",
    "HTTP_PROXY": "",
    "HTTPS_PROXY": "",
    "no_proxy": "*",
    "NO_PROXY": "*",
}


# ---------------------------------------------------------------------------
# Executor seam (production microVM plugs in here)
# ---------------------------------------------------------------------------
@dataclass
class ExecResult:
    """Normalised result of running a snippet through any executor."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    # Set when the runner REFUSED to run (a guard could not be established). The
    # default-deny path returns one of these instead of executing anything.
    refused: str | None = None


@runtime_checkable
class Executor(Protocol):
    """Pluggable code executor.

    PRODUCTION SEAM: a real deployment injects a microVM-backed executor
    (E2B / gVisor / Firecracker) implementing this single method via
    ``ctx.extras["code_executor"]``. The microVM provides the strong isolation
    (kernel-level network namespace, read-only rootfs, ephemeral disk); this
    Protocol is the only contract it must satisfy. Offline tests inject a fake
    executor here so no untrusted code runs on the host.
    """

    def run(
        self,
        lang: str,
        code: str,
        *,
        timeout_s: float,
        cwd: str,
        env: dict[str, str],
    ) -> ExecResult: ...


# ---------------------------------------------------------------------------
# Static, dependency-free pre-flight guards (default-deny)
# ---------------------------------------------------------------------------
def _coerce_timeout(value: Any) -> float:
    try:
        t = float(value)
    except (TypeError, ValueError):
        t = _DEFAULT_TIMEOUT_S
    if t <= 0:
        t = _DEFAULT_TIMEOUT_S
    return min(_HARD_TIMEOUT_S, t)


def check_fs_escape(code: str) -> str | None:
    """Return a refusal reason if the snippet references a host-fs path outside
    the temp cwd, else ``None``. Cheap static screen; the cwd confinement is the
    authoritative enforcement.
    """
    low = str(code or "").lower()
    for token in _FORBIDDEN_PATH_TOKENS:
        if token.lower() in low:
            return f"fs_escape_blocked:{token}"
    # A bare absolute path that is not under a tmp dir is suspicious.
    for tok in ("'/", '"/'):
        idx = low.find(tok)
        while idx != -1:
            tail = low[idx + 2 : idx + 6]
            if not tail.startswith(("tmp", "dev/nu", "dev/ze")):
                return "fs_escape_blocked:absolute_path"
            idx = low.find(tok, idx + 1)
    return None


def check_network_egress(code: str) -> str | None:
    """Return a refusal reason if the snippet names an obvious non-local network
    target, else ``None``. The in-child ``connect()`` shim is the authoritative
    block (it permits only localhost:{7770,9999,8090}); this is a static screen
    that refuses the snippet before we ever launch it.
    """
    low = str(code or "").lower()
    # Permit explicit localhost references on allowed ports; only flag the
    # non-local tokens.
    for token in _FORBIDDEN_NET_TOKENS:
        if token in low:
            # Tolerate localhost URLs on the allowed ports (e.g.
            # "http://localhost:7770/...") which legitimately contain "http://".
            if token in ("https://", "http://example", ".com", ".net", ".org", ".io"):
                if _only_localhost_urls(low):
                    continue
            return f"network_egress_blocked:{token}"
    return None


def _only_localhost_urls(low: str) -> bool:
    """True if every http(s) URL in the text targets an allowed localhost:port."""
    import re

    for m in re.finditer(r"https?://([^/\s\"')]+)", low):
        netloc = m.group(1)
        host, _, port = netloc.partition(":")
        if host not in _ALLOWED_HOSTS:
            return False
        if port:
            try:
                if int(port) not in _ALLOWED_PORTS:
                    return False
            except ValueError:
                return False
    return True


def preflight(code: str) -> str | None:
    """Run every static default-deny guard. Returns a refusal reason or ``None``.

    An empty snippet is refused (nothing to run). Both the fs-escape and the
    network-egress screens must pass.
    """
    if not str(code or "").strip():
        return "empty_code"
    reason = check_fs_escape(code)
    if reason:
        return reason
    reason = check_network_egress(code)
    if reason:
        return reason
    return None


# In-child prelude prepended to a Python snippet: installs a ``socket.connect``
# shim that permits ONLY localhost on the three sandbox ports and raises on any
# other egress. This is the authoritative, runtime network-lock for the local
# guarded runner (the production microVM enforces it at the kernel/netns layer).
_PY_NETLOCK_PRELUDE = """\
import socket as _s
_ALLOWED_HOSTS = {hosts!r}
_ALLOWED_PORTS = {ports!r}
_ALLOWED_IPS = {{'127.0.0.1', '::1', '0.0.0.0'}}

def _addr_ok(addr):
    try:
        host = addr[0]
        port = int(addr[1]) if len(addr) > 1 else None
    except Exception:
        return False
    if host not in _ALLOWED_HOSTS and host not in _ALLOWED_IPS:
        return False
    if port is not None and port not in _ALLOWED_PORTS:
        return False
    return True

_orig_connect = _s.socket.connect
_orig_connect_ex = _s.socket.connect_ex

def _guarded_connect(self, addr, *a, **k):
    if not _addr_ok(addr):
        raise PermissionError('network egress blocked by sandbox: %r' % (addr,))
    return _orig_connect(self, addr, *a, **k)

def _guarded_connect_ex(self, addr, *a, **k):
    if not _addr_ok(addr):
        raise PermissionError('network egress blocked by sandbox: %r' % (addr,))
    return _orig_connect_ex(self, addr, *a, **k)

_s.socket.connect = _guarded_connect
_s.socket.connect_ex = _guarded_connect_ex
# also defeat name resolution of non-local hosts
_orig_getaddrinfo = _s.getaddrinfo

def _guarded_getaddrinfo(host, port, *a, **k):
    if host not in _ALLOWED_HOSTS and host not in _ALLOWED_IPS:
        raise PermissionError('dns resolution blocked by sandbox: %r' % (host,))
    return _orig_getaddrinfo(host, port, *a, **k)

_s.getaddrinfo = _guarded_getaddrinfo
# NOTE: do NOT delete _orig_connect / _orig_connect_ex / _orig_getaddrinfo --
# the guarded wrappers reference them as module globals at call time.
"""


def _netlock_prelude() -> str:
    return _PY_NETLOCK_PRELUDE.format(
        hosts=set(_ALLOWED_HOSTS),
        ports=set(_ALLOWED_PORTS),
    )


# ---------------------------------------------------------------------------
# Local guarded runner (benign test code only; default-deny otherwise)
# ---------------------------------------------------------------------------
class LocalGuardedRunner:
    """Minimal local Executor used ONLY when no production executor is injected.

    It establishes, default-deny:
      * a temp cwd (``tempfile.mkdtemp``) -- the only writable surface;
      * a scrubbed env (no host secrets / proxies);
      * an in-child ``socket.connect`` shim that permits ONLY
        localhost:{7770,9999,8090} (network-lock);
      * a wall-clock ``timeout`` (kills the process group on over-run) and an
        ``RLIMIT_AS`` memory cap via a ``preexec_fn``.

    If any of those cannot be established (e.g. ``resource`` unavailable on the
    platform), the runner REFUSES rather than running unguarded.

    NOTE: this is deliberately a thin local guard for benign computation; the
    strong isolation surface in production is the injected microVM executor.
    """

    def __init__(self, mem_bytes: int = _DEFAULT_MEM_BYTES) -> None:
        self.mem_bytes = max(64 * 1024 * 1024, min(_HARD_MEM_BYTES, int(mem_bytes)))

    def _scrubbed_env(self, cwd: str) -> dict[str, str]:
        env = dict(_SCRUBBED_ENV)
        env["HOME"] = cwd
        env["TMPDIR"] = cwd
        return env

    def _preexec(self, cwd: str):
        """Build a preexec_fn that caps memory + isolates the process group.

        ``resource`` is imported lazily; if it is unavailable the caller treats a
        None preexec as a refusal (default-deny: never run without limits).
        """
        try:
            import os
            import resource
        except Exception:
            return None

        mem = self.mem_bytes

        def _limit() -> None:  # pragma: no cover - runs only in the child
            # New process group so the parent can kill the whole tree on timeout.
            try:
                os.setsid()
            except Exception:
                pass
            # Address-space (virtual memory) cap.
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except Exception:
                pass
            # No core dumps, bounded CPU seconds as a backstop to wall-clock.
            try:
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            except Exception:
                pass
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (_HARD_TIMEOUT_S_INT, _HARD_TIMEOUT_S_INT))
            except Exception:
                pass

        return _limit

    def run(
        self,
        lang: str,
        code: str,
        *,
        timeout_s: float,
        cwd: str,
        env: dict[str, str],
    ) -> ExecResult:
        # Lazy, so the module imports clean on a plain python3.
        try:
            import os
            import signal
            import subprocess
        except Exception as exc:  # pragma: no cover - stdlib always present
            return ExecResult(refused=f"runner_unavailable:{exc}")

        # Default-deny: we MUST be able to cap memory + isolate the group. If the
        # preexec cannot be built (no ``resource`` module), refuse to run.
        preexec = self._preexec(cwd)
        if preexec is None:
            return ExecResult(refused="resource_limits_unavailable")

        if lang == "python":
            import sys

            program = _netlock_prelude() + "\n" + str(code)
            argv = [sys.executable, "-I", "-S", "-c", program]
        elif lang == "bash":
            # Bash has no socket of its own; the network-lock for bash is the
            # scrubbed env (blanked proxies) + the cwd confinement + the
            # pre-flight static screen. We additionally restrict PATH so only
            # /usr/bin:/bin tools are reachable.
            argv = ["/bin/bash", "--noprofile", "--norc", "-c", str(code)]
        else:
            return ExecResult(refused=f"unsupported_lang:{lang}")

        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=preexec,
                start_new_session=False,  # preexec already calls setsid
            )
        except Exception as exc:
            return ExecResult(refused=f"spawn_failed:{exc}")

        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
            return ExecResult(
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=int(proc.returncode or 0),
                timed_out=False,
            )
        except subprocess.TimeoutExpired:
            # Kill the whole process group (the child called setsid).
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                stdout, stderr = proc.communicate(timeout=2.0)
            except Exception:
                stdout, stderr = "", ""
            return ExecResult(
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=-1,
                timed_out=True,
            )


# ---------------------------------------------------------------------------
# Shared tool body
# ---------------------------------------------------------------------------
def _resolve_source_urls(ctx: ToolContext, args: dict[str, Any]) -> list[str]:
    """Collect the source page URL(s) the computation is over.

    Accepts ``source_urls`` (list) and/or ``source_url`` (str); falls back to a
    configured ``ctx.extras["exec_source_urls"]`` list. Order-preserving dedupe.
    """
    raw: list[str] = []
    su = args.get("source_urls")
    if isinstance(su, (list, tuple)):
        raw.extend(str(u) for u in su)
    elif isinstance(su, str) and su.strip():
        raw.append(su)
    one = args.get("source_url")
    if isinstance(one, str) and one.strip():
        raw.append(one)
    if not raw:
        fallback = (ctx.extras or {}).get("exec_source_urls")
        if isinstance(fallback, (list, tuple)):
            raw.extend(str(u) for u in fallback)

    out: list[str] = []
    seen: set[str] = set()
    for u in raw:
        u = str(u).strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _resolve_executor(ctx: ToolContext) -> Executor:
    """Production microVM executor if injected, else the local guarded runner.

    PRODUCTION SEAM: ``ctx.extras["code_executor"]`` is where an E2B / gVisor /
    Firecracker microVM executor plugs in. Absent that, the local guarded runner
    is used (benign code only; it refuses if it cannot establish its limits).
    """
    injected = (ctx.extras or {}).get("code_executor")
    if injected is not None and hasattr(injected, "run"):
        return injected
    mem = (ctx.extras or {}).get("exec_mem_bytes", _DEFAULT_MEM_BYTES)
    try:
        mem_bytes = int(mem)
    except (TypeError, ValueError):
        mem_bytes = _DEFAULT_MEM_BYTES
    return LocalGuardedRunner(mem_bytes=mem_bytes)


def _truncate(text: str) -> str:
    text = str(text or "")
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS] + "\n...[truncated]"


def _run_snippet(
    ctx: ToolContext,
    *,
    lang: str,
    code: str,
    args: dict[str, Any],
) -> ToolResult:
    """Shared body for run_code / run_bash: pre-flight, execute, land evidence."""
    if not str(code or "").strip():
        return ToolResult(ok=False, error="empty_code")

    source_urls = _resolve_source_urls(ctx, args)
    if not source_urls:
        # Never land orphan compute output (COMPUTE-OVER-PAGES invariant).
        return ToolResult(ok=False, error="exec_no_source_url")

    # Default-deny static pre-flight (fs-escape + network-egress + empty).
    refusal = preflight(code)
    if refusal:
        return ToolResult(ok=False, error=refusal, display=f"refused: {refusal}")

    timeout_s = _coerce_timeout(args.get("timeout_s"))

    executor = _resolve_executor(ctx)

    # Establish the temp cwd. For the local runner this is the only writable
    # surface; an injected executor is free to ignore it (its microVM has its own
    # ephemeral disk), but we still hand it a clean dir + scrubbed env.
    import tempfile

    cwd = tempfile.mkdtemp(prefix="exec_sandbox_")
    if isinstance(executor, LocalGuardedRunner):
        env = executor._scrubbed_env(cwd)
    else:
        env = dict(_SCRUBBED_ENV)
        env["HOME"] = cwd
        env["TMPDIR"] = cwd

    try:
        result = executor.run(lang, code, timeout_s=timeout_s, cwd=cwd, env=env)
    except Exception as exc:
        return ToolResult(ok=False, error=f"executor_error:{type(exc).__name__}:{exc}")
    finally:
        # Best-effort cleanup of the temp dir.
        try:
            import shutil

            shutil.rmtree(cwd, ignore_errors=True)
        except Exception:
            pass

    if not isinstance(result, ExecResult):
        return ToolResult(ok=False, error="malformed_executor_result")

    if result.refused:
        # The guarded runner refused (could not establish a limit) -> default-deny.
        return ToolResult(ok=False, error=f"refused:{result.refused}", display=f"refused: {result.refused}")

    if result.timed_out:
        return ToolResult(
            ok=False,
            error="exec_timeout",
            display=_truncate(f"timed out after {timeout_s}s\n{result.stdout}\n{result.stderr}"),
        )

    # Strip trailing whitespace so the landed grounding text is clean and
    # deterministic (``print(x)`` adds a trailing newline; ``echo`` too).
    stdout = _truncate(result.stdout).strip()
    stderr = _truncate(result.stderr).strip()
    ok = int(result.exit_code) == 0

    # Rendered grounding text = the computed stdout (the number/sort/count the
    # agent derived from the source pages). Keyed to EVERY supplied source_url so
    # a Cite of the underlying page resolves exactly like a fetch.
    rendered = stdout if stdout else stderr
    if not ok:
        display = _truncate(f"exit={result.exit_code}\nstdout:\n{stdout}\nstderr:\n{stderr}")
        return ToolResult(
            ok=False,
            error="exec_nonzero_exit",
            display=display,
            n_results=0,
        )

    snippets = {u: rendered for u in source_urls}
    display = stdout
    if stderr:
        display = f"{stdout}\n[stderr]\n{stderr}"

    return ToolResult(
        snippets=snippets,
        fetched_urls=list(source_urls),
        n_results=1,
        display=_truncate(display),
        ok=True,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class RunCodeTool:
    """``run_code``: run agent-authored Python over already-fetched data.

    Lands the computed stdout keyed to the supplied ``source_urls`` so a later
    ``Cite(source_url)`` resolves like a fetch. Default-deny security: network is
    locked to localhost:{7770,9999,8090}, fs is confined to a temp cwd, env is
    scrubbed, and wall-clock + memory limits are enforced (refuses if they
    cannot be established).
    """

    name = "run_code"
    description = (
        "Run sandboxed Python over already-fetched page data to compute a derived "
        "result; lands stdout keyed to the source page URLs. Network-locked to the "
        "localhost sandbox, fs-confined, time + memory bounded."
    )
    args_schema: dict = {
        "code": {"type": "string", "required": True},
        "source_urls": {"type": "list", "required": False},
        "timeout_s": {"type": "float", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        code = str(args.get("code") or "")
        return _run_snippet(ctx, lang="python", code=code, args=args)


class RunBashTool:
    """``run_bash``: run agent-authored Bash over already-fetched data.

    Same default-deny posture and the same COMPUTE-OVER-PAGES landing as
    :class:`RunCodeTool`, for shell idioms (grep / sort / wc) over fetched text.
    """

    name = "run_bash"
    description = (
        "Run sandboxed Bash over already-fetched page data to compute a derived "
        "result (grep/sort/count); lands stdout keyed to the source page URLs. "
        "Network-locked to the localhost sandbox, fs-confined, time + memory bounded."
    )
    args_schema: dict = {
        "command": {"type": "string", "required": True},
        "source_urls": {"type": "list", "required": False},
        "timeout_s": {"type": "float", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        command = str(args.get("command") or args.get("code") or "")
        return _run_snippet(ctx, lang="bash", code=command, args=args)


# ---------------------------------------------------------------------------
# Provider-discovery contract
# ---------------------------------------------------------------------------
def provide_tools() -> list[Any]:
    """Return this module's two tools for the registry discovery loop.

    Called with NO args at registry-build time; cheap (no I/O, no heavy import).
    Returns exactly two tools: ``run_code`` and ``run_bash``.
    """
    return [RunCodeTool(), RunBashTool()]


__all__ = [
    "RunCodeTool",
    "RunBashTool",
    "Executor",
    "ExecResult",
    "LocalGuardedRunner",
    "preflight",
    "check_fs_escape",
    "check_network_egress",
    "provide_tools",
]
