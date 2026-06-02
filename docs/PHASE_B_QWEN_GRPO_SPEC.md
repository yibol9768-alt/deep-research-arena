# Phase B spec — real QwenPolicy + multi-turn GRPO loop (single 5090)

Status: implementation-ready. Targets the my5090 box (WSL2 Ubuntu, RTX 5090 32GB,
torch 2.11+cu128, sm_120). Replaces the GPU-deferred stub in `src/rl/qwen_policy.py`.
Goal: an honest efficacy PILOT (not SOTA) — real Qwen3-3B, real reward, live sandbox,
visible reward signal + healthy advantages + checkpoint/resume.

## 0. Why this shape
The existing harness drives the env via `policy.act(observation)` → `env.to_rollout()`,
and `Rollout` carries **no token_ids/logprobs** (verified: `src/eval/rollout.py`). GRPO
needs token-level data. So the policy itself records, per episode, the exact token
sequence and a response mask; `update(batch)` consumes those in episode order. We do NOT
change the frozen reward/composite path or the leaderboard path.

## 1. Model + inference (Unsloth, vLLM colocated)
- Load once: `FastLanguageModel.from_pretrained(model_name="unsloth/Qwen3-3B"... ,
  max_seq_length=PILOT_CTX (8192 for pilot), load_in_4bit=True, fast_inference=True,
  gpu_memory_utilization≈0.6)`. `fast_inference=True` colocates vLLM sharing weights
  (this is "Standby" — no manual sync). CONFIRM exact kwargs against the installed
  unsloth version before coding (`FastLanguageModel.from_pretrained.__doc__`).
- LoRA: `FastLanguageModel.get_peft_model(model, r=16, lora_alpha=32,
  target_modules=[q,k,v,o,gate,up,down]_proj, use_gradient_checkpointing="unsloth")`.
- Generation per turn: `model.fast_generate(prompt_text, sampling_params=...)` (vLLM).
  Pilot sampling: temperature 0.7, top_p 0.95, max_tokens 512 per turn.

## 2. The agent ↔ env loop (multi-turn ReAct-ish)
QwenPolicy is stateful per episode:
- `start_episode(task_config)`: reset `self._turns=[]`, `self._tok_ids=[]`,
  `self._resp_mask=[]`; seed the chat with a SYSTEM prompt (tool protocol + bilingual
  instruction echoing `scripts/run_deep_task.py`'s language injection) and a USER prompt
  with the task `prompt`/`intent`.
- `act(observation)`:
  1. Render the current chat (system+user+prior assistant/tool turns) via the tokenizer
     chat template → `prompt_text`, `prompt_ids`. Append the *new context tokens since
     last turn* to `self._tok_ids` with mask 0.
  2. `gen = model.fast_generate(prompt_text)`; `out_ids = tokenizer(gen).input_ids`.
     Append `out_ids` to `self._tok_ids` with mask 1 (trainable assistant tokens).
  3. Parse `gen` into one `Action` (see §3). Append assistant turn to chat.
  4. After env executes the action (next `step`), the runner feeds the next observation;
     we render the tool result as a TOOL/USER message — those tokens get mask 0 on the
     next `act`.
- On `Finalize`, the report is the last assistant turn. Episode token record is frozen
  and pushed to `self._episode_records` (list, in collect order).

## 3. Action parsing (robust, single action per turn)
Model emits a fenced directive, one per turn. Grammar (tolerant parser, regex+json):
- `SEARCH: <query>` → `Search(query)`
- `OPEN: <url>` → `Open(url)`
- `READ` → `Read()`
- `NOTE: <text>` → `WriteMemory(text)`  ; `RECALL` → `ReadMemory()`
- `CITE: <url>` → `Cite(url)`
- `FINALIZE:` then a markdown block → `Finalize(report_md)`
Fallbacks: if unparseable, treat as a no-op `ReadMemory()` (cheap) and count toward the
tool cap; if the model emits prose with inline `[title](http://localhost:....)` links and
the word FINALIZE, treat the whole text as the final report. Keep the parser in a small
pure function `parse_action(text) -> Action` with its own unit test (offline).

## 4. update(batch) — GRPO step
`batch` (built by `GRPOTrainer._build_batch`) has `rewards`, `advantages` (already group-
normalized: `(r-mean)/(std+eps)`), `rollouts` (episode order), `mask_tool_tokens`,
`rubric_snapshot`. The policy pops its `self._episode_records` (same order) to get
`(tok_ids, resp_mask)` per trajectory.

Per trajectory i:
- `ids = tensor(tok_ids_i)`, `resp = tensor(resp_mask_i)`. If `mask_tool_tokens`, resp is
  already the assistant-only mask we built (tool/observation tokens = 0).
- Forward `logits = model(ids[:-1]).logits`; `logp = log_softmax(logits)`; gather
  `tok_logp = logp[range, ids[1:]]`; align `resp[1:]`.
- Single-epoch on-policy GRPO ⇒ ratio≈1, so loss_i = `-(adv_i * (tok_logp*resp).sum()
  / resp.sum().clamp(min=1))`. (This is GRPO with one inner step = REINFORCE with the
  group baseline; correct and stable for a pilot. Add PPO clip + ref-KL in a later pass.)
- `loss = mean_i(loss_i)`; `loss.backward()`; clip grad-norm 1.0; `opt.step()`;
  `opt.zero_grad()`. Optimizer = 8-bit AdamW (bitsandbytes), lr 5e-7 (GRPOConfig.lr).
- Return metrics: `{loss, mean_reward, mean_abs_adv, n_resp_tokens, grad_norm}`.
Then clear `self._episode_records`.

Memory: process one trajectory at a time (no big batch), grad-checkpointing on, so a
3B/4-bit fits 32GB at ctx 8192. If OOM, lower ctx to 4096 and per-turn max_tokens to 384.

## 5. save/load
- `save(dir)`: `model.save_pretrained(dir/lora)` + `tokenizer.save_pretrained` + a small
  `qwen_policy.json` (model_name, ctx, step). `load(dir)`: load LoRA adapter.
- The trainer already persists step/rubric-store state; resume = trainer.load_checkpoint
  then policy.load. Test a 2-step → save → load → 1-step resume on the box.

## 6. Pilot entrypoint `scripts/train_grpo_pilot.py`
- Args: `--task-file` (one task json), `--steps` (default 20), `--g` (default 6),
  `--ctx` 8192, `--shim-url http://localhost:8081`, `--out runs/pilot1`.
- Build: QwenPolicy(...); backend_factory = lambda: HttpSandboxBackend(shim_url);
  evaluator_factory = lambda tid: ArenaEvaluator(tid, mode="fast"); RubricStore seeded
  from the task's checklist; GRPOTrainer(policy, evaluator_factory, {tid: store},
  GRPOConfig(g=..., refresh_every_n=16)).
- Loop `--steps`: `stats = trainer.step(task_config, backend_factory)`; log
  reward mean/std + advantage std + loss to `runs/pilot1/trend.jsonl`; checkpoint every
  10 steps. After training, `os._exit(0)` to skip torch teardown hang (known WSL issue).
- ACCEPTANCE: trend.jsonl shows reward variance within groups (advantage_std≈1 when
  rewards vary), update loss finite, no OOM, resume reproduces step+reward; a 3-step run
  finishes. (Reward going UP is a Tier-1 goal, not required for the smoke.)

## 7. Risks / confirm-on-box
- vLLM/unsloth must NOT downgrade torch off 2.11+cu128/sm_120 — the staged install
  verifies `MATMUL_OK` after each. If broken, pin torch==2.11 and install vllm/unsloth
  `--no-deps` + hand-add deps.
- `fast_generate` / `get_peft_model` kwargs vary by unsloth version — read the installed
  signatures first.
- Tool-call cap (env `max_tool_calls`, default 40) — pilot set to ~12 to keep episodes short.
- Keep generation+training in ONE process (shared weights); do not spawn a separate vLLM
  server for the pilot.
