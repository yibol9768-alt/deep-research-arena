from __future__ import annotations

import urllib.parse
from typing import Any

from .base import Verifier, VerifierResult


def _parse_url(u: str) -> tuple[str, dict[str, list[str]]]:
    p = urllib.parse.urlparse(u)
    base = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
    qs = urllib.parse.parse_qs(p.query)
    return base, qs


class URLVerifier:
    """Port of WebArena URLEvaluator.

    Reads `task_config["eval"]["reference_url"]`. If set, checks that the
    current page URL path matches the reference (ignoring query order) and
    that all reference query parameters are present (extras allowed).
    """

    kind = "url_match"

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any) -> VerifierResult:
        ref = (task_config.get("eval") or {}).get("reference_url", "")
        if not ref:
            return VerifierResult.fail("no reference_url in task_config")
        if page is None:
            return VerifierResult.fail("page required")

        current = page.url
        ref_base, ref_q = _parse_url(ref)
        cur_base, cur_q = _parse_url(current)

        base_ok = ref_base == cur_base
        missing = {k: v for k, v in ref_q.items() if cur_q.get(k) != v}

        if base_ok and not missing:
            return VerifierResult.ok(current_url=current, ref_url=ref)
        return VerifierResult(
            score=0.0,
            passed=False,
            details={"current_url": current, "ref_url": ref, "base_ok": base_ok, "missing_query": missing},
        )
