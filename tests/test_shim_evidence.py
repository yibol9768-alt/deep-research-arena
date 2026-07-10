"""Transport-evidence recorder invariants (integrations/search_shim/evidence.py).

The recorder is the only place that observes what the shim served to whom. Every
invariant below maps to a way the instrument was blind before 2026-07-08:

  * reentrant `/_mark start` must 409 instead of interleaving two runs into one
    log (attribution would become impossible, which is what happened when the
    two concurrent workers were told apart only by their `model` value);
  * traffic with no open run must land in `_unattributed.jsonl`, not be dropped
    (silent dropping is why `shim_search_delta` read 0 on all 312 runs);
  * a broken evidence path must bump `write_error`, never crash the request and
    never look like "the agent made no calls".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import integrations.search_shim.evidence as ev  # noqa: E402


@pytest.fixture
def clean_shim(tmp_path, monkeypatch):
    """Fresh process state + a writable evidence dir under tmp_path.

    evidence.py reads SHIM_EVIDENCE / SHIM_EVIDENCE_DIR on every call, so setenv
    is enough; there is no cached config to reset. The module-global _ACTIVE and
    _COUNTERS do persist across calls, hence reset_for_tests().
    """
    monkeypatch.setenv("SHIM_EVIDENCE", "1")
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.delenv("DRA_WORKER_ID", raising=False)
    ev.reset_for_tests()
    yield tmp_path
    ev.reset_for_tests()


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# --- run brackets ----------------------------------------------------------

def test_mark_start_same_run_id_is_idempotent(clean_shim):
    a = ev.mark_start({"run_id": "r1", "lane": "storm"})
    b = ev.mark_start({"run_id": "r1"})
    assert a is b
    assert ev.active().run_id == "r1"
    # The second start must not have flipped lane back to None.
    assert ev.active().lane == "storm"


def test_mark_start_reentrant_different_run_raises(clean_shim):
    ev.mark_start({"run_id": "r1"})
    with pytest.raises(ev.RunAlreadyActive):
        ev.mark_start({"run_id": "r2"})
    # The first run stays the open one; the intruder is rejected, not merged.
    assert ev.active().run_id == "r1"


def test_mark_start_requires_run_id(clean_shim):
    with pytest.raises(ValueError):
        ev.mark_start({"lane": "storm"})


def test_stale_bracket_is_reclaimed_not_409(clean_shim, monkeypatch):
    # The wedge fix: a run killed by SIGTERM/os._exit/SIGKILL never posts
    # mark_end and leaves _ACTIVE open. With a liveness TTL, the NEXT run in the
    # queue reclaims the orphaned bracket instead of 409-ing forever. TTL=0 makes
    # any already-open bracket immediately reclaimable for the test.
    monkeypatch.setenv("SHIM_BRACKET_TTL_S", "0")
    ev.mark_start({"run_id": "dead", "lane": "camel-ai"})
    # A different run arrives; the dead bracket is past TTL, so reclaim + open.
    ctx = ev.mark_start({"run_id": "fresh", "lane": "storm"})
    assert ctx.run_id == "fresh"
    assert ev.active().run_id == "fresh"
    # The dead run's own log carries an `orphaned` close, keeping it consistent.
    dead_log = _read_jsonl(clean_shim / "dead.jsonl")
    assert any(r.get("phase") == "end" and r.get("orphaned") for r in dead_log)
    # The fresh run's log did NOT inherit the dead run's records.
    fresh_log = _read_jsonl(clean_shim / "fresh.jsonl")
    assert all(r.get("run_id") == "fresh" for r in fresh_log)


def test_live_bracket_still_409s_within_ttl(clean_shim, monkeypatch):
    # A generous TTL must NOT let a concurrent worker steal a live bracket: the
    # 409 that protects attribution on a (mis-)shared shim stays intact.
    monkeypatch.setenv("SHIM_BRACKET_TTL_S", "3600")
    ev.mark_start({"run_id": "live"})
    with pytest.raises(ev.RunAlreadyActive):
        ev.mark_start({"run_id": "other"})
    assert ev.active().run_id == "live"


def test_mark_end_closes_active(clean_shim):
    ev.mark_start({"run_id": "r1"})
    summary = ev.mark_end({"run_id": "r1"})
    assert summary["closed"] == "r1"
    assert ev.active() is None


def test_mark_end_wrong_run_id_raises(clean_shim):
    ev.mark_start({"run_id": "r1"})
    with pytest.raises(ev.RunAlreadyActive):
        ev.mark_end({"run_id": "rX"})
    # A misdirected close must not silently close the real run.
    assert ev.active() is not None and ev.active().run_id == "r1"


def test_mark_end_with_no_active_is_noop(clean_shim):
    out = ev.mark_end({"run_id": "r1"})
    assert out["closed"] is None


# --- unattributed traffic is recorded, not dropped -------------------------

def test_record_with_no_active_run_goes_to_unattributed(clean_shim):
    # This is the exact regression: a record produced outside any bracket must
    # be written, not silently discarded.
    ev.record_search("q", ["http://localhost:9999/a"], endpoint="/search")
    unattr = clean_shim / f"{ev.UNATTRIBUTED}.jsonl"
    assert unattr.exists()
    recs = _read_jsonl(unattr)
    assert len(recs) == 1
    assert recs[0]["run_id"] is None
    assert recs[0]["kind"] == "search"
    # And it must not have been misfiled under some run log.
    assert not (clean_shim / "None.jsonl").exists()


def test_records_land_in_the_open_runs_log(clean_shim):
    ev.mark_start({"run_id": "r1", "lane": "storm", "task": "t7"})
    ev.record_search("q", ["http://localhost:9999/a"], endpoint="/search")
    ev.record_fetch("http://localhost:9999/a", 200, b"body", endpoint="/fetch")
    recs = _read_jsonl(clean_shim / "r1.jsonl")
    kinds = [r["kind"] for r in recs]
    assert "search" in kinds and "fetch" in kinds
    assert all(r["run_id"] == "r1" for r in recs)


# --- content-addressed blobs ----------------------------------------------

def test_store_blob_dedupes_identical_bodies(clean_shim):
    body = b"the same page bytes"
    d1 = ev.store_blob(body)
    d2 = ev.store_blob(body)
    assert d1 == d2
    blobs = list((clean_shim / "blobs").iterdir())
    assert len(blobs) == 1  # one physical file for identical content


def test_load_blob_roundtrips_raw_bytes(clean_shim):
    body = b"\x00\x01raw non-utf8 \xff bytes"
    digest = ev.store_blob(body)
    assert ev.load_blob(digest) == body


def test_load_blob_missing_returns_none(clean_shim):
    assert ev.load_blob("deadbeef" * 8) is None


# --- disabled mode ---------------------------------------------------------

def test_disabled_skips_files_but_still_digests(clean_shim, monkeypatch):
    monkeypatch.setenv("SHIM_EVIDENCE", "0")
    body = b"page bytes"
    # Digest must still be computable (the scorer keys blobs by it) even when
    # recording is off.
    digest = ev.store_blob(body)
    assert digest == __import__("hashlib").sha256(body).hexdigest()
    assert not (clean_shim / "blobs").exists()

    ev.mark_start({"run_id": "r1"})
    ev.record_search("q", ["http://localhost:9999/a"], endpoint="/search")
    assert not (clean_shim / "r1.jsonl").exists()


# --- write failures are counted, never fatal -------------------------------

def test_write_error_is_counted_not_raised(clean_shim, monkeypatch):
    # Point the evidence dir at a path whose parent is a regular file: mkdir
    # then raises NotADirectoryError even for root, unlike a chmod'd dir which
    # root can still write through.
    blocker = clean_shim / "afile"
    blocker.write_text("x")
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", str(blocker / "sub"))
    ev.reset_for_tests()

    # Must not raise: a broken evidence path cannot take down a served request.
    ev.record_search("q", ["http://localhost:9999/a"], endpoint="/search")

    counters = ev.counters()
    assert counters.get("search") == 1
    assert counters.get("write_error", 0) >= 1
