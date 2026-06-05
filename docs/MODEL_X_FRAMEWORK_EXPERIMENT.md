# DRA 实验协议:模型 × 框架 矩阵评测

> 配套文档:`docs/MODEL_X_FRAMEWORK_PLAN.md`(规划与优先级)。本文件回答"每个格子具体怎么跑、怎么打分、怎么不被自己坑"。

## 1. 因子与水平

**框架(行)**:camel-ai、deerflow、smolagents、flowsearcher-ds、ii-researcher、
langchain-odr、ldr、storm、gpt-researcher、qx-agents,外加 **eff 极简脚手架**
(`scripts/efficiency_experiment.py`,固定 2 调用协议,作为"裸模型"基线行)。

**模型(列)与端点**:

| 模型 | 端点 | 思考特性 | 实测单价依据 |
|---|---|---|---|
| deepseek-v4-flash | api.deepseek.com(JUDGE_API_KEY) | 支持,需显式开关 | $0.14/M 入 + $0.28/M 出 |
| deepseek-v4-pro | 同上 | 同上 | 待核实 |
| qwen3-32b / qwen-flash / qwen3-30b-a3b-instruct-2507 / qwen3-max | DashScope compatible-mode(DASHSCOPE_API_KEY) | qwen3 系非流式必须 enable_thinking=false | 30b-a3b 实测 $0.2/$0.8(国际口径) |
| glm-5 / kimi-k2.5 / MiniMax-M2.5 | DashScope(同上) | glm 需 thinking disabled | 待核实 |

> 单价规则:发布任何成本数字前,逐模型核实官方价格页;无法核实就只报 tokens。

## 2. 实验常量(所有格子一致)

- 任务集:94 个 comparable 任务(`deerflow__dr_cross_deep_*` 的任务并集);判官入评子集
  为 deep_clean manifest 的 74 任务(24 隔离)。
- 沙箱:统一 compose(shopping:7770 / forum:9999 / wiki:8090 / shim:8081),
  接地核验一律走冻结缓存 `data/results/sandbox_cache.json`(当前 29,445 URL)。
- 引用规范:报告只允许引用 `http://localhost:7770|9999|8090` 的逐字 URL;
  shim 返回的 docker 内部主机名必须经 `_canon_url` 规范化(已实现,教训:qwen 首轮
  全部 0 分就是因为喂了 `wiki:8080` 内部名,模型照抄或改编成公网假链)。
- 每格输出:94 份报告 + tokens/延迟逐任务日志。

## 3. 命名规范(工程前置,P0)

现状缺陷:报告名 `<agent>__<task>_matrix.md` 把"框架@模型"压成一个 agent 名,矩阵会撞名。

**新规范**:`<framework>@<model-safe>__<task>_matrix.md`(model-safe 为小写、
`[^a-z0-9.-]` 转 `-`)。存量文件视为 `<framework>@<其 meta 中 backbone>` 的隐式命名,
不改名,由打分器同时识别两种格式。涉及改动:运行器、`build_kappa_pairs.py`、
`score_grounding_from_cache.py`、`build_real_leaderboard.py` 的 agent 解析处。

## 4. 运行协议(每个格子)

1. **冒烟门(强制)**:先跑 1 个任务,自动检查:报告非空、引用全部为 localhost 规范 URL、
   引用数 > 0。不过门不许放量(教训:qwen 首轮 94 任务白跑一遍)。
2. 放量:94 任务切 3 个不相交分片并行(沙箱并发安全上限按 3 控制)。
3. **断点续跑**:存在且 >500B 的报告一律跳过(已实现 `--force` 覆盖开关)。
4. 看门狗:每 2 分钟巡检,"格子未满 94 且无对应进程"则拉起整列表续跑 lane;
   并发节流(全局 eff/框架运行进程 < 3)。
5. 框架接 DashScope 后端:经 ds_proxy 或框架自身的 OpenAI-compatible 配置注入
   base_url + key + model;每个 (框架, 模型) 组合先过冒烟门。
6. 远程操作一律 `ssh my5090 'bash -s' <<heredoc`(教训:单行命令经 Windows cmd
   的引号会被破坏,曾导致探测假报全挂)。

## 5. 评分管线(每格相同)

1. **接地(判官无关)**:`build_sandbox_cache.py`(增量抓新 URL)→
   `score_grounding_from_cache.py` → 每格 reach / quote / gate。
2. **质量(陪审团判官 v2)**:`build_real_leaderboard.py --judges
   deepseek-v4-flash,qwen3-max,glm-5 --battle-workers 3 --n-samples 1`,
   env:`JUDGE_THINKING=1 JUDGE_TIMEOUT_S=180 PAIRWISE_REPORT_CAP=30000
   --word-budget 4000`(全量 token)。
   - 每陪审员换位双判去偏;多数票定胜负;逐陪审员判定写入 battle_log。
   - **必做前置:对战级 checkpoint**(每 50 场把 battle_log 增量落盘
     `<out>.battles.partial.jsonl`,启动时加载并跳过已判对战)。暂停时 400/1552
     的进度因无此机制而作废,不许再发生。
3. **汇总**:`build_site_board_from_judge_elo.py` → 真值门控榜
   (gated = elo × gate,全员有分,裸判官为页签)。

## 6. 质量门与反作弊检查(每格出分后自动跑)

- 引用主机分布:非 localhost 主机出现即标红(编造)。
- 平局率:陪审团后整体平局率应 < 20%;某格异常高则抽查该格判官原始判定。
- 位置一致性:`['A','A']`/`['B','B']` 型判定占比为位置偏置监控指标,留档。
- 长度对照:gate 与词数的相关性监控(防"堆字数"刷分回潮)。

## 7. 分析计划

- 主效应:行均值(框架效应,固定列)、列均值(模型效应,固定行)。
- 交互:P0 六格 2×3 方差分解;关键假设检验:
  H1 框架排序跨模型稳定;H2 qwen3-32b 接地优势可迁移;H3 qwen3-max 的高编造率
  可被强脚手架部分抑制。
- 不确定性:Elo 用 bootstrap 95% CI;gate 用任务级 bootstrap。
- 呈现:矩阵热图(gate)+ 每格 (gated Elo, gate, 成本/任务) 三元组;
  模型基线行与框架列在站点分区展示,不混入同一张 Elo 表。

## 8. 成本与时长估算

| 项目 | 估算 |
|---|---|
| eff 行补列(每模型) | 约 17 分钟(3 分片)+ $0.1-0.5(便宜档)/ $3-7(旗舰档) |
| 框架格(每格) | 4-8 小时 + $2-15(模型价而定) |
| 陪审团全量重判 | 1553 场 × 3 判官 ≈ 9300 次调用,3 路并行 5-9 小时,$30-40 |
| P0 六格 + 重判 | 约 2-3 天 box 时间,$60-120 |

## 9. 暂停/恢复手册

见规划文档第 7 节。原则:任何长任务必须满足
(a) tmux 常驻 (b) 断点续跑 (c) 看门狗守护 (d) 逐步日志(PYTHONUNBUFFERED)
四件套,缺一不许上线。
