我先读取评审提示文件，了解全部要求。
我已读完 v1.3 规范。现在并行派出 4 个子代理逐篇提取 20 篇论文的指标聚合方式，同时我自己读另外两份 DRA 文档。
子代理已完成 20 篇论文提取。现在快速浏览三轴旧版设计文档的关键部分。
所有材料已读完：20 篇论文的指标提取（4 个子代理，含行号证据）、v1.3 四轴规范、三轴旧版设计、Qwen 扩展约束。以下为完整评审正文。

---

# DRA 评分设计独立方法学评审

评审对象：`DRA_FOUR_AXIS_SCORING_V1_3_SPEC.md`（下称 **v1.3**），参照 `DRA_THREE_AXIS_SCORING_REDESIGN_2026-07-22.md`（下称 **三轴稿**）与 `DRA_QWEN_SCORER_SCALING_WITHOUT_METRIC_CHANGE_2026-07-30.md`（下称 **Qwen 扩展稿**）。文献依据为 `docs/literature/dra_scoring_20_2026-08-02/` 的 20 篇论文，引用格式为 `[编号 简称, 章节]`，编号与标题对应 `paper_manifest.tsv`。本评审为只读分析，未修改任何文件，未运行评测。

## 1. 裁决摘要

1. **"大多数类似工作采用 precision–recall 思路"这一命题在严格口径下不成立，在宽口径下勉强成立，且在 deep research 专项基准中明显不成立。** 20 篇中显式命名 P/R 或 F1 作为生成内容核心指标的为 9/20（45%）；真正计算 F1 调和平均的为 7/20（35%）；把未命名双分母与单侧 precision 全部放宽计入才达 14/20（70%）。6 篇 deep research 报告级基准（01–04、15、20）中仅 1 篇（04 ReportBench）显式使用 P/R，主流是 rubric 通过率与多维面板。F1 集中在长文事实性与引用评估子领域（05、07、09、11、12、14、18）。
2. **v1.3 的 `Truth = Provenance × mean(Fact, Evidence, Completeness, Rubric)` 存在三处可指证的结构性缺陷**（非价值判断）：(a) Evidence 的 `R_E` 与 Completeness 共用 TEC unit 分母，轴间不独立；(b) 伪造 URL 在 Provenance（乘法）与 Evidence（`Observed` 失败）被重复计分，三轴稿 §14 自己承认了这一点；(c) Completeness 不门控真实性，产生"说错优于不说"的反向激励。此外 v1.3 缺少全部零分母约定，且 §10 同时挂着 linear 与 geometric 两个候选公式，当前并不存在唯一的正式聚合规则。
3. **Fact 与 Completeness 可以组成 Content F1，且 DRA 是少数满足前提的场景**——TEC 就是 canonical proposition universe,v1.3 §2 第 7 步的 claim→unit 映射已是机械化对应关系的雏形。前提是：recall 侧改为"被 v=true claim 覆盖"（门控真实性、不门控引用），映射表冻结可审计，out-of-census 的真实 claim 只诊断不罚。
4. **Evidence 应保留为独立的 Citation F1 轴，但 recall 分母必须从 TEC unit 改为报告的 citation-required statement（ALCE/LongCite 式）**,以消除与 Completeness 的分母重叠。
5. **Provenance 应取消报告级相乘，改为 binding 级合取 + 伪造率榜单旗标 + 资格标记**。五种失败（伪造、未观察、不支持、错绑、反证）在单元级合取下各自只计一次；报告级乘法惩罚的是"伪造密度"而非"伪造危害"，且随引用总数稀释。
6. **推荐主方案为"双 F1 + Rubric + Provenance 资格化"**(Truth = mean(Content F1, Citation F1, Rubric))，保守兼容方案为 v1.3 加零分母补丁并交叉发布一个周期。Qwen judge 必须逐轴做 metric-wise 人工校准——总分接近不能当作轴等价，这是论文 20 的核心实证发现。

## 2. 20 篇计数表

分类口径：**a** = 显式命名并计算 F1 调和平均；**a−** = 显式命名 P/R 但不合并、不算 F1;**b** = 双分母比例但不称 P/R、不合并；**c** = 单侧 precision（或 recall);**d** = rubric/多维面板；**e** = 其他聚合。组合表示多指标并存。"校准"指判官/指标与人类判断的一致性实验。

| # | 论文（简称） | 类别 | 显式 F1 | P 侧分母 | R 侧分母 | 人类校准 |
|---|---|---|---|---|---|---|
| 01 | DeepResearch Bench | c+d | 无 | 去重 statement–URL 对（C.Acc.，自称 precision,§E.1) | 无 recall;E.Cit. 为计数 | 有：100 对 support 96%/not-support 92%;RACE 50 任务×3 专家，Pearson 0.995 |
| 02 | DeepResearch Bench II | d | 仅 meta-eval |: | rubric 通过比例，分母=任务全部 rubric(§3.1.2) | 有：10 报告，judge ACC 91.75/F1 89.57(§4.3) |
| 03 | ResearcherBench | b+d | 仅 meta-eval | Faithfulness:被引 claim 数 | Groundedness：全部事实 claim（分子只要求"被引",§4.2) | 有：10 回答，judge Weighted F1=0.80(Table 3) |
| 04 | ReportBench | a− | 无 | 生成报告的参考文献 | gold 综述参考文献全集（§3.2) | 无系统实验，仅 2 例人工审计（§4) |
| 05 | OpenScholar | a+d | **有（Citation F1 主指标，§3.2)** | 报告给出的引用（含必要性检验） | citation-worthy 语句（句级） | 有：108 问答×16 专家；rubric 标注者 Pearson 0.793 |
| 06 | ALCE | a− | 无（全文无 F1) | 响应中全部引用条目（引用级） | 响应中全部陈述（句级，§3.3) | 有：200 例，κ recall 0.698/precision 0.525(§6) |
| 07 | LongCite | a | **有（Citation F1,§3.3.2)** | 全部引用条目 | 全部陈述（功能性句子豁免） | 有：150 响应/1064 陈述，κ 0.544–0.655(§5.3) |
| 08 | CiteEval | d | 仅对比基线 |: | 1–5 Likert + 学习编辑距离，mean pooling(§2.4/§4.2) | 有：1200 实例×3 盲标，α 0.774–0.980 |
| 09 | ALiiCE | a | **有（Table 1 表头 R/P/F1)** | 引用条目（recall=0 组连坐为 0) | 原子声明（claim 级，§3.3) | 有：κ recall 0.71/precision 0.62;Fleiss κ 0.58–0.78 |
| 10 | FActScore | c | 无（明确弃 recall,§3.1) | 响应的原子事实总数 |: | 有：183 实体，标注者一致率 88–96%；估计器 ER<2% |
| 11 | SAFE/LongFact | a | **有（F1@K,§5 式 1)** | S+N(irrelevant 除外） | 超参 K（人类偏好长度，非 gold 集） | 有：16,011 条标注，一致率 72% |
| 12 | VeriScore | a | **有（沿用 F1@K,§2.4)** | 全部可验证 claim \|C\| | 域内模型输出中位数 K | 有：Fleiss κ 0.73–0.77(§3) |
| 13 | D-FActScore | c | 无（明确只做 precision) | 全部原子事实 \|A_y\| |: | 有：300 段人工标注，Pearson 强相关（§5) |
| 14 | FaStFact | a | **有（F1@K′,§4.4.2 式 6)** | S+N | gold K′，对称逻辑斯蒂惩罚（过长也罚） | 有：400 样本×10 标注者，IRR 93.6–95.0% |
| 15 | DeepFact | e(a 限于验证器） | F1 是验证器分类性能，非报告事实性分 | 分类口径 | 分类口径；报告级无聚合分 | 有：micro-gold 协议，专家 60.8%→90.9%(§4) |
| 16 | MiniCheck | e | 无 |: | balanced accuracy,10 数据集平均（§4.1) | 有：合成数据 Fleiss κ 0.51/0.70 |
| 17 | RAGAs | c+e | 无 | faithfulness=supported/全部陈述（未命名） | context relevance=关键句/context 句数（未命名）;answer relevance 为余弦均值 | 有：2 标注者，一致率 90–95%，无 κ(§4) |
| 18 | RAGChecker | a | **有（claim 级 P/R/F1,§3.3.1)** | response 全部 claim | gold answer 全部 claim | 有：280 对×2 标注者，Pearson/Spearman，人类一致率 90.95% |
| 19 | ARES | e | 无 |: | 三分类器逐三元组取平均 + PPI 置信区间（§3.2–3.3) | 有：150–300 条人工验证集供 PPI；无 IAA |
| 20 | Deep Research, Shallow Evaluation | e（元评估） | 无 |: | 自身用 τ-b/一致率；其对象 ScholarQA-CS2 为四指标平均（§3) | 核心贡献即校准批评：IAA 仅 55%,metric-wise 一致率远低于系统级 |

容易误判的三处：(i) 06 ALCE 只有句级 citation recall + 引用级 citation precision，全文不计算 F1，按规则只能记 a−；(ii) 03 ResearcherBench 的 Groundedness 分子是"被引用的 claim"而非"被支持的 claim"，不是 ALCE 式 recall，记 b；(iii) 15 DeepFact 的 F1 是验证器对基准标签的分类 F1，与"生成文本事实性 F1"是不同对象，不可混入计数。

## 3. "precision–recall 思路"命题检验

**严格口径（论文显式命名 P/R 或 F1 作为生成内容的核心评价指标）**:04、05、06、07、09、11、12、14、18，共 **9/20 = 45%**。其中真正计算 F1 调和平均的（05、07、09、11、12、14、18）为 **7/20 = 35%**。分母结构：P 侧分母均为"系统产生的单元"（原子事实、引用条目、陈述），R 侧分母分三类——应覆盖单元（09 的原子声明、18 的 gold claim、05/06/07 的 citation-worthy 语句）、gold 参考集（04 的综述文献全集）、超参数 K（11、12、14，其中 14 改为 gold K′ 并对称惩罚冗长）。

**宽口径（任何"产生侧比例 + 覆盖侧比例"的双分母结构，无论是否命名，外加单侧 precision）**：严格 9 篇 + 03（未命名双比例）+ 01、10、13（仅单侧 precision)+ 17（两个未命名单侧比例）= **14/20 = 70%**。若把 20 号论文的评审对象 ScholarQA-CS2（显式 Citation Precision/Recall 但与 Answer Recall/Relevance 简单平均、不算 F1,[20, §3]）计入则为 15，但它是被评对象而非论文自身方法，不计。

**分领域看，命题的成立性完全依赖子领域**：长文事实性/引用评估子领域（05–14、16–19 共 15 篇）严格口径 9/15 = 60%;deep research 报告级基准（01、02、03、04、15、20 共 6 篇）严格口径 1/6 ≈ 17%，主流是 rubric 通过率（02 的 9,430 条二元 rubric)、加权 checklist(03)、动态加权四维面板（01)。**结论：DRA 的直接同类（deep research 基准）恰恰最不采用 P/R 思路；P/R–F1 传统来自 claim 级事实性与引用评估文献。为 DRA 的 Content/Citation F1 辩护时应引用后者，不应声称前者存在共识。**

## 4. 现公式审计

v1.3 §10 的正式候选为 `Truth = Provenance × mean(Fact, Evidence, Completeness, Rubric)`（另有 geometric 候选未选定）。逐项审计如下。

### 4.1 可保留的部分

- **多状态 Fact 裁决与分母纪律**(v1.3 §3):`true/false/conflicted` 进分母、`out_of_world/exempt` 中性、`unresolved` 收缩分母并另报 AdjudicationCoverage。这与文献最佳实践一致：SAFE 把 irrelevant 排除分母 [11, §5 脚注 7],VeriScore 在抽取阶段剔除不可验证内容 [12, §2.4],FaStFact 把 unverifiable 丢弃、conflicting/not-enough-evidence 并入 non-supported [14, §4.3]。v1.3 的处理比这三者更细，可保留。
- **Completeness 的 (facet, unit_type) 分组宏平均**(§7)：防止 unit 多的 facet 主导，方向正确。
- **Rubric 与 Completeness 的 source-ID 不相交证书**(§8)：正面回应了构念重叠风险。
- **Value-blind 检索**(§4）与**确定性 Provenance 谓词**(§9):12 个 harness 同尺子的基础，可保留。

### 4.2 重复计分（给具体反例）

**反例 A（伪造 URL 双重计分）**：报告引用 30 个 URL，其中 1 个伪造，被伪造 URL 支撑的 2 条 claim 内容恰好为真（参数知识答对）。按 v1.3:Provenance = 29/30（报告级乘法全局稀释）；该 binding 因无有效 native observation 而 `Observed` 失败，P_E 降为约 29/30;Fact 不受影响（claim 为真）。同一个伪造行为在**一个乘法项和一个加法项内被计两次**。三轴稿 §14 失败责任表自己写明"URL 伪造会降低 Provenance，并使相关 binding 无法通过。另行报告 fabricated URL 数量和比例，**便于解释重复影响**"——设计文档承认了重复，但 v1.3 未消除它。文献对照：OpenScholar 对幻觉引用只做存在性验证并在 citation 指标内计一次 [05, §3.2;Table 3];ReportBench 区分 statement hallucination 与 citation hallucination 但各自落在对应指标内一次 [04, §4]。

**反例 B(Evidence 与 Completeness 分母重叠）**:R_E 的分母是"citation-required units"(v1.3 §6),Completeness 的分母是"applicable TEC units"(§7)。citation-required units 几乎必然是 applicable units 的子集。设某 unit u 属两者：报告遗漏 u,Completeness 的 C_{f,g} 下降，R_E 同步下降，进而 Evidence 的 F1 下降。同一遗漏在四轴等权平均中被计约 1.5 次（Completeness 全额 + Evidence 的 recall 半额）。v1.3 §8 的 disjointness certificate 只约束 Rubric↔Completeness，未约束 Evidence↔Completeness。这违反了 §10 等权平均隐含的"轴已去重"前提——三轴稿 §12.2 声称"四个轴已经经过构念去重"，但分母共享使该声称在 Evidence–Completeness 之间不成立。

### 4.3 错误独立性假设（给具体反例）

**反例 C（说错优于不说的反向激励）**:v1.3 §7 规定 Completeness"不重新施加 Fact 或 Evidence 门"。设 unit u 询问某商品参数。报告甲给出错误答案：Fact 分母 +1 且不得分（Fact 降），但 u 在语义上"被覆盖",Completeness 得分。报告乙对 u 完全沉默：Fact 不受影响，Completeness 不得分。设其余轴相同，则甲的 mean 高于乙——**错误的覆盖比诚实的沉默得分更高**。`grounded_covered` 只是诊断字段，不进公式。文献对照：RAGChecker 的 overall recall 要求 response 蕴含 gold claim，暗含正确性门控 [18, §3.3.1];DRB-II 的 rubric 判定直接编码具体内容，覆盖与正确不可分 [02, §3.1.2]。没有任何一篇文献支持"错误内容计入覆盖"。

**反例 D（轴间可补偿）**：全凭参数知识答对、零引用的报告：Fact=1、Evidence=0、Completeness 中、Rubric 中，linear Truth ≈ 0.5×Provenance。v1.3 §10 引入 geometric 候选正是承认线性平均允许无关轴补偿零 Evidence；但 §10 把选择权留给"开发集人类排序校准"，当前规范状态下**正式公式不唯一**，这本身是一个审计发现。

### 4.4 构念混合（给具体反例）

- **Evidence 是五个谓词的 0/1 合取**(`Observed ∧ Bound ∧ Supports ∧ ScopeMatches ∧ RoleOK`,§6)：观测性（过程审计）、绑定位置、语义蕴含、范围匹配、来源角色是五个不同构念。反例 E:URL 真实但没抓（未观察）与抓了但内容不支持，在 Evidence 轴上得分完全相同，但前者是执行保真问题、后者是引用诚信问题——轴分无法区分，只能靠诊断字段补救。文献中这两类被明确分开：三轴稿 §11.2 把发现/抓取过程放入单独的 Execution Audit;ALCE 的 recall（缺引用）与 precision（坏引用）分轴报告 [06, §3.3]。
- **Fact 分母中的 conflicted 是世界属性**：多来源冲突时报告不得分但分母不减（§3 "Conflicted categorical claims receive no truth credit but remain in the denominator")。反例 F：两份内容相同的报告，评分世界快照中来源冲突程度不同，Fact 不同——分数差异来自世界而非报告。设计意图（惩罚在冲突证据下武断断言）合理，但它测量的是"报告在冲突世界中的行为"，与"报告说得对不对"不是同一构念，应至少分诊断字段报告。
- **Rubric 混合显式指令遵循与 latent 必要研究行为**(§8)：前者是 instruction following，后者与 Completeness 的 procedure/decision-structure 高阶 unit 在构念上是同一事物的"行为侧"表述。disjointness certificate 保证条目不重复，不保证构念不重叠。

### 4.5 零分母约定缺失

v1.3 未定义：`|Z|=0`（无引用时 Provenance，三轴稿 §11.1 定义为 0,v1.3 丢掉了这个约定）；无 binding 时 P_E；无 citation-required unit 时 R_E;K 为空集时 Completeness；无 rubric item 时 Rubric;Fact 分母全被 unresolved/exempt 排空时的取值。第 8 节给出完整约定表。

### 4.6 Provenance 报告级相乘的粒度问题

报告级乘法惩罚的是**伪造密度而非伪造危害**：引用 100 个 URL 时 1 个伪造只稀释 1%，引用 2 个时 1 个伪造稀释 50%，而两种情况下伪造支撑错误内容的危害可以完全相同。反过来，99 个真实 URL + 1 个关键伪造（支撑核心结论）只受 1% 惩罚。密度与危害脱钩，且随报告引用习惯（harness 风格）系统性偏移——这对引用稀疏的 harness 构成不成比例的惩罚，违反"12 个 harness 同一尺子"的前提。

## 5. Fact 与 Completeness 能否组成 Content F1

**结论：可以，DRA 恰好是少数满足前提的评估场景。** SAFE 系指标（F1@K）之所以用超参 K 当 recall 分母，是因为开放世界中"不可能构造确定的事实全集"[11, §5];DRA 的 TEC 就是冻结的 canonical proposition universe(atomic + higher-order units)，等效于 FaStFact 的 gold K′ [14, §4.4.2]，但语义化为 unit 集合而非计数。组成 Content F1 的充要条件与机械化方案：

1. **共享 universe 与冻结映射**:precision 侧单元 = 报告去重 material claim(v1.3 §2 管道）,recall 侧单元 = TEC applicable units。对应关系 = v1.3 §2 第 7 步已有的 claim→unit 映射，机械化要求：(a) 映射由同一冻结 Qwen3-8B 判定，输出 (claim_id, unit_id, relation∈{covers, partially_covers, contradicts, unrelated}, span 证据）;(b) 映射表随 claim ledger 一并冻结、哈希、可重放；(c) 映射质量纳入人工校准（见第 9 节）。
2. **recall 侧门控真实性、不门控引用**:Content Recall 的分子改为"被至少一条 v=true claim 覆盖的 applicable unit"。门控真实性消除反例 C；不门控引用，否则与 Citation 轴重复计分（见第 6 节）。
3. **precision 侧保持现 Fact 公式不变**(adjudicated claims 分母）。

边界情形的处理规则：

- **额外但真实的 claim（out-of-census)**:TEC 不可能完备（census_gap 状态的存在就是承认 [v1.3 §5])，因此真实但不在 census 的 claim **不进 Content F1 任何一侧**，只报 `off_census_claim_mass` 诊断。这不同于 SAFE 把 irrelevant 排除分母 [11, §5 脚注 7]——DRA 排除的依据是 census 外而非相关性，且 false 的 out-of-census claim 仍应进 Fact 分母（错误必须受罚，无论是否在 census 内）。
- **负命题**("X 不会导致 Y"):polarity 已是 v1.3 §2 去重键；claim 侧按多状态裁决处理——但 v1.3 硬不变量"Non-mention is never proof of a negative claim"意味着找不到正向 support span 的负命题**永远只能 unresolved**，不进分母（不奖不罚）。unit 侧允许 TEC 含负 unit（如"区分 A 与 B")，覆盖判定按语义匹配。负命题的处理是测量盲区，见第 11 节。
- **纯分析与推荐**:v1.3 §2 已规定 recommendations/preferences 不是 external atomic facts，故**只进 recall 侧**(decision-structure 高阶 unit 的覆盖），不进 precision 侧。这种不对称是合理的：分析不可判真假，但可判覆盖；它对应 RAGChecker 把 overall 指标与 generator 诊断分开的结构 [18, §3.3]。
- **不可裁决 claim**:`unresolved/retrieval_failure/instrument_ambiguous` 不进任何分母，由 AdjudicationCoverage 暴露，覆盖率过低触发 withheld 而非计 0(v1.3 §5 的 withhold 语义保留）。

## 6. Evidence 的位置：四种方案比较

**方案 E1（独立轴，现状）**：保留 P_E/R_E/F1。优点：诊断粒度最细，符合 ALCE/LongCite/ALiiCE/RAGChecker 的引用评估传统。缺点：R_E 与 Completeness 分母重叠（反例 B)；五谓词合取混合构念（反例 E)；等权平均给"引用 hygiene"25% 权重——**没有任何一篇文献给引用质量如此高的全局权重**:OpenScholar 把 Cite-F1 作为 citation accuracy 主指标但与 correctness、内容质量面板并列 [05, §3.2];DRB 的 C.Acc. 只是 FACT 分支下的一个数 [01, §E.1]。

**方案 E2（独立轴但改造分母，推荐）**:Citation Precision 维持 binding 级（passing bindings / all bindings);Citation Recall 分母从 TEC unit 改为**报告的 citation-required statements**(ALCE 句级 [06, §3.3]、LongCite 三档支持度 [07, §3.3.2]、CiteEval 的 Full 场景 [08, §3.1])。功能性句子（过渡、总结、纯推理）按 LongCite 先例豁免（recall 记 1 或判 N/A,[07, §3.3.2];CiteEval 的 parametric/response 归因 N/A 机制更系统 [08, §2.3])。优点：消除分母重叠；recall 分母只依赖报告自身与"是否需要引用"判定，与 TEC 解耦；文献支持最强。缺点：需要新增"citation-required"判定器并校准；句级 P/R 已知偏严（OpenScholar 承认相邻句引用会低估 [05, 局限])。

**方案 E3（claim 级 gate，并入 Fact)**：不独立成轴，定义 `grounded_true(c) = v(c)=true ∧ ∃ passing binding(c)`(citation-required 时）,Fact 只认 grounded claim，等价于把 FActScore 的 "supported by C" 换成 "supported by 本次观察"[10, §3.1]。优点：构念单一（"被本次研究证明的真")，彻底消除重复计分。缺点：无引用的真 claim 全灭，会鼓励策略性少引用（引用越多 binding 失败面越大）——除非 gate 只要求每条 claim ≥1 个 passing binding 且额外错绑另行计 precision，但那又把独立轴请了回来；且丢失"内容对但没证明"与"内容错"的区分，而这恰是 DRA 相对普通事实性基准的核心卖点（三轴稿 §15.4)。

**方案 E4（并入 Provenance)**:Provenance 谓词扩展为 `ValidURL ∧ Observed ∧ SupportsBoundClaim`，保持报告级乘法。优点：轴数减为 3,Provenance 一次性承担来源真实性。缺点：Provenance 从确定性规则变成语义判断，违背 v1.3 §9"Provenance does not judge semantic support"的设计隔离；报告级乘法的粒度问题（4.6 节）被放大到全部引用失败类型；伪造与"真实但未观察"在乘法中等同，诊断退化。

**比较结论：E2 最优。** E3 可作为并列诊断（`grounded_fact`)，类似 v1.3 已有的 `grounded_covered`。E4 拒绝。

## 7. Provenance 的粒度：三种方案对五种失败

| 失败情形 | P1 报告级相乘（现状） | P2 claim/binding 级合取（推荐） | P3 资格/完整性标记 |
|---|---|---|---|
| fabricated URL | Provenance 降 + binding 失败（**双计**，反例 A) | binding 必然无有效观察 → 该 claim/unit 失格**一次**；伪造率进榜单旗标 | 分数不动；伪造率超阈值 → 报告 flagged/withheld |
| 合法但未观察 | Provenance 通过，Evidence 失败（三轴稿 §11.3 表） | binding 的 Observed 失败 → 该 claim 不 grounded，计一次；URL 存在性 credit 保留在诊断 | 同 P2，另报 unobserved_rate |
| 已观察但不支持 | Evidence precision 降（一次） | binding 失败，计一次；URL 不受罚 | binding 失败，一次 |
| 错绑 | Evidence precision 降（一次） | 该 binding 失败；claim 有其他 passing binding 仍 grounded | 同 P2 |
| 反证（contradicted citation) | Evidence precision 降 + claim 可能判 false/conflicted 使 Fact 降（**双计**) | claim 判 false → unit 失格；binding 失败是同一事实的另一面，合取下只计一次 | 同 P2 |

P1 的问题已在 4.2（双计）与 4.6（密度≠危害）给出。P3 分数语义最干净（Truth 只测内容，伪造作为诚信问题单独处理，类比学术不端不按比例扣内容分），但资格阈值武断、低伪造密度完全逃逸惩罚。P2 使五种失败各计一次、惩罚局部化到被支撑的 claim/unit，伪造的功能后果（其支撑的内容不得分）自动成比例；残余的诚信维度由两个非分数机制承担：`fabricated_url_count/rate` 榜单旗标（公开可见）与 eligibility 规则（如确认伪造数 ≥ 预注册阈值则 formal 成绩 withheld)。**推荐 P2 + 旗标 + 阈值资格，即 P2 与 P3 的组合。** 这与 v1.3 §10 既有的"scorer-side failures cause withholding"机制兼容。

## 8. 候选方案与极端案例推演

### 8.1 三个可运行候选方案

**方案 A（保守兼容）**:v1.3 四轴 + Provenance 乘法原样保留，仅做四项补丁：(i) 补齐全部零分母约定；(ii) Completeness 主分改为 true-covered(`grounded_covered` 升为主分，消除反例 C);(iii) 伪造 URL 从 Provenance 比例中移出，改为 binding 级失败 + 旗标（消除反例 A 的双计）,Provenance 只测 canonicalization/registry/snapshot;(iv) 正式公式在 linear 与 geometric 之间用开发集校准选定一个。轴、judge、管道全部不动，可与历史分数 crosswalk。

**方案 B（双 F1 重构，主推荐）**：三轴 + 资格化 Provenance。
$$\mathrm{Truth}_t = \frac{1}{3}\left(\mathrm{ContentF1}_t + \mathrm{CitationF1}_t + \mathrm{Rubric}_t\right)$$
Content F1 按第 5 节定义（precision = 现 Fact;recall = true-covered applicable units 的分组宏平均）;Citation F1 按方案 E2 定义（binding 级 precision,statement 级 recall);Rubric 不变；Provenance 按第 7 节 P2+旗标+资格处理。

**方案 C（单元级合取，最简）**：唯一内容分 = TEC applicable units 中 `covered ∧ true ∧ (citation-required ⇒ grounded)` 的比例（DRB-II 通过率的 unit 级推广 [02, §3.1.2],加 grounding gate),Fact precision 与 binding 失败原因全部降为诊断；Rubric 独立；Provenance 纯资格标记。Truth = mean(UnitPassRate, Rubric) × eligibility。缺点：额外的错误陈述不进任何分母（说 1000 句错话但覆盖全部 unit 仍满分），必须外挂 false-claim penalty 才完备——外挂之后就退化为方案 B，故 C 只作对照。

### 8.2 八个极端报告推演

设定共用背景：TEC 分 4 个 (facet, unit_type) 组。数值为推演假设，用于暴露公式行为，不是实测。

**案例 1：短而全真。** 5 条 claim 全 true(CP=1),unit 覆盖 5%(CR=0.05),2 引用全 passing(CitF1=1),Rubric=0.3,Provenance=1。
A:Truth = 1×(1+1+0.05+0.3)/4 ≈ **0.59**。B:ContentF1 = 2·1·0.05/1.05 ≈ 0.095,Truth = (0.095+1+0.3)/3 ≈ **0.47**。C:UnitPassRate≈0.05,Truth ≈ **0.18**。三方案都挡住"一句真话接近满分"（三轴稿 §15.2 的目标），严厉程度 C>B>A。A 中 Evidence=1 给了过高补偿——5 句话的引用完备性与 500 句的引用完备性被等权，这是 A 残留的轴失衡。

**案例 2：长且堆真事实。** 300 条 claim 全 true(CP=1),atomic 组覆盖 70%、三个高阶组 0%(CR = (0.7+0+0+0)/4 ≈ 0.175),20 引用全 passing,Rubric=0.4。
A:1×(1+1+0.175+0.4)/4 ≈ **0.64**。B:ContentF1 ≈ 0.298,Truth = (0.298+1+0.4)/3 ≈ **0.57**。C:≈ **0.29**。A 把"事实收集器"评到 0.64 偏高——这正是三轴稿 §15.3 要区分的 Deep Research 与普通 fact collection;B、C 通过高阶 unit 缺失把它压下来。注意 B 中 Citation F1=1 同样有案例 1 的补偿问题，但被 ContentF1 的低值平衡。

**案例 3：广但少引用。** 覆盖 90% units,CP=0.95，只 3 个引用且 passing；多数 citation-required statements 无引用（CitP=1, CitR=0.1, CitF1≈0.18),Rubric=0.8,Provenance=1。
A:Evidence F1≈0.18,Truth = 1×(0.95+0.18+0.9+0.8)/4 ≈ **0.71**。B:ContentF1 ≈ 0.92(CR 不门控引用，避免与 Citation 轴双计）,Truth = (0.92+0.18+0.8)/3 ≈ **0.63**。C:unit 通过要求 grounded，未引用 unit 不得分，Truth ≈ **0.3**。C 把"没引用"与"没覆盖"混罚，且与 Citation 诊断重复；B 的分离最清晰：内容分照给，引用轴单独暴露。

**案例 4：引用很多但错绑。** 50 引用，CitP=0.2、CitR=0.9 → CitF1≈0.33;CP=0.9（内容本身对）,CR=0.8,Rubric=0.7，全部 URL 真实。
A:Truth = 1×(0.9+0.33+0.8+0.7)/4 ≈ **0.68**。B:ContentF1≈0.85,Truth = (0.85+0.33+0.7)/3 ≈ **0.63**。C:grounding gate 使通过率 ≈0.16,Truth ≈ **0.3**。A、B 相近且合理：错绑只伤引用轴，不伤内容分——错绑不是内容错误（三轴稿 §14 `wrong_binding` 行：Fact 内容可能正确）。C 把引用 hygiene 错当内容错误，过重。

**案例 5:URL 真实但没抓。** URL 全部在 registry 且有快照，但本次运行未观察 → 全部 binding 的 Observed 失败（CitF1=0);Fact 经独立检索仍判 CP=0.9,CR=0.7,Rubric=0.7。
A:Provenance=1（三轴稿 §11.3 的有意设计）,Evidence=0,Truth = 1×(0.9+0+0.7+0.7)/4 ≈ **0.58**。B:Truth = (ContentF1≈0.79 + 0 + 0.7)/3 ≈ **0.50**。C:≈ **0.23**。这是执行保真失败：B 的 0.50 比 A 的 0.58 更清楚地把它与案例 3（同样 CitF1≈0 档）区分开的代价是两者得分接近——可接受，因为诊断字段（`unobserved_rate` vs `missing_citation_rate`）承担了区分职责。

**案例 6：一个伪造 URL。** 30 引用中 1 个伪造，其支撑的 2 条 claim 内容为真。
A:Provenance=29/30 ≈ 0.967 全局相乘，且 binding 失败再计一次（反例 A);Truth ≈ 0.967×(≈0.85) ≈ **0.82**，伪造被计两次。B：该 binding 合取失败一次（CitP=29/30),`fabricated_url_count=1` 旗标上榜，内容与 Rubric 不受影响；无乘法。若预注册资格阈值为"确认伪造 ≥1 则 formal withheld"，则该报告 formal 成绩暂扣、诊断分照发——**这是推荐的阈值语义**：伪造是诚信事件，不是比例事件。C：同 B 的合取行为。

**案例 7：合理替代路线。** 不使用构题 witness graph，改用其他真实注册来源覆盖相同 units、引用全部 passing。
三方案均应得与 witness 路线相同的分：v1.3 §7 已规定"Alternative evidence routes are accepted. TEC witness URLs are not an allowlist"。推演结果 A=B=C=**不惩罚**。这是必须守住的回归不变量；风险点在实现——若 Completeness 的 claim→unit 映射或检索配额暗中偏向 witness URL，会隐性惩罚替代路线，须纳入第 10 节实验 E6。文献侧，没有任何论文把构题路线当唯一合法路线；SAFE/VeriScore 的检索器完全开放 [11, §4;12, §2]。

**案例 8：没有可引用正向 span 的负命题。** 报告正确陈述"X 不会导致 Y"，世界中只有 absence of evidence。
claim 侧：v1.3 硬不变量"Non-mention is never proof"→ 该 claim 永远 unresolved，不进 CP 分母（三方案同为**中性**,truth credit 拿不到但也不罚）。binding 侧：报告若附引用，NLI 蕴含无法从 absence 推出负命题 → Supports 失败 → **Citation 轴被系统性误伤**;ALCE/LongCite 的 NLI 路径有完全相同的问题，文献未解决 [06, 局限；07, §3.3.2]。处理建议：负命题 claim 的 citation-required 判定走"反驳检查"通道——引用页面需同范围讨论 X–Y 关系且不存在正向断言，则 binding 记 `supports_by_absence`（单独 verdict，需人工校准后才可给 credit)；校不准则该 binding 判 N/A 而非失败，避免惩罚诚实标注。此机制在任何候选方案中都缺失，列入第 10 节实验与第 11 节限制。

**跨案例小结**：方案 A 在案例 1、2 偏宽（轴补偿），方案 C 在案例 3、4 偏严（引用问题污染内容分），方案 B 在八个案例中无一出现方向性错误，且每个失败类型恰好落在一个轴上。B 对案例 5 与案例 6 的区分依赖诊断字段而非总分——可接受，因为榜单同时发布诊断字段（第 9 节）。

## 9. 推荐方案

### 9.1 主方案（方案 B）精确定义

记报告 t 的去重 material claim 集为 $\mathcal{C}_t$,verdict $v(c)$ 与 materiality mass $m(c)$ 沿用 v1.3 §2–§3;TEC applicable units 按 $(f,g)$=(facet, unit_type) 分组，组集为 $K_t$；冻结映射 $M: \mathcal{C}_t \to 2^{\mathrm{Units}}$。

**Content 轴：**
$$
\mathrm{CP}_t = \frac{\sum_{c:\,v(c)=true} m(c)}{\sum_{c:\,v(c)\in\{true,false,conflicted\}} m(c)}
$$
$$
\mathrm{CR}_{f,g} = \frac{\#\{u \in \mathrm{Applicable}_{f,g} : \exists c,\ v(c)=true \land u \in M(c)\}}{\#\mathrm{Applicable}_{f,g}},
\qquad
\mathrm{CR}_t = \frac{1}{|K_t|}\sum_{(f,g)\in K_t}\mathrm{CR}_{f,g}
$$
$$
\mathrm{ContentF1}_t = \frac{2\,\mathrm{CP}_t\,\mathrm{CR}_t}{\mathrm{CP}_t+\mathrm{CR}_t}
$$

**Citation 轴：** 设 $\mathcal{B}_t$ 为全部 binding,$\mathrm{pass}(b)= \mathrm{Observed}\land\mathrm{Bound}\land\mathrm{Supports}\land\mathrm{ScopeMatches}\land\mathrm{RoleOK}\land\mathrm{ValidURL}(b)$（伪造 URL 在此合取失败一次，见第 7 节）;$\mathcal{S}_t^{req}$ 为 citation-required statements（功能性/参数化句子按 LongCite–CiteEval 机制豁免或判 N/A)。
$$
\mathrm{CitP}_t=\frac{\#\{b:\mathrm{pass}(b)\}}{\#\mathcal{B}_t},
\qquad
\mathrm{CitR}_t=\frac{\#\{s\in\mathcal{S}_t^{req}: \exists\, \mathrm{pass}(b),\, b \hookrightarrow s\}}{\#\mathcal{S}_t^{req}},
\qquad
\mathrm{CitationF1}_t=\frac{2\,\mathrm{CitP}_t\,\mathrm{CitR}_t}{\mathrm{CitP}_t+\mathrm{CitR}_t}
$$

**Rubric 轴**：沿用 v1.3 §8 加权公式不变。

**聚合与层级（宏/微）**:L0 claim/binding/statement 级判定；L1 报告内——CP 为 mass 加权微平均，CR 组内微平均、组间宏平均，CitP/CitR 报告内微平均，Rubric 加权微平均；L2 报告级 $\mathrm{Truth}_t = \frac{1}{3}(\mathrm{ContentF1}+\mathrm{CitationF1}+\mathrm{Rubric})$;L3 harness 级为任务宏平均 $S_h = \frac{1}{|\mathcal{T}|}\sum_t \mathrm{Truth}_{h,t}$(三轴稿 §12.5 沿用）;L4 总榜为任务宏平均 + 以任务为聚类单元的 cluster bootstrap 95% CI。

**零分母约定表：**

| 量 | 空分母情形 | 约定 |
|---|---|---|
| CP | 报告无任何 material claim（空报告/空壳） | CP=0（可归责失败，沿用三轴稿 §12.4) |
| CP | 有 claim 但全部 unresolved/exempt | CP 未定义，Truth withheld,AdjudicationCoverage 暴露 |
| CR | 某 $(f,g)$ 组无 applicable units | 该组从宏平均剔除 |
| CR | 全部组空 | 任务 withheld(census_gap) |
| CitP | 无 binding 且 $\mathcal{S}_t^{req}\neq\varnothing$ | CitP 记 0（该引而不引）→ CitationF1=0 |
| CitP/CitR | $\mathcal{S}_t^{req}=\varnothing$（无引用要求，如纯分析任务） | Citation 轴 N/A,Truth 在两轴平均，N/A 状态随榜单公开 |
| Rubric | 无 item | 任务配置错误，withheld |
| fabricated_url_rate | 零引用 | rate 记 N/A，无旗标 |

### 9.2 正式榜单字段与诊断字段

**正式字段**:`harness_id, task_id, world_version, TEC_version, judge_snapshot_hash, ContentF1, CitationF1, Rubric, Truth, eligibility_status, fabricated_flag`。**诊断字段**（同榜发布，不进 Truth):CP、各组 CR、Fact verdict 分布、AdjudicationCoverage、CitP、CitR、binding 失败原因分布（unobserved/unsupported/wrong_binding/wrong_role/contradicted/supports_by_absence)、fabricated_url_count/rate、valid_url_ratio（原 Provenance 降级）、off_census_claim_mass、unresolved_rate、grounded_fact（方案 E3 诊断）、grounded_covered（沿用）。轴-N/A 与 withheld 必须出现在榜单行内，不得静默重归一化（三轴稿 §12.4)。

### 9.3 保守兼容方案

方案 A(8.1 节）与主方案并行计算一个完整周期，发布 crosswalk：两公式的任务级 Kendall τ、top-k 翻转率、逐 harness 可胜区域。若 τ ≥ 0.95 且无 harness 排名位移超过预注册幅度，主方案转正；否则按敏感性分析定位分歧轴。任何聚合规则变更提升 scorer major version 并重算全部历史输出（三轴稿 §12.2 第 6 条沿用）。

### 9.4 校准方案（Qwen judge 逐轴人工校准）

总原则：**总分接近不能当作轴等价**。论文 20 的实证：系统级 τ-b 0.40 而实例级仅 0.25;overall score 一致率 51.6% 接近 IAA 55.0%，但单指标一致率低得多（answer relevance 仅 34.5–35.2%)[20, 表 2–3, Findings 1–2]。judge 的总分与人类总分一致可能掩盖轴间系统性互换误差，因此校准必须 metric-wise，且人类标注指令与 judge 指令镜像（[20, R1])。

| 轴 | 抽样 | 人类协议 | 报告统计量及各自用途 |
|---|---|---|---|
| CP/Fact | ≥300 条 claim，按 verdict×materiality 分层 | 双人独立裁决 + 仲裁，同 judge 的 span 合同 | Accuracy：均衡标签总体一致；P/R/F1:false、conflicted 少数类（accuracy 在类别不平衡下虚高）;Cohen's κ：去机会一致的 judge–human 一致；Fleiss' κ：≥3 名人类时 IAA;cluster bootstrap 95% CI（按报告聚类） |
| CR/Completeness | (claim, unit) 候选对 + unit 覆盖判定各 ≥200 | 双人，映射成立与否 | 映射 P/R（映射器质量）;unit 级 accuracy + κ;CI |
| Citation | ≥300 binding，按失败类型分层（support/unsupported/wrong binding/wrong role/unobserved/contradicted) | 双人 + 仲裁；参照 ALCE §6(100 对、κ 0.698/0.525）与 LongCite §5.3（按 recall/precision 分开报 κ）的先例 | 每失败类型 P/R/F1；多类 κ;CI。statement 级 citation-required 判定单独校准（这是新判定器，文献中 LongCite κ 0.544 提示它是最难的一环） |
| Rubric | 全部 item 的 ≥20% 分层 | 双人，三档 ordinal；参照 DRB-II §4.3 的 ACC/F1 meta-eval 协议 | 二次加权 κ(ordinal 距离敏感）;Accuracy;CI |
| Provenance | 不需要人工校准 | 确定性规则 | snapshot/registry attestation 审计；fabricated 判定需 ≥2 人确认的申诉通道（误标为伪造的申诉） |

验收门槛预注册（参考 Qwen 扩展稿 §11.2 的既有门槛体系）：每轴 judge–human macro-F1、单报告轴分绝对差中位数、置换不一致率等，未通过则该轴降级 diagnostic,formal 榜不采用。标注者专业度按论文 20 的 R3 匹配：Citation 与 Fact 校准招深度专家，Rubric 中模拟一般用户判断的部分可用 near-expert [20, Finding 3]。

## 10. 需要做的实验

- **E1 映射器校准**:claim→unit 映射的人工审计集，测映射 P/R 与 κ；映射冻结前后的轴分稳定性。这是 Content F1 成立的全部前提。
- **E2 Citation recall 分母对照**:statement 级（推荐）vs unit 级（现状）vs ALCE 句级复刻，在人工标注集上比较与 human citation 判断的一致率；同时测 citation-required 判定器的 κ（预期最低，参照 LongCite κ 0.544 [07, §5.3])。
- **E3 聚合规则敏感性**：三轴 simplex 权重扫描 + linear/geometric/gated 对比，报 top-k 稳定率与两两翻转率（三轴稿 §12.2 已列程序，未执行）。
- **E4 伪造惩罚粒度 ablation**：报告级乘法 vs binding 级合取 vs 纯旗标，在注入伪造 URL 的对抗报告集上比较排名位移与可解释性。
- **E5 八极端案例回归套件**：把 8.2 节的推演固化为合成报告回归测试，纳入 v1.3 §11 最小回归套件。
- **E6 替代路线公平性**：构造用非 witness 路线覆盖相同 units 的报告对，验证检索配额与映射不偏向 witness URL（前提"不能把构题 witness graph 当作唯一合法研究路线"的可执行检验）。
- **E7 负命题通道**：构造含负命题 claim 的报告集，测 NLI 判定分布、`supports_by_absence` 通道的人类一致率；校不准则按 N/A 处理并公开限制。
- **E8 逐轴校准基线**：按 9.4 节建立四轴人类校准集，产出首版 κ/CI 基线与预注册门槛的实测对照。

## 11. 仍不能声称的内容

1. **不能声称文献共识支持 DRA 的四轴划分或等权平均。** 没有任何一篇被审论文使用 Fact/Evidence/Completeness/Rubric 这一划分；最接近的 ScholarQA-CS2 四指标是简单平均但构念不同 [20, §3]。等权的依据目前只是"没有证据证明任何一轴值固定倍数"（三轴稿 §12.2)，这是无证据默认，不是文献结论。
2. **不能声称"大多数类似工作采用 precision–recall 思路"**——严格口径 45%,deep research 子领域仅约 17%（第 3 节）。对外表述应改为"claim 级事实性与引用评估文献中 P/R–F1 是主流"并引用 05–07、09、11、12、14、18。
3. **不能声称任何聚合规则被验证优于其他。** 20 篇中没有一篇比较过报告级聚合规则；geometric vs linear 的选择只能来自 DRA 自己的开发集校准（E3)，校准前两者都是候选。
4. **不能声称 Qwen3-8B 在各轴上等准确。** 文献显示同一 judge 在不同指标上与人类的一致率差异巨大（ALCE κ 0.698 vs 0.525 [06, §6];DRSE answer relevance 34.5% vs citation recall 63.3% [20, 表 3–4])。DRA 尚无逐轴校准数据。
5. **不能声称 TEC 是完备 universe。** census_gap 状态的存在即为承认 [v1.3 §5];Content F1 的 recall 是相对"已认证可发现单元"的覆盖，不是相对"世界全部相关事实"——对外表述必须保留这个限定（三轴稿 §5.5 的诚实定义沿用）。
6. **不能声称负命题、纯分析与不可裁决 claim 被测量。** 它们目前只能中性化（案例 8)；负命题在 Citation 轴还存在系统性误伤风险，在 E7 完成前这是一个已知的测量盲区。
7. **不能声称消除重复计分后排名不变。** 方案 B 相对 v1.3 改变了伪造惩罚粒度、Evidence 分母与 Completeness 门控，harness 排名可能位移——这正是需要 crosswalk 周期（9.3 节）而非直接切换的原因。
8. **不能声称 K 类超参问题已被 TEC 消解。** SAFE 的 K、VeriScore 的域中位数 K、FaStFact 的 gold K′ [11, §5;12, §2.4;14, §4.4.2] 都是在没有 gold universe 时的替代物；DRA 用 TEC 替换 K 是设计进步，但 TEC 的组间宏平均对 unit 计数分布的敏感性（小组权重过大）尚未实测，E3 之前不能声称宏平均层级无偏。

---

**评审依据说明**：第 2–3 节的逐篇判定均可在 `text/*.txt` 中按所引章节定位，并可回溯至 `papers/` 对应 PDF；第 4–9 节对 v1.3 的引用以 `DRA_FOUR_AXIS_SCORING_V1_3_SPEC.md` 章节号为准。8.2 节数值为公式推演假设，非实测结果。
