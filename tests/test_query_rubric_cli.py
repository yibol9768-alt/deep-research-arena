from __future__ import annotations

import json

from scripts.build_route_a_board import main as board_cli
from scripts.compile_query_rubric import main as compile_cli


def test_compile_cli_emits_a_valid_draft(tmp_path, capsys) -> None:
    task = {
        "task_id": "cli-demo",
        "task_version": 2,
        "intent": "Compare Alpha and Beta.",
        "tri_source": {"cluster": "demo", "archetype": "comparison"},
    }
    atom = {
        "atom_id": "A_compare",
        "atom_type": "dimension",
        "description": "Compare both options.",
        "mention": {"all_term_groups": [["Alpha"], ["Beta"]]},
        "response_contract": {"all_term_groups": [["Alpha"], ["Beta"]]},
        "evidence": {
            "acceptable_source_roles": ["shopping"],
            "relevance_contract": {"all_term_groups": [["Alpha", "Beta"]]},
        },
        "approved": False,
    }
    task_path = tmp_path / "task.json"
    atom_path = tmp_path / "atoms.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    atom_path.write_text(json.dumps([atom]), encoding="utf-8")

    assert compile_cli(["--task", str(task_path), "--atoms", str(atom_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task_id"] == "cli-demo"
    assert payload["status"] == "draft"
    assert payload["scoring_semantics"] == "grounded_requirements_v1"


def test_board_cli_keeps_two_columns(tmp_path, capsys) -> None:
    rows = [{
        "status": "ok",
        "attributable": True,
        "grounded_requirement_coverage": 0.5,
        "requirement_coverage": 1.0,
        "integrity_clean": False,
        "url_integrity": {"n_in_corpus": 3, "n_fabricated": 1},
    }]
    path = tmp_path / "rows.json"
    path.write_text(json.dumps(rows), encoding="utf-8")

    assert board_cli(["--input", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["macro_grounded_requirement_coverage"] == 0.5
    assert payload["url_fabrication_rate"] == 0.25
    assert "quality" not in payload
