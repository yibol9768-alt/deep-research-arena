# Comparative Analysis of /f/news vs /f/worldnews Engagement Metrics on Postmill: A Methodological Report

## Key Citations

- No source URLs are available. All data retrieval attempts from `http://localhost:9999/f/news.json` and `http://localhost:9999/f/worldnews.json` failed due to content filter errors and tool unavailability.

---

## Key Points

- All attempts to retrieve submission data from both `/f/news` and `/f/worldnews` on the local Postmill instance (localhost:9999) failed due to content filter errors (HTTP 400, error code 1301).
- No engagement data — including scores, comment counts, or submission counts — was successfully collected for either forum.
- The Python REPL tool, intended as a fallback for data fetching and statistical computation, was disabled, further precluding analysis.
- A complete methodological framework and analysis code were prepared but could not be executed against live data.
- **No determination can be made regarding which forum has a higher median comment count.**

---

## Overview

This report was commissioned to compare engagement metrics between two forums — `/f/news` and `/f/worldnews` — hosted on a local Postmill instance accessible at `localhost:9999`. The intended analysis focused on four key metrics: number of submissions, average score, average comment count, and median comment count, with the specific objective of identifying which forum exhibits higher median engagement as measured by comments. 

Despite a structured methodological approach, all data retrieval operations were unsuccessful. Content filter errors blocked the initial data-fetching steps, and the computational fallback mechanism was unavailable. Consequently, this report documents the attempted methodology, the failures encountered, and the analytical framework that would have been applied, while transparently acknowledging that no empirical findings can be reported.

---

## Detailed Analysis

### 1. Data Retrieval Failures

Two primary data-fetching operations were attempted, both resulting in failure:

| Step | Target URL | Error Code | Error Description |
|------|-----------|------------|-------------------|
| Fetch /f/news submissions | `http://localhost:9999/f/news.json` | 1301 (HTTP 400) | Content filter triggered — input or generated content flagged as potentially unsafe or sensitive |
| Fetch /f/worldnews submissions | `http://localhost:9999/f/worldnews.json` | 1301 (HTTP 400) | Identical content filter error |

The error message (translated) indicates: *"The system detected that the input or generated content may contain unsafe or sensitive content. Please avoid prompts that may generate sensitive content."*

This suggests that the content filter layer — likely operating at the API gateway or model inference level — intercepted the requests before data could be returned from the Postmill instance.

### 2. Fallback Computational Tool Unavailability

A secondary approach involving the Python REPL tool was considered for directly making HTTP requests to the Postmill JSON API endpoints and computing statistics programmatically. However, the Python REPL tool was disabled at the time of the research, eliminating this alternative path.

### 3. Intended Methodological Framework

The following analytical pipeline was designed and ready for execution:

**Step 1 — Data Collection:**
- HTTP GET requests to `/f/news.json` and `/f/worldnews.json`
- Extraction of submission entries from the JSON response payload
- Fields of interest: `score`, `commentCount`, `id`, `permalink`

**Step 2 — Statistical Computation:**

| Metric | Formula / Method |
|--------|-----------------|
| `number_of_submissions` | Count of entries returned on the first page |
| `average_score` | Arithmetic mean of all submission scores |
| `average_comment_count` | Arithmetic mean of all `commentCount` values |
| `median_comment_count` | Median of all `commentCount` values |

**Step 3 — Comparative Determination:**
- Direct comparison of `median_comment_count` between the two forums
- Classification of the forum with the higher value

### 4. Prepared Analysis Code

The following Python code was prepared for execution but could not be run:

```python
import requests
import json
import statistics

def fetch_forum_submissions(forum_name):
    url = f"http://localhost:9999/f/{forum_name}.json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    entries = data.get('entries', data) if isinstance(data, dict) else data
    return entries

def compute_stats(submissions, forum_name):
    scores = []
    comment_counts = []
    for s in submissions:
        scores.append(s.get('score', 0))
        comment_counts.append(s.get('commentCount', 0))
    return {
        "number_of_submissions": len(submissions),
        "average_score": round(statistics.mean(scores), 2) if scores else 0,
        "average_comment_count": round(statistics.mean(comment_counts), 2) if comment_counts else 0,
        "median_comment_count": round(statistics.median(comment_counts), 2) if comment_counts else 0,
    }

news_stats = compute_stats(fetch_forum_submissions("news"), "news")
worldnews_stats = compute_stats(fetch_forum_submissions("worldnews"), "worldnews")
higher_median = "news" if news_stats["median_comment_count"] >= worldnews_stats["median_comment_count"] else "worldnews"
```

### 5. Expected Output Schema

Had the analysis succeeded, the result would conform to the following structure:

| Field | /f/news | /f/worldnews |
|-------|---------|-------------|
| `number_of_submissions` | *[integer — not available]* | *[integer — not available]* |
| `average_score` | *[float — not available]* | *[float — not available]* |
| `average_comment_count` | *[float — not available]* | *[float — not available]* |
| `median_comment_count` | *[float — not available]* | *[float — not available]* |

**Higher median comment count:** *Cannot be determined*

---

## Survey Note

### Literature Review & Theoretical Framework

Engagement metrics in federated and decentralized forum platforms (such as Postmill, a PHP-based Reddit-alternative) remain an underexplored domain in the academic literature. While engagement analysis on mainstream platforms (Reddit, Hacker News) has received substantial attention — particularly regarding the relationship between submission scores, comment volume, and content virality — the applicability of these frameworks to smaller, self-hosted instances is uncertain. The theoretical expectation is that forums with broader topical scope (e.g., `/f/worldnews`) may attract more diverse engagement than domestically-focused forums (e.g., `/f/news`), but this hypothesis remains untested in the present context.

### Methodology & Data Analysis

The intended methodology employed a **cross-sectional comparative design**, analyzing first-page submissions from both forums at a single point in time. Limitations of this approach include:

1. **Temporal snapshot bias**: First-page data represents only the current state, not historical engagement patterns.
2. **Pagination truncation**: Only the first page of submissions was to be collected, potentially excluding long-tail content with different engagement profiles.
3. **Algorithmic ranking confound**: Postmill's sorting algorithm determines which submissions appear on the first page, introducing selection bias into the sample.

### Critical Discussion

The complete failure of data retrieval represents a significant methodological limitation. The content filter errors (code 1301) suggest that the tool infrastructure's safety mechanisms may be overly aggressive for research tasks involving forums that discuss current events and news, which inherently touch upon politically or socially sensitive topics. This raises important questions about the feasibility of automated research on news-oriented communities when intermediated by content-filtering AI systems.

### Future Research Directions

1. **Direct API access**: Bypassing the AI-mediated tool layer and directly querying the Postmill JSON API would eliminate the content filter interference.
2. **Extended temporal analysis**: Collecting data over multiple time points would enable longitudinal engagement comparison.
3. **Content-topic interaction**: Future studies could examine whether specific topic categories within each forum drive differential engagement.
4. **Instance-level normalization**: Comparing engagement as a proportion of total instance activity, rather than raw counts, would control for differences in forum subscriber bases.

---

## Key Citations

- No source URLs are available. All data retrieval attempts from `http://localhost:9999/f/news.json` and `http://localhost:9999/f/worldnews.json` failed due to content filter errors and tool unavailability.