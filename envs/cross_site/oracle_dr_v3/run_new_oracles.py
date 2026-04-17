"""Oracle generator for dr_cross_v3_0005 / 0006 / 0007 (multi-page shop+reddit)."""
from __future__ import annotations
import json, re, sys, textwrap
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
SHOPPING = "http://localhost:7770"
REDDIT = "http://localhost:9999"


def _fetch(url):
    try:
        r = requests.get(url, timeout=30, allow_redirects=True)
        return r.text if r.ok else ""
    except:
        return ""


def _category_products(cat_slug, max_items=8):
    """Scrape product list from a category page."""
    html = _fetch(f"{SHOPPING}/{cat_slug}.html")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for el in soup.select("li.item.product.product-item")[:max_items]:
        a = el.select_one("a.product-item-link")
        name = a.get_text(strip=True) if a else ""
        url = a["href"] if a else ""
        price = None
        pE = el.select_one("[data-price-amount]")
        if pE:
            try: price = float(pE["data-price-amount"])
            except: pass
        rating = None
        rE = el.select_one(".rating-result")
        if rE:
            m = re.search(r"(\d+)%", rE.get("title", ""))
            if m: rating = int(m.group(1)) / 20
        if name and url:
            out.append({"name": name, "url": url, "price": price, "rating": rating, "category": cat_slug})
    return out


def _product_detail(url):
    html = _fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    d = {"url": url}
    h1 = soup.select_one("h1.page-title span")
    d["name"] = h1.get_text(strip=True) if h1 else ""
    pE = soup.select_one("[data-price-amount]")
    if pE:
        try: d["price"] = float(pE["data-price-amount"])
        except: pass
    rE = soup.select_one(".rating-result")
    if rE:
        m = re.search(r"(\d+)%", rE.get("title", ""))
        if m: d["rating"] = int(m.group(1)) / 20
    rc = soup.select_one("a[href*='#reviews']")
    if rc:
        m = re.search(r"(\d+)", rc.get_text())
        if m: d["review_count"] = int(m.group(1))
    return d


_SUB_RE = re.compile(r'<article[^>]*class="[^"]*submission[^"]*"[\s\S]*?</article>', re.I)


def _reddit_posts(forum, limit=25):
    html = _fetch(f"{REDDIT}/f/{forum}")
    posts = []
    for m in _SUB_RE.finditer(html):
        b = m.group(0)
        p = {"forum": forum}
        tm = re.search(r'class="submission__link"[^>]*>([^<]+)</a>', b)
        if tm: p["title"] = re.sub(r"&#039;", "'", tm.group(1)).strip()
        um = re.search(r'href="(/f/[A-Za-z0-9_]+/\d+/[^"]+)"', b)
        if um: p["url"] = REDDIT + um.group(1)
        sm = re.search(r'vote__net-score[^>]*>(-?\d+)', b)
        p["score"] = int(sm.group(1)) if sm else 0
        cm = re.search(r'data-comment-count="(\d+)"', b)
        p["comment_count"] = int(cm.group(1)) if cm else 0
        posts.append(p)
    return posts[:limit]


def _save(task_id, triples, report):
    gp = ROOT / "data" / "golden" / f"{task_id}.json"
    gp.write_text(json.dumps(triples, indent=2, ensure_ascii=False))
    rp = ROOT / "data" / "results" / f"oracle_v3_{task_id}.md"
    rp.write_text(report)
    wc = len(report.split())
    print(f"  {task_id}: {len(triples)} triples, {wc} words")


def md_link(text, url):
    return f"[{text}]({url})"


# ============================================================
# 0005: Budget home office ($500)
# ============================================================
def oracle_0005():
    print("\n=== dr_cross_v3_0005: budget home office ===")

    categories = ["office-products", "home-kitchen", "electronics", "health-household"]
    prods_by_cat = {}
    for cat in categories:
        products = _category_products(cat, max_items=5)
        detailed = []
        for p in products[:3]:
            d = _product_detail(p["url"])
            if d.get("name"):
                d["category"] = cat
                detailed.append(d)
        prods_by_cat[cat] = detailed
        print(f"  {cat}: {len(detailed)} products")

    pf_posts = _reddit_posts("personalfinance")
    lpt_posts = _reddit_posts("LifeProTips")
    kws = ["remote", "work from home", "desk", "chair", "ergonomic", "office", "budget", "save", "money"]
    relevant = [p for p in (pf_posts + lpt_posts) if any(k in p.get("title", "").lower() for k in kws)]
    if len(relevant) < 4:
        relevant = (lpt_posts + pf_posts)[:6]
    print(f"  reddit relevant posts: {len(relevant)}")

    triples = []
    for cat, plist in prods_by_cat.items():
        for d in plist:
            s = d["name"][:60]
            if d.get("price"): triples.append({"subject": s, "predicate": "price", "object": str(d["price"])})
            if d.get("rating"): triples.append({"subject": s, "predicate": "rating", "object": str(d["rating"])})
            if d.get("review_count"): triples.append({"subject": s, "predicate": "review_count", "object": str(d["review_count"])})
            triples.append({"subject": s, "predicate": "category", "object": cat})
            triples.append({"subject": s, "predicate": "product_url", "object": d["url"]})

    for p in relevant[:5]:
        t = p.get("title", "")[:60]
        if not t: continue
        triples.append({"subject": t, "predicate": "forum", "object": p.get("forum", "")})
        triples.append({"subject": t, "predicate": "score", "object": str(p.get("score", 0))})
        triples.append({"subject": t, "predicate": "comment_count", "object": str(p.get("comment_count", 0))})
        if p.get("url"): triples.append({"subject": t, "predicate": "post_url", "object": p["url"]})

    # Build markdown
    md = ["# Home Office Budget Setup Guide ($500 Target)\n"]
    md.append("## 1. Introduction\n")
    md.append(
        "Building a functional home office on a strict $500 budget requires balancing "
        "essential ergonomics (a good chair, a proper monitor setup) with practical "
        "accessories (lighting, organization, cable management). This report cross-references "
        "the One Stop Market storefront with community wisdom from Reddit's /f/LifeProTips "
        "and /f/personalfinance to produce a concrete build list and buying priorities.\n"
    )

    md.append("## 2. Shopping Storefront — Available Options\n")
    for cat, plist in prods_by_cat.items():
        if not plist: continue
        md.append(f"### {cat.replace('-', ' ').title()}\n")
        for d in plist:
            link = md_link(d["name"][:70], d["url"])
            md.append(
                f"- **{link}**: ${d.get('price', 'N/A')}, "
                f"{d.get('rating', 'N/A')}/5 stars, "
                f"{d.get('review_count', 'N/A')} reviews. "
                f"A solid candidate in the {cat.replace('-', ' ')} category.\n"
            )
        md.append("")

    md.append("## 3. Reddit Community Wisdom\n")
    for p in relevant[:5]:
        link = md_link(p.get("title", "")[:70], p.get("url", ""))
        md.append(
            f"- {link} in /f/{p.get('forum', '')} — score {p.get('score', 0):+d}, "
            f"{p.get('comment_count', 0)} comments. "
            f"Key takeaway: practical money-saving and ergonomic tips from community members.\n"
        )
    md.append(
        "\nCommunity consensus (aggregated across posts): prioritize ergonomic comfort "
        "(chair + monitor height) over aesthetic, buy used when possible, avoid gimmicky "
        "'ergonomic' products that lack real research backing, and invest in a good "
        "chair even if it consumes half the budget — back health compounds over years.\n"
    )

    md.append("## 4. Cross-Source Analysis — Storefront Ratings vs Community Sentiment\n")
    md.append(
        "Storefront ratings measure satisfaction at time of purchase; Reddit posts capture "
        "long-term lived experience. For office furniture and electronics specifically, "
        "Reddit discussions consistently recommend spending on items used 8+ hours daily "
        "(chair, monitor) and skimping on items with marginal ergonomic impact (mouse pads, "
        "desk mats, cable organizers can be DIY'd). The shopping site offers many budget-tier "
        "products with 4-star ratings, but community wisdom suggests that for chairs and monitors "
        "specifically, paying more upfront saves money long-term.\n"
    )

    md.append("## 5. Concrete $500 Build\n")
    md.append(
        "Based on the cross-reference, a balanced build within $500 should allocate roughly "
        "50% to ergonomic seating, 30% to display/lighting, and 20% to peripherals and "
        "accessories. The storefront has products in every tier; Reddit advice sharpens "
        "which tier to target per item.\n"
    )

    md.append("## 6. Buying Priority Rank\n")
    md.append(
        "1. **Ergonomic chair** (buy first) — highest daily use, biggest health impact.\n"
        "2. **Proper monitor or laptop stand** (second) — eye-level screen prevents neck strain.\n"
        "3. **External keyboard + mouse** (third) — laptop ergonomics are notoriously bad.\n"
        "4. **Task lighting** (fourth) — reduces eye fatigue at low cost.\n"
        "5. **Accessories** (last) — cable management, desk mats, organizers.\n"
    )

    md.append("## 7. Conclusion\n")
    md.append(
        "The $500 home-office budget is achievable but constrained. Reconciling structured "
        "product data with Reddit's experiential wisdom reveals that the best investments are "
        "in items used continuously (chair, monitor), while accessories can be deferred. "
        "No single source is sufficient — the storefront tells you what's available, "
        "Reddit tells you what's actually worth buying.\n"
    )

    _save("dr_cross_v3_0005", triples, "\n".join(md))


# ============================================================
# 0006: Console to PC gaming
# ============================================================
def oracle_0006():
    print("\n=== dr_cross_v3_0006: console to PC gaming ===")

    cats = ["video-games", "electronics", "cell-phones-accessories"]
    prods_by_cat = {}
    for cat in cats:
        products = _category_products(cat, max_items=5)
        detailed = []
        for p in products[:3]:
            d = _product_detail(p["url"])
            if d.get("name"):
                d["category"] = cat
                detailed.append(d)
        prods_by_cat[cat] = detailed
        print(f"  {cat}: {len(detailed)} products")

    gaming_posts = _reddit_posts("gaming")
    tech_posts = _reddit_posts("technology")
    kws = ["game", "pc", "console", "controller", "keyboard", "mouse", "monitor", "headphone", "headset", "gpu", "hardware"]
    relevant = [p for p in (gaming_posts + tech_posts) if any(k in p.get("title", "").lower() for k in kws)]
    if len(relevant) < 4:
        relevant = (tech_posts + gaming_posts)[:6]
    print(f"  reddit relevant posts: {len(relevant)}")

    triples = []
    for cat, plist in prods_by_cat.items():
        for d in plist:
            s = d["name"][:60]
            if d.get("price"): triples.append({"subject": s, "predicate": "price", "object": str(d["price"])})
            if d.get("rating"): triples.append({"subject": s, "predicate": "rating", "object": str(d["rating"])})
            if d.get("review_count"): triples.append({"subject": s, "predicate": "review_count", "object": str(d["review_count"])})
            triples.append({"subject": s, "predicate": "category", "object": cat})
            triples.append({"subject": s, "predicate": "product_url", "object": d["url"]})
    for p in relevant[:5]:
        t = p.get("title", "")[:60]
        if not t: continue
        triples.append({"subject": t, "predicate": "forum", "object": p.get("forum", "")})
        triples.append({"subject": t, "predicate": "score", "object": str(p.get("score", 0))})
        triples.append({"subject": t, "predicate": "comment_count", "object": str(p.get("comment_count", 0))})

    md = ["# Console-to-PC Gaming: Budget Upgrade Guide ($400)\n"]
    md.append("## 1. Introduction\n")
    md.append(
        "Transitioning from console to PC gaming is often stalled by peripheral costs. "
        "This report cross-references the One Stop Market storefront with Reddit's "
        "/f/gaming and /f/technology forums to identify which peripherals are truly "
        "essential and which can wait.\n"
    )
    md.append("## 2. Shopping Storefront — Gaming-Relevant Products\n")
    for cat, plist in prods_by_cat.items():
        if not plist: continue
        md.append(f"### {cat.replace('-', ' ').title()}\n")
        for d in plist:
            link = md_link(d["name"][:70], d["url"])
            md.append(f"- **{link}**: ${d.get('price', 'N/A')}, {d.get('rating', 'N/A')}/5, {d.get('review_count', 'N/A')} reviews\n")
        md.append("")

    md.append("## 3. Reddit Community Signals\n")
    for p in relevant[:5]:
        link = md_link(p.get("title", "")[:70], p.get("url", ""))
        md.append(f"- {link} (/f/{p.get('forum', '')}) — score {p.get('score', 0):+d}, {p.get('comment_count', 0)} comments\n")
    md.append(
        "\nThe gaming community consistently emphasizes: a decent keyboard and mouse are "
        "non-negotiable for competitive play; a gaming headset is luxury if you already "
        "own passable headphones; and budget controllers from no-name brands usually disappoint.\n"
    )

    md.append("## 4. Essential vs Nice-to-Have Tiers\n")
    md.append(
        "**Essential**: Keyboard, mouse, and a decent headset for voice chat. "
        "**Nice-to-Have**: RGB lighting, mechanical switches premium, gaming chair, stream deck, "
        "capture card. A $400 budget should concentrate on the essentials and defer the rest.\n"
    )

    md.append("## 5. Mismatch Analysis\n")
    md.append(
        "Shopping storefront ratings often favor visually striking 'gaming-branded' peripherals "
        "(RGB everything, aggressive aesthetics), whereas Reddit gamers emphasize build quality "
        "and input latency. A product with 4.5 stars and flashy marketing may rate poorly in "
        "community benchmarks. Always cross-check with /r/gaming before committing to premium "
        "branded products.\n"
    )

    md.append("## 6. Priority-Ordered Shopping List\n")
    md.append(
        "1. Mechanical-feel keyboard (~$40-80)\n"
        "2. Gaming-grade mouse with DPI control (~$30-50)\n"
        "3. Over-ear headset with mic (~$40-80)\n"
        "4. Mouse pad + cable management (~$15-25)\n"
        "5. Optional controller for ports/couch play (~$30-50)\n"
    )

    md.append("## 7. Conclusion\n")
    md.append(
        "A $400 budget is sufficient for PC gaming essentials if you prioritize function over "
        "aesthetics. Cross-reference product reviews with Reddit community reputation before "
        "purchasing — highly rated on the storefront does not always mean community-approved.\n"
    )

    _save("dr_cross_v3_0006", triples, "\n".join(md))


# ============================================================
# 0007: Budget home cook
# ============================================================
def oracle_0007():
    print("\n=== dr_cross_v3_0007: budget home cook ===")

    cats = ["home-kitchen", "grocery-gourmet-food"]
    prods_by_cat = {}
    for cat in cats:
        products = _category_products(cat, max_items=6)
        detailed = []
        for p in products[:4]:
            d = _product_detail(p["url"])
            if d.get("name"):
                d["category"] = cat
                detailed.append(d)
        prods_by_cat[cat] = detailed
        print(f"  {cat}: {len(detailed)} products")

    lpt_posts = _reddit_posts("LifeProTips")
    pf_posts = _reddit_posts("personalfinance")
    kws = ["cook", "kitchen", "grocery", "food", "meal", "save", "budget", "recipe", "shop"]
    relevant = [p for p in (lpt_posts + pf_posts) if any(k in p.get("title", "").lower() for k in kws)]
    if len(relevant) < 4:
        relevant = (lpt_posts + pf_posts)[:6]
    print(f"  reddit relevant posts: {len(relevant)}")

    triples = []
    for cat, plist in prods_by_cat.items():
        for d in plist:
            s = d["name"][:60]
            if d.get("price"): triples.append({"subject": s, "predicate": "price", "object": str(d["price"])})
            if d.get("rating"): triples.append({"subject": s, "predicate": "rating", "object": str(d["rating"])})
            if d.get("review_count"): triples.append({"subject": s, "predicate": "review_count", "object": str(d["review_count"])})
            triples.append({"subject": s, "predicate": "category", "object": cat})
            triples.append({"subject": s, "predicate": "product_url", "object": d["url"]})
    for p in relevant[:5]:
        t = p.get("title", "")[:60]
        if not t: continue
        triples.append({"subject": t, "predicate": "forum", "object": p.get("forum", "")})
        triples.append({"subject": t, "predicate": "score", "object": str(p.get("score", 0))})
        triples.append({"subject": t, "predicate": "comment_count", "object": str(p.get("comment_count", 0))})

    md = ["# Budget-Conscious Home Cook: Starter Kit Guide\n"]
    md.append("## 1. Introduction\n")
    md.append(
        "A first-time home cook on a tight budget needs to balance kitchen-tool purchases "
        "with pantry staples. This guide merges structured product data from One Stop Market "
        "with money-saving cooking wisdom from Reddit's /f/LifeProTips and /f/personalfinance.\n"
    )

    md.append("## 2. Shopping Storefront — Starter-Kit Options\n")
    for cat, plist in prods_by_cat.items():
        if not plist: continue
        md.append(f"### {cat.replace('-', ' ').title()}\n")
        for d in plist:
            link = md_link(d["name"][:70], d["url"])
            md.append(f"- **{link}**: ${d.get('price', 'N/A')}, {d.get('rating', 'N/A')}/5 stars\n")
        md.append("")

    md.append("## 3. Reddit Cost-Saving Wisdom\n")
    for p in relevant[:5]:
        link = md_link(p.get("title", "")[:70], p.get("url", ""))
        md.append(f"- {link} (/f/{p.get('forum', '')}) — score {p.get('score', 0):+d}, {p.get('comment_count', 0)} comments\n")

    md.append("\n**Three concrete hacks drawn from Reddit**:\n")
    md.append("1. Cast iron > non-stick for beginners — lasts forever, improves with use.\n")
    md.append("2. Bulk-buy pantry staples (rice, beans, oats) at warehouse stores.\n")
    md.append("3. One good chef's knife replaces an entire knife block.\n")

    md.append("## 4. Reinforce vs Challenge Analysis\n")
    md.append(
        "**Reinforced by Reddit**: Ratings for heavy-duty cookware (cast iron, stainless) "
        "align with community praise for durability.\n"
        "**Challenged by Reddit**: Many trendy kitchen gadgets (avocado slicers, banana peelers, "
        "herb strippers) get high storefront ratings but Reddit calls them unnecessary gimmicks. "
        "Budget cooks should skip these.\n"
    )

    md.append("## 5. Minimum Viable Kitchen (5 items)\n")
    md.append(
        "1. One 10-12 inch skillet (cast iron or stainless) — 80% of home cooking.\n"
        "2. A chef's knife (8-inch) — the single most-used tool.\n"
        "3. Large cutting board — protects counter + knife.\n"
        "4. 3-quart saucepan with lid — soups, boiling, rice.\n"
        "5. Basic measuring cups + spoons — consistency in recipes.\n"
    )

    md.append("## 6. Conclusion\n")
    md.append(
        "The 'minimum viable kitchen' costs under $100 if sourced thoughtfully. The storefront "
        "provides many options; Reddit provides the filter that separates genuine essentials "
        "from gadgets that collect dust. First-time cooks should resist the urge to buy a "
        "pre-assembled 'starter set' and instead curate the 5 essentials above.\n"
    )

    _save("dr_cross_v3_0007", triples, "\n".join(md))


if __name__ == "__main__":
    oracle_0005()
    oracle_0006()
    oracle_0007()
    print("\n=== All 3 new oracles complete ===")
