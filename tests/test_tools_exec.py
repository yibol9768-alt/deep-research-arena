"""Offline tests for the ``run_code`` / ``run_bash`` exec provider.

Everything runs on system ``python3`` with NO live service, NO GPU, and NO
untrusted code on the host: the snippets executed by the LOCAL guarded runner
are benign (``print(2+2)`` / ``echo 4`` / a tiny ``socket.connect`` probe that
the runner's network-lock blocks), and the default-deny / refusal paths are
exercised through an INJECTED fake :class:`Executor`. So the test never needs
root, a real microVM, or any non-local egress.

Coverage map (matches the EXEC DESIGN + task):
  * provide_tools() yields run_code + run_bash, importable without heavy deps.
  * ALLOWS a trivial localhost-only computation: ``print(2+2)`` / ``echo 4`` ->
    stdout ``4``, ok=True, landed keyed to a supplied source_url; the env folds
    it into ``retrieved_snippets`` (grounding-creditable, modality-agnostic).
  * BLOCKS (a) a non-localhost network attempt -- both the static pre-flight and
    the in-child ``socket.connect`` shim; localhost:7770 is permitted.
  * BLOCKS (b) reading a host file outside the temp cwd (``/etc/passwd``).
  * BLOCKS (c) an over-timeout loop -> ``timed_out`` -> ok=False.
  * default-deny: the runner REFUSES when it cannot establish its limits (proven
    via an injected fake executor returning ``refused=...``).
  * no source_urls -> ok=False ``exec_no_source_url`` (never lands orphan output).
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from src.rl.env import CallTool, MockSandboxBackend, ResearchEnv
from src.rl.tools import ToolContext, ToolResult
from src.rl.tools_exec import (
    ExecResult,
    LocalGuardedRunner,
    RunBashTool,
    RunCodeTool,
    check_fs_escape,
    check_network_egress,
    preflight,
    provide_tools,
)
from src.verifiers.citation_format import canonicalize_url


# --------------------------------------------------------------------------- #
# Fixtures: a source PDP URL the computation is "over". The MockSandboxBackend
# carries the page so a parity-style cite would resolve identically to a fetch.
# --------------------------------------------------------------------------- #
URL_PRODUCT = "http://localhost:7770/product-a.html"
URL_FORUM = "http://localhost:9999/f/headphones/alpha-thread"

PAGES = {
    URL_PRODUCT: "Alpha headphones price 199 battery 30h comfort travel.",
    URL_FORUM: "Owners report long-term comfort and durability for Alpha.",
}
INDEX = {"alpha": [URL_PRODUCT, URL_FORUM]}


def _backend() -> MockSandboxBackend:
    return MockSandboxBackend(PAGES, INDEX)


def _ctx(*, extras: dict[str, Any] | None = None) -> ToolContext:
    backend = _backend()
    return ToolContext(
        backend=backend,
        task_config={},
        fetch=lambda url: backend.fetch(url),
        canonicalize=canonicalize_url,
        extras=dict(extras or {}),
    )


class _FakeEchoExecutor:
    """Injected executor that NEVER runs anything: echoes a canned stdout.

    Used to exercise the tool body + landing logic and the default-deny refusal
    path without launching a subprocess.
    """

    def __init__(self, *, stdout: str = "", exit_code: int = 0, timed_out: bool = False, refused: str | None = None) -> None:
        self._res = ExecResult(stdout=stdout, exit_code=exit_code, timed_out=timed_out, refused=refused)
        self.calls: list[dict[str, Any]] = []

    def run(self, lang: str, code: str, *, timeout_s: float, cwd: str, env: dict[str, str]) -> ExecResult:
        self.calls.append({"lang": lang, "code": code, "timeout_s": timeout_s, "cwd": cwd, "env": dict(env)})
        return self._res


# =========================================================================== #
# Discovery + import hygiene.
# =========================================================================== #
def test_provide_tools_yields_run_code_and_run_bash() -> None:
    tools = provide_tools()
    names = [t.name for t in tools]
    assert names == ["run_code", "run_bash"]
    for t in tools:
        assert isinstance(t.name, str) and t.name
        assert isinstance(t.description, str) and t.description
        assert isinstance(t.args_schema, dict)


def test_module_imports_without_heavy_deps() -> None:
    # The module is importable on plain python3; no subprocess/resource pulled in
    # by THIS module at import time (Python may import subprocess itself, so we
    # assert on the module's own top-level source instead).
    import src.rl.tools_exec as mod

    src = open(mod.__file__, encoding="utf-8").read()
    for line in src.splitlines():
        stripped = line.lstrip()
        # A top-level (column-0) import of the lazy deps is forbidden.
        if line == stripped and (
            stripped.startswith("import subprocess")
            or stripped.startswith("import resource")
            or stripped.startswith("import tempfile")
        ):
            raise AssertionError(f"tools_exec imports a lazy dep at top level: {line!r}")


# =========================================================================== #
# ALLOWS: a trivial localhost-only computation lands keyed to source_url.
# =========================================================================== #
def test_run_code_allows_trivial_compute_and_lands_keyed_to_source_url() -> None:
    ctx = _ctx()
    result = RunCodeTool().run(ctx, {"code": "print(2+2)", "source_urls": [URL_PRODUCT]})
    assert result.ok is True
    assert result.display.strip() == "4"
    # Landed keyed to the source page URL (COMPUTE-OVER-PAGES invariant).
    assert result.snippets == {URL_PRODUCT: "4"}
    assert result.fetched_urls == [URL_PRODUCT]
    assert result.n_results == 1


def test_run_bash_allows_trivial_compute() -> None:
    ctx = _ctx()
    result = RunBashTool().run(ctx, {"command": "echo 4", "source_urls": [URL_PRODUCT]})
    assert result.ok is True
    assert result.display.strip() == "4"
    assert result.snippets == {URL_PRODUCT: "4"}
    assert result.fetched_urls == [URL_PRODUCT]


def test_run_code_lands_to_every_source_url() -> None:
    ctx = _ctx()
    result = RunCodeTool().run(
        ctx, {"code": "print(199 + 0)", "source_urls": [URL_PRODUCT, URL_FORUM]}
    )
    assert result.ok is True
    assert set(result.snippets.keys()) == {URL_PRODUCT, URL_FORUM}
    assert result.snippets[URL_PRODUCT].strip() == "199"
    assert result.snippets[URL_FORUM].strip() == "199"


# =========================================================================== #
# BLOCKS (a): non-localhost network -- static pre-flight + runtime connect shim.
# =========================================================================== #
def test_static_preflight_blocks_nonlocal_network() -> None:
    # An explicit non-local target is refused before launch.
    assert check_network_egress('socket.create_connection(("8.8.8.8", 53))') is not None
    assert check_network_egress('requests.get("https://example.com")') is not None
    # A localhost:7770 URL is permitted by the static screen.
    assert check_network_egress('open_url("http://localhost:7770/p.html")') is None


def test_run_code_blocks_nonlocal_network_at_preflight() -> None:
    ctx = _ctx()
    result = RunCodeTool().run(
        ctx, {"code": 'import socket; socket.create_connection(("8.8.8.8", 53))', "source_urls": [URL_PRODUCT]}
    )
    assert result.ok is False
    assert "network_egress_blocked" in str(result.error)
    # Nothing landed.
    assert result.snippets == {}
    assert result.fetched_urls == []


def test_runtime_connect_shim_blocks_nonlocal_but_allows_localhost() -> None:
    """The in-child socket.connect shim is the authoritative network-lock.

    Uses 192.0.2.1 (TEST-NET-1) which passes the static screen but must be
    blocked at runtime; and 127.0.0.1:7770 which the shim must permit (the
    connection is refused since nothing listens, but NO PermissionError).
    """
    ctx = _ctx()
    # Non-local IP that dodges the static token screen -> blocked by the shim.
    blocked = RunCodeTool().run(
        ctx,
        {
            "code": (
                "import socket\n"
                "try:\n"
                "    socket.socket().connect(('192.0.2.1', 80))\n"
                "    print('CONNECTED')\n"
                "except PermissionError:\n"
                "    print('BLOCKED')\n"
            ),
            "source_urls": [URL_PRODUCT],
        },
    )
    assert blocked.ok is True  # snippet itself caught the PermissionError
    assert blocked.display.strip() == "BLOCKED"

    # localhost:7770 is permitted by the shim (refused, not blocked).
    allowed = RunCodeTool().run(
        ctx,
        {
            "code": (
                "import socket\n"
                "try:\n"
                "    socket.socket().connect(('127.0.0.1', 7770))\n"
                "    print('OK_CONNECTED')\n"
                "except PermissionError:\n"
                "    print('BLOCKED')\n"
                "except OSError:\n"
                "    print('ALLOWED_REFUSED')\n"
            ),
            "source_urls": [URL_PRODUCT],
        },
    )
    assert allowed.ok is True
    assert allowed.display.strip() in {"OK_CONNECTED", "ALLOWED_REFUSED"}
    assert allowed.display.strip() != "BLOCKED"


# =========================================================================== #
# BLOCKS (b): reading a host file outside the temp cwd.
# =========================================================================== #
def test_static_preflight_blocks_fs_escape() -> None:
    assert check_fs_escape("open('/etc/passwd').read()") is not None
    assert check_fs_escape("open('/root/.ssh/id_rsa')") is not None
    # Reading/writing inside the temp cwd (relative path) is fine.
    assert check_fs_escape("open('out.txt', 'w').write('x')") is None


def test_run_code_blocks_host_fs_escape() -> None:
    ctx = _ctx()
    result = RunCodeTool().run(
        ctx, {"code": "print(open('/etc/passwd').read())", "source_urls": [URL_PRODUCT]}
    )
    assert result.ok is False
    assert "fs_escape_blocked" in str(result.error)
    assert result.snippets == {}


def test_run_bash_blocks_host_fs_escape() -> None:
    ctx = _ctx()
    result = RunBashTool().run(
        ctx, {"command": "cat /etc/passwd", "source_urls": [URL_PRODUCT]}
    )
    assert result.ok is False
    assert "fs_escape_blocked" in str(result.error)


# =========================================================================== #
# BLOCKS (c): an over-timeout loop -> timed_out -> ok=False.
# =========================================================================== #
def test_run_code_over_timeout_is_killed() -> None:
    ctx = _ctx()
    result = RunCodeTool().run(
        ctx, {"code": "while True:\n    pass", "source_urls": [URL_PRODUCT], "timeout_s": 1.0}
    )
    assert result.ok is False
    assert result.error == "exec_timeout"
    assert result.snippets == {}


# =========================================================================== #
# default-deny: refuse when limits cannot be established (injected fake).
# =========================================================================== #
def test_default_deny_refusal_path_via_injected_executor() -> None:
    refusing = _FakeEchoExecutor(refused="resource_limits_unavailable")
    ctx = _ctx(extras={"code_executor": refusing})
    result = RunCodeTool().run(ctx, {"code": "print(1)", "source_urls": [URL_PRODUCT]})
    assert result.ok is False
    assert "refused" in str(result.error)
    assert result.snippets == {}


def test_injected_executor_lands_canned_stdout() -> None:
    echo = _FakeEchoExecutor(stdout="42\n")
    ctx = _ctx(extras={"code_executor": echo})
    result = RunCodeTool().run(ctx, {"code": "print(40+2)", "source_urls": [URL_PRODUCT]})
    assert result.ok is True
    assert result.snippets == {URL_PRODUCT: "42"}
    # The executor was handed a scrubbed env + a temp cwd, never the host env.
    call = echo.calls[0]
    assert call["env"].get("PATH") == "/usr/bin:/bin"
    assert "exec_sandbox_" in call["cwd"]
    assert call["env"].get("HOME") == call["cwd"]  # HOME points at the temp cwd
    # No host secrets leaked into the child env.
    assert all(k not in call["env"] for k in ("AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY"))


def test_injected_executor_nonzero_exit_is_ok_false() -> None:
    failing = _FakeEchoExecutor(stdout="", exit_code=1)
    ctx = _ctx(extras={"code_executor": failing})
    result = RunCodeTool().run(ctx, {"code": "print(1)", "source_urls": [URL_PRODUCT]})
    assert result.ok is False
    assert result.error == "exec_nonzero_exit"
    assert result.snippets == {}


def test_injected_executor_timeout_is_ok_false() -> None:
    slow = _FakeEchoExecutor(timed_out=True)
    ctx = _ctx(extras={"code_executor": slow})
    result = RunCodeTool().run(ctx, {"code": "print(1)", "source_urls": [URL_PRODUCT]})
    assert result.ok is False
    assert result.error == "exec_timeout"


# =========================================================================== #
# No source_urls -> never land orphan compute output.
# =========================================================================== #
def test_no_source_url_is_refused() -> None:
    ctx = _ctx()
    result = RunCodeTool().run(ctx, {"code": "print(2+2)"})
    assert result.ok is False
    assert result.error == "exec_no_source_url"
    assert result.snippets == {}


def test_empty_code_is_refused() -> None:
    ctx = _ctx()
    result = RunCodeTool().run(ctx, {"code": "", "source_urls": [URL_PRODUCT]})
    assert result.ok is False
    assert result.error == "empty_code"


def test_source_urls_fallback_via_extras() -> None:
    echo = _FakeEchoExecutor(stdout="ok")
    ctx = _ctx(extras={"code_executor": echo, "exec_source_urls": [URL_FORUM]})
    result = RunCodeTool().run(ctx, {"code": "print('ok')"})
    assert result.ok is True
    assert result.fetched_urls == [URL_FORUM]


# =========================================================================== #
# Env integration: a CallTool('run_code') folds the computed result into the
# grounding store -> retrieved_snippets, so a Cite of the source page resolves
# exactly like a fetch (the modality-agnostic invariant).
# =========================================================================== #
def test_env_call_tool_run_code_folds_into_grounding() -> None:
    cfg = {
        "task_id": "exec_synth",
        "intent": "compute over fetched data",
        "prompt": "compute",
        "acquisition": {"tools_allowed": ["search", "fetch", "run_code", "run_bash"]},
        "sandbox_hosts": ["localhost:7770", "localhost:9999", "localhost:8090"],
    }
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()

    obs, done, info = env.step(
        CallTool("run_code", {"code": "print(199)", "source_urls": [URL_PRODUCT]})
    )
    assert done is False
    assert info["ok"] is True
    assert info["tool"] == "run_code"
    # Folded into the SAME slot _do_read writes -> reward-creditable.
    assert obs["fetched_urls"] == [URL_PRODUCT]
    assert obs["retrieved_snippets"] == {canonicalize_url(URL_PRODUCT): "199"}
    # Recorded under /tool/run_code.
    rollout = env.to_rollout()
    assert any(c["endpoint"] == "/tool/run_code" for c in rollout.tool_calls)


def test_env_run_bash_disallowed_when_not_in_tools_allowed() -> None:
    # run_bash absent from tools_allowed -> graceful tool_not_allowed, no crash.
    cfg = {
        "task_id": "exec_synth2",
        "intent": "x",
        "prompt": "x",
        "acquisition": {"tools_allowed": ["search", "fetch", "run_code"]},
        "sandbox_hosts": ["localhost:7770"],
    }
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()
    _obs, done, info = env.step(
        CallTool("run_bash", {"command": "echo 4", "source_urls": [URL_PRODUCT]})
    )
    assert done is False
    assert info["ok"] is False
    assert info["error"] == "tool_not_allowed"


# =========================================================================== #
# preflight aggregate guard.
# =========================================================================== #
def test_preflight_aggregates_guards() -> None:
    assert preflight("") == "empty_code"
    assert preflight("print(2+2)") is None
    assert "fs_escape_blocked" in str(preflight("open('/etc/passwd')"))
    assert "network_egress_blocked" in str(preflight("connect(('8.8.8.8', 53))"))


def test_local_runner_refuses_unsupported_lang() -> None:
    runner = LocalGuardedRunner()
    res = runner.run("ruby", "puts 1", timeout_s=1.0, cwd="/tmp", env={})
    assert isinstance(res, ExecResult)
    assert res.refused is not None and "unsupported_lang" in res.refused
