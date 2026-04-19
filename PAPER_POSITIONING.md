# Paper Positioning — "Prior Work & Positioning" 段落草稿

> 源:open-web benchmark 调研 subagent 2026-04-19

## Benchmark landscape 对照表

| Benchmark | Internet 方式 | Reproducible? | Scope |
|---|---|---|---|
| DeepResearch Bench (ICLR 2026) | Agent-native live | Scoring only | Full web |
| DRACO (Perplexity) | Agent-native live | Scoring only | Full web |
| ResearcherBench (GAIR-NLP) | Live + Jina | Scoring only | Full web |
| DRBench (ServiceNow) | Sandbox + dated URLs | Mostly | Medium |
| BrowseComp (OpenAI) | Live | ❌ | Full |
| **BrowseComp-Plus** (ACL 2026) | **Static 100k corpus** | ✅ | Medium |
| WebArena-Verified (ServiceNow) | Sandbox only(6 apps) | ✅ | None(transactional) |
| **我们(~200k docs)** | **Static kiwix + Magento + Postmill** | ✅ | **Medium(info + transactional)** |

**关键**:我们是 **唯一**结合 transactional sandbox(WebArena 血统)+ reproducible IR corpus(BrowseComp-Plus 血统)的 DR benchmark。

---

## Prior Work & Positioning(~400 词论文草稿)

**Prior Work and Positioning.** Benchmarks for Deep Research agents split cleanly along one axis: how they grant the agent access to "the world." The first camp — DeepResearch Bench (Ayanami et al., ICLR 2026), DRACO (Perplexity, 2025), and ResearcherBench (GAIR-NLP, 2025) — is agent-agnostic and assumes live internet: participating systems bring their own browser + commercial search API, and only the scoring layer (LLM-judge rubrics, sometimes post-hoc Jina re-scraping) is controlled. This maximizes ecological validity but, as the BrowseComp-Plus authors (Chen et al., ACL 2026) put it, "black-box web search APIs that operate over the entire internet are highly dynamic in content and consistently evolving," and evaluations under such APIs "conflate agent system performance with the effectiveness of their retrieval components, [which] severely undermines the reproducibility of experiments." Beyond reproducibility, live-web evaluation also imposes high per-run cost via commercial search APIs and offers no principled defense against base-model contamination on the target documents.

The second camp sacrifices scope for scientific control. WebArena and its reproducible successor WebArena-Verified (ServiceNow, 2025) containerize six transactional web apps (Shopping, Reddit, GitLab, etc.) with HAR-trace replay, but contain no open-web information-retrieval surface. BrowseComp-Plus (Chen et al., 2025) goes the opposite direction, freezing BrowseComp into a fixed 100,195-document corpus with BM25 / Qwen3-Embedding indexes, which lets authors cleanly demonstrate that retrieval quality accounts for a 14-point gap on GPT-5 (70.1% vs 55.9%) — a decomposition impossible under live APIs. DRBench (ServiceNow, Oct 2025) takes a middle path: enterprise applications are fully sandboxed in Docker, while the "public web" is reduced to a curated whitelist of dated, archival URLs chosen to resist drift.

Our benchmark occupies a distinct slot in this landscape. We adopt the WebArena-Verified container lineage for transactional behavior (Magento storefront, Postmill forum) and combine it with a 200k-document static corpus served via kiwix (Simple English Wikipedia), closely mirroring BrowseComp-Plus's argument for disentangled retrieval-vs-reasoning evaluation while extending it beyond pure IR into a mixed transactional-and-informational environment. In doing so we inherit BrowseComp-Plus's fairness and contamination-control properties — every agent faces an identical, frozen, human-verifiable corpus — while retaining the action-grounded richness of WebArena-Verified. We regard this as the first DR benchmark that is simultaneously (i) fully offline-replayable, (ii) large enough for non-trivial multi-hop research, and (iii) able to exercise both retrieval and site-interaction skills.

---

## BrowseComp-Plus 引用重点(paper 里直接可引)

> "Supporting documents are obtained through black-box web search APIs that operate over the entire internet, which are highly dynamic in content and consistently evolving over time." — [arXiv 2508.06600]

> "Current evaluations of deep-research agents often conflate agent system performance with the effectiveness of their retrieval components... This entanglement also severely undermines the reproducibility of experiments." — [arXiv 2508.06600]

> "The dependence on commercial web search APIs introduces substantial practical constraints, including high operational costs and variability in retrieval quality." — [arXiv 2508.06600]

---

## 每 benchmark 细节(一页摘要)

### DeepResearch Bench
- 100 PhD 任务 × 22 field
- Agent 自己带工具 (OpenAI DR / Gemini / Perplexity / OSS)
- 成本:judge $0.04–$0.47/query × 100 = $5-50 scoring + $20-200 agent
- Leaderboard 月度更新

### DRACO
- 100 tasks × ~40 rubric 条
- Perplexity 自家搜索 live;外部复现要接 Tavily/Serper
- HF 公开 task + rubric + judge prompt

### DRBench
- 15 → 100 tasks
- 企业沙盒 Docker(Nextcloud/Mattermost/Roundcube/FileBrowser)
- 公网走"dated URL 白名单",认为 archival 稳定
- 114 注入 ground-truth facts

### BrowseComp-Plus
- **830 任务 × 100,195 静态 docs**
- BM25 / Qwen3-Embedding / ReasonIR / oracle retriever 4 选 1
- GPT-5 + Qwen3-8B 70.1% vs BM25 55.9% = retriever 对 score 贡献 14 pp

### WebArena-Verified
- 6 apps(Shopping/Reddit/GitLab/CMS/Map)
- HAR 网络 trace replay → 完全 offline re-evaluate
- 确定性 JSON-schema 评分取代 substring

## 对我们的启示

1. **定位**:"reproducible mixed-mode DR benchmark"(IR + transactional 混合)
2. **叙事**:sandwich 在 BrowseComp-Plus(纯 IR)和 WebArena-Verified(纯 transactional)之间
3. **引用重点**:
   - BrowseComp-Plus 开创了"静态 corpus 换复现"的学术正当性
   - WebArena-Verified 开创了"沙盒 app 沙盒 transactional"路线
   - 我们 = 两者合集
4. **scope 自信**:不要试图跟 DeepResearch Bench 争 open web;承认窄,但窄得有系统性价值
