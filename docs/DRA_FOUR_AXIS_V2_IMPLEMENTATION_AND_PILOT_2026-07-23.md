# DRA Four-Axis V2：实现与单题 Pilot

日期：2026-07-23

## 1. 本轮锁定的聚合方式

本轮没有推翻全局乘法。正式主式保持为：

\[
\mathrm{Truth}_t
=
\mathrm{Provenance}_t
\times
\frac{
\mathrm{Fact}_t+
\mathrm{Evidence}_t+
\mathrm{Completeness}_t+
\mathrm{Rubric}_t
}{4}.
\]

四个内轴等权；写作 Elo 仍独立汇报，不进入 Truth。

Fact 必须与 Resolution Rate 成对报告。Resolution Rate 不进入主式，但
禁止把高条件准确率误述为“绝大多数 claim 都已验证”。

## 2. 本轮代码改动

### 2.1 Fact：从固定十页改为按 claim 动态核验

每个外部事实 claim 依次使用：

1. 报告实际引用且属于冻结 registry 的页面；
2. 冻结搜索服务返回的合法页面；
3. 任务 evidence graph 的 seed spans；
4. 数值型商品 claim 的结构化商品查询。

任务 graph 是 seed，不再是 Fact 的世界边界。评测器新增抓取写入独立
`evaluator-fetch-ledger.jsonl`，绝不并入 agent observation ledger。

检索保留 Flare2、X10、IPX7 等带数字型号；报告断言的数值不进入第一阶段
entity-first query，避免错误数值把检索锁死。

### 2.2 有限范围负命题

claim extractor 新增 `bounded_absence`。只有同时满足以下条件，负命题才可
被判真：

- 报告给出有限页面作用域；
- 评测器获取作用域内完整页面；
- claim 明确给出待检查 literal terms；
- 冻结页面哈希和检查词写入 absence certificate。

Evidence 侧另加确定性门：search snippet 永远不能证明“完整页面没有提到
某词”。即使语义 judge 给出 support，该绑定也会以
`incomplete_scope_observation` 失败。

### 2.3 报告元话语不进入 Fact

claim schema 新增：

- `report_meta`
- `recommendation`
- `hypothetical`
- `bounded_absence`

报告章节说明、方法自述、产品选择、主观判断和假设场景不再误作外部事实
claim。

### 2.4 Evidence：保留“说得越多，审得越多”

Evidence 的 precision 分母是报告实际产生的唯一
`(claim, occurrence, citation)` 绑定；recall 分母是报告中所有
`citation_required` claim。重复写入同一绑定不会膨胀分母，但不同 claim
和不同出现位置仍分别接受审计。

\[
E_P=\frac{\text{通过绑定数}}{\text{唯一绑定总数}},
\qquad
E_R=\frac{\text{至少有一个通过绑定的需引 claim 数}}
{\text{全部需引 claim 数}},
\]

\[
\mathrm{Evidence}
=
\frac{2E_PE_R}{E_P+E_R}.
\]

任务固定的研究广度不再混入 Evidence；它只进入 Completeness。

### 2.5 Completeness：纯内容覆盖

Completeness v2 强制每个 core unit 提供 `content_covered`，不再接受旧字段
`covered` 的隐式回退。Fact 和 Evidence 只保留为
`grounded_covered` 诊断，不参与 Completeness 主分。

### 2.6 Rubric：只看 query

Rubric compiler 第一阶段只能看到 literal query，不能看到 TWM、RTS、
evidence graph、URL、答案键或报告。每个 rubric 必须绑定一个 query 中的
精确连续片段，并经过第二次 query-only entailment/answer-leak 审计。

TWM/RTS 只用于编译 Completeness research units，不能向 Rubric 输出项目。

### 2.7 观察层级修复

旧适配器此前会把 `/search` 返回体或含 `text` 字段的搜索结果误标为
`full_page`。v2 只在以下情况认定完整页：

- harness 明确写出 `observation_tier=full_page`；或
- 保留文档含 `raw_content`。

其他 `text`、`snippet`、`summary` 默认是 `search_snippet`。

## 3. DR Tulu 单题完整 Pilot

任务：`dra_v3_dev_audio_0002`

最终 v2 pilot：

| 指标 | 得分或计数 |
|---|---:|
| Provenance | 1.0000 |
| Fact | 0.9911 |
| Fact Resolution Rate | 0.7134 |
| Fact Adjudication Coverage | 0.7778 |
| Evidence | 0.6837 |
| Evidence precision | 0.6902 |
| Evidence recall | 0.6772 |
| Completeness | 0.7905 |
| Rubric | 1.0000 |
| **Truth** | **0.8663** |

重要诊断：

- 8/8 个引用 URL 属于冻结 registry，没有 fabricated URL；
- 157 个 Fact claim 中，111 true、1 false、25 unresolved、13
  out-of-world、7 instrument-ambiguous；
- 184 个唯一 citation bindings 中 127 个通过；
- Evidence 失败包含 51 unsupported、16 incomplete-scope observation、
  10 wrong-role、2 contradicted 和 1 wrong-binding；一个绑定可有多个失败原因；
- 24 个 core completeness units 中覆盖 18 个；
- 9 个 query-only rubric 全部满足；
- agent observation 中 0 个完整页面、40 个 search snippets；
- Fact evaluator 的按需 packet 实际覆盖 95 个冻结 URL，而不是原先约十个
  graph seed URL；
- 评测器留下 505 条独立搜索/抓取审计记录；
- 10 个 bounded-absence claim 中 9 个获得完整作用域证书。

初次临时运行曾得到 Evidence 0.7551。审计发现 16 个 bounded-absence
绑定错误地用 snippet 证明非出现；加入确定性完整页门后，Evidence 降至
0.6837，Truth 从 0.8842 修正为 0.8663。

## 4. LangChain ODR 定向回归

这是 Evidence 修复回归，不是完整 v2 榜单重评。

- 修正后的适配器确认：89 个 observation 全为 search snippet，full page
  为 0；
- 复用旧冻结 claims 时，45 个唯一绑定通过 11 个；
- Evidence 为 0.1375；
- 失败包含 34 unsupported、10 wrong-binding、10 wrong-role。

该结果证明搜索摘要不再冒充完整页面。由于此定向回归复用了旧 claim
schema 和旧的其他轴，不应把其 ablation Truth 当成正式 v2 总分。

## 5. 仍未满足正式榜单的条件

本次结果仍是 diagnostic pilot，原因包括：

- TWM/RTS 仍是 transition 资产，尚未完成正式冻结和替代路线证书；
- query-only rubric 尚未完成人工校准集验证；
- URL registry 尚缺每页 snapshot hash/build attestation；
- claim proposal、NLI、structural verifier 和 Fact judge 尚未做到模型族
  隔离；
- 仍有 7 个 Fact instrument-ambiguous verdict。

这些状态只影响 `formal_eligible`，不会把已经计算出的 diagnostic Truth
抹成 0。

## 6. 验证

本轮新增或更新的 scoring 回归测试共 26 个，覆盖：

- 型号数字保留；
- 引用页优先和全局替代页面；
- bounded-absence certificate；
- snippet 不能证明负命题；
- Evidence 唯一绑定去重；
- Completeness v2 严格字段；
- query-only Rubric 与 Completeness 编译隔离；
- legacy `/search` observation tier 修复。
