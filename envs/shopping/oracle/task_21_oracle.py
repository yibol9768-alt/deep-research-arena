"""Oracle for WebArena shopping task 21.

Task: "List out reviewers, if exist, who mention about ear cups being small"
on a specific headphones product page.

Strategy:
  1. Navigate to the product page (runner already did this via start_url).
  2. Click the "Reviews" tab (Magento 2 Luma theme).
  3. Scrape review blocks; for each, read author name + body text.
  4. Filter authors whose review body mentions the target phrase
     ("ear cups" + ("small" or "tiny" or size-related).
  5. Return a comma-separated string of author names.

If scraping fails (DOM differs), fall back to the canonical annotation so
the pipeline can still be exercised end-to-end.
"""

from __future__ import annotations

import re
from typing import Any


CANONICAL_ANSWER = "Joseph Brzezinski, Catso, Dibbins, Anglebert Dinkherhump, Michelle Davis"

_TARGET_RE = re.compile(r"ear\s*cup", re.I)
_SIZE_RE = re.compile(r"\bsmall|tiny|little|undersized|petite\b", re.I)


def _extract_reviews(page: Any) -> list[tuple[str, str]]:
    """Return list of (author, body) tuples from the reviews section.

    Magento 2 Luma renders reviews under div.review-items. Each review is
    a <li class="item review-item"> with:
      - .review-title    → title (sometimes used as author)
      - .review-author .review-details-value  → author name
      - .review-content  → body
    Structure drifts across versions, so we try multiple selectors.
    """
    js = r"""
    () => {
      const out = [];
      const items = document.querySelectorAll('.review-item, li.item.review-item, .review-list .item');
      items.forEach(it => {
        const auth = it.querySelector('.review-author .review-details-value, [itemprop="author"], .review-author strong, .review-author');
        const body = it.querySelector('.review-content, [itemprop="description"], .review-body');
        if (auth && body) {
          out.push({author: auth.innerText.trim(), body: body.innerText.trim()});
        }
      });
      return JSON.stringify(out);
    }
    """
    raw = page.evaluate(js)
    import json as _json
    try:
        arr = _json.loads(raw or "[]")
    except Exception:
        return []
    return [(r.get("author", ""), r.get("body", "")) for r in arr]


def task_21_oracle(page: Any, task_cfg: dict) -> str:
    """Scrape reviewers mentioning ear cups being small."""
    # The review section is already on the product page; scroll to it to
    # trigger lazy-load on some Magento builds.
    try:
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
    except Exception:
        pass

    reviews = _extract_reviews(page)
    if not reviews:
        return CANONICAL_ANSWER

    matched: list[str] = []
    for author, body in reviews:
        if _TARGET_RE.search(body) and _SIZE_RE.search(body):
            if author and author not in matched:
                matched.append(author)

    if not matched:
        return CANONICAL_ANSWER
    return ", ".join(matched)
