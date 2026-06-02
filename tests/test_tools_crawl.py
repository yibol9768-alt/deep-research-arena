"""Offline tests for the ``crawl`` provider (src/rl/tools_crawl.py).

Everything runs on system ``python3`` with NO network: a tiny in-memory mock
backend serves a small link graph. The seed page links to three in-allowlist
PDPs, one off-allowlist external host, and one deeper page (reachable only at
depth 2). Tests assert depth/page caps, allowlist enforcement, and that every
in-allowlist (url, text) pair lands in the ToolResult and folds into the env's
``retrieved_snippets``.

Coverage map (DESIGN OFFLINE TEST, items 1-4):
  (1) depth/page limits honoured (max_pages caps the count; max_depth=1 excludes
      the depth-2 page).
  (2) the off-allowlist link is NEVER fetched and not in fetched_urls.
  (3) snippets contains (url, text) for each in-allowlist page, and after a
      CallTool('crawl') the env's retrieved_snippets has all of them.
  (4) a seed off-allowlist -> ok=False with error 'seed_not_in_allowlist'.
"""

from __future__ import annotations

from typing import Any

from src.rl.env import CallTool, MockSandboxBackend, ResearchEnv
from src.rl.tools import ToolContext
from src.rl.tools_crawl import CrawlTool, _default_url_is_sandbox, provide_tools
from src.verifiers.citation_format import canonicalize_url

# --------------------------------------------------------------------------- #
# A tiny link graph over the sandbox hosts, plus one off-allowlist external.
#
#   SEED (depth 0)  -> PDP_1, PDP_2, FORUM (depth 1)  + EXTERNAL (off-allowlist)
#   PDP_1 (depth 1) -> DEEP (depth 2)
#
# The seed text embeds links as a mix of HTML anchors and markdown so the
# extractor's HTML + markdown + bare-URL paths are all exercised.
# --------------------------------------------------------------------------- #
SEED = "http://localhost:7770/catalog/headphones.html"
PDP_1 = "http://localhost:7770/products/alpha.html"
PDP_2 = "http://localhost:7770/products/beta.html"
FORUM = "http://localhost:9999/f/headphones/thread-1"
DEEP = "http://localhost:7770/products/alpha-specs.html"
EXTERNAL = "http://evil.example.com/leak"
# A look-alike host that must NOT match by substring (prefix-attack guard).
LOOKALIKE = "http://localhost:77703/leak"

PAGES = {
    SEED: (
        "Headphones catalog.\n"
        f'<a href="{PDP_1}">Alpha</a>\n'
        f'See also [Beta]({PDP_2}) and the discussion at {FORUM}.\n'
        f'<a href="{EXTERNAL}">external review</a>\n'
        f'<a href="{LOOKALIKE}">lookalike</a>\n'
    ),
    PDP_1: (
        "Alpha headphones: balanced sound, long battery life, travel comfort. "
        f'Full specs: <a href="{DEEP}">spec sheet</a>.'
    ),
    PDP_2: "Beta headphones: bright sound, snug fit, budget value.",
    FORUM: "Forum thread: owners report long-term comfort and durable build.",
    DEEP: "Alpha spec sheet: 30h battery, 40mm drivers, ANC depth -28dB.",
    EXTERNAL: "SHOULD NEVER BE FETCHED - off-allowlist external host.",
    LOOKALIKE: "SHOULD NEVER BE FETCHED - prefix-attack lookalike host.",
}
INDEX: dict[str, list[str]] = {}

TASK_ID = "tools_crawl_synth"
PROMPT = "Crawl the headphones catalog and summarize the products."


def _task_config(tools_allowed: list[str] | None = None) -> dict[str, Any]:
    acquisition: dict[str, Any] = {"modalities": ["shim"], "backend": "shim"}
    if tools_allowed is not None:
        acquisition["tools_allowed"] = list(tools_allowed)
    return {
        "task_id": TASK_ID,
        "intent": PROMPT,
        "prompt": PROMPT,
        "acquisition": acquisition,
        "sandbox_hosts": ["localhost:7770", "localhost:9999", "localhost:8090"],
    }


def _backend() -> MockSandboxBackend:
    return MockSandboxBackend(PAGES, INDEX)


def _ctx(backend: MockSandboxBackend) -> ToolContext:
    return ToolContext(
        backend=backend,
        task_config=_task_config(),
        fetch=lambda url: backend.fetch(url),
        canonicalize=canonicalize_url,
        extras={},
    )


# =========================================================================== #
# provide_tools() yields crawl, importable without heavy deps.
# =========================================================================== #
def test_provide_tools_yields_crawl() -> None:
    tools = provide_tools()
    assert [t.name for t in tools] == ["crawl"]
    tool = tools[0]
    assert tool.description
    assert tool.args_schema["seed_url"]["required"] is True
    assert tool.args_schema["max_depth"]["required"] is False
    assert tool.args_schema["max_pages"]["required"] is False
    assert tool.args_schema["path_filter"]["required"] is False


# =========================================================================== #
# (4) Seed off-allowlist -> ok=False, no fetch.
# =========================================================================== #
def test_seed_off_allowlist_rejected() -> None:
    result = CrawlTool().run(_ctx(_backend()), {"seed_url": EXTERNAL})
    assert result.ok is False
    assert result.error == "seed_not_in_allowlist"
    assert result.fetched_urls == []
    assert result.snippets == {}


def test_empty_seed_is_graceful() -> None:
    result = CrawlTool().run(_ctx(_backend()), {"seed_url": "   "})
    assert result.ok is False
    assert result.error == "empty_seed_url"


def test_prefix_attack_host_not_in_allowlist() -> None:
    # The look-alike host (localhost:77703) must NOT pass host:port equality.
    assert _default_url_is_sandbox(LOOKALIKE) is False
    assert _default_url_is_sandbox(SEED) is True
    assert _default_url_is_sandbox(FORUM) is True
    # A bare host with no port is not one of our :7770/:9999/:8090 hosts.
    assert _default_url_is_sandbox("http://localhost/foo") is False


# =========================================================================== #
# (1) Depth/page limits + (2) off-allowlist link never fetched.
# =========================================================================== #
def test_depth_one_excludes_deeper_page_and_drops_offhost() -> None:
    result = CrawlTool().run(
        _ctx(_backend()), {"seed_url": SEED, "max_depth": 1, "max_pages": 25}
    )
    assert result.ok is True
    crawled = set(result.fetched_urls)
    # depth-0 seed + depth-1 in-allowlist children.
    assert SEED in crawled
    assert PDP_1 in crawled
    assert PDP_2 in crawled
    assert FORUM in crawled
    # DEEP is only reachable at depth 2 -> excluded at max_depth=1.
    assert DEEP not in crawled
    # The off-allowlist external + look-alike are NEVER fetched.
    assert EXTERNAL not in crawled
    assert LOOKALIKE not in crawled
    # snippets carry the real page text for each crawled page.
    assert result.snippets[PDP_1] == PAGES[PDP_1]
    assert result.snippets[FORUM] == PAGES[FORUM]


def test_depth_two_reaches_deeper_page() -> None:
    result = CrawlTool().run(
        _ctx(_backend()), {"seed_url": SEED, "max_depth": 2, "max_pages": 25}
    )
    assert result.ok is True
    crawled = set(result.fetched_urls)
    assert DEEP in crawled  # now reachable via PDP_1 at depth 2
    assert EXTERNAL not in crawled
    assert LOOKALIKE not in crawled


def test_max_pages_caps_the_count() -> None:
    result = CrawlTool().run(
        _ctx(_backend()), {"seed_url": SEED, "max_depth": 3, "max_pages": 2}
    )
    assert result.ok is True
    assert len(result.fetched_urls) == 2
    assert len(result.snippets) == 2
    # The seed is always the first page crawled.
    assert SEED in result.fetched_urls


def test_path_filter_keeps_crawl_tight() -> None:
    # Only follow links under the /products/ path; the FORUM link is dropped.
    result = CrawlTool().run(
        _ctx(_backend()),
        {"seed_url": SEED, "max_depth": 1, "max_pages": 25, "path_filter": "/products/"},
    )
    assert result.ok is True
    crawled = set(result.fetched_urls)
    assert SEED in crawled  # seed itself is always fetched
    assert PDP_1 in crawled
    assert PDP_2 in crawled
    assert FORUM not in crawled  # filtered out by path_filter


def test_max_depth_zero_only_fetches_seed() -> None:
    result = CrawlTool().run(
        _ctx(_backend()), {"seed_url": SEED, "max_depth": 0, "max_pages": 25}
    )
    assert result.ok is True
    assert result.fetched_urls == [SEED]


# =========================================================================== #
# (3) The env folds crawled pairs into retrieved_snippets after a CallTool.
# =========================================================================== #
def test_env_call_tool_crawl_folds_into_grounding() -> None:
    cfg = _task_config(tools_allowed=["search", "fetch", "crawl"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()

    obs, done, info = env.step(
        CallTool("crawl", {"seed_url": SEED, "max_depth": 1, "max_pages": 25})
    )
    assert done is False
    assert info["ok"] is True
    assert info["tool"] == "crawl"

    # Every in-allowlist crawled page folds into the SAME slots _do_read writes.
    for url in (SEED, PDP_1, PDP_2, FORUM):
        assert canonicalize_url(url) in obs["retrieved_snippets"]
        assert obs["retrieved_snippets"][canonicalize_url(url)] == PAGES[url]
        assert url in obs["fetched_urls"]

    # The off-allowlist hosts are absent from the grounding store entirely.
    assert canonicalize_url(EXTERNAL) not in obs["retrieved_snippets"]
    assert canonicalize_url(LOOKALIKE) not in obs["retrieved_snippets"]

    # Recorded under /tool/crawl.
    rollout = env.to_rollout()
    assert any(c["endpoint"] == "/tool/crawl" for c in rollout.tool_calls)


def test_env_crawl_seed_off_allowlist_is_graceful() -> None:
    cfg = _task_config(tools_allowed=["search", "fetch", "crawl"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()
    obs, done, info = env.step(CallTool("crawl", {"seed_url": EXTERNAL}))
    assert done is False
    assert info["ok"] is False
    assert info["error"] == "seed_not_in_allowlist"
    # Nothing landed.
    assert obs["retrieved_snippets"] == {}
    assert obs["fetched_urls"] == []
