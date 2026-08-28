# Biodiversity Q1 自动评分系统

这不是人工逐条打分脚本。它把一个 Harness 格的报告和本次检索证据转换成完整的 judgment packet，再交给 Q1 包绑定的确定性 GATE-TRUTH 实现计算 Citation Binding、GCP 和 GRR。

## 固定链路

1. 验证 Q1 evaluation package 全部引用文件的 SHA 和字节数。
2. 验证 run manifest，区分正常空报告与 Harness/环境失败。
3. 从报告提取带 exact substring 锚点的 material claims，代码重新分配 `C001…` ID。
4. 从 strict-evidence ledger 重建 search→fetch 法定发现链，验证 URL、page SHA、blob SHA 和 observation tier。
5. 固定 Judge 一次性判定 claim truth、citation binding 和 34 项 IU coverage。
6. 代码再验证 Judge 所有 exact quotes、ID 闭包、证据 ID、引用本次观测与 34 项分母。
7. 输出 `judgment-packet.json` 和 `shadow-score.json`，封存 Judge 请求/响应、实际模型身份、usage、HTTP、延迟和 SHA。

Judge 返回 429/5xx 或传输错误时最多独立重试一次。连续失败、非 JSON、Schema 不合法、实际模型身份不符或 usage 缺失都会 fail closed 为 `withheld`，不会写成 0 分。

`finish_reason=length` 是独立的截断失败，记为
`withheld_judge_truncated`。每次 Judge metadata 都保留
`finish_reason`、`content_chars`、`reasoning_content_chars`、usage 和延迟；
即使 HTTP 200，截断或 malformed JSON 也不会变成 0 分。

## 长报告分批

- Claim extraction 按空行、换行或安全句子边界确定性分批，默认每批最多
  1200 字符；所有批次逐字拼回必须等于原报告。若一段内容本身超过
  1200 字符，评分器只在可验证的安全边界切分；不存在安全边界时直接
  fail closed，不截断文本、不发超限请求。
- 单个 extraction 批次的 Schema 最多接受 64 claims；全局聚合后使用
  512 claims 的完整 Schema，以容纳正式首格实测的 260 项高召回原子 claim。
  超限仍然 withheld，不截断 claim 列表。
- Citation 只能属于唯一批次，保留全局 `CITE###`。Claim quote 必须在它的
  当前批次中严格 substring 命中，quote repair 也不得跨批次找文本。
- 对 DeerFlow 报告的 `[[n]](#ref-n)`，评分器先从文末 `<a id="ref-n">`
  定义解析真实 URL，再把正文锚点本身登记为 citation occurrence；因此
  `start/end/local_context` 位于 claim 所在正文段，而不是 Key Citations 或
  References 列表。引用定义缺失、编号不一致或同一 ref 指向冲突 URL 时，
  该正文锚点保留为 invalid citation candidate，使 Citation Binding 失败，
  不会被误写成 scorer infrastructure withheld。
- 批次结果按全局 quote 位置稳定聚合，再统一分配 `C001…`。聚合后仍执行
  完整 Schema 和 citation 闭包检查。
- Claim/binding adjudication 默认每批最多 4 claims 且 12 bindings；
  completeness adjudication 每批 2 个 IU。各批的 ID 闭包先独立验证，
  然后再聚合为冻结的全部 34 IU。
- 任意一批失败都使整格 withheld，不使用局部 claims、局部 IU 或已完成批次伪造分数。
- 所有批次的 Judge usage 都进入同一成本总账；Judge 成本仍与 Agent LLM
  成本分开。

## 重要口径

- GRR 分母永远是包内完整 34 项；少一项直接拒绝评分。
- GCP 跟随冻结实现，按 eligible claim 数量而非临时 materiality weight 计算。
- Citation Binding 只在 URL 有效、本次合法发现且 fetch、局部绑定、语义支持、role 合适全部通过时计分。
- 无临时综合分；`formal_eligible=false`，仅输出 shadow 向量。
- Judge 成本单列，不进入 Agent LLM 成本轴。
- 每次 Judge 调用保留模型身份、输入/输出/缓存等 usage 类别和延迟，便于与
  Agent LLM token 成本总账分开汇总；评分器不根据近似模型价格猜算成本。
- `manual_claim_or_unit_judgments=0`；人只能事后抽检，不是逐题发布门。
- Judge 调用现在有硬上限：`config/judge.*.json` 中 `max_calls` 默认按 8 执行；在 claim extraction 前和 adjudication 前都会先按确定性批次数 reserve，超出预算 fail-closed 为 `withheld_scorer_budget`，不会边跑边烧钱。
- 报告完全没有 citation，或所有 citation 经严格 alias 后仍不在冻结 registry 内时，评分器在 Judge 前短路为正常 0 分；这表示该报告在当前 core registry 内没有可绑定 claim。snapshot 内但 registry 外的引用必须先在 projection 诊断中单独分类，不得直接写成 fabrication。

## 运行

```bash
python auto_score_biodiv_q1.py \
  --package-dir <evaluation_package> \
  --report <cell>/report.md \
  --ledger <cell>/strict-evidence.jsonl \
  --run-manifest <cell>/run-manifest.json \
  --output-dir <new-score-run> \
  --run-id <unique-run-id> \
  --judge-config config/judge.glm5d2.v1.json \
  --aggregator ../biodiv_q1_scoring_audit/score_gate_truth_packet.py \
  --scorer-root /data1/deep-research-arena
```

`prepare_ab_canary.py` 会从冻结证据中复制一个完整页，生成只含两个 claim 的 A+B 系统 canary。它不是 Agent 结果，不占任何 Cross-5 正式格。

## 矩阵格：先投影，再评分

`prepare_matrix_cell.py` 只读取某一次 attempt 已捕获的 `search_evidence/*.jsonl` 及其 `response_blob_ref`；它不会重新搜索，也不会从报告反推证据。只有严格 URL alias 命中冻结 registry，且 raw content 包含该页至少一条冻结 exact quote 时，才绑定冻结页身份。

Projection 现在额外写 `citation-diagnostics.json`：每个报告 citation 都会被分到 `in_registry_and_fetched`、`in_registry_but_snippet_only`、`in_snapshot_but_out_of_package_registry`、`out_of_snapshot_or_fabricated`、`missing_reference_definition`、`quote_not_found` 等确定桶。`in_snapshot_but_out_of_package_registry` 表示页面属于同一冻结快照但不在本包 30 页 registry；它是资产覆盖诊断，不是伪造证明。

Run B Claude 的精确命令模板：

```bash
SCORER_DIR=/data1/deep-research-arena/matrix_workspaces/biodiv_q1_scoring_system_20260825_v2
ATTEMPT_DIR=/data1/deep-research-arena/matrix_runs/BQ1-CROSS5-PILOT-20260825-B/cells/biodiversity-q1--deerflow--claude-opus-5/attempt-1
PACKAGE_DIR="$SCORER_DIR/fixtures/q1_package"
PROJECTION_DIR=/data1/deep-research-arena/matrix_scores/BQ1-CROSS5-PILOT-20260825-B/biodiversity-q1--deerflow--claude-opus-5/projection-A
SCORE_DIR=/data1/deep-research-arena/matrix_scores/BQ1-CROSS5-PILOT-20260825-B/biodiversity-q1--deerflow--claude-opus-5/score-A
SCORE_RUN_ID=BQ1-CROSS5-PILOT-20260825-B--biodiversity-q1--deerflow--claude-opus-5--SCORE-A

python3 "$SCORER_DIR/prepare_matrix_cell.py" \
  --attempt-dir "$ATTEMPT_DIR" \
  --package-dir "$PACKAGE_DIR" \
  --output-dir "$PROJECTION_DIR" \
  --run-id "$SCORE_RUN_ID"

python3 "$SCORER_DIR/auto_score_biodiv_q1.py" \
  --package-dir "$PACKAGE_DIR" \
  --report "$ATTEMPT_DIR/report.md" \
  --ledger "$PROJECTION_DIR/strict-evidence.jsonl" \
  --run-manifest "$PROJECTION_DIR/run-manifest.json" \
  --output-dir "$SCORE_DIR" \
  --run-id "$SCORE_RUN_ID" \
  --judge-config "$SCORER_DIR/config/judge.glm5d2.v1.json" \
  --aggregator /data1/deep-research-arena/matrix_workspaces/biodiv_q1_scoring_audit_20260825_v1/score_gate_truth_packet.py \
  --scorer-root /data1/deep-research-arena
```

`PROJECTION_DIR` 和 `SCORE_DIR` 必须是不存在的新目录；同一现场不覆盖、不复用。Judge 凭据只从受控环境变量 `TRUTH1000_ADAMS_USER_TOKEN` 读取，不写入命令、manifest 或日志。Judge 的 Adams 路由头由冻结配置提供，运行时会同时核验实际模型身份和 usage。
