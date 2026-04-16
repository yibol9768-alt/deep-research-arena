"""Oracle for dr_shop_v3_0003 — tea price-quality quadrant analysis."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Any

from envs.shopping.oracle_dr.magento_scrape import list_products, product_details
from ._common import write_golden, md_link


_TYPE_PATTERNS = {
    "green":   [r"\bgreen tea\b", r"\bmatcha\b"],
    "black":   [r"\bblack tea\b", r"\bearl grey\b", r"\bdarjeeling\b"],
    "herbal":  [r"\bherbal\b", r"\bchamomile\b", r"\bmint\b", r"\bpeppermint\b", r"\binfusion\b"],
    "oolong":  [r"\boolong\b"],
    "white":   [r"\bwhite tea\b"],
    "fruit":   [r"\bfruit\b", r"\bberry\b", r"\bvanilla\b", r"\borange\b", r"\bapple\b"],
}


def _classify(name: str) -> str:
    n = name.lower()
    for t, pats in _TYPE_PATTERNS.items():
        for p in pats:
            if re.search(p, n):
                return t
    return "other"


def oracle(page: Any, task_cfg: dict) -> str:
    items = list_products(page)
    # Need at least 6 distinct teas
    enriched: list[dict] = []
    for it in items[:18]:
        url = it.get("product_url")
        name = (it.get("name") or "").lower()
        if "tea" not in name and "tisane" not in name:
            continue
        if not url:
            continue
        page.goto(url)
        page.wait_for_load_state("domcontentloaded")
        d = product_details(page) or {}
        merged = {**it, **{k: v for k, v in d.items() if v is not None}}
        if merged.get("price"):
            merged["tea_type"] = _classify(merged.get("name", ""))
            enriched.append(merged)
        if len(enriched) >= 8:
            break

    by_type: dict[str, list[dict]] = defaultdict(list)
    for p in enriched:
        by_type[p["tea_type"]].append(p)

    lines: list[str] = ["# Tea Market on One Stop Market: A Price-Quality Quadrant\n"]
    lines.append(
        f"We surveyed **{len(enriched)} tea products** on the One Stop Market by searching `tea` and visiting each detail page. "
        "Products were classified into types — green, black, herbal, oolong, white, fruit-infusion — based on name keywords. "
        "For each type with at least one observation we report inventory size, price range, and average customer rating, "
        "then identify the type that delivers the best price–quality ratio.\n"
    )

    lines.append("## Inventory by tea type\n")
    rows = ["| Type | n | Price range | Avg rating |", "|---|---:|---|---:|"]
    triples: list[dict] = []
    type_summary: dict[str, dict] = {}
    for t, group in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        prices = [g["price"] for g in group if g.get("price")]
        ratings = [g["rating"] for g in group if g.get("rating") is not None]
        if not prices:
            continue
        lo, hi = min(prices), max(prices)
        avg_r = round(statistics.fmean(ratings), 2) if ratings else None
        rows.append(f"| {t} | {len(group)} | ${lo:.2f}–${hi:.2f} | {avg_r if avg_r else '—'} |")
        type_summary[t] = {
            "n": len(group),
            "price_lo": lo,
            "price_hi": hi,
            "avg_rating": avg_r,
            "value": (avg_r / lo) if avg_r and lo else 0,
        }
        triples.append({"subject": f"tea-type:{t}", "predicate": "n_products", "object": str(len(group))})
        if avg_r is not None:
            triples.append({"subject": f"tea-type:{t}", "predicate": "avg_rating", "object": str(avg_r)})

    lines.extend(rows)
    lines.append("")

    lines.append("## Individual products examined\n")
    for p in enriched:
        n = p.get("name", "")
        triples.append({"subject": n, "predicate": "price", "object": str(p.get("price"))})
        if p.get("rating") is not None:
            triples.append({"subject": n, "predicate": "rating", "object": str(p.get("rating"))})
        triples.append({"subject": n, "predicate": "category", "object": p.get("tea_type")})
        triples.append({"subject": n, "predicate": "product_url", "object": p.get("product_url")})
        lines.append(
            f"- [{p.get('tea_type')}] {md_link(n, p.get('product_url',''))} — **${p.get('price')}**"
            + (f" — **{p.get('rating')} ⭐**" if p.get("rating") is not None else "")
        )
    lines.append("")

    # Best-value type (highest avg_rating / price_lo)
    if type_summary:
        best_type = max(type_summary.items(), key=lambda kv: kv[1].get("value", 0))[0]
        lines.append("## Price–quality quadrant analysis\n")
        lines.append(
            f"Plotting average rating against entry-price floor by type, the **{best_type}** segment delivers the best value "
            f"in this catalog: customers can enter the category at the lowest price point while still achieving a competitive "
            f"average rating. The sample sizes are modest (most types have 1–3 products), so this should be read as a "
            f"directional signal rather than a definitive market verdict.\n"
        )
        # Pick a concrete product within the best type with highest rating
        candidates = [g for g in enriched if g.get("tea_type") == best_type]
        candidates.sort(key=lambda g: (-(g.get("rating") or 0), g.get("price") or 9e9))
        if candidates:
            top = candidates[0]
            lines.append(
                f"### Concrete suggestion\n"
                f"For a buyer wanting to test this conclusion, start with "
                f"{md_link(top.get('name',''), top.get('product_url',''))} at **${top.get('price')}** — the highest-rated entry "
                f"within the best-value type.\n"
            )

    lines.append("## Limitations\n")
    lines.append(
        "- Tea-type classification is keyword-based and will misfile blends that don't include the dominant ingredient in the title.\n"
        "- Many products lack reviews entirely; ratings absent from the listing were excluded from per-type averages.\n"
        "- 'Best value' here uses a crude `avg_rating / price_floor` ratio. Buyers should weight ratio against personal "
        "preferences for caffeination, format (loose-leaf vs bagged), and seasonality.\n"
    )

    write_golden(task_cfg["task_id"], triples)
    return "\n".join(lines)
