"""Regression tests for STORM scratch-dir isolation.

Bug fixed here: ``storm_runner.run`` used to key its scratch dir on
``md5(intent[:300])`` with ``os.makedirs(exist_ok=True)`` and never cleaned it.
After ``runner.run()`` it recovered the article by rglob-ing the whole tree and
picking the LARGEST ``*.txt``. So a prior run of the same task (or a concurrent
same-intent run) that left a ``storm_gen_article*.txt`` behind could be silently
returned as THIS run's output whenever the current run produced no fresh, larger
article. The fix:

1. Use a unique per-invocation scratch dir (``uuid4().hex`` token) so two runs
   never share a tree.
2. Delete the tree in a ``finally`` block so nothing leaks to a later run.
3. ``_extract_article`` ignores any file whose mtime predates the run start,
   so even within one tree a stale article can never be picked up.

These tests exercise the pure ``_extract_article`` helper and the dir-uniqueness
contract without needing the (venv-only) ``dspy`` / ``knowledge_storm`` stack;
``dspy`` is stubbed in ``sys.modules`` exactly as the other storm tests do.
"""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# storm_runner imports dspy at module load; stub it so the import succeeds in a
# bare venv (same pattern as test_strict_sandbox_forwarding.py).
if "dspy" not in sys.modules:
    _dspy = types.ModuleType("dspy")

    class _Retrieve:  # minimal stand-in for dspy.Retrieve
        def __init__(self, *a, **k):
            pass

    _dspy.Retrieve = _Retrieve
    sys.modules["dspy"] = _dspy

import scripts.runners.storm_runner as storm_runner  # noqa: E402


def _write(path: Path, text: str, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mtime is not None:
        import os

        os.utime(path, (mtime, mtime))
    return path


def test_extract_article_ignores_stale_file(tmp_path):
    """A larger article that predates the run start must NOT be returned."""
    run_start = time.time()

    # Stale: written "before" the run, and bigger than the fresh one.
    _write(
        tmp_path / "topic" / "storm_gen_article.txt",
        "STALE " + "x" * 5000,
        mtime=run_start - 100,
    )
    # Fresh: smaller, but produced by this run.
    fresh = _write(
        tmp_path / "topic" / "storm_gen_article_polished.txt",
        "FRESH article body",
        mtime=run_start + 1,
    )

    out = storm_runner._extract_article(tmp_path, run_start)
    assert out.startswith("FRESH article body")
    assert "STALE" not in out
    assert fresh.read_text() in out


def test_extract_article_no_fresh_returns_empty_sentinel(tmp_path):
    """If only stale files exist, the run reports empty, not the stale text."""
    run_start = time.time()
    _write(
        tmp_path / "topic" / "storm_gen_article_polished.txt",
        "STALE polished from a previous run",
        mtime=run_start - 100,
    )

    out = storm_runner._extract_article(tmp_path, run_start)
    assert out == "(empty storm output)"
    assert "STALE" not in out


def test_extract_article_prefers_polished_then_largest(tmp_path):
    """Among fresh files the polished article wins; ties fall to largest."""
    run_start = time.time()
    _write(
        tmp_path / "topic" / "storm_gen_article.txt",
        "draft " + "y" * 9000,
        mtime=run_start + 1,
    )
    _write(
        tmp_path / "topic" / "storm_gen_article_polished.txt",
        "polished body short",
        mtime=run_start + 1,
    )
    out = storm_runner._extract_article(tmp_path, run_start)
    assert out.startswith("polished body short")


def test_extract_article_never_appends_harness_references(tmp_path, caplog):
    """Fairness contract: the harness NEVER writes STORM's bibliography into the report.

    STORM keeps its retrieved sources in ``url_to_info.json``. The harness used to
    append them as a ``## References`` block onto the extracted article "so the URL
    extractor can recover" them. That injected block was STORM's ENTIRE grounding:
    a counterfactual rescore with it removed dropped storm's macro reach
    0.9609 -> 0.0000. STORM's own article contains no sandbox URLs; the harness was
    ghost-writing its citations into the scored artifact, a credit no other
    framework gets from the harness. The injection was removed 2026-07-08 (fairness
    audit); the bibliography is now logged only, never appended.

    This test LOCKS that contract. Do NOT "fix" a red here by re-appending the
    references: that is exactly the reverted graft. The extracted report must be
    byte-identical to the file STORM itself wrote, and the bibliography URLs must
    appear only in the log, never in the returned text.
    """
    import json
    import logging

    run_start = time.time()
    # Article body deliberately contains none of the bibliography URLs, so any URL
    # found in the output could only have been injected by the harness.
    article_body = "# Report title\n\nBody of the report. No sandbox URLs here.\n"
    art = _write(
        tmp_path / "topic" / "storm_gen_article_polished.txt",
        article_body,
        mtime=run_start + 1,
    )
    _write(
        tmp_path / "topic" / "url_to_info.json",
        json.dumps(
            {
                "url_to_unified_index": {
                    "http://localhost:8081/a": 1,
                    "http://localhost:8081/b": 2,
                }
            }
        ),
        mtime=run_start + 1,
    )

    with caplog.at_level(logging.INFO, logger="scripts.runners.storm_runner"):
        out = storm_runner._extract_article(tmp_path, run_start)

    # No harness-injected references block, and no bibliography URL leaked in.
    assert "## References" not in out
    assert "http://localhost:8081/a" not in out
    assert "http://localhost:8081/b" not in out
    # The report is byte-identical to what STORM itself produced.
    assert out == art.read_text()
    assert out == article_body
    # The bibliography is still observed, but only as a diagnostic log line.
    assert any(
        "diagnostic only, not appended" in r.getMessage() for r in caplog.records
    ), "bibliography should be logged as diagnostic, not appended to the report"


def test_run_uses_unique_scratch_dir_and_cleans_up(monkeypatch, tmp_path):
    """run() must use a fresh, unique scratch dir and remove it afterwards.

    Two sequential runs with the SAME intent must not share a directory, and
    neither tree may survive the call (so a later run cannot read it back).
    """
    import asyncio

    # run() drives STORM through a forked native worker that imports
    # knowledge_storm (via _install_offline_information_table_patch) BEFORE it ever
    # reaches the monkeypatched _build_storm_runner. Without the dependency the
    # worker fails at import and run() returns an honest error stub, so the
    # scratch-dir contract can't be exercised. The workstation lacks the package;
    # the box has it. Skip rather than weaken the cleanup assertions.
    pytest.importorskip(
        "knowledge_storm",
        reason="storm native worker imports knowledge_storm; absent on workstation, present on box",
    )

    # Redirect the scratch root into tmp_path by pointing ROOT's data dir there.
    fake_root = tmp_path
    (fake_root / "data" / "results" / "deep").mkdir(parents=True)
    monkeypatch.setattr(storm_runner, "ROOT", fake_root)

    seen_dirs: list[str] = []

    class _FakeRunner:
        def __init__(self, output_dir: str):
            self.output_dir = output_dir

        def run(self, **kwargs):
            seen_dirs.append(self.output_dir)
            # Emit a fresh article so extraction succeeds.
            art = Path(self.output_dir) / "topic" / "storm_gen_article_polished.txt"
            art.parent.mkdir(parents=True, exist_ok=True)
            art.write_text("# Fresh report\n\nbody")

        def post_run(self):
            pass

    def _fake_build(*, shim_url, proxy_url, model, output_dir, api_key):
        return _FakeRunner(output_dir)

    monkeypatch.setattr(storm_runner, "_build_storm_runner", _fake_build)

    intent = "compare prices across stores " * 20  # > 300 chars

    out1 = asyncio.run(
        storm_runner.run(intent, "m", "http://localhost:8081", "http://localhost:8088/v1")
    )
    out2 = asyncio.run(
        storm_runner.run(intent, "m", "http://localhost:8081", "http://localhost:8088/v1")
    )

    assert out1.startswith("# Fresh report")
    assert out2.startswith("# Fresh report")
    # Distinct scratch dirs despite identical intent.
    assert len(seen_dirs) == 2
    assert seen_dirs[0] != seen_dirs[1]
    # Neither tree survives: a later run can never read a stale article back.
    for d in seen_dirs:
        assert not Path(d).exists(), f"scratch dir {d} was not cleaned up"


def test_run_cleans_up_even_on_runner_error(monkeypatch, tmp_path):
    """A failing runner.run() must still leave no scratch dir behind."""
    import asyncio

    # See test_run_uses_unique_scratch_dir_and_cleans_up: the native worker imports
    # knowledge_storm before the monkeypatch is reachable. Absent on workstation,
    # present on box. Skip rather than weaken the cleanup-on-error assertion.
    pytest.importorskip(
        "knowledge_storm",
        reason="storm native worker imports knowledge_storm; absent on workstation, present on box",
    )

    fake_root = tmp_path
    (fake_root / "data" / "results" / "deep").mkdir(parents=True)
    monkeypatch.setattr(storm_runner, "ROOT", fake_root)

    seen: list[str] = []

    class _Boom:
        def __init__(self, output_dir: str):
            seen.append(output_dir)

        def run(self, **kwargs):
            raise RuntimeError("storm exploded")

        def post_run(self):
            pass

    monkeypatch.setattr(
        storm_runner,
        "_build_storm_runner",
        lambda *, shim_url, proxy_url, model, output_dir, api_key: _Boom(output_dir),
    )

    with pytest.raises(RuntimeError, match="storm exploded"):
        asyncio.run(
            storm_runner.run("intent", "m", "http://localhost:8081", "http://localhost:8088/v1")
        )

    assert seen, "runner was never built"
    assert not Path(seen[0]).exists(), "scratch dir leaked after an error"
