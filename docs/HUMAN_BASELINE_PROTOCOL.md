# Human Baseline Protocol for `dr_arena_deep`

This is the protocol a human follows when producing the human-ceiling
report for a deep task. Written so that any future contributor can
reproduce it.

---

## Setup

- Workstation: any browser, no specialized agent tooling.
- Sandbox URLs: shopping `http://<host>:7770`, reddit `:9999`, wiki `:8090`.
- Output: a single `human_baseline.md` file that follows the same
  formatting rules as agent output (§7 of the task pre-registration).

---

## Time budget

- **Total**: 4 hours, hard cap.
- **Phase A — exploration** (45 min): scan all three sandbox sources
  for relevant material. Take notes only; no writing yet.
- **Phase B — drafting** (2 hours): write the report with citations
  in-line. Use copy-paste of URLs only — do NOT type URLs from memory.
- **Phase C — synthesis section** (45 min): contradiction findings,
  ranking, divergences, top-N list.
- **Phase D — bibliography + cleanup** (30 min): compile References
  section, validate every URL with `curl -I`.

---

## Rules

1. Every cited URL must come from a tab the runner actually visited.
2. No use of agent-style automation: no LLM, no scraping scripts, no
   search shim direct queries other than via the browser.
3. Search engines: shop catalog search, postmill search, kiwix search
   — all in-sandbox only. Public web is forbidden.
4. The runner MAY use a local LLM (e.g. running on their machine) for
   *editing* but not for retrieval. The composition must be human.
5. Notes log: maintain a free-text `notes.md` recording each browsing
   session for audit.

---

## Outputs

- `human_baseline.md` — the report
- `notes.md` — chronological notes (timestamps every ~15 min)
- `tabs.txt` — list of every URL the runner visited (browser export OK)

---

## Scoring

Once submitted, the human baseline is scored with the SAME composite
the agents use. Specifically:

```bash
python3 scripts/score_deep_answer.py \
  --task <TASK_ID> \
  --answer paths_to_human_baseline.md \
  --out   data/results/deep/human__<TASK_ID>.score.json
```

The composite is reported as the task's human ceiling.

---

## Exit criteria

- If the human baseline scores **< 0.50 composite**: the task is
  under-specified or too hard. Pull from the v1 release; rewrite the
  intent. Do NOT publish a task no human can pass.
- If the human baseline scores **≥ 0.85 composite**: the task is
  too easy. Either escalate the difficulty (more must-cite URLs,
  harder synthesis) or accept it as an "easy tier" datapoint.
- Sweet spot: **0.55 – 0.80** human composite.
