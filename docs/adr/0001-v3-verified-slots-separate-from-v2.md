# ADR 0001: v3 verified slots remain separate from the v2 weighted scorer

- Status: Accepted for implementation; v3 is not yet a formal scoring protocol.
- Date: 2026-07-15
- Decision owner: Deep Research Arena.

## Context

The v2 headline combines report-level provenance with a weighted sum of fact
support, proof of fetch, and answer-key completeness. Those inputs use different
units and partly credit the same behavior more than once. The v2 tasks were also
written before their deterministic gold was assembled, which permits a natural
query to ask for reasoning that the nearby gold does not decide.

## Decision

1. Preserve v2 as an immutable, replay-only baseline with its original formula,
   task bytes, answer-key bytes, and transport semantics.
2. Implement v3 in new schema, graph, ledger, scorer, CLI, and board modules.
   Existing v2 scoring functions are not given implicit v3 branches.
3. Use a required task slot as the sole v3 deterministic verification atom. An evidence slot passes
   only when correctness, citation binding, frozen-corpus membership, legal
   discovery, and observed support all pass (`C ∧ B ∧ R ∧ L ∧ O`).
4. A v3 task passes only when every critical slot and the decision pass, there
   are no critical contradictions, the observation ledger is complete, and the
   finished report contains zero fabricated citations.
5. Aggregate complete local research problems as required research subgoals:
   every declared evidence/bridge dependency and the deterministic local
   conclusion must pass before that subgoal contributes completion. Isolated
   evidence leaves never directly raise research completion.
6. Publish Verified Research Completion and Task Solve Rate as separate,
   co-headline metrics. Publish Verified F1 only as a slot/claim diagnostic;
   never combine these values into a weighted rank. Process diagnostics and
   usefulness remain separate.
7. Refuse any board or comparison that mixes v2 `quality` semantics with v3
   `verified_slots_v1`, or that mixes corpus/case/protocol stamps.  A formal
   stamp pins the exact public query bytes and private case bytes, and pins the
   complete frozen-corpus registry hash separately from the evidence-graph hash
   so neither task wording nor unused-but-real URL membership can drift. The
   manifest also pins the exact formal scorer implementation bytes; scorer
   changes require a new manifest even if the human-readable semantics label
   remains `verified_slots_v1`.
8. Treat the repository's earlier `*_v3` weighted/soft-floor experiments as
   transitional research artifacts.  A filename containing `v3` is not a
   protocol claim: only the complete
   `dra_v3_evidence_graph_verified_slots_v1` stamp denotes this redesign.

## Consequences

- Historical v2 numbers do not change during v3 development.
- A real but irrelevant citation earns no slot credit; a fabricated citation
  blocks strict TaskPass even when all critical slots otherwise pass.
- Missing or damaged observations cause `withhold`, never an observed zero.
- A pilot case cannot become formal until its frozen support spans, proof DAG,
  node ablation, oracle, and adversarial failures have been reviewed.
- There is no compatibility promise between v2 and v3 numeric scores.
- Scores produced by different formal scorer implementation hashes cannot be
  aggregated under one protocol manifest.
- `composite_v3_softfloor`, legacy KG oracles, and synthetic
  `build_deep_leaderboard_v3.py` output must not be relabelled or merged into a
  verified-slots board.

## Replay control

`scripts/freeze_v2_legacy_baseline.py` writes and verifies the v2 byte manifest.
It pins the 100 task, answer-key, and checklist artifacts, the URL registry,
and the transitive local Python dependency closure of the actual v2 scoring
entrypoints. The manifest is an identity record, not permission to rescore
historical reports under v3.
