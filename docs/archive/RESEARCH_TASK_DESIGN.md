# Deep Research Benchmark Design: State of the Art

*A literature review and design protocol for `dr_arena_deep`. Written 2026-04-25 after the v0 sandbox audit revealed that 3 of 5 popular OSS DR agents fabricate ≥97% of cited URLs under DeepSeek-V4-flash, and that LLM judges miss this entirely. The v0 dataset was hand-built only for `dr_cross_deep_0001`; the other 9 topics were template-cloned and are NOT publishable as-is.*

This doc grounds the next dataset cycle in prior work. Sections 1–8 are evidence; Section 9 is the concrete design we should adopt.

---

## 1. Existing deep-research benchmarks: how do they actually build tasks?

### 1.1 DeepResearch Bench (Du et al., arXiv 2506.11763, Jun 2025)

100 PhD-level research tasks across 22 distinct fields. Construction protocol (per the paper):

- **Distribution-grounded topics**: 96,147 raw queries collected from a web-search-enabled chatbot were used to set the topic *distribution*. The 100 tasks are then sampled to mirror that distribution. This is the strongest published defense against topic bias in DR benchmarks.
- **Expert authoring**: Each task is hand-crafted by domain experts — PhD holders or senior practitioners with 5+ years of relevant experience. No crowdsourcing.
- **Multi-step reasoning required**: Tasks are explicitly designed to require multi-step reasoning, comprehensive synthesis, and nuanced domain understanding. The paper claims they "test the upper limits" of current DR agents.
- **Two evaluation methodologies**: a reference-based method with adaptive criteria for report quality, plus a separate framework that measures "effective citation count" and "overall citation accuracy". (Specific formulas were not extractable from the abstract; the PDF was unreadable in our fetch — to obtain RACE / FACT formula details, an HTML mirror or LaTeX source needs to be re-fetched in a follow-up.)

**Lesson for us**: 100 tasks is the upper bound a small team can hand-author; 22 fields is the diversity floor; per-task expert authoring is non-negotiable for credibility.

### 1.2 BrowseComp (OpenAI, Wei et al., Apr 2025)

1266 challenging questions, all manually authored by trainers. Three filters per task:
- (i) GPT-4o + o1 + early deep-research model all fail it,
- (ii) the answer does not appear in the first page of 5 simple searches,
- (iii) a *different* human cannot solve it within 10 minutes.

Single short-form answer per task; verification is exact-string-match. **No citation requirement**.

### 1.3 BrowseComp-Plus (texttron, ACL 2026 Main)

Re-uses BrowseComp's 830 reasoning queries on top of a frozen ~100K-document corpus instead of the live web. Two label tiers per query:
- **Evidence documents** — needed to answer the query
- **Gold documents** — needed to answer AND semantically contain the final answer

Two evaluation modes: (a) end-to-end agent accuracy + recall + tool calls + calibration, (b) retrieval-only on the labelled relevance judgments using TREC metrics (Recall@5/100/1000, nDCG@10).

**Lesson for us**: a frozen corpus + per-task labelled relevance pool is now the field standard for reproducibility. Our sandbox is a frozen corpus already; we need labelled relevance per task (this is what `must_cite_urls` and `expected_pool_urls` already do, but needs IAA).

### 1.4 GAIA (Mialon et al., arXiv 2311.12983)

450 questions, exact-string-match answers, three difficulty levels:
- Level 1 — fewer than 5 steps
- Level 2 — 5–10 steps
- Level 3 — up to 50 steps

Headline philosophy: **human ≥ machine**. Humans score 92%, GPT-4 with plugins scores 15%. GAIA explicitly rejects "harder for humans" benchmarks; it argues AGI's milestone is *matching* average human robustness on *human-easy* questions.

**Lesson for us**: difficulty calibration should target a human-attainable ceiling. Our deep tasks should be solvable by a competent human researcher in a finite-but-real time budget (e.g. 4 hours), not infeasibly hard.

### 1.5 WebArena-Verified (ServiceNow, OpenReview)

Re-audit of WebArena's 812 tasks. Replaces brittle string-match scoring with:
- type- and normalization-aware comparators,
- backend state verification (REST API + DB queries),
- structured JSON schema with explicit status codes for deterministic scoring,
- 258-task hard subset for cost-effective evaluation,
- reproducibility checksums on every score.

**Lesson for us**: state-based deterministic verification is more robust than answer-text parsing. We already do this with URL reachability (HTTP 200 = state check), but should add fact-triple-level state checks where possible.

---

## 2. Multi-hop QA: how multi-source synthesis is annotated

### 2.1 HotpotQA (Yang et al., 2018)

Each example: question, answer span (Wikipedia), **sentence-level supporting facts**. Crowdsourced. Strong supervision: not just *which document* supports an answer, but *which sentence within it*.

### 2.2 MuSiQue (Trivedi et al., TACL 2022)

Bottom-up composition: take pairs of single-hop questions, filter so each hop is *indispensable* and the chain is *connected*. Filters specifically prevent disconnected reasoning and shortcut artefacts. Sentence-level supervision identical to HotpotQA but built systematically rather than crowdsourced.

**Lesson for us**: the synthesis dimension of our task (cross-source contradiction finding, brand sentiment ranking) is the multi-hop part. Today our golden has triples but does NOT supervise *which evidence sentence* supports each claim. If we want CiteEval-style audit, we need quote-span annotation per cited URL.

---

## 3. Citation / attribution evaluation — the verifier suite

### 3.1 RARR (Gao et al., arXiv 2210.08726)

Retrofit attribution by post-editing: search for evidence, then revise unsupported sentences. Established the "attribution as research" paradigm. The relevant signal for us: **claim-level rewriting after external retrieval** is doable; per-claim attribution is the right granularity.

### 3.2 AttributedQA (Bohnet et al., 2022)

Benchmarks LLM attribution at QA scale. Demonstrated NLI-style entailment between cited evidence and answer is a workable proxy for human-judged attribution.

### 3.3 CiteEval (arXiv 2506.01829, 2025)

Principle-driven citation evaluation. Critique of pure NLI: NLI loses context (user query, full retrieval set). CiteEval scores citations on supportiveness, source quality, *and* whether better cites were available in the retrieval pool. Moves beyond entailment to "what would a human grader call a good citation".

### 3.4 CiteAudit (arXiv 2602.23452, 2026)

Multi-agent citation verification pipeline: claim extraction → evidence retrieval → passage matching → reasoning → calibrated judgment. Targeted at scientific writing. Found that ≥100 NeurIPS-2025-accepted papers had at least one fabricated citation that all 3+ peer reviewers missed. **Direct evidence that human review does not catch URL fabrication at scale; deterministic verification is needed.**

### 3.5 VeriCite (SIGIR-AP 2025)

RAG-specific rigorous citation verification. Establishes that retrieval-grounding alone does NOT prevent citation errors; downstream verification is required.

### 3.6 ReClaim (arXiv 2407.01796)

NLI-based claim/citation matching with threshold θ = 0.8 — i.e. only retain citation–claim pairs with NLI entailment probability > 0.8 as "verified". This is a concrete, citeable threshold for our claim-quote NLI verifier (Section 9).

### 3.7 "Why Your Deep Research Agent Fails?" (arXiv 2601.22984, 2026)

Most directly relevant prior work. Defines **PIES taxonomy** for DR-agent hallucination:

| Type | What it is |
|---|---|
| **Explicit Summarization** | Fabrication (claim unsupported by any document) + Misattribution (citing a doc that does not support the claim) |
| **Implicit Summarization** | Failing to use retrieved relevant docs (Noise Domination) |
| **Explicit Planning** | Plans that drift from user intent or propagate prior fabrications (Action Hallucination) |
| **Implicit Planning** | Plan technically executes but silently ignores user constraints (Restriction Neglect) |

Companion benchmark **DeepHalluBench** (100 queries). Evaluation pipeline: retrieve-then-verify (embedding + reranker), then NLI-then-LLM cascade (NLI is the gatekeeper, LLM only adjudicates ambiguous cases). Reported overall hallucination scores for frontier DR agents: 0.149–0.208 (Qwen best, Perplexity worst). Crucially, **OpenAI and Grok are flagged as "confident fabricators"** (high fabrication, low misattribution): they invent claims wholesale rather than misciting real ones — exactly what we observe with gpt-researcher + DeepSeek-V4 in our v0 audit.

Validated against human labels: claim verification pipeline matches human at ~95% on FEVER and >85% on SciFact-Open.

**Lesson for us**: PIES taxonomy is the right frame for our F5/F6 findings; we should map our verifier outputs onto PIES axes in the paper.

---

## 4. Gold-answer construction protocols (cross-domain)

### 4.1 Wikipedia Featured Article (FA) criteria

Most mature human protocol for "long-form, claim-cited reports". Requirements relevant to us:
- "verifiable against high-quality reliable sources" with "consistently formatted inline citations"
- Per-claim citation expected where the claim is contentious; bundling allowed for non-contentious paragraphs but the bundled footnote must make clear which source supports which point
- Multi-stage peer review (FAC nomination + reviewer panel), no single author wraps it up

### 4.2 Cochrane systematic review

Domain-expert protocols for medical evidence synthesis: (i) prospectively-registered protocol; (ii) ≥2 independent reviewers screen + extract data; (iii) disagreements resolved by a third reviewer; (iv) IAA reported in the methods section.

**Mapping to us**: our golden_pool should be reviewed by ≥2 annotators with disagreements adjudicated. We should report IAA on a sample.

### 4.3 Inter-annotator agreement thresholds

Two scales widely used:

| Source | "Substantial" | "Excellent" / "Almost perfect" |
|---|---|---|
| Landis & Koch (1977) | κ = 0.61–0.80 | κ = 0.81–1.00 |
| Fleiss (1981) | κ = 0.40–0.75 ("fair to good") | κ > 0.75 |

Modern NLP practice (per several agreement-metric guides): **κ ≥ 0.75 is the conventional minimum for binary tasks**, κ ≥ 0.80 for production-grade datasets. Krippendorff's α used when missing data or > 2 annotators.

**For us**: target κ ≥ 0.75 on (a) is-this-URL-must-cite-worthy, (b) does-this-claim-need-citation, (c) is-this-checklist-item-PASS-or-FAIL. Below 0.65 = the question is ill-defined; rewrite it.


---

## 5. Difficulty calibration

### 5.1 GLUE / SuperGLUE protocol

Tasks were chosen so that human performance was around the 80–90% mark and SOTA at release was 30–50%. As models improved, GLUE saturated within ~12 months and was replaced. SuperGLUE was redesigned so that human performance stayed at ≥90% but SOTA at release was 71% — leaving headroom.

### 5.2 GAIA's ceiling rule

GAIA's 92% human / 15% GPT-4 split is the explicit anchor. The benchmark designers argue that "machine ≥ human" benchmarks are bad signals for AGI; the right target is robustness on tasks humans handle without trouble.

### 5.3 BIG-bench / HELM lessons

BIG-bench (204 tasks, 450 contributors) found that **task diversity matters more than task hardness** for predictive recoverability. Capability scaling is predictable from task-diversity coverage at R² > 0.95 across 56k+ runs. HELM uses an explicit top-down structure (scenario × metric grid) so that no single task type dominates.

### 5.4 Calibration for us

For the deep-tier benchmark, the operational target is:
- A **competent human researcher** with full sandbox access can produce a passing report (composite ≥ 0.5) in **3–4 hours per task**.
- A **frontier DR agent** (Sonnet-4 / GPT-5 / Qwen) on best-current-protocol scores **0.30–0.50**. Below 0.30 means the task is too hard and the benchmark won't differentiate; above 0.65 means saturation incoming.
- Empirically from v0: the 5 OSS agents we tested cluster at 0.01–0.28 on the truthfulness-first composite. That suggests our v0 task is *too hard* (or, more precisely, the task is fine but the agents are weaker than we thought).

We should **measure the human ceiling** before scaling: have one of us (or a contractor) actually do the task in 4 hours and score it.

---

## 6. Citation format standards

### 6.1 Inline numbered `[N]` vs markdown `[label](url)` vs structured JSON

Three formats in current use:

| Format | Used by | Pros | Cons |
|---|---|---|---|
| Numbered `[1]` + bibliography | STORM, Wikipedia, academic | Reads like a paper | Verifier must join citation→bibliography first |
| Markdown `[label](url)` | gpt-researcher, smolagents, DeerFlow | Self-contained, easy to extract | Visually noisier; agents sometimes cite the same URL 5x |
| Structured JSON | research APIs, OpenScholar | Machine-clean | No human consumption; agents must be patched |

**Our choice**: require markdown `[label](url)` in-line AND a parsed bibliography appendix (so `[N]` → URL is also recoverable). This dual requirement was effective for STORM in our v0 (it natively writes `[N]` + url_to_info.json).

### 6.2 Required metadata per citation

Per CiteEval and CiteAudit, the minimum publishable metadata per cited URL is:
- **URL** (canonical, schema-normalised)
- **Quoted span** from the source page that supports the claim (≤ 200 chars)
- **Claim text** (the sentence being supported)

A verifier can then run NLI(quoted_span, claim_text) to score support strength. Without quoted span, you can only check URL reachability — you cannot verify *whether the URL supports the claim*.

### 6.3 Machine-verifiability

Three layers, each cheaper than the next:
1. **HTTP reachability** — `curl -I` / GET, 200 means real URL. Free, instant, catches Fabrication-class errors.
2. **Quote-on-page check** — fetch URL, fuzzy-match the quoted span. Catches misattribution at the document level.
3. **NLI entailment** — run claim against quoted span (or full page). Catches misattribution at the claim level. Threshold: θ = 0.80 from ReClaim.

Our v0 has only layer 1. Layer 2 + 3 are the gap.

---

## 7. Task diversity axes (what "10 tasks" actually means)

A diverse benchmark must span axes other than topic. From BIG-bench / HELM / DeepResearch Bench:

### 7.1 Axis A: topic / domain

DRBench's 22-field taxonomy is a strong baseline. Our v0 is single-domain (consumer goods). For statistical strength, ≥ 5 domains, ≥ 2 tasks each.

### 7.2 Axis B: intent type

This is what our template-cloned v0 missed. From a survey of DRBench task types:
- **Comparison** ("compare X and Y on Z dimensions")
- **Enumeration / catalog** ("list every Z that has property W")
- **Timeline / evolution** ("how has X changed from year A to B?")
- **Causal explanation** ("why did X happen?")
- **Debunking / fact-check** ("which of these claims about X are false?")
- **Recommendation / decision-support** ("given constraints C, what should I buy / read / do?")

A 10-task benchmark should hit **at least 4 of 6** intent types.

### 7.3 Axis C: synthesis style

What the report has to *do* with the harvested information:
- **Ranking** (rank N items on metric M)
- **Taxonomy / clustering** (group findings into categories)
- **Contradiction finding** (where do sources disagree?)
- **Gap analysis** (what is *missing* from the available data?)
- **Causal inference** (which factor explains an effect?)

### 7.4 Axis D: difficulty tier

Per Section 5: easy / medium / hard. v1 should fix all tasks at *medium* to remove difficulty as a confounder; v2 introduces an ablation across tiers.

### 7.5 Axis E: dimension count (1, 2, 3 sandbox sources required)

Single-source tasks (only Magento, only Wiki) are useful as a control: do agents fabricate even when one source is enough?

---

## 8. Sample size, contamination, and reproducibility

### 8.1 Power analysis

Standard NLP convention is α = 0.05, power = 0.80. For *agent-on-task* matrices, the effective N is n_agents × n_tasks. At a between-agent effect size of d = 0.5 (Cohen's medium) the minimum N for two-sided power 0.80 is n ≈ 64 — i.e. **with 5 agents, ≥ 13 tasks** gives statistical separation between agents. With 8 agents (which we should grow to), 8 tasks is the floor.

Conclusion: **8–13 hand-built tasks is the statistical floor**, not 1.

### 8.2 Contamination defenses

Wikipedia is in every frontier model's training corpus. Issues for us:
- The mandatory Wikipedia articles are likely in the model's prior. Agents can "answer" the technical-grounding dimension from prior alone, not retrieval.
- Defense: include ≥ 2 *adversarial* Wiki articles per task that share a name with a real Wiki page but differ on a key fact (only present on the Kiwix mirror). Models that go from prior get the factoid wrong; models that retrieve get it right.
- TS-Guessing (mask part of test, ask model to fill) lets us *measure* contamination per task in advance.

### 8.3 Reproducibility

WebArena-Verified standard:
- Pinned Docker image digests for sandbox containers
- Network-trace replay so scoring does not require live network
- Checksum every score artefact

Our equivalent should also include: pinned ds_proxy / shim versions, stamped backbone model id (and judge model id) per run, frozen golden hash per task.

---

## 9. Concrete design decisions for `dr_arena_deep` v1

Each decision below has a citation to prior work that justifies it.

1. **Hand-author every task end-to-end.** No template cloning. Each task has its own domain-expert author, intent type, synthesis requirement, and authorial review. Cite: DRBench (100/100 expert-authored), BrowseComp (1266/1266 trainer-authored), GAIA (450/450 hand-validated).

2. **Target 12 tasks for v1.** Below the statistical floor (8) is anecdote; above 20 is unaffordable single-author work. 12 hits the n-power threshold for 5 agents with d = 0.5. Cite: Section 8.1 power analysis.

3. **Diversity grid for the 12.** 4 domains × 3 intent types (comparison / enumeration / debunking) × 1 difficulty tier (medium). Topics: 3× consumer goods, 3× scientific (e.g. medication interactions, climate facts, public-health claims), 3× current-affairs (e.g. recent news with cross-source check), 3× technical (e.g. open-source SW landscape). Cite: BIG-bench (diversity > hardness), HELM (scenario × metric grid).

4. **Two-annotator gold construction.** For each task: (a) author drafts intent + must-cite + checklist; (b) reviewer independently re-builds the must-cite list from the author's intent only; (c) overlap is reported as IAA. Tasks with κ < 0.65 on must-cite go back for redesign. Cite: Cochrane protocol, Landis & Koch κ thresholds.

5. **Citation format: dual.** Markdown `[label](url)` in-line + bibliography. Per claim, the agent SHOULD provide a quoted span (we can score with or without; agents that include it get a precision bonus on the NLI verifier). Cite: STORM uses `[N]` natively; CiteEval requires quoted spans for fine-grained scoring.

6. **Three-layer citation verification.**
   - Layer 1: URL reachability (`URLReachabilityVerifier`) — already built.
   - Layer 2: quote-on-page (fuzzy match quoted span against fetched page text).
   - Layer 3: NLI claim ↔ quoted span at θ ≥ 0.80. Use DeepSeek-V4-flash (non-reasoning) as NLI judge; cross-validate a 100-claim sample against human labels per ReClaim. Cite: ReClaim, CiteEval, CiteAudit.

7. **Truthfulness-first composite, multiplicative.**
   `composite = reachability × (0.40·url_coverage + 0.40·judge_pass + 0.20·spec_pass)` (existing). Add a second composite that includes layer 3 NLI: `composite_v2 = reachability × claim_support_rate × quality`. Report both. Cite: our own F6.

8. **Human ceiling per task.** Before publishing v1, one human researcher attempts each task with 4-hour budget; their composite score is the ceiling. Tasks where humans score < 0.50 are too hard; rewrite. Cite: GAIA's "human ≥ machine" rule.

9. **Adversarial wiki entries for contamination defense.** ≥ 2 wiki articles per task whose Kiwix-served content differs subtly from the public Wikipedia version on a load-bearing fact. Agents going from prior fail; agents that retrieve win. Cite: data contamination surveys (Survey 2406.04244, ICML 2025 leakage poster).

10. **Frozen sandbox + network-trace replay.** Pin Docker digests; record every shim search and HTTP request during agent runs so a failed score can be re-audited offline. Cite: WebArena-Verified.

11. **Cross-family judge always.** Backbone DeepSeek-V4 → judge GPT-5-chat. If we add a Claude-backbone agent later, the judge must be GPT-or-DeepSeek (anything but Claude). Cite: JudgeBench.

12. **Stamp identities on every score.** judge model id, judge proxy URL, backbone model id, ds_proxy commit, sandbox image digest. So that "did the judge non-determinism move the score?" is auditable. Cite: WebArena-Verified reproducibility checksums.


---

## 10. Mapping our v0 findings onto prior taxonomies

To position the paper:

| v0 finding | Maps to | Specific PIES axis |
|---|---|---|
| gpt-researcher / langchain-odr emit URL paths that 404 (`/products/anker...`, `/wiki/Bluetooth`) | **Fabrication** (Explicit Summarization) | High Fabrication, Low Misattribution = "confident fabricator" archetype, identical to OpenAI/Grok in Why-Your-DR-Fails |
| smolagents emits a mix of real + invented URLs | **Misattribution** + Fabrication | Mixed: cites some retrieved URLs but invents brand names not in sandbox |
| GPT-5-chat judge gives 21/21 PASS to 100%-fabricated reports | **F5 (ours): LLM judge blind to fabrication** | New finding; CiteAudit shows similar for *human* peer review (≥100 NeurIPS-25 fabrications missed). Combined: neither cheap LLM judges nor expensive human reviewers catch URL hallucination at scale → deterministic verifier is the only reliable layer |
| Composite ranking inverts when reachability is enforced | **F6 (ours): truthfulness/quantity tradeoff** | New finding; not directly framed in prior work but closest is BrowseComp-Plus's separation of "agent" vs "retrieval-only" eval modes |

The paper section on related work writes itself from this table.

---

## 11. Concrete pilot — "one task done right" recipe

Before any v1-of-12 push, we redo `dr_cross_deep_0001` end-to-end as a methodology proof. The recipe below is what the next contributor should follow on the next task too.

### Step 1: Pre-registration (30 min)

Author writes a 1-page pre-reg before scraping:
- Topic + intent type (one of 6 from §7.2)
- Synthesis style (one of 5 from §7.3)
- Mandatory must-cite count target (e.g. 60)
- Per-domain must-cite minimums (shopping/reddit/wiki)
- 21 binary checklist items (PASS/FAIL/UNCLEAR per CiteAudit phrasing)

### Step 2: Author scrape (1–2 hours)

Run `build_deep_golden.py --topic-config T.yaml`. Inspect output: is must_cite ≥ pre-reg target? Are domains balanced? If no, expand keyword/forum lists, re-scrape.

### Step 3: Author quote annotation (4–6 hours)

For each must-cite URL, fetch the page and add a `quoted_span` field — the ≤200-char passage the agent SHOULD cite when using this URL. This is the labour-intensive step but it's what unlocks claim-quote NLI verification (Layer 3).

### Step 4: Independent reviewer pass (3–4 hours)

A second person, given ONLY the task intent + checklist:
- Independently produces a must-cite list from the sandbox.
- Score Cohen's κ between author's must-cite and reviewer's must-cite.
- Resolve disagreements jointly. Aim for κ ≥ 0.75.
- Reviewer flags any must-cite URL whose author quote does not actually support the entailed claim.

### Step 5: Human-attempt baseline (4 hours)

A third person (or one of the first two with a cooldown) attempts the task as if they were the agent: 4-hour budget, browser + sandbox + their own notes. Their report is scored with the same composite. This is the **human ceiling**.

### Step 6: Publish + machine-baseline (1 hour run-time)

Run all 5 OSS agents under same protocol. Score with composite v2 (reachability × claim_support × quality). Publish the task + golden + checklist + human baseline + agent baselines together. NO task ships without a human baseline.

### Step 7: Continuous audit (ongoing)

Every 30 days, re-run a random 10% of cited URLs through reachability. If reach drops below 95%, the sandbox containers have drifted; pin a new digest, re-scrape, re-publish.

---

## 12. Tooling we still need to build

Currently built (v0):
- `URLCoverageVerifier` (golden-pool-based)
- `URLReachabilityVerifier` (curl-based, sequential w/ retries)
- `score_deep_answer.py` (composite v1)
- `build_deep_golden.py` (scraper)
- `gen_task_from_topic.py` (template task gen — to be DEPRECATED for v1)

Missing for the recipe above:
- **`quote_match_verifier.py`** (Layer 2): given (cited_url, quoted_span), fetch URL, fuzzy-match span, score 1 if found else 0.
- **`claim_nli_verifier.py`** (Layer 3): given (claim_text, quoted_span), call DeepSeek-V4 (non-reasoning) NLI prompt, return entailment probability; threshold θ ≥ 0.80.
- **`iaa_score.py`**: given two annotators' must-cite lists, compute Cohen's κ + Krippendorff α.
- **`task_preregistration.md` template** (one per task) for Step 1.
- **`run_human_baseline.md`** protocol — how the human attempt is logged.
- **`adversarial_wiki_inject.py`** — patch Kiwix to serve a modified copy of N specified articles, with a delta log so the verifier knows what was changed.

These six pieces are the engineering work for the next milestone.

---

## 13. Open questions / future work

- **NLI judge cross-validation**: ReClaim's θ = 0.80 is from a different domain. We should sample 200 of our claims, hand-label entailed/not-entailed, and recalibrate θ.
- **Topic-distribution grounding**: DRBench used 96K real queries to set topic balance. We don't have a query log. Do we (a) borrow a public log, (b) sample from BrowseComp's question set, or (c) declare "consumer-goods focus" and own it?
- **Sandbox extension**: 3 sandbox sources is the minimum for "cross-source synthesis". Adding a 4th source (e.g. arxiv mirror, GitHub clone) increases task design space.
- **Open-web parity**: a stretch goal is to pair each sandbox task with an open-web variant whose URLs are pinned to Wayback snapshots, so we can compare closed-sandbox vs frozen-open-web.
- **Multi-language**: DRBench's 22 fields are English-only. Cross-lingual is open.

---

## References

The following arXiv / OpenReview / blog citations are the load-bearing evidence in this doc. Numbers are arXiv ids unless noted.

- DeepResearch Bench — 2506.11763
- BrowseComp — 2504.12516 (OpenAI release April 2025)
- BrowseComp-Plus — github.com/texttron/BrowseComp-Plus, ACL 2026 main
- GAIA — 2311.12983
- WebArena-Verified — OpenReview CSIo4D7xBG (ServiceNow)
- HotpotQA — 1809.09600
- MuSiQue — TACL 2022
- RARR — 2210.08726
- CiteEval — 2506.01829
- CiteAudit — 2602.23452
- VeriCite — 2510.11394
- ReClaim — 2407.01796
- "Why Your Deep Research Agent Fails?" — 2601.22984
- BIG-bench — 2206.04615
- HELM — 2211.09110
- Data-contamination survey — 2406.04244
- Cohen's κ — Landis & Koch 1977; Fleiss 1981; modern conventions per Cleverx / iMerit / Keymakr annotation guides
- Wikipedia FA criteria — en.wikipedia.org/wiki/Wikipedia:Featured_article_criteria
- JudgeBench — ICLR 2025

