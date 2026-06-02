# Acquisition Roadmap

Workstream C, Deep Research Arena. Phased plan to add every identified
acquisition modality to the framework, GPU unconstrained (real computer-use,
vision, embeddings, and a code-sandbox are all in scope).

- Generated: 2026-06-02
- Companion docs: `docs/ACQUISITION_MODALITIES.md` (the three channels we ship
  today and the modality-parity proof), `docs/AGENTRL_TASK_SPEC.md` (the RL
  reward and budget), `docs/STRICT_SANDBOX_CONTRACT.md` (the allowlist).
- Code anchors: `src/rl/env.py` (action space + `SandboxBackend` +
  `HttpSandboxBackend`), `src/rl/backends.py` (`BrowserSandboxBackend`,
  `ComputerUseBackend`, `make_backend`), `integrations/search_shim/app.py`
  (the wire-protocol shim, structured lookups, strict allowlist),
  `integrations/wiki_overlay/app.py` (proof-of-fetch overlay),
  `src/eval/evaluator.py` (the modality-agnostic grounding reward).

The governing invariant, unchanged by everything below: the grounding reward in
`src/eval/evaluator.py::_compute_ground_signals` reads only
`rollout.retrieved_snippets` (`dict[url] -> page_text`) and the cited URLs, and
`s_ground = 0.6 * f1_claim + 0.4 * r_resolve`. It never inspects how bytes were
acquired. Any new channel earns identical reward as long as it lands the same
`(url, page_text)` pairs. New modalities that mutate state (write-actions) or
compute derived values need a SEPARATE verifier, not a change to grounding.

## 1. Unified taxonomy

Sandbox relevance: `core` = usable against our three hosts today and central to
the arena; `useful` = genuinely buildable against our hosts with added work;
`general-only` = a real frontier capability but needs seeded content or external
services we do not host (called out honestly in section 4). Status is relative
to this repo. Effort is S/M/L/XL. GPU need is the hardware a real implementation
wants (most are `none`; only vision/embeddings/ASR want a GPU).

| # | Modality | What it does | Exemplars (2026) | Sandbox relevance | Maps to in our code | Status | Effort | GPU |
| - | -------- | ------------ | ---------------- | ----------------- | ------------------- | ------ | ------ | --- |
| 1 | Web-search SERP retrieval | free-text query in, ranked `(title,url,snippet)` out; "search" is a swappable provider slot | Anthropic `web_search`; OpenAI deep research web search; STORM 10 retrievers; smolagents `WebSearchTool` | core | `SandboxBackend.search`; `HttpSandboxBackend.search` over the shim (7 vendor wire protocols) | have | S | none |
| 2 | Page extract / reader | fetch a known URL, strip boilerplate to LLM-ready text | Jina Reader; Firecrawl `/scrape`; smolagents `VisitWebpageTool`; Anthropic `web_fetch` | core | `SandboxBackend.fetch` -> shim `/extract` (`requests`+BS4, no JS) | have | S | none |
| 3 | Real-browser DOM automation | drive headless Chromium: goto, read `innerText`, multi-page traversal; click-through actions live in the computer-use page loop | Perplexity Comet; Magentic-One WebSurfer; WebArena a11y tree; WebWalkerQA | core | `BrowserSandboxBackend` (`src/rl/backends.py`), `make_backend('browser')`, `browser-dr` main runner | have | S | none |
| 4 | Computer-use / GUI vision | screenshot (+a11y/SoM) in, GUI ops out (click/scroll/type/keypress/drag/move/wait/screenshot) | OpenAI computer-use action set; Claude computer use; OSWorld; VisualWebArena | useful | `ComputerUsePolicy` Protocol + `ComputerUseBackend` seam + `_TextProxyPolicy` stub | partial | XL | VLM |
| 5 | Structured / typed connectors | schema-aware lookups returning typed records (product, post) not HTML | Firecrawl schema JSON + Agent; OpenAI DR MCP search+fetch; CAMEL structured toolkit | core | shim `/product_lookup` + `/post_lookup` exist; NOT routed into env action space | partial | S | none |
| 6 | Embeddings / local dense+hybrid RAG | chunk+embed the fixed corpus, retrieve by similarity (hybrid BM25+dense, rerank), `url` = doc id | BrowseComp-Plus fixed ~100K-doc corpus; STORM `VectorRM` (Qdrant offline); Qwen3-Embedding | core | missing (only `ds_proxy` passthrough; `MockSandboxBackend.index` is a dict) | missing | L | embeddings (CPU ok) |
| 7 | Sandboxed code execution / terminal | agent writes+runs Python/Bash over fetched data, file I/O, `curl`/`grep` the local hosts | OpenAI DR `code_interpreter`; Anthropic `code_execution_20260120`; E2B microVM; smolagents `CodeAgent` | useful | missing (dead `third_party/.../python_repl.py`; no exec endpoint) | missing | L | code-sandbox (CPU) |
| 7b | Read-only SQL / text-to-SQL | emit SQL against backing stores, get rows, cite the page URLs | BIRD-SQL agentic RAG; Snowflake Cortex Analyst; tau-bench grades DB state | useful | missing (no SQL endpoint; Magento=MySQL, Postmill=PostgreSQL; `sqlalchemy`+`psycopg2` already in reqs) | missing | M | none |
| 8 | Web crawl / site map | follow links from a seed with depth/limit; `/map` discovers a site's URL set | Firecrawl `/crawl` + `/v2/map`; DeerFlow crawler; gpt-researcher 20+ sources/run | useful | missing | missing | M | none |
| 9 | DB-mutating tool calls + user-sim | structured write-actions (add-to-cart/order) graded by final-DB-state diff, plus LLM user simulator | tau-bench / tau2-bench user-sim + DB-state pass^k; WebArena execution eval | useful | missing (Magento has cart/order DB + `admin/admin1234`) | missing | L | LLM user-sim |
| 10 | MCP server wrapper | expose our tools as a standard MCP server (Streamable HTTP, Tools/Resources/Prompts) for external agents | OpenAI DR connects to any MCP; gpt-researcher `gptr-mcp`; LangChain ODR `mcp_config`; CAMEL toolkit->MCP | useful | missing (we have the HTTP shim + `shim_intercept` instead) | missing | M | none |
| 11 | On-page image / content vision | VLM reads visual content embedded in fetched pages (product photos, diagrams) -> text into snippets | OpenAI o3/o4-mini visual reasoning; Gemini image understanding; VisualWebArena input images | useful | missing (sites DO contain real images) | missing | L | VLM |
| 12 | File / document ingestion | parse non-HTML artifacts (PDF/DOCX/XLSX/PPTX/CSV/OCR) to citeable text | OpenAI DR file upload + `file_search`; Docling Granite-Docling-258M (Jan 2026); GAIA; SpreadsheetBench | general-only | effectively missing (`pytesseract`/`pdf2image`/`pillow`/`markdownify` in reqs but unused; sandbox serves only HTML) | missing | L | VLM for OCR/charts; none for native PDF text |
| 13 | Audio / video ingestion | ASR transcription + keyframe+transcript alignment to citeable text | Whisper + ~1fps frames; MMCTAgent over video; GAIA audio/video | general-only | missing, no source exists | missing | XL | VLM + ASR |
| 14 | Scholarly / academic APIs | structured paper records + citation graph (arXiv, Semantic Scholar, PubMed, OpenAlex) | gpt-researcher arxiv/semantic_scholar; DeerFlow Arxiv; SPAR | general-only | OUT OF SCOPE (no live internet, no paper index) | n/a | L | none |
| 15 | Domain-restricted allowlist gating | constrain retrieval to a trusted allowlist instead of the open web | OpenAI DR "restrict to trusted sites"; Anthropic `web_search` allowed/blocked domains | core | the sandbox IS a permanent allowlist; `SHIM_MODE=strict` 403s off-list + logs `logs/shim_blocks.jsonl` | have | S | none |
| 16 | Provenance / proof-of-fetch | control layer that makes the fetched page the ground truth (adversarial fact rewrite + retrieval log) | our own design; aligns with BrowseComp-Plus controlled-corpus integrity | core | `integrations/wiki_overlay/app.py` (:8091), `contamination_verifier`, `logs/retrieval/<run_id>.jsonl` | have | S | none |

Sources (verified 2026-06-02): Anthropic web search and fetch
(https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool);
OpenAI deep research data sources (web search, MCP, file_search) and
code_interpreter
(https://developers.openai.com/api/docs/guides/deep-research ;
https://developers.openai.com/api/docs/guides/tools-code-interpreter);
OpenAI computer-use action set
(https://developers.openai.com/api/docs/guides/tools-computer-use);
Anthropic `code_execution_20260120` adds REPL state persistence + programmatic
tool calls, `code_execution_20250825` adds Bash+files
(https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool);
smolagents `CodeAgent`/`ToolCallingAgent` toolbox-as-dict
(https://github.com/huggingface/smolagents ;
https://smolagents.org/docs/tools-of-smolagents-in-depth-guide/);
LangChain tools as typed callables + `ToolNode`
(https://docs.langchain.com/oss/python/langchain/tools);
BrowseComp-Plus fixed ~100K-doc corpus + hard negatives, ACL 2026 Main
(https://arxiv.org/abs/2508.06600 ; https://github.com/texttron/BrowseComp-Plus);
Firecrawl `/v2/map` and `/crawl`
(https://docs.firecrawl.dev/features/map ;
https://www.firecrawl.dev/blog/mastering-the-crawl-endpoint-in-firecrawl);
tau2-bench DB-state diff + pass^k + constrained user simulator
(https://arxiv.org/pdf/2506.07982 ; https://github.com/sierra-research/tau2-bench);
MCP Streamable HTTP transport (Nov 2025 spec) + Tools/Resources/Prompts
(https://modelcontextprotocol.io/specification/2025-03-26/basic/transports ;
https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/);
OSWorld observation stack screenshot/a11y_tree/SoM
(https://os-world.github.io/ ; https://arxiv.org/pdf/2404.07972);
Docling Granite-Docling-258M single-VLM doc parsing (Jan 2026)
(https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion ;
https://github.com/docling-project/docling);
VisualWebArena Set-of-Marks
(https://github.com/web-arena-x/visualwebarena);
SpreadsheetBench (https://arxiv.org/abs/2406.14991);
GAIA heterogeneous attachments
(https://huggingface.co/datasets/gaia-benchmark/GAIA).

## 2. The architectural change: a typed tool registry over the backend protocol

### 2.1 Why `SandboxBackend(search, fetch)` is not enough, and what is

The current `SandboxBackend` protocol has exactly two verbs, `search(query)`
and `fetch(url)`, and the env action space is the fixed seven-action set
`Search | Open | Read | WriteMemory | ReadMemory | Cite | Finalize`
(`src/rl/env.py`). This is exactly right for modalities 1, 2, 3, 4, 6, 8, 11,
12, 13 because every one of them is a different WAY to turn a query into hits or
a URL into page text. The modality-parity proof
(`tests/test_modality_parity.py`) holds precisely because those modalities all
fit the `search`/`fetch` shape, so we can swap the backend without touching the
action space, the policy, the parser, or the reward.

Three of the new modalities do NOT fit `search`/`fetch`:

- SQL / text-to-SQL (7b): the input is a query language, not a URL, and the
  output is rows. It can be coerced into `fetch("sql://...")` but that is a
  leaky abstraction the policy cannot reason about.
- Code / terminal execution (7): the input is a program, the output is
  stdout/stderr/files. There is no URL.
- DB-mutating write-actions (9): the contract is a state diff, not a
  `(url, text)` pair, and the reward is a different verifier entirely.

Forcing these through `fetch` would either hide them from the policy or smuggle
arbitrary side effects through a method named "fetch". So the minimal correct
generalization is: keep `SandboxBackend(search, fetch)` as the load-bearing
acquisition seam for everything that lands `(url, text)`, and add ONE thin typed
tool layer on top for the non-`(url,text)` verbs. This mirrors how the frontier
frameworks converged: a registry of typed callables with declared
input/output schemas (LangChain tools, smolagents `agent.tools` dict, OpenAI
Responses API tool list, MCP Tools primitive). We do not need to rebuild as a
heavy generic framework; we need a small registry that the existing seven-action
loop dispatches into.

### 2.2 The recommended minimal generalization

Add a `Tool` abstraction and a per-task `ToolRegistry`, and add ONE new env
action, `CallTool(name, args)`. Concretely:

```python
# src/rl/tools.py  (new, ~120 lines)
@runtime_checkable
class Tool(Protocol):
    name: str                       # "run_code", "sql", "crawl", "read_pdf", ...
    input_schema: dict              # JSON schema for args (for the parser + MCP)
    def __call__(self, args: dict, ctx: "ToolContext") -> "ToolResult": ...

@dataclass
class ToolResult:
    # The union return: a tool may land grounding pairs, emit text for the obs,
    # AND/OR record a state mutation for a non-grounding verifier.
    snippets: dict[str, str] = field(default_factory=dict)   # url -> page_text -> retrieved_snippets
    fetched_urls: list[str] = field(default_factory=list)    # -> fetched_urls (proof-of-fetch)
    observation_text: str = ""                               # rendered into the tool-result message
    state_delta: dict | None = None                          # for write-action / state-diff verifiers
    ok: bool = True
    error: str | None = None
```

`ToolContext` carries the live `SandboxBackend`, the task config, the strict
allowlist, and the `run_id` for retrieval logging, so a tool reuses the existing
fetch/log/canonicalize plumbing rather than reimplementing it.

The existing seven actions stay verbatim. `Search`/`Open`+`Read` remain the
universal floor (they ARE just the `search`/`fetch` tools, kept first-class so
the 4B text policy and all 13 leaderboard adapters are byte-for-byte unchanged).
`CallTool` is the single new opcode; the registry maps `name` to a `Tool`. The
parser (`src/rl/action_parser.py`) gains one directive form,
`TOOL: <name> <json-args>` (and the JSON-action equivalent `{"action":"tool",
"name":..., "args":...}`), routed to `CallTool`. `ResearchEnv._do_call_tool`
runs the tool, then folds `ToolResult.snippets`/`fetched_urls` into the same
`retrieved_snippets` / `fetched_urls` it already maintains, so the grounding
reward sees tool-acquired evidence with ZERO reward change. `state_delta` is
recorded on the rollout for the write-action verifier only.

This keeps the reward modality-agnostic by construction: a tool that lands
`(url, text)` pairs is indistinguishable from `Read` at reward time; a tool that
only mutates state lands no pairs and is scored solely by its own verifier.

### 2.3 How tasks declare allowed tools (extend `acquisition`)

The `acquisition` block (`docs/ACQUISITION_MODALITIES.md` section 3) gains a
`tools_allowed` list. Default behaviour is unchanged: absent the field, the task
exposes only the universal floor (`search`, `fetch`) on the modality named by
`backend`/`modalities[0]`, exactly as today.

```json
"acquisition": {
  "modalities": ["browser"],
  "backend": "browser",
  "shim_url": "http://localhost:8081",
  "tools_allowed": ["search", "fetch", "sql", "run_code", "crawl"]
}
```

| Field | Type | Meaning | Default |
| ----- | ---- | ------- | ------- |
| `tools_allowed` | `list[str]`, optional | tool names the registry exposes for this task; gates `CallTool` | `["search", "fetch"]` (the floor implied by the chosen modality) |

`make_backend_from_task` keeps choosing the `(url,text)` backend; a sibling
`build_tool_registry(task_config, ctx)` builds the registry from
`tools_allowed`, refusing any name not on the task's list (a disallowed tool
call returns `ToolResult(ok=False, error="tool_not_allowed")`, never a crash).
A task can therefore be a pure-retrieval RL task (floor only, today's behaviour),
a "research + compute" task (`+run_code`, `+sql`), or a write-action task
(`+place_order`, scored by the state-diff verifier). This is also the natural
allowlist for the MCP server (modality 10): the MCP `tools/list` is exactly the
registry, so an external agent sees the same typed tools the native policy does.

### 2.4 What does NOT change

The seven-action opcode set grows by exactly one (`CallTool`). The grounding
reward, the strict allowlist, the proof-of-fetch overlay, the 13 leaderboard
adapters, the modality-parity test, and every existing task file are untouched.
Heavy modalities attach as tools whose heavy import is lazy (section 3.0), so
`import src.rl.tools` and `import src.rl.env` still succeed on a plain `python3`.

## 3. Phased rollout

Ordering is cheapest-highest-value first. Each phase lists the modalities, the
backend/tool to build, the lazy-import + offline-test discipline, the NEW tasks
that exercise it, any verifier/eval change, and the parity/regression tests.

### 3.0 Cross-cutting rules (apply to every phase)

- Heavy deps stay lazy: any `import torch` / `playwright` / VLM client / FAISS /
  Whisper lives INSIDE the tool method that needs it, never at module top, so
  `import src.rl.tools` succeeds on system `python3` (the existing
  `BrowserSandboxBackend._ensure_page` pattern).
- Offline-testable: every tool takes an injection seam (a fake backend, a canned
  index, a stub exec result) so its unit test runs with no network/GPU/service,
  the way `MockSandboxBackend` and the fake Playwright page already do.
- Allowlist first: any tool that reaches the network goes through
  `_url_is_sandbox` / `SHIM_MODE=strict` (`integrations/search_shim/app.py`) and
  logs proof-of-fetch to `logs/retrieval/<run_id>.jsonl`. A tool that executes
  code or SQL is network-locked to the three hosts and read-only by default.
- Parity gate: every new `(url,text)` tool must extend
  `tests/test_modality_parity.py` so that, for an identical acquired set, its
  reward equals the shim path's. Non-grounding tools get their own verifier test.

### Phase P0 -- foundation (the tool registry)

- Modalities: none yet; this is the enabling refactor for everything after.
- Build: `src/rl/tools.py` (`Tool`/`ToolResult`/`ToolContext`/`ToolRegistry`),
  the `CallTool` action + `ResearchEnv._do_call_tool`, the `TOOL:` parser
  directive, `build_tool_registry(task_config, ctx)`, and the `tools_allowed`
  field. Register `search` and `fetch` as the first two `Tool`s wrapping the
  current backend so the floor goes through the registry with no behaviour
  change.
- Lazy/offline: registry construction imports nothing heavy; the two floor tools
  just call the injected backend.
- New tasks: none; existing tasks resolve to `tools_allowed=["search","fetch"]`.
- Verifier/eval: none. `state_delta` plumbing added to the rollout dataclass but
  unused until P3.
- Tests: a new `tests/test_tool_registry.py` (dispatch, `tool_not_allowed`,
  `CallTool` folds snippets into `retrieved_snippets`); existing
  `test_modality_parity.py` must still pass unchanged, proving the floor is
  byte-identical through the registry. Effort S-M.

### Phase P1 -- sandbox-core, cheapest high value (no GPU)

Modalities 5 (structured connectors), 6 (local dense+hybrid RAG), 7b (read-only
SQL), 8 (crawl/map). All run against our three hosts with no GPU and land
`(url,text)` (5, 6, 8) or rows-then-cite-URLs (7b).

- 5 Structured connectors -- `Tool: product_lookup`, `Tool: post_lookup`.
  Build: thin tools that POST to the EXISTING shim `/product_lookup` and
  `/post_lookup` (`integrations/search_shim/app.py:533,574`) and return the typed
  record as `observation_text` plus the PDP/post URL into `fetched_urls`+`snippets`.
  This is the single cheapest high-value fix because the endpoints already exist;
  we only wire them into the registry. Effort S. New task: a product-spec or
  forum-thread task that needs a typed field (price, score). Tests: a fake-shim
  unit test; parity (the cited URL resolves like a `fetch`).
- 6 Local dense+hybrid RAG -- `make_backend('vector')` + `Tool: vector_search`.
  Build: an offline index over the Kiwix ZIM + Magento catalog + Postmill text
  (chunk, embed, FAISS or Qdrant; hybrid BM25+dense + optional rerank), `url` =
  doc id, returning `(url, snippet)`. This is the BrowseComp-Plus design and the
  single most valuable AgentRL ablation knob: vector vs keyword-shim vs browser
  as a controlled retriever variable. Lazy: FAISS/embedding model imported inside
  the backend; a tiny canned index for tests. Effort L (CPU ok, GPU optional for
  embedding throughput). New task: a retriever-sensitive task where the answer
  page is not the top keyword hit. Verifier: none (grounding unchanged). Tests:
  parity over a canned index; an ablation harness that runs the same task under
  shim vs vector and reports the reward delta.
- 7b Read-only SQL -- `Tool: sql`.
  Build: an allowlisted, read-only connector (`sqlalchemy`+`psycopg2` already in
  `requirements.txt`) to Magento MySQL and Postmill PostgreSQL; only `SELECT`,
  statement timeout, row cap, a column allowlist. Returns rows as
  `observation_text` AND maps each answer row to the page URL it renders on, put
  into `snippets`/`fetched_urls`, so the report still cites pages and the
  grounding reward is unchanged. Effort M. New task: a quantitative task (top-N
  SKUs by price, highest-voted threads) the HTML renders piecemeal. Tests: a
  SQLite-backed fake DB unit test; an injection test that a non-SELECT or
  off-allowlist table is refused.
- 8 Crawl / site map -- `Tool: crawl`, `Tool: map`.
  Build: seed-URL link-following with depth/page-count/path-filter limits over
  the bounded Magento (category->PDP) and Kiwix sites, returning many
  `(url,text)` pairs per call; `map` returns a site's URL set. Constrained to the
  7770/9999/8090 allowlist. Effort M. New task: a breadth task ("survey all PDPs
  in category X"). Tests: a fake-page-graph crawl unit test (depth/limit
  honoured, allowlist enforced); parity (each crawled pair credits like a fetch).

### Phase P2 -- heavy / vision modalities (GPU in scope)

Modalities 4 (computer-use vision policy), 11 (on-page content vision), 10 (MCP
wrapper). GPU is unblocked, so the real vision policy is now in scope.

- 4 Computer-use vision policy (partial -> real). Build: replace
  `_TextProxyPolicy` with a real `ComputerUsePolicy` whose `observe()` captures
  `page.screenshot()` (Playwright already provides it) + the accessibility tree
  (optionally Set-of-Marks) and whose `act()` is a VLM emitting the verified
  OpenAI/Anthropic action set (click/double_click/scroll/type/keypress/drag/
  move/wait/screenshot). `ComputerUseBackend.fetch()` already loops
  `observe -> act` until `done`; the real policy fills the loop and STILL returns
  the page's grounding text, so the reward contract is unchanged (the invariant
  documented in `src/rl/backends.py`). This matches the OSWorld/VisualWebArena
  web subset. Lazy: the VLM client + screenshot path import inside the policy;
  the stub stays the offline default so CI never needs a GPU. Effort XL, VLM. New
  task: a canvas/image-only page where DOM text is insufficient. Tests: the
  existing parity test keeps using the stub; a separate, GPU-gated integration
  test exercises the real policy and asserts `fetch()` still returns grounding
  text.
- 11 On-page content vision. Build: an optional vision step inside `fetch()` (or
  a `Tool: vision_extract`) that captions/OCRs real Magento/Wikipedia images and
  appends the text to `retrieved_snippets`; reward unchanged (text into
  snippets). Effort L, VLM. New task: an image-grounded question (a fact only in
  a product photo). Verifier: none new; the grounding F1 simply sees the
  caption text. Tests: a stub captioner for offline parity; a GPU-gated test with
  a real caption.
- 10 MCP server wrapper. Build: a local MCP server (Streamable HTTP transport,
  Tools/Resources/Prompts per the Nov 2025 spec) whose `tools/list` IS the P0
  registry, pointed at the strict allowlist, so external frontier agents (OpenAI
  DR, Claude Code, gpt-researcher, LangChain ODR) drive our corpus through the
  de-facto standard. Adds NO new local data; standardizes access and reuses the
  registry directly. Effort M. New task: none (transport, not a data source).
  Tests: an MCP client smoke test that `tools/list` matches the registry and a
  `search`/`fetch` round-trip returns the same bytes as the native path.

### Phase P3 -- general / external / new-content modalities

Modalities 9 (write-actions + user-sim), 12 (file ingestion), 13 (audio/video).
These need either a new reward contract or new seeded content.

- 9 DB-mutating write-actions + user-sim + state-diff verifier. Build: typed
  write tools (`add_to_cart`, `place_order`, `cancel_order`) on Magento's
  cart/order DB (authenticated `admin/admin1234`), an LLM user-simulator
  constrained by tools+observable state (the tau2-bench design), and a NEW
  `state_diff_verifier` that grades final DB state against a goal state (pass^k).
  This is a SEPARATE reward contract from grounding and uses `ToolResult.state_delta`.
  Effort L, LLM user-sim (no vision). New task: a transactional task ("cancel the
  pending order and re-order item Y"). Verifier: new `state_diff_verifier`; the
  grounding reward is not used for these tasks. Tests: a fake-DB state-diff unit
  test; a scripted-user-sim deterministic test. SECURITY: writes are confined to
  a resettable sandbox DB snapshot, never a shared store.
- 12 File / document ingestion. Build: FIRST seed document artifacts (product
  spec-sheet PDFs, forum XLSX exports) into the corpus, THEN a `Tool: read_pdf`
  (Docling-style single-VLM parse, with native-text fast path; `pdf2image`/
  `pytesseract`/`markdownify` already in reqs) whose output lands in
  `retrieved_snippets` via a `file://` URI. A NEW task-capability field plus new
  content, not just code. Effort L (VLM for OCR/charts; none for native PDF
  text). New task: a GAIA/SpreadsheetBench-shaped attachment task. Verifier:
  grounding unchanged (cite the `file://` URI). Tests: a native-text PDF fixture
  unit test; a GPU-gated OCR test.
- 13 Audio / video ingestion. Build: FIRST seed media, THEN a Whisper ASR +
  ~1fps keyframe pipeline emitting transcripts into `retrieved_snippets`.
  Lowest priority: needs both new content and heavy infra; only build if a future
  task explicitly demands AV grounding. Effort XL, VLM+ASR.

## 4. Honest notes

### Genuinely usable against OUR sandbox today (no new content)

- Floor (1, 2, 3) and gating/provenance (15, 16): already shipped.
- Structured connectors (5): endpoints exist; only registry wiring is missing.
- Local RAG (6), SQL (7b), crawl/map (8), code-exec (7): fully buildable against
  the three hosts with the data we already serve. RAG and SQL are the
  highest-value adds because they make the retriever and the quantitative surface
  controllable AgentRL variables. SQL is honest because Magento/Postmill are real
  relational stores; we cite the page URLs the rows render on, so grounding holds.
- Computer-use (4) and on-page vision (11): our sites contain real DOM and real
  images, so a vision policy has genuine work to do. These are honest the moment
  GPU is available, which it now is.
- MCP wrapper (10): honest, adds no data, standardizes external access.

### Needs new SEEDED content before it is honest

- File ingestion (12) and audio/video (13): the sandbox serves only HTML today.
  We must FIRST author/seed PDFs, spreadsheets, or media INTO the corpus; only
  then is a parse/ASR tool grounded. Do not ship a parse tool with nothing to
  parse. The unused `pytesseract`/`pdf2image`/`pillow`/`markdownify` deps are a
  reminder that this was scoped but never sourced.

### Out of scope (do NOT build a fake version)

- Scholarly APIs (14): no live internet, no arXiv/PubMed/Semantic Scholar, no
  citation graph. Kiwix Wikipedia is reference text, not a paper index. A
  scholarly tool with no grounded backing would be dishonest; listed only for
  full-surface completeness.
- Open-web search and live email/calendar connectors: the arena is a permanent
  closed allowlist by design (the reproducibility thesis); a live-web tool would
  break it.

### Where real GPU / model resources are needed

- VLM (a vision-language model): computer-use policy (4), on-page content
  vision (11), VLM-OCR/chart parsing in file ingestion (12). CPU-only stubs keep
  CI green; the GPU is needed only for the real policy/parser at train/eval time.
- Embeddings: local dense RAG (6) wants an embedding model. CPU works for a
  bounded local corpus; a GPU speeds index build and rerank.
- ASR (Whisper) + VLM: audio/video (13) only.
- LLM (text-only): the user-simulator for write-action tasks (9). No vision.
- No GPU at all: structured connectors (5), SQL (7b), crawl/map (8), code-exec
  sandbox (7), MCP wrapper (10), and the entire P0 registry refactor.

### Security notes (load-bearing)

- Code-exec (7) and SQL (7b) are the two highest-risk adds: arbitrary execution
  on the training host is a host-escape hole. Both MUST be network-locked to the
  three localhost services, SQL read-only by default with a column allowlist and
  statement timeout, and code-exec in a microVM/container with no host FS or
  outbound network. See `docs/SECURITY_RISK_AGENT_ESCAPE.md` and
  `docs/THREAT_MODEL_GENERAL_AGENT_INTEGRATION.md`.
- Write-actions (9) MUST run against a resettable sandbox DB snapshot, never a
  shared/canonical store, so a bad rollout cannot corrupt the corpus.
</content>
</invoke>
