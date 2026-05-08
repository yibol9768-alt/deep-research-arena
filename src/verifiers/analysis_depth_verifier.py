"""AnalysisDepthVerifier -- structural + LLM judge for analytical depth.

Evaluates 10 binary criteria in two tiers:

  Tier A (structural / deterministic, 4 items):
    1. has_cross_source_section -- paragraph references URLs from >= 2 domains
    2. contradiction_count     -- >= 3 paragraphs with cross-source contradiction language
    3. multi_evidence_chains   -- >= 3 claims backed by >= 3 URLs from >= 2 domains
    4. comparative_language_density -- >= 15% of paragraphs contain comparative language

  Tier B (LLM judge, 6 items, single call via judge_client):
    5.  beyond_enumeration      -- identifies patterns beyond listing facts
    6.  causal_reasoning        -- attempts causal explanations
    7.  source_triangulation    -- compares across source types
    8.  novel_insight           -- >= 1 insight requiring multiple sources
    9.  counterargument_awareness -- acknowledges limitations
    10. actionable_conclusion   -- specific evidence-grounded recommendations

Score = 0.3 * tier_a_rate + 0.7 * tier_b_rate
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .base import VerifierResult
from .judge_client import call_judge, judge_identity


# ---------------------------------------------------------------------------
# Tier A helpers
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)")

_CONTRADICTION_TERMS = re.compile(
    r"\b(?:however|contrary|contradicts?|disagrees?|disputes?|conflicts?\s+with"
    r"|at\s+odds|inconsistent|whereas|on\s+the\s+other\s+hand|in\s+contrast"
    r"|conversely|nevertheless|despite|although|while\s+.{0,30}\s+suggests?"
    r"|conflicting\s+(?:evidence|data|findings|reports))\b",
    re.IGNORECASE,
)

_COMPARATIVE_TERMS = re.compile(
    r"\b(?:compared?\s+to|in\s+comparison|relative\s+to|versus|vs\.?"
    r"|more\s+than|less\s+than|greater|fewer|higher|lower|better|worse"
    r"|outperform|underperform|superior|inferior|unlike|similarly"
    r"|differ(?:s|ent|ence)|contrast|analogous|whereas)\b",
    re.IGNORECASE,
)


def _extract_domain(url: str) -> str:
    """Extract a normalised "source identity" from a URL.

    For real internet URLs, returns the last two host parts ("amazon.com").
    For sandbox URLs all three corpora live under host=localhost on
    different ports (7770 = shopping, 9999 = reddit, 8090 = wiki), so
    we use **host:port** when present — otherwise multi-domain checks
    silently fail because all three sandbox URLs collapse to "localhost".
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except Exception:
        return ""
    if not host:
        return ""
    # Sandbox + any other host where the port disambiguates the corpus.
    if host in ("localhost", "127.0.0.1") and port:
        return f"{host}:{port}"
    parts = host.split(".")
    if parts and parts[0] == "www":
        parts = parts[1:]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _paragraphs(text: str) -> list[str]:
    """Split text into paragraphs (blocks separated by blank lines)."""
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip() and len(p.strip()) > 20]


def _urls_in_text(text: str) -> list[str]:
    """Extract every URL — markdown-linked OR bare. Catches the bare-URL
    case (some agents emit raw https:// URLs without [..](..) wrapping)."""
    from .base import CITED_BARE_URL_RE, _strip_url_trail
    seen: set[str] = set()
    out: list[str] = []
    for m in _MD_LINK_RE.finditer(text):
        u = _strip_url_trail(m.group("url"))
        if u and u not in seen:
            seen.add(u); out.append(u)
    for m in CITED_BARE_URL_RE.finditer(text):
        u = _strip_url_trail(m.group(0))
        if u and u not in seen:
            seen.add(u); out.append(u)
    return out


def _domains_in_text(text: str) -> set[str]:
    """Return distinct domains referenced via markdown links in text."""
    return {d for u in _urls_in_text(text) if (d := _extract_domain(u))}


def _has_cross_source_section(paragraphs: list[str]) -> tuple[bool, int]:
    """Check if any paragraph references URLs from >= 2 domains."""
    count = 0
    for para in paragraphs:
        domains = _domains_in_text(para)
        if len(domains) >= 2:
            count += 1
    return count > 0, count


def _contradiction_paragraphs(paragraphs: list[str]) -> int:
    """Count paragraphs containing cross-source contradiction language."""
    count = 0
    for para in paragraphs:
        if _CONTRADICTION_TERMS.search(para):
            count += 1
    return count


def _multi_evidence_chains(paragraphs: list[str], min_urls: int = 3, min_domains: int = 2) -> int:
    """Count paragraphs (as claim proxies) backed by >= min_urls URLs from >= min_domains domains."""
    count = 0
    for para in paragraphs:
        urls = _urls_in_text(para)
        if len(urls) >= min_urls:
            domains = {_extract_domain(u) for u in urls}
            domains.discard("")
            if len(domains) >= min_domains:
                count += 1
    return count


def _comparative_language_density(paragraphs: list[str]) -> float:
    """Fraction of paragraphs that contain comparative language."""
    if not paragraphs:
        return 0.0
    matches = sum(1 for p in paragraphs if _COMPARATIVE_TERMS.search(p))
    return matches / len(paragraphs)


def _run_tier_a(text: str) -> list[dict[str, Any]]:
    """Evaluate the 4 structural criteria."""
    paragraphs = _paragraphs(text)
    results: list[dict[str, Any]] = []

    # 1. has_cross_source_section
    has_cross, cross_count = _has_cross_source_section(paragraphs)
    results.append({
        "criterion": "has_cross_source_section",
        "passed": has_cross,
        "detail": f"paragraphs_with_multi_domain_refs={cross_count}",
    })

    # 2. contradiction_count >= 3
    contra = _contradiction_paragraphs(paragraphs)
    results.append({
        "criterion": "contradiction_count",
        "passed": contra >= 3,
        "detail": f"contradiction_paragraphs={contra}",
    })

    # 3. multi_evidence_chains >= 3
    chains = _multi_evidence_chains(paragraphs)
    results.append({
        "criterion": "multi_evidence_chains",
        "passed": chains >= 3,
        "detail": f"multi_evidence_paragraphs={chains}",
    })

    # 4. comparative_language_density >= 0.15
    density = round(_comparative_language_density(paragraphs), 3)
    results.append({
        "criterion": "comparative_language_density",
        "passed": density >= 0.15,
        "detail": f"density={density}, total_paragraphs={len(paragraphs)}",
    })

    return results


# ---------------------------------------------------------------------------
# Tier B: LLM judge
# ---------------------------------------------------------------------------

_TIER_B_CRITERIA = [
    "beyond_enumeration: The report identifies patterns, trends, or themes beyond simply listing facts from sources.",
    "causal_reasoning: The report attempts causal explanations -- proposing WHY something happens, not just WHAT happened.",
    "source_triangulation: The report explicitly compares or cross-references information across different source types (e.g., forums vs. product pages vs. official docs).",
    "novel_insight: The report contains at least one insight that could only emerge from synthesizing multiple sources together.",
    "counterargument_awareness: The report acknowledges limitations, caveats, or counterarguments to its main claims.",
    "actionable_conclusion: The final section provides specific, evidence-grounded recommendations rather than vague generalities.",
]

_JUDGE_SYSTEM = (
    "You are a strict analytical-depth judge for deep-research reports. "
    "For each numbered criterion you will output exactly one line: the criterion number, "
    "a period, a space, then PASS or FAIL, optionally followed by a dash and a "
    "brief reason (<=12 words). No other text.\n\n"
    "Be strict: if the report does not clearly demonstrate the criterion, mark FAIL. "
    "Surface-level or generic statements do not satisfy criteria like 'novel_insight' or 'causal_reasoning'."
)


def _build_tier_b_prompt(answer: str) -> str:
    numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(_TIER_B_CRITERIA))
    truncated = (answer or "")[:6000]
    return (
        f"Analytical depth criteria (judge each independently):\n{numbered}\n\n"
        f"Agent report (truncated to 6000 chars):\n---\n{truncated}\n---\n\n"
        f"For each criterion, emit one line:\n"
        f"  1. PASS|FAIL  (reason <= 12 words)\n"
        f"  2. PASS|FAIL  (reason <= 12 words)\n"
        f"  ...\n"
    )


def _parse_tier_b(text: str, n: int) -> list[dict[str, Any]]:
    """Parse judge output into per-criterion results.

    Tolerates numbered and unnumbered formats.
    """
    text = text or ""
    out: list[dict[str, Any]] = []

    # Pass 1: numbered parse
    for i in range(n):
        pat = rf"(?:^|\n)\s*{i+1}[\.\)]\s*(PASS|FAIL)\b\s*[-:.]?\s*(.*?)(?=\n\s*\d+[\.\)]|\Z)"
        m = re.search(pat, text, re.S | re.I)
        if m:
            out.append({
                "criterion": _TIER_B_CRITERIA[i].split(":")[0],
                "passed": m.group(1).upper() == "PASS",
                "reason": m.group(2).strip().split("\n")[0][:120],
            })
        else:
            out.append(None)

    # Pass 2: fallback to unnumbered PASS/FAIL tokens
    missing = [i for i, v in enumerate(out) if v is None]
    if len(missing) > n // 2:
        tokens = re.findall(r"(?:^|\n)\s*(PASS|FAIL)\b", text, re.I)
        if len(tokens) >= n:
            for i in range(n):
                out[i] = {
                    "criterion": _TIER_B_CRITERIA[i].split(":")[0],
                    "passed": tokens[i].upper() == "PASS",
                    "reason": "",
                }

    # Fill missing
    for i, v in enumerate(out):
        if v is None:
            out[i] = {
                "criterion": _TIER_B_CRITERIA[i].split(":")[0],
                "passed": False,
                "reason": "judge did not emit a verdict",
            }
    return out


# ---------------------------------------------------------------------------
# Main verifier
# ---------------------------------------------------------------------------

class AnalysisDepthVerifier:
    """Structural + LLM analytical depth verifier."""

    kind = "analysis_depth"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        from .base import is_degenerate_answer
        degen, why = is_degenerate_answer(answer, min_words=50, require_citations=False)
        if degen:
            return VerifierResult.fail(f"degenerate_answer:{why}")

        # --- Tier A (structural) ---
        tier_a_items = _run_tier_a(answer)
        tier_a_passed = sum(1 for x in tier_a_items if x["passed"])
        tier_a_rate = tier_a_passed / len(tier_a_items)

        # --- Tier B (LLM judge) ---
        tier_b_items: list[dict[str, Any]] = []
        judge_error: str | None = None
        judge_raw: str = ""

        text, err = call_judge(
            _JUDGE_SYSTEM,
            _build_tier_b_prompt(answer),
            max_tokens=1200,
        )
        if text is None:
            judge_error = err
            tier_b_items = [
                {"criterion": c.split(":")[0], "passed": False, "reason": f"judge error: {err}"}
                for c in _TIER_B_CRITERIA
            ]
        else:
            judge_raw = text
            tier_b_items = _parse_tier_b(text, len(_TIER_B_CRITERIA))

        tier_b_passed = sum(1 for x in tier_b_items if x["passed"])
        tier_b_rate = tier_b_passed / len(_TIER_B_CRITERIA)

        # --- Composite score ---
        score = round(0.3 * tier_a_rate + 0.7 * tier_b_rate, 4)

        return VerifierResult(
            score=score,
            passed=score >= 0.5,
            details={
                "tier_a_passed": tier_a_passed,
                "tier_a_total": len(tier_a_items),
                "tier_a_rate": round(tier_a_rate, 3),
                "tier_a_items": tier_a_items,
                "tier_b_passed": tier_b_passed,
                "tier_b_total": len(_TIER_B_CRITERIA),
                "tier_b_rate": round(tier_b_rate, 3),
                "tier_b_items": tier_b_items,
                "judge_model": judge_identity()["model"],
                "judge_provider": judge_identity()["provider"],
                "judge_error": judge_error,
                "raw_judge_output": judge_raw[:800],
            },
        )
