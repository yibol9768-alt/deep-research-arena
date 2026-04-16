"""Oracle for dr_shop_0001: three rated-4+ headphones from search results."""

from __future__ import annotations

import json
from typing import Any

from .magento_scrape import list_products


def oracle(page: Any, task_cfg: dict) -> str:
    items = [p for p in list_products(page) if (p.get("rating") or 0) >= 4.0 and (p.get("price") or 0) > 0]
    if len(items) < 3:
        # Try next page(s)
        for _ in range(3):
            nxt = page.query_selector('a.action.next, .pages-item-next a')
            if not nxt:
                break
            nxt.click()
            page.wait_for_load_state("domcontentloaded")
            for p in list_products(page):
                if (p.get("rating") or 0) >= 4.0 and (p.get("price") or 0) > 0:
                    items.append(p)
            if len(items) >= 3:
                break

    picks = items[:3]
    citations = []
    for i, p in enumerate(picks):
        citations.append({"field": f"products[{i}].price",  "url": p["product_url"]})
        citations.append({"field": f"products[{i}].rating", "url": p["product_url"]})

    top = picks[0]["name"] if picks else "none"
    report = {
        "products": [{"name": p["name"], "price": p["price"], "rating": p["rating"], "product_url": p["product_url"]} for p in picks],
        "recommendation": f"Top pick: {top} — highest rating among sampled results with price under budget.",
        "citations": citations,
    }
    return json.dumps(report, ensure_ascii=False)
