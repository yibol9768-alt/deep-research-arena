# GATES_GREEN_REPORT — 七道闸门收拢验证(2026-07-10)

分支 `fix/pof-citation-extractor`。四条 gates 车道已收拢进本分支(见 git log 的
四个 `merge(gates)` 提交)。下表为 G0-G6 逐道验证结论;闸门定义见
`docs/GOAL_GATES_V1.md`。打分口径(公式/权重/门控)未变,只加原因码/可观测字段与
三处"实现与自身声明语义不符"的修复。

## 合并的分支

| 车道 | 分支 | tip SHA | 内容 |
|------|------|---------|------|
| L3 | gates-L3-withhold | 8985c07e | G4:WithholdReason 枚举(18 码)+ 连坐 fetch 修复 + concept 可观测 |
| L5 | gates-L5-silentzero | 10eb4d04 | G6:零分原因码贯通 + check_no_silent_zero.py + 7 处 SPEC_ISSUES 修复 |
| L1 | wf-gates-g1g2g3 | 6bce1737 | G1/G2/G3:oracle_report + 闸门测试 + run_gates + 2 处 G3 打分器修复 |
| L2 | worktree-wf_661548f5-82e-2 | c1bc3437 | G0:披露面 + check_disclosure + 暗墙钟拆除 + 前端徽章 |

## 闸门结论(G0-G6)

| 闸门 | 名称 | 结论 | 证据 / 命令 |
|------|------|------|-------------|
| G0 | 协议对等 + 差异披露 | 绿 | `python3 scripts/check_parity.py` (rc=0) && `python3 scripts/check_disclosure.py` (rc=0);经 `run_gates.py` 复核 PASS |
| G1 | oracle 顶格(100 题) | 绿 | `python3 scripts/run_gates.py --gates G1` PASS(331s,test_gate_oracle 全 100 题) |
| G2 | 空壳归零(100 题) | 绿 | `python3 scripts/run_gates.py --gates G2` PASS(136s,test_gate_oracle 空壳分支) |
| G3 | 扰动必降 | 绿 | `python3 scripts/run_gates.py --gates G3` PASS(340s,test_gate_perturbation 全 100 题) |
| G4 | withhold 不打 0 | 绿 | `pytest tests/test_gate_withhold.py`(36 passed);经 `run_gates.py` PASS |
| G5 | 箱上 preflight 真跑 | SKIP | 箱上项(my5090 沙箱),工作站不可跑;证据 `data/results/gates/G5_box_preflight_20260709.txt` |
| G6 | 无静默零 | 绿(管线) | `pytest tests/test_gate_silent_zero.py`(25 passed);经 `run_gates.py` PASS。**管线绿,端到端终判待箱上冒烟**(需活底模端点,#39 全量首跑) |

## 全量验证

- `python3 -m pytest tests/ -q` → **1183 passed, 8 skipped, 15 deselected, 0 failed**(5:27;gates-marked 的 oracle/perturbation 扫描默认 deselect,见 tests/conftest.py)
- `python3 scripts/run_gates.py`(七道一键)→ rc=0:G0 PASS(15s)/ G1 PASS(331s)/ G2 PASS(136s)/ G3 PASS(340s)/ G4 PASS / G5 SKIP(箱上证据)/ G6 PASS
- `python3 scripts/check_parity.py && python3 scripts/check_disclosure.py` → 均 rc=0
- `cd frontend && npm run typecheck && npm run build` → typecheck 无错,build 成功(全页面静态生成;未部署、未改 web/dist)

## 跨车道调和

- `src/eval/decidable_scorer.py`:三方改动(L3 枚举/withhold、L5 零分 reason、L1 评分窗口)落在
  不同函数,git 三路自动合并;唯一三方重叠区 `score_completeness` 经逐行核对——L3 的 concept
  盲判计数、L5 的 comp_det+no_vital_covered、L1 的 exact-name 掩蔽+tail 三者共存(见文件
  2010-2120 行)。`_concept_quote_supported` 采 L3 的 `(supported, cache_present)` 元组版,
  `_forum_coverage_supported` 的调用点取 `[0]` 适配。
- `scripts/check_no_silent_zero.py`:删除 L5 的 WithholdReason 复刻集,改为从合并后 L3 枚举
  `from src.eval.decidable_scorer import WithholdReason` 直接导入(单一真相源),并加 repo-root
  入 sys.path 以保脚本独立运行。
- `data/changelog.json`:三条 v23 收拢成一条 `v23-2026-07-10`(七道闸门上线 / 打分器三处修复 /
  withhold 原因码 / deviations 披露),无重复版本号。
- `docs/SPEC_ISSUES.md`:以 6d70e811 canonical 为底,追加 L1 §4(G1-G3 执行注记)、L2 附录
  (G0 处置记录)、L3 增量三份注记,统计并入后合计 55 条。
- `scripts/run_gates.py`:新挂 G0(check_parity+check_disclosure 脚本闸门)、G4(test_gate_withhold)、
  G6(test_gate_silent_zero);G5 输出 SKIP 并指向箱上证据文件。真正一键跑七道。
- `data/golden/concept_page_cache.json.gz`:与主分支 615d8b49 同内容,保留主分支版本。
- 合并伤修复 1 处:`tests/test_disclosure_completeness.py` 的 red-on-old 证明原用
  `git show HEAD:config/lane_protocol.yaml` 作"闸门前协议"——只在披露改动未提交时成立,
  车道一提交(以及合并后)HEAD 即是已披露文件,证明自溶。已钉到闸门前基线快照
  `084de62f`(`PRE_GATE_COMMIT`),测试意图不变(五个 family 在旧文件上全部触发,101 违规)。

## 备注

- `docs/SPEC_DECISIONS.md`:维护者对 SPEC_ISSUES §1 全部 12 条真语义问题的裁决
  (语义层新 SSOT,2026-07-10),随本次合并一并入库,内容未动。**裁决的实施不在本次
  合并范围**——本次只收拢四条闸门车道并验证;逐条落地(打分器/门/前端)由后续任务
  按该文件执行(每条须配 changelog + 回归测试)。
