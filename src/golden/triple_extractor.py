"""LLM-based (subject, predicate, object) extractor from a markdown research report.

Used for the *precision* side of fact_kg scoring: given the agent's markdown,
enumerate the atomic factual claims it makes, then hand each to a TripleStore
for DB verification.

Contract:
  extract_triples(markdown, site) -> list[dict]
  where each dict has keys {subject, predicate, object}.

  The predicate vocabulary is pinned to the set used in v3 golden files
  (see db_schema_map.PREDICATES) so extraction stays in-domain.

We use the same Zhipu Anthropic-compat endpoint as LLMJudgeVerifier. Output
is a JSON array inside a ```json fence.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .db_schema_map import PREDICATES


EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", "glm-5.1")


def _predicates_for(site: str) -> list[str]:
    return [p for p, spec in PREDICATES.items() if spec.site == site]


_EXTRACTOR_SYSTEM_TMPL = """You extract atomic factual claims from a research report as (subject, predicate, object) triples.

Site: {site}
Allowed predicates (do NOT invent others): {predicates}

Rules:
  - One claim per triple. If the report says "Product A costs $30", emit {{"subject":"Product A","predicate":"price","object":"30"}}.
  - Strip currency symbols, 'stars', 'reviews' from the object (raw number only).
  - For {site}-shopping, `subject` is the PRODUCT NAME exactly as written. For {site}-reddit, `subject` is a POST TITLE (for score/comment_count/forum/post_title) or a USERNAME (for author). Aggregate predicates (avg_*, n_*, median_*) may use 'forum:<name>' or 'author:<name>' as subject.
  - Ignore opinion / qualitative text. Only numeric / categorical facts tied to the allowed predicates.
  - Skip claims where you cannot identify both subject and object with high confidence.

Output: a JSON array in a ```json fence, and NOTHING after the closing fence.
Each element: {{"subject": "...", "predicate": "...", "object": "..."}}
Emit [] if no verifiable claims are present.
"""


def _build_client():
    try:
        import anthropic  # type: ignore
    except Exception:
        return None, "anthropic SDK not installed"
    os.environ.setdefault("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        return None, "set ANTHROPIC_AUTH_TOKEN"
    return anthropic.Anthropic(), None


def _parse_array(text: str) -> list[dict]:
    fenced = re.findall(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    for candidate in reversed(fenced):
        try:
            arr = json.loads(candidate)
            if isinstance(arr, list):
                return [t for t in arr if isinstance(t, dict)]
        except Exception:
            continue
    # Last resort: any top-level array
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return [t for t in arr if isinstance(t, dict)]
        except Exception:
            pass
    return []


def extract_triples(
    markdown: str,
    *,
    site: str,
    model: str | None = None,
    max_tokens: int = 3000,
) -> tuple[list[dict], str]:
    """Return (triples, raw_llm_text). Triples are [{subject, predicate, object}, ...].

    If the LLM is unavailable, returns ([], error_message).
    """
    preds = _predicates_for(site)
    if not preds:
        return [], f"no predicates registered for site={site}"

    client, err = _build_client()
    if client is None:
        return [], f"extractor client unavailable: {err}"

    sys_msg = _EXTRACTOR_SYSTEM_TMPL.format(
        site=site,
        predicates=", ".join(sorted(preds)),
    )
    user_msg = (
        "Extract verifiable triples from the research report below.\n\n"
        "---BEGIN REPORT---\n"
        f"{(markdown or '')[:8000]}\n"
        "---END REPORT---\n\n"
        "Emit the JSON array now."
    )

    try:
        resp = client.messages.create(
            model=model or EXTRACT_MODEL,
            max_tokens=max_tokens,
            system=sys_msg,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = ""
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text += block.text
    except Exception as e:
        return [], f"extractor call failed: {type(e).__name__}: {e}"

    arr = _parse_array(text)
    # Keep only well-formed triples with in-domain predicates.
    out = []
    allowed = set(preds)
    for t in arr:
        if not isinstance(t, dict):
            continue
        s = (t.get("subject") or "").strip()
        p = (t.get("predicate") or "").strip()
        o = t.get("object")
        if p not in allowed or not s or o is None:
            continue
        out.append({"subject": s, "predicate": p, "object": str(o)})
    return out, text
