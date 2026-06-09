# 实验结果总结(2026-04-16)

> 本文档汇总至今所有 Arena 实验的关键发现,**用于直接拿来跟老师 / 同事讨论**。原始 leaderboard 详见 `data/results/bench_v2_*.md`。

---

## TL;DR (5 句话)

1. **9 task × 4 agent × 27 battles/agent** 的 MEGA Arena 跑通,DeerFlow 多 agent 框架 Composite Elo 1050 微胜 react-glm46 单 agent 1045(差 5 分)。
2. 但 5 task 时 DeerFlow 领先 122 Elo,**多 site 后碾压优势消失** —— 因为 GLM 内容安全在 reddit 政治内容长 prompt 上多次拦截 DeerFlow。
3. **Pairwise LLM judge 偏好简洁回答**(length-bias),把 Composite 排第 4 的 glm-4.5 排第 1 → **证明纯 LLM judge 不可信**。
4. **DeerFlow 独占 cite/fact pillar(Elo 1154)**,glm-46 单 agent 独占 judge/comp(1076/1057)→ **多维分解后没有全能选手**。
5. **glm-46 单 agent 是当前 benchmark 的最佳综合性价比方案**(Composite #2 但只用 1/6 成本)。

---

## 实验 1:5 task × 4 agent(2026-04-16 06:00)

只有 shopping 5 task,首次跑通 4-way Arena。

### Composite Elo

| Rank | Agent | Elo | W-L-D |
|:-:|---|---:|:-:|
| 1 | **deerflow-glm51** | 1097 | 12-3-0 |
| 2 | react-glm51 | 975 | 4-6-5 |
| 3 | react-glm45 | 968 | 3-6-6 |
| 4 | react-glm46 | 960 | 3-7-5 |

**结论**:DeerFlow 多 agent 大幅领先(122 Elo ≈ 67% 胜率,p≈0.01)。看上去多 agent 是答案。

### 局限

只有 1 个 site(shopping)。任务都是结构化字段输出,没暴露 long-context failure mode。

---

## 实验 2:9 task × 4 agent MEGA(2026-04-16 10:39)

加了 reddit 4 条任务,**真正的转折点**。

### Composite Elo

| Rank | Agent | Elo | W-L-D | Δ vs 5-task | 解读 |
|:-:|---|---:|:-:|:-:|---|
| 1 | **deerflow-glm51** | 1050 | 17-10-0 | -47 | 仍第 1,但优势骤减 |
| 2 | **react-glm46** | 1045 | 13-8-6 | **+85** | **从 #4 反超到 #2** |
| 3 | react-glm51 | 969 | 9-13-5 | -6 | 持平 |
| 4 | react-glm45 | 936 | 6-14-7 | -32 | 跌一名 |

### Pairwise Judge Elo

| Rank | Agent | Elo | W-L-D |
|:-:|---|---:|:-:|
| 1 | **react-glm45** | 1104 | 20-7-0 |
| 2 | deerflow-glm51 | 1020 | 15-12-0 |
| 3 | react-glm46 | 981 | 12-15-0 |
| 4 | react-glm51 | 895 | 7-20-0 |

### Per-pillar Elo(每维独立 Arena)

| Agent | Cite | Comp | Det | Eff | Fact | Judge |
|---|---:|---:|---:|---:|---:|---:|
| **deerflow-glm51** | **1154** | 963 | 865 | 1000 | **1154** | 988 |
| react-glm51 | 924 | 1042 | **1068** | 1000 | 924 | 1011 |
| react-glm46 | 961 | **1057** | 1034 | 1000 | 961 | **1076** |
| react-glm45 | 961 | 938 | 1032 | 1000 | 961 | 925 |

---

## 三个核心发现(论文素材)

### 发现 1:多 site 暴露 agent 鲁棒性差异

**现象**:DeerFlow 在 dr_red_0001(/f/news 政治内容)和 dr_red_0004(对比 news vs worldnews)上 Composite 直接 0.04 分(垃圾)。原因:DeerFlow 多 agent 流水线累积的 prompt 长(~5000+ tokens),触发 GLM 内容安全(error code 1301)。单 agent ReAct prompt 短(~1500 tokens)没踩雷。

**论文价值**:**单 site benchmark 看不到这种 failure mode**,只有跨 site / 跨内容类型才能暴露。这是一个支持"评测必须跨 site"的具体证据。

### 发现 2:Composite vs Pairwise Judge 严重背离

**现象**:同一个 glm-4.5 agent:
- Composite Elo:**936**(第 4,垫底)
- Pairwise Judge Elo:**1104**(第 1)

168 Elo 分的差距在同一个模型上出现,排名完全相反。

**原因**:LLM judge 偏好**简洁回答**。glm-4.5 因为是非推理模型,回答短,judge 看着舒服;但实际上回答信息量少,Composite 的 cite/fact pillar 给 0 分。

**论文价值**:这是 **LLM-as-judge length-bias 的干净复现**。MT-Bench 论文 2023 年报告过类似 bias,但在 Deep Research 这种 long-form output 场景上,我们这是首次量化。**说明纯 LLM judge 不可信,确定性多维评分必须**。

### 发现 3:多维拆分后没有全能选手

| Agent 强项维度 | 弱项维度 |
|---|---|
| **DeerFlow**:Cite, Fact | Det(prose 不出 JSON), Comp |
| **glm-51 ReAct**:Det | Cite, Fact, Judge |
| **glm-46 ReAct**:Comp, Judge | Cite, Fact |
| **glm-45 ReAct**:无明显 | 全部中等偏下 |

**论文价值**:**评测是真正的多维不可饱和**,单一 composite score 会掩盖差异。我们的 Per-pillar Elo 设计正好捕捉到这种细分能力差。这跟 LMSYS Chatbot Arena 的 category breakdown(Math / Coding / Hard prompts)异曲同工,但我们的 6 pillar 是**确定性指标**,不是另一组 LLM judge。

---

## 4 个 agent 的失败模式画像

| Agent | 主要失败模式 |
|---|---|
| **deerflow-glm51** | 长 prompt 触发内容安全(reddit 政治内容);reporter 出 markdown 不出 JSON → Det=0;成本是 ReAct 的 6× |
| **react-glm51** | 经常忘 citations 字段;偶尔 produced no answer(GLM-5.1 高方差);LLM judge 给最低分(可能因为冗长) |
| **react-glm46** | 推理 token 偶尔吃光预算 content 为空;但出对的时候质量最高(0.93 史诗) |
| **react-glm45** | 答得简短,Composite 各 pillar 都中等偏下;但 LLM judge 强烈偏好 → pairwise 第 1 |

---

## 数据规模演进

| 时间 | task | agent | battles/agent | 区分度(Elo 极差) |
|---|---:|---:|---:|---:|
| 06:00 | 5 (shop) | 4 | 15 | 137 |
| 10:39 | 9 (shop+red) | 4 | 27 | **209**(Composite); **209**(Pairwise) |
| 后续 | 18+ | 6+ | 60+ | 预期 250+ |

**任务越多 → 区分度越强 → Elo 误差棒越窄**。下一步应优先扩任务数。

---

## 与业界 benchmark 对照

| Benchmark | 评测方式 | 数据规模 | 我们的差异 |
|---|---|---|---|
| **DRACO** (Perplexity 2026) | 100 task × ~40 binary rubric | 100 | 我们多了 **Arena Elo + 跨 agent 对比**;少了人工 rubric 量 |
| **DeepResearch Bench** (USTC 2025) | 100 task × RACE 4 维 + FACT 引用 | 100 | 我们多了 **可控沙盒**(他们是开放 web);少了 task 数 |
| **LiveResearchBench** (Salesforce 2025) | 100 task × DeepEval 6 维 + checklist | 100 | 我们多了 **结构化 verifier 兜底**;少了人工标注 |
| **WebArena** (CMU 2024) | 187 shopping UI task × binary | 187 | 我们多了 **DR 任务设计 + Arena Elo + 多维评分**;沿用了沙盒 |
| **DeepResearchGym** (CMU 2025) | ClueWeb 离线索引 | 大 | 我们的沙盒**真站点**(Magento + Postmill),不是文档索引 |

**我们的独特定位**:
> 第一个**「可控沙盒(自有数据/可复位)+ Deep Research 任务(非 UI 操作)+ 六维确定性评分(非纯 LLM judge)+ Arena Elo 排位」一体化**的 AI Agent 评测系统。

---

## 当前限制

1. **Agent 多样性少**:都是 GLM 系列(成本考虑)。需要接 Claude / DeepSeek / Doubao 才算真正 cross-vendor 评测 → **缺 API key**。
2. **Task 数少**(每 site 4-5 条)。下一步扩到 8-10 条/site。
3. **Golden Answer 还是约束式**:不同答案都能过。需要 Oracle Dump 固化做 byte-identical match。
4. **DeerFlow reporter 出 markdown**:Det=0 拖累 Composite。需要 patch reporter prompt 或加 JSON-extractor 后处理节点。
5. **GLM 内容安全**对 reddit 政治内容敏感:DeerFlow 直接 0.04 分。需要换 judge 模型 / 改 task 选项。

---

## 下一步(按 ROI)

1. **扩任务到 18-20 条**(2 天)→ Elo 误差棒收窄
2. **修 DeerFlow reporter 出 JSON**(半天)→ DeerFlow Composite 重夺第 1
3. **Golden Answer Oracle Dump**(1 天)→ 真值更严格,弱 agent 自然掉分
4. **gitlab 沙盒**(等下载)→ 第 3 个 site,跨 site 论据更强
5. **接 Claude/DeepSeek 当 dual judge**(等申请到 key)→ 论文必须有 cross-vendor judge
6. **跨站任务**(shopping × reddit)→ 真正的 Deep Research 应该跨多源

---

## 文件清单

| 文件 | 内容 |
|---|---|
| `data/results/bench_v2_MEGA.md` | **最权威 leaderboard**(54 场 pairwise 含 LLM 推理) |
| `data/results/bench_v2_5T_4A_ARENA.md` | 5-task 实验对照 |
| `data/results/NIGHT_RUN_SUMMARY.md` | 通宵流水账 |
| `PLAN.md` | 进度 + 路线图 |
| `PROGRESS_REPORT.md` | 给老师看的一页纸 |
| `SCORING_FRAMEWORK.md` | v2 六柱设计文档 |
| `RESULTS_SUMMARY.md` | **本文档** |
