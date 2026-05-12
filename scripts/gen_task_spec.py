#!/usr/bin/env python3
"""Generate a deep-tier task JSON spec from a golden JSON and intent type.

Uses DeepSeek V4 flash (via OPENAI_BASE_URL / OPENAI_API_KEY) to generate:
  - The full intent prompt (following existing V1 patterns per intent type)
  - 21 task-specific checklist items

Reads existing task JSONs for format reference.

Usage:
    OPENAI_BASE_URL=http://westd:8088/v1 OPENAI_API_KEY=sk-... \
    python3 scripts/gen_task_spec.py \
        --golden-json data/golden/deep/dr_cross_deep_0031.json \
        --intent-type Recommendation \
        --topic-yaml configs/deep_topics/0031_new_topic.yaml \
        --task-id dr_cross_deep_0031 \
        --out data/tasks/deep_research/cross_site_deep/dr_cross_deep_0031.json

    # Also writes checklist items to stdout (append to checklists_deep.json manually)

Environment:
    OPENAI_BASE_URL  - API base URL (required)
    OPENAI_API_KEY   - API key (required)
    GEN_MODEL        - model name (default: deepseek-v4-flash)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INTENT_TYPES = [
    "Recommendation", "Comparison", "Debunking",
    "Causal", "Timeline", "Enumeration",
]

# Map intent types to reference task IDs (to load as examples)
INTENT_REFERENCE = {
    "Recommendation": "dr_cross_deep_0001",
    "Comparison":     "dr_cross_deep_0003",
    "Debunking":      "dr_cross_deep_0006",
    "Causal":         "dr_cross_deep_0009",
    "Timeline":       "dr_cross_deep_0010",
    "Enumeration":    "dr_cross_deep_0012",
}


def _load_yaml_minimal(path: str) -> dict:
    """Load topic YAML with pyyaml or a minimal fallback parser."""
    text = Path(path).read_text()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        pass
    # Minimal parser
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
            elif val == "" or val == "|":
                current_list = []
                result[key] = current_list
            else:
                result[key] = val
                current_list = None
    return result


def _load_reference_task(intent_type: str) -> dict:
    """Load a reference task JSON matching the intent type."""
    ref_id = INTENT_REFERENCE.get(intent_type, "dr_cross_deep_0001")
    ref_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{ref_id}.json"
    if ref_path.exists():
        return json.loads(ref_path.read_text())
    return {}


def _load_reference_checklist(intent_type: str) -> list:
    """Load a reference checklist for the intent type."""
    ref_id = INTENT_REFERENCE.get(intent_type, "dr_cross_deep_0001")
    cl_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / "checklists_deep.json"
    if cl_path.exists():
        data = json.loads(cl_path.read_text())
        return data.get(ref_id, [])
    return []


def _call_llm(prompt: str, system: str) -> str:
    """Call the LLM via OpenAI-compatible endpoint."""
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("openai SDK not installed.  pip install openai")

    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not base_url or not api_key:
        sys.exit("Set OPENAI_BASE_URL and OPENAI_API_KEY env vars.")

    model = os.environ.get("GEN_MODEL", "deepseek-v4-flash")
    client = OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        temperature=0.4,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content or ""


def _extract_json(text: str) -> dict:
    """Extract a JSON object from LLM output, stripping markdown fences."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try finding JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        # Find the matching closing brace
        candidate = m.group(0)
        depth = 0
        end = 0
        for i, c in enumerate(candidate):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > 0:
            try:
                return json.loads(candidate[:end])
            except json.JSONDecodeError:
                pass

    # Try more aggressive extraction
    for m in re.finditer(r"\{", text):
        start = m.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        break
    sys.exit(f"Could not parse LLM output as JSON:\n{text[:500]}")


def _build_task_json(
    task_id: str,
    intent: str,
    topic_cfg: dict,
    golden_meta: dict,
    synthesis_req: dict,
    ref_task: dict,
) -> dict:
    """Construct the full task JSON from components."""
    # Determine per-domain minimums based on intent type
    per_domain = ref_task.get("citation_policy", {}).get("per_domain_minimum", {})
    if not per_domain:
        per_domain = {
            "__SHOPPING__": 30,
            "__REDDIT__": 20,
            "__WIKIPEDIA__": 15,
        }

    task = {
        "schema_version": "deep-1.0.0",
        "task_id": task_id,
        "tier": "deep",
        "sites": ["shopping", "reddit", "wikipedia"],
        "difficulty": 5,
        "expected_steps": 80,
        "intent": intent,
        "start_url": f"__SHOPPING__/catalogsearch/result/?q={topic_cfg.get('shopping_keywords', [''])[0].replace(' ', '+')}",
        "storage_state": None,
        "require_login": False,
        "markdown_spec": {
            "min_words": 3500,
            "max_words": 8000,
            "min_paragraphs": 25,
            "min_citations": 60,
            "min_pages_browsed": 120,
        },
        "citation_policy": {
            "required_for": [
                "price", "rating", "thread_score",
                "feature_claim", "wiki_definition",
            ],
            "must_be_in_domain": [
                "__SHOPPING__", "__REDDIT__", "__WIKIPEDIA__",
            ],
            "min_distinct_sources": 60,
            "min_distinct_domains": 3,
            "per_domain_minimum": per_domain,
        },
        "url_coverage": {
            "golden_pool_path": f"data/golden/deep/{task_id}.json",
            "min_unique_urls_browsed": 100,
            "min_unique_urls_cited": 60,
            "min_must_cite_recall": 0.45,
            "min_expected_pool_coverage": 0.0,
            "min_domain_balance": 0.8,
            "weight_in_composite": 0.25,
            "scoring_weights": {
                "must_cite_recall": 0.55,
                "pool_coverage": 0.15,
                "domain_balance": 0.3,
            },
        },
        "url_reachability": {
            "min_reachability_rate": 0.3,
            "probe_timeout_seconds": 6.0,
        },
        "golden": {
            "triples_path": f"data/golden/deep/{task_id}.json",
            "expected_predicates": [
                "price", "rating", "review_count", "feature_claim",
                "forum", "thread_score", "comment_count",
                "thread_classification", "wiki_defines",
            ],
        },
        "synthesis_requirements": synthesis_req,
        "coverage_checklist_path": "data/tasks/deep_research/cross_site_deep/checklists_deep.json",
        "author_notes": (
            f"Deep-tier task generated by gen_task_spec.py from "
            f"configs/deep_topics/{topic_cfg.get('topic_id', '?')}.yaml. "
            f"Golden: must={golden_meta.get('n_must_cite', '?')}, "
            f"pool={golden_meta.get('n_expected_pool', '?')}."
        ),
    }
    return task


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a task spec JSON from golden and intent type")
    ap.add_argument("--golden-json", required=True,
                    help="Path to golden JSON (data/golden/deep/dr_cross_deep_XXXX.json)")
    ap.add_argument("--intent-type", required=True, choices=INTENT_TYPES,
                    help="Intent type for the task")
    ap.add_argument("--topic-yaml", default=None,
                    help="Topic YAML config (optional, for richer context)")
    ap.add_argument("--task-id", default=None,
                    help="Task ID (default: derived from golden filename)")
    ap.add_argument("--out", default=None,
                    help="Output task JSON file path (default: stdout)")
    ap.add_argument("--checklist-out", default=None,
                    help="Output checklist JSON fragment file (default: stderr)")
    args = ap.parse_args()

    # Load golden
    golden_path = Path(args.golden_json)
    if not golden_path.exists():
        print(f"[warn] golden file not found: {golden_path}; proceeding with empty metadata",
              file=sys.stderr)
        golden_meta = {}
        topic_display = "Unknown topic"
    else:
        golden = json.loads(golden_path.read_text())
        golden_meta = golden.get("metadata", {}).get("summary", {})
        topic_display = golden.get("task_id", "unknown")

    # Derive task_id
    task_id = args.task_id
    if not task_id:
        task_id = golden_path.stem  # e.g., "dr_cross_deep_0031"

    # Load topic YAML if provided
    topic_cfg = {}
    if args.topic_yaml and Path(args.topic_yaml).exists():
        topic_cfg = _load_yaml_minimal(args.topic_yaml)
        topic_display = topic_cfg.get("display_name", topic_display)

    # Load reference task and checklist for the intent type
    ref_task = _load_reference_task(args.intent_type)
    ref_checklist = _load_reference_checklist(args.intent_type)
    ref_intent = ref_task.get("intent", "")
    ref_synthesis = ref_task.get("synthesis_requirements", {})

    # Build the LLM prompt
    system = (
        "You are an expert benchmark designer for AI agent evaluation. "
        "You generate task specifications for deep-research benchmarks. "
        "Your output must be a single JSON object."
    )

    wiki_mandatory_str = ", ".join(topic_cfg.get("wiki_mandatory", []))
    shopping_kw_str = ", ".join(topic_cfg.get("shopping_keywords", []))
    reddit_forums_str = ", ".join(topic_cfg.get("reddit_forums", []))

    prompt = f"""Generate a deep-research task specification for:

Topic: {topic_display}
Topic ID: {topic_cfg.get('topic_id', task_id)}
Intent type: {args.intent_type}

Topic configuration:
- Shopping keywords: {shopping_kw_str}
- Reddit forums: {reddit_forums_str}
- Wiki mandatory articles: {wiki_mandatory_str}

Golden metadata:
- Must-cite URLs: {golden_meta.get('n_must_cite', 'N/A')}
- Expected pool URLs: {golden_meta.get('n_expected_pool', 'N/A')}

Reference task intent (same intent type, DIFFERENT topic -- adapt the pattern):
---
{ref_intent[:3000]}
---

Reference checklist (same intent type, DIFFERENT topic -- create NEW task-specific items):
{json.dumps(ref_checklist[:5], indent=2)}
... ({len(ref_checklist)} items total)

Reference synthesis_requirements:
{json.dumps(ref_synthesis, indent=2)}

Generate a JSON object with these fields:
1. "intent" - The full intent prompt string. Follow the same structure as the reference
   but adapt ALL specifics to the new topic. Must mention:
   - >= 120 sandbox URLs, >= 60 cited
   - The 3 sources: __SHOPPING__, __REDDIT__, __WIKIPEDIA__
   - Specific counts per source (products, threads, articles)
   - The mandatory wiki articles
   - Format rules (markdown links, sandbox-local, no fabrication)
   - Specific synthesis requirements matching the intent type

2. "synthesis_requirements" - A dict matching the intent type's pattern but
   adapted to the new topic. Include all relevant counts and flags.

3. "checklist" - An array of exactly 21 task-specific checklist items.
   Each item is a string question answerable as PASS/FAIL/UNCLEAR.
   Items should cover:
   - Structure requirements (items 1-6)
   - Source coverage (items 7-12)
   - Synthesis/cross-source requirements (items 13-16)
   - Format/general requirements (items 17-21)

Output ONLY the JSON object. No commentary."""

    print(f"[gen_task_spec] task_id={task_id} intent={args.intent_type} "
          f"topic={topic_display}", file=sys.stderr)
    print(f"[gen_task_spec] calling LLM...", file=sys.stderr)

    raw = _call_llm(prompt, system)
    result = _extract_json(raw)

    intent = result.get("intent", "")
    synthesis_req = result.get("synthesis_requirements", {})
    checklist = result.get("checklist", [])

    if not intent:
        print("[error] LLM did not produce an intent field", file=sys.stderr)
        return 1

    if len(checklist) != 21:
        print(f"[warn] got {len(checklist)} checklist items, expected 21", file=sys.stderr)

    # Build the full task JSON
    task_json = _build_task_json(
        task_id=task_id,
        intent=intent,
        topic_cfg=topic_cfg,
        golden_meta=golden_meta,
        synthesis_req=synthesis_req,
        ref_task=ref_task,
    )

    task_out = json.dumps(task_json, indent=2, ensure_ascii=False)
    checklist_out = json.dumps({task_id: checklist}, indent=2, ensure_ascii=False)

    # Write task JSON
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(task_out)
        print(f"[gen_task_spec] wrote task JSON to {args.out}", file=sys.stderr)
    else:
        print(task_out)

    # Write checklist
    if args.checklist_out:
        Path(args.checklist_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.checklist_out).write_text(checklist_out)
        print(f"[gen_task_spec] wrote checklist to {args.checklist_out}", file=sys.stderr)
    else:
        print(f"\n--- CHECKLIST ({len(checklist)} items) ---", file=sys.stderr)
        print(checklist_out, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
