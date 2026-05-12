"""Cross-process exclusive lock for subprocess runners that share a fixed
driver-script path. Used when N parallel bulk workers all call the same
runner; without this, two workers race on writing/reading the driver file
and one ends up reading a half-rewritten script (SyntaxError on
``unmatched ')'`` was the symptom).

Every runner that writes a driver to a fixed path should wrap its write +
subprocess + cleanup in:

    from scripts.runners._runner_lock import runner_exclusive_lock
    with runner_exclusive_lock("deerflow"):
        ...

Different agents (different lock names) keep parallelism; only same-agent
calls serialize.
"""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

_LOCK_DIR = Path("/tmp/dr_runner_locks")


@contextmanager
def runner_exclusive_lock(agent: str):
    """Block until this process owns the agent-scoped exclusive lock.

    Lock file is per-agent so different runners don't serialize against
    each other. Released on context exit (or process death — fcntl drops
    the lock automatically when the file descriptor closes).
    """
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = _LOCK_DIR / f"{agent}.lock"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(fd)
