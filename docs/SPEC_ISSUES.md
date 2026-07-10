# SPEC_ISSUES：语义层面待拍板问题清单

依据 `docs/GOAL_GATES_V1.md` 冻结令第 2 条建立：执行期发现的"语义层面不合理"一律不修，
记录于此等用户拍板；只有"实现与既定语义不符"的 bug 才转闸门（G0-G6）修复。

- 核实基线：commit `084de62f`（工作树干净），核实日期 2026-07-09。行号以该基线为准。
- 来源标签：`[WF]` = 8 镜头公平性审计 workflow（wf_a49d248c-9e1 journal，33 条 finding，
  其中 1 条被 3 个独立证伪 agent 全票击杀，见 §3）；`[R5]` = internal/docs/AUDIT_ROUND5_UNVERIFIED_2026-07-09.md
  的 25 条原始候选；`[OPEN]` = internal/docs/OPEN_DECISIONS_2026-07-09.md / HANDOFF §6 四个分叉；
  `[已知]` = 收割任务附带的已知候选。
- 每条判断三选一：**真语义问题**（等拍板）/ **实为实现 bug**（注明转哪道闸门）/ **已过时**（已修复或已证伪）。

---

## 1. 真语义问题（待用户拍板，冻结期一律不动）

- [ ] [WF] score_completeness 的 fetch 门槛把 snippet-only 架构（storm、langchain-odr，协议声明 fetch_mode: none）结构性打成 0：有 transport 证据时每个完备性槽位都要求源页在 fetched_ok，而这两条车道按架构 fetched 永远为空；影响：默认 transport 榜上这两条车道 completeness（0.33 权重）全任务恒 0，榜单实际在排"有没有 fetch 工具"，与 pof 轴对 snippet_only "不以参数记忆冤枉它"的口径自相矛盾；文件：src/eval/decidable_scorer.py:1762-1809、config/lane_protocol.yaml:167-182、src/eval/fetch_log.py:23-34；建议选项 A=对声明 fetch_mode:none 的车道豁免 fetch 要求（退回词面引用口径，同其 pof 的 snippet_only 处理），B=维持"读页是任务能力的一部分"，但榜单必须渲染"该车道结构性无法得此轴"徽章。判断：**真语义问题**（已在当前代码复核为真）。

- [ ] [已知][WF] 无 page cache 时概念/论坛槽位静默不可覆盖，withhold 语义未定：`_concept_quote_supported` 无缓存条目直接 False，`_forum_coverage_supported` 跳过缓存缺失线程，但两类槽位仍留在分母；build_truth_board `--cache` 缺省为 {} 且无任何警告拒绝；影响：约 278 概念槽 + 100 论坛槽 ≈ 24% 完备性分母对所有车道静默归零，违反"withhold 不打 0"总原则却无既定语义可依；文件：src/eval/decidable_scorer.py:1615-1616、1699-1708、1799-1801、1859；scripts/build_truth_board.py:773、840；建议选项 A=缓存缺失的槽位从 k_effective 分母剔除（withhold 语义），B=正式榜无 --cache 直接拒绝构建（fail-closed），并对"缓存里没有该线程"的论坛槽单独定义 withhold。判断：**真语义问题**（缓存覆盖面的采集缺陷另列 §2 转 G4）。

- [ ] [已知] fact 轴 supported_out_of_scope 记账口径：范围外（非任务相关产品）的正确报价/评分计入 precision 分子分母但不计 recall 体积；影响：报告可用离题却正确的目录事实无风险刷高 precision，稀疏但全对的任务内报告反而不占优；文件：src/eval/decidable_scorer.py:1325-1337、1414-1424、1438；建议选项 A=维持现状（范围外只验精度不买体积），B=范围外正确声明整体移出 tested（precision 只对任务内声明计），错误声明仍计矛盾。判断：**真语义问题**。

- [ ] [已知] 同句/同行引用要求对多行论证型报告是否过严：inline_fact_citation_required 要求声明句内出现指向同一产品的引用才可买 recall（supported_uncited 不计体积），inline_nugget_citation_required 要求 nugget 值与引用同一 Markdown 行；影响："先陈述两三句、段末统一给引用"的论证型写法被系统性降 fact recall 与 completeness，惩罚的是文风而非事实性；文件：src/eval/decidable_scorer.py:1211-1214、1249-1264、1297、1747、1805-1814；data/golden/answer_keys/*.json metadata 两开关均为 true；建议选项 A=维持句/行级绑定（最强反洗白），B=放宽到段落级窗口（引用与声明同段即绑定），保留反"报告顶部引用倾倒"的隔离。判断：**真语义问题**。

- [ ] [已知][HANDOFF §3 分母段] k_star 饱和上限与逐题池子口径：设计文案是饱和召回 min(covered/K*,1)、池 3K*=60，实际 100 题池仅 14-17 < K*=20，分母改为 min(K*,|pool|) 后完备性事实上变成"普查"（须覆盖全池才 1.0），饱和从不生效且分母逐题在 14-17 间浮动；影响：单条 vital 的边际价值随任务在 1/14-1/17 波动，"覆盖任意 K* 条即满分"的宣称语义与实现不再是一回事；文件：src/eval/decidable_scorer.py:1464-1466、1727-1736、1853-1861；建议选项 A=下调 K*（如 10）恢复真实饱和且跨任务统一，B=承认普查语义，改文案与 docstring 为"覆盖全部 vital 池"。判断：**真语义问题**（aggregate() 里 micro_comp 仍用 k_star*n 的旧分母属实现不一致，另列 §2 转 G6）。

- [ ] [OPEN #1][R5] 论坛是否入分（最高影响分叉）：vital 池 1200 商城 + 278 维基 + 0 论坛，fact 只见商城；现状中间态是每题 1 个"虚拟论坛槽"（约占完备性 1/15-1/18）；影响：0.72 的质量权重对论坛近乎失明，从不打开论坛的车道几乎不损失，而 README/DATASHEET 仍称三源评测；文件：scripts/build_answer_keys_v2.py:281-297、src/eval/decidable_scorer.py:1639-1719、1755-1756；建议选项 A=构建真实论坛 vital nugget（thread_score/comment_count 等可判定谓词）让论坛真正挣 completeness/fact，B=维持商城+维基计分，把计分处的"三源"表述全部改掉（虚拟槽是否保留一并定）。判断：**真语义问题**（OPEN_DECISIONS 原文推荐 A）。

- [ ] [OPEN #2][WF] 跨底模三重不对称是否等化：thinking qwen ON / glm ON / deepseek OFF，且 max_output_tokens 8192 仅 glm 例外 131072，qwen 的 CoT 却在同一 8192 里吃预算；影响：三个底模的可见输出预算各不相同（deepseek 8192 无思考、qwen 8192 减思考、glm 131072 减思考），跨底模榜"只换模型"的宣称为假，qwen 被双重压制；glm 例外的发放还依路由门不同（gateway 的 floor 把所有请求抬到 131072，ds_proxy 门维持车道自报的小预算），单底模 glm 榜内部车道间预算也可差 16-32 倍；文件：config/lane_protocol.yaml:96-117、integrations/llm_gateway/app.py:80、93、scripts/preflight.py check_backbone_sampling；建议选项 A=等化（全底模 thinking 统一 + 统一 8192，推翻 2026-07-06 决定），B=给 qwen 同等预算例外或改为"可见输出预算"计价；C=维持不对称但在所有跨底模视图渲染 confound 徽章，或把跨底模行撤出头条榜。判断：**真语义问题**（声明与 preflight 披露已就位，选边是用户的）。

- [ ] [OPEN #3][WF] 门控用 reach 还是 provenance，以及"先猜后取"洗白：fetch_log 自己命名了"引用前先 fetch 一把猜出来的 URL 是伪造 pof 最便宜的方式"，但 pof 与 provenance 两个记分量都全额授信，"guessed" 诊断从不上榜；影响：靠参数记忆猜维基 URL（真实可猜）再走 shim 取一遍的车道，与诚实检索驱动的车道分数完全相同；历史数据里换门控曾使 ldr #3→#8、opencode #1→#8；文件：src/eval/fetch_log.py:35-37、549-582、src/eval/decidable_scorer.py:2040-2043、scripts/build_truth_board.py（行不带 transport/provenance_counts）；建议选项 A=维持 reach 门控，但把 provenance 与 guessed 占比作为列发布并加 --gate 戳防混比，B=把门控换成 provenance（或从其分子中扣除 guessed），接受榜单重排。判断：**真语义问题**。

- [ ] [OPEN #4] fact 轴沉默与错误是否区分：tested==0 时 fact=0.0，与"每条声明都错"（precision 0）在 truth 里同分；影响：不做可核查声明的报告与满纸错价的报告并列，反捏造轴没做它名字里的事；但商城 302 修复前该轴 92.7% 读 0 部分是仪器问题，须先重测；文件：src/eval/decidable_scorer.py:1433-1437、fact_active 仅入 detail；建议选项 A=重测后维持"沉默=0"（沉默不是免检），B=拆成 accuracy（对做了声明的报告）+ 独立 contradiction 罚项，沉默走 withhold/权重重整。判断：**真语义问题**（前置条件：修好商城后重测再拍板）。

- [ ] [WF] usefulness jury 的 walkover 语义与设计契约相反：代码给交付 stub 的一方记满额 BT 败绩并全权重入 fit，设计文档（USEFULNESS_JURY_DESIGN_2026-07-07.md:142）写"跳过即弃权，记 walkover 不记败"，且 jury 没有 truth 榜那样的 infra/rerun 区分，watchdog 杀掉的跑法直接变成"人类不喜欢它"；影响：presentation 列与 truth 榜平局裁决被引擎故障污染，属项目定义的"冤案"类；文件：scripts/run_usefulness_jury.py:614-642、735-740（walkover 全额入 battles，仅从 fleiss 干净计数剔除）、tests/test_usefulness_jury_integrity.py:43 钉的是记败语义；建议选项 A=按设计文档改回弃权不记败（接受幸存者偏差风险并另行披露交付率），B=维持记败但把 infra 类 stub（timeout/watchdog）单列为欠账不入 BT，交付率单独成列。判断：**真语义问题**（文档与代码+测试两边都"故意"，必须有人裁决）。

- [ ] [WF] 预算按 token 计价、记分按文本计量的单位错配：8192 "identical" 在三个分词器下可买到相差约 10-15% 的英文文本量，协议逐字宣称 across backbones 一致却无任何披露；影响：贴着预算写满的报告，其完备性上限方向性地随底模偏移，读者会归因于模型；文件：config/lane_protocol.yaml:87-105、integrations/sampling_policy.py:118-132、src/eval/decidable_scorer.py:1722 起；建议选项 A=协议与榜单加一行"预算为各自分词器单位"的披露即可，B=改为字符计价的报告上限。判断：**真语义问题**（低severity，披露即可闭合）。

- [ ] [WF] codex（及 Windows 模式 claude-code/opencode）在强制隔离边界下结构性不可跑却无披露：remote_enforced() 依赖的 remote-isolation-proof schema 只有读者没有写者，netns 也不放行 SSH 出站，故该车道永远 withhold/缺席，榜上"没跑"与"跑了很差"不可分辨；影响：声明 17 条车道、榜上只出现 16 条而不说明原因；文件：scripts/run_deep_task.py:2279-2288、production_isolation.py:151、268-283、533；建议选项 A=榜单加"因隔离边界不可跑而排除"的机器可读原因行，B=实现 remote proof 写端把远程车道纳入边界，C=从声明协议中撤掉这些车道。判断：**真语义问题**（披露/取舍属方法论，proof 写端缺失部分是实现欠账）。

## 2. 实为实现 bug（违反已声明语义，转对应闸门修复；每条须配旧代码上会红的回归测试）

- [ ] [WF] 四条车道暗藏硬墙钟：tongyi-dr/deepagents/ldr 1800s、local-deep-researcher 1200s（手工 dispatch 包装不传 timeout_s，runner 模块默认值生效），其余车道无外层墙钟；协议明文 wall_clock_s: null、"由 stall watchdog 终止"；被杀记 status=fail（不可重跑）且 production_comparable=true；影响：慢底模上四条车道被闸成 0 分并记为框架失败，典型冤案；文件：scripts/run_deep_task.py:1959、1975、1983、1692 附近的手工包装 vs :2060-2071 的 _wrap_runner(timeout_s=None)；scripts/runners/{tongyi,deepagents,ldr,local_deep_researcher}_runner.py 的 DEFAULT_TIMEOUT_S；判断：**实为实现 bug → G0**（未声明差异；击杀改判 infra/rerunnable 部分兼 G4/G6）。已在当前代码复核为真。

- [ ] [WF] completeness 严格模式键错了开关：以 evidence.available（日志形好坏）而非 transport 可用性（fetch_observable/损坏日志）决定是否要求 fetch，导致 pof 被正确 withhold 的车道其 completeness 却按空 fetched 集打 0，且与无日志车道混在同一 text_v1 榜里语义不一；文件：src/eval/decidable_scorer.py:1664、1762-1763 vs src/eval/fetch_log.py:439-474；判断：**实为实现 bug → G4**（withhold 不打 0）。

- [ ] [WF][已知a配套] page cache 供给链失修：build_truth_board --cache 可缺省为 {} 静默出榜（无 refuse/警告）；scripts/build_sandbox_cache.py 只从 legacy 报告 glob 收集 URL，收不到正式 run-set 新引用的论坛线程，同样合规的引用因缓存有无而得分不同（仪器造成的车道不平等）；文件：scripts/build_truth_board.py:773、840；scripts/build_sandbox_cache.py:55-62；判断：**实为实现 bug → G4**（配套语义分叉见 §1 第 2 条）。

- [ ] [WF] 车道内混合 pof 语义触发 KeyError 而非 rc=3：axis_keys 取自该车道第一份报告，逐报告索引 axes，同一车道混 transport_v2/text_v1 时未到 rc=3 检查即裸崩；文件：scripts/build_truth_board.py:1194-1210 vs 混合语义门；判断：**实为实现 bug → G6**（0/失败必须带机器可读原因）。

- [ ] [WF] egress 结束标记 ACK 丢失被记成框架失败：`_close_brackets_best_effort` 对 end-mark 未确认 raise → egress_merge_error → err → status='fail'（终态、不可重跑、missing_as_zero 记 0），而 egress_proxy 注释明言这应是 infra_abort（可重跑）；同函数一边降级 fetch_observable（意为"保留可评、withhold pof"）一边置 err 杀跑，两分支自相矛盾；文件：scripts/run_deep_task.py:2938-2963、3122-3124、3143 vs integrations/egress_proxy/app.py:268-278；判断：**实为实现 bug → G4/G6**。

- [ ] [WF] reach 与 transport 对 off-corpus URL 身份认定不一致：reach 对 registry 无法归一的 URL 退回原串键 raw:{u}，transport 走 fetch_log.canonical（去 fragment/尾标点），同一伪造 URL 的拼写变体 reach 记两条、transport 记一条，fabrication == 1-reach 的声明恒等式被破坏；文件：src/eval/decidable_scorer.py:546-552 vs src/eval/fetch_log.py:87-91、481-487；判断：**实为实现 bug → G6**。

- [ ] [WF] decidable_scorer.aggregate() 的 micro 口径与逐报告实现脱节：micro fact 的体积项 tested=supported+contradicted 让错误声明也买体积（逐报告版只许 distinct supported 计），micro_comp 分母仍是 k_star*n（逐报告已改 min(k_star,|pool|)）；当前无生产调用方但属导出口径，一次 import 就上表；文件：src/eval/decidable_scorer.py:2244-2251 vs 1441、1860；判断：**实为实现 bug → G6**。

- [ ] [WF] jury fit_from_bank 跨代拼池：item 键 (task,a,b,order) 不含 report sha，重 stage/换 seed 后旧代报告的判决以文件位置论生死或双份计入 BT，"--fit 是纯重放"仅在同 seed 同 staging 下成立；文件：scripts/run_usefulness_jury.py:712-714、501-507；判断：**实为实现 bug → G6**（jury 整改）。

- [ ] [WF] jury 裁决是"忽略平票的相对多数"而非声明的多数票：votes={tie,tie,A} 判 A 全胜，2/3 评审的平票被 1 票压过，设计文档写 多数票裁决；文件：scripts/run_usefulness_jury.py:725-733 vs USEFULNESS_JURY_DESIGN_2026-07-07.md:47；判断：**实为实现 bug → G6**（jury 整改）。

- [ ] [WF] 任务文件缺失时 jury 拿空问题开庭：load_intent 返回 None 被 `or ""` 吞掉，battle 照跑、判决入 bank 且 error=None，与干净数据不可分辨；文件：scripts/run_usefulness_jury.py:396-412、1029、1081；判断：**实为实现 bug → G6**。

- [ ] [WF] bradley_terry.bootstrap_ci 给缺席重采样的 agent 填 1000 锚点伪观测、断图重采样裸 except 丢弃：稀疏 agent 的 95% CI 被拽向 1000 并上 v1 榜；文件：src/scoring/bradley_terry.py:174-181、scripts/build_real_leaderboard.py:1048-1056；判断：**实为实现 bug → G6**。

- [ ] [WF] presentation panel 是唯一零出处绑定的榜单输入：任意 {agent: float} json 可作 --panel，panel_from_fit 又主动剥掉 protocol/rubric_hash/backbone 戳，跨底模 jury 文件可静默重排名次且 board.json 无记录；文件：scripts/build_truth_board.py:841、1333、1358-1371、scripts/run_usefulness_jury.py:878-894；判断：**实为实现 bug → G0**（出处绑定/披露）。

- [ ] [WF] check_parity 的 backbone_keyed_behaviour 规则 10 种改写只抓 2 种，且 SCANNED 不含两个代理目录（真正的按底模分支都在那里）：历史事故的原样复发（model.startswith 换名）当前打印 parity OK；文件：scripts/check_parity.py:163-168、55-59；判断：**实为实现 bug → G0**（G0 自身工具的覆盖率）。

- [ ] [R5][WF] check_parity 的 citation_count 规则（守 reach 分子的那条）没有复用为反改写而建的 _QTY 量词集，软量词与大数词全漏，search_count 也要求数字（"MULTIPLE queries"逃逸）；文件：scripts/check_parity.py:49-53 vs 64-67、78-81；判断：**实为实现 bug → G0**。

- [ ] [WF] codex 车道的模型身份门探错主机：探针在发射机上解析 CODEX_DS_PROXY（默认 localhost:8100），codex 实际流量在 SSH 远端对同一字符串按远端回环解析；协议 codex deviation 自己写明"必须在该远程端点上做身份探针"，无代码执行；异机部署时会带着干净 attestation 挂错底模；文件：scripts/run_deep_task.py:2445-2451、3033-3039、scripts/runners/codex_runner.py:54、299-308、tests/test_lane_hidden_asymmetry.py:160-177（钉住的正是缺口）；判断：**实为实现 bug → G0**。

- [ ] [WF] qwen fit_to_window 的 len//3 估算对 ASCII 高估约 33%，把实际装得下的长 prompt 请求预算削到 8192 以下直至 256（apply_max_tokens 只降不升救不回来），仅 qwen 有此机制；影响：长上下文综合期的最终成稿在 qwen 榜被削成残稿并记为模型失败；文件：integrations/llm_gateway/app.py:247-252、277-287（当前代码复核：fit 仍先于 apply_max_tokens 且可低于 ceiling）；判断：**实为实现 bug → G0**（估算修正/机制申报；错削预算兼 G6）。

- [ ] [WF] max_tokens floor/ceiling 语义与优先级两门各错一处：gateway 给 glm 无条件 floor=131072（把任何小额请求抬满），而 lane_protocol/sampling_policy 逐字声明"clamp、never raise"；ds_proxy 则把 OPENAI_PROXY_MIN_MAX_TOKENS 放在 apply_max_tokens 之后，运维 env 可压过声明的 ceiling；同一请求两门出来的预算不同；文件：integrations/llm_gateway/app.py:93、262-267 vs integrations/sampling_policy.py:118-132、config/lane_protocol.yaml:105-117；integrations/ds_proxy/app.py:399-400 vs 413-416（当前代码均复核为真）；判断：**实为实现 bug → G0**（floor 本身去留属 §1 跨底模分叉）。

- [ ] [WF] 两个 LLM 门在采样器之外全面政策分歧：ds_proxy 有 8 次瞬态重试/think 剥离(截断 CoT 置空)/json_schema 降级+系统提示注入（仅 deepseek/glm 触发），gateway 全无且超时裸抛；混门跑法下车道在不同传输可靠性与请求改写下被打分；文件：integrations/ds_proxy/app.py:251-265、534-550、91-110、421-436 vs integrations/llm_gateway/app.py:548-596；判断：**实为实现 bug → G0**（统一或全量申报，任选皆须过披露完备性检查）。

- [ ] [WF] 上下文溢出救援仅 qwen 生效：fit_to_window 只开在 qwen 条目，refit 正则只认 vLLM 错误措辞，同样的越窗请求在 deepseek/glm 直接失败；"同 harness 只换模型"被按底模选择性修复破坏；文件：integrations/llm_gateway/app.py:78、307-334、354-400、559-567；判断：**实为实现 bug → G0**（申报或补齐两家措辞）。

- [ ] [WF] manifest 只快照发射器进程的 env 与磁盘哈希，不采集在役 gateway 的活策略（/healthz 的 per-prefix floor/cap/fit/thinking）也不哈希 LLM_GATEWAY_CONFIG 内容：服务端策略漂移/改后未重启的缓存陈旧都能在字节相同的 manifest 下改分；文件：scripts/run_manifest.py:360-406 与 integrations/llm_gateway/app.py:120、157、integrations/sampling_policy.py:33-63；判断：**实为实现 bug → G0**。

- [ ] [R5][HANDOFF] fetch_log 的 unattributed 窗口两处失真：shim 重启后 _ACTIVE 置空，尾段记录 ts > t_end 不计数、withhold 不触发（恰是文档瞄准的场景）；"每 evidence 目录同时只有一跑"的论证是每进程 409，多 worker 各起 shim 却共享默认 logs/fetch 目录，邻跑孤记录会冤枉本跑触发 withhold；文件：src/eval/fetch_log.py:209-214、229-234、251、integrations/search_shim/evidence.py:102、141-143、scripts/run_full_leaderboard.sh worker 段；判断：**实为实现 bug → G4**（HANDOFF 4a 高价值项，未过证伪，修前先复核当前行号）。

- [ ] [R5] 店铺页面 fetch 路径未做拨号改写：搜索路径已用 *_PUBLIC，但 /fetch、backend.extract、/product_lookup 均按原 URL 直连，release compose 里网关容器内 localhost:7770 无人监听，店铺 pof 读 0 而只探 search 的存活门发现不了；文件：integrations/search_shim/app.py:297、827、integrations/search_shim/backend.py:582；判断：**实为实现 bug → G5**（箱上 preflight 必须真跑 fetch 路径；未过证伪，修前复核）。

- [ ] [R5] wiki bloom 静默缺失让 reach 与 transport 分道：WikiBloom.load 对缺失/损坏文件静默返回 None 落入 partial 模式，transport 的 _in_registry 把 in_corpus=None 记伪造、reach 却经 page cache 记可达，两不变式破裂且无任何信号上浮；文件：src/eval/url_registry.py:86-98、src/eval/decidable_scorer.py:1364-1372 vs 461-471；判断：**实为实现 bug → G4/G5**（bloom 缺失=仪器缺失，应 refuse/withhold 而非静默降级；corpus 指纹已含 bloom，剩余是加载期的静默）。

- [ ] [R5] 93/100 任务的 start_url 与 intent_v1_legacy 仍指 re-theme 前旧题：playwright/webarena 类车道会被种到无关目录页，任务文件自相矛盾；当前 deep 榜不受影响（只读 v2 intent），属潜在不平等与数据卫生；文件：src/runner/playwright_runner.py:122、data/tasks 各 json；判断：**实为实现 bug → G1**（答案键/任务一致性；低优先）。

- [ ] [R5][HANDOFF 手检衍生] fact 轴四位数纯数字价格被静默漏检（supported=0, contradicted=0 的 false negative；逗号价与 X/5 误伤已修，此为手检时点出的"值得单看"残留）；影响：高价商品任务的 fact 体积被系统性低估；文件：src/eval/decidable_scorer.py:141 _NUM_RE 与 _standalone_number:426 邻域；判断：**实为实现 bug → G3**（扰动必降/漏检类；先写重现再修）。

## 3. 已过时 / 已证伪（记录在案防止回锅，不需动作）

- [ ] [WF] "gateway 对不带 max_tokens 的请求放行 ~64k 预算、绕过 8192" ：被 3 个独立证伪 agent 全票击杀，当前管线末位 apply_max_tokens 统一钉到 ceiling（omit→8192），preflight 亦有 ceiling+absent 断言；判断：**已证伪**（journal 唯一有 verdict 的 finding；同一 agent 关于"yaml 未声明例外/无 preflight 检查"的措辞也随之过期）。
- [ ] [R5] "min_report_truth 未补零重引幸存者偏差"：已修，现为 min(truths_all)（补零口径）+ 单列 min_report_truth_surviving；scripts/build_truth_board.py:1312-1314。判断：**已过时（已修复）**。
- [ ] [R5] "axes_mean/compliance 用幸存分母且无披露"：已修，现双口径并列 axes_mean_surviving / axes_mean_all_tasks；scripts/build_truth_board.py:1200-1210。判断：**已过时（已修复）**。
- [ ] [R5×2] "rc=7 manifest 门对 model_identity 空转（空列表零违规）"：已修，verify() 现要求至少一条成功的按底模探针且 model_identity 入必需节；scripts/run_manifest.py:499、571-575。判断：**已过时（已修复）**。
- [ ] [R5] "verify() 记录 framework 哈希却从不比对"：已修，现校验 frameworks 节非空及逐项完整；scripts/run_manifest.py:598-614。判断：**已过时（已修复）**。
- [ ] [R5] "concept 引用门对 https/http scheme 敏感"：已修，概念比对现走 _page_identity（registry 归一），http/https 同一身份（本次实测相等）；src/eval/decidable_scorer.py:1604、1622。判断：**已过时（已修复）**。
- [ ] [R5] "3 个任务的带括号概念页不可覆盖"：大体已修，提取器已保留括号 URL（本次实测 markdown/bare 两式均完整），Qi_(standard) 与 Ray_tracing_(graphics) 均 in_corpus=True（bloom 命中），0012 已不含括号概念；判断：**已过时（已修复；G1 oracle 跑通时自然复验）**。
- [ ] [R5] "concept_coverage 只需引 URL+提名概念即得分（generic 标题使主体检查空转）"：已过时，现要求缓存页词面引用支持（_concept_quote_supported），URL/标题空壳不再得分；src/eval/decidable_scorer.py:1795-1801。判断：**已过时（已被更严实现取代）**。
- [ ] [R5] "claude-code 独享方法论提示块（MULTIPLE queries / Cross-reference 三源）"：已过时，当前 claudecode/opencode/codex runner 中已无该文本（grep 无命中）。判断：**已过时（已删除）**。
- [ ] [R5] "kiwix/reddit 搜索结果链接仍用拨号主机（wiki:8080）"：与手检已证伪条同源，四个搜索函数均已用 *_PUBLIC 归一。判断：**已证伪**（注意：页面 fetch 路径是另一条，仍列 §2 转 G5）。
- [ ] [R5] "jury 跳过 stub 不记败=幸存者偏差"：已过时，当前代码走 walkover_record 记满额败绩，方向反转；真正待拍板的是记败 vs 弃权的语义冲突，见 §1。判断：**已过时（被 §1 jury 分叉取代）**。
- [ ] [R5] "逗号千分位价格拆成两条矛盾声明"：已修，_NUM_RE 已含千分位分支且注释点名此案；src/eval/decidable_scorer.py:139-141。判断：**已过时（已修复）**。
- [ ] [R5] "表格 4.5/5 评分按价格判矛盾"：HANDOFF 手检为 MISDESCRIBED（contradicted=0），且现有 /5、out of 前缀护栏；残留的 false negative 已单列 §2 G3 条。判断：**已过时（误描述）**。
- [ ] [R5] "egress 录制代理没接进任何跑法"：已过时，run_deep_task 现注入 DRA_EGRESS_PROXY 括号并在收尾合并证据（其收尾语义 bug 见 §2 egress 条）。判断：**已过时（已接线）**。
- [ ] [R5 手检] "_run_status 平铺 glob 忽略 backbone"：HANDOFF 已标 REAL, fixed（fails loud 或 --backbone），且正式布局现带 integrity binding 校验（backbone/replicate/agent/task 全比对）。判断：**已过时（已修复）**。
- [ ] [WF] "backbone 预算不均既无声明也无检查"（ae57 第 2 条的措辞部分）：声明与 preflight 披露现已存在（yaml:96-117 + check_backbone_sampling），残余的是否等化问题并入 §1 跨底模分叉。判断：**已过时（部分；实质并入 §1）**。

---

统计：真语义问题 12 条；实为实现 bug 25 条（按主闸门：G0×10、G1×1、G3×1、G4×5、G5×1、G6×7）；已过时/已证伪 16 条。合计 53 条。
