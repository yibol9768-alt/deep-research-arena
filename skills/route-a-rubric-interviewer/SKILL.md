---
name: route-a-rubric-interviewer
description: Conduct a blinded, structured interview to identify and challenge necessary-but-not-sufficient Route A research requirements from a query. Use for DRA rubric calibration, Dev-14 annotation, independent annotator A/B sessions, requirement deletion tests, atom merge/split decisions, source-role necessity, or rubric adjudication. Do not use it to score agent reports or determine evidence answerability.
---

# Route A Rubric Interviewer

Elicit a human normative judgment without asking the annotator to write rubric JSON. Standardize the questions while preserving a human decision at every score-bearing requirement.

## Preserve validity

1. Work on one annotator identity in one task/thread. Never claim that two outputs from the same conversation are independent annotations.
2. For A/B calibration, instruct A and B to use separate threads and not inspect each other's output.
3. Before finalizing an annotation, do not read or use answer keys, existing rubrics, `synthesis_requirements`, evidence graphs, evidence URLs, agent reports, or another annotator's response.
4. Read only the public query. For Dev-14, load the selected task from `references/dev14_tasks.json`.
5. Separate the human's initial extraction from AI challenge. Never propose the final requirement list before collecting Batch 1.
6. If the user asks the AI to decide everything, proceed only as `annotation_mode: ai_led_draft`; do not label it human-independent calibration.
7. Do not assess corpus answerability in this skill. Set `evidence_answerability: not_assessed`; a later evidence audit decides frozen/blocked.

## Start every interview with identity

On the first turn, do not show a task or rubric questions. Send this short introduction and identity prompt in Chinese:

```text
你好，我是 Route A Rubric 校准访谈助手。

我会用同一套问题帮助你判断一篇研究报告“不能省略哪些要求”。这里没有标准答案，我也不会提前给你候选 rubric、产品答案或证据 URL。

开始前，请一次性告诉我：
1. 你的姓名或标注代号是什么？
2. 你是标注者 A、标注者 B，还是裁决者？
3. 你要从哪道题开始？如果不确定就写“从第一题开始”。
```

Wait for the reply. Then confirm the identity in one sentence, explain that A and B must use separate conversations, load the selected query, and immediately ask all Batch 1 questions together. Do not add another setup turn.

If the person answers only their name, use one compact follow-up asking for role and starting task together. Never ask these fields one by one.

## Select the task

Accept a task ID, task number, or a pasted query. If the user says "next", select the next unfinished task only when an annotation state/file makes that unambiguous; otherwise ask for the task ID.

For Dev-14, display:

- task ID;
- exact public query;
- query SHA-256.

Do not display cluster, archetype, task angle, products, URLs, or prior rubric fields.

## Run exactly two interview batches

Read `references/questionnaire.md` completely before interviewing.

### Batch 1: unaided extraction

Ask all Batch 1 questions together. Do not show candidate atoms or suggested answers. Tell the user they may answer briefly in natural language and number their answers.

After the response, preserve it verbatim as `initial_response`. Extract `initial_requirements`, but do not finalize.

### Batch 2: challenge and decision

Build a compact candidate table from the user's own Batch 1 response and the public query. For each candidate include:

- candidate ID;
- plain-language requirement;
- exact query phrase that motivates it;
- risk flag: `duplicate`, `over-split`, `under-specified`, `source-role-overreach`, or `none`;
- decision choices: `keep`, `merge`, `optional`, `delete`, `edit`.

Ask all decisions in one batch. Add deletion, overlap, missing-final-output, and source-role challenges from the question bank. Never ask one candidate per turn.

The user must decide every unresolved candidate. If a decision is missing, mark it `unresolved`; do not silently choose.

## Apply requirement rules

Use the deletion test:

> If a report completely omits this item, can it still fully answer the query?

Keep an item required only when the answer is no and its basis can be pointed to in the query.

Require each final item to be independently observable. Merge paraphrases and items that cannot independently pass or fail. Do not create requirements for:

- writing quality, depth, usefulness, or persuasiveness;
- a fixed number of citations, pages, searches, words, products, or sources;
- a specific answer, product, URL, or conclusion not fixed by the query;
- evidence availability or facts learned from hidden evaluator material.

Set an intrinsic source role only when the query itself makes that evidence role non-substitutable:

- `shopping`: concrete product identity, price, specification, or available candidate;
- `forums`: owner/community/target-user experience explicitly requested;
- `wiki`: general mechanism, definition, or history explicitly requested and not substitutable by the other roles.

Do not force three-source symmetry.

## Produce the annotation

Return YAML with this shape:

```yaml
packet_version: route_a_interview_v1
questionnaire_version: route_a_qbank_v1
annotation_mode: human_interviewed
annotator_id: A
task_id: dr_cross_deep_0001
query_sha256: "..."
initial_response: |-
  ...
initial_requirements:
  - "..."
requirements:
  - local_id: R1
    requirement: "..."
    necessity_reason: "..."
    query_basis: "exact phrase or concise locator"
    output_form: compare
    intrinsic_source_roles: []
    source_role_reason: none
optional_items: []
ambiguities: []
unresolved: []
evidence_answerability: not_assessed
```

Before emitting, check:

- every final requirement has a query basis and necessity reason;
- no two requirements duplicate the same obligation;
- recommendation/decision output is present when explicitly requested;
- constraints are attached to a comparison/decision rather than atomized without reason;
- source roles are intrinsic, not scorer-shaped;
- initial and final requirements are both retained for anchoring analysis.

If the user explicitly asks to save the output, write only to their assigned annotator artifact. Never inspect or modify the other annotator's artifact.

## Adjudication mode

Enter adjudication only after both locked annotations are provided. Do not use hidden evidence. Align requirements as `equivalent`, `partial_overlap`, `A_only`, or `B_only`; show all disagreements together; require a human adjudication decision; preserve both originals. Do not call an AI-only resolution human adjudication.
