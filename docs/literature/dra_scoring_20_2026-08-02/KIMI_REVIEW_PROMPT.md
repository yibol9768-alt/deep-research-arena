# Kimi K3 max review prompt

你是 DRA（Deep Research Arena）评分设计的独立方法学审稿人。请以计划/只读模式工作，不要修改仓库，不要运行正式评测，不要调用外部付费服务。

## 必读材料

1. `paper_manifest.tsv`：恰好 20 篇论文的来源清单。
2. `papers/`：20 篇原始 PDF。
3. `text/`：PDF 的可搜索纯文本，仅用于定位；最终结论必须能回到 PDF。
4. `../../../DRA_FOUR_AXIS_SCORING_V1_3_SPEC.md`：当前四轴评分规范。
5. `../../../DRA_THREE_AXIS_SCORING_REDESIGN_2026-07-22.md`：上一版三轴设计。
6. `../../../DRA_QWEN_SCORER_SCALING_WITHOUT_METRIC_CHANGE_2026-07-30.md`：Qwen 统一裁判和扩展约束。

## 已知 DRA 前提

- 任务运行在有限、冻结、可复现的网页沙盒中。
- 12 个 harness 使用同一评分程序。
- 报告先拆成可验证 claim；URL registry 与 observation ledger 可以区分 fabricated、unobserved、unsupported、wrong binding、contradicted citation。
- 混合检索（exact/BM25/dense/structured/graph）只召回候选证据，不能直接贡献分数；最终由同一冻结 Qwen judge 或确定性规则裁决。
- 当前诊断轴为 Fact、Evidence、Completeness、Rubric，并在报告级乘 Provenance。写作 Elo 单独报告。
- 用户希望保持高度自动化、可复现、少依赖逐题人工 rubric，同时愿意在文献证据充分时修改公式。
- 不能把构题 witness graph 当作唯一合法研究路线。

## 你必须回答的问题

1. 在这 20 篇中，逐篇判定它究竟使用：显式 Precision/Recall/F1、双分母但不叫 P/R、单侧 precision、rubric/多维面板，还是其他聚合。不要把“有两个比例”误称为 F1。
2. 检验这个命题：`大多数类似工作采用 precision–recall 思路`。分别给出宽口径和严格口径的计数，并说明分母。
3. DRA 当前 `Truth = Provenance × mean(Fact, Evidence, Completeness, Rubric)` 的哪些部分可保留，哪些存在重复计分、错误独立性假设或构念混合？给具体反例，不要只做价值判断。
4. Fact 与 Completeness 能否组成 Content F1？只有在它们共享 canonical proposition universe 时才允许；请明确如何机械化建立对应关系，怎样处理额外但真实的 claim、负命题、纯分析、推荐和不可裁决 claim。
5. Evidence 应该是一条独立轴、Citation Precision/Recall/F1、claim 级 gate，还是 provenance 的组成部分？比较至少三种方案。
6. Provenance 应继续报告级相乘，改为 claim/binding 级合取，还是只做资格/完整性标记？必须覆盖 fabricated URL、合法但未观察、已观察但不支持、错绑、反证这五种情况。
7. 给三个可运行候选方案，并用至少八个极端报告反例推演：短而全真、长且堆真事实、广但少引用、引用很多但错绑、URL 真实但没抓、一个伪造 URL、合理替代路线、没有可引用正向 span 的负命题。
8. 推荐一个主方案与一个保守兼容方案。主方案必须给出精确定义、零分母约定、宏/微平均层级、正式榜单字段、诊断字段和 calibration 方案。
9. 明确哪些结论来自哪篇论文。引用论文编号、标题、章节或页码，不得编造。
10. 对 Qwen judge 的每个轴分别设计人工校准；总分接近不能当作轴等价。说明 Accuracy、Precision、Recall、F1、Cohen/Fleiss kappa、置信区间分别用于什么。

## 输出格式

用中文 Markdown。先给“裁决摘要”，再给“20 篇计数表”“现公式审计”“候选方案”“极端案例”“推荐方案”“需要做的实验”“仍不能声称的内容”。要求公式可直接由 Pandoc/LaTeX 渲染。不要使用花哨措辞，不要把模型偏好当证据。
