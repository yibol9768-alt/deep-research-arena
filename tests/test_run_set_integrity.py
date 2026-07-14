from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_run_set import (
    IntegrityError,
    assert_formal_environment,
    assert_lane_registry_parity,
    audit_run_set,
    bind_entry,
    is_bound_report_resumable,
    is_entry_resumable,
    read_queue,
    validate_entry,
    validate_manifest,
)


def _write_manifest(path: Path, run_set_id: str, backbone: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "manifest_version": 2,
        "model_identity": [{
            "endpoint": "http://model/v1",
            "declared": backbone,
            "actual": backbone,
            "ok": True,
            "error": None,
        }],
        "env": {"DRA_RUN_SET_ID": run_set_id},
    }))
    return path


def _report_text(marker: str = "same") -> str:
    return "# Governed report\n\n" + (f"Framework-native evidence {marker}. " * 20)


def _write_bound_entry(
    run_set_dir: Path,
    *,
    backbone: str,
    agent: str,
    task: str = "dr_cross_deep_0001",
    replicate: int = 1,
    report_text: str | None = None,
) -> tuple[Path, Path, Path, Path]:
    run_dir = run_set_dir / backbone
    raw = run_dir / "raw"
    scores = run_dir / "scores"
    raw.mkdir(parents=True, exist_ok=True)
    scores.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "run_manifest.json"
    if not manifest.exists():
        _write_manifest(manifest, run_set_dir.name, backbone)
    stem = f"{agent}__{task}_rep{replicate}"
    report = raw / f"{stem}.md"
    meta = raw / f"{stem}.meta.json"
    score = scores / f"{stem}.score.json"
    text = _report_text() if report_text is None else report_text
    report.write_text(text, encoding="utf-8")
    report_bytes = report.read_bytes()
    digest = hashlib.sha256(report_bytes).hexdigest()
    meta.write_text(json.dumps({
        "agent": agent,
        "task": task,
        "backbone": backbone,
        "run_id": f"{agent}-{task}-rep{replicate}",
        "status": "pass",
        "error": None,
        "report_seal": {"sha256": digest, "n_bytes": len(report_bytes)},
        "model_identity": {
            "declared": backbone,
            "actual": backbone,
            "ok": True,
            "error": None,
        },
    }))
    bind_entry(
        report,
        meta,
        manifest,
        run_set_id=run_set_dir.name,
        backbone=backbone,
        replicate=replicate,
        agent=agent,
        task=task,
    )
    score.write_text(json.dumps({
        "task": task,
        "answer_path": str(report.resolve()),
        "report_seal_check": {
            "checked": True,
            "ok": True,
            "actual_sha256": digest,
            "sealed_sha256": digest,
        },
    }))
    return report, meta, score, manifest


def test_lane_registry_parity_rejects_both_directions():
    with pytest.raises(IntegrityError, match="declared_without_runner=.*protocol-only"):
        assert_lane_registry_parity(
            protocol_names={"shared", "protocol-only"},
            runner_names={"shared", "runner-only"},
        )


def test_queue_rejects_unknown_lane_before_execution(tmp_path):
    queue = tmp_path / "queue.tsv"
    queue.write_text("undeclared\tdr_cross_deep_0001\n")
    with pytest.raises(IntegrityError, match="not in the exact"):
        read_queue(queue, valid_lanes={"lane-a"})


@pytest.mark.parametrize("name,value", [
    ("EVIDENCE_FALLBACK_ENABLE", "1"),
    ("EVIDENCE_FALLBACK_ENABLE", "0"),
    ("SMOLAGENTS_FORCE_FALLBACK", "native"),
    ("FORCE_EVIDENCE_FALLBACK_ALL", "true"),
    ("LANGCHAIN_ODR_ENABLE_BENCHMARK_FALLBACK", "yes"),
    ("LANGCHAIN_ODR_BENCHMARK_FALLBACK", ""),
    ("FLOWSEARCHER_MEMORY", "/tmp/report.md"),
])
def test_formal_environment_rejects_fallback_controls_even_when_falseish(name, value):
    with pytest.raises(IntegrityError, match=name):
        assert_formal_environment({name: value})


@pytest.mark.parametrize("name,value", [
    ("SMOLAGENTS_MAX_STEPS", "24"),
    ("SMOLAGENTS_SEARCH_MAX_RESULTS", "0"),
    ("SMOLAGENTS_SEARCH_SNIPPET_CHARS", ""),
    ("SMOLAGENTS_MIN_REPORT_CHARS", "false"),
    ("LDR_SEARCH_MAX_RESULTS", "6"),
    ("LDR_SEARCH_ITERATIONS", ""),
    ("DEERFLOW_TOKEN_LIMIT", "0"),
    ("OPENCODE_CONTEXT_LIMIT", "40960"),
    ("OPENCODE_MAX_OUTPUT_TOKENS", "8192"),
    ("QX_AGENTS_MIN_REPORT_CHARS", "3000"),
    ("LDR_INTENT_MASK", "false"),
    ("LCDR_INTENT_MASK", ""),
    ("DEEPAGENTS_INTENT_MASK", "0"),
    ("DZHNG_BREADTH", "2"),
    ("DZHNG_DEPTH", "2"),
    ("DEEP_RUN_SKIP_SOURCE_CHECK", "0"),
    ("SMOLAGENTS_NATIVE_TIMEOUT_S", "1800"),
    ("OPENCODE_TIMEOUT", "false"),
    ("DRA_WALL_CLOCK_S", ""),
    ("FLOWSEARCHER_PAGES_PER_SUBGOAL", "0"),
    ("FLOWSEARCHER_PER_PAGE_CHARS", "false"),
    ("FLOWSEARCHER_SHIM_URL", ""),
    ("FLOWSEARCHER_LLM_TIMEOUT", "600"),
    ("FLOWSEARCHER_FETCH_TIMEOUT", "12"),
])
def test_formal_environment_rejects_lane_specific_comparative_overrides(name, value):
    with pytest.raises(IntegrityError, match="lane-specific comparative overrides"):
        assert_formal_environment({name: value})


def test_formal_environment_allows_shared_contract_and_no_fallback_guard():
    assert_formal_environment({
        "DRA_STALL_TIMEOUT_S": "900",
        "DRA_EGRESS_ENFORCED": "1",
        "DEEP_RUN_OUT_DIR": "/tmp/raw",
        "CLAUDE_CODE_NO_WINDOWS_FALLBACK": "1",
    })


def test_resume_requires_every_binding_dimension_and_current_report(tmp_path):
    run_set = tmp_path / "rs1"
    report, meta, score, manifest = _write_bound_entry(
        run_set, backbone="model-a", agent="lane-a"
    )
    common = dict(
        run_set_id="rs1",
        backbone="model-a",
        replicate=1,
        agent="lane-a",
        task="dr_cross_deep_0001",
    )
    assert is_entry_resumable(score, meta, report, manifest, **common)
    score.unlink()
    assert is_bound_report_resumable(meta, report, manifest, **common)
    score.write_text("{}")
    assert not is_entry_resumable(
        score, meta, report, manifest, **{**common, "replicate": 2}
    )
    assert not is_entry_resumable(
        score, meta, report, manifest, **{**common, "run_set_id": "other"}
    )

    report.write_text(report.read_text() + "tampered")
    assert not is_entry_resumable(score, meta, report, manifest, **common)
    assert not is_bound_report_resumable(meta, report, manifest, **common)


def test_resume_rejects_manifest_drift_after_binding(tmp_path):
    run_set = tmp_path / "rs1"
    report, meta, score, manifest = _write_bound_entry(
        run_set, backbone="model-a", agent="lane-a"
    )
    data = json.loads(manifest.read_text())
    data["post_hoc_change"] = True
    manifest.write_text(json.dumps(data))
    assert not is_entry_resumable(
        score,
        meta,
        report,
        manifest,
        run_set_id="rs1",
        backbone="model-a",
        replicate=1,
    )


def test_manifest_rejects_current_run_environment_drift(tmp_path):
    manifest = _write_manifest(tmp_path / "run_manifest.json", "rs1", "model-a")
    validate_manifest(
        manifest,
        run_set_id="rs1",
        backbone="model-a",
        current_env={"DRA_RUN_SET_ID": "rs1"},
    )
    with pytest.raises(IntegrityError, match="DRA_EGRESS_PORT"):
        validate_manifest(
            manifest,
            run_set_id="rs1",
            backbone="model-a",
            current_env={"DRA_RUN_SET_ID": "rs1", "DRA_EGRESS_PORT": "18100"},
        )


def test_bind_rejects_stub_and_evidence_writer_signature(tmp_path):
    run_set = tmp_path / "rs1"
    run_dir = run_set / "model-a"
    raw = run_dir / "raw"
    raw.mkdir(parents=True)
    manifest = _write_manifest(run_dir / "run_manifest.json", "rs1", "model-a")
    for name, text in [
        ("stub", "(lane-a error: native: crash)"),
        (
            "fallback",
            "# Report\n\n" + (
                "This source remains relevant because it anchors the answer to a "
                "retrieved local record rather than an unsupported assumption. " * 5
            ),
        ),
    ]:
        report = raw / f"lane-a__dr_cross_deep_0001_{name}.md"
        meta = report.with_suffix(".meta.json")
        report.write_text(text)
        payload = report.read_bytes()
        meta.write_text(json.dumps({
            "agent": "lane-a",
            "task": "dr_cross_deep_0001",
            "backbone": "model-a",
            "status": "pass",
            "error": None,
            "report_seal": {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "n_bytes": len(payload),
            },
            "model_identity": {"ok": True, "declared": "model-a", "actual": "model-a"},
        }))
        with pytest.raises(IntegrityError):
            validate_entry(
                report,
                meta,
                manifest,
                run_set_id="rs1",
                backbone="model-a",
                replicate=1,
                require_binding=False,
            )


def test_bind_rejects_per_run_route_pollution(tmp_path):
    run_set = tmp_path / "rs1"
    report, meta, _, manifest = _write_bound_entry(
        run_set, backbone="model-a", agent="lane-a"
    )
    data = json.loads(meta.read_text())
    data["model_identity"]["actual"] = "model-b"
    meta.write_text(json.dumps(data))
    with pytest.raises(IntegrityError, match="mislabeled"):
        validate_entry(
            report,
            meta,
            manifest,
            run_set_id="rs1",
            backbone="model-a",
            replicate=1,
            require_binding=True,
        )


def test_cross_lane_duplicate_report_is_fatal(tmp_path):
    run_set = tmp_path / "rs1"
    text = _report_text("identical")
    _write_bound_entry(run_set, backbone="model-a", agent="lane-a", report_text=text)
    _write_bound_entry(run_set, backbone="model-a", agent="lane-b", report_text=text)
    result = audit_run_set(run_set, verify_live_manifests=False)
    assert not result["ok"]
    assert len(result["duplicate_contamination"]) == 1
    assert result["max_cross_identity_duplicate_groups"] == 0


def test_cross_backbone_duplicate_report_is_fatal(tmp_path):
    run_set = tmp_path / "rs1"
    text = _report_text("identical")
    _write_bound_entry(run_set, backbone="model-a", agent="lane-a", report_text=text)
    _write_bound_entry(run_set, backbone="model-b", agent="lane-a", report_text=text)
    result = audit_run_set(run_set, verify_live_manifests=False)
    assert not result["ok"]
    assert len(result["duplicate_contamination"]) == 1


def test_same_lane_same_task_replicate_duplicate_is_disclosed_not_hidden(tmp_path):
    run_set = tmp_path / "rs1"
    text = _report_text("deterministic replicate")
    _write_bound_entry(
        run_set, backbone="model-a", agent="lane-a", replicate=1, report_text=text
    )
    _write_bound_entry(
        run_set, backbone="model-a", agent="lane-a", replicate=2, report_text=text
    )
    result = audit_run_set(run_set, verify_live_manifests=False)
    assert result["ok"]
    assert result["duplicate_contamination"] == []
    assert len(result["same_lane_replicate_disclosures"]) == 1


def test_same_lane_duplicate_across_tasks_is_not_a_replicate_exception(tmp_path):
    run_set = tmp_path / "rs1"
    text = _report_text("reused across tasks")
    _write_bound_entry(
        run_set, backbone="model-a", agent="lane-a",
        task="dr_cross_deep_0001", report_text=text,
    )
    _write_bound_entry(
        run_set, backbone="model-a", agent="lane-a",
        task="dr_cross_deep_0002", report_text=text,
    )
    result = audit_run_set(run_set, verify_live_manifests=False)
    assert not result["ok"]
    assert len(result["duplicate_contamination"]) == 1


def test_legacy_unbound_glm_report_cannot_be_published(tmp_path):
    run_set = tmp_path / "glm-history"
    raw = run_set / "glm-4.7" / "raw"
    raw.mkdir(parents=True)
    (raw / "lane-a__dr_cross_deep_0001_rep1.md").write_text(_report_text("legacy"))
    result = audit_run_set(run_set, verify_live_manifests=False)
    assert not result["ok"]
    assert any("legacy/orphan report" in item for item in result["violations"])


def test_publish_audit_rechecks_full_live_manifest_by_default(tmp_path):
    run_set = tmp_path / "rs1"
    _write_bound_entry(run_set, backbone="model-a", agent="lane-a")
    result = audit_run_set(run_set)
    assert not result["ok"]
    assert any("manifest missing required section" in v for v in result["violations"])
