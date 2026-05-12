# Deep-Research Arena: A Sandbox Benchmark for Open-Source Deep-Research Agents

*Thesis-defense documentation. Last updated 2026-05-10.*

---

## 1. Title and Abstract

**Title:** Deep-Research Arena: a sealed-sandbox, truthfulness-gated, Bradley-Terry benchmark for open-source deep-research (DR) agents.

**Abstract.** This thesis builds and validates a reproducible benchmark for open-source deep-research agents. The benchmark substitutes the live internet with three sealed services: a Magento storefront on `localhost:7770`, a Postmill forum on `localhost:9999`, and a Kiwix offline-Wikipedia mirror on `localhost:8090`. Two glue services, a Tavily-compatible search shim on `localhost:8081` and an OpenAI-compatible LLM proxy on `localhost:8088`, are the only routes by which an agent's process can reach search or model traffic. Thirteen open-source DR frameworks were instrumented to route both kinds of traffic through these endpoints; nine produced enough valid runs across 56 cross-site deep tasks to enter the headline Bradley-Terry ranking. Each agent report is scored on seven verification pillars, three of which (URL reachability, quote match, claim NLI) are deterministic truthfulness probes and four of which (URL coverage, checklist, citation alignment, presentation, analysis depth) blend deterministic structure checks with DeepSeek V4-flash judges at temperature zero. The pillars feed into three composite scores: `composite_v1` is additive, `composite_v2_truthful` multiplies a reachability gate over the quality term and is the headline metric, and `composite_v3` extends the multiplicative form with citation alignment, depth, and presentation while replacing the hard gate with a `max(0.1, reach)` floor. The single most consequential finding is that the truthfulness gate inverts naive ranking. Under `composite_v1` the GitHub-popular `gpt-researcher` framework tops the leaderboard at Elo 1269. Under `composite_v2` the same agent drops to fifth place at Elo 866, and `camel-ai`, which has explicit URL-deduplication and citation-validation passes, rises to first at Elo 1481. Fluent prose is not the same thing as cited evidence, and a benchmark that scores them together rewards the wrong behaviour. The contribution of this thesis is the design choice that separates them, the implementation that runs reproducibly on commodity hardware, and the evidence from 283 scored runs that the separation actually matters.

---

## 2. Motivation: why live-internet DR benchmarks fail science

A deep-research agent reads a research question, searches the web, fetches pages, and writes a cited report. The behaviour we want to evaluate is multi-faceted: did the agent find the right sources, did it cite them faithfully, did it synthesise across sources rather than parrot one, did it acknowledge limitations. The natural setting in which to measure all of this is the live internet, and that is where the most-cited public DR benchmarks (GAIA, BrowseComp, AssistantBench, BrowserGym) operate. The premise of this thesis is that for *scientific* measurement of agent capability, as opposed to product evaluation, the live internet is the wrong setting.

The first problem is drift. The page that supported a claim last Tuesday may 404 today, may have been edited yesterday, may have been re-ranked by the search engine this morning. Two researchers who run "the same" benchmark a month apart get different numbers, and neither can prove the other wrong. The benchmark itself becomes unfalsifiable. GAIA partially mitigates this by anchoring answers to facts that change slowly, but it cannot anchor the *retrieval path*: whether the agent found a supporting page in 2024 says nothing about whether the same query returns the same page in 2026.

The second problem is that scoring the live web is intractable in the way that matters. Truthfulness scoring requires three things: did the agent's URL resolve, does the page actually contain the quoted text, does the cited page actually support the surrounding claim. On the live web each of these probes is a coin toss against geographic routing, login walls, rate limits, CDN variance, and silent page redesigns. A URL that returns 200 from the agent's machine may return 403 from the scorer's. ALCE (`Gao et al., 2023`) sidesteps this by precomputing a corpus and scoring against the corpus; that is exactly the move this thesis generalises to a multi-corpus interactive setting.

The third problem is that live-web benchmarks conflate product evaluation with capability measurement. When `gpt-researcher` (25.7k GitHub stars) ranks high on a live-web benchmark, two readings are possible. The first is that its agent architecture is good. The second is that its prompt is well-tuned to the live web's pages, its retrieval pipeline is well-engineered around real Google or Bing rankings, and the framework's authors have spent two years closing the implementation gap between paper and product. Both are valid forms of progress, but only the first is what we are claiming to measure. A sandbox benchmark with a fixed search shim and a frozen page corpus deliberately neutralises the second reading. Whatever ranking emerges has to be explained by the agent's logic given the same retrieval substrate. This is why ALCE-style citation faithfulness (`Gao et al., 2023`), FactScore (`Min et al., 2023`), and WebArena (`Zhou et al., 2024`) all freeze the substrate before they score.

A fourth, smaller problem: live-web evaluation is expensive. Every run pulls real pages over real networks, blocks on real rate limits, and burns real LLM tokens on pages that may not even be there next month. A sandbox lets us re-run a single agent on a single task in around fifteen minutes on the eval host, score it deterministically, and reproduce the score on demand.

The trade is realism for reproducibility. A sandbox is small (the three corpora in this work together total roughly 2000 product pages, a Reddit slice with a few tens of thousands of comments, and a Wikipedia subset). What is lost in coverage is gained in being able to compute every truthfulness probe in O(1), against frozen ground truth, with no judgement call on whether a 404 is the agent's fault or the network's. The thesis takes that trade.

---

## 3. Related Work

**DR benchmarks.** GAIA (`Mialon et al., 2023`) was the first widely-cited DR-style benchmark and frames evaluation as agent-against-live-web with answer-string scoring. BrowseComp (`Wei et al., 2024`) extends the same axis with a harder set of multi-step tasks and a tighter scoring rubric, but keeps the live web as the substrate. AssistantBench (`Yoran et al., 2024`) shifts toward longer-horizon tasks and partial-credit scoring, again on the live web. BrowserGym (`Drouin et al., 2024`) ships a unified browser-environment API that can connect to either live web or recorded HAR replays; it is the closest in spirit to this work but does not specify a scoring stack, only an environment.

**Sandboxed agent eval.** WebArena (`Zhou et al., 2024`) is the most direct ancestor: a sealed Magento + GitLab + Reddit + Map + Wikipedia setup against which web-navigation agents are scored. WebArena scores success on task completion; our benchmark inherits the same sandboxing philosophy and the same Magento and Postmill instances but trades the task-completion bit for a multi-pillar report-quality score. AgentBench (`Liu et al., 2024`) provides a broader sandboxed agent eval across eight environments but is geared toward single-task success, not multi-source synthesis.

**Citation faithfulness.** ALCE (`Gao et al., 2023`) introduced the per-citation precision/recall framing used by this thesis's `citation_alignment` pillar: does the cited URL actually support the surrounding claim? `Gao et al.` evaluated on a frozen retrieval corpus; we apply the same construct on top of a multi-corpus interactive sandbox. FactScore (`Min et al., 2023`) decomposes long-form generation into atomic facts and scores each against a knowledge base; we adapt the multi-pillar idea but keep the verification surface tighter, three deterministic probes plus four LLM-judged rubrics, rather than per-atomic-fact judgements.

**RAG and grounded generation.** RAGAS (`Es et al., 2023`) proposes a set of automated metrics for retrieval-augmented generation: faithfulness, answer relevance, context relevance. Our `claim_nli` pillar is the same construct expressed against per-task golden quoted spans rather than the runtime-retrieved context.

**LLM-as-judge.** The temperature-zero LLM-judge construct is standard practice since `MT-Bench` (`Zheng et al., 2024`) and Chatbot Arena (`Chiang et al., 2024`). This work adopts the rubric-decomposition variant ("split a single Likert into many independent binaries") associated with DRACO (`Ji et al., 2026`), and combines it with a deterministic grounding-keyword cross-check that downgrades a PASS verdict to FAIL when the relevant URLs do not resolve.

**Ranking via pairwise comparison.** Chatbot Arena uses Bradley-Terry / Elo on human-graded pairwise wins. This thesis uses the same model but synthesises battles from the multi-pillar composite, on the grounds that with a small agent set (nine in the headline) and a frozen task set (56), pairwise comparison is a more stable aggregation than raw mean composite (more discussion in section 10).

**Where this benchmark is different.** Three combinations are, to our knowledge, novel. First, a multi-source sealed sandbox (Magento + Postmill + Kiwix) glued by a single Tavily-compatible search shim, so any agent that speaks Tavily speaks our benchmark. Second, a multiplicative truthfulness gate (`composite_v2`) that makes URL reachability non-negotiable: an agent that fabricates URLs gets a literal zero, regardless of how fluent its prose is. Third, a complete reproducibility surface, sandbox + shim + ds_proxy + golden pools + scoring code, so any reviewer with the snapshot can rebuild every Elo number in this thesis from scratch.

---

## 4. System Overview

The benchmark architecture is three sandbox services, two glue services, one task corpus, one scoring stack, and a runner-per-framework integration layer. Every component runs on a single Windows + WSL host (`westd`), and every component is reachable on localhost.

The agent's process sees only localhost. Network egress is blocked except through the search shim and the LLM proxy. Every search call leaves the agent venv on port 8081; every model call leaves on port 8088. Every URL the agent produces is checked against the three sandbox host:port pairs (`localhost:7770`, `localhost:9999`, `localhost:8090`). If a URL points anywhere else, it does not count toward citation coverage or reachability. This single rule is what makes truthfulness scorable.

```
                    +-----------------+
                    |   Task corpus   |
                    |  100 specs +    |
                    |  golden pools   |
                    +--------+--------+
                             |
                             v
+--------+   intent    +-----+------+   search    +-----------+
| Runner +------------>|   Agent    +------------>|  Shim     |
| script | <- report --+  (in venv) |<- results --+ :8081     |
+---+----+             +---+--------+             +-----+-----+
    |                      |                            |
    |   md report          | LLM calls                  | route by domain
    v                      v                            v
+--------+            +-----+-------+         +---------+---------+
| Scorer |            | ds_proxy    |         | Magento :7770     |
|  7     |<-----------+ :8088       |         | Postmill :9999    |
| pillars|            +-----+-------+         | Kiwix :8090       |
+---+----+                  |                 +-------------------+
    |                       v
    v                +------+-------+
+--------+           | DeepSeek v4  |
| score  |           | flash (real) |
| .json  |           +--------------+
+--------+
    |
    v
+-------------------+
| Leaderboard build |
| Bradley-Terry +CI |
+-------------------+
```

The scorer (`scripts/score_deep_answer.py`) reads the markdown report from the runner, computes seven pillar scores, persists them into a `<agent>__<task>_matrix.score.json`, and writes nothing else. The leaderboard builder (`scripts/build_deep_leaderboard.py`) reads every such file, drops the degenerate ones, synthesises pairwise battles per task on `composite_v2`, fits a Bradley-Terry model with bootstrap CIs, and writes `LEADERBOARD_DEEP.md` and `leaderboard_deep.json`. The web app (`web/server.py`) reads those two files live, no database, so the in-flight bulk run is visible as soon as the builder finishes a pass.

| Component | Location | Owns |
|---|---|---|
| Magento (shopping) | `localhost:7770` (docker `webarena_shopping`) | ~2000 product pages, categories, reviews |
| Postmill (forum) | `localhost:9999` (docker `webarena_reddit`) | forum threads, comments, sub-forum taxonomy |
| Kiwix (Wikipedia) | `localhost:8090` (docker `kiwix`) | offline ZIM mirror of English Wikipedia |
| Search shim | `localhost:8081` (`integrations/search_shim/app.py`) | Tavily-compatible API surface, indexes the three corpora |
| DS proxy | `localhost:8088` (`integrations/ds_proxy/app.py`) | OpenAI-compatible proxy to DeepSeek V4-flash, injects `thinking: disabled` |
| Runner dispatch | `scripts/run_deep_task.py` `RUNNERS` dict (line 1359) | maps `--agent name` to one of 13 async runners |
| Verifier stack | `src/verifiers/` | 7 pillars, all called by `score_deep_answer.py` |
| Composite formulas | `src/scoring/leaderboard_composites.py` | single source of truth for v1, v2, v3 |
| Leaderboard build | `scripts/build_deep_leaderboard.py` | reads score JSONs, writes Elo table |

---

## 5. Sandbox Design

The sandbox is designed for three properties: every URL the agent might cite is deterministically reachable, the three corpora are different enough that a cross-source task is not trivial, and the whole stack fits on a single machine with no live-internet calls during a run. Each corpus is the smallest realistic fragment of a real DR substrate.

### 5.1 Magento (shopping, `localhost:7770`)

The shopping corpus is a Magento 2 storefront imported from the WebArena `onestopmarket` snapshot. It exposes roughly 2000 product pages across a category tree of three top-level departments (Electronics, Home & Kitchen, Beauty & Personal Care) and dozens of leaf categories. Every product page contains the URL slug, price, star rating, review count, free-text feature list, and a small number of user reviews; the leaderboard's recommendation and comparison tasks rely on all of those fields. Magento was selected because it is the realistic substrate WebArena uses, because the product pages have stable URL structure ending in `/product/...html`, and because a real Magento instance lets us reuse WebArena's category-page → product-page browsing pattern without rewriting any of it. Two practical consequences:

1. URLs are case-sensitive on the path (Magento defaults). Frameworks that lower-case the path break reachability; one of the `ldr` failure modes is exactly that.
2. Under parallel HEAD probes Magento occasionally resets the connection. The `URLReachabilityVerifier._probe` function (`src/verifiers/url_reachability_verifier.py:55-82`) uses GET (not HEAD) with three retries and exponential back-off for this reason.

### 5.2 Postmill (reddit, `localhost:9999`)

The forum corpus is a Postmill instance also imported from WebArena. It hosts a curated set of "subreddits" (`/f/technology`, `/f/gadgets`, `/f/AskReddit`, `/f/headphones`, `/f/askscience`, ...) with threads, comments, upvote counts, and timestamps. Postmill was selected because it is the open-source Reddit-clone WebArena ships, because its URL structure (`/f/<forum>/comments/<post_id>/<slug>`) is stable, and because the comment hierarchy gives the agent something to "harvest community sentiment" from in a way a static product page cannot. Tasks that ask the agent to classify threads (`praise`, `complaint`, `technical_question`, `comparison`, `purchase_advice`) rely on the comment text being intact.

### 5.3 Kiwix (Wikipedia, `localhost:8090`)

The encyclopedia corpus is a Kiwix server serving an offline `wikipedia_en_all_nopic` ZIM file. Article URLs take the form `localhost:8090/content/wikipedia_en_all_nopic/A/<Article_Title>`. Kiwix was selected because the ZIM file is a frozen, signed snapshot of Wikipedia, because the Kiwix server is small and deterministic, and because a Wikipedia mirror is the natural "encyclopedic backbone" against which technical claims (codecs, batteries, RFCs) can be checked. Two practical consequences:

1. Article paths are case-sensitive (`/A/Bluetooth` works, `/A/bluetooth` returns 404). Several frameworks normalise paths to lower case by default and get reachability=0 on the wiki corpus alone; the leaderboard ranks `ldr` low partly because of this (mean composite_v2 = 0.029 across its 30 scored runs, see leaderboard raw table for `ldr`).
2. Some frameworks emit Wikipedia URLs as `en.wikipedia.org/wiki/<Title>` because their search returned the live Wikipedia URL. The HTTP-level intercept in `scripts/run_deep_task.py:107-115` rewrites those into Kiwix-prefixed URLs in flight so the page actually loads; without the rewrite, `langchain-odr` and `ii-researcher` both ship reports full of external URLs that score reachability=0.

### 5.4 Search shim (`localhost:8081`)

The search shim is a Tavily-compatible HTTP service implemented in `integrations/search_shim/app.py`. Its public surface is two endpoints, `POST /search` and `POST /extract`, with the exact request/response schemas Tavily uses. Internally, the shim routes every incoming query to one or more of three indexes (product titles for shopping, thread titles + bodies for reddit, article titles + lede paragraphs for wikipedia), merges the top-N hits, and returns them in Tavily's JSON shape. Three properties are important:

1. **Tavily compatibility is the integration contract.** Every framework integrated in this benchmark already supports Tavily. Pointing each framework's Tavily client at the shim is a one-line config (a `base_url` or `api_base_url` kwarg). No prompt-engineering or custom-tool plumbing is required.
2. **No real internet.** The shim never makes outbound network calls. It serves only what is in the three sandbox indexes. An agent that searches for a brand the sandbox does not stock gets an empty list, the same way Tavily would return an empty list against a query with no hits.
3. **Stable ranking.** Search results are ordered by a fixed BM25 score, not by time or session, so the same query at minute 0 and minute 1000 returns identical results. This is what makes the per-task golden pool a valid frozen ground truth.

The shim is what makes the rest of the architecture work: every integration in section 7 is a five-line glue layer that points a framework's Tavily client at `http://localhost:8081`.

### 5.5 DS proxy (`localhost:8088`)

The DS proxy is an OpenAI-compatible LLM endpoint implemented in `integrations/ds_proxy/app.py`. The agent venvs talk to it as if it were `https://api.openai.com/v1`, with the same `Authorization: Bearer <key>` header and the same `/chat/completions` JSON shape. The proxy then translates each incoming request into a DeepSeek API call, injects `thinking: disabled` into the request body so the backbone never spends tokens on reasoning, and streams the response back. Three reasons to centralise the LLM in this proxy:

1. **One backbone for the whole benchmark.** Every agent in the headline ranking runs on the same `deepseek-v4-flash` non-reasoning checkpoint. Across-agent comparisons therefore measure agent architecture, not backbone strength. A future "Compare across LLMs" page (already routed in the web app at `/compare`) will swap the proxy's backend, not the agents.
2. **Server-side key.** Agents only see `OPENAI_API_KEY=anything`. The real DeepSeek key lives in the proxy environment, never in any agent venv or driver script. This is also what lets a fresh runner work zero-config: it inherits the `OPENAI_BASE_URL` env var from `scripts/run_deep_task.py:50-53` and reads `anything` as the key.
3. **Single point to disable reasoning.** Some frameworks (`langchain-odr`, `qx-agents`) silently switch to reasoning mode if the model name contains certain substrings. Injecting `thinking: disabled` at the proxy intercepts every request regardless of which framework issued it and guarantees the comparison is on the same non-reasoning checkpoint.

The proxy also serves as the judge endpoint. `judge_client.py` reads `JUDGE_BASE_URL=http://localhost:8088/v1`, so every LLM-judge call (checklist, citation_alignment, presentation, analysis_depth, claim_nli) hits the same proxy, the same backbone, with `temperature: 0`. Determinism of LLM-judge scoring is contingent on this temperature setting plus DeepSeek's documented zero-temperature determinism guarantee.

---

## 6. Task Design

The task corpus is 100 cross-site deep-research tasks, of which 57 are scored end-to-end in the current run (one task, `dr_cross_deep_0044`, was dropped during golden-pool sanity checks). Each task is a single YAML/JSON spec under `data/tasks/deep_research/cross_site_deep/`. A task spec contains the natural-language intent, citation policy (per-domain minima, total minimum, must-be-in-domain list), markdown spec (word/citation/paragraph limits), URL coverage settings (golden pool path, recall/coverage thresholds), URL reachability threshold, golden triple file path, optional synthesis requirements, and the path to the per-task checklist JSON. The schema is versioned (`schema_version: deep-1.0.0`) so verifiers can future-proof against added fields.

Three task-design constants:

1. **Three sites per task.** Every cross-site task requires citations from all three sandbox corpora. The `citation_policy.per_domain_minimum` block specifies how many distinct URLs from each (a representative split for the audio-headphones task is 30 shopping, 20 reddit, 15 wikipedia).
2. **Total citation floor.** Every task requires at least 60 cited URLs in the markdown (`citation_policy.min_distinct_sources` and `markdown_spec.min_citations`) and at least 120 must-cite URLs in the golden pool. The 120 number is the visibility floor: it forces the agent to genuinely cross-search and find independent evidence, not regurgitate the first three Tavily hits.
3. **Frozen golden pool.** Each task has a `data/golden/deep/dr_cross_deep_XXXX.json` file built by `scripts/build_deep_golden.py`. The golden pool contains a `must_cite_urls` list (the URLs the agent should hit, with weights), an `expected_pool_urls` list (the broader corpus a competent agent would find), and a `triples` list of `(subject, predicate, object, source_url, quoted_span)` quads. The triples power `claim_nli`. Both pools are scraped once from a clean sandbox snapshot and never regenerated, so the recall denominator is fixed.

A representative task is `dr_cross_deep_0001` (Consumer-grade audio headphones, market-intelligence). The intent spans 31 sentences and requires:

- Section A (product landscape): at least 40 distinct product pages spanning at least 6 brands and 3 price tiers, with price/rating/review count/feature claims per product.
- Section B (community sentiment): at least 30 Postmill threads across at least 4 sub-forums, classified into 5 sentiment categories.
- Section C (technical grounding): at least 25 Wikipedia articles backing the technical claims from section A, with mandatory coverage of 9 named articles (Active noise control, Noise-cancelling headphones, Bluetooth, AptX, LDAC, Headphones, Loudspeaker, Lithium-ion battery, Wireless microphone).
- Section D (cross-source synthesis): at least 5 contradictions between product feature claims and Wikipedia, brand ranking by Reddit sentiment, at least 3 rating-vs-sentiment divergences, and a top-10 buy list each with one shopping URL, two reddit URLs, and one wiki URL of evidence.

The full intent is 4,144 characters. The golden pool for this task is `must=125, pool=739` (recorded in the spec's `author_notes` field). The task is one of three "recommendation anchors" (0001 / 0002 / 0005) that test the agent's ability to produce a ranked deliverable rather than a flat enumeration; the remaining tasks span comparison, debunking, causal analysis, timeline, and enumeration patterns.

The full intent text and a sample task spec are available at `data/tasks/deep_research/cross_site_deep/dr_cross_deep_0001.json:12`; the per-task checklist used by the LLM judge lives at `data/tasks/deep_research/cross_site_deep/checklists_deep.json`. Per-task checklists are 21 items, written by hand once per task, and shared across the benchmark.

---

## 7. Framework Integration: 13 Frameworks

Every framework runs against the same shim and the same ds_proxy. The integration layer is one of three flavours: in-process (a function in `scripts/run_deep_task.py` that imports the framework and runs it inside `.venv-camel`), subprocess (a function that writes a driver script to `/tmp/`, scps it to its own venv directory, and runs it under a separate Python), or clean runner (a self-contained module in `scripts/runners/` that exports `async def run(intent, model, shim_url, proxy_url) -> str` and is auto-discovered by `scripts/runners/registry.py` then merged into the dispatch table at `run_deep_task.py:1336-1356`). The dispatch table is `RUNNERS = _build_runners_map()` at `scripts/run_deep_task.py:1359`.

### 7.1 camel-ai (in-process)

camel-ai is a single-loop ChatAgent with explicit tool-call structure. The integration (`scripts/run_deep_task.py:345-413`) monkey-patches `tavily.TavilyClient.__init__` so any TavilyClient instance created downstream gets its `base_url` redirected to the shim, then constructs a `ChatAgent` with `SearchToolkit().search_tavily` as the only tool, wires the model via `ModelFactory.create(model_platform=OPENAI_COMPATIBLE_MODEL, url=proxy)`, and runs a single `agent.step(intent)`. The system prompt is hand-written and contains the lines "NEVER invent URLs" and "you MUST cite at least 15 Wikipedia articles", because camel does not by default split queries across the three corpora. A post-processing pass strips chain-of-thought leakage prefixes ("I now have enough data to compile...") that occasionally appear on the first line. Venv: `.venv-camel`. Runner file: `scripts/run_deep_task.py:345`.

### 7.2 smolagents (in-process)

smolagents is HuggingFace's lightweight tool-call agent loop. The integration (`scripts/run_deep_task.py:288-342`) uses `ToolCallingAgent`, not `CodeAgent`, because CodeAgent generates Python code that *constructs* URLs from string-format patterns, which produced ~92% fabricated URLs in early runs. ToolCallingAgent forces the model to emit a structured tool-call JSON, so the URL must be copied verbatim from the search result. Tavily is patched the same way as for camel-ai; the LLM is `OpenAIServerModel(api_base=proxy)`; the tool stack is `ApiWebSearchTool` (pointed at `shim/search`) + `VisitWebpageTool`. `max_steps=60` is set high enough that the agent can iterate without truncating. Venv: `.venv-smol`. Runner file: `scripts/run_deep_task.py:288`.

### 7.3 gpt-researcher (subprocess via clean runner)

gpt-researcher 0.12.3 is a planner + many-parallel-searchers + writer framework. It imports several pre-1.0 LangChain submodules (`langchain.docstore`, `langchain.vectorstores`, etc.) that no longer exist in LangChain 1.x, which is what the main `.venv-camel` runs for `langchain-odr`. gpt-researcher therefore needs its own venv (`.venv-gptr`). The integration (`scripts/runners/gpt_researcher_runner.py`) writes a driver script to `/tmp/` and runs it under `.venv-gptr/bin/python`. The driver monkey-patches `gpt_researcher.retrievers.tavily.tavily_search.TavilySearch.__init__` to set `self.base_url = f"{shim_url}/search"`, sets `OPENAI_BASE_URL` to the proxy, and uses the `custom:text-embedding-v4` embedding alias so embedding calls also route through the proxy (the original `openai:embedding-3` alias bypassed `OPENAI_BASE_URL` and hit the real OpenAI endpoint, see runner source at `scripts/runners/gpt_researcher_runner.py:17-19` and main runner notes at `scripts/run_deep_task.py:60-65`). The gotcha that defines gpt-researcher's leaderboard position is the slug bug: it generates Magento product URLs by templating product names into `/products/<kebab-slug>`, but Magento's actual slugs include numeric suffixes the agent never sees. Reachability is therefore near zero (mean composite_v2 = 0.013 across 30 runs). Venv: `.venv-gptr`. Runner file: `scripts/runners/gpt_researcher_runner.py`.

### 7.4 langchain-open_deep_research (in-process)

LangChain ODR is a langgraph-based supervisor → researcher → writer pipeline. The integration (`scripts/run_deep_task.py:674-738`) patches both `tavily.TavilyClient` (sync) and `tavily.AsyncTavilyClient` (async), because the original patch only caught the sync client and ODR uses the async one. The async patch sets `self._api_base_url = shim` and, belt-and-suspenders, overrides `self._client.base_url` after init. The graph is compiled and `ainvoke`d with a config that sets all six model channels (`research_model`, `compression_model`, `final_report_model`, `summarization_model`, `writer_model`, `planner_model`) to `openai:<model>`, the search API to `tavily`, and the iteration limits to small numbers (`max_researcher_iterations=5`, `max_react_tool_calls=8`) to keep wall-clock bounded. ODR's failure mode is that when its retrieval cache misses, it falls back to emitting external URLs (real `en.wikipedia.org`, real `reddit.com`) instead of sandbox URLs. Mean composite_v2 = 0.001. Venv: `.venv-langchain-odr`. Runner file: `scripts/run_deep_task.py:674`.

### 7.5 ii-researcher (subprocess)

ii-researcher (Intelligent-Internet) is a ReAct-style chain-of-search agent. The integration (`scripts/run_deep_task.py:1098-1208`) writes a driver that patches `tavily.TavilyClient` in the subprocess to set `base_url=shim`, forces `SEARCH_PROVIDER=tavily` and `SCRAPER_PROVIDER=bs` (BeautifulSoup, so requests go through the patched `requests.Session.send`), purges all proxy env vars, and installs the HTTP-level intercept preamble (`_build_intercept_preamble`, `scripts/run_deep_task.py:70-176`) that rewrites `en.wikipedia.org/wiki/<X>` URLs to `localhost:8090/content/wikipedia_en_all_nopic/A/<X>` at the transport layer. ii-researcher's chain-of-search terminates after roughly three tool-call turns regardless of how long the intent is; the report typically ends with five to fifteen citations, far below the 60 floor. Mean composite_v2 = 0.001. Venv: `.venv-ii`. Runner file: `scripts/run_deep_task.py:1098`.

### 7.6 dzhng (subprocess via Node HTTP API)

dzhng is a Node/TypeScript deep-research framework that exposes an HTTP API on port 3051. The Python integration (`scripts/run_deep_task.py:1238-1257`) is therefore tiny: POST `{query, breadth, depth}` to `http://localhost:3051/api/generate-report` and wait up to 1800 seconds. The Node side is configured to point its OpenAI client and Firecrawl client at our `ds_proxy` and a Firecrawl-compatible adapter respectively. The integration gotcha is API-key plumbing: the Node side reads `OPENAI_API_KEY` from its own `.env`, not from the parent shell, so the key has to be set both inside the Node process environment and at the proxy. dzhng has fewer than 30 successful scored runs in the current dataset and is not on the headline leaderboard. Venv: Node `npm run api` inside `third_party/deep-research/`. Runner file: `scripts/run_deep_task.py:1238`.

### 7.7 flowsearcher-ds (in-process, our agent)

flowsearcher-ds is an in-house deep-research agent built on top of a memory module (`src/memory/hierarchical.py`) with three memory tiers: L1 per-task, L2 per-intent, L3 global. The agent uses memory-guided planning to bias its search toward sub-queries the agent (and prior runs against the same intent) found productive, and emits a structured plan before issuing tool calls. The runner is `scripts/run_flowsearcher.py`'s `run_flowsearcher(intent, model, task_id)` (`scripts/run_deep_task.py:1231-1235`). The integration is in-process because the agent is part of this repo; it lives in `.venv-camel`. flowsearcher-ds's place in the leaderboard (Elo 1401, rank 2) reflects the memory-guided planning: across 30 scored runs its mean composite_v2 is 0.296, lower than camel-ai's 0.410 but with tighter tails (fewer near-zero runs), which is what the pairwise Bradley-Terry rewards. Venv: `.venv-camel`. Runner: `scripts/run_flowsearcher.py`.

### 7.8 deerflow (subprocess via clean runner)

DeerFlow is a langgraph + Tavily multi-agent framework. The integration (`scripts/runners/deerflow_runner.py`) writes a `conf.yaml` and driver to DeerFlow's own root, sets `BASIC_MODEL__base_url` / `BASIC_MODEL__model` / `BASIC_MODEL__api_key` env vars (DeerFlow's official LLM-config surface), and sets `langchain_tavily._utilities.TAVILY_API_URL` to the shim before DeerFlow's wrapper imports it. The driver also replaces DeerFlow's default Jina-based crawler with a lightweight one that calls the shim's `/extract` endpoint, because the Jina default would POST to `https://r.jina.ai/`, which is not reachable from inside the sandbox. The driver also forces `aiohttp.ClientSession(trust_env=False)` to keep WSL's `/etc/environment` proxy vars from leaking through; this is the change that fixed DeerFlow's "real Tavily API rejects fake key" failure mode. Mean composite_v2 = 0.023. Venv: `third_party/deer-flow-v1/.venv`. Runner file: `scripts/runners/deerflow_runner.py`.

### 7.9 ldr (subprocess via clean runner)

LDR (LearningCircuit local-deep-research) uses its own programmatic API (`detailed_research()` with `create_settings_snapshot`). The integration (`scripts/runners/ldr_runner.py`) writes a subprocess driver that passes a settings snapshot via LDR's official `overrides=` parameter, no monkey-patching of LDR internals. The driver does install an HTTP-level intercept that rewrites `api.tavily.com` to the shim and masks `localhost:NNNN` to fake hostnames (`onestopmarket.com`, `postmill.net`, `kiwipedia.org`, `searchapi.internal`) in LLM API calls so DeepSeek V4-flash's safety filter does not block requests that contain raw `localhost:NNNN` (an early failure mode; see `scripts/runners/ldr_runner.py:72-80`). LDR's failure mode on this benchmark is that it lower-cases Kiwix paths in its citation list; Kiwix is case-sensitive on article names, so reachability silently zeros on the wiki domain. Mean composite_v2 = 0.029. Venv: `.venv-ldr312`. Runner file: `scripts/runners/ldr_runner.py`.

### 7.10 qx-agents (subprocess via clean runner)

qx-agents (qx-labs/agents-deep-research) is built on the openai-agents SDK with three configurable model channels and a SearchXNG search adapter. The integration (`scripts/runners/qx_runner.py`) sets `SEARCH_PROVIDER=searchxng`, points `SEARCHXNG_HOST` at a local SerperAdapter (`scripts/runners/serper_adapter.py`) that translates the SearchXNG GET wire format to the Tavily shim POST format, and sets `agents.run_config.DEFAULT_MAX_TURNS = 30` before importing any agent module. qx-agents's failure mode is structural rather than configurational: under DeepSeek V4-flash, the SDK raises `pydantic.ValidationError: 2 validation errors for KnowledgeGapOutput` and downstream `IndexError: list index out of range`, on every task. All 30 runs are filtered by the degenerate filter (`scripts/build_deep_leaderboard.py:60-79`) and qx-agents is excluded from the Elo table with a note in the audit row. Venv: `.venv-qx`. Runner file: `scripts/runners/qx_runner.py`.

### 7.11 tongyi-dr (subprocess via clean runner)

Tongyi DeepResearch is Alibaba-NLP's ReAct loop built around `qwen_agent`. The Tongyi 30B-A3B MoE checkpoint would require roughly 60 GB of VRAM in bf16; the RTX 5090 on the eval host has 32 GB. The integration (`scripts/runners/tongyi_runner.py`) instead writes a driver that redirects Tongyi's OpenAI client to the ds_proxy (so the LLM is DeepSeek V4-flash, not Qwen). Tongyi's five tools are kept: Search (replaced with a shim-compatible POST), Visit (replaced with `requests.get` plus LLM summarisation), Scholar (returns empty, sandbox has no scholar), Python (returns error, sandbox has no SandboxFusion), FileParser (disabled). `MAX_LLM_CALLS=50` caps total iterations. Tongyi is not on the headline leaderboard. Venv: `.venv-tongyi`. Runner file: `scripts/runners/tongyi_runner.py`.

### 7.12 deepagents (subprocess via clean runner)

LangChain DeepAgents is a langgraph super-agent with planning (`write_todos`), sub-agent spawning, and a filesystem tool. DeepAgents does not ship a built-in search tool; the integration (`scripts/runners/deepagents_runner.py`) defines a thin `internet_search()` function that POSTs to the Tavily shim and passes it to `create_deep_agent(tools=[...])`. The LLM is wired via `init_chat_model("openai:<model>", base_url=proxy, api_key=...)`. Output is extracted from `result["messages"][-1].content`. DeepAgents is not on the headline leaderboard (under-scored). Venv: `.venv-camel` (shared) or `.venv-deepagents`. Runner file: `scripts/runners/deepagents_runner.py`.

### 7.13 storm + co-storm (subprocess via clean runner)

STORM and Co-STORM are the Stanford `knowledge_storm` package. The STORM integration (`scripts/runners/storm_runner.py`) implements a `SandboxSearchRM` that subclasses `dspy.Retrieve` and issues searches against the shim, then drives the standard STORM pipeline (`run_knowledge_curation_module` → `run_outline_generation_module` → `run_article_generation_module` → `run_article_polishing_module` with `do_polish_article=True`). The bug that defined STORM's leaderboard position until very late in the benchmark was that the runner read `storm_gen_article_polished.txt` (which is the body of the article only) and never merged the separately-tracked `url_to_info.json` bibliography back into the markdown. The agent had cited correctly internally; we were scoring a citation-stripped body. The fix (`scripts/runners/storm_runner.py:299-313`) appends a `## References` section reconstructed from `url_to_info.json`. After the fix, STORM went from composite_v2 = 0.000 on every run to roughly 0.067 on the small post-fix re-run set. The Co-STORM runner (`scripts/runners/costorm_runner.py`) shares the same SandboxSearchRM but additionally replaces `knowledge_storm`'s LiteLLM-based `Encoder` with a local `SentenceTransformer` (`paraphrase-MiniLM-L6-v2`) because DeepSeek does not expose an embedding endpoint. STORM is on the headline leaderboard at rank 9; Co-STORM is integrated but under-scored.

A summary table of the 13 frameworks:

| Framework | Style | Glue | Venv | Runner file |
|---|---|---|---|---|
| camel-ai | single-loop ChatAgent | tavily monkey-patch + ds_proxy env | `.venv-camel` | `scripts/run_deep_task.py:345` |
| smolagents | ToolCallingAgent | tavily monkey-patch + ApiWebSearchTool | `.venv-smol` | `scripts/run_deep_task.py:288` |
| gpt-researcher | planner + parallel writers | subprocess driver, custom embedding alias | `.venv-gptr` | `scripts/runners/gpt_researcher_runner.py` |
| langchain-odr | langgraph supervisor + researcher + writer | tavily Sync+Async patch | `.venv-langchain-odr` | `scripts/run_deep_task.py:674` |
| ii-researcher | ReAct chain-of-search | subprocess + intercept preamble | `.venv-ii` | `scripts/run_deep_task.py:1098` |
| dzhng | Node HTTP API | localhost:3051 POST | Node + `.venv-camel` | `scripts/run_deep_task.py:1238` |
| flowsearcher-ds | memory-guided planner | in-process, our agent | `.venv-camel` | `scripts/run_flowsearcher.py` |
| deerflow | langgraph multi-agent | conf.yaml + env-var LLM, Jina swap | `third_party/deer-flow-v1/.venv` | `scripts/runners/deerflow_runner.py` |
| ldr | programmatic detailed_research | settings_snapshot + masking | `.venv-ldr312` | `scripts/runners/ldr_runner.py` |
| qx-agents | openai-agents SDK | SearchXNG → Serper adapter | `.venv-qx` | `scripts/runners/qx_runner.py` |
| tongyi-dr | qwen_agent ReAct loop | LLM redirect to ds_proxy, tools rewritten | `.venv-tongyi` | `scripts/runners/tongyi_runner.py` |
| deepagents | langgraph super-agent | custom search tool + init_chat_model | `.venv-camel` or `.venv-deepagents` | `scripts/runners/deepagents_runner.py` |
| storm + co-storm | knowledge_storm pipeline | SandboxSearchRM + bibliography merge | `.venv-storm` | `scripts/runners/{storm,costorm}_runner.py` |

The common-thread integration patterns are: (a) point Tavily at the shim, (b) point OpenAI client at the ds_proxy, (c) intercept any `en.wikipedia.org` or `api.tavily.com` URLs that leak through despite (a), and (d) for case-sensitive corpora, do not normalise the URL path.

---

## 8. Scoring Pillars

Each agent report is scored on seven pillars. The first three are deterministic truthfulness probes (URL coverage, URL reachability, quote match). The next three are LLM-judged rubrics with deterministic guards (checklist, citation alignment, presentation). The seventh (analysis depth) combines structural and LLM-judged criteria. Composite v1 and v2 use only the first four; v3 uses all seven plus presentation and analysis depth.

### 8.1 URL coverage (`src/verifiers/url_coverage_verifier.py`)

URL coverage measures whether the agent cited the URLs it should have. It has three sub-scores:

- **`must_cite_recall`** = $\frac{\sum_{u \in \text{cited} \cap \text{must}} w_u}{\sum_{u \in \text{must}} w_u}$
- **`pool_coverage`** = $\frac{|\text{cited} \cap \text{expected\_pool}|}{|\text{expected\_pool}|}$
- **`domain_balance`** = $\min_{d}\left(\min\left(1, \frac{\text{cited}_d}{\text{min}_d}\right)\right)$ across domains $d \in \{\text{shopping}, \text{reddit}, \text{wikipedia}\}$

The score is the weighted sum (defaults: 0.55 must-cite, 0.15 pool, 0.30 domain), and the pillar passes if must-cite recall $\geq 0.45$, pool coverage $\geq 0.12$, domain balance $\geq 0.80$, and total unique cited URLs $\geq 60$ (`src/verifiers/url_coverage_verifier.py:166-186`). Why all three terms: must-cite alone rewards agents that find the exact frozen pool but penalises agents that find equally good alternative pages; pool coverage compensates; domain balance is the only signal that an agent over-cited one corpus and dropped another. URLs are canonicalised before comparison (trailing slash stripped, host lower-cased, fragment dropped, query-string ordering sorted) via `canonicalize_url` in `src/verifiers/citation_format.py`. The 4xx-vs-5xx split is left to the reachability pillar.

### 8.2 URL reachability (`src/verifiers/url_reachability_verifier.py`)

Reachability is the single strongest signal against URL fabrication. The verifier extracts every cited URL from the markdown, filters to sandbox host:port pairs (strict equality, not substring, to avoid `localhost:7770` matching `localhost:77703`), GETs each with a 6-second timeout and three retries with exponential back-off, and counts 200 responses (`src/verifiers/url_reachability_verifier.py:55-82`). The score is

$$\text{reachability} = \frac{|\{u : \text{status}(u) = 200\}|}{|\{u : \text{status}(u) \neq 5\text{xx} \land \text{status}(u) \neq \text{net\_fail}\}|}$$

The denominator is *resolvable* probes (not total), so a 30% rate of 5xx or network failure does not get counted as the agent fabricating URLs; instead the verifier sets `infra_failure=True` when *every* probe returned 5xx or net-fail, and `infra_warning=True` when at least 30% did. This split is what lets the leaderboard distinguish "agent invented URLs" (high 4xx) from "sandbox was down for this run" (high 5xx) (`src/verifiers/url_reachability_verifier.py:131-156`). The pillar passes if rate $\geq 0.30$.

### 8.3 Quote match (`src/verifiers/quote_match_verifier.py`)

Quote match catches misattribution: the URL exists but the page does not actually contain anything supporting the surrounding claim. The verifier extracts `(url, claim_context)` pairs from the markdown (the claim context is a 200-character window around the citation site, with markdown link syntax replaced by the visible label), fetches every unique URL via the same retry-and-backoff `_fetch` helper, and computes a token-overlap ratio between the claim tokens and the page tokens. The pair "passes" if

$$\text{overlap} = \frac{|\text{tokens}(\text{claim}) \cap \text{tokens}(\text{page})|}{|\text{tokens}(\text{claim})|} \geq \theta$$

with $\theta = 0.10$ (`src/verifiers/quote_match_verifier.py:91-95`). The score is the fraction of pairs that pass. The verifier uses a stop-word filter on the claim tokens to keep "the of and" from inflating the denominator. This is the cheapest pillar by design: no LLM call, no NLI judgement, just BM25-style overlap.

### 8.4 Claim NLI (`src/verifiers/claim_nli_verifier.py`)

Claim NLI is the heavyweight version of quote match: for each `(claim_context, cited_url)` pair whose URL has a `quoted_span` in the golden, the verifier asks DeepSeek V4-flash via the ds_proxy:

> "CLAIM: ... SOURCE_QUOTE: ... Does the source quote DIRECTLY support the claim? Output JSON {entail, prob, reason}."

Probabilities at temperature 0 are calibrated such that the verifier considers a claim entailed when `prob >= 0.80` (default $\theta$ per ReClaim, `Gao et al., 2024`). The score is the fraction of evaluated claims above threshold, capped at `max_calls=80` per report to bound cost. As of the 2026-04-27 review, claim_nli is dropped from the headline `composite_v2` (the multiplier is set to 1.0) because the DeepSeek-V4-flash NLI judge produced too many false negatives on visually-noisy product pages. The pillar is still computed and persisted for transparency; the run-time per agent×task ranges from 30 to 120 seconds.

### 8.5 Checklist (`src/verifiers/checklist_verifier.py` and `scripts/score_deep_answer.py:96-193`)

The checklist is a 21-item task-specific binary rubric. The items are written by hand once per task (`data/tasks/deep_research/cross_site_deep/checklists_deep.json`). The judge is DeepSeek V4-flash via the ds_proxy at temperature zero; the system prompt instructs the judge to output PASS/FAIL/UNCLEAR per line in order. Three deterministic guards wrap the judge:

1. **Degenerate-answer guard** (`scripts/score_deep_answer.py:111-123`): if the answer is empty or under 50 words and lacks citations, every item is FAIL without an LLM call. This catches the case where the runner emitted "(qx-agents error: ValidationError ...)" and the judge would otherwise return 21 PASSes anyway.
2. **All-PASS short-answer guard** (`scripts/score_deep_answer.py:165-170`): if the judge returns PASS on every item and the answer is under 500 words, every verdict is downgraded to FAIL. This catches DeepSeek V4-flash's documented lenient-mode bug on short prompts.
3. **Grounding cross-check** (`scripts/score_deep_answer.py:174-180`): if URL reachability is below 0.30, any PASS verdict on an item containing grounding keywords ("URL", "cited", "linked", "sandbox", "domain", "reddit", "wikipedia", "shopping", "thread", "article", "page", "forum") is downgraded to FAIL. This is what stopped gpt-researcher from getting 21/21 PASS verdicts on reports that cited 93 fabricated URLs (task 0009 audit).

The score is `pass_count / 21`.

### 8.6 Citation alignment (`src/verifiers/citation_alignment_verifier.py`)

Citation alignment is the ALCE-style per-citation NLI probe. For each `(sentence, cited_url)` pair, the verifier fetches the cited page, strips HTML (`script`, `style`, `nav`, `footer`, `header`, `noscript`, `aside`, `svg` removed; tags stripped; whitespace collapsed), truncates to 8000 chars, and asks the judge:

> "Does the page SUPPORT the claim?" with output "VERDICT: SUPPORTED" or "VERDICT: NOT_SUPPORTED"

Then it computes:

- **precision** = $\frac{\text{supported pairs}}{\text{total pairs}}$
- **recall** = $\frac{\text{sentences with at least one supported cite}}{\text{sentences with any cite}}$

The score is precision (`src/verifiers/citation_alignment_verifier.py:321`). Caps: 200 pairs per report, 8000 chars per page body, 4-worker thread pool for fetches, single judge call per pair at `max_tokens=80`. The verifier handles both `[label](url)` and bare `https://...` citation forms (the bare-URL case is what breaks for `ldr` and was the reason quote_match used to return `claims_total=0` on those runs).

### 8.7 Analysis depth and presentation (`analysis_depth_verifier.py`, `presentation_verifier.py`)

These two pillars score how well the report reads as a research deliverable, not how well it cites. Both are two-tier hybrids of deterministic structural checks and an LLM-judge rubric.

**Analysis depth (10 criteria, 4 deterministic + 6 LLM, score = 0.3·tier_a + 0.7·tier_b):**

- Tier A: at least one paragraph references URLs from ≥ 2 domains; ≥ 3 paragraphs use contradiction language; ≥ 3 paragraphs are backed by ≥ 3 URLs from ≥ 2 domains; comparative-language density ≥ 0.15.
- Tier B: beyond-enumeration, causal reasoning, source triangulation, novel insight, counterargument awareness, actionable conclusion.

The contradiction and comparative language regexes are at `src/verifiers/analysis_depth_verifier.py:38-52`; the domain extraction uses `host:port` when host is localhost so the three sandbox corpora don't collapse to one domain.

**Presentation (12 criteria, 6 deterministic + 6 LLM, score = 0.4·tier_a + 0.6·tier_b):**

- Tier A: heading hierarchy ≥ 3 levels; ≥ 5 h2 sections; section-balance CV < 1.5; at least one list or table; no orphan blocks > 200 words without a heading above; Flesch Reading Ease ≥ 30.
- Tier B: logical flow, transition quality, no meta-filler, consistent formatting, conclusion synthesises, professional tone.

The tier B prompt sends head + tail of long reports rather than head-only, because `conclusion_synthesizes` and `consistent_formatting` need to see the end of the report (`src/verifiers/presentation_verifier.py:217-223`).

These two pillars are scored on every run and persisted in the `.score.json` files, but they contribute only via `composite_v3`. The headline `composite_v2` deliberately excludes them: a benchmark that puts "professional tone" on the same axis as "URL reachability" makes the truth-gate inversion impossible to see.

A summary of the seven pillars:

| Pillar | Range | Type | Cost | In composite |
|---|---|---|---|---|
| url_coverage | [0, 1] | deterministic | ms | v1, v2, v3 |
| url_reachability | [0, 1] | HTTP probe | seconds | v1, v2 (gate), v3 (floored gate) |
| quote_match | [0, 1] | deterministic | seconds | v3, optional v2 |
| claim_nli | [0, 1] | LLM judge | minutes | dropped from v2 headline |
| checklist | [0, 1] | LLM judge + guards | seconds | v1, v2, v3 |
| citation_alignment | [0, 1] | LLM judge per pair | minutes | v3 |
| presentation | [0, 1] | deterministic + judge | seconds | v3 |
| analysis_depth | [0, 1] | deterministic + judge | seconds | v3 |

---

## 9. Composite Scoring Formulas

Three composites coexist (`src/scoring/leaderboard_composites.py`). All three share a common `quality` term and differ only in how reachability gates it.

The quality term is
$$Q = 0.40 \cdot \text{url\_coverage} + 0.40 \cdot \text{checklist} + 0.20 \cdot \text{spec}$$
where `spec` is the fraction of markdown-spec flags satisfied (`words_ok`, `citations_ok`, `paragraphs_ok`; see `spec_pass_fraction` at `src/scoring/leaderboard_composites.py:28-35`).

**Composite v1 (legacy additive).** Reachability is folded into the quality input rather than acting as a gate.
$$\text{composite}_{v1} = Q$$
(`composite_v1` at `src/scoring/leaderboard_composites.py:60-68`). This is the "no truthfulness gate" baseline. Used in the leaderboard only to demonstrate that the rank order inverts under v2.

**Composite v2 truthful (multiplicative, headline).** Reachability is a multiplicative gate.
$$\text{composite}_{v2} = \text{reachability} \cdot Q$$
(`composite_v2_truthful` at `src/scoring/leaderboard_composites.py:71-81`). If reachability = 0, composite = 0. This is the headline ranking. An optional truthfulness-factored variant
$$\text{composite}_{v2,\text{factored}} = \text{reach} \cdot (0.5 + 0.5 \cdot qm) \cdot (0.5 + 0.5 \cdot nli) \cdot Q$$
is still computed by `score_deep_answer.py:233-243` and persisted, but the headline number is the plain multiplicative form because (a) `claim_nli` was dropped from the headline per the 2026-04-27 review, (b) the leaderboard builder reads `composite_v2_truthful` specifically, not the per-run factored version.

**Composite v3 (relaxed reach floor, 7-pillar).** Reachability is a floored gate, and four more pillars contribute to the quality raw score.
$$\text{composite}_{v3} = \max(0.1, \text{reach}) \cdot \big( 0.20 \cdot \text{url\_cov} + 0.20 \cdot qm + 0.20 \cdot \text{checklist} + 0.10 \cdot \text{spec} + 0.15 \cdot \text{cit\_align} + 0.10 \cdot \text{depth} + 0.05 \cdot \text{pres} \big)$$
(`composite_v3` at `src/scoring/leaderboard_composites.py:107-127`; same formula in `scripts/score_deep_answer.py:249-260`). The floor 0.1 keeps fabrication-only agents from getting literally zero, which makes v3 a softer ranking signal than v2. v3 is computed per run and persisted, but the headline leaderboard uses v2.

Why v2 is the headline. The multiplicative gate is the simplest possible expression of "fabrication is non-negotiable". An agent that gets reachability = 0 has produced no usable evidence; rewarding it 0.1× quality (as v3 does) understates how bad that report is in practice. The hard zero on v2 is the formula that surfaces finding 13.1 (truth-gate inversion). v3 exists for two reasons: (a) it lets the per-pillar analysis show that even with the four extra rubrics included, the truthfulness-gate clusters survive, and (b) it lets the audit page rank agents that score zero on v2 but produce non-trivial reports, so they don't disappear silently. The leaderboard headline is `composite_v2_truthful`; v1 is shown side-by-side for the reversal demonstration; v3 is shown in per-run audit detail but does not drive Elo.

---

## 10. Ranking: Bradley-Terry Elo, Bootstrap CIs, Permutation Significance

The ranking aggregates 227 per-task pairwise battles per agent (136 for storm, which scored 17 tasks out of the 30 it attempted). Battles are synthesised from `composite_v2`: for each task, for every pair of agents that both produced a non-degenerate score, the agent with the higher composite "wins" the battle and the loser "loses". If $|\Delta\text{composite}| < 0.005$ the battle is a "draw" (`scripts/build_deep_leaderboard.py:241-244` and `src/scoring/arena.py:33-39`). The tie-epsilon is tight on purpose: under v2, many agents collapse to composite = 0 (reach gate kills them), and a loose epsilon would let those agents draw with each other instead of being decided by the order battles are processed.

The Elo model is the same one Chatbot Arena uses (`Chiang et al., 2024`). For each battle $(a, b)$ with observed outcome $s_a \in \{0, 0.5, 1\}$:

$$E_a = \frac{1}{1 + 10^{(R_b - R_a)/400}}, \qquad R_a' = R_a + K (s_a - E_a)$$

The K-factor is 32, the start rating is 1000, and the algorithm runs 20 passes with shuffled battle order, averaging the final ratings across passes (`src/scoring/arena.py:84-120`). The multi-pass averaging is what removes the order-of-battles sensitivity that a single Elo pass exhibits on small datasets.

The 95% confidence interval is a non-parametric bootstrap (`compute_elo_with_ci`): resample the battles with replacement 1000 times, fit Elo each time, take the 2.5th and 97.5th percentiles. The headline ranking has CI widths of ±43 to ±96 Elo points; the smaller numbers (storm at ±43) are agents that participated in fewer battles.

The pairwise permutation significance test (`rank_significance_test`, N = 1000 permutations) shuffles the battle outcomes within each adjacent rank pair and asks: under the null hypothesis that the two agents are equally strong, how often would we observe an Elo gap at least as large as the one we did? The result is in the published leaderboard:

| Adjacent pair | Gap (Elo) | p-value | Significant at α=0.05 |
|---|---:|---:|---|
| camel-ai > flowsearcher-ds | 79.4 | 0.305 | no |
| flowsearcher-ds > smolagents | 94.1 | 0.447 | no |
| smolagents > ldr | 362.0 | 0.000 | yes |
| ldr > gpt-researcher | 79.3 | 0.326 | no |
| gpt-researcher > deerflow | 44.1 | 0.573 | no |
| deerflow > ii-researcher | 90.2 | 0.310 | no |
| ii-researcher > langchain-odr | 2.7 | 0.970 | no |
| langchain-odr > storm | 10.6 | 0.896 | no |

Only one gap is significant: the 362-Elo cliff between smolagents (rank 3) and ldr (rank 4). The top three are a statistically-tied front cluster; the bottom six are a statistically-tied tail. This is the right way to read the leaderboard: there are two clusters separated by one wide gap, not nine ordered tiers.

Why Bradley-Terry beats raw mean composite. Two reasons. First, per-task baseline difficulty varies wildly (composite_v2 means range from 0.000 on hard recommendation tasks to 0.664 on simpler enumeration tasks; see the per-(agent, task) raw table for variability). A raw-mean comparison is dominated by which tasks each agent ran. Bradley-Terry only compares agents on tasks they both ran, cancelling per-task baseline difficulty automatically. Second, the multiplicative gate produces a long tail of zeros. Mean-over-zeros is a discontinuous statistic with low resolving power; pairwise wins are continuous in the underlying probability and have better small-sample behaviour. The smolagents > ldr cliff is detected because smolagents wins almost every head-to-head pairing across the 30 tasks they share, not because smolagents has a higher mean.

---

## 11. Degenerate-Run Filter

Including degenerate runs in the Bradley-Terry battles distorts the rating. A runner-error placeholder like `"(qx-agents error: ValidationError ...)"` is a string from which the scorer happily extracts no URLs and the LLM judge happily emits PASS or FAIL verdicts on a near-empty answer. The resulting composite ($\approx 0.02$) is then either a win against any agent that scored 0 (sandbox-failure runs) or a loss against any agent that scored normally. Either way it is not a real signal about the agent's capability. The filter drops these before Bradley-Terry runs (`scripts/build_deep_leaderboard.py:82-131`).

Four patterns are dropped:

1. **Short-answer + no signal.** `answer_chars < 600` AND `url_reachability.score == 0` AND `checklist.pass_rate == 0`. Empty or near-empty reports with no measurable substance.
2. **Sandbox infrastructure failure.** `url_reachability.details.infra_failure == True`. Every probe returned 5xx or net-fail. This means the sandbox was down during scoring, not that the agent fabricated URLs.
3. **Judge total-failure.** `checklist.judge_error AND analysis_depth.judge_error AND presentation.judge_error`. All three LLM-judged pillars errored out (typically a ds_proxy timeout); the run has no judge signal.
4. **Runner-failure / runner-exception placeholders.** The answer markdown starts with `"(<Agent> produced no report after Ns, exit=N)"` (`_RUNNER_FAILURE_PREFIX_RE` at `scripts/build_deep_leaderboard.py:64-67`) or `"(<Agent> error: ...)"` / `"(<Agent> stderr: ...)"` (`_RUNNER_EXCEPTION_PREFIX_RE` at `scripts/build_deep_leaderboard.py:76-79`). These pass the short-answer filter when the stdout tail is long but the agent crashed.

The published filter outcomes in the leaderboard are:

| Agent | Files on disk | Kept | Dropped | Status |
|---|---:|---:|---:|---|
| qx-agents | 30 | 0 | 30 | excluded, every run filtered |
| flowsearcher-ds | 48 | 30 | 18 | partial, some runs dropped |
| storm | 30 | 17 | 13 | partial, some runs dropped |

The audit row in the leaderboard exists precisely so that an excluded framework does not silently vanish. A reader who does not see qx-agents in the Elo table and does not see the audit row would assume qx-agents was never benchmarked; the audit row says "tried, all 30 runs crashed, framework-incompatible".

---

## 12. Results

The headline ranking (`composite_v2_truthful`, 56 tasks, DeepSeek V4-flash backbone):

| Rank | Agent | Elo | 95% CI | W | L | D | Battles |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | camel-ai | **1480.6** | [1405, 1567] ±81 | 206 | 20 | 1 | 227 |
| 2 | flowsearcher-ds | **1401.2** | [1324, 1486] ±81 | 193 | 32 | 2 | 227 |
| 3 | smolagents | **1307.1** | [1211, 1404] ±96 | 170 | 42 | 15 | 227 |
| 4 | ldr | **945.1** | [871, 1014] ±72 | 80 | 100 | 47 | 227 |
| 5 | gpt-researcher | **865.8** | [793, 941] ±74 | 60 | 114 | 53 | 227 |
| 6 | deerflow | **821.7** | [756, 903] ±74 | 40 | 118 | 69 | 227 |
| 7 | ii-researcher | **731.5** | [676, 776] ±50 | 5 | 130 | 92 | 227 |
| 8 | langchain-odr | **728.8** | [674, 781] ±53 | 6 | 129 | 92 | 227 |
| 9 | storm | **718.2** | [677, 763] ±43 | 0 | 75 | 61 | 136 |

Three clusters fall out clearly.

**Top cluster (camel-ai, flowsearcher-ds, smolagents).** These three agents understand that a citation is a contract. Their reports cite URLs that resolve, the pages contain content related to the surrounding claim, and the citations span all three corpora. camel-ai (Elo 1481, 206 wins, 20 losses, 1 draw across 227 battles) wins because it has explicit per-source URL discipline (`scripts/run_deep_task.py:376-389`) and an explicit instruction to cite at least 15 Wikipedia articles, which is what stops the agent from dropping the wiki corpus. flowsearcher-ds (Elo 1401) has lower mean composite (0.296) than camel-ai (0.410) but tighter tails: the memory-guided planner avoids the runs where camel-ai occasionally crashes to 0 due to a CoT-prefix parse failure. smolagents (Elo 1307) sits at the bottom of the top cluster because its tool-call agent is structurally simple and DeepSeek V4-flash sometimes fails to fill the structured search-tool slot, dropping the report to composite 0.026 on some recommendation tasks. The top-three permutation gaps (79 and 94 Elo points) are *not* statistically significant (p = 0.31 and 0.45). For practical purposes the top three are tied.

**Middle cluster (ldr, gpt-researcher, deerflow).** Each fails on truthfulness in a different way. ldr (Elo 945, mean composite 0.029) lower-cases Kiwix paths; the Wikipedia corpus is case-sensitive on article names, so wiki-domain reachability is near zero. gpt-researcher (Elo 866, mean composite 0.013) templates Magento product URLs from name slugs the model invents; the real Magento slugs include numeric suffixes the agent never sees, so shopping reachability is ~0. deerflow (Elo 822, mean composite 0.023) truncates its citation tables: the langgraph writer emits a markdown report with the per-paragraph citations stripped from sections after a certain length, so even though search returned correct URLs, the final report only cites a handful (visible in deerflow per-task scores: the agent has 30 partial runs with composite ranging 0.000 to 0.186). The middle is a graveyard of agents that almost worked.

**Bottom cluster (ii-researcher, langchain-odr, storm).** ii-researcher (Elo 732, mean composite 0.001) terminates its chain-of-search after three to five tool-call turns and ships with a handful of citations. langchain-odr (Elo 729, mean composite 0.001) fabricates external URLs whenever its retrieval cache misses (Wikipedia URLs that point at real `en.wikipedia.org`, Reddit URLs to real `reddit.com`); the HTTP intercept catches some, but the report still ends up with external URLs that the reachability probe rejects. storm (Elo 718) under-cites because of the bibliography bug described in section 13.4; post-fix re-runs show composite 0.067 instead of 0.000.

**Per-pillar Elo** (`render_per_pillar_table` output in `LEADERBOARD_DEEP.md`):

| Agent | checklist | quote | reach | spec | url_cov |
|---|---:|---:|---:|---:|---:|
| camel-ai | 1170 | 1486 | 1287 | 1268 | 1182 |
| flowsearcher-ds | 1147 | 1398 | 1256 | 1269 | 1141 |
| smolagents | 1088 | 1317 | 1236 | 1003 | 1146 |
| ldr | 614 | 789 | 1215 | 644 | 908 |
| gpt-researcher | 1152 | 798 | 883 | 1238 | 1305 |
| deerflow | 943 | 824 | 860 | 1057 | 820 |
| ii-researcher | 970 | 805 | 752 | 772 | 816 |
| langchain-odr | 1024 | 788 | 766 | 1098 | 932 |
| storm | 893 | 795 | 745 | 652 | 750 |

The per-pillar table is the clearest single artefact in the benchmark. Notice that gpt-researcher has the highest url_coverage Elo (1305: it does emit many URLs that look like Magento URLs and a few of them are golden URLs by chance), the second-highest checklist Elo (1152: the LLM-judge thinks the report reads well), and yet the third-lowest reachability Elo (883: the URLs don't resolve). The composite v2 gate is what stops this profile from ranking #1.

**Coverage notes.** The leaderboard is built from 283 score files. Four agents have partial coverage: deerflow, gpt-researcher, ii-researcher, langchain-odr, and smolagents all ran on tasks 0001-0030; camel-ai and flowsearcher-ds extended through 0057; storm has 17 kept rows on a scattered subset of tasks 0013-0030; qx-agents has zero kept rows. The Bradley-Terry model accommodates partial coverage natively (an agent is compared only on tasks it ran), but the CI widths and significance tests are correspondingly larger for partial-coverage agents.

---

## 13. Findings

### 13.1 Truth-gate inversion (the headline finding)

Running the same battle matrix with `composite_v1` (the additive form, no multiplicative reachability gate) produces a different leaderboard.

| Agent | v2 Elo | v2 rank | v1 Elo | v1 rank | Move |
|---|---:|---:|---:|---:|:---|
| gpt-researcher | 866 | 5 | 1269 | 1 | +4 |
| flowsearcher-ds | 1401 | 2 | 1253 | 2 | 0 |
| camel-ai | 1481 | 1 | 1232 | 3 | −2 |
| smolagents | 1307 | 3 | 1088 | 4 | −1 |
| langchain-odr | 729 | 8 | 1005 | 5 | +3 |
| deerflow | 822 | 6 | 933 | 6 | 0 |
| ii-researcher | 732 | 7 | 898 | 7 | 0 |
| storm | 718 | 9 | 801 | 8 | +1 |
| ldr | 945 | 4 | 520 | 9 | −5 |

Three agents move by three or more ranks. gpt-researcher jumps from 5th to 1st: its prose is fluent, its checklist score is high, its url_coverage is the highest of all nine agents, and once you stop multiplying by reachability its quality term is the largest in the field. langchain-odr jumps from 8th to 5th: it emits long, well-structured reports that pass checklist and spec, just with external URLs. ldr falls from 4th to 9th: under the gate it was rescued by reachability (per-pillar reach Elo 1215, higher than gpt-researcher), without the gate it has nothing.

A concrete agent that scores high on presentation but low on reachability: gpt-researcher on `dr_cross_deep_0009`. The report is 6,200 words, passes 19 of 21 checklist items, scores 0.78 on presentation, and cites 93 URLs. Of those 93, fewer than 10 return HTTP 200 from the sandbox. The composite v1 for that run is 0.387; the composite v2 is 0.000. The audit page (`/audit`) flags this as the canonical "fluent fabrication" failure mode.

The strongest argument for the gated formula is that a DR agent that reads beautifully and fabricates URLs is *worse* than one that writes a clunky report and cites real pages, because the fluent fabrication is more likely to be believed downstream. The truth gate makes this directly visible.

### 13.2 Multi-agent harnesses beat single-loop on this sandbox

Of the top three frameworks, two are multi-agent harnesses (camel-ai's ChatAgent + SearchToolkit, flowsearcher-ds's memory-guided planner + executor) and one is a constrained tool-call loop (smolagents's ToolCallingAgent with `max_steps=60`). Two of the bottom six are single-loop or sequential pipelines that do not decompose (`ii-researcher`'s ReAct loop terminates after 3-5 turns; `gpt-researcher`'s sequence is planner → many writers → final assemble but each writer is single-shot). The trend is consistent with the hypothesis that DeepSeek V4-flash, as a non-reasoning backbone, benefits from external decomposition: when the framework breaks the task into sub-queries and orchestrates them, the model fills each sub-slot well; when the framework asks the model to do the decomposition implicitly in one prompt, the output truncates or drifts.

This is a sandbox-bounded finding. The 120-citation floor is what forces decomposition: a single forward pass through DeepSeek V4-flash will not produce 60 cross-source citations from one search round, and any framework that does not retry in multiple search rounds is structurally capped below the citation floor. With a reasoning-capable backbone (DeepSeek V4 with thinking on, or GPT-5 with reasoning), the gap between multi-agent and single-loop would narrow, because the model would do more of the planning itself. The multi-LLM extension page (`/compare`) is the planned validation.

### 13.3 Public sentiment vs measured rank

gpt-researcher has 25.7k GitHub stars at the time of writing and is the de facto reference implementation of the term "deep research" in open-source. It ranks 5th on this benchmark, behind a framework most readers have not heard of (flowsearcher-ds, in-house) and a generic agent loop (smolagents, not DR-specific). The discrepancy has three contributors.

First, popularity selects for *product-grade implementation*, not for measured-quality on a fixed eval. gpt-researcher is well-engineered for the live web: its prompt is tuned to real Google/Tavily, its retrieval pipeline assumes real CDN-served HTML, and its reporter expects real-world URL patterns. On a Magento sandbox with deterministic slugs that the model cannot template, that engineering does not transfer.

Second, popularity selects for *prose quality*. Most users evaluate a DR agent by reading the report, not by clicking 93 URLs to see whether they 200. gpt-researcher's reports read well, and a community of users that grades on prose is doing the same thing `composite_v1` does. `composite_v2` is what surfaces the difference.

Third, popularity selects for *easy setup*. gpt-researcher's one-liner setup is a real engineering achievement; smolagents, by contrast, is a generic tool-call loop with no DR-specific marketing. Easy setup and measured-quality are weakly correlated.

The lesson for the field is not that gpt-researcher is bad. It is that *community-favourite* and *measured-quality on a sealed sandbox* are different axes, and that the benchmark exists to be the second axis.

### 13.4 Failure modes (per-framework)

Four specific bugs caught and partially fixed during the benchmark:

- **qx-agents framework incompatibility.** Under DeepSeek V4-flash, the openai-agents SDK raises `pydantic.ValidationError: 2 validation errors for KnowledgeGapOutput` and downstream `IndexError: list index out of range` on every task. Not our bug to fix. qx-agents was excluded from Elo with a public audit-row note. All 30 score files were filtered by `_looks_degenerate` via the `_RUNNER_EXCEPTION_PREFIX_RE` pattern at `scripts/build_deep_leaderboard.py:76-79`.

- **storm bibliography fix.** The storm runner read storm's polished article body but never merged the separate `url_to_info.json` URL table back into the markdown. The agent had cited correctly internally; we were scoring a citation-stripped version. After fixing `scripts/runners/storm_runner.py:299-313` to append a reconstructed `## References` section, storm went from `composite_v2 = 0.000` on every run to roughly 0.067 on the small post-fix re-run set. This is the single largest bug-fix delta in the benchmark.

- **Kiwix URL alias bug.** The golden pool stored Wikipedia URLs in one canonical form (`localhost:8090/.../A/Page_Name`); some agents emit a Kiwix prefix variant (`/viewer#wikipedia/A/Page_Name`). The URL canonicaliser (`canonicalize_url` in `src/verifiers/citation_format.py`) was patched to collapse the alias variants. 64 score files were re-scored after the fix, three historical pairs unblocked.

- **dzhng API-key plumbing.** The Node side of dzhng reads `OPENAI_API_KEY` from its own `.env`, not from the parent shell. Setting the key only in the bash environment that launched the Node process did not propagate. Fix: set the key in `third_party/deep-research/.env` directly.

Two infrastructure issues caught:

- **GPU loss mid-run.** The RTX 5090 on the eval host went unresponsive (`nvidia-smi: GPU is lost`) partway through. The benchmark migrated from local Qwen3.5-27b on LM Studio to the DeepSeek API in parallel, resumed the bulk run with no data loss.
- **DeepSeek API HTTP 402 (balance).** The DeepSeek API returned HTTP 402 on a small fraction of later runs because the prepaid balance hit zero. The user topped up and the run continued. The leaderboard builder's degenerate-filter caught the runs that completed before the top-up as `judge_error`-trifecta drops, so they did not pollute Elo.

---

## 14. Web App and Reproducibility

The web app (`web/server.py`, FastAPI + Jinja2) reads the leaderboard files live from disk on every request, no database. The page map:

| Path | Purpose |
|---|---|
| `/` | Live leaderboard with per-agent drill-down |
| `/about` | One-paragraph project description + links |
| `/compare` | Agent × LLM matrix (placeholder for the multi-LLM extension) |
| `/how-it-works` | Plain-English explanation of pillars + Bradley-Terry |
| `/contribute` | Path for a new framework: write a runner module, drop a venv, get listed |
| `/audit` | Excluded runs, degenerate-filter audit trail |
| `/task/<id>` | Per-task explorer: full intent, per-agent ranking for that task |
| `/api/agent/<name>` | JSON: pillar scores, best/worst tasks per agent |
| `/api/leaderboard.json` | JSON mirror of `data/results/deep_v3/leaderboard_deep.json` |

The "live from disk" pattern (`web/server.py:59-70`) is the central simplification: when the bulk runner writes a new `<agent>__<task>_matrix.score.json`, the next call to `/api/leaderboard.json` after the next `build_deep_leaderboard.py` pass picks it up automatically. No invalidation logic, no Redis, no background refresh. This is enough for a small benchmark where the leaderboard refreshes on the order of minutes.

**Reproducing one agent × task end to end:**

```bash
ssh westd
wsl -d Ubuntu
cd /opt/deep_reserch

# Ensure shim + ds_proxy + sandbox dockers are running (see CLAUDE.md).
docker ps --filter name=kiwix --filter name=webarena_reddit --filter name=webarena_shopping
schtasks /Query /TN "DsProxy"
schtasks /Query /TN "ShimDaemon"

# Run camel-ai on dr_cross_deep_0001
.venv-camel/bin/python3 scripts/run_deep_task.py \
    --agent camel-ai --task dr_cross_deep_0001 \
    --backbone deepseek-v4-flash --out-suffix matrix

# Score the produced markdown
.venv-camel/bin/python3 scripts/score_deep_answer.py \
    --task dr_cross_deep_0001 \
    --answer data/results/deep/camel-ai__dr_cross_deep_0001_matrix.md \
    --out data/results/deep/camel-ai__dr_cross_deep_0001_matrix.score.json

# Rebuild the leaderboard
.venv-camel/bin/python3 scripts/build_deep_leaderboard.py
```

Bulk run: `bash scripts/parallel_bulk_launch.sh 6` launches six parallel runners across the agent × task grid, gated by `scripts/runners/_runner_lock.py` for frameworks that share global state (DeerFlow's `conf.yaml`, the driver script paths).

Every artefact a reviewer needs is on disk and version-controlled:

- Task specs: `data/tasks/deep_research/cross_site_deep/dr_cross_deep_XXXX.json`
- Golden pools: `data/golden/deep/dr_cross_deep_XXXX.json` (frozen)
- Checklists: `data/tasks/deep_research/cross_site_deep/checklists_deep.json`
- Reports: `data/results/deep/<agent>__<task>_matrix.md`
- Score files: `data/results/deep_v3/<agent>__<task>_matrix.score.json`
- Leaderboard: `data/results/deep_v3/LEADERBOARD_DEEP.md` and `leaderboard_deep.json`
- Audit: `data/results/audit/`

The scorer is deterministic given a task config, a markdown report, and a frozen golden pool: every LLM-judge call is `temperature: 0`, every HTTP probe retries with the same back-off, every URL is canonicalised identically. Re-running `build_deep_leaderboard.py` on the same score files produces identical Elo numbers; re-running `score_deep_answer.py` on the same markdown produces identical pillar scores up to DeepSeek's documented zero-temperature determinism.

---

## 15. Limitations

The benchmark is limited in five ways that the design makes explicit.

**Three corpora, not the web.** Magento + Postmill + Kiwix covers three vertical patterns (commerce, community, encyclopedia) but does not cover news, scholarly literature, primary documents, or anything behind a login wall. An agent that does very well at, say, financial-statement synthesis is not measured by this benchmark. The trade-off is intentional: a sandbox that covers the live web is the live web, and we are already specifying why that fails.

**One backbone in the headline run.** Every agent in the headline ranking runs on `deepseek-v4-flash` non-reasoning. Cross-architecture comparison would require the same agents on multiple backbones; the `/compare` page in the web app and the `ds_proxy` switching surface are designed for this, but the current numbers are single-backbone. The risk is that ranking with DeepSeek tells us which agent architecture is best *for DeepSeek*, not which architecture is best in general.

**LLM-as-judge bias.** Three of the seven pillars (checklist, citation alignment, the LLM half of presentation and analysis depth) call the same DeepSeek V4-flash judge. The deterministic guards (degenerate-answer skip, all-PASS-short-answer downgrade, grounding-keyword cross-check) catch the worst self-preference and lenient-mode failure modes, but the residual bias is non-zero. The 21-item checklist with PASS/FAIL/UNCLEAR per line is harder to game than a single Likert score (the DRACO-style construction), but a future iteration should swap in a different judge family (GPT-5, Claude) and measure agreement.

**Partial task coverage.** 57 of 100 designed tasks are scored end-to-end; the remaining 43 are designed and have task specs but no golden pool. The leaderboard Elo CIs would tighten from ±43-96 to roughly ±30-60 if all 100 ran.

**In-process runner venv collision.** Three of the in-process runners (camel-ai, smolagents, flowsearcher-ds, parts of deepagents) share `.venv-camel`. A dependency upgrade in one framework could mask a dep conflict in another. The subprocess runners avoid this by design (each in its own venv), but the in-process ones cannot. The pattern is a known limitation of in-process integration; a future cleanup would move every framework into its own venv via a clean runner.

A sixth, smaller limitation: the headline composite (`composite_v2`) drops `claim_nli` per the 2026-04-27 review because of NLI-judge reliability. The pillar is still computed and persisted, but the multiplier is 1.0 in the leaderboard. The principled fix is either a non-DeepSeek NLI judge or a manual calibration; both are future work.

---

## 16. Future Work

Four directions in order of priority.

**Multi-LLM compare matrix.** The most consequential next step. Same agents, same tasks, same scoring; swap the `ds_proxy` backend from DeepSeek V4-flash to GPT-5, Claude Opus 4.7, Gemini, Qwen3.5 (with reasoning on for one variant, off for another), and produce a 13 × 5 (agent × backbone) Elo grid. The page is already routed at `/compare`. The bottleneck is API budget; one full backbone pass is roughly 2,000 LLM calls × $0.005 (DeepSeek price), about $10, multiplied by five backbones at higher cost is on the order of $300 per full pass.

**More vertical sandboxes.** Adding a news corpus (Common Crawl slice) and a scholarly corpus (a frozen S2ORC slice) would let the benchmark say something about temporal reasoning and scholarly synthesis specifically. The shim's index interface is corpus-agnostic; only the search-index plug-in and the per-task golden builder would need new modules.

**Human-eval calibration.** Each LLM-judge pillar should be calibrated against a small human-judge dataset (50-100 reports per pillar). The current run already has a `data/results/audit/HUMAN_URL_AUDIT.md` for URL truthfulness (per-citation human grading on a 30-report sample); extending the same protocol to checklist, citation alignment, and presentation would give the LLM-judge an explicit error bar.

**Reasoning-mode comparisons.** DeepSeek V4 with thinking on, GPT-5 in extended thinking, Claude with reasoning, all produce different output patterns and should be compared explicitly. The truth-gate inversion finding is likely sharper on reasoning models, which are documented to fabricate more confidently.

**Longer-horizon tasks.** The current tasks are bounded at roughly 1800 seconds wall-clock per agent run. Tasks that require 4+ hours of search-fetch-rewrite cycles, with checkpointing, would test a different capability axis (long-horizon coherence) that the present benchmark cannot measure.

---

## 17. Reproducibility Appendix

**Sandbox bring-up on westd:**

```bash
ssh westd
wsl -d Ubuntu
cd /opt/deep_reserch

# Bring up the three docker corpora (Magento, Postmill, Kiwix)
docker compose -f infra/sandbox.docker-compose.yml up -d

# Verify ports
ss -tlnp | grep -E ':7770|:9999|:8090'

# Start the Tavily shim (Windows scheduled task: ShimDaemon)
schtasks /Run /TN "ShimDaemon"

# Start the DS proxy (Windows scheduled task: DsProxy)
schtasks /Run /TN "DsProxy"

# Verify both
curl -fsS http://localhost:8081/health
curl -fsS http://localhost:8088/v1/models
```

**Run one agent × task and score it:**

```bash
.venv-camel/bin/python3 scripts/run_deep_task.py \
    --agent camel-ai --task dr_cross_deep_0001 \
    --backbone deepseek-v4-flash --out-suffix matrix

.venv-camel/bin/python3 scripts/score_deep_answer.py \
    --task dr_cross_deep_0001 \
    --answer data/results/deep/camel-ai__dr_cross_deep_0001_matrix.md \
    --out data/results/deep/camel-ai__dr_cross_deep_0001_matrix.score.json
```

**Rebuild leaderboard:**

```bash
.venv-camel/bin/python3 scripts/build_deep_leaderboard.py
# reads data/results/deep_v3/*_matrix.score.json
# writes  data/results/deep_v3/LEADERBOARD_DEEP.md
# writes  data/results/deep_v3/leaderboard_deep.json
```

**Bulk run (six parallel workers):**

```bash
bash scripts/parallel_bulk_launch.sh 6
```

**Venv map** (every agent venv, its Python version, and the runner that uses it):

| Venv | Python | Used by |
|---|---|---|
| `.venv-camel` | 3.11 | camel-ai, flowsearcher-ds, scoring/judging, leaderboard build |
| `.venv-smol` | 3.11 | smolagents |
| `.venv-gptr` | 3.11 | gpt-researcher (subprocess via `scripts/runners/gpt_researcher_runner.py`) |
| `.venv-storm` | 3.11 | storm + co-storm (`scripts/runners/{storm,costorm}_runner.py`) |
| `.venv-langchain-odr` | 3.11 | langchain-open_deep_research (in-process; LangChain 1.x) |
| `.venv-ldr312` | 3.12 | ldr (`scripts/runners/ldr_runner.py`) |
| `.venv-lcdr` | 3.11 | langchain-ai/local-deep-researcher (`scripts/runners/local_deep_researcher_runner.py`) |
| `.venv-ii` | 3.11 | ii-researcher (subprocess) |
| `.venv-qx` | 3.11 | qx-agents (`scripts/runners/qx_runner.py`) |
| `.venv-tongyi` | 3.11 | Tongyi DeepResearch (`scripts/runners/tongyi_runner.py`) |
| `third_party/deer-flow-v1/.venv` | 3.12 | DeerFlow (`scripts/runners/deerflow_runner.py`) |
| Node `npm run api` in `third_party/deep-research/` | Node 20 | dzhng |

**Environment variables required for any agent run:**

```bash
DS_PROXY_URL=http://localhost:8088/v1
SHIM_URL=http://localhost:8081
OPENAI_API_KEY=anything
JUDGE_BASE_URL=http://localhost:8088/v1
JUDGE_MODEL=deepseek-v4-flash
SHOPPING=http://localhost:7770
REDDIT=http://localhost:9999
WIKIPEDIA=http://localhost:8090
TAVILY_API_KEY=tvly-shim-fake
```

The `OPENAI_API_KEY=anything` value is intentional: the ds_proxy uses its own server-side key and disregards the inbound key. Subprocess drivers (DeerFlow, gpt-researcher, ldr, ii-researcher) inherit the same env vars via `env=os.environ.copy()` plus the framework-specific extras (`BASIC_MODEL__*` for DeerFlow, `LDR_LLM_*` for ldr, etc.).

**Public artefacts (yibol9768-alt repo):**

- Repo: `https://github.com/yibol9768-alt/deep-research-arena`
- Live leaderboard (when the dev server is up on westd WSL): `http://172.30.52.43:8000/`
- Method page: `/how-it-works`
- Audit page: `/audit`
- Per-task pages: `/task/<task_id>`
- JSON API: `/api/leaderboard.json`, `/api/agent/<name>`

---

## 18. Glossary

**ALCE alignment.** A per-citation precision/recall metric introduced in `Gao et al., 2023`: for each `(claim, cited_url)` pair, does the cited page actually support the claim? Precision is supported pairs over total pairs; recall is sentences with at least one supported cite over sentences with any cite. Implemented in `src/verifiers/citation_alignment_verifier.py`.

**Bradley-Terry.** A model for pairwise comparison: given many pairwise outcomes between competitors, fit a single rating per competitor such that the probability of competitor A beating competitor B is $\sigma(R_A - R_B)$. The Elo update is one iterative algorithm that converges to the Bradley-Terry MLE on enough data. Implementation: `src/scoring/arena.py`.

**composite_v1.** Legacy additive composite: $Q$ = $0.40 \cdot \text{url\_cov} + 0.40 \cdot \text{checklist} + 0.20 \cdot \text{spec}$. No reachability gate. Used in the leaderboard only to demonstrate the truth-gate inversion.

**composite_v2.** Headline ranking. $\text{reach} \cdot Q$. The reachability gate is multiplicative: reach = 0 forces the composite to zero regardless of how well the report reads.

**composite_v3.** Seven-pillar relaxed composite. $\max(0.1, \text{reach}) \cdot \text{raw}$ where `raw` is a weighted sum of url_coverage, quote_match, checklist, spec, citation_alignment, analysis_depth, presentation. Used in per-run audit, not in the headline.

**Degenerate run.** A score row dropped by `_looks_degenerate` in `scripts/build_deep_leaderboard.py:82-131`. Four patterns: short-answer-no-signal, sandbox infra failure, judge total failure, runner-placeholder text. Excluded from Bradley-Terry battles to keep ratings clean.

**ds_proxy.** OpenAI-compatible HTTP service on `localhost:8088` (`integrations/ds_proxy/app.py`). Proxies every LLM call to DeepSeek V4-flash, injects `thinking: disabled`, holds the real API key server-side. Every agent and every LLM judge talks to the same proxy.

**Golden pool.** Per-task `data/golden/deep/dr_cross_deep_XXXX.json` file with `must_cite_urls` (the URLs the agent should hit), `expected_pool_urls` (the broader corpus a competent agent would find), and `triples` (subject-predicate-object plus `source_url` and `quoted_span` for NLI). Frozen, scraped once, never regenerated.

**must-cite.** A URL in the golden's `must_cite_urls` list with an associated weight. URL coverage's main term is must-cite recall, weighted by the per-URL weights.

**Permutation p-value.** The probability under the null hypothesis (the two agents are equally strong) of observing an Elo gap at least as large as the observed one. Estimated by shuffling battle outcomes within the adjacent rank pair 1000 times and counting how often the gap is matched or exceeded.

**Reachability gate.** The multiplicative reachability factor in `composite_v2`. Any URL the agent cites that does not return HTTP 200 from the sandbox pulls the reachability score down; reach=0 zeros the composite.

**Shim.** The Tavily-compatible search service on `localhost:8081` (`integrations/search_shim/app.py`). Every framework's Tavily client is pointed at this endpoint. The shim routes queries across the three sandbox indexes and returns Tavily-shape JSON.
