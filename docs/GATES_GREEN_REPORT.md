# GATES_GREEN_REPORT — 语义裁决落地 + 七道闸门终版(2026-07-10)

分支 `fix/pof-citation-extractor`。在四条 gates 车道(G0-G6)已上线的基线 `edf336cc`
之上,本轮把 docs/SPEC_DECISIONS.md 的 12 条语义裁决拆成三条实施车道收拢进本分支
(三个 `merge(gates)` 提交 + 一个 #8 权威修订提交)。闸门定义见 docs/GOAL_GATES_V1.md,
裁决见 docs/SPEC_DECISIONS.md。**打分公式/权重/头条门未变**;本轮改的是:snippet-only
豁免、离题事实出账、jury walkover 归属、诊断 withhold、census 文案、三源诚实化、
provenance/guessed/fact_precision/excluded 披露列,以及一次三镜头复审的披露诚实化修复。

## 合并的三条实施车道

| 镜头 | 分支 | tip SHA | 内容 |
|------|------|---------|------|
| D1 打分器 | gates-D1-scorer | 46fd7cd3 | 裁决 #1 / #2(打分器侧)/ #3 / #10 + 短主题词边界修复 + G1 诊断 99/100 gate + 0038 stub xfail |
| D2 榜单/文档 | gates-D2-board | 17436381 | 裁决 #2(board fail-closed)/ #4 / #5 / #6 / #8 / #9 / #11 / #12 + cache_policy 特性探测透传 + 前端披露列 |
| F1 复审修复 | gates-F1-fixes | e0f825ac | langchain-odr/deerflow/tongyi/camel/ldr 披露诚实化 + run_gates rc=5→FAIL + 门前置 + check_disclosure 扩到 26 对账器 |
| 合并者 #8 修订 | (提交)05a796c3 | — | 主树 SPEC_DECISIONS #8 权威修订(维持 provenance_v2 头条门,不回退 reach) |

## 12 条裁决落地对照表

| # | 裁决 | 落地车道 | 状态 |
|---|------|---------|------|
| 1 | snippet-only 豁免 fetch 门槛 | D1 打分器(沿用 L3 fallback 扩到 fetch_mode:none) | 已落地 |
| 2 | 无 cache fail-closed(rc=11)+ --diagnostic 诊断 withhold | D2 board + D1 打分器(cache_policy) | 已落地,透传经集成断言钉死 |
| 3 | 范围外正确事实移出 tested | D1 打分器 | 已落地 |
| 4 | 同句/同行引用绑定维持 + DATASHEET 披露文风代价 | D2 DATASHEET | 已落地(披露) |
| 5 | 承认普查语义,文案改"覆盖全部 vital 池" | D2 docstring/README/DATASHEET | 已落地(文案) |
| 6 | 论坛=provenance 维度非计分源;真论坛 nugget 列 v2.1 | D2 文档 | 短期 B 已落地;A(v2.1 数据集)遗留 |
| 7 | 统一可见输出预算(撤 131072 floor / qwen CoT 分离) | — | **不在本轮**(llm 门 + 箱上工作);仅 #11 token 单位披露已落地 |
| 8 | 维持 provenance_v2 头条门 + reach/prov/guessed 三列 | D2 board(grounding_provenance 三列)+ D1(withhold 感知回落) | 已落地;#17 人工校准后复审门选择(遗留) |
| 9 | fact_precision 详情列(头条分不动) | D2 board + 前端 | 已落地(UI 就位,数据待管道) |
| 10 | jury walkover 按故障归属拆分 | D1 run_usefulness_jury + 设计文档 + 测试 | 已落地 |
| 11 | 预算单位=各底模分词器 token 的披露 | D2 lane_protocol + README | 已落地(披露) |
| 12 | codex excluded_reason + 实际可跑车道数 | D2 board excluded_lanes + README + 前端徽章 | 已落地;remote proof 写端(遗留可选) |
| 追加 | 短主题概念死锁(实现 bug) | D1 词边界精确匹配 | 已落地(11 槽解锁) |
| 追加 | 字面 completeness=1.0 不可达 | D1(可达上限相等 gate 绿 + 诊断 99/100 gate 绿 + 字面 1.0 xfail) | 部分:0038 stub 残差以 xfail 挂起,待键构建期排除 |
| 追加 | 论坛槽"盲判"定义 | D1 随 #2 诊断口径落地 | 已落地 |

## 闸门结论(G0-G6)

一键 `python3 scripts/run_gates.py`(完整 100 题,非 --quick)结论如下:

| 闸门 | 名称 | 结论 | 证据 / 命令 |
|------|------|------|-------------|
| G0 | 协议对等 + 差异披露 | 绿 | run_gates G0 PASS(13s);另 `check_parity.py`(21 规则/0 违规)+ `check_disclosure.py`(17 车道/26 对账器/0 未申报差异)均 rc=0 |
| G1 | oracle 顶格(100 题) | 绿 | run_gates G1 PASS(173s)。可达上限相等断言绿;**新增诊断断言:诊断 cache_policy 下 oracle 字面 completeness=1.0 命中 99/100,唯一缺口是标题级 stub 概念页(0038),且缺口为精确残差**;GOAL_GATES_V1 字面 1.0-for-every-task 以 xfail 挂起指向 0038 |
| G2 | 空壳归零(100 题) | 绿 | run_gates G2 PASS(174s) |
| G3 | 扰动必降 | 绿 | run_gates G3 PASS(306s) |
| G4 | withhold 不打 0 | 绿 | run_gates G4 PASS;`pytest tests/test_gate_withhold.py` 全绿 |
| G5 | 箱上 preflight 真跑 | SKIP | 箱上项(my5090 沙箱),工作站不可跑;终判待箱上冒烟 |
| G6 | 无静默零 | 绿(管线) | run_gates G6 PASS;`pytest tests/test_gate_silent_zero.py` 全绿。**管线绿,端到端终判待箱上活底模端点(#39 全量首跑)** |

## 三镜头复审(F1)发现与处置摘要

F1 车道对 D1/D2 之外的适配层与披露做了一轮复审,处置=诚实化披露(不改打分语义),
每条配旧代码上会红的回归测试:

- **langchain-odr**:删除失实的"适配器已退休"声明,补齐 5 条真实单车道钳制申报
  (clamp_researcher_tool_calls / clamp_supervisor_research / clamp_search / noop_summarize /
  bypass_write_research_brief)。回归 tests/test_ldr_runner.py、check_disclosure。
- **deerflow**:协议由 direct_requests/off-shim 改正为 shim_extract(经记录 shim 的 POST /extract),
  补 2000 字符/页上限与 conf.yaml max_retries=3;fetch_observable 暂留 false 待箱上冒烟。
- **tongyi**:申报 ReAct 重试;call_llm 耗尽即抛出(原返回 'Error: ...' 哨兵可能进入被评分文本),
  改为与其他车道同构的 infra 失败。回归 tests/test_tongyi_runner.py。
- **camel**:sanitizer 只剥配平的 <think>/<tool_call>/<tool_response> 标签对;原悬挂开标签 `.*` 剥除
  会把正文删到 EOF。正文/引用逐字保留。回归 tests/test_camel_sanitize.py。
- **ldr**:仅当 masking 开启时才 unmask;parity 扩到沙箱掩码域。回归 tests/test_nav_citation_parity.py。
- **门装配**:run_gates rc=5(挂载的 gate 文件 0 测试)由 SKIP 改判 FAIL;goal-gate 前置到昂贵
  leaderboard 构建之前(run_full_leaderboard.sh + preflight);check_disclosure 扫描面扩到
  run_deep_task.py,共 26 对账器。回归 tests/test_run_gates_runner.py、test_disclosure_completeness.py。

另:F1 在 docs/SPEC_ISSUES.md §"F1 备查条目"记录 4 条语义/口径观察(aggregate() 跨版本
micro_comp 虚高、check_no_silent_zero 整轴豁免过宽、oracle 镜像谓词双盲、changelog v14 疑似重复),
按冻结令**只记不修**,等用户拍板。

## 合并调和点与解法

- **data/changelog.json**:D1 与 D2 各写了 `v24-2026-07-10`,收拢成唯一一条 v24(15 节:
  D1×6 + D2×8 + F1×1),标题/摘要/tags 取并集;F1 未写 changelog,其 High 修复补为第 15 节。无重复版本号。
- **config/lane_protocol.yaml**:D2(#11 头注、codex runnable:false)与 F1(langchain-odr/tongyi/
  deerflow/camel deviations)落在不同区块,git 自动三路合并,两侧全保留。
- **scripts/build_truth_board.py**:三处 D1×D2 重叠。`_declared_lanes`/`_lane_fetch_modes`(D1 重构)
  与 `declared_lanes` 赋值 git 自动合并;`evaluate()` 调用点手工取**两侧并集**——D1 的
  `lane_fetch_mode=`(裁决 #1)与 D2 的 `**_scorer_kw`(裁决 #2 特性探测透传)共存。
- **src/eval/decidable_scorer.py**:score_completeness 签名冲突——取 D1 的参数版
  (`lane_fetch_mode` / `cache_policy`)+ D2 的 census docstring 首行。
- **scripts/run_gates.py**:D1 的 G1 诊断节点 + F1 的 rc=5→FAIL 落在不同区块,自动合并,均保留。
- **docs/SPEC_DECISIONS.md**:D2 对 #8 的修订与主树工作区改动**逐字相同**,主树权威版先行提交,
  D2 侧自动无冲突并入。
- **透传激活验证**:新增 tests/test_truth_board_cache_policy_threading.py——in-process 驱动
  build_truth_board.main() 并 spy `evaluate`,断言 `--diagnostic` 时打分器真正收到
  cache_policy='diagnostic'(strict 为差分对照),completeness detail 出现 withheld_slots。
  这是"D2 特性探测透传合并后真正激活"的合并期证据:若未来有人删掉打分器的 cache_policy 参数
  使探测失活,该测试转红。
- **docs/SPEC_ISSUES.md**:§1 全部 12 条真语义问题打勾并逐条回链 docs/SPEC_DECISIONS.md 对应裁决;
  F1 的 4 条备查随车道并入。

## 全量验证(顺序跑)

- `python3 -m pytest tests/ -q` → **1245 passed, 8 skipped, 16 deselected, 0 failed**(5:50;
  含新增集成断言 tests/test_truth_board_cache_policy_threading.py 的 3 测试;gates-marked 的
  oracle/perturbation 扫描默认 deselect)。
- `python3 scripts/run_gates.py`(七道一键,完整非 --quick)→ G0 PASS(13s)/ G1 PASS(173s)/
  G2 PASS(174s)/ G3 PASS(306s)/ G4 PASS(4s)/ G5 SKIP(箱上)/ G6 PASS(7s),rc=0。
- `python3 scripts/check_parity.py && python3 scripts/check_disclosure.py` → 均 rc=0
  (parity:51 文件/21 规则/0 违规;disclosure:17 车道/26 对账器/0 未申报差异)。
- `cd frontend && npm run typecheck && npm run build` → typecheck 无错,build 成功
  (131 页全静态生成);**未部署、未改 web/dist**。

## 遗留清单

1. **裁决 #7(跨底模可见输出预算等化)不在本轮**:撤 gateway 131072 floor、qwen CoT 与可见预算
   分离属 llm 门 + lane_protocol + 前端的改造与箱上验证,本轮仅落地 #11 的 token 单位披露。
2. **裁决 #6 的 A 支(真实论坛 vital nugget)**:thread_score/comment_count 可判定谓词的金标构建
   列为数据集 v2.1 任务,不阻塞 #39;当前论坛为 provenance 维度、非计分源。
3. **deerflow fetch_observable 翻转待箱上冒烟**:适配层已改走 shim_extract,但 observable 翻转
   是打分变更,须先在箱上证明本车道端到端记录 fetch 行 > 0(fail-closed 排序规则),留待下次跑。
4. **0038 stub 页字面 1.0 残差**:dr_cross_deep_0038("Input lag")概念页全文短于 400 字符接地窗,
   任何报告都无法引文接地;诊断 withhold 只覆盖缺页不覆盖已缓存的太短页。GOAL_GATES_V1 的字面
   1.0-for-every-task 以 xfail 挂起(test_g1_oracle_completeness_literal_one),须在键构建期
   (build_answer_keys)排除此类 stub 页后转正。
5. **前端数据管道集成**:provenance_pct / guessed_pct / fact_supported / fact_tested / excluded 的
   类型与渲染已就位且类型安全,但填充真实数据要等 build_truth_board 产出经数据管道注入站点消费的
   JSON(#39 全量首跑后)。
6. **G5/G6 终判待箱**:G5(箱上 preflight 真跑 fetch 路径)为 my5090 沙箱项,工作站不可跑;
   G6 管线绿,端到端终判需活底模端点(#39 全量首跑)。
