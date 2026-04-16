"""Oracle for dr_shop_0002: three cheapest shampoos rated >= 3."""

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

    eligible = [p for p in all_items if (p.get("rating") or 0) >= 3.0 and (p.get("price") or 0) > 0]
    eligible.sort(key=lambda p: p["price"])
    picks = eligible[:3]
    citations = [{"field": f"products[{i}].price", "url": p["product_url"]} for i, p in enumerate(picks)]
    report = {
        "products": [{"name": p["name"], "price": p["price"], "rating": p["rating"], "product_url": p["product_url"]} for p in picks],
        "citations": citations,
    }
    return json.dumps(report, ensure_ascii=False)
