"""Narrow writing-quality sub-checks (language axis redesign).

TASK_CONSTRUCTION_DESIGN.md section 5: once correctness/completeness move to
the decidable axes, a monolithic pairwise "which report reads better" judge
measures the wrong thing (style/length/position lotteries, human ceiling
66-81%). The language axis is therefore rebuilt as narrow, mostly-decidable
sub-checks, each cheap, replayable, and auditable:

  structure_score           headers exist, hierarchy sane, intro present,
                            sections non-trivially sized       (decidable)
  redundancy_score          repeated-trigram mass + paragraph
                            near-duplicates                    (decidable)
  internal_contradiction_hook
                            NLI-pluggable; deterministic fallback is a weak
                            negation-asymmetry heuristic and is LABELLED so
                            (heuristic_weak), never sold as decidable
  answers_the_question      per-sub-ask lexical coverage; a LEXICAL PROXY,
                            labelled so; the narrow-rubric LLM hook is
                            declared but not implemented (stage 2)

`style_report` bundles them; its combined `style_score` averages ONLY the
deterministic checks (structure, redundancy, answer coverage). The
contradiction count is reported alongside but never folded in: with an
nli_fn it is model-dependent, and without one it is a weak heuristic.

Iron rule (enforced by the score combiner, not here): the style score can
never lift a report that the decidable axes suppress. It is a separate,
small-weight, disclosed column.

Everything here is stdlib-only and deterministic given the same inputs.
"""

from __future__ import annotations

import re

HEADER_RE = re.compile(r"(?m)^(#{1,6})\s+\S")
FENCE_RE = re.compile(r"(?ms)^```.*?^```\s*?$|^```.*\Z")
WS_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[a-z0-9']+")
# standalone numbers only: the 20 in "q20" is identity, not a quantity
NUM_RE = re.compile(r"(?<![a-z0-9])\d+(?:\.\d+)?(?![a-z0-9])")

# minimal English stopword list (question words included: sub-ask decomposition
# must not count "which"/"should" as content).
_STOPWORDS = {
    "a", "about", "after", "all", "also", "an", "and", "any", "are", "as",
    "at", "be", "been", "before", "best", "between", "both", "but", "by",
    "can", "could", "did", "do", "does", "each", "for", "from", "get", "give",
    "had", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its",
    "just", "like", "make", "many", "me", "more", "most", "much", "my", "no",
    "not", "of", "on", "one", "only", "or", "other", "our", "out", "over",
    "please", "same", "should", "so", "some", "such", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those", "to",
    "under", "up", "us", "want", "was", "we", "well", "were", "what", "when",
    "where", "whether", "which", "while", "who", "why", "will", "with",
    "would", "you", "your",
}

_NEGATION_MARKERS = (
    "not ", " no ", "never", "n't", "cannot", "without", "lacks", "lack of",
    "fails to", "unable to", "does not", "do not", "is not", "are not",
    "was not", "won't", "isn't", "doesn't", "don't", "aren't",
)

_COMPARATIVE_MARKERS = (
    "better", "worse", "best", "worst", "higher", "lower", "cheaper",
    "cheapest", "more expensive", "faster", "slower", "louder", "quieter",
    "longer", "shorter", "stronger", "weaker", "superior", "inferior",
)


def _strip_code(md: str) -> str:
    """Remove fenced code blocks; code repetition is not prose redundancy."""
    return FENCE_RE.sub(" ", md or "")


def _norm(s: str) -> str:
    return WS_RE.sub(" ", (s or "").lower()).strip()


def _paragraphs(md: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", _strip_code(md)) if p.strip()]


def _content_tokens(s: str) -> set[str]:
    return {t for t in WORD_RE.findall(_norm(s))
            if len(t) >= 3 and t not in _STOPWORDS}


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------

def structure_score(md: str, intro_min_words: int = 25,
                    section_min_words: int = 20) -> tuple[float, dict]:
    """Decidable document-structure check, [0,1]. Mean of five sub-checks:
      1. headers_present   at least one markdown header
      2. h1_sane           at most one h1 (a single title is fine)
      3. h2_sane           between 2 and 12 h2 sections
      4. intro_present     >= intro_min_words of prose before the first
                           SECTION header (a leading h1 title may precede it)
      5. sections_sized    fraction of sections with >= section_min_words
    """
    text = _strip_code(md)
    if not text.strip():
        return 0.0, {"empty": True}

    headers = []  # (level, char_offset)
    for m in HEADER_RE.finditer(text):
        headers.append((len(m.group(1)), m.start()))
    h1 = sum(1 for lv, _ in headers if lv == 1)
    h2 = sum(1 for lv, _ in headers if lv == 2)

    headers_present = bool(headers)
    h1_sane = h1 <= 1
    h2_sane = 2 <= h2 <= 12

    # intro: prose between the optional leading h1 title and the first
    # section header (level >= 2, or a second header of any level).
    section_starts = [off for i, (lv, off) in enumerate(headers)
                      if lv >= 2 or i >= 1]
    if section_starts:
        first_section = min(section_starts)
        pre = text[:first_section]
        pre = re.sub(r"(?m)^#{1,6}\s+.*$", " ", pre)  # drop the title line
        intro_present = len(pre.split()) >= intro_min_words
    else:
        # no sections at all; count the whole body as the intro
        body = re.sub(r"(?m)^#{1,6}\s+.*$", " ", text)
        intro_present = len(body.split()) >= intro_min_words

    # section sizes: text between consecutive headers (and after the last)
    if headers:
        bounds = [off for _, off in headers] + [len(text)]
        sizes = []
        for i in range(len(headers)):
            seg = text[bounds[i]:bounds[i + 1]]
            seg = re.sub(r"(?m)^#{1,6}\s+.*$", " ", seg)
            sizes.append(len(seg.split()))
        sections_sized = sum(s >= section_min_words for s in sizes) / len(sizes)
    else:
        sizes = []
        sections_sized = 0.0

    subs = [headers_present, h1_sane, h2_sane, intro_present, sections_sized]
    score = sum(float(x) for x in subs) / len(subs)
    return score, {
        "headers": len(headers), "h1": h1, "h2": h2,
        "headers_present": headers_present, "h1_sane": h1_sane,
        "h2_sane": h2_sane, "intro_present": intro_present,
        "sections_sized": round(sections_sized, 3),
        "section_words": sizes[:24],
    }


# ---------------------------------------------------------------------------
# redundancy
# ---------------------------------------------------------------------------

def redundancy_score(md: str, jaccard_dup: float = 0.7,
                     min_para_tokens: int = 5) -> tuple[float, dict]:
    """Decidable redundancy check, [0,1], higher = less redundant.

    Two components, the WORSE one is the score:
      trigram: 1 - excess-mass ratio of repeated word trigrams (each trigram
               gets one free occurrence; every extra occurrence is excess),
               whitespace/case deduped.
      paragraph: 1 - fraction of paragraphs that are a near-duplicate of an
               earlier paragraph (token-set Jaccard > jaccard_dup).
    """
    toks = WORD_RE.findall(_norm(_strip_code(md)))
    total = max(0, len(toks) - 2)
    if total <= 0:
        return 0.0, {"trigrams": 0}
    counts: dict[tuple, int] = {}
    for i in range(total):
        tri = (toks[i], toks[i + 1], toks[i + 2])
        counts[tri] = counts.get(tri, 0) + 1
    excess = sum(c - 1 for c in counts.values() if c > 1)
    trigram_ratio = excess / total
    trigram_component = 1.0 - trigram_ratio

    paras = [_content_tokens(p) | {t for t in WORD_RE.findall(_norm(p))}
             for p in _paragraphs(md)]
    paras = [p for p in paras if len(p) >= min_para_tokens]
    dups = 0
    dup_pairs = []
    for j in range(1, len(paras)):
        for i in range(j):
            inter = len(paras[i] & paras[j])
            union = len(paras[i] | paras[j])
            if union and inter / union > jaccard_dup:
                dups += 1
                dup_pairs.append((i, j))
                break
    para_component = 1.0 - (dups / len(paras) if paras else 0.0)

    score = min(trigram_component, para_component)
    return score, {
        "trigram_excess_ratio": round(trigram_ratio, 4),
        "trigram_component": round(trigram_component, 4),
        "paragraphs": len(paras), "near_duplicates": dups,
        "duplicate_pairs": dup_pairs[:8],
        "paragraph_component": round(para_component, 4),
    }


# ---------------------------------------------------------------------------
# internal contradictions (NLI-pluggable, weak deterministic fallback)
# ---------------------------------------------------------------------------

def _sentences(md: str) -> list[str]:
    text = _strip_code(md)
    text = re.sub(r"(?m)^\s*\|.*\|\s*$", " ", text)  # drop table rows (data)
    text = re.sub(r"(?m)^#{1,6}\s+.*$", " ", text)   # drop headings
    out = []
    # join hard-wrapped lines inside a paragraph, then split on punctuation
    for para in re.split(r"\n\s*\n", text):
        flat = WS_RE.sub(" ", para).strip()
        for s in re.split(r"(?<=[.!?])\s+", flat):
            s = s.strip().lstrip("*-+ ").strip()
            if len(WORD_RE.findall(s.lower())) >= 4:
                out.append(s)
    return out[:500]  # bound the O(n^2) pair scan


def _anchors(sent_low: str) -> set[str]:
    """Subject-identity candidates: long non-stopword tokens plus tokens that
    mix letters and digits (model numbers)."""
    out = set()
    for t in WORD_RE.findall(sent_low):
        if len(t) >= 5 and t not in _STOPWORDS:
            out.add(t)
        elif len(t) >= 3 and any(c.isdigit() for c in t) and any(c.isalpha() for c in t):
            out.add(t)
    return out


def _negated(sent_low: str) -> bool:
    padded = f" {sent_low} "
    return any(m in padded for m in _NEGATION_MARKERS)


def _comparative(sent_low: str) -> bool:
    return any(m in sent_low for m in _COMPARATIVE_MARKERS)


def internal_contradiction_hook(md: str, nli_fn=None,
                                max_pairs_sample: int = 5) -> dict:
    """Count internal contradictions between sentences of one report.

    nli_fn, when provided, is `nli_fn(premise, hypothesis) -> str` returning
    one of {"entail", "contradict", "neutral"}; it is run on candidate pairs
    (sentences sharing a subject anchor) and the method is reported as "nli".

    Without nli_fn the DETERMINISTIC FALLBACK flags a pair only if the two
    sentences share a subject anchor, exactly one of them carries a negation
    marker, and they share a number or both carry a comparative marker. That
    is a weak surface heuristic: it is labelled method="heuristic_weak" and
    must never be presented as a decidable check.
    """
    sents = _sentences(md)
    lows = [_norm(s) for s in sents]
    anchors = [_anchors(l) for l in lows]
    nums = [set(NUM_RE.findall(l)) for l in lows]

    method = "nli" if nli_fn is not None else "heuristic_weak"
    count, candidates, sample = 0, 0, []
    for j in range(1, len(sents)):
        for i in range(j):
            shared = anchors[i] & anchors[j]
            if not shared:
                continue
            candidates += 1
            if nli_fn is not None:
                hit = nli_fn(sents[i], sents[j]) == "contradict"
            else:
                neg_asym = _negated(lows[i]) != _negated(lows[j])
                same_ground = bool(nums[i] & nums[j]) or (
                    _comparative(lows[i]) and _comparative(lows[j]))
                hit = neg_asym and same_ground
            if hit:
                count += 1
                if len(sample) < max_pairs_sample:
                    sample.append((sents[i][:160], sents[j][:160]))
    return {"count": count, "pairs": sample, "method": method,
            "candidates_screened": candidates}


# ---------------------------------------------------------------------------
# answers-the-question coverage (lexical proxy)
# ---------------------------------------------------------------------------

def answers_the_question(md: str, question: str,
                         min_para_coverage: float = 0.6) -> tuple[float, dict]:
    """Coverage fraction over the question's sub-asks, a LEXICAL PROXY.

    The question is decomposed into sub-asks by splitting on question marks
    and then on ", and"/"and" clause boundaries (clauses with fewer than two
    content tokens are folded into their neighbour). A sub-ask counts as
    answered if some single paragraph of the report contains at least
    min_para_coverage of its stopword-filtered content tokens.

    This checks topical coverage, not answer quality; the output is labelled
    method="lexical_proxy". The narrow-rubric LLM check is a declared hook
    (answers_the_question_llm) and is intentionally not implemented here.
    """
    sub_asks: list[str] = []
    for part in re.split(r"\?", question or ""):
        clauses = re.split(r",?\s+\band\b\s+", part)
        for cl in clauses:
            if len(_content_tokens(cl)) >= 2:
                sub_asks.append(cl.strip())
            elif sub_asks and cl.strip():
                sub_asks[-1] = f"{sub_asks[-1]} and {cl.strip()}"
        if not any(len(_content_tokens(c)) >= 2 for c in clauses):
            if len(_content_tokens(part)) >= 1:
                sub_asks.append(part.strip())
    if not sub_asks:
        return 0.0, {"sub_asks": 0, "method": "lexical_proxy"}

    para_toks = [_content_tokens(p) for p in _paragraphs(md)]
    per = []
    covered = 0
    for ask in sub_asks:
        atoks = _content_tokens(ask)
        best = max((len(atoks & pt) / len(atoks) for pt in para_toks),
                   default=0.0) if atoks else 0.0
        ok = best >= min_para_coverage
        covered += ok
        per.append({"sub_ask": ask[:120], "best_para_coverage": round(best, 3),
                    "covered": ok})
    return covered / len(sub_asks), {
        "sub_asks": len(sub_asks), "covered": covered,
        "method": "lexical_proxy", "per": per,
    }


def answers_the_question_llm(md: str, question: str, rubric_fn):
    """Declared hook for the narrow-rubric LLM version (stage 2, not built).

    rubric_fn(question: str, sub_ask: str, report_md: str) -> float in [0,1]
    scores how directly the report answers one sub-ask under a narrow rubric
    (the mode where LLM judgment is most reliable per TASK_CONSTRUCTION_
    DESIGN.md section 5). Deliberately unimplemented: shipping it requires
    the calibration protocol (human anchor pairs) first.
    """
    raise NotImplementedError(
        "narrow-rubric LLM answer check is a stage-2 hook; "
        "use answers_the_question (lexical proxy) until it is calibrated")


# ---------------------------------------------------------------------------
# bundle
# ---------------------------------------------------------------------------

def style_report(md: str, question: str, nli_fn=None) -> dict:
    """All language-axis sub-checks for one report.

    style_score is the mean of the deterministic checks ONLY: structure,
    redundancy, and the lexical answer-coverage proxy. The contradiction
    hook's output is disclosed next to them but never averaged in (its
    fallback is heuristic_weak; with nli_fn it is model-dependent).
    """
    s_struct, d_struct = structure_score(md)
    s_red, d_red = redundancy_score(md)
    s_ans, d_ans = answers_the_question(md, question)
    contra = internal_contradiction_hook(md, nli_fn=nli_fn)
    deterministic = [s_struct, s_red, s_ans]
    return {
        "structure": {"score": round(s_struct, 4), **d_struct},
        "redundancy": {"score": round(s_red, 4), **d_red},
        "answers_the_question": {"score": round(s_ans, 4), **d_ans},
        "internal_contradiction": contra,
        "style_score": round(sum(deterministic) / len(deterministic), 4),
        "style_score_components": ["structure", "redundancy",
                                   "answers_the_question"],
        "excluded_from_style_score": [
            "internal_contradiction ({})".format(contra["method"])],
    }


if __name__ == "__main__":  # smoke on a real-ish report blob
    import json

    QUESTION = ("Which wireless headphones under $150 have the best noise "
                "cancellation, and how do real users rate their battery life?")
    REPORT = """# Wireless Headphones Under $150: Noise Cancellation and Battery

This report compares budget wireless headphones on active noise cancellation
and real-user battery feedback, drawing on the sandbox catalog, forum threads,
and encyclopedia background. Prices and ratings quoted below come from the
store listings themselves.

## Noise cancellation shortlist

The JBL Synchros E45BT ($129.99, 4.2 stars) offers passive isolation only.
The Anker Soundcore Q20 ($59.99) has hybrid active noise cancellation that
forum users describe as effective on low-frequency hum. The Q20 does not
handle high-frequency chatter well, according to three reddit threads.

## Battery life as rated by users

Forum users report the Q20 lasting around 40 hours with ANC on, well above
its 30-hour marketing claim. The E45BT is rated closer to 16 hours. One
reply insists the E45BT does not reach 16 hours in real use.

## Verdict table

| Model | ANC | Battery (user-reported) | Price |
|---|---|---|---|
| Soundcore Q20 | hybrid ANC | ~40 h | $59.99 |
| JBL E45BT | passive only | ~16 h | $129.99 |

## Caveats

The Q20 handles high-frequency chatter well in marketing copy, which
contradicts the forum consensus above. Ratings are store snapshots, not
lab measurements.
"""
    rep = style_report(REPORT, QUESTION)
    print(json.dumps(rep, indent=2, ensure_ascii=False))

    # degenerate blob: no structure, heavy repetition, off-topic
    SPAM = ("best value best value best value. " * 30) + "\n\n" + \
           ("best value best value best value. " * 30)
    rep2 = style_report(SPAM, QUESTION)
    print("spam style_score:", rep2["style_score"],
          "structure:", rep2["structure"]["score"],
          "redundancy:", rep2["redundancy"]["score"],
          "answers:", rep2["answers_the_question"]["score"])
    assert rep["style_score"] > rep2["style_score"], "spam must score lower"
    print("smoke OK: real-ish report outranks spam on style axis")

    # exercise the pluggable NLI interface with a stub
    def _stub_nli(premise, hypothesis):
        both = premise + " " + hypothesis
        return "contradict" if "does not reach" in both else "neutral"
    via_nli = internal_contradiction_hook(REPORT, nli_fn=_stub_nli)
    assert via_nli["method"] == "nli" and via_nli["count"] >= 1
    print("nli hook OK:", via_nli["count"], "contradiction(s) via stub nli_fn")
