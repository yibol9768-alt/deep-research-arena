#!/usr/bin/env python3
"""Local structural validation of topic YAMLs (no sandbox needed).

Checks: required fields, array lengths, topic_id/task_id consistency,
cross-file duplicates, and basic format sanity.

Usage:
    python3 scripts/validate_yamls_local.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPICS_DIR = ROOT / "configs" / "deep_topics"

REQUIRED_FIELDS = ["topic_id", "task_id", "display_name",
                   "shopping_keywords", "reddit_forums", "reddit_keywords",
                   "wiki_mandatory", "wiki_extra"]

MIN_COUNTS = {
    "shopping_keywords": 6,
    "reddit_forums": 5,
    "reddit_keywords": 5,
    "wiki_mandatory": 7,
    "wiki_extra": 10,
}


def parse_yaml(path: Path) -> dict:
    text = path.read_text()
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except (ImportError, yaml.YAMLError):
        pass
    result = {}
    current_key = None
    current_list = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current_key and current_list is not None:
                val = stripped[2:].strip().strip("'\"")
                current_list.append(val)
            continue
        m = re.match(r"^(\w[\w_]*)\s*:\s*(.*)", stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            current_key = key
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                result[key] = items
                current_list = None
            elif val == "" or val == "[]":
                current_list = []
                result[key] = current_list
            else:
                result[key] = val.strip("'\"")
                current_list = None
    return result


def validate_one(path: Path) -> list[str]:
    errors = []
    try:
        d = parse_yaml(path)
    except Exception as e:
        return [f"PARSE ERROR: {e}"]

    for field in REQUIRED_FIELDS:
        if field not in d:
            errors.append(f"missing field: {field}")

    for field, min_count in MIN_COUNTS.items():
        val = d.get(field, [])
        if not isinstance(val, list):
            errors.append(f"{field} should be a list, got {type(val).__name__}")
        elif len(val) < min_count:
            errors.append(f"{field} has {len(val)} items (need ≥{min_count})")

    num_match = re.search(r"^(\d{4})_", path.name)
    if num_match:
        expected_num = int(num_match.group(1))
        task_id = d.get("task_id", "")
        expected_task = f"dr_cross_deep_{expected_num:04d}"
        if task_id != expected_task:
            errors.append(f"task_id mismatch: got '{task_id}', expected '{expected_task}'")

    return errors


def main():
    yamls = sorted(TOPICS_DIR.glob("0*.yaml"))
    print(f"Validating {len(yamls)} YAML files...\n")

    all_topic_ids = Counter()
    all_task_ids = Counter()
    total_errors = 0
    missing_nums = []

    for p in yamls:
        d = parse_yaml(p)
        tid = d.get("topic_id", "?")
        taskid = d.get("task_id", "?")
        all_topic_ids[tid] += 1
        all_task_ids[taskid] += 1

    for num in range(1, 101):
        matches = [p for p in yamls if p.name.startswith(f"{num:04d}_")]
        if not matches:
            missing_nums.append(num)

    errors_by_file = {}
    for p in yamls:
        errs = validate_one(p)
        if errs:
            errors_by_file[p.name] = errs
            total_errors += len(errs)

    # Report
    if missing_nums:
        print(f"MISSING task numbers ({len(missing_nums)}): {missing_nums}\n")

    dup_topics = {k: v for k, v in all_topic_ids.items() if v > 1}
    if dup_topics:
        print(f"DUPLICATE topic_ids: {dup_topics}\n")

    dup_tasks = {k: v for k, v in all_task_ids.items() if v > 1}
    if dup_tasks:
        print(f"DUPLICATE task_ids: {dup_tasks}\n")

    if errors_by_file:
        print(f"FILES WITH ERRORS ({len(errors_by_file)}):\n")
        for fname, errs in sorted(errors_by_file.items()):
            print(f"  {fname}:")
            for e in errs:
                print(f"    - {e}")
            print()
    else:
        print("All files passed structural validation.")

    print(f"\nSummary: {len(yamls)} files, {len(missing_nums)} missing, "
          f"{total_errors} errors, {len(dup_topics)} duplicate topic_ids")
    return 1 if total_errors or missing_nums else 0


if __name__ == "__main__":
    sys.exit(main())
