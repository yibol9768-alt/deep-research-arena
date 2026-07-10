# Qwen3-8B DRA Partial Report Export

- generated_at: `2026-07-06T09:11:18`
- root: `/opt/deep-research-arena-20260704_qwen8_clean`
- result_dir: `/opt/deep-research-arena-20260704_qwen8_clean/data/results/deep_v3_qwen8_12x100_full_20260705`
- state: paused by user, queue tmux stopped
- planned_total: `12 agents x 100 tasks = 1200 scores`
- progress_scored_lines: `592`
- score_json_files: `592`
- answer_md_files_seen: `672`
- latest_start: `2026-07-06 03:11:45  starting   opencode  dr_cross_deep_0056`
- latest_scored: `2026-07-06 03:11:45  scored     claude-code  dr_cross_deep_0056`
- error_lines: `138`

## Scored by agent
- camel-ai: 41
- claude-code: 56
- deerflow: 55
- flowsearcher-ds: 55
- gpt-researcher: 55
- ii-researcher: 55
- langchain-odr: 55
- ldr: 55
- opencode: 55
- qx-agents: 55
- smolagents: 55

## Error counts by agent
- camel-ai: 28
- storm: 110

## Recent progress tail
```
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

## Recent errors tail
```
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
