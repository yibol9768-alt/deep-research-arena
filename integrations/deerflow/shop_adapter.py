"""Adapter that retargets DeerFlow's researcher from open web → our shopping sandbox.

Monkey-patches `get_web_search_tool` and `crawl_tool` to LangChain tools
that query the local Magento shopping site (http://localhost:7770/) via
plain HTTP + BeautifulSoup. No Playwright needed.

Usage:
    SHOPPING=http://localhost:7770 python shop_adapter.py dr_shop_0001
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

SHOPPING = os.environ.get("SHOPPING", "http://localhost:7770").rstrip("/")


def _fetch(url: str) -> str:
    try:
        r = requests.get(url, timeout=30, allow_redirects=True)
        return r.text if r.status_code < 400 else ""
    except Exception as e:
        return f"ERROR: {e}"


def _scrape_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for el in soup.select("li.item.product.product-item, .products-grid .product-item")[:20]:
        a = el.select_one("a.product-item-link, .product-item-name a")
        name = a.get_text(strip=True) if a else ""
        url = a.get("href", "") if a else ""
        price = None
        pEl = el.select_one("[data-price-amount]")
        if pEl and pEl.get("data-price-amount"):
            try:
                price = float(pEl["data-price-amount"])
            except Exception:
                pass
        rating = None
        r = el.select_one(".rating-result")
        if r:
            title = r.get("title") or ""
            sp = r.select_one("span")
            if sp and sp.get("title"):
                title = sp["title"]
            m = re.search(r"(\d+)%", title or "")
            if m:
                rating = round(int(m.group(1)) / 20, 1)
        items.append({"name": name, "url": url, "price": price, "rating": rating})
    return items


def _scrape_product(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {}
    t = soup.select_one("h1.page-title .base, .page-title .base")
    out["name"] = t.get_text(strip=True) if t else ""
    pEl = soup.select_one("[data-price-amount]")
    out["price"] = float(pEl["data-price-amount"]) if pEl and pEl.get("data-price-amount") else None
    r = soup.select_one(".rating-result")
    if r:
        title = r.get("title") or ""
        sp = r.select_one("span")
        if sp and sp.get("title"):
            title = sp["title"]
        m = re.search(r"(\d+)%", title or "")
        out["rating"] = round(int(m.group(1)) / 20, 1) if m else None
    else:
        out["rating"] = None
    rc = soup.select_one(".reviews-actions a, .review-count, a[href*='#reviews']")
    if rc:
        m = re.search(r"(\d+)", rc.get_text(" ", strip=True))
        out["review_count"] = int(m.group(1)) if m else None
    # Find product id from AJAX hint
    m = re.search(r"listAjax/id/(\d+)/", html)
    out["product_id"] = m.group(1) if m else None
    return out


@tool
def shop_search(query: str) -> str:
    """Search the shopping site for products matching `query`. Returns up to 20 items with name, url, price, rating."""
    url = f"{SHOPPING}/catalogsearch/result/?q={urllib.parse.quote(query)}"
    html = _fetch(url)
    items = _scrape_listing(html)
    return json.dumps({"search_url": url, "count": len(items), "items": items}, ensure_ascii=False)


@tool
def shop_browse(url: str) -> str:
    """Fetch a shopping-site URL. If it's a category / listing page, returns product items. If it's a product page, returns product details."""
    if "://" not in url:
        url = f"{SHOPPING}{'' if url.startswith('/') else '/'}{url}"
    if SHOPPING not in url:
        return json.dumps({"error": f"URL outside shopping domain: {url}"})
    html = _fetch(url)
    if not html:
        return json.dumps({"error": "empty response", "url": url})
    # Heuristic: product page has h1.page-title + product-view; else listing
    if "product-info-main" in html or "catalog-product-view" in html:
        return json.dumps({"kind": "product", "url": url, **_scrape_product(html)}, ensure_ascii=False)
    items = _scrape_listing(html)
    return json.dumps({"kind": "listing", "url": url, "count": len(items), "items": items}, ensure_ascii=False)


@tool
def shop_reviews(product_id: str, max_pages: int = 3) -> str:
    """Fetch reviews for a product by its numeric product_id (found via shop_browse on a product page)."""
    reviews = []
    for p in range(1, int(max_pages) + 1):
        html = _fetch(f"{SHOPPING}/review/product/listAjax/id/{product_id}/?p={p}")
        if not html or "review-item" not in html:
            break
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select(".review-item, li.item.review-item"):
            author = el.select_one(".review-details-value, [itemprop='author'], .review-author strong, .review-author")
            body = el.select_one(".review-content, [itemprop='description'], .review-body")
            title = el.select_one(".review-title")
            rating = None
            ratEl = el.select_one(".rating-result [title]")
            if ratEl:
                m = re.search(r"(\d+)%", ratEl.get("title") or "")
                if m:
                    rating = int(m.group(1)) // 20
            reviews.append({
                "author": author.get_text(strip=True) if author else "",
                "title": title.get_text(strip=True) if title else "",
                "body": body.get_text(" ", strip=True) if body else "",
                "rating": rating,
            })
    return json.dumps({"count": len(reviews), "reviews": reviews}, ensure_ascii=False)


# ---------- Monkey patch DeerFlow's tool factory ----------

def install_shop_tools() -> None:
    """Replace DeerFlow's web_search / crawl tools with our shop_* tools."""
    import src.tools.search as search_mod
    import src.tools.crawl as crawl_mod
    import src.graph.nodes as nodes_mod

    def _fake_get_web_search(*_a, **_kw):
        return shop_search

    search_mod.get_web_search_tool = _fake_get_web_search
    nodes_mod.get_web_search_tool = _fake_get_web_search

    # crawl_tool is imported directly in nodes; overwrite the attr
    nodes_mod.crawl_tool = shop_browse
    crawl_mod.crawl_tool = shop_browse


async def run_dr_task(task_id: str):
    install_shop_tools()

    from src.graph import build_graph
    from src.config.configuration import get_recursion_limit

    task_path = Path(__file__).resolve().parents[2] / "data" / "tasks" / "deep_research" / "shopping" / f"{task_id}.json"
    cfg = json.loads(task_path.read_text())

    prompt = (
        cfg["intent"]
        + "\n\nReport MUST be a single JSON object matching this schema:\n"
        + json.dumps(cfg["report_schema"], ensure_ascii=False, indent=2)
        + "\n\nAll product-page URLs must start with "
        + SHOPPING
        + "/ . Include a `citations` array with "
        "{field, url} entries for every price and rating you claim. "
        "Use the shop_search and shop_browse tools; do NOT browse the open web."
    )

    graph = build_graph()

    initial_state = {
        "messages": [{"role": "user", "content": prompt}],
        "auto_accepted_plan": True,
        "enable_background_investigation": False,
        "research_topic": prompt,
        "clarified_research_topic": prompt,
        "enable_clarification": False,
    }
    config = {
        "configurable": {
            "thread_id": f"dr-{task_id}",
            "max_plan_iterations": 1,
            "max_step_num": 4,
            # Explicitly empty MCP — we supply tools via monkey-patch
            "mcp_settings": {"servers": {}},
        },
        "recursion_limit": get_recursion_limit(default=60),
    }

    final_state = None
    async for s in graph.astream(input=initial_state, config=config, stream_mode="values"):
        final_state = s
        msgs = s.get("messages") or []
        if msgs:
            last = msgs[-1]
            role = getattr(last, "type", "") or getattr(last, "role", "")
            name = getattr(last, "name", "") or ""
            content = getattr(last, "content", "")
            preview = content if isinstance(content, str) else str(content)
            print(f"\n--- [{role}/{name}] ---\n{preview[:800]}")

    if final_state:
        print("\n====== FINAL REPORT ======")
        rep = final_state.get("final_report") or final_state.get("reporter_output") or ""
        print((rep or "")[:3000])
        # Save
        out = Path(__file__).resolve().parents[2] / "data" / "results" / f"deerflow_{task_id}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rep or "(no final_report)", encoding="utf-8")
        print(f"\nsaved: {out}")


if __name__ == "__main__":
    task_id = sys.argv[1] if len(sys.argv) > 1 else "dr_shop_0001"
    asyncio.run(run_dr_task(task_id))
