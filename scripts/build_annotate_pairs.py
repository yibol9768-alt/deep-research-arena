#!/usr/bin/env python3
"""Build the static report-pair bundle for the /annotate human-annotation page.

Reads the report .md files under data/results/deep/ (and data/results/deep_reports/
as a fallback) for the covered "deep cross-site" tasks, pairs up the agents whose
reports actually exist and are non-trivial, and writes the bundle consumed by the
client page at frontend/public/annotate-pairs.json.

The bundle is intentionally self-contained: the annotation UI is a static export
(no server), so everything it needs to render is baked in here.

Output schema:
    {
      "generated": "<ISO-8601 UTC>",
      "truncate_chars": 8000,
      "pairs": [
        {
          "task_id":  "dr_cross_deep_0001",
          "agent_a":  "camel-ai",
          "agent_b":  "claude-code",
          "intent":   "<short label / report H1>",
          "words_a":  1234,
          "words_b":  2345,
          "report_a": "<markdown, capped to ~8000 chars>",
          "report_b": "<markdown, capped to ~8000 chars>"
        },
        ...
      ]
    }

Run from the repo root:
    python3 scripts/build_annotate_pairs.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

# --- configuration ----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIRS = [
    REPO_ROOT / "data" / "results" / "deep",
    REPO_ROOT / "data" / "results" / "deep_reports",
]
PAIR_QUEUE = REPO_ROOT / "tools" / "human_pref_collector" / "pair_queue.jsonl"
TASKS_DIR = REPO_ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
OUT_PATH = REPO_ROOT / "frontend" / "public" / "annotate-pairs.json"

# Only the covered tasks (headphones / electronics family) where reports exist.
COVERED_TASKS = [f"dr_cross_deep_{i:04d}" for i in range(1, 6)]  # 0001..0005

# A report with fewer than this many characters is treated as empty/failed and
# is not eligible for annotation (e.g. the empty "storm" outputs).
MIN_REPORT_CHARS = 1000

# Cap each report so the JSON bundle stays reasonably small for a static export.
TRUNCATE_CHARS = 8000

# Keep the bundle bounded.
MAX_PAIRS = 30

# Report file suffixes, in preference order (matrix is the canonical run).
SUFFIX_PREFERENCE = ["_matrix", "_smoke", ""]


# --- helpers ----------------------------------------------------------------


def find_report(agent: str, task_id: str) -> Path | None:
    """Locate the best report .md for (agent, task), deterministically.

    Tries each results dir, then each known suffix, returning the first match
    that exists and clears the MIN_REPORT_CHARS bar.
    """
    for base in RESULTS_DIRS:
        for suffix in SUFFIX_PREFERENCE:
            candidate = base / f"{agent}__{task_id}{suffix}.md"
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                if len(text.strip()) >= MIN_REPORT_CHARS:
                    return candidate
    return None


def agents_with_reports(task_id: str, known_agents: list[str]) -> dict[str, Path]:
    """Return {agent: report_path} for every agent that has a usable report."""
    found: dict[str, Path] = {}
    for agent in known_agents:
        path = find_report(agent, task_id)
        if path is not None:
            found[agent] = path
    return found


def discover_agents() -> list[str]:
    """Collect every agent prefix seen across the results dirs plus the queue."""
    agents: set[str] = set()
    for base in RESULTS_DIRS:
        if not base.is_dir():
            continue
        for md in base.glob("*__dr_cross_deep_*.md"):
            prefix = md.name.split("__", 1)[0]
            agents.add(prefix)
    if PAIR_QUEUE.is_file():
        for line in PAIR_QUEUE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            for key in ("agent_a", "agent_b"):
                if obj.get(key):
                    agents.add(obj[key])
    return sorted(agents)


def queued_pairs() -> list[tuple[str, str, str]]:
    """Read (task_id, agent_a, agent_b) tuples from the pair queue, if present."""
    pairs: list[tuple[str, str, str]] = []
    if not PAIR_QUEUE.is_file():
        return pairs
    for line in PAIR_QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        task_id = obj.get("task_id")
        agent_a = obj.get("agent_a")
        agent_b = obj.get("agent_b")
        if task_id and agent_a and agent_b:
            pairs.append((task_id, agent_a, agent_b))
    return pairs


def first_heading(text: str) -> str | None:
    """Return the first markdown H1/H2 text, if any."""
    for line in text.splitlines():
        m = re.match(r"^\s{0,3}#{1,2}\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return None


def short_intent(task_id: str, report_text: str) -> str:
    """A short, human-friendly label for the task.

    Prefer the report H1 (these are clean topic titles like
    "Consumer-Grade Audio Headphones: ..."); fall back to the first sentence of
    the task JSON intent; finally fall back to the task id.
    """
    heading = first_heading(report_text)
    if heading:
        return heading
    task_json = TASKS_DIR / f"{task_id}.json"
    if task_json.is_file():
        try:
            data = json.loads(task_json.read_text(encoding="utf-8"))
            intent = (data.get("intent") or "").strip()
            if intent:
                # First sentence, trimmed to a sane length.
                first = re.split(r"(?<=[.!?])\s", intent, maxsplit=1)[0]
                return first[:160].strip()
        except (json.JSONDecodeError, OSError):
            pass
    return task_id


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def truncate(text: str) -> tuple[str, bool]:
    """Cap text to ~TRUNCATE_CHARS, appending a truncation note when cut."""
    text = text.strip()
    if len(text) <= TRUNCATE_CHARS:
        return text, False
    cut = text[:TRUNCATE_CHARS]
    # Avoid slicing mid-line; back off to the last newline if one is nearby.
    nl = cut.rfind("\n")
    if nl > TRUNCATE_CHARS - 600:
        cut = cut[:nl]
    cut = cut.rstrip() + "\n\n---\n\n_[report truncated for annotation: showing the "
    cut += f"first {TRUNCATE_CHARS} characters of the original]_\n"
    return cut, True


# --- build ------------------------------------------------------------------


def build() -> dict:
    known_agents = discover_agents()

    # Candidate ordered pairs. Start from the queue (covered tasks only), then
    # fill in with every co-present agent pair for the covered tasks so we have
    # enough material even though the queue references agents with no reports.
    seen: set[tuple[str, str, str]] = set()
    ordered: list[tuple[str, str, str]] = []

    def add(task_id: str, a: str, b: str) -> None:
        key = (task_id, a, b)
        rev = (task_id, b, a)
        if key in seen or rev in seen:
            return
        seen.add(key)
        ordered.append(key)

    # 1) Queue-driven pairs, restricted to covered tasks.
    for task_id, a, b in queued_pairs():
        if task_id in COVERED_TASKS:
            add(task_id, a, b)

    # 2) Exhaustive co-present pairs per covered task (fills gaps deterministically).
    for task_id in COVERED_TASKS:
        present = agents_with_reports(task_id, known_agents)
        for a, b in combinations(sorted(present), 2):
            add(task_id, a, b)

    pairs: list[dict] = []
    for task_id, agent_a, agent_b in ordered:
        if len(pairs) >= MAX_PAIRS:
            break
        path_a = find_report(agent_a, task_id)
        path_b = find_report(agent_b, task_id)
        if path_a is None or path_b is None:
            # One or both reports are missing/empty: not annotatable.
            continue
        raw_a = path_a.read_text(encoding="utf-8", errors="replace")
        raw_b = path_b.read_text(encoding="utf-8", errors="replace")
        report_a, _ = truncate(raw_a)
        report_b, _ = truncate(raw_b)
        pairs.append(
            {
                "task_id": task_id,
                "agent_a": agent_a,
                "agent_b": agent_b,
                "intent": short_intent(task_id, raw_a),
                "words_a": word_count(raw_a),
                "words_b": word_count(raw_b),
                "report_a": report_a,
                "report_b": report_b,
            }
        )

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "truncate_chars": TRUNCATE_CHARS,
        "pairs": pairs,
    }


def main() -> None:
    bundle = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)} with {len(bundle['pairs'])} pairs")
    for pair in bundle["pairs"]:
        print(
            f"  {pair['task_id']}  {pair['agent_a']} vs {pair['agent_b']}"
            f"  ({pair['words_a']}w / {pair['words_b']}w)"
        )


if __name__ == "__main__":
    main()
