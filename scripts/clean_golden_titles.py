"""Re-extract product titles from URLs and filter non-audio noise from
a deep-tier golden file.

The original scraper had two bugs:
  (1) When the page-title CSS selector matched a Magento "rating widget"
      (showing e.g. "87%") instead of the real <h1>, the triple's
      `subject` was set to "87%" instead of the product name.
  (2) Some products (e.g. "Ear Piercing Gun") slipped past the
      keyword-search filter just because the URL contained "ear".

This script:
  - For each unique URL referenced by a triple, fetches it via the local
    SSH tunnel to westd, extracts the real `<title>` tag.
  - Replaces every triple's `subject` field with the real title.
  - Drops triples whose URL or title is unambiguously NOT audio-related.
  - Re-points `must_cite_urls` and `expected_pool_urls` to keep only
    surviving URLs.

Output: a NEW file `<golden>.cleaned.json`. Original is preserved.

Usage:
    python3 scripts/clean_golden_titles.py \\
        --golden data/golden/deep/dr_cross_deep_0001.json \\
        --out    data/golden/deep/dr_cross_deep_0001.cleaned.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install requests beautifulsoup4")


# ─────────────────────────────────────────────────────────────────────────────
# Filters
# ─────────────────────────────────────────────────────────────────────────────

# Keep a triple ONLY if the URL slug or product title matches one of these.
# Order matters: we positive-match first, then negative-match exclusions.
AUDIO_POSITIVE = re.compile(
    r"\b(?:"
    r"headphone|headphones|headset|headsets|"
    r"earbud|earbuds|earphone|earphones|earpods|airpods|"
    r"speaker|speakers|soundbar|subwoofer|"
    r"microphone|microphones|"
    r"wireless\s*audio|bluetooth\s*audio|gaming\s*audio|"
    r"audio\s*(?:transmitter|adapter|receiver|jack|cable|interface)|"
    r"in[- ]?ear|over[- ]?ear|on[- ]?ear|"
    r"3\.5\s*mm|aux\b|aux\s*cable|"
    r"walkman|cassette|"
    r"dac\b|amp\b|"
    r"audiophile"
    r")\b",
    re.IGNORECASE,
)

AUDIO_NEGATIVE = re.compile(
    r"\b(?:"
    r"piercing|"
    r"earring|"
    r"ear\s*hook(?!\s*(?:headphone|earbud|earphone))|"
    r"ear\s*stud|"
    r"ear\s*muff|"
    r"ear\s*plug|"
    r"ear\s*cushion|"
    r"hearing\s*aid|"
    r"speakerphone\s*for\s*car|"
    r"phone\s*case|"
    r"phone\s*holder|"
    r"phone\s*charger|"
    r"watch\s*charger|"
    r"laptop\s*stand"
    r")\b",
    re.IGNORECASE,
)


def _is_audio(url: str, title: str) -> tuple[bool, str]:
    """Return (keep, reason)."""
    text = f"{url} {title}"
    if AUDIO_NEGATIVE.search(text):
        return False, f"negative_filter ({AUDIO_NEGATIVE.search(text).group(0)})"
    if AUDIO_POSITIVE.search(text):
        return True, "audio_positive"
    return False, "not_audio_keyword"


# ─────────────────────────────────────────────────────────────────────────────
# Title fetcher
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_title(url: str, timeout: float = 10.0) -> str | None:
    if "7770" not in url:
        # only shopping URLs need title-cleanup; reddit and kiwix already have
        # readable subjects (forum, article title)
        return None
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True,
                         headers={"User-Agent": "title-cleaner/1.0"})
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # try the canonical title sources in order
        for sel in [
            "span[itemprop='name']",
            "h1.page-title span",
            ".page-title-wrapper h1",
            "title",
        ]:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True)
                if t and not re.fullmatch(r"\d{1,3}\s*%", t):
                    return t[:200]
        return None
    except Exception:
        return None


def _slug_to_title(url: str) -> str:
    last = url.rstrip("/").rsplit("/", 1)[-1].replace(".html", "")
    return last.replace("-", " ").replace("_", " ").strip().title()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    g = json.loads(Path(args.golden).read_text())
    triples = g.get("triples", [])
    must_cite = g.get("must_cite_urls", [])
    pool = g.get("expected_pool_urls", [])

    # collect unique URLs
    urls = sorted({t.get("source_url", "") for t in triples if t.get("source_url")})
    print(f"unique URLs in triples: {len(urls)}")

    print(f"fetching titles ({args.workers} workers)...")
    titles: dict[str, str | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_fetch_title, u): u for u in urls if "7770" in u}
        for i, fut in enumerate(concurrent.futures.as_completed(futs)):
            u = futs[fut]
            titles[u] = fut.result()
            if (i + 1) % 25 == 0:
                print(f"  [{i+1}/{len(futs)}]")

    # urls without 7770 (reddit/wiki) keep their original subject
    print(f"got {sum(1 for v in titles.values() if v)} real titles")

    # decide keep/drop per URL
    keep_url: dict[str, tuple[bool, str, str]] = {}
    for u in urls:
        title = titles.get(u) or _slug_to_title(u)
        if "7770" in u:
            keep, reason = _is_audio(u, title)
        else:
            keep, reason = True, "non_shopping_pass"
        keep_url[u] = (keep, reason, title)

    n_keep = sum(1 for k, _, _ in keep_url.values() if k)
    n_drop = len(keep_url) - n_keep
    print(f"keep {n_keep} URLs / drop {n_drop} URLs (non-audio)")

    # rebuild triples
    new_triples = []
    drops_per_predicate = {}
    for t in triples:
        u = t.get("source_url", "")
        keep, reason, title = keep_url.get(u, (False, "no_url", ""))
        if not keep:
            drops_per_predicate[t.get("predicate", "?")] = drops_per_predicate.get(t.get("predicate", "?"), 0) + 1
            continue
        # patch subject to real title for shopping triples; leave reddit/wiki alone
        if "7770" in u:
            t = dict(t)
            t["subject"] = title
        new_triples.append(t)

    print(f"triples kept: {len(new_triples)} / {len(triples)}")
    print(f"dropped per predicate: {drops_per_predicate}")

    def _decide_url_for_list(u: str, category: str = "") -> bool:
        # Triple-derived URLs: use the per-URL decision we already made
        if u in keep_url:
            return keep_url[u][0]
        # Anything not a Magento product URL passes through (reddit thread,
        # wiki article, forum index, search-result page, etc.)
        if "7770" not in u:
            return True
        # Shopping search-result pages (?q= or /catalogsearch/) — keep, they
        # are part of the agent's expected browsing trace
        if "catalogsearch" in u or "?q=" in u:
            return True
        # Bare product URL we never visited; apply audio filter on the slug
        slug_title = _slug_to_title(u)
        keep, _ = _is_audio(u, slug_title)
        return keep

    new_must = [e for e in must_cite if _decide_url_for_list(e["url"], e.get("category", ""))]
    new_pool = [e for e in pool if _decide_url_for_list(e["url"], e.get("category", ""))]
    print(f"must_cite kept: {len(new_must)} / {len(must_cite)}")
    print(f"pool kept:      {len(new_pool)} / {len(pool)}")

    # write
    g["triples"] = new_triples
    g["must_cite_urls"] = new_must
    g["expected_pool_urls"] = new_pool
    g.setdefault("metadata", {})["title_cleanup"] = {
        "n_triples_dropped":  len(triples) - len(new_triples),
        "n_must_dropped":     len(must_cite) - len(new_must),
        "n_pool_dropped":     len(pool) - len(new_pool),
        "drops_per_predicate": drops_per_predicate,
    }

    Path(args.out).write_text(json.dumps(g, indent=2, ensure_ascii=False))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
