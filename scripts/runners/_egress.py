"""Shared runner-side policy for the recording egress door.

``DRA_EGRESS_PROXY`` means the harness has deliberately placed an HTTP proxy
between the framework process and every sandbox/service origin.  Runners must
not undo that decision by clearing proxy variables or setting ``NO_PROXY=*``.
When the variable is absent we preserve the historical standalone behaviour:
host proxy settings are scrubbed so a developer run cannot leak to the public
internet by accident.

The harness brackets the proxy and decides whether network enforcement is
strong enough to claim ``fetch_observable``.  This module only makes the final
process environment deterministic; it never upgrades evidence on its own.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import MutableMapping
from pathlib import Path


_PROXY_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "no_proxy",
)


def configured(env: MutableMapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return bool(str(source.get("DRA_EGRESS_PROXY", "")).strip())


def enforced(env: MutableMapping[str, str] | None = None) -> bool:
    """Return true only inside a concretely attested worker boundary.

    ``DRA_EGRESS_ENFORCED=1`` remains a human-readable marker, but it has no
    authority by itself. The current uid, capabilities, network namespace,
    routes, proxy, protected evidence paths, and root-owned live proof must all
    agree before a protocol-false lane can become fetch-observable.
    """
    source = os.environ if env is None else env
    value = str(source.get("DRA_EGRESS_ENFORCED", "")).strip().lower()
    if not configured(source) or value not in {"1", "true", "yes", "on"}:
        return False
    try:
        from scripts.production_isolation import current_context_is_enforced

        return current_context_is_enforced(source)
    except Exception:
        return False


def isolation_details(
    env: MutableMapping[str, str] | None = None,
) -> dict[str, object]:
    source = os.environ if env is None else env
    try:
        from scripts.production_isolation import current_context_details

        return current_context_details(source)
    except Exception as exc:  # noqa: BLE001
        return {"verified": False, "error": f"{type(exc).__name__}: {exc}"}


def remote_proxy(env: MutableMapping[str, str] | None = None) -> str:
    """Runner-visible URL for an SSH/Windows child.

    It must reach the *same* bracketed door, normally through an SSH reverse
    tunnel. A loopback URL on the benchmark host cannot simply be reused on a
    different machine.
    """
    source = os.environ if env is None else env
    return str(source.get("DRA_REMOTE_EGRESS_PROXY", "")).strip()


def remote_enforced(env: MutableMapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    if not enforced(source) or not remote_proxy(source):
        return False
    try:
        from scripts.production_isolation import remote_context_is_enforced

        return remote_context_is_enforced(source)
    except Exception:
        return False


def apply_proxy_env(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Apply the canonical proxy variables to a runner's *final* environment."""
    url = str(env.get("DRA_EGRESS_PROXY", "")).strip()
    if not url:
        return env
    from integrations.egress_proxy.app import proxy_env

    env.update(proxy_env(url))
    return env


def scrub_or_apply(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Use the recording door when configured, otherwise retain safe scrub.

    Every subprocess runner calls this immediately before ``subprocess.run``.
    This makes a late or stale host proxy unable to outrank the harness door.
    """
    if configured(env):
        return apply_proxy_env(env)
    for key in _PROXY_KEYS:
        env.pop(key, None)
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env


def install_aiohttp_trust_env() -> None:
    """Make in-process aiohttp clients honour the harness proxy when enabled.

    aiohttp defaults ``trust_env`` to false, unlike requests/curl.  Patch the
    constructor once, but only force the value while the egress door is active;
    standalone callers keep their explicit/default behaviour.
    """
    if not configured():
        return
    try:
        import aiohttp
    except ImportError:
        return
    original = aiohttp.ClientSession.__init__
    if getattr(original, "_dra_egress_trust_env", False):
        return

    def _init(self, *args, **kwargs):
        kwargs["trust_env"] = True
        return original(self, *args, **kwargs)

    _init._dra_egress_trust_env = True  # type: ignore[attr-defined]
    aiohttp.ClientSession.__init__ = _init


def scratch_path(prefix: str, suffix: str = ".py") -> Path:
    """Return a unique worker-writable path outside the read-only code tree."""
    safe = "".join(ch for ch in prefix if ch.isalnum() or ch in {"-", "_"}) or "driver"
    root = Path(
        os.environ.get("DRA_WORKER_SCRATCH_DIR")
        or os.environ.get("TMPDIR")
        or tempfile.gettempdir()
    )
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe}-{uuid.uuid4().hex}{suffix}"
