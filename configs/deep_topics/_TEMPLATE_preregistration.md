# Task Pre-Registration — `dr_cross_deep_<NNNN>`

*This document is filled out BEFORE any scraping or scoring. Saved as
`configs/deep_topics/<id>_<topic>.preregistration.md`. Once committed,
no field below may be changed without a separate `<id>_amendment.md`
file documenting the change and its reason.*

---

## 1. Identifiers

- **task_id**: `dr_cross_deep_____`
- **topic_id**: `_______________`
- **author**: `_______________`
- **author qualifications** (per DRBench §1.1 expert authoring): `___________`
- **created**: `YYYY-MM-DD`
- **planned freeze date**: `YYYY-MM-DD` (golden + checklist locked)

---

## 2. Intent type (pick exactly one — §7.2 of RESEARCH_TASK_DESIGN)

- [ ] Comparison         — compare X and Y on dimensions Z
- [ ] Enumeration / catalog — list every Z that has property W
- [ ] Timeline / evolution — how has X changed over time?
- [ ] Causal explanation  — why did X happen?
- [ ] Debunking / fact-check — which of these claims about X are false?
- [ ] Recommendation       — given constraints C, what should I do?

---

## 3. Synthesis style (pick at least one — §7.3)

- [ ] Ranking
- [ ] Taxonomy / clustering
- [ ] Contradiction finding
- [ ] Gap analysis
- [ ] Causal inference

---

## 4. Difficulty tier

- [ ] Easy   — 100 cited URLs, 2 dimensions, 5 synthesis findings, ~2h human
- [ ] Medium — 120+ URLs, 3 dimensions, 5–8 synthesis findings, ~4h human
- [ ] Hard   — 200+ URLs, 3 dimensions, ≥10 synthesis findings, ~8h human

For v1 release, ALL tasks should be Medium per §5 (eliminate difficulty as a confounder).

---

## 5. Mandatory dimensional targets

| Dimension | Source | Min must-cite | Notes |
|---|---|---|---|
| Product landscape | Magento :7770 | ___ | brands ≥ ___, price tiers ≥ ___ |
| Community sentiment | Postmill :9999 | ___ | sub-forums ≥ ___ |
| Technical grounding | Kiwix :8090 | ___ | mandatory articles list below |

### Mandatory wiki articles (named ahead of time, must all be cited)

- `_______________` — concept the report MUST define
- `_______________`
- `_______________`
- ...

---

## 6. Synthesis requirements (specific count + format)

- **Contradiction findings**: exactly ___ cross-source contradictions, each documented as `(product_url, wiki_url, explicit_contradiction_text)`.
- **Brand-sentiment ranking**: ranking of ≥ ___ brands, each with ≥ 2 reddit threads as evidence.
- **Rating-vs-sentiment divergences**: at least ___ cases where shopping ratings disagree with reddit sentiment.
- **Final list**: TOP-___ items with full evidence chain (≥1 shopping + ≥2 reddit + ≥1 wiki per item).

---

## 7. Citation format

- All citations are markdown `[label](url)` AND
- A "References" section at end repeats them as `[N] [title](url)` — both forms must be present.
- Each cited URL MUST resolve on the sandbox (HTTP 200 in a curl probe).
- Author commits to provide `quoted_span` (≤200 chars verbatim from page) for every must-cite URL.

---

## 8. Adversarial Wiki entries (contamination defense — §9 item 9)

For at least 2 of the mandatory wiki articles, the Kiwix-served version
will differ from public Wikipedia on a load-bearing fact. Agents that
rely on training prior get the fact wrong; agents that retrieve win.

- Article 1: `__________` — modification: `__________`
- Article 2: `__________` — modification: `__________`

---

## 9. Anticipated checklist items (21 binary)

The 21 PASS/FAIL/UNCLEAR items the LLM-judge will evaluate.

1.
2.
...
21.

---

## 10. Disagreement adjudication

- Two annotators (author + reviewer) build must-cite lists independently.
- Cohen's κ is computed via `src/verifiers/iaa_score.py`.
- Required: κ ≥ 0.75 to publish. Below 0.65 → task pulled and redesigned.
- Disagreement resolution: jointly review the 50 highest-disagreement URLs;
  agree or revise the intent so the disagreement disappears.

---

## 11. Human ceiling

A third annotator (or the author after a 1-week cooldown) attempts the
task as if they were the agent: 4-hour budget, browser + sandbox, no
prior on the must-cite list. Their composite score is the published
human ceiling.

- Targeted human composite: ≥ 0.50
- If achieved < 0.50, task is too hard or under-specified — rewrite intent.

---

## 12. Sign-off

- Author: ___________ (date)
- Reviewer: ___________ (date)
- Human-baseline runner: ___________ (date)
- Approved for arena release: [ ] yes / [ ] no
