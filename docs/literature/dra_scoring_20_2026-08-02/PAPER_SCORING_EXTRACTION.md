# DRA 相似评分论文的 20 篇原文审计

日期：2026-08-02
范围：Deep Research、长报告事实性、引用真实性与 RAG 评测
原文：`papers/` 目录中的 20 篇 PDF，共 556 页
可复核性：来源见 `paper_manifest.tsv`，文件哈希见 `SHA256SUMS`

## 1. 先给结论

“多数相关论文采用 precision–recall 思想”在宽口径下成立，但必须限定含义。

- 严格 P/R 口径：9/20 显式报告 Precision/Recall 对或 F1；其中真正计算调和平均 F1 的只有 7/20。
- 宽口径：把未命名双分母与单侧 precision-like 比例计入后为 14/20。
- 直接的 Deep Research 报告级子集里，只有 1/6 显式采用 P/R；其余主要使用 rubric pass rate、多个独立面板或 Judge 校准。
- Deep Research 工作通常不会让一个 F1 代替全部报告质量。事实性、引用、覆盖、分析和呈现经常分开报告。

因此，DRA 可以把 Fact 与 Completeness 解释成 precision-like 与 recall-like 构念，也可以构造候选 F1；但只有在两者共享同一个可枚举命题空间时，F1 才是严格成立的。Evidence 与 Provenance 也不能因为“像 precision/recall”就被随意并入同一个分数。

## 2. 逐篇分类

### 2.1 Deep Research 报告评测

#### 01. DeepResearch Bench

- 类别：单侧 citation precision 加独立报告质量面板。
- 单元：去重后的 statement–URL pair。
- 核心量：

\[
CitationAccuracy=
\frac{\#\text{支持的唯一 statement--URL 对}}
{\#\text{全部唯一 statement--URL 对}}
\]

- `Effective Citations` 是有效引用数量，不存在完整引用需求集合，因此不是 recall。
- RACE 另外评估报告质量，并相对参考报告归一化；它不与 citation accuracy 组成 F1。
- 对 DRA 的启示：保留 statement–URL 去重和引用准确性；不能把有效引用数量假装成完整性。

#### 02. DeepResearch Bench II

- 类别：rubric pass rate。
- 单元：9,430 个二元 rubric，分 Information Recall、Analysis、Presentation。
- 核心量：

\[
S_t=\frac{\#\text{通过的 rubrics}}{\#\text{全部 rubrics}}
\]

- 这个量只有目标侧分母，没有报告输出侧的 false-positive 分母，因此不是 precision。
- 对 DRA 的启示：细粒度二元要求有利于解释；专家报告路线和大量人工审核不符合 DRA 的低人工成本目标。

#### 03. ResearcherBench

- 类别：双分母，但不合成 F1。
- 单元：报告事实 claim、带引用 claim、专家 rubric。
- 核心量：

\[
Faithfulness=\frac{N_{supported}}{N_{cited}}
\]

\[
Groundedness=\frac{N_{cited}}{N_{all\ factual}}
\]

- 对 DRA 的启示：双分母结构与我们最接近。DRA 应将第二个分子的 `cited` 强化为合法、已观察、正确绑定且真实支持。

#### 04. ReportBench

- 类别：参考文献检索显式报告 Precision 与 Recall，但不计算 F1；引用一致性和无引用事实准确性另作面板。
- 单元：引用文献、cited statement、non-cited factual statement。
- 做法：以生成报告引用的参考文献为 precision 分母，以 gold 综述的参考文献全集为 recall 分母；另外获取完整页面，定位候选段落，判断 statement consistency，无引用事实由多个 Judge 多次裁决。
- 对 DRA 的启示：完整页面与可审计的中间证据有价值；六次联网裁决成本不适合 DRA 正式全量路径。

#### 05. OpenScholar

- 类别：引用子系统使用 P/R/F1，内容质量独立。
- 单元：citation-worthy sentence、单个 citation、内容 rubric。
- 核心量：

\[
CitationF1=
\frac{2\,CitationPrecision\,CitationRecall}
{CitationPrecision+CitationRecall}
\]

- 对 DRA 的启示：有力支持“Citation F1 只评引用子系统，不能替代报告正确性、覆盖和组织”。

### 2.2 引用真实性、完整性与绑定

#### 06. ALCE

- 类别：显式 Citation Precision、Recall、F1。
- Recall 分母是所有生成 statements：

\[
R_{cite}=
\frac{\#\text{由引用集合联合支持的 statements}}
{\#\text{全部 statements}}
\]

- Precision 分母是全部 citations，并检查单条 citation 对附近 statement 是否必要、相关且支持。
- 对 DRA 的启示：可以直接映射 `unsupported_citation` 与 `wrong_binding`；ALCE 不知道 URL 是否真的被 agent 观察，DRA 的 ledger 是额外能力。

#### 07. LongCite

- 类别：显式 Citation Precision、Recall、F1，加引用长度诊断。
- 单元：citation-worthy statement 与 citation span。
- 对 DRA 的启示：加入引用定位粒度或引用跨度诊断；必须在 DRA 自己的数据上报告 Judge–human Kappa 和逐轴 F1。

#### 08. CiteEval

- 类别：完整上下文中的引用编辑与独立 Likert 质量分。
- 单元：statement–citation edit action。
- 能区分缺失、冗余、错误和需替换引用，不只做局部 NLI。
- 对 DRA 的启示：保留细分诊断，但不要把 1–5 的主观引用质量直接混进 Truth。

#### 09. ALiiCE

- 类别：显式 Citation Precision、Recall、F1，加位置指标。
- 单元：句内 citation marker 对应的 atomic claim。
- Precision 在 claim 已被引用集合充分支持后，再检查单个 citation 是否必要。
- 对 DRA 的启示：claim span 与 citation span 的位置关系是 `wrong_binding` 的关键，句子级或 URL 级统计太粗。

### 2.3 长报告事实性

#### 10. FActScore

- 类别：单侧 factual precision。
- 单元：atomic fact。
- 核心量：

\[
FactPrecision=
\frac{\#\text{被知识源支持的 atomic facts}}
{\#\text{全部 atomic facts}}
\]

- 它使用短输出惩罚，但没有真实的任务答案全集。
- 对 DRA 的启示：支持当前 Fact 的输出侧分母；单独使用会奖励短而保守的报告。

#### 11. SAFE / LongFact

- 类别：显式 precision 与代理 recall，合成 \(F_1@K\)。
- 核心量：

\[
P=\frac{S}{S+N},\qquad
R@K=\min\left(\frac{S}{K},1\right)
\]

\[
F_1@K=\frac{2P(R@K)}{P+R@K}
\]

- \(K\) 是期望事实数量，而不是真实答案全集。
- 对 DRA 的启示：DRA 若有冻结的任务证据 census，就不应再使用人为设置的 \(K\)。

#### 12. VeriScore

- 类别：筛选可验证 claim 后使用 \(F_1@K\)。
- 先排除观点、建议和其他不可外部核验内容。
- 对 DRA 的启示：必须先做 claim eligibility，避免把元陈述、纯分析、偏好或建议误抽成事实 claim。

#### 13. D-FActScore

- 类别：事实精度加实体消歧，不是 recall 设计。
- 发现局部原子事实都为真，仍可能因实体、时间或关系拼接错误而形成错误段落。
- 对 DRA 的启示：加入 product model、实体、数字、单位和时间绑定检查，不能只验证孤立字符串。

#### 14. FaStFact

- 类别：Fact precision 与 \(F_1@K\) 的高效实现。
- 使用 chunk-level claim extraction、document-level evidence 与置信筛选减少调用。
- 对 DRA 的启示：可以共享页面证据并批量核验；正式评分不能因为低置信度就跳过 claim，否则改变分母。

#### 15. DeepFact

- 类别：claim 事实性加 Audit-then-Score 治理。
- 重点不是新总分，而是当报告证据与 benchmark 冲突时，允许 auditor 审查并版本化修订。
- 对 DRA 的启示：`census_gap`、新 URL 和矛盾证据需要冻结的申诉与版本治理，不能把初始答案表当绝对真理。

#### 16. MiniCheck

- 类别：claim–document 二元支持分类器的 meta-evaluation。
- 重点是 verifier 的准确率与成本，不是报告级 P/R 聚合。
- 对 DRA 的启示：可作为低成本 verifier 基线；必须先在 DRA gold 上做逐轴校准，不能只引用外部数据集成绩。

### 2.4 RAG 的双分母结构与 Judge 校准

#### 17. RAGAS

- 类别：多面板，其中 Faithfulness 是输出侧 precision-like，Context Recall 是目标侧 recall-like。
- 典型量：

\[
Faithfulness=
\frac{\#\text{context 支持的 response claims}}
{\#\text{全部 response claims}}
\]

- Context Recall 使用 ground-truth statements 为分母；各维度分开，不强制合成 F1。
- 对 DRA 的启示：Fact 与 Completeness 可以解释为双分母，但这本身不证明它们可以直接做 F1。

#### 18. RAGChecker

- 类别：显式 claim-level Precision、Recall、F1，加检索器和生成器诊断。
- 核心量：

\[
Precision=
\frac{\#\text{被 ground truth 蕴含的 model claims}}
{\#\text{model claims}}
\]

\[
Recall=
\frac{\#\text{被 model 覆盖的 ground-truth claims}}
{\#\text{ground-truth claims}}
\]

- 对 DRA 的启示：这是 Fact 与 Completeness 组成 P/R 最直接的先例，但前提是双方可以匹配到同一 canonical proposition universe。

#### 19. ARES

- 类别：三个独立分类器加 Prediction-Powered Inference，不合成 F1。
- 维度：Context Relevance、Answer Faithfulness、Answer Relevance。
- 使用少量人工标签校正 Judge 估计并报告置信区间。
- 对 DRA 的启示：应对 Qwen 每个轴单独做人工 gold calibration；总分接近不能证明两个 Judge 的轴等价。

#### 20. Deep Research, Shallow Evaluation

- 类别：Deep Research metric 的 meta-evaluation。
- 结论：pairwise 人类偏好适合验证系统级排序，但不能证明每个细粒度评分轴有效；轴级验证需要 metric-wise 专家标注。
- 对 DRA 的启示：Qwen 与 v4lite 总分接近不能当等价性证据。Fact、Evidence、Completeness、Rubric 必须分别报告 Precision、Recall、F1 或 Kappa。

## 3. DRA 中实际存在三组不同的双分母

### 3.1 报告内容的输出侧精度

\[
P_{claim}=
\frac{\text{报告中真实且满足证据要求的实质性 claims}}
{\text{报告中全部 eligible 实质性 claims}}
\]

它回答：报告说出来的内容有多少可信。

### 3.2 任务研究工作的目标侧召回

\[
R_{task}=
\frac{\text{被报告有证据完成的必要研究单元}}
{\text{冻结任务 census 中的全部必要研究单元}}
\]

它回答：题目要求的研究工作完成了多少。

### 3.3 引用系统的 precision 与 recall

\[
P_{cite}=
\frac{\text{合法、已观察、就地绑定且支持的 citation bindings}}
{\text{全部 citation bindings}}
\]

\[
R_{cite}=
\frac{\text{至少有一个合格 binding 的 citation-required claims}}
{\text{全部 citation-required claims}}
\]

\[
F_{cite}=\frac{2P_{cite}R_{cite}}{P_{cite}+R_{cite}}
\]

它回答：引用是否正确，以及该引用的地方是否都真正给了证据。

这三组量不能混成一个叫“precision”或“recall”的比例。Provenance 还需要额外回答 URL 是否在册、是否合法发现、是否在本次运行被观察。

## 4. 对当前公式的初步裁决

当前公式是：

\[
Truth_t=
Provenance_t\times
\frac{Fact_t+Evidence_t+Completeness_t+Rubric_t}{4}
\]

它有三个优点：自动化、统一、可复现；也保留了 DRA 独有的执行归因。不过，四轴等权没有来自上述 20 篇论文的直接先例，报告级乘法还会假设不同错误可以在总体比例上相互独立。

一个最小反例：十个 claim 中，Fact 与 Provenance 都是 0.9。如果它们失败的是同一个 claim，联合通过 9 个；如果失败的是不同 claim，联合只通过 8 个。但报告级乘法在两种情况下都给 0.81。逐 claim 合取才能区分。

因此，文献支持下一步把 Fact、Evidence 与 Provenance 下沉到 claim/binding 级组合，再与预先冻结的必要研究单元 recall 比较；并不支持简单把四轴改名后继续等权平均。

## 5. 在改主分之前必须满足的条件

1. 在看到被测报告之前冻结任务侧必要研究单元。
2. 单元描述必须路线无关，已知 URL 只作为 answerability witness。
3. 报告 claim 与任务单元能够匹配到同一个 canonical proposition universe。
4. 负命题允许通过限定范围内的系统性搜索与未发现证书处理，不能要求正向 support span。
5. 纯分析、偏好和建议不进入外部事实 claim 分母；决定性结论的外部前提仍需证据。
6. `unresolved` 与 `census_gap` 不能直接算错，也不能从分母静默删除；正式分应附可裁决率和上下界。
7. 多条等价证据路线由语义支持判定接受，不使用 URL 白名单。
8. 在替换现有总分前，用同一批报告比较候选公式与人工逐轴判断、系统级排序和极端反例的符合程度。

## 6. 暂定研究结论

最稳妥的实验顺序不是立刻宣布新总分，而是并行计算：

\[
ContentF1=H(P_{claim},R_{task})
\]

\[
CitationF1=H(P_{cite},R_{cite})
\]

并保留当前四轴与 Provenance 作为对照。只有当 Content F1 的两个分母确实共享同一个 proposition universe，且在短真报告、堆砌报告、错引报告、替代路线报告等受控反例上优于旧公式，才将它升级为正式主分。

不能声称的内容包括：

- “20 篇中的多数最终都使用 F1 排名”；
- “Fact 与 Completeness 天然就是严格的一对 P/R”；
- “引用正确性可以代替报告任务完成度”；
- “总分接近证明两个 Judge 等价”；
- “冻结环境自动保证任务侧 recall 分母完整”。
