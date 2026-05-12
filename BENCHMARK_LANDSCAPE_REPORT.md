# Deep Research Agent Benchmarks & Evaluation: Landscape Report

**Date**: 2026-04-30  
**Purpose**: Comprehensive survey of DR agent benchmarks/evaluation methods (2024-2026), gap analysis against our setup, and actionable recommendations.

---

## 1. Catalog of Existing DR Benchmarks

The table below lists every major benchmark specifically targeting deep-research / automated-research agents, ordered by release date.

| Benchmark | Year | Venue | # Tasks | # Domains | Output Type | Corpus | # Systems Evaluated |
|-----------|------|-------|---------|-----------|-------------|--------|---------------------|
| **GAIA** | 2023 (ICLR 2024) | ICLR | 450 | broad (multi) | Short answer | Live web | 20+ on leaderboard |
| **FanOutQA** | 2024 (ACL 2024) | ACL | 1,034 | Wikipedia-based | Short answer | Closed (Wikipedia snapshot) | 7 |
| **FRAMES** | 2024 (NAACL 2025) | NAACL | 824 | Multi (history, science, sports...) | Short answer | 2-15 Wikipedia articles/q | Multiple RAG systems |
| **WebArena** | 2023 (updated 2025) | NeurIPS | 812 | E-commerce, forums, CMS, dev | Task completion | Sandbox (Docker containers) | 15+ |
| **AssistantBench** | 2024 | arXiv | 214 | Travel, real estate, product, business | Short answer | Live web | Multiple |
| **BrowseComp** | Apr 2025 | OpenAI | 1,266 | Broad (fact-seeking) | Short answer | Live web | 5 (GPT-4o, GPT-4.5, o1, GPT-4o+browse, Deep Research) |
| **DeepResearchGym** | May 2025 | arXiv | ~1,000 (Researchy Questions) | Broad | Long-form report | Sandbox (ClueWeb22 + FineWeb, DiskANN) | Multiple |
| **DeepResearch Bench (DRB I)** | Jun 2025 | arXiv / OpenReview | 100 | 22 fields | Long-form report | Live web | 8+ (Gemini DR, Perplexity DR, OpenAI DR, etc.) |
| **Humanity's Last Exam (HLE)** | Jan 2025 (Nature 2025) | Nature | 2,500 | 90+ specialist areas | Short answer | N/A (closed-book primarily) | 10+ |
| **ResearchRubrics** | Nov 2025 (ICLR 2026) | ICLR | 101 | 9 domains | Long-form report | Live web | 3 (OpenAI DR, Gemini DR, Perplexity DR) |
| **Dr. Bench** | Oct 2025 | arXiv / OpenReview | 214 | 10 domains | Long-form report | Live web | 13 |
| **DRBench (Enterprise)** | Oct 2025 | arXiv | 100 | 10 enterprise domains | Long-form report | Sandbox (Nextcloud, Mattermost, Roundcube, etc.) | Multiple |
| **LiveResearchBench** | Oct 2025 | Salesforce / arXiv | 100 | 7 domains, 10 task categories | Long-form report | Live web (dynamic) | 17 |
| **ReportBench** | 2025 | OpenReview | 21K / 10K / 0.6K | Academic survey | Survey report | Academic literature | Multiple |
| **DeepSearchQA** | Dec 2025 | Google DeepMind / Kaggle | 900 | 17 fields | Exhaustive answer lists | Live web | Multiple (Kaggle leaderboard) |
| **DeepResearch Bench II (DRB II)** | Jan 2026 | arXiv | 132 | 22 domains | Long-form report | Live web | Multiple |
| **DRACO** | Feb 2026 | Perplexity / arXiv | 100 | 10 domains (40 countries) | Long-form report | Live web | 7 |
| **MMDeepResearch-Bench** | Jan 2026 | arXiv | 140 | 21 domains | Multimodal report | Live web + images | 25 |
| **ResearcherBench** | Jul 2025 | SII-GAIR / arXiv | 65 | 35 AI research subjects | Research report | Live web | Multiple |
| **BrowseComp-Plus** | 2025 (ACL 2026) | ACL | 830 | Same as BrowseComp | Short answer | Fixed corpus (~100K docs) | Multiple |
| **DeepScholar-Bench** | 2025 (NeurIPS) | NeurIPS | Dynamic (ArXiv-based) | Academic CS | Related-work section | Live web (ArXiv) | Multiple |
| **DR³-Eval** | Apr 2026 | arXiv | Multiple | Multi | Multi-file report | Per-task sandbox corpus | Multiple |

---

## 2. How DR Frameworks Are Evaluated in Their Papers

### 2.1 Commercial / Closed Systems

| System | Evaluation Method | Benchmarks Used | Metrics Reported | Human Eval? |
|--------|-------------------|-----------------|------------------|-------------|
| **OpenAI Deep Research** | Internal expert eval + BrowseComp | BrowseComp (51.5%), HLE (26.6%) | Accuracy, expert time-equivalence | Yes (domain experts rated hours saved) |
| **Gemini Deep Research** | DeepSearchQA + BrowseComp + HLE | DeepSearchQA (66.1%→93.3%), BrowseComp (59.2%→85.9%), HLE (46.4%) | Accuracy, comprehensiveness, pass@k | Limited |
| **Perplexity Deep Research** | DRACO (self-published benchmark) | DRACO (70.5% normalized score) | Factual accuracy, breadth/depth, presentation, citation quality | Rubric-based LLM judge |

### 2.2 Open-Source / Academic Systems

| System | Paper | # Eval Tasks | Metrics | Human Eval? |
|--------|-------|-------------|---------|-------------|
| **STORM** (Stanford, 2024) | NAACL 2024 | 100 (FreshWiki) | Heading Soft Recall, Entity Recall, citation recall/precision (Mistral 7B judge: 84.83% supported) | Yes: 10 Wikipedia editors, 20 article pairs |
| **Co-STORM** (Stanford, 2024) | arXiv | Same FreshWiki | Same + discourse coherence, topic coverage | Yes: Wikipedia editors |
| **MindSearch** (2024) | arXiv | 100 open-set + 3 closed-set benchmarks (Bamboogle, Musique, HotpotQA) | Depth, breadth, factuality (open-set); accuracy (closed-set) | Yes: 5 human experts, blind evaluation, majority-vote |
| **GPT-Researcher** (GPTR) | Blog / DeepResearchGym eval | ~1,000 (via DeepResearchGym) | Citation quality, report quality, information coverage | No |
| **DeerFlow** (ByteDance) | Evaluated in LiveResearchBench | 100 | Coverage, citation accuracy, presentation, consistency | Via LLM judge with human alignment validation |
| **AutoSurvey** (2024) | arXiv | Not standardized | Survey creation speed, citation quality, Multi-LLM-as-Judge (correlation with human: 0.5429) | Limited |

### 2.3 Key Observation

Most DR framework papers use **ad-hoc evaluation** rather than a standardized benchmark. Common patterns:
- Proprietary systems benchmark on their own tests (DRACO by Perplexity, BrowseComp by OpenAI, DeepSearchQA by Google)
- Open-source systems either evaluate on small custom sets (MindSearch: 100 queries) or piggyback on general benchmarks (GAIA)
- Standardized cross-system comparison only became possible in late 2025 with LiveResearchBench (17 systems) and Dr. Bench (13 systems)

---

## 3. Scale Comparison

### 3.1 Task Count Distribution

| Scale Tier | Benchmarks | Notes |
|------------|-----------|-------|
| **Small (< 100)** | ResearcherBench (65), **Ours (30)** | Acceptable for pilot; underpowered for statistical significance |
| **Medium (100-250)** | DeepResearch Bench (100), DRACO (100), LiveResearchBench (100), ResearchRubrics (101), Dr. Bench (214), AssistantBench (214), DRB II (132), MMDeepResearch-Bench (140) | **Industry standard for DR-specific benchmarks** |
| **Large (250-1000)** | GAIA (450), FRAMES (824), BrowseComp (830/1266), DeepSearchQA (900), WebArena (812), FanOutQA (1034) | Mostly short-answer / task-completion, not long-form |
| **Very Large (1000+)** | HLE (2500), ReportBench (21K) | HLE is not DR-specific; ReportBench is academic-only |

**Median for DR-specific long-form benchmarks: ~100 tasks.**

### 3.2 Number of Systems Compared

| Benchmark | # Systems |
|-----------|-----------|
| LiveResearchBench | **17** (highest) |
| Dr. Bench | **13** |
| DeepResearch Bench | 8+ |
| DRACO | 7 |
| MMDeepResearch-Bench | 25 (models, not full DR systems) |
| ResearchRubrics | 3 |
| **Ours** | **7+** |

**Typical evaluation matrix: 100 tasks x 5-17 systems = 500-1,700 runs.**

### 3.3 Our Matrix

- 30 tasks x 7 agents = **210 runs** (below typical 500-1,700)
- Need to scale to at least 100 tasks to match the field standard

---

## 4. Evaluation Dimensions: Industry Consensus

Synthesizing across all benchmarks, the field has converged on these evaluation dimensions:

### 4.1 The Six Pillars

| Dimension | Who Uses It | How Measured | Our Coverage |
|-----------|-------------|--------------|--------------|
| **1. Factual Accuracy** | DRACO (~50% of rubric weight), RACE, Dr. Bench, ResearchRubrics, LiveResearchBench | LLM judge against rubric criteria; claim extraction + verification | Partial (checklist_judge covers this implicitly) |
| **2. Comprehensiveness / Coverage** | DeepSearchQA (primary metric), RACE, LiveResearchBench, DRB II (InfoRecall) | Rubric checklist completeness; entity/topic recall vs. reference | Partial (checklist_judge + url_coverage) |
| **3. Citation / Attribution Quality** | ALCE, FACT, DRACO, LiveResearchBench, MMDeepResearch-Bench (TRACE) | Citation recall/precision; URL validity; claim-source alignment | Yes (url_coverage + reachability) but **missing claim-source alignment** |
| **4. Presentation / Readability** | DRACO, RACE, LiveResearchBench, DRB II | LLM judge on organization, coherence, structure | No (not measured) |
| **5. Analysis Depth / Insight** | DRB II (Analysis), ResearchRubrics (reasoning soundness), ResearcherBench | Pairwise comparison or rubric-based | No (not measured) |
| **6. Instruction Following** | RACE, DR³-Eval | Compliance with format/length/scope constraints | Partial (spec_compliance) |

### 4.2 Extended Dimensions (Used by Some)

| Dimension | Where Used | Our Coverage |
|-----------|------------|--------------|
| Semantic Drift / Topical Focus | Dr. Bench (SemanticDrift metric) | No |
| Hallucination Rate | DeepScholar-Bench, DR³-Eval | No (explicit measurement) |
| Efficiency (latency, cost, tokens) | DRACO (latency), our SCORING_FRAMEWORK v2 | Partial (planned, not active) |
| Multimodal Grounding | MMDeepResearch-Bench (MOSAIC) | No |
| Distractor Avoidance | DRBench Enterprise | No |
| Reproducibility | BrowseComp-Plus, DeepResearchGym, DR³-Eval | **Yes (sandbox = our strength)** |

### 4.3 Scoring Formulas in the Field

| Benchmark | Formula |
|-----------|---------|
| Dr. Bench | `IntegratedScore = Quality × (1 - SemanticDrift) × TrustworthyBoost × 100` (range 0-120) |
| DRACO | Binary per-criterion LLM judge → average pass rate across 4 axes |
| LiveResearchBench (DeepEval) | 6 separate sub-scores (0-100 each), reported individually + averaged |
| DRB II | % of 9,430 binary rubrics satisfied |
| ResearchRubrics | Ternary verdicts (satisfied/partial/not) → weighted sum, normalized |
| **Ours** | `url_coverage × reachability × checklist_judge × spec_compliance` (multiplicative composite) |

**Notable**: Our multiplicative formula is unusual. Most benchmarks use additive weighted sums. A multiplicative approach means one zero dimension kills the entire score, which may be overly harsh.

---

## 5. Sandbox vs. Live-Web: Where We Stand

### 5.1 The Reproducibility Problem

The field has recognized that live-web evaluation has serious flaws:
- **BrowseComp-Plus (ACL 2026)**: Created specifically because BrowseComp's reliance on live APIs makes results non-reproducible and unfair (different API versions, rate limits, content changes)
- **DeepResearchGym (CMU, 2025)**: Built a static corpus sandbox (ClueWeb22 + FineWeb) because "most existing frameworks rely on dynamic commercial search APIs, which pose reproducibility and transparency challenges"
- **DR³-Eval (Apr 2026)**: Uses per-task static research sandbox corpus that "simulates open-web complexity while remaining fully verifiable"
- **DRBench Enterprise (ServiceNow)**: Docker-based sandbox with Nextcloud, Mattermost, Roundcube

### 5.2 Our Sandbox Approach

Our setup (Magento + Postmill + Kiwix Wikipedia) is **methodologically well-positioned** — it aligns with the emerging best practice of controlled, reproducible environments. Key advantages:
- Deterministic content (no temporal drift)
- Full control over ground truth
- Fair comparison across agents (same retrieval surface)
- No API cost or rate-limit confounds

### 5.3 Limitations of Sandbox

- **Ecological validity**: Agents tuned for live web may underperform in unfamiliar sandbox
- **Domain coverage**: 3 sources (shopping + reddit + wikipedia) is narrow vs. real web
- **No dynamic content**: Cannot test agents' ability to handle conflicting/changing information
- **Transfer gap**: Performance in sandbox may not predict live-web performance

---

## 6. Detailed Gap Analysis

### 6.1 What We Have vs. What the Field Expects

| Aspect | Field Standard | Our Current State | Gap Severity |
|--------|---------------|-------------------|--------------|
| **Task count** | 100 (median for DR benchmarks) | 30 | **HIGH** — underpowered for statistical claims |
| **Domain coverage** | 10+ domains typical | 6-7 domains | MEDIUM — adequate if well-chosen |
| **Intent diversity** | Not standardized | 6 intent types | Good — unique differentiator |
| **Agent count** | 5-17 systems | 7+ | OK — in range |
| **Human evaluation** | Used by most top venues (STORM: Wikipedia editors; MindSearch: 5 experts; LiveResearchBench: 1,500 hrs) | **None** | **HIGH** — papers without human eval have weaker acceptance at top venues |
| **LLM judge validation** | Human-LLM alignment measured (LiveResearchBench: 82-100%; ResearchRubrics: F1 0.72-0.76) | No alignment validation | **HIGH** — must show judge reliability |
| **Factual accuracy** | Explicit dimension in 90%+ of benchmarks | Implicit in checklist_judge | MEDIUM — needs explicit extraction |
| **Citation-claim alignment** | ALCE, FACT, TRACE measure if claim is actually supported by cited URL | URL reachability only (binary) | **HIGH** — checking URL exists ≠ checking URL supports the claim |
| **Presentation quality** | Standard dimension | Not measured | MEDIUM |
| **Analysis depth** | Measured by DRB II, ResearcherBench | Not measured | MEDIUM |
| **Rubric granularity** | 20-43 criteria per task (ResearchRubrics), ~40 per task (DRACO) | ≥120 must-cite URLs per task | Different paradigm — URL-centric vs. criteria-centric |
| **Scoring formula** | Additive weighted (standard), or per-dimension reporting | Multiplicative composite | LOW-MEDIUM — defensible but unusual |
| **Sandbox reproducibility** | Emerging best practice (3-4 papers in 2025-2026) | **Yes** (Magento + Postmill + Kiwix) | **STRENGTH** — ahead of most |
| **Multi-judge ensemble** | ResearchRubrics uses 3 LLMs; DRACO uses 3 judges | Single judge | MEDIUM |
| **Inter-annotator agreement** | Reported when human eval exists | N/A | Needed if human eval added |

### 6.2 Statistical Power Concern

With 30 tasks and 7 agents:
- Cannot reliably detect effect sizes < 0.5 (Cohen's d) between agents
- Confidence intervals on per-agent scores will be wide
- Domain-level analysis (5 tasks/domain) is essentially anecdotal
- Cannot do meaningful stratified analysis by difficulty/intent

Comparison: Dr. Bench has 214 tasks x 13 agents = 2,782 evaluations. LiveResearchBench has 100 x 17 = 1,700. We have 210.

---

## 7. Recommendations (Prioritized)

### Priority 1: Critical (Do Before Submission)

#### R1. Scale to 100+ tasks
- Current 30 is below every published DR benchmark
- Target: 100 tasks across 10 domains (matching DRACO, LiveResearchBench, DeepResearch Bench)
- Keep the 6 intent types but increase to ~15-17 tasks per intent
- Add 3-4 more domains to reach 10 total

#### R2. Add citation-claim alignment verification
- URL reachability checks that a URL is live. It does NOT check that the cited URL actually supports the claim made in the report
- Implement: Extract (claim, URL) pairs from reports → fetch URL content → LLM judge whether content supports claim
- Reference implementation: ALCE (citation recall/precision), FACT framework, MMDeepResearch-Bench TRACE
- This is the single most important missing metric

#### R3. Add explicit factual accuracy scoring
- Separate from checklist compliance
- Approach: Extract atomic claims from report → verify each against sandbox ground truth or LLM judge
- DRACO allocates ~50% of rubric weight to factual accuracy

#### R4. Validate LLM judge with human annotations
- Sample 50-100 (task, report) pairs
- Have 2-3 human annotators score them on the same rubric used by LLM judge
- Compute inter-annotator agreement (Cohen's Kappa ≥ 0.75 target)
- Compute LLM-human alignment (target: F1 ≥ 0.70, per ResearchRubrics standard)
- This is essential for publication credibility

### Priority 2: Important (Strongly Recommended)

#### R5. Add presentation / readability dimension
- LiveResearchBench reports this as a separate 0-100 score with 10-point binary checklist
- Minimal implementation: LLM judge with structured rubric for organization, coherence, section structure, writing quality

#### R6. Add analysis depth dimension
- Distinguish "agent copied facts" vs. "agent synthesized insights"
- DRB II separates InfoRecall (retrieval) from Analysis (synthesis)
- Can be implemented as pairwise comparison (LiveResearchBench approach)

#### R7. Switch from multiplicative to additive scoring (or report both)
- Multiplicative scoring is defensible but non-standard
- If one dimension is 0, entire score is 0 regardless of other dimensions
- Recommendation: Report additive weighted composite as primary, keep multiplicative as a secondary "strict" score
- Reference weights from our SCORING_FRAMEWORK v2: Deterministic 0.30, Factuality 0.25, Citation 0.15, LLM Judge 0.15, Comprehensiveness 0.10, Efficiency 0.05

#### R8. Use multi-judge ensemble
- ResearchRubrics uses GPT-5 + Claude Sonnet 4.5 + Gemini 2.5 Pro
- DRACO uses Gemini-3-Pro + GPT-5.2 + Sonnet-4.5
- At minimum use 2 different LLM families; report rank-consistency across judges

### Priority 3: Nice-to-Have

#### R9. Add a small human evaluation study
- Even 20-30 tasks rated by 2 experts would significantly strengthen the paper
- MindSearch used only 5 experts on 100 queries; STORM used 10 Wikipedia editors on 20 pairs
- Focus human evaluation on dimensions hardest for LLM judges: analysis depth, practical usefulness

#### R10. Add hallucination detection
- Count fabricated facts, non-existent entities, impossible dates
- Particularly relevant in sandbox setting where ground truth is fully known

#### R11. Report efficiency metrics
- Latency, token usage, API cost per task
- DRACO reports latency (459-1808 seconds across systems)
- Differentiator: cost-performance Pareto frontier analysis

#### R12. Add distractor robustness testing
- DRBench Enterprise and DR³-Eval include distractors and noise in the corpus
- Our sandbox could inject misleading products, fake reddit posts, or contradictory Wikipedia edits

---

## 8. Comparison Summary: Our Setup vs. Top Benchmarks

| Feature | DeepResearch Bench | DRACO | LiveResearchBench | Dr. Bench | ResearchRubrics | **Ours** |
|---------|-------------------|-------|-------------------|-----------|-----------------|----------|
| Tasks | 100 | 100 | 100 | 214 | 101 | **30** |
| Domains | 22 | 10 | 7 | 10 | 9 | 6-7 |
| Output | Report | Report | Report | Report | Report | Report |
| Corpus | Live web | Live web | Live web | Live web | Live web | **Sandbox** |
| Reproducible | No | No | No (dynamic tasks) | No | No | **Yes** |
| Factual accuracy | RACE | ~50% rubric weight | Consistency dim | Quality metric | Factual grounding | Implicit |
| Citation quality | FACT | Dedicated axis | Citation accuracy + association | Trustworthy boost | Citation usage | URL coverage + reachability |
| Claim-source alignment | Yes (FACT) | Yes | Yes (rubric-tree) | Yes | Yes | **No** |
| Presentation | RACE | Yes | Yes (0-100) | SemanticDrift | Clarity | **No** |
| Analysis depth | Insight/Depth | Breadth/depth | Analysis Depth (pairwise) | Quality | Reasoning | **No** |
| Human eval | Expert judges | LLM-only | 1,500 hrs construction + alignment | Not reported | 9 annotators, 303 responses | **No** |
| LLM judge alignment | Not reported | Consistent across 3 judges | 82-100% human agreement | Not reported | F1 0.72-0.76 | **Not measured** |
| # Systems evaluated | 8+ | 7 | 17 | 13 | 3 | 7+ |
| Scoring | RACE + FACT | Binary rubric → pass rate | 6 sub-scores (0-100) | Multiplicative composite | Ternary → weighted | Multiplicative composite |
| Open-source | Yes | Yes | Yes | Yes | Yes (ICLR 2026) | Yes |

---

## 9. Unique Strengths to Emphasize

Despite gaps, our setup has distinctive strengths worth highlighting in a paper:

1. **Sandbox reproducibility**: Only DRBench Enterprise, DeepResearchGym, BrowseComp-Plus, and DR³-Eval share this property. Most benchmarks rely on non-reproducible live-web APIs. Position this as a methodological contribution.

2. **Multi-source sandbox**: Magento (e-commerce) + Postmill (social forum) + Kiwix (encyclopedia) mirrors the multi-domain structure of WebArena but adapted for research tasks. No other sandbox-based DR benchmark has this specific combination.

3. **Must-cite URL ground truth**: The ≥120 must-cite URLs per task with cross-source requirements provides a deterministic ground truth for citation evaluation that no live-web benchmark can offer.

4. **Intent-type taxonomy**: The 6 intent types (recommendation, comparison, debunking, causal, timeline, enumeration) provide a structured task categorization that most benchmarks lack.

5. **Cross-framework comparison**: Testing 7+ open-source agents in the same controlled environment is a fair comparison that live-web benchmarks cannot guarantee.

---

## 10. Suggested Positioning for Paper

Based on this analysis, the paper should position itself as:

> **"A reproducible, sandbox-based benchmark for deep research agents with deterministic ground truth"**

Key differentiators to claim:
- First DR benchmark combining e-commerce + social forum + encyclopedia sandbox sources
- Deterministic citation ground truth (vs. live-web approaches where ground truth shifts)
- Controlled, fair cross-agent comparison (same retrieval surface for all agents)
- Intent-type stratified analysis

Key limitations to acknowledge:
- Ecological validity gap (sandbox ≠ real web)
- Task count below field median (if not scaled to 100)
- No human evaluation (if not added)

---

## Sources

### Benchmarks
- [GAIA: a benchmark for General AI Assistants](https://arxiv.org/abs/2311.12983) — Meta, ICLR 2024
- [WebArena: A Realistic Web Environment](https://arxiv.org/abs/2307.13854) — CMU, NeurIPS 2023
- [BrowseComp: A Simple Yet Challenging Benchmark for Browsing Agents](https://openai.com/index/browsecomp/) — OpenAI, Apr 2025
- [BrowseComp-Plus: A More Fair and Transparent Evaluation](https://arxiv.org/abs/2508.06600) — ACL 2026
- [DeepResearch Bench](https://deepresearch-bench.github.io/) — arXiv 2506.11763, Jun 2025
- [DeepResearch Bench II: Diagnosing via Rubrics from Expert Report](https://arxiv.org/abs/2601.08536) — Jan 2026
- [Dr. Bench: A Multidimensional Evaluation for Deep Research Agents](https://arxiv.org/abs/2510.02190) — Oct 2025
- [DRACO: Cross-Domain Benchmark for Deep Research](https://arxiv.org/abs/2602.11685) — Perplexity, Feb 2026
- [LiveResearchBench: A Live Benchmark for User-Centric Deep Research](https://arxiv.org/abs/2510.14240) — Salesforce, Oct 2025
- [ResearchRubrics: Prompts and Rubrics For Evaluating Deep Research Agents](https://arxiv.org/abs/2511.07685) — Scale AI, ICLR 2026
- [DRBench: A Realistic Benchmark for Enterprise Deep Research](https://arxiv.org/abs/2510.00172) — ServiceNow, Oct 2025
- [DeepSearchQA: Bridging the Comprehensiveness Gap](https://storage.googleapis.com/deepmind-media/DeepSearchQA/DeepSearchQA_benchmark_paper.pdf) — Google DeepMind, Dec 2025
- [MMDeepResearch-Bench: Multimodal Deep Research Agents](https://arxiv.org/abs/2601.12346) — Jan 2026
- [ResearcherBench: Evaluating Deep AI Research Systems](https://arxiv.org/abs/2507.16280) — SII-GAIR, Jul 2025
- [DeepResearchGym: Reproducible Evaluation Sandbox](https://arxiv.org/abs/2505.19253) — May 2025
- [DR³-Eval: Realistic and Reproducible Deep Research Evaluation](https://arxiv.org/abs/2604.14683) — Apr 2026
- [DeepScholar-Bench: Live Benchmark for Generative Research Synthesis](https://arxiv.org/abs/2508.20033) — NeurIPS 2025
- [AssistantBench: Can Web Agents Solve Realistic Tasks?](https://arxiv.org/abs/2407.15711) — 2024
- [FRAMES: Fact, Fetch, and Reason](https://arxiv.org/abs/2409.12941) — Google, NAACL 2025
- [FanOutQA: Multi-Hop Multi-Document QA](https://arxiv.org/abs/2402.14116) — ACL 2024
- [Humanity's Last Exam](https://arxiv.org/abs/2501.14249) — CAIS + Scale AI, Nature 2025

### DR Framework Papers
- [STORM: Synthesis of Topic Outlines through Retrieval and Multi-perspective Question Asking](https://storm-project.stanford.edu/research/storm/) — Stanford, NAACL 2024
- [MindSearch: Mimicking Human Minds Elicits Deep AI Searcher](https://arxiv.org/abs/2407.20183) — 2024
- [AutoSurvey: Large Language Models Can Automatically Write Surveys](https://arxiv.org/abs/2406.10252) — 2024
- [DeerFlow: Open-Source Deep Research Framework](https://github.com/bytedance/deer-flow) — ByteDance, 2025
- [GPT-Researcher](https://gptr.dev/) — 2024-2025
- [Deep Research Agents: A Systematic Examination And Roadmap](https://arxiv.org/abs/2506.18096) — Survey, Jun 2025

### Evaluation Methodology
- [WebArena Verified](https://github.com/ServiceNow/webarena-verified) — ServiceNow, 2025
- [LLMs-as-Judges: A Comprehensive Survey](https://arxiv.org/abs/2412.05579) — 2024
- [Deep Research Bench Leaderboard](https://futuresearch.ai/deep-research-bench/) — FutureSearch
- [Labelbox Benchmarking Deep Research Agents](https://labelbox.com/blog/benchmarking-deep-research-agents/) — Labelbox, 2025
