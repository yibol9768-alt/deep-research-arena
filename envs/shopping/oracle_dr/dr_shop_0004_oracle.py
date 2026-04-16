"""Oracle for dr_shop_0004: two most-reviewed shampoos + price/rating ratio."""

from __future__ import annotations

import json
from typing import Any

from .magento_scrape import list_products, product_details


def oracle(page: Any, task_cfg: dict) -> str:
    items = list_products(page)[:10]
    # For each, visit its page to get review_count
    enriched: list[dict] = []
    for it in items:
        url = it.get("product_url")
        if not url:
            continue
        page.goto(url)
        page.wait_for_load_state("domcontentloaded")
        d = product_details(page)
        it_full = {**it, **{k: v for k, v in d.items() if v is not None}}
        enriched.append(it_full)
    enriched.sort(key=lambda p: -(p.get("review_count") or 0))
    top = [p for p in enriched if p.get("review_count") and p.get("price")][:2]

    if len(top) < 2:
        # Fallback: use first two with price even without review_count
        top = [p for p in enriched if p.get("price")][:2]
        for p in top:
            p.setdefault("review_count", 1)

    def ratio(p):
        r = p.get("rating") or 0.0001
        return round((p.get("price") or 0) / r, 2)

    better = top[0]["name"] if ratio(top[0]) <= ratio(top[1]) else top[1]["name"]
    report = {
        "products": [
            {
                "name": p["name"],
                "price": p["price"],
                "rating": p.get("rating") or 0,
                "review_count": p.get("review_count") or 1,
                "product_url": p["product_url"],
            }
            for p in top
        ],
        "better_value": better,
        "ratio_summary": f"price/star: {top[0]['name']}={ratio(top[0])}, {top[1]['name']}={ratio(top[1])}",
        "citations": [
            {"field": "products[0].price",        "url": top[0]["product_url"]},
            {"field": "products[0].review_count", "url": top[0]["product_url"]},
            {"field": "products[1].price",        "url": top[1]["product_url"]},
            {"field": "products[1].review_count", "url": top[1]["product_url"]},
        ],
    }
    return json.dumps(report, ensure_ascii=False)
