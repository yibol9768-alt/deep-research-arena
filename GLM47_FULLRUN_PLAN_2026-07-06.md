# GLM-4.7-Flash v2 全量实验计划

日期: 2026-07-06

## 0. 当前状态

- 已读取 handoff，并确认远端 `my5090` 的 WSL Ubuntu 环境可用。
- 两个 GLM 代理车道已启动:
  - lane0: `http://127.0.0.1:8089/v1`
  - lane1: `http://127.0.0.1:8092/v1`
- 两个代理各自写独立 usage 日志，方便 run 级归因:
  - `usage_glmflash_lane0.jsonl`
  - `usage_glmflash_lane1.jsonl`
- Chat 冒烟已通过: 客户端发 `max_tokens=16`，代理垫高后返回非空 `content`。
- 代理层 429/code1305 指数退避已验证: 冒烟时 lane1 实际遇到 HTTP 429，重试后恢复。
- Embedding 冒烟已通过: BigModel `embedding-3` 通过代理返回 2048 维向量。
- 所有 `/opt/deep_reserch/.venv-*` 已安装 GLM 适配 `.pth`，抽查通过 `tiktoken` fallback；有 `litellm` 的 venv 也能识别 `glm-4.7-flash` 的 200k 上下文。
- 目前还没有启动 full run。

## 1. 要跑多少框架

第一波正式全量跑 **12 个框架 x 100 个任务 = 1200 个 run**。

框架列表以远端 qwen8 full run 的 `queue_full_12x100.tsv` 为准，GLM 这次对齐同一组框架。

框架列表:

1. `camel-ai`
2. `claude-code`
3. `deerflow`
4. `flowsearcher-ds`
5. `gpt-researcher`
6. `ii-researcher`
7. `langchain-odr`
8. `ldr`
9. `opencode`
10. `qx-agents`
11. `smolagents`
12. `storm`

理由:

- handoff 里写了 6-7 个核心框架，但远端已有 qwen8 的 12x100 full-run 队列；为了和 qwen8 全量横向可比，GLM 也应跑同一组 12 个。
- 当前 `/opt/deep_reserch/scripts/run_deep_task.py` 的 runner 注册表里包含这 12 个名字。
- 暂不把 `browser-dr`、`co-storm`、`codex`、`deepagents`、`gemini-cli`、`local-deep-researcher`、`tongyi-dr` 等额外 runner 混入第一波；这些可以作为后续 extension batch。

## 2. 分阶段怎么跑

本次不直接从 full 开始，而是按 **subset -> mini -> full** 三阶段逐步扩张。

关键原则:

- 三个阶段都写同一个产物名: `data/results/deep/<agent>__<task>_glmflash.md`。
- 不使用 `_subset`、`_mini`、`_full` 这些不同后缀，否则 full 阶段无法天然复用前面阶段的结果。
- 每个 run 开始前都检查同名 `_glmflash.md` 是否已存在且大于 3KB；满足条件就 SKIP。
- full 阶段可以直接遍历 100 题全集，因为前两个阶段跑过的任务会被同名产物跳过。

阶段规模:

1. **subset 阶段**
   - 任务: `dr_cross_deep_0001` 到 `dr_cross_deep_0005`
   - 规模: 12 框架 x 5 题 = **60 runs**

2. **mini 阶段**
   - 任务来自 `data/tasks/deep_research/eval_small_v2/manifest.json`
   - 当前 13 题:
     `0010, 0011, 0019, 0034, 0041, 0045, 0054, 0060, 0072, 0078, 0083, 0089, 0096`
   - 规模: 12 框架 x 13 题 = **156 runs**
   - 当前 repo 中 subset 5 题与 mini 13 题没有任务 ID 重叠；如果以后 manifest 改了有重叠，也靠同名 `_glmflash.md` 自动跳过。

3. **full 阶段**
   - 任务: `dr_cross_deep_0001` 到 `dr_cross_deep_0100`
   - 理论规模: 12 框架 x 100 题 = **1200 runs**
   - 如果 subset 和 mini 都成功，full 阶段会跳过已完成的 18 题 x 12 框架 = 216 runs，只补 **984 runs**。
   - 如果前面某些 run 失败或产物 `<=3KB`，full 阶段会自然重试这些未达标 run。

采用 **两个独立串行车道并行**:

- lane0 跑奇数任务，走代理 `8089`。
- lane1 跑偶数任务，走代理 `8092`。
- 每个车道内部一次只跑一个 `(agent, task)`。
- 两个车道并行，所以全局并发是 2，符合 handoff 对 GLM 共享池限流的建议。
- 每个车道独立 usage 日志，避免两个 run 的 token 时间片互相污染。

每个 run 的流程:

1. 检查产物:
   `data/results/deep/<agent>__<task>_glmflash.md`
2. 如果文件存在且大于 3KB，直接 SKIP。
3. 向对应 lane 代理 POST `_mark` start:
   `run_id=<agent>__<task>__glm-4.7-flash`
4. 执行:
   ```bash
   python scripts/run_deep_task.py \
     --agent <agent> \
     --task <task> \
     --backbone glm-4.7-flash \
     --out-suffix glmflash
   ```
5. 无论成功、失败、超时，都 POST `_mark` end。
6. 失败不阻塞队列，继续下一个 run。
7. 每个阶段结束后，按缺失文件或 `<=3KB` 文件重建 retry queue，再重放该阶段失败集；进入下一阶段时仍然保留同一套 skip 逻辑。

远端已准备好的队列:

- subset:
  - `/root/pilot_v2/queues/queue_glm_subset_lane0_odd.tsv`，36 runs
  - `/root/pilot_v2/queues/queue_glm_subset_lane1_even.tsv`，24 runs
- mini:
  - `/root/pilot_v2/queues/queue_glm_mini_lane0_odd.tsv`，72 runs
  - `/root/pilot_v2/queues/queue_glm_mini_lane1_even.tsv`，84 runs
- full:
  - `/root/pilot_v2/queues/queue_glm_full_all_lane0_odd.tsv`，600 rows，实际会跳过已完成 `_glmflash.md`
  - `/root/pilot_v2/queues/queue_glm_full_all_lane1_even.tsv`，600 rows，实际会跳过已完成 `_glmflash.md`
- 参考用 remaining 队列:
  - `/root/pilot_v2/queues/queue_glm_full_remaining_after_subset_mini_if_all_success_*.tsv`
  - 只有在 subset+mini 全部成功且不想重试小集失败时才用；正常 full 阶段优先用 `full_all`，因为它能自动补跑前两阶段失败/短输出。

远端已准备好的 driver:

- `/root/pilot_v2/glm_oneagent.sh`
- `/root/pilot_v2/glm_lane_driver.sh`

启动命令模板:

```bash
# subset
tmux new -d -s glm_subset_lane0 \
  'bash /root/pilot_v2/glm_lane_driver.sh /root/pilot_v2/queues/queue_glm_subset_lane0_odd.tsv subset_lane0 http://127.0.0.1:8089 > /root/pilot_v2/logs/glm_subset_lane0.log 2>&1'
tmux new -d -s glm_subset_lane1 \
  'bash /root/pilot_v2/glm_lane_driver.sh /root/pilot_v2/queues/queue_glm_subset_lane1_even.tsv subset_lane1 http://127.0.0.1:8092 > /root/pilot_v2/logs/glm_subset_lane1.log 2>&1'

# mini: subset 完成并检查后再启动
tmux new -d -s glm_mini_lane0 \
  'bash /root/pilot_v2/glm_lane_driver.sh /root/pilot_v2/queues/queue_glm_mini_lane0_odd.tsv mini_lane0 http://127.0.0.1:8089 > /root/pilot_v2/logs/glm_mini_lane0.log 2>&1'
tmux new -d -s glm_mini_lane1 \
  'bash /root/pilot_v2/glm_lane_driver.sh /root/pilot_v2/queues/queue_glm_mini_lane1_even.tsv mini_lane1 http://127.0.0.1:8092 > /root/pilot_v2/logs/glm_mini_lane1.log 2>&1'

# full: mini 完成并检查后再启动；用 full_all，让 skip 机制补齐所有未达标 run
tmux new -d -s glm_full_lane0 \
  'bash /root/pilot_v2/glm_lane_driver.sh /root/pilot_v2/queues/queue_glm_full_all_lane0_odd.tsv full_lane0 http://127.0.0.1:8089 > /root/pilot_v2/logs/glm_full_lane0.log 2>&1'
tmux new -d -s glm_full_lane1 \
  'bash /root/pilot_v2/glm_lane_driver.sh /root/pilot_v2/queues/queue_glm_full_all_lane1_even.tsv full_lane1 http://127.0.0.1:8092 > /root/pilot_v2/logs/glm_full_lane1.log 2>&1'
```

运行环境关键变量:

- `BACKBONE=glm-4.7-flash`
- `DS_PROXY_URL=http://127.0.0.1:<lane_port>/v1`
- `OPENAI_BASE_URL=$DS_PROXY_URL`
- `OPENAI_API_BASE=$DS_PROXY_URL`
- `SHIM_URL=http://127.0.0.1:8081`
- `SHOPPING=http://localhost:17770`
- `REDDIT=http://localhost:9999`
- `WIKIPEDIA=http://localhost:8090`
- `TAVILY_API_KEY=tvly-shim-fake`

两个 CLI 类框架需要额外 preflight:

- `opencode`: 设置 `OPENCODE_MODEL=ds-shim/glm-4.7-flash`，`OPENCODE_DS_PROXY=http://127.0.0.1:<lane_port>/v1`。
- `claude-code`: runner 注释说明模型/proxy 走 Windows 侧 `ccr` 配置，不吃普通 `proxy_url`；启动 full run 前必须确认 ccr 已切到 GLM lane 代理，否则会混入旧 backbone。

超时策略:

- 默认每个 run 1800 秒。
- 如果某个框架持续慢但确实在产出，再只给该框架提高到 2400 秒。
- 不建议一开始全局拉高 timeout，否则失败反馈会太慢。

重试策略:

- 代理层负责无限重试 HTTP 429、BigModel code 1305、read timeout。
- 指数退避: `2 -> 4 -> 8 -> ... -> 60s`。
- 框架层如果仍然失败，靠 `>3KB` 断点机制在第二轮重放。
- 如果日志出现上下文超长 400，即 `prompt + 131072 > 200k`，重启代理把 `OPENAI_PROXY_MIN_MAX_TOKENS` 从 `131072` 降到 `65536`，只重跑受影响任务。

这次 generation pass 不打分、不跑 jury。先把报告和 usage 采完整，后面再合并 usage、抽检报告、构建 truth board。

## 3. 预计跑多久

规模估算:

- subset 阶段: 60 runs。
- mini 阶段: 156 runs；当前与 subset 无重叠，所以 subset+mini 合计 216 runs。
- full 阶段: 如果 subset+mini 已成功，预计只补 984 runs。
- 全部完成后总有效覆盖仍是 1200 个 `(framework, task)`。
- 历史经验每个 run 约 20-60 次 LLM 调用。
- 总调用量大约 2.4 万到 7.2 万次，中心估计约 3.5 万次。
- GLM-4.7-Flash 保留思维链，completion token 会明显放大，墙钟会比关思考慢。

墙钟估计:

- subset 阶段: **4-6 小时**，加重试预留 **5-10 小时**。
- mini 阶段: **10-16 小时**，加重试预留 **12-24 小时**。
- full 剩余阶段: 如果前两阶段成功，预计补跑 **65-100 小时**，加重试预留 **3-5 天**。
- 三阶段全部跑完的总墙钟仍应预留 **4-6 天**；分阶段的意义是更早拿到小集结果，同时避免重复跑已经完成的子集。

极端上限:

- 如果所有 run 都卡到 1800 秒，`1200 x 1800 / 2` 约 300 小时。
- 这是 timeout 天花板，不是预期耗时。

建议监控节奏:

- 启动后 30 分钟看一次，确认两个 lane 都在产出。
- 6 小时做一次正式 checkpoint:
  - 完成多少个 `>3KB` 报告
  - 每个框架失败/短输出分布
  - 429 retry 压力
  - usage 是否持续落盘
- 之后每 6-8 小时检查一次即可。

## 4. 监控指标

常用检查:

```bash
curl http://127.0.0.1:8089/healthz
curl http://127.0.0.1:8092/healthz

tail -F /root/pilot_v2/logs/glm_lane0.log
tail -F /root/pilot_v2/logs/glm_lane1.log

find /opt/deep_reserch/data/results/deep \
  -name '*_glmflash.md' -size +3k | wc -l

grep -c '"retry": true' \
  /mnt/c/Users/liuyibo/tri41/usage_glmflash_lane*.jsonl
```

重点看:

- 两个 lane 是否都在推进。
- 是否大量 429，但最终能恢复。
- 是否某个框架集中产出错误页或短文件。
- usage jsonl 是否有 `_mark` start/end 和 token 记录。
- 是否出现 context-length 400。

## 5. 产出与验收

生成阶段产出:

- `data/results/deep/<agent>__<task>_glmflash.md`
- `data/results/deep/<agent>__<task>_glmflash.meta.json`
- `usage_glmflash_lane0.jsonl`
- `usage_glmflash_lane1.jsonl`
- 跑完后合并为 `usage_glmflash.jsonl`

验收标准:

1. 目标 1200 个报告，先以 `>3KB` 作为有效产物粗筛。
2. 随机抽 3-5 份报告，确认:
   - 不是空内容
   - 不是错误页
   - 引用的是本地沙箱 URL
3. usage 聚合能按 run_id 列出 calls/tokens。
4. `usage_missing` 比例低于 5%；如果某个框架偏高，单独记录。
5. 完成后再进入 truth board / 五轴榜构建，不和 generation pass 混跑。

## 6. 不动清单

不碰以下内容:

- `qwen8_clamp_proxy`
- `shop7770_proxy`
- 任何 qwen8 full-run 相关 tmux
- vLLM `:8001`
- GPU power/clock 设置
- `paper_iclr/`
- `/root/local_jury/`
