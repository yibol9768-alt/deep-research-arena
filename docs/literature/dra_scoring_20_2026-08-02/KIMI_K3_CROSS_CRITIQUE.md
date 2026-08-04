以下为交叉审查正文（只读完成，未修改任何文件）。引用格式：`[编号, 章节]` 对应 `PAPER_SCORING_EXTRACTION.md` 的论文编号与该文档所记 PDF 章节位置；`GPT §n` 指 `GPT56_INITIAL_SCORING_PROPOSAL.md` 第 n 节；`评审 §n` 指同目录 `KIMI_K3_INDEPENDENT_REVIEW.md`。

---

# 对 GPT-5.6 初始评分方案的交叉审查

## 1. 该方案最强的三点

**（a）合取下沉到 claim/binding 层，取代报告级乘法。** GPT §2 的反例（Fact 与 Provenance 各 0.9 时联合通过是 8 还是 9，报告级乘法都给 0.81）与文献审计 §4 的最小反例完全一致，这是该方案相对 v1.3 的实质进步，方向有文献支持：claim 级判定是 FActScore [10]、SAFE [11]、RAGChecker [18, §3.3.1] 的共同单元选择。

**（b）recall 分母是看报告前冻结的、路线无关的必要研究单元。** 这使 DRA 避开了 SAFE/VeriScore 的超参 K [11, §5; 12, §2.4]，对应 FaStFact 的 gold K′ [14, §4.4.2] 但语义化为单元集合；DRA 的冻结世界恰好是少数满足"可枚举 proposition universe"前提的场景 [18 的成立条件，见审计 §1 与 §5 条件 3]。维度内平均再维度间平均防止易拆维度支配，方向正确。

**（c）unresolved/census_gap 的区间化处理。** 不静默算错、不删分母、发布 Resolution Rate 与 F1 上下界（GPT §7），比 FActScore 的短输出惩罚 [10]、SAFE 排除 irrelevant [11, §5 脚注 7] 更诚实，也落实了审计 §5 条件 6。附带优点：伪造 URL 不做数值清零而做 clean 榜分层（GPT §5），避免"一次 URL 错误把强报告变成空报告"——这一点我同意其动机，但机制不充分，见第 5 节。

## 2. P 与 R 是否真的共享 matching universe，F1 是否正当

**结论：不共享，严格意义的 F1 不成立；可通过去门控 + 映射冻结修正后弱成立。**

严格 P/R 的前提是两侧能匹配到同一 canonical proposition universe——RAGChecker 之所以正当，是因为 response claims 与 gold claims 映射到同一空间 [18, §3.3.1；审计 §1]。GPT 方案中：

- P 侧分母是**报告自己的** claim 集合 \(C_t\)（输出侧，内容随系统而变）；
- R 侧分母是**任务侧**冻结单元 \(U_{t,d}\)（目标侧，与报告无关）。

两者是不同空间，靠一个未说明的语义对应关系连接。审计 §1 已明确限定："只有在两者共享同一个可枚举命题空间时，F1 才是严格成立的"。GPT 方案把 \(H(P_t,R_t)\) 命名为 F1，但它实际是"报告可信率"与"任务研究完成率"两个不同构念的调和平均——类似于对 RAGAS 的 Faithfulness 与 Context Recall 取 F1 [17]，而 RAGAS 自己不这么做。

**修正建议：**

1. **匹配机制化**：补一个冻结的 claim→unit 映射 \(M: C_t \to 2^{U}\)（v1.3 §2 第 7 步已有雏形），输出 (claim_id, unit_id, relation, span)，随 claim ledger 冻结哈希。有了 \(M\)，两侧才可说"通过映射共享 universe"，F1 才从修辞变成近似严格。
2. **去除双重证据门控**（这是更严重的问题，详见第 8 节）：\(P\) 侧 \(g_c=f_ce_c\) 门控了证据，\(R\) 侧 \(z_u\) 又要求"关键前提有本次观察证据"（GPT §3.4）。两个门控语义重叠但不相同，使主分两侧相关性被人为抬高，F1 的可解释性进一步受损。修正：Content 侧只门控事实（recall 侧门控 \(v=true\)，不门控引用），证据完全交给独立的 Citation F1 [审计 §3.3 的第三组分母]。
3. **命名**：若保留证据门控，应改名（如 Grounded Coverage Score）并在文档中声明它不是经典 P/R；若按建议 2 去门控，可保留 Content F1 名称，但对外表述必须限定"recall 是相对已认证可发现单元的覆盖，不是相对世界全部相关事实"[审计 §5 条件与三轴稿 §5.5 的诚实定义]。

## 3. \(e_c=A_c\cdot\sum b/|J_c|\) 的问题、反例与替代定义

该公式有四个可指证的缺陷：

**（i）Supporting 谓词粒度未定义，误罚必要的多来源联合证据。** 复合 claim"产品 A 比 B 便宜且续航更长"需要 \(j_1\) 支持价格、\(j_2\) 支持续航。若 Supporting 按"支持整个 claim"判定，则每条单独 \(b=0\)，而联合支持 \(A_c=1\)，于是 \(e_c=1\cdot 0/2=0\)——**必要的联合证据得到零分**。若 Supporting 按"支持 claim 的某个方面"判定，则 \(b\) 与 \(A_c\) 冗余。ALiiCE 的顺序是先判"claim 已被引用集合充分支持"，再检查单条 citation 的必要性 [09, §3.3]；GPT 公式把两步揉成一个连乘，粒度含糊。

**（ii）重复惩罚。** \(A_c=0\)（联合不充分）时 \(e_c=0\)，即使每条引用单独合格；同时 `unsupported_citation` 已在 Citation Precision 诊断下降（GPT §5 表自己写明）。同一"支持不足"在 \(g_c\) 与 Citation P 两处计分。若证据还经 \(z_u\) 门控进 recall（第 8 节），最多计三次。

**（iii）奖励少引、且 spam 惩罚可被摊薄策略规避。** 单引用 claim 若该引用合格则 \(e_c=1\)；三引用中一条坏则 \(e_c=A\cdot 2/3\)。引用越少越安全——这与方案自己担心的"少引"激励相反方向的事实并存：把 \(k\) 条无关真引用集中到少数 claim 上（那些 claim \(e_c\approx 0\)），比分散到所有 claim（全体 \(e_c\) 微降）总分更高，**分配策略本身成为博弈自由度**。防 spam 的目标达到了一半：平均确实罚 spam，但罚的是分布而非总量。

**（iv）"真但无引用即零分"的极端。** 全凭参数知识答对的 claim，\(J_c=\varnothing\)，\(\sum b/|J_c|\) 无定义；按任何合理约定（记 0）都会让"内容正确但没证明"与"内容错误"同分，丢失 DRA 相对普通事实性基准的核心区分度 [评审 §6 方案 E3 的缺点]。

**替代定义（存在性门控）：**

\[
e_c=\mathbb{1}\big[\mathrm{exempt}(c)\ \lor\ \big(A_c=1\ \land\ \exists j\in J_c:\ b_{c,j}=1\big)\big]
\]

claim 层只要求"联合充分且至少一条合格 binding"；"引用集合中有多大比例合格"完全交给 Citation Precision [审计 §3.3 的 \(P_{cite}\)]，不在 claim 层重复。这正是 ALiiCE 的"先充分性、后必要性"结构 [09]。该替代消除了 (i)(ii)(iii)，但 (iv) 仍在——这是所有 claim 级证据门控的固有代价，根治办法是把证据门控整体移出 Content 轴（第 8 节）。

## 4. \(e_c=1\) 豁免的"包装成推理"漏洞与机械化区分

风险真实存在：模型可以把外部事实写成"由公开规格可推得……""显然……"来规避证据门控。citation-required 必须是 **claim 命题内容的属性，而非报告措辞的属性**。机械化方案：

1. **盲化判定**：豁免判定器只看抽出的 claim 命题本身，不展示其报告上下文与句式，使"包装"在判定界面不可见。
2. **默认 required、豁免需正证据**：凡含具名实体、数量、日期、单位、可证伪外部谓词的 claim 默认 citation-required；豁免仅限可枚举类别——纯数学/逻辑推导、用户给定约束的直接复述、报告自指元陈述。功能性句子豁免有 LongCite 先例 [07, §3.3.2]，parametric/response 归因判 N/A 有 CiteEval 的更系统机制 [08, §2.3]；VeriScore 的 eligibility 筛选在抽取阶段完成 [12, §2.4] 也支持"先筛后评"。
3. **独立校准**：citation-required 判定器必须单独做人工一致率——LongCite 的 κ 仅 0.544 [07, §5.3] 提示这是全部判定中最难的一环，不能与 fact 判定共用校准集。
4. **对抗回归**：构造"已知外部事实改写为推理句式"的注入集，监测豁免率漂移（第 10 节测试 T3）。

GPT 方案 §3.1 只列举了什么进入/不进入分母，没有给出判定器、盲化与校准要求，这是候选方案目前最薄的环节之一。

## 5. `fabricated_url`：clean 榜排除是否足够

**不足够，但数值门控同样错误；正确解是二者的结构化组合。**

GPT §5 的规则（数值照算 + 旗标 + clean 榜排除）有一个未解决的歧义：**哪个榜是主榜？** 若 clean 榜为主榜，含一个伪造 URL 的强报告从主榜消失，比数值清零更严厉——连诊断曝光都没了；若数值榜为主榜，伪造在排名上无任何后果，规则形同虚设。双榜制把"诚信事件如何影响排名"这个核心决定推给了读者。

数值门控（按比例扣分或清零）的问题在评审 §4.6 已分析：报告级乘法惩罚**伪造密度而非伪造危害**——100 引用中 1 个伪造只稀释 1%，2 引用中 1 个伪造稀释 50%，而两者危害可完全相同；且随 harness 引用习惯系统性偏移，违反"12 个 harness 同一尺子"前提。

**可解释性比较与推荐**：伪造是**诚信事件，不是比例事件**（类比学术不端不按比例扣内容分）。推荐三层结构 [对应评审 §7 的 P2+P3 组合]：

1. **binding 级合取**：伪造 URL 的 binding 必然无有效观察，其支撑的 claim/unit 失格——功能后果自动成比例，且只计一次。文献支持：OpenScholar 对幻觉引用在 citation 指标内计一次 [05, §3.2]；ReportBench 区分 statement 与 citation hallucination 各落对应指标一次 [04, §4]。
2. **阈值资格**：确认伪造数 ≥ 预注册阈值（建议 1）→ formal 成绩 withheld，诊断分照发。阈值语义比武断的连续扣分干净得多。
3. **榜单旗标** `fabricated_url_count/rate` 公开，作为申诉与复审计数的锚点 [DeepFact 的 audit-then-score 治理，15]。

GPT 的 clean 榜排除是第 2 层的弱形式（无明确阈值、无 withheld 语义），可吸收进该结构。

## 6. 必要研究单元是否回到昂贵逐题 rubric

**风险真实，GPT §9 自己也承认这是最大风险。** DRB-II 的先例是 9,430 个专家 rubric 加大量人工审核 [02]，审计已注明这不符合 DRA 的低成本目标 [审计 §2.1 对 02 的启示]。降本与降主观性的可行路径：

1. **从构题副产物半自动生成**：必要单元不应由人逐题撰写，而应从 query candidates、TEC 与冻结索引中已有的 witness evidence graph 抽取——研究维度（比较、机制、社区证据、预算、推荐）本质是任务原型的结构槽位，可模板化。
2. **路线无关性机械化**：单元描述禁止出现具体 URL、品牌或措辞偏好，只保留命题模板；已知 URL 降级为 answerability witness [审计 §5 条件 2、条件 7]。这可以由确定性 lint 检查（描述中含 URL 即拒绝）保证。
3. **人工只做二元审查**：每单元只审两个判定——*必要性*（删除该单元任务是否仍完整？仍完整则非必要，即"删除测试"）与*可回答性*（冻结索引中是否存在任一路线可完成？）。每题单元控制在每维度 3–8 个，人工量约每题十几次二元判定，类似 ARES 用少量人工标签校正自动估计的 PPI 思路 [19, §3.2–3.3]，而非 DRB-II 的万级标注。
4. **版本治理**：census_gap 与新增真实 claim 走冻结的申诉与版本化修订通道 [15 DeepFact]，不把初始答案表当绝对真理 [审计 §5 对 15 的启示]。
5. **主观性量入为出**：census 质量本身纳入 falsification 测试（第 10 节 T1/T2），用删除通过率与替代路线一致性量化"是否混入写作者偏好"，而不是靠流程声明。

## 7. unresolved/census_gap 区间是否过宽或可被利用

区间方法本身正确（符合审计 §5 条件 6），但有两个可操作漏洞：

**（a）点估计选取即博弈点。** 区间 \([P^{low},P^{high}]\) 发布时必须预注册排名用哪个点。按 \(P^{high}\) 排名会鼓励评分器把疑难 claim 搁置为 unresolved（搁置不扣分、上限不变）；按 \(P^{low}\) 排名则评分器不敢用 unresolved，被迫武断裁决，损害判定质量。建议：排名用区间中点或下界，同时 Resolution Rate 作为**并列资格指标**（低于阈值即 withheld，而非只是"同时展示"）。GPT §7 写了"可裁决率过低时暂缓正式分"但没有阈值与点估计约定，规则不完整。

**（b）区间宽度的信息量坍缩。** 未裁决比例 50% 时区间宽 0.5，跨系统区间大面积重叠，排名不可分辨——此时"展示区间"不等于"可以排名"。必须 withheld 的情形应至少包括：

1. Resolution Rate 低于预注册阈值（建议 ≥0.8）；
2. 某研究维度的单元全部落入 census_gap，该维度 \(R_{t,d}\) 无定义；
3. F1 区间宽度超过阈值（如 >0.15）或候选系统间区间重叠使 top-k 不可分辨（可用区间端点排名的 Kendall τ 稳定性量化，见第 10 节 T5）；
4. scorer-side failure（检索失败、judge 故障、ledger 不完整）——沿用 v1.3 §5 的 withhold 语义。

另外必须守住 FaStFact 的警告：不能因低置信度跳过 claim，否则静默改变分母 [14，审计 §2.3 对 14 的启示]——unresolved 留在分母内计入区间是对的，跳过才是错。

## 8. 与现有四轴 Evidence 的重复计分及无重复最终结构

**会重复，且是双重重复。** 现有 Evidence 轴即 Citation P/R/F1 [审计 §3.3]。GPT 方案中证据质量出现在三处：

1. \(g_c=f_ce_c\)：\(e_c\) 由 binding 合取构成（precision 侧）；
2. \(z_u\)：单元通过要求"关键前提有本次观察证据"（recall 侧，GPT §3.4）；
3. §8 诊断面板的 Evidence：Citation P/R/F1（仅诊断）。

Citation F1 不进主分，所以 (3) 不算分；但 (1)(2) 同时进主分——**同一次引用失败在 F1 的两个输入里各计一次**，而 F1 对两者取调和，惩罚被进一步放大。这正是评审 §4.2 反例 B（Evidence 与 Completeness 分母重叠）在候选方案里的换形再现。

**无重复计分的最终结构**（每个失败类型恰好落在一个轴上）：

- **Content 轴（不门控引用）**：
  \(CP_t=\frac{1}{|C_t|}\sum_c f_c\)（只门控事实）；
  \(CR_t=\) 维度宏平均的 true-covered 单元比例，\(z_u=\mathbb{1}[\exists c:\ v(c)=true \land u\in M(c)]\)（门控真实、不门控证据）；
  \(ContentF1_t=H(CP_t,CR_t)\)。
- **Citation 轴（承担全部证据/观察/绑定计分）**：
  \(CitP_t=\#\{pass\}/\#\mathcal{B}\)，\(pass=\) RegistryValid ∧ LegalDiscovery ∧ Observed ∧ LocalBinding ∧ Supporting ∧ RoleAppropriate（伪造 URL 在此失败一次）；
  \(CitR_t\) 分母为报告的 citation-required statements（ALCE 句级 [06, §3.3]、LongCite 豁免机制 [07, §3.3.2]）；
  \(CitationF1_t=H(CitP_t,CitR_t)\)。
- **聚合**：\(Truth_t=\frac{1}{3}(ContentF1_t+CitationF1_t+Rubric_t)\)；Provenance 资格化（旗标 + 阈值 withheld），不再报告级相乘。

关键原则：**观察证据（Observed）属于 Citation 轴而非 Content 轴**。"全凭参数知识答对、零引用"的报告应 Content 分照给、Citation 分清零——内容对不是错，没证明是引用系统的问题 [评审 §8.2 案例 3、案例 5 的推演]。Content recall 门控真实性的先例是 RAGChecker 的 recall 要求 response 蕴含 gold claim [18, §3.3.1]；没有任何文献支持"错误内容计入覆盖"（消除 v1.3 反例 C）。

## 9. 修订后的公式

**最小修补公式**（保留 GPT 单 F1 形态，改动最小）：

\[
g_c=f_c\cdot\mathbb{1}\big[\mathrm{exempt}(c)\lor\big(A_c\land\exists j:\,b_{c,j}=1\big)\big],\qquad
P_t=\tfrac{1}{|C_t|}\textstyle\sum_c g_c
\]

\[
z_u=\mathbb{1}\big[\exists c:\ v(c)=true\land u\in M(c)\big],\qquad
R_t=\tfrac{1}{|D_t|}\textstyle\sum_d R_{t,d},\qquad
DRA\text{-}GF1_t=H(P_t,R_t)
\]

即：平均改存在性门控（修第 3 节），recall 侧去掉观察证据门控、改为真实性门控（修第 8 节半面），Citation F1 留作并列诊断。残留缺陷：真但无引用的 claim 仍被 \(g_c\) 灭分（第 3 节 (iv)），需文档明示并接受。

**保守兼容公式**（不动轴与管道，可 crosswalk）：

\[
Truth_t=Provenance'_t\times\frac{Fact_t+Evidence_t+Completeness'_t+Rubric_t}{4}
\]

其中：\(Provenance'\) 移除伪造 URL 比例（改 binding 级失败 + 旗标 + 阈值资格），只测 canonicalization/registry/snapshot；\(Completeness'\) 把 `grounded_covered`（true-covered）升为主分；补齐全部零分母约定；linear/geometric 用开发集校准选定一个。

**主推荐**：第 8 节的双 F1 结构 \(Truth=\frac{1}{3}(ContentF1+CitationF1+Rubric)\)。GPT 方案若接受第 2、3、8 节的修正，其单 F1 即退化为该结构的 Content 分量，Citation F1 由诊断升轴——两方案的差异仅剩"引用轴是否进主分"。

## 10. 升级为正式主榜前必须通过的五个 falsification tests

**T1 冻结与替代路线公平性。** \(U_{t,d}\) 与映射 \(M\) 在接触任何被测报告前冻结哈希；构造用非 witness 真实注册来源覆盖相同单元的报告对，其 \(R_t\) 与 witness 路线差异须 ≤ 预注册 ε。替代路线被系统性压低 ⇒ recall 分母暗中绑定构题路线，方案作废 [审计 §5 条件 7；没有任何被审论文把构题路线当唯一合法路线，11 §4、12 §2 的检索器完全开放]。

**T2 census 必要性与扰动稳定性。** 随机抽取单元做删除测试：独立审查判定删除后任务是否仍完整，非必要单元比例超阈值 ⇒ census 混入写作者偏好，\(R_t\) 无效；同义改写单元描述后 \(z_u\) 判定翻转率须低于阈值。直接检验 GPT §9 自列的"确实必要而非写作者偏好"。

**T3 豁免包装攻击。** 将已知 citation-required 事实批量改写为推理/显然句式注入报告，豁免判定器的 exemption rate 漂移超阈值 ⇒ \(e_c=1\) 可被规避，须改为默认 required 重测（第 4 节的对抗回归）。

**T4 极端案例方向性回归。** 六类合成报告的相对排序必须符合预注册期望：短全真 < 全面研究；堆砌真事实被高阶维度缺失压下；广覆盖零引用只伤 Citation 不伤 Content；多引用错绑只伤 Citation P；单伪造 URL 触发 withheld 而非数值清零；citation spam（每 claim 挂 k 条无关真引用）不被摊薄策略豁免。任一方向性错误即否决 [对应评审 §8.2 推演，固化为回归套件]。

**T5 逐轴校准与区间排名稳定性。** 四轴判定（\(f_c\)、\(b_{c,j}\) 含失败类型细分、\(z_u\)/映射 \(M\)、citation-required）分别与人工校准集比较，macro-F1 与 κ 达预注册门槛——**总分接近不能证明轴等价** [20，审计 §2.4：系统级 τ-b 0.40 而实例级 0.25；单指标一致率远低于系统级]；难度基准参照 ALCE κ 0.698/0.525 [06, §6]、LongCite κ 0.544 [07, §5.3]。同时把全部 unresolved 分别按最有利/最不利裁决，区间两端排名的 Kendall τ 须 ≥ 阈值，否则区间过宽，正式分 withheld（第 7 节）。

五项任一不通过，\(DRA\text{-}GF1\) 不得升级为正式主榜，维持候选诊断地位——这与 GPT §9 自己的保守立场一致，本审查将其具体化为可执行门槛。

---

**总体裁决**：该方案在 claim 层合取、冻结 census、区间化处理三点上方向正确且有文献支持；但 \(e_c\) 的平均形式、证据在 \(g_c\) 与 \(z_u\) 的双重门控、豁免判定缺乏机械化、citation-required 校准缺失、clean 榜语义不完整五处必须在转正前修正。按第 8–9 节结构修订后，它与独立评审的双 F1 方案收敛，可作为同一候选族进入 crosswalk 周期。
