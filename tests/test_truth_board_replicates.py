from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_truth_board import (  # noqa: E402
    FORMULA_VERSION,
    _cluster_bootstrap_ci,
    _discover_formal_cells,
    _index_evidence,
    _protocols,
)
from scripts.verify_run_set import (  # noqa: E402
    IntegrityError,
    bind_entry,
    bind_outcome,
    create_run_plan,
    validate_run_plan,
    validate_outcome,
)
from src.eval.fetch_log import linked_urls  # noqa: E402


TASK = "dr_cross_deep_0001"
BACKBONE = "model-a"


def test_formula_stamp_discloses_forum_and_local_attribution_semantics():
    assert FORMULA_VERSION == "tv2.4-provenance-gate-factscope-forum-attribution"
    protocol = _protocols(1.5, [TASK], "transport_v2", "provenance_v2")
    assert "forum" in protocol["sources_scored"]["completeness"]
    assert "same Markdown line" in protocol["sources_note"]
    assert "same sentence or table row" in protocol["sources_note"]


def _manifest(run_dir: Path) -> Path:
    path = run_dir / "run_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "manifest_version": 2,
        "model_identity": [{
            "endpoint": "http://model/v1",
            "declared": BACKBONE,
            "actual": BACKBONE,
            "ok": True,
            "error": None,
        }],
        "env": {"DRA_RUN_SET_ID": run_dir.parent.name},
    }), encoding="utf-8")
    return path


def _report_text(marker: str) -> str:
    body = (
        "Bluetooth headphones use wireless radio and a loudspeaker driver. "
        f"The retrieved evidence is summarized for comparison {marker}. "
    ) * 20
    return (
        "# Findings\n\n" + body
        + "[Source](http://localhost:8090/wiki/Bluetooth)\n"
    )


def _pass(
    run_dir: Path,
    *,
    agent: str,
    replicate: int,
    filename: str,
    marker: str = "measured",
    report_filename: str | None = None,
) -> None:
    raw = run_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    report = raw / (report_filename or f"{filename}.md")
    meta_path = raw / f"{filename}.meta.json"
    text = _report_text(marker)
    report.write_text(text, encoding="utf-8")
    payload = report.read_bytes()
    meta_path.write_text(json.dumps({
        "agent": agent,
        "task": TASK,
        "backbone": BACKBONE,
        "run_id": f"{agent}-{replicate}",
        "status": "pass",
        "error": None,
        "report_seal": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "n_bytes": len(payload),
        },
        "model_identity": {
            "endpoint": "http://model/v1",
            "declared": BACKBONE,
            "actual": BACKBONE,
            "ok": True,
        },
        "timeout_contract": {"production_comparable": True},
        "source_check": {"state": "ok", "sample_in_corpus": True},
    }), encoding="utf-8")
    bind_entry(
        report,
        meta_path,
        _manifest(run_dir),
        run_set_id=run_dir.parent.name,
        backbone=BACKBONE,
        replicate=replicate,
        agent=agent,
        task=TASK,
    )


def _outcome(
    run_dir: Path,
    *,
    agent: str,
    replicate: int,
    status: str,
    filename: str,
) -> None:
    raw = run_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / f"{filename}.meta.json"
    path.write_text(json.dumps({
        "agent": agent,
        "task": TASK,
        "backbone": BACKBONE,
        "status": status,
        "error": status,
        "attempts": 2,
    }), encoding="utf-8")
    bind_outcome(
        path,
        _manifest(run_dir),
        run_set_id=run_dir.parent.name,
        backbone=BACKBONE,
        replicate=replicate,
        agent=agent,
        task=TASK,
    )


def _ensure_full_plan(
    run_dir: Path, *, replicates: int, agents: tuple[str, ...] = ("storm",)
) -> None:
    plan = run_dir / "run_plan.json"
    if not plan.exists():
        tasks = sorted(
            path.stem for path in (ROOT / "data/golden/answer_keys").glob("*.json")
        )
        create_run_plan(
            plan,
            run_set_id=run_dir.parent.name,
            backbone=BACKBONE,
            replicates=replicates,
            pairs=[(agent, task) for agent in agents for task in tasks],
            manifest_path=_manifest(run_dir),
        )


def _run_board(
    run_dir: Path,
    out: Path,
    *,
    replicates: int,
    keys_dir: Path | None = None,
) -> subprocess.CompletedProcess:
    assert (run_dir / "run_plan.json").is_file()
    command = [
        sys.executable,
        "scripts/build_truth_board.py",
        "--run-dir", str(run_dir),
        "--replicates", str(replicates),
        "--bootstrap-samples", "200",
        "--out", str(out),
        "--no-require-manifest",
        "--no-require-transport-pof",
        # No page cache is supplied here; build in diagnostic mode so the
        # SPEC_DECISIONS #2 fail-closed cache gate does not refuse these
        # aggregation/replicate tests. The gate is pinned separately in
        # tests/test_truth_board_cache_policy.py.
        "--diagnostic",
    ]
    if keys_dir is not None:
        command.extend(["--keys-dir", str(keys_dir)])
    return subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=180
    )


def test_run_plan_is_atomic_immutable_and_manifest_sealed(tmp_path):
    run_dir = tmp_path / "rs" / BACKBONE
    manifest = _manifest(run_dir)
    plan = run_dir / "run_plan.json"
    pairs = [("storm", "t1"), ("storm", "t2")]
    create_run_plan(
        plan,
        run_set_id="rs",
        backbone=BACKBONE,
        replicates=3,
        pairs=pairs,
        manifest_path=manifest,
    )
    validate_run_plan(
        plan,
        run_set_id="rs",
        backbone=BACKBONE,
        replicates=3,
        manifest_path=manifest,
        queue_pairs=[("storm", "t2")],
    )
    with pytest.raises(IntegrityError, match="already exists"):
        create_run_plan(
            plan,
            run_set_id="rs",
            backbone=BACKBONE,
            replicates=3,
            pairs=pairs,
            manifest_path=manifest,
        )
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(IntegrityError, match="manifest seal mismatch"):
        validate_run_plan(
            plan,
            run_set_id="rs",
            backbone=BACKBONE,
            replicates=3,
            manifest_path=manifest,
        )


def test_run_plan_rejects_non_cross_product_and_resume_outside_plan(tmp_path):
    run_dir = tmp_path / "rs" / BACKBONE
    manifest = _manifest(run_dir)
    with pytest.raises(IntegrityError, match="complete agents x tasks"):
        create_run_plan(
            run_dir / "bad.json",
            run_set_id="rs",
            backbone=BACKBONE,
            replicates=1,
            pairs=[("storm", "t1"), ("camel-ai", "t2")],
            manifest_path=manifest,
        )
    plan = run_dir / "run_plan.json"
    create_run_plan(
        plan,
        run_set_id="rs",
        backbone=BACKBONE,
        replicates=1,
        pairs=[("storm", "t1")],
        manifest_path=manifest,
    )
    with pytest.raises(IntegrityError, match="outside immutable run plan"):
        validate_run_plan(
            plan,
            run_set_id="rs",
            backbone=BACKBONE,
            replicates=1,
            manifest_path=manifest,
            queue_pairs=[("storm", "t2")],
        )


def test_legacy_layout_requires_explicit_opt_out_and_cannot_mix(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    no_opt_out = subprocess.run([
        sys.executable, "scripts/build_truth_board.py",
        "--reports-dir", str(reports),
    ], cwd=ROOT, capture_output=True, text=True)
    assert no_opt_out.returncode == 2
    assert "requires --legacy-nested-layout" in no_opt_out.stderr

    mixed = subprocess.run([
        sys.executable, "scripts/build_truth_board.py",
        "--run-dir", str(tmp_path / "rs" / BACKBONE),
        "--reports-dir", str(reports),
        "--replicates", "1",
    ], cwd=ROOT, capture_output=True, text=True)
    assert mixed.returncode == 2


def test_outcome_binding_is_strict_and_can_record_outer_timeout(tmp_path):
    run_dir = tmp_path / "rs" / BACKBONE
    meta = run_dir / "raw" / "opaque.meta.json"
    binding = bind_outcome(
        meta,
        _manifest(run_dir),
        run_set_id="rs",
        backbone=BACKBONE,
        replicate=2,
        agent="storm",
        task=TASK,
        status="timeout",
        error="outer timeout rc=124",
    )
    assert binding["replicate"] == 2
    assert binding["agent"] == "storm"
    validate_outcome(
        meta,
        _manifest(run_dir),
        run_set_id="rs",
        backbone=BACKBONE,
        replicate=2,
        agent="storm",
        task=TASK,
        require_binding=True,
    )
    doc = json.loads(meta.read_text())
    doc["agent"] = "camel-ai"
    meta.write_text(json.dumps(doc))
    with pytest.raises(IntegrityError, match="outcome metadata mismatch"):
        validate_outcome(
            meta,
            _manifest(run_dir),
            run_set_id="rs",
            backbone=BACKBONE,
            replicate=2,
            agent="storm",
            task=TASK,
            require_binding=True,
        )


def test_formal_discovery_uses_binding_not_filename_and_rejects_tampering(tmp_path):
    run_dir = tmp_path / "rs" / BACKBONE
    _pass(
        run_dir,
        agent="storm",
        replicate=1,
        filename="not-an-identity",
        report_filename="payload-with-another-name.md",
    )
    cells, _ = _discover_formal_cells(run_dir, replicates=2)
    assert set(cells) == {("storm", TASK, 1)}

    meta = run_dir / "raw" / "not-an-identity.meta.json"
    doc = json.loads(meta.read_text())
    doc["run_set_binding"]["replicate"] = 2
    meta.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="binding mismatch|run-set identity mismatch"):
        _discover_formal_cells(run_dir, replicates=2)


def test_bound_entry_detects_run_plan_rewrite(tmp_path):
    run_dir = tmp_path / "rs" / BACKBONE
    _ensure_full_plan(run_dir, replicates=1)
    _pass(run_dir, agent="storm", replicate=1, filename="opaque")
    plan = run_dir / "run_plan.json"
    plan.write_text(plan.read_text() + "\n")
    with pytest.raises(ValueError, match="run_plan_sha256"):
        _discover_formal_cells(run_dir, replicates=1)


def test_formal_discovery_rejects_run_id_reuse_across_replicates(tmp_path):
    run_dir = tmp_path / "rs" / BACKBONE
    _pass(run_dir, agent="storm", replicate=1, filename="one", marker="one")
    _pass(run_dir, agent="storm", replicate=2, filename="two", marker="two")
    second = run_dir / "raw" / "two.meta.json"
    doc = json.loads(second.read_text())
    doc["run_id"] = "storm-1"
    doc["run_set_binding"]["run_id"] = "storm-1"
    second.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="bound to multiple"):
        _discover_formal_cells(run_dir, replicates=2)


def test_board_zero_pads_all_task_replicates_and_publishes_outcomes(tmp_path):
    run_dir = tmp_path / "rs" / BACKBONE
    _ensure_full_plan(run_dir, replicates=5)
    _pass(run_dir, agent="storm", replicate=1, filename="z-last")
    _outcome(run_dir, agent="storm", replicate=2, status="fail", filename="a-first")
    _outcome(run_dir, agent="storm", replicate=3, status="stalled", filename="m-mid")
    _outcome(run_dir, agent="storm", replicate=4, status="infra_abort", filename="b")
    _outcome(run_dir, agent="storm", replicate=5, status="timeout", filename="y")
    out = tmp_path / "board.json"
    result = _run_board(run_dir, out, replicates=5)
    assert result.returncode == 0, result.stderr[-1000:]
    board = json.loads(out.read_text())
    assert board["protocols"]["formula_version"] == (
        "tv2.4-provenance-gate-factscope-forum-attribution"
    )
    assert "forum" in board["protocols"]["sources_scored"]["completeness"]
    row = board["rows"][0]
    assert row["n_task_replicates_expected"] == board["n_answer_keys"] * 5
    assert row["run_outcomes"]["counts"] == {
        "pass": 1,
        "fail": 1,
        "stalled": 1,
        "infra_abort": 1,
        "timeout": 1,
        "missing": board["n_answer_keys"] * 5 - 5,
    }
    assert row["pass_rate"] == pytest.approx(1 / (board["n_answer_keys"] * 5), 1e-5)
    assert row["min_report_truth"] == 0.0
    assert row["axes_denominator_all_tasks"] == board["n_answer_keys"] * 5
    assert row["compliance_denominator_all_tasks"] == board["n_answer_keys"] * 5
    assert row["truth_macro_ci95"]["cluster"] == "task"
    assert row["truth_macro_ci95"]["replicates_within_cluster"] == 5
    assert set(board["per_task"]["storm"][TASK]["replicates"]) == {
        "1", "2", "3", "4", "5"
    }


def test_bootstrap_is_invariant_to_task_and_replicate_order_and_agent_name():
    values_a = {"t2": [0.9, 0.1], "t1": [0.2, 0.4], "t3": [0.0, 0.3]}
    values_b = {"t3": [0.3, 0.0], "t1": [0.4, 0.2], "t2": [0.1, 0.9]}
    # Agent name is deliberately not an input to the sampling seed.
    storm = _cluster_bootstrap_ci(values_a, samples=1000, seed=99)
    renamed_lane = _cluster_bootstrap_ci(values_b, samples=1000, seed=99)
    assert storm == renamed_lane


def test_board_numbers_ignore_agent_filename_and_replicate_order(tmp_path):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    source_key = ROOT / "data/golden/answer_keys" / f"{TASK}.json"
    (keys_dir / source_key.name).write_bytes(source_key.read_bytes())

    def build_variant(run_set: str, agent: str, pass_rep: int, pass_name: str):
        run_dir = tmp_path / run_set / BACKBONE
        create_run_plan(
            run_dir / "run_plan.json",
            run_set_id=run_set,
            backbone=BACKBONE,
            replicates=2,
            pairs=[(agent, TASK)],
            manifest_path=_manifest(run_dir),
        )
        _pass(
            run_dir,
            agent=agent,
            replicate=pass_rep,
            filename=pass_name,
            marker="same-content",
        )
        _outcome(
            run_dir,
            agent=agent,
            replicate=3 - pass_rep,
            status="fail",
            filename="a-first" if pass_name == "z-last" else "z-last",
        )
        out = tmp_path / f"{run_set}.json"
        result = _run_board(
            run_dir, out, replicates=2, keys_dir=keys_dir
        )
        assert result.returncode == 0, result.stderr[-1000:]
        return json.loads(out.read_text())["rows"][0]

    first = build_variant("rs-a", "storm", 1, "z-last")
    renamed_reordered = build_variant("rs-b", "camel-ai", 2, "a-first")
    invariant_fields = (
        "truth_macro", "truth_macro_ci95", "truth_micro",
        "min_report_truth", "min_report_truth_surviving", "axes_mean",
        "compliance", "coverage", "run_outcomes", "rank",
    )
    assert {key: first[key] for key in invariant_fields} == {
        key: renamed_reordered[key] for key in invariant_fields
    }


def _write_evidence(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _mark(ts: float, phase: str, *, worker: str = "0") -> dict:
    return {
        "ts": ts,
        "kind": "mark",
        "phase": phase,
        "run_id": "run-1",
        "lane": "storm",
        "task": TASK,
        "backbone": BACKBONE,
        "worker": worker,
        "fetch_observable": True,
    }


def test_evidence_roots_merge_by_run_id_with_sticky_success_and_links(tmp_path):
    shim = tmp_path / "evidence" / "worker-0" / "run-1.jsonl"
    egress = tmp_path / "evidence" / "egress-worker-0" / "run-1.jsonl"
    url = "http://localhost:8090/wiki/Bluetooth"
    linked = "http://localhost:8090/wiki/Wireless"
    _write_evidence(shim, [
        _mark(1.0, "start"),
        {**_mark(2.0, "noop"), "kind": "search", "urls_returned": [url]},
        {**_mark(3.0, "noop"), "kind": "fetch", "url": url, "status": 503},
        _mark(4.0, "end"),
    ])
    _write_evidence(egress, [
        _mark(1.1, "start"),
        {**_mark(2.5, "noop"), "kind": "fetch", "url": url, "status": 200,
         "links": [linked]},
        _mark(3.5, "end"),
    ])
    _, by_run = _index_evidence([tmp_path / "evidence"])
    ev = by_run["run-1"]
    assert ev.available
    assert url in ev.fetched_ok
    assert url in ev.search_returned
    assert linked in linked_urls(ev)


def test_one_invalid_evidence_fragment_poison_merges_fail_closed(tmp_path):
    root = tmp_path / "evidence"
    _write_evidence(root / "worker-0" / "run-1.jsonl", [
        _mark(1.0, "start"), _mark(2.0, "end"),
    ])
    _write_evidence(root / "egress-worker-0" / "run-1.jsonl", [
        _mark(1.1, "start"),
    ])
    _, by_run = _index_evidence([root])
    assert not by_run["run-1"].available
    assert "missing end mark" in by_run["run-1"].unavailable_reason


def test_evidence_same_run_id_from_different_workers_is_never_pooled(tmp_path):
    root = tmp_path / "evidence"
    _write_evidence(root / "worker-0" / "run-1.jsonl", [
        _mark(1.0, "start", worker="0"), _mark(2.0, "end", worker="0"),
    ])
    _write_evidence(root / "worker-1" / "run-1.jsonl", [
        _mark(1.0, "start", worker="1"), _mark(2.0, "end", worker="1"),
    ])
    _, by_run = _index_evidence([root])
    assert not by_run["run-1"].available
    assert "disagree on worker" in by_run["run-1"].unavailable_reason
