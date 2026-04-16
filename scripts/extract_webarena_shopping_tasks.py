"""Extract the 187 pure-shopping tasks from WebArena's test.raw.json into
per-task JSON files under data/tasks/webarena/shopping/.

We keep WebArena's native format so the verifiers (ported from WebArena's
evaluators) can read the same `eval` schema without a translation layer.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "webarena_ref" / "config_files" / "test.raw.json"
DST = ROOT / "data" / "tasks" / "webarena" / "shopping"


def main() -> None:
    assert SRC.exists(), f"missing WebArena source: {SRC}"
    DST.mkdir(parents=True, exist_ok=True)

    tasks = json.loads(SRC.read_text())
    shopping = [t for t in tasks if t.get("sites") == ["shopping"]]
    print(f"total: {len(tasks)}, shopping-only: {len(shopping)}")

    for t in shopping:
        tid = t["task_id"]
        (DST / f"{tid}.json").write_text(json.dumps(t, indent=2, ensure_ascii=False))

    by_eval: dict[str, int] = {}
    for t in shopping:
        for e in t.get("eval", {}).get("eval_types", []):
            by_eval[e] = by_eval.get(e, 0) + 1

    index = {
        "count": len(shopping),
        "by_eval_types": by_eval,
        "task_ids": [t["task_id"] for t in shopping],
    }
    (DST / "index.json").write_text(json.dumps(index, indent=2))
    print(f"wrote {len(shopping)} tasks + index.json to {DST}")


if __name__ == "__main__":
    main()
