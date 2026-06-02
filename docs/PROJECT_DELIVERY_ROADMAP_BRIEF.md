# Deep Research Arena Program Roadmap Brief

This brief turns the project from a benchmark repository into a full delivery
program for Agentic RL, Deep Research agents, open benchmarks, papers, patents,
and demos. It is also the task brief for a later remote Claude Code roadmap
draft on `vircs`.

## 1. Contract Targets

The program must deliver four classes of outcomes:

1. Technical reserve: file 1 to 2 invention patents around the prototype system.
2. System construction:
   - An evaluation and training system based on Agentic RL.
   - A general Deep Research prototype that gathers information over multiple
     steps, reasons over evidence, and writes research reports.
   - An open Deep Research agent model and a benchmark task set.
   - Delivery of technical documents, source code, datasets, trained or
     fine-tuned models, experiment results, and demo systems.
3. Academic impact: submit 1 to 2 papers to CCF-A or equivalent international
   conferences or journals.
4. Talent training: train 1 to 2 interns in the related area.

## 2. Current Assets

The repo already has meaningful assets:

- Controlled Deep Research arena: Magento, Postmill, Kiwix, search shim,
  strict sandbox contract, citation and grounding verifiers.
- Benchmark and leaderboard path: multi-agent runners, score files, composite
  scoring, Elo, bootstrap confidence intervals, public site source and deploy
  artifact path.
- Agentic RL foundation: `ResearchEnv`, tool registry, `CallTool`, action
  parser, GRPO harness, Qwen policy skeleton, RL-suitable task set, and fast
  deterministic reward validation.
- Acquisition and tool modalities: search, fetch, browser, computer-use loop
  seam, structured lookup, RAG, SQL, crawl, code execution, write actions,
  state-diff verifier, user simulator, and vision caption tool.
- Offline validation: local import checks, Track A tests, modality parity, tool
  tests, reward tests, and GRPO harness tests.
- Website and demo surface: `frontend` as the main Next.js public site source,
  `web/dist` as deploy artifact, with older `web` and `web-next` surfaces that
  need ownership clarification.

Recent P0 cleanup:

- Multi-agent work rules are now explicit in `AGENT.md`.
- `docs/ACQUISITION_MODALITIES.md` now reflects that GRPO pilot backend
  selection uses `backend_from_task_config`.
- `docs/LOCAL_DEV_CHECKS.md` and `scripts/check_track_a_local.sh` document and
  run local smoke checks without requiring `vircs`.

## 3. Main Gaps

The next stage should close these gaps:

1. Program-level research survey: clarify related work, novelty claims,
   benchmark positioning, patentable mechanisms, and paper targets.
2. Task closure: add demonstrator tasks for write actions and vision; validate
   all RL tasks against live sandbox URLs when the sandbox is available.
3. Training closure: run the Qwen GRPO pilot on a 5090-class machine, confirm
   reward variance, finite loss, checkpoint and resume, then scale curriculum.
4. Model release closure: define what "open Deep Research agent model" means:
   base model, LoRA adapter, training data, policy interface, evaluation card,
   safety and reproducibility notes.
5. Benchmark release closure: freeze a versioned benchmark split, task schema,
   golden data, scoring scripts, baseline results, and public leaderboard.
6. Demo closure: converge on `frontend` as the main public site, add a usable
   Deep Research demo flow, and keep deploy changes behind changelog rules.
7. Paper closure: move from engineering claims to paper evidence with ablation,
   human audit, modality parity, reward anti-hacking, and training curves.
8. Patent closure: draft 1 to 2 patent disclosure packets before public release.
9. Team closure: assign 1 to 2 intern projects with clean mentorship outcomes.

## 4. Proposed Workstreams

### WP0: Engineering Hygiene and Coordination

Purpose: make multi-agent work reliable before scaling.

Deliverables:

- Clean multi-agent worktree workflow.
- Local smoke script and verification document.
- Case-collision note for `AGENT.md/agent.md` and `CLAUDE.md/claude.md`.
- Canonical ownership map for `frontend`, `web`, `web-next`, data outputs, and
  release artifacts.

Next actions:

- Decide whether to keep duplicate case variants in the repo or resolve them in
  a Linux or case-sensitive worktree.
- Add a top-level developer entry point if needed, for example `pyproject.toml`
  or a `Makefile` with local smoke targets.

### WP1: Research Survey and Novelty Map

Purpose: define what we contribute scientifically and what is patentable.

Deliverables:

- Related work table: Deep Research benchmarks, WebArena and VisualWebArena,
  BrowseComp style fixed-corpus QA, GAIA, DRACO, ResearchRubrics, tau-bench,
  OSWorld, Agentic RL and GRPO systems.
- Novelty map: controlled sandbox Deep Research, modality-agnostic grounding
  reward, tool registry over strict local hosts, execution-state verifier,
  RL-suitable task curriculum, and open agent release.
- Patent candidate list with claim sketches and public-disclosure risk notes.

### WP2: Agentic RL Evaluation and Training System

Purpose: turn current RL environment into a reliable training system.

Deliverables:

- Versioned task schema with acquisition tools, expected state, markdown spec,
  citation policy, and golden seeds.
- Deterministic fast reward path plus live reward path.
- GRPO pilot launcher, checkpoints, resume, trend logging, and run reports.
- Tool safety envelope for SQL, code, crawl, write actions, RAG, vision, and
  computer-use.

Next actions:

- Wire `StateDiffVerifier` into execution-goal task evaluation.
- Add `rl_tool_write_0001` and `rl_tool_vision_0001` demonstrator tasks.
- Add golden URL live-validation script for `data/golden/rl/*.json`.
- Run first Qwen GRPO pilot on the sandbox machine.

### WP3: General Deep Research Prototype

Purpose: build the actual Deep Research agent experience, not only the scoring
backend.

Deliverables:

- Multi-step evidence gathering loop with search, fetch, RAG, SQL, crawl,
  browser, vision, and optional computer-use seams.
- Report writer that produces citations, source summaries, uncertainty notes,
  and structured sections.
- User-facing demo with task selection, retrieval trace, citations, scoring
  breakdown, and report output.
- MCP or adapter surface so external agents can run against the same sandbox.

Next actions:

- Define a canonical demo flow in `frontend`.
- Add task cards for RL-suitable and arena tasks.
- Show trace, cited URLs, reward dimensions, and failure cases.

### WP4: Open Model and Benchmark Set

Purpose: produce the open-source agent model and benchmark deliverable.

Deliverables:

- Benchmark dataset version: task JSON, golden seeds, schema docs, scoring code,
  license, datasheet, and baseline result table.
- Model release: base model choice, LoRA or adapter weights, training recipe,
  tokenizer and prompt format, eval card, checkpoint hashes, and limitations.
- Reproducibility bundle: environment notes, sandbox setup, local smoke,
  expected metric ranges, and leaderboard regeneration path.

Next actions:

- Decide the first open model target: likely Qwen3 small model plus LoRA.
- Create an eval card template before training finishes.
- Separate training tasks from public leaderboard tasks.

### WP5: Experiments, Papers, and Leaderboard Evidence

Purpose: turn the system into 1 to 2 CCF-A level submissions.

Paper candidate A:

- Title theme: controlled-sandbox Deep Research benchmark with grounding reward
  and reproducible leaderboard.
- Venue targets: NeurIPS Datasets and Benchmarks, ICLR, ACL, EMNLP, WWW, SIGIR.
- Evidence needed: benchmark construction, task coverage, human audit,
  baseline agents, scoring validity, ablations, and failure taxonomy.

Paper candidate B:

- Title theme: Agentic RL for grounded Deep Research under controlled evidence
  acquisition.
- Venue targets: NeurIPS, ICML, ICLR, ACL, EMNLP.
- Evidence needed: RL task curriculum, GRPO training curves, reward variance,
  tool ablations, modality parity, anti-fabrication reward, and model release.

Next actions:

- Build experiment matrix: baselines, tools, modalities, reward variants, and
  model sizes.
- Add human audit set for citation support and report quality.
- Pre-register the main claims before large training runs.

### WP6: Patent Reserve

Purpose: protect the strongest system mechanisms before public release.

Patent candidate 1:

- A controlled-sandbox Deep Research evaluation and training method that uses
  local web corpora, proof-of-fetch retrieval traces, citation resolution, and
  modality-agnostic grounding reward.

Patent candidate 2:

- An Agentic RL system for tool-using research agents with per-task tool
  allowlists, state-diff execution verification, strict sandbox network guards,
  and curriculum tasks that preserve reward variance.

Next actions:

- Draft invention disclosure forms with problem, method, claims, diagrams, and
  examples.
- Review public docs and release timing so patent filings precede disclosure.

### WP7: Delivery and Talent Training

Purpose: make the project shippable and useful for interns.

Deliverables:

- Final source code and docs package.
- Dataset and benchmark package.
- Model package and result package.
- Demo system and deployment notes.
- Intern onboarding materials and two scoped intern projects.

Intern project examples:

- Intern 1: RL task validation and golden URL audit, plus task datasheet.
- Intern 2: frontend demo and experiment visualization, plus user study logs.

## 5. Milestones

### M0: 1 week

- Finish P0 engineering hygiene.
- Produce complete project roadmap.
- Assign workstreams and multi-agent ownership.
- Prepare patent disclosure skeletons.

### M1: 2 to 4 weeks

- Finish research survey and novelty map.
- Add missing demonstrator tasks for write and vision.
- Add live URL validation and RAG index runbook.
- Freeze first benchmark and model release definitions.

### M2: 1 to 2 months

- Run live sandbox validation.
- Run first Qwen GRPO pilot.
- Produce initial demo with retrieval trace and scoring breakdown.
- Draft patent disclosures.

### M3: 2 to 3 months

- Run expanded training and ablations.
- Produce open benchmark v0.1 and model adapter v0.1.
- Build paper figures and tables.
- Start intern-led audit and demo polishing.

### M4: 3 to 6 months

- Submit 1 paper and prepare the second.
- File 1 to 2 patents.
- Release benchmark, model, code, data, and demo package according to the
  agreed disclosure schedule.
- Deliver final technical report and handoff package.

## 6. Remote Claude Code Roadmap Task Brief

When calling Claude Code on `vircs`, ask it to write a full roadmap document,
not to modify core code. Suggested target path:
`docs/FULL_PROJECT_ROADMAP.md`.

Prompt:

```text
You are Claude Code on vircs. Repo: /root/Desktop/lyb/deep_reserch.

Write a complete program roadmap for Deep Research Arena based on the current
repo state and the following delivery targets:
1. 1 to 2 invention patents for the prototype system.
2. An Agentic RL evaluation and training system.
3. A general Deep Research prototype that performs multi-step evidence
   collection, reasoning, and report generation.
4. An open Deep Research agent model and benchmark evaluation set.
5. Delivery of technical docs, source code, datasets, model artifacts,
   experiment results, and demo system to the client.
6. 1 to 2 CCF-A or equivalent papers.
7. Training of 1 to 2 interns.

First inspect the repo docs and code. Pay special attention to:
- README.md
- AGENT.md
- docs/CODEX_HANDOFF.md
- docs/PROJECT_DELIVERY_ROADMAP_BRIEF.md
- docs/ACQUISITION_MODALITIES.md
- docs/ACQUISITION_ROADMAP.md
- docs/AGENTRL_TASK_SPEC.md
- docs/PHASE_B_QWEN_GRPO_SPEC.md
- docs/STRICT_SANDBOX_CONTRACT.md
- scripts/train_grpo_pilot.py
- src/rl/
- src/verifiers/
- frontend/

Output a detailed Chinese roadmap in docs/FULL_PROJECT_ROADMAP.md. It should
include:
- What has already been built.
- What is still missing.
- Overall technical route.
- Workstreams, milestones, owners, and deliverables.
- Patent directions and claim sketches.
- Paper directions, target venues, experiment requirements, and risk controls.
- Open model and benchmark release plan.
- Demo system plan.
- Intern training plan.
- 1 week, 1 month, 2 month, 3 month, and 6 month milestones.
- Acceptance criteria and validation commands.
- Risks and mitigations.

Do not commit, push, deploy, or edit data/changelog.json or web/dist. Avoid
English em-dash parenthetical style.
```
