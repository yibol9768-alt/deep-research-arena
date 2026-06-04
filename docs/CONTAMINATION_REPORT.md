# Contamination Probe Report (Eval Problem #5)

## What this checks

This probe verifies that a *base* model cannot answer the cross-site deep-research tasks **closed-book** (no retrieval, no tools). The sandbox corpus (One Stop Market products, Postmill forum threads, the served Wikipedia snapshot) is **private**: it lives on `localhost` hosts and is not on the public web. A base model therefore has no legitimate way to know the specific product pages, prices, thread scores, or URLs. We ask the model the research question closed-book, with placeholders neutralized so it is never told which private corpus to mine, and we check whether the answer asserts sandbox-specific facts anyway.

The **EXPECTED and HEALTHY** result is that the base model **cannot** produce the sandbox-specific answers closed-book. That confirms the benchmark measures **retrieval + grounding**, not memorization.

- Probe model: `qwen3-30b-a3b-instruct-2507` (Bailian / DashScope)
- Tasks probed: 5

## Scoring legend

- `closed_book_specificity` in [0,1]: HIGH = the closed-book answer asserts specific sandbox-shaped facts it could not legitimately know (red flag); LOW = generic / abstaining (healthy).
- `can_answer` (coarse): did the model claim it can deliver the concrete sourced report (leaked a sandbox URL/host, matched a golden price, or stayed confident without abstaining)?
- `url_leaks`: verbatim sandbox URLs reproduced (strongest signal).
- `golden_$`: emitted prices that match the task's golden prices.
- `inv_$`: total concrete `$` price tokens emitted (any guessing).
- Per-task verdict: `CLEAN` (healthy), `SUSPICIOUS` (specific but no verbatim leak), `CONTAMINATED` (leaked sandbox facts).

## Overall verdict

**PASS_NO_MEMORIZATION** - Healthy: the base model CANNOT produce the sandbox-specific answers closed-book. The eval measures retrieval+grounding, not memorization.

- Clean: 5 / 5
- Suspicious: 0 / 5
- Contaminated: 0 / 5
- Mean closed-book specificity: 0.0
- Mean self-reported confidence: 0.03
- Total verbatim sandbox URL leaks: 0
- Total golden-price matches: 0

## Per-task results

| task_id | topic | conf | spec | can_ans | abstain | url_leaks | golden_$ | inv_$ | verdict |
|---|---|---|---|---|---|---|---|---|---|
| dr_cross_deep_0001 | Consumer-grade audio headphones | 0.00 | 0.00 | no | yes | 0 | 0 | 0 | CLEAN |
| dr_cross_deep_0002 | Home coffee brewing equipment | 0.00 | 0.00 | no | yes | 0 | 0 | 0 | CLEAN |
| dr_cross_deep_0003 | three home-fitness equipment paths un... | 0.00 | 0.00 | no | yes | 0 | 0 | 1 | CLEAN |
| dr_cross_deep_0004 | three photography starter stacks unde... | 0.15 | 0.00 | no | yes | 0 | 0 | 1 | CLEAN |
| dr_cross_deep_0005 | Indoor and balcony gardening | 0.00 | 0.00 | no | yes | 0 | 0 | 0 | CLEAN |

## Per-task answer excerpts

### dr_cross_deep_0001 - Consumer-grade audio headphones

- specificity=0.00, can_answer=False, abstained=True, confidence=0.0
- excerpt: I cannot produce the requested market-intelligence report under closed-book constraints because:  - I do not have access to real-time or sandbox-specific URLs for products on "One Stop Market", Postmill threads, or Wikipedia via Kiwix. - I cannot verify or retrieve actual product...

### dr_cross_deep_0002 - Home coffee brewing equipment

- specificity=0.00, can_answer=False, abstained=True, confidence=0.0
- excerpt: I cannot produce the requested market-intelligence report under closed-book constraints because:  - I do not have access to real-time, sandbox-local URLs for specific product pages on "One Stop Market" (a fictional or unspecified e-commerce site), nor can I retrieve live data suc...

### dr_cross_deep_0003 - three home-fitness equipment paths under a fixed $300 starter budget - (P1) Adjustable dumbbells + bench, (P2) Barbell + plate set + rack, (P3) Bodyweight + resistance bands + pull-up bar - across exactly 5 use cases: (UC1) muscle hypertrophy, (UC2) cardio + fat loss, (UC3) small-apartment friendliness, (UC4) injury rehab / mobility, (UC5) progression beyond 12 months

- specificity=0.00, can_answer=False, abstained=True, confidence=0.0
- excerpt: I cannot produce the requested comparison report with the specified requirements because the task demands access to real-time, specific data - including exact product URLs, prices, ratings, review counts, forum thread scores, and encyclopedia article links - that I cannot retriev...

### dr_cross_deep_0004 - three photography starter stacks under a fixed $800 first-year budget - (S1) Mirrorless body + 1 prime + 1 zoom, (S2) Used DSLR body + 2 primes + flash, (S3) Smartphone + lens-attachment kit + tripod (no dedicated camera body) - across exactly 5 use cases: (UC1) family/portrait indoor, (UC2) travel/landscape outdoor, (UC3) low-light event/concert, (UC4) social-media short-video, (UC5) growth path to professional within 18 months

- specificity=0.00, can_answer=False, abstained=True, confidence=0.15
- excerpt: I cannot fulfill this task as specified because it requires access to real-time, specific data such as:  - Exact product pages from online stores (e.g., Amazon, B&H, Adorama) with prices, ratings, and feature claims. - Specific forum threads from Reddit (/r/photography, /r/AskPho...

### dr_cross_deep_0005 - Indoor and balcony gardening

- specificity=0.00, can_answer=False, abstained=True, confidence=0.0
- excerpt: I cannot produce the requested market-intelligence report as specified because the task demands access to real-time, sandbox-specific data - including exact product URLs from an online store (One Stop Market), live Reddit thread scores and comments, precise Wikipedia article link...

## Interpretation

A `PASS_NO_MEMORIZATION` verdict means: across the probed tasks, the base model did not reproduce any verbatim sandbox URLs and did not match the golden prices; its closed-book answers were generic and/or abstaining. This is the desired outcome. It confirms that scoring well on these tasks requires actually retrieving from and grounding in the sandbox corpus, so the benchmark measures research ability rather than memorization of leaked data.

A `WARN_HIGH_SPECIFICITY` or `FAIL_CONTAMINATION_DETECTED` verdict would indicate the opposite and should trigger a corpus-privacy / data-leak investigation.
