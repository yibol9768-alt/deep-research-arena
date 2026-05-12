#!/usr/bin/env python3
"""Generate topic candidate YAML files for deep-tier task scaling.

Uses DeepSeek V4 flash (via OPENAI_BASE_URL / OPENAI_API_KEY) to propose
5 topic candidates for a given domain and intent type.  Output matches the
format used in configs/deep_topics/*.yaml.

Usage:
    OPENAI_BASE_URL=http://westd:8088/v1 OPENAI_API_KEY=sk-... \
    python3 scripts/gen_topic_candidates.py \
        --domain "Consumer electronics" \
        --intent-type Recommendation \
        --out candidates.yaml

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


def _load_reference_yaml() -> str:
    """Load a reference YAML from the repo to show the LLM the format."""
    ref = ROOT / "configs" / "deep_topics" / "0001_audio_headphones.yaml"
    if ref.exists():
        return ref.read_text()
    # Fallback: inline minimal example
    return (
        "topic_id: audio_headphones\n"
        "task_id: dr_cross_deep_0001\n"
        "display_name: Consumer-grade audio headphones\n\n"
        "shopping_keywords:\n  - headphones\n  - earbuds\n  ...\n\n"
        "reddit_forums: [technology, gadgets, AskReddit, headphones, ...]\n"
        "reddit_keywords: [headphones, earbuds, bluetooth, ...]\n\n"
        "wiki_mandatory:\n  - Active noise control\n  - Bluetooth\n  ...\n\n"
        "wiki_extra:\n  - Sound\n  - Acoustics\n  ...\n"
    )


def _call_llm(prompt: str, system: str) -> str:
    """Call the LLM via OpenAI-compatible endpoint. Returns raw text."""
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
        temperature=0.7,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content or ""


def _extract_json(text: str) -> list:
    """Extract JSON array from LLM output, stripping markdown fences."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json|yaml|YAML)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # Try parsing as JSON array
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    # Try extracting the first JSON array
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # Last resort: try to find individual JSON objects
    objects = []
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL):
        try:
            objects.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue
    if objects:
        return objects

    sys.exit(f"Could not parse LLM output as JSON:\n{text[:500]}")


def _json_to_yaml(topics: list) -> str:
    """Convert topic candidate list to multi-document YAML string."""
    lines = []
    for i, t in enumerate(topics):
        if i > 0:
            lines.append("---")
        lines.append(f"topic_id: {t['topic_id']}")
        lines.append(f"# task_id: TBD  (assign when promoting to real task)")
        lines.append(f"display_name: {t['display_name']}")
        lines.append("")

        lines.append("shopping_keywords:")
        for kw in t.get("shopping_keywords", []):
            lines.append(f"  - {kw}")
        lines.append("")

        forums = t.get("reddit_forums", [])
        kws = t.get("reddit_keywords", [])
        lines.append(f"reddit_forums: [{', '.join(forums)}]")
        # Quote keywords containing spaces
        formatted_kws = []
        for k in kws:
            if " " in k:
                formatted_kws.append(f'"{k}"')
            else:
                formatted_kws.append(k)
        lines.append(f"reddit_keywords: [{', '.join(formatted_kws)}]")
        lines.append("")

        lines.append("wiki_mandatory:")
        for w in t.get("wiki_mandatory", []):
            lines.append(f"  - {w}")
        lines.append("")

        lines.append("wiki_extra:")
        for w in t.get("wiki_extra", []):
            lines.append(f"  - {w}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate topic candidates for deep-tier tasks")
    ap.add_argument("--domain", required=True,
                    help="Topic domain, e.g. 'Consumer electronics', 'Health/safety', 'Finance'")
    ap.add_argument("--intent-type", required=True, choices=INTENT_TYPES,
                    help="Intent type for the task")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: stdout)")
    ap.add_argument("--count", type=int, default=5,
                    help="Number of topic candidates to generate (default: 5)")
    args = ap.parse_args()

    ref_yaml = _load_reference_yaml()

    system = (
        "You are an expert benchmark designer for AI agent evaluation. "
        "You design deep-research tasks that require agents to search across "
        "three sandbox sources: an e-commerce site (shopping), a Reddit-like forum, "
        "and a Wikipedia mirror. Each task must be grounded in >= 120 sandbox URLs."
    )

    prompt = f"""Generate {args.count} NEW topic candidates for a deep-research benchmark task.

Domain: {args.domain}
Intent type: {args.intent_type}

For EACH topic, produce a JSON object with these exact fields:
- "topic_id": lowercase_snake_case identifier (e.g. "wireless_earbuds")
- "display_name": human-readable name (e.g. "Wireless earbuds for running")
- "shopping_keywords": array of exactly 9 search keywords for the e-commerce sandbox
  (these must be realistic product search terms that would yield results on a general-purpose online store)
- "reddit_forums": array of exactly 8 subreddit/forum names (without /f/ prefix)
  (pick from plausible Postmill forum names: technology, gadgets, AskReddit, Fitness, etc.)
- "reddit_keywords": array of exactly 8 search keywords for forum search
- "wiki_mandatory": array of exactly 10 Wikipedia article titles that MUST appear
  (use exact Wikipedia article titles — capitalize properly, include disambiguation if needed)
- "wiki_extra": array of exactly 15 additional Wikipedia articles for broader coverage

Requirements:
- Topics must be DIVERSE — no two should overlap significantly
- Shopping keywords must be specific enough to find relevant products
- Wiki articles must use real Wikipedia titles (exact casing matters)
- Reddit forums should include at least 2 general forums (AskReddit, LifeProTips, etc.)
  and at least 4 domain-specific forums
- Each topic should be rich enough to support a 3500-8000 word report with 60+ citations

Reference YAML format (existing topic):
```yaml
{ref_yaml}
```

Output ONLY a JSON array of {args.count} objects. No commentary outside the JSON."""

    print(f"[gen_topic_candidates] domain={args.domain!r} intent={args.intent_type} "
          f"count={args.count}", file=sys.stderr)
    print(f"[gen_topic_candidates] calling LLM...", file=sys.stderr)

    raw = _call_llm(prompt, system)
    topics = _extract_json(raw)

    if len(topics) < args.count:
        print(f"[warn] got {len(topics)} topics, expected {args.count}", file=sys.stderr)

    yaml_out = _json_to_yaml(topics)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(yaml_out)
        print(f"[gen_topic_candidates] wrote {args.out} ({len(topics)} topics)", file=sys.stderr)
    else:
        print(yaml_out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
