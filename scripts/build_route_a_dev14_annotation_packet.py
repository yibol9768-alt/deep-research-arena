#!/usr/bin/env python3
"""Build two blinded Route A Dev-14 annotation workbooks.

The workbooks contain only the public query.  They deliberately omit existing
rubrics, answer keys, evidence URLs, task angles and agent reports so the two
annotators can identify requirements independently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
DEFAULT_OUTPUT = ROOT / "data" / "calibration" / "route_a_dev14"


def _tasks() -> list[dict]:
    rows: list[dict] = []
    for number in range(1, 15):
        path = TASK_DIR / f"dr_cross_deep_{number:04d}.json"
        task = json.loads(path.read_text(encoding="utf-8"))
        query = str(task.get("intent") or "").strip()
        rows.append({
            "task_id": task["task_id"],
            "task_version": task.get("task_version"),
            "query": query,
            "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "source_file": str(path.relative_to(ROOT)),
        })
    return rows


def _requirement_template() -> str:
    return """复制下面的块，每个必要要求填写一次；数量由 query 决定，不要求凑数。

```yaml
- local_id: R1
  requirement: "用一句话写报告不能省略的要求"
  necessity_reason: "为什么删除它就没有完整回答 query"
  output_form: "compare | explain | verify | experience | recommend | other"
  intrinsic_source_roles: []  # 只在 query 本身要求时填 shopping/forums/wiki
  source_role_reason: "没有则写 none"
```

可选但非必要的内容：

```yaml
- optional_item: ""
  reason: ""
```

本题自检：

- [ ] 每个 requirement 都能在 query 原文中指出依据
- [ ] requirements 之间没有重复计分
- [ ] 没有把文风、篇幅、引用数量或搜索次数写成 requirement
- [ ] 没有写产品答案、URL、关键词 matcher 或我猜测的 gold
- [ ] 如果 query 要求最终建议，已经包含 recommendation requirement

疑问或歧义：

```text

```
"""


def _workbook(annotator: str, tasks: list[dict]) -> str:
    sections = [
        f"# Route A Dev-14 独立 Rubric 标注包：标注者 {annotator}",
        "",
        "请先阅读 `docs/ROUTE_A_DEV14_CALIBRATION_GUIDE.md`。标注期间不要查看另一位标注者的文件、现有 rubric、answer key、evidence graph 或 agent 报告。",
        "",
        f"标注者姓名/代号：`{annotator}`",
        "",
        "开始日期：`待填写`",
        "",
        "完成日期：`待填写`",
        "",
    ]
    for index, task in enumerate(tasks, 1):
        quote = "\n".join(f"> {line}" for line in task["query"].splitlines())
        sections.extend([
            f"## {index:02d}. `{task['task_id']}`",
            "",
            f"Query SHA-256：`{task['query_sha256']}`",
            "",
            quote,
            "",
            "Query 是否存在无法唯一解释的要求：`是 / 否`",
            "",
            _requirement_template(),
            "",
        ])
    return "\n".join(sections).rstrip() + "\n"


def _adjudication(tasks: list[dict]) -> str:
    sections = [
        "# Route A Dev-14 Rubric 分歧裁决表",
        "",
        "只有在标注者 A、B 都完成并锁定各自文件后才填写本表。不要回改独立标注文件。",
        "",
    ]
    for index, task in enumerate(tasks, 1):
        sections.extend([
            f"## {index:02d}. `{task['task_id']}`",
            "",
            "### A/B 对齐",
            "",
            "| A local_id | B local_id | 对齐关系：等价/部分重叠/A独有/B独有 | 说明 |",
            "|---|---|---|---|",
            "|  |  |  |  |",
            "",
            "### 最终 requirements",
            "",
            "```yaml",
            "- final_id: R1",
            "  requirement: \"\"",
            "  output_form: \"\"",
            "  required_source_roles: []",
            "  derived_from: []  # 例如 [A:R1, B:R2]",
            "  adjudication_reason: \"\"",
            "```",
            "",
            "### 任务级决定",
            "",
            "- Query requirement agreement：`一致 / 部分一致 / 严重分歧`",
            "- 下一阶段：`进入 evidence answerability audit / 先改写 query / 移出 Dev-14`",
            "- 裁决者：`待填写`",
            "- 裁决说明：",
            "",
            "```text",
            "",
            "```",
            "",
        ])
    return "\n".join(sections).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="build blinded Route A Dev-14 workbooks")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tasks = _tasks()
    (output / "annotator_A.md").write_text(_workbook("A", tasks), encoding="utf-8")
    (output / "annotator_B.md").write_text(_workbook("B", tasks), encoding="utf-8")
    (output / "adjudication.md").write_text(_adjudication(tasks), encoding="utf-8")
    (output / "task_manifest.json").write_text(
        json.dumps({
            "packet_version": "route_a_dev14_blind_v1",
            "task_count": len(tasks),
            "blinding": [
                "no_existing_rubric",
                "no_answer_key",
                "no_evidence_urls",
                "no_agent_reports",
                "no_task_angle",
            ],
            "tasks": tasks,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

