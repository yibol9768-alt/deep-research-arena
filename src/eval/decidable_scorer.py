"""Decidable five-axis scorer (METHODOLOGY_REDESIGN_2026-07-03.md section 2).

Axes the frozen sandbox can DECIDE, plus one residual LLM axis handled
elsewhere:

  axis 1a reachability    cited URL is a member of the enumerated closed world
  axis 1b proof-of-fetch  the report's own context appears on the cited page
  axis 2  fact_support    the report's structured claims vs DB truth
  axis 3  completeness    saturating recall over a ranked vital pool
  axis 4  spec            decidable output-shape checks
  axis 5  presentation    pairwise LLM judge (residual, NOT in this module)

Everything here is deterministic and model-free: given a report, an AnswerKey,
the sandbox page cache and (optionally) a UrlRegistry, it returns per-axis
scores that replay byte-for-byte.

Composition (FORMULA_LOCK_2026-07-08 = candidate K6; supersedes the old
four-axis K0. Structure derived from two adversarial criteria, not tuned):

    quality = 0.39*fact + 0.28*proof_of_fetch + 0.33*completeness
    truth   = reach**gamma * quality

  * THREE evidence/volume axes only (fact / pof / completeness). spec (output
    shape) is NO LONGER in truth: it is orthogonal to grounding (E-13: spec r
    with reach -0.01, with fact 0.13) and is the one axis where every agent is
    near ceiling, so multiplying it in let a format-compliant EMPTY SHELL
    (reach=1, zero substance, spec=1) outrank the honest champion (C2 failed at
    truth 0.145 > 0.113). spec is now computed and reported as a SEPARATE
    "compliance" column, never multiplied into truth.
  * NO quality floor (EPS_FLOOR=0.0, D1 endgame): each quality axis contributes
    its RAW value. The earlier FLOOR-IF-ACTIVE (eps=0.05 when raw>0) closed the
    zero-shell hole but opened a MINI-SHELL one: a report that merely grazes each
    axis (raw ~0.001-0.01, e.g. read one page / cite one real URL / hit one vital
    word) had all three axes lifted to 0.05, so quality=0.05 and truth=0.05 -- on
    the fixed panels that beat 9/10 (deepseek) to 10/10 (qwen) substantive honest
    systems. A 50x inflation of a trivial report is exactly what a floor must not
    do. Removing it collapses the cheap mini-shell to its earned value (raw 0.01
    -> truth 0.01, below every honest system but the near-zero-reach tail) while
    leaving the agent RANKING unchanged (no-floor == floor-if-active order on
    both panels; FORMULA_LOCK K2/K3~K6). The zero-shell stays truth=0 with no
    floor at all (a raw-0 axis contributes 0). The buffer-single-axis-noise
    argument does not survive the mini-shell data: the floor bought no ordering
    and cost a whole gameable plateau. ``eps`` is kept as a (now 0.0) kwarg for
    back-compat; a positive value re-enables floor-if-active.
  * reach is deliberately UNfloored: it is the anti-fabrication gate and a pure
    fabricator must be able to reach truth = 0 (criterion C1 / M-C2).
  * weights 0.39/0.28/0.33 are the declared four-axis harm-ordering weights
    (0.35/0.25/0.30) renormalized over the three surviving axes (/0.90) and
    rounded to hundredths; they are a stated convention, NOT fitted. The choice
    of exact weights is not claimed optimal: raw axis scores are published and
    the ranking's weight-sensitivity is disclosed (FORMULA_LOCK Dirichlet
    table). "fewer parameters / averaging" is never offered as a reason.
  * gamma defaults to 1.0, so the headline score is the directly interpretable
    product ``gate * quality``.  Larger exponents remain available only for
    sensitivity analysis; the fabrication-injection sweep showed the expected
    stronger penalty but did not identify a uniquely justified exponent.
  * no cross-denominator arithmetic: the old (fact+pof)/2 averaged two ratios
    with different denominators (M-L1); they are separate weighted terms.

PRESENTATION AND COMPLIANCE ARE NOT PART OF TRUTH (M-C1). score_report returns
the three decidable evidence axes, the truth score, and spec as a separate
"compliance" figure. The presentation judge (normalized Elo, an interval scale
with no true zero) and compliance are reported as SEPARATE columns at
leaderboard time and may only break ties between reports with equal truth; they
must never overturn the truth ordering, and are never multiplied in.

aggregate() reports macro AND micro views plus min_report_truth, so a single
catastrophic report can no longer hide inside a per-agent mean (M-M1).
"""

from __future__ import annotations

import bisect
import html as html_mod
import math
import functools as _functools
import re
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Tunables (defaults; see each docstring for the calibration story)
# ---------------------------------------------------------------------------

GAMMA_DEFAULT = 1.0      # Linear, interpretable headline gate: truth = gate *
                         # quality. The injection sweep is retained as a
                         # sensitivity analysis, not as evidence that 1.5 is a
                         # uniquely calibrated operating point.
EPS_FLOOR = 0.0          # NO quality floor (D1 endgame): the FLOOR-IF-ACTIVE
                         # eps=0.05 inflated a "mini-shell" (each axis grazed to
                         # raw~0.01) to truth=0.05 and beat 9-10/12 honest
                         # systems; abolishing it collapses the mini-shell to its
                         # earned value without changing agent order. Kept as a
                         # kwarg for back-compat; >0 re-enables floor-if-active.
K_F_DEFAULT = 10         # fact-volume saturation constant (M-C3)
K_STAR_DEFAULT = 20      # completeness saturation constant (T1)
POF_THRESHOLD_DEFAULT = 0.35  # calibrated (G-F1): data/results/
                              # pof_gamma_calibration.json. Operating point on
                              # 320 verbatim positives + 160 fabricated-quote +
                              # 160 cross-page negatives: TPR=1.000, FPR=0.000
                              # (fabricated) / 0.006 (cross-page). The verbatim
                              # span requirement separates the classes on its
                              # own, so TPR/FPR are flat over the whole 0.15-0.60
                              # grid; 0.35 sits mid-plateau, kept as the incumbent.
BIND_WINDOW = 40         # subject<->value binding window, chars (M-H2/G-F6)

# FORMULA_LOCK K6: three evidence/volume axes only. spec is OUT of truth (see
# module docstring) and reported as a separate compliance column. Weights are
# the declared four-axis harm-ordering weights renormalized over the survivors
# (0.35/0.90, 0.25/0.90, 0.30/0.90) rounded to hundredths; they sum to 1.0.
QUALITY_WEIGHTS = {
    "fact_support": 0.39,
    "proof_of_fetch": 0.28,
    "completeness": 0.33,
}

# ---------------------------------------------------------------------------
# Silent-zero reason codes (G6 gate: every 0 an axis emits must carry a
# machine-readable reason, so "0" always means "observed and genuinely bad",
# never "the instrument saw nothing"). These codes cover SCORED zeros only.
# The complementary "instrument was blind" half is the G4 lane's canonical
# WithholdReason enum (branch gates-L3-withhold, commit 8985c07e; defined in
# THIS module there: 18 codes -- no_evidence_log, fetch_not_observable,
# concept_page_not_cached, ... -- plus withhold_reason_code()); it merges into
# this module alongside these and is authoritative for every withhold. The two
# sets are disjoint by construction: a WithholdReason never accompanies a
# score, a ZERO_REASONS code always does. Values are stable identifiers, never
# prose, so a board / preflight can branch on them.
ZERO_REASONS = {
    # reach (axis 1a)
    "no_citations",              # nothing citable at all -> denominator 0
    "all_citations_off_corpus",  # cited only URLs outside the frozen corpus
    # proof_of_fetch / quote_support (axis 1b)
    "no_citable_pages",          # no cited URL resolved to a cached-200 page
    "no_quote_support",          # cited pages exist, none verbatim-supported
    "no_page_fetched",           # transport_v2: cited real pages, none fetched
    # fact_support (axis 2)
    "no_checkable_claims",       # report asserted no checkable structured claim
    "no_supported_claims",       # claims made, none supported (precision 0)
    "no_recall_volume",          # no distinct task-scoped supported fact
    # completeness (axis 3)
    "empty_vital_pool",          # task offers no vital pool to cover
    "no_vital_covered",          # vital pool exists, report covered none
    # spec / compliance (axis 4)
    "no_spec_requirement_passed",
}

# Withhold spelling: an axis the instrument could not observe is WITHHELD, not
# scored 0 (HANDOFF trap "Withhold, never zero"). The canonical codes are G4's
# WithholdReason enum (see the note above; unprefixed values like
# "no_evidence_log"). This prefix survives only as a LEGACY tolerance for
# synthetic/older results that spelled withholds "withheld_*"; nothing in the
# live pipeline emits it.
WITHHELD_REASON_PREFIX = "withheld_"

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BARE_URL_RE = re.compile(r"https?://\S+")

# Standalone digit runs inside a [label](url) are part of the subject's
# identity (pack counts, size tokens like "36 Ounce", "(Pack of 3)"), never
# claim VALUES. Mask them before value extraction so a price cue near the label
# tail cannot turn a name number into a phantom price/rating claim. Mirrors the
# slug-token exclusion in proof-of-fetch context. Alphanumeric model tokens
# ("wh-1000xm4", "e45bt") keep their digits: only fully standalone runs match.
_LABEL_NUM_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z0-9])")
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

# Numeric tokens are kept as tokens regardless of length (G-F15: the old
# [a-z0-9]{3,} tokenizer silently dropped rating values like "4.4" and "5").
TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|[a-z][a-z0-9]{2,}")

# A comma-formatted amount is ONE number.  Matching ``$1,769.00`` as ``1`` and
# ``769.00`` created two false contradictions against the true 1769.00 price.
_NUM_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,6}(?:\.\d{1,2})?)")

# Price claims trigger ONLY on an explicit price cue within 12 chars of the
# number ("$" or price/priced/costs/cost); "at 18 grams" no longer becomes a
# CONTRADICTED price (G-F6).
_PRICE_CUE = re.compile(r"\bpric(?:e|es|ed|ing)\b|\bcosts?\b")

# The same cue discipline, for buyer_sentiment. A number only conveys a rating
# if it is presented as one; likewise a review count.
_RATING_CUE = re.compile(
    r"%|\bpercent\b|\brating\b|\brated\b|\bstars?\b|out of 5|/\s*5\b|"
    r"\bpositive\b|\bsatisfaction\b|\bfavourable\b|\bfavorable\b", re.I)
_REVIEW_CUE = re.compile(r"\breviews?\b|\bratings?\b|\breviewers?\b|\bbuyers?\b", re.I)

# A number IMMEDIATELY followed by a count noun ("3 reviews", "12 ratings") is
# presented as the review count, never as the sentiment value. Without this
# guard the buyer_sentiment window check credited the COUNT as a 5-star-scale
# rating whenever count == rating/20 (60.0%/3rev, 100.0%/5rev: 24 of the 100
# tasks' first-ranked nuggets alone), so a report stating a WRONG percentage
# stayed covered -- exactly the "silent saturation" class gate G3 exists to
# kill, and the opposite of this function's own declared semantics ("The
# review COUNT is not the sentiment").
_COUNT_NOUN_AFTER = re.compile(r"\s*(?:reviews?|ratings?|reviewers?|buyers?)\b",
                               re.I)


# ---------------------------------------------------------------------------
# Withhold reason codes (G4 gate; foundation for G6 machine-readable reasons)
# ---------------------------------------------------------------------------
#
# A withhold is NOT a zero. `0` means "the instrument observed it and it is
# genuinely absent"; a WithholdReason means "the instrument could not observe
# it, so no score is licensed". Scoring a blind instrument as 0 is a false
# accusation -- the class of defect this project keeps re-fixing (see
# HANDOFF_2026-07-09.md #7 "Withhold, never zero").
#
# The human sentence stays in the `reason` field (transport tests pin those
# exact strings and the scoring semantics are frozen). This enum is the ONE
# canonical set of codes every withhold path collapses to, so a board or the G6
# gate can switch on a stable token that a reworded prose string can never move.
class WithholdReason(str, Enum):
    """Canonical machine-readable code for one "instrument was blind" outcome."""

    # transport / proof-of-fetch (src/eval/fetch_log.py) -- the evidence log
    NO_EVIDENCE_LOG = "no_evidence_log"
    EMPTY_EVIDENCE_LOG = "empty_evidence_log"
    LOG_MULTIPLE_RUN_IDS = "evidence_log_multiple_run_ids"
    MISSING_START_MARK = "evidence_missing_start_mark"
    MULTIPLE_START_MARKS = "evidence_multiple_start_marks"
    MISSING_END_MARK = "evidence_missing_end_mark"
    MULTIPLE_END_MARKS = "evidence_multiple_end_marks"
    TRAFFIC_AFTER_END = "evidence_traffic_after_end"
    ORPHANED_BRACKET = "evidence_orphaned_bracket"
    INVALID_TIMESTAMP = "evidence_invalid_timestamp"
    END_BEFORE_START = "evidence_end_before_start"
    LOG_DAMAGED = "evidence_log_damaged"
    LOG_INCOMPLETE_UNATTRIBUTED = "evidence_incomplete_unattributed"
    ISOLATION_AMBIGUOUS = "evidence_isolation_ambiguous"
    WORKER_DISAGREEMENT = "evidence_worker_disagreement"
    # transport / proof-of-fetch -- lane fetches off-shim (8/12 lanes)
    FETCH_NOT_OBSERVABLE = "fetch_not_observable"
    # completeness concept axis -- the evaluator holds no cached copy of the
    # concept's source page, so a quote cannot be verified either way.
    CONCEPT_PAGE_NOT_CACHED = "concept_page_not_cached"
    # completeness forum slot (diagnostic cache_policy, ruling #2) -- the cache
    # holds no candidate thread page for this task's allowed forums, so the slot
    # is blind for an instrument reason rather than an earned miss.
    FORUM_THREAD_NOT_CACHED = "forum_thread_not_cached"
    # anything the classifier does not recognise. test_gate_withhold locks every
    # LIVE withhold path to a non-UNKNOWN code, so this can only appear when a new
    # reason string is added without a matching code -- a loud, testable failure.
    UNKNOWN = "unknown_withhold"


def withhold_reason_code(reason: str | None) -> WithholdReason:
    """Map a human withhold sentence to its canonical code.

    Matching is on stable anchor substrings (the transport tests already pin
    these phrases), so the prose can be reworded without moving a code. Order is
    significant: more specific anchors ("traffic after its end mark",
    "missing end mark") are tested before the substrings they contain
    ("end mark", "end marks"). An unrecognised string returns UNKNOWN.
    """
    r = (reason or "").strip().lower()
    if not r:
        return WithholdReason.UNKNOWN
    # Off-shim lane: an exact machine token, checked first.
    if "fetch_not_observable" in r or "not observable" in r:
        return WithholdReason.FETCH_NOT_OBSERVABLE
    # Bracket-shape failures (order matters: specific before generic).
    if "traffic after" in r:
        return WithholdReason.TRAFFIC_AFTER_END
    if "precedes start" in r or "end before start" in r:
        return WithholdReason.END_BEFORE_START
    if "no valid timestamp" in r or "invalid timestamp" in r:
        return WithholdReason.INVALID_TIMESTAMP
    if "orphaned" in r:
        return WithholdReason.ORPHANED_BRACKET
    if "multiple run_id" in r or "mixes multiple run" in r:
        return WithholdReason.LOG_MULTIPLE_RUN_IDS
    if "missing start" in r:
        return WithholdReason.MISSING_START_MARK
    if "missing end" in r:
        return WithholdReason.MISSING_END_MARK
    if "start marks" in r:
        return WithholdReason.MULTIPLE_START_MARKS
    if "end marks" in r:
        return WithholdReason.MULTIPLE_END_MARKS
    # Isolation before "incomplete/unattributed": the ambiguous sentence also
    # contains "unattributed".
    if "ambiguous" in r:
        return WithholdReason.ISOLATION_AMBIGUOUS
    if "disagree on worker" in r:
        return WithholdReason.WORKER_DISAGREEMENT
    if "damaged" in r:
        return WithholdReason.LOG_DAMAGED
    if "incomplete" in r or "landed unattributed" in r:
        return WithholdReason.LOG_INCOMPLETE_UNATTRIBUTED
    if "empty evidence" in r:
        return WithholdReason.EMPTY_EVIDENCE_LOG
    if "forum" in r and "cache" in r:
        return WithholdReason.FORUM_THREAD_NOT_CACHED
    if "concept" in r and "cache" in r:
        return WithholdReason.CONCEPT_PAGE_NOT_CACHED
    if "no evidence log" in r:
        return WithholdReason.NO_EVIDENCE_LOG
    return WithholdReason.UNKNOWN


def _cue_near(win: str, start: int, end: int, cue: re.Pattern, radius: int = 24) -> bool:
    """Is a cue word within `radius` chars of this number?"""
    return bool(cue.search(win[max(0, start - radius): end + radius]))
PRICE_CUE_WINDOW = 12

# Numbers immediately followed by a unit word are measurements, never prices
# (G-F6). Longer alternatives first where prefixes collide.
_UNIT_AFTER = re.compile(
    r"^\s*-?\s*(?:%|/\s*5\b|out\s+of\s+5\b|(?:grams?|hours?|hrs|inch(?:es)?|stars?|reviews?|days?"
    r"|years?|khz|kbps|hz|mah|mm|cm|oz|lbs?|g|budgets?|total)\b)", re.I)

# A rating claim requires the stars / out-of-5 cue (G-F15: single-digit values
# are kept); an aspect qualifier between the number and the subject ("5 stars
# for build") disqualifies it as an OVERALL rating claim (G-F6).
_RATING_CLAIM = re.compile(
    r"\b(\d(?:\.\d)?)\s*(?:-\s*)?(?:stars?\b|/\s*5\b|out of 5\b)")
_ASPECT_QUALIFIER = re.compile(
    r"\bfor\s+(?:the\s+)?(?:build|sound|comfort|quality|design|value|bass"
    r"|mic|battery|durability|fit|style|noise)\b")

PRICE_ABS_TOL = 0.02     # absolute price tolerance
PRICE_REL_TOL = 0.01     # 1 percent relative price tolerance
RATING_TOL = 0.15

_SANDBOX_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?/", re.I)

# ~150-word English stopword set for proof-of-fetch context filtering (G-F1).
# Tokens under 3 chars never survive the tokenizer, but the short words stay
# here for completeness / reuse.
STOPWORDS = frozenset("""
a about above across after again against all along also although am among an
and any are around as at back be because been before behind being below
between beyond both but by can cannot could despite did do does doing down
during each either else etc even ever every except few first for from further
get got had has have having he hence her here hers herself him himself his how
however i if in include includes including into is it its itself just least
less like made make many may me might more moreover most much must my myself
neither never new no nor not now of off old on once one only or other our ours
ourselves out over own per said same say second see seen shall she should
since so some such than that the their theirs them themselves then there
therefore these they third this those though through thus to too toward
towards two under until up upon use used using very via was we well were what
when where whether which while who whom whose why will with within without
would yet you your yours yourself yourselves
""".split())

# Embedded Magento/Postmill/Kiwix chrome tokens, used when no page cache is
# available to compute document frequency (G-F1: navigation/footer chrome must
# not count as proof of having read a page).
CHROME_FALLBACK = frozenset({
    "account", "cart", "wishlist", "compare", "search", "sign", "copyright",
    "menu", "skip", "review", "rating", "add", "home", "page", "next",
    "previous", "categories", "forum", "submit", "comment", "wikipedia",
    "article", "edit",
})
_CHROME_TOP_N = 40       # top-N df tokens treated as chrome when cache present
_CHROME_MIN_PAGES = 8    # below this many cached pages, df is too noisy for
                         # chrome detection; keep df for IDF weights only


def norm(s: str) -> str:
    return WS_RE.sub(" ", (s or "").lower()).strip()


def strip_html(t: str) -> str:
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t or "")
    return WS_RE.sub(" ", html_mod.unescape(TAG_RE.sub(" ", t))).strip()


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def _is_numeric_tok(t: str) -> bool:
    return bool(t) and t[0].isdigit()


_STOP = {"the", "and", "for", "with", "wireless", "bluetooth", "new", "pack",
         "set", "pro", "plus", "inch", "black", "white", "blue", "red"}


def build_generic_tokens(answer_key, df_frac: float = 0.15) -> set:
    """Tokens that appear in more than df_frac of relevant entity names are
    'generic' for this topic (e.g. headphones, earbuds, wireless) and must NOT
    serve as subject identity (else every product's head term matches every
    other's). Auto-detected per answer key, so no topic config is needed."""
    import collections
    names = [e.name for e in answer_key.relevant_set
             if getattr(e, "relevant", True) and e.category == "shopping_product"]
    if not names:
        return set(_STOP)
    df = collections.Counter()
    for nm in names:
        for t in set(re.findall(r"[a-z0-9]+", nm.lower())):
            if len(t) > 2:
                df[t] += 1
    cut = max(3, int(df_frac * len(names)))
    return set(_STOP) | {t for t, c in df.items() if c >= cut}


def name_key(name: str, generic: set | None = None) -> str:
    """Distinctive tokens of a product name (brand + model), excluding topic
    generic tokens. 'JBL Synchros E45BT Wireless Headphones' -> 'jbl synchros e45bt'."""
    g = generic or _STOP
    toks = [t for t in re.findall(r"[a-z0-9]+", (name or "").lower())
            if len(t) > 2 and t not in g]
    return " ".join(toks[:6])


def _name_tokens(name: str, generic: set | None = None, *, cap=None) -> list[str]:
    """All distinctive name tokens, preserving model/size numbers.

    ``name_key`` intentionally keeps a short six-token display key.  It must not
    also be the entity identity used by the fact scorer: thousands of catalog
    variants share those first six words but have different prices.  This helper
    supplies the full identity for matching while keeping the old public helper
    stable for callers that only need a compact label.
    """
    g = generic or _STOP
    out, seen = [], set()
    for t in re.findall(r"[a-z0-9]+", (name or "").lower()):
        if (len(t) <= 2 and not any(c.isdigit() for c in t)) or t in g or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if cap is not None and len(out) >= cap:
            break
    return out


@_functools.lru_cache(maxsize=None)
def _subject_pattern(subject: str):
    """Compiled full-subject pattern, cached per subject.

    `_fact_mentions` asks this for every entity on every sentence: 1,592 catalog
    titles produce 1,592 DISTINCT patterns, which blows straight through
    `re`'s 512-entry internal cache, so every sentence recompiled every pattern.
    Measured: ~5s PER SENTENCE, ~25 minutes for one 28KB report, before any
    board could even be built. The pattern set is fixed per answer key, so an
    unbounded cache is a few MB and turns the compile cost into a one-time cost.
    """
    toks = re.findall(r"[a-z0-9]+", (subject or "").lower())
    if not toks:
        return None
    return re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, toks))
                      + r"(?![a-z0-9])")


def _exact_subject_spans(text: str, subject: str, cap: int = 20) -> list[tuple[int, int]]:
    """Spans of a complete lexical subject mention, punctuation-insensitive."""
    pat = _subject_pattern(subject)
    if pat is None:
        return []
    return [m.span() for m in pat.finditer(text)][:cap]


def _subject_value_spans(text: str, subject: str, tokens: list[str]) -> list[tuple[int, int]]:
    """Prefer the FULL subject span; fall back to individual identity tokens.

    The old completeness path kept only the first six tokens and opened a
    +-40-character window around each.  In a real long catalog title, the gold
    rating appears after the full title and therefore outside every one of those
    windows.  Exact oracle prose failed 1200/1200 self-coverage in the worst
    shape.  A full mention binds from its end, which is where a natural value is
    written; abbreviated mentions retain the conservative token fallback.
    """
    exact = _exact_subject_spans(text, subject)
    return exact or _token_spans(text, tokens)


def _visible_prose(md: str, *, mask_link_numbers: bool = False) -> str:
    """Normalised human-visible prose: labels stay, URL shells disappear."""
    try:
        from src.verifiers.citation_format import (
            BARE_URL_RE as _CITED_BARE_URL_RE,
            replace_markdown_links,
        )
        def label(link):
            return (_LABEL_NUM_RE.sub(" ", link.label)
                    if mask_link_numbers else link.label)
        text = replace_markdown_links(md or "", label)
        text = _CITED_BARE_URL_RE.sub(" ", text)
    except Exception:
        text = LINK_RE.sub(
            (lambda m: _LABEL_NUM_RE.sub(" ", m.group(1)))
            if mask_link_numbers else (lambda m: m.group(1)), md or "")
        text = BARE_URL_RE.sub(" ", text)
    return norm(text)


def _subject_tokens(n, generic: set | None) -> list[str]:
    """The tokens that identify this nugget's subject in the report.

    Generic-token stripping exists to keep one product's head term ("wireless",
    "headphones") from matching every other product. A wiki concept is not a
    product: its identity IS its head term. `build_generic_tokens` derives the
    generic set from the shopping catalog, and `_STOP` hardcodes `bluetooth`, so
    `name_key("Bluetooth", generic)` returned "" and the nugget was skipped for
    every report ever scored. 62 of 278 concept nuggets (22.3%) were structurally
    uncoverable this way -- `Bluetooth`, `Headphones`, `Coffee`, `Tea`,
    `Digital camera` -- which are the concepts the tasks are about.
    """
    if getattr(n, "predicate", None) == "concept_coverage":
        return [t for t in re.findall(r"[a-z0-9]+", (n.subject or "").lower())
                if len(t) > 2][:6]
    return name_key(n.subject, generic).split()


def _subject_discussed(text: str, subj_tokens: list[str]) -> bool:
    """The report discusses this entity only if its distinctive identity is
    present: a majority of identity tokens (capped at what the key actually
    has, so single-token subjects such as short forum-thread titles remain
    matchable), at least one of which is strong (>=4 chars, or a model-number
    style token containing a digit).

    Ruling #5 (docs/SPEC_DECISIONS.md lane addendum, short-topic concept
    deadlock): a subject whose EVERY token is short ("Tea", a single 3-char
    word) has no strong token, so the strong-token rule deadlocked it to "not
    discussed" for every report -- including the oracle -- an implementation bug,
    not the spec's intent. For an all-short-token subject the discussability test
    falls back to WORD-BOUNDARY exact matching of the identity tokens (stricter
    than the substring `in` test above, so "tea" no longer hides inside "team"):
    a genuinely discussed short concept is credited, a laundering substring
    collision is not."""
    if not subj_tokens:
        return False
    present = [t for t in subj_tokens if t in text]
    need = min(len(subj_tokens), max(2, (len(subj_tokens) + 1) // 2))
    if len(present) < need:
        return False
    if any(len(t) >= 4 or any(c.isdigit() for c in t) for t in present):
        return True
    # All-short-token subject: no strong token exists. Require word-boundary
    # matches (exact short phrases) for at least `need` of the identity tokens.
    return sum(1 for t in subj_tokens
               if _word_token_pattern(t).search(text)) >= need


@_functools.lru_cache(maxsize=None)
def _word_token_pattern(tok: str):
    """Compiled word-boundary token pattern; same cache story as _subject_pattern."""
    return re.compile(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])")


def _token_spans(text: str, tokens: list[str], cap: int = 200) -> list[tuple[int, int]]:
    """Character spans of each identity token in text (word-boundary matches)."""
    spans: list[tuple[int, int]] = []
    for t in tokens:
        if not t:
            continue
        for m in _word_token_pattern(t).finditer(text):
            spans.append(m.span())
            if len(spans) >= cap:
                return spans
    return spans


def _near(spans: list[tuple[int, int]], pos: int, window: int = BIND_WINDOW) -> bool:
    """The +-window char subject-binding helper (M-H2/G-F6): a value only
    binds to a subject if it sits within `window` chars of one of the
    subject's identity-token occurrences."""
    return any(s - window <= pos <= e + window for s, e in spans)


def _nearest_subject(subs: dict, pos: int, window: int = BIND_WINDOW):
    """Among candidate subjects (key -> (spans, coverage_frac)), the one that
    binds pos within the window. Specificity first (a key with all its
    identity tokens in the sentence beats a colliding key that only shares a
    few tokens with it), then proximity. Returns (key, span)."""
    best_key, best_span, best = None, None, None
    for key, (spans, frac) in subs.items():
        for s, e in spans:
            d = 0 if s <= pos <= e else min(abs(pos - e), abs(s - pos))
            if d > window:
                continue
            rank = (frac, -d)
            if best is None or rank > best:
                best_key, best_span, best = key, (s, e), rank
    return best_key, best_span


def _price_close(v: float, targets) -> bool:
    return any(abs(v - t) <= max(PRICE_ABS_TOL, PRICE_REL_TOL * t) for t in targets)


def _standalone_number(low: str, start: int, end: int) -> bool:
    """A numeric match is a VALUE only when it stands alone. Digits embedded
    in model tokens ('wh-1000xm4' -> '1000', '4') are identity, not claims
    (G-F6 cross-product crosstalk), and partial matches of longer numbers
    ('129.990000' -> '129.99') are not values either."""
    if start > 0 and (low[start - 1].isalnum() or low[start - 1] == "."):
        return False
    if end < len(low):
        c = low[end]
        if c.isalnum():
            return False
        if c == "." and end + 1 < len(low) and low[end + 1].isdigit():
            return False
    return True


@dataclass
class AxisScores:
    reach: float = 0.0           # axis 1a (UNfloored: the fabrication gate)
    proof_of_fetch: float = 0.0  # axis 1b
    fact_support: float = 0.0    # axis 2 (structured decidable part)
    fact_contradicted: int = 0
    fact_absent: int = 0         # claims made but unbindable/untestable
    completeness: float = 0.0    # axis 3
    spec: float = 0.0            # axis 4 (output shape) -- retained field
    compliance: float = 0.0      # spec surfaced as a SEPARATE column, NOT in
                                 # truth (FORMULA_LOCK K6); mirrors spec
    quality: float = 0.0         # weighted sum of floor-if-active evidence axes
    truth: float = 0.0           # reach**gamma * quality
    detail: dict = field(default_factory=dict)


def _cited_urls(md: str) -> list[str]:
    """Every cited URL regardless of citation style (G-F11): routed through
    the shared citation_format.extract_citations (markdown, bare, numbered,
    footnote), deduped in first-seen order; falls back to markdown-only
    extraction if the shared extractor is unavailable."""
    seen, out = set(), []
    try:
        from src.verifiers.citation_format import extract_citations
        for c in extract_citations(md, sandbox_only=False):
            u = getattr(c, "raw_url", None) or getattr(c, "canonical_url", None) \
                or (c.get("url") if isinstance(c, dict) else None)
            if u:
                u = u.rstrip(".,;")
                if u not in seen:
                    seen.add(u)
                    out.append(u)
        if out:
            return out
    except Exception:
        pass
    for m in LINK_RE.finditer(md):
        u = m.group(2).rstrip(".,;")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------------------------------------------------------------------------
# Axis 1a: reachability
# ---------------------------------------------------------------------------

def _cache_entry(cache: dict, u: str, registry=None):
    """Cache lookup tolerant to key-normalization drift between the extractor
    and the cache builder (trailing punctuation, localhost vs 127.0.0.1)."""
    for k in (u, u.rstrip("`.,;:!?)"),
              u.replace("127.0.0.1", "localhost"),
              u.replace("localhost", "127.0.0.1")):
        e = cache.get(k)
        if e is not None:
            return e
    # Registry aliases (/wiki/X, /content/<book>/A/X, forum decorative slugs)
    # name the same page.  Unknown-membership fallback must use that identity in
    # both reach and transport or their fabrication numbers diverge.
    if registry is not None:
        try:
            target = registry.classify(u).get("canonical")
        except Exception:
            target = None
        if target:
            for k, e in cache.items():
                try:
                    if registry.classify(k).get("canonical") == target:
                        return e
                except Exception:
                    continue
    return None


def _in_corpus_with_cache(u: str, cache: dict, registry=None) -> bool:
    """The single membership predicate used by reach and transport."""
    if registry is not None and getattr(registry, "loaded", True):
        try:
            d = registry.classify(u)
        except Exception:
            return False
        inc = d.get("in_corpus") if isinstance(d, dict) else bool(d)
        if inc is not None:
            return bool(inc)
        try:
            return int((_cache_entry(cache, u, registry) or {}).get("status", 0) or 0) == 200
        except (TypeError, ValueError):
            return False
    if not _SANDBOX_URL_RE.match(u or ""):
        return False
    try:
        return int((_cache_entry(cache, u) or {}).get("status", 0) or 0) == 200
    except (TypeError, ValueError):
        return False


def score_reachability(urls: list[str], cache: dict, registry=None) -> tuple[float, dict]:
    """axis 1a: closed-world reachability.

    Preferred path (fixes G-F2/F8/F10): registry membership via UrlRegistry.
    Reachable := parses AND canonical content shape AND in the enumerated
    corpus; search/nav URLs are excluded from both numerator and denominator;
    off-sandbox and content-shaped-but-absent URLs are fabricated. Misattributed
    Postmill citations (forum_mismatch) COUNT AS REACHABLE (the submission id
    resolves) but are reported separately for downstream penalties.

    Fallback path (registry file missing): HTTP-cache status, hardened per
    M-M2/G-F8/G-F10: 4xx, 5xx, status 0, uncached and off-sandbox URLs all
    stay in the denominator (in a closed world, unresolved == fabricated).
    The detail dict carries registry_missing=True so the degradation is loud.
    """
    if registry is not None and getattr(registry, "loaded", True):
        # per-URL classification so tri-state membership can be resolved:
        # in_corpus None (e.g. wiki_registry_partial: the v1 wiki list is a
        # partial enumeration) falls back to the page cache for THAT url;
        # unknown AND uncached counts as fabricated (conservative: excluding
        # it would reopen the G-F8 vanish-from-denominator hole) and is
        # tallied separately so a full ZIM enumeration can retire the flag.
        # Off-corpus / unresolvable URLs still need a per-PAGE identity for the
        # dedupe below. The registry has no canonical form for them, and the old
        # RAW-string fallback let spelling variants of one fabricated URL
        # (#fragment, trailing slash, https vs http, trailing punctuation) count
        # as several fabricated citations here while `transport_metrics` (keyed
        # on fetch_log.canonical) counted one, breaking the declared
        # `fabrication == 1 - reach` identity (SPEC_ISSUES G6). Use the SAME
        # normaliser transport uses for exactly these URLs. Lazy import keeps
        # the module import graph unchanged (same pattern as
        # transport_metrics_for).
        from src.eval.fetch_log import canonical as _transport_canonical
        ok = fab = nav = mismatch = 0
        unknown_cache_ok = unknown_cache_fab = unknown_uncached = 0
        n_variant_dupes = 0
        seen_canon: set[str] = set()
        reasons: dict[str, int] = {}
        for u in urls:
            d = registry.classify(u)
            # one PAGE counts once: dedupe on the canonical form so case/
            # host/prefix/query variants of a single real page cannot pad the
            # numerator and launder fabricated citations (verify finding)
            canon = d.get("canonical") or f"raw:{_transport_canonical(u)}"
            if canon in seen_canon:
                n_variant_dupes += 1
                continue
            seen_canon.add(canon)
            reasons[d.get("reason", "?")] = reasons.get(d.get("reason", "?"), 0) + 1
            kind = d.get("kind")
            if kind == "search_nav":
                nav += 1
                continue
            inc = d.get("in_corpus")
            if inc is True:
                ok += 1
                if d.get("forum_mismatch"):
                    mismatch += 1
            elif inc is False or kind == "off_sandbox":
                fab += 1
            else:  # unknown membership: resolve via cache
                st = int((_cache_entry(cache, u, registry) or {}).get("status", -1))
                if st == 200:
                    ok += 1
                    unknown_cache_ok += 1
                elif st == -1:
                    fab += 1
                    unknown_uncached += 1
                else:
                    fab += 1
                    unknown_cache_fab += 1
        den = ok + fab
        det = {
            "path": "registry",
            "reasons": reasons,
            "num": ok,
            "den": den,
            "n_search_nav_excluded": nav,
            "forum_mismatch_reachable": mismatch,
            "unknown_resolved_by_cache_ok": unknown_cache_ok,
            "unknown_resolved_by_cache_fab": unknown_cache_fab,
            "unknown_uncached_counted_fabricated": unknown_uncached,
            "variant_duplicates_collapsed": n_variant_dupes,
        }
        score = ok / den if den else 0.0
        if score == 0.0:
            # A scored 0 on the anti-fabrication gate must say which failure it
            # was: no citations to judge, or citations that were all off-corpus.
            det["reason"] = "no_citations" if den == 0 else "all_citations_off_corpus"
        return score, det

    ok = bad = off = 0
    for u in urls:
        if not _SANDBOX_URL_RE.match(u or ""):
            off += 1
            bad += 1
            continue
        try:
            st = int((cache.get(u) or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            st = 0
        if st == 200:
            ok += 1
        else:
            bad += 1
    den = ok + bad
    score = ok / den if den else 0.0
    det = {
        "path": "cache_status", "registry_missing": True,
        "cited": len(urls), "ok": ok, "unreachable": bad, "off_sandbox": off,
        "num": ok, "den": den,
        "note": ("closed world: 4xx/5xx/0/uncached/off-sandbox all stay in "
                 "the denominator (M-M2/G-F8/G-F10)"),
    }
    if score == 0.0:
        det["reason"] = "no_citations" if den == 0 else "all_citations_off_corpus"
    return score, det


# ---------------------------------------------------------------------------
# Axis 1b: proof-of-fetch
# ---------------------------------------------------------------------------

def build_page_stats(cache: dict, top_n_chrome: int = _CHROME_TOP_N,
                     min_pages_for_df: int = _CHROME_MIN_PAGES) -> dict:
    """One-time document-frequency pass over the cached pages (G-F1).

    Returns {"df": token->df or None, "n_pages": int, "chrome": set}.
    Chrome = the top-N tokens by page frequency (site-wide navigation, footer,
    boilerplate) when enough pages are cached; otherwise the embedded
    Magento/Postmill/Kiwix chrome list. Numeric tokens are never chrome."""
    docs = []
    for entry in (cache or {}).values():
        try:
            st = int((entry or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            st = 0
        if st == 200 and (entry or {}).get("text"):
            docs.append(set(_tokens(norm(strip_html(entry["text"])))))
    n = len(docs)
    if n == 0:
        return {"df": None, "n_pages": 0, "chrome": set(CHROME_FALLBACK)}
    import collections
    df = collections.Counter()
    for d in docs:
        df.update(d)
    if n >= min_pages_for_df:
        common = [t for t, c in df.most_common()
                  if not _is_numeric_tok(t) and c >= max(2, (n + 1) // 2)]
        chrome = set(common[:top_n_chrome]) or set(CHROME_FALLBACK)
    else:
        chrome = set(CHROME_FALLBACK)
    return {"df": dict(df), "n_pages": n, "chrome": chrome}


# Citation styles whose site sits next to a CLAIM in the running prose and can
# therefore serve as a proof-of-fetch evidence anchor (E-3 §6.3). Reference-list
# forms (``source`` = "URL: ..." bibliography lines, ``bullet`` = "- <url>"
# lists) are excluded from EVIDENCE: the 400 chars before such a site are the
# entry's own title / other bibliography rows, not a claim, so verifying them
# would either self-match the page title or prove nothing. They still count for
# reachability; here they only mark the page as CITED (denominator), never as
# read (numerator). Numbered / footnote inline anchors ([N], [^id]) are the
# in-text markers whose surrounding prose is the report's own claim.
POF_EVIDENCE_STYLES = frozenset({"markdown", "numbered", "footnote", "bare"})


# --- Reference-list / bibliography region detection (audit F1 / D4) ----------
# A citation marker that sits INSIDE a reference list -- a "## References" /
# "### Sources" section, a run of "[N] <title>" reference-entry lines, or a
# "[^id]: <url>" footnote-DEFINITION line -- is NOT an in-text claim and must
# not serve as a proof-of-fetch EVIDENCE anchor. The 400 chars preceding such a
# marker are the PREVIOUS bibliography entry's title / result-snippet, not the
# report's own running prose; anchoring on it lets entry N's verbatim snippet
# "bleed" onto the page that entry N+1 points at (a cross-entry false positive:
# 12/12 numbered reports triggered, 35.6% of numbered occurrences landed after a
# references heading -- audit F1). Such markers still count for reachability and
# for the PoF DENOMINATOR (the page is CITED); they are barred only from the
# NUMERATOR (evidence). Detection is deterministic: a reference-section heading,
# or the entry/footnote-definition LINE pattern itself.
_REF_SECTION_HEAD_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?\**\s*"
    r"(?:works\s+cited|bibliography|references?|sources?|citations?|"
    r"footnotes?|end\s?notes?|notes)"
    r"\s*:?\s*\**\s*$",
    re.IGNORECASE)
_ANY_MD_HEAD_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_NUM_ENTRY_LINE_RE = re.compile(r"^\s*\[\d{1,3}\]\s")   # "[N] <title>" ref head
_FN_DEF_LINE_RE = re.compile(r"^\s*\[\^[\w-]+\]:")       # "[^id]: <url>" def line


def _reference_region_offsets(md: str) -> list[tuple[int, int]]:
    """Char-offset spans of ``md`` that are reference-list / bibliography regions
    (audit F1 / D4). An evidence anchor whose offset falls inside any span is a
    bibliography row, not an in-text claim marker, and is dropped from the PoF
    numerator (kept for the denominator). Deterministic; three cues:

      (1) a reference-section HEADING ("## References", "### Sources",
          "**Footnotes**", ...) delimits a region up to the next non-reference
          markdown heading (or EOF);
      (2) a run of >=2 consecutive numbered-entry / footnote-definition lines
          (an unheaded reference list) is a region;
      (3) any single numbered-entry ("[N] ...") or footnote-definition
          ("[^id]: ...") LINE is itself a bibliography row.

    Returns a (possibly overlapping) list of ``(start, end)`` char spans."""
    spans: list[tuple[int, int]] = []
    lines = md.splitlines(keepends=True)
    n = len(lines)
    offs = []
    p = 0
    for ln in lines:
        offs.append(p)
        p += len(ln)
    total = len(md)

    # (1) heading-delimited reference sections
    i = 0
    while i < n:
        if _REF_SECTION_HEAD_RE.match(lines[i]):
            j = i + 1
            while j < n:
                if (_ANY_MD_HEAD_RE.match(lines[j])
                        and not _REF_SECTION_HEAD_RE.match(lines[j])):
                    break
                j += 1
            spans.append((offs[i], offs[j] if j < n else total))
            i = j
            continue
        i += 1

    def _is_entry(k: int) -> bool:
        return bool(_NUM_ENTRY_LINE_RE.match(lines[k])
                    or _FN_DEF_LINE_RE.match(lines[k]))

    # (2) runs of >=2 consecutive reference-definition lines (blank-tolerant)
    i = 0
    while i < n:
        if _is_entry(i):
            j = i
            last_entry = i
            while j < n and (_is_entry(j) or lines[j].strip() == ""):
                if _is_entry(j):
                    last_entry = j
                j += 1
            cnt = sum(1 for k in range(i, j) if _is_entry(k))
            if cnt >= 2:
                end = offs[last_entry] + len(lines[last_entry])
                spans.append((offs[i], end))
            i = max(j, i + 1)
            continue
        i += 1

    # (3) any single numbered-entry / footnote-definition line is a bibliography
    #     row on its own (covers a lone reference head and markdown-in-entry).
    for k in range(n):
        if _is_entry(k):
            spans.append((offs[k], offs[k] + len(lines[k])))
    return spans


def _offset_in_spans(off: int, spans: list[tuple[int, int]]) -> bool:
    for a, b in spans:
        if a <= off < b:
            return True
    return False


def _sentence_spans(md: str):
    """Yield the same claim segments as the fact parser plus source offsets."""
    split = re.compile(r"(?<=[.!?])\s+|\n")
    start = 0
    for match in split.finditer(md or ""):
        if match.start() > start:
            yield (md[start:match.start()], start, match.start())
        start = match.end()
    if start < len(md or ""):
        yield (md[start:], start, len(md))


def _line_spans(md: str):
    """Yield non-empty Markdown lines with source offsets."""
    start = 0
    for line in (md or "").splitlines(keepends=True):
        end = start + len(line)
        content = line.rstrip("\r\n")
        if content.strip():
            yield (content, start, start + len(content))
        start = end
    if md and not md.endswith(("\n", "\r")) and start < len(md):
        yield (md[start:], start, len(md))


def _resolve_cache_key(cache: dict, u: str):
    """The actual key under which ``u``'s page is cached, tolerant to the same
    normalization drift ``_cache_entry`` handles (trailing punctuation,
    localhost<->127.0.0.1). Returns the key string or None. Used to group
    citation occurrences by the ONE page they point at."""
    for k in (u, u.rstrip("`.,;:!?)"),
              u.replace("127.0.0.1", "localhost"),
              u.replace("localhost", "127.0.0.1")):
        if k in cache:
            return k
    return None


def _pof_occurrence_ok(md: str, offset: int, u: str, page_set: set,
                       page_tris: set, w, chrome: set, threshold: float,
                       span_len: int) -> tuple[bool, float, bool, bool]:
    """Evaluate ONE citation occurrence: does the 400 chars of prose BEFORE the
    citation site (labels + bare URLs stripped) verbatim-appear on the cited
    page? Returns (ok, cover, span_ok, empty_context). Same verbatim judge as
    the incumbent (IDF-weighted containment >= threshold AND a non-boilerplate
    contiguous span_len-token run present on the page); only the anchor moved
    from the markdown link to the extractor-reported citation offset."""
    raw_ctx = md[max(0, offset - 400): offset]
    try:
        from src.verifiers.citation_format import (
            BARE_URL_RE as _CITED_BARE_URL_RE,
            replace_markdown_links,
        )
        raw_ctx = replace_markdown_links(raw_ctx, " ")  # label REMOVED (G-F1)
        raw_ctx = _CITED_BARE_URL_RE.sub(" ", raw_ctx)
    except Exception:
        raw_ctx = LINK_RE.sub(" ", raw_ctx)
        raw_ctx = BARE_URL_RE.sub(" ", raw_ctx)
    ctx_seq = _tokens(norm(raw_ctx))
    # the cited URL's own slug tokens are the page title by construction:
    # pasting the slug as prose next to the link must not count as proof
    # of reading (G-F1 residual, verify pass)
    slug_toks = set(_tokens(norm(re.sub(r"[/\-_.]", " ", u.split("://")[-1]))))
    kept = [t for t in set(ctx_seq)
            if (_is_numeric_tok(t) or (t not in STOPWORDS and t not in chrome))
            and t not in slug_toks]
    if not kept:
        return False, 0.0, False, True
    total = sum(w(t) for t in kept)
    hit = sum(w(t) for t in kept if t in page_set)
    cover = hit / total if total else 0.0
    span_ok = True
    if len(ctx_seq) >= span_len:
        span_ok = False
        for i in range(len(ctx_seq) - span_len + 1):
            tri = tuple(ctx_seq[i:i + span_len])
            if all(not _is_numeric_tok(t) and (t in STOPWORDS or t in chrome)
                   for t in tri):
                continue  # an all-stopword/chrome span proves nothing
            if tri in page_tris:
                span_ok = True
                break
    return (cover >= threshold and span_ok), cover, span_ok, False


def score_proof_of_fetch(md: str, cache: dict, page_stats: dict | None = None,
                         threshold: float = POF_THRESHOLD_DEFAULT,
                         span_len: int = 3) -> tuple[float, dict]:
    """axis 1b (VERBATIM-EVIDENCE LOWER BOUND): for each DISTINCT cited page,
    does the report verbatim-reproduce that page's text next to at least one of
    its in-text citations? (E-3/E-4 rebuild.)

    Two structural fixes over the incumbent (audit E-3 §6):

    1. Citation extraction is shared with reachability via
       ``citation_format.extract_citations`` instead of the markdown-only
       ``LINK_RE``. 59% of cited-URL occurrences on the panel are non-markdown
       (numbered ``[N]``, bare, footnote); the old scanner saw ``checked=0`` for
       every numbered-citation agent (LDR/STORM) and returned 0.0 despite a
       62-83% page-level read rate. ``source``/``bullet`` reference-list forms
       are counted as CITED but are not evidence anchors (their context is the
       entry's own title, E-3 §6.3); the in-text markers are.

    2. Aggregation is PAGE-LEVEL any-occurrence, not per-marker averaging: a
       page passes if ANY of its citation sites carries verbatim evidence. The
       old per-marker mean diluted a page cited many times (a `[7]` repeated in
       enumerations) down to the single marker that hugged the quote; the read
       signal is "was this page demonstrably read", once per page (E-3 §2.3).

    Denominator = distinct cited pages that resolve to a cached status-200 entry
    (a cited page with no cached text is undecidable and excluded, as before);
    numerator = those with >=1 IN-TEXT occurrence whose 400-char preceding
    context (labels + bare URLs stripped) verbatim-matches the page. A page cited
    ONLY from a reference list (no in-text anchor) is checked-and-failed: a bare
    bibliography URL is not proof of having read it. Reference-region markers
    (``[N]`` entry heads, ``[^id]:`` footnote-definition lines, anything under a
    References/Sources/Bibliography heading) are NOT evidence anchors (audit F1 /
    D4): their preceding 400 chars are the previous bibliography entry, so
    anchoring on them let entry N's snippet "bleed" onto entry N+1's page. They
    still count for reachability and the denominator; see
    ``_reference_region_offsets``.

    SEMANTICS (what this number is and is NOT). This is a VERBATIM LOWER BOUND on
    grounding, not citation support and not equivalent to it. It fires only on
    lexical overlap that is literally present in the evaluator-fetched page; a
    faithful report that PARAPHRASES the page it read is a MISS here even though
    it is well grounded (order-preserving paraphrase still passes 82-86%, E-4 §2,
    but genuine rephrasing below that band is silently missed). The paraphrase
    miss rate on real agent prose is UNMEASURED (task #56); until it is measured,
    read this axis strictly as "the report reproduces page text verbatim next to
    a citation", a floor beneath true grounding, never as "the citation is
    supported". When there is no transport evidence this number is stamped
    ``pof_semantics="text_v1"`` and surfaced under the axis name
    ``grounding_quote_support`` (see ``_axis_key``): it does not observe whether
    the agent opened anything, so it must not wear the proof-of-fetch name.

    Verbatim judge (unchanged, still deterministic / model-free): IDF-weighted
    containment (weight 1/log(2+page_df) when a df table exists, else 1) >=
    ``threshold`` AND at least one non-boilerplate contiguous ``span_len``-token
    run appearing verbatim in the FULL page token stream (G-F4). Semantic
    grounding is carried by the reach gate, not this axis.

    threshold=0.35 is calibrated in data/results/pof_gamma_calibration.json
    (scripts/calibrate_pof_gamma.py). The calibration covers EVERY shipped anchor
    format, not just markdown (D5): per-format, 160 verbatim positives + 160
    fabricated + 160 cross-page negatives at threshold 0.35 hold

        format    TPR    FPR_fabricated  FPR_cross-page  FPR_bib-bleed
        markdown  1.000  0.000           0.000           -
        numbered  1.000  0.000           0.000           0.000
        footnote  1.000  0.000           0.013           0.000
        bare      1.000  0.000           0.006           -
        page_agg  0.981  0.000           0.000           -

    (page_agg = page-level any-occurrence; bib-bleed = the D4 cross-entry
    reference structure, 160 numbered + 160 footnote items -- 0.000 post-fix vs
    1.000 pre-fix). The span requirement carries the separation, so TPR is flat
    over the 0.15-0.60 grid and 0.35 is retained mid-plateau. The legacy
    markdown-only figure (TPR=1.000, FPR 0.000/0.006) is the ``markdown`` row."""
    stats = page_stats if page_stats is not None else build_page_stats(cache)
    df, chrome = stats.get("df"), stats.get("chrome", set(CHROME_FALLBACK))

    def w(t: str) -> float:
        if df:
            return 1.0 / math.log(2 + df.get(t, 0))
        return 1.0

    # (a) collect every citation site, group by the ONE cached-200 page it
    # points at. `cited_keys` is the denominator (distinct cited pages with
    # text); `evidence_by_key` holds only the in-text anchor occurrences.
    try:
        from src.verifiers.citation_format import extract_citations, strip_url_trail
        cits = [(strip_url_trail(c.raw_url), c.char_offset, c.style)
                for c in extract_citations(md, sandbox_only=False)]
    except Exception:
        cits = [(m.group(2).rstrip(".,;"), m.start(), "markdown")
                for m in LINK_RE.finditer(md)]

    # Reference-list / bibliography spans (audit F1 / D4): a marker inside one
    # is a bibliography row, not an in-text claim, so it counts for the
    # denominator (CITED) but never as an evidence anchor (numerator).
    ref_spans = _reference_region_offsets(md)

    cited_keys: dict[str, str] = {}   # cache_key -> a representative raw url
    evidence_by_key: dict[str, list[tuple[int, str]]] = {}
    for u, off, style in cits:
        k = _resolve_cache_key(cache, u)
        if k is None:
            continue
        entry = cache.get(k)
        try:
            st = int((entry or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            st = 0
        if st != 200:
            continue
        cited_keys.setdefault(k, u)
        if style in POF_EVIDENCE_STYLES and not _offset_in_spans(off, ref_spans):
            evidence_by_key.setdefault(k, []).append((off, u))

    # (b) score each distinct cited page: pass on ANY in-text occurrence.
    page_cache: dict[str, tuple[set, set]] = {}
    checked = passed = 0
    per = []
    for k, rep_url in cited_keys.items():
        entry = cache.get(k)
        if k not in page_cache:
            page_seq = _tokens(norm(strip_html((entry or {}).get("text", ""))))
            tris = {tuple(page_seq[i:i + span_len])
                    for i in range(len(page_seq) - span_len + 1)}
            page_cache[k] = (set(page_seq), tris)
        page_set, page_tris = page_cache[k]
        occ = evidence_by_key.get(k, [])
        checked += 1
        if not occ:
            per.append({"url": rep_url[-60:], "cover": 0.0, "span_ok": False,
                        "passed": False, "n_occ": 0, "reason": "no_inline_anchor"})
            continue
        best_cover, page_ok, any_span = 0.0, False, False
        for off, u in occ:
            ok, cover, span_ok, _empty = _pof_occurrence_ok(
                md, off, u, page_set, page_tris, w, chrome, threshold, span_len)
            best_cover = max(best_cover, cover)
            any_span = any_span or span_ok
            if ok:
                page_ok = True
                break
        passed += page_ok
        per.append({"url": rep_url[-60:], "cover": round(best_cover, 3),
                    "span_ok": any_span, "passed": bool(page_ok),
                    "n_occ": len(occ)})
    pof_score = passed / checked if checked else 0.0
    pof_det = {
        "checked": checked, "passed": passed, "threshold": threshold,
        "df_pages": stats.get("n_pages", 0),
        "aggregation": "page_level_any_occurrence", "per": per[:12]}
    if pof_score == 0.0:
        # A scored 0 is either "no cited page had cached text to verify against"
        # (nothing to check) or "cited pages were checked and none carried
        # verbatim evidence". Both are genuine, observed zeros -- name which.
        pof_det["reason"] = "no_citable_pages" if checked == 0 else "no_quote_support"
    return pof_score, pof_det


# ---------------------------------------------------------------------------
# Axis 2: fact support (structured, decidable)
# ---------------------------------------------------------------------------

def _fact_entities(answer_key, generic: set) -> tuple[dict, dict, dict]:
    """Entity-specific DB truth plus URL/name indexes.

    The old index key was the first six distinctive name tokens.  Real catalog
    variants routinely share that prefix and have different prices, so their
    truth sets were merged: stating variant A's exact DB price could bind to B,
    or any value from either variant could be accepted for both.  Keep identity
    per relevant-set row and treat an unresolved collision as unbound.
    """
    from src.verifiers.citation_format import canonicalize_url

    entities: dict[int, dict] = {}
    url_to_ids: dict[str, set[int]] = {}
    name_to_ids: dict[str, set[int]] = {}
    for idx, e in enumerate(answer_key.relevant_set):
        if not getattr(e, "relevant", True):
            continue
        facts = e.facts or {}
        prices, ratings = set(), set()
        for fk in ("price", "special_price"):
            if facts.get(fk) is not None:
                try:
                    prices.add(round(float(facts[fk]), 2))
                except (TypeError, ValueError):
                    pass
        if facts.get("rating") is not None:
            try:
                ratings.add(float(facts["rating"]))
            except (TypeError, ValueError):
                pass
        canon = canonicalize_url(e.url)
        entities[idx] = {
            "id": idx, "url": e.url, "canonical_url": canon,
            "name": e.name, "tokens": _name_tokens(e.name, generic),
            "prices": prices, "ratings": ratings,
        }
        if canon:
            url_to_ids.setdefault(canon, set()).add(idx)
        name_to_ids.setdefault(norm(e.name), set()).add(idx)

    # Nugget facts are authoritative too.  Attach by source URL first, then by
    # exact full name.  Never attach a fact through a six-token fuzzy key.
    for nug in (list(answer_key.vital_nuggets) + list(answer_key.useful_nuggets)):
        if not getattr(nug, "relevant", True) or nug.predicate not in {"price", "rating"}:
            continue
        ids = set()
        if getattr(nug, "source_url", None):
            ids = url_to_ids.get(canonicalize_url(nug.source_url), set())
        if not ids:
            ids = name_to_ids.get(norm(nug.subject), set())
        try:
            value = float(nug.object)
        except (TypeError, ValueError):
            continue
        for idx in ids:
            if nug.predicate == "price":
                entities[idx]["prices"].add(round(value, 2))
            else:
                entities[idx]["ratings"].add(value)
    return entities, url_to_ids, name_to_ids


def _fact_mentions(text: str, entities: dict[int, dict]) -> dict[int, dict]:
    """Candidate entity mentions in visible prose, exact full names first."""
    mentions: dict[int, dict] = {}
    for idx, ent in entities.items():
        # Cheap gate before the regex: an exact full-name match needs every
        # identity token as a substring, and a fuzzy match needs a majority.
        # Sentences are ~100 chars and candidates number in the hundreds, so
        # `in` here removes almost every `finditer` call. Semantics unchanged:
        # a token absent as a substring cannot match with word boundaries.
        fuzzy = ent.get("fuzzy_toks")
        if fuzzy is None:
            fuzzy = [t for t in ent["tokens"] if not t.isdigit()][:8]
            ent["fuzzy_toks"] = fuzzy
        anchor = ent.get("anchor_tok")
        if anchor is None:
            toks_all = ent["tokens"]
            anchor = max(toks_all, key=len) if toks_all else ""
            ent["anchor_tok"] = anchor
        if anchor and anchor not in text:
            # The longest (rarest) identity token is absent, so the exact full
            # name cannot match. The fuzzy path needs a majority of the fuzzy
            # tokens; count them with plain substring tests before paying for
            # regex spans. `need` mirrors _subject_discussed exactly.
            if not fuzzy:
                continue
            need = min(len(fuzzy), max(2, (len(fuzzy) + 1) // 2))
            if sum(t in text for t in fuzzy) < need:
                continue
        exact = _exact_subject_spans(text, ent["name"])
        if exact:
            mentions[idx] = {
                "spans": exact, "exact": True, "coverage": 1.0,
                "specificity": len(re.findall(r"[a-z0-9]+", ent["name"].lower())),
            }
            continue
        # Abbreviations remain matchable, but only through a short distinctive
        # signature.  Equal candidates stay ambiguous in `_nearest_fact_entity`.
        # Numeric-only tokens are useful in a complete exact title, but they
        # are unsafe fuzzy identity anchors.  A claim value such as ``$5.20``
        # otherwise makes every unrelated ``5-pound`` product look like the
        # closest subject, and pack counts can do the same.  Alphanumeric model
        # identifiers (for example ``wh1000xm4``) remain eligible.  If removing
        # size/count digits makes two variants indistinguishable, leaving the
        # claim unbound is safer than assigning it to the wrong product.
        toks = fuzzy
        if not toks or not _subject_discussed(text, toks):
            continue
        spans = _token_spans(text, toks)
        present = sum(t in text for t in toks)
        if spans:
            mentions[idx] = {
                "spans": spans, "exact": False,
                "coverage": present / len(toks), "specificity": present,
            }
    return mentions


def _nearest_fact_entity(mentions: dict[int, dict], pos: int,
                         window: int = BIND_WINDOW):
    """Bind a value to one entity; an equal best collision is unbound."""
    best_rank = None
    winners: set[int] = set()
    for idx, hit in mentions.items():
        for s, e in hit["spans"]:
            d = 0 if s <= pos <= e else min(abs(pos - e), abs(s - pos))
            if d > window:
                continue
            # A value belongs to the closest mentioned entity.  Putting name
            # specificity ahead of distance made a long product title steal a
            # price written immediately after a shorter product later in the
            # same sentence or table row.
            rank = (-d, int(hit["exact"]), hit["coverage"], hit["specificity"])
            if best_rank is None or rank > best_rank:
                best_rank, winners = rank, {idx}
            elif rank == best_rank:
                winners.add(idx)
    return next(iter(winners)) if len(winners) == 1 else None


def _mask_numbers_in_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Product-name numbers are identity, never report claim values."""
    if not spans:
        return text
    chars = list(text)
    for s, e in spans:
        for i in range(max(0, s), min(len(chars), e)):
            if chars[i].isdigit():
                chars[i] = " "
    return "".join(chars)


def score_fact_support(md: str, answer_key, generic: set | None = None,
                       k_f: int = K_F_DEFAULT) -> tuple[float, dict]:
    """axis 2 (structured, decidable): extract the price/rating claims the
    report EXPLICITLY makes about DB entities and check each against DB truth.

    What this axis measures, and what it does NOT (P2 construct honesty):
    it scores only CHECKABLE STRUCTURED CLAIMS the report explicitly makes about
    DB entities (a price or an overall rating bound to a named product). It is
    NOT a prose-quality axis: a fluent, well-organized report that never asserts
    a checkable price or rating makes zero testable claims and scores 0.0. That
    zero is BY DESIGN, not a bug: on the qwen backbone only 2/140 reports made
    any checkable claim, so `fact` (the largest 0.39 quality weight) is inert on
    ~98.6% of reports and `truth` there is driven by pof + completeness. The
    `fact_active` flag in the detail (== claims_tested > 0) is what a board reads
    to publish that inertness instead of leaving it buried in a doc.

    Volume-aware F1 (M-C3/G-F7: silence must not score):
        precision  = supported / tested
        recall_vol = min(distinct_task_scoped_supported / K_f, 1)
        fact       = harmonic mean (0 if either is 0)
    tested == 0 returns 0.0 with detail reason "no_checkable_claims" and
    fact_active == False: a report that asserts nothing checkable earns nothing
    (the old `else 1.0` gave a perfect score for silence).

    Claim extraction is hardened per G-F6: price triggers only with a "$" or
    price-word cue within 12 chars; unit-suffixed numbers are measurements;
    subject-number binding only within +-40 chars of a subject identity token
    in the same sentence; aspect-qualified ratings ("5 stars for build") are
    not overall-rating claims. special_price counts as an alternative correct
    price. Formal v2 keys require an inline citation to the same product in the
    claim sentence before a correct claim can fill recall; uncited or detached
    correct values remain visible in precision diagnostics but earn no volume
    credit."""
    from src.verifiers.citation_format import (
        canonicalize_url,
        extract_citations,
        iter_markdown_links,
    )

    generic = generic if generic is not None else build_generic_tokens(answer_key)
    entities, url_to_ids, _name_to_ids = _fact_entities(answer_key, generic)
    support = contra = unbound = untestable = skipped_aspect = duplicate_claims = 0
    supported_out_of_scope = supported_uncited = 0
    supported_fact_ids: set[tuple[int, str]] = set()
    seen_claims: set[tuple] = set()
    # ``relevant_set`` is a category enumeration (often ~1,900 products), not
    # a task-specific gold set.  Crediting any ten correct catalog prices lets
    # a report ignore the user's actual question and still fill fact recall.
    # The task-ranked sentiment/price/rating nuggets identify the products for
    # which structured facts can buy recall.  Correct facts about other catalog
    # items remain precision-tested, but they cannot fill the volume term.
    creditable_urls = {
        canonicalize_url(n.source_url)
        for n in (list(answer_key.vital_nuggets) + list(answer_key.useful_nuggets))
        if getattr(n, "relevant", True)
        and n.predicate in {"buyer_sentiment", "price", "rating"}
        and getattr(n, "source_url", None)
    }
    creditable_ids = {
        idx for idx, ent in entities.items()
        if ent.get("canonical_url") in creditable_urls
    }
    # Backward compatibility for small/manual answer keys that contain no
    # task-ranked structured nuggets: their declared relevant_set is the only
    # available scope and remains fully creditable.
    if not creditable_ids:
        creditable_ids = set(entities)
    require_inline_citation = bool(
        (getattr(answer_key, "metadata", {}) or {}).get(
            "inline_fact_citation_required", False
        )
    )
    ref_spans = _reference_region_offsets(md)
    inline_citations: list[tuple[int, set[int]]] = []
    cited_fact_ids: set[int] = set()
    if require_inline_citation:
        for citation in extract_citations(md, sandbox_only=False):
            if (citation.style not in POF_EVIDENCE_STYLES
                    or _offset_in_spans(citation.char_offset, ref_spans)):
                continue
            ids = set(url_to_ids.get(canonicalize_url(citation.raw_url), set()))
            cited_fact_ids.update(ids)
            inline_citations.append((citation.char_offset, ids))
    else:
        cited_fact_ids = set(entities)
    per = []
    # Doc-level entity prefilter. `_fact_mentions` used to scan all ~1,600
    # catalog entities on EVERY sentence; a sentence cannot mention an entity
    # whose identity tokens never appear anywhere in the document, so filter the
    # candidate set once against the whole visible prose. Superset-safe: the
    # doc prose is the concatenation of the per-sentence prose this loop feeds
    # `_fact_mentions`, so anything matchable in a sentence survives the filter.
    _all_spans = list(_sentence_spans(md))
    _doc_low = "\n".join(_visible_prose(t) for t, _a, _b in _all_spans)
    _cand = {}
    for _idx, _ent in entities.items():
        if _exact_subject_spans(_doc_low, _ent["name"]):
            _cand[_idx] = _ent
            continue
        _toks = [t for t in _ent["tokens"] if not t.isdigit()][:8]
        if _toks and _subject_discussed(_doc_low, _toks):
            _cand[_idx] = _ent
    fact_candidates = _cand

    for sent, sent_start, sent_end in _all_spans:
        sentence_cited_ids = {
            idx
            for offset, ids in inline_citations
            if sent_start <= offset < sent_end
            for idx in ids
        }
        linked_ids: set[int] = set(sentence_cited_ids)
        for link in iter_markdown_links(sent):
            linked_ids.update(url_to_ids.get(canonicalize_url(link.url), set()))
        forced_id = next(iter(linked_ids)) if len(linked_ids) == 1 else None
        claim_cited_ids = sentence_cited_ids if require_inline_citation else set(entities)
        # strip URLs from the prose: slug tokens must not act as subjects.
        # Keep the complete visible label for entity matching.  Masking digits
        # here broke exact matching for real names such as ``7.2`` or
        # ``RP-8000F``; the exact-name spans are masked below before claim-value
        # extraction, which removes those identity digits without destroying
        # the entity binding.
        low = _visible_prose(sent)
        if not low:
            continue
        mentions = _fact_mentions(low, fact_candidates)
        # Plain-text product titles can themselves contain "$900-$1000",
        # pack counts, years, sizes, and model numbers.  Find their spans first,
        # then mask those identity digits before value extraction.
        exact_spans = [sp for hit in mentions.values() if hit["exact"]
                       for sp in hit["spans"]]
        claim_text = _mask_numbers_in_spans(low, exact_spans)

        def record(idx, predicate: str, raw_value: str, value: float, targets: set):
            nonlocal support, contra, duplicate_claims, supported_out_of_scope
            nonlocal supported_uncited
            claim_id = (idx, predicate, round(value, 4))
            if claim_id in seen_claims:
                duplicate_claims += 1
                return
            seen_claims.add(claim_id)
            ok = (_price_close(value, targets) if predicate == "price"
                  else any(abs(value - t) <= RATING_TOL for t in targets))
            in_scope = idx in creditable_ids
            if ok and not in_scope:
                # Ruling #3 (docs/SPEC_DECISIONS.md): a CORRECT fact about a
                # product OUTSIDE the task-ranked scope is moved out of `tested`
                # entirely -- it neither buys precision (numerator) nor dilutes
                # it (denominator). Crediting off-topic correct catalog rows let
                # a report water down a low precision with easy true facts while
                # a sparse but fully-correct in-scope report lost. An
                # out-of-scope ERROR still counts as a contradiction (fabricated
                # evidence stays fabricated); only the correct off-scope claim is
                # withdrawn. Kept observable via supported_out_of_scope.
                supported_out_of_scope += 1
                per.append((entities[idx]["name"][:36], predicate, raw_value,
                            sorted(targets), "OK-oos"))
                return
            support += bool(ok)
            contra += not ok
            if ok:
                # in_scope is guaranteed here (out-of-scope correct returned
                # above). Recall is over gold FACT identities, not numeric
                # phrasings: otherwise one product priced at 1769 could be
                # repeated as ten slightly different values inside the 1%
                # tolerance and single-handedly fill K_f.
                if idx in claim_cited_ids:
                    supported_fact_ids.add((idx, predicate))
                else:
                    supported_uncited += 1
            per.append((entities[idx]["name"][:36], predicate, raw_value,
                        sorted(targets), "OK" if ok else "X"))

        # price claims
        for m in _NUM_RE.finditer(claim_text):
            if not _standalone_number(claim_text, m.start(), m.end()):
                continue
            prefix = claim_text[max(0, m.start() - 8):m.start()]
            if re.search(r"(?:/\s*|out\s+of\s+)$", prefix):
                continue  # denominator in ``4.2/5``, never a price
            if _UNIT_AFTER.match(claim_text[m.end():]):
                continue
            cue_win = claim_text[max(0, m.start() - PRICE_CUE_WINDOW):
                                 m.end() + PRICE_CUE_WINDOW]
            if "$" not in cue_win and not _PRICE_CUE.search(cue_win):
                continue
            idx = _nearest_fact_entity(mentions, m.start())
            # A unique markdown link is an exact entity identity.  Prefer it
            # over a fuzzy token collision, while still allowing a second
            # explicitly named product in the same sentence to own its nearby
            # value.  This prevents generic words from a long link label (and
            # the value itself) from binding the claim to another catalog row.
            if forced_id is not None and (
                idx is None or not mentions.get(idx, {}).get("exact", False)
            ):
                idx = forced_id
            if idx is None:
                idx = forced_id
            if idx is None:
                unbound += 1
                continue
            targets = entities[idx]["prices"]
            if not targets:
                untestable += 1
                continue
            try:
                val = round(float(m.group().replace(",", "")), 2)
            except ValueError:
                continue
            record(idx, "price", m.group(), val, targets)

        # overall-rating claims
        for m in _RATING_CLAIM.finditer(claim_text):
            idx = _nearest_fact_entity(mentions, m.start())
            if forced_id is not None and (
                idx is None or not mentions.get(idx, {}).get("exact", False)
            ):
                idx = forced_id
            if idx is None:
                idx = forced_id
            if idx is None:
                unbound += 1
                continue
            hit = mentions.get(idx)
            span = None
            if hit:
                near = [(abs(m.start() - e), (s, e)) for s, e in hit["spans"]]
                span = min(near)[1] if near else None
            if span is None:
                span = (m.start(), m.end())
            # aspect qualifier between the number and the subject anchor, or
            # attached right after the stars phrase ("5 stars for build")?
            lo = min(m.end(), span[1])
            hi = max(m.start(), span[0])
            between = claim_text[lo:hi] if lo < hi else ""
            trailing = claim_text[m.end(): m.end() + 24]
            if _ASPECT_QUALIFIER.search(between) or _ASPECT_QUALIFIER.search(trailing):
                skipped_aspect += 1
                continue
            targets = entities[idx]["ratings"]
            if not targets:
                untestable += 1
                continue
            val = float(m.group(1))
            record(idx, "rating", m.group(1), val, targets)

    tested = support + contra
    detail = {
        "claims_tested": tested, "supported": support, "contradicted": contra,
        "unbound": unbound, "untestable": untestable,
        "skipped_aspect_rating": skipped_aspect,
        "duplicate_claims_ignored": duplicate_claims, "k_f": k_f,
        "creditable_entity_count": len(creditable_ids),
        "inline_citation_required": require_inline_citation,
        "cited_creditable_entity_count": len(creditable_ids & cited_fact_ids),
        "supported_uncited": supported_uncited,
        "supported_out_of_scope": supported_out_of_scope,
        "distinct_supported_facts": len(supported_fact_ids),
        # fact_active: did this report make ANY checkable structured claim? When
        # False the 0.39 fact weight contributed nothing to truth. A board reads
        # this per report to publish fact's EFFECTIVE (not nominal) weight; see
        # scripts/analysis/fact_axis_report.py.
        "fact_active": tested > 0,
        "sample": per[:12],
    }
    if tested == 0:
        detail["reason"] = "no_checkable_claims"
        detail["precision"] = 0.0
        detail["recall_vol"] = 0.0
        return 0.0, detail
    precision = support / tested
    # False claims lower precision but NEVER buy recall/volume.  Volume is the
    # number of distinct correct structured facts the report actually supplied.
    recall_vol = min(len(supported_fact_ids) / k_f, 1.0)
    detail["precision"] = round(precision, 4)
    detail["recall_vol"] = round(recall_vol, 4)
    if precision <= 0.0 or recall_vol <= 0.0:
        # Claims WERE tested (tested>0) but the axis is still 0. Distinguish
        # "every claim contradicted / none supported" (precision 0) from "no
        # distinct task-scoped supported fact filled the volume term"
        # (recall_vol 0), so this zero is never mistaken for silence.
        detail["reason"] = ("no_supported_claims" if precision <= 0.0
                            else "no_recall_volume")
        return 0.0, detail
    return 2 * precision * recall_vol / (precision + recall_vol), detail


# ---------------------------------------------------------------------------
# Axis 3: completeness (single, saturating implementation)
# ---------------------------------------------------------------------------

def build_vital_pool(answer_key, k_star: int = K_STAR_DEFAULT,
                     pool_size: int | None = None) -> list:
    """Rank the relevant vital nuggets into the pool completeness is scored
    against (T1/T3).

    Importance ranking: entity weight desc, then price-tier spread (round-robin
    across the price quartiles of the relevant product set, plus a no-price
    tier for threads/articles, so the pool covers every price tier instead of
    only the popularity head), then rating-adjusted salience
    rating * log(1 + review_count) as the within-tier tie-break.

    pool_size defaults to 3*k_star: a report saturates completeness by
    covering any k_star of the top-ranked 3*k_star vital facts."""
    pool_size = pool_size if pool_size is not None else 3 * k_star
    ents = {e.url: e for e in answer_key.relevant_set}
    prices = sorted(
        float(e.facts["price"])
        for e in answer_key.relevant_set
        if getattr(e, "relevant", True) and e.category == "shopping_product"
        and (e.facts or {}).get("price") is not None
    )
    cuts = ([prices[len(prices) // 4], prices[len(prices) // 2],
             prices[(3 * len(prices)) // 4]] if prices else [])
    tiers: dict[int, list] = {i: [] for i in range(5)}
    for seq, n in enumerate(answer_key.vital_nuggets):
        if not getattr(n, "relevant", True):
            continue
        e = ents.get(n.source_url)
        weight = float(getattr(e, "weight", 0.5)) if e else 0.5
        facts = (e.facts if e else {}) or {}
        try:
            rating = float(facts.get("rating") or 0.0)
        except (TypeError, ValueError):
            rating = 0.0
        try:
            rc = float(facts.get("review_count") or facts.get("comment_count") or 0.0)
        except (TypeError, ValueError):
            rc = 0.0
        salience = rating * math.log1p(max(rc, 0.0))
        tier = 4
        if e is not None and e.category == "shopping_product" and cuts:
            try:
                tier = bisect.bisect_right(cuts, float(facts.get("price")))
                tier = min(tier, 3)
            except (TypeError, ValueError):
                tier = 4
        tiers[tier].append((-weight, -salience, seq, n))
    for t in tiers:
        tiers[t].sort(key=lambda x: x[:3])
    pool, idx = [], {t: 0 for t in tiers}
    while len(pool) < pool_size:
        progressed = False
        for t in range(5):
            if idx[t] < len(tiers[t]) and len(pool) < pool_size:
                pool.append(tiers[t][idx[t]][3])
                idx[t] += 1
                progressed = True
        if not progressed:
            break
    return pool


# The verbatim judge reads the 400 chars of prose BEFORE a citation (see
# ``md[max(0, offset - 400): offset]`` in ``_pof_occurrence_ok``). A quote must
# reach that far to fill the window with page text; the oracle's forum-slot guard
# uses it to skip a thread quote too short to ground. Concept STUB detection does
# NOT use this length (a short but content-bearing page still grounds): it uses
# the grounding-based ``_concept_page_is_stub`` instead.
MIN_GROUNDABLE_QUOTE_CHARS = 400


def _page_quote(text: str, *, n_words: int = 90, skip_head: int = 12) -> str:
    """A verbatim, content-bearing run of words from a cached page, usable as a
    grounding quote.

    The verbatim judge reads the 400 chars of prose BEFORE the citation and
    requires (a) IDF-weighted containment of that context in the page and (b) a
    contiguous 3-token run present verbatim on the page. Two things dilute (a):
    tokens from a NEIGHBOUR line bleeding into the 400-char window, and glue
    words not on the page. So the oracle emits ~90 words (~600 chars) of pure
    page text with no glue before the citation. Words are drawn from the same
    ``strip_html`` stream the scorer tokenises, so trigrams line up after
    normalisation. A short real page yields its whole body -- exactly what a
    report could quote -- so its length is the ceiling on any groundable quote."""
    words = strip_html(text or "").split()
    if not words:
        return ""
    if len(words) <= n_words:
        return " ".join(words)
    start = skip_head if len(words) > skip_head + n_words else 0
    return " ".join(words[start:start + n_words])


def _concept_page_is_stub(source_url: str, cache: dict, registry=None,
                          page_stats: dict | None = None) -> bool:
    """Whether this concept's source page is cached but ungroundable by ANY report.

    The page IS cached (status 200 + text), yet even the MAXIMAL report a perfect
    agent could write for it -- its own body verbatim immediately before the
    citation, with NO neighbour line to dilute the 400-char window -- still fails
    the scorer's grounding judge. The canonical instance is a title-only capture
    ("Input lag Input lag"): every token is the page's own title/slug, which the
    judge strips as non-evidence (repeating a page's title proves no read; see
    ``_pof_occurrence_ok``'s ``slug_toks`` removal), leaving the containment
    context empty so no citation can ever ground. Such a slot is coverable by NO
    report, so per docs/SPEC_DECISIONS.md '车道追加条目' (分母只含"存在某报告能覆盖"的槽位)
    it is excised from the completeness denominator at pool construction.

    Decided by the SCORER's own grounding path (``_concept_quote_supported`` run
    on the ideal isolated report), NOT a page-length heuristic: a SHORT but
    content-bearing page (a 100-char definition) still grounds in isolation and
    is NOT a stub. Returns False when the page is not cached -- the instrument-
    blind case, handled by the diagnostic withhold, not here."""
    target = _page_identity(source_url, registry)
    entry = None
    for k, v in (cache or {}).items():
        if _page_identity(k, registry) != target:
            continue
        try:
            status = int((v or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        if status == 200 and (v or {}).get("text"):
            entry = v
            break
    if entry is None:
        return False
    # The best any report can do for this page: the page's own text right before
    # the citation, nothing else to bleed off-page tokens into the window. If even
    # this cannot ground, the slot is uncoverable by construction.
    ideal = f"{_page_quote(entry['text'])} [source]({source_url})"
    supported, cache_present = _concept_quote_supported(
        ideal, source_url, cache, page_stats, registry)
    return bool(cache_present and not supported)


def stub_concept_slots(pool: list, cache: dict, registry=None,
                       page_stats: dict | None = None) -> list:
    """The concept nuggets in ``pool`` whose source page is cached but ungroundable
    by any report (see ``_concept_page_is_stub``): excised from the completeness
    denominator at pool construction and recorded in the manifest. Empty when
    ``cache`` is falsy -- no evidence with which to classify a stub."""
    if not cache:
        return []
    return [n for n in pool
            if getattr(n, "predicate", "") == "concept_coverage"
            and _concept_page_is_stub(
                getattr(n, "source_url", ""), cache, registry, page_stats)]


def _typed_value_in_window(win: str, n, alt_prices=(), tail: str = "") -> bool:
    """Per-predicate typed value check inside a subject window (M-H2: NO
    global substring matching anywhere).

    ``tail`` is the handful of characters that FOLLOW the window in the
    underlying text. It is consulted ONLY by the count-noun guard below (the
    +-40 slice can cut "5 reviews" to "5 rev", hiding the count noun from the
    guard and letting the count pass as a rating again); no value is ever
    extracted from it, so it can only remove credit, never add it."""
    if n.predicate == "price":
        try:
            targets = {round(float(n.object), 2)} | set(alt_prices)
        except (TypeError, ValueError):
            return False
        for m in _NUM_RE.finditer(win):
            if not _standalone_number(win, m.start(), m.end()):
                continue
            if _UNIT_AFTER.match(win[m.end():]):
                continue
            # ``_NUM_RE`` deliberately treats a thousands-formatted amount as
            # one token.  Normalise it here just as the fact extractor does;
            # otherwise an honest ``$1,769.00`` completeness claim raises
            # ValueError instead of being scored.
            if _price_close(round(float(m.group().replace(",", "")), 2), targets):
                return True
        return False
    if n.predicate == "rating":
        try:
            t = float(n.object)
        except (TypeError, ValueError):
            return False
        return any(abs(float(m.group(1)) - t) <= RATING_TOL
                   for m in _RATING_CLAIM.finditer(win))
    if n.predicate == "thread_score":
        try:
            iv = str(int(float(n.object)))
        except (TypeError, ValueError):
            return False
        return any(_standalone_number(win, m.start(), m.end())
                   for m in re.finditer(re.escape(iv), win))
    if n.predicate == "buyer_sentiment":
        # object "57.0%/50rev": covered when the rating (as % or /5 scale) or
        # the review count appears near the subject; the old literal-substring
        # fallback demanded the internal token verbatim, which no natural
        # report emits (verify finding: honest phrasing scored covered=0)
        #
        # The number must be presented AS a rating or AS a review count. Without
        # that, any standalone number within 1.0 of the rating percent covered
        # the nugget: a pure spec sentence ("85 dB", "5 mics", "11 mm drivers")
        # scored buyer sentiment it never conveyed, and `_NUM_RE` had no word
        # boundary, so `SKU-85X` matched too. This mirrors the discipline
        # `_PRICE_CUE` already imposes above, for the same reason.
        #
        # The review COUNT is not the sentiment. 817 of the 1200 buyer_sentiment
        # nuggets carry exactly "12rev", so writing "12 reviews" beside any named
        # product satisfied 68% of them without stating -- or while contradicting
        # -- the sentiment the nugget asserts. The rating branch is sound: 62
        # distinct percentages, and the number must land within 1.0 of the true
        # one, so it cannot be guessed. Only the rating conveys the sentiment.
        m = re.match(r"([\d.]+)%/(\d+)rev", str(n.object))
        if not m:
            return False
        rat = float(m.group(1))
        guard_text = win + tail
        for mm in _LABEL_NUM_RE.finditer(win):
            # Presented as a count ("across 3 reviews"): not a rating, however
            # close it lands to rat or rat/20 (see _COUNT_NOUN_AFTER). The
            # guard reads past the window edge via ``tail`` so a count noun
            # cut by the +-40 slice still classifies its number.
            if _COUNT_NOUN_AFTER.match(guard_text, mm.end()):
                continue
            v = float(mm.group())
            hit_rating = abs(v - rat) <= 1.0 or abs(v - rat / 20.0) <= 0.1
            if hit_rating and _cue_near(win, mm.start(), mm.end(), _RATING_CUE):
                return True
        return False
    if n.predicate == "concept_coverage":
        # subject==concept; upstream _subject_discussed already established
        # the concept is discussed near this window
        return True
    obj = norm(str(n.object))
    return bool(obj) and obj in win


def _page_identity(url: str, registry=None) -> str:
    """One content-page identity, shared by completeness/cache/transport."""
    from src.verifiers.citation_format import canonicalize_url
    if registry is not None:
        try:
            d = registry.classify(url)
            if isinstance(d, dict) and d.get("canonical"):
                return d["canonical"]
        except Exception:
            pass
    return canonicalize_url(url)


def _concept_quote_supported(md: str, source_url: str, cache: dict,
                             page_stats: dict | None = None,
                             registry=None) -> tuple[bool, bool]:
    """Does prose at this concept's citation quote that SAME cached page?

    Returns ``(supported, cache_present)``. ``cache_present`` is False when the
    evaluator holds no usable (status 200 + text) cached copy of this concept's
    source page: the quote CANNOT be verified either way, so the caller must
    WITHHOLD rather than read the resulting False as an uncovered nugget. A
    False with ``cache_present=True`` is a real miss (the page is in cache, the
    prose does not quote it). See G4 and SPEC_ISSUES.
    """
    from src.verifiers.citation_format import extract_citations
    target = _page_identity(source_url, registry)
    entry = cache_key = None
    for k, v in (cache or {}).items():
        if _page_identity(k, registry) == target:
            try:
                status = int((v or {}).get("status", 0) or 0)
            except (TypeError, ValueError):
                status = 0
            if status == 200 and (v or {}).get("text"):
                cache_key, entry = k, v
                break
    if entry is None:
        # Instrument blind: no cached page to compare the prose against.
        return False, False

    ref_spans = _reference_region_offsets(md)
    occ = [(c.char_offset, c.raw_url) for c in extract_citations(md, sandbox_only=False)
           if c.style in POF_EVIDENCE_STYLES
           and not _offset_in_spans(c.char_offset, ref_spans)
           and _page_identity(c.raw_url, registry) == target]
    if not occ:
        return False, True
    stats = page_stats if page_stats is not None else build_page_stats(cache)
    df, chrome = stats.get("df"), stats.get("chrome", set(CHROME_FALLBACK))

    def weight(tok: str) -> float:
        return 1.0 / math.log(2 + df.get(tok, 0)) if df else 1.0

    seq = _tokens(norm(strip_html(entry.get("text", ""))))
    tris = {tuple(seq[i:i + 3]) for i in range(max(0, len(seq) - 2))}
    page_set = set(seq)
    supported = any(_pof_occurrence_ok(
        md, off, raw, page_set, tris, weight, chrome,
        POF_THRESHOLD_DEFAULT, 3)[0] for off, raw in occ)
    return supported, True


def _fetch_mode_none(lane_fetch_mode) -> bool:
    """Ruling #1 (docs/SPEC_DECISIONS.md): a lane that DECLARES it reads no pages
    (`config/lane_protocol.yaml` `fetch_mode: none`, e.g. storm / langchain-odr /
    co-storm) is exempted from completeness's fetch requirement. Its facts are
    legitimately obtained from search snippets, its pof is already 0-honest and
    grounding is metered separately by pof/reach; charging completeness a fetch it
    cannot make by architecture would rank "has a page-read tool", not the answer.
    The exemption reuses the L3 fallback (see `_transport_fetch_usable`): the fetch
    requirement drops and coverage falls back to the cache-quote criterion, exactly
    as an off-shim/damaged run does. `None` means "lane not declared" (default), a
    distinct value from the string `"none"`."""
    return str(lane_fetch_mode) == "none"


def _transport_fetch_usable(evidence) -> bool:
    """Is the run's transport evidence usable to DECIDE whether a page was
    fetched?

    This mirrors, exactly, the gate `fetch_log.transport_metrics` uses to decide
    whether it may emit a real `pof` or must WITHHOLD (available=False): the log
    must exist and be well-formed (`available`), the lane's reads must go through
    the shim (`fetch_observable`), and the log must be neither damaged
    (`write_errors`) nor incomplete (`unattributed_in_window` /
    `unattributed_ambiguous`).

    Why completeness must use THIS, not `evidence.available`: the concept/forum
    fetch requirement demands the source page appear in `fetched_ok`. When the
    instrument cannot observe fetches -- an off-shim lane (fetch_observable=false,
    8/12 lanes), a damaged log, records lost to _unattributed.jsonl -- `fetched_ok`
    is empty or short for a reason that has NOTHING to do with the agent. Gating
    on `available` alone (log merely well-bracketed) then scores an impeccable,
    quoted, in-cache concept as UNCOVERED: `pof` is correctly withheld while
    completeness reads the same blind instrument as a 0. That is the false
    accusation this project keeps re-fixing. When transport is not usable the
    requirement falls back to the cache-quote criterion (the same fallback `pof`
    makes to text_v1), never to a demand the instrument cannot adjudicate.
    Registered as an implementation bug (SPEC_ISSUES, G4).
    """
    return bool(evidence is not None
                and getattr(evidence, "available", False)
                and getattr(evidence, "fetch_observable", True)
                and not getattr(evidence, "write_errors", 0)
                and not getattr(evidence, "unattributed_in_window", 0)
                and not getattr(evidence, "unattributed_ambiguous", 0))


def _forum_coverage_supported(md: str, answer_key, cache: dict,
                              page_stats: dict | None = None,
                              registry=None, evidence=None,
                              snippet_only: bool = False) -> tuple[bool, str | None]:
    """Accept one fetched, quoted and task-relevant forum thread.

    The answer key declares allowed forums plus conservative domain/query terms
    in metadata.  It deliberately does not nominate an automatically retrieved
    thread as factual gold.  A report may choose any real thread in an allowed
    forum, but the cited page must contain task terms and the citation context
    must quote that same cached page.  Formal transport evidence additionally
    proves that the agent fetched it.
    """
    from urllib.parse import unquote, urlparse
    from src.verifiers.citation_format import extract_citations

    meta = getattr(answer_key, "metadata", {}) or {}
    allowed = {str(f).strip().casefold() for f in meta.get("forums", [])
               if str(f).strip()}
    if not allowed or registry is None:
        return False, None
    core = {str(t).strip().lower() for t in meta.get("forum_core_keywords", [])
            if str(t).strip()}
    query = {str(t).strip().lower() for t in meta.get("forum_query_keywords", [])
             if str(t).strip()}
    ref_spans = _reference_region_offsets(md)
    # Gate on transport USABILITY, not merely a well-bracketed log: an off-shim
    # or damaged run has an empty/short fetched_ok for an instrument reason, and
    # requiring the thread there would withhold-then-zero it (see
    # _transport_fetch_usable / G4). A lane that declares fetch_mode:none reads no
    # pages by architecture, so it is exempted too (ruling #1 / _fetch_mode_none).
    require_fetch = _transport_fetch_usable(evidence) and not snippet_only
    fetched = ({_page_identity(u, registry) for u in evidence.fetched_ok}
               if require_fetch else set())

    def term_hit(term: str, doc_tokens: set[str]) -> bool:
        # Small morphology tolerance covers headphone/headphones and
        # battery/batteries without broad substring matching.
        if term in doc_tokens:
            return True
        if len(term) < 5:
            return False
        stem = term[:5]
        return any(len(tok) >= 5 and tok[:5] == stem for tok in doc_tokens)

    for c in extract_citations(md, sandbox_only=False):
        if c.style not in POF_EVIDENCE_STYLES or _offset_in_spans(c.char_offset, ref_spans):
            continue
        try:
            info = registry.classify(c.raw_url)
        except Exception:
            continue
        if (not isinstance(info, dict) or info.get("host_role") != "forums"
                or info.get("kind") != "content" or info.get("in_corpus") is not True):
            continue
        canonical = info.get("canonical") or c.raw_url
        parts = [unquote(p) for p in urlparse(canonical).path.split("/") if p]
        if len(parts) < 3 or parts[0].casefold() != "f" \
                or parts[1].casefold() not in allowed:
            continue
        target = _page_identity(canonical, registry)
        if require_fetch and target not in fetched:
            continue

        entry = None
        for key, candidate in (cache or {}).items():
            if _page_identity(key, registry) != target:
                continue
            try:
                status = int((candidate or {}).get("status", 0) or 0)
            except (TypeError, ValueError):
                status = 0
            if status == 200 and (candidate or {}).get("text"):
                entry = candidate
                break
        if entry is None:
            continue
        doc_tokens = set(re.findall(r"[a-z0-9]+", norm(strip_html(entry["text"]))))
        core_hits = sum(term_hit(t, doc_tokens) for t in core)
        query_hits = sum(term_hit(t, doc_tokens) for t in query)
        relevant = ((core_hits >= 1 and (query_hits >= 1 or not query))
                    or query_hits >= 2)
        if not relevant:
            continue
        if _concept_quote_supported(md, c.raw_url, cache or {}, page_stats, registry)[0]:
            return True, canonical
    return False, None


def _forum_candidate_cached(answer_key, cache: dict, registry=None) -> bool:
    """Diagnostic-mode blind test for the forum slot (docs/SPEC_DECISIONS.md lane
    addendum, forum-slot blind rule): True when the page cache holds at least one
    task-relevant CANDIDATE thread page -- a status-200 forum content page in an
    allowed forum whose text carries the task terms.

    When False, no report could have covered the forum slot for an INSTRUMENT
    reason (no candidate is cached), so a diagnostic build WITHHOLDS the slot from
    the denominator instead of scoring it 0. When True but the report cited no
    qualifying thread, the slot is a REAL miss (stays in the denominator, scores
    0). Mirrors the candidate + relevance predicate of _forum_coverage_supported;
    called only under cache_policy='diagnostic', never in strict scoring, so it
    cannot move a formal number."""
    from urllib.parse import unquote, urlparse

    meta = getattr(answer_key, "metadata", {}) or {}
    allowed = {str(f).strip().casefold() for f in meta.get("forums", [])
               if str(f).strip()}
    if not allowed or registry is None:
        return False
    core = {str(t).strip().lower() for t in meta.get("forum_core_keywords", [])
            if str(t).strip()}
    query = {str(t).strip().lower() for t in meta.get("forum_query_keywords", [])
             if str(t).strip()}

    def term_hit(term: str, doc_tokens: set[str]) -> bool:
        if term in doc_tokens:
            return True
        if len(term) < 5:
            return False
        stem = term[:5]
        return any(len(tok) >= 5 and tok[:5] == stem for tok in doc_tokens)

    for key, candidate in (cache or {}).items():
        try:
            info = registry.classify(key)
        except Exception:
            continue
        if (not isinstance(info, dict) or info.get("host_role") != "forums"
                or info.get("kind") != "content" or info.get("in_corpus") is not True):
            continue
        canonical = info.get("canonical") or key
        parts = [unquote(p) for p in urlparse(canonical).path.split("/") if p]
        if len(parts) < 3 or parts[0].casefold() != "f" \
                or parts[1].casefold() not in allowed:
            continue
        try:
            status = int((candidate or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        if status != 200 or not (candidate or {}).get("text"):
            continue
        doc_tokens = set(re.findall(r"[a-z0-9]+", norm(strip_html(candidate["text"]))))
        core_hits = sum(term_hit(t, doc_tokens) for t in core)
        query_hits = sum(term_hit(t, doc_tokens) for t in query)
        if (core_hits >= 1 and (query_hits >= 1 or not query)) or query_hits >= 2:
            return True
    return False


def score_completeness(md: str, answer_key, k_star: int = K_STAR_DEFAULT,
                       pool_size: int | None = None,
                       generic: set | None = None, cache: dict | None = None,
                       page_stats: dict | None = None, registry=None,
                       evidence=None, lane_fetch_mode=None,
                       cache_policy: str = "strict") -> tuple[float, dict]:
    """axis 3: vital-fact recall over the ranked vital pool (T1/T2/M-H1/H2).

    completeness = covered_vital / min(K_star, |pool|). SATURATION IS THE DESIGN
    INTENT (SAFE's R_K = min(S/K, 1), DRBench's k = |gold| + 5: credit any K_star
    of a larger pool), but it never fires at the pool sizes these tasks actually
    have. Each per-task vital pool holds ~14-17 nuggets, all below K_star=20, so
    the denominator collapses to |pool| and the axis is in practice a CENSUS:
    covering EVERY vital fact the task offers (all 14-17, per task) is what
    scores 1.0 (ruling #5). K_star is retained ONLY as an upper cap on the
    denominator; it does not bind at current pool sizes and can be lowered later
    to restore real saturation without changing today's numbers. Because the
    denominator floats with the task, one vital fact is worth 1/|pool| (1/14 to
    1/17), not a fixed 1/K_star. A focused shortlist that nails every vital fact
    still scores 1.0 and dumping 40 catalog rows still cannot beat it (T1). This
    is the ONLY completeness implementation in the codebase: the checklist
    verifier and the composition must both call it (T2), so the number displayed
    is the number scored.

    A vital fact counts as covered only if the report discusses its subject
    (distinctive identity tokens) AND the typed value appears within the
    +-40 char window of a subject mention, with per-predicate tolerance:
    price 0.02 absolute or 1 percent relative (special_price also accepted),
    rating +-0.15, thread_score exact-in-window. No global substring matching
    anywhere (M-H2). A v2 task that declares forums also contributes one
    virtual completeness slot. It is covered only by a fetched, in-text quoted,
    task-relevant thread from an allowed forum; arbitrary forum URLs and
    reference-list shells earn nothing. Formal v2 keys also require each
    structured nugget's own source page to be cited on the same Markdown line.
    When transport is available, that page must have been fetched as well."""
    # Only text a reader can see may satisfy a nugget.  URL paths contain exact
    # product/concept titles and numbers; leaving them in prose let a citation
    # shell cover facts it never stated.
    text = _visible_prose(md)
    generic = generic if generic is not None else build_generic_tokens(answer_key)
    pool = build_vital_pool(answer_key, k_star=k_star, pool_size=pool_size)
    # docs/SPEC_DECISIONS.md '车道追加条目': a concept whose source page is cached but
    # ungroundable by ANY report (a title-only capture whose whole body is its own
    # slug tokens, which the grounding judge strips as non-evidence -- see
    # _concept_page_is_stub) is uncoverable by construction, a page-cache fixture
    # defect rather than a real gap. It is EXCISED from the vital pool here so the
    # completeness denominator holds only slots some report can cover (分母只含"存在
    # 某报告能覆盖"的槽位). This differs from the diagnostic withhold, which covers a
    # MISSING (uncached) page: excision applies under EVERY cache_policy and fires
    # only with the cache as evidence (an empty cache excises nothing, so the
    # shell/G2 path is unchanged) and only for a page that fails to ground even in
    # isolation (a short but content-bearing page is NOT excised). The excised
    # slots are surfaced in comp_det['excluded_slots'] so the removal is
    # observable, never a silent disappearance.
    excluded_stub = stub_concept_slots(pool, cache or {}, registry, page_stats)
    excluded_slots = [{"subject": getattr(n, "subject", ""),
                       "source_url": getattr(n, "source_url", ""),
                       "reason": "stub_page"} for n in excluded_stub]
    if excluded_stub:
        _stub_urls = {n.source_url for n in excluded_stub}
        pool = [n for n in pool if not (
            getattr(n, "predicate", "") == "concept_coverage"
            and getattr(n, "source_url", "") in _stub_urls)]
    forum_slot = bool((getattr(answer_key, "metadata", {}) or {}).get("forums")) \
        and not any(getattr(n, "predicate", "") == "forum_coverage" for n in pool)
    if not pool and not forum_slot:
        return 0.0, {"pool": 0, "k_star": k_star, "covered": 0,
                     "reason": "empty_vital_pool"}
    ents = {e.url: e for e in answer_key.relevant_set}

    # Require the concept page in fetched_ok ONLY when transport can actually
    # decide it. On an off-shim/damaged/incomplete run (where pof is withheld,
    # not zeroed) this falls back to the cache-quote criterion instead of
    # demanding a fetch the instrument never observed (see _transport_fetch_usable
    # / G4). Was gated on evidence.available, which zeroed impeccable concepts on
    # every fetch_observable=false lane. A lane that DECLARES fetch_mode:none
    # reads no pages by architecture and is exempted too (ruling #1).
    snippet_only = _fetch_mode_none(lane_fetch_mode)
    require_concept_fetch = _transport_fetch_usable(evidence) and not snippet_only
    fetched = ({_page_identity(u, registry) for u in evidence.fetched_ok}
               if require_concept_fetch else set())
    require_nugget_citation = bool(
        (getattr(answer_key, "metadata", {}) or {}).get(
            "inline_nugget_citation_required", False
        )
    )
    inline_cited_pages: set[str] = set()
    cited_line_text: dict[str, list[str]] = {}
    if require_nugget_citation:
        from src.verifiers.citation_format import extract_citations
        ref_spans = _reference_region_offsets(md)
        lines = list(_line_spans(md))
        for c in extract_citations(md, sandbox_only=False):
            if (c.style not in POF_EVIDENCE_STYLES
                    or _offset_in_spans(c.char_offset, ref_spans)):
                continue
            page = _page_identity(c.raw_url, registry)
            inline_cited_pages.add(page)
            for raw_line, start, end in lines:
                if start <= c.char_offset <= end:
                    visible = _visible_prose(raw_line)
                    if visible:
                        cited_line_text.setdefault(page, []).append(visible)
                    break

    covered = 0
    covered_by_predicate: dict[str, int] = {}
    concept_nuggets_total = 0
    concept_withheld = 0
    sample = []
    for n in pool:
        candidate_texts = [text]
        if n.predicate == "concept_coverage":
            concept_nuggets_total += 1
            # URL/title shells earn nothing.  Require a lexical quote supported
            # by this exact page.  When transport evidence exists, additionally
            # require that the agent actually fetched the concept page.
            supported, cache_present = _concept_quote_supported(
                md, n.source_url, cache or {}, page_stats, registry)
            if not cache_present:
                # Instrument blind: the evaluator holds no cached copy of this
                # concept's source page, so a quote cannot be checked either
                # way. Behaviour and the denominator are UNCHANGED (this nugget
                # still contributes 0, exactly as before); only observability is
                # added so a board can see the axis was partly blind rather than
                # reading the 0 as an earned miss. The spec does not say whether
                # such a nugget should be withheld from the denominator instead:
                # registered in SPEC_ISSUES, not decided here (scoring frozen).
                concept_withheld += 1
                continue
            if not supported:
                continue
            if (require_concept_fetch
                    and _page_identity(n.source_url, registry) not in fetched):
                continue
        elif require_nugget_citation:
            source_page = _page_identity(n.source_url, registry)
            if source_page not in inline_cited_pages:
                continue
            if require_concept_fetch and source_page not in fetched:
                continue
            # Citation identity and claim content must share a Markdown line.
            # A detached source dump at the top of the report cannot license a
            # correct rating or price written elsewhere.
            candidate_texts = cited_line_text.get(source_page, [])
            if not candidate_texts:
                continue
        stoks = _subject_tokens(n, generic)
        if not stoks:
            continue
        e = ents.get(n.source_url)
        alt = []
        if e is not None and (e.facts or {}).get("special_price") is not None:
            try:
                alt.append(round(float(e.facts["special_price"]), 2))
            except (TypeError, ValueError):
                pass
        hit = False
        for candidate_text in candidate_texts:
            if not _subject_discussed(candidate_text, stoks):
                continue
            spans = _subject_value_spans(candidate_text, n.subject, stoks)
            if not spans:
                continue
            # Identity digits inside the subject's own written-out name are
            # identity, never claim values -- the same masking the fact axis
            # applies before value extraction. Without it a title like
            # "... iWatch SE Series 7 6 5 4 3 2 1" put a standalone "4" next
            # to a "rated" cue and covered an 80.0% sentiment nugget
            # (4 == 80/20) no matter what percentage the report stated.
            # Masking preserves offsets, so the spans above remain valid.
            masked = _mask_numbers_in_spans(
                candidate_text, _exact_subject_spans(candidate_text, n.subject))
            for s, en in spans:
                w_end = en + BIND_WINDOW
                win = masked[max(0, s - BIND_WINDOW): w_end]
                if _typed_value_in_window(win, n, alt_prices=alt,
                                          tail=masked[w_end: w_end + 16]):
                    hit = True
                    break
            if hit:
                break
        covered += hit
        if hit:
            covered_by_predicate[n.predicate] = covered_by_predicate.get(n.predicate, 0) + 1
        if hit and len(sample) < 10:
            sample.append((n.subject[:40], n.predicate, str(n.object)[:12]))
    forum_hit, forum_url = (False, None)
    if forum_slot:
        forum_hit, forum_url = _forum_coverage_supported(
            md, answer_key, cache or {}, page_stats, registry, evidence,
            snippet_only=snippet_only)
        if forum_hit:
            covered += 1
            covered_by_predicate["forum_coverage"] = 1
            if len(sample) < 10:
                sample.append(("community evidence", "forum_coverage", forum_url or ""))
    # The denominator cannot exceed what the task actually offers. `k_star=20`
    # against a vital pool of 14-17 (every one of the 100 tasks) meant the
    # saturating cap `min(., 1)` never activated: a report that conveyed EVERY
    # vital fact scored 0.70-0.85, never 1.0, and the ceiling differed per task,
    # so completeness was not comparable across tasks. Both the docstring above
    # and the published board text promised a 1.0 no report could earn.
    total_pool = len(pool) + int(forum_slot)
    # Ruling #2 (docs/SPEC_DECISIONS.md): cache_policy selects how instrument-blind
    # slots are treated. 'strict' (default) is UNCHANGED -- blind slots stay in the
    # denominator (score 0) and the fail-closed refusal is a board-side lane, this
    # interface only carries the parameter. 'diagnostic' WITHHOLDS the blind slots
    # from k_effective (withhold-not-zero): a concept whose source page was never
    # cached, and the forum slot when the cache holds no candidate thread for this
    # task. covered never counts a withheld slot, so completeness cannot exceed 1.
    forum_withheld = bool(
        cache_policy == "diagnostic" and forum_slot and not forum_hit
        and not _forum_candidate_cached(answer_key, cache or {}, registry))
    withheld_slots = ((concept_withheld + int(forum_withheld))
                      if cache_policy == "diagnostic" else 0)
    effective_pool = max(total_pool - withheld_slots, 0)
    denom = min(k_star, effective_pool) or k_star
    comp_score = min(covered / denom, 1.0)
    comp_det = {
        "pool": total_pool, "structured_pool": len(pool),
        "forum_slots": int(forum_slot), "forum_covered": bool(forum_hit),
        "forum_url": forum_url,
        "k_star": k_star, "k_effective": denom,
        "covered": covered, "covered_by_predicate": covered_by_predicate,
        "concept_transport_required": require_concept_fetch,
        # ruling #1: this lane declared fetch_mode:none, so the concept/forum
        # fetch requirement was dropped (coverage falls back to the cache-quote
        # criterion). None-declared lanes carry False.
        "fetch_mode_none_exempt": snippet_only,
        "inline_nugget_citation_required": require_nugget_citation,
        # G4 observability: a concept nugget whose source page the evaluator
        # never cached cannot be scored, so its 0 is a WITHHOLD (blind
        # instrument), not an earned miss. Score/denominator unchanged; these
        # fields let a board tell the two apart. reason is None when nothing was
        # withheld.
        "concept_nuggets_total": concept_nuggets_total,
        "concept_withheld_count": concept_withheld,
        "concept_axis_withheld": concept_withheld > 0,
        "concept_axis_withheld_reason": (
            WithholdReason.CONCEPT_PAGE_NOT_CACHED.value if concept_withheld else None),
        # Ruling #2: cache_policy and the diagnostic-mode withhold accounting.
        # In 'strict' withheld_slots is 0 and total_pool == k_effective(before
        # k_star cap), so these are pure observability. In 'diagnostic' the blind
        # slots are removed from k_effective above.
        "cache_policy": cache_policy,
        "withheld_slots": withheld_slots,
        "forum_slot_withheld": forum_withheld,
        "forum_axis_withheld_reason": (
            WithholdReason.FORUM_THREAD_NOT_CACHED.value if forum_withheld else None),
        # docs/SPEC_DECISIONS.md '车道追加条目': concept slots whose cached source page
        # grounds for no report (a title-only stub), excised from the pool (and
        # thus the denominator) BEFORE scoring. Empty unless the cache holds such a
        # stub page; makes the excision observable rather than a silent shrink.
        "excluded_slots": excluded_slots,
        "covered_sample": sample}
    if comp_score == 0.0:
        # The pool was non-empty here (the empty-pool case returned earlier with
        # reason="empty_vital_pool"): the report simply covered none of it.
        comp_det["reason"] = "no_vital_covered"
    return comp_score, comp_det


# ---------------------------------------------------------------------------
# Axis 4: spec compliance
# ---------------------------------------------------------------------------

def score_spec(md: str, answer_key) -> tuple[float, dict]:
    """axis 4: decidable output-shape checks. Each SpecRequirement is a small
    parser. This is where format quotas live, kept out of the quality axes."""
    reqs = answer_key.spec_requirements
    if not reqs:
        return 1.0, {"requirements": 0, "passed": 0}
    passed, per = 0, []
    for r in reqs:
        ok = _check_spec(md, r)
        per.append({"id": r.id, "kind": r.kind, "passed": ok})
        passed += ok
    spec_det = {"requirements": len(reqs), "passed": passed, "per": per}
    if passed == 0:
        # Requirements existed and every one failed: an observed compliance zero.
        spec_det["reason"] = "no_spec_requirement_passed"
    return passed / len(reqs), spec_det


def _check_spec(md: str, r) -> bool:
    p = r.params or {}
    if r.kind == "table_present":
        return md.count("|") >= p.get("min_pipes", 6) and "\n|" in md
    if r.kind == "verdict_values":
        allowed = set(v.upper() for v in p.get("allowed", []))
        found = set(re.findall(r"\b([A-Z_]{4,})\b", md))
        need = p.get("min_distinct", 1)
        return len(found & allowed) >= need
    if r.kind == "section_present":
        return any(kw.lower() in md.lower() for kw in p.get("keywords", []))
    if r.kind == "max_bullets":
        # There is no per-section machinery here, so a non-global max_bullets
        # used to `return True` unconditionally: a compliance check that never
        # ran but counted as passed, inflating the compliance column. The cap is
        # decidable only over the whole document, so apply it there for every
        # max_bullets requirement (drop the auto-pass). Author a per-section quota
        # as a real check before adding one; do not smuggle it in as always-pass.
        bullets = len(re.findall(r"(?m)^\s*[-*+]\s+", md))
        return bullets <= p.get("max", 999)
    if r.kind == "min_words":
        return len(md.split()) >= p.get("min", 0)
    return False


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def compose_truth(reach: float, fact: float, pof: float, completeness: float,
                  spec: float = 0.0, gamma: float = GAMMA_DEFAULT,
                  eps: float = EPS_FLOOR) -> tuple[float, float, dict]:
    """truth = reach**gamma * quality (FORMULA_LOCK K6; C1/C2 derived).

    quality = 0.39*fact + 0.28*pof + 0.33*completeness over the THREE evidence
    axes only. spec is accepted for signature compatibility but is NOT part of
    truth (it is the separate compliance column); passing it changes nothing.

    NO quality floor (D1 endgame, eps defaults to 0.0): each axis contributes its
    RAW value, so a zero-substance shell has quality=0 / truth=0 (criterion C2)
    AND a trivial mini-shell that only grazes each axis scores its earned value
    rather than an inflated 0.05 plateau. reach is UNfloored: it is the
    anti-fabrication gate and a pure fabricator collapses to 0 (criterion C1).
    gamma defaults to 1.0, making the headline score ``reach * quality``;
    sensitivity() can still probe alternative exponents. ``eps`` is retained
    for back-compat: a positive value re-enables the old floor-if-active
    (max(eps,v) for v>0). Returns (truth, quality, floors_applied)."""
    floors_applied = {}
    vals = {}
    for name, v in (("fact_support", fact), ("proof_of_fetch", pof),
                    ("completeness", completeness)):
        v = max(0.0, float(v))
        # eps=0.0 -> raw axis (no floor, D1); eps>0 -> floor-if-active (legacy)
        f = max(eps, v) if (eps > 0.0 and v > 0.0) else v
        floors_applied[name] = f > v
        vals[name] = f
    quality = sum(QUALITY_WEIGHTS[k] * vals[k] for k in QUALITY_WEIGHTS)
    truth = (max(0.0, float(reach)) ** gamma) * quality
    return truth, quality, floors_applied


class MissingEvidenceLog(RuntimeError):
    """A run has no transport evidence, and the caller asked for real PoF."""


def transport_metrics_for(urls, evidence, registry=None, cache=None) -> dict:
    """Bridge to src.eval.fetch_log, imported lazily to keep this module's
    import graph free of the shim."""
    from src.eval.fetch_log import transport_metrics, linked_urls

    def _in_registry(u: str) -> bool:
        # Exactly the same tri-state + page-cache fallback used by reach.  A
        # cached-200 wiki page under a partial registry cannot be reachable in
        # one axis and fabricated in another.
        return _in_corpus_with_cache(u, cache or {}, registry)

    # Resolve `linked` from the stored page bodies so a URL the agent reached by
    # following a link on a page it actually read is classified `linked` (honest
    # navigation), not `guessed`, and is not charged as hallucinated grounding.
    # Without this the blob-reading path is dead and every on-page-link citation
    # is mislabelled. load_blob comes from the shim's evidence module; if it is
    # unavailable (or a blob is missing) linked_urls yields the empty set and the
    # behaviour degrades to the previous `guessed` classification, never worse.
    linked = None
    try:
        from integrations.search_shim import evidence as _shim_ev
        linked = linked_urls(evidence, _shim_ev.load_blob)
    except Exception:
        linked = None
    def _identify(u: str) -> str:
        """The page a URL names, by the registry's identity, not by string form.

        `reach` and the transport axes must agree about what one page is.
        `fetch_log.canonical` collapses scheme/host/fragment/layered-nav; the
        registry additionally knows that `/wiki/Bluetooth` and
        `/content/<book>/A/Bluetooth` are one article, and that a forum thread is
        identified by its id, not by the board it is filed under. The shim serves
        one spelling and the model writes the other, so without this a page the
        agent really opened fell outside FETCHED and was scored
        `hallucinated_grounding` -- an accusation of parametric recall against a
        lane that read the page.
        """
        if registry is None:
            return u
        try:
            c = registry.classify(u)
        except Exception:  # noqa: BLE001
            return u
        return (c.get("canonical") if isinstance(c, dict) else None) or u

    def _is_nav(u: str) -> bool:
        """A navigation/search page: real, reachable, and carrying no claim.

        `score_reachability` drops these from its denominator. Keeping them here
        made one honest `catalogsearch/result/?q=` citation read as 50%
        fabrication on a report that fabricated nothing.
        """
        if registry is None:
            return False
        try:
            return registry.classify(u).get("kind") == "search_nav"
        except Exception:  # noqa: BLE001
            return False

    m = transport_metrics(urls, evidence, in_registry=_in_registry,
                          linked=linked, identify=_identify, is_nav=_is_nav)
    # G4/G6: stamp the machine-readable withhold code beside the human string,
    # so the transport block ALWAYS carries a stable `reason_code` when it
    # withholds. fetch_log keeps ownership of the (frozen) prose; the code is
    # derived here so a board never has to string-match. A withhold never emits
    # `pof`, so this can only decorate an available=False dict, never a real 0.
    if isinstance(m, dict) and not m.get("available"):
        m["reason_code"] = withhold_reason_code(m.get("reason")).value
    return m


def _axis_key(pof_semantics: str) -> str:
    """Name of the grounding-fidelity axis for a report scored under
    ``pof_semantics``. The KEY tracks the meaning; the composed truth score uses
    the same number either way (the formula does not change), only the name does.

        transport_v2 -> "grounding_proof_of_fetch"
        text_v1      -> "grounding_quote_support"

    Why a rename and not "proof_of_fetch, weaker": an axis called proof-of-fetch
    that actually measures text_v1 is a CONSTRUCT ERROR, not a looser estimator
    of the same quantity. text_v1 is a verbatim lexical match between the
    report's prose and a copy the EVALUATOR fetched after the run; it never
    observes the agent's transport at all. A model can reproduce that text
    without opening the page: it can quote a search snippet the shim handed it,
    or reproduce a page from parametric memory. Publishing that number under
    "grounding_proof_of_fetch" asserts a fetch the instrument never witnessed,
    which is exactly the claim-evidence break this rework exists to remove. Only
    transport_v2 (|cited & fetched| / |cited|, decided from the run's shim
    evidence log) witnesses a fetch, so only it may carry the proof-of-fetch
    name. See tests/test_transport_pof_integration.py and P1.

    Callers must key the axis off THIS return value, not a hard-coded string, so
    the column header can never again disagree with what the column measures."""
    return ("grounding_proof_of_fetch" if pof_semantics == "transport_v2"
            else "grounding_quote_support")


def score_report(md: str, answer_key, cache: dict, registry=None,
                 gamma: float = GAMMA_DEFAULT, k_f: int = K_F_DEFAULT,
                 k_star: int = K_STAR_DEFAULT,
                 pof_threshold: float = POF_THRESHOLD_DEFAULT,
                 eps: float = EPS_FLOOR,
                 page_stats: dict | None = None,
                 evidence=None,
                 require_transport_pof: bool = False,
                 lane_fetch_mode=None,
                 cache_policy: str = "strict") -> AxisScores:
    """Compute all decidable axes and the composed truth score.

    Returns axes + truth ONLY (M-C1): presentation is a separate column,
    fused (if at all) as a bounded tie-breaker downstream, never multiplied
    into truth.

    ``page_stats`` is the ``build_page_stats(cache)`` document-frequency pass
    over the WHOLE cache (G-F1); it depends only on ``cache``, not on this
    report, so callers scoring many reports against one cache (a full board
    build) should compute it once and pass it in here instead of paying an
    O(cache size) pass per report."""
    cache = cache or {}
    urls = _cited_urls(md)
    reach, rd = score_reachability(urls, cache, registry)
    stats = page_stats if page_stats is not None else build_page_stats(cache)
    pof, pd = score_proof_of_fetch(md, cache, page_stats=stats,
                                   threshold=pof_threshold)
    # `pof` above is a textual measure: does the report's prose match a page the
    # EVALUATOR fetched afterwards. It cannot see whether the agent opened
    # anything. When the run has a transport-level evidence log, the real
    # proof-of-fetch replaces it and the textual number is kept, renamed, as
    # `quote_support`: read-then-write fidelity, which is a different question.
    quote_support, pof_semantics, transport = pof, "text_v1", None
    if evidence is not None:
        transport = transport_metrics_for(urls, evidence, registry=registry,
                                          cache=cache)
        if transport.get("available"):
            pof, pof_semantics = transport["pof"], "transport_v2"
        elif require_transport_pof:
            raise MissingEvidenceLog(
                "no transport evidence for this run and require_transport_pof is set. "
                "Scoring pof as the old textual measure would silently change its "
                "meaning; scoring it as 0 would accuse an unobserved lane of "
                "fabricating. Refusing both."
            )
    elif require_transport_pof:
        raise MissingEvidenceLog(
            "require_transport_pof is set but no evidence was passed to score_report()"
        )
    generic = build_generic_tokens(answer_key)
    fact, fd = score_fact_support(md, answer_key, generic=generic, k_f=k_f)
    comp, cd = score_completeness(
        md, answer_key, k_star=k_star, generic=generic, cache=cache,
        page_stats=stats, registry=registry, evidence=evidence,
        lane_fetch_mode=lane_fetch_mode, cache_policy=cache_policy,
    )
    spec, sd = score_spec(md, answer_key)

    # A transport-observed run can decide whether the URL came from the
    # benchmark at all.  Gate on in-corpus pages that were searched, fetched, or
    # linked from a fetched page.  Raw reach remains a diagnostic.  Legacy
    # text_v1 runs have no transport observation and therefore retain the old
    # reach gate; the explicit stamp prevents the two semantics being mixed.
    gate_semantics = "provenance_v2" if pof_semantics == "transport_v2" else "reach_v1"
    gate_value = (float(transport.get("provenance", 0.0))
                  if gate_semantics == "provenance_v2" else reach)
    truth, quality, floors = compose_truth(gate_value, fact, pof, comp, spec,
                                           gamma=gamma, eps=eps)
    # G6: a single, downstream-stable map from each PUBLISHED axis key (the key
    # evaluate() emits under "axes") to the machine-readable reason for its zero.
    # Every axis whose emitted value is 0 gets a code here, so a summary or the
    # G6 checker never has to reach into a per-axis sub-detail whose shape
    # differs by axis. The per-axis `reason` fields set above are the source of
    # truth; the `.get(..., default)` fallbacks are belt-and-suspenders so no
    # scored zero can ever be emitted without a reason, even from a path a future
    # edit forgets to annotate. Additive: no score value depends on this.
    pof_key = _axis_key(pof_semantics)
    axis_reasons: dict[str, str] = {}
    if reach == 0.0:
        axis_reasons["grounding_reach"] = rd.get("reason", "no_citations")
    if pof == 0.0:
        if pof_semantics == "transport_v2" and transport is not None:
            axis_reasons[pof_key] = ("no_citations"
                                     if transport.get("n_cited", 0) == 0
                                     else "no_page_fetched")
        else:
            axis_reasons[pof_key] = pd.get("reason", "no_citable_pages")
    if fact == 0.0:
        axis_reasons["correctness_fact_support"] = fd.get("reason",
                                                          "no_checkable_claims")
    if comp == 0.0:
        axis_reasons["completeness"] = cd.get("reason", "no_vital_covered")
    if spec == 0.0:
        axis_reasons["spec"] = sd.get("reason", "no_spec_requirement_passed")
    s = AxisScores(
        reach=reach, proof_of_fetch=pof, fact_support=fact,
        fact_contradicted=fd.get("contradicted", 0),
        fact_absent=fd.get("unbound", 0) + fd.get("untestable", 0),
        completeness=comp, spec=spec, compliance=spec,
        quality=quality, truth=truth)
    s.detail = {
        "reach": rd, "proof_of_fetch": pd, "fact": fd,
        "completeness": cd, "spec": sd, "compliance": sd,
        # G6: {published_axis_key -> zero reason code} for every zero axis.
        "axis_reasons": axis_reasons,
        "floors_applied": floors, "gamma": gamma, "eps": eps,
        "quality_weights": dict(QUALITY_WEIGHTS),
        "quality": round(quality, 4), "truth": round(truth, 6),
        "compliance_score": round(spec, 4),
        # Which question `pof` answered for THIS report. Boards mixing the two
        # are not comparable: text_v1 asks "does the prose resemble the page",
        # transport_v2 asks "did the agent open the page".
        "pof_semantics": pof_semantics,
        "gate_semantics": gate_semantics,
        "gate_value": round(gate_value, 4),
        "raw_reach": round(reach, 4),
        "quote_support": round(quote_support, 4),
        "transport": transport,
        "counts": {
            "reach_num": rd.get("num", 0), "reach_den": rd.get("den", 0),
            "pof_passed": pd.get("passed", 0), "pof_checked": pd.get("checked", 0),
            "fact_supported": fd.get("supported", 0),
            "fact_tested": fd.get("claims_tested", 0),
            # SPEC_ISSUES G6 (aggregate micro divergence): the per-report recall
            # term is min(DISTINCT task-scoped supported / k_f, 1); aggregate()
            # was pooling `fact_tested` (supported+contradicted) as its volume
            # numerator, so a wrong claim bought micro recall the per-report path
            # forbids. Carry the distinct-supported count and the per-report
            # completeness denominator so aggregate() can pool them the same way
            # the per-report axes are computed. Additive fields.
            "fact_distinct_supported": fd.get("distinct_supported_facts", 0),
            "comp_covered": cd.get("covered", 0),
            "comp_k_effective": cd.get("k_effective", 0),
            "spec_passed": sd.get("passed", 0),
            "spec_total": sd.get("requirements", 0),
        },
    }
    return s


# ---------------------------------------------------------------------------
# Panel helpers: sensitivity + aggregation
# ---------------------------------------------------------------------------

def _axis_tuple(r) -> tuple[float, float, float, float, float]:
    """(reach, fact, pof, completeness, spec) from an AxisScores or an
    evaluate() output dict."""
    if isinstance(r, AxisScores):
        return (r.reach, r.fact_support, r.proof_of_fetch,
                r.completeness, r.spec)
    ax = r.get("axes", r)
    return (float(ax.get("grounding_reach", ax.get("reach", 0.0))),
            float(ax.get("correctness_fact_support", ax.get("fact_support", 0.0))),
            # text_v1 boards name this axis `grounding_quote_support` (P1); both
            # names hold the same number for a given report, so read either.
            float(ax.get("grounding_proof_of_fetch",
                         ax.get("grounding_quote_support",
                                ax.get("proof_of_fetch", 0.0)))),
            float(ax.get("completeness", 0.0)),
            float(ax.get("spec", 0.0)))


def _kendall_tau(x: list[float], y: list[float]) -> float:
    """Kendall tau over comparable (non-tied) pairs: only a strict order
    inversion counts against stability, so a panel tied at every gamma is
    stable (tau=1), not 'unranked'."""
    n = len(x)
    if n < 2:
        return 1.0
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (x[i] - x[j]) * (y[i] - y[j])
            if s > 0:
                conc += 1
            elif s < 0:
                disc += 1
    comparable = conc + disc
    return (conc - disc) / comparable if comparable else 1.0


def sensitivity(reports: list, gamma_list=(1.0, 1.25, 1.5, 1.75, 2.0),
                eps: float = EPS_FLOOR) -> dict:
    """Rank-stability of the truth ordering as gamma varies (M-H3).

    gamma is calibrated externally on an injected-fabrication set; this helper
    shows whether the PANEL ranking depends on the choice. Recomputes truth
    for every report at each gamma and reports Kendall tau of each ordering
    against the first gamma's ordering. rank_stable=True means the exponent
    choice cannot reorder this panel."""
    rows = [_axis_tuple(r) for r in reports]
    out: dict = {"gamma_list": [float(g) for g in gamma_list],
                 "truth_by_gamma": {}, "kendall_tau_vs_first": {},
                 "rank_stable": True}
    base = None
    for g in gamma_list:
        truths = [compose_truth(*row, gamma=float(g), eps=eps)[0] for row in rows]
        out["truth_by_gamma"][float(g)] = [round(t, 6) for t in truths]
        if base is None:
            base = truths
            out["kendall_tau_vs_first"][float(g)] = 1.0
        else:
            tau = _kendall_tau(base, truths)
            out["kendall_tau_vs_first"][float(g)] = round(tau, 4)
            if tau < 1.0:
                out["rank_stable"] = False
    return out


def aggregate(reports: list, gamma: float = GAMMA_DEFAULT,
              eps: float = EPS_FLOOR, k_f: int = K_F_DEFAULT,
              k_star: int = K_STAR_DEFAULT) -> dict:
    """Panel aggregation with BOTH macro and micro views plus per-report gate
    visibility (M-M1).

    macro_truth       mean of per-report truth (each task weighs equally)
    micro_truth       truth recomposed from pooled per-axis counts (each
                      citation/claim/vital fact weighs equally)
    min_report_truth  the worst single report: a [0.9,0.9,0.9,0.0] agent can
                      no longer launder the 0.0 into a 0.675 mean unseen."""
    n = len(reports)
    if n == 0:
        return {"n_reports": 0}
    truths, counts_list = [], []
    for r in reports:
        if isinstance(r, AxisScores):
            truths.append(r.truth)
            counts_list.append(r.detail.get("counts", {}))
        else:
            truths.append(float(r.get("truth", 0.0)))
            counts_list.append((r.get("detail") or {}).get("counts", {}))
    tot: dict[str, float] = {}
    for c in counts_list:
        for k, v in c.items():
            tot[k] = tot.get(k, 0) + (v or 0)
    micro_reach = tot.get("reach_num", 0) / tot["reach_den"] if tot.get("reach_den") else 0.0
    micro_pof = tot.get("pof_passed", 0) / tot["pof_checked"] if tot.get("pof_checked") else 0.0
    tested = tot.get("fact_tested", 0)
    if tested:
        p = tot.get("fact_supported", 0) / tested
        # Volume is DISTINCT supported facts, matching the per-report recall term
        # (SPEC_ISSUES G6). Fall back to `fact_supported` for boards serialized
        # before the distinct count was carried, so old panels still aggregate.
        distinct = tot.get("fact_distinct_supported", tot.get("fact_supported", 0))
        rvol = min(distinct / (k_f * n), 1.0)
        micro_fact = 0.0 if (p <= 0 or rvol <= 0) else 2 * p * rvol / (p + rvol)
    else:
        micro_fact = 0.0
    # Completeness denominator is the SUM of per-report k_effective (each report's
    # min(k_star,|pool|)), matching the per-report axis (SPEC_ISSUES G6). k_star*n
    # is the pre-fix denominator, kept only when the per-report figure is absent.
    comp_denom = tot.get("comp_k_effective") or (k_star * n)
    micro_comp = min(tot.get("comp_covered", 0) / comp_denom, 1.0) if comp_denom else 0.0
    micro_spec = (tot.get("spec_passed", 0) / tot["spec_total"]
                  if tot.get("spec_total") else 1.0)
    micro_truth, micro_quality, _ = compose_truth(
        micro_reach, micro_fact, micro_pof, micro_comp, micro_spec,
        gamma=gamma, eps=eps)
    return {
        "n_reports": n,
        "macro_truth": round(sum(truths) / n, 6),
        "micro_truth": round(micro_truth, 6),
        "min_report_truth": round(min(truths), 6),
        "per_report_truth": [round(t, 6) for t in truths],
        "micro_axes": {"reach": round(micro_reach, 4),
                       "fact_support": round(micro_fact, 4),
                       "proof_of_fetch": round(micro_pof, 4),
                       "completeness": round(micro_comp, 4),
                       "spec": round(micro_spec, 4),
                       "quality": round(micro_quality, 4)},
    }


# ---------------------------------------------------------------------------
# Smoke (python3 -m src.eval.decidable_scorer)
# ---------------------------------------------------------------------------

def _smoke() -> int:
    import json as _json
    from src.eval.answer_key import AnswerKey

    ak = AnswerKey.load("data/golden/answer_keys/dr_cross_deep_0001.json")
    generic = build_generic_tokens(ak)
    ents = {e.url: e for e in ak.relevant_set}
    pool = build_vital_pool(ak)

    # pick pool facts an honest agent would report (skip names whose '.' would
    # split our synthetic sentences)
    prods, thread = [], None
    for n in pool:
        if n.predicate == "price" and len(prods) < 3:
            if any(ch in n.subject for ch in ".!?"):
                continue
            if len(name_key(n.subject, generic).split()) < 2:
                continue
            prods.append(n)
        elif n.predicate == "thread_score" and thread is None:
            if any(ch in n.subject for ch in ".!?") or len(n.subject) > 60:
                continue
            thread = n
        if len(prods) == 3 and thread is not None:
            break

    cache: dict = {}
    honest_parts = []
    for n in prods:
        e = ents[n.source_url]
        price = round(float(n.object), 2)
        rating = (e.facts or {}).get("rating")
        rc = int(float((e.facts or {}).get("review_count") or 0))
        # a real report names the product in short form, not the 30-word
        # catalog title; the identity key is exactly that short form
        disp = name_key(n.subject, generic).title()
        page = (f"<html><body>{e.name} ${price:.2f} "
                + (f"rated {rating} out of 5 based on {rc} reviews. " if rating else "")
                + "Ships with a two year limited warranty and a detachable cable."
                  "</body></html>")
        cache[e.url] = {"status": 200, "text": page}
        sent = f"The {disp} costs ${price:.2f}"
        if rating:
            sent += f" and is rated {rating} out of 5 based on {rc} reviews"
        sent += (f"; the listing notes it ships with a two year limited warranty "
                 f"([source]({e.url})).")
        honest_parts.append(sent)
    if thread is not None:
        e = ents[thread.source_url]
        sc = int(float(thread.object))
        cc = int(float((e.facts or {}).get("comment_count") or 0))
        cache[e.url] = {"status": 200, "text": (
            f"<html><body>{e.name} submitted to f/{(e.facts or {}).get('forum', '')} "
            f"score {sc} with {cc} comments. Users report the build quality holds "
            f"up after years of daily use.</body></html>")}
        honest_parts.append(
            f"The thread \"{e.name}\" (score {sc}, {cc} comments) notes the build "
            f"quality holds up after years of daily use ([thread]({e.url})).")
    honest = (" ".join(honest_parts)
              + " No contradictions between marketing claims and community "
                "reviews were found. Recommended shortlist: the products above.")

    e0 = ents[prods[0].source_url]
    disp0 = name_key(prods[0].subject, generic).title()
    fabricator = (
        f"([overview]({e0.url})) Our lab benchmarked every headset on the "
        f"market this quarter. The {disp0} costs $999.99 and outperforms studio "
        "reference monitors. The QuantumX Hyperphone Ultra costs $9.99 and "
        "uses military grade titanium drivers "
        "([q](http://localhost:7770/quantumx-hyperphone-ultra.html)). "
        "A verified teardown confirms the quantum flux driver assembly "
        "([t](http://localhost:9999/f/audiophile/424242/quantum-teardown)).")

    silent = ("Headphones are a mature product category. Many people enjoy "
              "music on the go.")

    def show(tag, s):
        print(f"[{tag}] reach={s.reach:.3f} pof={s.proof_of_fetch:.3f} "
              f"fact={s.fact_support:.3f} comp={s.completeness:.3f} "
              f"spec={s.spec:.3f} quality={s.quality:.4f} truth={s.truth:.6f}")

    print("== fallback path (no registry file: cache-status + registry_missing) ==")
    hs = score_report(honest, ak, cache)
    fs = score_report(fabricator, ak, cache)
    zs = score_report(silent, ak, cache)
    show("honest    ", hs)
    show("fabricator", fs)
    show("zero-claim", zs)
    print("  reach path:", hs.detail["reach"]["path"],
          "registry_missing =", hs.detail["reach"]["registry_missing"])
    print("  fabricator fact detail:", {k: fs.detail["fact"][k] for k in
          ("claims_tested", "supported", "contradicted", "unbound")})
    print("  zero-claim fact detail:", {k: zs.detail["fact"][k] for k in
          ("claims_tested", "reason")})
    assert fs.truth < hs.truth, "fabricator must score strictly below honest"
    assert zs.fact_support == 0.0
    assert zs.detail["fact"]["reason"] == "no_checkable_claims"

    print("== registry path (in-memory UrlRegistry) ==")
    from urllib.parse import urlparse
    from src.eval.url_registry import UrlRegistry
    products, submissions = [], {}
    for u in cache:
        path = urlparse(u).path
        if ":7770" in u and path.endswith(".html"):
            products.append(path.strip("/")[:-len(".html")])
        elif ":9999" in u:
            segs = [s for s in path.split("/") if s]
            if len(segs) >= 3 and segs[0] == "f":
                submissions[segs[2]] = segs[1]
    reg = UrlRegistry(products=products, submissions=submissions, wiki=[])
    hs2 = score_report(honest, ak, cache, registry=reg)
    fs2 = score_report(fabricator, ak, cache, registry=reg)
    show("honest    ", hs2)
    show("fabricator", fs2)
    print("  fabricator reach reasons:", fs2.detail["reach"]["reasons"])
    assert fs2.truth < hs2.truth

    print("== panel helpers ==")
    agg = aggregate([hs, fs, zs])
    print("  aggregate:", _json.dumps({k: agg[k] for k in
          ("macro_truth", "micro_truth", "min_report_truth")}))
    sen = sensitivity([hs, fs, zs])
    print("  sensitivity rank_stable:", sen["rank_stable"],
          "taus:", sen["kendall_tau_vs_first"])
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_smoke())
