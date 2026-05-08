"""Pluggable judge-LLM backend.

One place to configure which model scores `llm_judge` / `checklist` /
`pairwise_judge`. Keeping this separate from the agents' LLM lets us
meet the **self-preference mitigation** requirement flagged by the
peer-review audit (Wataoka 2024 NeurIPS / JudgeBench ICLR 2025): if an
agent is GLM-5, the judge must be a *different-family* model.

Select backend with env vars (all optional — defaults kept for back-
compat with the legacy Anthropic path):

    JUDGE_PROVIDER     anthropic | openai      (default: anthropic)
    JUDGE_MODEL        deepseek-chat / glm-5 / claude-3-7-sonnet / ...
    JUDGE_BASE_URL     https://api.deepseek.com / https://open.bigmodel.cn/api/anthropic / ...
    JUDGE_API_KEY      dedicated judge key (separate from OPENAI_API_KEY / ANTHROPIC_API_KEY)

Back-compat fallback when JUDGE_* not set:
    anthropic path → ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN (old behaviour)
    openai path   → OPENAI_BASE_URL / OPENAI_API_KEY
"""

from __future__ import annotations

import os
from typing import Any


def judge_identity() -> dict:
    """Describes the judge currently configured — useful to stamp into
    verifier details so cross-judge comparison is traceable."""
    return {
        "provider": os.environ.get("JUDGE_PROVIDER", "anthropic").lower(),
        "model":    os.environ.get("JUDGE_MODEL")
                    or os.environ.get("CHECKLIST_JUDGE_MODEL")
                    or "glm-5.1",
        "base_url": os.environ.get("JUDGE_BASE_URL")
                    or os.environ.get("ANTHROPIC_BASE_URL")
                    or os.environ.get("OPENAI_BASE_URL")
                    or "",
    }


def call_judge(
    system: str,
    user: str,
    *,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> tuple[str | None, str | None]:
    """Return (text, error). Uses whichever backend is configured."""
    provider = os.environ.get("JUDGE_PROVIDER", "anthropic").lower()
    model = (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or ("deepseek-chat" if provider == "openai" else "glm-5.1")
    )

    if provider == "openai":
        return _call_openai(system, user, model=model, max_tokens=max_tokens, temperature=temperature)
    # default: anthropic
    return _call_anthropic(system, user, model=model, max_tokens=max_tokens)


def _call_anthropic(system: str, user: str, *, model: str, max_tokens: int) -> tuple[str | None, str | None]:
    try:
        import anthropic  # type: ignore
    except Exception:
        return None, "anthropic SDK not installed"

    base = os.environ.get("JUDGE_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") \
           or "https://open.bigmodel.cn/api/anthropic"
    key = os.environ.get("JUDGE_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") \
          or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None, "judge key missing (set JUDGE_API_KEY or ANTHROPIC_AUTH_TOKEN)"
    timeout_s = float(os.environ.get("JUDGE_TIMEOUT_S", "120"))
    try:
        # Anthropic SDK timeout was missing entirely; without it a stalled
        # provider hangs the whole rescore loop indefinitely.
        client = anthropic.Anthropic(base_url=base, auth_token=key, timeout=timeout_s)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            b.text for b in resp.content
            if getattr(b, "type", None) == "text"
        )
        return text, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _call_openai(
    system: str, user: str, *, model: str,
    max_tokens: int, temperature: float,
) -> tuple[str | None, str | None]:
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None, "openai SDK not installed"

    base = os.environ.get("JUDGE_BASE_URL") \
        or os.environ.get("OPENAI_BASE_URL") \
        or "https://api.deepseek.com"
    key = os.environ.get("JUDGE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None, "judge key missing (set JUDGE_API_KEY or OPENAI_API_KEY)"
    extra_body: dict = {}
    # Case-insensitive: `JUDGE_MODEL=DeepSeek-V4-flash` would otherwise miss
    # the thinking-disabled flag and the model would hide the answer in
    # `reasoning_content`, breaking JSON parsing downstream.
    if model.lower().startswith("deepseek-v4"):
        extra_body["thinking"] = {"type": "disabled"}

    timeout_s = float(os.environ.get("JUDGE_TIMEOUT_S", "120"))
    try:
        client = OpenAI(base_url=base, api_key=key, timeout=timeout_s, max_retries=1)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_body=extra_body or None,
        )
        msg = resp.choices[0].message
        text = msg.content or ""
        if not text.strip():
            reasoning = getattr(msg, "reasoning_content", "") or ""
            if reasoning and max_tokens < 8000:
                resp = client.chat.completions.create(
                    model=model,
                    max_tokens=8192,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    extra_body=extra_body or None,
                )
                msg = resp.choices[0].message
                text = msg.content or ""
        return text, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
