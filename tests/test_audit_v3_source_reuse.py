from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_v3_source_reuse import audit_source_reuse


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _case(
    root: Path,
    *,
    ordinal: int,
    cluster_id: str,
    source_url: str,
    source_type: str,
) -> None:
    task_id = f"dra_v3_test_{ordinal:04d}"
    _write(
        root / f"{task_id}.json",
        {
            "task_id": task_id,
            "task_version": 3,
            "cluster_id": cluster_id,
            "evidence_sources": [
                {
                    "evidence_id": f"ev_{ordinal:04d}",
                    "source_url": source_url,
                    "source_type": source_type,
                }
            ],
        },
    )


def _plan(
    root: Path,
    candidate_id: str,
    source_task_id: str,
    urls: list[str],
    *,
    source_type: str = "wikipedia",
) -> None:
    _write(
        root / f"{candidate_id}.r1.json",
        {
            "candidate_id": candidate_id,
            "metadata": {"candidate_source_task_id": source_task_id},
            "extracts": [
                {"url": url, "source_type": source_type} for url in urls
            ],
        },
    )


def _audit_file(path: Path, *, candidate_id: str = "cand_old") -> None:
    _write(
        path,
        {
            "candidates": [
                {
                    "candidate_id": candidate_id,
                    "source_task_id": "dr_cross_deep_0001",
                    "verdict": "rejected",
                }
            ]
        },
    )


def test_formal_exact_instance_cross_cluster_reuse_fails(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    plans = tmp_path / "plans"
    audit = tmp_path / "audit.json"
    url = "http://localhost:9999/f/test/reused-post"
    _case(cases, ordinal=1, cluster_id="alpha", source_url=url, source_type="postmill")
    _case(cases, ordinal=15, cluster_id="beta", source_url=url, source_type="postmill")
    _plan(plans, "cand_old", "dr_cross_deep_0001", ["http://old"])
    _audit_file(audit)

    result = audit_source_reuse(
        case_dirs=[cases], capture_plan_dir=plans, corpus_audit_path=audit
    )

    assert result["status"] == "failed"
    assert result["conflict_count"] == 1
    assert result["cross_cluster_conflicts"][0]["source_url"] == url


def test_same_cluster_reuse_and_cross_cluster_concept_are_reported_not_failed(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases"
    plans = tmp_path / "plans"
    audit = tmp_path / "audit.json"
    product = "http://localhost:7770/product"
    concept = "http://localhost:8090/content/wiki/Concept"
    _case(cases, ordinal=1, cluster_id="shared", source_url=product, source_type="magento")
    _case(cases, ordinal=15, cluster_id="shared", source_url=product, source_type="magento")
    _case(cases, ordinal=2, cluster_id="one", source_url=concept, source_type="wikipedia")
    _case(cases, ordinal=16, cluster_id="two", source_url=concept, source_type="wikipedia")
    _plan(plans, "cand_old", "dr_cross_deep_0001", ["http://old"])
    _audit_file(audit)

    result = audit_source_reuse(
        case_dirs=[cases], capture_plan_dir=plans, corpus_audit_path=audit
    )

    assert result["status"] == "passed"
    assert len(result["same_cluster_shared_sources"]) == 1
    assert len(result["cross_cluster_warnings"]) == 1
    assert result["conflict_count"] == 0


def test_rejected_candidate_capture_url_replay_fails(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    plans = tmp_path / "plans"
    audit = tmp_path / "audit.json"
    _case(
        cases,
        ordinal=15,
        cluster_id="fresh",
        source_url="http://localhost:7770/fresh",
        source_type="magento",
    )
    _plan(plans, "cand_old", "dr_cross_deep_0001", ["http://shared", "http://old"])
    _plan(plans, "cand_new", "dr_cross_deep_0001", ["http://shared", "http://new"])
    _audit_file(audit)

    result = audit_source_reuse(
        case_dirs=[cases], capture_plan_dir=plans, corpus_audit_path=audit
    )

    assert result["status"] == "failed"
    assert result["rejected_replay_conflicts"] == [
        {
            "source_task_id": "dr_cross_deep_0001",
            "rejected_candidate_id": "cand_old",
            "new_candidate_id": "cand_new",
            "rejected_capture_plans": [(plans / "cand_old.r1.json").as_posix()],
            "new_capture_plans": [(plans / "cand_new.r1.json").as_posix()],
            "overlapping_urls": ["http://shared"],
        }
    ]


def test_missing_rejected_plan_fails_only_when_a_replacement_plan_exists(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases"
    plans = tmp_path / "plans"
    audit = tmp_path / "audit.json"
    _case(
        cases,
        ordinal=15,
        cluster_id="fresh",
        source_url="http://localhost:7770/fresh",
        source_type="magento",
    )
    _audit_file(audit)

    before = audit_source_reuse(
        case_dirs=[cases], capture_plan_dir=plans, corpus_audit_path=audit
    )
    assert before["status"] == "passed"
    assert before["rejected_capture_plan_unavailable"] == [
        {
            "source_task_id": "dr_cross_deep_0001",
            "rejected_candidate_id": "cand_old",
        }
    ]

    _plan(plans, "cand_new", "dr_cross_deep_0001", ["http://new"])
    after = audit_source_reuse(
        case_dirs=[cases], capture_plan_dir=plans, corpus_audit_path=audit
    )
    assert after["status"] == "failed"
    assert after["conflict_count"] == 1
    assert after["rejected_replay_unverifiable"][0]["new_candidate_id"] == "cand_new"


def test_formal_capture_plan_exact_instance_reuse_fails_before_publication(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases"
    plans = tmp_path / "plans"
    audit = tmp_path / "audit.json"
    _case(
        cases,
        ordinal=15,
        cluster_id="fresh",
        source_url="http://localhost:8090/content/wiki/Fresh",
        source_type="wikipedia",
    )
    shared = "http://localhost:7770/shared-product"
    _plan(
        plans,
        "cand_prior",
        "dr_cross_deep_0002",
        [shared],
        source_type="magento",
    )
    _plan(
        plans,
        "cand_formal_0018_from_0003",
        "dr_cross_deep_0003",
        [shared],
        source_type="magento",
    )
    _plan(plans, "cand_old", "dr_cross_deep_0001", ["http://old"])
    _audit_file(audit)

    result = audit_source_reuse(
        case_dirs=[cases], capture_plan_dir=plans, corpus_audit_path=audit
    )

    assert result["status"] == "failed"
    assert result["formal_capture_plan_count"] == 1
    assert result["capture_plan_exact_instance_conflicts"][0]["source_url"] == shared


def test_postmill_slug_variants_are_the_same_capture_instance(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    plans = tmp_path / "plans"
    audit = tmp_path / "audit.json"
    _case(
        cases,
        ordinal=15,
        cluster_id="fresh",
        source_url="http://localhost:8090/content/wiki/Fresh",
        source_type="wikipedia",
    )
    old_url = "http://localhost:9999/f/headphones/12345/old-title"
    new_url = "http://localhost:9999/f/other/12345"
    _plan(
        plans,
        "cand_prior",
        "dr_cross_deep_0002",
        [old_url],
        source_type="postmill",
    )
    _plan(
        plans,
        "cand_formal_0018_from_0003",
        "dr_cross_deep_0003",
        [new_url],
        source_type="postmill",
    )
    _plan(plans, "cand_old", "dr_cross_deep_0001", ["http://old"])
    _audit_file(audit)

    result = audit_source_reuse(
        case_dirs=[cases], capture_plan_dir=plans, corpus_audit_path=audit
    )

    assert result["status"] == "failed"
    conflict = result["capture_plan_exact_instance_conflicts"][0]
    assert conflict["source_identity"].endswith("/submission/12345")
    assert conflict["source_urls"] == [old_url, new_url]
