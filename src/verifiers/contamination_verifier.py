"""ContaminationVerifier — Layer 4 of the citation-fidelity stack.

For each adversarial wiki article in the task config, classify whether
the agent's report mentions the *prior* fact value (the one in the
training corpus) or the *sandbox* value (the one our WikiOverlay
substitutes). If the agent cites the URL but reports the prior value,
that is direct evidence the agent did NOT actually fetch and read the
sandboxed page — it answered from training prior.

Aggregate metric:
    retrieval_authenticity_rate
        = (n_facts where agent reported sandbox_value)
        / (n_facts where agent referenced the article topic)

Score = retrieval_authenticity_rate. A 0.0 score means the agent
answered every fact from prior; 1.0 means every fact came from the page.

This is the cleanest contamination defense in the literature: agents
that retrieve win, agents that train-set-hallucinate lose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .base import VerifierResult


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def _claim_context(answer: str, marker: str, window: int = 400) -> list[str]:
    """Return all ~window-char windows around occurrences of marker (case-insensitive)."""
    out: list[str] = []
    a = _normalize(answer)
    m = _normalize(marker)
    if not m:
        return out
    start = 0
    while True:
        i = a.find(m, start)
        if i < 0:
            break
        lo = max(0, i - window)
        hi = min(len(answer), i + len(marker) + window)
        out.append(answer[lo:hi])
        start = i + len(marker)
    return out


def _classify_fact(answer: str, art: dict, mod: dict) -> dict:
    """Decide for one (article × modification) whether the agent's answer
    contains the prior fact, the sandbox fact, or neither, in proximity to
    the article's canonical topic mention."""
    topic = art.get("canonical_topic") or art.get("id", "")
    prior = (mod.get("prior_value") or "").strip()
    sand = (mod.get("sandbox_value") or "").strip()
    fact_kind = mod.get("fact_kind", "?")

    contexts = _claim_context(answer, topic, window=600)
    referenced = len(contexts) > 0
    if not contexts:
        contexts = [answer]

    prior_in_proximity = any(_normalize(prior) in _normalize(c) for c in contexts) if prior else False
    sand_in_proximity = any(_normalize(sand) in _normalize(c) for c in contexts) if sand else False

    if sand_in_proximity and not prior_in_proximity:
        verdict = "sandbox"
    elif prior_in_proximity and not sand_in_proximity:
        verdict = "prior"
    elif prior_in_proximity and sand_in_proximity:
        verdict = "both"
    elif referenced:
        verdict = "neither"
    else:
        verdict = "topic_not_referenced"

    return {
        "article_id": art.get("id"),
        "topic": topic,
        "fact_id": mod.get("id"),
        "fact_kind": fact_kind,
        "prior_value": prior,
        "sandbox_value": sand,
        "verdict": verdict,
    }


class ContaminationVerifier:
    kind = "contamination"

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        adv = task_config.get("adversarial_wiki") or []
        if not adv:
            cfg_path = task_config.get("adversarial_wiki_config_path") or "configs/wiki_overlay.yaml"
            p = Path(cfg_path)
            if not p.is_absolute():
                p = Path(__file__).resolve().parents[2] / cfg_path
            if p.exists():
                try:
                    import yaml
                    cfg = yaml.safe_load(p.read_text()) or {}
                    adv = cfg.get("articles", [])
                except Exception:
                    pass
        if not adv:
            return VerifierResult.fail(
                "no adversarial_wiki defined",
                articles=0,
            )

        rows: list[dict] = []
        for art in adv:
            for mod in art.get("modifications", []):
                rows.append(_classify_fact(answer, art, mod))

        n_total = len(rows)
        n_sand = sum(1 for r in rows if r["verdict"] == "sandbox")
        n_prior = sum(1 for r in rows if r["verdict"] == "prior")
        n_both = sum(1 for r in rows if r["verdict"] == "both")
        n_neither = sum(1 for r in rows if r["verdict"] == "neither")
        n_unref = sum(1 for r in rows if r["verdict"] == "topic_not_referenced")

        denom_referenced = n_total - n_unref
        if denom_referenced > 0:
            authenticity = (n_sand + 0.5 * n_both) / denom_referenced
        else:
            authenticity = 0.0

        threshold = float((task_config.get("contamination") or {}).get("min_authenticity", 0.50))

        return VerifierResult(
            score=round(authenticity, 4),
            passed=authenticity >= threshold,
            details={
                "n_facts":             n_total,
                "n_sandbox":           n_sand,
                "n_prior":             n_prior,
                "n_both":              n_both,
                "n_neither":           n_neither,
                "n_topic_unreferenced": n_unref,
                "authenticity_rate":   round(authenticity, 4),
                "threshold":           threshold,
                "per_fact":            rows,
            },
        )


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        task = json.loads(Path(sys.argv[1]).read_text())
        ans = Path(sys.argv[2]).read_text(errors="ignore")
        r = ContaminationVerifier().verify(task_config=task, answer=ans)
        print(json.dumps({"score": r.score, "passed": r.passed,
                          "details": r.details}, indent=2, ensure_ascii=False))
    else:
        print("usage: python contamination_verifier.py <task_json> <answer_md>")
