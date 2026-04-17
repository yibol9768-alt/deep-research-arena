# Deep Research Benchmark — HANDOFF 给下一个 Agent

**写于**: 2026-04-17
**上一轮做到哪**: v3 Phase 6 完整跑通(4 跨站任务 × 3 agent × 6 pillar × 12 pairwise battles)
**当前项目根目录**: `/Users/liuyibo/Desktop/lyb/deep_reserch/`

---

## 0. 一分钟上手

```bash
cd /Users/liuyibo/Desktop/lyb/deep_reserch

# 看最近干了什么
git log --oneline -15

# 看完整结果
cat RESULTS_SUMMARY_v3.md
cat PAPER_FINDINGS.md

# 服务器连接(SSH 跑 benchmark 的地方)
ssh westd "echo OK"
```

.env 里有 API key(不要提交!):
- `ANTHROPIC_API_KEY`: 中转 API (`http://35.220.164.252:3888`) 支持 glm-5, qwen3.5-plus, MiniMax-M2.7
- 直连智谱 API: `https://open.bigmodel.cn/api/anthropic`, key `77b40695421f481b9b3e791f534cedd1.fLxax38Q7tKNm6PS` - 支持 glm-5.1, glm-4.6, glm-4.5

---

## 1. 项目是什么

**Deep Research Benchmark** —— 评测 AI Agent 做深度研究能力的框架。核心:

- 沙盒网站里出题(4 站中 shopping + reddit 活着)
- AI Agent 浏览、搜索、整合信息,写长文研究报告
- 6 维 composite 分数 + Arena Elo 排位

**v3 核心创新**: **跨站 Deep Research** + **KG-grounded golden answer**(零人工标注)+ **6-pillar composite vs LLM judge 分歧**的系统证据。

---

## 2. 完整架构

### 沙盒容器(在 westd 服务器的 WSL Ubuntu Docker 里)

| 站点 | 端口 | 状态 | 用途 |
|---|---|---|---|
| Shopping (Magento) | 7770 | ✅ | 商品/评价/价格 |
| Reddit (Postmill) | 9999 | ✅ | 25 个版块帖子评论 |
| ~~GitLab~~ | 8023 | ❌ 镜像丢失 | 167 开源项目 |
| ~~Shopping Admin~~ | 7780 | ❌ 镜像丢失 | Magento 后台 |

> **警告**: gitlab + shopping_admin 在 WSL 崩溃时 overlayfs 损坏丢了,下载每个要几小时。本轮只用了 shopping + reddit。

### 代码结构

```
src/
├── agents/
│   └── glm_react_agent.py       # ★ 核心 ReAct agent,有 3-tier fallback
├── runner/
│   └── playwright_runner.py     # Playwright-based runner (Mac 用)
├── verifiers/
│   ├── fact_kg_verifier.py      # KG 三元组事实验证(主力)
│   ├── checklist_verifier.py    # DRACO 风 15 条 binary rubric
│   ├── llm_judge_verifier.py    # RACE 4 维 judge
│   ├── citation_verifier.py     # ALCE F1 引用
│   └── markdown_report_verifier.py  # 结构/字数/段落
├── scoring/
│   ├── composite_v3.py          # 6-pillar weighted
│   ├── pairwise_judge.py        # Battle(A,B) LLM judge
│   └── arena.py                 # Elo compute
├── golden/
│   └── db_connect.py, db_schema_map.py, triple_extractor.py
└── metrics/
    └── efficiency.py            # tokens/time/cost

data/
├── tasks/deep_research/
│   ├── shopping/       # 4 单站 v3 tasks
│   ├── reddit/         # 4 单站 v3 tasks
│   └── cross_site/     # ★ 4 跨站 v3 tasks (0001/0005/0006/0007)
├── golden/             # KG triples JSONs
└── results/            # 所有 benchmark 产出

envs/
├── shopping/           # Magento scraper
├── reddit/             # Postmill scraper
├── gitlab/             # ★ 新增 GitLab REST API wrapper(容器丢了但代码留着)
├── shopping_admin/     # ★ 新增 Magento 后台 scraper
└── cross_site/
    └── oracle_dr_v3/   # Oracle 生成脚本

integrations/deerflow/
└── unified_adapter.py  # ★ 多站统一工具,monkey-patch DeerFlow 的 web_search/crawl

scripts/
├── bench_v3.py         # Mac 本地 bench runner (用 Playwright)
├── server_full_bench.py      # ★ 服务器端 bench(无需 Playwright,cross_site=True)
├── server_deerflow_4tasks.py # ★ 服务器端 DeerFlow runner
└── 其他历史脚本

third_party/
└── deer-flow-v1/       # ByteDance DeerFlow v1 (在 Mac,有 Python 3.12 venv)
```

---

## 3. 当前完整成绩

### 3-agent × 4 任务 Arena (2026-04-17 终版)

| Task | glm-5 | qwen3.5-plus | DeerFlow-glm46 |
|---|---|---|---|
| 0001 headphones (shop+reddit) | **0.659** | **0.652** | 0.441 |
| 0005 $500 home office (shop×4+reddit×2) | 0.437 | 0.440 | **0.471** |
| 0006 PC gaming (shop×3+reddit×2) | 0.476 | **0.514** | 0.402 |
| 0007 budget home cook (shop×2+reddit×2) | **0.440** | 0.324 | **0.442** |
| **平均** | **0.503** | 0.483 | 0.439 |

**Pairwise Judge 12 场 battles**:
- qwen: 6 wins 🥇
- glm-5: 4 wins 🥈
- DeerFlow: 1 win 🥉
- tie: 1

**Top-2 互换**:composite 说 glm-5 > qwen, judge 说 qwen > glm-5 → 论文核心证据。

---

## 4. 关键代码改动(本轮)

### A. Agent robustness 3-tier fallback
`src/agents/glm_react_agent.py` ~L620-680

修复了 cross-site agent 失败的 3 种情况:
1. **步数用完没调 finish** → text-only 重试 call
2. **"Let me compile the report" 后停止** → 检测短 meta 文本触发 fallback
3. **fallback 被中转 API 拒绝 400** → 重建 message list 只用 string content

不改这个,cross-site 任务全部 0.09 composite。

### B. Cross-site 工具模式
`src/agents/glm_react_agent.py` `_exec_tool` 增加 `cross_site=True` 参数。

当 task 有多个 `sites` 时, Shopping 和 Reddit 工具改用 requests + BeautifulSoup 而不是 Playwright。避开了 Mac 上 Playwright 页面状态切换不稳定。

### C. 新增多站工具
- `_GITLAB_TOOLS`, `_ADMIN_TOOLS` 加到 `_pick_tools()`
- 对应的 `_exec_tool` branches 用 requests 调 GitLab API / Magento admin

### D. 服务器部署
- `scripts/server_full_bench.py` — 独立于 Playwright 的 bench runner
- 直接调 `glm_react_agent.glm_react_agent(None, cfg)` 传 `page=None`
- 通过 `BENCH_MODEL` 环境变量切换模型
- 使用 `setsid + python -u + nohup` 实现 SSH 断开后后台不死

---

## 5. 需要修的(⚠️ TODO)

### P0(马上该修)
1. **`dr_cross_v3_0007` agent markdown_structure=0.4** — 某些次 agent 没写出满足 min_words 的报告
2. **DeerFlow fact_kg 全部为 0** — DeerFlow 选的产品跟 oracle 完全不重叠,需要扩 oracle 覆盖或改 KG matching 逻辑更宽松
3. **qwen 在 task 0007 只拿 0.324** — citation=0 说明根本没放 [text](url),需要在 prompt 里对 qwen 加强 citation 格式要求

### P1(论文前要解决)
4. **容器 gitlab + shopping_admin 重建** — D 盘现有 695GB 可以放,但下载 156GB + 20GB 需要几小时
5. **Dual judge 消除 self-preference** — 当前 pairwise judge 用的是 glm-5,它偏好自己也偏好 qwen。需要 Claude 或 DeepSeek key
6. **扩 rubric 到 30 条/任务** — 当前 15 条,DRACO 2026 论文基准 40 条。现有 60 条 checklist 覆盖 cross_site 的 4 任务
7. **fact_kg precision 加回来** — 跨站任务 `do_precision=True` 时 DB 查询用 shopping 站 schema,但 Reddit 的 score/comment_count 没 DB backing

### P2(扩展)
8. **更多跨站任务** — 现在 4 条,论文可能要 10+
9. **v2 vs v3 对比实验** — 单站 benchmark vs 跨站 benchmark 上 agent 差异。v2 数据在 `data/results/bench_v2_MEGA.md`
10. **噪声鲁棒性曲线** — ImageNet-C 风格,给页面加 404/延迟/广告注入看 agent 如何降级
11. **合并 repo 结构** — 现在 PLAN.md/RESULTS_SUMMARY_v3.md/PAPER_FINDINGS.md/HANDOFF.md/README.md 都有内容,新 agent 首次看可能晕

---

## 6. 已知 bug / 遗留

| Issue | 位置 | 严重性 |
|---|---|---|
| SSH 隧道 Mac 上不稳定(Clash TUN fake-IP 劫持) | Mac 本地 | 中 - 可以重启 tunnel 恢复 |
| WSL 在长时间高负载后会崩 | westd 服务器 | 高 - 上次崩丢了 2 个容器镜像 |
| 中转 API 的 glm-5 在 multi-turn tool calling 会出现 "Invalid chat format" 400 | 代码已 workaround | 低 |
| DeerFlow 的 `src/` 和本项目 `src/` namespace 冲突 | 用 subprocess 隔离已解决 | 低 |
| `_pairwise_judge` 的 judge 也是 glm-5 → self-preference | TODO P1-5 | 中 |
| `fact_kg_verifier` 的 precision 分支对 reddit tasks 无意义 | `src/verifiers/fact_kg_verifier.py` `L140-170` | 低 |

---

## 7. 快速跑 benchmark(下次想复现)

### 本地跑(Mac,要 Playwright)
```bash
cd /Users/liuyibo/Desktop/lyb/deep_reserch
set -a; source .env; set +a
python scripts/bench_v3.py react --model glm-5 --tasks dr_cross_v3_0001 --no-judge --no-pairwise
```

### 服务器跑(推荐,稳定)
```bash
# SSH 到 westd
ssh westd

# 在 WSL 里跑(检查容器先)
wsl -d Ubuntu -- bash -c "
cd /opt/deep_reserch
docker ps
curl -s http://localhost:7770/ -o /dev/null -w 'shop=%{http_code}\n'

# 启动 bench(setsid 后台)
BENCH_MODEL=glm-5 setsid .venv/bin/python3 -u /mnt/c/tools/server_full_bench.py > /tmp/bench.log 2>&1 < /dev/null &

# 查看进度
tail -f /tmp/bench.log
"
```

### 跑 DeerFlow
```bash
# 服务器端脚本路径
/mnt/c/tools/server_deerflow_4tasks.py
# DeerFlow 需要 Python 3.12 venv
/opt/deep_reserch/third_party/deer-flow-v1/.venv/bin/python3
```

### 跑 pairwise judge
```bash
python /tmp/pairwise_3way.py  # 在 Mac 本地跑即可,只读 answer 文件
```

---

## 8. 最重要的一句话结论

> v3 框架完全跑通。**跨站 Deep Research benchmark 可用。Composite vs Judge 分歧在 cross-site 设定下复现 v2 MEGA Arena 发现,这是论文的核心证据。**DeerFlow 生成更长报告但得分最低,说明 multi-agent 结构复杂 ≠ 研究质量高。

---

## 9. 文件索引(新 agent 读顺序)

1. `HANDOFF.md` (本文件) — 全景
2. `PAPER_FINDINGS.md` — 5 个论文级发现
3. `RESULTS_SUMMARY_v3.md` — 完整分数表
4. `PLAN.md` — 历史进度 + 架构图
5. `README.md` — 用户文档(TODO: 需要根据 Phase 6 重写)
6. `data/results/final_*.json` — 所有 agent × task 分数
7. `data/results/pairwise_3way.json` — 12 场 battles
8. `data/results/deerflow_final_*.md` — DeerFlow 原始 26k char 报告

## 10. 联系信息

- 远程服务器: `ssh westd`(配置在 `~/.ssh/config`)
  - HostName: `8ll05950fh36.vicp.fun`(内网穿透,会变)
  - WSL Ubuntu: `wsl -d Ubuntu`
  - 项目部署路径: `/opt/deep_reserch/`
- API endpoints:
  - 中转(无限流,支持 glm-5/qwen3.5-plus/MiniMax-M2.7): `http://35.220.164.252:3888/v1/`
  - 直连智谱(有限流,支持 glm-5.1/4.6/4.5): `https://open.bigmodel.cn/api/paas/v4/`

## 11. 给下一个 agent 的忠告

- **如果要跑 benchmark,直接上服务器**。Mac 上 SSH tunnel + Playwright 两个都不稳定,别折腾。
- **API 出 429 别慌**,等 30-60s 就恢复。中转 API 对多轮 tool calling 容忍度差,用 DeerFlow 要加 sleep。
- **修 agent 前看 answer 文件**。`data/results/*.answer.md` 会告诉你 agent 实际输出什么,比看 composite 分数更有用。
- **fact_kg=0 不一定是 bug**,可能是 agent 选了不同的产品子集。先看 answer 和 oracle 对比才知道。
- **飞书文档路径**: `/tmp/feishu_*.py` 都是追加脚本,DOC_ID=VbmVdXEtUobBToxYziecLi76nBf。修改文档直接写新的 append script。
