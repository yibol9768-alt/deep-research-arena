# Running experiments on Deep Research Arena

Status: **2026-07-09**. The scoring stack described here is implemented and tested.
One enforcement step is not yet in place; §7 says exactly what it is and which
lanes it affects. Read §7 before you trust a `proof_of_fetch` number.

---

## 1. What this benchmark measures, and what it refuses to guess

DRA runs a deep-research framework against a **frozen sandbox**: a Magento store
(`:7770`), a Postmill forum (`:9999`), and an offline Kiwix Wikipedia (`:8090`).
There is no live web. Every page the agent can reach is in a fixed corpus, and
every fact worth grading is in a golden answer key.

The headline score is

```
truth = reach^1.5 * (0.39 * fact + 0.28 * pof + 0.33 * completeness)
```

Read `board.protocols` in any board JSON for the exact gamma, weights, and
version stamps that produced it. **Boards with different `formula_version` or
different `pof_semantics` are not comparable.** The builder refuses to mix them.

### The grounding axes answer four different questions

An agent can fail to be grounded in four ways, and collapsing them is how a
benchmark ends up rewarding fluent fabrication.

| Quantity | Question it answers |
|---|---|
| `reach` | Do the URLs it cited exist in the frozen corpus? |
| `pof` | **Did the agent actually open the pages it cites?** |
| `snippet_only` | It cited a real page it never opened, but search had shown it that page and a snippet. Shallow, not invented. |
| `hallucinated_grounding` | It cited a real page it never opened **and never searched for**. Nothing but the model's parameters could have supplied that URL. |
| `fabrication` | The URL does not exist at all. |
| `quote_support` | Having opened a page, does what it wrote match what the page says? |

`pof` is computed from a transport-level evidence log the shim writes while the
run is happening. It is not inferred from the report's prose. Until 2026-07-08 it
was: the evaluator fetched the cited URLs *afterwards* and matched them against
the text, so a model that guessed a URL that happened to exist and paraphrased a
page it never opened scored exactly like one that retrieved and read it.

### What the instrument refuses to do

If a run produced no evidence log, or the lane's page reads bypassed the shim,
`pof` **cannot be measured**. The scorer then does one of two things and never a
third:

- With `--require-transport-pof` (the default): the lane is **withheld** from the
  board, with the reason printed.
- With `--no-require-transport-pof`: `pof` falls back to the old textual measure
  and the board is stamped `pof_semantics: text_v1`, which makes it incomparable
  to any `transport_v2` board.

It never scores an unobserved lane as `pof = 0`. That would be an accusation of
citing pages it never read, made on the strength of our own failure to watch.

---

## 2. Bring the sandbox up

See `README.md` §7 for the Docker quickstart. Then start the two services that
sit between every agent and everything else:

```bash
# the search shim: the only way an agent may reach the sandbox
uvicorn integrations.search_shim.app:app --port 8081

# the LLM proxy: token accounting, per-run attribution
DSPROXY_USAGE_LOG=logs/usage.jsonl \
  uvicorn integrations.ds_proxy.app:app --port 8088
```

Running two workers concurrently? Each worker needs **its own shim instance**.
A shim serves one open run bracket at a time and returns `409` on a second, so a
shared shim serialises your workers rather than mixing their evidence. Derive the
port from `DRA_WORKER_ID` (`run_full_leaderboard.sh` does this).

---

## 3. The gate: refuse to run a blind experiment

```bash
python3 scripts/preflight.py --all
```

Non-zero exit means do not run. It is not advisory.

The core check is the **canary**: a scripted fake agent searches twice, opens one
of the returned pages, and cites three URLs, of which one is a real page it never
opened and one does not exist. The instrument must separate all three. If it
cannot, every `pof` you are about to compute is meaningless.

This check exists because `shim_search_delta` read exactly `0` on all 312 runs of
the 13-task subset, and nothing failed, nothing warned. "No agent ever searched
the sandbox" and "we never recorded that any agent searched the sandbox" produced
identical data, and the second one went unnoticed until the scores had already
been published.

The second check is that **the corpus can actually be reached, and that what it
hands the agent is what the scorer will accept.**

`check_sources_alive` puts a canned query through all three sites and fails if any
of them answers with nothing. `check_search_hits_are_in_corpus` then classifies
every URL the search tool returned and fails if any of them would be scored as
FABRICATED. Both must pass.

They exist because the store answered nothing, on every stack, for the life of the
project. The gateway dialled Magento by a `Host` it does not recognise; Magento
replied 302 to its `base_url` and dropped the query string; that address is a
closed port on the compose network; `requests` followed the redirect, raised, and
the handler returned `[]`. The guard was `if r.status_code >= 400`, which a 302
never trips. An unreachable store and a store with no match for the query produced
byte-identical data, so `fact` -- which only the store can support -- read 0 on
92.7% of reports, and that was written up as narrative style.

At run time, `run_deep_task` asks the shim for `GET /_sources/health?fresh=true`
**before** it opens the run's evidence bracket, and refuses to start if a source
is down. A live instrument pointed at a dead corpus records a clean, attributable,
meaningless run. The outcome is stamped into each run's meta as `source_check`;
`DEEP_RUN_SKIP_SOURCE_CHECK=1` records `skipped_by_env` there rather than leaving
no trace.

A source that answers but whose fan-out partly failed (the forum scans several
boards; one may 404) is reported as `degraded`. That warns, and is recorded, but
does not block: grounding every run over one missing board would be its own kind
of dishonesty.

`preflight` also runs `scripts/check_parity.py`, described next. Three checks can
only run on the box (per-lane model identity probe, "sandbox origins unreachable
except through the shim", and manifest-generated-on-the-executing-host); they are
reported as `SKIP` with the reason, never silently passed.

### If preflight fails on the store

`check_search_hits_are_in_corpus` fails when the store's `base_url` disagrees with
`url_registry.hosts.shopping`. Publish the store on `${SHOPPING_PORT:-7770}` with
`MAGENTO_BASE_URL=http://localhost:7770`, as `infra/release/compose.yml` and
`envs/shopping/docker-compose.yml` already specify.

Do **not** repair it by adding the other port to `url_registry`. That bakes a
scaffolding port into the definition of the frozen corpus, and every future board
inherits it.

If you must reach a source at an address it does not know itself by -- a compose
service name, a reverse proxy -- set `SHOPPING_PUBLIC` (likewise `REDDIT_PUBLIC`,
`KIWIX_PUBLIC`) to the origin it *does* answer to. The shim sends that as `Host`
and resolves the links the source emits against it.

---

## 4. Adding your own framework

### Parity is on capability, not on the prompt string

A native framework receives the sandbox as an in-process **tool**. A CLI
framework has no search tool at all and must be told how to `curl` the shim.
Those deliveries differ by necessity. What must not differ is the **task**.

`config/lane_protocol.yaml` states the contract. Every lane receives the shared
intent plus one shared line about output format, and nothing else. In particular
no lane may be told:

- a citation count (`at least N URLs`, `aim for >= N`)
- a word or paragraph count
- a number of searches to make
- a citation format (`use markdown links [label](url)`)
- an example URL

Each of those steers directly at a scored axis. `scripts/check_parity.py` scans
the adapter surface for them and fails the preflight on a hit. It parses
docstrings with `ast` rather than a regex, because several lane prompts *are*
triple-quoted strings and a regex that strips every triple-quoted block would
blind the checker to exactly what it exists to catch.

And the harness may not:

- write URLs or a sources block into the saved report
- rewrite a URL the model emitted (undoing a mask the harness itself applied is fine)
- retry, repair, or expand a report based on any scored quantity
- gate capture on any scored quantity

### These rules are not hypothetical

Every one was written after measuring what it cost.

| What the harness did | Measured effect |
|---|---|
| `ldr`: appended the framework's own retrieved link table to the report as `### Sources` | Removing it and rescoring: macro `reach` **0.9519 → 0.0000** (qwen), **0.9868 → 0.0000** (deepseek), 13/13 tasks. Its own prose cited no sandbox URL on any task. It had ranked #1 on both boards. |
| `storm`: appended `url_to_info.json` as `## References` | macro `reach` **0.9609 → 0.0000** |
| `ldr`: rewrote `en.wikipedia.org/wiki/X` into a Kiwix sandbox URL | Turned off-sandbox drift into perfect grounding, for one lane |
| `smolagents`: "the report is invalid unless it contains at least 5 exact `http://localhost` URLs", plus an automatic retry whenever `sandbox_url_count < 5` | A second attempt keyed on reach's numerator, which no other lane received |
| `is_weak_report`: classified a report as broken when `sandbox_url_count < 3` | The capture layer judged quality using the quantity the scorer measures |
| Per-backbone prompt masking, justified by "DeepSeek refuses localhost URLs" | Live API ablation, 4 arms x N=10: **0/10 refusals**, 114 localhost URLs written. The premise was false. |

Two frameworks (`storm`, `langchain-odr`) have **no page-read step at all**. They
consume search snippets. Their `pof` is `0` and that is honest: every citation
lands in `snippet_only`, and the instrument must not call it parametric recall.

### Declare your lane

Add an entry to `config/lane_protocol.yaml`:

```yaml
your-lane:
  delivery: in_process | subprocess | cli
  fetch_mode: shim_extract | shim_fetch | direct_requests | direct_aiohttp | direct_curl | none
  fetch_observable: false        # see §7 before setting true
  deviations: []                 # non-empty means a declared, disclosed exception
```

`fetch_observable: true` is a claim that **every** page read goes through the
shim. Verify it on the box (`logs/fetch/<run_id>.jsonl` must contain `fetch`
lines) before you set it. Setting it optimistically makes the instrument accuse
your lane of citing pages it never opened.

---

## 5. Run

```bash
python3 scripts/run_deep_task.py --agent <lane> --task dr_cross_deep_0001 \
    --backbone glm-4.7-flash
```

The harness generates a `run_id`, opens a `/_mark` bracket on the shim and on
`ds_proxy`, and closes it in a `finally`. If the shim is unreachable the run
**fails loudly** rather than proceeding un-instrumented.

Artifacts per run:

| File | What it proves |
|---|---|
| `<agent>__<task>.md` | the framework's own bytes |
| `<agent>__<task>.meta.json` | status, timings, and the report's `sha256` seal |
| `logs/fetch/<run_id>.jsonl` | every search and every page the shim served |
| `logs/fetch/blobs/<sha256>` | the exact bytes the agent was shown |
| `logs/usage.jsonl` | tokens, attributed by `run_id` |

The report seal is checked at scoring time. Anything appended to a report after
the framework produced it (a sources block, a bibliography) breaks the seal and
is reported as `TAMPERED`.

### Budget

There is **no comparative wall clock**. Cost is compared in tokens. A uniform
no-progress watchdog kills a run that has made no LLM call and no shim call for
`stall_timeout_s` (default 900s) and records it as `stalled`, which is an
infrastructure fault, not a framework failure. It is rerun. Only a task still
stalled after its reruns scores 0, and `build_truth_board` **refuses to build**
while any stalled task still has reruns owed to it.

This distinction exists because the local vLLM once spent 1206 seconds on a
single 128-token step while its neighbours ran at 106 tok/s.

---

## 6. Score

```bash
python3 scripts/build_truth_board.py \
    --run-dir data/results/runs/<run-set>/<backbone> \
    --replicates 3 \
    --cache sandbox_cache.json \
    --out board.json
```

- The formal builder requires the immutable `run_plan.json`. It reads flat
  `raw/*.meta.json` bindings and never infers lane, task, backbone, run set, or
  replicate from a filename. Historical nested trees require the explicit
  `--legacy-nested-layout` opt-out and cannot be mixed with formal artifacts.
- Shim and owned-egress evidence roots under `evidence/` are scanned
  recursively and merged by exact `run_id`; each recorder must have a complete
  owner bracket.
- Scoring **never opens a socket**. A cache miss raises rather than fetching the
  page, because the old behaviour confirmed a model's guessed URL with the
  evaluator's own request.
- Every missing or non-pass task x replicate cell scores `0`
  (`--missing-as-zero`, mandatory for formal boards). Without zero padding,
  the board rewards failing to produce a report: an agent that crashed on 11 of
  13 tasks used to be ranked on the 2 it finished. Measured: `claude-code` moved
  from #2 to #8 (qwen) and #4 to #9 (deepseek) once its missing tasks counted.
- Lanes below `--min-coverage` are ranked but flagged `low_coverage` and are
  excluded from headline claims.
- Rows publish pass/fail/stalled/infra_abort/timeout/missing rates. The 95%
  interval bootstraps tasks as clusters and keeps replicates inside each task;
  replicates are never treated as independent tasks.
- Mixing `text_v1` and `transport_v2` reports in one board is refused (`rc=3`).
- A board where **no** lane could be scored is refused (`rc=5`) rather than
  written empty. An empty board exiting 0 looks exactly like a clean run.

---

## 7. What is not yet enforced, and which lanes it affects

**The sandbox origins are still directly reachable.** The in-process gate rejects
off-sandbox URLs but lets `localhost:7770` through to the site, and it only
patches `requests`. `aiohttp`, `httpx`, and `curl` bypass it entirely.

So today, of twelve lanes:

| `fetch_observable` | Lanes | `pof` |
|---|---|---|
| `true` | `flowsearcher-ds`, `camel-ai` (shim `/extract`), `storm`, `langchain-odr` (no page reads) | `transport_v2`, real |
| `false` | `smolagents`, `gpt-researcher`, `deerflow`, `ii-researcher` (`requests`), `qx-agents` (`aiohttp`), `claude-code` (`curl`), `opencode`, `ldr` | **withheld** |

Patching each runner is not the fix. `codex` runs under
`--dangerously-bypass-approvals-and-sandbox` and `gemini-cli` under `--yolo`;
neither has an allowlist to tighten.

The fix is **network-level enforcement**: bind the three sandbox services where
only the shim can reach them, and let the shim own the canonical ports. Then any
lane's page read either goes through the shim or fails, whatever HTTP client it
uses, and `fetch_observable` becomes true by construction. That is the box-only
preflight check named `sandbox origins unreachable except through the shim`.

Until then, `--require-transport-pof` (the default) withholds those eight lanes
rather than guessing. That is the intended forcing function.

---

## 8. Known limitations, stated rather than buried

1. **The model identity probe reads a self-report.** vLLM's `--served-model-name`
   is free text. The manifest records `identity_scope: endpoint-self-reported`.
   It catches a misrouted lane (a `claude-code` run once filed qwen3-8b output
   under deepseek). It does not establish which weights ran.
2. **Long-lived services do not reload from disk.** A clean working tree does not
   mean the running shim is that code. The run contract requires `/healthz` to
   expose the sha of the loaded modules; **this is not implemented yet**.
3. **`quote_support` is a verbatim lower bound.** Paraphrase is missed.
4. **Cross-backbone comparison is not a single-variable experiment** until the
   thinking flag, sampling parameters, and context policy are aligned across
   lanes. Measured: the qwen lane ran with thinking ON, the deepseek lane with it
   OFF. `lane_protocol.yaml` declares `backbone.thinking: uniform`; there is no
   runtime assertion yet. Until there is, that axis is a **lane comparison**, not
   a backbone comparison.
5. **The usefulness jury has no human anchor.** Its Spearman correlation with
   `truth` is negative (-0.109 qwen, -0.409 deepseek) while the jurors agree with
   each other (kappa 0.63 / 0.80). The two axes measure different constructs. Do
   not use the jury to adjudicate which `truth` score is right. (`truth` itself is
   constructively decidable against the frozen corpus and needs no preference
   anchor; the jury does.)
6. **Historical data cannot be rescored.** The 13-task subset and the 55-task
   archive carry no evidence log. Their `pof` is not computable under
   `transport_v2`. They are diagnostic samples, not results.
7. **Concurrent attribution rests on discipline, not on request tagging.**
   Requests do not carry a `run_id` header; attribution comes from the shim's open
   bracket. One shim per worker, one open run per shim. An orphaned bracket is
   reclaimed after an idle TTL so a killed run cannot brick the queue, but two
   runs sharing one shim would still cross-attribute.

---

## 9. Reproducing a published board

Every board carries the identity of the code that produced it:

```bash
python3 -c "import json; print(json.load(open('board.json'))['protocols'])"
```

Check `formula_version`, `extractor_commit`, `pof_semantics`, and
`task_set_hash` against your tree. If any differ, you will not reproduce the
numbers, and you should not expect to.

`scripts/run_manifest.py` records, on the executing host, the git commit, whether
the tree was dirty, the content hash of every file that can move a score, the
hash of each framework's installed venv, the corpus fingerprints, and the model
identity probes. A manifest generated on a different host than the one that ran
the agents is refused by `verify()`, which is the point.
