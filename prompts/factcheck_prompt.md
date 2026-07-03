# Fact-check prompts (axis-2 prose support + axis-3 semantic coverage)

> METHODOLOGY_REDESIGN_2026-07-03.md §5c. Structured facts (price, rating,
> thread score) are decided without a model by matching against the DB. These
> prompts handle only the residual: prose/encyclopedic claims whose support is
> semantic. They mirror the CNV framework (arXiv 2605.06635) but run against
> the frozen page cache at temperature 0, so every verdict replays exactly.
> Backed by a local model; ~100 judgments are calibrated against human labels.

## Relevant-content check (binary)

System:
> You decide whether a cited web page is on the same topic as a claim from a
> research report. Answer with one word: YES if the page is about the subject
> of the claim, NO if it is unrelated.

User:
> CLAIM:
> {CLAIM}
>
> CITED PAGE (excerpt):
> {PAGE_TEXT}
>
> Is the page topically relevant to the claim? Answer YES or NO.

## Fact-check (four-way, only SUPPORTED counts as grounded)

System:
> You fact-check one claim from a research report against the page it cites.
> Look at the specific facts, numbers, dates, names, and assertions in the
> claim. Answer with exactly one word:
> - SUPPORTED — the page states or clearly implies the claim,
> - CONTRADICTED — the page says something incompatible with the claim,
> - ABSENT — the page does not contain the claimed information,
> - UNCERTAIN — the page is relevant but you cannot tell.

User:
> CLAIM:
> {CLAIM}
>
> CITED PAGE (excerpt):
> {PAGE_TEXT}
>
> Does the page support the claim? Answer SUPPORTED, CONTRADICTED, ABSENT, or
> UNCERTAIN.

## Semantic coverage check (axis 3, for prose vital facts)

System:
> You decide whether a research report conveys a specific fact, in its own
> words or verbatim. Answer YES if the report communicates the fact, NO if it
> is missing or materially altered.

User:
> FACT THE REPORT SHOULD CONVEY:
> {FACT}
>
> REPORT (excerpt around the most relevant passage):
> {REPORT_EXCERPT}
>
> Does the report convey this fact? Answer YES or NO.
