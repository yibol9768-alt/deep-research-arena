# Task redesign, worked example: the sleep-aid debunking task

> The task the user flagged as over-specified (dr_cross_deep_0011 / 0020, "audit
> 5 sleep-aid claims"). This shows the two-layer redesign
> (METHODOLOGY_REDESIGN_2026-07-03.md §3) on a concrete case: the question
> becomes what a person would actually ask; every quota moves to the DB answer
> key and the decidable checklist. Nothing that mattered is lost — it moves to
> where it can be *checked* instead of *demanded*.

## Before (current, over-specified — the scraping spec as a question)

> Produce a Debunking / Fact-Check report auditing 5 popular sleep-aid claims:
> (CL1) '10 mg melatonin is more effective than 0.3 mg'... Each receives a
> verdict in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED}.
> **Ground in >= 120 sandbox URLs (>= 60 cited). (A) >= 36 sleep-aid products
> ... (B) >= 30 threads from /f/sleep, /f/insomnia ... (C) >= 25 articles,
> mandatory: Melatonin, Sleep, Polysomnography ... plus >= 15 more.** Output a
> 5-claim verdict table ... at least 5 contradiction findings ... <= 8 bullets.

Problems: no user talks like this; the quotas (>=120 URLs, >=36 products, >=25
articles) are procedure, not intent; and — as the audit showed — the pairwise
judge that sets the headline never even sees them.

## After (redesigned — the user-facing question)

> I've had trouble sleeping for a while and I keep running into all these
> "fixes" online, but I honestly can't tell what works and what's just being
> sold to me. The ones I see everywhere: taking a big dose of melatonin (like
> 10mg) instead of a tiny one, whether those wrist trackers actually measure
> your sleep stages, blue-light-blocking glasses, magnesium for insomnia, and
> weighted blankets. Which of these actually hold up? I want the real story —
> what's being sold, what people who've tried them say, and what the science
> actually shows. And for melatonin and magnesium, if there's real evidence
> about how much to take, tell me what the numbers say.

### Output contract (soft, shown to the agent)

> Give me a straight verdict on each claim up front, and end with the free
> stuff that actually helps you sleep.

That's it. No URL counts, no per-forum quotas, no mandated article list. It
reads like the person who actually has the problem, because that is who asks.

## The answer key (hidden, DB-computed — where the quotas went)

Built by `scripts/build_answer_keys.py` from the DB golden; scored by the
decidable axes. Schema (src/eval/answer_key.py):

- **relevant_set** — every sleep-aid product / thread / article the DB contains,
  with DB-true facts (price, rating, thread score). This is the completeness
  denominator. The old "`>= 36 products`" becomes: *recall against the actual
  set of relevant products*, whatever its true size — not a magic 36.
- **vital_nuggets** — the facts a good report should convey (a reviewed
  product's price+rating, a high-signal thread's score). Coverage recall (axis 3)
  is measured over these. The old "`>= 25 mandatory articles`" becomes: *did the
  report convey the vital encyclopedic facts?*
- **decidable_verdicts** — for each of the 5 claims, the verdict the closed
  world supports where it can decide (e.g. the melatonin dose-response is in the
  Melatonin article; blue-light efficacy may be UNDETERMINED in-corpus). The
  report's verdict is checked against this (axis 2), instead of trusting a judge.
- **gold_contradictions** — the real product-claim-vs-encyclopedia conflicts the
  DB contains (a marketing claim a wiki article refutes). The old "`>= 5
  contradiction findings`" becomes: *recall over the contradictions that are
  actually there* — you cannot pad it with plausible-sounding fabrications.
- **spec_requirements** (axis 4, decidable parse) — extracted automatically by
  `src/eval/spec_extract.py`:
  - `verdict_table` present,
  - `verdict_values` in {SUPPORTED, PARTIALLY_SUPPORTED, DEBUNKED, UNDETERMINED},
  - `bullet_cap` <= 8 on the closing list.
  These are the only quotas that survive, and they live here, not in the
  question, and they are checked, not asked.

## What each old requirement became

| Old (in the question) | New (where it lives, how it's judged) |
|---|---|
| `>= 120 URLs / >= 60 cited` | dropped as a quota; grounding = reachability + proof-of-fetch (axis 1) |
| `>= 36 sleep-aid products` | completeness recall over the DB relevant product set (axis 3) |
| `>= 30 forum threads` | completeness recall over relevant threads (axis 3) |
| `>= 25 mandatory articles` | coverage of vital encyclopedic nuggets (axis 3) |
| `>= 5 contradiction findings` | recall over DB-precomputed gold contradictions (axis 3) |
| verdict schema | decidable_verdicts (axis 2) + verdict_values spec (axis 4) |
| `<= 8 bullets` | bullet_cap spec (axis 4, parsed) |
| "no chain-of-thought", "markdown links" | agent-prompt style guidance, not scored quotas |

Net effect: the question reads like a person, the requirements became decidable
checks against the frozen database, and the headline finally depends on them.
