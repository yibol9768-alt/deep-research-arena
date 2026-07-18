from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from scripts.import_route_a_annotator_b_yaml import import_annotations


ATTACHMENTS = Path(
    "/root/.codex/attachments/2abc0b95-49ed-4375-93cd-13abb57b40f6"
)


def test_annotator_b_import_preserves_originals_and_normalizes_yaml(tmp_path) -> None:
    output = tmp_path / "B"
    manifest = import_annotations(ATTACHMENTS, output)

    assert manifest["task_count"] == 14
    assert manifest["requirement_count"] == 53
    assert manifest["original_yaml_valid_count"] == 1
    assert manifest["normalized_yaml_valid_count"] == 14
    assert manifest["schema_valid_count"] == 14
    assert manifest["unresolved_total"] == 0
    assert manifest["independence_attestation"] == "not_provided"
    assert manifest["formal_calibration_eligible"] is False

    for row in manifest["tasks"]:
        source = ATTACHMENTS / row["source_filename"]
        archived = output / "original" / row["source_filename"]
        normalized = output / "normalized" / row["source_filename"]
        assert archived.read_bytes() == source.read_bytes()
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == row["original_sha256"]
        payload = yaml.safe_load(normalized.read_text(encoding="utf-8"))
        assert payload["task_id"] == row["task_id"]
        assert payload["annotator_id"] == "B"
        assert payload["annotation_mode"] == "human_interviewed"
        assert payload["unresolved"] == []
        assert len(payload["requirements"]) == row["requirement_count"]
        assert row["schema_errors"] == []


def test_annotator_b_import_surfaces_adjudication_flags(tmp_path) -> None:
    manifest = import_annotations(ATTACHMENTS, tmp_path / "B")
    flags = {
        (row["task_id"], row["local_id"], row["code"])
        for row in manifest["review_flags"]
    }
    assert (
        "dr_cross_deep_0001",
        "R6",
        "implicit_obligation_needs_adjudication",
    ) in flags
    assert (
        "dr_cross_deep_0001",
        "R7",
        "presentation_format_may_be_nonessential",
    ) in flags
