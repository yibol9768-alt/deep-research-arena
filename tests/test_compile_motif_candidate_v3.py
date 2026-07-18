from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.compile_motif_candidate_v3 as cli
from src.eval.case_discovery_v3 import GraphMotif
from test_motif_compiler_v3 import _parts_for_motif


def _generator_view(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "scenario": "Compare two options under a constrained scenario.",
                "constraints": ["budget limit", "long use"],
                "candidate_actions": ["option a", "option b"],
                "target": "Explain the evidence and give a constraint-consistent conclusion.",
            }
        ),
        encoding="utf-8",
    )


def test_cli_replays_selection_and_compiles_dual_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, candidate = _parts_for_motif(GraphMotif.MULTI_BRANCH_SYNTHESIS)
    monkeypatch.setattr(cli, "load_graph_structure", lambda _path: graph)
    monkeypatch.setattr(
        cli,
        "discover_candidates",
        lambda *_args, **_kwargs: SimpleNamespace(
            selected_candidates=(candidate,)
        ),
    )
    generator = tmp_path / "generator.json"
    output = tmp_path / "compiled.json"
    _generator_view(generator)

    assert cli.main(
        [
            "--graph-dir",
            str(tmp_path / "graph"),
            "--generator-view",
            str(generator),
            "--max-expansion-depth",
            "2",
            "--out",
            str(output),
        ]
    ) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == cli.OUTPUT_SCHEMA
    assert payload["directly_scorable_gold"] is False
    assert payload["candidate"]["eligibility"]["eligible"] is True
    assert payload["compilation"]["generator_view"]["constraints"] == [
        "budget limit",
        "long use",
    ]
    assert len(
        payload["compilation"]["evaluator_view"]["required_proof_steps"]
    ) >= 4


def test_generator_view_rejects_extra_private_fields(tmp_path: Path) -> None:
    generator = tmp_path / "generator.json"
    _generator_view(generator)
    payload = json.loads(generator.read_text(encoding="utf-8"))
    payload["evaluator_view"] = {"gold_answer": "option a"}
    generator.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(Exception, match="unknown"):
        cli._load_generator_view(generator)
