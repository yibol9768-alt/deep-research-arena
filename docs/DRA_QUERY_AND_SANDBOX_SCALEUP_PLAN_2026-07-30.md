# 执行结论

当前 DRA 需要同时解决两个问题：

1. 现有 `Truth56` 的 query、Task World Model（TWM）与 Research Test Suite（RTS）不是可继续横向复制的正式基线；
2. 现有沙盒规模很大，但研究垂直、来源角色、交互形态和正式构题能力尚未同时过门。

本规划采用两条并行路线：

- **修复线**：冻结旧结果，清除 query 中的证据泄漏与评分边界，重建公开/私有资产边界、人工治理链和 TWM/RTS compiler；
- **扩容线**：完成现有 Commerce、Community、Wikimedia 的 scale-up，并新增 Science/Technical、Travel/Geo，随后增加 Public Statistics pack。

六个月的目标不是“把编号写到 100”，而是形成一个经过淘汰和门控的题库漏斗：

```text
180 个场景/Blueprint intake
    → 140 个 answerability candidate
    → 110 个完整 pipeline candidate
    → Dev-20 + Formal-60 + Reserve-16
```

`Formal-60` 是第一版的容量上限，不是必须凑满的配额。若 ValidityGate 或 CapacityGate 未通过，应缩小正式集，不得降低标准。完成首版冻结并获得真实人时、分歧率、FRR/FAR 与运行成本后，再决定是否扩到 Formal-100+。

# 一、规划依据与联合评审

本规划基于 2026-07-30 对以下本地资产的只读核查：

- `data/tasks/deep_research/v3/` 的 57 个 v3 task；
- `data/results/truth56_full_20260727/assets/` 的 56 个 transition asset；
- `data/pilot_v33/dra_v3_dev_audio_0002/` 的完整单题切片；
- `data/golden/url_registry.json` 的沙盒 census；
- E1、E2 runbook、Query 人工治理流程和 sandbox-native scoring design。

Codex 与 Kimi Code 分别进行了独立审计。双方共识如下：

1. 不能在当前 transition builder 上直接追加题目；
2. query 修复与环境扩容应并行，而不是互相等待；
3. 新 pack 可以进入规划，但必须先完成 pack-level rights、coverage、surface 和 delivery gate；
4. 题库规模必须由完整 pipeline 的真实吞吐量决定；
5. 现有结果必须保留为历史诊断，不得静默覆盖或冒充正式集。

双方最初的主要分歧是正式集规模。Codex 的初始设想是 Formal-100；Kimi 指出，目前只有 `audio_0002` 展示了完整的 5 facets / 8 units / 25 checks / 20 evidence contracts 闭环，现有 56 题又全部为 `diagnostic_transition`。因此本规划采用：

- **首版冻结目标：Formal-60；**
- **长期容量目标：Formal-100+；**
- 是否晋级由 Dev-20 上实测的 ValidityGate、CapacityGate 和人时决定。

# 二、现有沙盒与工程状态

## 2.1 已有世界资产

- **Commerce / Magento：**104,368 products；用于商品、规格、价格、卖家主张、评论与分类。
- **Community / Postmill：**127,391 submissions、95 forums；用于社区经验、冲突、时间与群体偏差。
- **Wikimedia / Kiwix：**19,551,505 user entries、48.4 GB ZIM；用于百科背景、机制、历史叙述与跨页链接。
- **URL registry：**104,368 product slugs、127,391 submission IDs、Wikipedia bloom；用于闭世界成员与 URL 完整性。
- **Search / browse：**search shim、MCP、URL fetch、Kiwix 页面；用于 Agent-visible discovery 和读取。
- **Counterfactual asset：**`wiki_overlay`；用于参数记忆与证据依赖诊断。

Postmill 的现状需要专门澄清：旧 DATASHEET 将论坛描述为“tech-only”，但当前 registry 显示 95 个 forum，包含 `askreddit`、`news`、`personalfinance`、`science`、`food`、多个地区板块等。它不是严格的纯技术语料，但消费主题的覆盖深度非常不均衡：

- 较强：headphones、mechanicalkeyboards、gaming、consoles、iphone、technology、science、buyitforlife；
- 较弱或缺失：coffee、tea、photography/camera、furniture/chair；
- generic `food` 不能自动替代 chocolate/snacks 的同类经验。

因此，必须先生成正式的 `Forum Coverage Census`，不能继续根据旧文档或关键词命中决定每题是否需要社区角色。

## 2.2 E1 / E2 最近状态

- E1 已完成稳定 1% shard、compact A/B 构建和内容一致性验证，但 runbook 明确仍有人工审核字段未完成，因此状态仍为 `IN PROGRESS`；
- E2 W100K v2 已扫描全部 19,551,505 entries，实际编译 99,810 documents，并通过 identity、round-trip、BM25、resource 与恢复门；
- 文档记录 W1M 已启动，Wfull 与 E2 stage certificate 尚未完成；
- 这些大规模产物不在当前开发机上，正式规划必须把构建主机、artifact mirror、恢复路径和 SHA-256 验证写入运行手册。

## 2.3 评分管线的真实成熟度

目前只有 `dra_v3_dev_audio_0002` 展示了接近目标架构的完整垂直切片：

- 5 facets；
- 8 research units；
- 25 executable checks；
- 20 evidence contracts；
- oracle、对抗报告与 release gate 资产。

Truth56 的 56 个 transition 资产则全部写明：

```text
status = diagnostic_transition
formal_eligible = false
report_visible = false
```

因此，`audio_0002` 应作为 compiler 与 release-gate 的工程参考；Truth56 只能作为旧题诊断和 regression pool。

# 三、为什么不能直接扩写现有 56 题

## 3.1 题库结构过窄

Truth56 实际由 16 个 development task 和 40 个 formal/candidate task 构成，并不是“56 个独立正式题”。其 motif 分布为：

| Motif | 数量 |
|---|---:|
| `multi_branch_synthesis` | 27 |
| `constraint_match_and_select` | 21 |
| `causal_or_evolution_explanation` | 8 |
| `claim_verification` | 0 |
| `evidence_reconciliation` | 0 |

全部任务仍是消费购买或购买后的测试决策。即使题目标题发生变化，核心研究行为仍集中在“比较商品—解释规格—建议购买或 defer”。

## 3.2 Query 过长并泄漏证据边界

57 个 v3 task 的 query 中位长度约 515 英文词，最长约 1,289 词。正式题平均约 4,450 字符。常见问题包括：

- 在题干中列出多个冻结价格、评分、SKU 和规格；
- 直接告诉 Agent 某两个字段存在冲突；
- 把“不能如何推断”的评分边界列成十余条；
- 给出盲测阈值、成本停止线和最终决策算法；
- 重复使用 “do not treat”“do not infer”“or defer”等模板。

这会把“发现并审计证据”的研究任务改造成“按照已给审计清单复述”的指令遵循任务。

## 3.3 TWM 与 RTS 是复制层，不是可执行研究合同

Truth56 的 56 个 TWM 全部满足：

```text
relations = []
conflict_clusters = []
bounded_unknowns = []
```

其 assertion 来自冻结 case evidence catalog 的字段扩展，而不是从完整 World Index 通过 query-only probes 构建。RTS 共 310 个 facet，全部是：

```text
1 facet → 1 unit → 1 check
```

并且：

```text
evidence_contracts = []
search_certificates = []
full_pass_contract = {}
```

这意味着当前批次无法验证替代证据、替代路线、依赖链、冲突、bounded absence 或细粒度部分完成。

## 3.4 人工治理状态不可重放

Task 文件中虽然写有 `query_validation.disposition=accepted` 和 blind review hash，但仓库中没有对应的完整阶段资产：

```text
01_source_selection.json
03_evidence_review_decisions.json
05_graph_annotation.json
attempt_N.blind_packet.json
attempt_N.blind_review.json
query_release.json
```

因此，现有 validation 记录不能证明执行过 human query pipeline。新版本必须以“阶段资产存在且 hash 可重放”为准，不能以 task 文件里的自我声明为准。

# 四、正式决策：修复线与扩容线并行

## 4.1 修复线

立即执行，不依赖 E1/E2：

1. 将 Truth56 正名为 `candidate_pool_v0_diagnostic_transition`；
2. 冻结旧 query、case、运行结果和 hash，不原地覆盖；
3. Agent-facing public task 只保留自然 query 和必要运行元数据；
4. `generator_view`、candidate actions、evaluator view、oracle、acceptable conclusions 全部进入 private construction plane；
5. 建立 query leak linter、模板相似度检测、公开/私有资产 CI 门；
6. 建立真实 reviewer roster 和角色互斥规则；
7. 从旧 100 个 `cross_site_deep` 自然 query 中回收用户场景，但只把它们作为 scenario seed，旧 golden 不得直接晋级。

## 4.2 扩容线

环境扩容采用以下顺序：

```text
E1 完成人工审计
  ├─→ E3 Commerce / Community 全量重建
  ├─→ TWM / RTS compiler 三题 smoke
  └─→ existing-world Query MVP

E2 W1M → Wfull → E2 certificate
  └─→ Wikimedia 全量 query-only candidate pools

E4-A Science / Technical
  ├─ IETF RFC / official technical corpus
  └─ license-filtered PMC OA + metadata construction sidecar

E4-B Travel / Geo
  ├─ Wikivoyage
  └─ regional OSM / GeoNames + local route/place renderer

E4-C Public Statistics
  └─ 一个许可清楚、口径可冻结的政府或国际组织数据 pack

E5 unified Search / Browse / Interaction + delivery lineage
```

E4-A 与 E4-B 的 acquisition、rights、PII 和 renderer 设计可以立即并行启动，不必等 E1/E2 全部完成；但它们的 task 不得进入正式题库，直到 pack certificate 和 delivery surface 过门。

# 五、环境 scale-up 计划

## 5.1 E1：完成现有世界编译基础

交付物：

- 完成人工审核字段；
- E1 stage certificate；
- compact store rebuild instructions；
- artifact mirror 与 SHA-256 表；
- parser error strata 与修复记录。

硬门：

- 任一高风险 parser family 出现系统性语义丢失，停止 TWM rebuild；
- canonical block 无法回到 agent-visible 页面，停止；
- 人工审核与自动 quality report 不一致时，先修 compiler。

## 5.2 E2：Wikimedia W1M / Wfull

交付物：

- W1M、Wfull manifests；
- checkpoint/recovery 记录；
- native Kiwix、canonical artifact、debug HTTP 三方 round-trip；
- exact alias、BM25、resource、table 与 redirect census；
- E2 stage certificate。

硬门：

- 不允许跳过失败 entry；
- 不允许把 W100K 结果外推为 Wfull PASS；
- Wikidata 只作 construction sidecar，未通过 agent-visible surface 的内容不能支持得分。

## 5.3 E3：Commerce / Community 全量重建

交付物：

- Magento DB → canonical artifact → source-native HTTP 三方对齐；
- Postmill submission/post/reply/quote/time/author 结构；
- 商品 category/variant/price/review census；
- 95 个 forum 的主题覆盖、时间跨度、长度和重复簇报告；
- forum-topic answerability matrix。

硬门：

- query-conditioned inclusion 必须为零；
- 同名商品 variant 不得静默合并；
- 论坛引用与回复作者不得错归；
- task witness 只能在 build 完成后作为 recall probe。

## 5.4 E4-A：Science / Technical Pack

最低组成：

- 一个 official bulk / standards corpus；
- 一个许可允许的论文全文子集；
- 一个仅供 construction 的 metadata/citation sidecar；
- 论文 section、table、caption、citation anchor 的结构化 renderer。

必须证明的新能力：

- claim–method–measurement–limitation audit；
- 跨规范版本或跨论文方法综合；
- primary/official 与 secondary/encyclopedic source-role 区分。

## 5.5 E4-B：Travel / Geo Pack

最低组成：

- Wikivoyage；
- 一个预注册区域的 OSM/GeoNames；
- place、route、geometry、season/opening condition 的本地 surface；
- text API 与 browser/map/list 的 bridge manifest。

必须证明的新能力：

- 空间约束规划；
- 多地点组合与路线比较；
- 时间、季节、开放条件和地理范围的联合判断。

## 5.6 E4-C：Public Statistics Pack

初版只选一个许可清楚、版本稳定的数据源，不追求多机构规模。必须保存：

- 原始 CSV/JSON；
- table header、unit、region、time、missing value；
- 数据版本和修订语义；
- 可浏览表格与结构化 API 的等价映射。

必须证明的新能力：

- 跨表单位/口径对齐；
- 时间和地区聚合；
- 对缺失值、修订和不可比统计的 bounded conclusion。

## 5.7 E5：统一交付合同

任何 pack 进入 formal 前必须证明：

```text
raw source
  → canonical artifact
  → source-native / registered delivery transform
  → delivered artifact
  → observation ledger
```

不同 harness 不要求像素或工具序列相同，但必须获得等价的核心证据和结构。不能捕获实际交付内容的 adapter 只能进入 report-only lane。

# 六、题库目标与配额

## 6.1 题库漏斗

| 阶段 | 目标数量 | 说明 |
|---|---:|---|
| Scenario / Blueprint intake | 180 | 人工场景、旧自然 query seed、新 pack blueprint |
| Answerability candidates | 140 | 通过来源角色、候选池和最小 witness 门 |
| Full-pipeline candidates | 110 | 完整 evidence review、annotation、RTS、oracle、blind review |
| Dev | 20 | compiler、matcher、query round-trip 和产能校准 |
| Formal vNext | 最多 60 | 首版固定分母 |
| Reserve | 16 | erratum、版本迁移、held-out route 与替换 |
| Rejected / held out | 至少 44 | 保留失败理由，不隐藏淘汰历史 |

## 6.2 Formal-60 vertical 配额范围

配额采用范围而非强制填格。若某 vertical 的 pack 或 answerability 不过门，正式数应减少。

| Research vertical | 目标范围 |
|---|---:|
| Consumer / services / technology decision | 18–22 |
| Science / technical synthesis | 10–14 |
| Travel / geography planning | 8–12 |
| Public data / policy interpretation | 6–10 |
| General knowledge / history / standards | 6–10 |

控制规则：

- 任一 vertical 不超过正式集的 35%；
- 至少 10 个独立 topic/blueprint cluster；
- 同一核心 evidence subgraph 最多进入 2 个 formal task；
- dev 与 formal 不能只通过改 cluster 名称实现“分离”。

## 6.3 Formal-60 research-shape 目标

| Research shape | 目标数量 |
|---|---:|
| Multi-option comparison / constraint decision | 12 |
| Claim / mechanism audit | 10 |
| Evidence reconciliation / conflict / uncertainty | 10 |
| Causal or evolution explanation | 8 |
| Tutorial / action plan / budget allocation | 8 |
| Bounded enumeration | 6 |
| Cross-page aggregation | 6 |

这些是 portfolio 目标，不是为单题强行制造结构的模板。Evolution 必须先通过冻结世界内的日期声明数量、时点数和来源角色门；不达门时应声明 `unsupported_in_this_world_version`。

## 6.4 现有沙盒立即可拓展的主题

不等待新 pack，也可以从当前 104k 商品、95 个 forum 和 Wikipedia 中增加：

- 工具、DIY、维修性与 BIFL；
- home office、桌面、人体工学和空间约束；
- kitchen appliance、烹饪工具与维护；
- footwear、bags、outdoor gear、wearables；
- personal finance 与预算决策（forum + Wikipedia，不强制商品页）；
- machine learning、science、technology、space 的机制与证据协调；
- art、media、regional community 的跨页叙事综合；
- Magento category 上的 bounded enumeration 和 cross-page aggregation。

旧 `cross_site_deep` 的 100 个自然 query 覆盖了 headphones、smartphones、gaming、tools/BIFL、footwear、office、kitchen、bags、wearables 等 13 个 cluster。它们可以提供更自然的用户场景，但必须重新生成 Task Contract、TWM、RTS 和 answerability certificate，不能复用旧关键词 golden。

# 七、Query vNext 规范

## 7.1 公开 Query

默认要求：

- 120–300 英文词；
- 特殊复杂题最多 450 词，需独立审批；
- 2–5 个用户可理解的 research facets；
- 至少一个需要跨页比较、解释、协调或综合的输出；
- 允许用户自然知道的预算、时间、地点、已有设备和偏好；
- 不列出冻结页面中发现的价格、评分、规格冲突和证据结论；
- 不出现 scorer、proof step、seller assertion scope 等 benchmark 语言；
- 不把实验阈值、错误类型清单和推荐算法写进题面。

## 7.2 私有 Blueprint / Task Contract

私有资产保存：

- entities、constraints、facets、requested outputs；
- required source roles 及其认识论理由；
- answerability witnesses；
- conflict/unknown/bounded absence；
- disallowed inference；
- optional Decision Envelope；
- query round-trip 与 leak-lint 结果。

## 7.3 Query 泄漏检查

发布前自动比对 query 与 private case：

1. SKU、价格、评分、review count；
2. 冻结 assertion 的数字与单位；
3. conflict pair；
4. answerability witness 的独有术语；
5. evaluator rule 和 decision threshold；
6. 与其他 query 的高重合 n-gram / shingle。

用户已经提供的事实必须在 Blueprint 显式标为 `user_provided`；其他命中一律阻断。Query 中的 `user_provided` 事实不应再作为 evidence-bearing check 得分。

## 7.4 反模板与自然性

- 使用多组不同语气、结构和长度的 human-written development examples；
- renderer 只看 public Blueprint projection；
- 每个 attempt 保存完整请求、响应和失败历史；
- 独立 reviewer 只看 query，判断自然性、可答性和是否需要多分支研究；
- reviewer 还要从 query 反向恢复 facets，与 Blueprint 做 round-trip；
- 连续两次自然性盲审失败的题直接淘汰，不继续无限润色。

# 八、从候选题到正式题的 Release Gates

- **G0 World / Pack：**pack certificate、rights/PII、coverage、surface、hash；失败则 pack 不出题。
- **G1 Public/private hygiene：**公开面无 gold、contract、oracle，并绑定快照；失败则 task 拒绝入库。
- **G2 Query quality：**长度、leak lint、反模板、自然性、round-trip；失败可重试最多 2 次，之后淘汰。
- **G3 Answerability：**每个 core facet 有 witness，并通过 source-role deletion 与 candidate saturation；失败则 revise scope 或淘汰。
- **G4 TWM quality：**assertions 可回原始 span，relations/conflicts/unknowns 与 query 一致；失败则修 compiler，不手工补分。
- **G5 RTS integrity：**每个 unit 有 2–5 checks，并具备 evidence contracts、OR-of-AND 和依赖 DAG；失败则不得称可评分。
- **G6 Invariance：**通过 oracle、null、fact dump、URL dump、deletion、valid alternate route 和 invalid route；失败则修 matcher/compiler。
- **G7 Human validity：**FRR/FAR、agreement、blind adjudication、PENDING=0；失败记为 ValidityGate fail。
- **G8 Capacity：**novel pairs、人时、队列峰值、裁决吞吐与安全系数过门；失败则缩小 formal，不降标准。
- **G9 Freeze：**全部 manifest/hash、formal/reserve 分离、erratum/challenger 齐备；失败则不发布。

Formal task 必须有完整阶段目录和可重放 hash。状态字段不得由 task 文件自我声明。

# 九、六个月路线图

## M1：止损、正名与基础门

- 完成 E1 剩余人工审计；
- Truth56 冻结并正名；
- public/private artifact 分离；
- query leak linter 和 repo hygiene CI；
- 生成 Forum Coverage Census；
- 冻结 reviewer roster；
- 发布本 PDF v1。

停机条件：无法隔离 gold 或无法提供相互独立的人审角色时，正式题工作停止，只保留 dev/candidate。

## M2：现有世界 scale-up

- E2 W1M 过门并启动/恢复 Wfull；
- E3 Commerce/Community 全量重建；
- 从旧 100 个自然 query 中筛 scenario seed；
- 现有 56 题完成 query-only rewrite 候选，不改变旧 ID；
- 4 个任务走完真实 human pipeline。

停机条件：论坛/主题覆盖与旧 DATASHEET 严重不一致且无法解释时，不冻结 source-role 配额。

## M3：Compiler 重建

- E2 Wfull candidate 与 E3 三方对齐；
- 从完整索引为 3 个任务建立 candidate pool saturation；
- TWM/RTS compiler 产生真实 relations、conflicts、unknowns、evidence contracts；
- 重放 `audio_0002` 并运行 V1–V10。

停机条件：oracle ceiling 失败、shortcut probe 获得高分、alternative route FRR 超门时，禁止批量扩题。

## M4：新垂直 MVP

- Science/Technical pack 通过 acquisition/rights/renderer pilot；
- Travel/Geo pack 通过 acquisition/rights/renderer pilot；
- 构建“3 个 vertical × 5 个 research shapes”的 15 题方法学 MVP；
- 完成 Dev-20；
- 运行 query round-trip、source-role deletion 和 granularity invariance。

停机条件：新 pack 不能证明至少一种现有环境测不到的 research unit 时，不进入正式 world。

## M5：候选题漏斗与交付合同

- Public Statistics pack pilot；
- intake 180 → answerability 140；
- 至少 110 题进入完整 pipeline；
- 完成 E5 search/browse/interaction bridge；
- 对 12 adapter 运行 delivery lineage canary；
- 在 Dev-20 上实测人时、novel pair、分歧率和队列峰值。

停机条件：CapacityGate 推算无法在冻结窗口前清零 PENDING 时，提前缩小 Formal 目标。

## M6：冻结与发布准备

- ValidityGate 与 CapacityGate；
- 冻结 Dev-20、Formal 最多 60、Reserve-16；
- 8–10 题反事实/canary 审计；
- cluster bootstrap、MDE 与等效并列层预注册；
- 发布 PDF v2、datasheet、environment card、validation report；
- V23–V30 与全部 formal entry 的 PENDING 未清零前不发榜。

# 十、人员、产能与成本

## 10.1 人工角色

至少需要：

- pack reviewer；
- source/evidence reviewer；
- graph/Blueprint annotator；
- independent adjudicator；
- blind query reviewer；
- matcher disagreement adjudicator；
- release manager。

同一任务的关键角色必须互斥。`actor_id` 不是身份证明，正式批次还需要冻结 reviewer roster 和实际账号映射。

## 10.2 人时规划

在 Dev-20 之前不承诺每题固定人时。初始规划假设为每个 full-pipeline candidate 3–5 人时，必须在 Dev-20 实测：

```text
candidate-pool review
+ evidence review
+ Blueprint / annotation
+ query blind review
+ oracle / adversarial review
+ matcher adjudication
```

若 110 个 full-pipeline candidate 的实测负载超过团队带宽，应减少 Formal 数，而不是省略证据审核或让同一个模型/账号自审。

## 10.3 计算成本

环境与任务成本分开报告：

```text
C_env  = acquire + parse + index + render + audit
C_task = retrieve + semantic + compile + judge + adjudicate
```

每个新 pack 先跑稳定 1% shard，记录 raw bytes、documents、blocks、tables、edges、索引项、峰值内存、磁盘放大、吞吐和失败 strata，再决定 full build。不得从 W100K 或一个 pilot 直接承诺 Wfull / Formal-60 的总成本。

# 十一、硬停机条件

发生任一条件时必须停止对应阶段：

1. 公开 query 或 task artifact 出现 private contract / gold；
2. query leak linter 命中未标记的冻结事实；
3. pack rights、PII 或 redistribution 状态不清楚；
4. E1/E2/E3 的 canonical artifact 无法回到 agent-visible 页面；
5. query 要求 community evidence，但 forum coverage 不能证明；
6. query 声称冲突或 bounded absence，TWM 却无对应结构；
7. RTS 退化为一段长 prose check；
8. oracle 不能满分，null/URL dump/fact dump 获得实质高分；
9. 合法替代路线被拒或非法相似路线大量通过；
10. blind reviewer、annotator 与 adjudicator 不是独立角色；
11. PENDING 无法在冻结前清零；
12. CapacityGate 预测正式集无法在预算内完成；
13. 任何团队成员试图根据 12 个被评 harness 的排名反向修改正式题。

# 十二、明确不做

- 不在当前 transition builder 上继续批量追加题目；
- 不把 query 写得更长来“提高严谨性”；
- 不强制每题三源齐全；
- 不把 forum、vertical 和 source role 混为同一维度；
- 不在正式 task 文件中保存 `generator_view`、candidate actions 或 evaluator view；
- 不让 LLM renderer 自己批准 query；
- 不让单一 operator 账号同时充当 author、annotator、adjudicator 和 blind reviewer；
- 不因某 harness 得分低而降低 check 或改变 applicability；
- 不用页面数量代表研究难度；
- 不把 new pack 的 hidden construction oracle 当作 agent evidence；
- 不在旧 manifest 上静默重算；
- 不在 ReleaseGate 通过前发布排行榜。

# 十三、交付物清单

## 环境

- `environment-card-vNext.md/pdf`
- `domain-pack-manifests/`
- `coverage-certificates/`
- `rights-pii-decisions/`
- `world-index-manifest.json`
- `delivery-bridge-manifest.json`
- `forum-coverage-census.json/md`

## Query 与任务

- `query-portfolio-manifest.json`
- `scenario-intake/`
- `case-blueprints/`
- `query-pipeline/<candidate_id>/`
- `task-world-models/`
- `research-test-suites/`
- `answerability-certificates/`
- `query-leak-lint-report.json`
- `duplicate-cluster-report.json`

## 验证与发布

- `dev20-validation-report.md/pdf`
- `validity-gate.json`
- `capacity-gate.json`
- `formal60-manifest.json`
- `reserve16-manifest.json`
- `counterfactual-canary-report.md/pdf`
- `benchmark-datasheet.md/pdf`

# 十四、成功标准

首版成功不是“题目超过 56”或“环境达到若干百万页面”。成功必须同时满足：

1. 每个 formal query 自然、短、无答案事实和评分边界泄漏；
2. 每个 core facet 有可达 witness，但运行时不绑定 witness URL；
3. TWM 来自完整世界的 query-conditioned candidate pool；
4. RTS 的每个 check 有可执行 content/evidence contract；
5. 新合法证据可以通过，困难非法证据被拒；
6. 所有得分可回到 report span、delivered evidence 和 source role；
7. Dev-20 上的 scorer-human 校准、FRR/FAR 和产能过门；
8. Formal 与 Reserve 都有完整可重放治理资产；
9. 统计报告使用 cluster bootstrap 和等效并列层，不强行制造全序；
10. 旧 Truth56、旧榜和新 vNext manifest 可以并排重放，互不覆盖。

# 十五、状态命名

- **`legacy_historical`：**可以声称“可重放的旧结果”；不可以声称“新协议有效”。
- **`diagnostic_transition`：**可以声称“工程诊断资产”；不可以声称 formal、gold 或可发榜。
- **`structurally_compiled_candidate`：**可以声称 schema/graph 已编译；不可以声称人工治理或 answerability 已完成。
- **`human_governed_candidate`：**可以声称 query/evidence/annotation 链可重放；不可以声称 scorer 已校准。
- **`release_gate_candidate`：**可以声称 oracle、对抗与 validity/capacity 正在验收；不可以声称已冻结。
- **`released_formal_task`：**可以声称已进入固定正式分母；不可以被单方静默修改。

# 内部参考

设计与流程：Sandbox-native Scoring Design（2026-07-17）、Human Query Generation Workflow（2026-07-16）、Evidence Graph Redesign Plan（2026-07-15）、Route-flexible Rubric Migration（2026-07-17）。

运行与资产：E1 Shard Compiler Runbook、E2 Wikimedia Backbone Runbook、DATASHEET、pilot v3.3 audio 0002、Truth56 20260727 assets。
