# DRA V3 评分体系设计调研报告

日期:2026-07-17
范围:只讨论评分体系(Report Quality 构念、Grounded 定义、聚合方式、Judge 协议、rubric 构造、验证方法)。Query 生成不在本文范围。
方法:4 路并行精确提取(DR 基准评分公式 / 引用指标形式化定义 / judge 协议 / 聚合与测量理论),叠加 2026-07-17 早前完成的四路面上调研(见 `DRA_V3_LITERATURE_SOLUTIONS_2026-07-17.md`)。所有关键论文的公式与位置均从 arXiv 原文(HTML/PDF)或官方代码提取;凡未能钉到具体章节/公式的,标注 LOCATION-UNVERIFIED;凡文献沉默、属于我们自己推理的,标注【推断】。
证据缓存:提取用的 PDF/文本在 scratchpad(`drb.pdf`、`m2w2.pdf`、`deer.pdf`、`oecd_handbook.txt`、`hdr_technotes.txt`、`wmt07.txt`、`papers/`)。OpenReview 审稿原文被 Cloudflare 拦截未取到,相关 forum ID 已记录备查(Mind2Web 2 = AUaW6DS9si,BrowseComp-Plus = jjIKGiGqOo,ResearchRubrics = ErnvfmSX0P)。

---

# A. Executive Summary

1. **不要在报告级把两个聚合分相乘。** 对 12 个 DR/报告类基准逐一核实:没有任何一个使用 `Quality × Grounded` 式的报告级乘积。门控行为只存在于**条目级**:Mind2Web 2 的 gate-then-average(critical 叶失败清零父节点,§3.3 递归公式)与 LiveDRBench 的 claim 级清零(Eq 1)。TruthfulQA 的头名指标是**逐题合取**("% true AND informative",Fig 4 原文),不是聚合率乘积——引它为报告级乘法背书是审稿人能抓住的误读。唯一的报告级乘积活先例是 CARLA 驾驶榜(完成度 × 违规惩罚),但它乘的是机械计数惩罚,不是第二个 judge 打的质量聚合分。
2. **推荐主分:义务级证据门控覆盖率(Grounded Obligation Coverage,GC)。** 每条 query 派生义务,内容满足判定 `C_j` 与证据门 `E_j` 在**义务级**合取,再加权平均。这个数字有明确测量含义:"该报告有真实证据地完成了多少必要研究要求",是一个单一概率【推断:文献对"乘积无单位、逐条合取有概率语义"这一论证沉默,需自行论证】。它与迁移文档的 `z_j = max_r min_p g_{jrp}` 完全兼容。
3. **报告级相乘的三重反对证据:** (a) 无先例(上文);(b) 重复计分是实证事实——WMT 2007 元评测原文承认人类评委分不开 fluency 与 adequacy("the distinction might be false",随后 WMT 废除双维度),Style-over-Substance(2307.03025)实证 LLM judge 给含事实错误的答案打分高于短答案,即 judged ReportQuality 已含 grounding 光环,再乘 Grounded 等于不受控权重的二次计分;(c) 乘法不消除价值判断而是藏起它(HDI 之争:HDR 2010 技术注释 vs Ravallion 2012),`Grounded^{1.5}` 的指数是无出处的隐藏权重(OECD 手册 §1.6:"权重本质上是价值判断",Step 7 要求敏感性分析)。
4. **质量维度不进主分、不参与相乘,作为独立面板。** 分析/综合、冲突与不确定性处理、建议可执行性、呈现质量四个轴,LLM judge 逐维打分,单独列示(HELM 的多指标立场;但注意 HELM 2025 年也放弃了 population-dependent 的 mean win rate 改用绝对均值——支持 pointwise 绝对分)。
5. **Judge 协议:pointwise 逐条 rubric 判定,不用 pairwise 做主分。** WildBench 实证 checklist-pointwise 与 Arena Elo 相关 0.955(与 anchored pairwise 差 0.03 以内);COLM 2025(2504.14716)实证对生成方定向风格操纵,pairwise 翻转 ~35% 而绝对分仅 ~9%;单锚点 pairwise 换锚后仅 20% 模型排名稳定(2502.14074)。判定必须逐条不批量(RuVerBench:批量判长输出掉两位数精度)、附机器可核验的摘录引文(RULERS)、judge 快照+prompt+rubric 全部哈希进版本号(GPT-4 同名三个月内 84%→51%,2307.09009;DeepResearch Bench 自己已被迫因 Gemini-2.5-Pro 退役而迁移 judge 并挂双榜——活教材)。
6. **确定性/语义的分工线:** 在册、已观察、HTTP 200、citation position、哈希、来源角色(registry 预标注)全部确定性;"页面是否支持 claim"给 judge(有源文本时 ~80-90% 上限:AttributionBench ~80% F1;无源文本时完全不可用);"义务是否被满足""结论是否守约"给 judge 但配校准集。
7. **Grounded 的分母 = rubric 义务(加权、条件适用),不是全部 claim。** 报告级 DR 基准的通行做法是双分母(全部可验证 claim 做 completeness、已引 claim 做 correctness,DeepResearchGym/ResearcherBench/DEER),rubric 门控型(Mind2Web 2)用任务关键义务。DRA 主分取义务分母,claim 级两个比率降为诊断。纯分析/推理/观点陈述豁免引用(CiteEval 三豁免、VeriScore、LongCite 功能句豁免:文献一致,没有任何基准要求观点带引用),但决定性结论必须建立在 grounded 前提上(义务级检查)。
8. **验证故事已有全套先例可循:** judge 对人一致率对照人-人区间(HealthBench)、逐条金标 F1(PaperBench JudgeEval)、FRR/FAR 分层认证(三分法则,每层 ~300 条 0 错误 → ≤1% @95%)、PPI 无偏榜单分带置信区间(ARES,金标 ≥150/维度)、置换/对抗/风格扰动测试、权重敏感性分析(OECD Step 7)。合法替代路线层的误拒率认证无先例,是可声称贡献。

---

# B. 文献方法对照表

## B1. DR / 长篇报告基准(评分公式均已从原文提取)

| 基准 | 评测对象 | 维度 | 评分原子 | point/pair | LLM judge | grounding 测量 | 聚合公式(位置) | 人工校准 | 已知限制 |
|---|---|---|---|---|---|---|---|---|---|
| [DeepResearch Bench](https://arxiv.org/abs/2506.11763) | DR 报告 | RACE 四维(全面/深度/循令/可读)+ FACT | per-criterion 分(对目标与参考报告同时打)| 混合:参考对照式 pointwise | Gemini-2.5-Pro(已被迫迁 GPT-5.5,双榜过渡)| FACT:statement-URL 对去重后二值支持判定;C.Acc=支持/全部,E.Cit=每题支持对数 | 加权和后**对参考归一** S=S_tgt/(S_tgt+S_ref)(§3.1 Eq 3);FACT 独立列(App E Eq 4-6) | 50 题×4 系统×3 专家;PAR 71.33,人际 68.44(Table 2);FACT 与人 96%/92% | 自认"只看排名与比例差";依赖参考报告 |
| [DeepResearchGym](https://arxiv.org/abs/2505.19253) | DR 报告(冻结语料) | KPR/KPC/引用 P/R/清晰/洞见 | key point;claim | pointwise | gpt-4.1-mini,prompt App C | 引用 recall=有引 claim 占比;precision=1/0.5/0 三档(§3.2.2);无引用系统 Faithfulness=0(§4.2) | **纯面板,无合成分** | 210 题双盲 3 标注,κ:KPR .72,引用 .86,清晰 .89(§4.4) | key point 来自用户点击文档,完备性不可判 |
| [RAVine](https://arxiv.org/abs/2507.16725) | agentic search 报告(冻结) | 完整度/引用/搜索/抓取/成本 | nugget(vital/okay);citation-bounded block | pointwise | Gemini-2.5-Flash | block 级引用 P/R(Eq 6);nugget 多源聚类抗路线绑定 | 完整度=(Σs_v+0.5Σs_o)/(N_v+0.5N_o)(Eq 5);**纯面板** | 未报告 | 无人工校准数字 |
| [Mind2Web 2](https://arxiv.org/abs/2506.21506) | agentic search 答案 | 正确性+归因,单树 | rubric 树叶(二值),avg 34 叶/题 | pointwise | 每题专用 judge 脚本 + o4-mini | 归因叶 `verify_by_url`,**强制 critical**(App D.1) | **gate-then-average**(§3.3 递归式):critical 失败→父节点 0;否则非 critical 均值 | 720 叶人工复核仅 7 真错(§4.4) | 每题判官脚本数小时人工,不可扩展 |
| [HealthBench](https://arxiv.org/abs/2505.08775) | 医疗对话回复 | 单分 + 主题/轴分解 | criterion(-10..10 分),中位 11/题 | pointwise | GPT-4.1 | 无引用概念 | 得分=命中分/最大正分,均值后 clip [0,1](§2) | 医生金标 60,896 对,MF1 .709 落人际带内(Table 5) | 86% 单人撰写 criteria 未复核 |
| [DRB-II](https://arxiv.org/abs/2601.08536) | DR 报告 | 信息召回/分析/呈现 | 二值 rubric(~71/题) | pointwise | Gemini-2.5-Pro(50 条/批) | 无引用支持验证(§2.1 自辩) | 通过率,三维均值=TotalScore(§3.1.2) | 10 报告金标 F1 89.57(Table 4-5) | rubric 锚定单篇专家文章=参考路线绑定 |
| [LiveDRBench](https://arxiv.org/abs/2508.04183) | DR 关键 claim 集 | claim P/R/F1 | claim(嵌套子 claim) | pointwise | GPT-4o | 部分类目要求给源链接,无自动支持验证 | claim 级门控(父错全零,Eq 1),F1 头名 | 人工全量复核 Table 11 | 无 IAA;live 环境 |
| [ProfBench](https://arxiv.org/abs/2510.18941) | 专业报告 | 加权 criterion 满足率 | criterion(权 1-4),15-60/题 | pointwise | 多 judge 评测,报 MF1−Bias | 无 | Σw·1[met]/Σw(§5,叙述式) | 38 专业人士,Fleiss κ .912(§4.1) | 无环境 |
| [DR3-Eval](https://arxiv.org/abs/2604.14683) | DR 报告(每题沙箱) | 6 维 | insight/必需文档/claim-源对/checklist | pointwise | GPT-5.1 | **Citation Coverage=引用的必需文档/全部必需文档(Eq 3)=金标路线绑定** | 六指标分列 + 无权 Avg(Table 2) | 50 报告×4 专家 r .78/ρ .73(Table 4) | 反向构造刻意单一解法路径 |
| [ResearchQA](https://arxiv.org/abs/2509.00496) | 学术长答案 | rubric 覆盖 + Elo | rubric 项(0-4),~7.5/题 | 双轨 | gpt-4.1-mini | 仅 rubric 内引用要求项(8.3%) | Coverage%=均分/4;Elo 副榜(§4.1) | 项级 Pearson .63;IAA .73(Table 2) | 不验证答案引用 |
| [DEER](https://arxiv.org/abs/2512.17776) | 专家报告 | 7 维/25 子维/101 项 | rubric 项(1-10/N/A)+ 分型 claim(A-F) | pointwise | GPT-5.2 + GPT-5-mini | Claim Factuality=支持的A-C/全部A-C;Citation Support;Reference Reliability/Reproducibility/Diversity(App G.4) | 逐层均值(App D.4 Eq 2-5);验证指标住在 7 维中的 2 维内,**不相乘** | Pearson .73,人际 .81(Table 3);α .55 | 总分合成式未给出(LOCATION-UNVERIFIED) |
| [ReportBench](https://arxiv.org/abs/2508.15804) | 综述报告 | 引文重叠 + 陈述忠实 | 引文条目;陈述 | pointwise | gpt-4o + 双 Gemini 联网核查 | Reference P/R 对金标综述书目=**参考书目绑定**;Match Rate;非引用陈述 6 票多数核查 | **纯面板** | 无指标级人工验证 | 惩罚合法的非综述引文 |
| [LiveResearchBench](https://arxiv.org/abs/2510.14240) | DR 报告(live) | 4 协议多维 | claim;claim-URL 对 | pointwise | agentic judge | Citation Traceability(completeness,扣分制)与 Citation Accuracy(correctness,E1 不可达/E2 无关/E3 不支持错误计数,App E) | 面板 | 未提取 | live 定义上不可复现 |
| [ResearcherBench](https://arxiv.org/abs/2507.16280) | DR 报告 | Faithfulness + Groundedness | claim | pointwise | judge + Jina 取页 | **Faithfulness=支持的已引 claim/已引 claim;Groundedness=有引 claim/全部 claim(§4.2.1 Eq 2-3)**——双分母命名的最干净版本 | 面板 | 未提取 | live |

## B2. 引用/归因指标(形式化定义,位置见提取记录)

| 工作 | 单位 | 分母 | 无引用陈述 | 部分支持 | 矛盾 | 来源质量 |
|---|---|---|---|---|---|---|
| [ALCE](https://arxiv.org/abs/2305.14627) §3.3 | 句 | recall:全部句;precision:全部引用 | recall=0 | 检不出(App E 自认低估) | 无(NLI 不蕴含而已) | 无 |
| [Liu et al. 2304.09848](https://arxiv.org/abs/2304.09848) §2.3-2.5 | 句 | **verification-worthy** 句(排除自指与反问) | recall=0 | 条件计入 precision(并集全支持且无单引足够) | 折叠进 partial/no | 无 |
| [FActScore](https://arxiv.org/abs/2305.14251) §3.1 | 原子事实 | 相关原子事实(irrelevant 剔除) | n/a | 靠原子化解决 | 无 | Wikipedia 固定源 |
| [SAFE](https://arxiv.org/abs/2403.18802) §5 Eq 1 | 自足事实 | 相关事实 | n/a | 原子化 | 无 | 搜索为 oracle;F1@K,S=0→0 |
| [AIS](https://arxiv.org/abs/2112.12870) Def 3.2/3.8 | 整段输出 | 可解释输出(两阶段) | n/a | 无:严格全归因二值,"一处不 AIS 整体不 AIS"(§4.1.4) | 并入不可归因 | 无 |
| [CiteEval](https://arxiv.org/abs/2506.01829) §2.3-2.4 | 陈述(1-5 级) | **检索可归因陈述**;user/response/parametric 三类 N/A;Full 罚漏引 / Cited 不罚 | Full 罚 | 吸收进等级+编辑动作 | delete-misleading 罚最重 | **有**:credibility 编辑、择优引用 |
| [VeriScore](https://arxiv.org/abs/2406.19276) §2 | 可验证 claim | **仅可验证 claim**(观点/建议/虚构在抽取期剔除) | n/a | 按部分 | 定义了 contradicted 但因稀少并入 unsupported | 无 |
| [LongCite](https://arxiv.org/abs/2409.02897) §2 | 句(span 引用) | 全部,但**功能句自动过**(起始/过渡/总结/推理) | 非功能句=0 | recall 0/0.5/1;precision 认部分 | 无 | 无;附 Citation Length 反整页引用 |
| [CAQA](https://arxiv.org/abs/2401.14640) §3.2-3.3 | 陈述+引用集 | 分类基准 | n/a | Partially Supportive 类 | **Contradictory 独立类** | 无;聚合四型 single/union/intersection/concatenation |
| [AttrScore](https://arxiv.org/abs/2305.06311) §2 | 陈述+单参考 | 全部样本 | n/a | 无(extrapolatory 覆盖不足) | **Contradictory 独立类** | 无 |
| [DeepFact](https://arxiv.org/abs/2603.05912) §3.1 | 句 | 可验证句(None 剔除) | n/a | 句继承最差成分标签 | **Contradictory 为最高严重级**("任一矛盾则整句矛盾") | 可信度进标签定义 |

## B3. Judge 与聚合的关键事实(位置见提取记录)

- 位置偏差:GPT-4 换序一致仅 65%(MT-Bench Table 2);冲突率 GPT-4 至 46.3%、ChatGPT 至 82.5%,且偏向方向因 judge 而异(2305.17926 Table 2)。
- 长度偏差:重复列表攻击骗过 Claude/GPT-3.5 91.3%(MT-Bench Table 4);LC-AlpacaEval 回归控长把可操纵性从 22.9→64.3% 压到 41.9→51.6%(2404.04475 Fig 3)。
- pointwise vs pairwise:定向风格操纵下 pairwise 翻转 ~35%、绝对分 ~9%(2504.14716);单锚 pairwise 换锚仅 20% 排名稳定(2502.14074 §4.2);同一 judge 的分数与偏好自相矛盾率 23.3%(TrustJudge 2509.21117)。
- 自偏好:自识别能力与自偏好因果相连(2404.13076);PoLL 三小 judge 面板 κ 优于单 GPT-4 且成本 1/7(2404.18796 Table 1-2)。
- 聚合理论:OECD 手册 §1.6/6.11(线性=完全可补偿,几何=部分不可补偿,权重=价值判断,示例 21,1,1,1 vs 6,6,6,6);HDI 2010 技术注释(几何均值理由="不完全可替代");Ravallion 2012(乘法形式隐藏陡峭隐式权衡);HELM(拒绝合成、2025 年弃 mean win rate 因 population-dependent);TruthfulQA Fig 4(逐题合取);SWE-bench §2.2/App A.4(逐实例全测试通过=硬门槛);WMT07 §3.1/§6(人类评委 fluency/adequacy 分不开,遂废)。

---

# C. 构念分类(候选因素 → 归属)

判据:主分只收"构念上属于 evidence-grounded research breadth、且可在义务级判定"的因素;judge 打的整体质量轴一律独立列示;确定性可判的完整性信号进门槛或诊断;有已知偏差载体(长度、数量)的因素不得直接进任何分数。

## 主分(义务级门控覆盖率 GC 的组成部分)

| 因素 | 进入方式 |
|---|---|
| query-specific task fulfillment | 就是义务集合本身(C_j) |
| 研究广度 | =义务覆盖(与 task fulfillment 同一构念,**不得再设独立"广度"轴,否则双重计分**) |
| 事实准确性 | 经证据门 E_j 操作化(闭世界内"准确"=被冻结语料支持;**不得另设 judge 打的"准确性"轴,否则与门重复计分**) |
| citation correctness | E_j 的语义腿(页面支持 claim) |
| attribution / local binding | E_j 的确定性腿(就地绑定) |
| URL validity(在册) | E_j 的确定性腿 |
| 本次实际观察 | E_j 的确定性腿(ledger) |
| 冲突证据处理 | 当 query 蕴含时作为义务(conditional obligation);其余情形归质量面板 |

## 副指标(独立质量面板,judge 打分,永不并入主分)

- 分析深度、推理与综合质量(合并为一轴 Analysis;二者 judge 无法稳定区分,【推断】依据 WMT07 人类评委维度塌缩先例);
- 不确定性表达 + 冲突处理的非义务部分(一轴 Uncertainty & Conflict);
- 推荐相关性与可执行性(Recommendation;其合规部分已由 decision contract 二值判定进 Full Pass,面板只评"好不好用");
- 结构组织 + 清晰流畅(合并为一轴 Presentation;WMT07 塌缩证据 + 2307.03025 风格光环)。

## 硬门槛 / 标志(不进分数,决定榜单资格与 Full Pass)

- fabricated URL(注册表外):整报告 integrity flag(政策见 G);
- decisive claim 被引用页反驳(contradicted):critical error → Full Pass=0(DeepFact 的"矛盾为最高严重级"先例);
- decision contract 违约:Full Pass=0;
- 关键义务未 grounded:Full Pass=0。

## 诊断项(单独报告,解释分数,不参与排序)

citation completeness(报告级:未引用的可验证决定性 claim 率,ResearcherBench Groundedness 口径)、unobserved/unsupported/wrong-binding/contradicted 各计数(L0-L5 分类,见文献方案文档 §4.1)、Effective Citation Count(防少引保准确率,DRB E.Cit 口径)、来源多样性(DEER 的归一化 HHI 可直接搬)、来源角色分布、redundant citation(ALCE 移除测试)、引用格式、搜索相关性、抓取覆盖、成本与时延、轨迹失败模式(重复搜索/遗忘,FutureSearch 口径)。

## 不应使用

- 简洁性作为打分维度(长度偏差载体;长度只作协变量随面板报告,2404.04475 方法);
- 引用数量、报告长度、搜索次数作为深度/广度代理(研究原则明令;文献中 E.Cit 也只是诊断);
- 来源质量作为独立打分轴(在义务的 role contract 内做门,全局分布做诊断;单独打分会与门重复计分);
- 与参考报告的相似度(RACE 式;违反"不绑参考路线")。

**重叠/双重计分总结**:(1) fulfillment=广度=义务覆盖,一个构念一个分;(2) 事实准确性=证据门,不另设轴;(3) 结构/清晰/简洁塌缩为一轴;(4) 推荐质量拆成"守约"(二值,Full Pass)与"好用"(面板);(5) 来源质量只在门内按义务生效。

---

# D. 必须回答的问题

## D1. Report Quality 构念 → 见 C 节。

补充一条文献教训:DRB-II(§2.1)对"只查已引 claim"的批评(引用准确 ≠ 信息正确)与 DEER 的回应(用 citation back-tracking 把未引 claim 也纳入验证)说明:**只对已引内容做 correctness 会漏掉未引的错误陈述**。DRA 的对策是义务级判定(义务未被 grounded 支持就不得分,无论报告怎么写)+ 报告级未引决定性 claim 诊断。

## D2. Grounded 的定义

**推荐定义(与迁移文档五层对象一致):**

对义务 j:

- `a_j ∈ {0,1}`:适用条件(显式声明,确定性判定,不得从被评报告反推);
- `C_j ∈ {0, 0.5, 1}`:报告是否满足该研究要求(judge,语义;0.5 为部分满足,LongCite/DeepResearchGym 的三档先例);
- `E_j ∈ {0,1}`:证据门 = 存在一组决定性 claim 及其就地引用,同时通过 (i) 在册 (ii) 本次观察 (iii) 就地绑定 (iv) 语义支持 (v) 来源角色合同,允许沿任一 admissible route(OR-of-AND,= 迁移文档 z_j 的证据侧);
- `G_j = C_j · E_j`(条目级门控;E 为二值时等价于 min)。

$$GC_t = \frac{\sum_j w_j a_j G_j}{\sum_j w_j a_j}, \qquad CC_t = \frac{\sum_j w_j a_j C_j}{\sum_j w_j a_j}$$

`CC−GC` 差值即"说了但没证"的量,单列。

**逐项回答:**

- **分母**:rubric 义务(加权、适用),即"获得 rubric 分数所依赖的 claim"。理由:全 claim 分母会被不重要陈述稀释且鼓励少写(FActScore 自认 precision-only 鼓励弃答,§3.1 末段);义务分母有 Mind2Web 2 先例(归因检查只在 rubric 期望引用处存在且强制 critical,App D.1)。claim 级两比率(fabrication rate、unsupported rate)降为诊断,双分母口径按 ResearcherBench Eq 2-3 命名。
- **各失败模式**:决定性 claim 无引用 → E_j=0(非仅诊断);错绑 → 就地绑定腿失败 → E_j=0,计 wrong-binding 诊断;页面不支持 → 语义腿失败 → E_j=0;页面反驳 → E_j=0 **且** critical error(严重级高于不支持,DeepFact 排序先例);URL 伪造 → E_j=0 + integrity flag;未观察 → E_j=0(确定性,ledger)。
- **correctness vs completeness**:应区分,且已有命名先例(ResearcherBench Faithfulness/Groundedness;DeepResearchGym citation precision/recall;LiveResearchBench Accuracy/Traceability)。DRA:correctness 在门内,completeness 的义务部分在门内(决定性 claim 必须有引)、报告级部分做诊断。
- **来源质量/真实性**:真实性(在册+观察)必须在门内;质量作为义务级 role contract 在门内(仅当义务声明,如"性能 claim 不得引营销页"),全局质量分布单独报告。文献先例:CiteEval 把 credibility 纳入评级、DEER 有 Reference Reliability 指标,但都不与 grounding 混算。
- **纯分析/价值判断**:不要求引用。文献一致:CiteEval 三豁免(user/response/parametric,§2.3 Table 1)、VeriScore 抽取期剔除观点/建议、LongCite 功能句自动过、Liu et al. 只要求"关于外部世界的陈述"。但**决定性分析结论的前提必须 grounded**(义务级保证)【推断:该衔接规则文献无现成表述】。
- **binary gate vs 连续 vs 严重度**:证据门条目级二值(可判、可审计);内容满足三档;聚合层连续(加权平均);严重错误(矛盾、伪造)不做扣分算术,直接进 Full Pass 与 flag(HealthBench 负分是加法制的先例,但我们的伪造/矛盾语义上是资格问题而非程度问题,【推断】)。

## D3. 乘法问题:比较与结论

| 方案 | 可补偿性 | 零值行为 | 数字含义 | 权重敏感 | 先例 | 审稿攻击面 |
|---|---|---|---|---|---|---|
| 加权和(旧 0.39/0.28/0.33) | 完全(OECD §1.6) | 无:单项 0 可被补 | 弱:不可通约原子混合 | 最大,"权重=价值判断" | BIG-bench 归一均值(带重话警告);2010 前 HDI(已弃) | 任意权重;无证据报告可高分 |
| **报告级乘积 RQ×G** | 部分 | 硬:任一因子 0 → 总分 0 | **无单位、非概率** | 无显式权重但指数=隐藏权重 | 仅 CARLA(完成度×机械惩罚);**12 个 DR 基准零先例** | 双重计分(judge 光环);TruthfulQA 误读风险;`^1.5` 无出处 |
| 几何平均 | 部分(HDR 2010) | 硬(HDI 靠下限补丁) | 中 | 指数=权重 | HDI | Ravallion 2012 隐式权衡 |
| 调和平均(F 式) | 低 | 硬 | 同构念比率可,跨构念无理据 | β 显式 | van Rijsbergen(P/R 共享分子) | P/R 论证不迁移到 quality×grounding |
| **条目级合取后平均(GC)** | 条目级不可补偿、条目间可补偿 | 温和:一条坏一条 | **高:"有真实证据完成的义务占比"** | 仅条目权重(可预注册+敏感性分析) | TruthfulQA Fig 4;HealthBench §2;SWE-bench;Mind2Web 2 gate-then-average | 每条目双判定放大条目噪声;条目权重仍需辩护 |
| lexicographic | 层间零补偿 | 下层只破平 | 序数 | 层序=价值判断 | **ML 基准无先例(文献沉默)** | 忽略幅度 |
| Pareto/纯面板 | 不聚合 | n/a | 每个数干净 | 无 | HELM;ALCE;DeepResearchGym/RAVine | 无头名数;HELM 自己也补了绝对均值 |
| 主分+硬门槛 | 门上可补偿、门下资格制 | 门失败=除名/标志 | 高(若主分本身可解释) | 阈值=声明的价值判断 | SWE-bench;CARLA 惩罚下限 | 门槛悬崖 |

**结论:不推荐报告级乘法,推荐条目级合取(GC)+ 硬门槛。** 若坚持乘法必须回答的六问,在报告级都答不好:两因子测量含义(RQ 是 judge 光环污染的混合物)、为何零值归零(引用全缺时合理,但 RQ 低 × G 高的报告为什么和 RQ 高 × G 低同分?)、为何不重复惩罚(不能:未 grounded 的义务已经压低了 judge 眼中的质量)、为何不需要指数(答不了,指数本来就是为了修 G 不够狠,而那说明因子定义错了)、部分 grounding 解释(0.9×0.5=0.45 无单位)、极端案例(见附录)。这些问题在条目级全部消失:G_j=C_j·E_j 的含义是"这条义务完成且有证",零值语义、无指数、无重复惩罚、部分 grounding=义务占比,全部自洽。

## D4. Judge 使用

**协议选型(按独立提交稳定性排序,证据见 B3):**

1. **主分:pointwise 逐义务判定**(C_j、E_j 语义腿、decision contract)。零提交间耦合;WildBench 证明 checklist-pointwise 效度贴近 pairwise;2504.14716 证明更抗操纵。
2. **质量面板:pointwise 逐维,带锚定描述等级(0-4 或 1-7,附文字锚)**;冻结 2-3 份不同水平的 anchor report 作为 few-shot 校准物(多锚,不是单锚:2502.14074;中等强度锚:2603.16848)。
3. **anchored pairwise 只做验证 tab**(与人类偏好对照实验用),不做主分:依赖对手池、非传递性、翻转风险。
4. listwise 排除:长报告装不进一个上下文,且批量判定掉精度(RuVerBench Fig 5)。

**必须的偏差与稳定性控制(每条有出处):**

- 逐条判定,一次一条(RuVerBench 批量惩罚);
- 每个裁决附报告端+来源端摘录引文,程序核验存在性(RULERS §3.3;Mind2Web 2 的 Extractor/Verifier 分工);
- 3 judge 家族面板或 3-5 票投票,收益即平台(PoLL;RuVerBench Fig 6);judge 家族与被评 harness 家族隔离或量化自偏好(2404.13076);
- temperature 0 + 尽可能分布期望打分(G-Eval Eq 1;TrustJudge);
- 长度只影响面板维度:报告长度作协变量记录,面板分数可选 LC 式回归校正,系数在发布时冻结(2404.04475;冻结系数属【推断】的部署选择);
- judge 快照锁死非别名(2307.09009);judge prompt、rubric、锚报告、聚合代码 SHA-256 进 benchmark 版本号(JP-TL-Bench "structurally stable" 表述;DeepResearch Bench 被迫迁 judge 挂双榜是反面教材);judge 更换=版本升级+全量重跑校准集;
- 语义 judge 永不接触门字段自由文本(注入攻击结构性防御;红队套件验证,2410.07137/2403.17710)。

**分工线(哪些语义判断给 LLM):**

| 判定 | 执行者 | 依据/预期精度 |
|---|---|---|
| 在册、观察、HTTP 200、哈希、citation position、引文存在性 | 确定性程序 | 可判定;judge 在此不可信(REFLECT <55%) |
| 来源角色 | 确定性(registry 预标注) | 一次性人工标注换确定性 |
| 页面是否支持/反驳 claim(给源文本) | judge(+可选轻量 NLI 第二通道,分歧升审计) | ~80-90% 上限(AttributionBench;SemanticCite 84%);校准集必配 |
| 义务是否满足(C_j) | judge,逐条 | RuVerBench 前沿逐条 ~90-95% |
| decision contract 合规 | judge + 程序混合(约束数值程序查,权衡叙述 judge 查) | 【推断】 |
| 质量面板四轴 | judge | G-Eval 级相关(中等),独立列示故可接受 |
| 聚合、CI、PPI | 确定性程序 | Arena-Hard App A.1 bootstrap 先例 |

**rubric 泄漏**:judge 看 rubric 是设计必需(pointwise rubric 判定);被评 harness 是否能看 rubric 是政策问题(G 节)。TICK/STICK 显示模型能用 checklist 自我提升——rubric 公开=优化目标,正式集 rubric 应不公开,只公开义务类型学与 dev 集样例【推断,gaming 证据是代理性的】。

## D5. Task-specific rubric 构造

(承接 `DRA_V3_LITERATURE_SOLUTIONS_2026-07-17.md` §1.2 配方,此处只补评分侧参数与先例数字。)

- **数量**:每题 8-15 条义务、每条 1-4 个 proposition,总原子数落在 30-70 的文献常见带(HealthBench 中位 11 criteria;Mind2Web 2 平均 34 叶;DRB-II ~71;ProfBench 15-60;ResearchQA ~7.5)。低于 8 分辨力不足,高于 ~20 条义务时人审与判分成本超线性增长【推断】。
- **粒度**:每条义务单一、可独立判定(RaR 自包含公理;InFoBench 单需求分解);义务下 proposition 构成 OR-of-AND 路线。
- **等级**:义务判定用 0/0.5/1(不用 0-4:二值+半档在文献里与人一致性最好维护,0-4 描述等级留给质量面板);partial credit 允许在 C_j,不允许在 E_j(证据门必须可审计地过或不过)。
- **条件分支**:显式 `a_j` 条件 + `conditional_followup` 路型(迁移文档五路型);父子结构用 Mind2Web 2 的树形聚合语义表达(critical 子义务 gate,非 critical 平均)。
- **不同合理推荐**:decision contract 判"行动类合规+约束满足+权衡阐明",不点名产品(迁移文档结论语义);多合法结论按 exploration 轴控制分布(ResearchRubrics 三轴)。
- **新证据来源**:evidence contract(角色×关系×聚合×最小独立源数)判类型不判 URL;等价类只做建题期可满足性证明(eRAG 效用检查),绝不进运行时白名单。
- **requirement-deletion test**:删义务后 query 是否仍蕴含它;由标注者+裁决者双人执行(query 生成流程文档 §7 已有字段);通过率入 rubric 发布报告。
- **answerability 证明**:witness 等价类 ≥1(理想 ≥2)+ 冻结语料内检索复核;DR3-Eval 的 leave-one-out(删一源题必须变不可答)作为综合必要性补充检查。
- **LLM 生成后的审核与冻结**:LLM 只提案(两段式:witness 条件生成→去指涉化),人裁决必要性与合同;冻结前用 dev harness 输出做对抗挖漏与 learnability 过滤(全过/全挂条目删除);冻结后只允许版本化增补负分/惩罚类条目(OnlineRubrics 教训)。
- **避免 report-conditioned rubric**:rubric 必须在收取任何正式提交之前冻结;构造期 probe harness 限定为声明过的固定集合,其输出只用于 dev 集过滤,并在论文披露(与 BC+ 用 o3 采证据同类的披露义务);**绝不因某个新 harness 的报告修改正式 rubric**(只能记 disagreement 进下一版本)。

---

# E. 三个完整候选方案(D 节要求的方案在此)

## 方案 1(推荐):OGC——义务级门控覆盖 + 独立质量面板 + 资格门槛

**变量**:见 D2(a_j, w_j, C_j, E_j, G_j, GC_t, CC_t)。w_j ∈ {Essential=4, Important=2, Optional=1} 为预注册档位,发布前做 OECD Step 7 式敏感性分析(权重扰动下排名稳定性),不做连续调参。

**公式**:

$$\text{Headline} = \widehat{GC}^{PPI} = \text{PPI}\Big(\frac{1}{|T|}\sum_t GC_t\Big) \pm CI_{95}$$
$$FullPass_t = \mathbf{1}\Big[\bigwedge_{j\in Crit} G_j{=}1 \land DecisionValid \land \neg CriticalError\Big]$$

榜单列:GC(主排序)| CC | Full Pass 率 | 质量面板四轴 | integrity 状态 | 成本。伪造 URL>0 → integrity flag(政策见 G;底线沿用既定"造假者永不登顶"不变量:带 flag 的 harness 不得排在任何无 flag harness 之上)。

**流程**:确定性闸门 → 逐义务 judge(C_j、语义支持、contract)带摘录引文 → 程序聚合 → PPI 校正 → 面板 judge → 诊断汇编。

**优点**:主分是单一可解释概率;条目级门控有四个先例(TruthfulQA/HealthBench/SWE-bench/M2W2);对新 harness 零耦合;不绑路线(E_j 走合同);诊断/搜索污染天然分离;伪造者不可登顶由 flag+门保证而非脆弱的指数。

**缺点**:每义务两次判定放大条目级噪声(需校准集量化);w_j 档位仍是价值判断(靠预注册+敏感性分析辩护);质量面板不进主分,"文笔极差但全 grounded"的报告主分不受罚(靠面板列示与 Full Pass 的可读性底线兜住,见 G)。

**最易被审稿人挑战处**:C_j 的 judge 误差直接进主分(答:HarnessEval 校准集 + PPI 区间 + 人-人一致带对照);w_j 档位出处(答:预注册+敏感性分析+等权敏感性对照);"面板不进主分是否纵容烂文笔"(答:HELM 立场 + Full Pass 含可理解性底线,且文献中质量与 grounding 合并计分无先例)。

## 方案 2(被检验的假设):报告级 Truth = RQ × G

RQ = 质量面板加权和(或 judge 单一整体分),G = 报告级 grounded 比率(如 grounded 义务占比或 grounded claim 占比)。

**优点**:单数字;零证据归零;比旧三项加权和少两个任意权重;CARLA 有形似先例。

**缺点与攻击面**:(a) 12 个 DR 基准零先例,唯一乘积先例乘的是机械惩罚不是 judged 质量;(b) 双重计分:judge 的 RQ 已含 grounding 光环(WMT07、2307.03025),乘 G 是二次惩罚且权重不可控;(c) 数字无单位:0.9×0.5=0.45 与 0.6×0.75=0.45 同分,但前者"优秀但半证"后者"平庸但较实",排序含义无法辩护;(d) 部分 grounding 的边际惩罚随 RQ 变化(∂Truth/∂G=RQ),即好报告被罚得更狠,说不出道理;(e) 若嫌 G 惩罚不够狠加指数,立即回到 `^1.5` 无出处的老问题;(f) TruthfulQA 引用风险。

**极端案例行为**:见附录表;最致命的是案例 8(单个伪造 URL 只让 G 降 1/m,伪造者仍可登顶,违反既定不变量,必须再补门槛——补了门槛后乘法本身就多余了)。

**结论**:仅当"营销上必须一个含质量的总数"时作为展示 tab 考虑,且分母必须取义务级 G(=GC),等价于 GC×面板均值,并显著标注为展示用合成、不用于论文主结果。

## 方案 3(备选):硬门槛 + GC 主分 + 预注册加权质量合成(展示层)

门槛(资格制):fabricated=0;关键义务 grounded 全过 → 才有 "clean" 资格;clean 内主排序 GC;并为门外读者提供一个展示用 Overall = α·GC + (1−α)·Panel(α 预注册,dev 集上对人类整体偏好校准,论文只报 GC)。

**优点**:兼顾榜单传播与论文严谨;门槛资格制有 SWE-bench 先例;α 有校准程序而非拍脑袋。
**缺点**:α 仍是价值判断;门槛悬崖(差一条关键义务=资格骤变);两个榜单口径要长期维护。
**攻击面**:α 的 dev 校准会被质疑过拟合人类偏好样本(答:paired bootstrap + 预注册 + 报告 α 扰动敏感性)。

**未入选方案说明**:纯 Pareto 面板(HELM 式)因网站需要头名数且 HELM 自己已回补绝对均值而不推荐;lexicographic 因 ML 无先例且丢失幅度信息不推荐;几何/调和平均因跨构念无理据不推荐。

---

# F. 最终推荐

**主方案:方案 1(OGC)。备选:方案 3(仅当项目负责人判断网站必须有含质量的单一 Overall)。**

- **为何适合冻结环境**:E_j 的四条确定性腿(在册/观察/绑定/角色)只有闭世界能全部可判;义务级合同+等价类是闭世界独有能力;judge 只剩最小语义面,校准集可一次冻结长期复用。
- **为何适合新 harness**:pointwise、零对手耦合;分数=PPI 校正估计带 CI,第三方不需信任 judge;评测器版本哈希化,重跑可复现。
- **为何不绑路线**:E_j 按合同不按 URL;OR-of-AND 路线只加速已知路线;替代来源/分析/结论各有接受机制(合同/alternative_mechanism 路型/decision contract),且 FRR 有认证实验(F 节 V3)。
- **为何比旧公式合理**:旧公式的六个问题逐一消解——原子统一(全部在义务级)、无重复奖励(一个构念一个入口,C 节重叠分析)、无任意连续权重(档位+预注册+敏感性)、ProofOfFetch 从"打开过页面"升级为"支持具体 claim 的证据门之一腿"、无指数、长篇分析质量有专属面板不再被塞进事实分。
- **需 dev 集人工校准的量**:w_j 档位比值(4:2:1 vs 3:2:1 敏感性)、C_j 半档判据措辞、面板等级锚文本、(若用)长度协变量系数、judge 票数(1 vs 3)。
- **绝不能合并的指标**:integrity 信号(伪造/矛盾)不并入任何连续分;搜索/抓取效率不并入任何质量或 grounding 分;质量面板不并入 GC;CC 与 GC 永远分列(差值本身是信息)。

---

# G. 验证实验矩阵(可直接执行)

| # | 实验 | 样本量 | 指标 | 通过标准 | 证明什么 |
|---|---|---|---|---|---|
| V1 | 双盲双人标注 (report, obligation) 金标 | ~1,500-2,500 对(120-200 份报告,按 harness 风格与工具调用数分层) | 人-人 macro-F1 / κ,按义务类型分桶 | 建立人际带(预期 0.55-0.75 区间,HealthBench 先例) | 金标可用性;judge 验收的天花板 |
| V2 | judge 元评测 | V1 全集 | judge-人 macro-F1 分桶对照人际带;分歧样本 SAFE 式再裁决 | judge 落人际带内或之上;再裁决中 judge 错误占比 <50% | C_j/语义支持判定可用 |
| V3 | 合法替代层 FRR 认证 | ≥300 条替代路线/来源/结论条目(0 错误目标) | FRR + Clopper-Pearson 95% CI | 0 错 → FRR≤1%;≤3 错 → 修 evaluator 后重跑 | 不绑路线的量化证明(**文献无先例,可声称**) |
| V4 | 伪证据层 FAR 认证 | ≥300 条手术腐蚀条目(六型:伪造/未观察/洗白/数字扰动/结论翻转/注入) | FAR + CI;确定性型单元测试 100% | 确定性型全拦;语义型 FAR≤1-2% | 伪证据不通过 |
| V5 | 人类整体偏好对照 | ~200 报告对,3 标注者 | GC 排序 vs 人类偏好:Spearman/Kendall/pairwise accuracy;与旧公式、RQ×G、RACE 式对照 | GC 显著优于旧公式(paired bootstrap p<0.05) | 新分数效度增益(论文主表) |
| V6 | 榜单可分性 | 现有 12 harness 全量 | Arena-Hard 式 separability(CI 不重叠对占比)+ 最小可检测分差 | separability ≥ 旧方案;MDD 公布 | 分数区分度 |
| V7 | 三替换测试(source/route/conclusion) | 每类 ≥30 案例改写报告 | 分数不变性 |ΔGC|≤ε(ε=1 个义务权重) | 全过 | 合同接受替代;与 V3 互补(V3 认证率,V7 验机制) |
| V8 | 对抗扰动方向性 | 删引用/伪造/错绑各 ≥50 | 分数变化方向与幅度 = 预期(掉且只掉对应义务) | 100% 方向正确 | 门的靶向性,无过溢惩罚 |
| V9 | 风格扰动不变性 | 改写/重排/加长孪生 ≥100 对 | 判定不变率 | ≥95%(逐义务) | 长度/格式免疫 |
| V10 | judge 重复稳定性 | 16 次重跑全套 | 分数 std | ≤0.005(HealthBench 0.002 先例) | 可复现 |
| V11 | 跨 judge 一致性 | 3 家族 judge 全量 | 义务级 κ;榜单 Kendall τ | κ≥0.7;τ≥0.9 | 不被单 judge 绑架;为开源 judge 备份选型 |
| V12 | 权重敏感性 | w 档位扰动(4:2:1→3:2:1→等权) | 榜单排名变动 | Top-3 排序不变或披露 | OECD Step 7;堵"任意权重"质疑 |
| V13 | 门组件消融 | 逐个关掉 E_j 四腿 | 各 harness 分数与排名变化 | 每腿都改变至少一个排名对(否则该腿冗余) | 每个门都有存在证明 |
| V14 | dev/test 隔离 + 预注册 | 流程性 | 权重/阈值/prompt 在收正式提交前 SHA-256 存档 | 全部先于任何 test 集打分 | 反 report-conditioning |
| V15 | PPI 落地 | 每维度 ≥150 金标 | PPI 点估计+CI vs 裸 judge 分 | CI 覆盖模拟验证 | 榜单统计保证 |
| V16 | 冻结完整性监控 | 锚集 ~50 份已判报告,每月重判 | e-process 报警 | 无报警或触发版本升级流程 | "冻结"是持续证明的声明 |

执行顺序:V1→V2(阻塞其余)→ V4 确定性部分(纯程序,可先行)→ V3/V7/V8/V9 并行 → V5/V6 → V10-V13 → V14-V16 常态化。

---

# H. 未解决问题(需项目负责人拍板)

1. **伪造 URL 政策**:integrity flag 的具体后果——单独"non-clean"分区、排名封顶于所有 clean 之下、还是当期除名?(建议:flag+封顶,保留分数可见以供诊断。)
2. **Optional 义务是否进主分**:进(权 1)还是只做诊断?影响 GC 对"锦上添花"研究面的敏感度。
3. **正式集 rubric 是否对被评方保密**:保密(反 gaming)vs 公开(可复现性观感)。建议:义务类型学+dev 集全公开,正式集 rubric 延迟公开(评测季后)。
4. **质量面板在榜单的位置**:主页并列列 vs 二级 tab。涉及 AA 风格首页的信息密度。
5. **构造期 probe harness 集合**:learnability 过滤允许用哪些 harness(建议:现有 12 个中指定 4-6 个风格多样者,论文披露)。
6. **展示用 Overall 是否保留**(方案 3 的 α 合成):要不要为传播牺牲一点口径纯度。
7. **矛盾严重级的范围**:contradicted 触发 critical error 是仅限决定性 claim,还是任何被引 claim?(建议:仅决定性 claim,其余计诊断。)
8. **C_j 半档(0.5)的去留**:全二值更可审计,半档更贴近 judge 行为。建议 dev 集上按 V2 的 judge-人一致性择优。
9. **金标集治理**:PPI 金标与 HarnessEval 校准集的扩充节奏、出资与标注者 roster。
10. **judge 选型**:前沿 API judge(准确、但有 2307.09009 式退役风险)vs 开源可冻结 judge(Prometheus 2 式,准确率折价)。建议:API judge 主用 + 开源 judge 作 V11 的一致性备份与末日预案。

---

# 附录一:10 个极端案例在三方案下的行为

| # | 案例 | 方案 1 OGC | 方案 2 RQ×G | 方案 3 门槛+合成 |
|---|---|---|---|---|
| 1 | 内容表达俱佳、零引用 | GC=0(全部 E_j=0);CC 高、面板高、差值曝光"说而无证" | RQ≈0.9×G=0 → 0;结果同但无 CC/差值可解释 | 不过关键义务门 → 无 clean 资格;Overall 仅展示 |
| 2 | 半数关键结论有证 | GC≈0.5,含义直白"一半义务有证完成";Full Pass=0 | 0.9×0.5=0.45,无单位,与"平庸但较实"混淆 | 同 GC;资格取决于哪些关键义务缺 |
| 3 | 引用多且真、分析差 | C_j 低(义务满足要求综合非引用堆砌)→ GC 低;E.Cit 诊断高、面板低 | 风险:RQ 被引用光环抬高 × G 高 → 虚高 | 同方案 1 |
| 4 | 流畅但关键结论被引用页反驳 | 该义务 E_j=0 + critical error → Full Pass=0;contradicted 诊断≥1 | G 仅微降,除非另加矛盾特判(又要打补丁) | 同方案 1(门槛捕获) |
| 5 | 推荐异于参考但证据约束成立 | decision contract 过 → 无惩罚 | 取决于 RQ judge 是否参考对照式;若 RACE 式则误罚 | 同方案 1 |
| 6 | 另一组真实证据完成任务 | 合同判型不判 URL → E_j=1,满分路径 | G 的定义若按 witness 命中则误罚;按合同则同左 | 同方案 1 |
| 7 | 命中关键词无真综合 | C_j 语义判定(靠扰动测试过滤的义务措辞)+ 面板低;残余风险=judge 宽松,由 V2/V4 量化 | RQ 可能被表面覆盖骗高 × G 高 → 最坏情形 | 同方案 1 |
| 8 | 一个伪造 URL、其余正确 | 该义务 E_j=0 + **integrity flag**(政策 H1);伪造者不可登顶由资格制保证 | G 仅降 1/m → **伪造者可登顶,违反既定不变量**,必须另补门(补了门乘法就冗余) | 门槛直接除 clean 资格 |
| 9 | 仅一条关键义务无证、其余全 | GC=(Σw−w_k)/Σw(高分);Full Pass=0;"优秀但未完成"清晰可读 | 高×高=高,但 Full Pass 语义缺失,需另设 | 同方案 1 |
| 10 | 搜索污染重、最终引用与结论全对 | GC 不受影响;搜索相关性诊断低(RAVine 弱相关证据支持此分离) | 若 G 含 fetch 比例类项则误罚(旧公式的 ProofOfFetch 教训) | 同方案 1 |

# 附录二:本报告新增核验论文速查(全部 abs/原文取验,除注明)

评分公式提取:DeepResearch Bench 2506.11763(RACE Eq 1-3、FACT App E Eq 4-6)/ DeepResearchGym 2505.19253(§3.2.2、§4.4)/ RAVine 2507.16725(Eq 5-11)/ Mind2Web 2 2506.21506(§3.3 递归式、App D.1)/ HealthBench 2505.08775(§2)/ DRB-II 2601.08536(§3.1.2)/ LiveDRBench 2508.04183(§3.2 Eq 1-2)/ ProfBench 2510.18941(§4.1-5)/ DR3-Eval 2604.14683(Eq 1-6)/ ResearchQA 2509.00496(§4.1 Eq 1)/ DEER 2512.17776(App D.4、G.4)/ ReportBench 2508.15804(§2.2、3.2)。
引用指标:ALCE 2305.14627(§3.3 + eval.py)/ Liu et al. 2304.09848(§2.3-2.5)/ FActScore 2305.14251(§3.1)/ SAFE 2403.18802(§5 Eq 1、§D.3)/ AIS 2112.12870(Def 3.2/3.8、§4.1)/ Attributed QA 2212.08037(§3.2)/ RAGAS 2309.15217(§3)/ CiteEval 2506.01829(§2.3-2.4、§3-4)/ VeriScore 2406.19276(§2)/ LongCite 2409.02897(§2)/ CAQA 2401.14640(§3.2-3.3)/ AttrScore 2305.06311(§2)/ LiveResearchBench 2510.14240(§4.2、App E)/ ResearcherBench 2507.16280(§4.2.1 Eq 2-3)/ DeepFact 2603.05912(§3.1、App A)。
Judge 协议:MT-Bench 2306.05685 / Fair Evaluators 2305.17926 / LC-AlpacaEval 2404.04475 / Arena-Hard 2406.11939 / G-Eval 2303.16634 / Prometheus 2 2405.01535 / PoLL 2404.18796 / 自偏好 2404.13076 / verbosity 2310.10076 / 漂移 2307.09009 / WildBench 2406.04770 / 2504.14716(COLM 2025)/ 非传递性 2502.14074 / TrustJudge 2509.21117 / 锚点选择 2603.16848 / JP-TL-Bench 2601.00223 / REFLECT 2605.19196 / RuVerBench 2606.29920 / RULERS 2601.08654。
聚合与效度:TruthfulQA 2109.07958(§2.1、Fig 4)/ HELM 2211.09110(+2023/2025 官方博客)/ BIG-bench 2206.04615(§3.1)/ OECD 复合指标手册 2008(§1.6、6.11-6.12、Step 7,官方 PDF)/ HDR 2010 技术注释(官方 PDF)/ Ravallion 2012(存在性核验,原文引述 UNVERIFIED)/ Munda & Nardo 2009(存在性核验)/ Jacobs & Wallach 1912.05511 / Raji et al. 2111.15366 / Bean et al. 2511.04703(NeurIPS 2025,445 基准效度审查)/ 心理测量 2310.16379 / ECBD 2406.08723 / tinyBenchmarks 2402.14992 / F-measure:van Rijsbergen 1979(二手核验)+ Powers 1503.06410 / SWE-bench 2310.06770(§2.2、App A.4)/ CARLA 官方榜规则页 / WMT07 W07-0718(§3.1、§6,官方 PDF)/ Style over Substance 2307.03025。
