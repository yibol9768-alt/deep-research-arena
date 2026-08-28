# Deep Research Arena：Query、评分、语料与索引工作回顾

> 更新时间：2026-08-24（Asia/Shanghai）  
> 用途：记录此前已经完成的工作、当前真实状态和后续可选路线，供项目讨论与个人决策使用。  
> 本文不是启动命令，也不表示已经开始新的出题、评测或全量索引任务。

## 1. 一页结论

过去几个月的工作并没有“全部作废”，但不同阶段的资产成熟度差别很大：

- **旧 Query 已经形成可复用的历史题库和报告资产**，尤其是 Truth56 的 56 道题、3 个模型的 168 份报告及可重放评分结果。
- **新 Query 方法已经形成比较完整的生产规范**：从证据发现、hidden contract、proof DAG、自然题面生成，到公开/私有自动审计和独立模型盲解，逻辑上比旧题严格得多。
- **新 Query 目前仍没有正式发布题**：规划了 1000 道正式题和 200 道 reserve，但 `formal_eligible=true` 仍为 0。
- **当前最接近正式题的资产**已从证据包推进为 1 道生态分类 W1D1 自动审计合格候选题：上游仍是 33 个承重页面、87 个 evidence units、60 个 fetched pages；Q1 已完成确定性、Width、公开 GLM 和私有 closure 审计，但 BM25 solver 因搜索超过 180 秒客户端时限而阻塞，尚未进入 fetch、双模型盲解和最终冻结。
- **旧评分可以完整重放，新评分尚未完成真实闭环**。旧 Truth56 的 168 份评分可精确复算；新版 GCP/GRR 需要报告生成时的完整 search/fetch ledger，不能直接套在旧报告上。
- **三源全量语料已经清洗和切段**：Wikipedia、Magento、Postmill 合计约 1,942 万页面、3,425 万个 1000-token 段。
- **已有索引只是 K2 小索引，不是全量索引**：约 33.6 万页、184 万 passages；全量 3,425 万段索引尚未建立。
- **KaLM 知识库上传尝试不能算完成检索闭环**：历史记录是 720/720 文件已提交，后续索引/Embedding 被主动停止，实际检索质量没有得到证明。

因此，项目现在不是“什么都没做”，而是处在一个典型的中间状态：**旧资产足够做历史基线，新规范足够指导下一版，但新题、新评分和全量检索还没有被一条完整实验链同时打通。**

### 1.1 2026-08-24 新增项目原则：不以人工核验阻塞出题

本项目希望突出的是**可自动扩展、可复算、可审计的端到端出题能力**，而不是依赖人工逐题放行。因此后续正式规则应为：

- evidence review 由自动审计器完成，自动门通过后可以继续编译 hidden contract 和题面；
- public/private Query audit 由相互隔离的模型或确定性检查完成；
- blind solve 使用至少两个独立模型族，避免由出题模型自己证明自己；
- 人工只用于可选抽检、协议校准、争议仲裁和论文误差分析；
- `human_evidence_review=PENDING` 不应继续作为每道题的生产硬门；
- 任何“取消人工硬门”的修改都不能等价于取消 evidence、引用、ablation、泄漏和可回答性检查。

当前远程 `PRODUCTION_PROTOCOL.md` 和运行状态仍保留旧的人工作为硬门的设计。本条记录的是新的项目决策；在代码和协议完成版本化修改前，不能把旧实现描述成已经自动化完成。

---

## 2. 旧 Query 资产

### 2.1 Truth56

- 题目数：56。
- 历史报告：56 题 × 3 个模型 = 168 份。
- 旧评分结果可以在不调用模型的情况下重放，现有 168/168 结果与历史聚合值一致。
- 这些题和报告已经是项目资产，适合用于：
  - 历史基线；
  - 评分回放；
  - 失败案例分析；
  - 新旧出题方法对比；
  - 论文中的 baseline 或 protocol ablation。

局限：

- 题目是在旧生成协议下形成的，不满足全部新版证据审计和独立模型盲解要求。
- 评分 suite 是报告生成后补建的，当前全部 `formal_eligible=false`。
- 缺少报告生成时的合法检索轨迹，不能直接得到可信的新 GCP/GRR。

### 2.2 Shopping 相关旧题

当前盘点得到的资产分为：

| 类别 | 数量 | 说明 |
|---|---:|---|
| 单站 Deep Research 题 | 9 | 可作为较小、较直接的检索题 |
| 旧跨站题 | 100 | 题面通常更脚手架化，需重新审计 |
| 对抗版跨站题 | 20 | 可保留为困难样本或失败模式测试 |
| WebArena 操作题 | 187 | 属于网页操作任务，不能直接混为 Deep Research Query |

旧跨站题的主要问题不是只有 domain，而是：

- 经常把来源网站和检索路线直接写进题面；
- 强行要求访问某些不承重的 Shopping 页面；
- 表格列、步骤和来源角色写得过细，像隐藏 rubric 的公开版本；
- 部分题面甚至暗示或泄漏正确结论；
- Width 有时由“要求访问多少网页”制造，而不是由答案确实依赖多少证据制造。

这些题不必物理删除。更合理的定位是：**保留为历史题库，但重新标记为 baseline、rework 或 retire，不直接冒充新版正式 Query。**

---

## 3. 新 Query 方案是如何形成的

新方法现在可概括为：**Graph-first + Evidence-first + Automation-first**。人工不再逐题放行，只保留可选抽检和仲裁角色。

### 3.1 完整流程

```text
Seed / 用户情境
→ dense 检索发现候选证据
→ Qwen3-Reranker-8B 重排
→ fetch 原文
→ 精确引用、支持关系和反证审计
→ hidden evidence contract / proof DAG
→ 从 hidden contract 提炼 public intent
→ DeepSeek 生成 3 个自然语言候选题面
→ GLM 审核公开题面的自然性、泄漏和可回答性
→ GLM 审核私有证据闭包和 hidden contract
→ 两个不参与出题的不同模型族独立 blind solve
→ 可选人工抽检 / 争议仲裁（不作为逐题硬门）
→ 冻结 Query、gold、rubric、证据和运行信息
```

核心变化是：**先证明证据图真的存在，再让模型把它表达成一个自然问题**，而不是先写一个看上去很难的问题，再去网上拼证据。

### 3.2 公开题面禁止泄漏的内容

公开 renderer 不应看到或暴露：

- evidence 文本、URL、span 和证据哈希；
- hidden contract、proof DAG、gold、rubric；
- W/D cell、预期答案和 expected outcome；
- “访问以下页面”“按以下网站顺序搜索”等来源计划；
- “根据附件/给定来源/上述资料”等不稳定表述。

题面长度分为四档：

- 40–70 词；
- 71–120 词；
- 121–180 词；
- 181–220 词；
- 单题硬上限为 220 词。

### 3.3 Width 与 Depth

最新版 page-correct 定义为：

| 维度 | 定义 |
|---|---|
| W1 | 至少 30 个承重页面，一个主题 |
| W2 | 至少 50 个承重页面，至少两个主题 |
| W3 | 至少 100 个承重页面，跨两个一级领域 |
| W4 | 至少 200 个承重页面，跨至少三个一级领域 |
| D1 | 最长依赖链 1 hop，没有真正串行依赖 |
| D2 | 2–3 hops，至少一处真实依赖 |
| D3 | 4–5 hops，包含条件分支或冲突裁决 |
| D4 | 至少 6 hops，至少两个条件分支和一个冲突裁决门 |

这里的“承重页面”必须满足：删除该页面后，gold 答案会缺行、改变或无法推出。搜索次数、fetch 次数、引用数量和 bibliography 长度都不能直接当作 Width。

### 3.4 当前仍未统一的地方

1. 旧 allocation 和部分 YAML 仍使用 branch/source-role 版本的 Width；最新文档已经改为 30/50/100/200 页，但实现尚未完全同步。
2. 最新决策要求出题侧只使用 dense + rerank + fetch，BM25 只在出题后检查 solver reachability；旧 discovery prompt 仍会在出题中使用 BM25。
3. W4 需要 200+ 页面，但部分旧 schema 的 `max_urls` 仍为 200，需要重新统一上限。
4. 旧生产协议把 `human_evidence_review` 设为题面生成前硬门；新的项目原则要求改为自动 evidence audit 放行，人工仅作可选抽检和仲裁。

这些不是小文案问题，而是会直接影响哪些候选能被标记为正式题。

---

## 4. 新 Query 实际做到了多少

必须区分 taxonomy、slot、candidate 和 formal Query：

| 层级 | 数量 | 状态 |
|---|---:|---|
| 一级领域 | 25 | 已规划 |
| leaf topics | 125 | taxonomy 审计最终 125/125 ACCEPT，仅批准 slot planning |
| planned slots | 1200 | 1000 formal + 200 reserve，全部仍为 planned |
| micro Query ID | 2 | 共 9 个不同候选文本，均被新版质量门退回 |
| renderer canary | 24 个候选实例 | 18 个不同文本，只验证 renderer |
| full-pipeline 尝试 | AWE、ECO-R2、ECO-PROMPTFIX 等 | pending 或 rework，没有冻结为正式题 |
| ECO-06 自动化题面 | 3 个候选 | Q1/Q2/Q3 均通过确定性、Width、公开 GLM 和私有 closure 审计；自动选择 Q1 |
| ECO-06 语言 A/B | 3 个 treatment 候选 | 已生成；B1/B2 确定性 PASS，B3 FAIL；严格 language audit 解析失败并 fail-closed |
| heavy authoring A–F | 多次运行 | 均未完成正式 Query 闭环 |
| 正式 Query | **0** | `formal_eligible=true` 为 0 |
| 正式采纳 Query | **0** | 尚未发生 |

当前最好的资产是一个 W1D1 生态分类 evidence bundle 及其自动审计合格题面：

- 33 个承重页面；
- 87 个 evidence units；
- 60 个 fetched pages。
- 合格运行：`T1000-QUERY-AUTO-V4-20260824-W1D1-ECO-06`；
- 自动选择候选：Q1；
- 状态：`AUTOMATED_AUDIT_PASS_PENDING_SOLVER`；
- `human_query_review=PENDING` 仅为非阻塞 metadata。

自动选中的 Q1 为：

> I'm studying how the documented ecosystem classification relates to the limitations and uncertainties stated alongside it. Could you reconcile the documented terrestrial, freshwater, and marine ecosystem type categories with their documented constraints? Build a complete named inventory of types that have their own dedicated entry, and for each entry report only the classification, boundary, environmental, or vegetation-constraint information it actually states—without requiring fields it omits. Also record terminology overlap, classification disagreement, or boundary limitations when an entry states them. Overview pages may point to eligible types, but they cannot substitute for each type's own entry.

它已经完成自然题面、确定性检查、page-correct Width、公开 GLM 审计和私有 closure 审计。尚缺的是 solver reachability、双模型族盲解和最终冻结，而不是人工逐题审核。

### 4.1 Solver 与语言层 canary 的真实结果

Solver 使用隔离 canonical shim 和 BM25-only 路线，没有改动现有 8081 服务。正式 Q1 的搜索请求在客户端 180 秒时限内未返回；服务端证据账本约 296 秒后才记录 HTTP 200。客户端因此没有取得搜索结果，也没有进入 fetch 和双模型 blind solve。当前结论是 `PERFORMANCE_BLOCKED / REVIEW`，不是题面或证据失败，也不能把延迟到达的 HTTP 200 当成 solver PASS。

语言层遵循“只改表达、不改 evidence/intent/need/closure/Width/Depth”的边界，使用 `purpose_first`、`question_first`、`evidence_gap_first` 三种 discourse strategy 做过一次 A/B canary：

- B1、B2 的确定性和 Width 检查通过；
- B3 因 hub non-substitution 表达和无效 public field reference 未通过；
- GLM 返回了可供诊断的非正式 soft 分，但正式 language audit 输出包含多个 JSON 对象，违反严格 schema，最终 `FAIL_CLOSED`；
- 没有自动选择任何 treatment，Control A 仍是上述 ECO-06 Q1；
- 远程定向测试已独立重跑，结果为 **36 passed**；当前无残留 query、language 或 solver 进程。

本地语言层结构资产位于 `analysis/multi_benchmark_query_quality/language_layer_handoff/`。它可以继续用于修复 audit 输出协议，但不应为了取得分数而放宽 schema，也不需要重新生成 33 页 evidence bundle。

---

## 5. 评分体系

### 5.1 旧 Truth56 评分

旧评分包括：

- **Fact**：可判定事实中的正确比例；
- **Evidence**：citation binding precision 与必要证据 recall 的 F1；
- **Completeness**：facet × unit type 的宏平均覆盖；
- **Rubric**：各要求的加权完成率；
- **Provenance**：有效来源 URL 比例；
- **Quality**：Fact、Evidence、Completeness、Rubric 四轴均值；
- **Truth**：`Provenance × Quality`。

已确认：

- 168 份旧评分可以零 API 精确重放；
- 实际 judge 是 `adams-qwen3.6-35b-a3b`；
- 不是早期文档中写的 Qwen3-8B；
- 现有评分和 suite 均不能自动升级为正式新评分资产。

### 5.2 新评分

新版希望把“说得准”和“研究得全”拆开：

- **Grounded Claim Precision（GCP）**：报告写出的重要 claims 中，有多少由合法发现、准确绑定的证据支持；
- **Grounded Research Recall（GRR）**：题目要求覆盖的必要研究单元中，有多少被真正发现、使用和回答；
- **Citation binding**：作为前置门，确认引用确实支持相应 claim；
- **Writing Elo**：单独比较写作、组织和可读性，不与事实分相乘。

新评分需要在回答生成前冻结 TEC/census，并在运行时记录：

- search 调用；
- fetch 调用；
- 合法发现身份；
- snapshot/内容哈希；
- claim 与 citation 的绑定。

旧 168 份报告缺少这些运行时观测。直接把缺失字段当作 false 会制造“全零”假象，正确处理应是 `unscorable` 或 `withheld_observability`。

当前评分核心测试已重新运行，结果为 **34 passed**。

---

## 6. 语料和知识库工作

### 6.1 已清洗的三源语料

| 来源 | 页面数 | 原始清洗 chunks | 1000-token 重打包段 |
|---|---:|---:|---:|
| Wikipedia 2026-06 nopic | 19,191,219 | 66,307,438 | 33,793,963 |
| Magento | 104,368 | 266,372 | 138,736 |
| Postmill | 127,391 | 417,454 | 318,707 |
| 合计 | 19,423,030 | 66,991,264 | 34,251,406 |

补充信息：

- 1000-token 重打包文本约 72.09GB；
- 配置为目标约 900 tokens、上限 1000 tokens；
- 完整清洗结果压缩后约 24.5GB，逻辑 TSV 约 164GB；
- GitLab 尚未进入这套清洗结果，服务器上目前主要是约 77.8GB tar 资产。

### 6.2 KaLM 公共知识库上传尝试

历史停止点为：

- 720/720 manifest 文件已提交；
- 后续索引和 Embedding 因公共资源写入压力被主动停止；
- supervisor 已退出，部分活动文档被暂停；
- 没有完成同文档检索和全量 retrieval 验证。

因此“文件上传完成”不等于：

- 所有文档完成切分；
- 所有 chunk 完成 Embedding；
- 向量数据库完整；
- Query 能检索到对应原文；
- 检索质量达到可出题标准。

这次尝试留下了有价值的上传脚本、manifest、去重账本、切分配置和容量数据，但公共 KaLM 不应被描述成已经完成的全量知识库。

---

## 7. any2 上的索引状态

`sivenfuuliu-any2` 当前为：

- 32 CPU；
- 62GiB 内存；
- 无 GPU；
- `/data` 可用约 310GB；
- `/data1` 可用约 136GB。

### 7.1 已有 K2 小索引

- 页面：336,032；
- passages：1,839,989；
- BM25 SQLite FTS5：约 19.24GB；
- KaLM 896 维 fp16 dense：约 3.30GB；
- dense 状态：`COMPLETE`、`serving_permitted=true`；
- dense scope：只允许 evidence/query authoring；
- solver 仍应为 BM25-only。

局限：

- 这不是 1,919 万 Wikipedia 全量索引；
- 当前 8081 服务没有真正绑定这套冻结 BM25/dense；
- 639 条历史查询只有 selection agreement；
- Precision@10、MRR、Recall 没有独立 gold 数值；
- 现有结果证明链路可构建，没有证明检索质量合格。

### 7.2 全量索引的量级

对 34,251,406 段按现有比例估算：

- BM25：约 281GB；
- KaLM 896 维 fp16 原始向量：约 61.4GB；
- fp32 则约 122.8GB；
- row ID、hash 和绑定元数据：约 13GB；
- 还需原文、ANN、manifest、日志和构建临时空间；
- 新增产物总量预计约 360–450GB。

any2 能作为索引存储和 CPU 检索节点，但当前空间分散，不能无准备地构建一个全量单体 SQLite。KaLM Embedding 和 Qwen reranker 更适合放在 my5090 或已有受控模型服务；reranker 本身不需要预建索引。

---

## 8. 目前真正存在的几个决策问题

### 8.1 旧 Query 要不要废掉

有三种表达方式：

1. **全部沿用**：论文连续性最好，但新版方法的贡献会被旧题质量拖累。
2. **全部废掉**：方法最干净，但几个月的旧题、报告和评分资产无法进入论文主线。
3. **分层保留**：旧题作为 Historical/Legacy baseline，新题作为 Formal protocol benchmark。

目前更稳妥的是第三种：**不把旧题包装成新题，也不把旧资产删除。**

这样可以对老师解释：前期工作负责暴露问题、建立报告和评分基线；后期工作根据这些问题升级了生成与评测协议。两者不是简单的 domain 差异，而是 benchmark maturity 的两个阶段。

### 8.2 先跑旧题，还是先建全量索引

- 先跑旧题：能最快判断旧题和评分到底有哪些可保留内容。
- 先建全量索引：能扩大后续出题空间，但成本高，且不能自动解决题目和评分协议问题。
- 先用 K2 闭环一题：最小成本验证新 Query、新评分和检索能否一起工作。

当前没有必要为了“开始思考”就立即启动 3,425 万段全量构建。现成 K2 已足够支持小规模诊断和第一道新题闭环。

### 8.3 全量 dense 是否必须立即做

不一定。

- solver 只需要 BM25；
- 出题需要 dense，但可以先对目标语料或分片生成；
- 全量 fp16 向量本身约 61.4GB，主要瓶颈是 Embedding 吞吐；
- 旧吞吐线性外推可能达到约 30 天，因此应先在 my5090 做 1–5 万段吞吐测试再估算。

---

## 9. 后续可选路线

### 路线 A：优先整理旧资产

适合目标：先回答“以前做的题和评分到底好不好”。

- 精确回放 168 份旧评分；
- 从 Truth56 选择 6 题、18 份现成报告做诊断；
- 从 Shopping 单站、旧跨站、对抗版各选 1 题做新鲜 canary；
- 把旧题分为 baseline、rework、retire；
- 输出一份可放论文的“旧协议问题 → 新协议改进”对照。

### 路线 B：优先完成第一道新正式题

适合目标：证明新方法不是只有规范文档。

- 已在 ECO-06 上使用现有 33 页生态证据包；
- 已生成 3 个候选题面，并完成确定性、page-correct Width、公开 GLM 和私有 closure 审计；
- 已自动选择 Q1，人工 `PENDING` 不阻塞；
- 优先解决或规避当前 BM25 单次搜索超过 180 秒的性能阻塞；
- 做两个独立模型族的 blind solve；
- 人工继续只保留为可选抽检或争议仲裁；
- 生成第一份可计算 GCP/GRR 的完整评分 bundle。

### 路线 C：优先扩检索能力

适合目标：为更大规模出题准备基础设施。

- 先把现成 K2 BM25/dense 接入统一 search/fetch API；
- 建立独立 retrieval gold；
- 再做 100 万段 canary；
- 测 BM25 空间和速度、my5090 Embedding 吞吐、ANN recall；
- 确认清理或加盘后，再建立三源全量分片索引；
- GitLab 作为后续独立 source track 加入。

### 一个比较平衡的顺序

如果希望兼顾已有投入和新方法可信度，可以按以下顺序考虑：

1. 先审 6 道 Truth56 和 3 道 Shopping canary；
2. 保留当前 ECO-06 Q1，先解决 K2 BM25 solver 的性能阻塞并完成双模型盲解；
3. 把通过 solver 的 Q1 冻结为第一道正式新题；
4. 证明新评分可以在真实运行 ledger 上计算；
5. 最后再决定是否马上建立 3,425 万段全量索引。

这个顺序的目的不是拖延索引，而是先确认：**我们最终需要大规模支持的究竟是哪一种题和哪一种评分。**

---

## 10. 当前状态标签

| 项目 | 当前结论 |
|---|---|
| Truth56 旧题 | 已有，可作为历史基线 |
| Truth56 168 份报告 | 已有 |
| 旧评分重放 | 已验证 |
| 新 GCP/GRR | 设计和代码存在，旧报告不可直接正式计算 |
| Truth1000 taxonomy | 已完成到 slot-planning gate |
| 1000 formal + 200 reserve | 仅规划，未正式生成 |
| 新正式 Query | 0；已有 1 道 `AUTOMATED_AUDIT_PASS_PENDING_SOLVER` 候选 |
| 最佳新资产 | 33 页 W1D1 evidence bundle + 自动选择的 ECO-06 Q1 |
| ECO-06 自动审计 | 确定性、Width、公开 GLM、私有 closure 均 PASS |
| ECO-06 solver | `PERFORMANCE_BLOCKED / REVIEW`；BM25 搜索超过客户端 180 秒时限，未进入 fetch/双模型盲解 |
| 语言层 A/B | 已运行；Treatment 因严格 JSON/schema 解析失败而 fail-closed，Control A 保持不变 |
| 人工 evidence review | 旧协议硬门；新决策改为可选抽检，不再逐题阻塞 |
| K2 BM25/dense | 已构建，小规模质量未正式证明 |
| 三源全量清洗 | 已完成 |
| 三源全量 BM25 | 未构建 |
| 三源全量 dense/ANN | 未构建 |
| GitLab 清洗与索引 | 未完成 |
| KaLM 公共知识库 | 文件已提交过，索引/检索闭环未完成且已停止 |

## 11. 最后一句话

项目真正的价值不只是一批 Query，而是已经逐渐形成了一套关于“什么题算难、什么页面算承重证据、什么评分算可观测”的方法论。现在最重要的选择不是简单地“保留旧题还是全部重做”，而是决定：**旧题在论文中承担历史基线，还是正式 benchmark；新方法需要先证明一题闭环，还是直接投入全量基础设施。**
