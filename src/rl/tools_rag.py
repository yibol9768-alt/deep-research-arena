"""``rag_search`` provider: local dense+hybrid retrieval over the fixed corpus.

This is P1 acquisition modality 1 from ``docs/ACQUISITION_ROADMAP.md`` section 3.
It is wired into the registry purely through the PROVIDER-DISCOVERY CONTRACT:
this module exposes a single module-level :func:`provide_tools` factory that the
``src.rl.tools._discover_provider_tools`` loop calls at registry-build time.
``src/rl/tools.py`` is never edited by this module's owner.

What ``rag_search`` does
------------------------
Dense + hybrid (BM25 + embedding) ranked retrieval over the FIXED corpus (Kiwix
ZIM text + Magento catalog text + Postmill text). The doc id IS the real sandbox
page URL (``http://localhost:8090/.../A/Slug`` Wikipedia, ``:7770`` PDP, ``:9999``
post), so grounding stays honest and modality-agnostic.

Modality-agnostic reward (the HARD INVARIANT)
---------------------------------------------
For the top-``k`` chunks the tool lands BOTH a SERP view AND grounding pairs, so
it credits like ``search`` + ``fetch`` combined for the pages it surfaces:

* ``hits``         -> ``[{url, title, snippet}]`` (folds into ``search_results``).
* ``snippets``     -> ``{doc_url: chunk_text}`` so a ``Cite(doc_url)`` resolves
  ``r_resolve`` / ``f1_claim`` IDENTICAL to a ``fetch`` of that page (the env
  folds it into ``retrieved_snippets[canonicalize_url(doc_url)]``).
* ``fetched_urls`` -> ``[doc_url, ...]``; ``display`` -> rendered ranked list.

Vector-store seam (offline-safe, no heavy deps at import)
---------------------------------------------------------
A small :class:`VectorStore` Protocol ``search(query, top_k, alpha) ->
list[(url, chunk_text, score)]``. :class:`RagSearchTool` resolves a store in
this order:

1. ``ctx.extras["rag_store"]`` -- an injected store object OR a plain callable
   with the same ``(query, top_k, alpha)`` signature (tests + DI).
2. A process-global store built (and cached) from a persisted index dir at
   ``ctx.extras["rag_index_dir"]`` / task ``acquisition.rag_index_dir``.

The indexer entrypoint :func:`build_rag_index` lazily imports ``faiss`` +
``sentence-transformers`` (CPU embeddings are fine; GPU optional), chunks +
embeds the corpus and writes a FAISS index + a BM25 sidecar + a url->chunk map.
It is deferred / guarded and NEVER called in tests.

No heavy/top-level imports: only ``dataclasses`` / ``typing`` / ``re`` here, plus
the cheap ``ToolResult`` value object. ``faiss`` / ``sentence-transformers`` /
``numpy`` are imported LAZILY inside the indexer and the persisted-store loader,
so ``import src.rl.tools_rag`` and ``provide_tools()`` succeed on a plain
``python3`` with none of them installed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.rl.tools import ToolContext, ToolResult

# A retrieval hit, as ranked tuples come out of a VectorStore.
RagHit = tuple[str, str, float]

# Hard cap on returned chunks, mirrored from the DESIGN security guard.
_MAX_TOP_K = 50
_DEFAULT_TOP_K = 8


# ---------------------------------------------------------------------------
# Vector-store seam
# ---------------------------------------------------------------------------
@runtime_checkable
class VectorStore(Protocol):
    """Ranked retrieval seam over the fixed corpus.

    ``alpha`` blends BM25 (lexical) and embedding (dense) scores: ``0.0`` is
    BM25-only, ``1.0`` is dense-only, anything in between is hybrid. A store
    that supports only one of the two may ignore ``alpha``.
    """

    def search(self, query: str, top_k: int, alpha: float | None = None) -> list[RagHit]: ...


# ---------------------------------------------------------------------------
# Offline reference store: pure-Python BM25-ish + optional dense fold-in.
# Used by the persisted-index loader fallback AND directly injectable in tests.
# No numpy / faiss / sentence-transformers required.
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


@dataclass
class InMemoryVectorStore:
    """A dependency-free hybrid store over ``(url, chunk_text)`` docs.

    Lexical scoring is a compact BM25 (k1=1.5, b=0.75). An optional per-doc
    dense embedding vector (``embeddings``) enables a cosine dense leg blended by
    ``alpha``; with no embeddings the store is BM25-only and ``alpha`` is ignored.
    This is the offline reference VectorStore: the same class the persisted-index
    loader rehydrates into (with embeddings) and the one tests inject (without).
    """

    docs: list[tuple[str, str]] = field(default_factory=list)
    embeddings: list[list[float]] | None = None
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self) -> None:
        self._doc_tokens: list[list[str]] = [_tokenize(text) for _url, text in self.docs]
        self._doc_len: list[int] = [len(toks) for toks in self._doc_tokens]
        n = len(self.docs)
        self._avg_len: float = (sum(self._doc_len) / n) if n else 0.0
        # Document frequency per term for the IDF.
        df: dict[str, int] = {}
        for toks in self._doc_tokens:
            for term in set(toks):
                df[term] = df.get(term, 0) + 1
        self._df = df
        self._n = n

    # -- lexical (BM25) --
    def _bm25_scores(self, query: str) -> list[float]:
        q_terms = _tokenize(query)
        scores = [0.0] * self._n
        if not q_terms or not self._n:
            return scores
        for term in set(q_terms):
            df = self._df.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))
            for i, toks in enumerate(self._doc_tokens):
                tf = toks.count(term)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1.0 - self.b + self.b * (self._doc_len[i] / (self._avg_len or 1.0)))
                scores[i] += idf * (tf * (self.k1 + 1.0)) / (denom or 1.0)
        return scores

    # -- dense (cosine over provided embeddings) --
    def _dense_scores(self, query: str) -> list[float] | None:
        if not self.embeddings:
            return None
        # The query embedding is computed lazily; in the offline reference store
        # there is no embedder, so dense scoring is only available when a caller
        # has supplied a precomputed query vector via embeddings semantics. We
        # therefore skip dense unless an embedder is wired (persisted loader sets
        # ``_embed_query``); default offline store stays BM25-only.
        embed_query = getattr(self, "_embed_query", None)
        if not callable(embed_query):
            return None
        try:
            q_vec = embed_query(query)
        except Exception:
            return None
        out: list[float] = []
        for vec in self.embeddings:
            out.append(_cosine(q_vec, vec))
        return out

    def search(self, query: str, top_k: int, alpha: float | None = None) -> list[RagHit]:
        if not self._n:
            return []
        lex = self._bm25_scores(query)
        dense = self._dense_scores(query)
        blended = _blend(lex, dense, alpha)
        order = sorted(range(self._n), key=lambda i: (blended[i], -i), reverse=True)
        hits: list[RagHit] = []
        for i in order[: max(0, int(top_k))]:
            if blended[i] <= 0.0 and dense is None:
                # BM25-only and zero lexical overlap -> not a real hit.
                continue
            url, chunk = self.docs[i]
            hits.append((url, chunk, float(blended[i])))
        return hits


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    nb = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return dot / (na * nb)


def _normalize(scores: list[float]) -> list[float]:
    """Min-max normalize a score vector into [0, 1] for a fair hybrid blend."""
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if hi <= lo:
        return [0.0 for _ in scores]
    span = hi - lo
    return [(s - lo) / span for s in scores]


def _blend(lex: list[float], dense: list[float] | None, alpha: float | None) -> list[float]:
    """Hybrid blend: ``alpha`` weights dense, ``1 - alpha`` weights lexical."""
    if dense is None:
        return list(lex)
    a = 0.5 if alpha is None else max(0.0, min(1.0, float(alpha)))
    if a <= 0.0:
        return list(lex)
    if a >= 1.0:
        return list(dense)
    nlex = _normalize(lex)
    nden = _normalize(dense)
    return [(1.0 - a) * nlex[i] + a * nden[i] for i in range(len(nlex))]


# ---------------------------------------------------------------------------
# Persisted-index loader (process-global cache). Heavy deps imported LAZILY.
# ---------------------------------------------------------------------------
_INDEX_CACHE: dict[str, VectorStore] = {}


def _load_persisted_store(index_dir: str) -> VectorStore:
    """Rehydrate a VectorStore from a persisted index dir built by build_rag_index.

    Lazily imports ``faiss`` + ``sentence-transformers`` + ``numpy``. On any
    failure (missing dep / missing files) raises so the tool reports
    ``rag_index_unavailable`` -- it NEVER crashes the registry or the env.

    The persisted layout written by :func:`build_rag_index`:
      * ``chunks.json``  -> [{"url": str, "text": str}, ...] (url->chunk map)
      * ``dense.faiss``  -> FAISS index over the chunk embeddings (optional)
      * ``meta.json``    -> {"model": embed-model-name, "dim": int, "dense": bool}
    """
    import json
    import os

    cached = _INDEX_CACHE.get(index_dir)
    if cached is not None:
        return cached

    chunks_path = os.path.join(index_dir, "chunks.json")
    with open(chunks_path, encoding="utf-8") as fh:
        rows = json.load(fh)
    docs = [(str(r["url"]), str(r.get("text") or "")) for r in rows]

    # Dense leg is best-effort: if the index is explicitly sparse, or if faiss /
    # the model are unavailable, we degrade to the BM25-only reference store
    # rather than failing the whole tool.
    embeddings: list[list[float]] | None = None
    embed_query = None
    meta_path = os.path.join(index_dir, "meta.json")
    meta: dict[str, Any] = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)

    if meta.get("dense") is False or meta.get("no_dense") is True:
        store = InMemoryVectorStore(docs=docs)
        _INDEX_CACHE[index_dir] = store
        return store

    if meta:
        try:
            import numpy as np  # noqa: F401  (lazy, GPU not required)
            from sentence_transformers import SentenceTransformer  # lazy

            model_name = str(meta.get("model") or "sentence-transformers/all-MiniLM-L6-v2")
            model = SentenceTransformer(model_name, device="cpu")
            embeddings = [
                list(map(float, v))
                for v in model.encode([t for _u, t in docs], convert_to_numpy=True)
            ]

            def embed_query(q: str) -> list[float]:
                return list(map(float, model.encode([q], convert_to_numpy=True)[0]))
        except Exception:
            embeddings = None
            embed_query = None

    store = InMemoryVectorStore(docs=docs, embeddings=embeddings)
    if embed_query is not None:
        store._embed_query = embed_query  # type: ignore[attr-defined]
    _INDEX_CACHE[index_dir] = store
    return store


# ---------------------------------------------------------------------------
# Indexer entrypoint (deferred / guarded; NEVER called in tests).
# ---------------------------------------------------------------------------
def build_rag_index(corpus_iter: Any, out_dir: str, *, model_name: str | None = None,
                    chunk_words: int = 220, chunk_overlap: int = 40) -> str:
    """Build a persisted dense+BM25 index from the fixed corpus.

    ``corpus_iter`` yields ``(url, text)`` pairs over the Kiwix / Magento /
    Postmill corpus content (the indexer ONLY ingests :7770 / :9999 / :8090
    pages, so returned urls are honest sandbox URLs). Each document is chunked
    by words, embedded (CPU is fine), and written to ``out_dir`` as:

      * ``chunks.json`` -> the url->chunk map (also the BM25 sidecar source).
      * ``dense.faiss`` -> a FAISS index over the chunk embeddings.
      * ``meta.json``   -> {"model", "dim", "n_chunks"}.

    Heavy deps (``faiss`` / ``sentence-transformers`` / ``numpy``) are imported
    LAZILY here so the module imports without them. This entrypoint is run by an
    offline indexing job on the training box; offline tests use an injected
    in-memory store instead and never call this.
    """
    import json
    import os

    import numpy as np  # lazy
    import faiss  # lazy
    from sentence_transformers import SentenceTransformer  # lazy

    os.makedirs(out_dir, exist_ok=True)
    model_name = model_name or "sentence-transformers/all-MiniLM-L6-v2"
    model = SentenceTransformer(model_name, device="cpu")

    rows: list[dict[str, str]] = []
    for url, text in corpus_iter:
        url = str(url or "").strip()
        if not url:
            continue
        for chunk in _chunk_text(str(text or ""), chunk_words, chunk_overlap):
            if chunk.strip():
                rows.append({"url": url, "text": chunk})

    texts = [r["text"] for r in rows]
    vecs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False) if texts else np.zeros((0, 1))
    vecs = np.asarray(vecs, dtype="float32")
    dim = int(vecs.shape[1]) if vecs.size else 1

    index = faiss.IndexFlatIP(dim)
    if vecs.size:
        faiss.normalize_L2(vecs)
        index.add(vecs)

    with open(os.path.join(out_dir, "chunks.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    faiss.write_index(index, os.path.join(out_dir, "dense.faiss"))
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "model": model_name,
                "dim": dim,
                "n_chunks": len(rows),
                "chunk_words": chunk_words,
                "chunk_overlap": chunk_overlap,
                "dense": True,
            },
            fh,
        )
    return out_dir


def build_sparse_rag_index(
    corpus_iter: Any,
    out_dir: str,
    *,
    chunk_words: int = 220,
    chunk_overlap: int = 40,
) -> str:
    """Build a BM25-only persisted index with no heavy dependencies."""
    import json
    import os

    os.makedirs(out_dir, exist_ok=True)
    rows: list[dict[str, str]] = []
    for url, text in corpus_iter:
        url = str(url or "").strip()
        if not url:
            continue
        for chunk in _chunk_text(str(text or ""), chunk_words, chunk_overlap):
            if chunk.strip():
                rows.append({"url": url, "text": chunk})

    dense_path = os.path.join(out_dir, "dense.faiss")
    if os.path.exists(dense_path):
        os.remove(dense_path)
    with open(os.path.join(out_dir, "chunks.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "model": None,
                "dim": 0,
                "n_chunks": len(rows),
                "chunk_words": chunk_words,
                "chunk_overlap": chunk_overlap,
                "dense": False,
            },
            fh,
        )
    return out_dir


def _chunk_text(text: str, chunk_words: int, overlap: int) -> list[str]:
    """Word-window chunking with overlap (no sentence model needed)."""
    words = text.split()
    if not words:
        return []
    chunk_words = max(1, int(chunk_words))
    overlap = max(0, min(int(overlap), chunk_words - 1))
    step = chunk_words - overlap
    chunks: list[str] = []
    for start in range(0, len(words), step):
        window = words[start : start + chunk_words]
        if window:
            chunks.append(" ".join(window))
        if start + chunk_words >= len(words):
            break
    return chunks


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------
def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _hit_title(url: str) -> str:
    """A cheap human title from the doc URL's last path segment."""
    tail = url.rstrip("/").rsplit("/", 1)[-1] or url
    return tail.replace("_", " ").replace("-", " ").strip() or url


def _rag_display(hits: list[RagHit], limit: int = 8) -> str:
    lines: list[str] = []
    for idx, (url, chunk, score) in enumerate(hits[:limit], start=1):
        snippet = " ".join(str(chunk or "").split())[:160]
        lines.append(f"{idx}. [{score:.3f}] {url}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


class RagSearchTool:
    """``rag_search``: local dense+hybrid retrieval; lands (url, chunk) hits.

    Returns ranked corpus hits AND lands each surfaced chunk into the grounding
    store keyed by its real sandbox doc URL, so a later ``Cite(doc_url)`` resolves
    exactly like a ``fetch`` of that page (the modality-agnostic invariant).

    Read-only over a prebuilt local index: no network, no exec. ``top_k`` is
    capped at 50. If no store can be resolved (e.g. ``faiss`` / the index dir is
    unavailable) it returns ``ToolResult(ok=False, error="rag_index_unavailable")``
    and NEVER crashes.
    """

    name = "rag_search"
    description = (
        "Local dense+hybrid (BM25 + embedding) retrieval over the fixed sandbox "
        "corpus: query in, ranked (url, chunk) hits out, landed into grounding."
    )
    args_schema: dict = {
        "query": {"type": "string", "required": True},
        "top_k": {"type": "int", "required": False, "default": _DEFAULT_TOP_K},
        # 0 = BM25-only, 1 = dense-only, anything between = hybrid.
        "alpha": {"type": "float", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or args.get("q") or "").strip()
        if not query:
            return ToolResult(ok=False, error="empty_query")

        top_k = _coerce_int(args.get("top_k"), _DEFAULT_TOP_K)
        top_k = max(1, min(_MAX_TOP_K, top_k))
        alpha = _coerce_float(args.get("alpha"))

        try:
            store = self._resolve_store(ctx)
        except Exception:
            return ToolResult(ok=False, error="rag_index_unavailable")
        if store is None:
            return ToolResult(ok=False, error="rag_index_unavailable")

        try:
            raw = store.search(query, top_k, alpha) if _store_takes_alpha(store) else store.search(query, top_k)
        except Exception as exc:  # any store failure is graceful, never a crash
            return ToolResult(ok=False, error=f"rag_search_failed: {type(exc).__name__}")

        hits_t = _normalize_rag_hits(raw)[:top_k]
        if not hits_t:
            return ToolResult(ok=True, n_results=0, display="(no hits)")

        # Land BOTH a SERP view AND grounding pairs. Last-write-wins keeps one
        # chunk per url in snippets; the SERP keeps every ranked hit.
        snippets: dict[str, str] = {}
        fetched_urls: list[str] = []
        serp: list[dict[str, Any]] = []
        for url, chunk, score in hits_t:
            url = str(url).strip()
            chunk = str(chunk or "")
            if not url or not chunk:
                continue
            snippets[url] = chunk
            if url not in fetched_urls:
                fetched_urls.append(url)
            serp.append(
                {
                    "url": url,
                    "title": _hit_title(url),
                    "snippet": " ".join(chunk.split())[:200],
                    "score": float(score),
                }
            )

        if not snippets:
            return ToolResult(ok=True, n_results=0, display="(no hits)")

        return ToolResult(
            snippets=snippets,
            fetched_urls=fetched_urls,
            hits=serp,
            n_results=len(serp),
            display=_rag_display(hits_t),
            ok=True,
        )

    # -- store resolution: injected DI first, then persisted index dir --
    def _resolve_store(self, ctx: ToolContext) -> VectorStore | None:
        extras = ctx.extras or {}
        injected = extras.get("rag_store")
        if injected is not None:
            return _adapt_store(injected)

        index_dir = (
            extras.get("rag_index_dir")
            or (ctx.task_config.get("acquisition") or {}).get("rag_index_dir")
            or ctx.task_config.get("rag_index_dir")
        )
        if index_dir:
            return _load_persisted_store(str(index_dir))
        return None


# ---------------------------------------------------------------------------
# Store adapters / hit normalization
# ---------------------------------------------------------------------------
def _store_takes_alpha(store: Any) -> bool:
    """True if ``store.search`` accepts an ``alpha`` argument."""
    import inspect

    fn = getattr(store, "search", None)
    if not callable(fn):
        return False
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return True
    return "alpha" in params or any(
        p.kind == inspect.Parameter.VAR_POSITIONAL or p.kind == inspect.Parameter.VAR_KEYWORD
        for p in params.values()
    )


class _CallableStore:
    """Wrap a plain ``(query, top_k, alpha) -> hits`` callable as a VectorStore."""

    def __init__(self, fn: Any) -> None:
        self._fn = fn

    def search(self, query: str, top_k: int, alpha: float | None = None) -> list[RagHit]:
        import inspect

        try:
            params = inspect.signature(self._fn).parameters
            takes_alpha = "alpha" in params or any(
                p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                for p in params.values()
            )
        except (TypeError, ValueError):
            takes_alpha = True
        return self._fn(query, top_k, alpha) if takes_alpha else self._fn(query, top_k)


def _adapt_store(obj: Any) -> VectorStore:
    """Accept either a VectorStore-like object or a bare callable."""
    if hasattr(obj, "search") and callable(getattr(obj, "search")):
        return obj  # type: ignore[return-value]
    if callable(obj):
        return _CallableStore(obj)
    raise TypeError("rag_store must be a VectorStore or a (query, top_k, alpha) callable")


def _normalize_rag_hits(raw: Any) -> list[RagHit]:
    """Coerce assorted store outputs into ``[(url, chunk_text, score)]``."""
    out: list[RagHit] = []
    for item in raw or []:
        if isinstance(item, dict):
            url = str(item.get("url") or item.get("id") or "").strip()
            chunk = str(item.get("text") or item.get("chunk") or item.get("snippet") or "")
            score = float(item.get("score") or 0.0)
        elif isinstance(item, (tuple, list)):
            url = str(item[0]).strip() if len(item) > 0 else ""
            chunk = str(item[1]) if len(item) > 1 else ""
            score = float(item[2]) if len(item) > 2 else 0.0
        else:
            continue
        if url:
            out.append((url, chunk, score))
    return out


# ---------------------------------------------------------------------------
# Provider-discovery contract
# ---------------------------------------------------------------------------
def provide_tools() -> list[Any]:
    """Return this module's tools for the registry discovery loop.

    Called with NO args at registry-build time; cheap (no I/O, no heavy import).
    Returns exactly one tool: ``rag_search``.
    """
    return [RagSearchTool()]


__all__ = [
    "RagSearchTool",
    "VectorStore",
    "InMemoryVectorStore",
    "build_rag_index",
    "build_sparse_rag_index",
    "provide_tools",
]
