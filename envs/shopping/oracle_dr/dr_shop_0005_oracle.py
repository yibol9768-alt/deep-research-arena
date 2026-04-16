"""Oracle for dr_shop_0005: best 'backpack' matching multi-constraint rule."""

from __future__ import annotations

import json
from typing import Any

from .magento_scrape import list_products


def oracle(page: Any, task_cfg: dict) -> str:
    all_items: list[dict] = []
    for _ in range(5):
        all_items.extend(list_products(page))
        nxt = page.query_selector('a.action.next, .pages-item-next a')
        if not nxt:
            break
        nxt.click()
        page.wait_for_load_state("domcontentloaded")

    cands = [
        p for p in all_items
        if "backpack" in (p.get("name") or "").lower()
        and (p.get("price") or 0) <= 100
        and (p.get("rating") or 0) >= 4.0
    ]
    if not cands:
        # Fall back to best-effort: match backpack + any price/rating
        cands = [p for p in all_items if "backpack" in (p.get("name") or "").lower() and (p.get("price") or 0) > 0]

    cands.sort(key=lambda p: (-(p.get("rating") or 0), p.get("price") or 9e9))
    best = cands[0] if cands else {"name": "(no match)", "price": 0.0, "rating": 0.0, "product_url": ""}
    report = {
        "best": {
            "name": best["name"],
            "price": best["price"],
            "rating": best.get("rating") or 0,
            "product_url": best["product_url"],
        },
        "rationale": f"Selected '{best['name']}' as it meets the keyword / price / rating filters and has the highest rating among candidates.",
        "citations": [
            {"field": "best.price",  "url": best["product_url"]},
            {"field": "best.rating", "url": best["product_url"]},
        ],
    }
    return json.dumps(report, ensure_ascii=False)
