from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest

from integrations.search_shim import evidence


def test_blob_store_is_safe_for_duplicate_concurrent_bodies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SHIM_EVIDENCE", "1")
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", str(tmp_path))
    evidence.reset_for_tests()
    body = b"the same fetched page body"
    writers = 8
    barrier = threading.Barrier(writers)
    original_write_bytes = Path.write_bytes

    def synchronized_write(path: Path, value: bytes) -> int:
        written = original_write_bytes(path, value)
        if path.suffix == ".part":
            barrier.wait(timeout=5)
        return written

    monkeypatch.setattr(Path, "write_bytes", synchronized_write)
    with ThreadPoolExecutor(max_workers=writers) as pool:
        digests = list(pool.map(evidence.store_blob, [body] * writers))

    assert len(set(digests)) == 1
    assert (evidence.blob_dir() / digests[0]).read_bytes() == body
    assert evidence.counters().get("blob_error", 0) == 0
    assert not list(evidence.blob_dir().glob("*.part"))
