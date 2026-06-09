# 论文优势分析 & 框架评估

**Date**: 2026-05-02
**Status**: 100 tasks verified, scoring ablation done, ready for paper writing

---

## 一、我们 vs 竞品的核心差异

### 1.1 唯一的三源 sandbox DR benchmark

| 特性 | DeepResearchGym | BrowseComp-Plus | DRBench Enterprise | DR³-Eval | **Ours** |
|---|---|---|---|---|---|
| Corpus 类型 | ClueWeb22 静态 | BrowseComp 100K 文档 | Docker 企业应用 | Per-task 静态 | Magento+Postmill+Kiwix |
| 可交互性 | IR only | IR only | 全交互 | IR only | **全交互+IR** |
| 多源结构 | 单一 corpus | 单一 corpus | 4 应用但非 IR | 自定义 | **3 源 (电商+论坛+百科)** |
| 产品可搜 | ❌ | ❌ | ❌ | ❌ | **✅ (Magento 2K+ products)** |
| 社区讨论 | ❌ | ❌ | ✅ (Mattermost) | ❌ | **✅ (Postmill threads)** |
| 百科知识 | ❌ | ✅ (web) | ❌ | ✅ (custom) | **✅ (Kiwix Wikipedia)** |
| 确定性 ground truth | ❌ | ❌ | 部分 | 部分 | **✅ (≥120 must-cite/task)** |

**核心优势**：我们是唯一同时具备 (a) 全交互 sandbox、(b) 三种异构信息源、(c) 确定性 URL ground truth 的 DR benchmark。

### 1.2 Intent 分类体系

竞品 benchmark 大多不区分任务类型。我们的 6 种 intent type 是独有贡献：

| Intent | 数量 | 代表任务 | 评估什么 |
|---|---:|---|---|
| Recommendation | 17 | 最佳血压计、最佳 VPN | 产品搜索+评价综合 |
| Comparison | 17 | AWS vs Azure、三种饮食对比 | 多维度结构化对比 |
| Debunking | 17 | 5G 健康谣言、回收神话 | 证据提取+论证 |
| Causal | 16 | 抗生素耐药、创业失败原因 | 因果链构建 |
| Timeline | 16 | 支付系统演变、火星探测史 | 时间线整理+事实密度 |
| Enumeration | 17 | USB 标准目录、退休账户类型 | 穷举覆盖+分类学 |

这让我们能做 intent-stratified analysis —— 分析不同框架在不同任务类型上的表现差异，是其他 benchmark 做不到的。

### 1.3 Truthfulness-first 评分

消融研究的关键发现 (**F6 finding**)：

- **去掉 reachability gate → gpt-researcher 从 #3 跳到 #1**
- gpt-researcher 产出流畅、结构好、judge pass rate 高，但 97% 的 URL 是编造的
- truth gate 是唯一能区分 "hallucinating but fluent" vs "grounded but rough" 的机制

这个发现本身就值一个 section —— 当前大部分 DR benchmark 靠 LLM judge 评分，**根本检测不到 URL 造假**，因为 judge 不会去访问 URL。

---

## 二、框架合理性自检

### 2.1 评分体系 (V2 composite)

```
truth = reachability × (0.5 + 0.5×quote_match) × (0.5 + 0.5×claim_nli)
quality = 0.4×url_coverage + 0.4×checklist_judge + 0.2×spec_compliance
composite = truth × quality
```

**消融验证结果**：
- ✅ truth gate 是决定性因素（去掉后 ranking 变 τ=0.40）
- ✅ 质量维度权重稳定（±50% 不影响排名）
- ⚠️ NLI 维度全零（所有 agent 都没触发，需要考虑去掉或换实现）
- ⚠️ reach 和 quote 高度冗余（ρ=0.91），论文里报告但保留两者

**建议论文中**：
1. 报 V2 (truth-gated multiplicative) 为主指标
2. 报 additive (无 gate) 为对照，展示 F6 finding
3. 去掉 NLI（或标注为 "not discriminative in current setup"）
4. 保留 reach + quote 但讨论冗余性

### 2.2 Golden ground truth

**优势**：
- 每题 ≥120 must-cite URLs（实际 mean=135, median=135）
- 跨 3 域（shopping + reddit + wikipedia）
- 确定性 —— golden 是从 sandbox 爬的，不会变

**局限**：
- 4 个任务 must_cite < 120（93, 110, 115, 118），但都 > 90
- 1 个任务 (0077 voter fraud) 没有 shopping URLs
- must_cite 是 "sandbox 上真实存在的页面"，不是 "最优答案应该引用的页面"

### 2.3 Task 质量

**统计**：
- 100 tasks, 13 domains, 6 intent types
- Intent 长度: mean=1937 chars, min=995, max=4696
- Checklist: 100 tasks × avg 20.7 items
- 0 critical issues in final audit

**对比竞品**：
| Benchmark | Tasks | Domains | Intent Types | Checklist Items/Task |
|---|---:|---:|---:|---:|
| DRACO | 100 | 10 | N/A | ~40 |
| LiveResearchBench | 100 | 7 | 10 categories | ~10 |
| Dr. Bench | 214 | 10 | N/A | N/A |
| ResearchRubrics | 101 | 9 | N/A | 20-43 |
| **Ours** | **100** | **13** | **6** | **~21** |

---

## 三、论文还缺什么

### 必须补的 (P0)

1. **充值 DeepSeek / 找替代 LLM** — 跑全量 matrix 需要 judge（当前 ds_proxy 没余额）
2. **全量 matrix 重跑** — 10+ agent × 100 task，产出新 leaderboard
3. **LLM judge 可靠性验证** — 至少 sample 50 对 (task, report) 让人标注，算 judge-human agreement
4. **论文写作** — abstract, intro, method, experiments, findings, related work

### 建议补的 (P1)

5. **Multi-backbone 消融** — top-3 agent × 2+ backbone (DeepSeek V4 vs GPT-5-chat)，~$20
6. **效率指标** — latency, token 消耗, cost per task
7. **人工抽查** — 3 agent × 10 task × 20 URL = 600 条 URL 真实性人工验证（~5h）

### 可选 (P2)

8. **Citation-claim alignment** — ALCE 风格的 "cited URL 是否支持 claim" 验证（已有 verifier 框架但需要 LLM 余额）
9. **Presentation / Analysis Depth** — V3 里的新维度（代码已写但 score 文件里没有）
10. **Multi-judge ensemble** — 用 2-3 家 LLM 当 judge

---

## 四、论文结构建议

**Title**: "SandboxDR: A Reproducible Multi-Source Benchmark for Deep Research Agents with Deterministic Ground Truth"

### Sections

1. **Introduction** (1.5 pages)
   - DR agent 爆发（2025-2026），评测缺乏标准化
   - Live-web benchmark 的不可复现问题（引 BrowseComp-Plus）
   - 我们的贡献：sandbox + 三源 + intent 分类 + URL ground truth

2. **Related Work** (1 page)
   - 已有草稿在 PAPER_POSITIONING.md
   - 20+ benchmark 对比表

3. **Benchmark Design** (2 pages)
   - 3.1 Sandbox architecture (Magento + Postmill + Kiwix)
   - 3.2 Task design: 13 domains × 6 intents, golden generation pipeline
   - 3.3 Scoring: V2 composite, 6 dimensions, truth gate

4. **Experiments** (2 pages)
   - 4.1 Agents tested (10+)
   - 4.2 Main results: leaderboard, per-intent breakdown
   - 4.3 Key findings (F1-F6)

5. **Analysis** (1.5 pages)
   - 5.1 Scoring ablation: truth gate is decisive
   - 5.2 Intent-stratified: which agents excel at what
   - 5.3 URL fabrication analysis (the F6 finding)
   - 5.4 Efficiency analysis

6. **Discussion & Limitations** (0.5 page)
   - Sandbox vs live-web ecological validity
   - Single LLM judge limitation

7. **Conclusion**

---

## 五、2026 最新竞品更新（搜索 2026-05-02）

之前的调研截至 2026-04-30，以下是新发现或需特别关注的竞品：

| Benchmark | Date | Key Feature | 和我们的关系 |
|---|---|---|---|
| **TRACE** (ACM Web 2026) | 2602 | Trajectory-aware evaluation, process quality, not just output | 互补：我们评 output，TRACE 评 process |
| **IDRBench** | 2601 | Interactive DR（用户反馈循环） | 不同方向：我们是 autonomous，它是 interactive |
| **KDR-Bench** | 2604 | Knowledge-intensive，41 题 + 1252 结构化表格 | 小规模，focus 不同 |
| **DeepResearch-9K** | 2603 | 9000 题！但主要是 QA 不是长文报告 | 规模大但非同类 |
| **ProductResearch** (Amazon) | 2602 | 电商 DR agent，synthetic trajectory distillation | 有趣：也是电商场景但是训练方法论文不是 benchmark |

**关键发现**：截至 2026-05-02，**没有新的 sandbox-based DR benchmark 出现**。DR³-Eval (2604) 是最接近的但它用 per-task 自定义 corpus，不是统一 sandbox。我们的三源交互式 sandbox 仍然独特。

**Citation fabrication 热点**：GPTZero 在 ICLR 2026 发现 50+ hallucinated citations，NeurIPS 2025 有 100+。这正是我们 F6 finding 的大背景 —— citation truthfulness 是学术界当下的热点话题。

---

## 五、核心 Selling Point (审稿人视角)

1. **可复现性** — "Try running DRACO or LiveResearchBench today and getting the same numbers as the paper." 我们可以。
2. **F6 Finding: Fluent Hallucinator Problem** — gpt-researcher 在无 truth gate 时排名第一但 97% URL 是假的；当前大部分 DR benchmark 靠 LLM judge 评分根本检测不到 URL 造假。结合 2025-2026 年 citation fabrication 在顶会的爆发（NeurIPS 100+ fake citations），这个 finding 极具时效性。
3. **Intent taxonomy** — first DR benchmark with structured task categorization enabling stratified analysis
4. **Fair comparison** — 10+ open-source agents on identical retrieval surface, no API confound
5. **Deterministic ground truth** — ≥120 must-cite URLs per task，sandbox 内容不变，citation verification 有确定答案
