# DRA V3 挑战文献调研:方案与落地建议

日期:2026-07-17
调研方法:4 路并行文献侦察(rubric 生成与验证 / judge 元评测与统计保证 / deep research 基准与冻结环境 / 引用归因与替代答案接受),约 60 篇论文,全部 arXiv ID 经抓取 abs 页逐一核验(个别仅标题级核验的已注明)。
对应上游文档:`DRA_V3_ROUTE_FLEXIBLE_RUBRIC_MIGRATION_2026-07-17.md`(迁移方案)、`DRA_V3_HUMAN_QUERY_GENERATION_WORKFLOW_2026-07-16.md`(query 生成流程)。

---

## 0. 结论摘要

针对两个未解核心问题,文献给出的答案是:

1. **Rubric Builder 规模化生成必要但不绑路线的 obligations**:可解。配方 = 证据树反向生成保可答性(DEEPRUBRIC)+ 两段式"witness 条件生成、再去指涉化改写"(RaR)+ 三重过滤(deletion 测必要性、perturbation 测区分度、多 harness learnability 测路线绑定)+ 闭世界证据等价类枚举(DRA 独有优势)。文献中没有任何工作同时做到"必要性验证 + 闭世界可答性 + 路线自由",这三点都是可声称的贡献。
2. **Evaluator 的替代路线接受率证明**:可解,且比预想便宜。配方 = 分层校准集 HarnessEval(自然层 40% / 伪证据层 30% / 合法替代层 30%,共约 1,500-2,500 条 (report, obligation) 人工判定对)+ 三分法则给 FRR/FAR 统计证书(每层约 300 条、0 错误即认证 ≤1% @95%)+ PPI 把榜单分数变成无偏估计带置信区间(金标 ≥150 条/维度)+ 红队套件 + 冻结完整性监控。"合法替代层认证误拒率"文献中无先例,是第四个可声称贡献。

两个硬警告:

- **静态 rubric 会被未见过的 harness 攻破**(OnlineRubrics 实证)。冻结前必须用多样 harness 输出做对抗挖漏,冻结后只保留"版本化增补负分项"的治理通道,不动正义务,保持跨 harness 可比。
- **通用 LLM judge 检出细粒度证据失败的准确率可低至 <55%**(REFLECT),二分类归因判定微调后也只有约 80% F1(AttributionBench)。语义 judge 永远不能裸用;能下沉到确定性闸门的判定(在册、已观察、角色、聚合结构)全部下沉,只把最后的蕴含判定留给 judge,并配受控扰动校准集。

另有一个必须处理的事务性风险:**AAAI 2026 已有一篇同名论文 "DeepResearch Arena"(2509.01396,seminar 转写生成任务,机制上与我们无关)**。论文与网站必须显式消歧。

---

## 1. 核心问题 1:Rubric Builder 怎么规模化(对应挑战 1 + 2)

### 1.1 文献坐标

| 工作 | ID | 与 DRA 的关系 |
|---|---|---|
| DEEPRUBRIC | 2606.17029 | 最同构:冻结种子上建 evidence tree,叶=原子可验证目标,再从树反推 query 与 rubric,可答性由构造保证。但它面向 RL 训练数据,query 与证据路径构造性耦合,route-binding 恰是它不处理的 |
| QUBRIC | 2606.03968 | 直接说出核心矛盾:"开放查询产出模糊 rubric,粗暴收窄查询则引入无人能验证的捏造参照"。方案:query 与 rubric 共同设计 + learnability filtering(多参考系统跑一遍,删全过/全挂条目) |
| Rubrics as Rewards | 2507.17746 | 四条生成公理:专家指导、覆盖全面、重要性分层、**自包含可独立判定**(隐性防路线绑定);Essential(5)/Important(3-4)/Optional(1-2)/Pitfall(负分) 分层;perturbation 测试测区分度 |
| HealthBench | 2505.08775 | consensus criteria 模板层(多人多数决验证,跨题复用)+ example-specific 单例层(低成本);负分陷阱项;人-人一致率 55-75% 作为验证天花板 |
| PaperBench | 2504.01848 | 加权层级 rubric 树:条件分支=子树,父节点聚合实现 OR;叶节点类型系统(类型决定判据形态,而非指定实现路径) |
| RLCF | 2507.18624 | 条目二分:程序可验证 vs 需判分器,加权合成。与"确定性闸门优先"原则一致 |
| DR3-Eval | 2604.14683 | leave-one-out 综合必要性检查(删一个证据源,题必须变得不可答,否则该源非必要);distractor/noise 分层控制语料信噪比。**反例警示**:它靠反向构造刻意保证单一解法路径,是文献中最清晰的 designed route-binding |
| ResearchRubrics | 2511.07685 | 显式/隐式义务二分;复杂度三轴(conceptual breadth / logical nesting / exploration);纯专家成本上界:2800 人时 / 101 题 ≈ 28 人时每题 |
| TICK | 2410.03608 | rubric 质量的可量化指标:装配 rubric 后人类标注者 IAA 从 0.194 升至 0.256。即"rubric 好不好,看它能不能让人类判得更一致" |
| OnlineRubrics | 2510.07284 | 静态 rubric 训练中被 hack 的实证;在线从策略对比中增补 criteria |
| EvalGen | 2404.12272 | criteria drift:人必须先看真实输出才能定稿判据,判据不可能完全先验固定 |
| CaRR | 2601.06021 | 多跳问题分解为单跳可验证 rubric,每跳要求"实体正确 + 引用正确"构成证据链;可用于把 Evidence Graph 多跳路径分解为义务 |

### 1.2 Rubric Builder v1 配方

按流水线顺序:

1. **反向生成,可答性由构造保证**。保持现有方向(冻结语料 → evidence graph → 选子图 → query),这与 DEEPRUBRIC 同构且文献已证明有效。差异化:每个叶命题不存单 witness,而存**证据等价类**(语料内所有可证实该命题的页面集合,闭世界可枚举、可审计)。等价类基数同时是"路线自由度"的度量:基数 1 的命题要么升级为 conditional,要么明确接受单源风险。
2. **两段式生成防绑定**(RaR 的"以参考为条件生成、再删参考痕迹")。第一段:Rubric Builder 看 GeneratorView + witness graph,起草义务(保证必要性与覆盖);第二段:**去指涉化改写**,把 URL 引用改写成证据类型合同、把具体结论改写成结论谓词(如"结论须被所引本地证据蕴含且满足预算约束"),并机检改写后文本不含任何 witness 实体。RaR 四公理作为生成规范,尤其"自包含":每条义务不得引用参考路径中的实体。
3. **义务分层替代全 required**(HealthBench + RaR)。Essential / Important / Optional 加权,再加 Pitfall 负分义务(捏造引用、未观察即引用、营销页支撑性能声明)。彻底消灭"1,054 步全 required"。
4. **双通道判定**(RLCF)。每条义务显式标注 `verifier: deterministic | semantic`。本地引用存在、ledger 含该页、数字与语料一致、来源角色合规走程序;蕴含判定走 judge。
5. **三重过滤作为发布闸门**:
   - **deletion test**(已有):删义务,query 是否仍蕴含它 → 测必要性;
   - **perturbation test**(RaR):构造好/坏报告对,义务能否区分 → 测区分度;
   - **learnability / route-binding test**(QUBRIC 行为学版):用 k 个多样参考 harness 跑该题,其中至少含一个故意捏造者和一个只走另一条合法路线者;删掉全过/全挂义务;**"合法替代路线 harness 的义务满足率"直接就是 route-binding 的量化指标**,可给每题报数。
   - 这一步与迁移文档 Phase 2 的六项 substitution/adversarial 测试合并执行,不另起炉灶。
6. **模板层 + 单例层混合**(HealthBench)。跨题复用的 consensus 义务模板(如"比较类 query 双侧都须有 grounded 证据""绝对声明须处理反例")用多人多数决验证一次,单例义务低成本生成。RaR 实证:纯模板与纯单例都失败,必须混合。
7. **冻结治理**(OnlineRubrics + EvalGen 的教训)。冻结前:用现有 12 个 harness 的真实输出做对抗挖漏(这正是五轮审计"每轮都有新发现"的制度化);冻结后:只允许版本化增补 Pitfall 负分项,正义务不动,历史分数不重算。

成本对照:纯专家路线 28 人时/题(ResearchRubrics)不可扩展;上述配方中人只做三件事:审等价类枚举、裁决过滤结果、标校准集,与 query 生成流程文档的"人拍板、程序校验、LLM 只提案"权限边界完全一致。

---

## 2. 核心问题 2:Evaluator 的接受率怎么证明(对应挑战 5 + 3)

### 2.1 先接受现实天花板

- 二分类归因判定:微调 GPT-3.5 约 80% macro-F1(AttributionBench 2402.15089);三分类最好 85.1%(AttrScore 2305.06311,GPT-4 zero-shot);
- 通用 LLM judge 检出细粒度证据失败:准确率 <55%(REFLECT 2605.19196);
- 人类金标自身一致率只有 55-75%(HealthBench;AI2 2603.06942)。

结论:验证目标不是"judge 完美",而是 (a) judge 落在人-人一致带内或之上;(b) 榜单聚合分带统计证书;(c) 确定性闸门覆盖的部分用单元测试穷尽证明,与统计声明分开报告。

### 2.2 HarnessEval 校准集(冻结 evaluator 的说明书)

在 (report, obligation) 粒度人工标注约 1,500-2,500 对,来自 120-200 份报告,三层:

1. **自然层(约 40%)**:现有 12 个 harness 的真实报告,风格尽量多样(judge 准确率是 generator-dependent 的:Coin Flip 2603.06594),并**按轨迹长度 / 工具调用数分层**("Cited but Not Verified" 2605.06635 实证:工具调用 2→150 次,引用事实核查准确率掉约 42%)。
2. **伪证据层(约 30%)**:对 grounded 报告做手术式定向腐蚀,每份只改一处,真值由构造已知(MiniCheck 2404.10774 的合成配方):
   - 注册表外 URL(必须被确定性闸门 100% 拦截,以单元测试而非统计报告);
   - 在册但本次未抓取(ledger 违例,同上);
   - 引用洗白:真 claim 重新归因到"已观察但无关"的页面(语义 judge 的主战场);
   - claim 内数字/实体扰动;
   - 引用不动、结论翻转;
   - 安全子套件:null-model 恒定报告(2410.07137 用它在 AlpacaEval 刷到 86.5% 胜率)、JudgeDeceiver 式注入后缀(2403.17710)。
3. **合法替代层(约 30%),文献无先例,DRA 的独有贡献**:委托构造"用不同路线满足同一义务"的报告:等证据力的替代在册来源、替代分析路径、可辩护的替代结论,外加改写/重排/加长的 metamorphic 孪生(判定必须不变)。接受准则用 BEM 的**非对称等价**(2202.07654):替代证据"至少与参考路线同等有力"即接受,信息更多也算对。

标注协议:每对 2-3 名独立标注,判定表述与 judge 看到的完全一致(AI2 2603.06942 的 metric-mirroring 要求);分歧仲裁;judge-人分歧样本做 SAFE 式再裁决(2403.18802:分歧样本中 76% 是机器对,先查清是谁错再记 judge 错误)。

### 2.3 发布指标(随冻结 evaluator 一起公布)

- 按义务类型分桶的 macro-F1 与 kappa,对照人-人一致带(PaperBench 分桶 F1 从 0.72 到 0.94 差异巨大,必须分桶);
- **合法替代层 FRR 与伪证据层 FAR,各带 Clopper-Pearson 95% 区间**。三分法则:每层 n≈300、观察到 0 错误,即认证错误率 ≤1% @95%(n≈150 → ≤2%);
- 注入/null 子套件攻击成功率(目标 0;结构性论证:语义 judge 永不接触闸门字段,闸门先行);
- 确定性闸门:穷尽单元测试清单(registry、ledger、HTTP 200、哈希、citation position、source role),与统计声明分开;
- judge 排序 vs 人工排序的 Kendall tau(ARES 口径,榜单级效度);
- ABC 基准有效性检查表(2507.02825)完成并公布(空报告能否得分、闸门能否短路等)。

### 2.4 统计保证:采用 PPI

- 核心机制(ARES 2311.09476 + PPI 2301.09633):冻结金标集(每评分维度 ≥150 条)+ judge 全量标注 → **PPI 校正的 harness 分数 + 95% 置信区间**。无偏性不依赖 judge 的误差特性;judge 越好区间越窄,judge 差区间变宽但永不失效。第三方拿到的是统计保证,不是"请信任我们的 judge"。
- 子条目级(per-obligation 聚合到 per-report)正是 PRECISE(2601.18777)的设定,公式可直接复用;2606.05308 实证 30-100 条人工标注即可显著收窄排序误差。
- 同时公布**当前金标规模下的最小可检测分差**;榜单上两个 harness 分差落在其内时不宣称排序。
- 可选补充:Rogan-Gladen 灵敏度校正的违例率(2606.10315)、conformal 区间(2606.13221)。

### 2.5 冻结完整性监控

judge 若调用托管 API,"冻结"是个需要持续证明的声明:保留一个已判分报告锚集,定期重判,用 e-process 任意时刻有效检验区分"系统变了还是 judge 变了"(Who Drifted 2606.15474)。judge 每个裁决必须返回报告端与来源端的**摘录引文**(RULERS 2601.08654),无引文裁决自动升级人工审计队列,第三方无需信任 judge 即可复核。

### 2.6 对挑战 3(无法枚举所有合理路线)的回答

文献共识与我们方向一致:评结果不评路线。落地三件套:

- 合同判定(下节 schema):新来源只需过"在册 + 本次观察 + 角色合格 + 支持邻近 claim",不需要出现在任何预枚举路线里;显式 `R_j` 路线集只是已知路线的加速通道,`alternative_mechanism` 路型兜底;
- 非对称等价准则(BEM)处理"路线外但更强"的证据;
- eRAG(2404.13781)式效用检查在建题时验证合同可满足性:语料内确实存在 ≥1 处(理想 ≥2 处)能满足该合同的页面,并记录等价类。

---

## 3. 其余挑战的文献答案(简)

### 挑战 4:搜索 API 混杂因素

- **oracle-retrieval 消融**(BrowseComp-Plus 2508.06600):把金标证据直接喂给 agent,gpt-4.1 从 14.58% 升到 93.49%,干净分离"找不到"与"用不好"。DRA 可用 ledger 回放或注入等价类证据实现同款诊断车道;
- RAVine(2507.16725)实证:搜索精度与最终报告质量**弱相关**;DeepWeb-Bench(2605.21482):检索仅占错误的 12-14%,瓶颈在取证后。这两条是"必须分开报告搜索相关性 / 页面获取 / 报告 grounding"的现成论据;
- DeepResearchGym(2505.19253):citation faithfulness 是跨搜索后端最不稳的指标,佐证搜索污染与报告造假不能混算。

### 挑战 6:覆盖 rubric ≠ 报告整体优秀

- 文献一致做法:holistic 质量独立评,不入乘法总分(HealthBench 分轴;DeepResearchGym 的 clarity/insight 独立 judge,配 "do not be generous" 提示硬化;RACE 作为 holistic tab 的参考实现);
- AdaRubric(2603.21362)的 DimensionAwareFilter 处理"维度掩蔽"(文笔好掩盖证据缺失):义务分组聚合、组间不可互补。

### 挑战 7:外部有效性

- 关键先例:FutureSearch Deep Research Bench(2506.06287)的 RetroSearch 验证了**离线冻结网页上的 agent 行为与真网可比**,直接回应"沙箱不真实"的审稿质疑;论文引用它并可复刻一个小规模等价性实验;
- 边界措辞照旧:DRA 证明的是冻结、有限、可审计环境中的研究能力,不外推开放互联网。

---

## 4. 引用错误分类与 evidence contract schema

### 4.1 分类(文献合并版,可判定性逐层递减)

```text
L0 在册性(确定性:registry)
   F1 fabricated-unregistered   注册表外 URL
   F1b identifier-hijacking     在册 URL 但被说成别的内容(Ansari 2602.05930;闭世界真实攻击面)
   F2 stale                     在册但快照不可达(闭世界中出现即 harness bug 信号)
L1 观察性(确定性:observation ledger)
   U1 unobserved citation       在册但本次未抓取。文献最近亲是 post-rationalization
                                (2412.18004,只能反事实干预近似);DRA 是首个可判定实现
L2 相关性(轻量语义)
   R1 irrelevant                被引页与 claim 离题(CAQA 2401.14640)
L3 支持性(重语义)
   S1 unsupported-insufficient  在题但不蕴含(AttrScore extrapolatory / CAQA insufficient)
   S2 partially-supported       部分蕴含(现缺此档,建议补)
   S3 contradicted              蕴含否定(CAQA 细化定义:支持推理但结论不同)
L4 绑定性(位置语义)
   B1 wrong-binding             引文支持邻近另一 claim。文献缺位(CiteEval 明文确认不区分);
                                DRA 第二个独有贡献点
L5 卫生诊断(不进门槛,进诊断面板)
   H1 redundant(ALCE 移除测试)  H2 missing citation  H3 substandard source(角色不合格)
```

我们有而文献缺:U1、B1。文献有而我们缺:R1/S1 拆分、S2、F1b、H1/H2。

三类豁免(CiteEval 2506.01829):可归因于 query 本身、纯推理、常识的陈述不强制引用,防 C_i 过罚。

### 4.2 per-obligation evidence contract schema

```json
{
  "proposition": "<claim 模板,不含 witness 实体>",
  "allowed_roles": ["measurement", "official_doc", "community_experience"],
  "disqualified_roles": {"marketing": "不得支撑性能/耐久类 claim"},
  "relation": "entails | measures | exemplifies",
  "aggregation": "single | union | intersection | chain",
  "min_independent_sources": 1,
  "exemptions": ["query_given", "pure_reasoning", "common_knowledge"],
  "witness_equivalence_class": "<私有,仅证可答性,不入运行时白名单>"
}
```

- 角色本体:论辩挖掘的 Study/Expert/Anecdotal 三型(Rinott et al., EMNLP 2015)扩展为 DRA 语料角色;registry 元数据可**预先标注每页角色**,把角色判定降为确定性检查;
- 聚合词汇来自 CAQA 四型;"拼接后整体蕴含"判定来自 ALCE(2305.14627);
- 树形聚合与 partial credit 形态参照 Mind2Web 2(2506.21506,文献中"接受替代合法来源"最成熟的实现)与迁移文档的 `z_j = max_r min_p g_jrp` 完全兼容;
- 文献缺口(可占位):没人把"角色 × 关系 × 可观察性"合成单一 per-obligation 合同;"证据等价类"显式枚举无任何基准做过。

---

## 5. 定位与论文弹药

### 5.1 四个经查证的空白(可声称贡献)

1. **requirement-deletion test 无先例**(最近亲:RaR perturbation 测区分度、QUBRIC learnability 测训练信号量,都不是必要性);
2. **闭世界可答性 + 证据等价类枚举无先例**(DEEPRUBRIC 最接近但用于训练合成、不可审计、路径耦合);
3. **route-binding 无名无度量**;多合法结论的 rubric 设计(开放结论 + 结论-证据蕴含谓词)完全空白。现有工作两极:绑金标文档(BrowseComp-Plus、DR3-Eval、ReportBench、DeepResearch Bench II、Wiki Live)或放弃可判定性(Mind2Web 2 手工 judge 脚本、RACE 参考报告、纯 rubric bundle 系);**没人同时做到可判定 + 路线自由**;
4. **合法替代层认证 FRR 无先例**(2604.16383 记录了误拒失败模式但无解法;BEM 只做了短答案侧)。

另两个独有机制:U1 unobserved(凭 ledger 首个可判定实现)、B1 wrong-binding。"proof of fetch" / "observation ledger" 术语检索无先例,可占名,引 BrowseComp-Plus 交互日志 Recall、RAVine fetch 指标、Mind2Web 2 judge 时缓存作部分先例。

### 5.2 ledger 必要性的实证弹药(引用别人的失败)

- RAVine:部分模型 50%+ 的 completeness 来自参数知识而非抓取页面("prior evaluations 的疏漏");
- DR3-Eval:参数知识幻觉是首要失败模式;
- AssistantBench:闭卷模型"体面但幻觉";
- DeepTRACE(2509.04499):生产级 DR 系统大量陈述不被自己的引用支持;
- 2604.03173:商业 DR agent 引用幻觉率至多 13.3%,给验链工具后可降 6-79 倍(干预实验设计可复刻);
- 2605.06635:前沿模型链接有效率 >94% 但事实核查仅 39-77%,且随研究深度显著劣化。

### 5.3 必须处理的写作事项

- **同名消歧**:"DeepResearch Arena"(Wan et al., 2509.01396, AAAI 2026)已存在,机制无关(seminar 转写生成任务、live 环境、无 grounding)。论文 related work 与网站 FAQ 都要显式消歧;
- 与 BrowseComp-Plus 的对比要点名:其 retrieval recall 与 citation 指标绑定人工标注的证据文档集,正是 DRA 拒绝的 reference-route;它对多解 query 的处理是删除(避免)而非接受(解决);
- DR Tulu(2511.19399)的 evolving rubrics 是训练侧合理、评测侧反面的教材:测量需要冻结靶子;引它论证"冻结 + 版本化增补"的治理选择;
- QUEST(2605.24218,ID 再次确认)可引作"语料派生 rubric 监督正在成为训练侧标准,DRA 补上缺失的可判定评测侧";DRA 的非二值 reward 设计使其可反向充当 QUEST 式配方的 RL 环境(呼应 RL-ready V3 设计)。

### 5.4 值得借来补短板的机制(按性价比排序)

1. BrowseComp-Plus 的 oracle-retrieval 消融车道(ledger 回放即可实现,成本低,诊断价值高);
2. DR3-Eval 的 leave-one-out 综合必要性检查并入建题闸门;distractor/noise 信噪分层作为语料难度轴;
3. RAVine 的 block 级 citation P/R 与 vital/okay 加权;每轮迭代 search gain 曲线;
4. DeepResearch Bench 的 Effective Citation Count 作 per-report 丰度诊断(防少引保准确率);
5. FutureSearch 的轨迹失败分类(重复搜索/遗忘/过早下结论)作为 ledger 派生的廉价诊断;
6. ResearchRubrics 复杂度三轴给 DRA 案例分层,治理"49/57 单结论"的分布性缺陷(exploration 轴高的题天然多结论)。

---

## 6. 建议的行动顺序

前置于 #39 的部分只有 (1)(2) 的设计冻结;其余可与迁移并行。

1. **Rubric Builder v1**(§1.2 配方)落到迁移文档 Phase 2:17 道 development 题上先跑通"两段式生成 + 三重过滤",把 learnability filtering 并入六项 substitution 测试,产出每题的 route-binding 量化数(合法替代 harness 义务满足率);
2. **HarnessEval 校准集启动**(§2.2):伪证据层可先行(手术腐蚀程序化生成,真值免标注);合法替代层与迁移文档 Phase 3 的"构造多路线报告"合并,一份人力两用;
3. **contract schema 定稿**(§4.2)并给 registry 页面预标注证据角色(一次性工作,换来角色判定确定性化);
4. **evaluator 发布件**:指标清单(§2.3)+ PPI 管线(§2.4)+ 锚集监控(§2.5);
5. 论文侧:同名消歧、§5.1 四空白写入贡献、§5.2 弹药入 related work / motivation。

---

## 附录 A:核心论文 ID 速查(全部经 abs 页核验,除注明者)

**Rubric 生成与验证**:HealthBench 2505.08775 / PaperBench 2504.01848 / RaR 2507.17746 / TICK 2410.03608 / InFoBench 2401.03601 / WildBench 2406.04770 / CheckEval 2403.18771 / ResearchRubrics 2511.07685(Scale AI,ICLR 2026)/ ProfBench 2510.18941 / RLCF 2507.18624 / EvalGen 2404.12272 / OnlineRubrics 2510.07284 / QUBRIC 2606.03968 / DEEPRUBRIC 2606.17029 / CHERRL 2606.04923 / RuVerBench 2606.29920 / LLM 写 rubric 元评测 2607.12835 / AdaRubric 2603.21362 / RubricHub 2601.08430 / 结构化评测综述 2606.08625

**Judge 元评测与统计**:ARES 2311.09476 / PPI 2301.09633 / AutoEval Done Right 2403.07008 / PRECISE 2601.18777 / PPI 排序 2606.05308 / JudgeBench 2410.12784 / MT-Bench judge 2306.05685 / null-model 攻击 2410.07137 / JudgeDeceiver 2403.17710 / Coin Flip 2603.06594 / MiniCheck 2404.10774 / FActScore 2305.14251 / SAFE 2403.18802 / VeriScore 2406.19276 / AttributionBench 2402.15089 / BEM 2202.07654 / ABC 2507.02825 / RubricEval 2603.25133 / Autorubric 2603.00077 / RULERS 2601.08654 / Catching One in Five 2606.10315 / 医疗 judge 分歧 2604.16383 / AI2 元评测 2603.06942 / Conformal Elo 2606.13221 / Who Drifted 2606.15474 / REFLECT 2605.19196

**DR 基准与环境**:DeepResearch Bench 2506.11763 / FutureSearch DRB 2506.06287 / BrowseComp 2504.12516 / BrowseComp-Plus 2508.06600(ACL 2026)/ DeepResearchGym 2505.19253 / Mind2Web 2 2506.21506 / RAVine 2507.16725 / DR3-Eval 2604.14683 / GAIA 2311.12983 / AssistantBench 2407.15711 / LiveDRBench 2508.04183 / DeepResearch Arena(同名,他人)2509.01396 / ReportBench 2508.15804 / LiveResearchBench 2510.14240 / Dr. Bench 2510.02190 / DEER 2512.17776 / DeepResearch Bench II 2601.08536 / ResearchQA(rubric)2509.00496 / ResearchQA(citation-grounded)2607.11074 / DeepTRACE 2509.04499(标题级)/ DeepResearchEval 2601.09688 / Wiki Live 2602.01590 / DeepWeb-Bench 2605.21482 / Deep Research Comparator 2507.05495(标题级,WWW 2026)

**归因与等价**:ALCE 2305.14627 / AIS 2112.12870 / Attributed QA 2212.08037 / AttrScore 2305.06311 / CAQA 2401.14640 / ExpertQA 2309.07852 / CiteEval 2506.01829 / L-CiteEval 2410.02115 / LongCite 2409.02897 / RAGAS 2309.15217 / eRAG 2404.13781 / 生成式搜索可验证性 2304.09848 / post-rationalization 2412.18004 / GopherCite 2203.11147 / PEDANTS 2402.11161 / Return of EM 2404.15650 / 引文幻觉五型 2602.05930 / 引文幻觉规模审计 2605.07723 / 引用幻觉检测与纠正 2604.03173 / Cited but Not Verified 2605.06635 / DeepSciVerify 2605.27710 / PING 2601.22984 / 证据类型本体 Rinott et al. EMNLP 2015(非 arXiv)

**训练侧近邻**:QUEST 2605.24218 / DR Tulu 2511.19399 / CaRR 2601.06021
