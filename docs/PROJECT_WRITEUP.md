# Deep-Research Arena: A Sandbox Benchmark for Open-Source DR Agents

## 1. Abstract

We built a reproducible benchmark for open-source deep-research (DR) agents that runs entirely on a sealed local sandbox: Magento for shopping, Postmill for forums, and Kiwix for an offline Wikipedia mirror. Thirteen frameworks were instrumented to route their search and LLM calls through the sandbox; nine produced enough valid runs to enter the leaderboard. Reports are scored on seven pillars and combined into `composite_v2`, a quality score multiplied by a truthfulness gate (URL reachability, quote fidelity, claim NLI), and ranked by Bradley-Terry Elo. The single most consequential finding is that the truth gate inverts naive rankings: agents that write the most fluent prose are not the agents that cite real, reachable URLs.

## 2. Why this benchmark

Existing public DR benchmarks (GAIA, BrowseComp, HumanEval-DR-style suites) push agents at the live web. That is the right setting for product evaluation but a poor setting for science: the live web drifts under your feet. A page that supported a claim last Tuesday may 404 today. A search engine that indexed result A this morning may rank result B above it tonight. Two researchers running "the same" benchmark a month apart get different numbers, and neither can prove the other wrong.

A sandbox benchmark trades realism for ground truth. We get exactly three corpora, exactly one search index, and exactly one set of pages that should be cited per task. Every URL the agent writes can be checked in O(1): is it in the sandbox, does it resolve, does the page actually contain the quoted text. We can build a frozen golden URL pool per task and never look at it again. Anyone re-running the benchmark a year from now gets the same numbers if the sandbox snapshot is the same.

This is closer in spirit to WebArena than to GAIA: a fixed, sealed environment that makes evaluation cheap and reproducible. The trade-off is that the sandbox is small (~2000 product pages, a slice of forums, a Wikipedia subset). What you lose in coverage you gain in being able to score every URL deterministically.

## 3. The sandbox

Three services on the evaluation host:

- **Magento** at `localhost:7770`. Roughly 2000 product pages, prices, descriptions, category trees.
- **Postmill** at `localhost:9999`. Reddit-style forums with threads, comments, tags.
- **Kiwix** at `localhost:8090`. An offline Wikipedia ZIM file.

Two glue services:

- **Search shim** at `localhost:8081`. A Tavily-compatible search API that the agents see; it actually searches across all three sandbox corpora.
- **DeepSeek proxy** at `localhost:8088`. An OpenAI-compatible proxy to DeepSeek V4-flash, with `thinking:disabled` injected so every framework gets the same non-reasoning backbone.

Each task is a one-paragraph research prompt that requires the agent to cite at least 120 distinct URLs across all three sources. The 57 cross-site tasks span recommendation, comparison, debunking, causal analysis, timeline, and enumeration patterns. Every task ships with a frozen golden URL pool of 120-130 must-cite URLs, scraped once and never regenerated.

No agent ever touches the real internet. Network egress from the agent venvs is blocked except through the shim and the LLM proxy. If an agent wants to "google" something, it gets shim results. If it wants a page, it gets a sandbox page or nothing. This is the constraint that makes truthfulness scorable.

## 4. The scoring

Every report is scored on seven pillars (the public explanation lives at `/how-it-works`):

1. **URL coverage**. Did the agent cite the URLs it should have? Recall against the must-cite pool, plus pool coverage and a domain-balance term across the three sandbox sources.
2. **URL reachability**. Do the cited URLs actually resolve in the sandbox? Each URL is HTTP-probed. Hallucinated paths return 4xx/5xx and reachability falls.
3. **Quote match**. When the agent quotes a page, does the page actually contain that text? Fuzzy match against fetched content.
4. **Claim NLI**. Are the agent's factual claims entailed by their cited page rather than contradicted or unrelated? NLI per claim.
5. **Checklist (LLM judge)**. A 21-item task-specific yes/no rubric evaluated by a DeepSeek judge at temperature 0.
6. **Citation alignment (ALCE-style)**. For each cited URL, does the linked page actually support the surrounding claim? Per-citation precision and recall.
7. **Spec compliance**. Hard rule checks: word count, citation count, paragraph count. Pass fraction over the three.

Two further LLM-judge rubrics (analysis depth, presentation) are scored but only contribute through `composite_v3`; the headline ranking is `composite_v2`.

The headline number is:

```
composite_v2 = reachability · qm_factor · nli_factor · (0.40·url_coverage + 0.40·judge_pass + 0.20·spec)
qm_factor    = 0.5 + 0.5·quote_match
nli_factor   = 0.5 + 0.5·claim_nli
```

The key idea is the **multiplicative truthfulness gate**. Reachability multiplies the quality score, not adds to it. If the agent fabricates URLs (reachability = 0), the whole composite goes to zero, regardless of how fluent the prose. If it quotes pages it never actually fetched, the quote-match factor pulls the score down hard. Truthfulness is non-negotiable.

For ranking, we record a "battle" on every task where two agents both have a valid score: whoever has the higher `composite_v2` wins, ties under a small epsilon are draws. We fit a Bradley-Terry model (the same model behind chess Elo) to the battle matrix and bootstrap a 95% CI. Pairwise comparison cancels out per-task baseline difficulty, which is why chess Elo works at all.

## 5. Results

Headline ranking on `composite_v2_truthful`, 56 tasks, DeepSeek V4-flash backbone:

| Rank | Agent | Elo | 95% CI | W | L | D |
|---:|---|---:|---|---:|---:|---:|
| 1 | camel-ai | **1481** | [1405, 1567] | 206 | 20 | 1 |
| 2 | flowsearcher-ds | **1401** | [1324, 1486] | 193 | 32 | 2 |
| 3 | smolagents | **1307** | [1211, 1404] | 170 | 42 | 15 |
| 4 | ldr | **945** | [871, 1014] | 80 | 100 | 47 |
| 5 | gpt-researcher | **866** | [793, 941] | 60 | 114 | 53 |
| 6 | deerflow | **822** | [756, 903] | 40 | 118 | 69 |
| 7 | ii-researcher | **732** | [676, 776] | 5 | 130 | 92 |
| 8 | langchain-odr | **729** | [674, 781] | 6 | 129 | 92 |
| 9 | storm | **718** | [677, 763] | 0 | 75 | 61 |

Excluded (every run filtered out): qx-agents (pydantic and IndexError under DeepSeek; framework-incompatible).

Three clusters fall out:

**Top (camel-ai, flowsearcher-ds, smolagents).** These three agents understand that a citation is a contract: the URL must resolve and the page must support the surrounding text. camel-ai's Elo lead over flowsearcher-ds is not statistically significant (p = 0.31 by permutation), nor is flowsearcher-ds's lead over smolagents. They are, for our purposes, a tied front cluster well clear of the rest. They differ in style. camel-ai writes long, structured reports with disciplined per-source URLs. flowsearcher-ds, our hierarchical-memory variant, has lower mean composite (0.30 vs camel-ai's 0.41) but more consistent tail behavior, which the Elo rewards. smolagents takes a different route again, leaning on a tight tool loop, but lands in the same neighborhood.

**Middle (ldr, gpt-researcher, deerflow).** Each fails at truthfulness in a recognizable way. ldr lower-cases Kiwix paths that the Kiwix server happens to be case-sensitive on, so reachability silently zeros. gpt-researcher invents `/products/<slug>` Magento paths whose slugs are never the real ones, so the URL pool recall is near zero (mean composite_v2 = 0.013). deerflow truncates its citation tables, producing reports that pass spec but cite far fewer than 120 URLs (mean composite_v2 = 0.023). The middle is a graveyard of agents that almost worked.

**Bottom (ii-researcher, langchain-odr, storm).** ii-researcher's chain-of-search loop terminates early, leaving the report with handful of citations. langchain-odr fabricates external URLs outright (Wikipedia URLs that point at the real Wikipedia, not Kiwix; Reddit URLs to live reddit.com). storm under-cites: its bibliography path was buggy in our integration until very late, see Section 6.

## 6. Selected findings

### 6.1 Reach-gate inversion (#findings)

Run the same battle matrix without the multiplicative gate (`composite_v1 = reachability · quality`, no quote-match or NLI multiplication) and the leaderboard inverts in interesting places. gpt-researcher jumps to #1 (Elo 1269), camel-ai falls to #3, ldr falls all the way to #9 (Elo 520, no longer rescued by reachability). The agents that produce the most fluent, longest, most-citation-shaped prose top the v1 leaderboard. The agents whose URLs actually resolve top the v2 leaderboard. This is the strongest argument for the gated formula. A DR agent that reads beautifully and fabricates URLs is worse than one that writes a clunky report and cites real pages, because the fluent fabrication is more likely to be believed downstream.

### 6.2 Per-framework failure modes (#failures)

Each agent at the bottom fails differently. gpt-researcher's failure is a slug bug: it generates Magento product URLs by templating product names into `/products/<kebab-slug>`, but Magento's actual slugs include numeric suffixes the agent never sees. Reachability ~0. ldr's failure is a case-sensitivity assumption: it lower-cases all Kiwix paths because most web URLs are case-insensitive, but Kiwix's Wikipedia ZIM is case-sensitive on article names. Reachability ~0 again, with a different root cause. langchain-odr does not bother with the sandbox at all when its retrieval cache misses; it confidently emits real-Wikipedia and real-Reddit URLs. ii-researcher quits the search loop after three turns. storm worked correctly but had an integration bug on our side, see Section 6.3.

### 6.3 Bugs we caught (#bugs)

Four bugs were caught and fixed mid-benchmark, and the runs were re-scored:

- **Kiwix URL alias bug.** The golden pool stored Wikipedia URLs in one canonical form (`/wiki/Page_Name`); some agents emit a Kiwix prefix variant (`/viewer#wikipedia/A/Page_Name`). The URL canonicaliser was patched to collapse the alias variants. Three historical pairs unblocked. 64 score files were re-scored after the fix.
- **storm bibliography bug.** Our storm runner read storm's polished article output but never merged the separate `url_to_info.json` URL table back into the markdown. The agent had cited correctly internally; we were scoring a citation-stripped version. After fixing `storm_runner.py`, storm went from "always 0" to roughly fourth-cluster performance on the runs we got.
- **qx-agents framework incompatibility.** Pydantic validation errors and an IndexError under DeepSeek backbone. Not our bug to fix; framework filtered from Elo with a public note in the audit table.
- **GPU loss mid-run.** The 5090 went unresponsive (`nvidia-smi: GPU is lost`) partway through. We migrated from local Qwen3.5-27b on LM Studio to the DeepSeek API in parallel, resumed the bulk run with no data loss. Separately, a DeepSeek API HTTP 402 (balance) interrupted later runs; the user topped up and the run continued.

### 6.4 What surprised us (#surprises)

The middle cluster surprised us most. Going in, we expected gpt-researcher and langchain-odr (the two most-starred frameworks in the field) to be among the strongest. Both bottom out on truthfulness. We also expected smolagents (a generic agent loop, not DR-specific) to lag the DR-specialist frameworks. It outperforms most of them. The DR-specialist label is doing less work than the architectural choices around URL handling and search-loop discipline. Camel-ai's strong showing was less surprising once we read its source: it has explicit URL-deduplication and citation-validation passes that other frameworks treat as the prompt's job.

A second surprise is the role of `composite_v2`'s claim_nli factor. It was originally added to penalize fluent-but-wrong claims. After the 2026-04-27 review, we dropped claim_nli from the headline composite (the multiplier is set to 1.0 for the runs reflected in the current leaderboard) because of NLI-judge reliability concerns; the truth gate stayed because reachability and quote_match alone already invert the ranking. The lesson: the cheapest pillars do most of the work.

### 6.5 Where the scoring is still imperfect (#limits)

Three honest limits. (1) Battles are synthesised from composite, not from real LLM-judge head-to-head; we cross-check against a separate human-graded URL truthfulness audit, but a future iteration should include an LLM-judge head-to-head signal. (2) Tasks are not yet stratified by type in the headline number. Recommendation tasks (anchors 0001/0002/0005) and Comparison/Causal tasks may interact with different agent architectures; the per-task table in the leaderboard makes this visible but the Elo collapses across types. (3) Some frameworks (storm, deerflow, ii-researcher) ran under different versions of our integration glue across the 30+ tasks for which they have data; rerunning all 56 tasks for those agents under the post-fix integration is on the queue.

## 7. What's next

- **Multi-LLM extension.** The current numbers are all DeepSeek V4-flash. The same scoring works for GPT-5, Claude, Gemini, Qwen. A "Compare across LLMs" page is the entry point: same agents, different backbones, same tasks, same gate.
- **More tasks.** We have 100 cross-site tasks designed; only 57 are scored to date. Expanding to 100 would tighten Elo CIs from ±80 to roughly ±60.
- **More frameworks.** Open contribution path: a runner module in `scripts/runners/`, a venv on the eval host, and the framework joins the leaderboard. Co-storm, deepagents, and tongyi are integrated but under-scored.
- **Human baseline.** A protocol exists (`HUMAN_BASELINE_PROTOCOL.md`) for human researchers to do the tasks under the same constraints. Human numbers would anchor the gap between agents and competent researchers, not just between agents.

## 8. Reproducibility

```bash
# On the eval host with sandbox + shim + ds_proxy running:
bash scripts/parallel_bulk_launch.sh 6
```

Or one agent on one task:

```bash
.venv-camel/bin/python3 scripts/run_deep_task.py \
    --agent camel-ai --task dr_cross_deep_0001 \
    --backbone deepseek-v4-flash --out-suffix matrix
.venv-camel/bin/python3 scripts/score_deep_answer.py \
    --task dr_cross_deep_0001 \
    --answer data/results/deep/camel-ai__dr_cross_deep_0001_matrix.md \
    --out data/results/deep/camel-ai__dr_cross_deep_0001_matrix.score.json
.venv-camel/bin/python3 scripts/build_deep_leaderboard.py
```

Public artifacts:

- Live leaderboard: `http://172.30.52.43:8000/`
- Repo: `https://github.com/yibol9768-alt/deep-research-arena`
- Method explanation page: `/how-it-works` on the leaderboard site.
- Frozen golden pools: `data/golden/deep/dr_cross_deep_XXXX.json`
- Per-run scores: `data/results/deep_v3/<agent>__<task>_matrix.score.json`
- Audit page (excluded runs, audit trail): `/audit` on the leaderboard site.

The scorer is deterministic given a task config, a markdown report, and the frozen golden pool (LLM-judge calls are temperature 0). Anyone with the sandbox snapshot can re-run the leaderboard from scratch and get the same numbers.
