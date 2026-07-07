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

Composition (registry findings M-C1/C2/H3/H4/H5/M1/L1):

    quality = 0.35*fact + 0.25*proof_of_fetch + 0.30*completeness + 0.10*spec
    truth   = reach**gamma * quality

  * fact / pof / completeness / spec are each floored at eps=0.05 AFTER
    computation, so a matcher recall error cannot annihilate an honest report
    (M-H5); reach is deliberately UNfloored: it is the anti-fabrication gate
    and a pure fabricator must be able to reach truth = 0 (M-C2).
  * the old a/b exponents are gone (M-H3): they were non-identifiable and
    redundant with gamma. gamma defaults to 1.5 and is to be calibrated
    EXTERNALLY on an injected-fabrication set, never fitted on the eval panel;
    sensitivity() reports how the ranking moves across candidate gammas.
  * spec is inside the composition with a small weight (M-H4): instruction
    following is a real axis, not decoration.
  * no cross-denominator arithmetic means: the old (fact+pof)/2 averaged two
    ratios with different denominators (M-L1); they are now separate weighted
    terms.

PRESENTATION IS NOT PART OF TRUTH (M-C1). score_report returns the decidable
axes and the truth score only. The presentation judge (normalized Elo, an
interval scale with no true zero) is reported as a SEPARATE column at
leaderboard time and may only break ties between reports with equal truth; it
must never overturn the truth ordering, and it is never multiplied in.

aggregate() reports macro AND micro views plus min_report_truth, so a single
catastrophic report can no longer hide inside a per-agent mean (M-M1).
"""

from __future__ import annotations

import bisect
import html as html_mod
import math
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tunables (defaults; see each docstring for the calibration story)
# ---------------------------------------------------------------------------

GAMMA_DEFAULT = 1.5      # grounding gate exponent, calibrated EXTERNALLY on an
                         # injected-fabrication series (M-H3): data/results/
                         # pof_gamma_calibration.json. Truth is monotone
                         # non-increasing in the fabrication rate at every tested
                         # gamma; 1.5 gives clean-vs-50% mean separation 0.042
                         # and is not dominated (no gamma beats it on BOTH
                         # separation and monotonicity), so it is retained.
EPS_FLOOR = 0.05         # per-axis floor on the quality axes only (M-H5)
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

QUALITY_WEIGHTS = {
    "fact_support": 0.35,
    "proof_of_fetch": 0.25,
    "completeness": 0.30,
    "spec": 0.10,
}

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

_NUM_RE = re.compile(r"\d{1,6}(?:\.\d{1,2})?")

# Price claims trigger ONLY on an explicit price cue within 12 chars of the
# number ("$" or price/priced/costs/cost); "at 18 grams" no longer becomes a
# CONTRADICTED price (G-F6).
_PRICE_CUE = re.compile(r"\bpric(?:e|es|ed|ing)\b|\bcosts?\b")
PRICE_CUE_WINDOW = 12

# Numbers immediately followed by a unit word are measurements, never prices
# (G-F6). Longer alternatives first where prefixes collide.
_UNIT_AFTER = re.compile(
    r"^\s*-?\s*(?:%|(?:grams?|hours?|hrs|inch(?:es)?|stars?|reviews?|days?"
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


def _subject_discussed(text: str, subj_tokens: list[str]) -> bool:
    """The report discusses this entity only if its distinctive identity is
    present: a majority of identity tokens (capped at what the key actually
    has, so single-token subjects such as short forum-thread titles remain
    matchable), at least one of which is strong (>=4 chars, or a model-number
    style token containing a digit)."""
    if not subj_tokens:
        return False
    present = [t for t in subj_tokens if t in text]
    need = min(len(subj_tokens), max(2, (len(subj_tokens) + 1) // 2))
    if len(present) < need:
        return False
    return any(len(t) >= 4 or any(c.isdigit() for c in t) for t in present)


def _token_spans(text: str, tokens: list[str], cap: int = 200) -> list[tuple[int, int]]:
    """Character spans of each identity token in text (word-boundary matches)."""
    spans: list[tuple[int, int]] = []
    for t in tokens:
        if not t:
            continue
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text):
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
    spec: float = 0.0            # axis 4
    quality: float = 0.0         # weighted sum of floored quality axes
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

def _cache_entry(cache: dict, u: str):
    """Cache lookup tolerant to key-normalization drift between the extractor
    and the cache builder (trailing punctuation, localhost vs 127.0.0.1)."""
    for k in (u, u.rstrip("`.,;:!?)"),
              u.replace("127.0.0.1", "localhost"),
              u.replace("localhost", "127.0.0.1")):
        e = cache.get(k)
        if e is not None:
            return e
    return None


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
            canon = d.get("canonical") or f"raw:{u}"
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
                st = int((_cache_entry(cache, u) or {}).get("status", -1))
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
        return (ok / den if den else 0.0), det

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
    return score, {
        "path": "cache_status", "registry_missing": True,
        "cited": len(urls), "ok": ok, "unreachable": bad, "off_sandbox": off,
        "num": ok, "den": den,
        "note": ("closed world: 4xx/5xx/0/uncached/off-sandbox all stay in "
                 "the denominator (M-M2/G-F8/G-F10)"),
    }


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


def score_proof_of_fetch(md: str, cache: dict, page_stats: dict | None = None,
                         threshold: float = POF_THRESHOLD_DEFAULT,
                         span_len: int = 3) -> tuple[float, dict]:
    """axis 1b: does the report's own context around each citation actually
    appear on the cited page? (G-F1 rebuild.)

    Context = the 400 chars BEFORE the link, with every markdown link label
    REMOVED (not substituted back in: the label is usually the page title and
    would auto-hit) and bare URLs stripped. Tokens = words >=3 chars MINUS the
    stopword set MINUS the chrome tokens; numeric tokens are always kept
    (G-F15). Pages are scanned in FULL, never a 5k/20k/40k prefix (G-F4).

    Match = IDF-weighted containment (weight 1/log(2+page_df) when a df table
    exists, else 1) >= `threshold` AND at least one contiguous span of
    `span_len` raw context tokens appearing verbatim in the page token stream
    (the span requirement kills bag-of-words gaming: pasting a product name
    plus topic words no longer passes).

    threshold=0.35 is calibrated (G-F1) in data/results/
    pof_gamma_calibration.json (scripts/calibrate_pof_gamma.py): on 320 verbatim
    positives + 160 fabricated-quote + 160 cross-page negatives it holds
    TPR=1.000 at FPR=0.000 (fabricated) / 0.006 (cross-page). The span
    requirement carries the separation, so the operating point is flat over the
    0.15-0.60 grid and 0.35 is retained mid-plateau."""
    stats = page_stats if page_stats is not None else build_page_stats(cache)
    df, chrome = stats.get("df"), stats.get("chrome", set(CHROME_FALLBACK))

    def w(t: str) -> float:
        if df:
            return 1.0 / math.log(2 + df.get(t, 0))
        return 1.0

    page_cache: dict[str, tuple[set, set]] = {}
    checked = passed = 0
    per = []
    for m in LINK_RE.finditer(md):
        u = m.group(2).rstrip(".,;")
        entry = cache.get(u)
        try:
            st = int((entry or {}).get("status", 0) or 0)
        except (TypeError, ValueError):
            st = 0
        if not entry or st != 200:
            continue
        raw_ctx = md[max(0, m.start() - 400): m.start()]
        raw_ctx = LINK_RE.sub(" ", raw_ctx)      # label REMOVED (G-F1)
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
            # a cached-200 citation with ZERO non-boilerplate context is
            # exactly "no proof of fetch": count it as checked-and-failed,
            # else slug/stopword padding turns real-but-unread citations into
            # skips and pof collapses to the one genuine citation (verify
            # finding: 1 real + 5 padded scored 1.000)
            checked += 1
            per.append({"url": u[-60:], "cover": 0.0, "span": False,
                        "ok": False, "reason": "empty_context"})
            continue
        if u not in page_cache:
            page_seq = _tokens(norm(strip_html(entry.get("text", ""))))  # FULL text (G-F4)
            tris = {tuple(page_seq[i:i + span_len])
                    for i in range(len(page_seq) - span_len + 1)}
            page_cache[u] = (set(page_seq), tris)
        page_set, page_tris = page_cache[u]
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
        ok = cover >= threshold and span_ok
        checked += 1
        passed += ok
        per.append({"url": u[-60:], "cover": round(cover, 3),
                    "span_ok": span_ok, "passed": bool(ok)})
    return (passed / checked if checked else 0.0), {
        "checked": checked, "passed": passed, "threshold": threshold,
        "df_pages": stats.get("n_pages", 0), "per": per[:12]}


# ---------------------------------------------------------------------------
# Axis 2: fact support (structured, decidable)
# ---------------------------------------------------------------------------

def _fact_indices(answer_key, generic: set) -> tuple[dict, dict]:
    """DB truth indexed by distinctive subject key. Values are SETS: variants
    sharing a key are all acceptable, and facts['special_price'] is accepted
    as an alternative correct price when present (G-F6 sale-vs-list)."""
    price_of: dict[str, set] = {}
    rating_of: dict[str, set] = {}
    for n in (list(answer_key.vital_nuggets) + list(answer_key.useful_nuggets)):
        if not getattr(n, "relevant", True):
            continue
        key = name_key(n.subject, generic)
        if not key:
            continue
        try:
            if n.predicate == "price":
                price_of.setdefault(key, set()).add(round(float(n.object), 2))
            elif n.predicate == "rating":
                rating_of.setdefault(key, set()).add(float(n.object))
        except (TypeError, ValueError):
            continue
    for e in answer_key.relevant_set:
        if not getattr(e, "relevant", True):
            continue
        key = name_key(e.name, generic)
        if not key:
            continue
        facts = e.facts or {}
        for fk in ("price", "special_price"):
            if facts.get(fk) is not None:
                try:
                    price_of.setdefault(key, set()).add(round(float(facts[fk]), 2))
                except (TypeError, ValueError):
                    pass
        if facts.get("rating") is not None:
            try:
                rating_of.setdefault(key, set()).add(float(facts["rating"]))
            except (TypeError, ValueError):
                pass
    return price_of, rating_of


def score_fact_support(md: str, answer_key, generic: set | None = None,
                       k_f: int = K_F_DEFAULT) -> tuple[float, dict]:
    """axis 2 (structured, decidable): extract the price/rating claims the
    report EXPLICITLY makes about DB entities and check each against DB truth.

    Volume-aware F1 (M-C3/G-F7: silence must not score):
        precision  = supported / tested
        recall_vol = min(tested / K_f, 1)          # K_f defaults to 10
        fact       = harmonic mean (0 if either is 0)
    tested == 0 returns 0.0 with detail reason "no_checkable_claims": a report
    that asserts nothing checkable earns nothing (the old `else 1.0` gave a
    perfect score for silence).

    Claim extraction is hardened per G-F6: price triggers only with a "$" or
    price-word cue within 12 chars; unit-suffixed numbers are measurements;
    subject-number binding only within +-40 chars of a subject identity token
    in the same sentence; aspect-qualified ratings ("5 stars for build") are
    not overall-rating claims. special_price counts as an alternative correct
    price."""
    generic = generic if generic is not None else build_generic_tokens(answer_key)
    price_of, rating_of = _fact_indices(answer_key, generic)
    all_keys = price_of.keys() | rating_of.keys()

    # url slug -> index key, for link-precedence binding (verify finding:
    # official-title prose bound claim values to ANOTHER product via title
    # tail tokens; the citation link IS the subject identity)
    slug_key: dict[str, str] = {}
    for e in answer_key.relevant_set:
        if not getattr(e, "relevant", True):
            continue
        k = name_key(e.name, generic)
        if k:
            slug_key[e.url.rsplit("/", 1)[-1].removesuffix(".html").lower()] = k

    support = contra = unbound = untestable = skipped_aspect = 0
    per = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", md):
        links = LINK_RE.findall(sent)
        linked_keys = {slug_key[u.rstrip(".,;").rsplit("/", 1)[-1]
                                .removesuffix(".html").lower()]
                       for _lab, u in links
                       if u.rstrip(".,;").rsplit("/", 1)[-1]
                             .removesuffix(".html").lower() in slug_key}
        forced_key = next(iter(linked_keys)) if len(linked_keys) == 1 else None
        # strip URLs from the prose: slug tokens must not act as subjects.
        # Label words stay for subject identity, but their standalone numbers
        # are masked so name digits never extract as claim values (G-F6 tail).
        low = norm(BARE_URL_RE.sub(
            " ", LINK_RE.sub(lambda m: _LABEL_NUM_RE.sub(" ", m.group(1)), sent)))
        if not low:
            continue
        subs: dict[str, tuple] = {}
        for key in all_keys:
            toks = key.split()
            if _subject_discussed(low, toks):
                spans = _token_spans(low, toks)
                if spans:
                    frac = sum(t in low for t in toks) / len(toks)
                    subs[key] = (spans, frac)

        # price claims
        for m in _NUM_RE.finditer(low):
            if not _standalone_number(low, m.start(), m.end()):
                continue
            if _UNIT_AFTER.match(low[m.end():]):
                continue
            cue_win = low[max(0, m.start() - PRICE_CUE_WINDOW):
                          m.end() + PRICE_CUE_WINDOW]
            if "$" not in cue_win and not _PRICE_CUE.search(cue_win):
                continue
            key, _span = _nearest_subject(subs, m.start())
            if forced_key is not None:
                key = forced_key   # the sentence cites exactly one entity
            if key is None:
                unbound += 1
                continue
            targets = price_of.get(key)
            if not targets:
                untestable += 1
                continue
            try:
                val = round(float(m.group()), 2)
            except ValueError:
                continue
            ok = _price_close(val, targets)
            support += ok
            contra += not ok
            per.append((key[:36], "price", m.group(),
                        sorted(targets), "OK" if ok else "X"))

        # overall-rating claims
        for m in _RATING_CLAIM.finditer(low):
            key, span = _nearest_subject(subs, m.start())
            if forced_key is not None and key is None:
                key, span = forced_key, (m.start(), m.end())
            if key is None:
                unbound += 1
                continue
            # aspect qualifier between the number and the subject anchor, or
            # attached right after the stars phrase ("5 stars for build")?
            lo = min(m.end(), span[1])
            hi = max(m.start(), span[0])
            between = low[lo:hi] if lo < hi else ""
            trailing = low[m.end(): m.end() + 24]
            if _ASPECT_QUALIFIER.search(between) or _ASPECT_QUALIFIER.search(trailing):
                skipped_aspect += 1
                continue
            targets = rating_of.get(key)
            if not targets:
                untestable += 1
                continue
            val = float(m.group(1))
            ok = any(abs(val - t) <= RATING_TOL for t in targets)
            support += ok
            contra += not ok
            per.append((key[:36], "rating", m.group(1),
                        sorted(targets), "OK" if ok else "X"))

    tested = support + contra
    detail = {
        "claims_tested": tested, "supported": support, "contradicted": contra,
        "unbound": unbound, "untestable": untestable,
        "skipped_aspect_rating": skipped_aspect, "k_f": k_f,
        "sample": per[:12],
    }
    if tested == 0:
        detail["reason"] = "no_checkable_claims"
        detail["precision"] = 0.0
        detail["recall_vol"] = 0.0
        return 0.0, detail
    precision = support / tested
    recall_vol = min(tested / k_f, 1.0)
    detail["precision"] = round(precision, 4)
    detail["recall_vol"] = round(recall_vol, 4)
    if precision <= 0.0 or recall_vol <= 0.0:
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


def _typed_value_in_window(win: str, n, alt_prices=()) -> bool:
    """Per-predicate typed value check inside a subject window (M-H2: NO
    global substring matching anywhere)."""
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
            if _price_close(round(float(m.group()), 2), targets):
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
        m = re.match(r"([\d.]+)%/(\d+)rev", str(n.object))
        if not m:
            return False
        rat, cnt = float(m.group(1)), m.group(2)
        for mm in _NUM_RE.finditer(win):
            v = float(mm.group())
            if abs(v - rat) <= 1.0 or abs(v - rat / 20.0) <= 0.1:
                return True
        return bool(re.search(rf"\b{cnt}\b", win))
    if n.predicate == "concept_coverage":
        # subject==concept; upstream _subject_discussed already established
        # the concept is discussed near this window
        return True
    obj = norm(str(n.object))
    return bool(obj) and obj in win


def score_completeness(md: str, answer_key, k_star: int = K_STAR_DEFAULT,
                       pool_size: int | None = None,
                       generic: set | None = None) -> tuple[float, dict]:
    """axis 3: SATURATING recall over the ranked vital pool (T1/T2/M-H1/H2).

    completeness = min(covered_vital / K_star, 1). K_star defaults to 20,
    following SAFE's saturating recall R_K = min(S/K, 1) and DRBench's
    k = |gold| + 5, both of which cap the credited gold set at a small
    vital-insight budget instead of demanding a census of the catalog: a
    focused shortlist that nails 20 vital facts scores 1.0, and dumping 40
    catalog rows no longer beats it (T1). This is the ONLY completeness
    implementation in the codebase: the checklist verifier and the composition
    must both call it (T2), so the number displayed is the number scored.

    A vital fact counts as covered only if the report discusses its subject
    (distinctive identity tokens) AND the typed value appears within the
    +-40 char window of a subject mention, with per-predicate tolerance:
    price 0.02 absolute or 1 percent relative (special_price also accepted),
    rating +-0.15, thread_score exact-in-window. No global substring matching
    anywhere (M-H2)."""
    text = norm(md)
    generic = generic if generic is not None else build_generic_tokens(answer_key)
    pool = build_vital_pool(answer_key, k_star=k_star, pool_size=pool_size)
    if not pool:
        return 0.0, {"pool": 0, "k_star": k_star, "covered": 0,
                     "reason": "empty_vital_pool"}
    ents = {e.url: e for e in answer_key.relevant_set}
    covered = 0
    sample = []
    for n in pool:
        stoks = name_key(n.subject, generic).split()
        if not stoks or not _subject_discussed(text, stoks):
            continue
        spans = _token_spans(text, stoks)
        e = ents.get(n.source_url)
        alt = []
        if e is not None and (e.facts or {}).get("special_price") is not None:
            try:
                alt.append(round(float(e.facts["special_price"]), 2))
            except (TypeError, ValueError):
                pass
        hit = False
        for s, en in spans:
            win = text[max(0, s - BIND_WINDOW): en + BIND_WINDOW]
            if _typed_value_in_window(win, n, alt_prices=alt):
                hit = True
                break
        covered += hit
        if hit and len(sample) < 10:
            sample.append((n.subject[:40], n.predicate, str(n.object)[:12]))
    return min(covered / k_star, 1.0), {
        "pool": len(pool), "k_star": k_star, "covered": covered,
        "covered_sample": sample}


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
    return passed / len(reqs), {"requirements": len(reqs), "passed": passed, "per": per}


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
        bullets = len(re.findall(r"(?m)^\s*[-*+]\s+", md))
        return bullets <= p.get("max", 999) if p.get("global") else True
    if r.kind == "min_words":
        return len(md.split()) >= p.get("min", 0)
    return False


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def compose_truth(reach: float, fact: float, pof: float, completeness: float,
                  spec: float, gamma: float = GAMMA_DEFAULT,
                  eps: float = EPS_FLOOR) -> tuple[float, float, dict]:
    """truth = reach**gamma * quality (M-C2/H3/H4/H5/L1).

    quality = 0.35*fact + 0.25*pof + 0.30*completeness + 0.10*spec, with each
    quality axis floored at eps AFTER computation (floors stop matcher-error
    annihilation, M-H5) and reach UNfloored (it is the anti-fabrication gate:
    a pure fabricator collapses to 0). gamma defaults to 1.5 and is to be
    calibrated EXTERNALLY on an injected-fabrication set (M-H3); sensitivity()
    is the accompanying rank-stability probe. Returns (truth, quality,
    floors_applied)."""
    floors_applied = {}
    vals = {}
    for name, v in (("fact_support", fact), ("proof_of_fetch", pof),
                    ("completeness", completeness), ("spec", spec)):
        f = max(eps, float(v))
        floors_applied[name] = f > float(v)
        vals[name] = f
    quality = sum(QUALITY_WEIGHTS[k] * vals[k] for k in QUALITY_WEIGHTS)
    truth = (max(0.0, float(reach)) ** gamma) * quality
    return truth, quality, floors_applied


def score_report(md: str, answer_key, cache: dict, registry=None,
                 gamma: float = GAMMA_DEFAULT, k_f: int = K_F_DEFAULT,
                 k_star: int = K_STAR_DEFAULT,
                 pof_threshold: float = POF_THRESHOLD_DEFAULT,
                 eps: float = EPS_FLOOR) -> AxisScores:
    """Compute all decidable axes and the composed truth score.

    Returns axes + truth ONLY (M-C1): presentation is a separate column,
    fused (if at all) as a bounded tie-breaker downstream, never multiplied
    into truth."""
    cache = cache or {}
    urls = _cited_urls(md)
    reach, rd = score_reachability(urls, cache, registry)
    stats = build_page_stats(cache)
    pof, pd = score_proof_of_fetch(md, cache, page_stats=stats,
                                   threshold=pof_threshold)
    generic = build_generic_tokens(answer_key)
    fact, fd = score_fact_support(md, answer_key, generic=generic, k_f=k_f)
    comp, cd = score_completeness(md, answer_key, k_star=k_star, generic=generic)
    spec, sd = score_spec(md, answer_key)

    truth, quality, floors = compose_truth(reach, fact, pof, comp, spec,
                                           gamma=gamma, eps=eps)
    s = AxisScores(
        reach=reach, proof_of_fetch=pof, fact_support=fact,
        fact_contradicted=fd.get("contradicted", 0),
        fact_absent=fd.get("unbound", 0) + fd.get("untestable", 0),
        completeness=comp, spec=spec, quality=quality, truth=truth)
    s.detail = {
        "reach": rd, "proof_of_fetch": pd, "fact": fd,
        "completeness": cd, "spec": sd,
        "floors_applied": floors, "gamma": gamma, "eps": eps,
        "quality_weights": dict(QUALITY_WEIGHTS),
        "quality": round(quality, 4), "truth": round(truth, 6),
        "counts": {
            "reach_num": rd.get("num", 0), "reach_den": rd.get("den", 0),
            "pof_passed": pd.get("passed", 0), "pof_checked": pd.get("checked", 0),
            "fact_supported": fd.get("supported", 0),
            "fact_tested": fd.get("claims_tested", 0),
            "comp_covered": cd.get("covered", 0),
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
            float(ax.get("grounding_proof_of_fetch", ax.get("proof_of_fetch", 0.0))),
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
        rvol = min(tested / (k_f * n), 1.0)
        micro_fact = 0.0 if (p <= 0 or rvol <= 0) else 2 * p * rvol / (p + rvol)
    else:
        micro_fact = 0.0
    micro_comp = min(tot.get("comp_covered", 0) / (k_star * n), 1.0)
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
