"""ALCE-style citation verifier for deep-research tasks.

Two metrics (following ALCE, EMNLP 2023):

  Citation Recall
    = fraction of claims requiring a citation that actually carry one
    Denominator:  policy.required_for (wildcard-expanded against the report)
    Numerator:    required fields for which the report has at least one
                  in-domain URL attached (citation shape A or B, or — for
                  prose reports — a markdown URL in the same paragraph as
                  the claim's value)

  Citation Precision
    = fraction of given citations whose URL content actually supports the
      claimed value
    A citation (field, url) is "supported" iff:
      - URL is reachable (HTTP 200)
      - URL is in `policy.must_be_in_domain`
      - The value at `field` in the report appears in the fetched page
        text (numeric tolerance of 2% for floats), OR the citation's
        explicit `snippet` appears

  Score = F1(recall, precision)  (harmonic mean)

Also returns the legacy `passed` flag iff recall == precision == 1 and
distinct-source count meets `min_distinct_sources` — preserves backward
compatibility with existing tests.

Robust to two answer shapes:
  (a) Structured JSON answer (ReAct-style) — full recall/precision compute.
  (b) Prose / markdown answer (DeerFlow-style) — parse all [text](url)
      anchors + bare http URLs, use them as "citations". Recall is then
      computed against the report text containing each required claim's
      value (heuristic), precision via the URL-supports-value check.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from .base import VerifierResult
from .report_verifier import _as_dict


_PATH_RE = re.compile(r"([a-zA-Z_][\w]*)|\[(\d+)\]")
_URL_RE = re.compile(r"https?://[^\s)\]\"'>]+", re.I)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def _resolve_path(obj: Any, path: str) -> Any:
    cur = obj
    for m in _PATH_RE.finditer(path):
        key, idx = m.group(1), m.group(2)
        if key is not None:
            if isinstance(cur, dict):
                cur = cur.get(key)
            else:
                return None
        else:
            try:
                cur = cur[int(idx)]
            except Exception:
                return None
    return cur


def _expand_wildcards(paths: list[str], obj: dict) -> list[str]:
    out: list[str] = []
    for p in paths:
        if "[*]" not in p:
            out.append(p)
            continue
        prefix, rest = p.split("[*]", 1)
        arr = _resolve_path(obj, prefix)
        if isinstance(arr, list):
            for i in range(len(arr)):
                out.append(f"{prefix}[{i}]{rest}")
    return out


def _collect_citations(obj: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in obj.get("citations") or []:
        if isinstance(c, dict) and "field" in c and "url" in c:
            out.append(c)

    def _walk(x: Any, path: str) -> None:
        if isinstance(x, dict):
            for k, url in (x.get("_sources") or {}).items():
                out.append({"field": f"{path}.{k}" if path else k, "url": url})
            for k, v in x.items():
                if k == "_sources":
                    continue
                _walk(v, f"{path}.{k}" if path else k)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                _walk(v, f"{path}[{i}]")

    _walk(obj, "")
    return out


def _is_in_domain(url: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    p = urllib.parse.urlparse(url)
    for a in allowed:
        ap = urllib.parse.urlparse(a)
        if ap.netloc and p.netloc == ap.netloc:
            return True
    return False


def _fetch(url: str, page: Any) -> tuple[int, str]:
    """Fetch URL body. Tries Playwright page.request, falls back to requests."""
    try:
        if page is not None and hasattr(page, "request"):
            resp = page.request.get(url, timeout=10_000)
            return resp.status, resp.text()
    except Exception:
        pass
    try:
        import requests  # type: ignore

        r = requests.get(url, timeout=10, allow_redirects=True)
        return r.status_code, r.text
    except Exception:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.status, r.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return 0, f"fetch error: {e}"


def _value_matches(value: Any, body: str) -> bool:
    """True if the claimed value is textually present on the fetched page.

    Numeric values (int/float) get ±2% tolerance, formatted with and
    without trailing ".00".  Strings are case-insensitive substring check
    (first 40 chars, to guard against full-sentence values).
    """
    if value is None:
        return False
    low = body.lower()
    if isinstance(value, (int, float)):
        try:
            v = float(value)
        except Exception:
            return False
        # Try a handful of printed forms
        candidates = [
            f"{v:.2f}",
            f"{v:.1f}",
            f"{int(v)}" if v == int(v) else f"{v}",
            f"${v:.2f}",
        ]
        for c in candidates:
            if c.lower() in low:
                return True
        # Fuzzy: search for any number in body within ±2%
        for m in re.finditer(r"\$?\s*(\d[\d,]*\.?\d*)", body):
            try:
                num = float(m.group(1).replace(",", ""))
            except Exception:
                continue
            if v and abs(num - v) / max(abs(v), 1e-6) <= 0.02:
                return True
        return False
    s = str(value).strip().lower()
    if not s:
        return False
    return s[:40] in low


def _sentence_before(answer: str, pos: int, max_lookback: int = 400) -> str:
    """Return the sentence (or paragraph slice) ending at `pos`.

    Used to augment prose-mode snippets when the anchor text is a short
    numeric reference like `[1]`.  Looks back up to `max_lookback` chars,
    cuts at the start of the current sentence/paragraph.
    """
    start = max(0, pos - max_lookback)
    window = answer[start:pos]
    cut = 0
    for sep in ("\n\n", ". ", "! ", "? ", "\n"):
        idx = window.rfind(sep)
        if idx > cut:
            cut = idx + len(sep)
    return window[cut:].strip()


def _parse_prose_urls(answer: str) -> list[dict[str, Any]]:
    """For DeerFlow-style markdown answers, return [{field, url, snippet}].

    If the anchor text is too short to yield distinctive tokens (e.g.
    numeric academic-style references like `[1](url)`), the snippet is
    augmented with the sentence preceding the citation.  This lets the
    precision check find keywords on the cited page even when the writer
    uses numbered references instead of descriptive link text.
    """
    seen: dict[str, dict[str, Any]] = {}
    for m in _MD_LINK_RE.finditer(answer):
        txt, url = m.group(1), m.group(2)
        anchor_tokens = re.findall(r"[A-Za-z0-9]{3,}", txt)
        if len(anchor_tokens) < 2:
            ctx = _sentence_before(answer, m.start())
            snippet = f"{ctx} {txt}".strip() if ctx else txt
        else:
            snippet = txt
        # First occurrence wins per URL.
        if url not in seen:
            seen[url] = {"field": f"prose:{txt[:40]}", "url": url, "snippet": snippet}
    for m in _URL_RE.finditer(answer):
        url = m.group(0).rstrip(".,;:!?)")
        if url not in seen:
            seen[url] = {"field": "prose:bare", "url": url}
    return list(seen.values())


class CitationVerifier:
    """Emits recall / precision / F1. `passed` = strict perfect run."""

    kind = "citation_check"

    def verify(self, *, task_config: dict[str, Any], answer: str, page: Any = None) -> VerifierResult:
        policy = task_config.get("citation_policy") or {}
        required_for = policy.get("required_for") or []
        allowed = policy.get("must_be_in_domain") or []
        min_sources = int(policy.get("min_distinct_sources") or 0)

        import os as _os
        _PLACEHOLDERS = {
            "__SHOPPING__": _os.environ.get("SHOPPING", "http://localhost:7770"),
            "__REDDIT__":   _os.environ.get("REDDIT",   "http://localhost:9999"),
            "__GITLAB__":   _os.environ.get("GITLAB",   "http://localhost:8023"),
        }
        start = task_config.get("start_url", "")
        if "://" in start:
            base = "/".join(start.split("/")[:3])
            # Pick the placeholder whose default host is similar to `start`
            for ph, val in _PLACEHOLDERS.items():
                if val.split("//")[-1].split("/")[0] in start:
                    _PLACEHOLDERS[ph] = base
        resolved_allowed: list[str] = []
        for a in allowed:
            for ph, val in _PLACEHOLDERS.items():
                a = a.replace(ph, val)
            resolved_allowed.append(a)
        allowed = resolved_allowed

        report = _as_dict(answer)
        prose_mode = report is None

        if prose_mode:
            citations = _parse_prose_urls(answer)
            # Prose-mode recall: can't resolve field paths. We use a
            # coarse proxy — recall = 1 iff any in-domain URL exists AND
            # the original required_for list is non-empty; otherwise 0.
            # Precision still computed per URL.
            required = _expand_wildcards(required_for, {}) or []
        else:
            citations = _collect_citations(report)
            required = _expand_wildcards(required_for, report)

        # ---- Precision: per-citation support check ----
        cite_results: list[dict[str, Any]] = []
        distinct: set[str] = set()
        supported_count = 0
        for c in citations:
            url = (c.get("url") or "").strip()
            r: dict[str, Any] = {"field": c.get("field"), "url": url}
            if not url:
                r["reason"] = "empty url"
                cite_results.append(r)
                continue
            if not _is_in_domain(url, allowed):
                r["reason"] = "out_of_domain"
                cite_results.append(r)
                continue
            status, body = _fetch(url, page)
            r["status"] = status
            if status != 200:
                r["reason"] = "unreachable"
                cite_results.append(r)
                continue
            distinct.add(url)

            # What value is this citation supposed to support?
            value = None
            if not prose_mode and isinstance(c.get("field"), str):
                value = _resolve_path(report, c["field"])
            snippet = c.get("snippet")
            ok = False
            if snippet and isinstance(snippet, str) and snippet.strip():
                # Snippet is the link text in prose mode, or an explicit
                # snippet string in JSON mode. We split the snippet into
                # tokens (≥3 chars) and require most to appear on the
                # fetched page — the link text often contains brand /
                # model names which is exactly what we want to verify.
                tokens = [t for t in re.findall(r"[A-Za-z0-9]{3,}", snippet)][:6]
                if tokens:
                    hits = sum(1 for t in tokens if t.lower() in body.lower())
                    if hits / len(tokens) >= 0.5:
                        ok = True
                        r["match"] = "snippet_tokens"
                        r["snippet_hits"] = f"{hits}/{len(tokens)}"
            if not ok and value is not None:
                ok = _value_matches(value, body)
                if ok:
                    r["match"] = "value"
            # No free pass in prose mode: URL reachability alone is
            # explicitly NOT sufficient. We need snippet/value support.
            if ok:
                supported_count += 1
                r["supported"] = True
            else:
                r["supported"] = False
                r.setdefault("reason", "value_not_supported_on_page")
            cite_results.append(r)

        total_citations = len(citations)
        precision_substring = (supported_count / total_citations) if total_citations else 0.0
        precision = precision_substring  # default mode

        # ---- Claim-level NLI entailment (if enabled) ----
        # CITATION_MODE=entailment swaps the headline precision from
        # substring-matching to judge-LLM entailment (DeepResearch Bench
        # FACT / RAGChecker protocol). The substring number is still
        # emitted as a baseline in `details` for ablation.
        nli_result: dict[str, Any] | None = None
        import os as _os_local
        if _os_local.environ.get("CITATION_MODE", "substring").lower() == "entailment" and prose_mode:
            try:
                from .citation_nli import nli_score_citations
                # Build {url: body} from whatever we already fetched.
                page_bodies: dict[str, str] = {}
                for c, r in zip(citations, cite_results):
                    url = c.get("url") or ""
                    if url and r.get("status") == 200:
                        # Re-fetch body if we didn't retain it above.
                        s2, b2 = _fetch(url, page)
                        if s2 == 200 and b2:
                            # strip html tags roughly
                            page_bodies[url] = re.sub(r"<[^>]+>", " ", b2)[:20000]
                nli_result = nli_score_citations(answer, page_bodies, max_claims=20)
                precision = nli_result["citation_precision_nli"]
            except Exception as e:
                nli_result = {"error": f"{type(e).__name__}: {e}"}

        # ---- Recall: required claims that got a *supported* citation ----
        # JSON mode  : recall = covered_required / total_required, where
        #              "covered" = required field has at least one
        #              citation whose URL was supported.
        # Prose mode : we can't resolve field→URL, so recall proxies as
        #              supported_count / max(min_distinct_sources,
        #              total_required). Caps at 1.
        supported_fields = {
            c.get("field")
            for c, r in zip(citations, cite_results)
            if r.get("supported") and c.get("field")
        }
        if prose_mode:
            denom = max(min_sources, len(required) if required else min_sources, 1)
            recall = min(1.0, supported_count / denom)
            covered_required = supported_count
            total_required = denom
        else:
            covered_required = sum(1 for req in required if req in supported_fields)
            total_required = len(required)
            recall = (covered_required / total_required) if total_required else 1.0

        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        distinct_ok = len(distinct) >= min_sources
        strict_pass = (recall == 1.0 and precision == 1.0 and distinct_ok and total_citations > 0)

        details = {
            "citation_recall": round(recall, 3),
            "citation_precision": round(precision, 3),
            "citation_precision_substring_baseline": round(precision_substring, 3),
            "citation_precision_nli": (nli_result or {}).get("citation_precision_nli"),
            "citation_mode": _os_local.environ.get("CITATION_MODE", "substring"),
            "nli_result": nli_result,
            "citation_f1": round(f1, 3),
            "total_citations": total_citations,
            "supported_citations": supported_count,
            "covered_required": covered_required,
            "total_required": total_required,
            "distinct_sources": len(distinct),
            "min_distinct_sources": min_sources,
            "prose_mode": prose_mode,
            "per_citation": cite_results[:15],  # cap for log size
        }

        return VerifierResult(score=round(f1, 3), passed=strict_pass, details=details)
