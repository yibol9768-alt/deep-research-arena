"""Self-hosted LLM client for the closed-world pipeline (NO paid APIs).

Talks OpenAI-compatible chat-completions to the my5090 vLLM (Qwen3-8B by default;
see memory my5090-vllm-serve). Used as the single judge model for grounding
support judging and NeedCite classification (judge == one model for now, per the
"先用8b, judge同一个模型" directive). Stdlib-only (urllib) so it runs both on this
workstation (via an ssh -L tunnel) and on the box (localhost) with no extra deps.

Every helper degrades gracefully: callers should fall back to the deterministic
token-overlap path when ``available()`` is False, so scoring never hard-depends
on the server being up.
"""

from __future__ import annotations

import json
import os
import urllib.request

BASE_URL = os.environ.get("CW_LLM_BASE_URL", os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8000/v1"))
MODEL = os.environ.get("CW_LLM_MODEL", os.environ.get("JUDGE_MODEL", "qwen3-8b"))
TIMEOUT = float(os.environ.get("CW_LLM_TIMEOUT", "60"))
_API_KEY = os.environ.get("CW_LLM_API_KEY", "EMPTY")


def _endpoint(path: str) -> str:
    return BASE_URL.rstrip("/") + path


def available() -> bool:
    """True if the vLLM /v1/models endpoint answers. Cheap liveness probe."""
    try:
        req = urllib.request.Request(_endpoint("/models"), headers={"Authorization": f"Bearer {_API_KEY}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def chat(messages: list[dict], *, max_tokens: int = 16, temperature: float = 0.0) -> str | None:
    """One chat completion. Thinking is disabled (Qwen3) for terse, fast verdicts.
    Returns the assistant text, or None on any transport/parse failure.
    """
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        _endpoint("/chat/completions"), data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            out = json.loads(r.read())
        return out["choices"][0]["message"]["content"]
    except Exception:
        return None


_SUPPORT_SYS = (
    "You are a strict grounding judge for a research benchmark. Decide whether the "
    "SOURCE text actually supports the CLAIM. Judge ONLY from the SOURCE; never use "
    "outside knowledge. Be strict: partial/numeric mismatches are not full support. "
    "Answer with exactly one word: FULL, PARTIAL, or NONE."
)


def support_level(claim: str, source: str, *, max_source_chars: int = 4000) -> float:
    """LLM grounding verdict -> 1.0 (FULL) / 0.5 (PARTIAL) / 0.0 (NONE).

    Returns 0.0 if inputs are empty. On any server failure returns -1.0 so the
    caller can detect the miss and fall back to the deterministic checker.
    """
    if not (claim and source):
        return 0.0
    prompt = (
        f"CLAIM: {claim}\n\n"
        f"SOURCE (the cited page text):\n{source[:max_source_chars]}\n\n"
        "Does the SOURCE support the CLAIM? One word: FULL, PARTIAL, or NONE."
    )
    out = chat(
        [{"role": "system", "content": _SUPPORT_SYS}, {"role": "user", "content": prompt}],
        max_tokens=8,
    )
    if out is None:
        return -1.0
    u = out.strip().upper()
    if u.startswith("FULL"):
        return 1.0
    if u.startswith("PARTIAL"):
        return 0.5
    return 0.0


_NEEDCITE_SYS = (
    "You decide whether a sentence from a research report makes a checkable "
    "factual claim that should be backed by a cited source (prices, ratings, "
    "counts, specs, named facts) versus framing/opinion/common knowledge. "
    "Answer exactly one word: YES or NO."
)


def needs_citation(sentence: str) -> bool | None:
    """LLM NeedCite verdict. Returns None on server failure (caller falls back)."""
    s = (sentence or "").strip()
    if len(s.split()) < 4:
        return False
    out = chat(
        [{"role": "system", "content": _NEEDCITE_SYS},
         {"role": "user", "content": f"SENTENCE: {s}\n\nNeeds a citation? YES or NO."}],
        max_tokens=4,
    )
    if out is None:
        return None
    return out.strip().upper().startswith("Y")
