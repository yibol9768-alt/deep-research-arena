# DRA v3 人工治理的 Query 生成流程

日期：2026-07-16  
流程版本：`human_query_pipeline_v1`  
适用范围：Route B graph-native v3 题目  
规范依据：`DRA_V3_EVIDENCE_GRAPH_REDESIGN_PLAN_2026-07-15.md`

## 1. 这套流程解决什么问题

正式 query 不能再由交互式 Codex 会话边查、边猜、边改，然后把结果直接当 gold。Codex 可以维护流程代码、补测试和排查错误，但不得充当正式题目的来源选择者、gold 标注者、few-shot 作者、语义裁决者或盲审人。

正式数据链固定为：

```text
人选择研究目标和来源
  -> 程序按清单采集并冻结网页 bytes
  -> 人审核 support span、proposition 和来源范围
  -> 程序编译 evidence graph 和 Case Spec
  -> 人审核 proof steps 与 GeneratorView，另一人裁决
  -> 三道 development 题由人写 query，另一人裁决，冻结为 few-shot
  -> 注册且版本固定的普通 LLM 只看 GeneratorView 和三个 few-shot
  -> 程序做硬规则检查
  -> 独立的人只看 GeneratorView 和 query 做盲审
  -> 程序冻结全部尝试历史和发布证书
  -> 正式编译器写出 private case 和 public task
```

LLM 在这里仅承担“把已经批准的公开结构改写成自然语言”这一项工作。事实是否成立、span 是否正确、proof step 是否必要、query 是否忠实，都不由 LLM 自己批准。

## 2. 三条不可绕过的边界

1. `GeneratorView` 之前是 gold 构建阶段。来源、证据、proof DAG 和答案合同必须先完成，之后才能生成 query。
2. query renderer 只能收到目标 `GeneratorView`，以及恰好三个 `(GeneratorView, HumanWrittenQuery)`。不能收到 URL、evidence、proof steps、oracle、答案或 scorer 字段。
3. 没有人工证据审核、独立图裁决、人工 few-shot、注册模型原始响应、连续重试历史和独立盲审，就不能生成 `approved_for_formal_compile` 证书。

## 3. 人和程序分别负责什么

| 环节 | 人负责 | 程序负责 | LLM 是否有正式决定权 |
|---|---|---|---|
| 选题与选源 | 写研究目标、来源角色、选择 URL、说明理由 | 校验角色数量、URL 身份和清单完整性 | 无 |
| 采集 | 不复制网页正文 | 按批准清单搜索、抓取、冻结 bytes、记录哈希和观察日志 | 无 |
| evidence 提案 | 可手工写；自动方法只能提案 | 校验 byte offset、span hash、typed graph 和 corpus membership | 无 |
| 冻结证据审核 | 阅读网页快照与上下文，逐项判断 | 生成离线 HTML、导入决定、输出 gate report | 无 |
| proof DAG 与 GeneratorView | 标注必要性、依赖、删除测试、公开投影 | exact coverage、hash binding、schema 校验 | 无 |
| development few-shot | 人写自然 query，另一人裁决 | 只保留公开二元组，检查三个不同任务和 motif | 无 |
| 目标 query | 不手工润色正式输出 | 固定 prompt 调注册 API，保存请求和原始响应 | 仅生成候选文本 |
| query 验收 | 独立盲审四项语义 | 检查约束、选项、URL、泄漏、重试历史 | 无 |
| 发布 | 人完成后续 human oracle | 编译 case/task、绑定所有 SHA-256 | 无 |

`actor_id` 和 attestation 是可审计声明，不是生物识别或密码学身份证明。正式标注批次还应冻结 reviewer roster，并由指定人员通过各自账号提交或签署审核 artifact。程序负责拒绝角色冲突和内容篡改，项目管理负责确认账号确实属于该人。

## 4. 推荐目录

每个候选题单独保存，不覆盖旧候选题：

```text
data/pilot_v3/query_pipeline/<candidate_id>/
  01_source_selection.json
  02_capture_plan.json
  capture/
  inventory.json
  graph/
  evidence_review_packet/
  03_evidence_review_decisions.json
  04_evidence_review_gate.json
  case_draft.json
  reachability.json
  05_graph_annotation.json
  prompt_inspection.json
  attempt_1.generation.json
  attempt_1.blind_packet.json
  attempt_1.blind_review.json
  attempt_1.closed.json
  query_release.json
```

三个 development few-shot 使用单独目录，不能放入正式测试分母：

```text
data/pilot_v3/query_pipeline/dev_few_shots/
  example_1.json
  example_2.json
  example_3.json
  dataset_approver.json
  manual_dev_three_motifs_v1.json
  renderer_config.json
```

## 5. 阶段 A：人先选来源，程序再采集

### A1. 生成人工选源表

```bash
python3 scripts/v3_query_pipeline.py init-source-selection \
  --candidate-id <candidate_id> \
  --corpus-snapshot <snapshot_id> \
  --run-id <run_id> \
  --out <workdir>/01_source_selection.json
```

人编辑这个文件，至少填写：

- `research_goal`：本题要解决的研究决策，不能先写答案。
- `selected_by.actor_id` 和 `selected_at_utc`。
- `source_requirements`：例如 product、mechanism、community 各自为什么必要。
- `searches`：实际搜索词、域名范围和搜索中确认的 URL。
- `selected_sources`：最终要冻结的 URL、来源角色和选择理由。
- `source_identity`：本次使用的冻结搜索服务或语料身份。

每个选中的 URL 必须出现在某条 `searches.required_urls` 中。这样可以证明它来自记录过的搜索，而不是事后把 gold URL 塞进题目。

### A2. 编译并执行采集计划

```bash
python3 scripts/v3_query_pipeline.py capture-plan \
  --selection <workdir>/01_source_selection.json \
  --out <workdir>/02_capture_plan.json

python3 scripts/capture_v3_candidate_sources.py \
  --plan <workdir>/02_capture_plan.json \
  --out <workdir>/capture

python3 scripts/capture_v3_candidate_sources.py \
  --verify <workdir>/capture
```

采集程序只访问清单中的来源，保存搜索响应、fetch 响应、正文 blob、内容哈希和 observation log。人不应该把浏览器复制出来的文本直接贴进 gold。

## 6. 阶段 B：构造 graph 提案并做人审

### B1. inventory 是提案，不是 gold

从冻结 capture 构造 `evidence_graph_inventory_v1`，其中包含 documents、nodes、edges 和 support spans。结构化字段可由确定性代码产生；自然语言 assertion/proposition 可以人工写，也可以由另一个注册提案模型提出，但自动输出只能标为 proposal。

当前正式流程不允许 Codex 会话直接把 `build_inventory.py` 中的硬编码内容视为人工 gold。若暂时没有注册 extraction proposal 服务，这一步就由人编辑 `inventory.json`。后面的冻结网页审核会逐项检查它。

编译 graph：

```bash
python3 scripts/build_evidence_graph.py \
  --inventory <workdir>/inventory.json \
  --blob-root <workdir>/capture \
  --out-dir <workdir>/graph
```

### B2. 生成人能阅读的网页快照审核包

```bash
python3 scripts/build_v3_review_packet.py \
  --inventory <workdir>/inventory.json \
  --snapshot-root <workdir>/capture \
  --out-dir <workdir>/evidence_review_packet
```

人工打开：

```text
<workdir>/evidence_review_packet/index.html
```

审核页展示冻结英文 bytes、精确高亮 span、前后文、拟议 proposition、来源身份和内容哈希。实时网页只能辅助确认来源身份，不能覆盖冻结快照。中文翻译只用于理解，也不能替代英文冻结证据。

人逐项填写：

- span 是否截取正确；
- proposition 是否真的被原文支持；
- 来源范围是否被夸大；
- 上下文是否充分；
- 整个候选是 eligible、reject 还是 revise_scope。

网页导出 `03_evidence_review_decisions.json` 后执行：

```bash
python3 scripts/import_v3_review_decisions.py \
  --review-packet <workdir>/evidence_review_packet \
  --decisions <workdir>/03_evidence_review_decisions.json \
  --authority human \
  --out <workdir>/04_evidence_review_gate.json
```

只有 gate 的 `status` 为 `eligible_for_case_generation`，且 blocker 为空，才能继续。`llm_simulation` 永远不能晋级正式 gold。

## 7. 阶段 C：人审 proof DAG 和 GeneratorView

先用现有 motif compiler 生成 `case_draft.json` 和 `reachability.json`。随后把已通过的证据审核自动导入图标注表：

```bash
python3 scripts/v3_query_pipeline.py init-annotation \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --candidate-id <candidate_id> \
  --evidence-review-gate <workdir>/04_evidence_review_gate.json \
  --out <workdir>/05_graph_annotation.json
```

证据项已经从人审 gate 导入。图标注者还要逐个填写：

- `proof_steps[].necessary`：是否为解决 query 所必需；
- `dependencies_correct`：依赖是否正确；
- `verifier_contract_clear`：程序是否能够按合同验证；
- `deletion_test`：删除关键证据后，结论是否改变或变为 unresolved；
- `necessity_rationale`：为什么这个 step 不能删；
- `generator_view_review`：公开场景、约束、选项和目标是否完整、忠实且不泄漏 gold。

然后由另一位人填写 `adjudicator`、`adjudicated_at_utc` 和裁决说明。图标注者与裁决者 ID 必须不同。

```bash
python3 scripts/v3_query_pipeline.py validate-annotation \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json
```

任何 evidence ID、span ID、step ID、case hash、GeneratorView hash 或 graph hash 不一致都会失败。

## 8. 阶段 D：冻结三个人工 few-shot

三个示例必须来自 development subset，覆盖三个不同 graph motif，且不得进入正式测试分母。

对每个 development case 执行：

```bash
python3 scripts/v3_query_pipeline.py init-few-shot-example \
  --case <dev_case.json> \
  --graph-dir <dev_graph_dir> \
  --annotation <dev_graph_annotation.json> \
  --example-id <example_id> \
  --out <example.json>
```

人只根据表内的 `generator_view` 写 `human_written_query`，填写作者 ID 和时间。另一位人独立检查后填写 adjudicator ID、时间和 `adjudication_note`。作者与裁决者必须不同。

`dataset_approver.json` 的格式为：

```json
{
  "actor_type": "human",
  "actor_id": "<human_id>",
  "role": "few_shot_adjudicator",
  "attestation": "human_completed_without_model_substitution"
}
```

冻结三个示例：

```bash
python3 scripts/v3_query_pipeline.py build-few-shots \
  --case <dev_case_1.json> --graph-dir <dev_graph_1> --annotation <dev_ann_1.json> --example <example_1.json> \
  --case <dev_case_2.json> --graph-dir <dev_graph_2> --annotation <dev_ann_2.json> --example <example_2.json> \
  --case <dev_case_3.json> --graph-dir <dev_graph_3> --annotation <dev_ann_3.json> --example <example_3.json> \
  --dataset-id manual_dev_three_motifs_v1 \
  --approved-by <dataset_approver.json> \
  --out <few_shot_dataset.json>
```

传给模型时，每个示例会被程序再次裁剪成且仅成：

```json
{
  "generator_view": {},
  "human_written_query": "..."
}
```

作者、任务 ID、图哈希和审批信息只保存在 provenance 中，不进入模型 prompt。

## 9. 阶段 E：注册 LLM 并生成 query

### E1. 冻结模型配置

```bash
python3 scripts/v3_query_pipeline.py init-renderer-config \
  --renderer-id <renderer_id> \
  --base-url <openai_compatible_base_url> \
  --model <versioned_model_name> \
  --model-revision <pinned_revision> \
  --api-key-env DRA_QUERY_RENDERER_API_KEY \
  --seed 7 \
  --out <renderer_config.json>
```

规则固定为 `temperature=0`、非流式、固定 seed、固定 max tokens。`latest`、`default`、`unknown`、`unversioned` revision 会被拒绝；模型名含 `codex` 也会被拒绝。API key 只从环境变量读取，不进入 artifact。

### E2. 先检查模型将看到什么

```bash
python3 scripts/v3_query_pipeline.py build-prompt \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json \
  --few-shots <few_shot_dataset.json> \
  --out <workdir>/prompt_inspection.json
```

这里应该只有三个公开 few-shot 和目标 `GeneratorView`。出现 URL、proof step、evidence 或答案字段时必须停止。

### E3. 第一次生成

```bash
python3 scripts/v3_query_pipeline.py generate \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json \
  --few-shots <few_shot_dataset.json> \
  --model-config <renderer_config.json> \
  --attempt 1 \
  --out <workdir>/attempt_1.generation.json
```

generation record 保存完整 prompt/request 哈希、模型配置、原始 API 响应 bytes 的 base64 与 SHA-256、抽出的 query 和硬规则结果。

硬规则检查：

```text
ConstraintCoverage
AND OptionCoverage
AND NoURL
AND NoScorerTerms
AND NoAnswerLeak
```

硬规则失败时不做人审，直接关闭为 retry：

```bash
python3 scripts/v3_query_pipeline.py close-attempt \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json \
  --few-shots <few_shot_dataset.json> \
  --generation <workdir>/attempt_1.generation.json \
  --out <workdir>/attempt_1.closed.json
```

## 10. 阶段 F：只看公开信息的人工盲审

硬规则通过后生成盲审包：

```bash
python3 scripts/v3_query_pipeline.py blind-packet \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json \
  --few-shots <few_shot_dataset.json> \
  --generation <workdir>/attempt_1.generation.json \
  --packet-out <workdir>/attempt_1.blind_packet.json \
  --review-template-out <workdir>/attempt_1.blind_review.json
```

盲审人只能拿到 `blind_packet.json`，不能拿 case gold、graph、annotation 或 oracle。盲审人判断：

- faithful：是否忠实覆盖 GeneratorView；
- natural：是否像自然研究问题；
- closed_environment_answerable：冻结环境是否能回答；
- requires_multi_branch_research：是否确实需要多分支研究。

盲审人填写模板后关闭 attempt：

```bash
python3 scripts/v3_query_pipeline.py close-attempt \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json \
  --few-shots <few_shot_dataset.json> \
  --generation <workdir>/attempt_1.generation.json \
  --blind-review <workdir>/attempt_1.blind_review.json \
  --out <workdir>/attempt_1.closed.json
```

盲审人不能是目标题的 graph annotator 或 graph adjudicator。

## 11. 重试合同

盲审失败或硬规则失败后，下一次必须显式携带此前的 closed attempt：

```bash
python3 scripts/v3_query_pipeline.py generate \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json \
  --few-shots <few_shot_dataset.json> \
  --model-config <renderer_config.json> \
  --attempt 2 \
  --prior-attempt <workdir>/attempt_1.closed.json \
  --out <workdir>/attempt_2.generation.json
```

第 3 次需要同时传 `attempt_1.closed.json` 和 `attempt_2.closed.json`，顺序不能乱。程序强制：

- attempt 必须从 1 连续递增；
- 只有 `retry_required` 才能继续；
- renderer config 不能在重试中更换；
- 时间必须递增；
- 第 3 次仍失败时 disposition 为 `discarded`；
- 不能只保留最后一次成功结果，隐藏前两次失败。

## 12. 发布证书与正式编译

最终 attempt 为 accepted 后，将全部尝试按顺序传入：

```bash
python3 scripts/v3_query_pipeline.py release \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --annotation <workdir>/05_graph_annotation.json \
  --few-shots <few_shot_dataset.json> \
  --attempt <workdir>/attempt_1.closed.json \
  --out <workdir>/query_release.json

python3 scripts/v3_query_pipeline.py validate-release \
  --case <workdir>/case_draft.json \
  --graph-dir <workdir>/graph \
  --release <workdir>/query_release.json
```

如果成功发生在第 2 或第 3 次，`release` 命令必须依次重复所有 `--attempt`。

正式编译：

```bash
python3 scripts/compile_case_v3.py <workdir>/case_draft.json \
  --evidence-catalog <workdir>/graph \
  --reachability-manifest <workdir>/reachability.json \
  --query-release-certificate <workdir>/query_release.json \
  --case-out data/golden/cases_v3/<task_id>.json \
  --task-out data/tasks/deep_research/v3/<task_id>.json
```

private case 的 `formal_bindings` 会记录：

```json
{
  "query_authoring_policy": "human_query_pipeline_v1",
  "query_release_sha256": "<sha256>"
}
```

这一步只发布 query。题目仍需通过 machine oracle、human oracle、minimal oracle、adversarial baselines 和最终 release gate，才能称为正式完成。

## 13. 现有 57 道题如何处理

现有文件全部保留，不删除、不覆盖，原评分方案也继续保留。它们当前是 legacy candidates，不能因为有 graph JSON 和一个 query 文本就自动宣称为人工批准的正式 gold。

回填时逐题执行：

1. 复用并验证已有 capture 和 graph，不重复抓取相同 snapshot。
2. 生成冻结证据审核网页，由人完成 evidence review。
3. 生成新的 graph annotation，由另一人裁决 proof DAG 和 GeneratorView。
4. 使用同一个已冻结的三条人工 few-shot 数据集和同一个 renderer config 重新生成 query。
5. 独立盲审，生成 query release certificate。
6. 通过 oracle 和 release gate 后，才从 candidate 晋级。

旧 query 可以保留作对比分析，但不能悄悄变成 few-shot，也不能冒充新流程输出。

## 14. 状态名称必须统一

| 已有 artifact | 可以称为什么 | 还不能称为什么 |
|---|---|---|
| capture + graph manifest | structurally compiled candidate | 人工 gold |
| eligible evidence review gate | human-reviewed evidence candidate | query 已批准 |
| approved graph annotation | human-approved case semantics | 正式发布题 |
| query release certificate | human-governed query candidate | 完整 formal task |
| formal compile + 全部 oracle/release gates | released formal task | 无 |

这样论文、网页和内部进度不会再把“Codex 写出了文件”“schema 通过”“人审完成”“正式发布”混成同一个完成状态。

## 15. 对应代码

- `src/tasks/human_query_pipeline_v3.py`：人工身份、选源、图标注、few-shot、注册模型、尝试历史、盲审和发布证书 schema。
- `scripts/v3_query_pipeline.py`：上述各阶段 CLI。
- `scripts/capture_v3_candidate_sources.py`：清单驱动的冻结采集。
- `scripts/build_v3_review_packet.py`：冻结网页快照审核 UI。
- `scripts/import_v3_review_decisions.py`：人工审核决定的 fail-closed 导入。
- `scripts/compile_case_v3.py`：消费 query release certificate 的正式编译器。
- `src/tasks/query_renderer_v3.py`：GeneratorView 投影、硬规则和泄漏检查。
- `tests/test_v3_human_query_pipeline.py`：人审、few-shot 隔离、非 Codex 模型、盲审独立性、证书重放和正式编译集成测试。
