"""Integration assertion: build_truth_board --diagnostic THREADS cache_policy to
the scorer (SPEC_DECISIONS #2; merge of the D1 scorer param and the D2 board
feature-probe).

D2's board probes ``ds.score_report``'s signature and passes ``cache_policy``
only when the parameter exists; before D1's scorer lane merged, the probe
returned False, ``_scorer_kw`` was empty, and a ``--diagnostic``-stamped board
silently scored in STRICT mode -- the stamp said diagnostic while the numbers
were strict. After the merge the passthrough is LIVE.

This drives ``build_truth_board.main()`` in-process with a spy on ``evaluate``
and asserts the scorer actually RECEIVES ``cache_policy='diagnostic'`` (with
``'strict'`` as the differential control), plus that the withhold accounting
reaches the score detail. A future regression that drops the scorer param --
making the feature-probe go dead so the stamp and the scoring diverge again --
turns this red. It is the merge-time proof that "the passthrough truly activated".
"""

from __future__ import annotations

import inspect
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.build_truth_board as btb  # noqa: E402
from src.eval import decidable_scorer as ds  # noqa: E402

TID = "dr_cross_deep_0001"


def _fixture(tmp_path, lane="storm", tid=TID):
    text = (
        "# Findings\n\nBluetooth headphones use a loudspeaker driver and wireless "
        "radio. [Source](http://localhost:8090/wiki/Bluetooth)\n")
    reports = tmp_path / "reports"
    (reports / lane).mkdir(parents=True, exist_ok=True)
    (reports / lane / f"{tid}.md").write_text(text)
    return reports


def _run_capture(tmp_path, monkeypatch, extra):
    """Run the board in-process, capturing the cache_policy the scorer saw."""
    seen: list = []
    detail_seen: list = []
    real_eval = btb.evaluate

    def spy(*a, **kw):
        seen.append(kw.get("cache_policy"))
        out = real_eval(*a, **kw)
        comp = (out.get("detail") or {}).get("completeness") or {}
        detail_seen.append(comp)
        return out

    monkeypatch.setattr(btb, "evaluate", spy)
    reports = _fixture(tmp_path)
    out = tmp_path / "board.json"
    argv = [
        "build_truth_board.py",
        "--reports-dir", str(reports), "--legacy-nested-layout",
        "--meta-dir", str(tmp_path),
        "--no-require-manifest", "--no-require-transport-pof",
        "--no-require-report-seals", "--no-require-verified-corpus",
        "--out", str(out), *extra,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    rc = btb.main()
    return rc, seen, detail_seen, out


def test_merged_scorer_exposes_the_cache_policy_param():
    """The whole passthrough is contingent on this signature; probe it directly."""
    assert "cache_policy" in inspect.signature(ds.score_report).parameters
    assert "cache_policy" in inspect.signature(ds.score_completeness).parameters


def test_diagnostic_board_threads_diagnostic_to_the_scorer(tmp_path, monkeypatch):
    rc, seen, detail_seen, out = _run_capture(tmp_path, monkeypatch, ["--diagnostic"])
    assert rc == 0, "diagnostic board should build"
    assert seen, "the board scored no report -- fixture or threading broke"
    # THE integration assertion: the scorer saw diagnostic, not the default strict.
    assert all(cp == "diagnostic" for cp in seen), seen
    # ... and the withhold accounting reached the completeness detail.
    assert detail_seen and all(d.get("cache_policy") == "diagnostic"
                               for d in detail_seen), detail_seen
    assert all("withheld_slots" in d for d in detail_seen), detail_seen
    board = json.loads(out.read_text())
    assert board["cache_policy"] == "diagnostic"


def test_strict_board_threads_strict_to_the_scorer(tmp_path, monkeypatch):
    """Differential control: with a cache the strict board threads 'strict'."""
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({
        "http://localhost:8090/wiki/Bluetooth": {
            "status": 200,
            "text": "Bluetooth is a short-range wireless technology standard.",
        }
    }))
    rc, seen, detail_seen, out = _run_capture(
        tmp_path, monkeypatch, ["--cache", str(cache)])
    assert rc == 0, "strict board with a cache should build"
    assert seen, "the board scored no report -- fixture or threading broke"
    assert all(cp == "strict" for cp in seen), seen
    assert detail_seen and all(d.get("withheld_slots") == 0 for d in detail_seen), \
        detail_seen
