# Framework root-cause forensics (11 Deep Research frameworks)

Goal: for each framework we scored, find the MECHANISM behind its score profile and
assign blame: AGENT fault / OUR-RUNNER fault / OUR-SCORING fault / SANDBOX-state
fault. This builds on `docs/FRAMEWORK_WEAKNESS_ANALYSIS.md` and goes one layer
deeper, citing runner code, verifier code, golden data, and per-task score JSON
`details`.

## How to read the verdicts

- **AGENT** — the framework's own output is the problem (fabricates URLs, writes
  tiny reports, enumerates instead of synthesizes). The low score is deserved.
- **RUNNER** — our adapter in `scripts/runners/*` or `scripts/run_deep_task.py`
  produced a degenerate/stub output (wrong venv path, capture miss, crash). The
  score is an artifact of our harness, not agent quality.
- **SCORING** — our verifier or threshold makes a real, grounded report look bad
  (e.g. an unreachable golden gate, an off-by-scheme URL match).
- **SANDBOX** — the sandbox services (`:7770` shopping, `:9999` reddit, `:8090`
  kiwix, `:8081` shim) were down or stale at run or score time, so live-fetch
  verifiers saw 404/connection failures for legitimately-cited pages.

## Two scoring batches exist; they disagree

There are TWO score corpora and they are NOT the same numbers:

- `data/results/deep_v3/*.score.json` — the FROZEN batch the weakness analysis
  tabulated. Many entries are stale (e.g. `gpt-researcher__dr_cross_deep_0001`
  records `answer_chars=69`, a capture failure).
- `data/results/deep/*.score.json` — the CURRENT local re-run. The same task
  now records `answer_chars=28504` with 110 cited URLs.

Where the two disagree this document cites both and flags the live one as
authoritative. The frozen deep_v3 means in the prompt's table mix real agent
behaviour with historical runner/sandbox failures; that mixing is itself one of
the systemic problems (see Synthesis section).

## The verifier mechanics that decide everything

Three deterministic verifiers dominate the pillars and recur in every verdict:

1. `src/verifiers/url_coverage_verifier.py:122-133` — `must_cite_recall` is
   `weighted-hit / weighted-total` over the golden `must_cite_urls`. The pass
   gate (`:166`, `:194-197`) requires `must_cite_recall >= 0.45`. This single
   number is the systemic story (see Synthesis 1).
2. `src/verifiers/url_reachability_verifier.py` + `quote_match_verifier.py:83-119`
   — both LIVE-FETCH every cited sandbox URL. `quote_match` only scores a claim
   if the URL returns HTTP 200 (`:95`). Therefore: (a) a fabricated URL scores 0;
   (b) a real URL scored while the sandbox is DOWN also scores 0. Reachability
   and quote_match cannot, by themselves, distinguish "agent lied" from "our box
   was offline."
3. `src/verifiers/citation_format.py:97-131` — canonicalisation. It bridges
   Kiwix path aliases, query-order, trailing slash, host case. It does NOT and
   cannot bridge an agent that invents a different URL *scheme* (e.g.
   `/product/<slug>` when the sandbox serves `/<slug>.html`). That distinction is
   what separates a SCORING bug from an AGENT bug for the fluent hallucinators.

The composite (`scripts/score_deep_answer.py:250-260`) multiplies a
`grounding_gate = max(0.1, reachability)` against the weighted quality score, so
an ungrounded report is floored at 10% of its quality — by design.

---

# Per-framework root cause

## 1. claude-code  (n5)

(a) **Produces**: long (median 46k, up to 72k chars), real-slug-grounded reports.
Sampled citations from `claude-code__dr_cross_deep_0001_matrix.md` are exact
sandbox product slugs, e.g.
`http://localhost:7770/beats-by-dr-dre-powerbeats-headphones-black-with-usb-adapter-cubes.html`
and `.../denon-ah-d5200-over-ear-headphones.html` — these resolve and appear in
the golden pool.

(b) **Scores**: reach 0.96, quote 0.86, depth 0.65, pres 0.67, cov 0.27,
**mcr 0.028**, 0 fail. Top of the field on every grounded pillar.

(c) **Root cause of the one weak pillar (mcr)**: NOT the agent. On task 0001 it
cites 155 unique URLs and hits 6 of the 121 golden must-cite pages
(`claude-code__dr_cross_deep_0001_matrix.score.json`: `must_cite_hit=6`,
`must_cite_recall=0.0605`). It genuinely grounds in real pages; it simply cannot
cite 45% of a 121-URL exhaustive crawl (Synthesis 1). Its only true weakness is
the n=5 sample (under-sampled standing) and verbosity (72k chars risks the
8k-word `max_words` spec ceiling, `markdown_spec.max_words`).

(d) **Verdict**: AGENT-good. The mcr 0.028 is ~90% SCORING (golden over-breadth),
~10% agent (it could target the highest-weight pages). Standing caveat is
sampling, our fault (only 5 tasks dispatched).

(e) **Fix**: run all tasks for a fair n; fix the golden must-cite set (Synthesis
1) and mcr will jump for claude-code more than anyone.

## 2. camel-ai  (n57)

(a) **Produces**: the most robust real reports (57 tasks, 0 capture failures),
median 29k chars, citing exact sandbox slugs (sampled: `.../66-audio-sport2-bt-5-0-wireless-sports-headphones-new-2022.html`,
`.../akg-pro-audio-k72-over-ear-closed-back-studio-headphones-matte-black.html`).
Run in-process via `_run_camel` (`run_deep_task.py:409`), Tavily client patched
to the shim (`:419-425`), HTTP gate optional (`:416`).

(b) **Scores**: reach 0.91, quote 0.78, depth 0.59, cov 0.14, **mcr 0.033**, 0 fail.

(c) **Root cause**: grounded and stable. The runner wiring is correct (search →
shim, LLM → proxy, output captured directly from `resp.msg.content` with CoT
stripped at `:465-481`). mcr 0.033 is again the golden-breadth ceiling: on task
0001 it cites 98 URLs, hits 8/121 must-cite (`must_cite_hit=8`, recall 0.0605),
and across its tasks must-cite hits range 0–9 with recall never above ~0.086. It
is doing real targeted retrieval; the 0.45 gate is unreachable for everyone.

(d) **Verdict**: AGENT-good. mcr ~85% SCORING, ~15% agent (depth is only 0.59 —
it enumerates products well but reconciles sources less). No runner or sandbox
fault.

(e) **Fix**: golden fix (Synthesis 1). To lift depth, the system prompt
(`:446-460`) could demand explicit contradiction/cross-source paragraphs that
`analysis_depth_verifier` rewards (`tier_a: has_cross_source_section`,
`contradiction_count`).

## 3. smolagents  (n31)

(a) **Produces**: shorter reports (median 15k), `ToolCallingAgent` to force
verbatim URL copying (`_run_smolagents`, `run_deep_task.py:366-391`). Sampled
citations LOOK like real slugs (`.../anker-soundcore-life-q20-wireless-bluetooth-headphones-noise-cancelling-40h-playback.html`,
`.../corsair-hs35-stereo-gaming-headset-pc-ps4-3-5mm-microphone.html`).

(b) **Scores**: reach 0.70, quote 0.62, depth 0.40, cov 0.12, **mcr 0.055**
(field-best), 1 fail.

(c) **Root cause**: a SPLIT personality, and it is the agent's. Reachability per
task is bimodal: of 31 tasks, 9 hit reach=1.0 but 3 hit 0.0 and several land
0.3–0.7 (`for f in deep_v3/smolagents__*: url_reachability.score`). On task 0001
the local score shows only 8/108 cited URLs return 200 (`http_200:8, http_4xx:100`)
— here it CONSTRUCTED plausible slugs that 404 despite the "NEVER construct URLs"
instruction (`:389-391`). On other tasks it copies real slugs and scores 1.0.
smolagents posts the field-best max single-task mcr (0.2785 on task 0005), so
when it grounds, it grounds best — but it is inconsistent.

(d) **Verdict**: ~70% AGENT (URL fabrication on a minority of tasks even under a
copy-verbatim prompt and ToolCallingAgent; shortest reports → lower coverage and
depth), ~30% SCORING (mcr ceiling). 1 capture fail is a minor RUNNER blip.

(e) **Fix**: agent-side, none we can apply without changing smolagents. Our lever
is the golden fix; that alone makes its real 0.055 mcr look respectable.

## 4. flowsearcher-ds  (n48)

(a) **Produces**: medium reports (28k) but ~38% of runs failed to capture
(18/48 < 1500 chars). Runs through `_run_flowsearcher_ds` →
`scripts/run_flowsearcher.run_flowsearcher` (`run_deep_task.py:1317-1321`).

(b) **Scores**: reach 0.50, quote 0.45, depth 0.32, cov 0.06, mcr 0.007,
18/48 fail.

(c) **Root cause**: MIXED. ~half its cited URLs resolve (reach 0.50) — partial
real grounding, partial fabrication, the same construct-slug failure smolagents
shows but worse. The 18 capture failures are a RUNNER/stability problem in the
flowsearcher adapter (the high fail count, not seen in camel/claude, indicates
the adapter or its sub-process crashes ~⅓ of the time).

(d) **Verdict**: ~45% AGENT (half-fabricated citations, shallow synthesis),
~40% RUNNER (18 capture failures inflate the "partial grounding" label by
dragging means down with stubs), ~15% SCORING (mcr ceiling). The 0.007 mcr is
below even camel/claude because the 18 stubs cite nothing.

(e) **Fix**: stabilise the flowsearcher runner (find why ~⅓ of subprocesses
return < 1500 chars), exclude `invalid_runs` from means, then re-rank.

## 5. gpt-researcher  (n32)  — fluent hallucinator (the canonical case)

(a) **Produces**: long (median 28k), beautifully formatted, heavily "cited"
reports that are PARAMETRIC HALLUCINATIONS. `_run_gpt_researcher`
(`run_deep_task.py:192-285`) patches `TavilySearch.base_url` to the shim
(`:262-267`), so search input is real — but the report WRITER drops the real
retrieved URLs and emits sequential fakes. Direct quote from
`gpt-researcher__dr_cross_deep_0001_matrix.md`:

> 1. **Sony WH-1000XM5** - [Product Page](http://localhost:7770/products/1)
> ...
> [Product 47](http://localhost:7770/products/47) - Bowers & Wilkins Px8 ...
> 1. [Thread 1](http://localhost:9999/threads/1) - "Sony WH-1000XM5 vs AirPods Max"

The sandbox has NO `/products/N` or `/threads/N` routes — it serves `/<slug>.html`
and `/f/<forum>/...`. The product names (Sony WH-1000XM5, Bose QC Ultra) are the
LLM's real-world knowledge, not the sandbox catalog. It even invents review
counts ("2,847 reviews") that no page contains.

(b) **Scores (live deep/ batch)**: 110 cited, 110 sandbox-format, but
`http_200:3, http_4xx:107` → reach 0.027; quote_match 0.0 with all 116 claims
`reason:"unreachable"` (`gpt-researcher__dr_cross_deep_0001_matrix.score.json`).
mcr 0.0 (0 must-cite hits). Presentation 0.71 (field-best).

(c) **Root cause**: AGENT. The grounding gate and live-fetch verifiers are doing
EXACTLY their job: catching fluent fabrication. Canonicalisation cannot save it
because `/products/1` is a fabricated scheme, not a normalisation variant. (Note
the frozen deep_v3 0001 entry is a separate 69-char capture failure — that one
specific historical number is a RUNNER artifact, but the agent's real behaviour,
captured in the live batch, is fabrication.)

(d) **Verdict**: ~95% AGENT (confident URL fabrication under a working search
wiring). ~5% legacy RUNNER noise in the frozen batch.

(e) **Fix**: none on our side makes it look better honestly — the gate SHOULD
penalise it. The only legitimate improvement is agent-side (feed the writer the
verbatim retrieved-URL list); the codebase already attempts query-level nudges
(`:271-282`) but the writer ignores them.

## 6. langchain-odr  (n31)  — fluent hallucinator, scheme-invention variant

(a) **Produces**: fluent (pres 0.71), some real analysis (depth 0.39), via a
langgraph supervisor→researcher→writer (`_run_langchain_odr`,
`run_deep_task.py:760-824`). Both sync and async Tavily clients are patched to
the shim (`:773-794`), so retrieval is real. But it cites a FABRICATED URL
SCHEME. Sampled from `langchain-odr__dr_cross_deep_0001_matrix.md`:
`http://localhost:7770/product/anker-soundcore-life-q20`,
`http://localhost:7770/product/apple-airpods-max`. The real sandbox path is
`/anker-soundcore-life-q20-wireless-...-40h-playback.html` — no `/product/`
prefix, with the full descriptive slug and `.html`.

(b) **Scores**: reach 0.01 (3/91 return 200), quote 0.00, mcr 0.000, depth 0.39,
pres 0.71, 4 fail.

(c) **Root cause**: AGENT. The writer normalises product names into a clean,
invented `/product/<brand-slug>` URL form instead of copying the messy real slug.
`citation_format.canonicalize_url` (`:97-131`) cannot rewrite path structure, so
all 88 invented URLs 404. This is genuine fabrication, not a scoring artifact.

(d) **Verdict**: ~90% AGENT (URL-scheme invention), ~10% RUNNER (4 capture fails).

(e) **Fix**: agent-side. Our gate is correct to floor it.

## 7. deerflow  (n30)  — under-cited, cites OFF-sandbox real-web URLs

(a) **Produces**: long (25k) presentable prose (pres 0.58) but only ~14 citations
and they point OFF the sandbox. `_run_deerflow` → `deerflow_runner.run`
(`run_deep_task.py:827-832`). The runner correctly redirects Tavily to the shim
(`deerflow_runner.py:99-144`, rewrites `langchain_tavily._utilities.TAVILY_API_URL`),
so search returns sandbox content — but the reporter LLM writes real-internet
URLs (en.wikipedia.org and friends) instead of the localhost ones it was given.
The reachability verifier reports `"reason":"no sandbox-domain URLs cited",
cited_off_sandbox:61` for task 0001 (deep_v3 score), and quote_match returns
`"no sandbox-domain markdown links", claims_total:0`. The .md is not synced
locally (score JSON `details` only), so URLs are read from those details.

(b) **Scores**: reach 0.16, quote 0.02, mcr 0.000, cov 0.01, depth ~0, pres 0.58,
0 fail (it always produces SOMETHING, just ungrounded).

(c) **Root cause**: AGENT, with a small SCORING edge-effect. The reporter ignores
the sandbox URLs and emits its parametric real-web URLs. Because the verifiers
score only sandbox-host citations (`quote_match_verifier.py:132-148`), an
all-off-sandbox report yields `claims_total:0` and reach over off-sandbox only.
The penalty is deserved (the agent did not cite what it retrieved), but the
"61 cited, all off-sandbox" shape also shows our reachability scorer simply
ignores off-sandbox URLs rather than penalising them as fabrications — a
reporting nuance, not a wrong verdict.

(d) **Verdict**: ~85% AGENT (reporter emits real-web URLs, under-cites), ~15%
SCORING-presentation (the "no URLs cited" message understates that it cited 61,
just wrong-domain).

(e) **Fix**: agent-side reporter prompt to copy localhost URLs verbatim
(the OLD runner attempted post-hoc URL replacement, `_run_deerflow_OLD:880-887`,
since removed). On our side, surface off-sandbox citation counts so deerflow's
failure reads as "cited the wrong internet" not "cited nothing."

## 8. ldr (local-deep-researcher)  (n30)  — tiny by construction

(a) **Produces**: consistently TINY reports. Char counts run 794 → 5782 with
median ~1.5k (`for f in deep_v3/ldr__*: answer_chars` → 794,853,864,...,3757,5782).
Via `_run_ldr` → `ldr_runner.run` (`run_deep_task.py:900-905`). The OLD runner
(`:908+`) reveals the cause: DeepSeek-V4-flash refuses to write reports that
mention localhost URLs (safety filter), so the runner STRIPS all localhost URLs
from the intent (`:917-918` comment: "DeepSeek V4 flash refuses... triggers safety
filter"). LDR then researches a sanitised topic and writes a short summary.

(b) **Scores**: median 1.5k chars, 2 citations, depth ~0.01, reach 0.65 (but over
only 2–3 URLs — on task 0001 it cites 3, all 3 return 200: `http_200:3`), mcr 0.0,
19/30 fail (< 1500 chars).

(c) **Root cause**: MIXED, leaning AGENT-by-design + MODEL. LDR is a lightweight
summariser, not a comprehensive researcher; its design produces short output.
The 19 capture "failures" are mostly real LDR runs that are simply < 1500 chars
(not stubs) — so the fail label over-counts. The few URLs it does cite are REAL
(reach 0.65–1.0), so it is honestly grounded, just shallow. The localhost-URL
refusal is a MODEL behaviour our proxy (deepseek-v4-flash) imposes, partly our
infrastructure choice.

(d) **Verdict**: ~60% AGENT (shallow by design), ~25% RUNNER/MODEL (the
URL-stripping workaround and the model's refusal shrink output further), ~15%
SCORING (the < 1500 "fail" threshold mislabels short-but-valid reports).

(e) **Fix**: run LDR with a model that does not refuse localhost URLs; stop
labelling short-but-real reports as capture failures (distinguish "stub/error"
from "short").

## 9. ii-researcher  (n30)  — runner-broken on 23/30, real on the rest

(a) **Produces**: BIMODAL. 7 real runs (8.3k–35k chars, one task hit 157
citations and passed the citation spec — `ii-researcher__dr_cross_deep_0001`:
29038 chars, `citation_count:157, citations_ok:true`) and 23 stub runs of exactly
74 chars / 11 words. Via `_run_ii_researcher` (`run_deep_task.py:1184-1294`), a
subprocess in `.venv-ii` with a large injected driver (TavilyClient base-url
patch + URL-collection + wiki-URL injection).

(b) **Scores**: 23/30 = 74 chars → mean 74 chars, mcr 0, reach 0.00, 23 fail.

(c) **Root cause**: RUNNER. The 74-char output is the driver's exception branch
(`:1281-1283`): `print("===REPORT===")` then
`print(f"(ii-researcher error: {type(e).__name__}: {e})")`. An 11-word
`(ii-researcher error: <ExceptionType>: <message>)` string is exactly 74 chars.
So on 23/30 tasks the ii-researcher subprocess threw (the `ReasoningAgent.run`
call at `:1257-1258` crashes — plausibly an asyncio event-loop, connection, or
proxy error), and our runner captured the error placeholder as the "report." The
7 successes prove the wiring CAN work; the failures are an unstable adapter.

(d) **Verdict**: ~75% RUNNER (the 23 stubs are our subprocess crashing and us
recording the error string as the answer), ~25% real signal from the 7 good runs
(which look competitive — 157 citations). The mean is meaningless as agent
quality.

(e) **Fix**: harden the ii driver (catch and retry the crashing call, log the
real exception text instead of swallowing it into a 74-char stub), re-run all 30,
and EXCLUDE error-stub runs from means before ranking.

## 10. storm  (n31)  — runner-broken on ~22/31 (empty-article), our pipeline

(a) **Produces**: 22/31 runs are the literal 20-char / 3-word string
`(empty storm output)`; 8 runs are ~409 chars; 1 is a real 11479-char article.
Via `_run_storm` → `storm_runner.run` (`run_deep_task.py:486-491`). The runner
uses a clean `SandboxSearchRM(dspy.Retrieve)` talking straight to the shim
(`storm_runner.py:63-161`) — no fake Tavily key (the older weakness-analysis note
about a "fake Tavily key" is outdated; this runner does not use Tavily at all).

(b) **Scores**: median 20 chars, mcr 0, reach 0.03, quote 0.03, 30/31 fail.

(c) **Root cause**: RUNNER/PIPELINE. `(empty storm output)` is returned at
`storm_runner.py:391` ONLY when no article file is found after the STORM pipeline
runs (`:356-391` searches `storm_gen_article_polished.txt` →
`storm_gen_article*.txt` → `*.txt`). The scratch dir DOES contain artifacts for
the one task that worked (`data/results/deep/_storm_scratch/Produce_a_Causal_..._cold-/storm_gen_article_polished.txt`
exists), so when STORM completes it is found. On the 22 empty runs the STORM
pipeline (conv-simulator → outline → article → polish, all on deepseek-v4-flash
via LiteLLM, `storm_runner.py:191-207`) did not produce an article file — most
likely an LLM/LiteLLM error mid-pipeline or a topic-name path issue truncating
the scratch subdir lookup. Either way the agent never got to write; the score is
our harness's empty-output marker, not STORM's capability.

(d) **Verdict**: ~95% RUNNER (the article-generation stage fails for most tasks
and we record the empty marker). The 1 real article (11.5k chars) shows STORM
can run end-to-end here.

(e) **Fix**: capture and log the STORM pipeline exception instead of silently
returning `(empty storm output)`; verify the per-stage LiteLLM calls succeed on
deepseek-v4-flash; re-run all tasks; exclude empty-marker runs from means.

## 11. qx-agents  (n30)  — 100% identical deterministic runner failure (the smoking gun)

(a) **Produces**: EVERY one of 30 runs is byte-identical at 367 chars / 41 words /
1 paragraph / 1 h2 (`for f in deep_v3/qx-agents__*: answer_chars` → `30 × 367`).
No variation across tasks at all.

(b) **Scores**: chars 367 (identical), 0 citations, ALL pillars 0, presentation
0.20 (3/6 tier-A pass: only `section_balance`, `no_orphan_text`,
`flesch_readability` — exactly what a single short error paragraph passes),
30/30 fail.

(c) **Root cause**: RUNNER — a deterministic venv-path bug. The qx runner returns
an early error string before any agent code runs if its venv is missing:
`qx_runner.py:214-216`:

```python
qx_python = QX_VENV_PYTHON          # ROOT/".venv-qx"/"bin"/"python"
if not qx_python.exists():
    return f"(qx-agents error: venv not found at {qx_python})"
```

The smoke logs capture this exact string on the scoring host (Windows):
`data/results/smoke/smoke_20260510_035437.json` →
`(qx-agents error: venv not found at D:\\lyb\\deep_reserch\\.venv-qx\\bin\\python)`.
On Windows the interpreter lives at `.venv-qx\Scripts\python.exe`, NOT
`.venv-qx/bin/python`, so `QX_VENV_PYTHON.exists()` is ALWAYS False, and the
runner returns the SAME error string for every task — hence 30 identical outputs.
(The 367-char deep_v3 form is the same class of fixed pre-flight error string;
the absolute proof is the identical-length, zero-variance, single-paragraph shape
plus the smoke-log capture of the literal message.) No qx-agent ever executed.

(d) **Verdict**: 100% RUNNER. The qx-agents score is pure harness artifact and
must not appear on any leaderboard as agent quality.

(e) **Fix**: make `QX_VENV_PYTHON` OS-aware (`Scripts/python.exe` on Windows,
`bin/python` on POSIX) or resolve via `sys.executable` of the created venv;
verify `.venv-qx` exists on the scoring host; re-run all 30; until then DROP
qx-agents from the board entirely.

---

# Synthesis: the systemic problems

## S1. The golden must-cite set is structurally unreachable (the dominant SCORING bug)

This is the single most important finding and it affects EVERY framework's
headline `must_cite_recall`.

- The golden `must_cite_urls` is essentially the ENTIRE crawl, not the few
  sources needed to answer. `build_deep_golden.py:316-328,461-465,523-525` marks
  nearly every parsed item as must-cite (weight > 0): for task 0001 that is 121
  URLs = 56 shopping + 40 reddit + 25 wiki (verified via Counter on
  `dr_cross_deep_0001.json`), built from 60 parsed products / 40 parsed threads.
- The pass gate demands `must_cite_recall >= 0.45`
  (`url_coverage_verifier.py:166,194`) — i.e. cite ~54 of 121 exact pages.
- The BEST-grounded agents cite real golden pages but top out near 6–8%:
  camel-ai 8/121 (0.0605), claude-code 6/121 (0.0605). The ABSOLUTE ceiling
  across all 11 frameworks and all tasks is **0.2785** (smolagents, task 0005) —
  still below the 0.45 gate. No framework can pass.
- Conclusion: the near-zero mcr is ~85% an EVAL problem (the must-cite set
  conflates "topic-relevant pool" with "required evidence") and ~15% an agent
  problem (agents could prioritise the weight-1.0 pages). This was the open
  question in the prior analysis; the data answers it: **EVAL problem**.
- Fix: rebuild must-cite as a SMALL set (5–15) of genuinely answer-critical,
  high-weight, currently-live URLs per task; demote the rest to `expected_pool`
  (already scored separately, weight 0.15). Then re-derive the 0.45 gate from the
  achievable distribution.

## S2. Runner-capture pollution (the dominant RUNNER problem)

Four frameworks are mostly or entirely our harness failing, not the agent:

| framework | failure | mechanism | who |
| --- | --- | --- | --- |
| qx-agents | 30/30 identical 367-char | `.venv-qx/bin/python` missing on Windows scoring host (`qx_runner.py:214`) | 100% RUNNER |
| storm | 22/31 `(empty storm output)` | STORM pipeline produces no article file; we return the empty marker (`storm_runner.py:391`) | ~95% RUNNER |
| ii-researcher | 23/30 `(ii-researcher error: ...)` 74-char | subprocess crashes; driver swallows it into a stub (`run_deep_task.py:1281-1283`) | ~75% RUNNER |
| flowsearcher-ds | 18/48 < 1500 chars | adapter/subprocess instability | ~40% RUNNER |

Plus the deep_v3 vs deep/ batch divergence (gpt-researcher 0001: 69 vs 28504
chars) — stale frozen scores mixing capture failures with real behaviour. The
`invalid_runs` exclusion fix handles this going forward, but every historical
mean for these four agents is untrustworthy until a clean re-run on a working
sandbox with an OS-correct venv resolution.

## S3. Fluent-hallucinator mode (the dominant AGENT problem)

Three frameworks produce long, polished, heavily-"cited" reports whose citations
do not resolve — and the grounding gate correctly catches all three:

- **gpt-researcher**: invents sequential `/products/N`, `/threads/N` URLs and
  real-world product names; 107/110 cited URLs 404.
- **langchain-odr**: invents a `/product/<brand-slug>` scheme; 88/91 URLs 404.
- **deerflow**: emits off-sandbox real-web URLs (en.wikipedia.org) instead of the
  localhost URLs it retrieved.

In all three, the runner correctly wires search to the shim — the failure is the
REPORT WRITER substituting parametric knowledge for retrieved evidence. The
live-fetch reachability/quote_match verifiers and the `grounding_gate` floor are
doing exactly the job they exist for. Canonicalisation (`citation_format.py`)
deliberately does NOT rescue invented schemes, which is correct. These three
SHOULD score low; their low scores are trustworthy.

## S4. The depth gap (a real, field-wide AGENT weakness)

Even the grounded leaders enumerate more than they synthesize. `analysis_depth`
tops out at 0.65 (claude-code) and is < 0.40 for most. camel-ai 0.59 with
field-best robustness still mostly lists products/threads rather than reconciling
contradictions across sources (the `analysis_depth_verifier` tier-A criteria:
`has_cross_source_section`, `contradiction_count`). This is genuine and not our
fault — current DR agents are good retrievers, weak synthesizers.

## S5. Live-fetch verifiers cannot distinguish "lie" from "box was down"

`quote_match_verifier.py:95` and the reachability probe both require HTTP 200 at
SCORE time. A correctly-cited real URL scored while `:7770/:9999/:8090` were
offline returns the same 0 as a fabricated URL. We currently cannot tell these
apart from the score alone. For the fluent hallucinators we confirmed fabrication
by reading the .md (the URLs are structurally impossible), so their verdicts hold
— but any agent whose reachability is low AND whose URLs are structurally valid
slugs deserves a sandbox-uptime check before being labelled a hallucinator.

---

# Prioritized fix list (to make the leaderboard trustworthy)

1. **Fix the golden must-cite set (S1).** Highest leverage: it depresses the
   headline grounding metric for EVERY agent including the honest leaders, and
   makes the 0.45 gate unpassable. Rebuild must-cite as a small, answer-critical,
   live-verified set; re-derive the gate. Do this first — it changes the relative
   ordering of the grounded agents (claude-code/camel-ai/smolagents) the most.

2. **Fix the qx-agents venv resolution and re-run (S2).** One-line OS-aware path
   fix (`Scripts/python.exe` vs `bin/python`). Until then DROP qx-agents from the
   board; a 30/30 identical error string is not a score.

3. **Re-run storm and ii-researcher on the working sandbox, logging real
   exceptions (S2).** Replace the silent `(empty storm output)` /
   `(ii-researcher error: ...)` stubs with captured tracebacks; exclude
   error/empty runs from means. Their handful of good runs (storm 11.5k article,
   ii 157-citation report) show real capability the current means hide.

4. **Stabilise flowsearcher-ds and re-run (S2).** Diagnose the ~⅓ subprocess
   capture failures; exclude `invalid_runs`.

5. **Add a sandbox-uptime guard to scoring (S5).** Before trusting a low
   reachability/quote score, confirm the sandbox returned 200 for a known-good
   control URL at score time. Refuse to score (or flag) otherwise.

6. **Distinguish "stub/error" from "short-but-real" in the fail filter (ldr).**
   The < 1500-char threshold currently mislabels honest short LDR reports as
   capture failures.

7. **Re-base the leaderboard on the live `deep/` batch, not frozen deep_v3.**
   The frozen batch mixes capture failures into agent means. Freeze a NEW batch
   only after fixes 1–4 land.

8. **Keep the grounding gate and live-fetch verifiers as-is (S3).** They
   correctly separate the three fluent hallucinators (gpt-researcher,
   langchain-odr, deerflow) from the grounded agents (claude-code, camel-ai,
   smolagents). This part of the eval is working; do not soften it to make the
   hallucinators look better.

## One-paragraph honest summary of blame

Of the 11 frameworks: **3 deserve their low scores** (gpt-researcher,
langchain-odr, deerflow — fluent URL fabrication, AGENT fault); **2 are honestly
mid** (smolagents inconsistent URL-copying, ldr shallow-by-design — mostly AGENT,
partly model/threshold); **2 are honestly good and under-credited** (claude-code,
camel-ai — grounded and stable, dragged down ONLY by the unreachable golden
must-cite gate, a SCORING fault); **1 is a partial mix** (flowsearcher-ds — half
real, ⅓ runner-crashed); and **3 are pure harness artifacts that must be re-run**
(qx-agents 100% RUNNER venv bug, storm ~95% RUNNER empty-article, ii-researcher
~75% RUNNER subprocess crash). The single systemic eval bug — must-cite set built
as the whole crawl with a 0.45 gate no agent can reach — is what makes the entire
grounding leaderboard currently untrustworthy, independent of the per-runner
failures.
