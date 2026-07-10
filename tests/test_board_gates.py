"""The board must refuse what it cannot vouch for.

Three guards existed on paper and fired never:

1. The stall-rerun policy (`--max-stall-reruns`, rc=4) read the sidecar from a
   nested `<agent>/<task>.meta.json` that nothing ever wrote. `run_deep_task`
   writes it FLAT. So a watchdog kill -- an infrastructure fault -- was scored as
   a framework that delivered nothing, and the whole rerun policy was dead code.

2. `source_check` is stamped into every run's meta, and no board read it. A run
   whose sources were never proved reachable pooled with verified ones.

3. `run_manifest.verify()` says in its docstring "the scorer calls this and
   refuses". No scorer called it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_truth_board import _run_status  # noqa: E402


def _write(p: pathlib.Path, obj) -> None:
    if p.name.endswith(".meta.json") and isinstance(obj, dict) and obj.get("run_id"):
        backbone = obj.setdefault("backbone", "qwen3-8b")
        obj.setdefault("agent", p.name.split("__", 1)[0])
        if "__" in p.name:
            tail = p.name.split("__", 1)[1]
            obj.setdefault("task", tail.split("_matrix.meta.json", 1)[0])
        obj.setdefault("model_identity", {
            "ok": True, "declared": backbone, "actual": backbone,
            "endpoint": "http://127.0.0.1:8088/v1",
        })
        obj.setdefault("timeout_contract", {"production_comparable": True})
        obj.setdefault("source_check", {"state": "ok", "sample_in_corpus": True})
        if isinstance(obj.get("source_check"), dict):
            obj["source_check"].setdefault("sample_in_corpus", True)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _seal(text: str) -> dict:
    raw = text.encode("utf-8")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "n_bytes": len(raw)}


def test_stall_sidecar_is_found_at_the_path_the_harness_actually_writes(tmp_path):
    reports = tmp_path / "reports"
    (reports / "storm").mkdir(parents=True)
    meta = tmp_path / "deep"
    # exactly run_deep_task.py:2227 -> <agent>__<task><suffix>.meta.json
    _write(meta / "storm__dr_cross_deep_0001_matrix.meta.json",
           {"status": "stalled", "attempts": 1})

    assert _run_status(reports / "storm", "dr_cross_deep_0001") == {}, \
        "nested lookup alone is the dead-code path"
    st = _run_status(reports / "storm", "dr_cross_deep_0001", meta)
    assert st["status"] == "stalled" and st["attempts"] == 1


def test_flat_sidecar_beside_the_reports_tree_is_found(tmp_path):
    reports = tmp_path / "reports"
    (reports / "ldr").mkdir(parents=True)
    _write(reports / "ldr__t7_matrix.meta.json", {"status": "stalled", "attempts": 3})
    assert _run_status(reports / "ldr", "t7")["attempts"] == 3


def test_nested_sidecar_still_wins(tmp_path):
    reports = tmp_path / "reports"
    (reports / "ldr").mkdir(parents=True)
    _write(reports / "ldr" / "t7.meta.json", {"status": "ok", "attempts": 9})
    _write(reports / "ldr__t7_matrix.meta.json", {"status": "stalled", "attempts": 1})
    assert _run_status(reports / "ldr", "t7")["status"] == "ok"


def _run_board(args, cwd=ROOT):
    args = list(args)
    if "--reports-dir" in args and "--legacy-nested-layout" not in args:
        args.append("--legacy-nested-layout")
    # These gate tests build without a page cache; run them in diagnostic mode
    # so the SPEC_DECISIONS #2 fail-closed cache gate does not preempt the gate
    # each test is actually exercising. The fail-closed gate itself is pinned by
    # tests/test_truth_board_cache_policy.py.
    if "--diagnostic" not in args and "--no-diagnostic" not in args:
        args.append("--diagnostic")
    return subprocess.run([sys.executable, "scripts/build_truth_board.py", *args],
                          cwd=cwd, capture_output=True, text=True, timeout=180)


def test_board_refuses_a_report_set_with_no_manifest(tmp_path):
    reports = tmp_path / "reports"
    (reports / "storm").mkdir(parents=True)
    (reports / "storm" / "t1.md").write_text("report")
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-report-seals"])
    assert r.returncode == 7, r.stderr[-400:]
    assert "no run manifest" in r.stderr


def test_the_manifest_gate_can_be_waived_for_legacy_report_sets(tmp_path):
    reports = tmp_path / "reports"
    (reports / "storm").mkdir(parents=True)
    (reports / "storm" / "t1.md").write_text("report")
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-report-seals"])
    assert r.returncode != 7, r.stderr[-300:]


def test_board_refuses_reports_whose_corpus_was_never_verified(tmp_path):
    """`DEEP_RUN_SKIP_SOURCE_CHECK=1` is the documented way to bring a box up.

    A run made that way was pooled with verified runs on the published board,
    and nothing downstream could tell them apart.
    """
    tid = "dr_cross_deep_0001"     # a real answer key, so the lane is scorable
    reports = tmp_path / "reports"
    (reports / "storm").mkdir(parents=True)
    (reports / "storm" / f"{tid}.md").write_text(
        "Bluetooth headphones use a loudspeaker driver. "
        "See [page](http://localhost:8090/wiki/Bluetooth).")
    _write(tmp_path / f"storm__{tid}_matrix.meta.json",
           {"status": "ok", "source_check": {"state": "skipped_by_env"}})

    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-report-seals"])
    assert r.returncode == 6, (r.returncode, r.stderr[-400:])
    assert "skipped_by_env" in r.stderr


def test_the_corpus_gate_can_be_waived_for_pre_gate_report_sets(tmp_path):
    tid = "dr_cross_deep_0001"
    reports = tmp_path / "reports"
    (reports / "storm").mkdir(parents=True)
    (reports / "storm" / f"{tid}.md").write_text(
        "Bluetooth headphones. [p](http://localhost:8090/wiki/Bluetooth)")
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-verified-corpus",
                    "--no-require-report-seals"])
    assert r.returncode != 6, r.stderr[-300:]


def _report_fixture(tmp_path, lane="storm", tid="dr_cross_deep_0001"):
    text = (
        "# Findings\n\nBluetooth headphones use a loudspeaker driver and wireless "
        "radio. [Source](http://localhost:8090/wiki/Bluetooth)\n")
    reports = tmp_path / "reports"
    (reports / lane).mkdir(parents=True, exist_ok=True)
    rp = reports / lane / f"{tid}.md"
    rp.write_text(text)
    return reports, rp, text


def test_current_run_missing_report_seal_is_refused(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, _ = _report_fixture(tmp_path, tid=tid)
    _write(tmp_path / f"storm__{tid}_matrix.meta.json", {
        "run_id": "new-run", "status": "pass", "source_check": {"state": "ok"},
    })
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-transport-pof"])
    assert r.returncode == 9
    assert "report seal missing" in r.stderr


def test_present_report_seal_mismatch_cannot_be_waived(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, _ = _report_fixture(tmp_path, tid=tid)
    _write(tmp_path / f"storm__{tid}_matrix.meta.json", {
        "run_id": "new-run", "status": "pass", "source_check": {"state": "ok"},
        "report_seal": {"sha256": "0" * 64, "n_bytes": 1},
    })
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-transport-pof",
                    "--no-require-report-seals"])
    assert r.returncode == 9
    assert "seal mismatch" in r.stderr


def test_old_report_is_not_scored_against_new_stalled_meta(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, text = _report_fixture(tmp_path, tid=tid)
    _write(tmp_path / f"storm__{tid}_matrix.meta.json", {
        "run_id": "new-stalled", "status": "stalled", "attempts": 1,
        "source_check": {"state": "ok"}, "report_seal": _seal(text),
    })
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-transport-pof"])
    assert r.returncode == 9
    assert "stale report" in r.stderr


def test_same_nonstub_report_across_lanes_is_refused(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, text = _report_fixture(tmp_path, lane="storm", tid=tid)
    (reports / "camel-ai").mkdir()
    (reports / "camel-ai" / f"{tid}.md").write_text(text)
    for lane in ("storm", "camel-ai"):
        _write(tmp_path / f"{lane}__{tid}_matrix.meta.json", {
            "run_id": f"{lane}-run", "status": "pass",
            "source_check": {"state": "ok"}, "report_seal": _seal(text),
        })
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-transport-pof"])
    assert r.returncode == 9
    assert "identical non-stub report" in r.stderr


def test_run_id_never_falls_back_to_another_attempts_evidence(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, text = _report_fixture(tmp_path, tid=tid)
    _write(tmp_path / f"storm__{tid}_matrix.meta.json", {
        "run_id": "wanted-run", "status": "pass",
        "source_check": {"state": "ok"}, "report_seal": _seal(text),
    })
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    records = [
        {"ts": 1.0, "run_id": "other-run", "lane": "storm", "task": tid,
         "worker": "w0", "kind": "mark", "phase": "start"},
        {"ts": 2.0, "run_id": "other-run", "lane": "storm", "task": tid,
         "worker": "w0", "kind": "fetch",
         "url": "http://localhost:8090/wiki/Bluetooth", "status": 200},
        {"ts": 3.0, "run_id": "other-run", "lane": "storm", "task": tid,
         "worker": "w0", "kind": "mark", "phase": "end"},
    ]
    (evidence / "other-run.jsonl").write_text(
        "\n".join(json.dumps(x) for x in records) + "\n")
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--evidence-dir", str(evidence), "--no-require-manifest"])
    assert r.returncode == 5, (r.returncode, r.stderr[-500:])
    assert "no lane could be scored" in r.stderr


def test_aggregate_fields_publish_surviving_and_zero_padded_denominators(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, text = _report_fixture(tmp_path, tid=tid)
    _write(tmp_path / f"storm__{tid}_matrix.meta.json", {
        "run_id": "run", "status": "pass", "source_check": {"state": "ok"},
        "report_seal": _seal(text),
    })
    out = tmp_path / "board.json"
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--out", str(out), "--no-require-manifest",
                    "--no-require-transport-pof"])
    assert r.returncode == 0, r.stderr[-500:]
    row = json.loads(out.read_text())["rows"][0]
    assert row["min_report_truth"] == 0.0
    assert row["axes_denominator_surviving"] == 1
    assert row["axes_denominator_all_tasks"] > 1
    assert row["axes_mean"] == row["axes_mean_all_tasks_zero_padded"]
    assert row["compliance"] == row["compliance_all_tasks_zero_padded"]
    assert "axes_mean_surviving" in row and "compliance_surviving" in row


def test_current_report_requires_exact_model_identity(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, text = _report_fixture(tmp_path, tid=tid)
    _write(tmp_path / f"storm__{tid}_matrix.meta.json", {
        "run_id": "wrong-model", "status": "pass",
        "source_check": {"state": "ok", "sample_in_corpus": True},
        "report_seal": _seal(text),
        "model_identity": {
            "ok": True, "declared": "qwen3-8b", "actual": "glm-4.7-flash",
            "endpoint": "http://127.0.0.1:8088/v1",
        },
    })
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-transport-pof"])
    assert r.returncode == 9
    assert "invalid per-run model identity" in r.stderr


def test_timeout_override_report_is_not_production_comparable(tmp_path):
    tid = "dr_cross_deep_0001"
    reports, _, text = _report_fixture(tmp_path, tid=tid)
    _write(tmp_path / f"storm__{tid}_matrix.meta.json", {
        "run_id": "timed", "status": "pass", "report_seal": _seal(text),
        "timeout_contract": {
            "production_comparable": False,
            "operator_overrides": ["DRA_WALL_CLOCK_S"],
        },
    })
    r = _run_board(["--reports-dir", str(reports), "--meta-dir", str(tmp_path),
                    "--no-require-manifest", "--no-require-transport-pof"])
    assert r.returncode == 9
    assert "not production-comparable" in r.stderr
