You are an independent adversarial methodology reviewer for DRA's current
four-axis scoring pilot. Work read-only: do not edit, create, delete, or
reformat any repository file. Inspect the actual code and artifacts rather
than trusting this prompt's interpretation.

The authors want a highly automated, reproducible scorer for deep-research
reports in a frozen sandbox. They want to preserve a simple headline score
where possible, avoid expensive hand-written per-task rubrics, verify product
facts and observed evidence, and treat writing Elo separately.

Current formula:

    Quality = (Fact + Evidence + Completeness + Rubric) / 4
    Truth = Provenance * Quality

Inspect at minimum:

- src/scoring/four_axis_score.py
- src/scoring/four_axis_pipeline.py
- src/scoring/report_claim_pipeline.py
- src/scoring/task_manifest_compiler.py
- src/scoring/legacy_report_adapter.py
- docs/DRA_THREE_AXIS_SCORING_REDESIGN_2026-07-22.md
- data/results/four_axis_pilot/dr-tulu-dra-v3-dev-audio-0002-v8/
- data/results/four_axis_pilot/gpt-researcher-deepseek-v4-pro-audio-0002-v1/
- data/results/four_axis_pilot/langchain-odr-deepseek-v4-pro-zh-audio-0002-v2/
- data/results/four_axis_pilot/langchain-odr-deepseek-v4-pro-en-audio-0002-v2/
- the reports and input paths recorded in each input-manifest.json

Observed scores for the same task:

| report | Truth | P | Fact | Evidence | Completeness | Rubric |
|---|---:|---:|---:|---:|---:|---:|
| DR Tulu | .8052 | 1 | .9881 | .6920 | .6607 | .88 |
| LangChain ODR Chinese | .6526 | 1 | .9859 | .1926 | .5119 | .92 |
| GPT Researcher English | .5595 | 1 | 1.0 | 0 | .2381 | 1.0 |
| LangChain ODR English | 0 | 0 | .9130 | 0 | .3571 | .92 |

For DR Tulu, Fact resolves 84/171 material claims: 83 true, 1 false,
47 unresolved, 35 out_of_world, 5 instrument_ambiguous. Explain why the
resolution rate is only 49.1%, and attribute the loss among:

1. report expansion beyond the task world;
2. task evidence census / corpus gaps;
3. retrieval packet failures;
4. judge/instrument failures;
5. claim extraction or schema errors.

Do an independent audit of every subscore. Specifically investigate:

1. Provenance: what it really measures; whether external/unregistered and
   fabricated are wrongly conflated; whether its denominator is gameable.
2. Fact: whether true/false decisions look defensible; whether excluding
   unresolved/out_of_world creates misleading saturation; whether Fact must
   always be paired with resolution rate; whether claim verbosity can game it.
3. Evidence: distinguish visible cite occurrences, unique citation IDs/URLs,
   claim-citation bindings, and claim-level grounding. Determine whether the
   current "recall" denominator is fixed across reports. Test for false
   positives/negatives, especially absence claims inferred from snippets or a
   handful of irrelevant search results.
4. Execution reconstruction: verify whether the legacy LangChain `/search`
   observations are snippets or full pages. Determine whether
   legacy_report_adapter.py and reconstruct_native_observations misclassify
   them and whether this can materially change Evidence, not just diagnostics.
5. Completeness: inspect the 23 units, the 14 macro groups, content-only versus
   evidence-gated coverage, and whether Evidence failures are counted twice.
6. Rubric: inspect the 25 items, their provenance, equal weighting, overlap
   with Fact/Completeness, evidence/trace blindness, route binding, and
   saturation. Check whether items marked "directly explicit in query" contain
   answer-key details that are not actually in the query.
7. Judge reliability and cost: locate concrete semantic judge errors and
   estimate whether the number of calls per report is scalable.

We have provisionally observed:

- The DR Tulu report has 70 visible cite tags, 12 unique citation IDs, 8
  unique URLs, 167 claim-citation bindings, and 117 passing bindings.
- A DR Tulu snippet was accepted as evidence that a complete page lacked
  Hi-Res wording, which may be invalid negative evidence.
- A source title saying "Outdoor Speakers ... for Home" was rejected as not
  supporting outdoor/home use, which may be a false negative.
- Some Chinese-report claims about "no same-model result found" passed merely
  because cited hits were irrelevant, which may not establish bounded absence.
- The legacy LangChain ledger events have metadata endpoint="/search" and
  roughly 125-character content blobs, yet the adapter projects them as
  full_page because it puts the blob in document.text.
- Rubric scores are .88-1.0 and Fact scores .913-1.0 across all four reports.
- GPT Researcher gets Fact=1 and Rubric=1 with Evidence=0.

Challenge these observations; do not simply agree.

Return a rigorous Chinese review with four clearly separated sections:

A. Verified code/adapter bugs that require rerun.
B. Scoring-definition problems, ranked blocker/high/medium/low.
C. Claims from our provisional audit that you reject or qualify, with evidence.
D. Minimal revised design that preserves automation and the frozen-sandbox
   advantage. Do not propose a wholesale replacement unless necessary.

For each conclusion, cite concrete local file paths plus relevant IDs, stages,
or fields. State which of the four reported scores remain interpretable and
which must be withdrawn or marked diagnostic-only.
