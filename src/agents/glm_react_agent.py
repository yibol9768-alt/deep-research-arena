"""Site-aware ReAct agent using GLM via Anthropic-compatible endpoint.

Exposes `glm_react_agent(page, task_cfg) -> str` usable by `PlaywrightRunner.run()`.

Tools are picked based on `task_cfg["sites"]`:
  - "shopping"  → Magento-specific tools (page_products, page_product, list_reviews, search)
  - "reddit"    → Postmill-specific tools (list_submissions, get_submission, list_user_submissions)

Common tools (always present): browse, read_visible, click_text, finish.
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from typing import Any

import anthropic

from envs.shopping.oracle_dr.magento_scrape import list_products, product_details, list_reviews
from envs.reddit.scrape import list_submissions as red_list_submissions, get_submission as red_get_submission, list_user_submissions as red_list_user_submissions
from src.metrics import EfficiencyMetrics, from_anthropic_response


LAST_METRICS: EfficiencyMetrics | None = None

MAX_STEPS = 20
MODEL = os.environ.get("GLM_MODEL", "glm-5.1")


_SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are a deep-research agent operating inside one or more sandboxed
    websites (listed in the task's `sites` field). You MUST answer by
    calling tools and end with the `finish` tool whose `answer_json`
    argument is a JSON string matching the task's report_schema.

    Rules:
      - Plan first: read the intent; identify what data you need; decide
        which pages to visit.
      - Always include a `citations` array inside the final JSON. Each
        citation is an object like:
          {"field": "<path in the report>", "url": "<sandboxed URL>"}
        The exact fields that require a citation are listed in the task's
        `citation_policy.required_for`. ALL of those MUST get a citation.
      - Use the site-specific structured tools (e.g. page_products,
        list_submissions) in preference to `browse` + `read_visible` —
        they return clean JSON of the facts you need.
      - If a listing tool returns < N results, visit the next page URL
        (e.g. ?p=2) via `browse`.
      - You have up to %d tool calls. Use them.
      - Return ONLY the JSON via `finish(answer_json=...)`. No prose.
    """
) % MAX_STEPS


_SYSTEM_PROMPT_V3 = textwrap.dedent(
    """\
    You are a deep-research agent operating inside sandboxed websites
    (listed in the task's `sites` field). Your job is to produce a
    **long-form markdown research report** that answers the task's
    `intent` in depth.

    Output contract:
      - Submit via the `finish` tool, passing the **full markdown report**
        as the `answer_json` argument (the name is legacy — treat it as
        free-form text).
      - DO NOT emit JSON. The expected output is prose + tables + lists,
        with markdown formatting.
      - Structure: intro paragraph → findings section(s) → conclusion.
        At minimum %d paragraphs, ~%d words, %d inline citations.
      - EVERY factual claim about a specific product, post, user, forum,
        rating, score, or comment count MUST be backed by a markdown
        citation like `[text](url)`. URLs must be sandboxed site pages.
      - Browse first, write last. Use site tools (page_products,
        list_submissions, get_submission, etc.) to collect facts before
        synthesizing.
      - You have up to %d tool calls. Visit distinct pages — the task's
        `min_pages_browsed` is a structural floor.
      - Write as an analyst, not a database dump: include reasoning,
        tradeoffs, comparisons.

    Common failure modes (AVOID):
      - Wrapping the report in JSON — it must be raw markdown.
      - Copying product titles as "reviews" — quote actual review bodies.
      - Making claims without a backing citation URL.
      - Skipping the synthesis / "why" / "tradeoff" discussion.
      - *** CRITICAL: When your research is done, you MUST call the `finish`
        tool with the full markdown report in `answer_json`. Do NOT just
        write a plain-text message saying "now let me compile the report".
        The ONLY way to submit your report is the `finish` tool call. ***
    """
)


def _render_system_prompt(task_cfg: dict) -> str:
    """Pick the prompt variant based on whether this is a v3 markdown task."""
    spec = task_cfg.get("markdown_spec") or {}
    if not spec:
        return _SYSTEM_PROMPT
    sites = task_cfg.get("sites") or []
    steps = MAX_STEPS
    if len(sites) > 1:
        steps = max(MAX_STEPS, int(task_cfg.get("expected_steps", 20)) + 10)
    return _SYSTEM_PROMPT_V3 % (
        int(spec.get("min_paragraphs", 4) or 4),
        int(spec.get("min_words", 400) or 400),
        int(spec.get("min_citations", 3) or 3),
        steps,
    )


_COMMON_TOOLS = [
    {
        "name": "browse",
        "description": "Navigate the browser to a URL (must be in the sandboxed site). Returns a short text summary.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "click_text",
        "description": "Click the first anchor on the current page whose visible text contains <text>.",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    },
    {
        "name": "read_visible",
        "description": "Return the visible text of the current page (truncated).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "finish",
        "description": "Submit the final JSON answer (string form of a JSON object matching the task's report_schema).",
        "input_schema": {"type": "object", "properties": {"answer_json": {"type": "string"}}, "required": ["answer_json"]},
    },
]


_SHOPPING_TOOLS = [
    {
        "name": "search",
        "description": "Search the Magento shopping catalog. Navigates to /catalogsearch/result/?q=<query>.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "page_products",
        "description": "Scrape the current Magento listing page. Returns a JSON array of {name, price, rating, product_url}.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "page_product",
        "description": "Scrape the current Magento product detail page. Returns {name, price, rating, review_count, product_url}.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_reviews",
        "description": "Fetch reviews for a Magento product by its numeric product_id. Returns array of {author, body, rating, title}.",
        "input_schema": {
            "type": "object",
            "properties": {"pid": {"type": "string"}, "max_pages": {"type": "integer", "default": 3}},
            "required": ["pid"],
        },
    },
]


_REDDIT_TOOLS = [
    {
        "name": "list_submissions",
        "description": "List submissions of a Postmill forum. `forum_or_url` can be slug ('news'), path ('/f/news'), or URL. Returns array of {title, url, author, comments, score, posted_at}.",
        "input_schema": {
            "type": "object",
            "properties": {"forum_or_url": {"type": "string"}},
            "required": ["forum_or_url"],
        },
    },
    {
        "name": "get_submission",
        "description": "Fetch a Postmill submission detail page. Returns {title, author, score, body_html, comments: [{author, body, score, posted_at}]}.",
        "input_schema": {
            "type": "object",
            "properties": {"url_or_path": {"type": "string"}},
            "required": ["url_or_path"],
        },
    },
    {
        "name": "list_user_submissions",
        "description": "List a Postmill user's recent submissions via /user/<username>/submissions.",
        "input_schema": {
            "type": "object",
            "properties": {"username": {"type": "string"}},
            "required": ["username"],
        },
    },
]


_GITLAB_TOOLS = [
    {
        "name": "gitlab_search",
        "description": "Search GitLab for projects by keyword. Returns array of {id, name, path, url, description, stars, forks}.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "gitlab_issues",
        "description": "List issues for a GitLab project. Pass numeric project ID. `state` can be 'opened','closed','all'. Returns array of {iid, title, state, labels, author, url}.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "state": {"type": "string", "default": "all"},
                "per_page": {"type": "integer", "default": 10},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "gitlab_browse",
        "description": "Fetch a GitLab page (project, issue, MR). If it's an issue URL, returns structured data via API. Otherwise returns page text.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
]


_ADMIN_TOOLS = [
    {
        "name": "admin_browse",
        "description": "Browse a Shopping Admin page (Magento backend). Pass a path like '/admin/dashboard/' or '/admin/sales/order/'. Requires login (handled automatically). Returns page text content.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
]


def _pick_tools(task_cfg: dict) -> list[dict]:
    sites = set(task_cfg.get("sites") or [])
    tools = list(_COMMON_TOOLS)
    if "shopping" in sites:
        tools.extend(_SHOPPING_TOOLS)
    if "reddit" in sites:
        tools.extend(_REDDIT_TOOLS)
    if "gitlab" in sites:
        tools.extend(_GITLAB_TOOLS)
    if "shopping_admin" in sites:
        tools.extend(_ADMIN_TOOLS)
    return tools


def _summary(page, limit: int = 2000) -> str:
    try:
        text = page.evaluate("() => document.body.innerText || ''") or ""
    except Exception:
        text = ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _http_get(url: str) -> str:
    """Simple HTTP GET via requests (no Playwright needed)."""
    import requests as _req
    try:
        r = _req.get(url, timeout=30, allow_redirects=True)
        return r.text if r.ok else ""
    except Exception as e:
        return ""


def _http_scrape_products(html: str) -> list[dict]:
    """Parse Magento product listing from HTML (requests-based)."""
    from bs4 import BeautifulSoup as _BS
    soup = _BS(html, "html.parser")
    items = []
    for el in soup.select("li.item.product.product-item")[:20]:
        a = el.select_one("a.product-item-link, .product-item-name a")
        name = a.get_text(strip=True) if a else ""
        url = a.get("href", "") if a else ""
        price = None
        pEl = el.select_one("[data-price-amount]")
        if pEl:
            try: price = float(pEl["data-price-amount"])
            except: pass
        rating = None
        rEl = el.select_one(".rating-result")
        if rEl:
            m = re.search(r"(\d+)%", rEl.get("title", ""))
            if m: rating = int(m.group(1)) / 20
        items.append({"name": name, "url": url, "price": price, "rating": rating})
    return items


def _http_scrape_product_detail(html: str, url: str) -> dict:
    """Parse Magento product detail page from HTML."""
    from bs4 import BeautifulSoup as _BS
    soup = _BS(html, "html.parser")
    d: dict = {"product_url": url}
    h1 = soup.select_one("h1.page-title span")
    d["name"] = h1.get_text(strip=True) if h1 else ""
    pEl = soup.select_one("[data-price-amount]")
    if pEl:
        try: d["price"] = float(pEl["data-price-amount"])
        except: pass
    rEl = soup.select_one(".rating-result")
    if rEl:
        m = re.search(r"(\d+)%", rEl.get("title", ""))
        if m: d["rating"] = int(m.group(1)) / 20
    rc = soup.select_one("a[href*='#reviews']")
    if rc:
        m = re.search(r"(\d+)", rc.get_text())
        if m: d["review_count"] = int(m.group(1))
    return d


_SUB_RE_AGENT = re.compile(r'<article[^>]*class="[^"]*submission[^"]*"[\s\S]*?</article>', re.I)

def _http_reddit_posts(url: str) -> list[dict]:
    """Parse Postmill submissions from HTML (requests-based)."""
    html = _http_get(url)
    posts = []
    for m in _SUB_RE_AGENT.finditer(html or ""):
        block = m.group(0)
        p: dict = {}
        tm = re.search(r'class="submission__link"[^>]*>([^<]+)</a>', block)
        if tm: p["title"] = re.sub(r"&#039;", "'", tm.group(1)).strip()
        um = re.search(r'href="(/f/[A-Za-z0-9_]+/\d+/[^"]+)"', block)
        reddit_base = os.environ.get("REDDIT", "http://localhost:9999")
        if um: p["url"] = reddit_base + um.group(1)
        am = re.search(r'class="submission__submitter[^"]*"[^>]*><strong>([^<]+)', block)
        if am: p["author"] = am.group(1).strip()
        sm = re.search(r'vote__net-score[^>]*>(-?\d+)', block)
        p["score"] = int(sm.group(1)) if sm else 0
        cm = re.search(r'data-comment-count="(\d+)"', block)
        p["comments"] = int(cm.group(1)) if cm else 0
        posts.append(p)
    return posts[:25]


def _http_reddit_detail(url: str) -> dict:
    """Parse a Postmill submission detail page."""
    html = _http_get(url)
    if not html:
        return {"error": "empty response"}
    out: dict = {"url": url}
    tm = re.search(r'<a[^>]*class="submission__link"[^>]*>([^<]+)</a>', html)
    if tm: out["title"] = re.sub(r"&#039;", "'", tm.group(1)).strip()
    sm = re.search(r'class="vote__net-score"[^>]*>(-?\d+)', html)
    out["score"] = int(sm.group(1)) if sm else 0
    comment_re = re.compile(r'<article[^>]*class="[^"]*comment[^"]*"[\s\S]*?</article>', re.I)
    comments = []
    for cm in comment_re.finditer(html):
        blk = cm.group(0)
        c: dict = {}
        am = re.search(r'comment__author[^>]*>([^<]+)|href="/user/([^"]+)"', blk)
        if am: c["author"] = (am.group(1) or am.group(2) or "").strip()
        bm = re.search(r'class="comment__body[^"]*"[^>]*>([\s\S]*?)</div>', blk)
        if bm: c["body"] = re.sub(r"<[^>]+>", " ", bm.group(1)).strip()[:400]
        sm2 = re.search(r'vote__net-score[^>]*>(-?\d+)', blk)
        c["score"] = int(sm2.group(1)) if sm2 else 0
        comments.append(c)
    out["comments"] = comments[:20]
    out["num_comments"] = len(comments)
    return out


def _exec_tool(name: str, args: dict, page, base_url: str, *, cross_site: bool = False) -> str:
    """Execute a tool call. When cross_site=True, use requests instead of Playwright for reliability."""
    try:
        shopping_url = os.environ.get("SHOPPING", "http://localhost:7770")
        reddit_url = os.environ.get("REDDIT", "http://localhost:9999")

        # ---- common ----
        if name == "browse":
            url = args["url"]
            if cross_site:
                html = _http_get(url)
                if not html:
                    return json.dumps({"error": "empty response", "url": url})
                from bs4 import BeautifulSoup as _BS
                soup = _BS(html, "html.parser")
                for t in soup.select("script,style"): t.decompose()
                text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:2000]
                return json.dumps({"url": url, "text": text})
            page.goto(url, timeout=30_000)
            page.wait_for_load_state("domcontentloaded")
            return json.dumps({"url": page.url, "text": _summary(page, 1200)})
        if name == "click_text":
            if cross_site:
                return json.dumps({"ok": False, "reason": "click_text not supported in cross-site mode, use browse with full URL instead"})
            target = args["text"].lower()
            handle = page.evaluate_handle(
                "(t) => { const as=[...document.querySelectorAll('a')]; return as.find(a => (a.innerText||'').toLowerCase().includes(t)); }",
                target,
            )
            el = handle.as_element() if handle else None
            if not el:
                return json.dumps({"ok": False, "reason": "no match"})
            el.click()
            page.wait_for_load_state("domcontentloaded")
            return json.dumps({"ok": True, "url": page.url})
        if name == "read_visible":
            if cross_site:
                return json.dumps({"error": "read_visible not supported in cross-site mode, use browse with the URL"})
            return json.dumps({"url": page.url, "text": _summary(page, 2500)})

        # ---- shopping (requests-based for cross-site) ----
        if name == "search":
            url = f"{shopping_url}/catalogsearch/result/?q={args['query']}"
            if cross_site:
                html = _http_get(url)
                items = _http_scrape_products(html)
                return json.dumps({"url": url, "count": len(items), "items": items}, ensure_ascii=False)
            page.goto(url, timeout=30_000)
            page.wait_for_load_state("domcontentloaded")
            return json.dumps({"url": page.url, "text": _summary(page, 1200)})
        if name == "page_products":
            if cross_site:
                return json.dumps({"error": "page_products requires browse first in cross-site mode. Use 'search' tool which returns items directly."})
            return json.dumps(list_products(page))
        if name == "page_product":
            if cross_site:
                return json.dumps({"error": "page_product not available in cross-site mode. Use 'browse' on the product URL."})
            return json.dumps(product_details(page))
        if name == "list_reviews":
            pid = args["pid"]
            max_pages = int(args.get("max_pages") or 3)
            reviews = []
            for p in range(1, max_pages + 1):
                url = f"{shopping_url}/review/product/listAjax/id/{pid}/?p={p}"
                html = _http_get(url)
                if not html or "review-item" not in html:
                    break
                from bs4 import BeautifulSoup as _BS
                soup = _BS(html, "html.parser")
                for el in soup.select(".review-item, li.item.review-item"):
                    author = el.select_one(".review-details-value, [itemprop='author']")
                    body = el.select_one(".review-content, [itemprop='description']")
                    title_el = el.select_one(".review-title")
                    rating = None
                    ratEl = el.select_one(".rating-result [title]")
                    if ratEl:
                        m = re.search(r"(\d+)%", ratEl.get("title") or "")
                        if m: rating = int(m.group(1)) // 20
                    reviews.append({
                        "author": author.get_text(strip=True) if author else "",
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "body": body.get_text(" ", strip=True) if body else "",
                        "rating": rating,
                    })
            return json.dumps(reviews)

        # ---- reddit (requests-based for cross-site) ----
        if name == "list_submissions":
            forum = args["forum_or_url"]
            if "://" in forum:
                url = forum
            elif forum.startswith("/"):
                url = reddit_url + forum
            else:
                url = f"{reddit_url}/f/{forum}"
            if cross_site:
                posts = _http_reddit_posts(url)
                return json.dumps(posts)
            subs = red_list_submissions(args["forum_or_url"], base=reddit_url, page=page)
            return json.dumps(subs[:25])
        if name == "get_submission":
            url_or_path = args["url_or_path"]
            if "://" not in url_or_path:
                url_or_path = reddit_url + ("" if url_or_path.startswith("/") else "/") + url_or_path
            if cross_site:
                return json.dumps(_http_reddit_detail(url_or_path))
            d = red_get_submission(args["url_or_path"], base=reddit_url, page=page)
            if isinstance(d.get("comments"), list):
                d["comments"] = d["comments"][:30]
            return json.dumps(d)
        if name == "list_user_submissions":
            if cross_site:
                url = f"{reddit_url}/user/{args['username']}/submissions"
                posts = _http_reddit_posts(url)
                return json.dumps(posts)
            subs = red_list_user_submissions(args["username"], base=reddit_url, page=page)
            return json.dumps(subs[:25])

        # ---- gitlab ----
        if name == "gitlab_search":
            import requests as _req
            gitlab_url = os.environ.get("GITLAB", "http://localhost:8023")
            r = _req.get(f"{gitlab_url}/api/v4/projects",
                         params={"search": args["query"], "per_page": 10}, timeout=20)
            projects = [{"id": p["id"], "name": p["name"],
                         "path": p["path_with_namespace"],
                         "url": f"{gitlab_url}/{p['path_with_namespace']}",
                         "description": (p.get("description") or "")[:200],
                         "stars": p.get("star_count", 0),
                         "forks": p.get("forks_count", 0)}
                        for p in (r.json() if r.ok else [])]
            return json.dumps({"count": len(projects), "projects": projects})
        if name == "gitlab_issues":
            import requests as _req
            gitlab_url = os.environ.get("GITLAB", "http://localhost:8023")
            pid = args["project_id"]
            r = _req.get(f"{gitlab_url}/api/v4/projects/{pid}/issues",
                         params={"state": args.get("state", "all"),
                                 "per_page": args.get("per_page", 10)},
                         timeout=20)
            issues = [{"iid": i["iid"], "title": i["title"], "state": i["state"],
                       "labels": i.get("labels", []),
                       "author": i.get("author", {}).get("username", ""),
                       "url": i.get("web_url", ""),
                       "description_preview": (i.get("description") or "")[:300]}
                      for i in (r.json() if r.ok else [])]
            return json.dumps({"count": len(issues), "issues": issues})
        if name == "gitlab_browse":
            import requests as _req
            url = args["url"]
            gitlab_url = os.environ.get("GITLAB", "http://localhost:8023")
            # Try API for issues
            m = re.search(r'/([^/]+/[^/]+)/-/issues/(\d+)', url)
            if m:
                from urllib.parse import quote
                proj, iid = quote(m.group(1), safe=""), m.group(2)
                r = _req.get(f"{gitlab_url}/api/v4/projects/{proj}/issues/{iid}", timeout=20)
                if r.ok:
                    i = r.json()
                    return json.dumps({"kind": "issue", "title": i["title"],
                                       "state": i["state"], "labels": i.get("labels", []),
                                       "description": (i.get("description") or "")[:2000]})
            # Fallback: fetch HTML
            r = _req.get(url, timeout=20)
            from bs4 import BeautifulSoup as _BS
            soup = _BS(r.text, "html.parser")
            for t in soup.select("script,style,nav"): t.decompose()
            return json.dumps({"kind": "page", "url": url,
                               "text": soup.get_text(" ", strip=True)[:3000]})

        # ---- shopping admin ----
        if name == "admin_browse":
            import requests as _req
            from bs4 import BeautifulSoup as _BS
            admin_url = os.environ.get("SHOPPING_ADMIN", "http://localhost:7780")
            sess = _req.Session()
            # Login
            r = sess.get(f"{admin_url}/admin/", timeout=20, allow_redirects=True)
            soup = _BS(r.text, "html.parser")
            fk = soup.select_one('input[name="form_key"]')
            sess.post(f"{admin_url}/admin/admin/dashboard/", data={
                "form_key": fk["value"] if fk else "",
                "login[username]": "admin", "login[password]": "admin1234",
            }, timeout=20, allow_redirects=True)
            path = args["path"]
            if not path.startswith("http"):
                path = f"{admin_url}{'' if path.startswith('/') else '/'}{path}"
            r = sess.get(path, timeout=30, allow_redirects=True)
            soup = _BS(r.text, "html.parser")
            for t in soup.select("script,style,nav,header"): t.decompose()
            return json.dumps({"kind": "admin_page", "url": path,
                               "text": soup.get_text(" ", strip=True)[:5000]})

    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
    return json.dumps({"error": f"unknown tool {name}"})


def glm_react_agent(page, task_cfg: dict) -> str:
    """Run the ReAct loop against one of our sandboxed sites."""
    global LAST_METRICS
    import time as _time
    metrics = EfficiencyMetrics(model=MODEL)
    LAST_METRICS = metrics
    _t0 = _time.time()

    os.environ.setdefault("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        raise RuntimeError(
            "Set ANTHROPIC_AUTH_TOKEN (or ANTHROPIC_API_KEY) to a Zhipu coding-plan token. "
            "See README.md > Setup."
        )
    client = anthropic.Anthropic()

    start_url = task_cfg.get("start_url", "") or ""
    base_url = start_url
    if "://" in base_url:
        base_url = "/".join(base_url.split("/")[:3])
    else:
        base_url = "http://localhost:7770"

    tools = _pick_tools(task_cfg)

    # v3 tasks don't have a report_schema; include markdown_spec instead
    # so the agent sees its concrete floors.
    is_v3 = bool(task_cfg.get("markdown_spec"))
    spec_field = "markdown_spec" if is_v3 else "report_schema"
    user_prompt = json.dumps(
        {
            "sites": task_cfg.get("sites"),
            "intent": task_cfg.get("intent"),
            "start_url": task_cfg.get("start_url"),
            spec_field: task_cfg.get(spec_field),
            "citation_policy": task_cfg.get("citation_policy"),
        },
        ensure_ascii=False,
    )

    system_prompt = _render_system_prompt(task_cfg)
    messages: list[dict] = [
        {"role": "user", "content": f"Task spec (JSON):\n{user_prompt}\n\nThe browser is already on {page.url if page else start_url}. Use tools to complete the task."}
    ]

    final_answer = ""
    # Cross-site tasks need more steps; use expected_steps or 2× for multi-site
    sites = task_cfg.get("sites") or []
    max_steps = MAX_STEPS
    if len(sites) > 1:
        max_steps = max(MAX_STEPS, int(task_cfg.get("expected_steps", 20)) + 10)
    for _ in range(max_steps):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
        except Exception as e:
            metrics.wall_time_s = _time.time() - _t0
            return f'{{"error": "LLM error: {type(e).__name__}: {e}"}}'

        t_in, t_out = from_anthropic_response(resp, MODEL)
        metrics.add_llm_call(tokens_in=t_in, tokens_out=t_out, model=MODEL)

        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            final_answer = "\n".join(text_parts)
            break

        tool_results = []
        saw_finish = False
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == "finish":
                final_answer = block.input.get("answer_json", "") or ""
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "ok",
                })
                saw_finish = True
                continue
            result = _exec_tool(block.name, dict(block.input or {}), page, base_url,
                                cross_site=len(sites) > 1)
            metrics.add_tool_call(block.name)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result[:8000],
            })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        if saw_finish:
            break

    # Fallback: if the final answer is missing OR is just short meta-commentary
    # (e.g. "Let me compile the report"), force a final prose report
    _looks_like_report = (len(final_answer or "") >= 300 and
                          ("#" in (final_answer or "") or "[" in (final_answer or "")))
    if not final_answer or not _looks_like_report:
        try:
            # Extract gathered tool-result data as plain-text context
            # (rebuild a CLEAN message list with only string content — some proxies
            # reject mixed tool_result blocks)
            gathered = []
            for m in messages:
                c = m.get("content")
                if isinstance(c, str):
                    gathered.append(c[:1500])
                elif isinstance(c, list):
                    for item in c:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                gathered.append(str(item.get("text", ""))[:1500])
                            elif item.get("type") == "tool_result":
                                gathered.append(str(item.get("content", ""))[:1500])
                        else:
                            # Anthropic TextBlock / ToolUseBlock
                            t = getattr(item, "text", None) or getattr(item, "input", None)
                            if t:
                                gathered.append(str(t)[:1500])
            context = "\n\n".join(gathered)[:30000]

            final_msg = (
                "You have used all your tool calls. Based on the data you gathered, "
                "write the complete markdown research report as your response — "
                "no more tool calls.\n\n"
                "Task intent: " + task_cfg.get("intent", "") + "\n\n"
                "Data gathered during research:\n" + context + "\n\n"
                "Now write the full report with citations [text](url), "
                "following the required structure."
            )
            resp_final = client.messages.create(
                model=MODEL, max_tokens=6000, system=system_prompt,
                messages=[{"role": "user", "content": final_msg}],
            )
            t_in, t_out = from_anthropic_response(resp_final, MODEL)
            metrics.add_llm_call(tokens_in=t_in, tokens_out=t_out, model=MODEL)
            text_parts = [b.text for b in resp_final.content if getattr(b, "type", None) == "text"]
            final_answer = "\n".join(text_parts)
        except Exception as e:
            final_answer = f'{{"error": "fallback failed: {type(e).__name__}: {e}"}}'

    metrics.wall_time_s = _time.time() - _t0
    return final_answer or '{"error": "agent did not produce an answer"}'
