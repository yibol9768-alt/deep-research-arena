# Full Report Evaluation and AgentRL Roadmap

Generated: 2026-06-03

## 0. Position

The project should not treat one composite score as the answer to every
problem. We need three related but separate evaluation layers:

1. Public benchmark ranking: compare agents fairly on the same task set.
2. AgentRL reward: provide cheap, smooth, nonzero training signal over
   trajectories.
3. Full report acceptance: decide whether a user-facing report is complete,
   truthful, long-form, analytical, and safe to deliver.

The current V2 and V3 code already covers the first two partially. It does not
yet cover the third. The next major research step is therefore a new
`FullReportEvaluator`, not another tweak to the V3 soft gate.

## 1. Repository cleanup status

The mainline evaluation path is:

```text
scripts/run_deep_task.py
  -> data/results/deep/<agent>__<task>_matrix.md
scripts/score_deep_answer.py
  -> data/results/deep_v3/<agent>__<task>_matrix.score.json
scripts/build_deep_leaderboard.py
  -> data/results/deep_v3/leaderboard_deep.json
```

The V3 reward path is:

```text
src/eval/evaluator.py::ArenaEvaluator
src/scoring/leaderboard_composites.py::composite_v3_softfloor
scripts/build_deep_leaderboard_v3.py
```

The browser acquisition path now belongs to the mainline:

```text
integrations/agents/browser_dr/agent.py
scripts/runners/browser_dr_runner.py
scripts/plan_full_leaderboard.py
```

Removed from the working tree cleanup pass:

```text
src/dr_harness/
scripts/dr_harness.py
tests/test_dr_harness_*.py
data/runs/
data/tasks/deep_research/browser_click_debug/
data/tasks/deep_research/browser_click_core/
docs/DR_HARNESS_EVAL_PLAN.md
docs/EXPERIMENT_MATRIX.md
docs/HUMAN_AUDIT_PROTOCOL.md
docs/templates/DR_RUN_SCHEMA.md
```

Reason: those files described a parallel harness path. The correct design is
to make browser and future full-report evaluation fit the existing
`run_deep_task.py`, scorer, and leaderboard contracts.

Python cache artifacts were also removed:

```text
__pycache__/
*.pyc
```

## 2. External methods we should absorb

### 2.1 FActScore style atomic factuality

FActScore decomposes long-form generations into atomic facts and computes the
percentage supported by a reliable source. This addresses the core weakness of
whole-report judging: one long report can contain a mixture of true and false
claims.

Source: https://arxiv.org/abs/2305.14251

Design lesson for us:

```text
FullEval must score claim-level factual precision, not only URL-level validity.
```

### 2.1b SAFE and LongFact style long-form factuality

SAFE turns long answers into self-contained facts, verifies them with search,
and reports long-form factuality with precision and F1@K style metrics. The
important addition over pure precision is that verbose but unsupported reports
and very short but safe reports can both be diagnosed.

Source: https://arxiv.org/abs/2403.18802

Design lesson for us:

```text
FullEval should report both atomic support precision and a richness-adjusted
metric, so a two-paragraph safe answer cannot beat a complete grounded report.
```

### 2.2 ALCE style citation quality

ALCE evaluates cited generation along fluency, correctness, and citation
quality. The important point for us is citation association: a source must be
attached to the right nearby claim, not merely listed somewhere in the report.

Source: https://arxiv.org/abs/2305.14627

Design lesson for us:

```text
A citation should support the local claim span around it.
References-at-the-end is not enough.
```

### 2.3 RAGChecker style retrieval and generation diagnosis

RAGChecker separates retrieval quality from generation quality with
fine-grained diagnostic metrics. This is close to our setting because an agent
may retrieve the right pages and still write wrong claims, or retrieve weak
pages and write fluent prose.

Source: https://arxiv.org/abs/2408.08067

Design lesson for us:

```text
FullEval should separate retrieval coverage, evidence use, and final writing.
```

### 2.3b RAGAS and ARES style calibrated RAG judging

RAGAS popularized separate faithfulness, answer relevance, context precision,
and context recall style metrics. ARES adds trained lightweight judges and
prediction-powered inference so automatic scores can be reported with
confidence intervals against a small human-labeled set.

Sources:

```text
https://arxiv.org/abs/2311.09476
https://docs.ragas.io/
```

Design lesson for us:

```text
FullEval should keep cheap deterministic diagnostics for every run, then use
human-calibrated judge scores for expensive report-quality dimensions.
```

### 2.4 DeepResearch Bench

DeepResearch Bench uses expert-crafted tasks and separates report quality from
citation quality. It introduces a report-quality evaluation and a FACT-style
citation framework measuring effective citation count and citation accuracy.

Source: https://arxiv.org/abs/2506.11763

Design lesson for us:

```text
Report quality and citation accuracy must be separate axes.
High prose quality cannot rescue bad citations.
```

### 2.4b ResearcherBench and expert rubric evaluation

ResearcherBench-style evaluation uses expert-written rubrics and claim,
citation, and context triplets. This is closer to real research usefulness
than generic writing-quality judging because the expected answer space is
encoded as weighted criteria.

Design lesson for us:

```text
Each core FullEval task needs a task-specific aspect tree, not only global
markdown and citation rules.
```

### 2.5 LiveResearchBench and DeepEval

LiveResearchBench proposes user-centric, multi-faceted, search-intensive tasks.
Its DeepEval suite covers coverage, presentation, citation accuracy and
association, consistency, and depth of analysis.

Source: https://arxiv.org/abs/2510.14240

Design lesson for us:

```text
FullEval must include report-level quality, content-level quality, and
citation-source association.
```

### 2.5b DeepResearch Bench II style binary rubrics

DeepResearch Bench II uses many binary rubrics derived from expert articles.
The useful idea for us is not to copy the dataset, but to make each task
carry enough binary checks to distinguish missing information, weak analysis,
and bad presentation.

Design lesson for us:

```text
FullEval task configs should include required aspects and binary rubric leaves
that can be audited by humans and approximated by judges.
```

### 2.6 DeepResearchGym

DeepResearchGym focuses on a reproducible search sandbox and evaluates
alignment with user information needs, retrieval faithfulness, and report
quality.

Source: https://arxiv.org/abs/2505.19253

Design lesson for us:

```text
Our sandbox is a real advantage. We should use proof-of-fetch and replayable
retrieval traces as first-class evaluation assets.
```

### 2.7 DeepResearcher and SFR-DeepResearch

Recent Deep Research RL work trains agents in search environments and focuses
on autonomous tool use, search strategy, reasoning, and final answer quality.

Sources:

```text
https://arxiv.org/abs/2504.03160
https://arxiv.org/abs/2509.06283
```

Design lesson for us:

```text
Training reward must be cheaper and denser than full report grading.
Full report grading should be used for periodic eval, not every rollout.
```

## 3. What is wrong with our current full evaluation

Current strong pieces:

```text
URLCoverageVerifier
URLReachabilityVerifier
QuoteMatchVerifier
ClaimNLIVerifier
MarkdownReportVerifier
LongformQualityVerifier
SourceDiversityVerifier
PerspectiveBalanceVerifier
CitationAlignmentVerifier
AnalysisDepthVerifier
PresentationVerifier
SandboxComplianceVerifier
```

Current weak points:

1. No claim inventory. We do not know how many factual claims the report made.
2. No atomic fact support rate. We cannot say what percentage of the report is
   actually supported by fetched evidence.
3. No required aspect tree. The checklist is flat and task-specific, but not a
   structured model of the user's information need.
4. No hard full-report gate. V3 soft-floor is useful for RL, but user-facing
   reports need fail-closed truthfulness gates.
5. No strong citation association. A URL may be valid while supporting a
   different claim than the one near the citation.
6. No synthesis-specific metric. Current depth judges can reward prose that
   sounds analytical without checking whether the analysis actually integrates
   multiple sources.
7. No conflict-handling metric. A good report should notice disagreement and
   uncertainty instead of smoothing it away.
8. V3 naming is overloaded. `score_deep_answer.py`, `ArenaEvaluator`, and
   `src/scoring/composite_v3.py` represent different historical V3 designs.
9. The public rank score and the train-time reward are still too easy to
   confuse. They should share verifier outputs, but not the same acceptance
   semantics.
10. The codebase does not yet have one obvious place for full-report
    acceptance artifacts, human audit labels, and calibrated thresholds.

## 4. Proposed three-layer evaluation architecture

### 4.1 Layer A: Public benchmark ranking

Purpose: compare agents on the same task suite.

Keep:

```text
composite_v2_truthful for headline truthfulness-gated ranking
composite_v3_softfloor for diagnostic and future smooth ranking variants
```

Do not use this layer as the final user acceptance test.

### 4.2 Layer B: AgentRL reward

Purpose: train policies with cheap, dense, nonzero signals.

Use:

```text
ArenaEvaluator(mode="fast")
ResearchEnv rollout traces
retrieved_snippets
fetched_urls
tool_calls
tool_state_deltas
source_diversity
longform skeleton signals
process reward
penalties
```

This layer may use soft gates, approximations, and dense process signals.

### 4.3 Layer C: Full report acceptance

Purpose: decide whether a user can trust and use the final report.

New entry point:

```text
src/eval/full_report_evaluator.py::FullReportEvaluator
```

This layer must be stricter:

```text
hard gates first
quality pillars second
failure taxonomy always
claim audit always
evidence audit always
```

## 5. FullEval v0 contract

### 5.1 Output schema

```json
{
  "task_id": "dr_cross_deep_0001",
  "agent": "browser-dr",
  "valid": true,
  "final_score": 0.82,
  "gates": {
    "sandbox_compliance": {"passed": true, "score": 1.0},
    "proof_of_fetch": {"passed": true, "score": 1.0},
    "citation_support": {"passed": true, "score": 0.91},
    "atomic_fact_support": {"passed": true, "score": 0.87},
    "aspect_coverage": {"passed": true, "score": 0.84},
    "longform_minimum": {"passed": true, "score": 0.95}
  },
  "pillars": {
    "truthfulness": 0.87,
    "completeness": 0.84,
    "analysis_depth": 0.78,
    "source_synthesis": 0.76,
    "rigor_uncertainty": 0.80,
    "citation_quality": 0.91,
    "longform_structure": 0.88,
    "presentation": 0.86
  },
  "claim_audit": {
    "n_claims": 128,
    "supported": 111,
    "partially_supported": 9,
    "unsupported": 8,
    "major_unsupported": 1
  },
  "failure_modes": []
}
```

### 5.1b Diagnostic panel

Every FullEval output should include a diagnostic panel in addition to the
final score. This keeps the result useful for research even when the report
fails.

```json
{
  "diagnostics": {
    "atomic_precision": 0.87,
    "atomic_f1_at_k": 0.81,
    "citation_accuracy": 0.91,
    "average_effective_citations": 18.4,
    "citation_association": 0.86,
    "retrieval_claim_recall": 0.78,
    "context_precision": 0.73,
    "generator_faithfulness": 0.88,
    "context_utilization": 0.69,
    "analysis_rubric_pass_rate": 0.76,
    "presentation_rubric_pass_rate": 0.84
  }
}
```

Interpretation:

```text
atomic_precision: supported factual claims divided by all checkable claims
atomic_f1_at_k: factual precision adjusted by useful fact richness
citation_accuracy: cited URLs actually support their nearby claims
average_effective_citations: citations that are fetched, relevant, and used
citation_association: the local claim and the cited source match
retrieval_claim_recall: needed task claims covered by fetched evidence
context_precision: fetched evidence that is actually useful
generator_faithfulness: generated claims supported by context
context_utilization: useful fetched evidence reflected in the report
```

### 5.2 Hard gates

The report is invalid if any hard gate fails.

| Gate | Pass condition | Why it matters |
| ---- | -------------- | -------------- |
| `sandbox_compliance` | cited URLs stay inside allowlist | prevents open-web leakage |
| `proof_of_fetch` | cited URL appears in retrieval trace or fetched artifacts | prevents post-hoc fabricated citations |
| `citation_support` | cited page supports nearby claim | prevents irrelevant but reachable citations |
| `atomic_fact_support` | supported plus partial facts above threshold, no major unsupported claims | protects long-form factuality |
| `aspect_coverage` | required user aspects covered | protects completeness |
| `longform_minimum` | meets length, section, paragraph, and citation-density floors | prevents thin answers |

Suggested default thresholds:

```text
proof_of_fetch >= 0.95
citation_support >= 0.80
atomic_fact_support >= 0.85
major_unsupported_claims <= 0 for user-facing acceptance
aspect_coverage >= 0.80
longform_minimum >= 0.75
```

### 5.3 Quality pillars

Only valid reports receive a final quality score.

| Pillar | Weight | Main signals |
| ------ | -----: | ------------ |
| `truthfulness` | 0.25 | atomic support, citation support, quote match |
| `completeness` | 0.20 | required aspect tree, source coverage, must-answer questions |
| `analysis_depth` | 0.15 | multi-evidence claims, causal reasoning, comparison quality |
| `source_synthesis` | 0.10 | cross-source integration, conflict handling |
| `rigor_uncertainty` | 0.10 | hedging, limitations, no overclaiming |
| `citation_quality` | 0.10 | association, density, diversity, effective citation count |
| `longform_structure` | 0.05 | sections, paragraph depth, balance, executive summary |
| `presentation` | 0.05 | readability, tables, recommendation clarity |

Initial formula:

```text
final_score = sum(weight[p] * pillar[p])
valid = all(hard_gates_pass)
published_score = final_score if valid else 0
```

## 6. New verifier modules to build

### 6.1 AtomicClaimExtractor

Path:

```text
src/verifiers/atomic_claims.py
```

Contract:

```python
extract_claims(answer: str) -> list[AtomicClaim]
```

Each claim:

```json
{
  "id": "c001",
  "text": "The product has 30 hours of battery life.",
  "section": "Battery life",
  "sentence_span": [12, 12],
  "nearby_citations": ["http://localhost:7770/..."],
  "claim_type": "product_fact"
}
```

Implementation plan:

1. Deterministic sentence splitter and citation-window extraction.
2. LLM extractor for high-quality atomic decomposition in full mode.
3. Cache results keyed by report hash.
4. Offline tests with fixed markdown samples.

### 6.2 AtomicClaimSupportVerifier

Path:

```text
src/verifiers/atomic_claim_support_verifier.py
```

Input:

```text
claims
retrieved_snippets
task_config
```

Output:

```text
supported
partially_supported
unsupported
contradicted
not_checkable
```

Support method:

1. Start with deterministic lexical overlap and quote match.
2. Use NLI or LLM judge only for ambiguous claims.
3. Require support from nearby citations first.
4. Fall back to any fetched page only as a weaker signal.

### 6.3 TaskAspectCoverageVerifier

Path:

```text
src/verifiers/task_aspect_coverage_verifier.py
```

Add task schema:

```json
"full_report_spec": {
  "target_words": 4000,
  "required_sections": ["Executive summary", "Evidence", "Analysis", "Conclusion"],
  "must_answer": [
    {"id": "q1", "question": "Which option is best for the stated user need?", "weight": 0.25}
  ],
  "required_aspects": [
    {"id": "price", "description": "price comparison", "weight": 0.15},
    {"id": "risks", "description": "risks and limitations", "weight": 0.15}
  ],
  "source_requirements": {
    "min_unique_urls": 20,
    "min_domains": 3,
    "min_wiki": 4,
    "min_forum": 4,
    "min_shopping": 4
  }
}
```

### 6.4 EvidenceSynthesisVerifier

Path:

```text
src/verifiers/evidence_synthesis_verifier.py
```

Measures:

```text
multi_source_claim_ratio
cross_domain_synthesis_count
comparison_table_quality
conflict_mentioned
conflict_resolved_or_declared
```

### 6.5 UncertaintyCalibrationVerifier

Path:

```text
src/verifiers/uncertainty_calibration_verifier.py
```

Detects:

```text
overconfident unsupported claims
missing limitations
missing caveats where sources conflict
clear confidence language where evidence is strong
```

### 6.6 ReportUsefulnessVerifier

Path:

```text
src/verifiers/report_usefulness_verifier.py
```

Measures whether the final report gives the user an actionable answer:

```text
clear answer to task
decision criteria
tradeoffs
recommendation or conclusion
next steps
```

This should be LLM-judged in full mode only.

## 7. FullEval implementation phases

### Phase F0: Naming and cleanup

Status: started.

Actions:

1. Keep V2, V3-RL, and FullEval names separate.
2. Remove or mark parallel harness code as deprecated.
3. Add this document as the canonical plan.

### Phase F1: FullEval skeleton

Files:

```text
src/eval/full_report_evaluator.py
tests/test_full_report_evaluator.py
docs/FULL_REPORT_EVAL_AGENTRL_ROADMAP.md
```

Build:

```python
class FullReportEvaluator:
    def evaluate_report(report_md, task_config, trace=None) -> FullReportEvalResult
```

Acceptance:

```text
fake valid report passes
fabricated citation fails
no-fetch citation fails
thin report fails
source dump without analysis fails quality but may pass basic truth gate
```

### Phase F2: Atomic claims

Files:

```text
src/verifiers/atomic_claims.py
src/verifiers/atomic_claim_support_verifier.py
tests/test_atomic_claim_support_verifier.py
```

Acceptance:

```text
extracts stable claims from markdown
nearby citation support wins
unsupported claims are counted
major unsupported claim fails hard gate
```

### Phase F3: Task aspect tree

Files:

```text
src/verifiers/task_aspect_coverage_verifier.py
scripts/stamp_full_report_spec.py
tests/test_task_aspect_coverage_verifier.py
```

Acceptance:

```text
existing cross_site_deep task can be stamped with full_report_spec
missing required aspect fails completeness
partial aspect coverage gets partial credit
```

### Phase F4: Synthesis and uncertainty

Files:

```text
src/verifiers/evidence_synthesis_verifier.py
src/verifiers/uncertainty_calibration_verifier.py
tests/test_evidence_synthesis_verifier.py
tests/test_uncertainty_calibration_verifier.py
```

Acceptance:

```text
single-source summaries score low on synthesis
multi-source comparison scores higher
ignored contradictions are detected
overconfident unsupported claims are penalized
```

### Phase F5: FullEval CLI

Files:

```text
scripts/evaluate_full_report.py
scripts/evaluate_full_report_batch.py
```

Commands:

```bash
python3 scripts/evaluate_full_report.py \
  --task dr_cross_deep_0001 \
  --answer data/results/deep/browser-dr__dr_cross_deep_0001_matrix.md \
  --trace logs/retrieval/browser-dr__dr_cross_deep_0001_matrix.jsonl \
  --out data/results/full_eval/browser-dr__dr_cross_deep_0001.json
```

### Phase F6: Human audit calibration

Files:

```text
docs/HUMAN_FULL_REPORT_AUDIT_PROTOCOL.md
scripts/sample_full_eval_audit.py
scripts/compute_full_eval_kappa.py
```

Human labels:

```text
claim supported
claim partially supported
claim unsupported
citation associated
aspect covered
analysis useful
uncertainty calibrated
```

Metrics:

```text
Cohen kappa
Krippendorff alpha
correlation with FullEval gates
calibrated thresholds
```

## 8. AgentRL reward design

FullEval is too expensive and too sparse for every RL rollout. We should train
with a faster decomposed reward and run FullEval periodically.

### 8.1 Reward layers

Use five layers. The first four can run during training. The fifth is periodic
evaluation.

| Layer | Name | Used in hot loop | Purpose |
| ----- | ---- | ---------------- | ------- |
| L0 | structural hard gate | yes | reject no report, sandbox escape, all citations unfetched |
| L1 | proof-of-fetch grounding | yes | reward fetched evidence and cited evidence |
| L2 | deterministic quality proxy | yes | score coverage, source mix, report skeleton, aspect proxy |
| L3 | process reward | yes | reward useful searches, reads before cite, efficient exploration |
| L4 | FullEval | periodic only | judge deliverable long-form report quality |

Hot-loop reward should be smooth. Full-report acceptance should be strict.

### 8.2 Fast rollout reward

Use during GRPO or other AgentRL training:

```text
R_rollout = clip01(H * (reach_soft(s_ground) * Q_fast
            + lambda_proc * R_process - P_hack))

reach_soft(s_ground) = 0.5 + 0.5 * s_ground

Q_fast =
  0.25 * proof_of_fetch
+ 0.20 * citation_trace_support
+ 0.15 * source_coverage
+ 0.10 * source_diversity
+ 0.10 * longform_skeleton
+ 0.10 * task_aspect_proxy
+ 0.10 * process_quality
```

Signals:

```text
proof_of_fetch: cited URLs were actually fetched
citation_trace_support: cited URL has nonempty snippet and local claim overlap
source_coverage: expected domains and must-cite pool coverage
source_diversity: shopping, forum, wiki balance
longform_skeleton: headings, paragraphs, citation density, length band
task_aspect_proxy: keyword or rubric-leaf coverage before LLM judge
process_quality: useful searches, reads before cite, no duplicate spam
```

Penalties:

```text
fabricated_url
cite_without_read
external_url
duplicate_citation_spam
empty_report
tool_error_spam
over_budget
```

`H` should only zero the rollout for structural invalidity:

```text
no final report
sandbox escape
state-diff task has completely wrong final state
all citations are unfetched
```

Do not put long-report acceptance gates directly into the hot loop:

```text
3500 word minimum
60 citation minimum
all LLM judges pass
full atomic claim audit
multi-judge human-calibrated report score
```

Those are useful for FullEval but too sparse and expensive for rollout reward.

### 8.3 Hot-loop versus periodic metrics

| Signal | Hot-loop reward | Periodic FullEval |
| ------ | --------------- | ----------------- |
| proof of fetch | yes | yes |
| sandbox compliance | yes | yes |
| citation URL format | yes | yes |
| local citation overlap | yes | yes |
| atomic claim support | sampled proxy | full audit |
| aspect coverage | keyword or rubric proxy | full aspect tree |
| source diversity | yes | yes |
| longform skeleton | yes | full structure rubric |
| synthesis quality | cheap proxy | judge plus human audit |
| uncertainty calibration | no or weak proxy | judge plus human audit |
| live URL reachability at scale | no | yes |
| human preference calibration | no | yes |
| reward hacking audit | sampled | yes |

### 8.4 Periodic full reward

Use every N training steps or for validation:

```text
R_full = FullEval.final_score if FullEval.valid else 0
```

This is the report-quality target but should not be called every rollout.

### 8.5 Curriculum

Stage 1:

```text
short reports
3 to 6 citations
single-domain and two-domain tasks
fast reward only
```

Stage 2:

```text
multi-domain reports
10 to 20 citations
source diversity and aspect coverage
fast reward plus sampled atomic support
```

Stage 3:

```text
long-form reports
20 to 60 citations
full_report_spec required
periodic FullEval
```

Stage 4:

```text
browser acquisition and tool-rich tasks
RAG, SQL, crawl, vision, write-state tasks
FullEval plus task-specific state verifiers
```

## 9. Concrete code reuse map

Reuse immediately:

```text
src/eval/evaluator.py
src/eval/rollout.py
src/eval/reward_terms.py
src/rl/env.py
src/rl/backends.py
src/rl/tools.py
src/verifiers/url_coverage_verifier.py
src/verifiers/url_reachability_verifier.py
src/verifiers/quote_match_verifier.py
src/verifiers/claim_nli_verifier.py
src/verifiers/markdown_report_verifier.py
src/verifiers/longform_quality_verifier.py
src/verifiers/source_diversity_verifier.py
src/verifiers/perspective_balance_verifier.py
src/verifiers/citation_alignment_verifier.py
src/verifiers/analysis_depth_verifier.py
src/verifiers/presentation_verifier.py
src/verifiers/sandbox_compliance_verifier.py
integrations/search_shim/app.py
```

Add new:

```text
src/eval/full_report_evaluator.py
src/verifiers/atomic_claims.py
src/verifiers/atomic_claim_support_verifier.py
src/verifiers/task_aspect_coverage_verifier.py
src/verifiers/evidence_synthesis_verifier.py
src/verifiers/uncertainty_calibration_verifier.py
src/verifiers/report_usefulness_verifier.py
scripts/evaluate_full_report.py
scripts/stamp_full_report_spec.py
docs/HUMAN_FULL_REPORT_AUDIT_PROTOCOL.md
```

Keep separate:

```text
V2 leaderboard: public ranking and truthfulness finding
V3-RL: smooth reward and training signal
FullEval: user-facing report acceptance
```

## 10. Minimum viable milestone

The first non-GPU milestone should not try to solve everything. It should prove
that FullEval catches failures our current V3 misses.

Build these five fixtures:

```text
oracle_full_report: valid, long, grounded, analytical
fabricated_citation_report: URL-like citations but no support
no_fetch_report: cites real URLs not present in trace
source_dump_report: many true facts but no synthesis
thin_report: short answer with citations
```

Expected:

| Fixture | Hard gate | Quality |
| ------- | --------- | ------- |
| oracle | pass | high |
| fabricated citation | fail | zero published score |
| no fetch | fail | zero published score |
| source dump | pass or partial pass | low analysis and synthesis |
| thin report | fail longform minimum | zero published score |

This milestone is enough to show the key improvement:

```text
Current V3 rewards useful training behavior.
FullEval rejects bad user-facing reports.
Together they are stronger than either alone.
```

## 11. Research claim we can make after implementation

After FullEval v0, the project can claim:

```text
Deep Research Arena separates train-time reward from user-facing report
acceptance. Train-time reward uses smooth trace-grounded signals suitable for
AgentRL, while FullEval applies hard evidence gates, atomic claim verification,
task-aspect coverage, and long-form synthesis metrics before a report is
considered deliverable.
```

That is a stronger and cleaner story than:

```text
We changed V3 to a soft gate.
```
