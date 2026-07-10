# my5090 Deep Research Arena Qwen3-8B partial run handoff

生成时间: `2026-07-06T08:37:04`  
位置: `vircs:/root/Desktop/lyb/deep_reserch/data/results/my5090_qwen8_partial_reports/`

## 1. 这份东西是什么

这是 `my5090` 上 Deep Research Arena 的 Qwen3-8B 局部实验结果归档。实验原计划跑 `12 agents × 100 cross-site deep tasks = 1200` 个评分记录。用户后来要求先停掉实验，所以这里保存的是已经完成的部分，不是最终全量排行榜。

本次我已经把可用结果集中成一个主文件:

- 主文件: `/root/Desktop/lyb/deep_reserch/data/results/my5090_qwen8_partial_reports/MY5090_QWEN8_DRA_PARTIAL_HANDOFF_AND_UNIFIED_RESULTS_20260706.json`
- 可读 handoff: `/root/Desktop/lyb/deep_reserch/data/results/my5090_qwen8_partial_reports/HANDOFF_MY5090_QWEN8_DRA_PARTIAL_20260706.md`
- 原始压缩包: `/root/Desktop/lyb/deep_reserch/data/results/my5090_qwen8_partial_reports/qwen8_partial_report_20260706_091118.tar.gz`
- 原始解压目录: `/root/Desktop/lyb/deep_reserch/data/results/my5090_qwen8_partial_reports/qwen8_partial_report_20260706_091118`
- my5090 任务 JSON 快照: `/root/Desktop/lyb/deep_reserch/data/results/my5090_qwen8_partial_reports/my5090_task_snapshot_20260706/data/tasks/deep_research/cross_site_deep`

## 2. 当前状态

- 状态: 已按用户要求暂停，队列 tmux 已停止。
- 已完成 score JSON: `592` / `1200`。
- 有分数覆盖的 task 数: `56` / `100`。
- 已复制进统一 JSON 的 answer markdown: `592`。
- 缺失 answer 文件数: `0`。
- 最新 scored 记录: `2026-07-06 03:11:45  scored     claude-code  dr_cross_deep_0056`。
- 暂停前最新 starting 记录: `2026-07-06 03:11:45  starting   opencode  dr_cross_deep_0056`。
- pause marker: `2026-07-06 03:16:19  PAUSE-REQUESTED by Codex/user`。

## 3. 模型怎么来的, 跑的是什么模型

- 模型名: `Qwen3-8B`。
- 实验里使用的 served model name: `qwen3-8b`。
- my5090 本地模型路径: `/mnt/e/models/Qwen3-8B`。
- 服务方式: vLLM OpenAI-compatible API, `http://127.0.0.1:8001/v1`。
- 观测到的 judge identity: `provider=openai`, `model=qwen3-8b`, `heavy_model=qwen3-8b`, `base_url=http://127.0.0.1:8001/v1`。
- vLLM 启动配置记录: `--max-model-len 40960`, `--gpu-memory-utilization 0.90`, `--enforce-eager`, `enable_thinking=false`, `--enable-auto-tool-choice`, `--tool-call-parser hermes`。
- 硬件: NVIDIA GeForce RTX 5090。
- 注意: GPU 功率限制按用户要求保持最高 `600W`, 不要擅自改回 `400W`。

## 4. 数据从哪里来

- 代码仓库: `https://github.com/yibol9768-alt/deep-research-arena.git`。
- my5090 工作目录: `/opt/deep-research-arena-20260704_qwen8_clean`。
- 观测到的 my5090 git branch/head: `main @ d379d3d7bbfd7129805c2bdb3158f0128d353044`。
- 任务目录: `data/tasks/deep_research/cross_site_deep/`。
- 任务文件: `dr_cross_deep_0001.json` 到 `dr_cross_deep_0100.json`, 共 `100` 个已从 my5090 快照复制。
- 每个 task 是 cross-site deep research 任务, 站点为 sandbox 内的 `shopping`, `reddit`, `wikipedia`。
- 本次统一 JSON 里包含了 `tasks` 字段, 保存了这 100 个任务 JSON 的原文, 也在每条结果里放了 `task_intent` 和 `task_sites`。

## 5. agent/harness 覆盖情况

- `claude-code`: 56 score files, avg `composite_v4` = 0.000927
- `opencode`: 55 score files, avg `composite_v4` = 0.0
- `camel-ai`: 41 score files, avg `composite_v4` = 0.031771
- `deerflow`: 55 score files, avg `composite_v4` = 0.350155
- `flowsearcher-ds`: 55 score files, avg `composite_v4` = 0.012051
- `smolagents`: 55 score files, avg `composite_v4` = 0.0
- `langchain-odr`: 55 score files, avg `composite_v4` = 0.0
- `ii-researcher`: 55 score files, avg `composite_v4` = 0.239484
- `ldr`: 55 score files, avg `composite_v4` = 0.0
- `storm`: 0 score files, avg `composite_v4` = None
- `gpt-researcher`: 55 score files, avg `composite_v4` = 0.007076
- `qx-agents`: 55 score files, avg `composite_v4` = 0.0

覆盖直方图, key 是某个 task 有多少个 agent 成功评分:

```json
{
  "1": 1,
  "10": 14,
  "11": 41
}
```

## 6. 已知问题

- `storm` 没有有效 score, 错误日志中反复出现 `RUN-FAILED` 和 `NO-REPORT`。
- `camel-ai` 有部分 `NO-REPORT` 缺口, 当前只有 `41` 个有效 score。
- `dr_cross_deep_0056` 只有 `claude-code` 已 scored, 暂停前刚开始 `opencode`。
- 这里统计的是当前 score JSON 里的 `composite_v4` 等自动评分, 不是最终官方 Elo。后续要跑完整排行榜时, 应按项目官方 Elo 流程重新汇总。

错误计数:

- `camel-ai`: 28
- `storm`: 110

## 7. 统一 JSON 文件结构

`MY5090_QWEN8_DRA_PARTIAL_HANDOFF_AND_UNIFIED_RESULTS_20260706.json` 是主文件, 可以直接用 Python `json.load` 读取。顶层字段如下:

- `metadata`: 实验来源、模型、代码 commit、数据目录、计数、哈希和已知问题。
- `handoff_markdown`: 本文档同内容, 便于单文件转交。
- `tasks`: 100 个 task JSON 快照, key 为 task id。
- `records`: `592` 条已完成结果。每条包含 agent、task_id、score 文件、answer 文件、answer 正文、answer sha256、所有评分 metrics、composite 分数、judge identity 和原始 score JSON。
- `raw_logs`: progress 和 error 日志全文。

## 8. 后续怎么接着做

1. 如果要继续同一轮, 从 `opencode / dr_cross_deep_0056` 附近恢复, 但建议先修 `storm` 和 `camel-ai` 的 no-report 问题。
2. 如果要最终 Elo, 不要拿本文件的 partial average 直接当最终分数。应该先跑满全量或确定跳过策略, 然后调用项目官方 Elo/leaderboard 汇总流程。
3. 如果要迁移到云端, 优先带走这个统一 JSON 和原始压缩包, 再决定是否复制完整 sandbox。
4. 不要把后面 GLM 或 SenseCore 的任务混进这个 Qwen3-8B/my5090 局部结果。

## 9. 最近进度尾部

```text
2026-07-06 02:21:45  scored     camel-ai  dr_cross_deep_0054
2026-07-06 02:21:45  starting   deerflow  dr_cross_deep_0054
2026-07-06 02:24:48  scored     deerflow  dr_cross_deep_0054
2026-07-06 02:24:48  starting   flowsearcher-ds  dr_cross_deep_0054
2026-07-06 02:27:41  scored     flowsearcher-ds  dr_cross_deep_0054
2026-07-06 02:27:41  starting   smolagents  dr_cross_deep_0054
2026-07-06 02:29:56  scored     smolagents  dr_cross_deep_0054
2026-07-06 02:29:56  starting   langchain-odr  dr_cross_deep_0054
2026-07-06 02:31:57  scored     langchain-odr  dr_cross_deep_0054
2026-07-06 02:31:57  starting   ii-researcher  dr_cross_deep_0054
2026-07-06 02:33:30  scored     ii-researcher  dr_cross_deep_0054
2026-07-06 02:33:30  starting   ldr  dr_cross_deep_0054
2026-07-06 02:34:33  scored     ldr  dr_cross_deep_0054
2026-07-06 02:34:33  starting   storm  dr_cross_deep_0054
2026-07-06 02:37:27  starting   gpt-researcher  dr_cross_deep_0054
2026-07-06 02:39:54  scored     gpt-researcher  dr_cross_deep_0054
2026-07-06 02:39:54  starting   qx-agents  dr_cross_deep_0054
2026-07-06 02:40:24  scored     qx-agents  dr_cross_deep_0054
2026-07-06 02:40:24  starting   claude-code  dr_cross_deep_0055
2026-07-06 02:43:42  scored     claude-code  dr_cross_deep_0055
2026-07-06 02:43:42  starting   opencode  dr_cross_deep_0055
2026-07-06 02:50:13  scored     opencode  dr_cross_deep_0055
2026-07-06 02:50:13  starting   camel-ai  dr_cross_deep_0055
2026-07-06 02:51:32  scored     camel-ai  dr_cross_deep_0055
2026-07-06 02:51:32  starting   deerflow  dr_cross_deep_0055
2026-07-06 02:54:52  scored     deerflow  dr_cross_deep_0055
2026-07-06 02:54:52  starting   flowsearcher-ds  dr_cross_deep_0055
2026-07-06 02:57:50  scored     flowsearcher-ds  dr_cross_deep_0055
2026-07-06 02:57:50  starting   smolagents  dr_cross_deep_0055
2026-07-06 02:59:18  scored     smolagents  dr_cross_deep_0055
2026-07-06 02:59:18  starting   langchain-odr  dr_cross_deep_0055
2026-07-06 03:00:20  scored     langchain-odr  dr_cross_deep_0055
2026-07-06 03:00:20  starting   ii-researcher  dr_cross_deep_0055
2026-07-06 03:01:41  scored     ii-researcher  dr_cross_deep_0055
2026-07-06 03:01:41  starting   ldr  dr_cross_deep_0055
2026-07-06 03:02:46  scored     ldr  dr_cross_deep_0055
2026-07-06 03:02:46  starting   storm  dr_cross_deep_0055
2026-07-06 03:06:05  starting   gpt-researcher  dr_cross_deep_0055
2026-07-06 03:07:40  scored     gpt-researcher  dr_cross_deep_0055
2026-07-06 03:07:40  starting   qx-agents  dr_cross_deep_0055
2026-07-06 03:08:26  scored     qx-agents  dr_cross_deep_0055
2026-07-06 03:08:26  starting   claude-code  dr_cross_deep_0056
2026-07-06 03:11:45  scored     claude-code  dr_cross_deep_0056
2026-07-06 03:11:45  starting   opencode  dr_cross_deep_0056
2026-07-06 03:16:19  PAUSE-REQUESTED by Codex/user
```

## 10. 最近错误尾部

```text
2026-07-05 16:07:26  RUN-FAILED storm dr_cross_deep_0030 rc=0
2026-07-05 16:07:26  NO-REPORT  storm dr_cross_deep_0030
2026-07-05 16:27:52  RUN-FAILED storm dr_cross_deep_0031 rc=0
2026-07-05 16:27:52  NO-REPORT  storm dr_cross_deep_0031
2026-07-05 16:48:13  RUN-FAILED storm dr_cross_deep_0032 rc=0
2026-07-05 16:48:13  NO-REPORT  storm dr_cross_deep_0032
2026-07-05 16:51:22  RUN-FAILED camel-ai dr_cross_deep_0033 rc=0
2026-07-05 16:51:22  NO-REPORT  camel-ai dr_cross_deep_0033
2026-07-05 17:06:22  RUN-FAILED storm dr_cross_deep_0033 rc=0
2026-07-05 17:06:22  NO-REPORT  storm dr_cross_deep_0033
2026-07-05 17:08:56  RUN-FAILED camel-ai dr_cross_deep_0034 rc=0
2026-07-05 17:08:56  NO-REPORT  camel-ai dr_cross_deep_0034
2026-07-05 17:25:16  RUN-FAILED storm dr_cross_deep_0034 rc=0
2026-07-05 17:25:16  NO-REPORT  storm dr_cross_deep_0034
2026-07-05 17:45:33  RUN-FAILED storm dr_cross_deep_0035 rc=0
2026-07-05 17:45:33  NO-REPORT  storm dr_cross_deep_0035
2026-07-05 18:05:41  RUN-FAILED storm dr_cross_deep_0036 rc=0
2026-07-05 18:05:41  NO-REPORT  storm dr_cross_deep_0036
2026-07-05 18:25:58  RUN-FAILED storm dr_cross_deep_0037 rc=0
2026-07-05 18:25:58  NO-REPORT  storm dr_cross_deep_0037
2026-07-05 18:45:01  RUN-FAILED storm dr_cross_deep_0038 rc=0
2026-07-05 18:45:01  NO-REPORT  storm dr_cross_deep_0038
2026-07-05 19:05:18  RUN-FAILED storm dr_cross_deep_0039 rc=0
2026-07-05 19:05:18  NO-REPORT  storm dr_cross_deep_0039
2026-07-05 19:27:28  RUN-FAILED storm dr_cross_deep_0040 rc=0
2026-07-05 19:27:28  NO-REPORT  storm dr_cross_deep_0040
2026-07-05 19:56:25  RUN-FAILED storm dr_cross_deep_0041 rc=0
2026-07-05 19:56:25  NO-REPORT  storm dr_cross_deep_0041
2026-07-05 20:25:05  RUN-FAILED storm dr_cross_deep_0042 rc=0
2026-07-05 20:25:05  NO-REPORT  storm dr_cross_deep_0042
2026-07-05 20:55:31  RUN-FAILED storm dr_cross_deep_0043 rc=0
2026-07-05 20:55:31  NO-REPORT  storm dr_cross_deep_0043
2026-07-05 21:27:11  RUN-FAILED storm dr_cross_deep_0044 rc=0
2026-07-05 21:27:11  NO-REPORT  storm dr_cross_deep_0044
2026-07-05 21:54:44  RUN-FAILED storm dr_cross_deep_0045 rc=0
2026-07-05 21:54:44  NO-REPORT  storm dr_cross_deep_0045
2026-07-05 22:25:12  RUN-FAILED storm dr_cross_deep_0046 rc=0
2026-07-05 22:25:12  NO-REPORT  storm dr_cross_deep_0046
2026-07-05 22:54:02  RUN-FAILED storm dr_cross_deep_0047 rc=0
2026-07-05 22:54:02  NO-REPORT  storm dr_cross_deep_0047
2026-07-05 23:24:46  RUN-FAILED storm dr_cross_deep_0048 rc=0
2026-07-05 23:24:46  NO-REPORT  storm dr_cross_deep_0048
2026-07-05 23:52:40  RUN-FAILED storm dr_cross_deep_0049 rc=0
2026-07-05 23:52:40  NO-REPORT  storm dr_cross_deep_0049
2026-07-06 00:34:47  RUN-FAILED storm dr_cross_deep_0050 rc=0
2026-07-06 00:34:47  NO-REPORT  storm dr_cross_deep_0050
2026-07-06 00:47:13  RUN-FAILED camel-ai dr_cross_deep_0051 rc=0
2026-07-06 00:47:13  NO-REPORT  camel-ai dr_cross_deep_0051
2026-07-06 01:05:05  RUN-FAILED storm dr_cross_deep_0051 rc=0
2026-07-06 01:05:05  NO-REPORT  storm dr_cross_deep_0051
2026-07-06 01:18:05  RUN-FAILED camel-ai dr_cross_deep_0052 rc=0
2026-07-06 01:18:05  NO-REPORT  camel-ai dr_cross_deep_0052
2026-07-06 01:34:14  RUN-FAILED storm dr_cross_deep_0052 rc=0
2026-07-06 01:34:14  NO-REPORT  storm dr_cross_deep_0052
2026-07-06 02:13:22  RUN-FAILED storm dr_cross_deep_0053 rc=0
2026-07-06 02:13:22  NO-REPORT  storm dr_cross_deep_0053
2026-07-06 02:37:27  RUN-FAILED storm dr_cross_deep_0054 rc=0
2026-07-06 02:37:27  NO-REPORT  storm dr_cross_deep_0054
2026-07-06 03:06:05  RUN-FAILED storm dr_cross_deep_0055 rc=0
2026-07-06 03:06:05  NO-REPORT  storm dr_cross_deep_0055
```
