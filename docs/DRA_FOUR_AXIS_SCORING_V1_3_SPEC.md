# DRA Four-Axis Scoring v1.3

Status: implementation candidate. Formal leaderboard publication remains
fail-closed until the Task Evidence Census, retrieval, fixed-Qwen calibration,
and snapshot-attestation certificates are complete.

## 1. Axis boundaries

Each axis answers one question.

| Axis | Question | Denominator |
|---|---|---|
| Provenance | Are cited URLs canonical, registered, and backed by attested snapshots? | Unique canonical cited URLs |
| Fact | Are the report's deduplicated material atomic claims correct in the frozen world? | Successfully adjudicated in-world material claims |
| Evidence | Does each citation bind observed text that supports the local claim at an admissible source role? | Claim-citation bindings and citation-required units |
| Completeness | Which frozen discoverable content units are addressed by the report? | Applicable TEC atomic and higher-order content units |
| Rubric | Did the report perform the user's requested and report-blind necessary research actions? | Frozen explicit and latent rubric items |

Writing Elo is pairwise presentation evaluation and never enters Truth.

## 2. Claim pipeline

The report claim instrument is source-preserving and blind to TEC labels and
evidence pages:

1. Segment the report and preserve exact offsets.
2. Propose material claims at high recall.
3. Run the frozen Qwen judge with the NLI entailment and qualifier prompt.
4. Run the same frozen Qwen snapshot with the structural and qualifier prompt.
5. Run residual claim extraction at clause level.
6. Deduplicate by subject, predicate, object, qualifiers, polarity, modality,
   and attribution.
7. Map accepted claims to frozen TEC units for materiality and gap analysis.

Headings, citation identifiers, report self-description, preferences, and
recommendations are not external atomic facts.

## 3. Fact

Allowed verdicts are:

`true`, `false`, `conflicted`, `unresolved`, `out_of_world`,
`retrieval_failure`, `census_gap`, `world_scope_gap`, `exempt`, and
`instrument_ambiguous`.

Hard invariants:

- `true` requires at least one allowed support span.
- `false` requires at least one allowed same-scope contradiction span and the
  false guard, appeal, and final NLI checks.
- `conflicted` requires non-empty support and contradiction spans under
  matching scope.
- Missing stages or malformed span references become
  `instrument_ambiguous`.
- Non-mention is never proof of a negative claim.

Let `m(c)` be frozen materiality mass:

$$
\mathrm{Fact}
=
\frac{\sum_{c:\,v(c)=true}m(c)}
{\sum_{c:\,v(c)\in\{true,false,conflicted\}}m(c)}.
$$

Conflicted categorical claims receive no truth credit but remain in the
denominator. Out-of-world and exempt claims are neutral.

Fact confidence is reported separately:

$$
\mathrm{AdjudicationCoverage}
=
\frac{\sum_{c:\,v(c)\in\{true,false,conflicted\}}m(c)}
{\sum_{c:\,v(c)\notin\{out\_of\_world,exempt\}}m(c)}.
$$

No fixed eligibility threshold is specified in v1.3. Thresholds require
development-set calibration against human adjudication.

## 4. Value-blind Fact retrieval

The first-stage ranking query may contain subject, predicate, attribution, and
non-value entity/model qualifiers. It must not contain the report's asserted
object, number, unit, polarity, or comparison result.

Formal retrieval is the union of:

- BM25 lexical retrieval;
- dense exact or audited ANN retrieval;
- structured field lookup;
- entity and relation graph expansion;
- support, refute, and product/model variant routes;
- source-role quotas.

Structured values are compared after retrieval and never receive first-stage
ranking bonuses for matching the report.

The transition lexical retriever is diagnostic only. It cannot issue a formal
out-of-world or census certificate.

## 5. Gap states

The following states are distinct:

| State | Meaning | Formal handling |
|---|---|---|
| out_of_world | The claim is outside the certified frozen task world | Neutral |
| retrieval_failure | TEC evidence exists but runtime retrieval missed it | Withhold |
| census_gap | Frozen-world evidence exists but the TEC omitted the unit | Withhold task version |
| world_scope_gap | The frozen world lacks material task evidence | Withhold task version |
| instrument_ambiguous | Extraction or judging cannot be trusted | Review or calibrated withholding |

A gap certificate records world snapshot ID, query logs, retrieved span IDs,
exact-vs-ANN probes, missing-span forensics, and TEC version.

## 6. Evidence

A binding passes when:

`Observed AND Bound AND Supports AND ScopeMatches AND RoleOK`.

URL registry validity belongs to Provenance. It is not counted as a second
Evidence predicate, although an invalid URL normally cannot produce a valid
native observation.

$$
P_E=\frac{\#PassingBindings}{\#AllBindings}
$$

$$
R_E=\frac{\#GroundedCitationRequiredUnits}
{\#CitationRequiredUnits}
$$

$$
\mathrm{Evidence}=\frac{2P_ER_E}{P_E+R_E}.
$$

Missing citations reduce recall. Extra irrelevant, contradictory, or
mis-scoped citations reduce precision.

## 7. Completeness

Completeness is pure semantic content coverage. It does not reapply Fact or
Evidence gates. A separate `grounded_covered` diagnostic records the
cross-axis conjunction.

Atomic units are slots such as an entity-property-condition combination.
Higher-order units include comparison, mechanism, conflict, synthesis,
community pattern, procedure, and decision structure.

For each non-empty `(facet, unit_type)` group:

$$
C_{f,g}=
\frac{\#ContentCoveredUnits_{f,g}}
{\#ApplicableUnits_{f,g}}.
$$

The primary score is the macro average:

$$
\mathrm{Completeness}
=
\frac{1}{|K|}\sum_{(f,g)\in K}C_{f,g}.
$$

Alternative evidence routes are accepted. TEC witness URLs are not an
allowlist.

## 8. Rubric

Explicit rubrics are user instructions. Latent rubrics are report-blind,
answer-independent necessary research actions. Latent items require blinded
double-human review and arbitration before formal use.

Rubric values are:

- fulfilled: 1.0;
- partially fulfilled: 0.5;
- not fulfilled: 0.0;
- ambiguous: 0.0 plus review status.

Positive verdicts require at least one exact quote from the report. Partial
credit is allowed only for a naturally divisible requirement.

$$
\mathrm{Rubric}
=
\frac{\sum_rw_rv_r}{\sum_rw_r}.
$$

Rubric and Completeness are disjoint. A source requirement is assigned to one
axis. Mixed requirements must be split before freezing. The TEC manifest
contains an axis-disjointness certificate over source check IDs.

## 9. Provenance

For each unique canonical cited URL:

`ValidURL = Canonicalized AND InRegistry AND SnapshotAttested`.

Snapshot attestation requires a readable blob, a matching hash, a world
snapshot ID, and a registry-manifest build attestation.

$$
\mathrm{Provenance}
=
\frac{\#ValidUniqueURLs}{\#CitedUniqueURLs}.
$$

Provenance does not judge semantic support.

## 10. Aggregation and publication

Always publish the axis vector and a linear diagnostic:

$$
\mathrm{Truth}_{linear}
=
\mathrm{Provenance}
\cdot
\frac{Fact+Evidence+Completeness+Rubric}{4}.
$$

Publish a geometric formal candidate:

$$
\mathrm{Truth}_{geometric}
=
\mathrm{Provenance}
\cdot
(Fact\cdot Evidence\cdot Completeness\cdot Rubric)^{1/4}.
$$

The geometric candidate prevents a zero Evidence axis from being compensated
by unrelated axes. It remains a candidate until development-set human ranking
calibration selects the formal aggregation rule.

Report-side failures receive low scores. Scorer-side failures cause
withholding. Formal publication requires:

- a protocol-complete TEC certificate;
- no retrieval, census, or world-scope gap;
- one frozen Qwen judge snapshot plus an axis-level human calibration
  certificate;
- frozen, disjoint, reviewed rubrics;
- attributable native observations;
- snapshot and registry build attestations;
- no unresolved hard-invariant violation.

When any scorer-side condition fails, `formal_truth` is null while diagnostic
scores remain available.

### 10.1 Official judge lock

All semantic evaluation stages use one frozen `Qwen3-8B` judge snapshot:
Task Evaluation Contract compilation, claim proposal/NLI/structural filtering,
Fact, Evidence, Completeness, and Rubric. Qwen never generates or rewrites the
evaluated harness report.

Changing prompts does not create an independent judge, so every prompt and
model artifact is hashed. A task contract is compiled once and frozen per
task; a Claim Ledger and Fact packet bundle are frozen per report before the
scoring replay. Other models may be used only in calibration experiments and
must never be mixed into official axis scores.

The validity certificate is human agreement against the fixed Qwen snapshot,
reported per axis with sample size, confusion matrix, agreement coefficient,
and bootstrap confidence interval. Requiring different models for different
stages is not an eligibility condition: it would change the ruler across axes
without establishing that any model is more correct.

## 11. Minimum regression suite

The implementation must test:

- true Fact requires support spans;
- false Fact requires contradiction spans;
- conflicted Fact requires both span roles;
- one true plus many unresolved claims exposes low adjudication coverage;
- out-of-world claims are Fact-neutral;
- conflicted claims cannot shrink the Fact denominator;
- report values do not enter Fact retrieval ranking;
- support and refute variants survive retrieval;
- zero Evidence produces zero geometric Truth candidate;
- Completeness is content coverage, with grounded coverage reported separately;
- positive Rubric verdicts require exact quotes;
- Rubric and Completeness source IDs are disjoint;
- unobserved bindings fail Evidence;
- registry membership without snapshot attestation is not formally eligible;
- census, retrieval, and world-scope gaps withhold formal publication.
