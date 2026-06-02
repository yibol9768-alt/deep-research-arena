"""Offline tests for the ``rag_search`` provider (src/rl/tools_rag.py).

Everything runs on system ``python3`` with NO faiss / sentence-transformers /
numpy / GPU / network: a tiny in-memory mock vector store over ~4 canned
``(url, chunk)`` docs is injected through ``ToolContext.extras["rag_store"]`` (the
DI seam). Deterministic BM25-ish ranking, no embeddings.

Coverage map (DESIGN OFFLINE TEST, items 1-4):
  (1) provide_tools() yields a tool named ``rag_search`` importable without faiss.
  (2) a query returns hits whose top url is the relevant doc, and
      ``snippets[url] == chunk_text`` for surfaced chunks.
  (3) the env folds them so ``retrieved_snippets[canonicalize_url(url)]`` is set
      after a ``CallTool('rag_search')``.
  (4) PARITY: an episode citing a rag-surfaced url earns the SAME grounding
      credit + composite as one that fetched it (test_modality_parity.py style).
"""

from __future__ import annotations

import sys
from typing import Any

from src.eval.evaluator import ArenaEvaluator
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
from src.rl.tools import ToolContext
from src.rl.tools_rag import (
    InMemoryVectorStore,
    RagSearchTool,
    provide_tools,
)
from src.verifiers.citation_format import canonicalize_url


# --------------------------------------------------------------------------- #
# Shared fixtures: one task, two resolved sandbox URLs (mirrors the parity /
# tool-registry tests so the reward path is exercised identically), plus a
# ~4-doc corpus the in-memory store ranks deterministically.
# --------------------------------------------------------------------------- #
TASK_ID = "tools_rag_synth"
PROMPT = "Compare Alpha headphones using product and forum evidence."

URL_PRODUCT = "http://localhost:7770/product-a.html"
URL_FORUM = "http://localhost:9999/f/headphones/alpha-thread"
URL_NOISE_1 = "http://localhost:8090/content/A/Unrelated_topic"
URL_NOISE_2 = "http://localhost:7770/other-product.html"

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

# The rag corpus: the two relevant docs carry the SAME page text the backend
# fetch returns (so a rag hit and a fetch land byte-identical grounding), plus
# two distractor docs the BM25 ranking must push below them.
RAG_DOCS = [
    (URL_PRODUCT, PAGES[URL_PRODUCT]),
    (URL_FORUM, PAGES[URL_FORUM]),
    (URL_NOISE_1, "Completely unrelated encyclopedia article about geology and rocks."),
    (URL_NOISE_2, "A budget travel mug listing with stainless steel and a lid."),
]

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


def _rag_store() -> InMemoryVectorStore:
    return InMemoryVectorStore(docs=list(RAG_DOCS))


def _ctx(backend: MockSandboxBackend, *, store: Any = None) -> ToolContext:
    return ToolContext(
        backend=backend,
        task_config=_task_config(),
        fetch=lambda url: backend.fetch(url),
        canonicalize=canonicalize_url,
        extras={"rag_store": store} if store is not None else {},
    )


def _evaluator() -> ArenaEvaluator:
    ev = ArenaEvaluator(TASK_ID, mode="fast")
    ev._task_config = _task_config()
    ev._rl_strict = True
    return ev


# =========================================================================== #
# (1) provide_tools() yields rag_search and the module needs no faiss.
# =========================================================================== #
def test_provide_tools_yields_rag_search_without_faiss() -> None:
    tools = provide_tools()
    assert [t.name for t in tools] == ["rag_search"]
    tool = tools[0]
    assert tool.description
    assert "query" in tool.args_schema
    # Importing/using the provider never pulls the heavy deps.
    assert "faiss" not in sys.modules
    assert "sentence_transformers" not in sys.modules


def test_rag_args_schema_caps_and_defaults() -> None:
    schema = RagSearchTool().args_schema
    assert schema["query"]["required"] is True
    assert schema["top_k"]["required"] is False
    assert schema["alpha"]["required"] is False


# =========================================================================== #
# (2) A query returns hits; top url is the relevant doc; snippets == chunk.
# =========================================================================== #
def test_rag_search_ranks_relevant_doc_first_and_lands_snippets() -> None:
    backend = _backend()
    ctx = _ctx(backend, store=_rag_store())
    result = RagSearchTool().run(ctx, {"query": "Alpha headphones balanced sound battery", "top_k": 2})

    assert result.ok is True
    assert result.n_results >= 1
    # Top SERP hit is the relevant product doc.
    assert result.hits[0]["url"] == URL_PRODUCT
    # Surfaced chunks land into snippets keyed by the real doc URL == chunk text.
    assert result.snippets[URL_PRODUCT] == PAGES[URL_PRODUCT]
    assert URL_PRODUCT in result.fetched_urls
    # Distractor docs are not surfaced for a tight top_k.
    assert URL_NOISE_1 not in result.snippets
    assert result.display


def test_rag_search_top_k_capped_at_50() -> None:
    backend = _backend()
    ctx = _ctx(backend, store=_rag_store())
    # An absurd top_k is clamped; with only 4 docs we just get <=4 hits, no crash.
    result = RagSearchTool().run(ctx, {"query": "headphones", "top_k": 9999})
    assert result.ok is True
    assert result.n_results <= 4


def test_rag_search_empty_query_is_graceful() -> None:
    result = RagSearchTool().run(_ctx(_backend(), store=_rag_store()), {"query": "   "})
    assert result.ok is False
    assert result.error == "empty_query"


def test_rag_search_no_store_is_graceful() -> None:
    # No rag_store injected and no index dir -> rag_index_unavailable, no crash.
    result = RagSearchTool().run(_ctx(_backend()), {"query": "anything"})
    assert result.ok is False
    assert result.error == "rag_index_unavailable"


def test_rag_search_accepts_callable_store() -> None:
    """The DI seam also accepts a bare (query, top_k, alpha) callable."""
    backend = _backend()

    def fake_store(query: str, top_k: int, alpha: float | None = None):
        return [(URL_FORUM, PAGES[URL_FORUM], 1.0)]

    result = RagSearchTool().run(_ctx(backend, store=fake_store), {"query": "forum"})
    assert result.ok is True
    assert result.snippets[URL_FORUM] == PAGES[URL_FORUM]
    assert result.hits[0]["url"] == URL_FORUM


# =========================================================================== #
# (3) The env folds rag hits into retrieved_snippets after a CallTool.
# =========================================================================== #
def test_env_call_tool_rag_search_folds_into_grounding() -> None:
    cfg = _task_config(tools_allowed=["search", "fetch", "rag_search"])
    env = ResearchEnv(cfg, _backend(), max_tool_calls=40)
    # Inject the in-memory store into the env's tool context via extras, the way
    # the structured_lookup registry test patches _tool_ctx.
    base_tool_ctx = env._tool_ctx

    def _patched_ctx() -> ToolContext:
        ctx = base_tool_ctx()
        ctx.extras["rag_store"] = _rag_store()
        return ctx

    env._tool_ctx = _patched_ctx  # type: ignore[method-assign]
    env.reset()
    env._tool_ctx = _patched_ctx  # type: ignore[method-assign]

    obs, done, info = env.step(
        CallTool("rag_search", {"query": "Alpha headphones balanced sound battery", "top_k": 2})
    )
    assert done is False
    assert info["ok"] is True
    assert info["tool"] == "rag_search"
    # Folded into the SAME stores _do_read writes -> reward-creditable.
    assert canonicalize_url(URL_PRODUCT) in obs["retrieved_snippets"]
    assert obs["retrieved_snippets"][canonicalize_url(URL_PRODUCT)] == PAGES[URL_PRODUCT]
    assert URL_PRODUCT in obs["fetched_urls"]
    # The ranked hits also populate search_results (SERP breadth).
    serp_urls = {h["url"] for h in obs["search_results"]}
    assert URL_PRODUCT in serp_urls
    # Recorded under /tool/rag_search.
    rollout = env.to_rollout()
    assert any(c["endpoint"] == "/tool/rag_search" for c in rollout.tool_calls)


# =========================================================================== #
# (4) PARITY: citing a rag-surfaced url == citing a fetched url (same reward).
# =========================================================================== #
def test_rag_surfaced_citation_earns_same_credit_as_a_fetch() -> None:
    """A rag_search episode and a fetch episode land identical grounding bytes.

    Leg A (fetch): Search/Open/Read both pages, cite both, finalize.
    Leg B (rag):   one CallTool('rag_search') surfaces BOTH pages with the same
                   page text, cite both, finalize the SAME report.
    The env folds rag (url, chunk) into the SAME retrieved_snippets slots a fetch
    writes, so composite + per_dim must be byte-identical (modality-agnostic).
    """
    # -- Leg A: fetch path (legacy opcodes, no tools_allowed) --
    fetch_cfg = _task_config(tools_allowed=None)
    fetch_policy = MockPolicy(
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
    fetch_env = ResearchEnv(fetch_cfg, _backend(), max_tool_calls=40)
    rollout_fetch = run_episode(fetch_cfg, fetch_env, fetch_policy)

    # -- Leg B: rag path. The store returns both docs (top_k=4) with the exact
    #    page text, so the folded grounding is identical to Leg A's fetch. --
    rag_cfg = _task_config(tools_allowed=["search", "fetch", "rag_search"])
    rag_env = ResearchEnv(rag_cfg, _backend(), max_tool_calls=40)
    base_tool_ctx = rag_env._tool_ctx

    def _patched_ctx() -> ToolContext:
        ctx = base_tool_ctx()
        ctx.extras["rag_store"] = _rag_store()
        return ctx

    rag_env._tool_ctx = _patched_ctx  # type: ignore[method-assign]
    # run_episode calls reset() then steps; re-patch after reset to be safe.
    rag_policy = MockPolicy(
        scripted_actions=[
            CallTool("rag_search", {"query": "Alpha headphones comfort battery durability forum", "top_k": 4}),
            Cite(URL_PRODUCT),
            Cite(URL_FORUM),
            Finalize(REPORT_MD),
        ]
    )
    rag_env.reset()
    rag_env._tool_ctx = _patched_ctx  # type: ignore[method-assign]
    rollout_rag = run_episode(rag_cfg, rag_env, rag_policy)

    # -- env-level invariant: same grounding bytes in the same slots --
    assert rollout_fetch.report_md == rollout_rag.report_md == REPORT_MD
    assert rollout_fetch.retrieved_snippets == rollout_rag.retrieved_snippets
    assert rollout_fetch.retrieved_snippets == {
        canonicalize_url(URL_PRODUCT): PAGES[URL_PRODUCT],
        canonicalize_url(URL_FORUM): PAGES[URL_FORUM],
    }

    # -- reward invariant: composite + per_dim identical --
    ev = _evaluator()
    res_fetch = ev.evaluate_rollout(rollout_fetch)
    res_rag = ev.evaluate_rollout(rollout_rag)

    assert res_fetch.composite == res_rag.composite
    assert res_fetch.per_dim == res_rag.per_dim
    # The grounded dims are genuinely exercised, not all-neutral.
    grounding = res_rag.reward_terms["grounding"]
    assert grounding["source"] == "proof_of_fetch"
    assert grounding["n_resolved"] >= 1
    assert grounding["R_resolve"] > 0.0
    assert res_rag.composite > 0.0
