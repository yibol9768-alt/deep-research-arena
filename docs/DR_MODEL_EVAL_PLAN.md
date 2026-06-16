# 训练型深度研究模型 评测路线图(DR-model eval roadmap)

文档日期:2026-06-09
适用仓库:/root/Desktop/lyb/deep_reserch
关联:[`FINDINGS_2026-06-09.md`](FINDINGS_2026-06-09.md)、[`PROJECT_STATUS_2026-06-09.md`](PROJECT_STATUS_2026-06-09.md)

---

## 1. 背景与动机

现有框架榜上的 12 个 agent(gpt-researcher、camel-ai、deerflow、storm 等)都是**脚手架(framework/scaffold)**:外挂一个通用 LLM,自己写检索-综合流程。

新方向:评测**训练过的 agent 模型**,也就是**专门用 RL 训练出来、放出权重的深度研究模型**(它自带 agent 循环 + 工具调用习惯)。DR Tulu-8B 是我们接入的第一个。

**驱动这件事的初步发现(DR Tulu,公平评测下,2026-06-09):**
- DR Tulu 在我们沙箱里**只检索十几个真实来源(100% 可达),却在报告里写了 75-86 个 URL,其中 ~75-80% 是它凭空编的**(假产品 slug、假帖子 id),全部 404。
- 真实接地率 ≈ 13-25%,**垫底档**。
- 之前 box 上那套 harness 因为把真 URL 直接喂给它,把这个毛病完全盖住了(详见第 2 节"公平性")。

**核心问题:这是 DR Tulu 个例,还是一类系统性问题?** 要回答,必须再公平地测几个同类训练模型。这也是本路线图的目的。

---

## 2. 评测方法(公平口径,所有模型统一)

每个训练模型都按 DR Tulu 的公平做法接入,保证可比:

1. **用模型自己的原生工具**(它训练时见过的 search/browse 工具格式),不替换成我们自己的工具。
2. **工具后端锁进我们的沙箱 shim**(`POST localhost:8081/search` + 浏览沙箱 URL),和 field 里其他 agent **同一套检索**。
3. **模型自驱**:它自己决定搜什么,**禁止任何硬编码查询计划**。
4. **不注水引用**:不往报告里补凑链接。
5. **打分统一**:judge-free 接地分(reachability + quote)+ 判官 Elo(deepseek-v4-flash,见 [`dra-judge-bailian-route`]),最终 truth-gated Elo = 判官 Elo × 接地门。

**接入模式(可复用)**:参照公平 DR Tulu runner(`/opt/deep_reserch/.dra_tmp/run_dr_tulu_fair_eval.py`)——**子类化模型原生工具,只重写 `_execute_mcp_call`(或等价的网络后端),指向沙箱**;其余 agent 循环、工具名、引用解析全部保留原生。每接一个新模型,主要工作就是搞清它原生工具的后端调用点,然后照这个套路接沙箱。

> ⚠️ 反例(不要重蹈):box 上旧的 `run_dr_tulu_official_dra_eval.py` 有 4 处破坏公平 —— 硬编码耳机查询计划、自定义非原生工具、引用重写绑死自定义工具、`append_references` 凑 60 个链接。**任何新模型接入都不能出现这些**。

---

## 3. 候选模型清单

筛选标准:**开源权重 + 有推理/agent 代码 + 能在我们沙箱里跑**。优先长报告型(我们的任务是市场情报长报告,不是 BrowseComp 短问答)。

### 高优先(训练型 DR 模型,契合度高)

| 模型 | 机构 | arXiv | 权重 | 5090(32GB)可跑 | 任务契合 | 现状 |
|---|---|---|---|---|---|---|
| **DR Tulu-8B** | Ai2 / UW | 2511.19399 | HF `rl-research/DR-Tulu-8B` | ✅ 直接(~16GB) | ✅ 长报告 | **正在跑(公平版)** |
| **WebSailor-7B / 3B** | 阿里 Tongyi | 2507.02592 | HF(Alibaba-NLP/WebAgent) | ✅ 7B 直接 | ⚠️ 偏短问答,长报告待验证 | 未接 |
| **Tongyi DeepResearch 30B-A3B** | 阿里 | 2510.24701 | HF,Apache-2.0 | ⚠️ 30B MoE ~60GB,**需量化**(AWQ→~16-18GB) | ✅✅ 长报告旗舰 | **半接**:`tongyi_runner` 用的是 Tongyi 框架 + DeepSeek 假后端,**不是真模型**;只算了 grounding 未上榜 |
| **WebWeaver** | 阿里 Tongyi | 2509.13312 | 框架(planner+generator) | ✅ 配小后端 | ✅ 报告生成,DeepResearch Bench SOTA | 未接 |

### 低优先(短问答型为主,长报告契合差,选做)

WebShaper / WebDancer / WebWalker / WebExplorer(阿里)、Search-R1、R1-Searcher / R1-Searcher++、ZeroSearch、Jan-nano(Menlo)、O-Researcher(2601.03743)、OpenResearcher(2603.20278)、LiteResearcher(2604.17931)、WebThinker、MiroThinker。这些多为 BrowseComp/QA 风格,跟我们"长报告"任务格式不匹配,接入价值低,留作后续补充。

> 注:arXiv 号与机构以调研时所见为准,**正式接入前需逐个核对**(权重 repo 名、license、是否真有推理代码、是否长报告)。历史上有过 arXiv 号张冠李戴(见 [`dr-rl-key-papers`]),引用前必查。

---

## 4. GPU 与接入约束(my5090,32GB)

- **7-8B 模型**:bf16 直接装(DR Tulu-8B、WebSailor-7B)。
- **30B+ 模型**:bf16 装不下(Tongyi 30B ~60GB),**必须量化**(AWQ/GPTQ 到 ~16-18GB)才能在 5090 上自托管;否则只能用"框架+小后端"的半真方案(就像现在的 tongyi_runner,但那不算评测真模型)。
- **显存共享**:同一时刻只能起一个被测模型的 vLLM(顺序跑)。换模型要先停上一个的 vLLM。
- **box 不稳**:长批处理要可断点续跑(跳过已完成报告)+ tmux,参照 DR Tulu 批处理 `drtulu_fair_batch.sh`。

---

## 5. 优先级路线图

> 前提:**先等 DR Tulu 公平版 75 题全部跑完 + 出完整接地画像**,确立基线和流程,再依次接后续模型。

1. **P1 — WebSailor-7B**:最像 DR Tulu(阿里 RL web agent,7B 直接装),工作量最小。先验证"RL 训练的 web agent 在沙箱里是否也编 URL"。
2. **P2 — 真 Tongyi DeepResearch 30B-A3B(量化版)**:开源长报告旗舰,价值最高。要把现在的"假后端"换成**真模型量化自托管**。工作量中等(量化 + 起 vLLM + 接原生工具到沙箱)。
3. **P3 — WebWeaver**:框架型,SOTA 报告生成,配小后端跑;归入"框架"类别对比。
4. **P4 — 短问答型若干**:选做,补充覆盖面。

每一步的产物:该模型在全 75 题的**接地画像(免费)** + 判官 Elo + truth-gated 排名,纳入榜单。

---

## 6. 研究角度 / 假设

DR Tulu 暴露的现象若在 WebSailor / Tongyi 上复现,就不是个例,而是一类系统性问题:

> **假设:RL 训练的深度研究模型,在分布漂移到受控沙箱时,会系统性地"编造"看似合理的引用 URL(检索少量真源,然后凭记忆/模式补全大量不存在的链接)。纯 LLM-as-judge 的榜单看不出来,truth-gated 接地门能把它们一一抓出并压到榜尾。**

这是个有分量的结论方向:不只测"谁强",而是揭示**一类训练范式的共性失败模式 + 一个能抓住它的评测方法**。多接 2-3 个训练模型就能坐实或证伪。

需要诚实记录的对照点:
- 这些模型多在真实开放网络上训练/评测;放进我们封闭沙箱属于分布漂移,"编造"有一部分是漂移导致(它把沙箱当真实 Google 用,发 `site:localhost:7770` 这种 query)。这一点要在结论里讲清楚——我们测的是**"接地真实性 under 受控环境"**,不是它在开放网络的绝对能力。

---

## 7. 现状(2026-06-09)

- **DR Tulu 公平版**:75 题批处理在 box tmux `drtulu` 跑(进度见 `.dra_tmp/drtulu_fair_progress.txt`),judge-free 接地分跑完后给完整画像。判官 Elo(花钱)暂缓。
- **观察到的早期异常**:个别任务(如 0004)产出极短报告(~500 字),需在跑完后统计有多少"空报告"——这本身也是 DR Tulu 的一部分真实表现(某些题直接崩)。
- **下一步**:等 DR Tulu 跑完 → 按 P1(WebSailor-7B)→ P2(真 Tongyi 30B 量化)依次接入,每个都走第 2 节的统一公平口径。

---

### 参考来源(调研 2026-06-09,正式接入前需逐个核对)

- DR Tulu(Ai2/UW):https://arxiv.org/abs/2511.19399 · https://huggingface.co/rl-research/DR-Tulu-8B · https://github.com/rlresearch/dr-tulu
- WebSailor(阿里 Tongyi):https://arxiv.org/abs/2507.02592 · https://github.com/Alibaba-NLP/WebAgent
- Tongyi DeepResearch 30B-A3B(阿里):https://arxiv.org/pdf/2510.24701 · https://github.com/Alibaba-NLP/DeepResearch
- WebWeaver(阿里 Tongyi):https://arxiv.org/pdf/2509.13312
