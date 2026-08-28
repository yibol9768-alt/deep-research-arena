# DRA 最终评测指标与报告分层计划（2026-08-26）

## 口径结论

- 不发明单一总分。保留现有 `Citation Binding / GCP / GRR`，并补齐可靠性、延迟、成本、引用诊断。
- 固定核心指标：26 个；产品化扩展指标：3 个。总计 29 个可报告字段。
- Headline 只展示 4–5 个，其他进入诊断表。

## Headline（最多 5 个）

1. `citation_binding`
2. `gcp`
3. `grr`
4. `mandatory_rubric_coverage`（后续 rubric/answer 质量接入）
5. `answer_usefulness_win_rate`（有盲评时；无则 N/A）

有唯一答案子集时才用 `answer_accuracy_pass1`，不和开放式 usefulness win rate 混报。

## 固定核心 26 项

### 质量 8

```text
citation_binding
gcp
grr
fact_precision
citation_completeness
raw_coverage
rubric_pass_rate
fabrication_rate
```

### 可靠性 6

```text
valid_run_rate
report_success_rate
scoring_completion_rate
retry_rate
request_success_rate
model_identity_match_rate
```

### 延迟 4

```text
run_latency_p50_s
run_latency_p95_s
agent_request_latency_p50_ms
agent_request_latency_p95_ms
```

### 成本 4

```text
agent_cost_per_valid_run_usd
judge_cost_per_scored_run_usd
total_cost_per_scored_run_usd
agent_cost_per_grounded_required_unit_usd
```

### Citation/source 4

```text
citation_precision
citation_recall
unique_cited_url_count
source_diversity_effective_n
```

每个指标统一附属列：

```text
value, numerator, denominator, status, reason, n, aggregation_method, score_version
```

规则：withheld/missing 不当 0；无有效分母输出 `N/A` + reason。

## 产品扩展 3 项

```text
answer_usefulness_mean
jury_win_rate
jury_tie_rate
```

## 公式补丁

不改动 `GCP/GRR` 定义；新增标准 citation 指标：

```text
citation_precision = valid_supporting_binding_count / evaluable_binding_count
citation_recall = eligible_citation_required_claims_with_valid_support / eligible_citation_required_claim_count
```

成本效率：

```text
agent_cost_per_grounded_claim = agent_cost_usd / gcp_numerator
agent_cost_per_grounded_required_unit = agent_cost_usd / grr_numerator
judge_cost_ratio = judge_cost_usd / agent_cost_usd
```

## 固定表

1. `Evaluation Scope & Validity`
2. `Cell Leaderboard`
3. `Run Reliability`
4. `Agent Requests`
5. `Judge Audit`
6. `Citation Quality`
7. `Cost Accounting`
8. `Source Diversity`
9. `Jury Evaluation`（产品模式）

## 固定图

1. Quality Scorecard（Citation Binding/GCP/GRR，带分子分母和 withheld）
2. Cost vs Grounded Quality（GCP/GRR/Citation Binding Pareto）
3. Latency Distribution（run + request p50/p95）
4. Reliability Funnel（intended→attempted→successful→report present→scored）
5. Citation Outcome Breakdown（registry/fetched/snippet/context/out-of-snapshot/fabricated）
6. Cost Composition（Agent/Judge/Diagnostic 分账）

## 外部对齐

参考 DeepResearch Bench、DRACO、BrowseComp/BrowseComp-Plus、ResearchRubrics、LiveResearchBench、WebArena/WorkArena、GAIA、AssistantBench。对齐方式：保留我们的 grounding 三件套，同时补 citation precision/recall、rubrics coverage、usefulness win rate、成本/延迟/invalid run rate。不抄别人的单一 composite。

## 模块化 CLI 目标

最终对外只保留：

```bash
dra author ...
dra eval ...
dra score ...
dra report ...
```

内部模块：`author / eval / score / report`。用户不需要知道 projection、judgment packet、aggregator 的内部命令顺序。
