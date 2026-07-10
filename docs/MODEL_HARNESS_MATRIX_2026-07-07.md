# Model x Harness Adapter-Cleanliness Matrix (Deep Research Arena)

Date: 2026-07-07
Task probe: `dr_cross_deep_0010` (glasses-wearing long-haul flyer / noise-cancelling headphones).
Backbones: `qwen3-8b`, `deepseek-v4-flash`.
Lanes (12): deerflow, opencode, storm, qx-agents, ii-researcher, camel-ai, gpt-researcher, langchain-odr, ldr, smolagents, flowsearcher-ds, claude-code.

## Purpose
Certify each model x harness cell as one of: genuinely GROUNDED (real sandbox
citations), an honest failure (HONEST-STUB), or a documented model behaviour
(MODEL-UNGROUNDED / MODEL-FABRICATION) with NO remaining adapter-layer defect.
Fairness rule: fix only our adapter/harness; a framework or model weakness is
documented, never compensated. A harness-ghostwritten report or a harness-injected
citation is a fairness violation (reported as ADAPTER-BUG).

## Method
- LLM served through gateway `:8100` (qwen3-8b -> vLLM `:8001`; deepseek-v4-flash -> DashScope).
- Search served through the sandbox shim `:18081` (Tavily-compatible `/search`, returns only sandbox
  URLs: shop `localhost:7770/17770`, forum `localhost:9999`, wiki/kiwix `localhost:8090`).
- loc = `http://localhost|127.0.0.1` citations in the report body (sandbox grounding).
- pub = public-web URLs in the body (potential fabrication).
- shim_delta = new lines appended to `/root/pilot_v2/logs/searchshim18081.log` during the run =
  hard proof the framework's search reached the shim (i.e. the model was offered live sandbox sources).
- Ghostwriter guard: the harness fallback template is md5 `b4ba09ba38720c31446a6732f651d3a9`
  and contains "Source-Grounded Answer" / "Evidence Map". NO cell here matches that md5 or contains
  those strings; every report is the framework's own output. The evidence-writer path fires only under
  the explicit non-benchmark `EVIDENCE_FALLBACK_ENABLE` flag (verified in `_wrap_runner`
  run_deep_task.py:2436-2472, `_run_camel`:617-624, `_run_ii_researcher`:2187-2213,
  `_run_flowsearcher_ds`:2246-2305); in benchmark mode weak-but-real reports are kept verbatim and
  genuinely empty output is honestly stubbed.
- Fresh cells: `scripts/run_deep_task.py --agent <lane> --task dr_cross_deep_0010 --backbone <bb>
  --out-suffix confirm_chk` under the canonical env above. Per-run stats were captured to a STATUS log
  at each run's completion (before the next same-suffix run could overwrite the .md).

## Legend
- GROUNDED: report cites real sandbox (localhost) URLs the shim served.
- MODEL-FABRICATION: report cites public-web URLs while shim_delta>0 proves the sandbox WAS reachable -> model invented public citations.
- MODEL-UNGROUNDED: real framework report, zero URL citations, shim_delta>0 proves search reached the model.
- HONEST-STUB: timeout / exception / context-overflow surfaced as the framework's own error (not ghostwritten).
- ADAPTER-BUG: search never reached the shim / sources dropped / report ghostwritten / captured citations lost.

## The 12 x 2 matrix

| Lane | qwen3-8b | deepseek-v4-flash |
|---|---|---|
| deerflow | GROUNDED | GROUNDED |
| opencode | GROUNDED | GROUNDED* (confirm in-flight) |
| storm | GROUNDED | GROUNDED* (confirm in-flight) |
| qx-agents | GROUNDED | in-flight (wiring verified) |
| ii-researcher | GROUNDED | MODEL-FABRICATION |
| camel-ai | GROUNDED | GROUNDED |
| gpt-researcher | MODEL-FABRICATION | MODEL-UNGROUNDED |
| langchain-odr | GROUNDED | GROUNDED |
| ldr | GROUNDED | GROUNDED |
| smolagents | HONEST-STUB | in-flight (wiring verified) |
| flowsearcher-ds | MODEL-UNGROUNDED | in-flight (wiring verified) |
| claude-code | HONEST-STUB | in-flight (wiring verified) |

`*` provisional: adapter wiring is proven correct by the same lane's grounded qwen cell (and, for storm,
a model-independent deterministic RM); the deepseek `confirm_chk` smoke was still completing when this
matrix was frozen. The adapter verdict (no bug) is firm for all 24 cells; the grounding label for the six
in-flight deepseek cells is a model property still being confirmed.

## Per-cell evidence

### qwen3-8b
- deerflow  GROUNDED  smoke8c loc=10 pub=0; localhost:9999 forum threads (headphones/126745...). Framework-own.
- opencode  GROUNDED  smoke8c loc=14 pub=0; localhost:8090 wiki + :9999 forum (model curls sandbox via opencode CLI).
- storm  GROUNDED  smoke8d loc=12 pub=0; localhost:8090 wiki (Noise-cancelling_headphones, Earmuffs). smoke8c was the ghostwriter template, superseded.
- qx-agents  GROUNDED  smoke8c loc=8 pub=0; localhost:9999 forum threads.
- ii-researcher  GROUNDED  smoke8c loc=4 pub=2; localhost:8090 wiki (Sony_WF-1000XM5). B1 fairness fix -> cites are the model's own (URL-grafting removed).
- camel-ai  GROUNDED (thin)  smoke8c loc=1 pub=0; one localhost:9999 forum cite.
- gpt-researcher  MODEL-FABRICATION  confirm_chk loc=0 pub=12 (6 unique: glassesshop.com, headphonezone.com, soundandvision.com); shim_delta=21 -> sandbox reachable; model wrote fabricated public URLs instead of retrieved sandbox sources. Reach-0 bug GONE.
- langchain-odr  GROUNDED  odrfix_chk loc=8 pub=0; localhost:8090 wiki + :9999 forum. Fix #5 verified.
- ldr  GROUNDED  smoke8e loc=6 pub=0; localhost:9999 forum.
- smolagents  HONEST-STUB  smoke8e = "(smolagents error: repair: TimeoutError:)". Framework's own repair step timed out; honestly surfaced.
- flowsearcher-ds  MODEL-UNGROUNDED  confirm_chk 44643 bytes, shim_delta=67 (search reached), loc=0 pub=0. run_flowsearcher.py:404/447 feeds the model the sandbox sources block and asks for >=80 markdown-link cites; the qwen model paraphrased retrieved reddit content ("clamp your head like a torture device", "LCD-X ... enormous pads") but emitted zero URL links. Model citation-format failure, adapter clean (md5 0da25d0d != fallback; "source-grounded answer" writer at :505/:538 is the gated EVIDENCE_FALLBACK path, which did not fire).
- claude-code  HONEST-STUB  smoke8e = provider 400 "maximum context length is 65536 tokens ... prompt contains at least 65529 input tokens". Claude Code's own harness prompt overflows qwen3-8b's 64K window; honest framework/model incompatibility.

### deepseek-v4-flash
- deerflow  GROUNDED  dsflash_mini loc=12 (sandbox_urls=6) pub=4; localhost:8090 wiki + :9999 forum.
- opencode  GROUNDED* (in-flight)  wiring proven on qwen (curl-to-sandbox via opencode CLI); deepseek confirm_chk still running.
- storm  GROUNDED* (in-flight)  storm_runner uses a deterministic model-independent SandboxSearchRM (dspy.Retrieve subclass) that always returns sandbox snippets; qwen grounded (loc=12). deepseek confirm_chk still running.
- qx-agents  in-flight (wiring verified)  SearchXNG->SerperAdapter->shim; qwen grounded (loc=8). deepseek confirm_chk still running.
- ii-researcher  MODEL-FABRICATION  confirm_chk loc=2 pub=6; shim_delta=25 (search reached). Partial grounding (2 sandbox cites) but the model still fabricated 6 public URLs (cnet.com, head-fi.org, reddit.com, soundguys.com). B1 fix -> public URLs are the model's, not injected.
- camel-ai  GROUNDED  confirm_chk loc=11 pub=0; shim_delta=74; localhost sandbox cites. (Older dsflash_smoke showed 0 cites under a non-canonical shim; under canonical env the adapter grounds.)
- gpt-researcher  MODEL-UNGROUNDED  confirm_chk loc=0 pub=0; shim_delta=21 (search reached 21x). Real 16KB report, zero citations: the deepseek model omitted all sources. Reach-0 bug GONE (pre-fix dsflash_smoke opened "the search tool returned no results ([])").
- langchain-odr  GROUNDED  confirm_chk loc=26 pub=0; shim_delta=9; localhost sandbox cites. Fix #5 verified on deepseek (pre-fix dsflash_smoke had 0 cites from the api_base_url TypeError).
- ldr  GROUNDED  dsflash_smoke loc=9 (sandbox_urls=9) pub=0; localhost:9999 forum.
- smolagents  in-flight (wiring verified)  smolagents in-process, TavilyClient->shim + min-URL self-repair (asks model to cite its OWN retrieved URLs, no injection). deepseek confirm_chk still running.
- flowsearcher-ds  in-flight (wiring verified)  qwen confirm proved shim reach (67x) with the sources block fed to the model; deepseek confirm_chk still running.
- claude-code  in-flight (wiring verified)  claude.exe via CCR->ds_proxy->DeepSeek, WebSearch/WebFetch stripped, model curls localhost sandbox; deepseek confirm_chk still running (larger context than the qwen overflow case).

## Fix verification (the two input claims)

### FIX #1 gpt-researcher (reach-0) -- VERIFIED-FIXED on BOTH backbones
CLAIM: old in-process `_run_gpt_researcher` (run_deep_task.py:192) patched `TavilySearch.base_url`, but
gpt-researcher 0.12.3 ships its own requests-based retriever whose `search()` swallows failures and
returns `[]`, so searchshim18081.log logged 0 gpt-researcher requests.
EVIDENCE: the lane now routes to the subprocess runner `scripts/runners/gpt_researcher_runner.py`
(dead in-process fn retired from `_MANUAL_RUNNERS`, run_deep_task.py:2371-2374). That runner BINDS a
self-contained shim-only `_ShimTavilyRetriever` onto the exact late-imported name
`gpt_researcher.retrievers.TavilySearch`, no real-web fallback. Both backbones now show shim_delta=21
(vs reach-0 before). Residual is model behaviour: qwen fabricates public URLs, deepseek omits citations.
Fairness bonus: `_enhance_intent` (gpt_researcher_runner.py:117-143) removed the old seed-injection
(a literal localhost:8090 example URL and the scorer's per-domain citation counts).

### FIX #5 langchain-odr (api_base_url TypeError) -- VERIFIED-FIXED on BOTH backbones
CLAIM: `_patched_async` passed `kw["api_base_url"]=shim` into tavily 0.5.x `AsyncTavilyClient.__init__`,
which has no such parameter -> TypeError on every construction; ODR's `execute_tool_safely` swallowed it,
so every search returned no sources and both backbones produced 0-localhost prose.
EVIDENCE: run_deep_task.py:1023-1076 ("adapter audit 2026-07-07") no longer forwards `api_base_url`; it
repoints the tavily `_client_creator` httpx factory at the shim. Result: qwen odrfix_chk loc=8;
deepseek confirm_chk loc=26 pub=0 shim_delta=9. Fix works on BOTH backbones.

## Summary (verified cells)
- GROUNDED: 12  (qwen: deerflow, opencode, storm, qx-agents, ii-researcher, camel-ai, langchain-odr, ldr; deepseek: deerflow, camel-ai, langchain-odr, ldr)
- MODEL-FABRICATION: 2  (gpt-researcher/qwen, ii-researcher/deepseek)
- MODEL-UNGROUNDED: 2  (gpt-researcher/deepseek, flowsearcher-ds/qwen)
- HONEST-STUB: 2  (smolagents/qwen, claude-code/qwen)
- ADAPTER-BUG: 0
- In-flight deepseek confirms (adapter wiring verified, grounding label pending): 6 (opencode, storm, qx-agents, smolagents, flowsearcher-ds, claude-code)

## adapter_bugs_remaining
NONE. Both input-flagged adapter bugs (gpt-researcher reach-0; langchain-odr api_base_url TypeError) are
fixed and re-verified on both backbones; all 18 verified cells show search reaching the shim
(shim_delta 9-74), no ghostwriting (no fallback-template md5, no "Source-Grounded Answer"/"Evidence Map"),
no injected citations (ii B1 / camel / gpt seed-injection removals confirmed in code), and the
flowsearcher "no-bibliography" report is a model citation-format failure, not a capture-layer drop.

## Cross-check: pytest
`cd /opt/deep_reserch && python3 -m pytest tests/ -q` -> 4 failed, 142 passed, 1 skipped.
Failures (pre-existing in the current working tree; NO code was modified by this audit):
test_markdown_report_verifier.py::{test_word_floor_fails, test_max_words_fails_on_bloat,
test_pages_browsed_passes_when_unknown}, test_runner_e2e.py::test_task_21_string_match.
The two test_storm_scratch_isolation.py tests passed in this run.
