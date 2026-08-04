# GPT-5.6 Sol max final synthesis and layout prompt

你是 DRA 评分方案的最终方法学编辑。请只读检查下列材料并输出一份可直接作为项目正式设计文档的中文 Markdown。不要修改代码，不要臆造实验结果，不要隐藏争议。

## 必读材料

1. `PAPER_SCORING_EXTRACTION.md`
2. `paper_manifest.tsv`
3. `KIMI_K3_INDEPENDENT_REVIEW.md`
4. `KIMI_K3_CROSS_CRITIQUE.md`
5. `GPT56_INITIAL_SCORING_PROPOSAL.md`
6. `../../../DRA_FOUR_AXIS_SCORING_V1_3_SPEC.md`
7. `../../../DRA_QWEN_SCORER_SCALING_WITHOUT_METRIC_CHANGE_2026-07-30.md`

## 目标

Kimi 与 GPT-5.6 已分别研究并互相质疑。你需要做出最终裁决，而不是简单拼接两份意见。

## 不可丢失的 DRA 前提

- 有限、冻结、可复现的网页沙盒。
- 同一程序评分 12 个 harness。
- claim 级事实核验、URL registry、legal discovery 与 observation ledger。
- exact/BM25/dense/structured/graph 只召回候选证据，不直接产生分数。
- 不把 query 构造时的 witness URL 当唯一合法路线。
- 高自动化、低逐题人工 rubric 成本、可审计。
- 写作 Elo 是相对偏好量，不能未经验证与绝对比例相加或相乘。

## 文档必须包含

1. 一页以内的执行摘要，明确当前公式是否立即替换。
2. 20 篇文献的严格计数与宽口径计数，明确“多数用 P/R 思想”和“多数用 F1 总分”的区别。
3. 当前公式的优点与最小反例审计。
4. 最终推荐评分体系，给出：
   - eligible claim；
   - claim-level truth、citation binding、joint support、provenance gate；
   - Grounded Claim Precision；
   - 路线无关的 Grounded Research Recall；
   - F1 或其他聚合；
   - 零分母、unresolved、census_gap、负命题、纯分析和推荐的处理；
   - fabricated、unobserved、unsupported、wrong binding、contradicted citation 的精确后果；
   - 宏平均层级和置信区间。
5. 只保留用户真正需要看到的正式榜单字段；详细诊断放二级面板，不能堆出十几个主指标。
6. 一个保守兼容车道：在新方案通过 meta-evaluation 前，不破坏现有分数与历史结果。
7. 至少十个受控反例，展示旧公式与候选公式会怎样排序。
8. Qwen judge 的轴级人工校准和统计验证方案，说明 Accuracy、Precision、Recall、F1、Kappa、bootstrap/PPI 的用途。
9. 从 Dev-14 到 56 题的分阶段实施计划、冻结点、退出条件和回滚条件。
10. 清楚区分：已经由文献支持的结论、需要实验证明的假设、当前不能声称的内容。
11. 论文 Methods 可直接复用的英文表述，避免过度宣称。
12. 附录给出 20 篇论文到 DRA 设计决策的映射。

## 最终方法学偏好

- 如果两个比例没有共享可枚举的 matching universe，不得仅因为一个像 precision、一个像 recall 就计算 F1。
- 尽量在 claim/binding 级合取 truth、support 与 observation，再聚合，避免报告级乘法假设错误独立。
- recall 分母必须在看到被测报告前冻结、证明可回答、允许替代证据路线。
- 不要用无法解释的 0.39/0.28/0.33 或任意四轴等权作为最终理论依据。
- 若证据不足以立即换榜单，应明确推荐“双轨影子运行 + 预注册升级条件”，而不是强行下结论。

## 排版要求

- 标题、版本、状态、决策摘要清楚。
- 数学公式使用 `\[ ... \]` 或 `\( ... \)`，确保 XeLaTeX Markdown 包可渲染。
- 表格每列文字简洁，避免超宽。
- 使用 Mermaid 只画一个总流程图；同时提供纯文本含义，避免 PDF 渲染依赖。
- 语言简洁、审稿人可核查；不要使用口号。
- 最后附“模型协作与可复现记录”：Kimi K3 max 独立审查、GPT-5.6 Sol max 初始方案与最终编辑，列出对应材料路径，但明确模型讨论不是科学证据。

只输出最终 Markdown 正文，不要输出解释或代码围栏。
