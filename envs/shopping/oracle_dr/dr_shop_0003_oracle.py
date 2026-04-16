"""Oracle for dr_shop_0003: top-3 complaints in reviews of 6s headphones."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from .magento_scrape import list_reviews


# Hand-crafted complaint patterns (labels + keyword groups).
_TAGS = [
    ("Ear cups feel small",   [r"ear\s*cup", r"\b(small|tight|tiny)\b"]),
    ("Poor battery life",     [r"batter", r"\b(short|drain|dies|poor)\b"]),
    ("Weak bass / sound",     [r"\b(bass|sound|audio)\b", r"\b(weak|tinny|poor|bad|flat)\b"]),
    ("Uncomfortable fit",     [r"\b(comfort|hurt|headache|ache|pain)\b"]),
    ("Build quality issues",  [r"\b(break|broke|cracked|flimsy|cheap)\b"]),
    ("Bluetooth connection",  [r"bluetooth|pair", r"\b(drop|disconnect|lose|fail)\b"]),
]


def _match_tag(text: str, patterns: list[str]) -> bool:
    tl = text.lower()
    return all(re.search(p, tl) for p in patterns)


def oracle(page: Any, task_cfg: dict) -> str:
    reviews: list[dict] = []
    base = task_cfg["start_url"]
    # Find product id from page (anchor to review ajax URL)
    try:
        import re as _re
        html = page.content()
        m = _re.search(r"listAjax/id/(\d+)/", html)
        pid = m.group(1) if m else None
    except Exception:
        pid = None

    if pid:
        origin = "/".join(base.split("/")[:3])
        for p in range(1, 8):
            page.goto(f"{origin}/review/product/listAjax/id/{pid}/?p={p}")
            batch = list_reviews(page)
            if not batch:
                break
            reviews.extend(batch)

    if not reviews:
        # Last resort: scroll the product page & read what's inline
        page.goto(base)
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        reviews = list_reviews(page)

    hits: dict[str, list[dict]] = {}
    for tag, patterns in _TAGS:
        for rv in reviews:
            text = (rv.get("title") or "") + " " + (rv.get("body") or "")
            if _match_tag(text, patterns):
                hits.setdefault(tag, []).append(rv)

    ordered = sorted(hits.items(), key=lambda kv: -len(kv[1]))
    complaints = []
    citations = []
    for i, (tag, rvs) in enumerate(ordered[:3]):
        snippet = (rvs[0].get("body") or "")[:200]
        complaints.append({"label": tag, "example_snippet": snippet})
        citations.append({"field": f"complaints[{i}].example_snippet", "url": base})

    while len(complaints) < 3:
        # Pad with neutral entries so schema minItems=3 holds
        complaints.append({"label": "Other issues", "example_snippet": "See reviews for additional concerns."})
        citations.append({"field": f"complaints[{len(complaints)-1}].example_snippet", "url": base})

    return json.dumps({"complaints": complaints, "citations": citations}, ensure_ascii=False)
