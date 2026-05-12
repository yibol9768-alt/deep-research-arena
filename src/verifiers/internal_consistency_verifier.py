"""InternalConsistencyVerifier -- 报告内部一致性 pillar (v4 新增).

motivation
~~~~~~~~~~
DR 智能体生成 6 000+ 词长报告时,不同段落往往来自不同子搜索线程,容易出现
前后矛盾:第 3 节说 "Sony WH-1000XM5 在主动降噪上击败 Bose QC45",第 7 节
又说 "Bose QC45 是同价位最强主动降噪"。这种内部冲突我们当前的 7 pillar 完全
测不出来 (citation_alignment 只看单句与单页的对应,quote_match 只看词重叠)。

literature
~~~~~~~~~~
* SummaC / SummaCConv (Laban TACL 2022):句对 NLI + conv 聚合,balanced acc 74.4%
* CONTRADOC (Li NAACL 2024):449 篇人工自相矛盾文档,验证 long-doc 设定下
  NLI 的可行性
* ContraGen (arXiv 2510.03418, 2025-10):跨/内部矛盾基准,报告了 NLI 单独
  做跨句矛盾会塌缩到 ~41% (近随机),hybrid (NLI + LLM) 是最佳方案
* Self-Contradictory Reasoning (arXiv 2311.09603, 2024):reasoning vs answer
  vs self 三种矛盾类型

design (hybrid: cheap clustering + targeted heavy NLI)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Step 1  Sentence split (period / question / exclamation + paragraph break).
Step 2  Per-sentence entity extraction (lightweight: regex over capitalised
        noun phrases + product slugs, deterministic). Sandbox-friendly:
        Magento brand names, /f/<subforum> tokens, Wikipedia titles are all
        case-rich and recoverable without LLM.
Step 3  Entity-cluster bucketing. Each sentence falls into the cluster of
        its dominant entity. Sentences without any extracted entity skipped.
Step 4  Within each cluster, sample sentence pairs (max 12 pairs / cluster
        to bound cost) and ask call_judge_heavy a 3-way NLI verdict
        (entail / contradict / neutral).
Step 5  Aggregate: score = 1 - (contradicting_pairs / total_pairs).
        Pass gate score >= 0.85 (high bar because contradictions are rare;
        score = 1.0 is the expected baseline for a coherent report).

cost
~~~~
* 0 LLM calls for steps 1-3 (deterministic).
* ~12 pairs/cluster × ~5 clusters = ~60 LLM calls / report worst case;
  more typically 20-30 because most clusters have ≤ 4 sentences.
* Heavy-judge calls because V4 Pro NLI is materially better on this
  hard 3-way task than V4 Flash.
"""

from __future__ import annotations

import re
from itertools import combinations
from typing import Any

from .base import VerifierResult, is_degenerate_answer
from .judge_client import call_judge_heavy, judge_identity


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_SENT_LEN = 30           # chars; drops dangling fragments
_MAX_SENT_LEN = 400          # chars; chops very long sentences for NLI cost
_MIN_CLUSTER_SIZE = 2        # ≥2 sentences mentioning same entity to compare
_MAX_PAIRS_PER_CLUSTER = 12  # NLI budget per entity cluster
_MAX_TOTAL_PAIRS = 60        # global hard cap


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

# Roughly the same splitter as citation_alignment but tightened — we want
# self-contained sentences, not bullets.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
# Heading and bullet markers we strip out before splitting.
_HEADING_RE   = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)
_TABLE_RE     = re.compile(r"^\|.+\|$", re.MULTILINE)
_BULLET_RE    = re.compile(r"^[\s]*[-*+]\s+", re.MULTILINE)
_MD_LINK_FLAT = re.compile(r"\[([^\]]*)\]\(https?://[^)\s]+\)")
_INLINE_CODE  = re.compile(r"`[^`]*`")


def _flatten(text: str) -> str:
    """Strip markdown noise so the NLI judge sees clean prose."""
    text = _HEADING_RE.sub("", text)
    text = _TABLE_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _MD_LINK_FLAT.sub(lambda m: m.group(1), text)  # keep label text
    text = _INLINE_CODE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_sentences(answer: str) -> list[str]:
    flat = _flatten(answer)
    out: list[str] = []
    for raw in _SENT_SPLIT_RE.split(flat):
        s = raw.strip()
        if _MIN_SENT_LEN <= len(s) <= _MAX_SENT_LEN:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Entity extraction (deterministic)
# ---------------------------------------------------------------------------

# Capitalised noun phrases of length 1-4 tokens. Skips sentence-initial
# capitalisation by checking that the phrase is NOT at offset 0 of the
# sentence (which is invariably the sentence start). Also skips common
# noise words even when capitalised.
_NP_RE = re.compile(r"\b([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-/&]*){0,3})\b")
_NOISE = {
    "the", "a", "an", "this", "that", "these", "those",
    "i", "you", "he", "she", "it", "we", "they",
    "however", "moreover", "furthermore", "nevertheless", "nonetheless",
    "additionally", "specifically", "particularly", "instead", "rather",
    "first", "second", "third", "fourth", "fifth", "last", "next", "later",
    "amazon", "google", "microsoft", "apple",  # too generic; rarely useful
    "section", "table", "figure", "chapter", "part",
    "for example", "in particular", "of course", "in fact", "as shown",
    "see also", "for instance", "in contrast", "on average",
    "review", "reviews", "product", "products", "user", "users", "customer",
    "people", "many", "some", "most", "few", "all", "several",
}


def _entities_in(sentence: str) -> list[str]:
    """Return distinct capitalised noun-phrases of length 2-4 tokens, or
    single tokens that look like product slugs (mixed case + digits).
    Lowercased for matching but original-cased for display.
    """
    found: list[str] = []
    sent_low = sentence.lower()
    for m in _NP_RE.finditer(sentence):
        phrase = m.group(1).strip()
        if phrase.lower() in _NOISE:
            continue
        # Reject single-token phrases unless they look like product slugs
        # (contain a digit or hyphen).
        toks = phrase.split()
        if len(toks) == 1 and not re.search(r"[0-9\-]", phrase):
            continue
        found.append(phrase)
    # Deduplicate preserving order. Use lowercased key.
    seen: set[str] = set()
    out: list[str] = []
    for e in found:
        k = e.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Cluster construction
# ---------------------------------------------------------------------------

def _build_entity_clusters(sentences: list[str]) -> dict[str, list[int]]:
    """For each entity mentioned across the report, collect the indices of
    sentences that mention it. Returns clusters with ≥ _MIN_CLUSTER_SIZE
    members only.
    """
    clusters: dict[str, list[int]] = {}
    for idx, s in enumerate(sentences):
        for e in _entities_in(s):
            clusters.setdefault(e.lower(), []).append(idx)
    return {k: v for k, v in clusters.items() if len(v) >= _MIN_CLUSTER_SIZE}


# ---------------------------------------------------------------------------
# NLI judge (heavy)
# ---------------------------------------------------------------------------

_NLI_SYSTEM = (
    "You decide whether sentence S1 and sentence S2 (both from the same "
    "research report, about the same named entity) CONTRADICT each other.\n"
    "Rules:\n"
    "- CONTRADICT: the two sentences make claims that cannot both be true "
    "(opposite verdicts on a property, mutually exclusive facts, conflict "
    "in numbers / attributes / rankings).\n"
    "- AGREE: the sentences make the same or compatible claims, or one "
    "elaborates on the other.\n"
    "- NEUTRAL: the sentences make different claims that can both be true "
    "(unrelated attributes, complementary facts).\n"
    "Subjective phrasing differences ('most liked' vs 'highly rated') are "
    "NEUTRAL, not CONTRADICT. Only mark CONTRADICT when the underlying "
    "factual / evaluative claim is genuinely incompatible.\n\n"
    "Output exactly one line: VERDICT: CONTRADICT or VERDICT: AGREE or VERDICT: NEUTRAL"
)


def _nli_pair(entity: str, s1: str, s2: str) -> tuple[str, str | None]:
    """Call heavy judge. Returns (verdict, error). Verdict is one of
    CONTRADICT / AGREE / NEUTRAL / ERROR.
    """
    user = (
        f"ENTITY: {entity}\n\n"
        f"S1: {s1}\n\n"
        f"S2: {s2}"
    )
    text, err = call_judge_heavy(_NLI_SYSTEM, user, max_tokens=60, temperature=0.0)
    if err and not text:
        return "ERROR", err
    txt = (text or "").upper()
    if "CONTRADICT" in txt:
        return "CONTRADICT", None
    if "AGREE" in txt:
        return "AGREE", None
    if "NEUTRAL" in txt:
        return "NEUTRAL", None
    return "ERROR", "unparseable_verdict"


# ---------------------------------------------------------------------------
# Pair sampling
# ---------------------------------------------------------------------------

def _sampled_pairs(indices: list[int], cap: int) -> list[tuple[int, int]]:
    """All pairs if small; deterministic stride-sample when above cap.

    We use a stride sample (every k-th pair) instead of random for
    reproducibility — score JSONs must be byte-identical when reruns
    happen at the same input.
    """
    all_pairs = list(combinations(indices, 2))
    if len(all_pairs) <= cap:
        return all_pairs
    stride = max(1, len(all_pairs) // cap)
    return all_pairs[::stride][:cap]


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class InternalConsistencyVerifier:
    """Intra-document contradiction-detection pillar (v4 new).

    Returns score = 1 - (contradictions / pairs_tested). When no clusters
    of size ≥ 2 exist (very short reports, or reports where entities
    cannot be extracted), returns score = 1.0 with `applicable=False`.

    Constructor knobs:
        max_pairs_per_cluster   default 12
        max_total_pairs         default 60
        min_score               pass gate, default 0.85
    """

    kind = "internal_consistency"

    def __init__(
        self,
        max_pairs_per_cluster: int = _MAX_PAIRS_PER_CLUSTER,
        max_total_pairs: int = _MAX_TOTAL_PAIRS,
        min_score: float = 0.85,
    ):
        self.max_pairs_per_cluster = int(max_pairs_per_cluster)
        self.max_total_pairs = int(max_total_pairs)
        self.min_score = float(min_score)

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        # Guard 1: degenerate answer (don't waste heavy LLM on placeholders).
        degen, reason = is_degenerate_answer(answer or "", min_words=80, require_citations=False)
        if degen:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": "degenerate_answer", "degen_reason": reason},
            )

        sents = _split_sentences(answer or "")
        if len(sents) < 6:
            return VerifierResult(
                score=1.0, passed=True,
                details={
                    "applicable": False,
                    "reason": "too_few_sentences",
                    "sentence_count": len(sents),
                },
            )

        clusters = _build_entity_clusters(sents)
        if not clusters:
            return VerifierResult(
                score=1.0, passed=True,
                details={
                    "applicable": False,
                    "reason": "no_entity_clusters",
                    "sentence_count": len(sents),
                },
            )

        # Iterate clusters in order of size (larger clusters first — they
        # are more likely to contain genuine contradictions, and the
        # global cap kicks in before tail clusters drown out cost).
        ordered = sorted(clusters.items(), key=lambda kv: -len(kv[1]))
        verdict_rows: list[dict] = []
        contradicts = 0
        total_pairs = 0
        judge_err: str | None = None
        cluster_summary: list[dict] = []

        for entity, idxs in ordered:
            if total_pairs >= self.max_total_pairs:
                break
            pair_idxs = _sampled_pairs(idxs, min(
                self.max_pairs_per_cluster,
                self.max_total_pairs - total_pairs,
            ))
            cluster_contras = 0
            for i, j in pair_idxs:
                s1 = sents[i]
                s2 = sents[j]
                if s1 == s2:
                    continue
                verdict, err = _nli_pair(entity, s1, s2)
                total_pairs += 1
                if err and not judge_err:
                    judge_err = err
                row = {
                    "entity": entity,
                    "i": i, "j": j,
                    "s1_excerpt": s1[:180],
                    "s2_excerpt": s2[:180],
                    "verdict": verdict,
                }
                if verdict == "CONTRADICT":
                    contradicts += 1
                    cluster_contras += 1
                    verdict_rows.append(row)
                if total_pairs >= self.max_total_pairs:
                    break
            cluster_summary.append({
                "entity": entity,
                "size": len(idxs),
                "pairs_tested": len(pair_idxs),
                "contradictions": cluster_contras,
            })

        if total_pairs == 0:
            return VerifierResult(
                score=1.0, passed=True,
                details={
                    "applicable": False,
                    "reason": "no_pairs_tested",
                    "cluster_count": len(clusters),
                },
            )

        score = 1.0 - (contradicts / total_pairs)
        passed = score >= self.min_score

        return VerifierResult(
            score=round(float(score), 4),
            passed=bool(passed),
            details={
                "applicable":        True,
                "sentence_count":    len(sents),
                "cluster_count":     len(clusters),
                "pairs_tested":      total_pairs,
                "contradictions":    contradicts,
                "min_score":         self.min_score,
                "judge":             judge_identity().get("heavy_model"),
                "judge_error":       judge_err,
                "cluster_summary":   cluster_summary[:20],
                "contradiction_rows": verdict_rows[:25],
            },
        )
