# DeepResearchArena (DRA) 项目进展汇报

文档日期：2026-06-09
适用仓库：/root/Desktop/lyb/deep_reserch
线上站点：https://www.deepresearcharena.com

---

## 1. 项目定位与目标

DeepResearchArena (DRA) 是一个面向 Deep-Research AI 智能体的评测基准。它在一个不可变的沙箱网页环境里运行评测，沙箱包含三个站点：Magento 购物站 (端口 7770)、Postmill 论坛站 (端口 9999)、kiwix 维基站 (端口 8090)，要求被测智能体完成跨站点的深度研究任务。当前项目目标已由用户确认：**不再做 RL 训练，而是把它建设成一个真正高质量的 Deep-Research 评测基准**，包含约 120 个跨站点任务、跨厂商可复现、接地可验证、诚实且有区分度的打分、以及人类对齐证据，并配套一个真实在线的排行榜。锁定的打分方法学是 "truth-gated Elo (真值门控 Elo)"：headline = 判官 Elo × 接地门控，其中 `gated_score = round(elo × (reachability% + url_veracity%)/200)`。目前线上有两块榜：框架榜 (12 个智能体，含 claude-code、opencode) 和新增的 /models 骨干 LLM 榜 (8 个 LLM)。

---

## 2. 已完成 (经核验确认)

以下每一项均经过逐文件、逐数字核验 (confirmed)，被反驳 (contradicted) 或仅停留在文档层面 (aspirational) 的内容已剔除到第 5 节待办。

### 2.1 评测集与 golden

- **主评测集就是 100 个跨站点深度任务**。证据：`data/tasks/deep_research/cross_site_deep/` 下恰有 100 个匹配 `dr_cross_deep_[0-9]+.json` 的任务文件，外加 `checklists_deep.json`。
- **100 个任务的清洗后 golden 已全部写出**。证据：`data/golden/deep_clean/` 含 100 个 `dr_cross_deep_*.json` + `_manifest.json`；schema 为 `must_cite_urls / expected_pool_urls / triples / metadata`，每条 cite 带 `url/category/weight/why`。
- **可计分任务的权威口径 = 75 个 (65 valid + 10 forum-invalid)，25 个隔离 (quarantine)，0 个 broken**。证据：`data/golden/deep_clean/_manifest.json` 中 `canonical_scorable=75`，`counts={valid:65, forum-invalid:10, quarantine:25}`，已从头独立重算复核。
- **manifest 可从文档复现**。证据：运行 `scripts/build_clean_benchmark_manifest.py` 重新生成的 `_manifest.json` 与原文件**逐字节一致 (byte-identical)**；脚本真正解析 `docs/EVAL_SET_REMEDIATION.md` 的第 2 节 (正则 `_TASK`/`_SRC`)，并硬断言 `counts==65/10/25`、`scorable==75`、`len==100`，文档漂移会立即触发解析失败。
- **per-task 来源限制 (valid_sources) 分布已核验**。证据：`_manifest.json` 重算得 36 个 forum+shopping+wiki、26 个 forum+wiki、13 个 shopping+wiki、25 个 NONE(隔离)；75 个可计分内 wiki 全保留 75、forum 保留 62、shopping 保留 49；10 个 forum-invalid 全为 shopping+wiki。
- **闭卷污染探测通过**。证据：`docs/CONTAMINATION_REPORT.md` = `PASS_NO_MEMORIZATION`，Clean 5/5、Suspicious 0/5、Contaminated 0/5，0 个 URL 泄漏，0 个 golden 价格命中，mean specificity 0.0，探测模型 `qwen3-30b-a3b-instruct-2507`。**注意：仅探测了 100 个任务中的 5 个 (0001-0005)**，该范围限制在报告中是明确写出的。
- **配套工具齐全且真实**。`scripts/build_deep_golden.py` (28171 字节，防御式 try/except 抓三个沙箱源)，原始 golden 在 `data/golden/deep/` (103 个真实 JSON + 2 个 .bak)；`scripts/clean_golden_titles.py` (音频正/负则匹配 + 经 westd 隧道抓标题)。

### 2.2 打分方法学与排行榜

- **truth-gated Elo 公式已实现并与锁定规范一致**。证据：`frontend/lib/data/load-leaderboard.ts:215-222` 与 `frontend/lib/data/load-models.ts:80-87`：`gate=(reachability_pct+url_veracity_pct)/200; gated_score=Math.round(elo*gate)`，按 `gated_score` 降序排序。**该计算在前端 TypeScript 完成，Python 构建脚本不写 gated_score**。
- **框架榜已提交，门控排名可从 JSON 复现**。证据：`data/results/deep_v3/leaderboard_deep_v3.json` 重算：① claude-code elo=1166.4 reach=90.1 quote=86.8 gated=**1032**；② opencode 1078.0/94.1/86.8 gated=**975**；⑪ gpt-researcher 1147.0/4.3/2.2 gated=**37**；⑫ qx-agents 441.9/2.6/0.0 gated=**6**。线上 `web/dist/api/leaderboard` 的 12 行与重算的顺序及 gated_score 完全一致。`judge` 子对象内 `n_battles=2615`、`n_tasks=74`、`judge_errors=0`，`jury=['deepseek-v4-flash','qwen3-max','glm-5']`。
- **骨干 LLM 榜已提交，门控排名可从 JSON 复现**。证据：`data/results/deep_v3/leaderboard_models_v3.json` (n_tasks=24, n_battles=643) 重算：① glm-5 elo=1013.3 reach=60.4 quote=57.2 gated=**596**；④ deepseek-v4-flash 1155.9/26.4/26.9 gated=**308**；⑦ qwen3-max (raw elo 最高 1174.2) gated 跌到 **244**。8 个 LLM 完整为 eff-deepseek-v4-flash / eff-glm-5 / eff-kimi-k2.5 / eff-minimax-m2.5 / eff-qwen-flash / eff-qwen3-30b-a3b-instruct-2507 / eff-qwen3-32b / eff-qwen3-max。
- **死信号 claim_nli 已确认接近失效**。证据：`data/results/deep_v3/` 下 349 个 `*_matrix.score.json` 中 claim_nli 有 345 个为 0 (98.9%)，仅 4 个非零，mean 0.0034，max 0.625。(文档 `FINDINGS_2026-06-09.md:73` 说它 "恒为 0" 是轻微夸大，功能上确实无区分度。)
- **可膨胀 vs 有区分度信号的取舍已实现**。证据：`scripts/assemble_discriminative_board.py` 用 OLS 对 presentation 做 word_count 长度残差化 (`--w-reach=0.75`、`--w-pres=0.25`、`--floor=0.30`)，使啰嗦无法抬高分数；`QUALITY=0.75×reachability+0.25×presentation_lenadj`。
- **接地门控 recall-vs-quote 分量分析已提交且可复现**。证据：`docs/GROUNDING_GATE_ANALYSIS.md` + `scripts/analyze_grounding_gate.py`：quote_match 在诚实组 0.58-0.86 vs 捏造组 ~0.001-0.002 有强区分；curated_recall 区分弱 (诚实 0.12-0.25 vs 捏造 0.069-0.076)；recall_w 从 0.3 时分离度 +0.459 降到 0.8 时 +0.188 (AT RISK，最低诚实 0.250 跌破 0.30 floor)。结论：保持 `0.5×recall + 0.5×quote`。
- **接地缓存已提交，10/12 智能体与榜单完全一致**。证据：`data/results/grounding_uniform2.json` (1027 行)，camel-ai、deerflow、gpt-researcher、ii-researcher、langchain-odr、ldr、qx-agents、smolagents、storm、flowsearcher-ds 的 reach%/quote% 与榜单 `per_agent_profile` 逐位一致。
- **判官无关的接地打分流水线齐备**。`scripts/build_sandbox_cache.py` (每个去重 URL 抓一次 → `{url:{status,text}}`)、`scripts/score_grounding_from_cache.py` (装 sandbox_http_cache，跑 URLReachabilityVerifier + QuoteMatchVerifier + curated_recall，无判官调用)；三端口 7770 购物 / 9999 论坛 / 8090 维基。

### 2.3 判官陪审

- **3 判官 PoLL 陪审已在代码中存在且跑到收敛：1553 场对战，全部 3 判官投票，0 个判官错误**。证据：`data/results/real/leaderboard_jury_elo.json` summary：`jury_size=3`、`min_valid_jurors=2`、`valid_juror_distribution={"3":1553}`、`n_judge_errors=0`、`n_degraded_below_floor=0`；遍历全部 1553 条 battle_log 每条 `len(verdicts_raw)==3`。
- **静默 "判官出错 → 判平局" 的 bug 已定位并修复**。证据：bug 源 `src/scoring/pairwise_judge.py:203` `if text is None: return "tie", f"(judge error: {err})"`；修复在 `scripts/build_real_leaderboard.py`：`is_judge_error_result` (line 433)、`_n_valid_jurors` (line 780，用 `judge_errors_partial` 计数而非 `verdicts_raw`)、`_min_jurors=2` (line 774)、retry `_juror` (`JURY_JUROR_RETRIES=3`)。
- **平局率从 50.6% 降到 16.9%**。证据：`data/changelog.json` 条目 `v3-2026-06-06a`；从原始数据重算 winner=='tie' 为 262/1553 = 16.87%；83.1% 对战有决定性结果 (一致 27.7% + 多数 54.9%)；分判官决定性 deepseek 68% / glm 61% / qwen 50%。
- **两阶段污染拦截 ("914 假干净" 事件) 已记录**。证据：`docs/JURY_REJUDGE_GOAL_2026-06-06.md:95-114`：首版 "收敛" 榜 `n_judge_errors=0` 但只有 639 真干净 / 914 仍单判官，二次修复改用 `judge_errors_partial` 计数，正确口径 clean=656 / degraded=897。
- **位置交换去偏 + n_samples=3 + Bradley-Terry bootstrap CI**。证据：`pairwise_judge.battle()` 默认 `swap_for_position_bias=True`，`n_samples=3`；`src/scoring/bradley_terry.py` 定义 `bootstrap_ci` 与 `fit_bradley_terry`；榜单 `elo_v3_ci['camel-ai']` = {elo 1039.9, elo_lo 1008.8, elo_hi 1094.2, half_width 42.7, n_battles 409}。
- **标签无关的判官对齐已用 3 种方法验证 (真实落盘工件)**。证据：合成 golden 扰动 + 接地相关性 + LLMBar 借用人类标签，harness 为 `scripts/judge_meta_eval.py`。
  - deepseek-v4-flash 运行 (`data/judge_gold/meta_eval_synth_v2.json`)：synth-gold **0.9062 (29/32)**，分型 drop_citations 0.75、inject_false 1.0、truncate 1.0、shuffle 0.875。
  - **glm-5.1 运行 (`data/judge_gold/meta_eval_results.json`) 也已落盘并通过**：synth-gold **1.0 (32/32)**，LLMBar Natural **0.94 (47/50)**，Spearman vs must_cite_recall rho=0.494 (p=0.213, n=8)。

### 2.4 接地信号

- **reachability% 判官无关计算**。证据：`src/verifiers/url_reachability_verifier.py:130-177`，仅对沙箱 URL (host:port 精确匹配) 算 HTTP-200 率，`resolvable=total-5xx-net`，4xx 计为捏造，5xx/网络错误排除出分母 (沙箱重启不算捏造)，默认 `min_reachability_rate=0.30`，workers 4 / max_urls 200 / timeout 6.0s / retries 3。
- **quote_match% 判官无关计算**。证据：`src/verifiers/quote_match_verifier.py`，抓 URL 去 HTML 后用 约 400 字符上下文 token 重叠 (ctx 归一化包含率，非对称)，`jaccard_threshold=0.10`，max_urls 150，页面文本截 20000 字符。
- **curated must-cite recall 判官无关**。证据：`src/verifiers/golden_curate.py` 确定性 top-K (按 weight、review_count、星级、稳定序，k=12)，`score_grounding_from_cache.py:57-74` 读 `data/golden/deep_clean/<task>.json` 并按 valid_sources 过滤。
- **cache-once-then-score 设计存在**。证据：`scripts/build_sandbox_cache.py` (每个去重 URL 抓一次，kiwix /wiki->/content 重试，每 250 个 checkpoint)、`src/verifiers/sandbox_http_cache.py` (monkeypatch requests.get，文本截 40000)。
- **门控公式确已接入两块线上榜**。证据：`load-leaderboard.ts:216-220` 与 `load-models.ts:81-85` 同一公式；12 个 `per_agent_profile` reach/quote 全部与 `leaderboard_deep_v3.json` 一致 (claude-code 90.1/86.8、opencode 94.1/86.8、camel-ai 60.0/50.1、gpt-researcher 4.3/2.2、qx-agents 2.6/0.0 等)。

### 2.5 沙箱与基础设施

- **统一单命令沙箱 compose 存在且结构完整**。证据：`infra/sandbox.docker-compose.yml` 定义 5 个服务于一个 bridge 网络：shopping 7770->80、reddit 9999->80、wiki 8090->8080、gateway 8081->8081、ds_proxy expose 8088 (不发布)。
- **每个服务都设了 `restart: unless-stopped`**。证据：compose L44/62/80/105/118，外加 `envs/shopping/docker-compose.yml:5` 与 `envs/reddit/docker-compose.yml:5`。
- **所有服务有 healthcheck，gateway depends_on 三个站点 service_healthy**。证据：compose L50-55/66-71/90-96/134-139，shopping start_period 90s，interval 10s / timeout 5s / retries 30。
- **gateway 与 ds_proxy 的 `/healthz` 端点在代码中真实实现**。证据：`integrations/search_shim/app.py:984-986`、`integrations/ds_proxy/app.py:267-269`。
- **gateway 接线**：`SHIM_LLM_UPSTREAM -> ds_proxy:8088/v1`，ds_proxy 为 OpenAI 兼容透传到 DeepSeek 且注入 thinking-disabled。证据：compose L121-127、Dockerfile.gateway / Dockerfile.ds_proxy、`ds_proxy/app.py:217`。
- **并行验证 overlay compose 存在**。证据：`infra/sandbox.verify.docker-compose.yml` (端口 17770/19999/18090/18081，`-p drv2verify`)。
- **已知失效模式已准确记录**：WSL 拆除导致容器悬挂、镜像在 Docker Desktop vhdx (D 盘 约 222GB)、credsStore=desktop.exe 破坏 compose、box 无法访问 docker.io/ghcr.io、SSH 断开后 约 13s 杀掉脱管进程。证据：`docs/SANDBOX_RECOVERY.md:17-44` 与 auto-memory。
- **无 Docker 的恢复路径已记录 + reset.sh 存在**。证据：`docs/SANDBOX_RECOVERY.md:31-44` (kiwix 静态二进制 v3.8.2 + uvicorn shim/ds_proxy)；`envs/shopping/reset.sh` (down -v + up + 120s 等健康 + 重写 Magento base_url)、`envs/reddit/reset.sh` (无 base_url 重写)。

### 2.6 站点与部署

- **生产应用 = `frontend/` Next.js 静态导出** (`output:'export'`、`trailingSlash:true`、`images.unoptimized`)，构建到 `frontend/out`，再 rsync 进入提交的 `web/dist` (290 个 git 跟踪文件)，推送 GitHub main 后 Cloudflare 自动重新部署。证据：`frontend/next.config.js`、`CLAUDE.md:12,33`、`web/dist/wrangler.jsonc` (266 字节)。
- **本地 HEAD == origin/main == commit `ee25063a`** (即 /models 那次提交)，已部署。证据：`git rev-parse HEAD`/`origin/main`；remote = github.com/yibol9768-alt/deep-research-arena。
- **两块榜确认线上存活**。证据：curl `https://www.deepresearcharena.com/` 返回 HTTP 200 且含 12 个框架智能体 (含 claude-code、opencode)；`/models` (307 跳转后) HTTP 200 且含 deepseek-v4-flash、glm-5、kimi-k2.5 等 8 个 LLM 及 "Backbone"/"truth-gated" 字样。
- **路由 /models、/annotate、/status、/methodology 均存在且线上 200**。证据：对应 `page.tsx` 均存在，`web/dist/models/index.html` (78621 字节) 已提交。
- **标注后端是真实的 Cloudflare Worker**。证据：`web/worker.js` (5004 字节/117 行) 实现 POST/GET `/api/annotate` -> KV `ANNOTATIONS`，外加 `/api/annotate/count` 与 `/api/status`；`web/dist/wrangler.jsonc` 接线 `main='../worker.js'`，绑定 KV id=7cffb8c6dcc74205854cb67f5fec4cc0。
- **changelog.json 19 条**，最新 4 条：`v3-2026-06-08b` (2026-06-08，/models 榜)、`v3-2026-06-08` (2026-06-08，加 claude-code/opencode)、`v3-2026-06-06b` (2026-06-06，平局 51%->17%)、`v3-2026-06-06a` (2026-06-06，3 判官重判 + 静默平局 bug 修复)。

### 2.7 人类对齐 (仅标签无关部分为真实)

- **标签无关的判官对齐 harness 真实存在并有落盘工件** (见 2.3 末尾)。`data/judge_gold/` 含 `llmbar_natural.json` (100 个缓存对)、`meta_eval_results.json` (glm-5.1)、`meta_eval_synth_v2.json` (deepseek)。
- **/annotate 人类偏好采集页已构建并上线**。证据：`frontend/app/annotate/page.tsx` (789 行)，bundle `frontend/public/annotate-pairs.json` (3,676,196 字节，三处都有)。
- **人类评测协议 + kappa 流水线脚本已写 (仅规范，未跑真实数据)**。证据：`docs/HUMAN_EVAL_PROTOCOL.md`、`scripts/build_kappa_pairs.py` (179 行，`--max-pairs` 默认 48)、`scripts/compute_judge_human_kappa.py` (204 行，对 kappa<0.40 且 n>=10 的维度报警)、`data/human_prefs/SCHEMA.md`。

---

## 3. 关键发现 (作为研究结论)

### 3.1 判官偏好与接地真实度解耦 (核心发现)

裁判 LLM 的偏好和报告的接地真实度并不一致：原始判官 Elo 排第一的智能体，在真值门控下会沉底。

- **框架榜**：gpt-researcher 原始 Elo 1147.0 (相当高)，但 reach 仅 4.3% / quote 2.2%，门控后 gated=37，排第 11；qx-agents 门控后 gated=6 排末位。判官 Elo 与接地的相关 rho=**0.32** (n=12)。
- **骨干 LLM 榜**：qwen3-max 原始 Elo 最高 (1174.2)，门控后跌到第 7 (gated=244)；glm-5 原始 Elo 仅 1013.3，但 reach 60.4/quote 57.2，门控后升到第 1 (gated=596)。判官 Elo 与接地相关 rho=**-0.31** (n=8)。

**为什么重要**：这正是基准要捕捉的核心问题，一个只会写得好看、却大量捏造/无法触达引用的智能体不应排在前面。门控把 "判官喜欢" 和 "证据可验证" 分开，让捏造者永远无法登顶。证据：`docs/FINDINGS_2026-06-09.md:102` (rho 0.32 / -0.31)、两块榜单 JSON 重算。**重大保留：rho=0.32 (n=12) 与 rho=-0.31 (n=8) 在统计上均不显著 (p 未达标)，目前该 headline 只是定性的排名反转，不是有功效的统计结论。**

### 3.2 静默 "判官出错 → 平局" bug，平局率 50.6% -> 16.9%

修复前，一次判官 API 失败会返回 ("tie", "(judge error)") 并被当成真实平局票，造成大量假平局 (主要是 position-lock)。修复并对全部 1553 场重判后，平局率从 **50.6% 降到 16.9%**，83.1% 对战变得有决定性。**为什么重要**：假平局会摧毁榜单的区分度，让强弱智能体看起来打平。证据：`changelog v3-2026-06-06a`、从 jury_elo.json 重算 262/1553=16.87%。

### 3.3 死信号与可膨胀信号的识别与剔除

- **死信号**：claim_nli 在 345/349 个打分文件里为 0 (98.9%)，无区分度，已弃用。
- **可膨胀信号**：字数、引用条数、原始 presentation 可被啰嗦刷高，已剔除；presentation 经长度残差化后才进分。
- **合法区分信号**：reachability + 长度归一的 presentation + quote_match。

**为什么重要**：一个诚实的基准必须拒绝 "写得长 = 分高" 的捷径。证据：`docs/FINDINGS_2026-06-09.md:73-75`、`scripts/assemble_discriminative_board.py:100-109`、`scripts/analyze_grounding_gate.py`。

---

## 4. 当前基准的真实状态 (诚实体检表)

| 维度 | 真实现状 | 与目标差距 | 证据 |
|---|---|---|---|
| 可计分主任务 | **75** (65 valid + 10 forum-invalid) | 距 ~120 目标缺口未补 | `_manifest.json` canonical_scorable=75 |
| 隔离任务 | **25** (语料覆盖不足，论坛第三方丢失) | 待重爬救回 | `_manifest.json` quarantine=25 |
| 对抗 v2 任务 | **20 个** (7 causal + 7 contradiction + 6 long_tail)，有 schema/intent/阈值，但 **golden 不存在，不可计分** | `data/golden/deep_v2/` 缺失，20 个任务的 triples_path 全指向不存在文件，每任务仅 6-8 个 `__MACRO__` 占位种子，0 个真实 localhost URL | os.path.exists 全 False |
| (注) 任务数口径 | 任务说明里的 "22 个对抗任务" **不准确**，实为 20 个任务文件 + index/checklist | — | index.json n_tasks=20 |
| 框架榜 | 12 智能体，2615 battles，74 任务 | **不可从仓库重建** | 见下 "复现性" |
| 骨干 LLM 榜 | 8 LLM，**24/30 任务**，643 battles | 缺 0032-0038 共 7 个任务 (约 170 场全平局待重判) | leaderboard_models_v3.json |
| 离线复现性 | **不可离线复现**。`data/results/sandbox_cache.json` 缺失 (find 全仓无)，无 `*.battles.jsonl` checkpoint，仓库内 jury 源是旧的 **10 智能体 / 1553 battles** 版 (无 claude-code/opencode)，grounding 缓存也缺这两个智能体的行 | "跨厂商可复现" 目标当前 **0% 可从仓库达成** | `build_site_board_from_judge_elo.py` 读到的是 10 智能体源 |
| 门控排名本身 | **可从已提交的 board JSON 确定性复现** (顺序 + 每个 gated_score 重算一致，与 web/dist 一致) | 复现性问题仅在上游 (原料->board)，headline 仍可从已提交 JSON 审计 | 已重算 |
| 真实人类 kappa | **不存在**。`data/human_prefs/` 只有 .gitkeep (0 字节) + SCHEMA.md，无 prefs.jsonl；`tools/human_pref_collector/pair_queue.jsonl` (300 行) 是 **未标注的待标任务**，非已采集标签 | 缺最关键的可信度锚 | 已核验目录 |
| "人类对齐" 文档 | **是合成产物，非真实**：`HUMAN_ALIGNMENT_REPORT.md` (Spearman 0.6429) 标注 "(synthetic --dry-run)"，`JUDGE_HUMAN_KAPPA.md` 标注 "(approx via pillar_elo)"，均 2026-05-22，task id 全为 "synthetic"。**这是仓库里最具误导性的一对工件** | 须用真实标签重生成后才能引用 | 文档头部源标注 |
| 标签无关对齐 (真实) | synth-gold deepseek 0.906 / glm-5.1 1.0；LLMBar 0.94 (n=50) 或文档称 0.817 (n=60，但该 60 对数据已不在盘上)；接地相关 rho约 0.49 (n=8，不显著) | 是 "可辩护证据"，但不是人类 kappa | `data/judge_gold/*.json` |
| 污染探测覆盖 | 仅 5/100 任务 | 全集污染结论尚不充分 | CONTAMINATION_REPORT.md |
| 沙箱持久化 | **半自动**：wiki+shim+ds_proxy 可无 Docker 复活，但购物站/论坛站仍需手动启动 Docker Desktop | Phase 0 目标 (wsl --shutdown 后自动恢复到 200) 未达成 | WEEKLY 文档 line 167 |
| 自愈脚本 | boot.sh / watchdog.sh / DRA_StackGuard **仅在 box 上 (/opt/.dra_tmp/)，未纳入版本控制**，无法在仓库核验 | 一旦 box 被擦除即丢失 | 仓库 scripts/ 125 文件无匹配 |

**文档-数据漂移 (部分已修)**：`JUDGE_ALIGNMENT_VALIDATION.md` 仍描述已废弃的 5000 字符判官窗口 (代码实际已是 `PAIRWISE_REPORT_CAP=12000` 头+尾截断)，待修；`EVAL_SET_REMEDIATION.md` 的 "5,121 cites" 聚合值过时 (盘上实为 5,132，差 +11 全在任务 0001)，待修；`FULL_PROJECT_ROADMAP.md` 已于 2026-06-09 重写为 v3 评测基准方向 (不再是 RL/GRPO/专利/Mac 旧框架)，已修。

**更正两处先前的误报 (本节复核后撤回)**：

1. **线上首页对战数并不矛盾**。实测 https://www.deepresearcharena.com 三处均一致显示 **2,615** (= `n_runs`)；5,230 只是 per-agent `n_battles` 求和的中间量 (每场按双方各计一次)，前端 `totalPairwiseBattles` 除以 2 后即 2,615，从不直接展示；1,553 仅出现在 2026-06-06 的 changelog 文字里，对当时的 10 智能体陪审是历史正确的，并非 live 数字。原 "三个数同时矛盾" 的判断不成立。

2. **但 `FINDINGS_2026-06-09.md` 的 "框架陪审回退到 2 判官" 方向上是对的，且实情更严重**：真实部署所依据的 12 智能体陪审源 (`data/results/real/leaderboard_jury_elo.json`，2026-06-09 从 box 取回) 的 `valid_juror_distribution = {1: 1058, 3: 1557}`，即 2,615 场里只有 **59.5% (1,557 场) 是 3 判官**，**40.5% (1,058 场) 只有 1 个有效判官** (后加入的 claude-code/opencode 多在判官账号将尽时跑，降级为单判官)。board JSON 标注 `jurors=[3 judges]` 是过度简化。**这是一条需诚实写进对外材料的重大保留**：现 live 框架榜并非干净的 3 判官榜，headline 约四成对战实为单判官，须在判官 API 充值后同批重判补齐 (任务 #45)。

---

## 5. 还要做什么 (分阶段)

### Phase 0 — 沙箱稳定化 (任务 #38/#39，进行中)
- **为什么**：box 不稳定是用户认定的头号风险，是其他一切的前置；购物站/论坛站这两个接地关键服务目前仍需手动启 Docker Desktop。
- **阻塞项**：Docker Desktop 需手动启动；box 无法拉/重建重型 shopping/postmill 镜像 (docker.io 不通、ghcr.io 401)；binfmt interop 每次重启需重做。
- **零阻塞可立即做的**：把 seed 折进 reset.sh bring-up；修 kiwix book 配置不一致 (compose 默认 `wikipedia_en_simple_all_maxi` vs shim/恢复路径 `wikipedia_en_all_nopic`，否则 wiki URL 可能 404 拖垮接地)；把 boot.sh/watchdog.sh/StackGuard 纳入版本控制；补 `infra/wiki-zim` 默认挂载目录 (现缺失会导致 wiki 起不来)。

### Phase 1 — 语料扩展 + 重爬 golden (任务 #40，进行中)
- **现状**：种子工具与数据已就绪并提交 (`data/corpus_seed/forum_threads.json` 300128 字节，254 条非技术贴，38 个论坛含 34 个净新论坛，映射到 25 个隔离任务 id；`scripts/seed_forum_corpus.py` 166 行幂等)。
- **为什么**：根因是 Postmill 论坛是纯技术语料，导致 25 隔离 + 10 forum-invalid 任务丢了论坛第三方；重爬后可计分集有望从 75 升向 ~95-100。
- **未做的部分**：种子未跑进真实 box (所有受影响 golden 仍是 2026-06-03，`dr_cross_deep_0014` 仍 46 条全 wiki、0 条论坛 cite)；种子非持久 (`envs/reddit/reset.sh:13` `down -v` 会擦掉)。
- **阻塞项**：需 my5090 box 沙箱在线先跑 `seed_forum_corpus.py` 再跑 `build_deep_golden.py`；且容器名不一致 (reset.sh 用 webarena_reddit，种子脚本默认 dr_sandbox_reddit) 需注意；**任务晋级是手动编辑 `EVAL_SET_REMEDIATION.md` 第 2 节裁定 + 重生 manifest，非自动流水线**。

### Phase 2 — 对抗任务 golden (任务 #41，待办)
- **为什么**：把任务总量推向 ~120；20 个对抗任务目前只有占位种子，不可计分。
- **阻塞项**：需 my5090 沙箱抓取并把结果落到 `data/golden/deep_v2/`，且需单独再清洗/重生 manifest。

### Phase 3 — 统一打分 + 分数入库 (任务 #42，进行中)
- **为什么**：让基准离线可复现、不再依赖脆弱的 box；当前接地覆盖不均，`grounding_uniform2.json` 已过时 (15 个抽查里 7 个 curated_recall 与当前 golden 不符，如 camel-ai 0001 存 0.0 重算 0.1667、smolagents 0003 存 0.0 重算 0.6667)。
- **要做**：把 `sandbox_cache.json` 构建并 **提交进仓库**；重新生成 `grounding_uniform2.json`；把 claude-code/opencode 的接地行补进缓存；重新提交 12 智能体/2615-battle 的 jury 源 + `*.battles.jsonl` checkpoint (否则连陪审成员标签都会重生成为空)；缓解 cache 中毒风险 (一次瞬时抓取失败被存成 status 0/空文本并永久服务)。
- **阻塞项**：需 box 沙箱在线 (无缓存的重打分会挂，60s 超时)。

### Phase 4 — 锁定打分方法学 (任务 #43，待办)
- **为什么**：最终文档锁定。
- **要做**：统一两套并存的接地门控表述 (`simple_score.py` 的离线 per-report F1 硬门控 vs `load-leaderboard.ts` 的 headline 乘性门控)；floor 校准与显著性；统一文档与数据漂移。
- **阻塞项**：依赖 Phase 5 (真实 kappa) 先存在。

### Phase 5 — 真实人类 kappa (任务 #32，待办)
- **为什么**：headline 人类对齐当前无支撑，只有合成/借用代理；这是可信度锚。
- **要做**：招募真实标注者采集 prefs.jsonl → 跑 `build_kappa_pairs.py` + `compute_judge_human_kappa.py` → 用真实标签重生成 `HUMAN_ALIGNMENT_REPORT.md` / `JUDGE_HUMAN_KAPPA.md` 替换合成版；并核验线上 `/api/annotate` 是否真的持久化一次 POST (这是唯一未测的人类数据采集环节)。
- **阻塞项**：需真实标注者；后端代码已就绪 (web/worker.js + KV 绑定)，但线上持久化未实测。此阶段独立于 box/funding。

### Phase 6 — 重算上线 + 定稿文档 (含任务 #45)
- **为什么**：把扩展后的全量场重算、重判模型榜 0032-0038 (24->30 任务) 并把框架陪审从 2 判官升回真 3 判官，最后定稿。
- **阻塞项**：**判官 API 欠费** (deepseek "402 Insufficient Balance"、DashScope/百炼 "400 overdue-payment")，即任务 #45，须用户充值/换 key。
- **统计功效 (任务 #12)**：扩到 30+ 任务以让 rho 显著，需 box 稳定 + 判官 API + Phase 1/2 的任务供给。

---

## 6. 阻塞与依赖

两个根阻塞门控了几乎一切：**(A) box/沙箱稳定性 (Phase 0)** 与 **(B) 判官 API 欠费 (#45)**。

```
[A] box/沙箱稳定 ──┐
[B] 判官 API 充值 ──┤
                   ▼
[C] 构建并提交 sandbox_cache.json (需 A) ──► 解锁全部离线复现 (接地/打分/语料 Phase C)
     ├─► [D] 重提交 12 智能体/2615 *.battles.jsonl + jury 源 (需 A+B) ─► 榜单可重建
     │        └─► 框架陪审 2->3 判官 (需 B)
     ├─► [E] 重生 grounding_uniform2.json (7/15 recall 不符)
     ├─► [F] 补 claude-code/opencode 接地行
     └─► [G] 语料: 跑 seed -> 重爬 35 任务 -> 重清洗 -> 手改裁定 -> 重生 manifest
[B] 还独立解锁: 重判模型榜 0032-0038 (24->30)
[A] 解锁: [H] 构建 20 个对抗 v2 golden (#41)
[I] 真实标注者 (#32) ── 独立于 A/B/C ──► prefs.jsonl -> kappa -> 重生人类对齐文档 + 实测 /api/annotate
[J] 扩到 30+ 任务求显著 (#12) ── 需 A+B，依赖 G/H 供给任务
[K] 最终锁定 (#43) ── 依赖 I (真实 kappa) + J (显著性)

零阻塞、即刻可做 (不需 box/不需充值/不需标注者):
  折 seed 进 reset.sh / 修 kiwix book 配置 / 把 boot.sh/watchdog 入库 /
  统一过时文档 (对齐判官 5000->12000 窗口、cites 5121->5132；roadmap 已修) /
  处理 28 文件的前端重构工作树 (提交或丢弃) / 把污染探测扩到任务 6-100
  (注: "首页 battle 计数矛盾" 经复核为误报，已从清单移除，见第 4 节)
```

任务跟踪器权威状态：
- **DONE**：#36 (清洗 golden + per-task 来源限制)、#37 (接地门控重权到 must-cite recall)、#39 (Phase 0 统一 compose)、#33/#34/#44 (部署真实分数 + 跑框架 + 多厂商模型榜上线)。
- **IN_PROGRESS**：#38 (box 门控批处理: 扩 N、补缺失框架、重做 board)、#40 (扩论坛语料 + 重爬 golden)、#42 (全量统一打分 + 分数入库)。
- **PENDING**：#12 (扩到 30+ 任务 x 智能体 + 显著性)、#32 (落实人类偏好标签)、#41 (20 个对抗任务 golden)、#43 (锁定打分 + 人类 kappa + 部署文档)、#45 (判官 API 充值 -> 重判模型榜 0032-0038 24->30 + 框架陪审 2->3 判官)。

---

## 7. 优先级建议 (下三步)

1. **立刻做零阻塞清理** (不需 box/不需充值)：修 kiwix book 配置不一致、把 seed 折进 reset.sh、把 boot.sh/watchdog/StackGuard 入库、统一所有过时文档与首页 battle 计数 (1553/5230/2615 三个数当前同时存在且矛盾)、处理 28 文件的前端重构工作树。这些直接消除 "文档骗人" 风险且本周内可完成。
2. **并行解决两个根阻塞**：给判官 API 充值 (#45) + 稳定 box (#38/#39)。这是真正的关键路径，其余阶段都挂在它们下面。
3. **一旦 box 在线，先做 `sandbox_cache.json` 构建并入库 + 重提交对战 checkpoint (Phase 3 的 C/D)**。这一步成本最低、收益最高：它让现有两块线上榜从 "只能从成品 JSON 审计" 变成 "可从原料完整重建"，直接兑现 "跨厂商可复现" 这一核心目标，再据此推进语料重爬 (Phase 1)、对抗 golden (Phase 2)，以及全程并行招募真实标注者 (Phase 5)。

**最诚实的一句话总结**：打分方法学 (truth-gated Elo、判官无关接地门控、修复了静默平局 bug 的 3 判官 PoLL) 是真实、已实现的，headline 反转可从已提交 JSON 审计；但 "好基准" 四根支柱里有三根尚未到位:**任务规模 (75 而非 120)、可复现性 (榜单不可重建、关键工件未入库/仅在 box 上)、人类对齐 (零真实标签，合成文档伪装成真实)**。区分度打分是最强的一条腿，可复现性与人类证据是最弱的两条,且都被不稳定的 box 加上欠费的判官 API 卡住。