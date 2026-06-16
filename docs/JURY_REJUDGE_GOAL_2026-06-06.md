# GOAL: 陪审团重判到上线(长时运行,2026-06-06 起)

## ✅ 已完成并上线(2026-06-06)

全流程跑通,公开站点已更新验证。最终数据:
- **1,553 场全部三判官有效投票**(`valid_juror_distribution {3:1553}`,0 判官错误)。
- 陪审团平局率 **16.9%**(单判官时 50.6%),可决 83.1%(果断 27.7% + 多数 54.9%)。
- 三判官果断均衡:deepseek 68% / glm 61% / qwen 50%。
- 真值门控榜:camel-ai 第 1(可达 60%),gpt-researcher 原始判官 Elo 第 1 但可达仅 4% → 门控后第 9。
- 修了两个 bug:(1) error→TIE 静默记票;(2) 外部改的 `_is_degraded` 用 verdicts_raw
  计有效判官被 error-TIE 骗(改用 judge_errors_partial 准确计数,保留 2/3 多数有效的意图)。
- 提交:`7e3ee35`(榜单+引擎+changelog)、`c977d2e`(methodology 页改三判官)。push origin main。
- 站点验证:changelog 新条目、首页 gpt-researcher Elo 1179(旧 1207 已消失)、
  methodology 页"3-judge cross-family PoLL jury"均已 live。
- 残留(可选清理):box 上 `DRA_StackGuard` 计划任务每 5 分钟跑(保活,现已无活可保);
  卸载 `schtasks /Delete /TN DRA_StackGuard /F`。污染榜备份 `*.CONTAMINATED.*.json` 留底。


> 一句话:把"假三判官"修成"真三判官",重判被污染的对战,跑完质量门,
> 汇总真值门控榜,上线 deep2researcharena.com。期间持续监控、自愈、续跑。

## 致命诊断(实测,2026-06-06)

checkpoint `leaderboard_jury_elo.json.battles.jsonl` 共 1506 场:

| 类别 | 场数 | 含义 |
|---|---|---|
| 干净(3 判官都答) | **236** | 真三判官 |
| 退化(`judge_errors_partial>=1`) | **1270** | qwen3-max 错 1269、glm-5 错 1270 |

根因:**判官报错被静默记成 TIE**。`_judge_once` 在 `call_judge` 出错时返回
`("tie", "(judge error)")`,`_run_battle` 把它当成弃权 TIE 票写进 checkpoint 并落盘。
中段(对战 200-1400)DashScope egress 断流,qwen+glm 每场都 error→TIE,整段实为
**deepseek 单判官**穿着三判官的外衣。直接出榜 = 重犯审计文档已清除过一次的
"假双判官"造假。

DashScope 现已恢复(最近 80 场 86% 干净)。窗口证据:0-200 与 1400+ 两端 qwen/glm
正常,中段 100% error。env 来自 `/root/.config/dra/judge.env`(本地 .env 缺代理/密钥,
所以临时 subshell 测连通会瞬时 connection error,不代表真实跑批状态)。

## 方法学修复(已实装,env 开关 `JURY_REDO_DEGRADED=1`)

改 `scripts/build_real_leaderboard.py`,四处,全在一个开关后:

1. **逐判官重试**:`_run_battle` 里每个 juror 出错重试 `JURY_JUROR_RETRIES`(默认 3)次。
2. **加载过滤**:载入 checkpoint 时跳过退化记录(`judge_errors_partial` 或 error)→ 当未判处理。
3. **提交门**:只有"三判官全部真答"的对战才落盘;有 juror 报错的不写 → 下轮续判。
4. **收尾门**:本轮跑完若仍有 `n_judge_errors>0`,抛 `JudgeErrorAbort`(不写最终 json),
   看门狗续跑;直到 0 退化才写 `leaderboard_jury_elo.json` 收口。

铁律:**每一场落盘的对战都必须是三判官真答**,error 永不充当 TIE 票。

## 执行流水线(阶段 + 完成判据)

- **P1 修引擎**:补丁 push 到 box;`run_jury.sh` 加 `JURY_REDO_DEGRADED=1`、
  `JUDGE_TIMEOUT_S=90`。判据:box 上 md5 与本地一致、run_jury.sh 含开关。
- **P2 刷库重启**:停现 jury;备份后从 checkpoint 物理删退化记录(留 236 干净);
  看门狗(120s)自动用新引擎拉起。判据:checkpoint 仅剩干净记录、jury 进程在跑。
- **P3 重判收敛**:看门狗 + StackGuard 守护,跨 DashScope 抖动/WSL 重启续跑,
  直到 1553 场全干净 → 写最终 json。判据:`leaderboard_jury_elo.json` 出现
  且 `n_judge_errors==0`、checkpoint 1553 全干净。
- **P4 质量门**:`scripts/jury_quality_gates.py`。判据:陪审团平局率 <20%、
  可决率 ≥60%、三判官果断率均衡(对照试点 14% / 62-65%)。
- **P5 汇总**:`build_site_board_from_judge_elo.py`(源需指向新 jury elo;注意脚本默认
  读 `leaderboard_judge_elo.json`,本次产物是 `leaderboard_jury_elo.json`,
  汇总前对齐源文件名)→ gated = elo × gate,全员有分,裸判官为页签,bootstrap 95% CI。
- **P6 上线**:`data/changelog.json` 加条目(硬性规则)→ `frontend` typecheck+build →
  rsync `web/dist`(校验 wrangler.jsonc 还在)→ commit 源+数据+dist → push main →
  Cloudflare 自动重部署。用户已授权"直到最后上线"。

## 运维约束(已固化)

- 远程一律 `ssh my5090 'bash -s' <<heredoc`;不 dump `/proc/<pid>/environ`(分类器拒绝且无必要)。
- 不重建并行 box 基建:复用现有 `boot.sh`/`watchdog.sh`/`run_jury.sh`/StackGuard/checkpoint。
- box 基建/语料/复现归 Codex;本任务的引擎修复属"评测方法学",归 Claude;用户当面指令优先。
- 监控用自配速 ScheduleWakeup 循环推进阶段;长任务靠 box 看门狗自愈,不靠我常驻轮询。

## 当前状态(2026-06-06,持续更新)

- **P1 引擎**:已上线 box,md5 本地=box 一致(`ca591aa1...`)。
- **P2 刷库**:已用加载过滤(非物理删)规避竞态;`run_jury.sh` 已加
  `JURY_REDO_DEGRADED=1 JUDGE_TIMEOUT_S=90`,并发 `--battle-workers 4`(从 2 提速 5x)。
- **P3 重判**:进行中,~8.2 干净/分钟,ETA ~2.4h。clean 已从 263→365+,degraded 递减。
  后台监工 `bymiahgjh`(json 出现即唤醒我)。box 看门狗+StackGuard 自愈。
- **质量门预览**(348 场干净):平局率 **16.1%**(目标<20%)、可决 83.9%、
  三判官果断 67/53/62%——通过。
- **P5 已就绪**:`build_site_board_from_judge_elo.py` 已改为优先读 `leaderboard_jury_elo.json`,
  陪审名单从 checkpoint 的 `jury` 字段派生(不硬编码),已 push 到 box。
  **注意:grounding_uniform2.json 本地与 box 不一致(box 为准),P5 必须在 box 上跑
  或先把 box 的 grounding 拉到本地。**
- **P6 工具链已验证**:本地 `npm run typecheck` ✓、`npm run build` ✓(Next 14.2.18,
  静态导出到 frontend/out)。本地是 git repo,分支 `eval-redesign-impl` 与 origin/main 同在
  `c3d64f0` → 上线 = 提交后 `git push origin HEAD:main`(快进)。changelog 下一版本 `v3-2026-06-06a`。

## 事故与二次修复(2026-06-06 14:2x):污染榜单已拦截

第一次"收敛"写出的榜单是**污染的**:`n_judge_errors=0` 但实际只有 639 场真干净,
914 场仍是 deepseek 单判官。根因:`build_real_leaderboard.py` 被外部(Codex/用户)改过,
把"任一判官报错即退化"放宽成 `_min_jurors=2`(2/3 多数即有效,合理),但
**有效判官计数算错**:`_n_valid_jurors` 用 `verdicts_raw` 非空判定,而报错判官产生
`["TIE","TIE"]`(error→TIE)看着非空 → 三判官全被算"有效" → 914 退化场当干净放行。

二次修复(保留 2/3 意图,只修计数):
- `_n_valid_jurors` 改用准确的 `judge_errors_partial`:有效 = 判官数 − 报错数。
- 收尾门改用 `n_degraded`(`_is_degraded` 计数,基于有效判官 < `_min_jurors`),
  不再用 `n_judge_errors`(=全判官失败,漏掉部分退化)。
- summary 增 `jury_size/min_valid_jurors/valid_juror_distribution/n_degraded_below_floor` 溯源。
- 已单测三形态:914-式(valid=1,退化✓)、2/3(valid=2,放行✓)、3/3(valid=3✓)。
- 已 push box(md5 `1f45acfc...` 一致)、重启 jury(pid 10509)。污染榜已 mv 成
  `leaderboard_jury_elo.CONTAMINATED.*.json`。正确口径:clean=656 / degraded=897。

**新成功判据**:不仅 `leaderboard_jury_elo.json` 存在,还要 summary
`n_degraded_below_floor==0`(收尾门已保证,但上线前复核)。
**注意外部并发编辑**:该文件可能被 Codex 同时改;每次操作前后核 md5。

## 收敛后执行手册(P4→P6,可被全新上下文照做)

1. **P4 质量门**(box):`python3 scripts/jury_quality_gates.py
   data/results/real/leaderboard_jury_elo.json.battles.jsonl`。断言平局率<20%、可决≥60%。
2. **P5 汇总**(box,用 canonical grounding):
   `cd /opt/deep_reserch && python3 scripts/build_site_board_from_judge_elo.py`
   → 写 `data/results/deep_v3/leaderboard_deep_v3.json`(elo_v3_ci + per_agent_profile +
   composite_formula + jury)。校验 `jury` 字段=三判官、n_agents=10。
3. **拉产物到本地**:scp/ssh 把 box 的 `leaderboard_jury_elo.json`、其 `.battles.jsonl`、
   `leaderboard_deep_v3.json`、`grounding_uniform2.json` 拉到本地对应路径(保持 canonical)。
4. **P6 上线**(本地):
   a. `data/changelog.json` 顶部加 `v3-2026-06-06a` 条目(真三判官重判:平局率、可决率、
      排名变化;修了 error→TIE 静默 bug;1270/1506 退化场已重判)。
   b. `cd frontend && npm run typecheck && npm run build`
   c. `rsync -a --delete --exclude 'wrangler.jsonc' frontend/out/ web/dist/`,校验 web/dist/wrangler.jsonc 还在。
   d. `git add -A && git commit`(源+数据+web/dist+docs)→ `git push origin HEAD:main`。
   e. 验证:抓 https://www.deepresearcharena.com/ 确认榜单与 changelog 更新。
   前端 gated_score = elo × (reach%+quote%)/200 客户端算,所以只要 deep_v3 json 的
   elo_v3_ci + per_agent_profile 正确,排名自动正确。
