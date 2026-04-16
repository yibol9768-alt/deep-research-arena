"""Oracle for dr_cross_v3_0001: headphones — shopping products + reddit sentiment.

Collects ground-truth data from both sites, writes:
  - data/results/oracle_v3_dr_cross_v3_0001.md  (reference report)
  - data/golden/dr_cross_v3_0001.json           (KG triples)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

SHOPPING = "http://localhost:7770"
REDDIT = "http://localhost:9999"


def _fetch(url: str) -> str:
    try:
        r = requests.get(url, timeout=30)
        return r.text if r.ok else ""
    except Exception:
        return ""


def _scrape_products(query: str, max_items: int = 10) -> list[dict]:
    html = _fetch(f"{SHOPPING}/catalogsearch/result/?q={query}")
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for el in soup.select("li.item.product.product-item")[:max_items]:
        a = el.select_one("a.product-item-link")
        name = a.get_text(strip=True) if a else ""
        url = a["href"] if a else ""
        price = None
        pEl = el.select_one("[data-price-amount]")
        if pEl:
            try:
                price = float(pEl["data-price-amount"])
            except Exception:
                pass
        rating = None
        rEl = el.select_one(".rating-result [title]")
        if rEl:
            m = re.search(r"(\d+)%", rEl.get("title", ""))
            if m:
                rating = int(m.group(1)) / 20
        products.append({"name": name, "url": url, "price": price, "rating": rating})
    return products


def _product_detail(url: str) -> dict:
    html = _fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {"url": url}
    h1 = soup.select_one("h1.page-title span")
    out["name"] = h1.get_text(strip=True) if h1 else ""
    pEl = soup.select_one("[data-price-amount]")
    if pEl:
        try:
            out["price"] = float(pEl["data-price-amount"])
        except Exception:
            pass
    rEl = soup.select_one(".rating-result [title]")
    if rEl:
        m = re.search(r"(\d+)%", rEl.get("title", ""))
        if m:
            out["rating"] = int(m.group(1)) / 20
    rev = soup.select_one("a[href*='#reviews']")
    if rev:
        m = re.search(r"(\d+)", rev.get_text())
        if m:
            out["review_count"] = int(m.group(1))
    return out


def _reddit_posts(forum: str, max_posts: int = 25) -> list[dict]:
    html = _fetch(f"{REDDIT}/f/{forum}")
    _SUB_RE = re.compile(r'<article[^>]*class="[^"]*submission[^"]*"[\s\S]*?</article>', re.I)
    posts = []
    for m in _SUB_RE.finditer(html):
        block = m.group(0)
        p: dict = {"forum": forum}
        tm = re.search(r'class="submission__link"[^>]*>([^<]+)</a>', block)
        if tm:
            p["title"] = re.sub(r"&#039;", "'", tm.group(1)).strip()
        um = re.search(r'href="(/f/[A-Za-z0-9_]+/\d+/[^"]+)"', block)
        if um:
            p["url"] = REDDIT + um.group(1)
        sm = re.search(r'vote__net-score[^>]*>(-?\d+)', block)
        p["score"] = int(sm.group(1)) if sm else 0
        cm = re.search(r'data-comment-count="(\d+)"', block)
        p["comment_count"] = int(cm.group(1)) if cm else 0
        posts.append(p)
    return posts[:max_posts]


def main():
    print("=== Oracle dr_cross_v3_0001: headphones shopping + reddit ===\n")

    # --- Shopping: find headphones ---
    print("Searching shopping for headphones...")
    products = _scrape_products("headphones")
    # Filter $30-100 range
    in_range = [p for p in products if p.get("price") and 30 <= p["price"] <= 100]
    print(f"  Found {len(products)} total, {len(in_range)} in $30-100 range")

    # Get details for top products
    detailed = []
    for p in (in_range or products)[:5]:
        if p.get("url"):
            d = _product_detail(p["url"])
            if d.get("name"):
                detailed.append(d)
                print(f"  Product: {d['name']} ${d.get('price', '?')} rating={d.get('rating', '?')}")

    # --- Reddit: find tech discussions about headphones/audio ---
    print("\nSearching reddit /f/technology for headphone/audio posts...")
    tech_posts = _reddit_posts("technology")
    audio_related = [p for p in tech_posts if any(kw in (p.get("title", "") or "").lower()
                     for kw in ["headphone", "audio", "sound", "music", "apple", "amazon", "google"])]
    if not audio_related:
        # Broader: take top posts from /f/technology as general tech sentiment
        audio_related = tech_posts[:5]
    print(f"  Found {len(audio_related)} relevant posts")

    for p in audio_related[:5]:
        print(f"  Post: [{p.get('score', 0):+d}|{p.get('comment_count', 0)}c] {p.get('title', '?')[:60]}")

    # --- Build KG triples ---
    triples = []
    for d in detailed:
        subj = d["name"]
        if d.get("price"):
            triples.append({"subject": subj, "predicate": "price", "object": str(d["price"])})
        if d.get("rating"):
            triples.append({"subject": subj, "predicate": "rating", "object": str(d["rating"])})
        if d.get("review_count"):
            triples.append({"subject": subj, "predicate": "review_count", "object": str(d["review_count"])})
        triples.append({"subject": subj, "predicate": "product_url", "object": d["url"]})

    for p in audio_related[:5]:
        title = p.get("title", "")
        if not title:
            continue
        triples.append({"subject": title[:60], "predicate": "forum", "object": p.get("forum", "technology")})
        triples.append({"subject": title[:60], "predicate": "score", "object": str(p.get("score", 0))})
        triples.append({"subject": title[:60], "predicate": "comment_count", "object": str(p.get("comment_count", 0))})
        if p.get("url"):
            triples.append({"subject": title[:60], "predicate": "post_url", "object": p["url"]})

    # Save golden
    golden_path = ROOT / "data" / "golden" / "dr_cross_v3_0001.json"
    golden_path.write_text(json.dumps(triples, indent=2, ensure_ascii=False))
    print(f"\nGolden: {len(triples)} triples → {golden_path}")

    # --- Build markdown report ---
    md_lines = ["# Noise-Cancelling Headphones: Shopping Data vs Reddit Sentiment\n"]
    md_lines.append("## 1. Introduction\n")
    md_lines.append(
        "This report cross-references product data from the One Stop Market shopping site "
        "with community discussions on the Reddit /f/technology forum to evaluate noise-cancelling "
        "and wireless headphones in the $30-100 price range.\n"
    )

    md_lines.append("## 2. Shopping Site Findings\n")
    md_lines.append(
        f"A search for 'headphones' on the shopping site returned {len(products)} results, "
        f"of which {len(in_range)} fall in the $30-100 target range.\n"
    )
    for d in detailed:
        name = d["name"]
        url = d.get("url", "")
        price = d.get("price", "N/A")
        rating = d.get("rating", "N/A")
        rc = d.get("review_count", "N/A")
        md_lines.append(
            f"**[{name}]({url})**: ${price}, {rating}/5 stars, {rc} reviews.\n"
        )

    md_lines.append("## 3. Reddit Community Sentiment\n")
    md_lines.append(
        "On /f/technology, the following discussions provide context on how the tech community "
        "views audio products and consumer tech:\n"
    )
    for p in audio_related[:5]:
        title = p.get("title", "?")
        url = p.get("url", "")
        score = p.get("score", 0)
        cc = p.get("comment_count", 0)
        md_lines.append(
            f"- **[{title}]({url})**: score {score:+d}, {cc} comments\n"
        )

    md_lines.append("## 4. Cross-Source Analysis\n")
    md_lines.append(
        "The shopping site provides structured product data (price, rating, review count) while "
        "Reddit captures broader community sentiment about tech companies and consumer rights. "
        "Products with high ratings on the shopping site may not necessarily align with Reddit "
        "sentiment, which often focuses on company practices rather than individual product quality.\n"
    )

    md_lines.append("## 5. Conclusion\n")
    md_lines.append(
        "Cross-referencing structured e-commerce data with unstructured community discussions "
        "reveals that product ratings and community trust operate on different axes. A product "
        "can be highly rated on the storefront while its manufacturer faces criticism on social "
        "platforms. Comprehensive consumer research requires both perspectives.\n"
    )

    report = "\n".join(md_lines)
    report_path = ROOT / "data" / "results" / "oracle_v3_dr_cross_v3_0001.md"
    report_path.write_text(report)
    print(f"Report: {len(report.split())} words → {report_path}")


if __name__ == "__main__":
    main()
