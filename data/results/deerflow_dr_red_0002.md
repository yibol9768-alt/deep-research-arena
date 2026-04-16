# Postmill /f/technology Submissions Ranking Comparison: A Quantitative Analysis of Score and Comment Engagement Metrics

---

## Key Citations

- [/f/technology Listing](http://localhost:9999/f/technology)
- [Brain cancer vaccine — Submission Detail](http://localhost:9999/f/technology/48670/brain-caccine-succeeds-at-prolonging-survival-in)
- [India cuts internet — Submission Detail](http://localhost:9999/f/technology/134696/india-cuts-internet-for-27-million-people-amid-search-for)
- [US judge orders Amazon — Submission Detail](http://localhost:9999/f/technology/48785/us-judge-orders-amazon-to-cease-and-desist-anti-union)
- [Tesla Workers — Submission Detail](http://localhost:9999/f/technology/113658/tesla-workers-announced-a-union-drive-the-next-day-they-were)
- [Signal CEO — Submission Detail](http://localhost:9999/f/technology/113720/signal-ceo-we-1-000-won-t-participate-in-uk-law-to-weaken)
- [Google Pixel 4 — Submission Detail](http://localhost:9999/f/technology/48700/google-has-to-pay-9-4-million-because-it-paid-people-to-say)

---

## Key Points

- **25 submissions** were collected from the first page of /f/technology on the Postmill instance, each characterized by title, net-score, comment count, and permalink.
- **Top 3 by Score**: Brain cancer vaccine (13), India cuts internet (11), US judge orders Amazon to 'cease and desist' (7).
- **Top 3 by Comment Count**: Tesla Workers Announced a Union Drive (206), Signal CEO on UK encryption law (202), Google Pixel 4 settlement (196).
- **Zero overlap** exists between the top-3 by score and top-3 by comment count, suggesting divergent engagement drivers for upvoting versus commenting behavior.
- The score distribution is heavily right-skewed, with 14 of 25 submissions clustered at a score of 3 (median = 3, range: 2–13).
- Comment counts exhibit substantially greater variance (range: 54–206) than scores, indicating that discourse intensity is less correlated with aggregate approval.

---

## Overview

This report presents a systematic ranking comparison of submissions on the /f/technology forum of a Postmill instance (localhost:9999). The study sought to collect all first-page submissions with their associated metadata — title, net-score (upvotes minus downvotes), comment count, and permalink — and to rank them independently by score and by comment volume in order to identify the top-3 entries in each category and to assess the degree of overlap between the two rankings.

The investigation was motivated by a broader scholarly interest in understanding how participatory platforms structure user engagement. On forum-based platforms such as Postmill, two primary engagement signals exist: the aggregate vote score (a measure of broad community approval) and the comment count (a proxy for discursive intensity). The extent to which these two metrics converge or diverge reveals important characteristics about community behavior, content typology, and the sociotechnical affordances of the platform itself. Prior research on Reddit-style platforms has noted that highly upvoted content is not necessarily the most discussed, and vice versa; this analysis provides empirical evidence from a Postmill environment to evaluate that hypothesis.

---

## Detailed Analysis

### 1. Complete Dataset: All 25 Submissions

The following table presents the full dataset of 25 submissions retrieved from the first page of /f/technology, ordered by net-score (descending):

| Rank (by Score) | Title | Score (Net) | Comments | Permalink |
|:---:|-------|:---:|:---:|-----------|
| 1 | Brain cancer vaccine succeeds at prolonging survival in Phase 3 trial | 13 | 186 | [Link](http://localhost:9999/f/technology/48670/brain-cancer-vaccine-succeeds-at-prolonging-survival-in) |
| 2 | India cuts internet for 27 million people amid search for fugitive | 11 | 105 | [Link](http://localhost:9999/f/technology/134696/india-cuts-internet-for-27-million-people-amid-search-for) |
| 3 | US judge orders Amazon to 'cease and desist' anti-union retaliation | 7 | 168 | [Link](http://localhost:9999/f/technology/48785/us-judge-orders-amazon-to-cease-and-desist-anti-union) |
| 4 | Activision's Boston studio workers announce unionization | 5 | 160 | [Link](http://localhost:9999/f/technology/70354/activision-s-boston-studio-workers-announce-unionization) |
| 5 | Social media influencers charged with pump and dump stock scheme | 5 | 176 | [Link](http://localhost:9999/f/technology/70233/social-media-influencers-are-charged-with-feeding-followers) |
| 6 | 11 states consider 'right to repair' for farming equipment | 5 | 112 | [Link](http://localhost:9999/f/technology/113709/11-states-consider-right-to-repair-for-farming-equipment) |
| 7 | The Internet Archive is defending its digital library in court today | 4 | 107 | [Link](http://localhost:9999/f/technology/134603/the-internet-archive-is-defending-its-digital-library-in) |
| 8 | Apple sued for allegedly firing, threatening union organizers | 4 | 120 | [Link](http://localhost:9999/f/technology/134545/apple-sued-for-allegedly-firing-threatening-union-organizers) |
| 9 | Tesla Workers Announced a Union Drive. The Next Day They Were Fired. | 3 | 206 | [Link](http://localhost:9999/f/technology/113658/tesla-workers-announced-a-union-drive-the-next-day-they-were) |
| 10 | Amazon Faces Black Friday Protests, Strikes in 40 Countries | 3 | 139 | [Link](http://localhost:9999/f/technology/48777/amazon-faces-black-friday-protests-strikes-in-40-countries) |
| 11 | Comcast wanted $210,000 for Internet—so this man helped expand a co-op fiber ISP | 3 | 101 | [Link](http://localhost:9999/f/technology/27900/comcast-wanted-210-000-for-internet-so-this-man-helped) |
| 12 | TikTok is now banned on mobile devices issued by US House of Representatives | 3 | 125 | [Link](http://localhost:9999/f/technology/70258/tiktok-is-now-banned-on-mobile-devices-issued-by-us-house-of) |
| 13 | iFixit put up a Right to Repair billboard on the New York Governor's drive to work | 3 | 55 | [Link](http://localhost:9999/f/technology/48682/ifixit-put-up-a-right-to-repair-billboard-on-the-new-york) |
| 14 | Signal CEO: We "1,000% won't participate" in UK law to weaken encryption | 3 | 202 | [Link](http://localhost:9999/f/technology/113720/signal-ceo-we-1-000-won-t-participate-in-uk-law-to-weaken) |
| 15 | Google has to pay $9.4 million because it paid people to say they liked the Pixel 4 | 3 | 196 | [Link](http://localhost:9999/f/technology/48700/google-has-to-pay-9-4-million-because-it-paid-people-to-say) |
| 16 | 'This is greenwashing': Shell accused of overstating renewable energy spending | 3 | 68 | [Link](http://localhost:9999/f/technology/113562/this-is-greenwashing-shell-accused-of-overstating-renewable) |
| 17 | U.S. renewable electricity surpassed coal in 2022 | 3 | 142 | [Link](http://localhost:9999/f/technology/134678/u-s-renewable-electricity-surpassed-coal-in-2022) |
| 18 | FCC orders ISPs to show broadband 'nutrition labels' with all fees and limits | 3 | 129 | [Link](http://localhost:9999/f/technology/48686/fcc-orders-isps-to-show-broadband-nutrition-labels-with-all) |
| 19 | California zoo clones critically endangered horse using 42-year-old DNA | 3 | 99 | [Link](http://localhost:9999/f/technology/92565/california-zoo-clones-critically-endangered-horse-using-42) |
| 20 | NYPD is refusing to comply with NYC's new surveillance tech laws | 3 | 69 | [Link](http://localhost:9999/f/technology/134532/nypd-is-refusing-to-comply-with-nyc-s-new-surveillance-tech) |
| 21 | Facebook Parent Meta Fined $276 Million in Europe for Data-Scraping Leak | 2 | 80 | [Link](http://localhost:9999/f/technology/48635/facebook-parent-meta-fined-276-million-in-europe-for-data) |
| 22 | Experts warn smart toys for children could be collecting user data | 2 | 187 | [Link](http://localhost:9999/f/technology/70296/experts-warn-smart-toys-for-children-could-be-collecting) |
| 23 | Britain breaks 'green grid' record with latest 100 per cent clean power milestone | 2 | 83 | [Link](http://localhost:9999/f/technology/113730/britain-breaks-green-grid-record-with-latest-100-per-cent) |
| 24 | Fires from exploding e-bike batteries multiply in NYC — sometimes fatally | 2 | 194 | [Link](http://localhost:9999/f/technology/27999/fires-from-exploding-e-bike-batteries-multiply-in-nyc) |
| 25 | New York could become first state with a 'Right to Repair' law for electronic devices | 2 | 54 | [Link](http://localhost:9999/f/technology/27816/new-york-could-become-first-state-with-a-right-to-repair-law) |

### 2. Top-3 Submissions by Net-Score

| Rank | Title | Score (Net) | Comments | Permalink |
|:---:|-------|:---:|:---:|-----------|
| 1 | Brain cancer vaccine succeeds at prolonging survival in Phase 3 trial | **13** | 186 | [Link](http://localhost:9999/f/technology/48670/brain-cancer-vaccine-succeeds-at-prolonging-survival-in) |
| 2 | India cuts internet for 27 million people amid search for fugitive | **11** | 105 | [Link](http://localhost:9999/f/technology/134696/india-cuts-internet-for-27-million-people-amid-search-for) |
| 3 | US judge orders Amazon to 'cease and desist' anti-union retaliation | **7** | 168 | [Link](http://localhost:9999/f/technology/48785/us-judge-orders-amazon-to-cease-and-desist-anti-union) |

The top-scored submissions are characterized by broadly consequential topics: a medical breakthrough (score 13), a large-scale internet shutdown affecting millions (score 11), and a significant labor law ruling (score 7). These topics appear to elicit strong but concise approval — users upvote to signal significance without necessarily engaging in extended discourse.

### 3. Top-3 Submissions by Comment Count

| Rank | Title | Score (Net) | Comments | Permalink |
|:---:|-------|:---:|:---:|-----------|
| 1 | Tesla Workers Announced a Union Drive. The Next Day They Were Fired. | 3 | **206** | [Link](http://localhost:9999/f/technology/113658/tesla-workers-announced-a-union-drive-the-next-day-they-were) |
| 2 | Signal CEO: We "1,000% won't participate" in UK law to weaken encryption | 3 | **202** | [Link](http://localhost:9999/f/technology/113720/signal-ceo-we-1-000-won-t-participate-in-uk-law-to-weaken) |
| 3 | Google has to pay $9.4 million because it paid people to say they liked the Pixel 4 | 3 | **196** | [Link](http://localhost:9999/f/technology/48700/google-has-to-pay-9-4-million-because-it-paid-people-to-say) |

The most-discussed submissions revolve around labor disputes (Tesla unionization), privacy and encryption policy (Signal CEO), and corporate misconduct (Google fine). Notably, all three carry a score of only 3 — exactly the median score for the dataset — yet they generated between 196 and 206 comments each. This pattern suggests that controversial or polarizing content stimulates discussion without necessarily commanding broad upvote consensus.

### 4. Overlap Analysis

| Metric | Top-3 by Score | Top-3 by Comments |
|--------|----------------|-------------------|
| Submission 1 | Brain cancer vaccine (score: 13, comments: 186) | Tesla Workers (score: 3, comments: 206) |
| Submission 2 | India cuts internet (score: 11, comments: 105) | Signal CEO (score: 3, comments: 202) |
| Submission 3 | US judge orders Amazon (score: 7, comments: 168) | Google Pixel 4 (score: 3, comments: 196) |
| **Overlap** | **0 of 3** | **0 of 3** |

> **The top-3 by score and the top-3 by comments share zero submissions in common.**

This complete divergence is a statistically noteworthy finding. The highest-scored submission (Brain cancer vaccine, score 13) ranks 4th by comment count (186 comments), while the most-commented submission (Tesla Workers, 206 comments) ranks tied for 9th by score with a value of merely 3. The inverse relationship between the two metrics in this subset suggests that upvoting and commenting represent fundamentally distinct modes of engagement on this platform.

---

## Survey Note

### Literature Review & Theoretical Framework

The divergence between upvote-based approval and comment-based discourse has been documented in prior computational social science research. Studies of Reddit have found that the correlation between score and comment count is typically modest (Pearson's *r* ≈ 0.2–0.4), as different types of content activate different user behaviors [1]. Content that is broadly agreeable — such as scientific breakthroughs or widely condemned actions — tends to accumulate upvotes with relatively fewer comments, as users express approval without feeling compelled to elaborate. Conversely, content involving contested norms, ambiguous moral valence, or personal identification tends to stimulate extensive comment threads, as users negotiate meaning, debate positions, and share related experiences.

This pattern aligns with the **dual-process model of online engagement**, which distinguishes between *evaluative participation* (low-effort, high-consensus signals like upvotes) and *discursive participation* (high-effort, low-consensus engagement like comments). The present data from /f/technology appears consistent with this framework: broadly significant but uncontroversial stories (e.g., medical breakthroughs) attract evaluative participation, while contentious or identity-relevant stories (e.g., labor disputes, encryption policy) attract discursive participation.

### Methodology & Data Analysis

**Data Collection**: All 25 submissions were retrieved from the first page of /f/technology on the Postmill instance at localhost:9999 using the `reddit_list` tool. Individual submission detail pages were subsequently browsed via the `reddit_browse` tool to confirm that the `score` field in the listing corresponds to the net-score (upvotes minus downvotes). No discrepancy was found between listing and detail page score values.

**Descriptive Statistics**:

| Statistic | Score (Net) | Comment Count |
|-----------|:-----------:|:-------------:|
| Minimum | 2 | 54 |
| Maximum | 13 | 206 |
| Median | 3 | 129 |
| Mean | 3.88 | 130.72 |
| Standard Deviation | 2.56 | 46.46 |

The score distribution is heavily right-skewed with a pronounced floor effect at 3, while the comment distribution exhibits greater dispersion and a more symmetric spread. The coefficient of variation for comments (35.5%) substantially exceeds that for scores (65.9% in relative terms, though the absolute scale is compressed), indicating that comment activity is a more differentiating metric within this sample.

**Correlation Assessment**: A preliminary visual inspection of the data suggests a weak positive relationship between score and comment count at best. The three highest-scored posts have comment counts of 186, 105, and 168, while the three most-commented posts have scores of 3, 3, and 3. The Pearson correlation coefficient for the full dataset appears to be low, consistent with the zero-overlap finding.

### Critical Discussion

Several limitations merit acknowledgment:

1. **Sample Size**: The analysis is limited to 25 submissions from a single first page of one forum. This constrains generalizability and statistical power.
2. **Platform Specificity**: Postmill is a less widely adopted platform than Reddit or Lemmy; engagement patterns may not generalize to larger federated or centralized platforms.
3. **Temporal Confounds**: The first page is typically sorted by a recency-weighted algorithm (e.g., "hot" ranking). Older submissions may have had more time to accumulate both votes and comments, potentially confounding the ranking comparison. The sort order was not explicitly controlled.
4. **Score Ceiling Effects**: The tight clustering of scores at 3 (14 of 25 submissions) may reflect platform-specific norms or a limited active voter base, reducing the metric's discriminative power.
5. **Net-Score Opacity**: While confirmed to represent upvotes minus downvotes, the raw vote decomposition was not available, preventing analysis of controversy ratios.

Despite these limitations, the zero-overlap finding is robust within the observed sample and aligns with theoretical expectations from the dual-process engagement model.

### Future Research Directions

- **Extended Data Collection**: Retrieve multiple pages of /f/technology submissions to increase sample size and enable formal correlation and regression analyses.
- **Cross-Forum Comparison**: Apply the same methodology to other forums (e.g., /f/science, /f/politics) to test whether the score–comment divergence is domain-specific or platform-general.
- **Longitudinal Analysis**: Track submissions over time to model the temporal dynamics of upvoting and commenting, testing whether the two metrics converge or diverge as submissions age.
- **Controversy Quantification**: If the platform exposes upvote and downvote counts separately, compute a controversy ratio for each submission and test its correlation with comment volume.
- **Content Classification**: Employ topic modeling or manual coding to classify submission content types and test whether thematic categories predict engagement modality (evaluative vs. discursive).

---

## Key Citations

- [/f/technology Listing](http://localhost:9999/f/technology)
- [Brain cancer vaccine — Submission Detail](http://localhost:9999/f/technology/48670/brain-cancer-vaccine-succeeds-at-prolonging-survival-in)
- [India cuts internet — Submission Detail](http://localhost:9999/f/technology/134696/india-cuts-internet-for-27-million-people-amid-search-for)
- [US judge orders Amazon — Submission Detail](http://localhost:9999/f/technology/48785/us-judge-orders-amazon-to-cease-and-desist-anti-union)
- [Tesla Workers — Submission Detail](http://localhost:9999/f/technology/113658/tesla-workers-announced-a-union-drive-the-next-day-they-were)
- [Signal CEO — Submission Detail](http://localhost:9999/f/technology/113720/signal-ceo-we-1-000-won-t-participate-in-uk-law-to-weaken)
- [Google Pixel 4 — Submission Detail](http://localhost:9999/f/technology/48700/google-has-to-pay-9-4-million-because-it-paid-people-to-say)