# Deep Research Arena — HANDOFF 给下一个 Agent

**写于**: 2026-04-20
**上一轮做到哪**: Phase 10b 完成 9/14 实验 + paper scaffold(中文 `latex/findings.tex` 可编译,7 页 PDF)
**当前项目根**: `/Users/liuyibo/Desktop/lyb/deep_reserch/`
**远程镜像**: `ssh westd` → `/opt/deep_reserch/`(WSL Ubuntu,非 git repo)

> 如果你是完全新来的,先读这个文件,然后读 `PLAN.md`、`latex/findings.tex`,
> 再看 `~/.claude/plans/iterative-doodling-parrot.md`。其他 `.md` 文件都是
> 历史快照,真要懂当前状态只看这三份就够了。

---

## 0. 一分钟上手

```bash
cd /Users/liuyibo/Desktop/lyb/deep_reserch
git log --oneline -5          # 最近 5 个 commit

# 编译 paper
cd latex && make pdf          # 产出 latex/findings.pdf(7 页)

# 跑分析(本地,零成本)
python scripts/length_ablation.py      # → data/results/LENGTH_ABLATION.md
python scripts/error_taxonomy.py       # → data/results/ERROR_TAXONOMY.md
python scripts/irt_calibration.py      # → data/results/IRT_CALIBRATION.md

# 连远程(SSH 偶尔被 Clash 劫持,重试几次就通)
ssh westd "echo ok"

# 远程 sandbox
wsl -d Ubuntu -- 'docker ps'          # magento:7770 / postmill:9999 / kiwix:8090
```

`.env` 里有 API key(不要 commit):
- `ANTHROPIC_API_KEY`: 中转 API(`http://35.220.164.252:3888`)支持 glm-5/qwen3.5-plus
- 直连智谱: `https://open.bigmodel.cn/api/anthropic`,支持 glm-5.1/4.6/4.5
- OpenAI 代理: `http://35.164.11.19:3887/v1`(第三方,有 `gpt-5-chat-latest` 和 `gpt-5.4`)

---

## 1. 这个项目是什么

一套 **可复现的深度研究 Agent 基准**,对标 DeepResearch Bench、DRACO、
BrowseComp-Plus。核心差异:在沙盒环境(Magento 电商 + Postmill 论坛 + 49 GB
英文 Wikipedia via Kiwix)内跑 14 个 Agent,做 7 支柱打分 + Bradley-Terry
Elo + IRT 交叉验证。

**已挂上论文级的 4 个发现**(全部本地数据可复现):
- F1: LLM Judge 无长度偏好(Spearman ρ=-0.30,反向)
- F2: URL 幻觉是架构问题(集中在 4 个 agent 各 100%,其他 9 个 0%)
- F3: IRT 与 BT-Elo 排序 ρ=1.00,排名自洽
- F4: 同 shim 下 agent 架构决定源多样性(gpt5chat 平均引 2.5 个 Wiki,
  gpt-researcher 引 0 个)

4 个发现已写进 `latex/findings.tex`,表格从 `data/results/*.json` 自动生成。

---

## 2. 状态一览(2026-04-20)

### 任务进度(14 计划,9 完成)

| # | 任务 | 状态 | 产出 |
|---|---|---|---|
| 52 | 49 GB Wiki + scholarly smoke | ✅ | `integrations/search_shim/backend.py` 加 `_search_kiwix`,shim via uvicorn |
| 53 | GPT-5-chat-latest 接入 agent 池 | ✅ | `scripts/run_gpt5.py`,8 runs |
| 54 | Per-agent token budget | ✅ | `src/budget/token_guard.py` |
| 55 | WebArena 187 tasks 接入 | ✅ | `scripts/adapt_webarena_tasks.py` + `src/verifiers/factoid_verifier.py` |
| 56 | Bradley-Terry + bootstrap CI | ✅ | `src/scoring/bradley_terry.py` |
| 58 | Length-controlled ablation | ✅ | `scripts/length_ablation.py` + LENGTH_ABLATION.md |
| 59 | Error taxonomy | ✅ | `scripts/error_taxonomy.py` + ERROR_TAXONOMY.md |
| 60 | Adversarial corpus poisoning | ✅ | `scripts/generate_adversarial_tasks.py` + 5 tasks + `AdversarialRefusalVerifier` |
| 64 | IRT 2-PL 校准 | ✅ | `scripts/irt_calibration.py` + IRT_CALIBRATION.md |
| 57 | Pairwise battle 12 → 50+ | ⏳ | 需要 #65 先完成(全 agent 集合) |
| 61 | Browser agent(magentic-ui) | ⏳ | 未开始,半天+ 工作量 |
| 62 | Multi-LLM compositional | ⏳ | 未开始 |
| 63 | Cross-benchmark(DR Bench/DRACO)| ⏳ | 未开始 |
| 65 | **DS judge + GLM 全 matrix 重跑** | ⏳ | **最大单次数据解锁**,覆盖 gpt5chat × consumer + 全 14 agent × scholarly |

### Arena 当前(13 agent × 4 consumer task = 52 runs + gpt5chat 另 8 runs)

| Rank | Agent | BT Elo | 备注 |
|---:|---|---:|---|
| 1 | react-qwen35plus | 1174 | GLM-4.5 + ReAct,上限 |
| 2 | gpt-researcher | 1158 | 官方 Tavily pipeline,citation 高 |
| 3 | react-glm5 | 1137 | GLM-5.1 + ReAct |
| 4 | deerflow-glm46-shim | 1018 | raw HTML 直进 shim |
| 5 | camel-ai | 983 | GLM-4.5 |
| 6–8 | deerflow-glm46-new/legacy, camel-ai-ds | 854–939 | |
| 9–13 | smolagents, smolagents-ds, odr-ds, deerflow-ds, gpt-researcher-ds | < 1000 | 含 4 个 URL 幻觉 agent |

`gpt5chat`(新接入)在 consumer task 上 composite avg 0.47,citation **0.97 全榜第一**。

### 沙盒服务(westd Docker)

| 服务 | 端口 | 状态 |
|---|---|---|
| Magento(shopping) | 7770 | ✅ up 2d+ |
| Postmill(reddit) | 9999 | ✅ up 2d+ |
| Kiwix(Wikipedia)| 8090 | ✅ 挂了两本 ZIM:3 GB Simple + 49 GB nopic 全英文 |
| search_shim | 8081 | ✅ uvicorn + .venv-camel,已加 kiwix 索引 |
| GitLab / shopping_admin | 8023/7780 | ❌ 容器丢了没重建 |

---

## 3. 下次 session 开工路径(按 ROI 排)

### 选项 A:#65 全 matrix 重跑(最高回报,~$7,2 h)

跑完后 IRT / length ablation / error taxonomy 都能从 n=52 扩到 ~280,F3/F4
的 "directional only" caveat 可以撤掉。

步骤:
1. 修 `scripts/rescore_all_with_deepseek.py`:当前 `TASKS` 列表硬编码,
   `RESCORE_ONLY_TASKS` 环境变量不生效。加环境变量处理(第 ~40 行附近)。
2. 在 westd 上让 13 个已有 agent 跑 scholarly 4-subset(0088/0095/0100/0105)。
   各 agent runner 已经就位(`.venv-gptr/bin/python3 scripts/run_gpt_researcher.py`
   之类),shim 已经加了 kiwix 索引,无需改代码。agent 跑 ≈ $5。
3. 再跑 `rescore_all_with_deepseek.py` 给所有新 answer.md 打分(DeepSeek judge,
   跨 14 agent × 4 task = 56 judge call,≈ $2)。
4. 重跑三个本地分析脚本:`length_ablation.py`、`error_taxonomy.py`、
   `irt_calibration.py`。它们都是扫描 `data/results/final_*.json` 自动更新。
5. 跑 `python latex/generate_tables.py && make -C latex pdf`,PDF 自动用新数据。

**退出条件**:
- `jq '.composite_elo_new | length' data/results/arena_elo_ED.json` = 14
- `ls data/results/final_*_dr_cross_v3_0088.json | wc -l` ≥ 10
- `irt_calibration.py` 输出 `n_tasks = 8`,且新 task 的 discrimination `a_j` 不全部顶到 clip 上限(若顶到,说明 4 道 scholarly 又都太相似,要再扩)

### 选项 B:#62 Multi-LLM compositional(便宜新意,~$0.5,1 h)

写 `scripts/run_compositional.py`,一个 orchestrator:
- GPT-5 做 task 分解 + 规划
- GLM-4.5 做 tool 调用 + 摘要
- DeepSeek 做最终 report 撰写

为什么做:当前 14 个 agent 都是 "单 LLM + tool-calling" 同一范式,审稿人
会问 "多 LLM 组合能不能做得更好"。跑完能把 composite 上限往上顶一段,
paper 里加一个"为什么 frontier 不止一条"的结论。

### 选项 C:其他三个都不紧迫

- #57 Pairwise battle 扩到 50+/pair:当前 12 场 CI 已经 ±80,扩到 50 降到 ±30,
  但排名不会翻,ROI 低。
- #63 Cross-benchmark(DR Bench / DRACO):需要外部 test set 访问权限,
  能给 external validity,但不是必要路径。
- #61 Browser agent(magentic-ui):半天+ 构建,换不同范式,但与 paper
  核心论点正交,先放。

---

## 4. 关键代码地图(新旧一起)

### 本次 session 新增(9 个 commit 在 `5b140b9..e1684ec` 之间)

```
src/
├── budget/
│   ├── __init__.py
│   └── token_guard.py             # 每 run 200k input / 20k output cap,
│                                    通用 guard 供所有 runner 使用
├── scoring/
│   └── bradley_terry.py           # MLE + bootstrap CI,替代旧 arena.py 的
│                                    sequential Elo(arena.py 保留作 baseline)
├── verifiers/
│   ├── factoid_verifier.py        # WebArena string_match 打分器
│   └── adversarial_verifier.py    # 拒答 / 幻觉 / 含糊 三档评分

scripts/
├── run_gpt5.py                    # GPT-5-chat-latest tool-calling runner
├── adapt_webarena_tasks.py        # 187 WebArena 任务转我们的 schema
├── generate_adversarial_tasks.py  # 5 道虚构实体任务
├── length_ablation.py             # F1 的脚本
├── error_taxonomy.py              # F2 的脚本
└── irt_calibration.py             # F3 的脚本(含符号校正)

data/
├── tasks/
│   ├── deep_research/adversarial/ # 5 道 adv task
│   └── webarena_factoid/          # 187 道 WebArena task
└── results/                       # *.json 被 .gitignore 默认排除,
                                     但白名单保护了 length_ablation.json /
                                     error_taxonomy.json / irt_calibration.json /
                                     arena_elo_ED.json

latex/
├── findings.tex                   # 4 个发现的论文 section(中文,ctex+xelatex)
├── refs.bib                       # 5 个 bib entries(英文,标准格式)
├── generate_tables.py             # 从 data/results/*.json 重生成 tables/*.tex
├── Makefile                       # make pdf / make clean / make all
└── tables/                        # .tex 表格,自动生成(gitignore 排除)
```

### 上一轮留下的(Phase 7-9)

- `src/agents/glm_react_agent.py`:自研 ReAct agent + 3-tier fallback。
  **注意**:`:569` 用 Anthropic SDK + DeepSeek `/anthropic` 兼容端,DS 不支持
  完整 `tool_use` block shape → react-ds 出 0 byte。修法:加 OpenAI-compat 分支
  (这是原 PLAN Phase 10b B1 任务,本次未做)。
- `src/verifiers/`:老的 `fact_kg_verifier.py`、`checklist_verifier.py`、
  `llm_judge_verifier.py`、`citation_verifier.py`、`markdown_report_verifier.py`
- `src/scoring/composite_v3.py`:7 pillar 加权 scorer。v3.2 权重见文件顶部注释。
- `scripts/rescore_all_with_deepseek.py`:批量重跑 judge 评分。**该脚本的
  `TASKS` 列表硬编码,`RESCORE_ONLY_TASKS` 环境变量不生效** —— 选项 A 的
  第一步就是修这个。
- `integrations/search_shim/backend.py`(westd 上):**本次改过**,加了
  `_search_kiwix`,shim 原本只返回 magento+reddit,现在混合 magento+reddit+wiki。
  Mac 本地这份文件没同步过来(backend.py 在 `third_party/deerflow/*` 之外,
  `.gitignore` 把 `third_party/` 全部排除了),**只在 westd `/opt/deep_reserch/
  integrations/search_shim/backend.py` 上有新版**,需要从远程拉下来 commit。

---

## 5. 必看的坑(踩过的)

### SSH 到 westd 经常断(Clash TUN fake-IP 劫持)

域名 `8ll05950fh36.vicp.fun` 会被 Clash 劫持成 `198.18.0.9`。解法:
- `~/.ssh/config` 里不写 `ProxyCommand`(保留直连)
- 用 `for i in 1 2 3; do ssh westd "…" && break; sleep 5; done` 重试模式
- 传递大量 bash 逻辑时,写 `/tmp/X.sh` → `scp` 到 `C:/tools/` → WSL `tr -d '\r' < /mnt/c/tools/X.sh > /tmp/X.sh && bash /tmp/X.sh`

### GPT-5.4 在 tool-loop 里偷烧 reasoning tokens

单 prompt 测试时 `reasoning_tokens=0`(像 pure chat 模型),但**多轮 tool-call
对话下**会突然开启 reasoning,每次无形回复烧 ~750 output tokens,直到 budget
耗尽。agent benchmark 不能用 gpt-5.4,**必须用 `gpt-5-chat-latest`**。
这个结论在 `scripts/run_gpt5.py` 的 docstring 里也写了一份。

### Shim 是 FastAPI 不是脚本,不能 `python -m`

正确启动(在 westd):
```bash
cd /opt/deep_reserch
setsid nohup .venv-camel/bin/uvicorn integrations.search_shim.app:app \
  --host 0.0.0.0 --port 8081 \
  > /tmp/shim.log 2>&1 < /dev/null &
disown
```

`python -m integrations.search_shim.app` 只加载模块不起服务,会立刻退出。
shim 挂了的症状:任意 POST `/search` 返回 connection refused。

### gpt-5-chat-latest 把 tool 参数当 content 返回

gpt-5-chat-latest 偶尔会把 `finish(markdown_report=…)` 的参数 JSON 打在
`content` 字段里而不是 `tool_calls` 里。`scripts/run_gpt5.py` 的
`_unwrap_markdown_json` 用正则提取 `{"markdown_report":"…"}` 的内容。
保留这段代码,别以为是 bug 删掉。

### Oracle v2 category granularity bug(待修)

`data/golden/*.filtered.json` 有个 bug:intent-filter 选出"headphones"时
会泄到父类 `cell-phones-accessories`,把蓝牙耳机、VR 眼镜都塞进 oracle。
导致 fact_kg pillar 在 task 0001 上全员 0 分。现在的 rescore 已经回退到
pre-filter 版 golden。修法(PLAN Phase 10b B5)是在 filter 加一层产品名称
关键词。

### Cost 警戒

- GLM Coding Plan 是月费包,跑 13 agent × N tasks ≈ $0
- DeepSeek judge:$0.02–0.05 / judge call,14 × 4 = ~$1;扩到 14 × 24 = ~$7
- GPT-5-chat-latest agent:4 task ≈ $0.15
- OpenAI 代理走 `http://35.164.11.19:3887/v1`(第三方聚合商,日志可能被看)
  —— **不要往里发敏感信息**。Key 若泄露立即去面板 rotate。

---

## 6. 构建 paper PDF(完整)

```bash
cd latex
python3 generate_tables.py      # 从 data/results/*.json 重生 tables/*.tex
make pdf                         # xelatex + bibtex + xelatex × 2
# → latex/findings.pdf, 7 页
make clean                       # 清 build/
make distclean                   # 清 build/ + findings.pdf + tables/*.tex
```

要求:TeX Live 2023+ with `ctex`、`xeCJK`、`natbib`、`booktabs`、`enumitem`、
`siunitx`、`fontspec`。Mac 装了 MacTeX 就够。中文字体 fallback 写的 `Songti SC`
+ `Heiti SC`(macOS 自带),其他系统要改 `\setCJKmainfont`。

---

## 7. 值得读的 commit

```
e1684ec latex: fix Chinese typography / compile warnings     ← 排版定版
9bfa102 latex: 把 findings 从英文改成中文(ctex + xelatex)   ← 中文翻译
5b140b9 Phase 10b: 9 items landed + paper scaffold           ← 本次大提交(218 files)
5141d0c Phase 10b P0: +25 diversity tasks
2108b64 Phase 10a: Oracle v2 plumbing (partial)
c2639ca Phase 10a quick wins: kiwix full-en, smolagents sentinel
16e217c Phase 7-9: shim + multi-framework Elo arena + dual-judge
f46f80c HANDOFF.md: full project handoff doc for next agent  ← 上一任 HANDOFF
```

---

## 8. 文件索引(读完这份再看其他)

按阅读优先级:

1. **本文件**(`HANDOFF.md`)— 全景
2. **`PLAN.md`** — 历史 Phase 1-10 详细日志
3. **`latex/findings.tex`** — 4 个 paper 发现
4. **`~/.claude/plans/iterative-doodling-parrot.md`** — 上次 session 的 plan file,含下一次的推荐执行顺序和验证标准

次级(必要时再读):

5. `METHODOLOGY_AUDIT_2026-04-19.md` — 论文级硬伤清单(3 条 P0)
6. `PAPER_POSITIONING.md` — 在已有 benchmark 中的定位
7. `PAPER_FINDINGS.md` — Phase 9 阶段的 5 个 finding(现已被 `latex/findings.tex` 的 4 个发现取代/扩展)
8. `RESULTS_SUMMARY_v3.md` — Phase 6 完整分数表
9. `FRAMEWORK_INVENTORY.md` — 11 个可接入 / 已接入框架清单
10. `CORPUS_DOWNLOAD_STATUS.md` — 3 个 corpus 下载状态

历史(只在 debug 时看):
- `BYTEDANCE_DEEP_RESEARCH_SURVEY.md`、`DEEP_RESEARCH_TASK_SPEC.md`、
  `ELO_ARENA_PLAN_2026-04-17.md`、`FRAMEWORK_INSTALL_STATUS.md`、
  `ROADMAP.md`、`SCORING_FRAMEWORK.md`、`SCORING_REVIEW_2026-04-17.md`

---

## 9. 联系信息

- 远程: `ssh westd`,WSL Ubuntu,`/opt/deep_reserch/`
- API endpoints:
  - GLM 中转: `http://35.220.164.252:3888/v1/`(无限流,支持 glm-5/qwen3.5-plus/MiniMax)
  - GLM 直连: `https://open.bigmodel.cn/api/paas/v4/`(有限流,支持 glm-5.1/4.6/4.5)
  - OpenAI 代理: `http://35.164.11.19:3887/v1`(第三方,支持 gpt-5-chat-latest,
    **不要放敏感数据**)
- Feishu wiki(DR Arena 工作记录,中文):
  `https://rcn52ut42d3j.feishu.cn/wiki/CRYGw6kV0iSjeQkqVvdcuevpnAb`

---

## 10. 给下一个 agent 的忠告

- **实验前先 `git log --oneline -10` 看最近改了什么** —— 本轮大改了 shim、加了
  3 个分析脚本、改了 rescore pipeline 的 AGENTS 字典,不了解这些会重复踩坑。
- **所有大的数据跑都上 westd,不在 Mac 上跑** —— 容器只在 westd,shim 也只在
  westd。Mac 只做代码改、本地分析、paper 编译。
- **发现 `data/results/*.json` 被 gitignore 别急着改** —— 默认规则是对的,
  只有 length_ablation.json、error_taxonomy.json、irt_calibration.json、
  arena_elo_ED.json 走白名单被保留(这 4 个是 paper 表格的源)。
- **改 `scripts/rescore_all_with_deepseek.py` 时,先 `cp` 一份备份** ——
  它被本轮 patch 过(加了 gpt5chat 到 AGENTS 字典),但 `RESCORE_ONLY_TASKS`
  环境变量仍不工作。
- **改 `integrations/search_shim/backend.py` 在 westd 上** —— 不要改 Mac 上的
  (如果 Mac 上有的话),因为 shim 只在 westd 运行。
- **paper 要保持中文** —— 用户明确要求 findings.tex 中文化。如果要加新 section
  保持同样语言风格。
- **跑 `make -C latex pdf` 前先 `python3 latex/generate_tables.py`** —— 否则
  tables/*.tex 不存在或过时,表格数字会跟实际数据对不上。

祝好。

---

**状态**: Phase 10b 完结,9/14 任务完成,paper scaffold 可编译,等待 Phase 10c
(#65 + #62)开工。
