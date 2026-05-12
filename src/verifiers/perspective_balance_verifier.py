"""PerspectiveBalanceVerifier -- 视角与立场平衡 pillar (v4 新增).

motivation
~~~~~~~~~~
对于评价类 / 推荐类 / 比较类任务,一份合格的 DR 报告应当同时呈现正面与
负面视角。例如「推荐头部 ANC 耳机」任务,如果智能体只夸 Sony / Bose
而完全不提它们的缺点 (续航焦虑、舒适度、价位过高等等),即便引文都真、
覆盖也广,这份报告的可信度也是低的。DRACO (Perplexity 2025) 把 objectivity
作为 presentation 子维度,LiveResearchBench / DeepEval 把它列在六维体系
里的 Factual & Logical Consistency 旁边。我们目前的 7 pillar 完全没测它。

design (two-tier, mirrors presentation / analysis_depth pattern)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tier A (deterministic, sentiment lexicon)
    对从报告中抽取的「被评价实体」(典型:商品名 / 品牌 / 论坛主题词),
    在其周围 ±100 字符窗口里数 positive / negative 情感词频。要求每个
    实体的负向词频 ≥ 1 且 正:负 ≤ 5:1。
    词典:打包了一份 ~250 词的双向情感词典 (英文,VADER 风格 + DR 域增补),
    完全离线,跑两次给同样结果。

Tier B (LLM judge, V4 Flash 默认 / 可调)
    对每个被评价实体,单一二值问题:「这份报告是否对 <entity> 给出至少
    一条具体且非琐碎的局限 / 缺点 / 反对意见?」 PASS / FAIL.
    一次 LLM 调用 / 实体,典型报告 ~5-10 个评价对象,~5-10 LLM 调用。

Score = 0.4 · tier_a_rate + 0.6 · tier_b_rate

design notes
~~~~~~~~~~~~
* 实体抽取走两条路:
  (a) 任务 spec 显式声明 evaluated_entities 列表 — 推荐任务通常会;
  (b) 否则从报告 H2 / H3 标题中抽取 (启发式,降级方案)。
* 非评价类任务 (timeline / debunk / enumerate) 没有评价对象,此时
  score = 1.0,意为「不适用本维度,不扣分」。
* 词典放在文件末尾,可读且可改。
"""

from __future__ import annotations

import re
from typing import Any

from .base import VerifierResult, is_degenerate_answer
from .judge_client import call_judge, judge_identity


# ---------------------------------------------------------------------------
# Sentiment lexicon (~250 words, DR-domain augmented)
# ---------------------------------------------------------------------------

_POSITIVE_WORDS = {
    # Generic positive
    "excellent", "outstanding", "superior", "superb", "exceptional",
    "great", "good", "best", "better", "top", "leading", "premier",
    "impressive", "remarkable", "stunning", "perfect", "ideal",
    "recommended", "recommend", "preferable", "preferred", "favorite",
    "favourite", "outstanding", "powerful", "robust", "reliable",
    "stable", "consistent", "smooth", "elegant", "clean", "polished",
    "refined", "premium", "high-quality", "high-end", "professional",
    "praised", "praises", "praise", "acclaimed", "acclaim",
    "loved", "loves", "love", "favorite", "celebrated", "celebrate",
    "advantage", "advantages", "strength", "strengths", "pro", "pros",
    "benefit", "benefits", "beneficial", "valuable", "worthwhile",
    # DR / product-review positive
    "comfortable", "lightweight", "long-lasting", "long-battery",
    "clear", "crisp", "rich", "balanced", "natural", "warm", "detailed",
    "wide-soundstage", "soundstage", "immersive", "punchy",
    "well-built", "sturdy", "durable", "well-designed",
    "intuitive", "user-friendly", "seamless", "responsive", "fast",
    "accurate", "precise", "effective", "efficient",
    # Recommendation language
    "must-have", "must-buy", "buy", "purchase", "worth", "deserves",
    "endorse", "endorsement", "support", "supports", "approve", "approves",
}

_NEGATIVE_WORDS = {
    # Generic negative
    "poor", "bad", "worst", "worse", "inferior", "subpar", "mediocre",
    "disappointing", "disappointed", "disappoint", "weak", "lackluster",
    "lacking", "lacks", "lack", "missing", "absent", "deficient",
    "flawed", "flaw", "flaws", "defective", "defect", "defects",
    "broken", "buggy", "unstable", "unreliable", "inconsistent",
    "problem", "problems", "problematic", "issue", "issues",
    "complain", "complaint", "complaints", "criticized", "criticism",
    "criticize", "criticizes", "negative", "concerns", "concern",
    "disadvantage", "disadvantages", "weakness", "weaknesses",
    "con", "cons", "drawback", "drawbacks", "downside", "downsides",
    "limitation", "limitations", "limit", "limits", "limited",
    "compromise", "compromises", "tradeoff", "tradeoffs", "trade-off",
    "but", "however", "although", "though", "despite", "yet",
    # Strong negative
    "terrible", "awful", "horrible", "useless", "worthless", "junk",
    "garbage", "trash", "fail", "fails", "failed", "failure",
    # DR / product-review negative
    "uncomfortable", "heavy", "bulky", "short-battery", "short-lived",
    "muddy", "harsh", "tinny", "bright", "sibilant", "boomy",
    "flimsy", "fragile", "cheap-feeling", "plastic", "creaky",
    "clunky", "unintuitive", "confusing", "laggy", "slow",
    "inaccurate", "imprecise", "ineffective", "inefficient",
    # Price / value negative
    "overpriced", "expensive", "costly", "pricey", "not-worth", "not-recommended",
    "avoid", "skip", "regret", "returned", "refunded",
    # Discrepancy / contradiction
    "contradicts", "contradict", "contradiction", "conflicting",
    "disputed", "dispute", "disagreement", "disagree", "disputed",
    "controversial", "questioned", "questionable",
}


_PUNCT_SPLIT_RE = re.compile(r"[^\w\-]+")


def _tokens(text: str) -> list[str]:
    """Lowercase tokenisation, preserving intra-word hyphens (so
    'short-battery' / 'long-lasting' match the lexicon)."""
    return [t for t in _PUNCT_SPLIT_RE.split(text.lower()) if t]


def _entity_window(text: str, entity: str, window: int = 100) -> str:
    """Return all char-windows in `text` around occurrences of `entity`,
    concatenated. Case-insensitive match. Returns "" when not mentioned.
    """
    if not entity:
        return ""
    pat = re.compile(r"\b" + re.escape(entity) + r"\b", re.IGNORECASE)
    chunks: list[str] = []
    for m in pat.finditer(text):
        a = max(0, m.start() - window)
        b = min(len(text), m.end() + window)
        chunks.append(text[a:b])
    return " ".join(chunks)


def _sentiment_counts(snippet: str) -> tuple[int, int]:
    """Return (positive_word_count, negative_word_count) over `snippet`."""
    pos = neg = 0
    for tok in _tokens(snippet):
        if tok in _POSITIVE_WORDS:
            pos += 1
        elif tok in _NEGATIVE_WORDS:
            neg += 1
    return pos, neg


def _tier_a(answer: str, entities: list[str]) -> tuple[float, list[dict]]:
    """Per-entity sentiment ratio check.

    For each entity:
      * collect ±100-char windows around its mentions;
      * count positive & negative tokens;
      * pass condition: neg >= 1 AND pos / max(neg, 1) <= 5.0

    Returns (rate = passed / total, per_entity_breakdown).
    """
    if not entities:
        # No evaluated entities means this dimension does not apply to
        # this task (timeline / debunk / enumerate). Score 1.0 = neutral.
        return 1.0, []
    rows = []
    passed = 0
    for ent in entities:
        win = _entity_window(answer, ent, window=100)
        if not win:
            rows.append({
                "entity": ent, "mentioned": False,
                "positive": 0, "negative": 0, "ratio": 0.0, "passed": False,
            })
            continue
        pos, neg = _sentiment_counts(win)
        ratio = (pos / neg) if neg > 0 else float("inf")
        ok = (neg >= 1) and (ratio <= 5.0)
        if ok:
            passed += 1
        rows.append({
            "entity": ent, "mentioned": True,
            "positive": pos, "negative": neg,
            "ratio": round(ratio if neg > 0 else 99.9, 2),
            "passed": bool(ok),
        })
    rate = passed / len(entities)
    return rate, rows


# ---------------------------------------------------------------------------
# Tier B (LLM judge)
# ---------------------------------------------------------------------------

_TIER_B_SYSTEM = (
    "You evaluate whether a research report gives at least one specific, "
    "non-trivial LIMITATION / CRITICISM / DOWNSIDE for a named entity.\n"
    "Rules:\n"
    "- PASS only if the report mentions a concrete shortcoming "
    "(weak ANC at low frequencies, short battery, build-quality issue, "
    "value-for-money concern, customer-service complaint, etc).\n"
    "- 'Some users may prefer X' is NOT a specific limitation — FAIL.\n"
    "- Generic disclaimers ('no product is perfect') are NOT specific — FAIL.\n"
    "- 'X has been criticized for Y' WITH Y being a concrete attribute — PASS.\n"
    "Output exactly: VERDICT: PASS or VERDICT: FAIL"
)


def _tier_b(answer: str, entities: list[str]) -> tuple[float, list[dict], str | None]:
    """Per-entity LLM verdict.

    Returns (rate, per_entity_breakdown, judge_error). When entities is
    empty, returns (1.0, [], None) — task is not perspective-bearing.
    """
    if not entities:
        return 1.0, [], None
    rows = []
    passes = 0
    judge_err: str | None = None
    for ent in entities:
        # Per-entity prompt is small (~ entity + 6k chars of report excerpts);
        # we keep the report short by extracting a ±400-char window per
        # mention of the entity, capped at ~6 windows / 4kb total.
        win = _entity_window(answer, ent, window=400)
        if len(win) > 4000:
            win = win[:4000]
        if not win:
            rows.append({"entity": ent, "verdict": "FAIL", "reason": "not_mentioned"})
            continue
        user = (
            f"ENTITY: {ent}\n\n"
            f"REPORT EXCERPTS:\n{win}\n\n"
            "Question: Does the report give AT LEAST ONE specific, "
            "non-trivial limitation / criticism / downside about this entity?"
        )
        text, err = call_judge(_TIER_B_SYSTEM, user, max_tokens=100, temperature=0.0)
        if err and not text:
            judge_err = err
            rows.append({"entity": ent, "verdict": "ERROR", "reason": err})
            continue
        verdict = "FAIL"
        if text and "PASS" in text.upper():
            verdict = "PASS"
            passes += 1
        rows.append({"entity": ent, "verdict": verdict})
    rate = passes / len(entities)
    return rate, rows, judge_err


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
# Strip common section labels that aren't entities to evaluate.
_SECTION_NOISE = re.compile(
    r"^(introduction|conclusion|references|methodology|background|"
    r"overview|summary|appendix|outline|findings|results|discussion|"
    r"part [a-z\d]+|section [a-z\d]+|product landscape|community sentiment|"
    r"technical context|technical foundation|cross-source synthesis|"
    r"buying guide|recommendations?|comparison)",
    re.IGNORECASE,
)


def _extract_entities(task_config: dict[str, Any], answer: str) -> list[str]:
    """Resolve the list of entities to evaluate.

    Priority order:
      1. task_config["perspective_balance"]["evaluated_entities"]
      2. task_config["evaluated_entities"]  (top-level convenience)
      3. Heuristic: H3 headings under H2 sections that look like
         "Recommendations" / "Product Landscape" / "Top X" — capped at 12
         to bound LLM cost.

    Returns [] when nothing can be resolved (timeline / debunk / enumerate
    tasks usually don't have rated entities; the verifier scores 1.0).
    """
    cfg = task_config.get("perspective_balance") or {}
    cand: list[str] = (
        cfg.get("evaluated_entities")
        or task_config.get("evaluated_entities")
        or []
    )
    if cand:
        return [e for e in cand if isinstance(e, str) and e.strip()][:12]

    # Heuristic fallback: look at H3 headings; H2 are usually section names.
    entities: list[str] = []
    for m in _H3_RE.finditer(answer):
        title = m.group(1).strip()
        if not title or _SECTION_NOISE.match(title):
            continue
        # Strip leading rank labels like "1.", "(2)", "Top 1:" etc.
        title = re.sub(r"^[\(\[]?\d+[\)\].:\-]?\s*", "", title)
        title = re.sub(r"^top\s*\d+\s*[:\-]?\s*", "", title, flags=re.IGNORECASE)
        title = title.strip().strip("-:")
        # Drop overlong titles (likely full claims, not entities).
        if 3 <= len(title) <= 80:
            entities.append(title)
    # Dedupe preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for e in entities:
        key = e.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped[:12]


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class PerspectiveBalanceVerifier:
    """Two-tier perspective-balance pillar (v4 new).

    Score = 0.4·tier_a_rate + 0.6·tier_b_rate.

    Empty-entity tasks (timeline / debunk / enumerate) score 1.0 — the
    pillar is N/A on those tasks. This avoids penalising agents on
    tasks that don't have evaluated entities; if a task should be
    perspective-bearing, the task spec should list ``evaluated_entities``
    so the verifier picks them up.
    """

    kind = "perspective_balance"

    def __init__(self, tier_a_weight: float = 0.4, tier_b_weight: float = 0.6):
        if abs(tier_a_weight + tier_b_weight - 1.0) > 1e-6:
            raise ValueError("tier weights must sum to 1.0")
        self.tier_a_weight = tier_a_weight
        self.tier_b_weight = tier_b_weight

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        # Guard 1: degenerate answer.
        degen, reason = is_degenerate_answer(answer or "", min_words=50, require_citations=False)
        if degen:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": "degenerate_answer", "degen_reason": reason},
            )

        entities = _extract_entities(task_config, answer or "")
        if not entities:
            # Not a perspective-bearing task; return 1.0 (neutral),
            # mark `applicable=False` so callers can see this is N/A.
            return VerifierResult(
                score=1.0, passed=True,
                details={
                    "applicable": False,
                    "reason": "no_evaluated_entities",
                    "note": "task does not declare evaluated_entities and no H3 entity headings found",
                },
            )

        tier_a_rate, tier_a_rows = _tier_a(answer, entities)
        tier_b_rate, tier_b_rows, judge_err = _tier_b(answer, entities)

        score = (
            self.tier_a_weight * tier_a_rate
            + self.tier_b_weight * tier_b_rate
        )
        passed = score >= float((task_config.get("perspective_balance") or {}).get("min_score", 0.50))

        return VerifierResult(
            score=round(float(score), 4),
            passed=bool(passed),
            details={
                "applicable": True,
                "entities": entities,
                "tier_a": {
                    "weight": self.tier_a_weight,
                    "rate": round(tier_a_rate, 4),
                    "rows": tier_a_rows,
                },
                "tier_b": {
                    "weight": self.tier_b_weight,
                    "rate": round(tier_b_rate, 4),
                    "rows": tier_b_rows,
                    "judge": judge_identity()["model"],
                    "judge_error": judge_err,
                },
            },
        )
