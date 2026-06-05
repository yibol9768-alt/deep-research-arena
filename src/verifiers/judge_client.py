"""Pluggable judge-LLM backend.

One place to configure which model scores `llm_judge` / `checklist` /
`pairwise_judge`. Keeping this separate from the agents' LLM lets us
meet the **self-preference mitigation** requirement flagged by the
peer-review audit (Wataoka 2024 NeurIPS / JudgeBench ICLR 2025): if an
agent is GLM-5, the judge must be a *different-family* model.

Select backend with env vars (all optional; defaults kept for back-
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

import json
import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Shared judge-alignment helpers (used by depth/rigor/style/checklist).
# These keep the four verifiers consistent on de-truncation, few-shot
# exemplar loading, evidence-block formatting, and cross-family routing.
# ---------------------------------------------------------------------------

_EXEMPLAR_ROOT = Path(__file__).resolve().parents[2] / "data" / "judge_exemplars"

# Known model-family keywords. Used by cross-family routing to pick a judge
# of a DIFFERENT family from the agent under test (self-preference mitigation).
_FAMILY_KEYWORDS = {
    "glm": "glm",
    "chatglm": "glm",
    "zhipu": "glm",
    "deepseek": "deepseek",
    "ds": "deepseek",
    "claude": "claude",
    "anthropic": "claude",
    "gpt": "openai",
    "openai": "openai",
    "qwen": "qwen",
    "gemini": "gemini",
}


def family_of(name: str | None) -> str | None:
    """Map a model or agent name to a coarse model family keyword.

    Returns None when the family cannot be inferred. Matching is
    case-insensitive substring against a small keyword table so that names
    like ``glm-5.1`` or ``deepseek-v4-flash`` resolve correctly.
    """
    if not name:
        return None
    low = str(name).lower()
    for kw, fam in _FAMILY_KEYWORDS.items():
        if kw in low:
            return fam
    return None


def configured_judge_families() -> dict[str, str]:
    """Return the judge families that are configured via env vars.

    Looks at JUDGE_MODEL (primary) and JUDGE_MODEL_ALT (an optional second
    family configured for cross-family routing). Keys are family names,
    values are the concrete model strings. Graceful when only one family
    is configured: the dict then has a single entry.
    """
    out: dict[str, str] = {}
    primary = (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or "deepseek-v4-flash"
    )
    fam = family_of(primary)
    if fam:
        out[fam] = primary
    alt = os.environ.get("JUDGE_MODEL_ALT")
    if alt:
        afam = family_of(alt)
        if afam:
            out[afam] = alt
    return out


def select_cross_family_judge(agent_family: str | None) -> dict[str, Any]:
    """Pick a judge model of a DIFFERENT family than the agent under test.

    A GLM-family agent should be judged by a non-GLM judge and vice versa,
    to remove the self-preference confound. Behaviour:

      - If two (or more) judge families are configured and one of them
        differs from ``agent_family``, return that different-family judge.
      - If only one judge family is configured, or the agent family is
        unknown, fall back to the configured default JUDGE_MODEL.

    Returns ``{"model": <str>, "family": <str|None>, "cross_family": bool,
    "reason": <str>}``. This is env-driven and never raises offline.
    """
    families = configured_judge_families()
    default_model = (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or "deepseek-v4-flash"
    )
    agent_fam = family_of(agent_family) if agent_family else None

    if not agent_fam:
        return {
            "model": default_model,
            "family": family_of(default_model),
            "cross_family": False,
            "reason": "agent family unknown; using configured default judge",
        }

    # Prefer a configured family that differs from the agent family.
    for fam, model in families.items():
        if fam != agent_fam:
            return {
                "model": model,
                "family": fam,
                "cross_family": True,
                "reason": f"selected {fam} judge for {agent_fam} agent",
            }

    return {
        "model": default_model,
        "family": family_of(default_model),
        "cross_family": False,
        "reason": "only the agent's own family is configured; using default judge",
    }


def smart_truncate(text: str, *, cap: int = 9000, head_frac: float = 0.6) -> str:
    """De-truncate replacement for the old hard ``text[:6000]`` slice.

    The old slice silently dropped the conclusion of long reports, where
    synthesis usually lives. This keeps BOTH the head and the tail: if the
    text exceeds ``cap``, we keep the first ``head_frac`` of the budget and
    the last ``1 - head_frac``, joined by a visible elision marker so the
    judge knows the middle was cut. Short texts pass through unchanged.
    """
    text = text or ""
    if len(text) <= cap:
        return text
    marker = "\n\n[... middle of report omitted to fit context; head and conclusion kept ...]\n\n"
    budget = cap - len(marker)
    if budget <= 0:
        return text[:cap]
    head_len = int(budget * head_frac)
    tail_len = budget - head_len
    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""
    return head + marker + tail


def load_exemplars(dimension: str) -> list[dict[str, Any]]:
    """Load few-shot calibration exemplars for a dimension.

    Reads ``data/judge_exemplars/<dimension>.json``. Each entry is
    ``{"level": int, "snippet": str, "rationale": str}``. Returns an empty
    list when the file is missing or malformed, so callers fall back to the
    pre-existing no-exemplar behaviour.
    """
    path = _EXEMPLAR_ROOT / f"{dimension}.json"
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and "snippet" in item and "rationale" in item:
            out.append(item)
    return out


def format_exemplars_block(exemplars: list[dict[str, Any]]) -> str:
    """Render exemplars as a calibration-anchor block for the rubric prompt.

    Returns the empty string when there are no exemplars so the prompt is
    byte-for-byte unchanged in the fallback path.
    """
    if not exemplars:
        return ""
    lines = ["Calibration exemplars (hand-authored anchors; match the level scale):"]
    for ex in exemplars:
        lvl = ex.get("level", "?")
        snippet = str(ex.get("snippet", "")).strip()[:400]
        rationale = str(ex.get("rationale", "")).strip()[:300]
        lines.append(f"  LEVEL {lvl}: {snippet}")
        lines.append(f"    why: {rationale}")
    return "\n".join(lines)


def format_evidence_block(evidence: dict | None, *, cap: int = 4000) -> str:
    """Render retrieved evidence (url -> snippet text) as a bounded block.

    Returns the empty string when ``evidence`` is None or empty, so the
    no-evidence path behaves exactly as before. When present, the block is
    capped to ``cap`` chars (truncated gracefully) and instructs the judge
    to check grounding and genuine cross-source synthesis.
    """
    if not evidence or not isinstance(evidence, dict):
        return ""
    parts: list[str] = []
    used = 0
    for url, snippet in evidence.items():
        chunk = f"- {url}\n  {str(snippet or '').strip()}"
        if used + len(chunk) > cap:
            remaining = cap - used
            if remaining > 0:
                parts.append(chunk[:remaining])
            break
        parts.append(chunk)
        used += len(chunk)
    body = "\n".join(parts)
    return (
        "Retrieved evidence the report had access to (check that claims are\n"
        "grounded in these sources and that the report genuinely synthesises\n"
        "ACROSS sources rather than restating one):\n"
        f"{body}"
    )


def judge_identity() -> dict:
    """Describes the judge currently configured. Useful to stamp into
    verifier details so cross-judge comparison is traceable.

    `heavy_model` reports which model heavy / extraction-style verifiers
    (factual_exactness, internal_consistency) route to via call_judge_heavy.
    `JUDGE_MODEL_HEAVY` defaults to V4 Pro when unset and the regular
    JUDGE_MODEL points at a V4-flash sibling, otherwise falls back to the
    regular JUDGE_MODEL.
    """
    regular = (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or "deepseek-v4-flash"
    )
    heavy = os.environ.get("JUDGE_MODEL_HEAVY") or _default_heavy_model(regular)
    return {
        "provider": os.environ.get("JUDGE_PROVIDER", "anthropic").lower(),
        "model":    regular,
        "heavy_model": heavy,
        "base_url": os.environ.get("JUDGE_BASE_URL")
                    or os.environ.get("ANTHROPIC_BASE_URL")
                    or os.environ.get("OPENAI_BASE_URL")
                    or "",
    }


def _default_heavy_model(regular: str) -> str:
    """When JUDGE_MODEL_HEAVY is unset, pick V4 Pro if the regular judge is
    a V4-flash sibling. Reasoning: heavy verifiers (atomic fact extraction,
    pairwise NLI for intra-document contradiction) materially benefit from
    V4 Pro's higher-capacity reasoning, while v2-only verifiers (checklist /
    citation_alignment) keep using V4 Flash to control cost.
    """
    low = (regular or "").lower()
    if low.startswith("deepseek-v4") and "flash" in low:
        # Same family, Pro tier sibling. Provider-specific override possible.
        return os.environ.get("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro")
    return regular


def call_judge(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> tuple[str | None, str | None]:
    """Return (text, error). Uses whichever backend is configured.

    This is the *regular* judge entry point: checklist, citation_alignment,
    presentation Tier B, analysis_depth Tier B, perspective_balance Tier B
    use this. For heavy extraction / NLI work, prefer ``call_judge_heavy``.

    When ``model`` is provided it OVERRIDES the JUDGE_MODEL /
    CHECKLIST_JUDGE_MODEL env vars for this single call, so a caller that has
    already resolved a concrete judge (e.g. the pairwise battle picking a
    cross-family judge) can guarantee that exact model is used rather than
    silently re-reading the environment. When ``model`` is None the env-driven
    default is used (back-compat behaviour).
    """
    provider = os.environ.get("JUDGE_PROVIDER", "anthropic").lower()
    model = model or (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or ("deepseek-chat" if provider == "openai" else "glm-5.1")
    )

    if provider == "openai":
        return _call_openai(system, user, model=model, max_tokens=max_tokens, temperature=temperature)
    # default: anthropic
    return _call_anthropic(system, user, model=model, max_tokens=max_tokens)


def call_judge_heavy(
    system: str,
    user: str,
    *,
    max_tokens: int = 4000,
    temperature: float = 0.0,
) -> tuple[str | None, str | None]:
    """Heavy-judge entry point, used by factual_exactness (atomic fact
    extraction + per-fact verification) and internal_consistency (pairwise
    NLI). Defaults differ from ``call_judge``: zero temperature for
    determinism, higher max_tokens for structured JSON outputs, and the
    model defaults to V4 Pro when the regular judge is V4 Flash.

    Override the heavy model via ``JUDGE_MODEL_HEAVY`` env var. When
    JUDGE_MODEL_HEAVY is unset and the regular judge is not a V4 sibling,
    the heavy path falls back to the regular model; heavy verifiers will
    still work, just without the Pro-tier boost.
    """
    provider = os.environ.get("JUDGE_PROVIDER", "anthropic").lower()
    regular = (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("CHECKLIST_JUDGE_MODEL")
        or ("deepseek-chat" if provider == "openai" else "glm-5.1")
    )
    model = os.environ.get("JUDGE_MODEL_HEAVY") or _default_heavy_model(regular)

    if provider == "openai":
        return _call_openai(system, user, model=model, max_tokens=max_tokens, temperature=temperature)
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
    # GLM-family models are routed through the bigmodel anthropic-compatible
    # endpoint (the default base_url here). They default to emitting a long
    # chain-of-thought that, on the tight pairwise budget, consumes the whole
    # token allowance and leaves the text content empty -> spurious TIE.
    # Disable thinking via the extra body the bigmodel endpoint understands.
    # Native Anthropic (claude-*) models ignore this branch entirely, so the
    # legacy Claude path is byte-for-byte unchanged.
    extra: dict = {}
    if model.lower().startswith("glm"):
        extra["thinking"] = {"type": "disabled"}
    try:
        # Anthropic SDK timeout was missing entirely; without it a stalled
        # provider hangs the whole rescore loop indefinitely.
        client = anthropic.Anthropic(base_url=base, auth_token=key, timeout=timeout_s)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            extra_body=extra or None,
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
    # Multi-provider routing for the judge JURY (PoLL, arXiv 2404.18796):
    # qwen/glm/kimi/MiniMax jurors live on DashScope, deepseek on its own API.
    # If a DashScope key is present and the model belongs there, route to it.
    _low = model.lower()
    if (_low.startswith(("qwen", "glm", "kimi", "minimax"))
            and os.environ.get("DASHSCOPE_API_KEY")):
        base = os.environ.get("DASHSCOPE_BASE_URL",
                              "https://dashscope.aliyuncs.com/compatible-mode/v1")
        key = os.environ["DASHSCOPE_API_KEY"]
    if not key:
        return None, "judge key missing (set JUDGE_API_KEY or OPENAI_API_KEY)"
    extra_body: dict = {}
    low_model = model.lower()
    # Case-insensitive: `JUDGE_MODEL=DeepSeek-V4-flash` would otherwise miss
    # the thinking-disabled flag and the model would hide the answer in
    # `reasoning_content`, breaking JSON parsing downstream.
    # JUDGE_THINKING=1 keeps reasoning ON (pairwise battles: the no-thinking
    # judge showed ~50% pure position-bias draws; reasoning fixes that and the
    # verdict extractor reads `content`, which still carries the final answer).
    if low_model.startswith("deepseek-v4") and os.environ.get("JUDGE_THINKING") != "1":
        extra_body["thinking"] = {"type": "disabled"}
    # GLM-family models (glm-4.6, glm-5, glm-5.1, ...) default to emitting a
    # long chain-of-thought into `reasoning_content`. On a tight pairwise
    # budget (1500 tokens) that reasoning eats the whole budget and leaves
    # `content` empty, which downstream parses as an unparseable verdict and
    # collapses to a spurious TIE. Disable thinking so the budget is spent on
    # the visible answer. GLM accepts the same `thinking: {type: disabled}`
    # shape as DeepSeek on its OpenAI-compatible endpoint.
    elif low_model.startswith("glm"):
        extra_body["thinking"] = {"type": "disabled"}
    # qwen3 hybrids reject thinking in non-streaming calls; always disable.
    elif low_model.startswith("qwen3"):
        extra_body["enable_thinking"] = False

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
