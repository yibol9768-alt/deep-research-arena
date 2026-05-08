# Contributing a Deep-Research Agent

This benchmark scores Deep-Research frameworks on an offline sandbox of
Magento (shopping), Postmill (reddit), and Kiwix (Wikipedia). To get your
agent on the public leaderboard, you implement one Python class against
the `BaseAgent` contract, run it against the sandbox locally, and open a
PR.

## Quick start

### 1. Bring up the sandbox

You need Docker. The compose file fetches 3 sandbox images (~35 GB total)
plus our shim gateway:

```bash
git clone https://github.com/<this-repo>/deep_reserch.git
cd deep_reserch
export DEEPSEEK_API_KEY=sk-...               # the LLM ds_proxy needs one
docker compose -f infra/sandbox.docker-compose.yml up -d
curl http://localhost:8081/healthz           # gateway should return {"ok":true}
```

If you can't fetch the sandbox images from a registry, see
`infra/build-images.md` for offline corpus rebuild instructions (uses
`scripts/build_deep_golden.py` to scrape and bake fresh images).

### 2. Implement BaseAgent

```python
# my_pkg/my_agent.py
from __future__ import annotations
import time
from integrations.agents.base import AgentServices, AgentResult, BaseAgent


class MyAgent(BaseAgent):
    name = "my-cool-agent"          # appears on the leaderboard
    venv = None                     # set to a Path if you need a separate venv

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        t0 = time.time()
        # `services.search_url` speaks Tavily/Brave/Serper/DDG/SearxNG —
        # call any wire format you prefer.
        # `services.llm_url` is OpenAI-compat (and Anthropic-compat at /llm/v1/messages)
        report_md = await self._do_research(intent, services)
        return AgentResult(
            markdown=report_md,
            elapsed_s=time.time() - t0,
            metadata={"model": services.model},
        )

    async def _do_research(self, intent, services):
        # ... your agent's research loop here ...
        return "# Report\n\nMy findings cite [Sony WH-CH710N](http://localhost:7770/sony-wh-ch710n.html) ..."
```

Things to know:

* `services.search_url` is `http://localhost:8081`. The gateway answers
  `POST /search` (Tavily), `GET /v1/brave/web/search`, `POST /v1/serper`,
  `GET /searxng/search`, `GET /duckduckgo/search` — pick whichever your
  framework already uses.
* `services.llm_url` is `http://localhost:8081/llm/v1` (OpenAI-compat) or
  `/llm/v1/messages` (Anthropic-compat). The gateway proxies to ds_proxy
  which talks to DeepSeek-V4 with thinking disabled.
* If your agent fails (subprocess crash, timeout, etc.) **return**
  `AgentResult(markdown="", error="...")` instead of a placeholder
  string. The harness writes a `*.md.error` file and excludes the
  attempt from leaderboard battles — *not* a 0-score loss to other
  agents.
* All cited URLs in your markdown should resolve on the sandbox
  (`localhost:7770/...`, `localhost:9999/f/...`, `localhost:8090/wiki/...`).
  Fabricated URLs sink your `reachability` score, which gates the
  multiplicative composite.

### 3. Run the public test set

```bash
python -m integrations.submit my_pkg.my_agent.MyAgent --tasks 0001-0005
```

Output:

```
Running my-cool-agent on 5 task(s) → http://localhost:8081
[dr_cross_deep_0001] reach=0.92 qm=0.78 ck=0.50 V3=0.31 (45s)
[dr_cross_deep_0002] ...
...
mean V3                                              0.295  (5/5 scored)
log: data/results/submitted/my-cool-agent__submission.json
```

Run the full 30-task common subset (`--tasks 0001-0030`) before opening
a PR. The submitter writes `*.score.json` files alongside the `*.md`
under `data/results/submitted/`.

### 4. Open a PR

In your PR, include:

* Add your slug + class to `integrations/agents/__init__.py:_register(...)`
* Submission log file (`data/results/submitted/<your-slug>__submission.json`)
* Notes on which search wire-format you used, any quirks, expected
  weaknesses

A maintainer re-runs your agent against the full leaderboard tasks to
verify reproducibility, then merges.

## What's scored

Six pillars feed the headline V2 composite:

1. **`url_reachability`** — fraction of cited URLs that 200-OK on the
   sandbox. Multiplicative gate; URL fabricators get pinned to ~0.
2. **`url_coverage`** — `must_cite_recall` against a per-task golden
   pool of ≥120 URLs.
3. **`quote_match`** — your claims' token-overlap with the cited page
   body.
4. **`claim_nli`** — NLI judgment that the cited page entails the
   claim.
5. **`checklist`** — per-task LLM judge over 21 binary criteria.
6. **`citation_alignment`** — sentence-level "did the cited URL support
   this sentence" judgment.

The headline composite is `composite_v2 = reachability × quality`, where
`quality = 0.40·url_coverage + 0.40·checklist_pass_rate + 0.20·spec`.
See `src/scoring/leaderboard_composites.py` for canonical formulas.

## Citation styles supported

You can cite however your framework naturally writes — the extractor at
`src/verifiers/citation_format.py` recognises six styles:

| Style | Example |
|---|---|
| Markdown link | `[label](http://...)` |
| Source: prefix | `Source: http://...` |
| Bullet line | `- http://...` (alone on the line) |
| Numbered ref | `[1]` inline + `## References\n[1] http://...` |
| Footnote | `[^a]` inline + `[^a]: http://...` |
| Bare URL | `http://...` (catchall) |

URLs are canonicalised (sorted query, normalised slash/port/fragment) so
your style choice doesn't bias the score.

## What's prohibited

* Network calls outside the sandbox (`*.real-internet.com`). The
  gateway's HTTP intercept catches these — they count as fabricated
  citations.
* Hardcoding the answer key for a task in the agent. Re-run validation
  on a held-out task split will catch this.
* Reading the golden pool directly. The `data/golden/` directory is
  for evaluators only; agents that touch it are excluded from the
  leaderboard (the `golden-dump` baseline is allowed because it's
  marked as a known upper bound).
