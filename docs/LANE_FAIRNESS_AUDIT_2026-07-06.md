# Deep Research Arena: Lane Fairness Audit, Synthesis and Decision Document

Date: 2026-07-06
Scope: workstation-only static audit of the 12 benchmark lanes, cross-checked against the archived paused Qwen3-8B partial run (`data/results/my5090_qwen8_partial_reports/MY5090_QWEN8_DRA_PARTIAL_HANDOFF_AND_UNIFIED_RESULTS_20260706.json`, 592 records). No box was contacted. Planned backbone targets audited against: `qwen3-8b @ --max-model-len 65536 with YaRN factor 2` and `glm-4.7-flash @ 200k via ds_proxy (thinking ON, reasoning_content)`.

## 0. Data provenance and honesty note

This synthesis merges 12 per-lane audits. Their availability differed:

- Full auditor report delivered: `deerflow`, `flowsearcher-ds`, `gpt-researcher`, `langchain-odr`.
- Recovered from scratchpad (full auditor text): `ii-researcher`, `camel-ai`.
- Truncated auditor text, completed from code + evidence: `smolagents`.
- Auditor report was null/missing; verdicts below are SYNTHESIZER-DERIVED from a direct read of the runner file plus archived evidence, and are marked `[SD]`: `ldr`, `qx-agents`, `claude-code`, `opencode`, `storm`.

For the five `[SD]` lanes the archived evidence captures the PRE-FIX broken state; every one of their runners has since been reworked in the working tree, so their leaderboard rows in the archive are stale and a re-smoke is mandatory (Section 7).

## 1. Executive decision

NOT publishable as-is. Two hard fairness blockers, both in files this synthesizer may not edit, must be resolved before any headline run:

- B1. `ii-researcher` grafts real shim search-result Wikipedia URLs onto the finished report by string-matching titles (`run_deep_task.py:1885-1900`). A single injected reachable localhost URL flips `grounding_gate` from 0.1 to 1.0, a 10x multiplier on the truth-gated headline. This is harness-manufactured grounding, not agent grounding.
- B2. `flowsearcher-ds` injects a hierarchical MEMORY that feeds real cited sandbox URLs and section skeletons mined from prior scored runs on the SAME eval set (`run_flowsearcher.py:120-158`, `data/memory/L1_task/*.json`, `L3_global.json`). No other lane receives any prior-run URL memory. This is cross-task golden-URL seed injection.

Plus one capture blocker that laundered total failures into scored zeros: `flowsearcher-ds` returned a literal 27-char sentinel for 44 of 55 tasks, all scored composite 0 with `meta.error=null` (`run_flowsearcher.py:315`).

Everything else is either OK, a documented model-capability limit (do not paper over with prompt-stuffing), or a lane-owned adapter defect already fixed this round.

## 2. Six-dimension verdict matrix

Legend: OK / BUG / FIXED (this round, in-lane) / FLAG (asymmetry to normalize) / GAP (minor). `[SD]` = synthesizer-derived (auditor report was missing).

| Lane | endpoint_wiring | sandbox_wiring | prompt_parity | output_capture | timeouts | model_adaptation |
|---|---|---|---|---|---|---|
| deerflow (reference) | OK: DS_PROXY :8088, env precedence over conf placeholder, no module-const override | OK: search+crawl through shim, 364 localhost URLs cited, reach 0.796 | OK CLEAN: injects only the intent, url_coverage 0.000 | OK: real final_report, median 10021 chars, 0 empties | OK: 1800s, 55/55, 0 timeouts | OK; FIXED opt-in `DEERFLOW_TOKEN_LIMIT` (default byte-identical) so context-compression threshold reads env not the blind 100000 |
| ii-researcher | OK: DS_PROXY env, OPENAI_BASE_URL=proxy, no override | OK best-effort: tavily+bs intercepts, 190 localhost cited; caveat: STRICT-ineligible, no network gate | BUG: input clean, but OUTPUT-side citation graft (B1) inflates grounding | BUG (fidelity): saved report = framework output MUTATED by the graft | OK: 1500s vs observed max 751s | OK both backbones by delegation to ds_proxy; no hardcoded context const |
| camel-ai | OK: DS_PROXY :8088 non-clamping, max_tokens 8192 honored | OK: TavilyClient patch + shim_intercept + strict gate; grounded reach 1.0/quote 1.0 when it cites | FLAG: heaviest rubric nudge (>=60 cites, >=15 wiki, >=20 searches, 3500+ words); NO seed URLs | FAITHFUL but UNSANITIZED: saves `<tool_call>`/`<think>` XML verbatim (reports 0013/0024/0037) | GAP: no outer wait_for; not the failure cause (14 fails died in 7-57s) | ROOT=model: qwen emits tool calls as literal `<tool_call>` text, hermes parser miss, one-round termination; settings compliant, no context const |
| flowsearcher-ds | BUG (latent): reads SHIM_URL/DS_PROXY into module consts; default :8088 vs qwen serve :8001; OPENAI_BASE_URL-vs-DS_PROXY split can route this lane to a different backbone | OK-caveat: shim contract correct, localhost reaches writer prompt, BUT `_fetch_page` is dead code so model sees only 300-char snippets | BUG: MEMORY seed injection (B2) + writer scaffolding (>=80 URLs, 4000-7000 words) | BUG (root): 27-char sentinel returned with no exception; 44/55 scored as composite 0 | OK per-call 600s; GAP: no outer wall-clock cap | OK context/tokens (evidence cap 25000 chars, max_tokens <=8192); GAP: no enable_thinking / `<think>` strip, no reasoning_content fallback, brittle JSON parse |
| gpt-researcher | OK: _wrap_runner passes shim+proxy; OPENAI_BASE_URL=proxy; setdefault; no override | BUG (root cause of reach 0): TavilySearch->shim monkey-patch ineffective at query time; 1294 wikipedia vs 1 localhost, that 1 = echoed injected example | FIXED in-lane: removed example-URL + per-domain quota seed; residual visited_urls appendix flagged | OK: real write_report, 4317-19595 chars, clean; new diag emitted OUTSIDE sentinels | OK: 1800s, observed 44-159s | OK: no context const; think-tag clean on qwen; verify glm reasoning_content on first glm run |
| langchain-odr | OK: DS_PROXY :8088 non-clamping, no :8002, no module-const bug | OK connected: _search posts to shim, localhost inlined into writer prompt; sandbox proven live (0/564 is model, not wiring) | ASYMMETRIC: bespoke citation-forcing (>=8 sandbox URLs, cover shopping/reddit/wiki) + query-suffix steering | MISLABELED: default path is a hand-rolled writer, NOT open_deep_research (graph only under LANGCHAIN_ODR_FORCE_GRAPH=1) | OK default 600s; RISK: graph timeout 240s too short, silently masks framework | SAFE both backbones; no context const; caps <=8192; default path tool-format-agnostic |
| ldr `[SD]` | OK: LDR_LLM_OPENAI_ENDPOINT_URL=proxy, OPENAI_BASE_URL=proxy | OK-caveat: own search shimmed to sandbox; mask/unmask localhost<->.internal; archive 0 localhost cited | FLAG (reverse handicap): intent sanitization strips the sandbox host roots the shared prompt gives every other lane | reworked: result.final_report + evidence_fallback on weak/timeout | OK: 1800s, native cap | OK: no context const; mask scheme built for DeepSeek safety filter, may be a no-op handicap under qwen |
| smolagents | OK: OpenAIServerModel api_base=proxy; ToolCallingAgent | Tools registered (ShimSearch/VisitWebpage); archive 0 localhost cited | FLAG: FINAL REPORT REQUIREMENTS (>=5 localhost URLs, >=4500 chars, 6-10 searches) + repair loop | FAITHFUL: real report or evidence_fallback; median 3577 | OK: native wait_for | ROOT=model: 0 grounding despite scaffolding; no context const |
| qx-agents `[SD]` | OK: LOCAL_MODEL_URL=proxy, _chat_completions_url | OK: SearchXNG->SerperAdapter->shim; archive 0 localhost (pre-fix failure) | LOW: generic "inline citations + References, ~1500 words" | reworked: was capturing Pydantic ValidationError as answer (median 497); now is_weak_report + fallback | OK: 1500s, HARD cap | FIXED-in-file: `<think>` strip (85-87) + forces text output_parser (non-openai base_url) instead of guided JSON qwen cannot satisfy |
| claude-code `[SD]` | OK-by-design: proxy_url IGNORED, CCR :3456 configured separately to reach ds_proxy | OK: --append-system-prompt enumerates sandbox endpoints + allowed curl; archive 4 localhost total | FLAG: system prompt "at least 2000 words, cite every claim as [anchor](sandbox URL)" | reworked: archive captured conversational chat (median 200 chars, min 56); now is_weak_report(3000)->synthesize_report | OK: 1800s, native cap | GAP: relies on CCR/ds_proxy for think handling; conversational-turn capture is the archive failure |
| opencode `[SD]` | FIXED-in-file (owner): `_resolve_llm_base_url` precedence fix, the module-const OPENCODE_DS_PROXY default no longer outranks harness proxy_url (THE opencode bug) | OK: sandbox-only system prompt, allowed curl allowlist; archive captured raw PowerShell/RemoteException (29-char median) | FLAG: "at least 2000 words, cite every claim as [anchor](sandbox URL)" | reworked: archive was scaffold/terminal noise; now evidence_fallback | FIXED-in-file: floor 1800 (was OPENCODE_TIMEOUT=360 -> 36/55 timeouts) | PARTIAL: output seatbelt 3840 matches the RETIRING clamp; `OPENCODE_CONTEXT_LIMIT_DEFAULT=40960` still HARDCODED (env-overridable), violates the "no 40960" rule for the 65536 move |
| storm `[SD]` | OK: api_base=proxy_url, max_tokens 8192 | OK path exists; native knowledge_storm import fails -> evidence_fallback | LOW: topic=intent[:300], no citation nudge | reworked: archive had ZERO records (total RUN-FAILED, 110 error-log hits); now multiprocess + synthesize_report fallback | OK: native multiprocess join + fallback | OK: no context const; depends on knowledge_storm availability on box |

## 3. Prompt-parity matrix (verbatim per-lane injection vs the shared prompt)

Shared task prompt: `_resolve_intent` (`run_deep_task.py:37-46`) is the raw natural-language intent with `__SHOPPING__`/`__REDDIT__`/`__WIKIPEDIA__` substituted to `localhost:17770/9999/8090`. It carries the three sandbox host ROOTS but NO golden page URLs and NO must-cite list. That is the parity baseline.

| Lane | Verbatim injection beyond shared intent | Class | Fairness judgment |
|---|---|---|---|
| deerflow | none | none | CLEAN REFERENCE. url_coverage 0.000, must_cite_hit 0/121: proves it is not fed the golden list. Use as baseline. |
| storm | `topic = intent[:300]` (truncation, no added instructions) | truncation | Fair; mild info loss from 300-char topic cap. |
| qx-agents | "Write a complete markdown report with inline citations and a References section", "about 1500 words" | generic style | Fair; generic, no domain quota, no URLs. |
| claude-code | "The report MUST: Be at least 2000 words. Cite every factual claim inline as [anchor text](sandbox URL pointing at $ShoppingUrl / $RedditUrl / $WikipediaUrl)" + curl allowlist enumerating sandbox hosts | sandbox-op + length/citation | Borderline-fair: the enumerated hosts are already in the shared prompt; the >=2000-word + cite-every-claim steering is heavier than native lanes. Normalize. |
| opencode | identical "at least 2000 words / cite every factual claim as [anchor](sandbox URL)" system prompt + curl allowlist | sandbox-op + length/citation | Same as claude-code; normalize the two CLI lanes together. |
| smolagents | "NEVER construct or guess URLs... Only use EXACT URLs from search", "at least 4500 characters and at least 10 paragraphs", "invalid unless it contains at least 5 exact `http://localhost:...` URLs", "Make 6 to 10 focused searches", plus a REPAIR LOOP that re-prompts on failure | rubric-shaped quota | FLAG: aggressive citation/length quota mirrors the scorer; no golden URLs. Normalize across lanes; do not add more. |
| langchain-odr | "Include at least 8 distinct sandbox URL citations", "Cover shopping/product, forum/reddit, encyclopedia/wiki evidence", "e.g. [title](http://localhost:8090/...)" + query suffixes "reddit forum discussion"/"wikipedia background"/"product price comparison" | rubric-shaped quota + query steering | FLAG: heavier scaffolding than native lanes; not seed injection (no answer URLs). Normalize or record. |
| camel-ai | "at least 60 distinct citations", "at least 15 Wikipedia articles", "at least 20 separate search calls", "3500+ word report", explicit per-domain keyword strategy | rubric-shaped quota | FLAG: the heaviest rubric nudge among in-process lanes, mirrors scorer thresholds (60/30/20/15). No golden URLs. Normalize. |
| gpt-researcher | WAS: example URL `[Active noise control](http://localhost:8090/...)` + "at least 15 Wikipedia article citations" + per-domain requirement | seed example URL + quota | FIXED this round in the runner (replaced with grounding-neutral anti-fabrication text). Proven harm: the example was regurgitated verbatim as the sole fake localhost citation in dr_cross_deep_0023.md:55. DEAD copy still lives in `run_deep_task.py:275-282`. |
| ldr | intent SANITIZATION: strips/masks `http://localhost:*` and `__SHOPPING__/__REDDIT__/__WIKIPEDIA__` to neutral descriptions or `.internal` fake domains | reverse handicap | FLAG (opposite direction): ldr is the only lane that REMOVES the sandbox host roots that the shared prompt gives everyone else. Built for the DeepSeek safety filter; likely an uncompensated handicap under qwen. Verify on re-smoke. |
| ii-researcher | INPUT clean (verbatim intent, report_type BASIC). OUTPUT: harness post-processes the finished report and hyperlinks real shim wiki URLs onto first-occurrence title words (`run_deep_task.py:1885-1900`) | OUTPUT-side citation graft (seed class) | BLOCKER B1: manufactures grounding the framework never produced; flips grounding_gate 0.1->1.0. Unique to this lane. |
| flowsearcher-ds | writer scaffold "Cite AT LEAST 80 distinct URLs", "4000-7000 words", domain quotas; PLUS a hierarchical MEMORY feeding L1-neighbor real cited sandbox URLs + prior high-scoring section skeletons + L3 URL templates, all mined from prior scored runs on the SAME eval set | GOLDEN-URL SEED INJECTION | BLOCKER B2: cross-task golden-URL leakage; `retrieve` excludes only the exact current task_id, still returns top-3 neighbor tasks' real cited URLs. No other lane gets prior-run URL memory. |

Bottom line for parity: only two lanes cross the seed-injection line (ii-researcher output graft B1, flowsearcher-ds memory B2). Five lanes (camel, smolagents, langchain-odr, claude-code, opencode) carry rubric-shaped instruction asymmetry that should be normalized down toward the deerflow baseline but is not answer-seeding. ldr carries a reverse handicap. deerflow/storm/qx-agents are clean.

## 4. Adapter-vs-model classification (per the user rule)

Adapter-layer defect in the lane's own runner = fixable now; shared-file defect = describe only; model-capability failure = document, do not prompt-stuff.

Model-capability failures (DOCUMENT, do NOT fix by prompt-stuffing):
- camel-ai: qwen3-8b emits tool calls as literal `<tool_call>` text (often malformed JSON), hermes parser misses them, ChatAgent terminates after one round. Cause of the 14 fast fails (7-57s) and the low citation count. Framework-design + model gap.
- langchain-odr: qwen3-8b writes from parametric memory (Sony WH-1000XM5, fake Amazon ASINs, generic [1]-[9] markers), 0/564 localhost. Search layer is correctly wired; the model overrides retrieved URLs with fabrications.
- smolagents: 0 localhost grounding despite the heaviest citation scaffolding; model does not ground.
- qx-agents: qwen3-8b cannot satisfy the qx-labs KnowledgeGapOutput structured schema (Pydantic ValidationError: research_complete / outstanding_gaps missing). Model incapacity; the adapter now sidesteps it by forcing the text output_parser.
- claude-code: model/CCR returns a conversational chat turn instead of a research report (archive median 200 chars).
- gpt-researcher: the FLUENT-but-ungrounded output is a symptom; the ROOT is an adapter sandbox-wiring bug (below), not model fabrication.

Adapter-layer defects fixed this round in the lane's own runner:
- deerflow: added opt-in `DEERFLOW_TOKEN_LIMIT` env so the context-compression threshold reads config, not the blind 100000 default. Default-unset conf is byte-identical. 5 unit tests.
- gpt-researcher: removed the seed example-URL + per-domain quota injection (now grounding-neutral anti-fabrication text); added a `===GPTR_DIAG=== retrieved=N localhost=M` self-diagnostic emitted OUTSIDE the report sentinels so the reach-0 root cause is self-revealing on the next live run. 7 unit tests.
- opencode `[SD]`, off-limits, fixed by its OWNER agent: `_resolve_llm_base_url` precedence fix (the module-const default no longer outranks harness proxy_url), timeout floor 1800, output-token seatbelt, context-limit knob.
- qx-agents `[SD]`, own file: `<think>` stripping + force text output_parser + evidence_fallback on weak/timeout. 
- claude-code `[SD]`, own file: is_weak_report(3000)->synthesize_report fallback so a conversational turn is caught.
- ldr `[SD]`, own file: mask/unmask + evidence_fallback; test added.
- storm `[SD]`, off-limits, owner: multiprocess isolation + synthesize_report fallback.

Adapter-layer defect that could NOT be safely fixed on the workstation:
- gpt-researcher sandbox wiring (reach 0): the TavilySearch->shim monkey-patch is ineffective at query time and could not be corrected without the box venv (`.venv-gptr`). Left a diagnostic; definitive fix requires a live check (Section 6).

## 5. Fixes applied this round (in-lane, minimal, both backbones preserved)

| File | Change | Test |
|---|---|---|
| `scripts/runners/deerflow_runner.py` | `_resolve_token_limit` + opt-in `DEERFLOW_TOKEN_LIMIT` into the BASIC_MODEL block; default byte-identical | `tests/test_deerflow_conf.py` (5) |
| `scripts/runners/gpt_researcher_runner.py` | neutralized seed injection via pure `_enhance_intent`; added `===GPTR_DIAG===` grounding self-diagnostic outside sentinels | `tests/test_gpt_researcher_runner.py` (7) |
| `scripts/runners/ldr_runner.py` `[SD]` | mask/unmask + evidence_fallback rework | `tests/test_ldr_runner.py` |
| `scripts/runners/qx_runner.py` `[SD]` | `<think>` strip + text output_parser + fallback | (none added) |
| `scripts/runners/claudecode_runner.py` `[SD]` | is_weak_report -> synthesize_report fallback | (none added) |

Lanes with NO in-lane fix possible because the entire adapter lives in shared/off-limits files (all defects routed to Section 6): `ii-researcher`, `camel-ai`, `langchain-odr`, `smolagents` (all inside `run_deep_task.py`), `flowsearcher-ds` (inside `run_deep_task.py` dispatch + the read-only `run_flowsearcher.py`).

## 6. Consolidated fixes needed elsewhere (shared files, box files, retired clamp)

These require the owning agent; this synthesizer did not edit them.

SHARED `scripts/run_deep_task.py` (do NOT edit here):
1. B1 FAIRNESS: delete the ii-researcher output citation graft, `run_deep_task.py:1885-1900`. `out` must be exactly `result.get('final_report') or result.get('answer') or str(result)`. Verified impact: on dr_cross_deep_0001 the sole sandbox citation IS the injected title link; removing it drops grounding_gate 1.0->0.1 and composite_v3 0.4392->0.044. 25/55 ii reports are gated on localhost presence; 5 are single-citation injection-fragile.
2. Dead-code parity hazard: delete `_run_deerflow_OLD` (`run_deep_task.py:1505-1529`, still contains the "Cite >=60 distinct sandbox URLs" sites-block at :1524-1529) and `scripts/patches/deerflow_patch.py`. Not on the active path, but would break parity if re-pointed.
3. Dead-code seed leak: `_run_gpt_researcher` (`run_deep_task.py:275-282`) still injects the example URL + "at least 15 Wikipedia" quota; reachable via the V2 wrapper `integrations/agents/gpt_researcher/agent.py:30`. Apply the same neutralization the runner got.
4. Prompt-parity normalization: reconcile the citation quotas across `_run_camel` (`551-596`), `_run_smolagents` (`450-467`), langchain-odr writer (`1344-1361`) toward the deerflow baseline. Do NOT add golden URLs and do NOT add more steering.
5. camel-ai robustness: after `resp.msg.content` (`run_deep_task.py:599`) detect the unparsed `<tool_call>` leak and either raise (so the 14 fails record an honest error instead of a scored-garbage or "(empty)" report) or strip to "". Add a model-gated `extra_body={"chat_template_kwargs":{"enable_thinking":False}}` at `:573` (keep glm thinking ON).
6. langchain-odr labeling (BLOCKING): by default the lane runs a hand-rolled writer, not open_deep_research. Either export `LANGCHAIN_ODR_FORCE_GRAPH=1` AND raise `LANGCHAIN_ODR_GRAPH_TIMEOUT_S` from 240 to ~900-1200s, or relabel the leaderboard row, or knowingly accept and document the fallback.
7. Outer timeout: wrap `_invoke_runner_once` (`~2290-2303`) in `asyncio.wait_for` with an env ceiling so a hung 8B loop cannot stall a queue worker (affects camel, flowsearcher which have no outer cap).
8. Optional model-adaptation: env-drive the hardcoded writer `max_tokens` (all <=8192, safe today) and add `<think>`/reasoning_content stripping for glm robustness in the langchain-odr writer and `evidence_fallback.py:351` (shared by opencode/claudecode/ldr; preserve them).

READ-ONLY `scripts/run_flowsearcher.py` (foreign uncommitted changes; do NOT edit):
9. B3 CAPTURE (BLOCKER): `_write_report` (`:306-315`) must RAISE on total failure instead of returning the 27-char sentinel, so the harness records `meta.error` and the scorer excludes it rather than scoring 44 zeros.
10. B2 FAIRNESS (BLOCKER): gate the hierarchical memory behind an env flag defaulting OFF, or at minimum stop injecting per-task `cited_url_patterns` example URLs (`:137-140`), which are golden-derived seeds no other lane receives. Generic structural L3 templates may stay.
11. `_llm_call` (`:86-91`): on the last retry distinguish HTTP/JSON error from empty completion and raise; add `content = msg.get("content") or msg.get("reasoning_content") or ""` for glm; optionally send `enable_thinking=false` and strip `<think>` for qwen.
12. Endpoint: forward proxy/shim explicitly from the dispatcher instead of reading module constants; align on OPENAI_BASE_URL vs DS_PROXY_URL so this lane cannot split to a different backbone than peers; ensure the resolved endpoint serves the exact model id (qwen serve is :8001, flowsearcher default is :8088).
13. Low priority: wire the dead `_fetch_page` (`:55`) so the model sees full page bodies, not 300-char snippets.

OFF-LIMITS, owner agents mid-work (already modified in the working tree, verify only):
14. `scripts/runners/opencode_runner.py`: confirm `OPENCODE_CONTEXT_LIMIT_DEFAULT=40960` (`:81`) is set from env for the 65536-YaRN move rather than left at the hardcoded default, and that the `3840` output seatbelt (which matches the RETIRING clamp :8002) is revisited once the clamp is retired.
15. `scripts/runners/storm_runner.py`: confirm knowledge_storm is installed on the box (the workstation lacks it, hence the two tolerated test failures) so the native path runs rather than always falling to synthesize_report.

BOX / INFRA (do NOT connect from here):
16. Retire the clamp proxy :8002: several lanes assume it (opencode seatbelt 3840). Ensure `DS_PROXY_URL` resolves to the non-clamping ds_proxy :8088/v1 everywhere before the run; the flowsearcher OPENAI_BASE_URL-vs-DS_PROXY_URL split (item 12) is the highest risk of a silent per-lane backbone mismatch.
17. gpt-researcher reach-0 confirmation: run one task, read stderr for `===GPTR_DIAG=== retrieved=N localhost=M`. retrieved=0 means the TavilySearch->shim patch is a no-op (inspect whether 0.12.3 uses the tavily SDK vs `self.base_url`; if search() posts to `self.base_url + "/search"`, change the patch to `self.base_url = SHIM` to avoid the double `/search` 404 vs the shim POST /search at root).
18. ii-researcher / qx-agents box config: confirm the model-selection env keys (ii: R_MODEL/R_REPORT_MODEL/REPORT_MODEL; qx: LOCAL_MODEL_URL) are the exact keys those frameworks read, else selection silently falls back.

## 7. Re-smoke list for the box round

The archived Qwen3-8B partial run predates the current working tree for many lanes; its leaderboard is stale. Re-smoke priorities:

MANDATORY (archive captured broken pre-fix state; all five runners reworked):
- opencode: verify endpoint precedence fix (LLM lands on the intended proxy, no HTTP 400 at vLLM), timeout floor 1800 (was 36/55 timeouts at 360s), report is a real >=2000-word markdown not 29-char terminal noise.
- storm: verify it produces ANY records (archive had zero, 110 RUN-FAILED error-log hits); confirm knowledge_storm native path or clean fallback.
- qx-agents: verify no Pydantic ValidationError captured as answer; `<think>` stripped; report grounded.
- claude-code: verify a real report, not a 200-char conversational turn; is_weak_report fallback engages when CCR returns chat.
- ldr: verify the mask/unmask round-trips localhost URLs back into citations (archive 0 localhost); confirm the intent sanitization is not an uncompensated handicap under qwen.

MANDATORY FAIRNESS RE-RUN (after B1/B2/B3 land in the shared/read-only files):
- ii-researcher: re-run after deleting the P2.4 graft; expect grounding to drop honestly.
- flowsearcher-ds: re-run after `_write_report` raises on empty AND the memory seed is gated OFF; expect the 44 laundered zeros to become honest errors and scores to reflect real grounding.

DIAGNOSTIC RE-RUN:
- gpt-researcher: re-run and read `===GPTR_DIAG===`; if retrieved=0, apply the box-side retriever fix (item 17) and re-run again.

REFERENCE / LOW-RISK:
- deerflow: reference lane; optionally export `DEERFLOW_TOKEN_LIMIT=60000` for qwen@65536, unset or ~180000 for glm@200k.
- camel-ai, langchain-odr, smolagents: fair to run as-is; their low grounding is genuine qwen weakness. For langchain-odr also decide FORCE_GRAPH vs relabel (item 6).

BACKBONE-MIGRATION CHECKS (both apply to every lane):
- qwen3-8b @ 65536 YaRN: no lane hardcodes 40960/32768 in a way that 400s vLLM; the one hardcoded default is opencode `OPENCODE_CONTEXT_LIMIT_DEFAULT=40960` (env-overridable, conservative, will not 400). Output caps are all <=8192.
- glm-4.7-flash @ 200k thinking ON: verify reasoning_content does not leak into `content` for lanes without explicit `<think>` stripping (camel, langchain-odr writer, smolagents, flowsearcher, ii via ds_proxy, deerflow). ds_proxy is expected to keep reasoning in the separate field; confirm on the first glm run.

## 8. Off-limits file sanity check (deliverable 3)

`git status --short` shows these off-limits / shared files modified in the working tree:

| File | Diff size | Off-limits reason | Attribution |
|---|---|---|---|
| `scripts/run_deep_task.py` | +766/-? | SHARED, do-not-edit | Not claimed by any of the 12 lane auditors (all routed changes to fixes_needed_elsewhere). Consistent with a harness-owner agent mid-work. |
| `scripts/runners/opencode_runner.py` | +447 | off-limits (owner mid-work) | Diff content is the endpoint-precedence + timeout fix with owner-voice comments; consistent with the opencode OWNER agent, not the read-only fairness auditor. |
| `scripts/runners/storm_runner.py` | +383 | off-limits (owner mid-work) | Multiprocess + fallback rework; consistent with the storm OWNER agent. |
| `integrations/ds_proxy/app.py` | +116 | off-limits (box/infra) | Infra-owner mid-work. |
| `integrations/search_shim/app.py` | +78 | off-limits (box/infra) | Infra-owner mid-work. |
| `integrations/search_shim/tests/test_schema.py` | +11 | off-limits (box/infra) | Infra-owner mid-work. |
| `scripts/run_flowsearcher.py` | modified | read-only (foreign uncommitted) | Foreign changes, as the flowsearcher auditor already noted. |

Verdict: NO confirmed violation by the 12 lane auditors. Every delivered/recovered audit whose `files_changed` I can see edited only its own lane runner plus a same-lane test (`deerflow_runner.py`+`test_deerflow_conf.py`; `gpt_researcher_runner.py`+`test_gpt_researcher_runner.py`; `ldr_runner.py`+`test_ldr_runner.py`; `qx_runner.py`; `claudecode_runner.py`). The off-limits files being dirty is the EXPECTED state the brief warned about (other agents actively editing storm/opencode/ds_proxy/search_shim/run_deep_task).

Flags to raise, not silence:
- The runners `opencode_runner.py`, `storm_runner.py`, `ldr_runner.py`, `claudecode_runner.py` all carry the identical mtime `2026-07-06 22:41:33`, suggesting a single coordinated write/restore rather than independent edits. Worth an owner confirmation that nothing was clobbered.
- `tests/test_opencode_endpoint.py` was ADDED for an off-limits lane. Adding a new test file does not modify the off-limits runner, but since the opencode fairness auditor was told to stay read-only, the owner should confirm the opencode auditor did not also touch `opencode_runner.py` (the +447 diff is attributable to the owner, but this synthesizer cannot prove the split from the working tree alone).
- `scripts/run_deep_task.py` at +766 lines is the single largest off-limits change and the one carrying the two fairness blockers (B1, B2 dispatch). Because it is shared, confirm which agent owns it before B1/B2 are applied.

## 9. Test cross-check (deliverable 2)

`python3 -m pytest tests/ -q` -> 2 failed, 547 passed, 6 skipped (75s).

- The 2 failures are the tolerated pre-existing pair `tests/test_storm_scratch_isolation.py::test_run_uses_unique_scratch_dir_and_cleans_up` and `::test_run_cleans_up_even_on_runner_error`, both caused by `knowledge_storm` not being installed on the workstation (unrelated to fairness).
- The third tolerated case `tests/test_real_leaderboard.py::test_output_states_actual_additive_formula` PASSED this run (it is within the tolerated set, so its passing is fine).
- 547 passed includes the 32 new in-lane tests added this round (deerflow 5, gpt-researcher 7, ldr, opencode-endpoint). No new breakage introduced by the audit round.

## 10. Summary judgment

- Publish-blocking: B1 (ii-researcher output graft), B2 (flowsearcher memory seed), B3 (flowsearcher 27-char capture). All in shared/read-only files.
- Fix-and-verify: five reworked `[SD]` lanes (opencode, storm, qx-agents, claude-code, ldr) plus gpt-researcher reach-0; all need a box re-smoke because the archive is pre-fix.
- Normalize (not blocking): rubric-shaped citation quotas in camel, smolagents, langchain-odr, claude-code, opencode toward the deerflow baseline; ldr's reverse handicap.
- Genuine model limits (do not prompt-stuff): camel tool-call-as-text, langchain-odr/smolagents/ldr fabrication, qx structured-output incapacity, claude-code conversational turns.
- Backbone-ready: no lane hard-blocks the 65536-YaRN move; the only stale constant is opencode's env-overridable 40960 default; the only clamp coupling is opencode's 3840 seatbelt tied to the retiring :8002.
- deerflow remains the clean fairness reference.
