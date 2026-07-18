# Route A Question Bank

Questionnaire version: `route_a_qbank_v1`

Use exactly two batches per task. Preserve the user's Batch 1 answer before proposing candidates.

## Batch 1: unaided extraction

Ask all seven questions together:

1. What concrete output or decision does the user ultimately ask the report to produce?
2. Which alternatives, products, form factors, claims, or time periods must the report cover?
3. Which mechanisms or factual claims does the user explicitly ask to explain or verify?
4. Which user constraints must materially affect the comparison or recommendation?
5. Does the query explicitly request owner, community, expert, or target-user experience? If so, whose experience?
6. Apply the deletion test yourself: list every item whose complete omission would make the answer incomplete.
7. Which phrases in the query are ambiguous enough that two reasonable annotators might split them differently?

Tell the user: "Answer 1–7 briefly. You do not need YAML, URLs, evidence, or polished wording."

## Batch 2: challenge and decision

After extracting candidates from Batch 1, show one table and ask all decisions together.

Always ask:

1. For each candidate, choose `keep`, `merge with Rx`, `optional`, `delete`, or provide an edit.
2. Are any two candidates unable to pass or fail independently? If yes, merge them.
3. Did we split a user constraint, such as budget or duration, away from the decision it constrains? If yes, attach it instead of double-counting it.
4. If the query requests a recommendation, is there exactly one observable recommendation requirement?
5. Is any candidate merely desirable writing quality rather than an explicit query obligation? Delete it.
6. For every proposed source role, could another source type satisfy the query equally well? If yes, remove the role constraint.
7. Is any explicit query obligation missing from the candidate table? Add it in the user's words.

## Challenge probes by output form

Use only relevant probes.

### Compare

- Are the alternatives themselves one coverage requirement, while decision dimensions are separate requirements?
- Would separate atoms double-count the same comparison sentence?
- Does the query require comparing all alternatives or merely considering them?

### Explain or verify

- Is the requirement to discuss a mechanism, determine a direction/verdict, or both?
- Is the proposed requirement smuggling in the expected answer?
- Can the item be expressed without asserting a hidden gold truth?

### Experience

- Does the query truly require first-person/target-group experience, or merely say it would be nice?
- Is the requested population specific enough to be observable?
- Is a forum role intrinsic, or could a different source provide the requested experience?

### Recommend

- Which constraints must the final recommendation explicitly respect?
- Are those constraints already scored as comparison requirements, creating double credit?
- Does the requirement allow conditional or set-valued recommendations when the query permits them?

## Anchoring labels

Use these modes exactly:

- `human_interviewed`: the human supplied Batch 1 and decided all Batch 2 candidates.
- `human_interviewed_unresolved`: the human supplied Batch 1 but left one or more Batch 2 decisions unresolved.
- `ai_led_draft`: the AI supplied or decided the normative requirement list.
- `adjudicated_human`: a human resolved differences between two locked independent annotations.
- `synthetic_stress_test`: an AI produced an alternative list only to challenge a rubric; it is not an independent annotation.

Never pool these modes as if they had equal evidentiary value.
