"""Transport-level evidence recorder for the sandbox shim.

Background
----------
Until 2026-07-08 the benchmark reconstructed grounding from the report prose:
``build_sandbox_cache.py`` scanned the finished reports for URLs, the evaluator
fetched those URLs itself, and ``decidable_scorer`` matched the report text
against the evaluator's copy. Nothing in that chain observes the agent. A model
that guesses a URL that happens to exist, and paraphrases a page it never
opened, scores exactly like a model that retrieved and read it.

The proof that the instrument was blind: ``shim_search_delta`` was 0 on all 312
runs of the 13-task subset, while ``llm_calls_delta`` varied normally. The shim
only ever logged *blocked* URLs, never the ones it served.

This module records the other side: what the shim actually served, to whom.

Design constraints
------------------
1. The record is written by the shim, which lives outside the agent process.
   The agent cannot forge it. (Contrast: the 2026-07-06 B1 defect, where the
   harness grafted URLs into the agent's own report.)
2. Every record carries a ``run_id``. Attribution comes from ``/_mark``
   brackets, the same mechanism ds_proxy already uses for token accounting.
3. ``/_mark`` brackets are only sound when one run at a time uses a given shim
   instance. The harness runs two workers concurrently (measured: max
   concurrency 2, always cross-backbone), so each worker MUST get its own shim
   instance. :func:`mark_start` raises :class:`RunAlreadyActive` on a reentrant
   start rather than silently interleaving two runs into one log.
4. Traffic that arrives with no active run is written to ``_unattributed.jsonl``
   rather than dropped. A silently-dropped record is how ``shim_search_delta``
   stayed 0 for months without anyone noticing.
5. Response bodies are content-addressed. The scorer reads the bytes the agent
   was served, never re-fetches at scoring time.

Environment
-----------
``SHIM_EVIDENCE_DIR``   where to write (default: ``<repo>/logs/fetch``)
``SHIM_EVIDENCE``       ``0`` disables recording entirely (default: enabled)
``DRA_WORKER_ID``       free-form worker label stamped on every record
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]

UNATTRIBUTED = "_unattributed"


class RunAlreadyActive(RuntimeError):
    """A second `/_mark start` arrived while a run was still open.

    The caller must surface this as HTTP 409. Interleaving two runs into one
    evidence log would make every derived metric unattributable, which is the
    exact failure this module exists to prevent.
    """


@dataclass
class RunContext:
    run_id: str
    lane: Optional[str] = None
    task: Optional[str] = None
    backbone: Optional[str] = None
    worker: Optional[str] = None
    # Whether this lane's PAGE READS are observable through the shim. Declared by
    # the harness from config/lane_protocol.yaml and stamped onto every record so
    # `fetch_log` can decide, per run, whether `pof` is a real transport measure
    # or must be withheld. A lane whose fetches bypass the shim (direct requests/
    # aiohttp/curl to the site) is NOT observable: if we still computed pof it
    # would read 0 and the lane would be accused of citing pages it never opened,
    # when in fact it opened them off-shim. See FETCH_PATH_AUDIT_2026-07-08.md.
    #
    # Default is None, NOT False, on purpose: a bracket opened without declaring
    # observability (the preflight canary, unit tests, any pre-2026-07-08 log)
    # must not stamp `fetch_observable=false` into its records, or every existing
    # transport test and the canary would flip to available=False. `stamp()`
    # drops None, so an undeclared bracket writes no field and `fetch_log`
    # treats an absent field as observable (backward compatible). The harness is
    # the sole authority: it always sends an explicit value and defaults unknown
    # lanes to False, which is where "when unsure, do not claim observable"
    # actually lives.
    fetch_observable: Optional[bool] = None
    started_ts: float = field(default_factory=lambda: round(time.time(), 3))

    def stamp(self) -> dict:
        d = asdict(self)
        d.pop("started_ts", None)
        return {k: v for k, v in d.items() if v is not None}


_LOCK = threading.RLock()
_ACTIVE: Optional[RunContext] = None
# Wall-clock of the last write attributed to _ACTIVE (its start, or any of its
# search/fetch/block records). Used to tell a LIVE bracket from an ORPHANED one:
# a run killed by `timeout` SIGTERM, the watchdog's os._exit, or an external
# SIGKILL runs neither its finally nor any atexit, so it never posts mark_end and
# leaves _ACTIVE open forever. Without a liveness check that stale bracket 409s
# every later run and one dead run bricks the whole queue. See mark_start.
_ACTIVE_LAST_TS: float = 0.0
_COUNTERS: dict[str, int] = {}


def bracket_ttl() -> float:
    """Idle seconds after which an open bracket is treated as orphaned and a
    start for a DIFFERENT run may reclaim it instead of 409-ing.

    Set above the longest gap between shim calls in a LIVE run: the no-progress
    watchdog kills a genuinely stalled run at stall_timeout_s (900s default), so
    a bracket idle longer than that belongs to a run that is already dead. Under
    the required one-shim-per-worker deployment reclaim is always correct, since
    a second `start` only arrives after the previous run on that shim ended. On a
    (mis-)shared shim the TTL still protects a live sibling: it keeps writing
    records, so it never goes idle and a concurrent start still 409s. Override
    with SHIM_BRACKET_TTL_S.
    """
    raw = os.environ.get("SHIM_BRACKET_TTL_S", "").strip()
    try:
        v = float(raw) if raw else 900.0
    except ValueError:
        v = 900.0
    # 0 is allowed (reclaim any already-idle bracket immediately, useful in the
    # strict one-shim-per-worker deployment and in tests). Only a negative /
    # unparseable value falls back to the safe 900s default.
    return v if v >= 0 else 900.0


def enabled() -> bool:
    return os.environ.get("SHIM_EVIDENCE", "1").strip().lower() not in {"0", "false", "no", "off"}


def evidence_dir() -> Path:
    raw = os.environ.get("SHIM_EVIDENCE_DIR", "").strip()
    return Path(raw) if raw else (_REPO_ROOT / "logs" / "fetch")


def blob_dir() -> Path:
    return evidence_dir() / "blobs"


def worker_id() -> Optional[str]:
    return os.environ.get("DRA_WORKER_ID", "").strip() or None


def active() -> Optional[RunContext]:
    with _LOCK:
        return _ACTIVE


def counters() -> dict[str, int]:
    """Per-process tallies, for the preflight canary and for /healthz."""
    with _LOCK:
        return dict(_COUNTERS)


def reset_for_tests() -> None:
    global _ACTIVE, _ACTIVE_LAST_TS
    with _LOCK:
        _ACTIVE = None
        _ACTIVE_LAST_TS = 0.0
        _COUNTERS.clear()


def mark_start(payload: dict) -> RunContext:
    """Open a run bracket.

    Raises RunAlreadyActive only if a DIFFERENT run is open AND still live (its
    last record is within bracket_ttl()). If the open bracket has gone idle past
    the TTL its owner is dead (killed without posting mark_end); it is reclaimed
    with an ``orphaned`` close on ITS OWN log so one dead run cannot 409-brick the
    rest of the queue. A reentrant start for the same run_id is a no-op.
    """
    global _ACTIVE, _ACTIVE_LAST_TS
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    with _LOCK:
        if _ACTIVE is not None and _ACTIVE.run_id != run_id:
            idle = time.time() - _ACTIVE_LAST_TS
            if idle <= bracket_ttl():
                raise RunAlreadyActive(
                    f"run {_ACTIVE.run_id!r} is still live (idle {idle:.0f}s <= "
                    f"ttl {bracket_ttl():.0f}s); refusing to interleave {run_id!r}. "
                    "Give each concurrent worker its own shim instance."
                )
            # Orphaned bracket: the owning run died without closing. Reclaim it.
            # The close record lands on the DEAD run's log, so its evidence stays
            # self-consistent and attributable, and the new run starts clean.
            stale = _ACTIVE
            _ACTIVE = None
            _write(stale, {"kind": "mark", "phase": "end",
                           "orphaned": True, "idle_s": round(idle, 1)})
        if _ACTIVE is not None and _ACTIVE.run_id == run_id:
            _ACTIVE_LAST_TS = time.time()
            return _ACTIVE
        # Read fetch_observable straight from the payload. Absent -> None (not
        # stamped, treated as observable downstream); present -> coerce to bool
        # so an explicit false is honoured and withholds pof for this run.
        fo = payload.get("fetch_observable")
        _ACTIVE = RunContext(
            run_id=run_id,
            lane=payload.get("lane") or payload.get("agent"),
            task=payload.get("task") or payload.get("task_id"),
            backbone=payload.get("backbone") or payload.get("model"),
            worker=payload.get("worker") or worker_id(),
            fetch_observable=(None if fo is None else bool(fo)),
        )
        _ACTIVE_LAST_TS = time.time()
        ctx = _ACTIVE
    _write(ctx, {"kind": "mark", "phase": "start"})
    return ctx


def mark_end(payload: dict) -> dict:
    """Close the current bracket. Returns a small summary for the runner."""
    global _ACTIVE
    run_id = str(payload.get("run_id") or "").strip()
    with _LOCK:
        ctx = _ACTIVE
        if ctx is None:
            return {"ok": True, "closed": None, "note": "no active run"}
        if run_id and ctx.run_id != run_id:
            raise RunAlreadyActive(
                f"cannot close {run_id!r}: run {ctx.run_id!r} is the open one"
            )
        _ACTIVE = None
        summary = {
            "ok": True,
            "closed": ctx.run_id,
            "elapsed_s": round(time.time() - ctx.started_ts, 3),
            "counters": dict(_COUNTERS),
        }
    _write(ctx, {"kind": "mark", "phase": "end"})
    return summary


def _bump(kind: str) -> None:
    global _ACTIVE_LAST_TS
    with _LOCK:
        _COUNTERS[kind] = _COUNTERS.get(kind, 0) + 1
        # Every attributed record is a sign of life for the open bracket, so the
        # orphan-reclaim TTL in mark_start measures true inactivity, not just
        # "time since the run started".
        if _ACTIVE is not None:
            _ACTIVE_LAST_TS = time.time()


def _log_path(run_id: str) -> Path:
    d = evidence_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{run_id}.jsonl"


def _write(ctx: Optional[RunContext], record: dict) -> None:
    if not enabled():
        return
    rec = {"ts": round(time.time(), 3)}
    rec.update(ctx.stamp() if ctx is not None else {"run_id": None, "worker": worker_id()})
    rec.update(record)
    try:
        path = _log_path(ctx.run_id if ctx is not None else UNATTRIBUTED)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
    except Exception:
        # Never let evidence writing take down a request. But do count it, so a
        # broken evidence path shows up in the canary instead of looking like
        # "the agent made no calls".
        _bump("write_error")


def store_blob(body: bytes) -> str:
    """Content-address a response body. Returns its sha256 hex digest."""
    digest = hashlib.sha256(body).hexdigest()
    if not enabled():
        return digest
    try:
        d = blob_dir()
        d.mkdir(parents=True, exist_ok=True)
        target = d / digest
        if not target.exists():
            # Concurrent full-content searches often return the same page to
            # several summarizers. A digest-wide ``.part`` name lets those
            # writers race: the first rename removes the shared temporary file
            # and every later rename is counted as ``blob_error``. Give each
            # request thread its own temporary file; replacing an identical
            # content-addressed target is safe and atomic.
            tmp = d / (
                f".{digest}.{os.getpid()}.{threading.get_ident()}.part"
            )
            try:
                tmp.write_bytes(body)
                tmp.replace(target)
            finally:
                tmp.unlink(missing_ok=True)
    except Exception:
        _bump("blob_error")
    return digest


def load_blob(digest: str) -> Optional[bytes]:
    p = blob_dir() / digest
    try:
        return p.read_bytes()
    except Exception:
        return None


def record_search(query: str, urls: list[str], *, endpoint: str,
                  n_results: Optional[int] = None,
                  source_diag: Optional[dict] = None) -> None:
    """One search call: the query, and every URL the shim handed back.

    ``urls_returned`` is what makes `retrieval_utilization` and the
    `searched / linked / guessed` provenance classes computable. Without it a
    cited URL cannot be distinguished from a guessed one.
    """
    _bump("search")
    rec = {
        "kind": "search",
        "endpoint": endpoint,
        "query": query,
        "n_results": len(urls) if n_results is None else n_results,
        "urls_returned": list(urls),
    }
    if source_diag:
        # Which of the three sandbox sources answered, and why the silent ones
        # were silent. A source that refuses the connection and a source with no
        # match for this query both return zero hits; only this field separates
        # them. The store was down for an entire scored subset and nothing in
        # the data said so.
        rec["source_diag"] = source_diag
    _write(active(), rec)


def record_fetch(url: str, status: int, body: bytes, *, endpoint: str,
                 error: Optional[str] = None,
                 links: Optional[list[str]] = None) -> str:
    """One page fetch. Stores the served bytes and returns their digest.

    ``links`` are the absolute on-page navigable URLs, captured by the shim from
    the served HTML at fetch time. They are stored on the record (not re-derived
    from the blob at scoring time) because the /extract chokepoint stores
    ``get_text()`` output, which has already thrown away every ``<a href>``: a
    regex over that blob finds zero links, so a real page the agent reached by
    following an on-page link would be mis-scored ``hallucinated_grounding``, a
    false accusation. See FETCH_PATH_AUDIT_2026-07-08.md and fetch_log.linked_urls.
    """
    _bump("fetch")
    digest = store_blob(body or b"")
    rec = {
        "kind": "fetch",
        "endpoint": endpoint,
        "url": url,
        "status": int(status),
        "resp_bytes": len(body or b""),
        "body_sha256": digest,
    }
    # Distinguish "no links field" (old log / blocked page) from "parsed, none
    # found": store the list whenever the caller parsed the page, even if empty,
    # so fetch_log does not fall back to the useless blob regex for a page we
    # already know has zero navigable links.
    if links is not None:
        rec["links"] = list(links)
    if error:
        rec["error"] = error
    _write(active(), rec)
    return digest


def record_block(url: str, endpoint: str, reason: str) -> None:
    _bump("block")
    _write(active(), {"kind": "block", "endpoint": endpoint, "url": url, "reason": reason})
