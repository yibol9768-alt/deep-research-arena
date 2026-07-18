#!/usr/bin/env python3
"""Build and replay one real Route B proof-steps pilot.

The pilot uses the frozen ``dra_v3_dev_audio_0002`` speaker-claims case.  It
creates an AI-reviewed proof-step annotation, a positive oracle report, an
evidence-only partial report, a positive report with one fabricated citation,
and replayable observation ledgers backed by the frozen content-addressed
blobs.  It then invokes the public score_case_v3 CLI for all three scenarios.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "dra_v3_dev_audio_0002"
CASE_PATH = ROOT / f"data/golden/cases_v3/development/{TASK_ID}.json"
PUBLIC_TASK_PATH = ROOT / f"data/tasks/deep_research/v3/development/{TASK_ID}.json"
GRAPH_DIR = ROOT / "data/evidence_graph/dra-v3-pilot-audio-speaker-claims-20260715-r1"
GRAPH_PATH = GRAPH_DIR / "nodes.jsonl"
REGISTRY_PATH = GRAPH_DIR / "corpus_registry.json"
PROTOCOL_PATH = ROOT / f"data/pilot_v3/protocol_manifests/{TASK_ID}.protocol.json"
DEFAULT_OUTPUT = ROOT / f"data/pilot_v3/route_b_end_to_end/{TASK_ID}"
FABRICATED_URL = "http://localhost:7770/route-b-fabricated-speaker.html"


STEP_NOTES = {
    "E1": "核查 Ortizan 商品页的价格、40W Max、失真、IPX7、续航等完整声明。",
    "E2": "核查 Soundcore Flare 2 商品页的价格、20W、THD+N、360 度、IPX7、续航等声明。",
    "E3": "限定社区编码讨论的适用范围，不能把一般讨论当成候选产品实测。",
    "E4": "解释扬声器扩散/指向性的物理意义与质量推断边界。",
    "E5": "解释 hi-res audio 标签能说明什么、不能说明什么。",
    "E6": "解释 IPX7 的标准测试边界，避免推成无限防水。",
    "E7": "解释 LDAC 码率和连接条件，避免推成稳定无损。",
    "E8": "解释被动振膜是实际结构，但不能单独证明低频质量。",
    "E9": "限定一般音箱偏好论坛经验，不能冒充同型号泳池或海滩验证。",
    "E10": "解释瓦数、效率、连续/峰值功率和允许失真的关系。",
    "B1": "综合 E3/E4/E5/E7/E8，区分真实机制与营销推论。",
    "B2": "综合 Ortizan 商品声明、被动振膜和功率知识，判断 40W Max 与无失真说法的证据边界。",
    "B3": "综合 Soundcore 商品声明、扩散概念和功率知识，形成可审计的声明矩阵。",
    "B4": "综合两商品页、IPX7 和论坛范围，判断防水声明及真实用户验证边界。",
    "D1": "依赖四个桥接结论，在审计性和失真风险优先的约束下给出最终选择。",
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_by_id(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["evidence_id"]: source for source in case["evidence_sources"]}


def _evidence_paragraphs(case: dict[str, Any]) -> list[str]:
    sources = _source_by_id(case)
    paragraphs: list[str] = []
    for step in case["evaluator_view"]["required_proof_steps"]:
        if step["type"] != "evidence":
            continue
        source = sources[step["claim"]]
        phrase = source["verifier"]["accepted_phrases"][0]
        paragraphs.append(
            f"{step['step_id']}. {phrase} "
            f"[source]({source['source_url']})"
        )
    return paragraphs


def _bridge_paragraphs(case: dict[str, Any]) -> list[str]:
    rules = case["rule_definitions"]
    paragraphs: list[str] = []
    for step in case["evaluator_view"]["required_proof_steps"]:
        if step["type"] != "bridge":
            continue
        phrase = rules[step["rule"]]["accepted_phrases"][0]
        paragraphs.append(f"{step['step_id']}. {phrase}")
    return paragraphs


def _decision_paragraph(case: dict[str, Any]) -> str:
    decision_step = next(
        step
        for step in case["evaluator_view"]["required_proof_steps"]
        if step["type"] == "decision"
    )
    rule = case["rule_definitions"][decision_step["rule"]]
    relation = rule["decision_matcher"]["accepted_phrases"][0]
    conclusion = rule["conclusion_matchers"]["soundcore_flare2"]["accepted_phrases"][0]
    return f"{decision_step['step_id']}. {relation} {conclusion}"


def _ledger(case: dict[str, Any], run_id: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    event_id = 1
    for source in case["evidence_sources"]:
        url = source["source_url"]
        evidence_id = source["evidence_id"]
        snippet = f"Search result exposing {evidence_id}: {url}"
        search_id = event_id
        events.append(
            {
                "run_id": run_id,
                "event_id": search_id,
                "timestamp": float(search_id),
                "event_type": "search_result",
                "request_url": f"http://localhost:8081/search?q={evidence_id}",
                "canonical_url": url,
                "parent_event_id": None,
                "content_sha256": _sha256_text(snippet),
                "content_text_or_blob_ref": snippet,
                "http_status": None,
                "observable": True,
            }
        )
        event_id += 1
        digest = source["content_sha256"]
        events.append(
            {
                "run_id": run_id,
                "event_id": event_id,
                "timestamp": float(event_id),
                "event_type": "fetch_body",
                "request_url": url,
                "canonical_url": url,
                "parent_event_id": search_id,
                "content_sha256": digest,
                "content_text_or_blob_ref": {"blob_ref": digest},
                "http_status": 200,
                "observable": True,
            }
        )
        event_id += 1
    return {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": events,
    }


def _annotation(case: dict[str, Any]) -> dict[str, Any]:
    requirements = case["query_requirements"]
    subgoals = case["research_subgoals"]
    steps = []
    for step in case["evaluator_view"]["required_proof_steps"]:
        step_id = step["step_id"]
        steps.append(
            {
                "step_id": step_id,
                "type": step["type"],
                "claim": step.get("claim"),
                "rule": step.get("rule"),
                "requires": step.get("requires", []),
                "vital": step.get("vital", False),
                "decision": "keep",
                "rationale_zh": STEP_NOTES[step_id],
                "query_requirement_ids": [
                    req["requirement_id"]
                    for req in requirements
                    if step_id in req["slot_ids"]
                ],
                "research_subgoal_ids": [
                    goal["subgoal_id"]
                    for goal in subgoals
                    if step_id in goal["requires"]
                ],
            }
        )
    return {
        "schema": "route_b_proof_step_annotation_v1",
        "task_id": case["task_id"],
        "annotation_mode": "ai_pilot_review",
        "reviewer_id": "codex",
        "status": "pilot_reviewed_not_human_gold",
        "scoring_semantics": "proof_steps_v1",
        "motif": case["motif"],
        "step_count": len(steps),
        "steps": steps,
        "issues": [
            {
                "code": "equivalent_paths_not_exhaustively_enumerated",
                "severity": "follow_up",
                "detail": (
                    "Most evidence steps currently list one frozen source_id. "
                    "The pilot is replayable, but equivalent supporting source_ids "
                    "should be added where the corpus contains them."
                ),
            },
            {
                "code": "human_step_boundary_review_pending",
                "severity": "follow_up",
                "detail": "This AI pilot review is not an independent human annotation.",
            },
        ],
    }


def _annotation_markdown(case: dict[str, Any], annotation: dict[str, Any]) -> str:
    public = json.loads(PUBLIC_TASK_PATH.read_text(encoding="utf-8"))
    lines = [
        "# Route B proof-step pilot：便携音箱宣传核查",
        "",
        f"任务：`{case['task_id']}`",
        "",
        f"> {public['intent']}",
        "",
        "本次是 AI pilot review，不是人工 gold。15 个步骤全部保留，用于先跑通 scorer。",
        "",
        "| 步骤 | 类型 | 依赖 | 标注意义 |",
        "|---|---|---|---|",
    ]
    type_zh = {"evidence": "证据", "bridge": "桥接", "decision": "最终决策"}
    for step in annotation["steps"]:
        deps = ", ".join(step["requires"]) if step["requires"] else "无"
        lines.append(
            f"| {step['step_id']} | {type_zh[step['type']]} | {deps} | {step['rationale_zh']} |"
        )
    lines.extend(
        [
            "",
            "## 当前缺口",
            "",
            "- 这份既有 development case 的证据步骤大多只枚举一个冻结 source ID；后续需要在语料允许时补充等价 source IDs，避免把代表性 witness 误成唯一路线。",
            "- 本次标注是 AI pilot review，正式冻结仍需人工检查步骤边界、依赖和最终答案合同。",
        ]
    )
    return "\n".join(lines)


def _ensure_blob_link(output_dir: Path) -> None:
    link = output_dir / "blobs"
    target = os.path.relpath(GRAPH_DIR / "blobs", output_dir)
    if link.is_symlink():
        if os.readlink(link) != target:
            raise RuntimeError(f"existing blob symlink points elsewhere: {link}")
        return
    if link.exists():
        raise RuntimeError(f"refusing to replace existing blob path: {link}")
    link.symlink_to(target, target_is_directory=True)


def _score_scenario(
    output_dir: Path,
    scenario: str,
    run_id: str,
) -> dict[str, Any]:
    score_path = output_dir / f"score_{scenario}.json"
    cmd = [
        sys.executable,
        str(ROOT / "scripts/score_case_v3.py"),
        "--case",
        str(CASE_PATH),
        "--scoring-semantics",
        "proof_steps_v1",
        "--report",
        str(output_dir / f"report_{scenario}.md"),
        "--ledger",
        str(output_dir / f"ledger_{scenario}.json"),
        "--evidence-graph",
        str(GRAPH_PATH),
        "--corpus-registry",
        str(REGISTRY_PATH),
        "--protocol-manifest",
        str(PROTOCOL_PATH),
        "--public-task",
        str(PUBLIC_TASK_PATH),
        "--agent",
        f"route-b-pilot-{scenario}",
        "--replicate",
        "1",
        "--expected-run-id",
        run_id,
        "--pretty",
    ]
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    _write_json(score_path, payload)
    return payload


def run(output_dir: Path) -> dict[str, Any]:
    case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_blob_link(output_dir)

    annotation = _annotation(case)
    _write_json(output_dir / "proof_step_annotation.json", annotation)
    _write_text(output_dir / "ANNOTATION.md", _annotation_markdown(case, annotation))

    evidence = "\n\n".join(_evidence_paragraphs(case))
    bridges = "\n\n".join(_bridge_paragraphs(case))
    decision = _decision_paragraph(case)
    positive = f"{evidence}\n\n{bridges}\n\n{decision}"
    reports = {
        "positive": positive,
        "partial": evidence,
        "fabricated": (
            positive
            + f"\n\nUnrelated fabricated citation: [fabricated]({FABRICATED_URL})"
        ),
    }
    run_ids = {
        scenario: f"route-b-audio-0002-{scenario}-v1"
        for scenario in reports
    }
    for scenario, report in reports.items():
        _write_text(output_dir / f"report_{scenario}.md", report)
        _write_json(output_dir / f"ledger_{scenario}.json", _ledger(case, run_ids[scenario]))

    scores = {
        scenario: _score_scenario(output_dir, scenario, run_ids[scenario])
        for scenario in reports
    }
    summary = {
        "schema": "route_b_end_to_end_pilot_result_v1",
        "task_id": TASK_ID,
        "annotation_mode": annotation["annotation_mode"],
        "required_steps": len(annotation["steps"]),
        "scenarios": {
            name: {
                "status": score.get("status"),
                "withheld": score.get("withheld"),
                "passed_steps": score.get("passed_steps"),
                "required_steps": score.get("required_steps"),
                "partial_completion": score.get("partial_completion"),
                "full_pass": score.get("full_pass"),
                "final_answer_pass": score.get("final_answer_pass"),
                "fabricated_citations": score.get("fabricated_citations"),
                "failure_reasons": score.get("full_pass_failure_reasons"),
            }
            for name, score in scores.items()
        },
        "known_follow_up": annotation["issues"],
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    summary = run(args.output_dir.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
