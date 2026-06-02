"""Offline tests for the P0 typed tool registry (docs/ACQUISITION_ROADMAP.md sec 2).

Everything here runs on system ``python3`` with NO network, GPU, or live shim:
the backend is :class:`MockSandboxBackend` and the ``structured_lookup`` transport
is injected via ``ToolContext.extras["structured_lookup_post"]`` so the typed
PDP/post records are canned dicts that mirror the shim's ``ProductLookupResponse``
/ ``PostLookupResponse`` shapes (integrations/search_shim/app.py:561,520).

Coverage map (task items a-f):
  (a) ToolRegistry.register / get / list / has + allowed-filter view.
  (b) the ``search`` and ``fetch`` floor tools land (url, text) into the
      grounding store (snippets + fetched_urls / hits).
  (c) ``structured_lookup`` returns a typed record AND lands a citeable
      (url, text) pair, for product and post kinds; ok==false is graceful.
  (d) parse_action parses a ``TOOL:`` directive and the JSON call_tool form
      into a CallTool.
  (e) ResearchEnv.step dispatches a CallTool, honours tools_allowed (a
      disallowed/unknown tool is a graceful observation, not a crash, and the
      episode continues) and counts the call against max_tool_calls.
  (f) BYTE-IDENTICAL: an episode with no tools_allowed produces the SAME
      retrieved_snippets / fetched_urls / report_md and the SAME
      ArenaEvaluator(mode='fast') composite + per_dim whether it is driven by
      the legacy Search/Open/Read opcodes or routed through the registry's
      search/fetch tools via TOOL: directives.
"""

from __future__ import annotations

from typing import Any

from src.eval.evaluator import ArenaEvaluator
from src.rl.action_parser import parse_action
from src.rl.env import (
    CallTool,
    Cite,
    Finalize,
    MockSandboxBackend,
    Open,
    Read,
    ResearchEnv,
    Search,
)
from src.rl.policy import MockPolicy
from src.rl.runner import run_episode
from src.rl.tools import (
    FetchTool,
    SearchTool,
    StructuredLookupTool,
    ToolContext,
    ToolRegistry,
    ToolResult,
    build_default_registry,
    build_tool_registry,
)
from src.verifiers.citation_format import canonicalize_url


# --------------------------------------------------------------------------- #
# Shared fixtures: one task, two resolved sandbox URLs, a tiny markdown spec.
# Mirrors tests/test_modality_parity.py so the reward path is exercised the
# same way (in-sandbox localhost:7770 / :9999 URLs, fast + strict grounding).
# --------------------------------------------------------------------------- #
TASK_ID = "tool_registry_synth"
PROMPT = "Compare Alpha headphones using product and forum evidence."

URL_PRODUCT = "http://localhost:7770/product-a.html"
URL_FORUM = "http://localhost:9999/f/headphones/alpha-thread"

PAGES = {
    URL_PRODUCT: (
        "Alpha headphones balanced sound battery life comfort travel value. "
        "Evidence from a hands-on product test with practical limitations noted."
    ),
    URL_FORUM: (
        "Forum owners report long term comfort, value, fit and durability "
        "evidence for Alpha headphones across many months of everyday use."
    ),
}
INDEX = {PROMPT: [URL_PRODUCT, URL_FORUM]}

REPORT_MD = (
    "# Alpha Headphones Review\n\n"
    "Alpha headphones deliver balanced sound and strong battery life, with "
    f"comfort suited to travel use [product]({URL_PRODUCT}).\n\n"
    "Owners on the forum corroborate long-term comfort, fit and durability "
    f"over months of everyday use [forum]({URL_FORUM}).\n"
)


def _task_config(tools_allowed: list[str] | None = None) -> dict[str, Any]:
    acquisition: dict[str, Any] = {"modalities": ["shim"], "backend": "shim"}
    if tools_allowed is not None:
        acquisition["tools_allowed"] = list(tools_allowed)
    return {
        "task_id": TASK_ID,
        "intent": PROMPT,
        "prompt": PROMPT,
        "acquisition": acquisition,
        "sandbox_hosts": ["localhost:7770", "localhost:9999"],
        "markdown_spec": {
            "min_words": 20,
            "max_words": 240,
            "min_paragraphs": 2,
            "min_citations": 1,
            "min_pages_browsed": 0,
        },
        "citation_policy": {"must_be_in_domain": []},
        "url_coverage": {
            "min_unique_urls_cited": 1,
            "min_must_cite_recall": 0.0,
            "min_expected_pool_coverage": 0.0,
            "min_domain_balance": 0.0,
        },
        "search": {"target_distinct_queries": 1},
    }


def _backend() -> MockSandboxBackend:
    return MockSandboxBackend(PAGES, INDEX)


def _ctx(backend: MockSandboxBackend, *, extras: dict[str, Any] | None = None) -> ToolContext:
    """A ToolContext wired exactly like ``ResearchEnv._tool_ctx`` (no truncation)."""
    return ToolContext(
        backend=backend,
        task_config=_task_config(),
        fetch=lambda url: backend.fetch(url),
        canonicalize=canonicalize_url,
        extras=dict(extras or {}),
    )


def _evaluator() -> ArenaEvaluator:
    ev = ArenaEvaluator(TASK_ID, mode="fast")
    ev._task_config = _task_config()
    # Strict grounding (matches the train pilot + parity test): no text-only
    # proxy, citations counted against the fetch trace, deterministic in fast.
    ev._rl_strict = True
    return ev


# Canned typed records mirroring the shim's response models. The transport
# callable returns these by path so structured_lookup never touches the network.
PRODUCT_RECORD = {
    "ok": True,
    "url": URL_PRODUCT,
    "name": "Alpha Headphones",
    "price": 199.99,
    "rating": 4.5,
    "sku": "ALPHA-001",
    "description": "Balanced sound, long battery life, comfortable for travel.",
    "review_count": 128,
    "in_stock": True,
}
POST_RECORD = {
    "ok": True,
    "url": URL_FORUM,
    "title": "Alpha headphones long-term review",
    "author": "owner_jane",
    "forum": "headphones",
    "score": 342,
    "comment_count": 57,
    "body": "After months of everyday use the Alpha comfort and durability hold up.",
    "top_comments": [
        {"author": "user_a", "body": "Fit stays comfortable on long flights."},
        {"author": "user_b", "body": "Battery and value are excellent."},
    ],
}


def _fake_structured_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Injected structured-lookup transport: route by shim path, no I/O."""
    leaf = path.strip("/").split("/")[-1]
    if leaf == "product_lookup":
        return dict(PRODUCT_RECORD)
    if leaf == "post_lookup":
        return dict(POST_RECORD)
    return {"ok": False, "url": payload.get("url", ""), "error": "unknown_endpoint"}


# =========================================================================== #
# (a) Registry register / get / list / has + allowed-filter.
# =========================================================================== #
def test_registry_register_get_list_has() -> None:
    reg = ToolRegistry()
    assert reg.list() == []
    assert reg.get("search") is None
    assert reg.has("search") is False

    search = SearchTool()
    fetch = FetchTool()
    reg.register(search)
    reg.register(fetch)

    assert reg.get("search") is search
    assert reg.get("fetch") is fetch
    assert reg.has("search") is True
    assert reg.has("missing") is False
    # Insertion order preserved.
    assert reg.list() == ["search", "fetch"]


def test_registry_register_overrides_by_name() -> None:
    reg = ToolRegistry()
    first = SearchTool()
    second = SearchTool()
    reg.register(first)
    reg.register(second)
    # Same name -> later register wins, no duplicate entry.
    assert reg.list() == ["search"]
    assert reg.get("search") is second


def test_registry_allowed_filters_to_requested_and_registered() -> None:
    full = build_default_registry()
    assert set(full.list()) >= {"search", "fetch", "structured_lookup"}

    # Allow-list filters to requested-AND-registered names only.
    view = full.allowed(["search", "structured_lookup", "does_not_exist"])
    assert view.has("search") is True
    assert view.has("structured_lookup") is True
    assert view.has("does_not_exist") is False
    assert view.has("fetch") is False
    assert view.list() == ["search", "structured_lookup"]

    # None -> the floor.
    floor = full.allowed(None)
    assert floor.list() == ["search", "fetch"]


def test_build_tool_registry_default_is_floor() -> None:
    # No tools_allowed -> floor only.
    reg = build_tool_registry(_task_config(tools_allowed=None))
    assert reg.list() == ["search", "fetch"]
    assert reg.has("structured_lookup") is False

    # Explicit ["search","fetch"] -> identical floor.
    reg2 = build_tool_registry(_task_config(tools_allowed=["search", "fetch"]))
    assert reg2.list() == ["search", "fetch"]

    # Opting in to a new tool exposes it; unknown requested names are dropped.
    ctx = _ctx(_backend())
    reg3 = build_tool_registry(
        _task_config(tools_allowed=["fetch", "structured_lookup", "nope"]),
        ctx,
    )
    assert reg3.has("structured_lookup") is True
    assert reg3.has("fetch") is True
    assert reg3.has("nope") is False
    assert reg3.has("search") is False
    # The silent drop is observable via ctx.extras, never raised.
    assert "nope" in ctx.extras.get("dropped_tools", [])


# =========================================================================== #
# (b) Floor tools land (url, text) into the grounding store.
# =========================================================================== #
def test_search_tool_returns_hits() -> None:
    backend = _backend()
    result = SearchTool().run(_ctx(backend), {"query": PROMPT})
    assert isinstance(result, ToolResult)
    assert result.ok is True
    urls = {h["url"] for h in result.hits}
    assert urls == {URL_PRODUCT, URL_FORUM}
    assert result.n_results == 2
    # SERP is rendered for the obs; no grounding pairs from a bare search.
    assert URL_PRODUCT in result.display
    assert result.snippets == {}
    assert result.fetched_urls == []


def test_fetch_tool_lands_url_text_pair() -> None:
    backend = _backend()
    result = FetchTool().run(_ctx(backend), {"url": URL_PRODUCT})
    assert result.ok is True
    assert result.snippets == {URL_PRODUCT: PAGES[URL_PRODUCT]}
    assert result.fetched_urls == [URL_PRODUCT]
    assert result.display == PAGES[URL_PRODUCT]
    assert result.n_results == 1


def test_fetch_tool_empty_page_is_graceful() -> None:
    backend = _backend()
    result = FetchTool().run(_ctx(backend), {"url": "http://localhost:7770/missing.html"})
    assert result.ok is False
    assert result.snippets == {}
    assert result.fetched_urls == []
    assert result.n_results == 0


# =========================================================================== #
# (c) structured_lookup returns a typed record AND lands a citeable pair.
# =========================================================================== #
def test_structured_lookup_product_lands_typed_record() -> None:
    backend = _backend()
    ctx = _ctx(backend, extras={"structured_lookup_post": _fake_structured_post})
    result = StructuredLookupTool().run(ctx, {"url": URL_PRODUCT, "kind": "product"})

    assert result.ok is True
    # The typed fields are rendered deterministically into the grounding text.
    rendered = result.snippets[URL_PRODUCT]
    assert "name: Alpha Headphones" in rendered
    assert "price: 199.99" in rendered
    assert "rating: 4.5" in rendered
    assert "sku: ALPHA-001" in rendered
    # Lands into the grounding store like a fetched page.
    assert result.fetched_urls == [URL_PRODUCT]
    assert result.display == rendered
    assert result.n_results == 1


def test_structured_lookup_post_lands_typed_record() -> None:
    backend = _backend()
    ctx = _ctx(backend, extras={"structured_lookup_post": _fake_structured_post})
    result = StructuredLookupTool().run(ctx, {"url": URL_FORUM, "kind": "post"})

    assert result.ok is True
    rendered = result.snippets[URL_FORUM]
    assert "title: Alpha headphones long-term review" in rendered
    assert "author: owner_jane" in rendered
    assert "score: 342" in rendered
    # top_comments bodies are folded in so they are grounding-creditable too.
    assert "Fit stays comfortable on long flights." in rendered
    assert result.fetched_urls == [URL_FORUM]


def test_structured_lookup_auto_routes_by_host() -> None:
    backend = _backend()
    seen: list[str] = []

    def transport(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(path)
        return _fake_structured_post(path, payload)

    ctx = _ctx(backend, extras={"structured_lookup_post": transport})
    tool = StructuredLookupTool()
    # :7770 -> product endpoint
    tool.run(ctx, {"url": URL_PRODUCT})
    # :9999 / /f/ path -> post endpoint
    tool.run(ctx, {"url": URL_FORUM})

    assert seen[0].endswith("product_lookup")
    assert seen[1].endswith("post_lookup")


def test_structured_lookup_not_found_is_graceful() -> None:
    backend = _backend()

    def transport(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "url": payload.get("url", ""), "error": "post not found or empty"}

    ctx = _ctx(backend, extras={"structured_lookup_post": transport})
    result = StructuredLookupTool().run(ctx, {"url": URL_FORUM, "kind": "post"})
    assert result.ok is False
    assert result.error == "post not found or empty"
    assert result.snippets == {}
    assert result.fetched_urls == []


def test_structured_lookup_empty_url_is_graceful() -> None:
    ctx = _ctx(_backend(), extras={"structured_lookup_post": _fake_structured_post})
    result = StructuredLookupTool().run(ctx, {"url": ""})
    assert result.ok is False
    assert result.error == "empty_url"


# =========================================================================== #
# (d) parse_action parses TOOL: directive + JSON call_tool form -> CallTool.
# =========================================================================== #
def test_parse_tool_directive_with_json_args() -> None:
    action = parse_action('TOOL: structured_lookup {"url": "http://localhost:7770/p.html", "kind": "product"}')
    assert isinstance(action, CallTool)
    assert action.name == "structured_lookup"
    assert action.args == {"url": "http://localhost:7770/p.html", "kind": "product"}


def test_parse_tool_directive_with_kv_args() -> None:
    action = parse_action("TOOL: structured_lookup url=http://localhost:7770/p.html kind=product")
    assert isinstance(action, CallTool)
    assert action.name == "structured_lookup"
    assert action.args == {"url": "http://localhost:7770/p.html", "kind": "product"}


def test_parse_tool_directive_no_args() -> None:
    action = parse_action("TOOL: search")
    assert isinstance(action, CallTool)
    assert action.name == "search"
    assert action.args == {}


def test_parse_json_call_tool_form() -> None:
    action = parse_action(
        '{"action": "tool", "name": "structured_lookup", "args": {"url": "http://localhost:9999/f/x"}}'
    )
    assert isinstance(action, CallTool)
    assert action.name == "structured_lookup"
    assert action.args == {"url": "http://localhost:9999/f/x"}


def test_json_tool_verb_value_still_resolves_to_search() -> None:
    # Collision guard: a payload whose ``tool`` KEY holds "search" still resolves
    # to a Search action (verb is the first non-empty of action/type/tool/name,
    # and "search" != "tool"), so existing JSON cases are unchanged.
    action = parse_action('{"tool": "search", "query": "alpha headphones"}')
    assert isinstance(action, Search)
    assert action.query == "alpha headphones"


# =========================================================================== #
# (e) ResearchEnv.step dispatches CallTool, honours tools_allowed, counts cap.
# =========================================================================== #
def test_env_dispatches_call_tool_folds_into_grounding() -> None:
    cfg = _task_config(tools_allowed=["search", "fetch"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()

    obs, done, info = env.step(CallTool("fetch", {"url": URL_PRODUCT}))
    assert done is False
    assert info["ok"] is True
    assert info["tool"] == "fetch"
    # Folded into the SAME stores _do_read writes -> reward-creditable.
    assert obs["fetched_urls"] == [URL_PRODUCT]
    assert obs["retrieved_snippets"] == {canonicalize_url(URL_PRODUCT): PAGES[URL_PRODUCT]}
    # The call is recorded under /tool/fetch.
    rollout = env.to_rollout()
    assert any(c["endpoint"] == "/tool/fetch" for c in rollout.tool_calls)


def test_env_call_tool_search_sets_search_results() -> None:
    cfg = _task_config(tools_allowed=["search", "fetch"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()
    obs, done, info = env.step(CallTool("search", {"query": PROMPT}))
    assert info["ok"] is True
    urls = {h["url"] for h in obs["search_results"]}
    assert urls == {URL_PRODUCT, URL_FORUM}
    # /tool/search endpoint still contains "search" -> process search-breadth parity.
    rollout = env.to_rollout()
    assert any("search" in c["endpoint"] for c in rollout.tool_calls)


def test_env_disallowed_tool_is_graceful_not_crash() -> None:
    # structured_lookup is NOT in tools_allowed -> registry.get returns None.
    cfg = _task_config(tools_allowed=["search", "fetch"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()

    obs, done, info = env.step(CallTool("structured_lookup", {"url": URL_PRODUCT}))
    # Graceful: episode continues, no crash, recorded as tool_not_allowed.
    assert done is False
    assert info["ok"] is False
    assert info["error"] == "tool_not_allowed"
    assert obs["retrieved_snippets"] == {}
    assert obs["fetched_urls"] == []
    # The episode is still alive: a follow-up Finalize works.
    _obs2, done2, _info2 = env.step(Finalize("# done"))
    assert done2 is True


def test_env_unknown_tool_is_graceful() -> None:
    cfg = _task_config(tools_allowed=["search", "fetch"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    env.reset()
    _obs, done, info = env.step(CallTool("nonexistent_tool", {}))
    assert done is False
    assert info["ok"] is False
    assert info["error"] == "tool_not_allowed"


def test_env_structured_lookup_via_call_tool_resolves_citation() -> None:
    """A structured_lookup CallTool lands a citeable record; Cite resolves it."""
    cfg = _task_config(tools_allowed=["search", "fetch", "structured_lookup"])
    cfg["run_id"] = "test_run"
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    # Inject the offline transport into the env's tool context via extras.
    # ResearchEnv builds its own ctx; patch the bound _tool_ctx to add the seam.
    base_tool_ctx = env._tool_ctx

    def _patched_ctx() -> ToolContext:
        ctx = base_tool_ctx()
        ctx.extras["structured_lookup_post"] = _fake_structured_post
        return ctx

    env._tool_ctx = _patched_ctx  # type: ignore[method-assign]
    env.reset()
    env._tool_ctx = _patched_ctx  # type: ignore[method-assign]

    env.step(CallTool("structured_lookup", {"url": URL_PRODUCT, "kind": "product"}))
    env.step(Cite(URL_PRODUCT))
    rendered_report = (
        "# Alpha\n\n"
        f"The Alpha Headphones cost 199.99 with rating 4.5 [product]({URL_PRODUCT}).\n\n"
        "This is grounded in the typed product record retrieved via structured lookup.\n"
    )
    env.step(Finalize(rendered_report))
    rollout = env.to_rollout()

    # The PDP URL landed in the grounding store as a citeable (url, text) pair.
    assert canonicalize_url(URL_PRODUCT) in rollout.retrieved_snippets
    assert "name: Alpha Headphones" in rollout.retrieved_snippets[canonicalize_url(URL_PRODUCT)]
    assert URL_PRODUCT in rollout.fetched_urls

    # Reward credit: a Cite of the looked-up URL resolves (R_resolve > 0).
    ev = _evaluator()
    res = ev.evaluate_rollout(rollout)
    grounding = res.reward_terms["grounding"]
    assert grounding["source"] == "proof_of_fetch"
    assert grounding["n_resolved"] >= 1
    assert grounding["R_resolve"] > 0.0
    assert res.composite > 0.0


def test_call_tool_counts_against_max_tool_calls() -> None:
    cfg = _task_config(tools_allowed=["search", "fetch"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=2)
    env.reset()

    # Two successful tool calls consume the budget.
    _o1, d1, i1 = env.step(CallTool("fetch", {"url": URL_PRODUCT}))
    assert d1 is False and i1["ok"] is True
    _o2, d2, i2 = env.step(CallTool("fetch", {"url": URL_FORUM}))
    assert d2 is False and i2["ok"] is True
    assert env.tool_calls_used == 2

    # The third tool call trips the cap and ends the episode.
    _o3, d3, i3 = env.step(CallTool("fetch", {"url": URL_PRODUCT}))
    assert d3 is True
    assert i3["ok"] is False
    assert i3["error"] == "tool_call_cap_exceeded"


# =========================================================================== #
# (f) BYTE-IDENTICAL: no tools_allowed legacy path == registry search/fetch path.
# =========================================================================== #
def test_byte_identical_legacy_vs_registry_tool_path() -> None:
    """Drive the SAME acquisition outcome two ways and assert reward equality.

    Leg 1 (legacy): the scripted MockPolicy emits Search/Open/Read/Cite/Finalize
    on a default task (no tools_allowed) -> the registry is dormant; the env
    takes the existing _do_search/_do_open/_do_read branches verbatim.

    Leg 2 (registry): a scripted policy routes the SAME acquisition through the
    registry's ``search`` and ``fetch`` tools via CallTool, then cites + finalizes
    the SAME report. ``fetch`` folds (url, text) into the SAME slots _do_read
    writes, so the grounding bytes are identical -> identical composite + per_dim.
    """
    # -- Leg 1: legacy opcodes, default task (registry never consulted) --------
    legacy_cfg = _task_config(tools_allowed=None)
    legacy_policy = MockPolicy(
        scripted_actions=[
            Search(PROMPT),
            Open(URL_PRODUCT),
            Read(),
            Open(URL_FORUM),
            Read(),
            Cite(URL_PRODUCT),
            Cite(URL_FORUM),
            Finalize(REPORT_MD),
        ]
    )
    legacy_env = ResearchEnv(legacy_cfg, _backend(), max_tool_calls=40)
    rollout_legacy = run_episode(legacy_cfg, legacy_env, legacy_policy)

    # -- Leg 2: registry search/fetch tools via CallTool -----------------------
    registry_cfg = _task_config(tools_allowed=["search", "fetch"])
    registry_policy = MockPolicy(
        scripted_actions=[
            CallTool("search", {"query": PROMPT}),
            CallTool("fetch", {"url": URL_PRODUCT}),
            CallTool("fetch", {"url": URL_FORUM}),
            Cite(URL_PRODUCT),
            Cite(URL_FORUM),
            Finalize(REPORT_MD),
        ]
    )
    registry_env = ResearchEnv(registry_cfg, _backend(), max_tool_calls=40)
    rollout_registry = run_episode(registry_cfg, registry_env, registry_policy)

    # -- env-level invariant: same grounding bytes in the same slots -----------
    assert rollout_legacy.report_md == rollout_registry.report_md == REPORT_MD
    assert rollout_legacy.fetched_urls == rollout_registry.fetched_urls == [URL_PRODUCT, URL_FORUM]
    assert rollout_legacy.retrieved_snippets == rollout_registry.retrieved_snippets
    assert rollout_legacy.retrieved_snippets == {
        canonicalize_url(URL_PRODUCT): PAGES[URL_PRODUCT],
        canonicalize_url(URL_FORUM): PAGES[URL_FORUM],
    }

    # -- reward invariant: composite + per_dim identical -----------------------
    ev = _evaluator()
    res_legacy = ev.evaluate_rollout(rollout_legacy)
    res_registry = ev.evaluate_rollout(rollout_registry)

    assert res_legacy.composite == res_registry.composite
    assert res_legacy.per_dim == res_registry.per_dim
    assert res_legacy.policy["quote_match"] == res_registry.policy["quote_match"]
    assert res_legacy.composite > 0.0


def test_default_task_trace_is_byte_identical() -> None:
    """A default-path episode (no CallTool) keeps the legacy trace dict shape.

    ``tool_state_deltas`` is added to the trace ONLY when a CallTool recorded a
    state_delta, so the default-path Rollout.trace stays exactly
    {"memory": [...], "cited_urls": [...]}.
    """
    cfg = _task_config(tools_allowed=None)
    policy = MockPolicy(
        scripted_actions=[
            Search(PROMPT),
            Open(URL_PRODUCT),
            Read(),
            Cite(URL_PRODUCT),
            Finalize(REPORT_MD),
        ]
    )
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    rollout = run_episode(cfg, env, policy)
    assert set(rollout.trace.keys()) == {"memory", "cited_urls"}
    assert "tool_state_deltas" not in rollout.trace
