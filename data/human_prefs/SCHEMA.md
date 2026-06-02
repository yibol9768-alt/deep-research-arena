# Human preference label schema (`data/human_prefs/*.jsonl`)

Each `*.jsonl` file under `data/human_prefs/` holds one JSON object per line.
Each object is one human verdict on one pair of agent reports for one task.
The format is a superset of the unlabeled pair queue
(`tools/human_pref_collector/pair_queue.jsonl`, schema
`{"task_id","agent_a","agent_b"}`) plus the human verdict fields written by
the collector (`tools/human_pref_collector/server.py`).

## Record fields

| field        | type                  | required | meaning |
|--------------|-----------------------|----------|---------|
| `task_id`    | string                | yes      | Task id, e.g. `dr_cross_deep_0017`. Used to locate report `.md` files. |
| `agent_a`    | string                | yes      | Agent name on side A, e.g. `opencode`. Used as `<agent>__<task_id>*.md`. |
| `agent_b`    | string                | yes      | Agent name on side B. |
| `winner`     | `"a"` \| `"b"` \| `"tie"` | yes  | The annotator's OVERALL preference. Lowercase. |
| `dims`       | list[string]          | no       | Dimensions the annotator cited as the reason for the verdict, drawn from the judge dimensions: `coverage`, `depth`, `rigor`, `style`, `checklist`, `spec`. |
| `dims_cited` | list[string]          | no       | Legacy alias for `dims`. The collector currently writes this field. Tools accept either; if both are present they are unioned. |
| `annotator`  | string                | no       | Opaque annotator id (for inter-annotator agreement later). |
| `ts`         | string (ISO-8601)     | no       | When the label was made. The collector may write `timestamp` instead; both are accepted. |

## Example

```json
{"task_id": "dr_cross_deep_0017", "agent_a": "opencode", "agent_b": "storm", "winner": "a", "dims": ["depth", "rigor"], "annotator": "alice", "ts": "2026-06-02T10:00:00Z"}
{"task_id": "dr_cross_deep_0030", "agent_a": "tongyi-dr", "agent_b": "storm", "winner": "tie", "dims_cited": ["style"], "annotator": "bob", "timestamp": "2026-06-02T10:05:00Z"}
```

## Notes

- `winner` is the human's overall choice. `dims` / `dims_cited` are the
  reasons cited and are what align with the per-dimension judge labels in
  `scripts/compute_judge_human_kappa.py` and
  `scripts/validate_judge_alignment.py`.
- `tie` verdicts are kept on disk but dropped from the binary Cohen kappa
  contingency (kappa is computed over `{a, b}` only).
- Reports are located by trying, in order:
  `data/results/deep_reports/<agent>__<task_id>.md`,
  `..._matrix.md`, `..._smoke.md`, then the same set under
  `data/results/deep/`. The first existing match wins (deterministic).
