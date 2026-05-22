"""SandboxComplianceVerifier — audit every cited URL in an agent report
against the strict-sandbox allowlist.

Design goals (matches the file-shape of `url_coverage_verifier.py`):
  1. Fully deterministic — no LLM, so it can run as part of an automated
     post-run audit step under `--strict-sandbox`.
  2. Catches every citation style emitted in the wild by DR frameworks,
     not just markdown links. We reuse `citation_format.extract_cited_urls`
     so the audit sees what every other URL-aware verifier sees.
  3. A single ``policy_violation`` bool the caller can wire straight into
     a gate: any non-sandbox URL means False.

Closed-book contract (the methodological story):
  In strict mode every URL in every report MUST be in the sandbox allowlist
  ``{http://localhost:7770/, :8090/, :9999/, :8081/}`` (plus the 127.0.0.1
  equivalents).  Anything else is a leak — either the agent ignored the
  sandbox prompt, or the shim's URL gate was bypassed.  This verifier is
  the third enforcement layer (the per-adapter tool allowlist is the first,
  the shim-level URL gate is the second).

Usage:
    from src.verifiers.sandbox_compliance_verifier import (
        verify_sandbox_compliance,
    )
    r = verify_sandbox_compliance(report_md)
    if r["policy_violation"]:
        print(f"Non-sandbox URLs cited: {r['non_sandbox_urls']}")
"""

from __future__ import annotations

from typing import Any

from .citation_format import extract_citations, host_in_set


# Default allowlist: every origin the strict-sandbox arena can reach.
# `host:port` keys match `host_in_set`'s netloc form. Both localhost AND
# 127.0.0.1 are accepted — they're the same socket, and some frameworks
# (notably anything that calls `socket.gethostbyname('localhost')` and
# caches the resolved IP) normalise to 127.0.0.1 before emitting URLs.
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:7770",   # Magento (shopping)
    "http://localhost:9999",   # Postmill (reddit-like)
    "http://localhost:8090",   # Kiwix (offline Wikipedia)
    "http://localhost:8081",   # search shim
    "http://127.0.0.1:7770",
    "http://127.0.0.1:9999",
    "http://127.0.0.1:8090",
    "http://127.0.0.1:8081",
)


def _origin_to_host(origin: str) -> str:
    """Strip scheme to produce `host:port` keys for `host_in_set`.

    Accepts both ``http://localhost:7770`` (full origin) and the bare
    ``localhost:7770`` form. Anything else is passed through; `host_in_set`
    treats bare hosts (no port) as host-only matches.
    """
    s = origin.strip()
    for prefix in ("http://", "https://"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    # Drop any trailing path so ``http://localhost:7770/`` works too.
    s = s.split("/", 1)[0]
    return s


def verify_sandbox_compliance(
    report_md: str,
    allowed_origins: list[str] | None = None,
) -> dict[str, Any]:
    """Audit ``report_md`` against the sandbox URL allowlist.

    Parameters
    ----------
    report_md : str
        The agent's markdown report.
    allowed_origins : list[str] | None
        Origins (``http://host:port`` or bare ``host:port``) that the agent
        is permitted to cite. Defaults to ``DEFAULT_ALLOWED_ORIGINS``.

    Returns
    -------
    dict with keys:
        sandbox_url_pct : float
            Fraction of cited URLs that are in the allowlist. 1.0 if all
            URLs are sandbox; 0.0 if none are; defined as 1.0 when there
            are zero URLs (vacuously compliant, but ``total_urls=0`` lets
            the caller treat that as a separate failure mode).
        total_urls : int
            Total distinct URLs cited (across every citation style).
        sandbox_urls : int
            Count of cited URLs that ARE in the allowlist.
        non_sandbox_urls : list[str]
            Distinct raw URLs (preserving the form the agent emitted) that
            are NOT in the allowlist. Order-preserving on first citation
            offset so downstream readers see them in report order.
        policy_violation : bool
            True iff ``sandbox_url_pct < 1.0`` (equivalently:
            ``len(non_sandbox_urls) > 0``).
    """
    allowed = allowed_origins or list(DEFAULT_ALLOWED_ORIGINS)
    sandbox_hosts = {_origin_to_host(o) for o in allowed}

    # Pull every citation regardless of style (markdown, bare, numbered,
    # footnote, "Source: <url>", bullet-line). sandbox_only=False because
    # we WANT the non-sandbox URLs reported back — that's the whole point
    # of this verifier.
    citations = extract_citations(
        report_md or "",
        sandbox_hosts=sandbox_hosts,
        sandbox_only=False,
    )

    seen_canon: set[str] = set()
    sandbox_urls: list[str] = []
    non_sandbox_urls: list[str] = []

    # extract_citations sorts by char_offset, so iterating preserves
    # first-occurrence order for the non_sandbox_urls list.
    for c in citations:
        if c.canonical_url in seen_canon:
            continue
        seen_canon.add(c.canonical_url)
        if host_in_set(c.raw_url, sandbox_hosts):
            sandbox_urls.append(c.raw_url)
        else:
            non_sandbox_urls.append(c.raw_url)

    total = len(sandbox_urls) + len(non_sandbox_urls)
    if total == 0:
        pct = 1.0
    else:
        pct = len(sandbox_urls) / total

    return {
        "sandbox_url_pct": round(pct, 6),
        "total_urls": total,
        "sandbox_urls": len(sandbox_urls),
        "non_sandbox_urls": non_sandbox_urls,
        "policy_violation": pct < 1.0,
    }


__all__ = ["verify_sandbox_compliance", "DEFAULT_ALLOWED_ORIGINS"]
