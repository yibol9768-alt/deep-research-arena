# DRA v3 Route-Flexible Rubric Migration

## Decision

The evidence graph used to construct a query is an **answerability witness**, not
the unique route an evaluated agent must reproduce. DRA will therefore score
query-derived research obligations through any admissible, observed, claim-supporting
route in the frozen environment.

Existing `evidence_graph_case_v1` files remain immutable baselines during the
migration. Route-flexible rubrics and scores run in shadow mode until validation
is complete.

## Why the current 57 cases need migration

The repository currently contains 57 case specs, numbered 0001 through 0057:

- 17 development cases;
- 2 promoted formal cases;
- 38 formal candidates.

The generated audit shows a suite-wide structural problem:

- all 690 evidence steps bind to exactly one witness `source_id`;
- none of the 1,054 proof steps is optional or conditionally applicable;
- every case's oracle declares every evidence-node ablation decision-breaking;
- 49 of 57 cases expose only one acceptable conclusion;
- only three of the intended five motifs occur in the current cases.

Adding more URLs to the existing `source_ids` lists would only create a larger
page whitelist. It would not remove reference-route overfitting.

## New semantic layers

Each route-flexible case separates five objects:

1. **Obligation** — a necessary research requirement derived from the public query.
2. **Proposition** — a semantic claim that may satisfy part of an obligation.
3. **Proof route** — one sufficient combination of grounded propositions.
4. **Witness** — an authoring-time page proving that a proposition is answerable.
5. **Decision contract** — constraints that a conclusion must satisfy, without
   fixing the conclusion name in advance.

Witness IDs and URLs are excluded from runtime answer acceptance. Runtime evidence
must instead pass URL validity, observed-page, local citation binding, semantic
support, and source-role checks.

## Obligation semantics

For obligation `j`, let `R_j` be its explicitly reviewed alternative routes and
let `g_jrp` indicate whether proposition `p` in route `r` is grounded:

\[
z_j = \max_{r \in R_j}\min_{p \in r} g_{jrp}.
\]

An obligation passes when any complete admissible route passes. Applicability
`a_j` is determined by an explicit condition, not inferred from the evaluated
report after scoring.

\[
PartialCompletion_t =
\frac{\sum_j w_j a_j z_j}{\sum_j w_j a_j}.
\]

\[
FullPass_t = \mathbf{1}\left[
\bigwedge_{j\in Critical}z_j=1
\land DecisionValid=1
\land CriticalError=0
\right].
\]

The old graph-route coverage remains a diagnostic only.

## Supported route types

Every route must declare one of the following forms:

- `positive_support`: observed evidence establishes the proposition;
- `bounded_non_inference`: observed inputs are insufficient and the report
  correctly refuses a stronger conclusion;
- `conditional_followup`: deeper research is required only when a triggering
  claim is present;
- `scoped_negative_search`: a frozen, recorded search found no matching evidence
  within a declared corpus scope;
- `alternative_mechanism`: different evidence establishes the same decision-relevant
  proposition.

An absence claim cannot pass merely because the report says "I found nothing."
It needs either complete inspection of an explicitly bounded source set or a
frozen negative-search certificate.

## Conclusion semantics

Product or answer names are not a whitelist. A conclusion passes when it:

- selects an allowed action class, including an explicitly permitted defer action;
- respects the public constraints and priority order;
- follows from grounded obligation results;
- explains the decisive tradeoff and remaining uncertainty;
- contains no critical contradiction or unsupported decisive claim.

Different conclusions may pass the same case when their stated conditions and
tradeoffs are supported.

## Migration procedure

### Phase 0 — preserve baseline

- Keep the current 57 case files and `proof_steps_v1` scorer unchanged.
- Generate the route-flexibility audit and review queue.
- Never silently replace historical scores.

### Phase 1 — implement shadow schema and scorer

- Add a versioned route-flexible evaluator view.
- Reuse the existing observation ledger and URL-integrity checks.
- Accept any observed page that semantically supports the proposition and meets
  the source-role contract.
- Add conditional applicability, OR-of-AND proof routes, negative-search
  certificates, and an open decision contract.

### Phase 2 — migrate the 17 development cases

For each task, reviewers see only the public query when drafting obligations.
They then receive the witness graph to check answerability and enumerate known
routes. Each obligation must pass a requirement-deletion test. Each route must
pass a sufficiency test. The witness URL is never copied into a runtime whitelist.

Development migration is complete only when each task passes:

1. source-substitution test;
2. route-substitution test;
3. conclusion-substitution test;
4. requirement-deletion test;
5. scoped-negative-search test where applicable;
6. adversarial unsupported-citation and contradiction tests.

### Phase 3 — calibrate and freeze

- Score deliberately constructed reports following different valid routes.
- Blindly compare automatic results with two human reviewers.
- Resolve disagreements and freeze schema, prompts, and judge versions.
- Do not tune on the formal candidate reports.

### Phase 4 — migrate formal cases

- Migrate the 2 promoted formal cases first as release-gate rehearsal.
- Migrate the 38 formal candidates by topic cluster and motif.
- Exclude cases whose obligations or decision contract cannot be made unambiguous.
- Freeze formal cases only after all substitution and adversarial tests pass.

### Phase 5 — shadow comparison and cutover

For at least one representative report set, publish both:

- legacy fixed-route Partial Completion / Full Pass;
- route-flexible Partial Completion / Full Pass;
- URL integrity and acquisition diagnostics;
- disagreement reasons such as `alternative_route_accepted`, `legacy_witness_miss`,
  `unsupported_alternative`, and `decision_contract_failure`.

Cut over only after route-flexible Full Pass has acceptable precision against the
blind human judgments and no systematic preference for witness-route reports.

## Generation rule for future cases

Future query generation may use a selected evidence subgraph, but compilation
must produce two separate artifacts:

- `answerability_witness_graph`: private, frozen authoring evidence;
- `query_obligation_rubric`: source-agnostic runtime scoring contract.

The compiler must not automatically mark every selected evidence node as required.
Criticality and conditionality require an explicit query-level review.

## Reproducible audit

Run:

```bash
python3 scripts/audit_route_flexibility_v3.py \
  --case-root data/golden/cases_v3 \
  --json-out data/pilot_v3/route_flexibility_audit_v1.json \
  --markdown-out data/pilot_v3/route_flexibility_audit_v1.md
```

The JSON includes a per-task evidence and derived-step review packet. It is a
migration input, not a frozen rubric.
