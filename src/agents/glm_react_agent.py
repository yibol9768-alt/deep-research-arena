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


def _pick_tools(task_cfg: dict) -> list[dict]:
    sites = set(task_cfg.get("sites") or [])
    tools = list(_COMMON_TOOLS)
    if "shopping" in sites:
        tools.extend(_SHOPPING_TOOLS)
    if "reddit" in sites:
        tools.extend(_REDDIT_TOOLS)
    return tools


def _summary(page, limit: int = 2000) -> str:
    try:
        text = page.evaluate("() => document.body.innerText || ''") or ""
    except Exception:
        text = ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _exec_tool(name: str, args: dict, page, base_url: str) -> str:
    try:
        # ---- common ----
        if name == "browse":
            page.goto(args["url"], timeout=30_000)
            page.wait_for_load_state("domcontentloaded")
            return json.dumps({"url": page.url, "text": _summary(page, 1200)})
        if name == "click_text":
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
            return json.dumps({"url": page.url, "text": _summary(page, 2500)})

        # ---- shopping ----
        if name == "search":
            url = f"{base_url.rstrip('/')}/catalogsearch/result/?q={args['query']}"
            page.goto(url, timeout=30_000)
            page.wait_for_load_state("domcontentloaded")
            return json.dumps({"url": page.url, "text": _summary(page, 1200)})
        if name == "page_products":
            return json.dumps(list_products(page))
        if name == "page_product":
            return json.dumps(product_details(page))
        if name == "list_reviews":
            pid = args["pid"]
            max_pages = int(args.get("max_pages") or 3)
            origin = base_url.rstrip("/")
            out = []
            for p in range(1, max_pages + 1):
                page.goto(f"{origin}/review/product/listAjax/id/{pid}/?p={p}", timeout=20_000)
                batch = list_reviews(page)
                if not batch:
                    break
                out.extend(batch)
            return json.dumps(out)

        # ---- reddit (Postmill) ----
        if name == "list_submissions":
            subs = red_list_submissions(args["forum_or_url"], base=base_url, page=page)
            return json.dumps(subs[:25])  # cap to page-worth
        if name == "get_submission":
            d = red_get_submission(args["url_or_path"], base=base_url, page=page)
            # Truncate comments to avoid blowing up the context
            if isinstance(d.get("comments"), list):
                d["comments"] = d["comments"][:30]
            return json.dumps(d)
        if name == "list_user_submissions":
            subs = red_list_user_submissions(args["username"], base=base_url, page=page)
            return json.dumps(subs[:25])

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

    user_prompt = json.dumps(
        {
            "sites": task_cfg.get("sites"),
            "intent": task_cfg.get("intent"),
            "start_url": task_cfg.get("start_url"),
            "report_schema": task_cfg.get("report_schema"),
            "citation_policy": task_cfg.get("citation_policy"),
        },
        ensure_ascii=False,
    )

    messages: list[dict] = [
        {"role": "user", "content": f"Task spec (JSON):\n{user_prompt}\n\nThe browser is already on {page.url}. Use tools to complete the task."}
    ]

    final_answer = ""
    for _ in range(MAX_STEPS):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=_SYSTEM_PROMPT,
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
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    final_answer = block.text
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
            result = _exec_tool(block.name, dict(block.input or {}), page, base_url)
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

    metrics.wall_time_s = _time.time() - _t0
    return final_answer or '{"error": "agent did not produce an answer"}'
