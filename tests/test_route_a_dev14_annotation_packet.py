from __future__ import annotations

import json

from scripts.build_route_a_dev14_annotation_packet import main


def test_dev14_packet_contains_two_blinded_workbooks_and_adjudication(tmp_path) -> None:
    assert main(["--output-dir", str(tmp_path)]) == 0

    manifest = json.loads((tmp_path / "task_manifest.json").read_text(encoding="utf-8"))
    a = (tmp_path / "annotator_A.md").read_text(encoding="utf-8")
    b = (tmp_path / "annotator_B.md").read_text(encoding="utf-8")
    adjudication = (tmp_path / "adjudication.md").read_text(encoding="utf-8")

    assert manifest["task_count"] == 14
    assert manifest["tasks"][0]["task_id"] == "dr_cross_deep_0001"
    assert manifest["tasks"][-1]["task_id"] == "dr_cross_deep_0014"
    assert all(task["query"] in a and task["query"] in b for task in manifest["tasks"])
    assert all(task["task_id"] in adjudication for task in manifest["tasks"])
    assert "synthesis_requirements" not in a
    assert "vital_product_urls" not in a
    assert "agent report" not in json.dumps(manifest, ensure_ascii=False).lower()

