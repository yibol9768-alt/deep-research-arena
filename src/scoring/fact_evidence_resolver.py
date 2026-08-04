"""On-demand evidence acquisition for frozen-world Fact verification.

The task evidence graph is a seed set, not the boundary of the adjudication
world.  This module resolves report claims against:

1. valid sandbox pages explicitly cited by the report;
2. pages returned by the frozen sandbox search service; and
3. the small task seed corpus supplied by the evidence graph.

Evaluator reads are deliberately recorded in a separate ledger.  They never
become agent observations and therefore cannot make an unobserved citation
pass the Evidence axis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import subprocess
from typing import Any, Protocol

import httpx

from src.scoring.url_registry import FrozenURLRegistry


MODEL_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9.+_-]*\d[A-Za-z0-9.+_-]*\b")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+\-/]*")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_role(source_type: str) -> str:
    return {
        "product": "retailer",
        "forum": "community",
        "wikipedia": "encyclopedic_reference",
        "search_result": "search_index",
    }.get(source_type, "unknown")


def _html_to_text(raw: str) -> str:
    """Return stable visible-ish text while preserving tables and list order."""

    try:
        from bs4 import BeautifulSoup
    except Exception:
        return raw
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return "\n".join(
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    )


def chunk_document(
    *,
    url: str,
    text: str,
    source_type: str,
    document_sha256: str | None = None,
    chunk_chars: int = 1400,
    overlap_chars: int = 220,
    retrieval_mode: str,
) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    document_sha256 = document_sha256 or _sha256_text(text)
    step = max(1, chunk_chars - overlap_chars)
    rows: list[dict[str, Any]] = []
    for start in range(0, len(text), step):
        value = text[start : start + chunk_chars]
        if len(value.strip()) < 40:
            continue
        rows.append(
            {
                "span_id": f"eval:{document_sha256}:{start}",
                "url": url,
                "source_type": source_type,
                "source_role": _source_role(source_type),
                "start": start,
                "end": start + len(value),
                "text": value,
                "sha256": _sha256_text(value),
                "document_sha256": document_sha256,
                "retrieval_mode": retrieval_mode,
                "complete_document_available": True,
            }
        )
    return rows


def claim_search_queries(claim: dict[str, Any]) -> list[str]:
    """Build deterministic entity-first queries without dropping model digits."""

    subject = str(claim.get("subject") or "").strip()
    predicate = str(claim.get("predicate") or "").strip()
    attribution = str(claim.get("attribution") or "").strip()
    qualifiers = claim.get("qualifiers") or {}
    entity_parts = [subject]
    if isinstance(qualifiers, dict):
        for key in ("manufacturer", "brand", "model", "product", "entity"):
            value = str(qualifiers.get(key) or "").strip()
            if value:
                entity_parts.append(value)
    # Model-like tokens such as Flare2, X10, or IPX7 are essential entity
    # qualifiers and must survive the value-blind first-stage query.
    normalized = str(claim.get("normalized_claim") or "")
    entity_parts.extend(MODEL_TOKEN_RE.findall(normalized))
    entity = " ".join(dict.fromkeys(part for part in entity_parts if part))
    queries = [
        " ".join(part for part in (entity, predicate, attribution) if part),
    ]
    # A second query may use the complete proposition.  It is a recall fallback,
    # never the only retrieval route, so an asserted wrong value cannot hide a
    # contradicting page found by the entity-first query.
    if normalized:
        queries.append(normalized)
    return list(dict.fromkeys(" ".join(query.split()) for query in queries if query))


class FactGateway(Protocol):
    def search(self, query: str, *, max_results: int) -> list[dict[str, Any]]:
        ...

    def fetch(self, url: str) -> dict[str, Any]:
        ...

    def product_lookup(self, url: str) -> dict[str, Any] | None:
        ...


@dataclass
class HttpFrozenWorldGateway:
    """Read the frozen sandbox while keeping an evaluator-only local audit."""

    search_base_url: str
    timeout_seconds: float = 30.0
    audit_rows: list[dict[str, Any]] = field(default_factory=list)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.search_base_url.rstrip('/')}{path}"
        response = httpx.post(url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def search(self, query: str, *, max_results: int) -> list[dict[str, Any]]:
        try:
            payload = self._post(
                "/search",
                {
                    "query": query,
                    "max_results": max_results,
                    "include_raw_content": False,
                },
            )
            rows = payload.get("results") or []
            self.audit_rows.append(
                {
                    "operation": "search",
                    "query": query,
                    "ok": True,
                    "result_urls": [
                        str(row.get("url") or "") for row in rows if row.get("url")
                    ],
                }
            )
            return [row for row in rows if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            self.audit_rows.append(
                {
                    "operation": "search",
                    "query": query,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return []

    def fetch(self, url: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                url,
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
            raw = response.text or ""
            ok = response.status_code == 200 and bool(raw)
            row = {
                "operation": "fetch",
                "url": url,
                "ok": ok,
                "http_status": response.status_code,
                "content_sha256": _sha256_text(raw) if raw else None,
                "content_chars": len(raw),
            }
            self.audit_rows.append(row)
            return {
                **row,
                "raw_content": raw,
                "text": _html_to_text(raw),
            }
        except Exception as exc:  # noqa: BLE001
            row = {
                "operation": "fetch",
                "url": url,
                "ok": False,
                "http_status": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
            self.audit_rows.append(row)
            return row

    def product_lookup(self, url: str) -> dict[str, Any] | None:
        try:
            payload = self._post("/product_lookup", {"url": url})
        except Exception as exc:  # noqa: BLE001
            self.audit_rows.append(
                {
                    "operation": "product_lookup",
                    "url": url,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return None
        self.audit_rows.append(
            {
                "operation": "product_lookup",
                "url": url,
                "ok": bool(payload.get("ok")),
                "fields": sorted(
                    key
                    for key, value in payload.items()
                    if key not in {"ok", "url", "error"} and value is not None
                ),
            }
        )
        return payload if payload.get("ok") else None


@dataclass
class SshPowerShellFrozenWorldGateway:
    """Diagnostic gateway for a sandbox hosted on a remote Windows machine.

    This is intentionally an evaluator transport, not an agent tool.  It lets
    a local scorer audit the same frozen services without SSH port forwarding.
    Formal deployments should normally co-locate the scorer and use
    :class:`HttpFrozenWorldGateway`.
    """

    ssh_host: str
    search_base_url: str = "http://localhost:8081"
    timeout_seconds: float = 60.0
    audit_rows: list[dict[str, Any]] = field(default_factory=list)
    control_path: str = field(
        default_factory=lambda: f"/tmp/dra-fact-ssh-{os.getpid()}-%C"
    )

    def _run_json(self, script: str) -> dict[str, Any]:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(
            [
                "ssh",
                "-o",
                "ControlMaster=auto",
                "-o",
                "ControlPersist=300",
                "-o",
                f"ControlPath={self.control_path}",
                self.ssh_host,
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
        )
        if completed.returncode:
            raise RuntimeError(
                f"ssh exited {completed.returncode}: {completed.stderr.strip()}"
            )
        output = completed.stdout.strip()
        start = output.find("{")
        if start < 0:
            raise RuntimeError("remote command returned no JSON object")
        decoder = json.JSONDecoder()
        value, _ = decoder.raw_decode(output[start:])
        if not isinstance(value, dict):
            raise RuntimeError("remote command returned non-object JSON")
        return value

    @staticmethod
    def _ps_json_payload(value: dict[str, Any]) -> str:
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload_b64 = self._ps_json_payload(payload)
        url_b64 = base64.b64encode(
            f"{self.search_base_url.rstrip('/')}{path}".encode("utf-8")
        ).decode("ascii")
        script = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$url = [System.Text.Encoding]::UTF8.GetString(
  [System.Convert]::FromBase64String('{url_b64}')
)
$body = [System.Text.Encoding]::UTF8.GetString(
  [System.Convert]::FromBase64String('{payload_b64}')
)
try {{
  $response = Invoke-RestMethod -UseBasicParsing -Method Post -Uri $url `
    -ContentType 'application/json; charset=utf-8' -Body $body
  @{{ok=$true; payload=$response}} | ConvertTo-Json -Depth 30 -Compress
}} catch {{
  @{{ok=$false; error=$_.Exception.Message}} | ConvertTo-Json -Compress
}}
"""
        envelope = self._run_json(script)
        if not envelope.get("ok"):
            raise RuntimeError(str(envelope.get("error") or "remote POST failed"))
        payload_value = envelope.get("payload")
        return payload_value if isinstance(payload_value, dict) else {}

    def search(self, query: str, *, max_results: int) -> list[dict[str, Any]]:
        try:
            payload = self._post(
                "/search",
                {
                    "query": query,
                    "max_results": max_results,
                    "include_raw_content": False,
                },
            )
            rows = [
                row
                for row in payload.get("results", [])
                if isinstance(row, dict)
            ]
            self.audit_rows.append(
                {
                    "operation": "search",
                    "query": query,
                    "ok": True,
                    "result_urls": [
                        str(row.get("url") or "") for row in rows if row.get("url")
                    ],
                }
            )
            return rows
        except Exception as exc:  # noqa: BLE001
            self.audit_rows.append(
                {
                    "operation": "search",
                    "query": query,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return []

    def fetch(self, url: str) -> dict[str, Any]:
        url_b64 = base64.b64encode(url.encode("utf-8")).decode("ascii")
        script = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$url = [System.Text.Encoding]::UTF8.GetString(
  [System.Convert]::FromBase64String('{url_b64}')
)
try {{
  $response = Invoke-WebRequest -UseBasicParsing -Uri $url
  @{{ok=([int]$response.StatusCode -eq 200); http_status=[int]$response.StatusCode;
     raw_content=[string]$response.Content}} | ConvertTo-Json -Depth 5 -Compress
}} catch {{
  $status = 0
  if ($_.Exception.Response) {{ $status = [int]$_.Exception.Response.StatusCode }}
  @{{ok=$false; http_status=$status; error=$_.Exception.Message}} |
    ConvertTo-Json -Compress
}}
"""
        try:
            row = self._run_json(script)
            raw = str(row.get("raw_content") or "")
            result = {
                "operation": "fetch",
                "url": url,
                "ok": bool(row.get("ok")) and bool(raw),
                "http_status": int(row.get("http_status") or 0),
                "content_sha256": _sha256_text(raw) if raw else None,
                "content_chars": len(raw),
                "raw_content": raw,
                "text": _html_to_text(raw),
            }
        except Exception as exc:  # noqa: BLE001
            result = {
                "operation": "fetch",
                "url": url,
                "ok": False,
                "http_status": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        self.audit_rows.append(
            {
                key: value
                for key, value in result.items()
                if key not in {"raw_content", "text"}
            }
        )
        return result

    def product_lookup(self, url: str) -> dict[str, Any] | None:
        try:
            payload = self._post("/product_lookup", {"url": url})
            ok = bool(payload.get("ok"))
            self.audit_rows.append(
                {
                    "operation": "product_lookup",
                    "url": url,
                    "ok": ok,
                    "fields": sorted(
                        key
                        for key, value in payload.items()
                        if key not in {"ok", "url", "error"} and value is not None
                    ),
                }
            )
            return payload if ok else None
        except Exception as exc:  # noqa: BLE001
            self.audit_rows.append(
                {
                    "operation": "product_lookup",
                    "url": url,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return None


@dataclass
class FrozenFactEvidenceResolver:
    seed_chunks: list[dict[str, Any]]
    citation_map: list[dict[str, Any]]
    observations: dict[str, Any]
    registry: FrozenURLRegistry
    gateway: FactGateway | None = None
    max_search_results: int = 6
    max_search_queries: int = 2
    max_fetched_pages: int = 6
    _document_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    _search_cache: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    audit_rows: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._citation_map = {
            str(row.get("evidence_id")): row
            for row in self.citation_map
            if row.get("evidence_id")
        }

    def _claim_citation_urls(self, claim: dict[str, Any]) -> list[str]:
        citation_ids: list[str] = []
        for occurrence in claim.get("occurrences") or []:
            citation_ids.extend(str(x) for x in occurrence.get("citation_ids", []))
        citation_ids.extend(str(x) for x in claim.get("citation_ids", []))
        urls: list[str] = []
        for citation_id in dict.fromkeys(citation_ids):
            mapped = self._citation_map.get(citation_id) or {}
            observed = (self.observations.get("documents") or {}).get(
                citation_id, {}
            )
            url = str(
                mapped.get("url")
                or (mapped.get("document") or {}).get("url")
                or observed.get("url")
                or ""
            )
            if url:
                urls.append(url)
        return list(dict.fromkeys(urls))

    def _observed_chunks(self, citation_id: str) -> list[dict[str, Any]]:
        observed = (self.observations.get("documents") or {}).get(
            citation_id, {}
        )
        text = str(observed.get("observed_text") or "").strip()
        url = str(observed.get("url") or "")
        if not text or not url:
            return []
        inspected = self.registry.inspect(url)
        source_type = str(inspected.get("source_type", "unknown"))
        document_sha256 = str(
            observed.get("delivery_sha256") or _sha256_text(text)
        )
        observation_tier = str(
            observed.get("observation_tier") or "unknown"
        )
        rows = chunk_document(
            url=url,
            text=text,
            source_type=source_type,
            document_sha256=document_sha256,
            retrieval_mode=f"agent_{observation_tier}",
        )
        for row in rows:
            # Observation IDs stay distinct from evaluator-fetched chunks even
            # when both derive from the same frozen document.
            row["span_id"] = (
                f"observed:{citation_id}:{int(row.get('start') or 0)}"
            )
            row["complete_document_available"] = (
                observation_tier == "full_page"
            )
        return rows

    def _fetch_document(self, url: str) -> dict[str, Any] | None:
        if url in self._document_cache:
            return self._document_cache[url]
        inspected = self.registry.inspect(url)
        if not inspected.get("valid") or self.gateway is None:
            return None
        fetched = self.gateway.fetch(url)
        if not fetched.get("ok") or not fetched.get("text"):
            return None
        document = {
            "url": url,
            "source_type": inspected.get("source_type", "unknown"),
            "text": str(fetched["text"]),
            "content_sha256": fetched.get("content_sha256")
            or _sha256_text(str(fetched["text"])),
            "complete": True,
        }
        if inspected.get("source_type") == "product":
            structured = self.gateway.product_lookup(url)
            if structured:
                document["structured"] = structured
        self._document_cache[url] = document
        return document

    def _search(self, query: str) -> list[dict[str, Any]]:
        if query not in self._search_cache:
            self._search_cache[query] = (
                self.gateway.search(query, max_results=self.max_search_results)
                if self.gateway is not None
                else []
            )
        return self._search_cache[query]

    def prepare(
        self,
        claims: list[dict[str, Any]],
        *,
        max_workers: int = 6,
    ) -> None:
        """Warm search and page caches concurrently for one report.

        The resolver still applies each claim's own cited-first ordering in
        :meth:`resolve`.  Warming changes latency only, not the candidate set or
        score.
        """

        if self.gateway is None:
            return
        queries = list(
            dict.fromkeys(
                query
                for claim in claims
                for query in claim_search_queries(claim)[
                    : self.max_search_queries
                ]
            )
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(self._search, queries))

        urls: list[str] = []
        for claim in claims:
            urls.extend(self._claim_citation_urls(claim))
            for query in claim_search_queries(claim)[: self.max_search_queries]:
                valid_hits = [
                    str(hit.get("url") or "")
                    for hit in self._search_cache.get(query, [])
                    if hit.get("url")
                    and self.registry.inspect(str(hit.get("url"))).get("valid")
                ]
                urls.extend(valid_hits[: self.max_fetched_pages])
        unique_urls = list(dict.fromkeys(urls))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(self._fetch_document, unique_urls))

    def resolve(self, claim: dict[str, Any]) -> dict[str, Any]:
        cited_urls = self._claim_citation_urls(claim)
        search_urls: list[str] = []
        search_queries = claim_search_queries(claim)[: self.max_search_queries]
        for query in search_queries:
            for hit in self._search(query):
                url = str(hit.get("url") or "")
                if url and self.registry.inspect(url).get("valid"):
                    search_urls.append(url)
        # Every valid cited page is inspected first.  The fetch cap applies
        # only to additional search-discovered pages, so a citation-heavy
        # claim cannot silently lose one of its own sources.
        candidate_urls = list(
            dict.fromkeys(cited_urls + search_urls[: self.max_fetched_pages])
        )

        documents: list[dict[str, Any]] = []
        for url in candidate_urls:
            document = self._fetch_document(url)
            if document is not None:
                documents.append(document)

        chunks = [dict(row) for row in self.seed_chunks]
        for document in documents:
            chunks.extend(
                chunk_document(
                    url=document["url"],
                    text=document["text"],
                    source_type=str(document["source_type"]),
                    document_sha256=str(document["content_sha256"]),
                    retrieval_mode=(
                        "direct_cited_full_page"
                        if document["url"] in cited_urls
                        else "sandbox_search_full_page"
                    ),
                )
            )
            structured = document.get("structured")
            if structured:
                structured_text = json.dumps(
                    structured,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                chunks.append(
                    {
                        "span_id": (
                            f"structured:{document['content_sha256']}:product"
                        ),
                        "url": document["url"],
                        "source_type": document["source_type"],
                        "source_role": _source_role(
                            str(document["source_type"])
                        ),
                        "start": 0,
                        "end": len(structured_text),
                        "text": structured_text,
                        "sha256": _sha256_text(structured_text),
                        "document_sha256": document["content_sha256"],
                        "retrieval_mode": "structured_product_lookup",
                        "complete_document_available": True,
                    }
                )

        # When the evaluator gateway is unavailable, retain actual agent
        # observations as candidate text for diagnostic runs.  These do not
        # change the Evidence observation ledger.
        for citation_id in {
            str(x)
            for occurrence in claim.get("occurrences") or []
            for x in occurrence.get("citation_ids", [])
        }:
            chunks.extend(self._observed_chunks(citation_id))

        absence_certificate = None
        if claim.get("claim_kind") == "bounded_absence":
            complete_by_url = {row["url"]: row for row in documents}
            qualifiers = claim.get("qualifiers") or {}
            explicit_scope_urls = (
                qualifiers.get("scope_urls", [])
                if isinstance(qualifiers, dict)
                else []
            )
            scoped_urls = [
                str(url)
                for url in (explicit_scope_urls or cited_urls)
                if str(url)
            ]
            absence_terms = (
                qualifiers.get("absence_terms", [])
                if isinstance(qualifiers, dict)
                else []
            )
            if isinstance(absence_terms, str):
                absence_terms = [absence_terms]
            absence_terms = [
                str(term).strip()
                for term in absence_terms
                if str(term).strip()
            ]
            scope_complete = bool(scoped_urls) and all(
                url in complete_by_url for url in scoped_urls
            )
            present_terms: dict[str, list[str]] = {}
            for url in scoped_urls:
                if url not in complete_by_url:
                    continue
                haystack = complete_by_url[url]["text"].casefold()
                found = [
                    term
                    for term in absence_terms
                    if term.casefold() in haystack
                ]
                if found:
                    present_terms[url] = found
            if scope_complete and absence_terms and not present_terms:
                certificate_payload = {
                    "scope_type": "complete_pages",
                    "scope_urls": scoped_urls,
                    "absence_terms": absence_terms,
                    "document_sha256": {
                        url: complete_by_url[url]["content_sha256"]
                        for url in scoped_urls
                    },
                    "search_queries": search_queries,
                }
                absence_certificate = {
                    "certificate_id": (
                        "absence:"
                        + _sha256_text(
                            json.dumps(
                                certificate_payload,
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                        )[:20]
                    ),
                    **certificate_payload,
                    "scope_complete": True,
                    "terms_absent": True,
                }

        resolution = {
            "claim_id": claim["claim_id"],
            "cited_urls": cited_urls,
            "search_queries": search_queries,
            "candidate_urls": candidate_urls,
            "fetched_urls": [row["url"] for row in documents],
            "chunk_count": len(chunks),
            "absence_certificate": absence_certificate,
            "gateway_available": self.gateway is not None,
        }
        self.audit_rows.append(resolution)
        return {
            "chunks": chunks,
            "preferred_urls": set(cited_urls),
            "absence_certificate": absence_certificate,
            "resolution_audit": resolution,
        }


__all__ = [
    "FactGateway",
    "FrozenFactEvidenceResolver",
    "HttpFrozenWorldGateway",
    "SshPowerShellFrozenWorldGateway",
    "chunk_document",
    "claim_search_queries",
]
