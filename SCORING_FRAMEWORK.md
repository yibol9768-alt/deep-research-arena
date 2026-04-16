# Deep Research 评分框架 v2

**日期**:2026-04-16
**依据**:内部调研 `paper_survey/articles/01_deep_research_评测框架与数据来源全景解析.md` + 工业界 DRACO / DeepResearch Bench / LiveResearchBench / FActScore / ALCE 等 2024-2025 年研究。
**现状**:v1 只有"字段约束 + 引用可达",漏了业界评测六大支柱中的四项。v2 对齐主流范式,同时保留"可控沙盒 + 确定性基线"这个我们的差异化。

---

## 一、为什么 v1 不够

当前的 `ReportVerifier` + `CitationVerifier` 属于 **WebArena-Verified 风格**——字段级确定性匹配。优点零方差,缺点是:

1. **只能判 "格式对不对"**,判不了 "事实对不对" —— DeerFlow 返回的是正确但 markdown 形式的报告,v1 直接 0 分
2. **不评价信息覆盖度** —— Agent 只报 3 条产品 vs 应该覆盖 10 类维度,v1 只要 3 条过约束就满分
3. **不评价推理深度** —— "直接取 top 3" 和 "识别样本量过小后选 review 多的产品",v1 分不出高下
4. **不评效率** —— 100s / $0.05 的 agent 和 300s / $0.50 的 agent 同分

## 二、业界共识的六大评测支柱(按重要度)

来源见 `paper_survey/articles/01_...md`,截至 2025 年底:

| # | 维度 | 代表实现 | 权重提示 |
|---|---|---|---|
| 1 | 事实准确性 Factuality | FActScore, DRACO(~50%), RACE-Factuality | 最重 |
| 2 | 信息覆盖/全面性 Comprehensiveness | DeepSearchQA "全面性差距", RACE-Comp | 重 |
| 3 | 引用/归因质量 Citation Quality | ALCE (Citation Recall / Precision), FACT | 重 |
| 4 | 逻辑与可读性 Readability | DRACO Presentation, RACE-Read, LiveResearchBench 短板 | 中 |
| 5 | 指令遵循 Instruction Following | RACE-IF(OpenAI DR 领先 49.27) | 中 |
| 6 | 效率 Efficiency | 端到端延迟 / token / 工具调用数 | 当前最不成熟 |

## 三、v2 分层设计

```
┌──────────────────────────────────────────────────────────────┐
│                     Composite Score (0-1)                    │
│       = 0.30·DeterministicScore                              │
│       + 0.25·FactualityScore                                 │
│       + 0.15·CitationScore                                   │
│       + 0.15·LLMJudgeScore                                   │
│       + 0.10·ComprehensivenessScore                          │
│       + 0.05·EfficiencyScore                                 │
└──────────────────────────────────────────────────────────────┘
```

分层设计的好处:**先用便宜层过滤,再上 LLM judge**——控成本。

### 层 1:Deterministic(v1 已有,保留)

字段约束 + JSON Schema + 硬编码真值匹配。**零方差 / 零 LLM / 快**。

不变,权重下调到 0.30(不再是唯一评分)。

### 层 2:Factuality(新,参考 FActScore + ALCE)

对每条"声明"做原子事实抽取 + 证据验证:

1. LLM 从 agent 输出里抽 atomic claims(`(entity, attribute, value)`,例如 `("TECNO N1", "price", "39.99")`)
2. 对每条 claim:
   - 若 agent 给出 citation URL → 拉该 URL,在页面上找 `value`(精确 / 数值容差)
   - 若没给 URL → 走 shopping 沙盒 search + product page 做事实检索(给 agent 多一次机会)
3. **FactualityScore = verified_claims / total_claims**

这一层比 CitationVerifier 强,因为不只看 URL 可达,还看 URL 的内容**确实支持**该声明。

### 层 3:Citation Quality(v1 升级)

从"URL 可达 + 域名白名单"扩展成 ALCE 双指标:

- **Citation Recall** = 需要引用的声明中,实际带了引用的比例
- **Citation Precision** = 给出的引用中,URL 页面真的支持该声明的比例

DRACO 现行工业数据:最佳系统 Citation Precision 约 **90%**,最多引用数 **111**(Gemini DR)。用这个做标定。

### 层 4:LLM-as-Judge(新,参考 RACE + G-Eval)

分解式评分,每次只评一个维度,CoT + Few-shot 校准。4 维每维 1-5 分:

| 维度 | 说明 |
|---|---|
| `comprehensiveness` | 是否覆盖 intent 要求的所有方面 |
| `insight_depth` | 是否有超出表面枚举的分析(如 DeerFlow 的"样本量过小"洞察) |
| `instruction_following` | 是否严格按 output schema / 约束回答 |
| `readability` | 结构 / 语言 / 排版 |

Judge 模型用 GLM-5.1(与被测一致)+ claude-sonnet-4-6 双 judge 对比 → 防止 self-preference 偏差(Zheng et al 2023 披露 LLM judge 70% 位置偏差问题)。

实现复用 `paper_dr_lab/scripts/06_evaluate.py` 的 `JUDGE_SYSTEM` prompt 结构,按我们的任务改 4 维名字。

### 层 5:Comprehensiveness(分离出来的特殊 LLM judge)

因为 DeepSearchQA 2025-12 指出 "Comprehensiveness Gap" 是当前最大短板,单独拉出来:

- 对每个 task,预先人工写一份 `coverage_checklist` —— 形如 `["包含价格对比", "包含至少 2 条评论证据", "提及至少 1 个不推荐的理由"]`
- 判定 agent 输出中有多少 checkbox 被满足 → pass/fail per item
- DRACO 风格的二值 rubric,降低 LLM judge 细粒度评分的方差

### 层 6:Efficiency(新)

纯机械测量,不吃 LLM token:

```python
eff = {
    "wall_time_s": ...,
    "llm_input_tokens": ...,
    "llm_output_tokens": ...,
    "tool_calls_total": ...,
    "cost_usd": input*PRICE_IN + output*PRICE_OUT,
}
```

归一化成 0-1:用同 task 下所有被测系统的中位数做 reference,成本 ≤ median 给 1.0,超 2×median 给 0。DRACO 的 Parallel.ai 评测说明最贵系统不一定最好,**必须报效率**才能画 Pareto 前沿。

---

## 四、输出契约

每次运行输出一个 `RunResult v2`:

```json
{
  "task_id": "dr_shop_0001",
  "agent": "react-glm51",
  "composite_score": 0.64,
  "breakdown": {
    "deterministic": 1.00,
    "factuality":    {"score": 0.83, "verified": 5, "total": 6},
    "citation":      {"recall": 0.80, "precision": 1.00, "score": 0.89},
    "llm_judge":     {"comprehensiveness": 4, "insight_depth": 2, "instruction_following": 5, "readability": 4, "weighted": 3.6},
    "comprehensiveness_checklist": {"passed": 3, "total": 5, "score": 0.60},
    "efficiency":    {"wall_time_s": 95, "tokens_in": 12000, "tokens_out": 3000, "cost_usd": 0.018, "score": 0.95}
  },
  "verifier_details": [...],
  "agent_answer": "..."
}
```

**关键**:`composite_score` 是主排序,但排行榜必须展示所有子分——让使用者按自己需求重排(有人不在乎成本,有人不在乎可读性)。

---

## 五、实现优先级

已做:v1 `ReportVerifier` + `CitationVerifier`(层 1 + 部分层 3)。

按 ROI 顺序补齐:

- [ ] **P0 — 层 3 升级到 ALCE 双指标**:citation recall / precision,~1h,对 DeerFlow 跑分质变
- [ ] **P0 — 层 4 LLM judge**:复用 `06_evaluate.py` 的 JUDGE_SYSTEM,改 4 维名字,接 GLM-5.1,~2h
- [ ] **P0 — 层 6 Efficiency**:从 Runner 的 RunResult + Anthropic 响应里抓 token usage,~1h
- [ ] **P1 — 层 2 Factuality**:原子事实抽取需要 LLM,成本较高,先实现简化版(price/rating 数值匹配),~3h
- [ ] **P1 — 层 5 Comprehensiveness checklist**:每 task 人工写 5 条,再跑 LLM judge per-item,~2h + 每 task 15min 人工
- [ ] **P2 — CompositeScorer**:把六层加权汇总 + 排行榜导出,~2h
- [ ] **P2 — Dual-judge 校准**:GLM-5.1 + Claude-sonnet-4-6 两个 judge 的一致率报告,~2h

做完 P0 三项(~4h)就能出一份**可投稿水准**的 React vs DeerFlow 对比表。

## 六、为什么这是正确的路径

1. **合潮流不盲从**:业界共识的六支柱我们都做,但保留了确定性层作为"锚",避免纯 LLM judge 的方差问题
2. **对我们的沙盒是 superpower**:因为所有 URL 都在我们控制的 Magento 里,citation precision 和 factuality 可以**100% 自动化验证**,不像开放 web deep research 评测必须信 LLM judge
3. **能发论文**:主流 benchmark(DRACO / DeepResearch Bench)都是 100+ task、100 小时标注级别。我们单靠 5 task 扩到 50 task + 可控沙盒 + 多维打分,可以做"Reproducible Deep Research Benchmark on Controlled Sandbox"类论文
4. **成本可控**:P0 三项加起来 ~4 小时代码 + 每次跑分 ~$0.5 token(GLM-5.1 便宜)
