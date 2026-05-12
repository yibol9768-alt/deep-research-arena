"""FactualExactnessVerifier -- atomic-fact precision pillar (v4 新增).

motivation
~~~~~~~~~~
我们目前的 quote_match / citation_alignment 都是「这一页是否大致支撑这个论断」
级别的检查,不验证「价格 $349」「评论数 1234」「电池寿命 30 小时」这类
具体数值是否与源页一致。这是 FactScore (Min EMNLP 2023) / SAFE (Wei 2024) /
VeriScore (Findings EMNLP 2024) / VeriFastScore (2025) 系列的核心评测对象,
我们 7 pillar 完全没覆盖这一轴。

approach
~~~~~~~~
分两步:
  Step 1  原子事实提取 (call_judge_heavy / 默认 V4 Pro)
          每个段落一次调用,输出 JSON list[{subject, predicate, object,
          source_url, value, value_type, raw_span}]
          重点抓 numeric / named-entity / quantitative / temporal facts —
          这些是沙盒中可结构化校验的部分。
  Step 2  逐条验证,deterministic-first:
          (a) 优先在源页用正则 / 字符串包含校验 (沙盒 60%+ 命中率)
          (b) 落空时用 call_judge_heavy 做 NLI 二次校验

Score = supported_facts / max(1, total_facts)
通过门 (passed): score >= min_score (default 0.50).

设计权衡
~~~~~~~~
* 不抽取无法验证的事实 (主观陈述、未来预测、推理结论)。提取 prompt 明确
  指示模型只输出可在源页验证的「硬事实」(数字 / 实体 / 关系)。
* 沙盒结构化数据帮我们把 LLM 比例压到 ~40%:Magento 商品页含 schema.org
  microdata 微数据,价格 / 星级 / 评论数都在固定 XPath 上;Kiwix 维基的
  infobox 数字也是结构化的。我们用 regex 在 cleaned HTML 上做第一遍校验。
* 资源上限:
    每报告 max_paragraphs       12  (优先选含 ≥ 2 citation 的段落)
    每报告 max_total_facts      40  (sampled when extractor returns more)
    每页 max_page_chars         8 000
    并发 fetch workers           4

cost estimate
~~~~~~~~~~~~~
12 段提取 + ~10 LLM-fallback 校验 = ~22 calls / 报告。
V4 Pro 调用比 Flash 贵 ~5×,但只用在 (a) 提取与 (b) deterministic 落空的
fallback,平均成本仍可控:~$0.20 / 报告。
"""

from __future__ import annotations

import concurrent.futures
import json
import re
from typing import Any

from .base import VerifierResult, is_degenerate_answer
from .citation_format import canonicalize_url, extract_citations, host_in_set
from .judge_client import call_judge_heavy, judge_identity


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_PARAGRAPHS = 12
_MAX_TOTAL_FACTS = 40
_MAX_PAGE_CHARS = 8_000
_FETCH_TIMEOUT = 8.0
_FETCH_RETRIES = 2
_FETCH_WORKERS = 4


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = (
    "You extract VERIFIABLE atomic facts from a research-report paragraph.\n"
    "An atomic fact is a single, self-contained, source-verifiable claim. "
    "Each fact must be checkable against ONE cited page.\n\n"
    "EXTRACT only facts of these types:\n"
    "  - numeric: price, rating, review count, battery hours, bandwidth, "
    "    year, percentage, count, dimension, weight, version number\n"
    "  - entity: brand, product name, model number, person, place, "
    "    organization, technology name, standard / RFC identifier\n"
    "  - relation: 'X has feature Y', 'X released in Y', 'X is sold at Y'\n\n"
    "DO NOT extract:\n"
    "  - subjective claims ('best sound', 'most comfortable')\n"
    "  - opinions / sentiment / recommendations\n"
    "  - speculation / predictions\n"
    "  - aggregations across pages (cross-source synthesis)\n"
    "  - the same fact stated multiple times\n\n"
    "Output strict JSON array, each element:\n"
    "  {\n"
    '    "subject":     "<short noun phrase, the entity/product/topic>",\n'
    '    "predicate":   "<short verb phrase, what we are claiming>",\n'
    '    "value":       "<the specific value being asserted, '
    'e.g. \\"$349\\", \\"30 hours\\", \\"Bluetooth 5.3\\", \\"2019\\">",\n'
    '    "value_type":  "<one of: price | rating | count | duration | '
    'frequency | year | percentage | dimension | weight | version | '
    'entity | relation>",\n'
    '    "source_url":  "<the cited URL this fact is anchored to '
    '(must appear in the paragraph as a [text](url) citation)>",\n'
    '    "raw_span":    "<the verbatim sentence fragment, max 220 chars>"\n'
    "  }\n\n"
    "Output ONLY the JSON array. No prose. If no verifiable atomic facts "
    "exist, output []."
)


# ---------------------------------------------------------------------------
# Source-page fetch (reuse pattern from citation_alignment_verifier)
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Remove script/style/nav and HTML tags, return plain text."""
    html = re.sub(
        r"<\s*(script|style|nav|footer|header|noscript|aside|svg)"
        r"[^>]*>.*?</\s*\1\s*>",
        " ", html, flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fetch_url(url: str) -> tuple[str, str | None]:
    """Fetch URL, strip HTML, return (url, body_or_None)."""
    try:
        import requests  # type: ignore
    except ImportError:
        return url, None
    for attempt in range(_FETCH_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=_FETCH_TIMEOUT,
                allow_redirects=True,
                headers={"User-Agent": "deep-factual-exactness/1.0"},
            )
            if resp.status_code != 200:
                if attempt == _FETCH_RETRIES:
                    return url, None
                continue
            body = _strip_html(resp.text)[:_MAX_PAGE_CHARS]
            return url, body
        except Exception:
            if attempt == _FETCH_RETRIES:
                return url, None
    return url, None


# ---------------------------------------------------------------------------
# Deterministic verification (regex + string)
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_PRICE_RE = re.compile(r"[$£€¥]\s?(\d+(?:[.,]\d+)?)")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def _numeric_canon(s: str) -> str | None:
    """Return canonical numeric token (digits-only, no commas/dots-as-thousands)
    of the first number in ``s``; None if none found.

    Used to compare two textual numbers (e.g. "1,234" vs "1234") for
    equality despite formatting.
    """
    if not s:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    raw = m.group(0)
    # Strip leading +/- and treat both . and , as thousand separators OR
    # decimal — heuristic: if exactly one of them appears AND only at one
    # position from the right, it's decimal; otherwise treat as thousands.
    sign = ""
    if raw.startswith(("-", "+")):
        sign = raw[0]
        raw = raw[1:]
    if raw.count(".") == 1 and raw.count(",") == 0:
        # 12.34 — could be decimal. Treat as decimal if .NN looks like
        # cents / fractional.
        int_part, frac = raw.split(".")
        if 1 <= len(frac) <= 2:
            return sign + int_part + "." + frac
        return sign + raw.replace(".", "")
    return sign + raw.replace(",", "").replace(".", "")


def _value_in_page(value: str, value_type: str, page_text: str) -> bool:
    """Return True if `value` of `value_type` is found verbatim or via
    type-specific extraction in page_text.

    Strategy by value_type:
      price       → match $NNN.NN with same magnitude OR raw substring
      year        → 4-digit year exact substring (since 1900-2099)
      percentage  → NN% substring
      count / duration / rating / frequency / dimension / weight / version
                  → numeric canon equality OR raw substring
      entity      → case-insensitive substring search
      relation    → loose: each whitespace-separated token (≥ 3 chars) of
                    value must appear in page (limited to ≤ 8 tokens)
    """
    if not value or not page_text:
        return False
    val = value.strip()
    txt = page_text.lower()
    v_low = val.lower()

    # Step 1: exact case-insensitive substring match — covers entities,
    # brand strings, version numbers like "Bluetooth 5.3", and most
    # numeric values when authors don't change formatting.
    if v_low in txt:
        return True

    # Step 2: type-specific structural match.
    if value_type == "price":
        nums = _PRICE_RE.findall(page_text)
        v_canon = _numeric_canon(val)
        if v_canon and any(_numeric_canon(n) == v_canon for n in nums):
            return True
    elif value_type in {"year"}:
        if val in page_text and _YEAR_RE.fullmatch(val):
            return True
    elif value_type in {"percentage"}:
        nums = _PERCENT_RE.findall(page_text)
        v_canon = _numeric_canon(val.rstrip("%"))
        if v_canon and any(_numeric_canon(n) == v_canon for n in nums):
            return True
    elif value_type in {"count", "duration", "rating", "frequency", "dimension", "weight", "version"}:
        # Numeric token equality.
        v_canon = _numeric_canon(val)
        if v_canon:
            for n in _NUM_RE.findall(page_text):
                if _numeric_canon(n) == v_canon:
                    return True
    elif value_type == "relation":
        # Loose token-overlap: requires all major tokens of value to appear.
        toks = [t for t in re.split(r"\s+", v_low) if len(t) >= 3][:8]
        if toks and all(t in txt for t in toks):
            return True

    return False


# ---------------------------------------------------------------------------
# LLM fallback (NLI-style binary verdict)
# ---------------------------------------------------------------------------

_VERIFY_SYSTEM = (
    "You verify whether a specific atomic fact is SUPPORTED by a web page.\n"
    "Rules:\n"
    "- SUPPORTED: the page contains the claimed value (or a synonymous/"
    "equivalent statement). Different units OK if equivalent "
    "(e.g. 30 hours ≡ '30 hr'). Different word order OK.\n"
    "- NOT_SUPPORTED: the page contradicts the value, is about a "
    "different entity, or simply does not state the value.\n"
    "Output exactly: VERDICT: SUPPORTED or VERDICT: NOT_SUPPORTED"
)


def _llm_verify(fact: dict, page_body: str) -> tuple[bool, str | None]:
    """Ask the heavy judge whether `fact` is supported by `page_body`.
    Returns (supported, error_or_none).
    """
    user = (
        f"FACT:\n"
        f"  subject:   {fact.get('subject', '')}\n"
        f"  predicate: {fact.get('predicate', '')}\n"
        f"  value:     {fact.get('value', '')}\n"
        f"  type:      {fact.get('value_type', '')}\n"
        f"  raw_span:  {fact.get('raw_span', '')}\n\n"
        f"PAGE TEXT (first {_MAX_PAGE_CHARS} chars):\n{page_body[:_MAX_PAGE_CHARS]}"
    )
    text, err = call_judge_heavy(_VERIFY_SYSTEM, user, max_tokens=80, temperature=0.0)
    if err and not text:
        return False, err
    txt = (text or "").upper()
    return ("SUPPORTED" in txt and "NOT_SUPPORTED" not in txt.split("VERDICT:", 1)[-1]), None


# ---------------------------------------------------------------------------
# Paragraph segmentation + extraction
# ---------------------------------------------------------------------------

_PARA_SPLIT_RE = re.compile(r"\n\s*\n+")


def _split_paragraphs(answer: str) -> list[str]:
    return [p.strip() for p in _PARA_SPLIT_RE.split(answer) if p.strip()]


def _para_has_citations(para: str) -> int:
    """Count markdown-link citations in a paragraph. Used for prioritisation
    when more paragraphs exist than _MAX_PARAGRAPHS."""
    return len(re.findall(r"\[[^\]]{1,200}\]\(https?://[^)\s]+\)", para))


def _extract_from_paragraph(paragraph: str) -> list[dict]:
    """Run the heavy judge to extract atomic facts from ONE paragraph.

    Returns a list of fact dicts; empty list on error or no extractable
    facts. Best-effort JSON parsing — accepts arrays with or without
    surrounding prose (defensive against models that ignore "no prose").
    """
    user = (
        f"PARAGRAPH:\n{paragraph[:6000]}\n\n"
        "Extract verifiable atomic facts from this paragraph. Output JSON array only."
    )
    text, err = call_judge_heavy(_EXTRACT_SYSTEM, user, max_tokens=2000, temperature=0.0)
    if err and not text:
        return []
    if not text:
        return []
    # Tolerant JSON parsing: pull the largest [ ... ] block.
    m = re.search(r"\[\s*(?:\{.*?\}\s*,?\s*)*\]", text, flags=re.DOTALL)
    if not m:
        return []
    blob = m.group(0)
    try:
        facts = json.loads(blob)
    except Exception:
        return []
    if not isinstance(facts, list):
        return []
    # Defensive filtering: keep only well-formed dicts.
    cleaned: list[dict] = []
    for f in facts:
        if not isinstance(f, dict):
            continue
        if not f.get("value") or not f.get("source_url"):
            continue
        cleaned.append({
            "subject":     str(f.get("subject", "")).strip(),
            "predicate":   str(f.get("predicate", "")).strip(),
            "value":       str(f.get("value", "")).strip(),
            "value_type":  str(f.get("value_type", "")).strip().lower(),
            "source_url":  str(f.get("source_url", "")).strip(),
            "raw_span":    str(f.get("raw_span", ""))[:300],
        })
    return cleaned


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class FactualExactnessVerifier:
    """Atomic-fact precision pillar (v4 new).

    Score = supported / max(1, total) over extracted facts.

    Constructor knobs:
      max_paragraphs    upper bound on extraction calls (default 12)
      max_total_facts   sample to this many if extractor over-produces (40)
      min_score         pass-gate threshold (default 0.50)
    """

    kind = "factual_exactness"

    def __init__(
        self,
        max_paragraphs: int = _MAX_PARAGRAPHS,
        max_total_facts: int = _MAX_TOTAL_FACTS,
        min_score: float = 0.50,
    ):
        self.max_paragraphs = int(max_paragraphs)
        self.max_total_facts = int(max_total_facts)
        self.min_score = float(min_score)

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        # Guard 1: degenerate answer.
        degen, reason = is_degenerate_answer(answer or "", min_words=50, require_citations=True)
        if degen:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": "degenerate_answer", "degen_reason": reason},
            )

        # Step 0: pick top-N most citation-dense paragraphs to bound LLM cost.
        paras = _split_paragraphs(answer)
        paras_with_cites = [(p, _para_has_citations(p)) for p in paras]
        paras_with_cites.sort(key=lambda t: -t[1])
        chosen = [p for p, c in paras_with_cites if c > 0][: self.max_paragraphs]
        if not chosen:
            return VerifierResult(
                score=0.0, passed=False,
                details={"reason": "no_cited_paragraphs", "paragraph_count": len(paras)},
            )

        # Step 1: extract atomic facts (heavy judge, ~1 call / paragraph).
        sandbox_hosts: list[str] = task_config.get("sandbox_hosts") or [
            "localhost:7770", "localhost:9999", "localhost:8090",
        ]
        sandbox_set = {h.lower() for h in sandbox_hosts}

        all_facts: list[dict] = []
        extract_errors = 0
        for para in chosen:
            facts = _extract_from_paragraph(para)
            if facts:
                all_facts.extend(facts)
            else:
                extract_errors += 1
            if len(all_facts) >= self.max_total_facts:
                break

        # Drop facts whose source_url isn't a sandbox URL — keeps the
        # verifier honest (only fact-check what we can actually fetch).
        all_facts = [
            f for f in all_facts
            if host_in_set(f.get("source_url", ""), sandbox_set)
        ]

        if not all_facts:
            return VerifierResult(
                score=0.0, passed=False,
                details={
                    "reason": "no_extracted_facts",
                    "paragraphs_attempted": len(chosen),
                    "extract_errors": extract_errors,
                    "judge": judge_identity().get("heavy_model"),
                },
            )

        # Cap to max_total_facts.
        if len(all_facts) > self.max_total_facts:
            all_facts = all_facts[: self.max_total_facts]

        # Step 2: fetch source pages in parallel (one fetch per unique URL).
        unique_urls = list({canonicalize_url(f["source_url"]): f["source_url"] for f in all_facts}.values())
        url_to_body: dict[str, str | None] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as ex:
            for url, body in ex.map(_fetch_url, unique_urls):
                url_to_body[url] = body

        # Step 3: verify each fact, deterministic-first.
        per_fact_rows: list[dict] = []
        supported = 0
        det_supported = 0
        llm_supported = 0
        llm_calls = 0
        llm_errors = 0
        unfetchable = 0

        for f in all_facts:
            url = f["source_url"]
            body = url_to_body.get(url)
            row = {
                "subject": f["subject"], "predicate": f["predicate"],
                "value": f["value"], "value_type": f["value_type"],
                "source_url": url, "supported": False, "method": "",
            }
            if not body:
                unfetchable += 1
                row["method"] = "unfetchable"
                per_fact_rows.append(row)
                continue

            # 3a. Deterministic check.
            if _value_in_page(f["value"], f["value_type"], body):
                row["supported"] = True
                row["method"] = "deterministic"
                det_supported += 1
                supported += 1
                per_fact_rows.append(row)
                continue

            # 3b. LLM-fallback NLI.
            ok, err = _llm_verify(f, body)
            llm_calls += 1
            if err:
                llm_errors += 1
                row["method"] = f"llm_error:{err}"
                per_fact_rows.append(row)
                continue
            if ok:
                row["supported"] = True
                row["method"] = "llm_nli"
                llm_supported += 1
                supported += 1
            else:
                row["method"] = "llm_nli_neg"
            per_fact_rows.append(row)

        total = max(1, len(all_facts))
        score = supported / total
        passed = score >= self.min_score

        return VerifierResult(
            score=round(float(score), 4),
            passed=bool(passed),
            details={
                "total_facts":          len(all_facts),
                "supported":            supported,
                "deterministic_hits":   det_supported,
                "llm_hits":             llm_supported,
                "llm_calls":            llm_calls,
                "llm_errors":           llm_errors,
                "unfetchable_pages":    unfetchable,
                "paragraphs_attempted": len(chosen),
                "extract_errors":       extract_errors,
                "min_score":            self.min_score,
                "judge":                judge_identity().get("heavy_model"),
                "per_fact":             per_fact_rows[:60],   # cap dump size
            },
        )
