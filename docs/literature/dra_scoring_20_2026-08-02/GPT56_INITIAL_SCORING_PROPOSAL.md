# GPT-5.6 初始评分方案

模型：GPT-5.6 Sol，高推理档
角色：在 Kimi 独立评审前提出候选方案，供后续交叉质疑
状态：候选，不是最终规范

## 1. 核心裁决

不建议把当前四轴直接改名成 precision / recall。更有可解释性的候选主分是：

> 对报告 claim 先做事实、证据、引用和执行来源的逐项合取，得到 Grounded Claim Precision；再与路线无关的 Grounded Research Recall 计算 F1。Fact、Evidence、Completeness、Rubric、Provenance 继续作为诊断字段，写作质量与任务格式遵循独立报告。

## 2. 为什么报告级乘法不够精确

报告级：

\[
Truth=Provenance\times Quality
\]

无法确定两个错误是否发生在同一个 claim 上。十个 claim 中，如果 Fact 与 Provenance 都是 0.9：

- 两个失败落在同一个 claim 上，联合正确且有来源的 claim 是 9 个；
- 两个失败落在不同 claim 上，联合通过只有 8 个；
- 报告级乘法在两种情况下都得到 0.81。

所以合取应尽量下沉到 claim/binding 层，再聚合。

## 3. Claim-gated Grounded F1

### 3.1 Eligible claim 集合

对报告抽取并语义去重后的实质性 claim 集合记为 \(C_t\)。元陈述、纯写作连接、主观偏好和不要求外部事实的分析不进入外部事实 claim 分母。决定性推荐的外部前提仍进入。

对每个 claim \(c\)：

\[
f_c\in[0,1]
\]

表示它相对于冻结世界的事实正确性。

### 3.2 Citation binding 与 observation gate

对绑定到 claim 的引用集合 \(J_c\)，每条引用判断：

\[
b_{c,j}=
RegistryValid
\land LegalDiscovery
\land Observed
\land LocalBinding
\land Supporting
\land RoleAppropriate
\]

同时判断全部引用联合起来是否完整支持 claim：

\[
A_c\in\{0,1\}
\]

定义：

\[
e_c=A_c\cdot\frac{\sum_{j\in J_c}b_{c,j}}{|J_c|}
\]

它防止一条好引用加大量无关引用仍得满分，也允许多条引用共同支持复合 claim。

若 claim 不需要外部证据，例如纯逻辑推导或用户约束的直接推论，令 \(e_c=1\)。关键商品事实、数字、争议机制、社区经验和决定性推荐前提仍要求证据。

逐 claim grounded correctness：

\[
g_c=f_c e_c
\]

### 3.3 Grounded Claim Precision

\[
P_t=\frac{1}{|C_t|}\sum_{c\in C_t}g_c
\]

它回答：报告主动提出的实质性内容，有多少同时正确、证据充分并能归因到本次运行。

### 3.4 Grounded Research Recall

每道题在看到被测报告前冻结路线无关的必要研究单元 \(U_{t,d}\)，按比较、机制、社区证据、冲突综合、教程、预算和推荐等研究维度分组。

单元只有在内容完成，且需要外部核验的关键前提有本次观察证据时才通过：

\[
R_{t,d}=\frac{\sum_{u\in U_{t,d}}z_u}{|U_{t,d}|}
\]

\[
R_t=\frac{1}{|D_t|}\sum_{d\in D_t}R_{t,d}
\]

先在维度内平均，再在维度间平均，可以避免容易拆成大量小项的维度支配整道题。

### 3.5 主分

\[
DRA\text{-}GF1_t=
\frac{2P_tR_t}{P_t+R_t}
\]

当 \(P_t+R_t=0\) 时记为 0。

主分的一句话含义是：

> 报告提出的实质性内容有多少真正可信，以及任务要求的研究工作有多少真正完成。

## 4. 为什么暂不使用 \(F_2\)

若强调 Deep Research 广度，可定义：

\[
F_{\beta,t}=(1+\beta^2)
\frac{P_tR_t}{\beta^2P_t+R_t}
\]

但在 \(P=0.5,R=1\) 时：

- \(F_1=0.667\)；
- \(F_2=0.833\)。

这会让覆盖很广但一半内容不可信的报告过高。除非人工偏好实验支持，否则主榜使用无参数的 \(F_1\)，并同时展示 \(P\) 与 \(R\)。

## 5. URL 错误的处理

| 类型 | Claim/binding 处理 | Research recall | 独立诊断 |
|---|---|---|---|
| `fabricated_url` | 对应 \(b_{c,j}=0\) | 该证据路线不能完成单元 | `integrity_clean=false` |
| `unobserved_citation` | \(b_{c,j}=0\) | 不算 grounded coverage | 单独报告 |
| `unsupported_citation` | \(b_{c,j}=0\) | 对应单元不能靠它通过 | Citation Precision 下降 |
| `wrong_binding` | \(b_{c,j}=0\) | 对应 claim 不通过 | 单独报告 |
| `contradicted_citation` | \(f_c=0,b_{c,j}=0\) | 若为必要单元则 recall 失败 | critical error |
| 仅搜索 snippet、未抓完整页 | 默认 `Observed=0` | 不算完整证据 | ProofOfFetch 诊断 |

伪造 URL 不建议把数值能力分直接清零，因为这会把一份整体很强但含一次 URL 错误的报告和空报告都变成 0。候选排行榜规则是：

1. 数值主分照常计算；
2. `integrity_clean=false` 明确显示；
3. clean leaderboard 排除含 fabricated URL 的报告，或保证所有 clean 报告排在 tainted 报告之前。

## 6. 宏平均层级

1. citation 内先算 binding 判断；
2. claim 内做事实与证据合取；
3. 单题内计算 \(P_t\)；
4. 必要单元先在研究维度内平均，再在维度间平均得到 \(R_t\)；
5. 单题计算 \(F_{1,t}\)；
6. 最后对任务宏平均；
7. 若题目在主题或原型上不均衡，再报告 topic × archetype 分层宏平均；
8. 置信区间按主题簇 bootstrap。

不应将整个基准的 claim 做 micro-average，否则长报告和 claim 多的题会支配榜单。

## 7. Unresolved 与 census gap

未裁决项不能静默算错，也不能从分母删除。建议计算区间：

\[
P_t^{low}=\frac{\text{已确认通过}}{|C_t|}
\]

\[
P_t^{high}=\frac{\text{已确认通过}+\text{未裁决}}{|C_t|}
\]

Recall 同理，再得到 F1 上下界。正式发布同时展示：

- Resolution Rate；
- F1 区间宽度；
- census gap 数量。

可裁决率过低时暂缓正式分。

## 8. 诊断面板

原轴保留但不再等权相加：

- Fact：\(\operatorname{mean}(f_c)\)，说明报告说得对不对；
- Evidence：Citation Precision、Citation Recall、Citation F1 与失败类型；
- Completeness：\(R_t\)，说明必要研究工作完成多少；
- Rubric：仅保留语言、格式、预算形式、明确推荐等纯任务遵循；
- Provenance：URL registry、legal discovery、observation ledger 与 integrity；
- Resolution Rate：评分器对该报告能裁决多少；
- 主分：\(DRA\text{-}GF1\)。

写作质量继续 pairwise Elo，但不与绝对比例相加或相乘。如果必须给唯一排序，候选字典序为：

\[
(IntegrityClean,\ DRA\text{-}GF1,\ InstructionFollowing,\ WritingElo)
\]

## 9. 必须验证的最大风险

最大的挑战不是 F1 公式，而是 recall 分母。必须证明任务侧 necessary research unit census：

- 在看到被测报告之前已冻结；
- 每个单元确实必要而不是写作者偏好；
- 冻结环境中可回答；
- 不绑定预先选择的 URL；
- 接受合理替代研究路线；
- 对新增真实 claim 与负命题有稳定处理；
- 删除测试、替代路线测试和受控扰动测试均通过。

在这些条件未完成前，\(DRA\text{-}GF1\) 只能作为候选诊断，不能直接替换正式 Truth。
