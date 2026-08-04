# DRA 报告级四轴真实性评分重构

## Rubric Fulfillment、Claim Fact、Observed Evidence 与 Corpus Completeness

> 版本：Draft v1.2，2026-07-24
> 文档性质：独立的新方案，不覆盖 `DRA_SANDBOX_NATIVE_SCORING_DESIGN_2026-07-17.md`。
> 目标：保留报告级 `Truth = Provenance × Quality` 的直觉与自动化优势，同时修正旧 `Fact / ProofOfFetch / Completeness` 的构念错位、重复计分和任务路线绑定，并显式加入用户要求与预先冻结的潜在研究要求。

---

## 0. 一页结论

保留报告级骨架：

$$
\begin{aligned}
Quality_t
&=
w_F Fact_t+w_E Evidence_t\\
&\quad+w_C Completeness_t+w_R Rubric_t,\\
Truth_t&=Provenance_t\cdot Quality_t,\\
w_F+w_E+w_C+w_R&=1.
\end{aligned}
$$

但四个内层项必须互不替代地回答不同问题：

| 新轴 | 回答的问题 | 分母 | 主判定资产 |
|---|---|---|---|
| `Fact` | 报告主动说出的、可裁决原子事实有多准确？ | 报告中可裁决的 material atomic claims | 独立多来源事实证据包 + Fact judge |
| `Evidence` | 报告中的外部主张有多少真正绑定了本次观察到、且确实支持它的证据？ | citation bindings；报告中 citation-required units | 运行账本 + 冻结 evidence spans |
| `Completeness` | 相对该题可发现、可回答的内容集合，报告覆盖了多少原子事实与高阶研究单元？ | TEC 中 protocol-complete 的 atomic + higher-order units | 多路全库检索 + Task Evidence Census |
| `Rubric` | 报告是否满足用户明确要求，以及在看答案前冻结的潜在研究要求？ | explicit + latent rubric items | Task Contract + 双人审核 rubric |
| `Provenance` | 报告引用的 URL 是否真实存在、可规范化并有冻结内容快照？ | 报告中的唯一 evidence URLs | URL registry + HTTP/快照记录 |

写作流畅度、结构和可读性采用独立 pairwise jury / Bradley–Terry Elo；它不乘入 `Truth`，也不改变真实性排名。

旧权重 `0.39 / 0.28 / 0.33` 仅保留为 legacy ablation。新定义改变了构念，并增加了 `Rubric`，不能继承旧权重的含义。首个候选版本采用四轴等权：

$$
w_F=w_E=w_C=w_R=\frac14.
$$

等权不是声称四种错误伤害完全相同，而是在没有可靠效用函数时避免伪精确；正式版本必须同时发布四个 raw axes、门槛/几何聚合 ablation 与权重敏感性结果。

本方案最关键的构建变化是：**每道题发布前先完成一次 Task Evidence Census（TEC，单题证据普查），对冻结世界做全库候选扫描，并把所有计分分母、任务相关事实/关系单元、支持与反驳 span、等价 URL、排除记录和可发现性证书冻结。** 正式评分只对这份版本化总账做匹配，不临时改变答案空间。

如果正式运行发现了一个表外、真实、任务相关且会影响得分的 claim，或者发现一个未登记但确实支持既有单元的新 URL，这都不是正常的“按需加分”，而是 `census_gap`：该版本的题目暂停进入正式榜，修复 TEC、提升版本，并对所有历史报告统一重算。任何单份报告都不能因为先暴露了漏项而获得一条私有评分路线。

---

## 1. 我们要保住的东西

旧方案并不是一项差工作。它有四个非常重要、应当保留的优点：

1. 自动化程度高；
2. 冻结输入下结果可复现；
3. 不依赖运行后临时编写、针对某份报告的大型人工 rubric；
4. 所有 harness 使用完全相同的程序、registry、页面快照和评分器。

因此，新方案不是把确定性评测推翻为一个大型 LLM rubric judge。它仍以冻结世界、固定表、可回放账本和可审计 span 为主；LLM 只承担四个边界清楚、可校准的窄任务：

- 从报告原文中提出原子 claim 候选；
- 使用 NLI 与独立 verifier 检查 claim 是否被原文蕴含、是否保持限定条件；
- 在给定冻结候选 span 后判定支持、反驳、冲突或不可裁决；
- 匹配报告内容与预先冻结的 rubric / completeness units。

LLM 不被允许自由上网，不被允许凭参数知识补事实，也不被允许自行改变计分分母。

---

## 2. 为什么旧三项现在不够

### 2.1 旧 `Fact` 不是报告事实正确性

当前 `score_fact_support` 主要检查与商城实体绑定的价格和 overall rating，并在内部计算 volume-aware F1。代码和 README 已经明确记录：在一组 140 份报告中，只有 2 份出现可检查 claim，约百分之 98.6 的报告中 `Fact` 失活。

因此，名义权重 0.39 并不代表百分之 39 的真实区分力。更严重的是，它只衡量购物数据库中的两个字段，却被命名为整个报告的 `Fact`。

结论：保留现有结构化字段验证器，但把 `Fact` 扩展为覆盖整个报告的 claim-level factuality。

### 2.2 旧 `ProofOfFetch` 混了两个构念

当前存在两种不同语义：

- `transport_v2`：`|cited ∩ fetched_200| / |cited|`，能证明某 URL 本次被成功抓取；
- `text_v1`：评测器事后页面缓存与报告引用附近文本的逐字匹配，只能说明存在 lexical overlap，不能证明 agent 本次抓取过页面。

前者是过程事实，后者更接近 quote fidelity。二者不应共享一个名为 `ProofOfFetch` 的质量槽位。

更重要的是，“抓过页面”本身不是报告质量。一个 agent 可以抓取一百个页面、最终完全不用它们。真正应进入报告质量的是：**报告里的主张是否绑定了本次实际观察、且能支持该主张的证据。**

结论：原始 URL-level FetchRate 退出主分、保留为诊断；旧 PoF 槽由 `Evidence` 接替。

### 2.3 旧 `Completeness` 容易变成“复现预选页面”

当前 vital pool 每题通常约 14–17 条，小于 `K*=20`，实际接近对答案键的全量普查。若 vital nuggets 来自构题时预选页面，并要求同一 `source_url`，就会把出题路线变成 agent 必须复现的路线。

这无法完整测量 Deep Research：一个好报告不仅要提到若干事实，还要完成比较、机制解释、冲突处理、社区经验综合、教程、预算方案和最终决策。

结论：`Completeness` 的分母必须从 query 与冻结世界共同编译，覆盖可发现的 atomic facts 与 higher-order research units；它不再统计预选 URL，也不再把 coverage 塞进 `Fact`。

### 2.4 用户要求不能被“语料覆盖率”替代

一个报告可以覆盖大量事实，却没有回答用户真正的问题。例如，用户要求“在固定预算下比较两个方案并给出最终选择”，报告即使列出很多规格，只要没有预算约束、比较和推荐，就没有完成任务。

因此新增 `Rubric Fulfillment`：

- explicit rubric 直接来自 query 中明确写出的约束、候选、输出形式和决策要求；
- latent rubric 是完成该类研究不可缺少、但 query 未逐字写出的要求，例如处理来源冲突、区分厂商声明与用户体验、说明关键不确定性；
- 所有 latent rubric 必须在看到任何 harness 报告前生成、双人审核并冻结；
- rubric 不能把某个参考答案的具体结论或特定 URL 写成必须复现的路线。

### 2.5 旧权重没有错在小数点，而是语义未分开

`0.39 / 0.28 / 0.33` 是声明式 harm ordering 的归一化结果，不是从人类偏好、预测效度或统计拟合中得到。只要三项还存在失活、重叠和命名错位，继续调小数无法解决构念问题。

先修轴，再讨论权重。

---

## 3. 文献给出的共同结构

现有 Deep Research benchmark 很少只看一个答案是否正确。反复出现的构念可以归为四组：

| 构念家族 | 代表工作 | 对本方案的启发 |
|---|---|---|
| 内容正确性与引用准确性 | FActScore、ALCE、DeepResearch Bench FACT | 把长文本拆成 claims；事实真假与引用是否支持要分开 |
| 覆盖与信息召回 | DeepResearch Bench I/II、ResearcherBench | 深搜报告需要显式测 breadth，而不是只测少量事实 |
| 分析、综合与任务完成 | DeepResearch Bench I/II、LiveResearchBench、DEER | 比较、机制、冲突、综合和决策必须进入正式测量对象 |
| 呈现与可读性 | DeepResearch Bench I/II、DeepResearchGym、LiveResearchBench | 写作质量有价值，但不应污染可判定真实性分 |

[FActScore](https://arxiv.org/abs/2305.14251) 将长文本拆成 atomic facts 并计算被知识源支持的比例；它证明 claim-level 检查可以规模化，也提醒我们 atomicity 和去重决定指标是否可用。

[DeepResearch Bench](https://arxiv.org/abs/2506.11763) 把报告的 comprehensiveness、insight/depth、instruction-following、readability 与 FACT 引用验证分开；[DeepResearch Bench II](https://arxiv.org/abs/2601.08536) 则使用 information recall、analysis、presentation 三类细粒度标准。

[ResearcherBench](https://arxiv.org/abs/2507.16280) 同时报告 rubric insight、faithfulness 与 groundedness，而不是把“引用支持”和“信息覆盖”混成一个量。[LiveResearchBench](https://arxiv.org/abs/2510.14240) 也把 coverage、presentation、consistency、analysis depth、citation association 与 citation accuracy 分开。

DRA 的差异不是再复制这些 rubric，而是利用冻结沙盒把它们改造成：**预编译的任务事实/关系普查 + 运行时可回放的观察证据。**

---

## 4. 总体架构

\begin{figure}[htbp]
\centering
\input{dra-three-axis-architecture.tex}
\caption{DRA 四轴评分：构建期冻结 Task Evidence Census 与 Rubric Manifest，运行期只匹配报告、冻结证据和本次观察账本。}
\end{figure}

系统严格分为两个阶段。

### 4.1 构建期：昂贵但只做一次

```text
Frozen World
  → per-task multi-channel corpus scan
  → task-relevant page closure
  → semantic extraction and canonicalization
  → Task Evidence Census
  → coverage/discoverability certificate
  → frozen task scoring manifest
```

构建期 evaluator 可以使用全量 BM25、精确/近似向量检索、结构化字段查询、链接图扩展和 LLM 语义抽取。它拥有比被测 harness 更强的“全知外挂”，因为它承担的是建立测试标准，而不是与 agent 竞争搜索。

### 4.2 运行期：所有 harness 完全相同

```text
Agent report + run ledger
  → extract report claims / relations / citation bindings
  → table match against the frozen task manifest
  → Fact, Evidence, Completeness, Rubric, Provenance
  → Truth
  → writing jury/Elo reported separately
```

正式评分器不得临时重新抓取互联网，不得让 judge 使用自身知识补证据，也不得根据某个 harness 的输出改变分母。

---

## 5. 冻结语料与 Task Evidence Census

\begin{figure}[htbp]
\centering
\input{dra-three-axis-census.tex}
\caption{单题 Task Evidence Census 的编译、准入与 census-gap 修复闭环。}
\end{figure}

### 5.1 输入是冻结语料，不是新的全局前置工程

新版方案不再设置与题目无关的全局语义编译层、评分对象或必须先完成的前置项目。TEC compiler 直接读取已经冻结的沙盒语料。冻结语料至少保留：

- canonical URL / document ID；
- 页面快照和 content hash；
- block / paragraph / table cell / product field / post / reply；
- DOM 或结构位置；
- 页面类型与来源角色；
- 链接边、回复父子边、重定向边；
- agent-visible delivery serializer 的版本与哈希。

BM25/FTS、dense embedding、结构化检索和链接遍历可以作为 compiler 内部的计算实现，也可以随规模替换；它们不出现在正式分数里，不作为 benchmark 的独立发布资产，也不要求 harness 使用。原生网站与统一公开搜索 API 仍是 agent 的研究界面。

### 5.2 每题提前生成的 TEC 资产

每道题必须在发布前生成并冻结下列文件：

| 资产 | 内容 | 是否进入计分分母 |
|---|---|---:|
| `task_contract.json` | 用户约束、候选范围、所需输出类型 | 是 |
| `facets.json` | query 拆出的研究 facet | 是 |
| `rubric_items.jsonl` | explicit 与 latent 用户/研究要求、来源、审核记录 | `Rubric` |
| `task_page_census.jsonl` | 全库扫描命中的候选页、纳入/排除状态及理由 | 间接 |
| `atomic_facts.jsonl` | 可发现核心原子事实单元 | `Completeness` atomic coverage；`Fact` 裁决候选 |
| `research_units.jsonl` | 比较、机制、冲突、综合、教程、决策等高阶单元 | `Completeness` research coverage |
| `evidence_spans.jsonl` | 支持、反驳、冲突 span 与 source role | 间接 |
| `support_routes.jsonl` | 同一单元允许的 OR-of-AND 证据组合 | `Evidence` 验证 |
| `discoverability.jsonl` | 通过公开搜索/链接路径的发现证书 | 分母准入 |
| `census_counts.json` | 每一类页面、单元、span、URL、路线及排除项的固定条数 | 审计 |
| `coverage_certificate.json` | 检索饱和、已知 witness recall、抽检与版本信息 | 正式题准入 |

每份 TEC 都必须把实际条数写入 manifest，而不是只保存若干“推荐 witness”。最低统计包括：全库扫描的 document/block 数、各检索通道候选数、去重后候选页数、纳入与排除页数、core/supporting atomic units 数、各类 higher-order units 数、支持/反驳 spans 数、canonical URLs 数、等价证据集合数、support routes 数、公开可发现与 `interface_gap` 数，以及各轮新增量。

### 5.3 相关页面与命题闭包如何尽量做全

单一向量 ANN 的 top-k 不能被称为全量，也不能直接定义答案键。TEC 的对象不是“构题时挑中的页面”，而是**相对于冻结世界、预注册检索协议与公开可发现性约束的最大可审计候选集合**。构建器使用多通道 union：

1. 从 query 中拆出实体、约束、决策对象、争议点和所需输出，生成彼此独立的 facet 查询族；
2. 对冻结语料的**全部 blocks**建立 BM25/FTS 与 dense vector index；dense 检索同时使用 exact/Flat 审计切片和 ANN 全量索引，避免只相信单一近似 top-k；
3. 每个 facet 生成 lexical、semantic、entity-only、predicate-only、question paraphrase、negative/contrast 六类查询，并对每类分别取候选；
4. 对商品、日期、数值、单位、类别、作者、线程和页面类型做结构化查询，补回向量模型容易遗漏的精确字段；
5. 从候选页沿链接、回复、重定向、同商品、同实体、引用和页面版本关系扩展；
6. 按来源角色分层保留候选，防止商城、Wikipedia 或某一大域在全局 top-k 中压制论坛、论文、标准和厂商页面；
7. 对候选页抽取原子命题与高阶关系，并进行实体对齐、限定条件保留、去重和 canonicalization；
8. 对每个 canonical unit 生成 value-blind 反向查询，重新扫描整个冻结语料，分别寻找支持、反驳、条件冲突和等价表达；
9. 对每个 evidence unit 枚举所有通过语义支持与来源角色检查的 canonical URLs，形成冻结等价证据集合，而不是保存唯一 URL；
10. 使用与主 compiler 不共享 query 模板和随机种子的第二遍独立 discovery pass，以及合法替代路线的合成报告做漏项挑战；
11. 对低于检索阈值的尾部按来源、分数区间和文档类型分层抽样，估计遗漏率；
12. 重复轮次，直到预注册的饱和检查通过且所有已确认物质性 gap 均已清零。

#### 5.3.1 向量数据库的高召回配置

向量数据库用于扩大语义召回，不单独决定答案空间。每个 block 至少保存 `embedding_model_id`、向量维度、归一化方式、index build hash、document/block ID 和原文 hash。构建期采用以下组合：

- 全量 ANN 检索用于规模化候选生成；
- 在每个来源域和分数区间上使用 Flat/exact 检索审计 ANN 漏召回；
- 同时检索标题、段落、表格行、结构化字段和线程回复，不只检索整页 embedding；
- 对短查询与长 query expansion 分别编码，取 union 后按 canonical page 去重；
- 不设置单一全局 top-k，而是采用 `facet × query family × source role` 的分层配额；
- 对数字、型号、百分比和单位始终并行执行 lexical/structured lookup，因为 dense embedding 对精确值不可靠。

正式 manifest 记录每一路候选数、去重后新增量、ANN 对 exact probe 的 recall、不同 top-k 下的饱和曲线，以及被人工挑战新发现的页面与 unit。

#### 5.3.2 迭代闭包与停止规则

第 0 轮只使用 query 和 task contract；后续轮次只从已确认的实体、谓词、别名、冲突值和页面链接生成新查询。每一轮分别记录新增 page、atomic unit、research unit、support span、contradiction span 和 equivalence URL。

停止不能只看“连续一轮没有新增”。最低建议是：

1. 连续两轮没有新增 material core unit；
2. known witness recall 和 alternative-route recall 达到预注册门槛；
3. ANN 对 exact probe 的 recall 达标；
4. 来源分层尾部抽检没有确认的新 material unit；
5. 独立 DeepSeek-V4-Lite challenge pass 没有找到新的任务相关支持/反驳路线；
6. `known_material_gap_count=0`。

这里的 DeepSeek-V4-Lite 只提出遗漏候选并解释检索线索，不能直接把新 unit 写入 TEC。候选仍需绑定冻结 span，并通过独立 verifier 或人工确认。

“扫描全部 blocks”不等于让 LLM 阅读世界里的每一个 block。检索后端对全部 blocks 计算可复现分数，compiler 对多路 union 候选做语义抽取；同时对阈值以下尾部按来源与分数区间分层抽样，估计遗漏率。这样既利用整个冻结语料，又不把数百万页面全部送入昂贵 judge。

检索 query 必须尽量 value-blind：先使用 subject + predicate 检索支持与反驳候选，再由 judge 比较 value。直接把报告声称的数值写入检索词会产生 confirmation bias。

### 5.4 公平性边界

evaluator 的单题 corpus scanner 可以比 agent 的公开接口更强，但正式分母中的每个 core unit 必须满足：

$$
Answerable(u)=1
\quad\land\quad
Discoverable_{public}(u)=1.
$$

`Answerable` 要求冻结世界中至少存在支持或可判定冲突的 span；`Discoverable_public` 要求至少一条支持路线能通过所有 harness 共用的公开搜索 API 或已观察页面链接被发现。

发现证书必须绑定：

- world snapshot ID；
- search API / corpus snapshot version；
- 查询文本与查询词来源；
- 返回排名和结果快照；
- top-k 与预算；
- SERP / response hash。

只被 evaluator 内部扫描找到、却无法由公开接口发现的 unit 不进入 agent 的正式分母，而进入 `interface_gap` 诊断。

### 5.5 “完整”的诚实定义

DRA 不能声称穷尽自然语言里所有可能的表述。可声称的是：

> 相对于冻结语料快照、版本化的多通道 census compiler、预注册停止规则、人工抽检和挑战机制，TEC 对该任务的可发现核心事实与研究关系达到 protocol-complete。

它比“几条人工 gold URL”强得多，但仍需要覆盖证书和版本治理。

正式冻结的最低条件是：`known_material_gap_count=0`，独立 challenge pass 中没有确认的新 core unit 或等价证据 URL，所有 core units 均有公开发现证书，并且分层尾部抽检结果与置信区间被写入 coverage certificate。这里的“0”表示**已经发现并确认的 gap 必须全部修复**，不是声称未来发现 gap 的概率在数学上为零。

---

## 6. TEC 中的三类冻结单元

### 6.1 Atomic fact units

Atomic fact 是单一、可判定、不可再安全拆分的外部命题，例如：

- 某产品的价格、重量、尺寸、规格或声明；
- 某概念的定义；
- 某用户明确报告的一段体验；
- 某页面是否提出某项营销主张；
- 某结构化列表中是否存在一个实体或属性。

每个 atomic unit 至少包含：

```json
{
  "unit_id": "a_0017",
  "facet_id": "f_battery",
  "subject_id": "entity:...",
  "predicate": "battery_capacity",
  "object_norm": "6600 mAh",
  "qualifiers": {
    "model_variant": "...",
    "region": "...",
    "time": "...",
    "condition": "..."
  },
  "polarity": "positive",
  "importance": "core",
  "support_span_ids": ["s_..."],
  "contradiction_span_ids": ["s_..."],
  "source_role_policy": ["manufacturer", "retailer"],
  "discoverability_certificate_ids": ["d_..."]
}
```

Atomic units 有两个用途，但不重复计分：

1. 作为 `Completeness` 的 atomic coverage 分母，判断报告覆盖了多少核心事实；
2. 作为 Fact Agent 的 canonical match 和独立检索入口，判断报告主动说出的 claim 是否真实。

`Fact` 不再包含 atomic recall，因此“说得准”和“说得全”被正式拆开。

### 6.2 Higher-order research units

Higher-order unit 不是另一个原子网页字段，而是 Deep Research 必须完成的关系：

| 类型 | 例子 |
|---|---|
| `comparison` | 在同一用户约束下比较两个或多个方案的取舍 |
| `mechanism` | 解释“眼镜腿破坏密封 → 被动隔音下降”的因果关系 |
| `conflict` | 区分厂商宣传、标准含义和用户长期体验之间的冲突 |
| `cross_source_synthesis` | 组合商品页、社区经验与百科机制形成结论 |
| `community_pattern` | 不是引用一个帖子，而是准确概括多个经验的共性与边界 |
| `procedure` | 给出完整、可执行、顺序正确的教程 |
| `budget_allocation` | 在固定预算中形成方案组合并解释机会成本 |
| `decision` | 推荐与用户约束、证据和不确定性一致 |

每个 unit 必须保持原子化。例如，不创建一个“同时解释机制、比较三类产品并给出推荐”的大 unit，而拆成三个独立 relation units。这样 `covered` 可以是明确的语义匹配，不需要凭整体印象打分。

### 6.3 Explicit 与 latent rubric items

Rubric item 测的是任务履约，不是语料中出现了多少事实。它分为：

- `explicit`：直接来自用户 query 的候选范围、预算、时间、格式、比较对象、必须回答的问题和最终输出要求；
- `latent`：完成该类 Deep Research 合理需要、但用户没有逐字列出的步骤，例如处理冲突来源、说明关键不确定性、区分厂商声明与独立体验、让推荐和约束一致。

每个 rubric item 至少包含：

```json
{
  "rubric_id": "r_0012",
  "origin": "explicit",
  "query_span": "...",
  "requirement": "在5200与6600 mAh两个版本之间解释差异",
  "importance": "core",
  "admissible_outputs": ["comparison", "conflict_resolution"],
  "forbidden_answer_leak": true,
  "author_1_status": "approved",
  "author_2_status": "approved",
  "frozen_before_reports": true
}
```

latent rubric 不能规定某个赢家、某个具体数值或某条 URL，除非这些内容本来就在用户 query 中。它只能规定需要完成的研究动作。所有 rubric 必须在看到任何 harness 报告前冻结，分歧由第三人仲裁。

---

## 7. Fact：NLI 采集、独立检索与多状态裁决

### 7.1 Claim 采集不是一次自由生成

Claim pipeline 以高召回提出候选，再用原文蕴含和独立 verifier 删除 extractor 幻觉。完整流程为：

```text
Report
  → source-preserving sentence/span segmentation
  → high-recall atomic claim proposal
  → NLI entailment filter
  → DeepSeek-V4-Lite structural verifier
  → residual sentence sweep
  → entity/qualifier normalization
  → semantic deduplication
  → frozen report_claims.jsonl
```

#### Stage A：保留来源位置的分句与候选提出

先按段落、列表项、表格行、引用锚点和句法边界切分报告，保留字符 offset、原文 hash、所属标题和邻近 citation。候选提出器对每个 span 做高召回原子化：

- 并列句拆成多个 subject-predicate-object 命题；
- 数值、单位、时间、型号、地区、版本和条件不得丢失；
- “厂商声称”“某用户报告”等 attribution 必须保留；
- 否定、可能性、范围词和比较方向必须保留；
- 推荐和主观措辞不能被错误改写成客观事实。

候选提出可以使用规则、轻量 sequence tagger 或生成模型的 union。此阶段宁可多提，不直接进入计分。

#### Stage B：NLI 原文蕴含过滤

对每个候选 claim，使用原报告 span 作为 premise、规范化 atomic claim 作为 hypothesis，执行 NLI：

```text
premise = 报告原始句子或最小充分上下文
hypothesis = 候选原子 claim
label ∈ {entailment, contradiction, neutral}
```

只有 `entailment` 候选进入下一步。NLI 只验证“报告是否真的说了这个 claim”，不判断现实世界真假。对数值、否定、比较级和 attribution，另加规则一致性检查，避免 NLI 对细粒度限定词不敏感。

#### Stage C：DeepSeek-V4-Lite 结构检验

DeepSeek-V4-Lite 接收原始 span、候选 claim JSON 和允许的类型表，只执行以下窄任务：

1. 原文是否蕴含该 claim；
2. claim 是否原子化；
3. 是否添加、删除或改变了时间、版本、条件、否定和归因；
4. 是否属于 external atomic、derived arithmetic、higher-order relation、subjective 或 exempt；
5. 是否应拆分、重写或拒绝。

输出必须是固定 JSON：

```json
{
  "verdict": "accept",
  "nli_relation": "entailed",
  "atomicity": "atomic",
  "qualifier_fidelity": "pass",
  "claim_kind": "external_atomic",
  "revised_claim": null,
  "reason_code": "all_checks_pass"
}
```

模型版本、provider、prompt、temperature、schema 和输出 hash 全部冻结。DeepSeek-V4-Lite 不允许浏览互联网，也不允许在 claim extraction 阶段看到 TEC 真值标签。

#### Stage D：残差扫描与去重

为了降低漏采集，系统对每个包含实体、数字、日期、比较词、因果词或 citation anchor 的报告 span执行 residual sweep。若一个 material span 没有任何已接受 claim 覆盖，则重新进入候选提出。

最后按 canonical subject、predicate、object、qualifiers、polarity 和 attribution 去重。重复表达只保留一个 canonical claim，但保存所有 report spans，便于审计。

### 7.2 报告 claim schema

```json
{
  "claim_id": "c_0042",
  "report_span": {
    "start": 1830,
    "end": 1924,
    "raw_text": "...",
    "sha256": "..."
  },
  "subject": {
    "surface": "...",
    "world_entity_id": "entity:...",
    "binding": "exact"
  },
  "predicate": "battery_capacity",
  "object_norm": "6600 mAh",
  "qualifiers": {
    "model_variant": "...",
    "region": "...",
    "time": "..."
  },
  "polarity": "assert",
  "modality": "categorical",
  "attribution": "direct_fact",
  "claim_kind": "external_atomic",
  "evidence_policy": "citation_required",
  "dedup_group": "g_0012",
  "citations": ["binding:b_009"],
  "extractor": {
    "nli_model": "...",
    "nli_label": "entailment",
    "verifier_model": "DeepSeek-V4-Lite",
    "verifier_prompt_hash": "..."
  }
}
```

机器必须验证 `raw_text` 是报告原文的精确 substring，防止 extractor 自己发明 claim。任何自动重写都必须再次通过 NLI 和 qualifier check。

### 7.3 哪些 claim 进入 Fact

| claim 类型 | Fact | Evidence | Completeness | Rubric |
|---|---:|---:|---:|---:|
| 外部原子事实 | 是 | 通常需要 | 可覆盖 atomic unit | 视要求 |
| 来源归因事实 | 判断“该来源是否这样声称” | 需要 | 可覆盖 atomic unit | 视要求 |
| 比较、机制、冲突、综合 | 原子前提进 Fact | 外部前提需要 | 可覆盖 research unit | 可能 |
| 可复算算术/单位换算 | 验证计算，不当外部事实 | 前提需要 | 可作为 comparison 前提 | 可能 |
| 用户在 query 中给定的条件 | 豁免 | 豁免 | 不当外部发现 | 可进入 explicit rubric |
| 纯推荐、主观措辞 | 否 | 外部前提另判 | 可覆盖 decision unit | 可能 |
| 冻结世界外且不可裁决 | 不奖不罚 | 有快照时另判 | 不进入冻结分母 | 不自动满足 |

“常识豁免”必须很窄：若一句话包含具体实体、数值、时间、比较、外部机制或决定推荐的关键前提，默认需要外部证据。物理常识可以作为连接推理，但若它本身就是 query 要审核的争议点，就不能豁免。

### 7.4 Fact Agent 必须独立于报告引用

Evidence Agent 打开报告绑定的 URL，判断该页面是否支持 claim。Fact Agent 则必须从冻结世界独立寻找支持和反驳证据，不能把“网页上这样写”直接等同于“事实为真”。

对每个 material atomic claim，Fact Agent 执行：

1. 隐藏报告引用 URL，先用 subject + predicate + qualifiers 做 value-blind 检索；
2. 从 BM25、dense、structured 和 graph expansion 的 union 中取得候选 spans；
3. 分别构造 support、refute、conflict 和 variant-context 证据集合；
4. 按 claim 类型检查 source role，例如官方规格适合判定型号参数，论坛个例只适合证明“某用户报告过”；
5. 生成固定 evidence packet；
6. 由 DeepSeek-V4-Lite Fact verifier 在 evidence packet 内裁决；
7. 第二遍才允许查看报告绑定 URL，用于识别 attribution、版本差异和漏掉的等价证据；
8. 高影响、低置信度、冲突和 gap 进入人工复核。

Evidence packet 示例：

```json
{
  "claim_id": "c_0042",
  "claim": "产品A的电池容量是6600 mAh",
  "support": [
    {"span_id": "s_101", "source_role": "retailer", "value": "6600 mAh"}
  ],
  "refute": [
    {"span_id": "s_202", "source_role": "manufacturer", "value": "5200 mAh"}
  ],
  "variant_context": [
    {"span_id": "s_303", "relation": "possible_region_or_model_variant"}
  ],
  "retrieval_manifest_hash": "...",
  "world_snapshot_id": "..."
}
```

Fact verifier 只能引用 packet 中的 span ID，不允许使用参数知识补事实。营销页面支持“厂商/商品页提出了该声明”，不自动支持“该性能已被独立验证”；论坛个例支持“该用户报告了此体验”，不自动支持“所有用户都会如此”。

### 7.5 Fact 的多状态裁决

Fact verdict 使用：

- `true`：在完整限定条件下被足够证据支持，且没有未解决的同条件反驳；
- `false`：被更合适来源或明确反驳 span 否定；
- `conflicted`：同条件下存在无法自动消解的支持与反驳；
- `unresolved`：冻结世界有相关材料，但不足以判断真假；
- `out_of_world`：claim 超出冻结世界可裁决范围；
- `census_gap`：支持/反驳材料实际存在于冻结世界，但 TEC 未收录会影响评分的 unit 或证据路线；
- `exempt`：用户给定条件、纯主观表达或其他不应进入 Fact 的内容；
- `instrument_ambiguous`：claim extraction、实体绑定、解析或 judge 本身不可靠。

DeepSeek-V4-Lite 与第二个独立 verifier 一致且置信度超过预注册阈值时可自动接受。`false`、`conflicted`、`census_gap`、高影响 `unresolved` 和随机抽取的高置信结果进入人工审核，用于估计自动裁决误差。

### 7.6 冻结世界外不惩罚

报告提到冻结世界外的数据时，不因为 benchmark 没有收录它就自动判错：

- `out_of_world` 不进入 Fact 的分子或分母，因此增加这类 claim 不会降低、也不会提高 Fact；
- 它不进入当前版本的 Completeness 分母，也不能凭自身新增主分 credit；
- 若它与任务无关或只是扩写，记录 `out_of_world_claim_rate` 后继续评分；
- 若它任务相关、物质性强，并可能改变正确答案或正式排名，则标记 `world_scope_gap`，该题 withheld，而不是处罚先发现它的报告；
- 若证据其实位于冻结世界，只是 TEC compiler 漏掉，则不是 `out_of_world`，而是 `census_gap`，必须升版并统一重算。

为防止模型用大量不可裁决 claim 逃避评测，系统发布 out-of-world 数量、占比和 materiality，并对高占比报告进行人工审计；这些诊断不直接扣分。报告仍只能通过冻结的 Rubric 与 Completeness units 获得任务完成 credit。

### 7.7 Fact 公式

令 $\mathcal{C}^{T}_t$ 与 $\mathcal{C}^{F}_t$ 分别为报告中经裁决为 `true` 和 `false` 的去重 material atomic claims，$m(c)$ 为预先定义的 materiality 权重，则：

$$
Fact_t
=
\frac{\sum_{c\in\mathcal{C}^{T}_t}m(c)}
{\sum_{c\in\mathcal{C}^{T}_t\cup\mathcal{C}^{F}_t}m(c)}.
$$

若没有任何 in-scope、可裁决的 material atomic claim，则 $Fact_t=0$；这是“没有产生可测事实”的结果，不是对 out-of-world claim 额外扣分。事实覆盖率不再进入 Fact，而进入 Completeness。

同时强制发布：

- `fact_true_rate`；
- `fact_false_rate`；
- `fact_conflict_rate`；
- `fact_unresolved_rate`；
- `out_of_world_claim_rate`；
- `fact_adjudication_coverage`；
- 自动裁决与人工裁决的分歧率。

### 7.8 表外 claim 或 URL 的版本治理

正式 scorer 只查冻结表。报告中的未匹配 claim 先标记为 `pending_table_match`：

1. 若它只是已有 unit 的新表述，matcher 映射到已有 canonical unit；
2. 若它超出冻结世界，标记 `out_of_world`，不奖不罚；
3. 若它被世界内证据明确反驳，按 `false` 处理；
4. 若它是真实、任务相关、物质性的新 unit，且证据位于冻结世界，则触发 `census_gap`；
5. 若它揭示冻结世界本身缺少完成任务所需的材料，则触发 `world_scope_gap`；
6. 两类 material gap 都使该题退出当前正式聚合，修复后对全部报告统一重算。

新 URL 使用同样原则，但要区分：

1. 已登记页面的重定向、镜像别名或 canonicalization 结果，确定性归并；
2. URL 真实但内容不支持对应命题，Evidence binding 失败；
3. URL 位于冻结世界外且当前 evaluator 无快照，标记 `out_of_world_url`，不自动判 claim 为假；
4. URL 确实为已有 evidence unit 提供了此前漏登记的合法冻结 span，触发 `evidence_equivalence_gap`。

任何 gap 都不能在当前版本临时补进等价集合并只给发现者得分。正确做法是冻结当前任务结果，补齐 TEC、重新执行反向枚举和挑战审计，提升版本，再统一重算所有 harness。

---

## 8. Evidence：接替旧 ProofOfFetch 槽

### 8.1 为什么不能只按 URL 计

一个 URL 可以支持二十个 claims，也可能一个都不支持。仅计算 `|cited ∩ fetched| / |cited|` 会漏掉：

- 抓过页面但引用位置与 claim 错绑；
- 页面相关但不支持附近说法；
- 页面明确反驳报告；
- 参考文献区堆 URL，没有任何就地引用；
- 只看到搜索 snippet，却写出超出 snippet 的深层结论。

因此，Evidence 同时使用两个分母：citation binding precision 与 claim/unit evidence coverage。

### 8.2 Citation binding

一个 binding 是：

```text
报告 claim/research-unit span
× 文内 citation anchor
× canonical URL
× 被观察的 source span
```

只列在 bibliography、没有文内 anchor 的 URL 不构成支持 binding，但仍进入 URL 完整性诊断。

### 8.3 一个 binding 何时通过

对 binding $b$，定义：

$$
Pass(b)
=
Valid(b)
\land Observed(b)
\land Bound(b)
\land Supports(b)
\land RoleOK(b).
$$

- `Valid`：URL 属于冻结 registry，canonicalization 成功；
- `Observed`：本次运行账本证明 agent 实际收到支持文本；
- `Bound`：文内引用在局部上绑定对应 claim，而不是参考文献漂移；
- `Supports`：观察到的 span 语义支持完整 claim；
- `RoleOK`：来源角色足以支持 claim 的措辞与强度。

`Provenance` 只判断 URL 是否真实存在、可规范化并有冻结快照。URL 如何被搜索发现、本次是否打开以及收到的是 snippet 还是完整页面，由 Execution Audit 分别报告；其中“是否实际观察到足够文本”继续作为 Evidence 的必要条件。

### 8.4 Evidence Agent：NLI 初筛、DeepSeek-V4-Lite 复核与人工抽查

Evidence Agent 只判断“报告 claim 与绑定页面之间的支持关系”，不判断世界最终真相。对每个 binding：

1. 根据 citation anchor 找到最小 report claim span；
2. 从运行账本恢复 agent 实际看到的最小 source span；
3. 以 source span 为 premise、report claim 为 hypothesis 执行 NLI；
4. `contradiction` 直接进入失败候选，`neutral` 进入 insufficient 候选，`entailment` 进入复核；
5. DeepSeek-V4-Lite 检查数值、单位、否定、时间、型号、条件、attribution 和 source role；
6. 输出 `support / refute / insufficient / wrong_scope / wrong_role / ambiguous`；
7. 高影响 claim、模型分歧、低置信结果和随机样本交由人工检查。

NLI 负责高吞吐初筛，DeepSeek-V4-Lite 负责细粒度限定词和来源角色，人工负责校准边界。三个阶段都只能使用冻结 source span，不允许自由上网或使用模型参数知识补证据。

### 8.5 整页与 snippet 的统一规则

观察对象不是“URL 字符串”，而是 agent 实际收到的 bytes：

- 整页抓取：日志保存 status 200、body hash、delivery serializer 与可定位 blocks；
- 搜索 snippet：日志必须保存 snippet 原文或 content-addressed blob，而不只是 URL；
- 仅看到 URL：没有内容观察，不能支撑 claim。

当 snippet 本身完整包含支持 claim 的 span 时，它是合法的 observed evidence，可以给满 binding credit。若 claim 超出 snippet 内容，即使 URL 真实存在，也记 `insufficient_observation`，binding 失败。

这不会不公平地偏袒 snippet-only harness：浅 factoid 可以由 snippet 支持；需要上下文、表格、冲突或长证据链的主张必须读取更完整内容。能力差异出现在真正需要能力的位置，而不是先给所有 snippet harness 固定扣 0.28。

### 8.6 Evidence 公式

令：

- $\mathcal{B}_t$：报告中的全部 material in-text citation bindings；
- $\mathcal{B}^{pass}_t$：通过上述五腿的 bindings；
- $\mathcal{X}^{cite}_t$：报告中全部 citation-required atomic claims 与 higher-order units；
- $\mathcal{X}^{grounded}_t$：至少有一个 passing binding 的 units。

$$
P^{evidence}_t
=
\frac{|\mathcal{B}^{pass}_t|}{|\mathcal{B}_t|},
\qquad
R^{evidence}_t
=
\frac{|\mathcal{X}^{grounded}_t|}{|\mathcal{X}^{cite}_t|}.
$$

$$
Evidence_t
=
\begin{cases}
\dfrac{2P^{evidence}_tR^{evidence}_t}
{P^{evidence}_t+R^{evidence}_t},
&P^{evidence}_t+R^{evidence}_t>0,\\[6pt]
0,&\text{otherwise.}
\end{cases}
$$

若正式任务要求外部研究而报告没有 citation，则 $Evidence_t=0$。若运行日志缺失或无法完整归责，整个 run 的正式 `Truth` 被 withheld；不把 Evidence 记成 0，也不对其他轴重归一化。

### 8.7 原始 PoF 留在哪里

以下指标继续发布，但不进入 Quality：

$$
FetchRate_t
=
\frac{|CitedURLs_t\cap Fetched200_t|}{|CitedURLs_t|}.
$$

同时报告：

- `snippet_observation_rate`；
- `full_page_observation_rate`；
- `fetched_but_unused_rate`；
- `search_returned_but_unopened_rate`；
- `quote_fidelity_text_v1`，仅诊断；
- 各 harness 的 observation tier 分布。

`text_v1` 不得回落为正式 Evidence，也不得再以 ProofOfFetch 名义混入同一榜单。

---

## 9. Completeness：相对可发现内容集合的覆盖率

### 9.1 Completeness 不再与 Fact 重复

`Fact` 只测报告主动说出的可裁决事实是否准确；`Completeness` 接管全部 coverage，回答：

> 相对于冻结世界中按照预注册协议能够发现、能够回答且与任务相关的内容集合，报告覆盖了多少？

它同时覆盖 atomic facts 与 higher-order research units，但分层计算，防止某一类数量特别多的单元淹没其他研究能力。

### 9.2 Atomic 与 research unit coverage

对每个 TEC unit $u$，定义：

$$
Covered_t(u)=1
$$

当且仅当报告中存在一个去重 span：

1. 与 $u$ 的 subject、predicate/relation、object、direction、condition、polarity 和 attribution 匹配；
2. 没有被同条件 contradiction span 明确反驳；
3. 对 comparison/decision unit，包含要求的候选与约束；
4. 对 conflict unit，表达冲突双方及适用边界；
5. 对 cross-source unit，不只复述单一来源；
6. 对 atomic unit，不能只出现实体名而没有对应事实。

Completeness 的 unit match 不要求报告复现构题 URL。只要报告内容与 canonical unit 匹配，并满足相应 Evidence 要求，就可以通过合法替代路线覆盖。

### 9.3 分层宏平均

令 $\mathcal{U}_{t,f,g}$ 为任务 $t$、facet $f$、unit type $g$ 下的 core units，其中 $g$ 包括 `atomic`、`comparison`、`mechanism`、`conflict`、`synthesis`、`procedure` 和 `decision`。先计算：

$$
C_{t,f,g}
=
\frac{\sum_{u\in\mathcal{U}_{t,f,g}}Covered_t(u)}
{|\mathcal{U}_{t,f,g}|}.
$$

设 $\mathcal{K}_t=\{(f,g):|\mathcal{U}_{t,f,g}|>0\}$，则：

$$
Completeness_t
=
\frac{1}{|\mathcal{K}_t|}
\sum_{(f,g)\in\mathcal{K}_t}C_{t,f,g}.
$$

这样，一个包含大量商品字段的 facet 不会压制只有少数机制或冲突 unit 的 facet。题目中不适用的类型不进入平均。

### 9.4 “最大子集”的可审计含义

这里的最大子集不是数学意义上穷尽冻结世界的所有自然语言命题，而是：

> 由 BM25、dense vector、structured lookup、graph expansion、反向检索、来源分层、独立 challenge pass 和尾部抽检共同建立的 protocol-complete discoverable set。

正式发布时，每题必须提供：

- 各检索通道召回的页面与 unit 数；
- 每轮新增量与饱和曲线；
- known witness 与 alternative-route recall；
- ANN 相对 exact probe 的 recall；
- source-stratified tail audit；
- core unit 的公开 discoverability certificate；
- 已知 material gap 为 0 的冻结状态。

### 9.5 深度如何进入 Completeness

不另加一个凭整体印象评分的 `Depth` 标量。Depth 通过需要多步研究的 unit 类型进入：

- 单一页面复述只能覆盖 atomic fact；
- comparison 需要对齐多候选与同一约束；
- mechanism 需要方向、条件和因果边；
- conflict 需要支持与反驳双方；
- cross-source synthesis 需要多个来源角色；
- decision 需要把证据、用户约束、不确定性和结论连接起来。

---

## 10. Rubric Fulfillment：用户要求与潜在研究要求

### 10.1 两类 rubric

对每个任务构建：

$$
\mathcal{R}_t
=
\mathcal{R}^{explicit}_t
\cup
\mathcal{R}^{latent}_t.
$$

`explicit` 直接来自 query，不得改写其语义；`latent` 只能补充完成该任务所必需的研究动作，不能预埋参考答案。候选 latent rubric 由 query-only Rubric Agent 提出，DeepSeek-V4-Lite 检查是否必要、是否答案泄漏、是否与其他项重复，再由两名标注者在不看报告的条件下审核冻结。

### 10.2 Rubric item 的通过条件

每个 rubric item $r$ 的 verdict 为：

- `fulfilled`：报告明确完成要求；
- `partially_fulfilled`：完成可拆分要求中的一部分；
- `not_fulfilled`：未完成；
- `not_applicable`：构建期确认该题不适用，冻结后不能临时改；
- `ambiguous`：judge 无法可靠判断，进入人工复核。

core rubric 应尽量拆成可二元判断的原子要求；只有天然可分段的 procedure 或多候选比较允许预注册部分分。

### 10.3 Rubric 公式

令 $v_t(r)\in\{0,0.5,1\}$，$q(r)$ 为冻结 importance 权重，则：

$$
Rubric_t
=
\frac{\sum_{r\in\mathcal{R}_t}q(r)v_t(r)}
{\sum_{r\in\mathcal{R}_t}q(r)}.
$$

Rubric judge 不能把“提到了很多相关事实”直接当作满足用户要求。例如，报告列出大量电池参数，却没有按预算比较、处理 5200/6600 mAh 冲突或给出最终建议，则 Completeness 的部分单元可能通过，但对应 Rubric 仍失败。

### 10.4 防止 latent rubric 变成隐藏答案

每个 latent rubric 必须满足：

1. 能从 query、任务类型和一般研究规范解释其必要性；
2. 不指定某个答案赢家、具体数值或特定 URL；
3. 在看到所有 harness 报告前冻结；
4. 有双人审核与分歧仲裁记录；
5. 通过 leave-one-rubric-out 和人类适当性评估；
6. 若正式运行暴露必要但漏掉的 rubric，触发 `rubric_gap` 并统一升版重算。

---

## 11. Provenance：只测 URL 是否真实存在

### 11.1 定义

令 $\mathcal{Z}_t$ 为报告引用的 canonical evidence URL 集。对 URL $z$：

$$
ValidURL(z)
=
Canonicalized(z)
\land
InRegistry(z)
\land
SnapshotAvailable(z).
$$

其中 `SnapshotAvailable` 要求冻结 HTTP 200 页面或可验证的等价成功快照，并绑定 content hash。若页面在冻结世界外且 evaluator 无法取得快照，标记 `out_of_world_url`，不自动把相关 claim 判假，但该 URL 不能获得 Provenance credit。

$$
Provenance_t
=
\frac{\sum_{z\in\mathcal{Z}_t}ValidURL(z)}
{|\mathcal{Z}_t|}.
$$

当 $|\mathcal{Z}_t|=0$ 时定义 $Provenance_t=0$。

### 11.2 发现与抓取过程单独审计

URL 是否通过 search API 返回、是否由页面链接发现、是否被实际打开，仍然重要，但不再混入 URL existence 的定义。Execution Audit 单独发布：

- `search_discovered_url_rate`；
- `link_discovered_url_rate`；
- `guessed_real_url_rate`；
- `fetched_200_rate`；
- `search_returned_but_unopened_rate`；
- `snapshot_hash_match_rate`。

Evidence 中的 `Observed` 继续要求本次运行实际看到足够支持 claim 的文本。因此，一个猜中的真实 URL 可以获得 Provenance，但若没有观察内容，Evidence 仍失败。

### 11.3 为什么与 Evidence 不相同

- Provenance 按 URL，问“这个来源是否真实存在并有冻结快照？”；
- Evidence 按 binding 与 claim，问“本次观察到的页面内容是否支持报告说法？”

| 情况 | Provenance | Evidence |
|---|---:|---:|
| URL 真实，但引用内容不支持 claim | 高 | 低 |
| URL 真实且支持，但本次没有观察到内容 | 高 | 低 |
| URL 伪造或无法规范化 | 低 | 无 passing support |
| URL 真实、实际观察、正确绑定并支持 | 高 | 高 |

URL 伪造会降低 Provenance，并使相关 binding 无法通过。另行报告 fabricated URL 数量和比例，便于解释重复影响。

---

## 12. 最终合成与权重

\begin{figure}[htbp]
\centering
\input{dra-three-axis-denominators.tex}
\caption{五个分数使用不同分母：Provenance 作为 URL 有效性外层，四个互补质量轴进入 Quality。}
\end{figure}

### 12.1 候选正式公式

$$
Quality_t
=
\frac14Fact_t
+
\frac14Evidence_t
+
\frac14Completeness_t
+
\frac14Rubric_t.
$$

$$
Truth_t
=
Provenance_t\cdot Quality_t.
$$

不再使用 `Provenance^1.5`；指数没有独立构念，直接乘法最容易解释：

> 一份报告在事实准确、证据绑定、信息覆盖和任务履约上获得的质量，只有在其引用 URL 真实存在并具有冻结快照时才兑现。

### 12.2 为什么先等权

四个轴已经经过构念去重，但当前没有证据证明其中任何一轴的一分应值另一轴的固定倍数。使用两位小数只会制造错误精度。

等权版本必须配套：

1. 发布四个 raw axes；
2. 在四维权重 simplex 上做系统敏感性分析；
3. 报告 top-k 排名稳定率、两两顺序翻转率和各 harness 的可胜区域；
4. 使用独立人类内容偏好只验证排序相关性，不在 formal test 上拟合权重；
5. 额外报告最低轴门槛与几何平均 ablation，检查线性加权是否让关键短板被其他轴补偿；
6. 任何权重或聚合规则修改都提升 scorer major version，并重算全部历史输出。

### 12.3 Legacy ablation

同一批新轴可以额外计算：

$$
Truth_t^{legacy\ weights}
=
Provenance_t
\left(0.39Fact_t+0.28Evidence_t+0.33Completeness_t\right).
$$

该值仅用于回答“排名是否依赖权重”，不作为首个正式榜默认。

### 12.4 缺失轴不重归一化

若某个 formal run 的 ledger、report、registry snapshot 或 TEC manifest 不完整：

- `Truth_t` 标记 `withheld`；
- 不把缺失轴当 0 诬罚 agent；
- 不把剩余轴重归一化后伪装成同一指标；
- 修复基础设施后重跑或重算。

这保证所有榜单行使用同一个测量工具。

### 12.5 跨任务聚合

对固定任务集 $\mathcal{T}$：

$$
Score_h
=
\frac{1}{|\mathcal{T}|}
\sum_{t\in\mathcal{T}}Truth_{h,t}.
$$

使用 task macro-average，避免 TEC unit 数量多的题获得更大任务权重。基础设施不可归责失败被 withheld；可归责的超时、空报告或 harness 失败按预注册运行规则计 0。

---

## 13. 写作 Elo 单独报告

写作 jury 只比较：

- 语言是否清楚；
- 结构是否易读；
- 术语是否一致；
- 是否有不必要重复；
- 表格与段落是否帮助读者理解。

它不得重新判断引用真假、Fact、Evidence、Completeness 或 Rubric。建议使用位置交换的 pairwise judging，拟合 Bradley–Terry 分数，同时发布：

- judge–human agreement；
- 双人 Cohen's kappa / Krippendorff alpha；
- position bias 与 length bias；
- bootstrap confidence interval。

Elo/BT 依赖参赛池，是展示性和写作偏好指标，不与 `Truth` 相乘，也不作为隐藏 tie-break。

正式裁判 instruction、JSON 输出合同、位置交换、长度窗口和 Bradley–Terry 拟合规则冻结在 `DRA_WRITING_ELO_JUDGE_INSTRUCTION_2026-07-23.md`，协议名为 `dra_writing_elo_v1`。

---

## 14. 失败类型的唯一责任表

| 失败类型 | Fact | Evidence | Completeness | Rubric | Provenance | 诊断 |
|---|---:|---:|---:|---:|---:|---|
| `fabricated_url` | 内容另判 | 无有效 binding | 相关 unit 可能未 grounded | 内容另判 | 失败 | 数量/比例 |
| `guessed_real_url` | 内容另判 | 只有实际观察并支持才通过 | 内容另判 | 内容另判 | URL 存在则通过 | discovery diagnostic |
| `unobserved_citation` | 内容另判 | 失败 | 内容匹配可诊断但未 grounded | 内容另判 | URL 存在则通过 | snippet/full-page 状态 |
| `wrong_binding` | 内容可能正确 | 失败 | 内容若正确可匹配 | 内容另判 | 不受影响 | binding error |
| `unsupported_citation` | claim 可能为真 | 失败 | 内容另判 | 内容另判 | 不受影响 | support verdict |
| `false_claim` | 失败 | 相关 binding 通常失败 | 对应 unit 不覆盖 | 可能失败 | 不受影响 | critical claim flag |
| `omitted_atomic_fact` | 不受影响 | 不适用 | atomic coverage 下降 | 视要求 | 不适用 | atomic miss |
| `omitted_comparison/mechanism` | 原子前提另判 | 不适用 | research coverage 下降 | 可能失败 | 不适用 | unit-type miss |
| `missed_explicit_requirement` | 不受影响 | 不受影响 | 内容另判 | 失败 | 不受影响 | explicit rubric miss |
| `out_of_world_claim` | 不奖不罚 | 有快照时另判 | 不进入冻结分母 | 不自动满足 | URL 另判 | 数量/占比 |
| `fetched_but_unused` | 不受影响 | 无 credit | 不受影响 | 不受影响 | URL 可能有效 | process waste |
| `census_gap/rubric_gap` | 题目 withheld | 题目 withheld | 题目 withheld | 题目 withheld | 不适用 | 触发版本修复 |
| `world_scope_gap` | 不处罚报告 | 不处罚报告 | 题目 withheld | 题目 withheld | URL 可另判 | 修复世界或移除题目 |

这张表不是说所有失败完全统计独立，而是规定每个轴的主问题，防止用同一个 URL 集合同时解释所有质量维度。

---

## 15. 极端案例推演

### 15.1 空报告或纯格式空壳

- 没有可裁决事实，Fact 为 0；
- Evidence 为 0；
- Completeness 为 0；
- Rubric 为 0；
- Provenance 为 0；
- Truth 为 0。

### 15.2 一条完全正确且有证据的短答案

- Fact 可以很高，因为说出的事实准确；
- Evidence 可高；
- 相对 atomic + research unit bank 的 Completeness 很低；
- 若用户要求完整比较和推荐，Rubric 也低；
- 因此不会因为“只说一句真话”接近满分。

### 15.3 宽泛事实堆砌，没有比较和结论

- Fact 可高；
- Evidence 可高；
- comparison/mechanism/decision units 大量缺失，Completeness 低；
- 用户要求的比较或结论未完成时，Rubric 低；
- 这正是 Deep Research 与普通 fact collection 的区别。

### 15.4 逻辑漂亮但靠参数知识，没有本次引用

- Fact 和 Completeness 可能在内容上较高；
- Evidence 低；
- 无 citation 时 Provenance=0；
- Truth=0，明确测出“说对了但没有证明是本次研究所得”。

### 15.5 抓了许多页面但引用全错

- raw FetchRate 高；
- Evidence binding precision 低；
- raw fetch 不再直接买质量分。

### 15.6 Snippet-only harness 完成浅事实核对

- 若日志中的 snippet 完整支持 factoid，Evidence 可通过；
- FetchRate 为 0，作为诊断披露；
- 若它尝试基于 snippet 写长上下文结论，Observed/Supports 失败。

### 15.7 使用不同于构题路线的真实页面

正式 TEC 应已通过反向全语料扫描把它列入 support equivalence class，因此正常得分。若未列入而经仲裁确认有效，触发 census gap 和统一重算；不能只给该 harness 私下开例外。

若该页面确实位于冻结世界外，相关 claim 标记 `out_of_world`，不奖不罚；只有当它任务相关、物质性强且会改变正确答案时，触发 `world_scope_gap` 并暂停该题。

### 15.8 一个伪造 URL 混在十个真实 URL 中

- Provenance 约按比例下降；
- 相关 claim 没有 passing binding 时 Evidence recall 下降；
- 不把整题一票否决；
- fabricated count 单列，读者能直接看到诚信问题。

### 15.9 报告内容优秀但文风很差

- Truth 可以很高；
- writing Elo 低；
- 两个结果共同描述报告，而不是相互污染。

### 15.10 运行日志坏了

- 不能知道 agent 是否实际看到证据；
- 该 run withheld，而不是 `Evidence=0` 或自动退回 `text_v1`；
- 修复后重跑。

### 15.11 引用页面支持说法，但世界证据反驳

- Evidence 可以高，因为引用页面确实这样写；
- Fact 为低或进入 `conflicted`，因为独立多来源证据不支持该结论；
- 如果差异来自型号、地区或时间，Fact Agent 必须保留限定条件，不得把版本冲突误判为 false；
- 这正是 Fact 与 Evidence 分开的必要案例。

---

## 16. Census gap 与版本治理

### 16.1 为什么不能把 on-demand 当正常功能

如果正式输出经常找到表外有效证据，说明构建期“相关页面闭包”和等价类没有做全。把它静默补进当前报告会产生三个问题：

- 分母在不同 harness 之间变化；
- 后跑系统比先跑系统获得更完整答案键；
- benchmark 无法复现。

因此，on-demand matcher 只作挑战与审计入口。

这里的 matcher 只能回答“当前版本是否暴露了资产缺口”，不能改变当前版本的分子或分母。正式计分路径中不存在 `dynamic_append=true`。

### 16.2 挑战流程

```text
report produces unmatched material claim / URL
  → deterministic canonicalization and duplicate check
  → frozen-world evidence review
  → task-relevance review
  → if invalid/irrelevant: score normally
  → if outside frozen world and non-material: neutral out_of_world
  → if outside frozen world and material: world_scope_gap
  → if valid and already equivalent: compiler/matcher bug
  → if valid new claim: atomic_or_relation_census_gap
  → if valid new supporting URL: evidence_equivalence_gap
  → if valid missing requirement: rubric_gap
  → task status = needs_recompile
  → TEC version bump
  → recompute every historical report for that task
```

不允许只修改某一个系统的分数。每次修复必须留下 before/after manifest hash、unit diff、受影响报告数量和排名变化。

### 16.3 防止恶意 DoS

只有同时满足以下条件才触发 census/rubric gap：

1. claim/URL 在冻结 registry 中可核验；
2. 证据 span 确实支持完整命题；
3. 命题与 query 的正式 facet 相关；
4. 它不是已有 unit 的表面改写；
5. 它会新增 core atomic unit、research unit、rubric item 或 equivalence member。

虚构、无关、重复和非物质性的 out-of-world 内容不触发升版。已确认的任一种 material gap 都必须清零后才能重新发布该任务；不设置按缺口比例忽略问题的容忍阈值。

---

## 17. 校准与验证计划

### 17.1 TEC corpus scan 召回

| 测试 | 数据 | 建议准入目标 |
|---|---|---|
| known witness recall | 构题时已知、冻结后隐藏的 support spans | 各域 Recall@candidate ≥ 0.95 |
| alternative-route recall | 人工/独立检索找到的替代页面 | false reject ≤ 0.05 |
| source-stratified recall | 商城、论坛、百科、论文等 | 每类单独达标，不只看总体 |
| ANN exact-probe recall | 分层 Flat/exact 检索切片 | 达到预注册门槛并报告置信区间 |
| saturation | 每轮新增页面/unit/equivalence member | 曲线达到预注册平台期 |
| tail audit | 阈值以下来源/分数分层样本 | 无确认 material 漏项 |
| parser round-trip | 表格、回复树、字段、链接 | 结构化关键字段精确率/召回率 ≥ 0.99 |
| discoverability | 公开 search API 证书回放 | 全部可重放 |

数值是工程 go/no-go 候选，应先在 Dev-14 上验证后预注册；未达标不能把任务标为 `frozen`。

### 17.2 Claim extractor

对 Dev-14 与多 harness 报告分层抽样，双人标注 claim 边界、类型、豁免类别与去重组：

- exact/overlap claim boundary F1；
- NLI entailment precision/recall；
- qualifier fidelity，单独覆盖数值、单位、否定、时间、型号和 attribution；
- DeepSeek-V4-Lite accept/rewrite/reject 与人工一致率；
- claim-kind macro-F1；
- material external claim recall；
- duplicate collapse precision；
- residual sentence escape rate；
- extractor escape rate。

候选准入目标：边界 F1 ≥ 0.90，类型 macro-F1 ≥ 0.85，material claim recall ≥ 0.95。

### 17.3 Fact 与 Evidence judge

构建平衡校准集，覆盖：

- supported；
- contradicted；
- true / false；
- conflicted / unresolved；
- `out_of_world` / `census_gap`；
- wrong binding；
- mixed / source-role conflict；
- snippet sufficient / insufficient；
- paraphrase 与数值单位等价。

每项由两名独立标注者判断，分歧仲裁。报告：

- human–human Cohen's kappa；
- Krippendorff alpha；
- judge–human macro-F1；
- 各类别 precision/recall；
- false acceptance / false rejection；
- 置信区间。

候选准入目标：三分类 kappa ≥ 0.70，judge macro-F1 不低于 human agreement band，`contradicted` precision ≥ 0.90。

Fact 与 Evidence 必须分别校准：Evidence judge 只能看报告 claim、绑定 URL 和本次观察 span；Fact judge 只能看独立检索 evidence packet，并在第一遍隐藏报告引用。若两者共享同一输入，实验不能证明两个构念已经分开。

### 17.4 Rubric judge

对 explicit 与 latent rubric 分层标注，至少报告：

- query-to-explicit-rubric recall；
- latent rubric appropriateness；
- answer-leak rate；
- duplicate rubric rate；
- rubric–human macro-F1；
- `fulfilled / partial / not_fulfilled` 混淆矩阵；
- 双人 agreement 与分歧仲裁率。

任何 latent rubric 若包含参考答案赢家、报告特有措辞或非 query 必需的具体数值，直接判定为泄漏并禁止冻结。

### 17.5 运行账本注入测试

程序化构造：

- fabricated URL；
- guessed real URL；
- search-returned but unopened；
- snippet sufficient；
- snippet truncated；
- full page fetched；
- wrong binding；
- bibliography bleed；
- log damage；
- cross-run contamination。

集合分类、hash、run isolation 和 withhold code 应接近确定性全部通过。

### 17.6 端到端不变量

正式 scorer 必须通过：

- 添加一个正确、已观察、支持且任务相关的 unit 不得降低分数；
- 添加一个错误 claim 不得提高 Fact；
- 添加一个 out-of-world claim 不得改变 Fact；
- 只增加无关 fetch 不得提高 Evidence；
- 替换为同一 equivalence class 的证据 URL 不得降低分数；
- 删除一个 core atomic 或 research unit 不得提高 Completeness；
- 删除一个已满足的 core rubric 不得提高 Rubric；
- 一条 fabricated URL 不得增加任何主轴；
- 缺日志不得自动变成 0 或 `text_v1`；
- 改变 harness 不得改变同一任务的 TEC 分母。

### 17.7 权重敏感性

在 simplex $w_F+w_E+w_C+w_R=1$ 上采样，至少报告：

- 榜首稳定区域；
- top-3 集合稳定率；
- 两两 harness 顺序翻转概率；
- leave-one-axis-out 排名；
- equal weight 与 legacy weight 的 Kendall/Spearman 相关；
- 结论依赖某一狭小权重区域时的警告。

---

## 18. 一道任务的示意产物

以下数字仅示意 schema，不是现有题目的正式统计：

```yaml
task_id: headphone_glasses_flight_demo
tec_version: 1
corpus_snapshot: corpus-v1-demo

atomic_fact_bank:
  total_core: 18
  by_facet:
    seal_and_glasses: 4
    anc_low_frequency: 3
    comfort: 4
    portability: 3
    battery: 4

research_units:
  total_core: 13
  by_type:
    comparison: 3
    mechanism: 2
    conflict: 2
    community_pattern: 2
    cross_source_synthesis: 2
    decision: 2

rubric_items:
  total_core: 7
  explicit: 4
  latent: 3
  double_review_status: passed

evidence:
  support_spans: 61
  contradiction_spans: 14
  canonical_urls: 29
  support_routes: 37

certificates:
  answerable_core_units: 31
  discoverable_core_units: 31
  witness_recall: 1.0
  ann_exact_probe_recall: 0.98
  out_of_world_policy: neutral
  human_audit_status: passed
```

正式任务必须把真实统计直接写入 manifest 和题目 factsheet，不能只在论文中口头描述。

---

## 19. 实施路线

### Phase 0：公式与 schema 锁定

- 固定本文件中的五个主对象：Atomic Fact、Evidence Binding、Completeness Unit、Rubric Item、URL Provenance；
- 固定 NLI 与 DeepSeek-V4-Lite 的模型快照、prompt、JSON schema 和人工升级规则；
- 固定空分母、withhold、census gap 与版本规则；
- 发布 JSON Schema 和最小 oracle cases；
- 不先锁小数权重之外的隐含阈值。

### Phase 1：单题完整 TEC

选择一道人类已充分理解、三类来源齐全的 dev 题：

- 从 query-only 启动 census；
- 禁止用旧 graph 的 URL 作为检索白名单；
- 旧 witnesses 只作最终 recall probe；
- 列出全部 atomic facts、research units、support/contradiction equivalence classes；
- 编译 explicit/latent rubric 并完成双人盲审；
- 运行 ANN/exact probe、来源分层尾部抽检和独立 challenge pass；
- 人工审计完整 manifest；
- 用至少三份极端 mock 报告跑通公式。

### Phase 2：真实 harness pilot

- 选一个强 harness 与一个 snippet-heavy harness；
- 使用相同任务、搜索 API、TEC 和 scorer；
- 检查 Fact/Evidence/Completeness/Rubric 是否各自抓住预期失败；
- 检查 out-of-world claim 是否保持不奖不罚；
- 检查新 URL 是否都已被 census 枚举；
- 若出现 census gap，返回 Phase 1 修 compiler，而不是给某份报告临时补分；
- 重新发布前必须扩展反向全库枚举，并对同题所有历史报告统一重算。

### Phase 3：Dev-14

- 对 14 道题全部生成 TEC；
- 双人抽查 claim/research-unit/rubric 分类；
- 完成 judge calibration、kappa 和账本注入测试；
- 发布权重敏感性；
- 冻结 scorer v1。

### Phase 4：56 题扩展

- 批量 census；
- 按域和 unit type 分层抽检；
- 自动输出每题 coverage certificate；
- 不通过证书的题进入 quarantine；
- 正式集冻结后再跑全部 harness。

### Phase 5：榜单与论文

主表固定发布以下列：

```text
Harness | Truth | Fact | Evidence | Completeness | Rubric | Provenance | Writing Elo
```

附录再报告：

- fabricated / guessed / unobserved / wrong-binding / contradicted rates；
- conflicted / unresolved / out-of-world rates；
- unit-type coverage；
- explicit/latent rubric fulfillment；
- full-page / snippet observation tier；
- census coverage certificate；
- judge calibration；
- 权重敏感性；
- 任务级明细。

---

## 20. 可能的 reviewer challenge 与回答

### Challenge 1：TEC 仍然是 LLM 生成的 rubric

回答：TEC 不是自由文本评分标准，而是由冻结世界 span 支撑的、类型化事实和关系总账。LLM 负责提出和归一化，所有 unit 必须带可核查 support/contradiction span、hash、source role、discoverability certificate 和人工抽检结果。主分分母在运行前冻结，不由 judge 临时决定。

仍需诚实承认：关系 unit 的语义归一化包含模型判断，因此必须报告 human agreement 与 compiler error rate。

### Challenge 2：你们真的枚举了全部相关事实和 URL 吗

回答：不声称逻辑上穷尽所有自然语言命题，声称 protocol-complete。证据包括 BM25/dense/structured/graph union、ANN 对 exact probe 的召回、全语料反向扫描、饱和曲线、已知 witness recall、source-stratified tail audit 和 census-gap 挑战机制。任何确认 gap 都触发版本修复和全量重算。

### Challenge 3：evaluator 的向量库比 agent 强，不公平

回答：测试 oracle 比被测程序更强是正常的；不公平只会发生在 evaluator 内部扫描找到的目标被放进 agent 无法发现的分母。因此，每个正式 core unit 必须有公开 API 的发现证书；私有扫描能力用于建立/验证标准，不作为 agent 的隐藏工具。

### Challenge 4：Fact 与 Completeness 都是 recall

回答：新版 Fact 不含 recall，只测报告主动说出的、可裁决原子 claims 的事实准确率；Completeness 独立测冻结 atomic + higher-order unit universe 的覆盖率。因此 Fact 回答“说出的对不对”，Completeness 回答“该说的覆盖了多少”。

### Challenge 5：Evidence 与 Provenance 都在罚引用

回答：Provenance 的分母是 URL，只测 URL 是否真实存在、可规范化并有冻结快照；Evidence 的分母是 binding 和 citation-required report units，测本次观察、局部绑定和语义支持。真实但错误引用呈现 `Provenance 高 / Evidence 低`；发现和抓取路径由 Execution Audit 单独报告。

### Challenge 6：为什么用加权和，为什么等权

回答：报告级加权和是候选产品目标；等权是没有效用函数时最少承诺的起点，不是假装最优。四个 raw axes、legacy ablation、最低轴门槛、几何聚合和四维 simplex 敏感性全部公开。若主要结论依赖狭窄权重范围，论文不得声称稳健。

### Challenge 7：零 citation 但内容全对为什么 Truth 为零

回答：DRA 测的是 evidence-grounded research，不是闭卷知识问答。零 citation 的报告可能事实正确，但无法证明内容来自本次研究；Fact/Completeness 明细仍可显示其内容能力，正式 Truth 为零是构念选择而非事实真假判决。

### Challenge 8：为什么不用一个额外 Depth 主轴

回答：Depth 已被具体化为高阶 research unit coverage；再加一个整体 judge depth 分会重复、引入风格偏差且降低自动化。若未来发现 unit coverage 与人类深度判断相关性不足，可以把整体 depth 保留为验证面板，而不是立即加入主分。

### Challenge 9：表外 claim 会让榜单频繁重算

回答：先区分 `out_of_world` 与 `census_gap`。冻结世界外、非物质性的 claim 不奖不罚，不触发重算；证据实际在冻结世界内而 TEC 漏掉，或外部事实物质性强到改变任务答案时，才触发 gap。频繁 material gap 说明任务不应冻结。每次修复统一重算，优先保证公平。

### Challenge 10：为什么相信 NLI 与 DeepSeek-V4-Lite

回答：两者都不是最终真值来源。NLI 只验证候选 claim 是否被报告原文蕴含；DeepSeek-V4-Lite 只在固定 schema 与冻结 evidence packet 内检查原子性、限定词、支持、反驳和冲突。所有输出绑定 span ID、模型快照和 prompt hash，并通过双人标注、第二 verifier、高影响人工审核和随机抽检校准。

### Challenge 11：latent rubric 会不会成为隐藏答案

回答：latent rubric 只描述必要研究动作，不包含答案赢家、特定数值或 URL。它由 query-only agent 在看报告前提出，经答案泄漏检测和双人审核后冻结。任何运行后新增的必要要求都触发 `rubric_gap` 和统一升版，不能针对单个系统临时加减分。

---

## 21. 需要立即拍板的规格

本稿已经给出推荐默认，实施前仍需在代码规格中逐条锁定：

1. `material claim`、`out_of_world` 与 `world_scope_gap` 的判定 schema；
2. atomic / higher-order unit 的互斥类型规则；
3. explicit/latent rubric 的生成、答案泄漏检查与双人冻结规则；
4. NLI claim entailment、DeepSeek-V4-Lite verifier 与 residual sweep schema；
5. support/contradiction/source-role verdict vocabulary；
6. snippet observation 的日志格式；
7. citation binding 提取格式与 reference-region 规则；
8. ANN/exact probe、来源分层配额与 TEC 饱和停止规则；
9. discoverability certificate 的查询预算与禁用 oracle token 规则；
10. census/rubric/world-scope gap 仲裁、任务暂停与版本重算流程；
11. judge snapshot、prompt hash 和 fallback 禁令；
12. four-axis equal-weight candidate、门槛/几何聚合与 legacy ablation 的 board naming。

这些是可执行规格。Rubric 已作为第四个内层质量轴加入，不再用 Completeness 代替用户任务履约。

---

## 22. 最终判词

旧公式的骨架可以保留，但它只是候选聚合。真正重要的是把四个内层质量构念和 URL 有效性外层定义清楚。

重构后：

- `Fact` 是报告主动说出的可裁决原子 claims 的事实准确率，不再承担 coverage；
- `Evidence` 是本次观察证据的 binding precision–coverage；
- `Completeness` 是 protocol-complete atomic + higher-order unit universe 的分层 coverage；
- `Rubric` 是用户明确要求和预先冻结潜在研究要求的履约率；
- `Provenance` 是 URL 存在、规范化和冻结快照有效性的折扣；
- writing Elo 是独立呈现质量。

报告 claim 由高召回候选、NLI 原文蕴含、DeepSeek-V4-Lite 结构复核和残差扫描产生；Fact 再由独立多来源检索、支持/反驳 evidence packet、第二 verifier 与人工抽查裁决。冻结世界外内容不因为 benchmark 缺数据而判错；非物质性内容不奖不罚，物质性缺口触发任务暂停和统一修复。

真正困难的工作不再是调一组小数权重，而是证明 claim 没有系统漏采、TEC 检索接近协议完备、Fact 与 Evidence 输入真正独立、latent rubric 没有答案泄漏，并让每个自动 verdict 都能回到冻结 span 和人工审计记录。

---

## 参考资料

- [DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents](https://arxiv.org/abs/2506.11763)
- [DeepResearch Bench II: Diagnosing Deep Research Agents via Rubrics from Expert Report](https://arxiv.org/abs/2601.08536)
- [DeepResearchGym: A Free, Automated, and Reproducible Deep Research Agent Training Environment](https://arxiv.org/abs/2505.19253)
- [ResearcherBench: Evaluating Deep AI Research Systems on the Frontiers of Scientific Inquiry](https://arxiv.org/abs/2507.16280)
- [LiveResearchBench: A Live Benchmark for User-Centric Deep Research in the Wild](https://arxiv.org/abs/2510.14240)
- [FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation](https://arxiv.org/abs/2305.14251)
- [LongCite: Enabling LLMs to Generate Fine-grained Citations in Long-context QA](https://arxiv.org/abs/2409.02897)
- [ALiiCE: Evaluating Positional Fine-grained Citation Generation](https://arxiv.org/abs/2406.13375)
- [LoHoSearch: Benchmarking Long-Horizon Search Agents Beyond the Human Difficulty Ceiling](https://arxiv.org/abs/2606.12837)
- DRA current implementation: `../deep_reserch/src/eval/decidable_scorer.py`
- DRA transport evidence: `../deep_reserch/src/eval/fetch_log.py`
- DRA current design baseline: `DRA_SANDBOX_NATIVE_SCORING_DESIGN_2026-07-17.md`
