from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_v3_formal_candidate_queue import QueueBuildError, build_queue


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _source(path: Path, ordinal: int, domain: str = "test_domain") -> None:
    _write(
        path / f"dr_cross_deep_{ordinal:04d}.json",
        {
            "task_id": f"dr_cross_deep_{ordinal:04d}",
            "task_version": 2,
            "domain": domain,
            "intent": f"intent {ordinal}",
            "tri_source": {
                "cluster": domain,
                "archetype": "claim-check",
                "angle": f"angle {ordinal}",
            },
        },
    )


def _supplemental(path: Path, count: int = 1) -> None:
    _write(
        path,
        {
            "schema": "dra_v3_supplemental_scenario_seed_pool_v1",
            "seeds": [
                {
                    "source_task_id": f"dra_v3_supplemental_seed_{ordinal:04d}",
                    "domain": "replacement_domain",
                    "cluster": "replacement_cluster",
                    "archetype": "use-case-fit",
                    "angle": f"replacement angle {ordinal}",
                    "intent": f"replacement intent {ordinal}",
                }
                for ordinal in range(1, count + 1)
            ],
        },
    )


def _terminal_rejection(path: Path, source_task_id: str) -> None:
    _write(
        path / "candidate" / "rejection_audit.json",
        {
            "candidate_id": "terminal_candidate",
            "decision": {
                "status": "rejected_pre_capture",
                "formal_release_eligible": False,
                "code": "missing_vital_evidence",
            },
            "identity": {
                "source_task_id": source_task_id,
                "target_task_id": "dra_v3_formal_test_0002",
            },
        },
    )


def _fixture(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "source_dir": tmp_path / "sources",
        "public_dir": tmp_path / "public",
        "authoring_dir": tmp_path / "authoring",
        "capture_plan_dir": tmp_path / "plans",
        "corpus_audit_path": tmp_path / "audit.json",
    }
    for ordinal in range(1, 4):
        _source(paths["source_dir"], ordinal)
    _write(paths["public_dir"] / "dra_v3_dev_test_0001.json", {"task_id": "dra_v3_dev_test_0001"})
    _write(
        paths["authoring_dir"] / "cand_one.case_authoring_source.json",
        {"task_id": "dra_v3_dev_test_0001", "candidate_id": "cand_one"},
    )
    _write(
        paths["capture_plan_dir"] / "cand_one.r1.json",
        {
            "candidate_id": "cand_one",
            "metadata": {"candidate_source_task_id": "dr_cross_deep_0002"},
        },
    )
    _write(
        paths["corpus_audit_path"],
        {
            "candidates": [
                {
                    "candidate_id": "cand_old_rejected",
                    "source_task_id": "dr_cross_deep_0001",
                    "verdict": "rejected",
                }
            ]
        },
    )
    return paths


def test_queue_is_complete_deterministic_and_reaudits_rejections(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    first = build_queue(**paths, target_total=3)
    second = build_queue(**paths, target_total=3)

    assert first == second
    assert first["existing_count"] == 1
    assert first["queued_count"] == 2
    assert first["counted_total"] == 3
    assert first["development_target_count"] == 3
    assert first["formal_target_count"] == 0
    assert first["development_existing_count"] == 1
    assert first["development_queued_count"] == 2
    assert first["formal_existing_count"] == 0
    assert first["formal_queued_count"] == 0
    assert first["existing_tasks"][0]["panel_partition"] == "development"
    assert all(row["panel_partition"] == "development" for row in first["queue"])
    assert [row["ordinal"] for row in first["queue"]] == [2, 3]
    assert [row["source_task_id"] for row in first["queue"]] == [
        "dr_cross_deep_0001",
        "dr_cross_deep_0003",
    ]
    assert first["queue"][0]["prior_corpus_audit_verdict"] == "rejected"
    assert first["queue"][0]["fresh_snapshot_required"] is True
    assert all(row["legacy_v2_mutated"] is False for row in first["queue"])


def test_queue_rejects_duplicate_published_source(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _write(paths["public_dir"] / "dra_v3_dev_test_0002.json", {"task_id": "dra_v3_dev_test_0002"})
    _write(
        paths["authoring_dir"] / "cand_two.case_authoring_source.json",
        {"task_id": "dra_v3_dev_test_0002", "candidate_id": "cand_two"},
    )
    _write(
        paths["capture_plan_dir"] / "cand_two.r1.json",
        {
            "candidate_id": "cand_two",
            "metadata": {"candidate_source_task_id": "dr_cross_deep_0002"},
        },
    )

    with pytest.raises(QueueBuildError, match="reuse the same source task"):
        build_queue(**paths, target_total=3)


def test_queue_requires_enough_eligible_source_seeds(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(QueueBuildError, match="not enough eligible scenario seeds"):
        build_queue(**paths, target_total=4)


def test_terminal_rejection_is_excluded_and_supplemental_seed_fills_target(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    supplemental = tmp_path / "supplemental.json"
    rejection_root = tmp_path / "rejections"
    _supplemental(supplemental)
    _terminal_rejection(rejection_root, "dr_cross_deep_0001")

    result = build_queue(
        **paths,
        target_total=3,
        supplemental_seed_path=supplemental,
        rejection_root=rejection_root,
    )

    assert result["counted_total"] == 3
    assert result["terminal_rejected_count"] == 1
    assert result["terminal_rejections"][0]["source_task_id"] == "dr_cross_deep_0001"
    assert result["reserve_count"] == 0
    assert [row["source_task_id"] for row in result["queue"]] == [
        "dr_cross_deep_0003",
        "dra_v3_supplemental_seed_0001",
    ]
    supplemental_row = result["queue"][1]
    assert supplemental_row["source_kind"] == "v3_supplemental_scenario_seed"
    assert supplemental_row["candidate_id"] == "cand_formal_0003_from_supplemental_0001"
    assert result["source_inventory"] == {
        "legacy_v2_scenario_seed_count": 3,
        "v3_supplemental_scenario_seed_count": 1,
        "eligible_after_terminal_rejections": 3,
    }


def test_terminal_rejection_without_replacement_fails_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    rejection_root = tmp_path / "rejections"
    _terminal_rejection(rejection_root, "dr_cross_deep_0001")

    with pytest.raises(QueueBuildError, match="not enough eligible scenario seeds"):
        build_queue(
            **paths,
            target_total=3,
            rejection_root=rejection_root,
        )


def test_extra_supplemental_seed_is_kept_as_reserve(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    supplemental = tmp_path / "supplemental.json"
    _supplemental(supplemental, count=2)

    result = build_queue(
        **paths,
        target_total=3,
        supplemental_seed_path=supplemental,
    )

    assert result["counted_total"] == 3
    assert result["reserve_count"] == 2
    assert [row["source_task_id"] for row in result["reserve_sources"]] == [
        "dra_v3_supplemental_seed_0001",
        "dra_v3_supplemental_seed_0002",
    ]


def test_supplemental_entry_hash_is_stable_when_pool_gains_a_reserve(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    supplemental = tmp_path / "supplemental.json"
    rejection_root = tmp_path / "rejections"
    _terminal_rejection(rejection_root, "dr_cross_deep_0001")
    _supplemental(supplemental, count=1)
    first = build_queue(
        **paths,
        target_total=3,
        supplemental_seed_path=supplemental,
        rejection_root=rejection_root,
    )

    _supplemental(supplemental, count=2)
    second = build_queue(
        **paths,
        target_total=3,
        supplemental_seed_path=supplemental,
        rejection_root=rejection_root,
    )

    first_row = first["queue"][1]
    second_row = second["queue"][1]
    assert first_row["source_task_sha256"] == second_row["source_task_sha256"]
    assert first_row["source_entry_sha256"] == second_row["source_entry_sha256"]
    assert first_row["source_container_sha256"] != second_row["source_container_sha256"]
    assert first_row["source_hash_basis"] == "canonical_seed_entry"


def test_queue_splits_dev14_from_formal_candidates(tmp_path: Path) -> None:
    paths = {
        "source_dir": tmp_path / "sources",
        "public_dir": tmp_path / "public",
        "authoring_dir": tmp_path / "authoring",
        "capture_plan_dir": tmp_path / "plans",
        "corpus_audit_path": tmp_path / "audit.json",
    }
    for ordinal in range(1, 17):
        _source(paths["source_dir"], ordinal)
    for ordinal in range(1, 16):
        task_id = f"dra_v3_dev_test_{ordinal:04d}"
        candidate_id = f"cand_{ordinal:04d}"
        source_task_id = f"dr_cross_deep_{ordinal:04d}"
        _write(paths["public_dir"] / f"{task_id}.json", {"task_id": task_id})
        _write(
            paths["authoring_dir"] / f"{candidate_id}.case_authoring_source.json",
            {"task_id": task_id, "candidate_id": candidate_id},
        )
        _write(
            paths["capture_plan_dir"] / f"{candidate_id}.r1.json",
            {
                "candidate_id": candidate_id,
                "metadata": {"candidate_source_task_id": source_task_id},
            },
        )
    _write(paths["corpus_audit_path"], {"candidates": []})

    result = build_queue(**paths, target_total=16)

    assert result["development_target_count"] == 14
    assert result["formal_target_count"] == 2
    assert result["development_existing_count"] == 14
    assert result["formal_existing_count"] == 1
    assert result["formal_queued_count"] == 1
    assert result["existing_tasks"][-1]["panel_partition"] == "formal_candidate"
    assert result["queue"][0]["panel_partition"] == "formal_candidate"
