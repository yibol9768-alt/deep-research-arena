"""Draft a `quoted_span` for every triple in a deep-tier golden file.

For each triple `(subject, predicate, object, source_url)`:
  1. Fetch source_url (must be reachable on sandbox)
  2. Extract clean text content
  3. Call DeepSeek-V4 (non-reasoning) to extract a ≤200-char span from the
     page that *most directly supports* the triple
  4. If no span is found, mark `quoted_span_needs_review = true` and leave
     a `null` span

Output is the same golden file with two new fields per triple:
  - `quoted_span`: str or null
  - `quoted_span_meta`: {source: "draft-llm", model: "...", needs_review: bool, fetched_at: "..."}

Usage:
    python3 scripts/draft_quote_spans.py \\
        --golden data/golden/deep/dr_cross_deep_0001.json \\
        --out    data/golden/deep/dr_cross_deep_0001.quotes.json

Cost estimate: ~559 triples × ~$0.005 (DS-v4-flash, ≤500 input tokens, ≤80 output) = $2.80
Wall: ~30 min (2 req/s rate-limited, with retries)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install requests beautifulsoup4")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DS_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DS_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
HTTP_TIMEOUT = 12.0
LLM_TIMEOUT = 30.0
MAX_PAGE_CHARS = 8000  # truncate page text before sending to LLM

# ─────────────────────────────────────────────────────────────────────────────
# Page fetcher
# ─────────────────────────────────────────────────────────────────────────────


def _fetch_text(url: str, retries: int = 2) -> str | None:
    """Fetch URL, return clean text content (~ first 8k chars), or None on failure."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(
                url, timeout=HTTP_TIMEOUT, allow_redirects=True,
                headers={"User-Agent": "deep-quote-drafter/1.0"},
            )
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            return text[:MAX_PAGE_CHARS]
        except Exception:
            if attempt == retries:
                return None
            time.sleep(1.0 + attempt)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# DeepSeek-V4 quote extractor
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_SYSTEM = (
    "You extract literal evidence quotes from web pages. Given a fact triple "
    "and a page's text, return ONLY a JSON object: "
    '{"span": "...", "found": true|false}. '
    'The span MUST be a verbatim substring of the page (no paraphrasing), '
    "≤ 200 characters, that most directly supports the triple. "
    'If no such span exists, return {"span": "", "found": false}. '
    "Output the JSON object and nothing else — no prose, no markdown fences."
)


def _extract_span(triple: dict, page_text: str) -> tuple[str | None, bool]:
    """Call DS-v4 to extract a ≤200-char span. Return (span_or_None, llm_returned_found_true)."""
    if not DS_KEY:
        return None, False
    user = (
        f'Triple: subject="{triple.get("subject", "")[:200]}", '
        f'predicate="{triple.get("predicate", "")}", '
        f'object="{triple.get("object", "")[:200]}"\n\n'
        f"Page text (truncated): {page_text}"
    )
    body = {
        "model": DS_MODEL,
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": user},
        ],
        "max_tokens": 250,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    try:
        r = requests.post(
            f"{DS_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {DS_KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=LLM_TIMEOUT,
        )
        if r.status_code != 200:
            return None, False
        msg = r.json()["choices"][0]["message"]
        text = msg.get("content") or ""
        if not text.strip():
            return None, False
        try:
            d = json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                return None, False
            d = json.loads(m.group(0))
        span = (d.get("span") or "").strip()
        found = bool(d.get("found"))
        if not found or not span:
            return None, False
        if len(span) > 250:
            span = span[:250]
        if span in page_text:
            return span, True
        sub = span[:60]
        if sub in page_text:
            i = page_text.index(sub)
            return page_text[i : i + len(span)], True
        return None, False
    except Exception:
        return None, False


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────


def _process_one(idx: int, triple: dict, page_cache: dict[str, str | None]) -> dict:
    url = triple.get("source_url", "") or triple.get("url", "")
    if not url:
        triple["quoted_span"] = None
        triple["quoted_span_meta"] = {
            "source": "skip", "reason": "no source_url",
            "needs_review": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return triple

    if url not in page_cache:
        page_cache[url] = _fetch_text(url)
    page_text = page_cache[url]
    if not page_text:
        triple["quoted_span"] = None
        triple["quoted_span_meta"] = {
            "source": "skip", "reason": "page_fetch_failed",
            "needs_review": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return triple

    span, llm_found = _extract_span(triple, page_text)
    triple["quoted_span"] = span
    triple["quoted_span_meta"] = {
        "source": "draft-llm",
        "model": DS_MODEL,
        "needs_review": True,
        "found": bool(span),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return triple


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None, help="cap number of triples for testing")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if not DS_KEY:
        print("DEEPSEEK_API_KEY not set", file=sys.stderr)
        return 2

    g = json.loads(Path(args.golden).read_text())
    triples = g.get("triples", [])
    if args.limit:
        triples = triples[: args.limit]
    print(f"Drafting quoted_span for {len(triples)} triples ...")

    page_cache: dict[str, str | None] = {}
    n_found = 0
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_process_one, i, t, page_cache): i for i, t in enumerate(triples)}
        for done_i, fut in enumerate(concurrent.futures.as_completed(futs)):
            r = fut.result()
            if r.get("quoted_span"):
                n_found += 1
            if (done_i + 1) % 25 == 0:
                elapsed = time.time() - t0
                print(f"  [{done_i+1}/{len(triples)}] found={n_found} elapsed={elapsed:.0f}s")

    if args.limit:
        g["triples"] = triples + g["triples"][args.limit:]
    else:
        g["triples"] = triples
    g.setdefault("metadata", {})["quote_draft"] = {
        "drafted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": DS_MODEL,
        "n_triples": len(triples),
        "n_with_span": n_found,
        "rate": round(n_found / max(1, len(triples)), 4),
        "needs_human_review": True,
    }
    Path(args.out).write_text(json.dumps(g, indent=2, ensure_ascii=False))
    print(f"\nwrote {args.out}: {n_found}/{len(triples)} triples got a span "
          f"({100.0 * n_found / max(1, len(triples)):.1f} %)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
