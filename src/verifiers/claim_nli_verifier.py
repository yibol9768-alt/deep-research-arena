"""ClaimNLIVerifier — Layer 3 of the citation-fidelity stack.

For each (claim_text, cited_url) pair extracted from the agent's report:
  1. Look up the golden's `quoted_span` for that URL (any triple whose
     source_url matches).
  2. If a quoted_span exists, ask DeepSeek-V4-flash (non-reasoning):
     "Does the quoted_span entail the claim?"
  3. Score 1 if entailment_prob >= θ (default 0.80 per ReClaim 2407.01796).

If the cited URL has no golden quoted_span (e.g. agent cited a pool URL
not in must_cite), this verifier abstains for that claim.

NOTE: this calls the LLM once per (claim, url) pair — could be 100s of
calls per report. Cap with `max_calls` (default 80). Cheap with
DS-v4-flash (~$0.005/call; 80 calls ≈ $0.40 / agent-report).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .base import VerifierResult


_MD_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)")


def _claim_context(markdown: str, span_start: int, window: int = 220) -> str:
    a = max(0, span_start - window)
    b = min(len(markdown), span_start + window)
    chunk = markdown[a:b]
    chunk = _MD_LINK_RE.sub(lambda m: m.group("label"), chunk)
    chunk = re.sub(r"`[^`]*`", " ", chunk)
    chunk = re.sub(r"\s+", " ", chunk)
    return chunk.strip()


def _normalize_url(u: str) -> str:
    return u.strip().rstrip("`'\"\\)>,;:.")


def _build_url_quote_index(golden: dict) -> dict[str, list[str]]:
    """url -> list of distinct quoted_span strings."""
    idx: dict[str, list[str]] = {}
    for t in golden.get("triples", []):
        u = _normalize_url(t.get("source_url", ""))
        q = t.get("quoted_span")
        if not u or not q:
            continue
        if u not in idx:
            idx[u] = []
        if q not in idx[u]:
            idx[u].append(q)
    return idx


_NLI_SYSTEM = (
    "You are an entailment judge. Given a CLAIM and a SOURCE_QUOTE, decide "
    "whether the source quote DIRECTLY supports the claim. Respond with a "
    'single JSON object: {"entail": true|false, "prob": 0.0..1.0, "reason": "..."}.'
    " Be strict: a quote that mentions the same topic but does not state the "
    'claim is NOT entailment. Output ONLY the JSON object.'
)


def _ds_nli(claim: str, quote: str) -> tuple[bool, float, str]:
    """Return (entail, prob, reason). reason carries failure detail when prob=0."""
    from .judge_client import call_judge

    user = f"CLAIM: {claim[:500]}\n\nSOURCE_QUOTE: {quote[:500]}"
    text, err = call_judge(_NLI_SYSTEM, user, max_tokens=200, temperature=0.0)
    if err:
        return False, 0.0, f"judge_err:{str(err)[:80]}"
    if not text or not text.strip():
        return False, 0.0, "empty_response"
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return False, 0.0, f"no_json:{text[:60]}"
    try:
        d = json.loads(m.group(0))
    except Exception as e:
        return False, 0.0, f"json_parse:{type(e).__name__}"
    try:
        prob = float(d.get("prob") or 0.0)
    except (TypeError, ValueError):
        prob = 0.0
    return bool(d.get("entail")), prob, str(d.get("reason") or "")[:120]


class ClaimNLIVerifier:
    kind = "claim_nli"

    def __init__(self, theta: float = 0.80, max_calls: int = 80, max_workers: int = 3):
        self.theta = theta
        self.max_calls = max_calls
        self.max_workers = max_workers

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        cov_cfg = task_config.get("url_coverage") or {}
        gp = cov_cfg.get("golden_pool_path")
        if not gp:
            return VerifierResult.fail("no golden_pool_path on task")
        gp_path = Path(gp)
        if not gp_path.is_absolute():
            gp_path = Path(__file__).resolve().parents[2] / gp
        if not gp_path.exists():
            return VerifierResult.fail(f"golden missing: {gp_path}")

        golden = json.loads(gp_path.read_text())
        url_quotes = _build_url_quote_index(golden)
        if not url_quotes:
            return VerifierResult.fail("golden has no quoted_span — run draft_quote_spans.py first",
                                       n_quotes=0)

        sandbox_hosts: list[str] = task_config.get("sandbox_hosts") or [
            "localhost:7770", "localhost:9999", "localhost:8090",
        ]
        sandbox_set = {h.lower() for h in sandbox_hosts}

        claims: list[tuple[str, str]] = []
        for m in _MD_LINK_RE.finditer(answer):
            url = _normalize_url(m.group("url"))
            if not any(h in url for h in sandbox_set):
                continue
            if url not in url_quotes:
                continue
            ctx = _claim_context(answer, m.start())
            claims.append((url, ctx))

        if not claims:
            return VerifierResult.fail(
                "no agent claims overlap with golden quoted_span URLs",
                claims_with_quote=0,
            )

        # Cap calls
        budget = claims[: self.max_calls]
        results = []
        n_entailed = 0
        n_above_theta = 0
        for url, claim_ctx in budget:
            quotes = url_quotes[url]
            best_prob = 0.0
            best_reason = ""
            for q in quotes[:1]:  # 1 quote per URL — keep latency bounded
                entail, prob, reason = _ds_nli(claim_ctx, q)
                if prob > best_prob:
                    best_prob = prob
                    best_reason = reason
                    if entail:
                        pass
                if best_prob >= self.theta:
                    break
                time.sleep(0.05)
            if best_prob >= self.theta:
                n_above_theta += 1
            if best_prob > 0.5:
                n_entailed += 1
            results.append({
                "url": url[:80],
                "claim_ctx_len": len(claim_ctx),
                "best_prob": round(best_prob, 3),
                "above_theta": best_prob >= self.theta,
                "reason": best_reason[:80],
            })

        denom = max(1, len(budget))
        support_rate = n_above_theta / denom
        soft_rate = n_entailed / denom
        threshold = float((task_config.get("claim_nli") or {}).get("min_support_rate", 0.50))

        return VerifierResult(
            score=round(support_rate, 4),
            passed=support_rate >= threshold,
            details={
                "claims_total_in_answer": len(claims),
                "claims_evaluated": len(budget),
                "claims_above_theta": n_above_theta,
                "support_rate_strict": round(support_rate, 4),
                "support_rate_soft": round(soft_rate, 4),
                "theta": self.theta,
                "threshold_pass": threshold,
                "samples": results[:5],
            },
        )
