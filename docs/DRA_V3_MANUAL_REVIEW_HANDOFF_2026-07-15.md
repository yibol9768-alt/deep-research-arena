# DRA v3 人工审核与正式发布交接

日期：2026-07-15

这份交接把“代码可运行”和“已经具备正式发布资格”分开。程序不会替人选择 pilot、写 gold、判断 query 自然性、伪造 human oracle，或代填标注一致率。当前真实 sandbox 服务和冻结语料没有在本轮完成正式复核，因此所有人工项继续保持 `pending`；现在不能发布 v3 正式榜。

## Gate 怎么用

先生成一份空白 TODO。模板中的 `pending`、`false`、`null` 和空数组都不构成证明：

```bash
cd /root/Desktop/lyb/deep_reserch
python3 scripts/check_v3_release_readiness.py \
  --init-template \
  --out data/pilot_v3/release_readiness.json
```

每完成一阶段，把人工记录和证据文件的相对路径、SHA-256 填进该 JSON，再检查：

```bash
python3 scripts/check_v3_release_readiness.py \
  --check data/pilot_v3/release_readiness.json
```

退出码含义：

- `0`：`formal_release_eligible`，机器证据和全部人工签名都齐全；
- `2`：仍是 `code_pending` 或 `manual_pending`，这不是失败分，也不能发布；
- `1`：文档、哈希、artifact status、字段或人工证明无效。

相对 artifact 路径以 `release_readiness.json` 所在目录为基准。文件改动后必须重新计算 SHA-256。Gate 严格拒绝未知字段、哈希漂移、单纯布尔自证、缺审核人、缺签名以及不完整的 12-harness 记录。

机器证据的外层只允许文件路径和文件哈希，不再允许任意 `json_status_field` 指针：

```json
{
  "status": "passed",
  "artifact": {
    "path": "oracle-release-bundle.json",
    "sha256": "<artifact 文件的 64 位小写 SHA-256>"
  }
}
```

checker 根据 artifact 类型固定调用三套验证逻辑：formal protocol manifest schema/self-hash、`dra_v3_oracle_release_bundle_v1`、`dra_v3_harness_ledger_matrix_v1`。一个普通 `{"status":"passed"}` JSON 永远不能通过。后三者还必须绑定同一个 protocol `manifest_sha256` 和完全相同、排序稳定的 pilot-12 task IDs。

## 请按这个顺序完成人工工作

### 0. 先确认并固化权威 v2 legacy baseline

本轮开始时 v2 task、answer key、scorer 和 runner 已有未提交改动，因此代码没有擅自把当前脏工作树认定为历史权威基线。请先由你确认要保留的 v2 commit/文件状态，在干净且可追溯的副本中生成持久 manifest：

```bash
python3 scripts/freeze_v2_legacy_baseline.py \
  --out data/baselines/dra_v2_legacy_baseline.json

python3 scripts/freeze_v2_legacy_baseline.py \
  --verify data/baselines/dra_v2_legacy_baseline.json
```

该 manifest 会固定 100 个 v2 tasks、answer keys、checklists、URL registry，以及真实 v2 scoring entrypoints 的传递本地依赖闭包。选择哪一个历史状态作为权威 baseline 是版本治理决定，必须由你确认；不要在未审查的脏工作树上直接盖章。

### 1. 复核 20 个候选的真实冻结语料

生成候选审核表：

```bash
python3 scripts/prepare_v3_pilot_audit.py \
  --candidates data/pilot_v3/candidate_20.json \
  --tasks-dir data/tasks/deep_research/cross_site_deep \
  --out data/pilot_v3/corpus_audit_20.json
```

人工逐题从 product、mechanism、community、case_spec 中选择至少两个真正位于 critical path 的来源角色，确认其不可替代证据存在于同一个冻结 snapshot，并记录 evidence IDs、审核说明和审核人；未选角色要明确标为不在 critical path。decision rule 单独审核，不把四类角色强行凑成对称配额。不得沿用 v2 gold，也不得用自动 buyer-sentiment 匹配补缺失证据。审核完可运行：

```bash
python3 scripts/prepare_v3_pilot_audit.py \
  --check-audit data/pilot_v3/corpus_audit_20.json
```

在 20 题中记录 10 至 15 个证据结构合格候选，并明确选择其中恰好 12 题作为 `pilot-12`。正式 handoff 需要 20 个候选全部被归入“eligible”或“rejected/deferred”，不能漏项。

### 2. 手写 pilot-12 的 case、support span、decision rule 和 oracle

这是人工 gold authoring，不交给模型自动签字。每题至少要完成：

- 私有 CaseSpecV3；
- 对冻结 bytes 定位并复核的 support spans；
- bridge 和 decision rule；
- machine、minimal，以及所有 admissible alternative oracle 材料；
- 单页不充分、关键节点消融、唯一解或 admissible-set 检查。

先做 draft 校验：

```bash
python3 scripts/compile_case_v3.py path/to/draft.json --validate-draft
```

正式编译必须提供已验证 evidence graph、完整 corpus registry 和 discoverability/reachability 绑定。按 CLI 的实际参数逐题编译，例如：

```bash
python3 scripts/compile_case_v3.py path/to/draft.json \
  --evidence-catalog data/evidence_graph/CORPUS_SNAPSHOT/ \
  --corpus-registry data/evidence_graph/CORPUS_SNAPSHOT/corpus_registry.json \
  --reachability-manifest path/to/TASK_ID.reachability.json \
  --case-out data/golden/cases_v3/TASK_ID.json \
  --task-out data/tasks/deep_research/v3/TASK_ID.json
```

如果编译器要求显式 graph edges、support spans 或 reachability manifest，必须提供真实 artifact；不要为了让命令通过而把 critical evidence 自己声明成 discovery root。

### 3. 人工审核每个公开 query

对 renderer 输出逐题检查并签名：

- 语言自然、用户目标清楚；
- 决策优先级足以让 decision rule 可判定；
- 没有 gold 产品、gold URL、slot ID、答案或 scorer-shaped quota 泄漏；
- query constraint 与 case constraint 的机器 diff 为空。

布尔值只能记录结论；还要保存逐题 review worksheet 或 diff report，写入 `evidence` 并填审核人签名。

### 4. 建立并验证正式 protocol manifest

12 个 compiled cases 和 12 个 public tasks 都稳定后再盖章：

```bash
python3 scripts/build_v3_protocol_manifest.py \
  --graph-dir data/evidence_graph/CORPUS_SNAPSHOT \
  --case data/golden/cases_v3/TASK_01.json \
  --public-task data/tasks/deep_research/v3/TASK_01.json \
  --out data/pilot_v3/protocol_manifest.json
```

`--case` 与 `--public-task` 对其余 11 题分别重复。正式检查时改用 `--verify data/pilot_v3/protocol_manifest.json`。把 manifest 的文件 SHA-256 填进 `machine_evidence.protocol_manifest`。Manifest 必须恰好包含人工选定的 12 个 formal task IDs；多一题、少一题或换一题都会使 Gate 失败。正式 pilot-12 还必须覆盖五种 proof motif，每种 2 至 3 题。

Manifest 还会自动写入 `scorer_implementation_sha256`，绑定 CaseSpec、evidence graph、query renderer、observation ledger、protocol 校验、slot scorer 和 citation parser 的实际源码字节。上述正式实现发生变化后，旧 manifest 会明确失效，必须重新审核并盖章，不能继续沿用同一个 `verified_slots_v1` 名称混排。

### 5. 跑 machine/minimal/admissible oracle 与全部负例

每题在同一个正式 scorer 上确认：

- machine、minimal、human 和每个 admissible alternative oracle 都是 `TaskPass=1`、Verified Recall `=1`、critical contradictions `=0`、fabricated citations `=0`；
- URL dump、正确答案加 fabricated URL、fetch-all 无回答、unsupported answer、fact dump、单来源缺前提、guessed-then-fetched、错误页面绑定、矛盾 decision 和 silence 都按设计失败。

单题确定性重放入口是：

```bash
python3 scripts/score_case_v3.py \
  --case data/golden/cases_v3/TASK_ID.json \
  --report path/to/report.md \
  --ledger path/to/observation-ledger.json \
  --evidence-graph data/evidence_graph/CORPUS_SNAPSHOT/nodes.jsonl \
  --corpus-registry data/evidence_graph/CORPUS_SNAPSHOT/corpus_registry.json \
  --protocol-manifest data/pilot_v3/protocol_manifest.json \
  --public-task data/tasks/deep_research/v3/TASK_ID.json \
  --agent ORACLE_OR_ADVERSARIAL_ID \
  --replicate 1 \
  --expected-run-id RUN_ID \
  --fail-on-withhold
```

正式 case 的 discovery roots 只能来自 compiled case，禁止追加 `--seed-url`。如果提供 `--corpus-registry` 做外部核对，其 URL 集和 registry hash 必须与 case 中封存值完全相同；它不能覆盖或扩充正式 registry。

完整的 oracle/adversarial suite 应通过专用入口重放并生成 self-hashed result：

```bash
python3 scripts/validate_oracle_suite_v3.py \
  --suite path/to/TASK_ID.oracle-suite.json \
  --out data/pilot_v3/TASK_ID.oracle-validation.json \
  --pretty
```

正式 suite 的根对象必须同时用带原始文件 SHA-256 的 `case` 和
`public_task` path artifact；inline case/public task 只允许合成机制测试，
不能满足 formal exact-bytes 绑定。

12 个结果要汇总为 `dra_v3_oracle_release_bundle_v1`：包含 `status=passed`、protocol `manifest_sha256`、与 protocol 完全一致的 `task_ids`，以及 12 个 suite/result 成对引用。每项格式为 `{"suite":{"path":"...","sha256":"..."},"result":{"path":"...","sha256":"..."}}`。最后填写排除 `bundle_sha256` 字段后对 canonical JSON 计算的 self-hash。

Gate 不会只相信 result 的自哈希。它会重新读取原 suite、case、public task、report、ledger、evidence graph 和 protocol artifacts，通过正式 scorer 完整重放，并要求新结果与引用的 result canonical bytes 完全一致；随后再核对 formal scope、真实 human attestation、machine/human/minimal 核心 oracle、十类 adversarial、正负例分数契约、agent/task/run/replicate 身份和协议文件哈希。未运行、withheld、synthetic-only、漏题、漏负例、篡改 result 或只跑合成单测都不能通过。

### 6. 人工完成 human oracle

人在冻结环境中独立完成 pilot-12 的每一题，逐题填写：

- `task_id`；
- 实际耗时 `elapsed_minutes`；
- 搜索、snippet、页面 fetch 的真实 `access_path`；
- 完成时间和 reviewer note。

路径不能从 machine oracle 复制，也不能把公网浏览写成冻结环境访问。12 题要一题一个记录，并附 review artifact 与签名。

### 7. 预注册并测量双人 slot 一致率

先由人决定并登记 `preregistered_threshold`，保存带时间/版本的 preregistration artifact；本实现故意不提供默认阈值。之后由两位独立标注者对 `slot_pass_fail` 标注，保存 measurement artifact，再填写 `observed_agreement`。

正式 Gate 要求：

- 恰好两位不同 annotator；
- 两人都签名；
- threshold 和 observed 都是 `[0,1]` 数值；
- `observed_agreement >= preregistered_threshold`；
- preregistration 与实测各有一个哈希绑定 artifact。

不要在看到 observed 后反向修改 threshold；任何 artifact 变更都会造成已填哈希失效。

### 8. 审核 12 个 maintained harness

以下 12 个 lane 每个都要在至少一个正式 pilot case 上运行并单独留证：

```text
camel-ai, claude-code, deerflow, flowsearcher-ds,
gpt-researcher, ii-researcher, langchain-odr, ldr,
opencode, qx-agents, smolagents, storm
```

每个 entry 都需要 formal case ID，以及三个独立可哈希证据：完整 observation ledger、isolation audit、fetch-bypass audit。必须确认 run attribution、event order、content hash 和 `guessed_then_fetched` 可重放，不存在未披露公网旁路。

仓库现有 matrix runner 是：

```bash
python3 scripts/run_harness_smoke_matrix.py --help
```

它只有在真实服务、正式 v3 case、统一 observation ledger 和 isolation 条件都满足时，才可作为本 Gate 的正式 matrix 证据；旧 smoke 成功或进程启动成功不能替代 v3 审核。

最终 matrix 必须使用 `dra_v3_harness_ledger_matrix_v1`，带 self-hash，并绑定同一个 protocol `manifest_sha256` 和完整 pilot-12 task set。`runs` 按上面固定的 12-harness 顺序逐项记录 `harness_id`、formal `task_id`、唯一 `run_id`，以及 ledger、isolation audit、bypass audit 的 `{path, sha256}`；对应状态只能是 `complete/passed/passed`。Gate 会重新读取并哈希三个文件，不能只写三个成功布尔值。验证后再把 matrix 自身路径/哈希写到 `machine_evidence.harness_ledger_matrix`。

### 9. 完成 validation-30、CI 和公平性审核

至少 30 个验证任务运行后，分别保存并人工复核：

- validation panel/task-set artifact；
- evidence-subgraph cluster bootstrap CI；
- replicate 稳定性报告；
- 12 harness fairness audit。

四个 artifact 都要单独哈希；三个结论布尔值都为真仍不足以通过，必须有文件证据和审核签名。

### 10. 核对论文、网站、datasheet 和实现文案

逐一保存 paper、website、datasheet、scorer 和 board JSON 的版本 artifact。抽取各处最终方法公式文本，规范化后计算同一个 `method_text_sha256`，并由人核对：

- Evidence slot 为 `C_i AND B_i AND R_i AND L_i AND O_i`；
- fabricated citation 是 TaskPass 的全局阻断条件；
- real-but-unused citation 不得加分，也不阻断；
- Verified Research Completion 与 Task Solve Rate 是并列主指标；
- 不发布混合 `quality`，不把 v2 与 v3 直接比较。

五个 surface 都要填 artifact 和相同 method-text hash，最后签名。

## 当前必须保持 pending 的事项

截至这份交接创建时，本轮没有完成以下正式事实验证：

- `localhost:7770`、`:9999`、`:8090` 对应的真实 sandbox 服务可用性；
- candidate-20 所需完整冻结 corpus bytes 与证据覆盖；
- 权威 v2 legacy baseline 的 commit/文件状态与持久 manifest；
- 人工筛出的 pilot-12、手写 gold/support spans/decision rules；
- 真实 human oracle 的访问路径和时间；
- 双人标注的预注册阈值及实测一致率；
- 12 maintained harness 的正式 v3 observation/isolation/bypass matrix；
- validation-30、bootstrap CI、replicate stability、fairness audit；
- 论文、网站、datasheet、scorer 与 board JSON 的最终文案一致性。

这些是需要你或指定审核人实际完成并签名的工作。代码测试通过只能说明 gate/scorer/compiler 的行为符合约定，不能替代上述人工事实，也不能自动把模板提升为正式发布资格。
