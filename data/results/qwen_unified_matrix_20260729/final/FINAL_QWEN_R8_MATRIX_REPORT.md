# DRA 单题统一 Qwen 评分矩阵：R8 最终报告

## 1. 结论

本轮对同一道任务 `dra_v3_dev_audio_0002` 的 11 份已交付 harness
报告进行了统一评分。所有报告使用同一个冻结 Task Contract、同一个
Qwen3-8B 裁判和同一版评分代码。

- 已交付并完成评分：11/11
- 评分器失败：0
- QX-Agents：non-delivery，不进入 11 份报告的排名，也不记为 0 分
- Qwen-only 证书：11/11 通过
- 冻结 Task Contract 哈希：11/11 一致
- 最终 score 与矩阵汇总：11/11 一致
- claim ledger 与 fact-packet 哈希链：11/11 一致

这是单题 retrospective diagnostic ranking，不是 56 题正式总榜。
所有运行的 `formal_truth` 仍为 `null`、`formal_eligible=false`。

## 2. 当前合成方式

本轮实际执行的公式是：

```text
Quality = (Fact + Evidence + Completeness + Rubric) / 4
Truth_diagnostic = Provenance × Quality
```

其中：

- Provenance 检查引用 URL 是否规范化、在冻结 registry 中且有快照；
- Fact 只在可裁决 claim 中计算真假，必须和 Resolution Rate 成对阅读；
- Evidence 是引用绑定 precision 与有证据 claim recall 的调和平均；
- Completeness 对任务研究单元按 facet × unit type 分组后宏平均；
- Rubric 只检查任务遵循要求；
- Provenance 继续作为报告级乘法项。

## 3. 最终 Truth 排名

| 排名 | Harness | Truth | Provenance | Fact | Resolution | Evidence | Completeness | Rubric | Quality |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | GPT-Researcher | 0.6728 | 1.0000 | 1.0000 | 0.4793 | 0.5813 | 0.5099 | 0.6000 | 0.6728 |
| 2 | STORM | 0.6713 | 1.0000 | 1.0000 | 0.1000 | 0.3705 | 0.4147 | 0.9000 | 0.6713 |
| 3 | OpenCode | 0.6535 | 1.0000 | 1.0000 | 0.4492 | 0.0167 | 0.5972 | 1.0000 | 0.6535 |
| 4 | Claude Code | 0.6214 | 1.0000 | 0.9583 | 0.2017 | 0.0331 | 0.4940 | 1.0000 | 0.6214 |
| 5 | LDR | 0.5498 | 1.0000 | 1.0000 | 0.2432 | 0.5383 | 0.6607 | 0.0000 | 0.5498 |
| 6 | LangChain ODR | 0.5323 | 0.8333 | 0.9855 | 0.3920 | 0.4757 | 0.2937 | 0.8000 | 0.6387 |
| 7 | II-Researcher | 0.5029 | 1.0000 | 1.0000 | 0.3148 | 0.0922 | 0.3194 | 0.6000 | 0.5029 |
| 8= | CAMEL | 0.0000 | 0.0000 | 1.0000 | 0.2124 | 0.0000 | 0.4167 | 0.4000 | 0.4542 |
| 8= | DeerFlow | 0.0000 | 0.0000 | 1.0000 | 0.4250 | 0.0000 | 0.3433 | 1.0000 | 0.5858 |
| 8= | SmolAgents | 0.0000 | 0.0000 | 0.9412 | 0.2656 | 0.0000 | 0.2540 | 1.0000 | 0.5488 |
| 8= | MiroFlow | 0.0000 | 0.0000 | 1.0000 | 0.3491 | 0.0000 | 0.2183 | 0.8000 | 0.5046 |

GPT-Researcher 与 STORM 的差值只有 0.0015。对于尚未完成人工校准和
正式资格认证的单题诊断分，不应把这个差值解释为稳定的能力胜负。

四个 Provenance 为 0 的 harness 在 Truth 上并列；表中排列不构成它们
之间的优劣顺序。它们的 Quality 仍保留，便于诊断“内容写了多少”与
“URL 完整性失败”之间的区别。

## 4. 读分时必须注意的现象

### Fact 必须与 Resolution Rate 同报

多个报告的 Fact 接近 1，但 Resolution Rate 只有 0.10–0.48。这表示：
在当前证据语料中成功裁决的 claim 大多为真，不表示整份报告的所有
claim 都已被证明。

### Evidence 不会单独门控当前 Truth

OpenCode 的 Evidence 只有 0.0167，但 Completeness、Rubric 和 Fact 较高，
因此等权平均后的 Truth 仍为 0.6535。这不是运行错误，而是当前冻结公式
允许各质量轴互相补偿的直接结果。是否增加 Evidence 门槛应作为后续公式
实验处理，不能在看到本轮结果后临时改分。

### Provenance 是全局乘法项

CAMEL、DeerFlow、SmolAgents 和 MiroFlow 的 Provenance 为 0，所以
Truth 归零。它们没有被当作 non-delivery；其 Fact、Completeness、
Rubric 和 Quality 仍完整保留。

## 5. 本轮修复并冻结的评分器行为

1. claim 原文由程序按报告 segment 精确锚定，不再让裁判复制原文；
2. Fact、Evidence 和 Completeness 使用 JSON Schema、动态批处理和失败二分；
3. 完整页面切成可回溯 span，Evidence 只投影少量 claim 相关窗口；
4. claim 去重先做确定性同文去重，再做保守的 pairwise 语义去重；
5. 不同主体、型号、数字、语气、否定、条件、来源归因和范围不得合并；
6. 加入 CJK 双字片段与中文语气、否定、条件、并列边界；
7. QX-Agents 缺少报告、trace 和 citation map 时记录为 non-delivery。

相关回归测试：

- 本地相关测试：64 passed
- 远端关键测试：33 passed

## 6. 完整性审计

逐 harness 审计以下条件，11 份均通过：

- `qwen_only_certificate.passed == true`
- 所有非空裁判模型字段均为 `qwen3-8b`
- `shared_task_contract_reused == true`
- `report_generator_unchanged == true`
- `task_contract_sha256` 均为
  `3d734c061b43c4a89f6774b62fc692ca52acce93b5caec2c36f9633468edc2cc`
- manifest、score 和矩阵汇总中的各轴数值一致
- claim-ledger 与 fact-packet 哈希在 manifest 和 score 间一致
- 11 份 controlled score 均存在
- scorer failure 数量为 0

## 7. 产物位置

- `harness-matrix-qwen3-8b-shared-contract-r8/matrix-summary.json`
- `harness-matrix-qwen3-8b-shared-contract-r8/matrix-progress.json`
- 每个 harness 的 `unified-qwen-run-manifest.json`
- 每个 harness 的 `03-qwen-controlled-score/score.json`
- 每个 harness 的完整 claim、Fact、Evidence、Completeness、Rubric、
  observation ledger 与 judge-call 审计目录
- `harness-matrix-qwen3-8b-shared-contract-r8.log`

下一阶段若扩展到 56 题，必须保持本轮协议和代码快照不变；单题分先按
task 聚合，再按 harness 汇总，并继续把 non-delivery、scorer failure 和
正式资格状态与 Truth 分开报告。
