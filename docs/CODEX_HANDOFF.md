# Codex Handoff: Multi-Modality Acquisition + AgentRL Task Set

Audience: Codex (gpt-5.5, bypass) implementing the next chunks. Claude orchestrates and
reviews. This doc is self-contained; read it fully before writing code.

Repo: `/root/Desktop/lyb/deep_reserch`. Run everything from the repo root with system
`python3` for offline work. Heavy training/sandbox work is gated to the my5090 box.

---

## 0. Operating rules (non-negotiable; a change that breaks any of these is a defect)

1. **Do not change the reward contract.** Grounding is modality-agnostic: `src/eval/evaluator.py`
   `_compute_ground_signals` reads only `rollout.retrieved_snippets` (dict url -> text) and the
   cited URLs (`s_ground = 0.6*f1_claim + 0.4*r_resolve`). Any new acquisition tool MUST land its
   evidence as `(url, text)` into `ToolResult.snippets` (and `fetched_urls`) so the reward credits
   it without any reward-side change. For tools that compute over pages (SQL, code-exec), key the
   computed result text to the SOURCE page URL(s) the agent supplied.
2. **Byte-identical default path.** A task with no `acquisition.tools_allowed` (or exactly
   `["search","fetch"]`) must behave exactly as before, same reward, same env trace. Never alter
   the existing `Search/Open/Read/WriteMemory/ReadMemory/Cite/Finalize` semantics or the default
   registry.
3. **Heavy deps are lazy.** Every module must import on a machine with NO faiss, torch, playwright,
   psycopg2, mysql, sentence-transformers, or mcp. Import those inside functions, guarded. Tests run
   with none of them installed.
4. **Regression must stay green.** Baseline (verified 2026-06-02):
   ```
   python3 -m pytest tests/test_tool_registry.py tests/test_modality_parity.py \
     tests/test_rl_reward.py tests/test_grpo_harness.py tests/test_action_parser.py \
     tests/test_composite_v3.py tests/test_tools_rag.py tests/test_tools_sql.py \
     tests/test_tools_crawl.py tests/test_tools_exec.py tests/test_mcp_server.py -q
   # => 122 passed, 4 skipped
   ```
   The 4 skips are `mcp`-guarded tests (package absent) plus one browser-parity skip. Keep it at
   `>= 122 passed`.
5. **Do NOT touch `data/changelog.json`, do NOT deploy, do NOT `git push`, do NOT `git commit`**
   unless the user explicitly asks. The changelog is the public record of SHIPPED changes; nothing
   in this workstream is deployed. Hold draft changelog text in your final report instead.
6. **House style:** no em-dash parentheticals in English prose. Use commas, parentheses, or colons.
7. **Security (load-bearing):** `run_code`/`run_bash` stay network-locked to the three localhost
   sandbox hosts only; SQL stays read-only with table/column allowlists. Never widen these.

---

## 1. What is already DONE and verified (do not redo)

### 1a. AgentRL training task set (`data/tasks/deep_research/rl/`)
The arena's 124 tasks are RL-unsuitable (they demand 100+ pages browsed, 60+ citations, 3500-8000
words, so a 4B in an 8-tool-call budget floors the reward and the GRPO group has zero variance).
A separate budget-feasible set was built and validated OFFLINE:

- 6 trainable tasks: `rl_easy_0001/0002`, `rl_medium_0001/0002`, `rl_harder_0001`, `rl_bilingual_0001` (zh).
- 2 modality demonstrators: `rl_modality_browser_0001`, `rl_modality_computeruse_0001`.
- 5 tool demonstrators: `rl_tool_{rag,sql,crawl,exec,mcp}_0001`.
- Golden seeds at `data/golden/rl/`. Validator: `scripts/rl_task_validate.py`.
- Every task validates READY (FAST + `_rl_strict` + `WEIGHTS_RL`): competent 0.74-0.81, fabricated/
  no-fetch nullifies to 0.0, group std ~0.26. Spec: `docs/AGENTRL_TASK_SPEC.md`. Manifest:
  `data/tasks/deep_research/rl/MANIFEST.md`.
- CAVEAT: golden-seed URLs are NOT network-confirmed (sandbox was down). Confirm or repoint at the
  first live run.

### 1b. Modality-complete env (P0 + P1, all offline)
- **P0 registry** (`src/rl/tools.py`): `Tool` / `ToolResult` / `ToolContext` / `ToolRegistry` +
  `build_tool_registry(task_config, ctx)` reading `acquisition.tools_allowed` (default
  `["search","fetch"]`). New `CallTool(name, args)` opcode in `src/rl/env.py` (folds ToolResult into
  the grounding store, enforces `tools_allowed` gracefully, counts vs `max_tool_calls`). `TOOL:` and
  `{"action":"call_tool",...}` parsing in `src/rl/action_parser.py`. Built-ins: `search`, `fetch`,
  `structured_lookup` (routes shim `/product_lookup` + `/post_lookup` into the action space).
- **P1 tools** (5 lazy provider modules):
  - `src/rl/tools_rag.py` (`rag_search`): dense+hybrid retrieval, doc_url is the citation id;
    `build_rag_index()` indexer; `VectorStore` Protocol + `ctx.extras["rag_store"]` DI seam.
  - `src/rl/tools_sql.py` (`sql_query`): READ-ONLY, SELECT-only + table/column allowlist +
    multi-statement reject + row cap + timeout; lazy sqlalchemy/psycopg2/mysql.
  - `src/rl/tools_crawl.py` (`crawl`): BFS link-follow bounded to the 3-host allowlist + depth/page/
    path limits.
  - `src/rl/tools_exec.py` (`run_code`, `run_bash`): network-locked to localhost 7770/9999/8090,
    temp cwd, scrubbed env, wall-clock + RLIMIT_AS, fs-escape block, default-deny; production microVM
    seam at the `Executor` Protocol (inject via `ctx.extras["code_executor"]`).
  - `integrations/mcp_server/` (`build_mcp_server`): exposes shim search/extract/lookups as a standard
    MCP server for external agents; eval-side federation, lazy `mcp`.
- **Browser + computer-use** (built earlier, `src/rl/backends.py`): `BrowserSandboxBackend`
  (Playwright), `ComputerUseBackend` (Protocol + text-proxy stub). `make_backend` /
  `backend_from_task_config` select a backend from the task `acquisition` block. `browser-dr` arena
  adapter registered (`integrations/agents/browser_dr/agent.py`).

### 1c. Architecture cheat-sheet (how to add a tool, the cheap path)
1. Create `src/rl/tools_<name>.py` exposing `def provide_tools() -> list[Tool]:` returning your
   tool instances. Mirror the existing providers (`provide_tools` at `tools_sql.py:511`,
   `tools_rag.py:561`, `tools_crawl.py:276`, `tools_exec.py:695`).
2. Add `"src.rl.tools_<name>"` to `_PROVIDERS` in `src/rl/tools.py:396`. The discovery loop
   (`_discover_provider_tools`, `tools.py:404`) imports it with try/except, so a missing heavy dep
   just omits the tool, never breaks `build_tool_registry`.
3. Your tool's `run(ctx, args) -> ToolResult` must land `(url, text)` into `snippets`/`fetched_urls`.
   Optional `state_delta` is for write-actions and is NOT scored by the grounding reward (it feeds a
   separate verifier).
4. Add `tests/test_tools_<name>.py` (offline, mocks/sqlite/injected fakes), and optionally a
   demonstrator task copied from a READY rl task with `acquisition.tools_allowed` extended.

The full survey and rationale is in `docs/ACQUISITION_ROADMAP.md`. Modality matrix is in
`docs/ACQUISITION_MODALITIES.md`.

---

## 2. Your work, prioritized

Two tracks. Track A is offline-buildable NOW (this is your main job). Track B is live-gated
(needs the my5090 sandbox up); prepare the code and scripts, but the actual run is done in a
sandbox-up session, not by you offline.

### TRACK A: offline-buildable now

**A1. Write-action tool + DB-state-diff verifier + simulated user (tau-bench style).** [P3, offline-doable]
- Goal: a new acquisition+action modality where the agent mutates sandbox state (Magento add-to-cart,
  place/cancel order) and is graded by comparing final DB state to a goal state, plus an
  LLM-simulated user turn. This is a SECOND reward contract (execution-based), separate from grounding.
- Files: `src/rl/tools_write.py` (`provide_tools` -> write-action tools, each returns a `ToolResult`
  with `state_delta` and NO grounding snippets), add to `_PROVIDERS`; a new
  `src/verifiers/state_diff_verifier.py` (compare observed vs goal state); a user-sim seam (inject an
  LLM client, offline test with a scripted fake).
- Contract: write-actions must be allowlisted per task (`acquisition.tools_allowed`) and the
  state-diff verifier is opt-in per task (do not perturb the grounding reward for read-only tasks).
- Acceptance: offline tests against an in-memory mock store assert the write applies, the state-diff
  verifier scores goal-match, and the user-sim seam works with a scripted fake. Regression stays green.
- Note: real Magento DB writes are Track B; build and test the logic against a mock store now.

**A2. On-page image content vision tool.** [P2, interface offline-buildable]
- Goal: a `read_image` / vision-extract step so a VLM can caption/OCR real Magento/Wikipedia images
  reachable in-browser, emitting text into `retrieved_snippets` (reward unchanged).
- Files: `src/rl/tools_vision.py` with a `Captioner` Protocol + `ctx.extras["captioner"]` DI seam;
  the real VLM call is the seam (do NOT hard-import a model). `provide_tools` -> `read_image`.
- Acceptance: offline test with a fake captioner that returns canned text, asserts the (image_url,
  caption) pair lands in snippets. The real VLM run is Track B.

**A3. Real computer-use policy wiring (the loop, not the weights).** [P2, loop offline-buildable]
- Goal: replace the `_TextProxyPolicy` stub with a real `ComputerUsePolicy` whose `observe()` captures
  the Playwright `page.screenshot()` + a11y tree and `act()` emits the standard action set
  (click/double_click/scroll/type/keypress/drag/move/wait/screenshot). `ComputerUseBackend.fetch()`
  loops observe -> act and STILL returns grounding text so the reward is unchanged.
- Files: extend `src/rl/backends.py` (or a new `src/rl/computeruse_policy.py`). The VLM that drives
  `act()` is an injected seam; do NOT bundle a model.
- Acceptance: offline test drives the observe->act loop with a SCRIPTED fake policy (no VLM, no live
  browser via an injected fake page), asserts it terminates and lands grounding text. The real VLM +
  live browser run is Track B (GPU now unblocked).

**A4. RAG indexer hardening + CLI.** [P1 follow-up, offline-buildable]
- Goal: make `build_rag_index()` in `tools_rag.py` a runnable CLI (`scripts/build_rag_index.py`) that,
  given a corpus path, chunks + embeds + writes a FAISS/Qdrant index, with a tiny-corpus offline test.
- Acceptance: offline test builds an index over a 5-doc in-memory corpus via the mock store and
  `rag_search` retrieves correctly. The full Kiwix+Magento+Postmill index build is Track B.

**A5. File/document ingestion is BLOCKED.** [P3] Do not build a fake PDF/XLSX tool: the sandbox has
no documents. This needs seeded content first (a user/Claude decision). Skip until content exists.

**Out of scope (do NOT build):** scholarly APIs (arXiv/PubMed/Semantic Scholar), open-web search,
email/calendar connectors. No live internet here; a fake tool would be dishonest or would break the
closed-allowlist reproducibility that is the arena's whole point.

### TRACK B: live-gated (prepare code/scripts; run happens on my5090 with sandbox up)

Do not attempt these offline. Write the wiring + a runnable script + a clear "how to run on the box"
note, and leave validation to a sandbox-up session.

- B1. Wire `sql_query` to the real Magento MySQL and Postmill PostgreSQL (connection config via env,
  read-only credentials). Validate the allowlist against the real schema.
- B2. Build the real RAG index over the live corpus (Kiwix ZIM + Magento + Postmill) with A4's CLI.
- B3. Run `run_code`/`run_bash` against a real microVM executor (inject via `ctx.extras["code_executor"]`,
  e.g. an E2B/gVisor/Firecracker backend) and confirm the network-lock holds at the kernel layer.
- B4. Confirm every golden-seed URL in `data/golden/rl/*.json` resolves on the live sandbox; repoint
  any 404 to a real opened URL, then re-run `scripts/rl_task_validate.py` on the affected tasks.
- B5. Run the GRPO pilot (`scripts/train_grpo_pilot.py`) with the new RL task set and a `tools_allowed`
  task, on the 5090, to confirm the realized reward curve matches the offline design target. See the
  my5090 access + recipe notes (ask Claude/user; do not hardcode credentials here).

---

## 3. How to verify your work (run before reporting done)

```
# imports must work with NO heavy deps installed
python3 -c "import src.rl.tools, src.rl.tools_rag, src.rl.tools_sql, src.rl.tools_crawl, \
  src.rl.tools_exec, src.rl.env, integrations.agents; print('imports OK')"

# full suite (must stay >= 122 passed; add your new test file to the list)
python3 -m pytest tests/test_tool_registry.py tests/test_modality_parity.py tests/test_rl_reward.py \
  tests/test_grpo_harness.py tests/test_action_parser.py tests/test_composite_v3.py \
  tests/test_tools_rag.py tests/test_tools_sql.py tests/test_tools_crawl.py tests/test_tools_exec.py \
  tests/test_mcp_server.py -q

# any task you add or touch must validate READY
python3 scripts/rl_task_validate.py data/tasks/deep_research/rl/<task>.json
```

For each new tool: confirm `build_tool_registry({"acquisition":{"tools_allowed":[...,"<tool>"]}}, ctx)`
exposes it, and that the default `build_tool_registry({}, ctx)` still lists exactly `["fetch","search"]`.

---

## 4. Pointers

- Plan + survey (cited): `docs/ACQUISITION_ROADMAP.md`
- Modality matrix: `docs/ACQUISITION_MODALITIES.md`
- RL task spec + readiness: `docs/AGENTRL_TASK_SPEC.md`, `data/tasks/deep_research/rl/MANIFEST.md`
- Registry + reward: `src/rl/tools.py`, `src/rl/env.py`, `src/eval/evaluator.py`
- Validator: `scripts/rl_task_validate.py`; modality stamper: `scripts/stamp_task_modality.py`
- CLAUDE.md has the deploy/changelog hard rule (Track B / deploy only, not your offline work).

## 5. Report format (what to hand back to Claude for review)

For each task you complete: the files created/edited, the exact pytest result lines, the security-guard
test results (for write/SQL/exec), any path covered only by mocks (and why), and a DRAFT changelog
entry text (do NOT write it to `data/changelog.json`). Flag anything you could not do offline as
Track B with the reason.
