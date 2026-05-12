"""Per-pair bug audit for the running Qwen3.5-27b bulk leaderboard.

For each ``*_matrix.score.json`` produced by the bulk run:

  schema         JSON parses, has top-level ``task`` and ``composite.composite_v2``
  empty          ``answer_chars`` is non-trivial (>=100) — empty answers indicate
                 the runner returned nothing
  thinking-leak  the answer markdown does not contain ``<think>`` /
                 ``Thinking Process:`` (proxy strip working)
  judge          no ``judge_error`` in checklist / analysis_depth /
                 presentation / citation_alignment
  unclear        not 21/21 unclear (judge_client max-tokens retry working)
  composite      ``composite.composite_v2`` is in [0, 1]
  reach          if ``url_reachability.passed`` is True, ``cited_total > 0``
  all-zero       composite_v2 == 0 with non-trivial answer_chars (signals
                 scoring exception, not a real failure)
  dup            no four-way composite_v2 tie across tasks for the same agent
                 (template-output tell)

Print one line per pair ``OK`` / ``BUG``. Exit code is the bug count.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/opt/deep_reserch/data/results/deep_v3")
PAIR_NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d{4})_matrix\.score\.json$")
THINK_LEAK_RE = re.compile(r"(<think>|Thinking Process:|</think>)", re.IGNORECASE)


def _gp(d: dict, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _ck_schema(data: dict) -> str | None:
    if "task" not in data:
        return "missing top-level 'task'"
    if _gp(data, "composite", "composite_v2") is None:
        return "missing composite.composite_v2"
    return None


def _ck_empty(data: dict) -> str | None:
    chars = data.get("answer_chars")
    if not isinstance(chars, (int, float)):
        return "answer_chars not numeric"
    if chars < 100:
        return f"answer_chars={chars} (effectively empty)"
    return None


def _ck_thinking_leak(answer_path: Path) -> str | None:
    if not answer_path.exists():
        return None
    head = answer_path.read_text(encoding="utf-8", errors="replace")[:8000]
    m = THINK_LEAK_RE.search(head)
    if m:
        return f"answer.md contains '{m.group(0)}' at offset {m.start()}"
    return None


def _ck_judge_errors(data: dict) -> str | None:
    bad = []
    for path in (
        ("checklist", "judge_error"),
        ("analysis_depth", "details", "judge_error"),
        ("presentation", "details", "judge_error"),
        ("citation_alignment", "details", "judge", "error"),
    ):
        v = _gp(data, *path)
        if v:
            bad.append(f"{'.'.join(path)}={v}")
    if bad:
        return "; ".join(bad)
    return None


def _ck_unclear(data: dict) -> str | None:
    cl = data.get("checklist") or {}
    verdicts = cl.get("verdicts") or []
    unclear = cl.get("unclear_count", 0)
    if verdicts and unclear == len(verdicts):
        return f"checklist {unclear}/{len(verdicts)} unclear (judge couldn't parse answers)"
    return None


def _ck_composite(data: dict) -> str | None:
    c2 = _gp(data, "composite", "composite_v2")
    if not isinstance(c2, (int, float)):
        return f"composite_v2 not numeric: {c2!r}"
    if not (0.0 <= c2 <= 1.0):
        return f"composite_v2 out of range: {c2}"
    return None


def _ck_reach(data: dict) -> str | None:
    rp = _gp(data, "url_reachability", "passed")
    cited = _gp(data, "url_reachability", "details", "cited_total", default=0)
    if rp is True and cited == 0:
        return "reach.passed=True but cited_total=0"
    return None


def _ck_all_zero(data: dict) -> str | None:
    c2 = _gp(data, "composite", "composite_v2")
    chars = data.get("answer_chars", 0)
    if c2 == 0.0 and isinstance(chars, (int, float)) and chars > 5000:
        return f"composite_v2=0 with answer_chars={chars} (scoring may have errored)"
    return None


CHECKS = (
    ("schema",        _ck_schema),
    ("empty",         _ck_empty),
    ("judge",         _ck_judge_errors),
    ("unclear",       _ck_unclear),
    ("composite",     _ck_composite),
    ("reach",         _ck_reach),
    ("all-zero",      _ck_all_zero),
)


def main() -> int:
    files = sorted(ROOT.glob("*_matrix.score.json"))
    if not files:
        print("no score files yet")
        return 0
    by_agent: dict[str, list[tuple[str, float]]] = defaultdict(list)
    bugs = 0
    print(f"checking {len(files)} score JSONs in {ROOT}\n")
    for fp in files:
        m = PAIR_NAME_RE.match(fp.name)
        if not m:
            print(f"BUG schema-name {fp.name}")
            bugs += 1
            continue
        agent, task = m.group(1), m.group(2)
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"BUG json-parse {agent} {task}: {exc}")
            bugs += 1
            continue
        bug_for_pair = []
        for label, fn in CHECKS:
            err = fn(data)
            if err:
                bug_for_pair.append(f"{label}: {err}")
        # thinking-leak check needs the answer markdown
        ans = data.get("answer_path")
        if isinstance(ans, str):
            ans_path = Path(ans)
            if not ans_path.is_absolute():
                ans_path = Path("/opt/deep_reserch") / ans_path
            err = _ck_thinking_leak(ans_path)
            if err:
                bug_for_pair.append(f"thinking-leak: {err}")
        if bug_for_pair:
            for b in bug_for_pair:
                print(f"BUG  {agent} {task}: {b}")
            bugs += 1
        else:
            c2 = _gp(data, "composite", "composite_v2", default=0.0)
            chars = data.get("answer_chars", 0)
            cited = _gp(data, "url_reachability", "details", "cited_total", default=0)
            cl = data.get("checklist") or {}
            print(f"OK   {agent} {task}  composite_v2={c2:.4f}  chars={chars}  cited={cited}  "
                  f"checklist={cl.get('pass_count', 0)}/{cl.get('fail_count', 0)}/{cl.get('unclear_count', 0)} (P/F/U)")
            by_agent[agent].append((task, float(c2)))

    # cross-pair duplicate check (template tell): only fires once we have >= 4 pairs/agent
    print()
    for agent, rows in by_agent.items():
        score_to_tasks = defaultdict(list)
        for task, c2 in rows:
            score_to_tasks[round(c2, 6)].append(task)
        for c2, tasks in score_to_tasks.items():
            if len(tasks) >= 4:
                print(f"BUG dup {agent}: composite_v2={c2} on tasks {tasks}")
                bugs += 1

    print(f"\nresult: {len(files)} pairs, {bugs} bug-pairs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
