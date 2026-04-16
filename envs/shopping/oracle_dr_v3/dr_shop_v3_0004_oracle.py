"""Oracle for dr_shop_v3_0004 — bluetooth headphone common quality issues report."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from envs.shopping.oracle_dr.magento_scrape import list_products, product_details, list_reviews
from ._common import write_golden, md_link


_THEMES = [
    ("Battery life",       [r"batter", r"\b(short|drain|dies|hour)\b"]),
    ("Build quality",      [r"\b(broke|cracked|flimsy|cheap|durab)\b"]),
    ("Sound / bass",       [r"\b(bass|sound|audio|tinny|muffled|distort)\b"]),
    ("Bluetooth / pairing", [r"bluetooth|pair|connect", r"\b(drop|disconnect|fail|lose)\b"]),
    ("Comfort / fit",      [r"\b(uncomfort|painful|tight|hurt|headache|fit)\b"]),
    ("Microphone",         [r"\b(microphone|mic|call)\b", r"\b(bad|poor|fail|terrible|low)\b"]),
]


def _matches(text: str, patterns: list[str]) -> bool:
    tl = text.lower()
    return all(re.search(p, tl) for p in patterns)


def oracle(page: Any, task_cfg: dict) -> str:
    items = list_products(page)
    # Pick 3 products with reviews
    chosen: list[dict] = []
    for it in items[:12]:
        url = it.get("product_url")
        if not url:
            continue
        page.goto(url)
        page.wait_for_load_state("domcontentloaded")
        d = product_details(page) or {}
        merged = {**it, **{k: v for k, v in d.items() if v is not None}}
        if (merged.get("review_count") or 0) >= 1:
            # Determine product id for AJAX endpoint
            html = page.content()
            m = re.search(r"listAjax/id/(\d+)/", html)
            merged["product_id"] = m.group(1) if m else None
            chosen.append(merged)
        if len(chosen) >= 3:
            break

    # Pull reviews for each
    base = task_cfg["start_url"].split("/catalogsearch")[0]
    all_reviews: list[dict] = []  # tuples include product info
    for prod in chosen:
        pid = prod.get("product_id")
        if not pid:
            continue
        for p_idx in range(1, 5):
            page.goto(f"{base}/review/product/listAjax/id/{pid}/?p={p_idx}")
            batch = list_reviews(page) or []
            if not batch:
                break
            for r in batch:
                r["_product"] = prod
                all_reviews.append(r)

    # Tally themes from low-rated reviews (rating ≤ 3)
    low = [r for r in all_reviews if (r.get("rating") or 5) <= 3]
    theme_hits: Counter = Counter()
    examples: dict[str, dict] = {}
    products_per_theme: dict[str, set[str]] = {}
    for theme, pats in _THEMES:
        for r in low:
            text = (r.get("title") or "") + " " + (r.get("body") or "")
            if _matches(text, pats):
                theme_hits[theme] += 1
                products_per_theme.setdefault(theme, set()).add(r["_product"].get("name", ""))
                examples.setdefault(theme, r)

    top_themes = theme_hits.most_common(3) if theme_hits else []
    if not top_themes:
        # Fallback: use any review (not just low) for theme tallying so the
        # report still has structure even on a thin review corpus.
        for theme, pats in _THEMES:
            for r in all_reviews:
                text = (r.get("title") or "") + " " + (r.get("body") or "")
                if _matches(text, pats):
                    theme_hits[theme] += 1
                    products_per_theme.setdefault(theme, set()).add(r["_product"].get("name", ""))
                    examples.setdefault(theme, r)
        top_themes = theme_hits.most_common(3)

    # ----- Markdown -----
    lines: list[str] = ["# Bluetooth Headphones: Common Quality Complaints\n"]
    lines.append(
        f"We surveyed customer reviews for **{len(chosen)} bluetooth-headphone products** on the One Stop Market — "
        "browsing each product page and pulling its review listing via the `/review/product/listAjax/` endpoint. "
        "We then tallied recurring complaint themes across low-rated reviews and report the three most common, "
        "with verbatim examples drawn from real review bodies.\n"
    )

    lines.append("## Products examined\n")
    triples: list[dict] = []
    for p in chosen:
        name, price = p.get("name", ""), p.get("price")
        rating, rc = p.get("rating"), p.get("review_count")
        url = p.get("product_url", "")
        lines.append(f"- {md_link(name, url)} — **${price}** — {rating} ⭐ ({rc} reviews)")
        triples.append({"subject": name, "predicate": "price", "object": str(price)})
        triples.append({"subject": name, "predicate": "rating", "object": str(rating)})
        triples.append({"subject": name, "predicate": "review_count", "object": str(rc)})
        triples.append({"subject": name, "predicate": "product_url", "object": url})
    lines.append("")

    lines.append("## Top recurring complaint themes\n")
    if not top_themes:
        lines.append("*No clearly recurring complaint patterns surfaced — the review corpus is too thin to support theme extraction at this time.*\n")
    for i, (theme, cnt) in enumerate(top_themes, 1):
        ex = examples.get(theme, {})
        lines.append(f"### {i}. {theme} — observed in {cnt} reviews across {len(products_per_theme.get(theme, []))} products\n")
        snippet = (ex.get("body") or "").strip()[:240]
        ex_prod = ex.get("_product", {}).get("name", "")
        if snippet:
            lines.append(f"> \"{snippet}\" — review on {md_link(ex_prod, ex.get('_product', {}).get('product_url',''))}\n")
            triples.append({"subject": ex_prod, "predicate": "review_text", "object": snippet[:200]})

    lines.append("## Most pervasive complaint\n")
    if top_themes:
        winning = max(products_per_theme.items(), key=lambda kv: len(kv[1]))[0] if products_per_theme else top_themes[0][0]
        n_prods = len(products_per_theme.get(winning, set()))
        lines.append(
            f"Across the products we sampled, **{winning}** is the complaint that touches the most distinct products "
            f"({n_prods}/{len(chosen)}), making it the most pervasive quality concern buyers in this segment should weigh.\n"
        )

    lines.append("## Caveats\n")
    lines.append(
        "- Theme classification is regex-based on simple keyword conjunctions; nuanced complaints (e.g. comfort *after* an hour) "
        "may be missed unless they share keywords with our patterns.\n"
        "- Sample sizes per product are small. A single negative reviewer with a strong opinion can over-inflate a theme.\n"
        "- Verbatim quotes are taken from the live review listing and reflect content available at the time of the survey.\n"
    )

    write_golden(task_cfg["task_id"], triples)
    return "\n".join(lines)
