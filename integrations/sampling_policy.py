"""The sampling knobs every lane must share, read from `config/lane_protocol.yaml`.

`lane_protocol.yaml` says of the backbone block: "Cross-backbone comparison is
only meaningful when nothing but the weights changes. These must be identical
across lanes AND across backbones." It named the proxy as the enforcement point.
No proxy enforced anything.

storm sampled all five of its stages at 0.7 while holding #1 on the qwen board.
costorm passed `top_p=0.9` where no other lane set it. A lane that sends no
`temperature` inherits the upstream default, near 1.0 for an OpenAI-compatible
endpoint. Fixing the runners reaches only the runners we have read; the proxy is
the one place every lane's request must pass, so the value is stamped there.

BOTH proxies matter. `run_deep_task._setup_ds_backbone` points eleven lanes at
`ds_proxy` (:8088); only claude-code routes through `llm_gateway` (:8100). An
equalisation that lives in one of them equalises one lane.

`thinking` is NOT forced here. The protocol requires it uniform, it is not
(qwen ON, glm ON per a 2026-07-06 decision, deepseek OFF), and choosing for the
maintainer would silently overturn that decision. Instead the declaration is read
back and `preflight.check_backbone_sampling` asserts the code matches what is
written down, so the asymmetry is disclosed rather than hidden.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_PROTOCOL = Path(__file__).resolve().parents[1] / "config" / "lane_protocol.yaml"

_UNSET = object()
_CACHE: dict[str, Any] = {}


def _protocol() -> dict:
    if "doc" not in _CACHE:
        try:
            import yaml
            _CACHE["doc"] = yaml.safe_load(_PROTOCOL.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 -- a missing protocol must not break serving
            _CACHE["doc"] = {}
    return _CACHE["doc"]


def _declared(key: str) -> float | None:
    return (_protocol().get("backbone") or {}).get(key)


def _forced(key: str, env_var: str):
    """`env_var=off` disables the override for a non-benchmark deployment."""
    ck = f"forced:{key}"
    if _CACHE.get(ck, _UNSET) is not _UNSET:
        return _CACHE[ck]
    env = os.environ.get(env_var)
    if env is not None:
        val = None if env.strip().lower() in ("", "off", "none") else float(env)
    else:
        d = _declared(key)
        val = float(d) if d is not None else None
    _CACHE[ck] = val
    return val


def forced_temperature():
    return _forced("temperature", "DRA_FORCE_TEMPERATURE")


def forced_top_p():
    return _forced("top_p", "DRA_FORCE_TOP_P")


def declared_thinking() -> dict:
    """`{uniform: bool, per_backbone: {prefix: on|off}}` as written in the protocol."""
    t = (_protocol().get("backbone") or {}).get("thinking")
    if isinstance(t, dict):
        return t
    return {"uniform": False, "per_backbone": {}}


def max_output_tokens_for(model: str):
    """The output-token ceiling this model must run under, or None when unset.

    `lane_protocol.yaml` declares `max_output_tokens: 8192` "identical across
    lanes AND across backbones". What actually ran: the gateway capped qwen at
    8192, left deepseek uncapped, and RAISED glm to 131072 -- a 16x output-budget
    spread feeding `completeness` (0.33 of quality weight), and ds_proxy, the
    door eleven lanes use, enforced nothing at all. "Same harness, change only
    the model" was false at the token budget.

    glm's exception is real and stays, but DECLARED: glm keeps thinking ON (the
    2026-07-06 decision) and its thinking spends from the same max_tokens budget,
    so a uniform 8192 would starve its visible answer. The asymmetry is written
    in `max_output_tokens_exceptions`, like `thinking`, and preflight asserts the
    code matches the declaration. `DRA_FORCE_MAX_TOKENS=off` disables enforcement
    for a non-benchmark deployment.
    """
    env = os.environ.get("DRA_FORCE_MAX_TOKENS")
    if env is not None:
        s = env.strip().lower()
        if s in ("", "off", "none"):
            return None
        return int(env)
    bb = _protocol().get("backbone") or {}
    base = bb.get("max_output_tokens")
    if base is None:
        return None
    exceptions = bb.get("max_output_tokens_exceptions") or {}
    # Longest matching prefix wins, mirroring the gateway's routing.
    best = None
    for prefix, v in exceptions.items():
        if model.startswith(prefix) and (best is None or len(prefix) > best[0]):
            best = (len(prefix), int(v))
    return best[1] if best else int(base)


def apply_max_tokens(body: dict) -> list[str]:
    """Clamp `max_tokens` to the declared ceiling; never raise it.

    A lane that sends nothing gets the ceiling explicitly: leaving the field
    absent hands the decision to the upstream default, which differs per
    backbone -- the exact non-uniformity this exists to end.
    """
    ceiling = max_output_tokens_for(str(body.get("model", "")))
    if ceiling is None:
        return []
    mt = body.get("max_tokens")
    if mt is None or int(mt) > ceiling:
        body["max_tokens"] = ceiling
        return ["max_tokens"]
    return []


def apply_sampling(body: dict) -> list[str]:
    """Stamp the declared sampler onto an OpenAI-compatible request body.

    Returns the names of the fields it changed, for usage accounting. Mutates
    `body` in place, as the proxies' other policy steps do.
    """
    adj: list[str] = []
    for key, forced in (("temperature", forced_temperature()),
                        ("top_p", forced_top_p())):
        if forced is not None and body.get(key) != forced:
            body[key] = forced
            adj.append(key)
    return adj


def reset_for_tests() -> None:
    _CACHE.clear()
