# Methodology Peer-Review Audit (2026-04-19)

源:subagent 调研 15 篇 2024-2026 benchmark / critic paper 后的严审。

## Verdict

**BORDERLINE,偏 REJECT**。直接投 NeurIPS/ICLR/ACL 2026 benchmark track 估 **25-35% 过审**。护城河(reproducibility + 多框架 shim + 7-pillar + Elo)在,但**3 个硬伤**任选一个都能 desk-reject。

## 3 条必改硬伤(按严重性)

### #1 Judge self-preference 污染 —— paper-killer
**现状**: GLM-5 既当 agent 选手(`react-glm5`)又当 judge(`llm_judge`/`checklist`)。

**证据**:
- Wataoka et al. 2024 (NeurIPS,arXiv 2410.21819):GPT-4 对自家输出 bias 非零且统计显著;**同家族模型都受影响**(perplexity-familiarity 假说)
- JudgeBench (ICLR 2025):即使 Claude-3.5 也只 64% judge accuracy
- Reviewer 一眼锁定

**必须做**:
- (a) 换第三方 judge(GPT-4.1 或 Claude 4.x)跑 cross-judge 一致性
- (b) 定量测 self-preference(匿名化 GLM-5 output 再 judge 一遍,比 Δscore)
- (c) 对 GLM-5 选手报 adjusted-for-self-preference 分

### #2 Citation metric substring → claim-level entailment
**现状**: citation verifier 查 `[text](url) → fetch URL → body.contains(text)`。权重 0.25。

**证据**:
- CiteLab (ACL 2025)、"On Capacity of Citation Generation" (arXiv 2410.11217) 批过 ALCE substring 方法
- 2024+ 新标准已经是 **claim-level NLI entailment**(RAGChecker NeurIPS 2024,DeepResearch Bench FACT judge-LLM 判 page supports claim)
- 我们方法被 2026 reviewer 当"2023-era metric"

**gaming vector**:
- agent 可以先 fetch 找 URL → 造合适 link text 贴上去
- 过度奖励长 page,过度惩罚不需要 citation 的陈述

**必须做**:
- claim extractor 拆 report → atomic claims
- 对 (claim, fetched_page) 跑 NLI entailment
- substring 可保留为 baseline,但主指标必须升级

### #3 Task domain 窄 + scope 不明确
**现状**: 87 条 cross-site 全是 consumer research / sentiment / budget,corpus = shopping + reddit + simple wiki。

**对标**:
- DRACO: 10 domain(含 Academic / Finance / Law / Medicine)
- DR.BENCH: 214 entries 覆盖 policy evaluation / strategic planning
- ResearcherBench: 9 domain 含 business / historical
- DeepResearch Bench: 22 field

**Reviewer 评语**:"benchmark is overfit to e-commerce & social-media QA, cannot be called Deep Research"

**必须做** 二选一:
- **扩 20-30 条 scholarly/policy/financial 任务**(用 Simple Wiki + 公开 SEC/PubMed abstract 静态快照)
- **或 scope 改成 "Consumer & Social-UGC Deep Research Benchmark"**(窄 claim 宽护城河)

宽定位 + 窄任务 = **最糟组合**。

## 次级要改但不致命

### 4. Pairwise Elo battles/pair 12-24 场太少
- Chatbot Arena 用 6M+ votes;Arena-Hard 跑 permutation test
- 我们 n=20 时 Elo 标准差 ±80-120,真实差距可能只 30-50 → **很多排名差异不显著**
- 必须:(a) bootstrap CI (b) permutation test (c) 每对升到 50+ (d) Bradley-Terry MLE 代替 sequential Elo

### 5. evidence_density 权重 0.20 偏高 + 独立加和
- 鼓励数量 > 质量;agent 可以刷 unique slug 数
- 建议:权重 0.10,且与 citation accuracy **乘法合成**(density × accuracy)而非加和

### 6. length-coupled 权重累积 ~45%(llm_judge 0.20 + checklist 0.20 + structure 0.05)
- LLM judge 偏好长 confident output (Wataoka 2024 证实)
- 必须跑 length-controlled ablation,report Spearman(score, length)
- 若 > 0.4 → 加 length-normalized variant

### 7. DeerFlow "输给单 LLM ReAct" 结论 需解释 external validity scope
- 我们 sandbox 3 site,cross-site 任务 ≈ "search + aggregate" = ReAct sweet spot;不 suspicious 但需 scope 声明
- 最好加 long-horizon 子集(50+ step)显示 multi-agent 在那里追上

### 8. fact_kg 5% 尴尬
- 留着 substring-match 三元组是 worst of both worlds
- 要么做实(≥10% + entailment 替代 substring),要么干脆 drop

## 可防守的点

- **reproducibility**:BrowseComp-Plus / WebArena Verified 都是静态 corpus,已在业界 accept
- **oracle-free**:DRACO/ResearcherBench 也无 KG triples
- **多框架 shim**:无先例,可讲故事
- **6 agent × 80 task × 7 pillar × Elo** 规模合理,超过多数 2024 benchmark

## 行动 Roadmap(按 ROI)

| # | 改动 | 工作量 | 紧急 |
|---|---|---:|---|
| P0-1 | Judge 换第三方 + cross-judge | 0.5 天 | 必 |
| P0-2 | Citation → NLI entailment(保留 substring baseline) | 2 天 | 必 |
| P0-3 | 加 20-30 scholarly/policy 任务 **或** 窄化 scope | 3-5 天 | 必 |
| P1-1 | Pairwise battles 每对升到 50+ | 1 天(钱/时间) | 建议 |
| P1-2 | Length-controlled ablation | 0.5 天 | 建议 |
| P1-3 | evidence_density × accuracy 乘法合成 | 0.5 天 | 建议 |

做完 P0 三项 → 过审概率估 **55-70%**。再做 P1 三项 → **70-85%**。

## 结论

方法论**不是废的**,骨架 defensible,但**执行细节有 2023-era 味道**。换 judge + 换 citation metric + 扩 task domain(或明确窄 scope)三件事做了,benchmark track 就有戏。
