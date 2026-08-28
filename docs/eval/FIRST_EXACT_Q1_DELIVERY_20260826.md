# 第一题最小闭环交付：FIRST-EXACT-20260826-F

## 结论

第一题的最小可评分闭环已经打通并出分：

- Citation Binding = 1.0（1/1）
- GCP = 1.0（1/1）
- GRR = 1.0（1/1）
- Judge = 0 调用 / 0 token

产物：

```text
package: /data1/deep-research-arena/matrix_workspaces/biodiv_first_exact_20260826_v6
score:   /data1/deep-research-arena/matrix_diagnostics/FIRST-EXACT-20260826-F/score
```

## 这道题

```text
Using the June 2026 English Wikipedia snapshot available in the research environment, state the four general steps of environmental mitigation and cite the supporting entry.
```

冻结资产：

- 1 个 required IU：`IU001`
- 1 条 evidence exact quote：`IU001:E001`
- 1 个 registry URL：`Environmental_mitigation`
- `formal_eligible=false`，shadow/experimental，不是 benchmark gold。

## 问题归因口径已固定

- preflight 不过 / 隔离证明缺失 / recorder 丢证据 / usage 不可归属 / state 脏 running：`withheld_infrastructure`，不算模型 0。
- preflight 过后 CLI/stub/不写报告/空报告：`report_failure_or_capability_zero`，算这个 Harness×LLM cell。
- 上游 5xx/transport retry 后失败：`provider_transport_failure`，不进内容质量分。

## 评分口径

- exact quote 命中且 citation 合法：deterministic 出分，不调 judge。
- paraphrase：后续接 `qwen3d6_35b_a3b` narrow judge；exact 命中的不重复调用。
- Qwen3-4B 不作为默认 judge；qwen3d6 用 `reasoning_effort=none` 避免 reasoning 吃掉输出预算。

## 之前指标不丢

这次最小闭环只用于证明“能出分”。正式交付仍会保留旧指标：

- Agent tokens：input/output/cached/cache_write/reasoning/total；
- Agent cost、Judge cost、diagnostic cost 分账；
- 每请求 latency/http_status/retry/identity_match；
- citation diagnostics：registry/fetched/snippet/context/out-of-snapshot；
- failure_status 分类；
- run/cell/report/projection/score 的 SHA seal；
- cost-GCP / cost-GRR / Pareto 图所需字段。

## 复现命令要点

在 any2 上，使用 scoring v8：

```text
/data1/deep-research-arena/matrix_workspaces/biodiv_q1_scoring_system_20260826_v8
```

关键验证：

```bash
cd /data1/deep-research-arena/matrix_workspaces/biodiv_q1_scoring_system_20260826_v8
python3 -m unittest discover -s . -p 'test_*.py'
```

当前结果：`Ran 40 tests, OK`（1 个真实长报告 fixture 在无该本地文件时 skip）。

## 还没做完

- 这只是最小第一题闭环证明；要跑真实 Harness×LLM 生产报告，还需把该包接入 matrix runner。
- Q1-v2 宽题仍需 narrow paraphrase judge；否则 registry 外合法引用和 paraphrase 覆盖仍会被低估。
- 模块化 CLI（`dra author/eval/score/report`）仍需收尾，不能让别人评测时手工拼内部命令。
