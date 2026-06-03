# DR eval execution plan (model roles locked, Bailian-backed)

Status: 2026-06-03. Companion to docs/roadmap/index.html (the component map) and
EVAL_STATUS_AND_LIMITATIONS.md (current state). This is the concrete how-we-run-it.

## Locked model roles (user decision)

All via Alibaba Bailian / DashScope (OpenAI-compatible, key at
`/root/.config/dra/bailian.env`, 211 models available):

- **Agents under test = Qwen.** Small/cheap first for the end-to-end smoke
  (`qwen3-30b-a3b-instruct-2507`), scalable to `qwen3-max` for the real run.
  The agent backbone drives search -> read -> write a cited report in the sandbox.
- **Judge = a bigger CROSS-FAMILY model: GLM-5.1** (`glm-5.1` on Bailian).
  Cross-family to the Qwen agents, so there is no self-preference bias (the
  judge never scores its own family). This is exactly the fairness property the
  human-alignment literature requires.
- **Grounding = judge-independent** (deterministic): citation precision with
  proof-of-fetch x curated must-cite recall. Unaffected by the judge choice, so
  the truth-gate is stable regardless of which LLM judges quality.

Why this split is fair: quality is the only judge-dependent axis; using GLM-5.1
(not Qwen) to judge Qwen agents removes self-enhancement bias, and the grounding
gate (deterministic) does the anti-fabrication work independent of any judge.

## Order of operations (the user's sequence: plan -> review -> do)

1. **Review (in progress).** A multi-agent review workflow audits the eval system
   for obvious problems (correctness, fairness, data integrity, agent pipeline,
   methodology, judge setup) before scaling. Fix the BLOCKERS it confirms.
2. **Ready the run surface.**
   - Confirm the my5090 sandbox is up (`/opt/deep_reserch`, Magento :7770 +
     Postmill :9999 + Kiwix :8090 + shim :8081 + ds_proxy :8088).
   - Confirm a runner can drive a Qwen-backbone agent via Bailian
     (OpenAI-compatible base_url + `qwen3-30b-a3b` model).
   - Pick the task subset that the corpus actually covers (task 0001 family is
     fully covered; 0002-0005 forum dimension is unreliable until the corpus is
     seeded, so either restrict to covered tasks or score only shopping+wiki for
     those).
3. **Smoke run (cheap, end-to-end, FAIR).**
   - Run the small Qwen agent on a few covered tasks -> cited reports.
   - Score: grounding (deterministic gate) + quality (GLM-5.1 pairwise, length
     controlled, position-swap) -> Bradley-Terry with bootstrap CI.
   - Verify fairness: gate removes ungrounded reports; ranking tracks grounding;
     no length/family bias; invalid captures excluded.
4. **Human annotation (the labeling site).** Build the annotation feature on the
   existing site so humans can label report pairs -> `data/human_prefs/*.jsonl`
   -> real per-dimension kappa for the GLM-5.1 judge (closes the human-alignment
   gap). Until then, validate the GLM judge with the label-free harness
   (judge_meta_eval: synthetic-gold + grounding correlation + LLMBar).
5. **Scale.** qwen3-max + more agents/tasks; report separability + rank
   significance; re-base + redeploy the public leaderboard with a changelog.

## Eval protocol (per run)

- Tasks: from the covered set; each task is a 3-source DR question (shopping +
  forum + wiki) with a curated golden.
- Agents: Qwen backbone (smoke: qwen3-30b-a3b; scale: qwen3-max) through the
  sandbox shim; every tool call logged (proof-of-fetch).
- Grounding (gate): citation precision (cited URL fetched + claim supported) x
  curated top-K must-cite recall; below floor -> excluded, fabrication -> 0.
- Quality: GLM-5.1 pairwise vs peers/reference, length-controlled, position-swap,
  multi-sample; aggregated by Bradley-Terry + bootstrap 95% CI.
- Validity: gate excludes fluent hallucinators; judge validated by judge_meta_eval
  (and, once labels exist, human kappa).
- Integrity: no synthetic data; invalid-capture runs excluded; changelog before
  any deploy.

## Open items the review will sharpen

- Corpus-task mismatch for 0002-0005 (seed forum corpus, or restrict tasks).
- Whether to re-base the public board on Qwen-agent + GLM-judge results.
- Annotation hosting: enhance the local collector vs a public site tab + Worker.
