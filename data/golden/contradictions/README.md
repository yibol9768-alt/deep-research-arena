# Gold contradictions: status and pipeline

## Status (2026-07-03): NO adjudicated gold contradictions exist

As of 2026-07-03 this directory contains zero adjudicated gold
contradictions. Every published answer key ships `gold_contradictions: []`.
The "find the contradictions" pillar (registry items T4/T5 in
`paper_iclr/UNREASONABLE_PARTS_REGISTRY.md`) is currently a schema promise
with no content.

**The paper must not claim this pillar** (no "precomputed gold
contradictions", no P4 selling point, no contradiction-recall numbers)
until at least one task in this directory has a populated, human-filled
adjudication file with SUPPORTED_CONFLICT entries. Until then, any
contradiction-related quota in legacy task configs is deprecated
(see `contradiction_findings_min_deprecated` markers in the task JSONs).

## Scope: numeric/spec conflicts only

Per registry T5, soft marketing-vs-review tension ("immersive noise
cancelling" vs "ANC weak at high frequencies") is a nuance, not a decidable
contradiction, and is out of scope here (it belongs to the subjective
rubric). The builder only extracts unit-typed numeric claims (battery
hours, driver mm, Bluetooth version, bitrate kbps, impedance ohm, weight g,
ANC dB) and flags a candidate only when a marketing value conflicts with a
wiki/DB numeric reference for the same product or technology beyond a typed
tolerance.

## Pipeline (three stages, no shortcuts)

1. **Builder** (`scripts/build_gold_contradictions.py`): reads local
   products/wiki-facts JSON, emits `<task_id>.candidates.json` plus
   `<task_id>.adjudication.template.json`. Every candidate carries
   `status: "candidate_needs_human_adjudication"`. The builder never
   emits gold, by design.
2. **Human adjudication**: a person copies the template to
   `<task_id>.adjudication.json` and fills, for every entry:
   `candidate_id`, `verdict` (one of `SUPPORTED_CONFLICT`,
   `NOT_A_CONFLICT`, `NUANCE`), `adjudicator`, `note`. Partial
   adjudication is rejected at promotion time.
3. **Promotion** (`--promote`): only entries with
   `verdict == "SUPPORTED_CONFLICT"` become gold, written to
   `<task_id>.gold.json`. `NOT_A_CONFLICT` and `NUANCE` entries are
   recorded in the counts but never enter the gold set.

Demo (self-checking fixture, prints only):

```
python3 scripts/build_gold_contradictions.py --demo
```

## Files

| File | Meaning |
|---|---|
| `<task_id>.candidates.json` | machine-flagged numeric conflicts, NOT gold |
| `<task_id>.adjudication.template.json` | empty adjudication form |
| `<task_id>.adjudication.json` | human-filled verdicts (create by copying the template) |
| `<task_id>.gold.json` | adjudicated gold, SUPPORTED_CONFLICT only |
