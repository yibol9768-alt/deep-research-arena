"""Fail-closed page-cache policy for the truth board (SPEC_DECISIONS #2).

A formal (headline) board is REFUSED when no sandbox page cache is supplied,
because the concept-quote and forum-coverage completeness slots then have no
page text to ground against and score 0 for every lane -- an instrument-caused
zero, exactly the failure mode the board contract forbids. `--diagnostic` opts
into a non-headline build that is stamped ``cache_policy="diagnostic"`` and
threads that policy to the scorer, which withholds the ungroundable slots from
the completeness denominator instead of silently scoring them 0.

On the pre-decision code these assertions go red: the ``--diagnostic`` flag did
not exist and a cache-less build produced a normal (rc=0) board.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BUILD = "scripts/build_truth_board.py"
TID = "dr_cross_deep_0001"


def _report_fixture(tmp_path, lane="storm", tid=TID):
    text = (
        "# Findings\n\nBluetooth headphones use a loudspeaker driver and wireless "
        "radio. [Source](http://localhost:8090/wiki/Bluetooth)\n")
    reports = tmp_path / "reports"
    (reports / lane).mkdir(parents=True, exist_ok=True)
    (reports / lane / f"{tid}.md").write_text(text)
    return reports


def _run(reports, tmp_path, extra):
    cmd = [
        sys.executable, BUILD,
        "--reports-dir", str(reports), "--legacy-nested-layout",
        "--meta-dir", str(tmp_path),
        "--no-require-manifest", "--no-require-transport-pof",
        "--no-require-report-seals", "--no-require-verified-corpus",
        *extra,
    ]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          timeout=180)


def test_strict_board_refuses_when_no_cache(tmp_path):
    reports = _report_fixture(tmp_path)
    out = tmp_path / "board.json"
    r = _run(reports, tmp_path, ["--out", str(out)])
    assert r.returncode == 11, (r.returncode, r.stderr[-500:])
    assert "no page cache" in r.stderr
    assert not out.exists(), "a refused board must not be written"


def test_diagnostic_flag_lets_a_cacheless_board_build(tmp_path):
    reports = _report_fixture(tmp_path)
    out = tmp_path / "board.json"
    r = _run(reports, tmp_path, ["--out", str(out), "--diagnostic"])
    assert r.returncode == 0, r.stderr[-500:]
    board = json.loads(out.read_text())
    assert board["cache_policy"] == "diagnostic"
    assert board["protocols"]["cache_policy"] == "diagnostic"


def test_strict_board_builds_with_a_nonempty_cache(tmp_path):
    reports = _report_fixture(tmp_path)
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({
        "http://localhost:8090/wiki/Bluetooth": {
            "status": 200,
            "text": "Bluetooth is a short-range wireless technology standard.",
        }
    }))
    out = tmp_path / "board.json"
    r = _run(reports, tmp_path, ["--out", str(out), "--cache", str(cache)])
    assert r.returncode == 0, r.stderr[-500:]
    board = json.loads(out.read_text())
    assert board["cache_policy"] == "strict"
    assert board["protocols"]["cache_policy"] == "strict"


def test_empty_cache_file_is_treated_as_no_cache(tmp_path):
    reports = _report_fixture(tmp_path)
    cache = tmp_path / "empty.json"
    cache.write_text("{}")
    r = _run(reports, tmp_path, ["--cache", str(cache)])
    assert r.returncode == 11, (r.returncode, r.stderr[-500:])
