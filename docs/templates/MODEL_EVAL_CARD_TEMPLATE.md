# Model Eval Card Template

## 1. Model Identity

- Model name:
- Base model:
- Adapter type:
- Adapter path:
- Checkpoint hash:
- Release date:
- License:

## 2. Intended Use

Describe intended use cases for the Deep Research agent and explicit non-goals.

## 3. Training Setup

| Field | Value |
| --- | --- |
| Training algorithm |  |
| Reward |  |
| Task split |  |
| Tool budget |  |
| Context length |  |
| Hardware |  |
| Training steps |  |

## 4. Tool Interface

Allowed tools:

- `search`
- `fetch`
- optional `rag_search`
- optional `sql_query`
- optional `crawl`
- optional `run_code`
- optional `run_bash`
- optional `read_image`
- optional write tools

Safety constraints:

- sandbox-local URLs only
- SQL read-only
- code execution network-locked
- write actions only in resettable sandbox or mock store

## 5. Prompt and Action Format

Document:

- system prompt
- action grammar
- final report format
- citation policy

## 6. Evaluation Tasks

| Split | Path | Count | Notes |
| --- | --- | --- | --- |
| RL train | `data/tasks/deep_research/rl/` |  |  |
| Held-out |  |  |  |
| Public arena |  |  |  |

## 7. Results

| Metric | Score | Notes |
| --- | --- | --- |
| FAST reward mean |  |  |
| grounding score |  |  |
| citation resolve rate |  |  |
| state_diff score |  | opt-in tasks only |
| human audit agreement |  |  |

## 8. Ablations

| Ablation | Result | Interpretation |
| --- | --- | --- |
| no tools |  |  |
| search/fetch only |  |  |
| +RAG |  |  |
| +SQL |  |  |
| +vision |  |  |
| grounding gate off |  |  |

## 9. Limitations

- The model should not be treated as open-web capable unless evaluated outside the sandbox.
- The model may overfit to sandbox URL style.
- Tool failures can reduce report quality.
- Judge-based dimensions require human calibration.

## 10. Reproduction

```bash
bash scripts/check_track_a_local.sh import
bash scripts/check_track_a_local.sh track-a
bash scripts/check_track_a_local.sh core
```

Add the exact model load and evaluation command once the adapter exists.
