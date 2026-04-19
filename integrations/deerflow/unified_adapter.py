"""Unified multi-site adapter for DeerFlow v1.

Monkey-patches DeerFlow's researcher tools with a **polyglot tool set**
that can access all 4 sandboxed sites simultaneously:
  - Shopping  (Magento,  localhost:7770)
  - Reddit    (Postmill, localhost:9999)
  - GitLab    (CE,       localhost:8023)
  - Shopping Admin (Magento backend, localhost:7780)

This is the key enabler for cross-site Deep Research tasks.

Usage:
    python unified_adapter.py dr_cross_v3_0001
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

# --- Site URLs ---
SHOPPING       = os.environ.get("SHOPPING",       "http://localhost:7770").rstrip("/")
REDDIT         = os.environ.get("REDDIT",         "http://localhost:9999").rstrip("/")
GITLAB         = os.environ.get("GITLAB",         "http://localhost:8023").rstrip("/")
SHOPPING_ADMIN = os.environ.get("SHOPPING_ADMIN", "http://localhost:7780").rstrip("/")

ROOT = Path(__file__).resolve().parents[2]
# When imported as a library (e.g. from scripts/run_deerflow_cross.py's
# subprocess runner), do NOT insert ROOT at sys.path[0] — that shadows
# DeerFlow's own `src.*` namespace. Only insert when run standalone.
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))


def _fetch(url: str) -> str:
    try:
        r = requests.get(url, timeout=30, allow_redirects=True)
        return r.text if r.status_code < 400 else ""
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# Shopping tools (from shop_adapter.py, condensed)
# ============================================================

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
        rEl = el.select_one("[title]")
        if rEl:
            m = re.search(r"(\d+)%", rEl.get("title") or "")
            if m:
                rating = int(m.group(1)) / 20
        items.append({"name": name, "url": url, "price": price, "rating": rating})
    return items


def _scrape_product(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {}
    h1 = soup.select_one("h1.page-title span, h1.page-title")
    out["name"] = h1.get_text(strip=True) if h1 else ""
    pEl = soup.select_one("[data-price-amount]")
    if pEl and pEl.get("data-price-amount"):
        try:
            out["price"] = float(pEl["data-price-amount"])
        except Exception:
            pass
    rEl = soup.select_one(".rating-result [title]")
    if rEl:
        m = re.search(r"(\d+)%", rEl.get("title") or "")
        if m:
            out["rating"] = int(m.group(1)) / 20
    rev_count = soup.select_one(".reviews-actions a, a[href*='#reviews']")
    if rev_count:
        m = re.search(r"(\d+)", rev_count.get_text())
        if m:
            out["review_count"] = int(m.group(1))
    desc = soup.select_one(".product.attribute.description .value, #description .value")
    if desc:
        out["description"] = desc.get_text(" ", strip=True)[:500]
    return out


@tool
def shop_search(query: str) -> str:
    """Search the Shopping site (Magento) for products. Returns a JSON list of {name, url, price, rating}."""
    html = _fetch(f"{SHOPPING}/catalogsearch/result/?q={requests.utils.quote(query)}")
    items = _scrape_listing(html)
    return json.dumps({"site": "shopping", "query": query, "count": len(items), "items": items}, ensure_ascii=False)


@tool
def shop_browse(url: str) -> str:
    """Fetch a Shopping site URL. Returns product details or listing items."""
    if "://" not in url:
        url = f"{SHOPPING}{'' if url.startswith('/') else '/'}{url}"
    html = _fetch(url)
    if not html:
        return json.dumps({"error": "empty response", "url": url})
    if "product-info-main" in html or "catalog-product-view" in html:
        return json.dumps({"site": "shopping", "kind": "product", "url": url, **_scrape_product(html)}, ensure_ascii=False)
    items = _scrape_listing(html)
    return json.dumps({"site": "shopping", "kind": "listing", "url": url, "count": len(items), "items": items}, ensure_ascii=False)


@tool
def shop_reviews(product_url_or_id: str, max_pages: int = 3) -> str:
    """Fetch reviews for a shopping product. Pass either the product page URL or numeric product_id."""
    pid = product_url_or_id
    if "/" in pid:
        html = _fetch(pid)
        m = re.search(r'/id/(\d+)/', html) or re.search(r'product_id["\s:=]+(\d+)', html)
        pid = m.group(1) if m else ""
    reviews = []
    for p in range(1, int(max_pages) + 1):
        html = _fetch(f"{SHOPPING}/review/product/listAjax/id/{pid}/?p={p}")
        if not html or "review-item" not in html:
            break
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select(".review-item, li.item.review-item"):
            author = el.select_one(".review-details-value, [itemprop='author']")
            body = el.select_one(".review-content, [itemprop='description']")
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
    return json.dumps({"site": "shopping", "count": len(reviews), "reviews": reviews}, ensure_ascii=False)


# ============================================================
# Reddit tools (from reddit_adapter.py, condensed)
# ============================================================

_SUB_RE = re.compile(r'<article[^>]*class="[^"]*submission[^"]*"[\s\S]*?</article>', re.I)

def _one_sub(block: str) -> dict:
    out: dict = {}
    m = re.search(r'<a\s+href="([^"]+)"[^>]*class="submission__link"[^>]*>([^<]+)</a>', block)
    if m:
        out["title"] = re.sub(r"&#039;", "'", m.group(2)).strip()
    m = re.search(r'href="(/f/[A-Za-z0-9_]+/\d+/[^"]+)"', block)
    if m:
        out["url"] = REDDIT + m.group(1)
    m = re.search(r'class="submission__submitter[^"]*"[^>]*><strong>([^<]+)', block)
    if m:
        out["author"] = m.group(1).strip()
    m = re.search(r'data-comment-count="(\d+)"', block)
    out["comments"] = int(m.group(1)) if m else 0
    m = re.search(r'class="vote__net-score"[^>]*>(-?\d+)', block)
    out["score"] = int(m.group(1)) if m else 0
    return out


@tool
def reddit_search(forum_or_url: str) -> str:
    """List submissions from a Reddit (Postmill) forum. Pass a forum slug like 'technology', a path like '/f/news', or a full URL."""
    if "://" in forum_or_url:
        url = forum_or_url
    elif forum_or_url.startswith("/"):
        url = REDDIT + forum_or_url
    else:
        url = f"{REDDIT}/f/{forum_or_url}"
    html = _fetch(url)
    subs = [_one_sub(m.group(0)) for m in _SUB_RE.finditer(html or "")]
    return json.dumps({"site": "reddit", "url": url, "count": len(subs), "submissions": subs[:25]}, ensure_ascii=False)


@tool
def reddit_browse(url: str) -> str:
    """Fetch a Reddit (Postmill) URL. Returns submission details with comments, or a listing."""
    if "://" not in url:
        url = REDDIT + ("" if url.startswith("/") else "/") + url
    html = _fetch(url)
    if not html:
        return json.dumps({"error": "empty response", "url": url})
    if '<h1 class="submission__title' in html or "submission__body" in html:
        out: dict = {"site": "reddit", "kind": "submission", "url": url}
        m = re.search(r'<a[^>]*class="submission__link"[^>]*>([^<]+)</a>', html)
        if m:
            out["title"] = re.sub(r"&#039;", "'", m.group(1)).strip()
        m = re.search(r'class="vote__net-score"[^>]*>(-?\d+)', html)
        out["score"] = int(m.group(1)) if m else 0
        comment_re = re.compile(r'<article[^>]*class="[^"]*comment[^"]*"[\s\S]*?</article>', re.I)
        comments = []
        for cm in comment_re.finditer(html):
            blk = cm.group(0)
            c: dict = {}
            am = re.search(r'comment__author[^>]*>([^<]+)|href="/user/([^"]+)"', blk)
            if am:
                c["author"] = (am.group(1) or am.group(2) or "").strip()
            bm = re.search(r'class="comment__body[^"]*"[^>]*>([\s\S]*?)</div>', blk)
            if bm:
                c["body"] = re.sub(r"<[^>]+>", " ", bm.group(1)).strip()[:400]
            sm = re.search(r'vote__net-score[^>]*>(-?\d+)', blk)
            c["score"] = int(sm.group(1)) if sm else 0
            comments.append(c)
        out["comments"] = comments[:20]
        out["num_comments"] = len(comments)
        return json.dumps(out, ensure_ascii=False)
    subs = [_one_sub(m.group(0)) for m in _SUB_RE.finditer(html)]
    return json.dumps({"site": "reddit", "kind": "listing", "url": url, "count": len(subs), "submissions": subs[:25]}, ensure_ascii=False)


# ============================================================
# GitLab tools
# ============================================================

@tool
def gitlab_search(query: str) -> str:
    """Search GitLab for projects or issues. Returns a JSON list."""
    r = requests.get(f"{GITLAB}/api/v4/projects", params={
        "search": query, "per_page": 10,
        "order_by": "last_activity_at", "sort": "desc"
    }, timeout=20)
    projects = []
    for p in (r.json() if r.ok else []):
        projects.append({
            "id": p["id"],
            "name": p["name"],
            "path": p["path_with_namespace"],
            "url": f"{GITLAB}/{p['path_with_namespace']}",
            "description": (p.get("description") or "")[:200],
            "stars": p.get("star_count", 0),
            "forks": p.get("forks_count", 0),
        })
    return json.dumps({"site": "gitlab", "query": query, "count": len(projects), "projects": projects}, ensure_ascii=False)


@tool
def gitlab_issues(project_path_or_id: str, state: str = "all", per_page: int = 10) -> str:
    """List issues for a GitLab project. Pass project numeric ID or 'owner/repo' path. `state` can be 'opened', 'closed', or 'all'."""
    pid = project_path_or_id
    if "/" in pid and not pid.isdigit():
        pid = requests.utils.quote(pid, safe="")
    r = requests.get(f"{GITLAB}/api/v4/projects/{pid}/issues",
                     params={"state": state, "per_page": per_page},
                     timeout=20)
    issues = []
    for i in (r.json() if r.ok else []):
        issues.append({
            "iid": i["iid"],
            "title": i["title"],
            "state": i["state"],
            "labels": i.get("labels", []),
            "author": i.get("author", {}).get("username", ""),
            "url": i.get("web_url", ""),
            "description_preview": (i.get("description") or "")[:300],
        })
    return json.dumps({"site": "gitlab", "project": project_path_or_id, "count": len(issues), "issues": issues}, ensure_ascii=False)


@tool
def gitlab_browse(url: str) -> str:
    """Fetch a GitLab page (project, issue, merge request). Returns structured data if API-accessible, otherwise raw text."""
    if "://" not in url:
        url = f"{GITLAB}{'' if url.startswith('/') else '/'}{url}"
    # Try to detect issue URL and use API
    m = re.search(r'/([^/]+/[^/]+)/-/issues/(\d+)', url)
    if m:
        proj, iid = m.group(1), m.group(2)
        pid = requests.utils.quote(proj, safe="")
        r = requests.get(f"{GITLAB}/api/v4/projects/{pid}/issues/{iid}", timeout=20)
        if r.ok:
            i = r.json()
            return json.dumps({
                "site": "gitlab", "kind": "issue", "url": url,
                "title": i["title"], "state": i["state"],
                "labels": i.get("labels", []),
                "author": i.get("author", {}).get("username", ""),
                "description": (i.get("description") or "")[:2000],
                "upvotes": i.get("upvotes", 0),
            }, ensure_ascii=False)
    # Fallback: HTML scrape
    html = _fetch(url)
    if not html:
        return json.dumps({"error": "empty", "url": url})
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, nav"):
        tag.decompose()
    text = soup.get_text(" ", strip=True)[:3000]
    return json.dumps({"site": "gitlab", "kind": "page", "url": url, "text": text}, ensure_ascii=False)


# ============================================================
# Shopping Admin tools
# ============================================================

_ADMIN_SESS = requests.Session()
_ADMIN_LOGGED = False


def _admin_login():
    global _ADMIN_LOGGED
    if _ADMIN_LOGGED:
        return
    r = _ADMIN_SESS.get(f"{SHOPPING_ADMIN}/admin/", timeout=20, allow_redirects=True)
    soup = BeautifulSoup(r.text, "html.parser")
    fk = soup.select_one('input[name="form_key"]')
    _ADMIN_SESS.post(
        f"{SHOPPING_ADMIN}/admin/admin/dashboard/",
        data={
            "form_key": fk["value"] if fk else "",
            "login[username]": "admin",
            "login[password]": "admin1234",
        },
        timeout=20, allow_redirects=True,
    )
    _ADMIN_LOGGED = True


@tool
def admin_browse(path_or_url: str) -> str:
    """Browse the Shopping Admin panel. Pass a path like '/admin/sales/order/' or '/admin/catalog/product/'. Returns page text content."""
    _admin_login()
    if "://" in path_or_url:
        url = path_or_url
    else:
        url = f"{SHOPPING_ADMIN}{'' if path_or_url.startswith('/') else '/'}{path_or_url}"
    r = _ADMIN_SESS.get(url, timeout=30, allow_redirects=True)
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup.select("script, style, nav, header"):
        tag.decompose()
    text = soup.get_text(" ", strip=True)[:5000]
    return json.dumps({"site": "shopping_admin", "kind": "admin_page", "url": url, "text": text}, ensure_ascii=False)


# ============================================================
# Unified search dispatcher
# ============================================================

@tool
def multi_search(query: str, site: str = "auto") -> str:
    """Search across sandbox sites. `site` can be 'shopping', 'reddit', 'gitlab', 'admin', or 'auto' (searches all). Returns combined results."""
    results = {}
    sites = [site] if site != "auto" else ["shopping", "reddit", "gitlab"]
    for s in sites:
        if s == "shopping":
            results["shopping"] = json.loads(shop_search.invoke(query))
        elif s == "reddit":
            results["reddit"] = json.loads(reddit_search.invoke(query))
        elif s == "gitlab":
            results["gitlab"] = json.loads(gitlab_search.invoke(query))
    return json.dumps(results, ensure_ascii=False)


@tool
def multi_browse(url: str) -> str:
    """Browse any sandbox URL. Auto-detects which site it belongs to and uses the right scraper."""
    if "localhost:7770" in url or "__SHOPPING__" in url:
        return shop_browse.invoke(url)
    elif "localhost:9999" in url or "__REDDIT__" in url:
        return reddit_browse.invoke(url)
    elif "localhost:8023" in url or "__GITLAB__" in url:
        return gitlab_browse.invoke(url)
    elif "localhost:7780" in url or "__SHOPPING_ADMIN__" in url:
        return admin_browse.invoke(url)
    else:
        return json.dumps({"error": f"Unknown site for URL: {url}. Use localhost:7770 (shopping), localhost:9999 (reddit), localhost:8023 (gitlab), localhost:7780 (admin)"})


# ============================================================
# DeerFlow monkey-patch installer
# ============================================================

ALL_TOOLS = [
    multi_search, multi_browse,
    shop_search, shop_browse, shop_reviews,
    reddit_search, reddit_browse,
    gitlab_search, gitlab_issues, gitlab_browse,
    admin_browse,
]


def install_multi_site_tools() -> None:
    """Replace DeerFlow's web_search/crawl with our multi-site tools."""
    import importlib
    deerflow_root = str(ROOT / "third_party" / "deer-flow-v1")

    # Temporarily prioritize DeerFlow's src/ over ours
    import sys as _sys
    _sys.path.insert(0, deerflow_root)
    try:
        # Force reimport from DeerFlow's namespace
        if "src.tools.search" in _sys.modules:
            del _sys.modules["src.tools.search"]
        if "src.tools.crawl" in _sys.modules:
            del _sys.modules["src.tools.crawl"]
        if "src.graph.nodes" in _sys.modules:
            del _sys.modules["src.graph.nodes"]

        search_mod = importlib.import_module("src.tools.search")
        crawl_mod = importlib.import_module("src.tools.crawl")
        nodes_mod = importlib.import_module("src.graph.nodes")
    finally:
        _sys.path.remove(deerflow_root)

    search_mod.get_web_search_tool = lambda *a, **kw: multi_search
    nodes_mod.get_web_search_tool = lambda *a, **kw: multi_search
    nodes_mod.crawl_tool = multi_browse
    crawl_mod.crawl_tool = multi_browse


# ============================================================
# Task runner
# ============================================================

def _resolve_task_path(task_id: str) -> Path:
    parts = task_id.split("_")
    if "cross" in parts:
        return ROOT / "data" / "tasks" / "deep_research" / "cross_site" / f"{task_id}.json"
    site_map = {"shop": "shopping", "red": "reddit", "git": "gitlab"}
    site = site_map.get(parts[1], "shopping") if len(parts) >= 2 else "shopping"
    return ROOT / "data" / "tasks" / "deep_research" / site / f"{task_id}.json"


async def run_dr_task(task_id: str):
    install_multi_site_tools()

    from src.graph import build_graph
    from src.config.configuration import get_recursion_limit

    cfg = json.loads(_resolve_task_path(task_id).read_text())
    sites = cfg.get("sites", ["shopping"])
    ms = cfg.get("markdown_spec", {})

    # Build v3 markdown prompt
    site_desc = {
        "shopping": f"Shopping (Magento): {SHOPPING} — product catalog, reviews, prices",
        "reddit": f"Reddit (Postmill): {REDDIT} — 25 forums (technology, news, wallstreetbets...)",
        "gitlab": f"GitLab: {GITLAB} — 167 repos, issues, merge requests",
        "shopping_admin": f"Shopping Admin: {SHOPPING_ADMIN} — backend orders, inventory, customers",
    }
    sites_block = "\n".join(f"  - {site_desc.get(s, s)}" for s in sites)
    tools_block = "\n".join([
        "  - multi_search(query, site='auto') — search across all sites at once",
        "  - multi_browse(url) — fetch any sandbox URL",
        "  - shop_search(query), shop_browse(url), shop_reviews(product_url_or_id)",
        "  - reddit_search(forum), reddit_browse(url)",
        "  - gitlab_search(query), gitlab_issues(project, state), gitlab_browse(url)",
        "  - admin_browse(path) — browse shopping admin pages",
    ])

    prompt = f"""{cfg['intent']}

## Available sandbox sites:
{sites_block}

## Available tools:
{tools_block}

## Research protocol (MANDATORY — override default researcher instructions):

**You are doing deep research, not surface search.** The `multi_search` /
`shop_search` / `reddit_search` tools only give you a listing overview —
they are NOT sufficient on their own. You MUST drill deeper.

1. **For the Shopping site**: after `shop_search` or `shop_browse` on a
   category, you MUST call `shop_browse(product_url)` on **at least 6
   individual product detail pages** (URLs ending in `.html` with a
   product slug, e.g. `sony-zx110nc-noise-cancelling-headphones.html`).
   Optionally call `shop_reviews(product_url)` to get buyer quotes.
2. **For the Reddit site**: after `reddit_search` on a forum, you MUST
   call `reddit_browse(post_url)` on **at least 4 individual post URLs**
   (URLs like `/f/<board>/<id>/...`) to read the actual title, body, and
   top comments with upvote scores. Forum listing pages do NOT count.
3. Cite EVERY factual claim with a markdown link `[descriptive text](url)`
   pointing to the specific product or post URL you crawled — NOT the
   category/forum page.
4. A "product exists" citation is not enough — you must quote a specific
   price, rating, or buyer comment taken from the crawled page.

**IMPORTANT — do not write a meta-report about tool failures.** If a tool
returns empty or an error, retry with a different URL or search query.
Do not spend words describing "extraction challenges" or
"methodology limitations"; readers want product/forum substance, not
process commentary.

## Output requirements:
Write a **long-form markdown research report** (NOT JSON).
- Minimum {ms.get('min_words', 500)} words, {ms.get('min_paragraphs', 5)} paragraphs
- Include at least {ms.get('min_citations', 5)} inline citations as markdown links [text](url)
- Browse at least {ms.get('min_pages_browsed', 6)} distinct pages across the sites above
- Structure: introduction → findings per site → cross-site analysis → conclusion
- Every factual claim MUST have a citation linking to the sandbox page where you found it
- URLs must be from the sandbox sites listed above — NO external URLs
- Do NOT include sections like "Methodology", "Limitations", "Literature Review",
  "Survey Note", or "Future Research Directions" — they add word count without
  research substance. Spend all words on actual product/forum findings.
"""

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
            "max_step_num": 6,  # more steps for cross-site
            "mcp_settings": {"servers": {}},
        },
        "recursion_limit": get_recursion_limit(default=80),
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
        rep = final_state.get("final_report") or final_state.get("reporter_output") or ""
        print(f"\n====== FINAL REPORT ({len(rep)} chars) ======")
        print((rep or "")[:3000])
        out = ROOT / "data" / "results" / f"deerflow_{task_id}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rep or "(no final_report)", encoding="utf-8")
        print(f"\nsaved: {out}")


if __name__ == "__main__":
    task_id = sys.argv[1] if len(sys.argv) > 1 else "dr_cross_v3_0001"
    asyncio.run(run_dr_task(task_id))
