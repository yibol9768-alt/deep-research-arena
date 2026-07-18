"""Deterministic scorer for DRA Route A grounded breadth rubrics.

The scorer never fetches a URL.  A rubric atom passes only when the report
addresses it, satisfies its response contract, binds a legitimate citation near
that discussion, and the cited support was visible in this run's observation
ledger.  URL fabrication remains a separate integrity metric.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.eval.observation_ledger import ObservationEvent, ObservationLedger, load_observation_ledger
from src.eval.query_rubric_schema import QueryRubric, TextMatcher, load_query_rubric
from src.eval.url_registry import UrlRegistry
from src.verifiers.citation_format import Citation, extract_citations


RESULT_SEMANTICS = "route_a_result_v2"


@dataclass(frozen=True)
class TextBlock:
    start: int
    end: int
    text: str
    masked_text: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mask_urls(text: str) -> str:
    """Blank URL destinations while preserving offsets and Markdown labels."""

    chars = list(text)
    for match in re.finditer(r"https?://[^\s<>]+", text, re.IGNORECASE):
        for index in range(match.start(), match.end()):
            chars[index] = " "
    return "".join(chars)


def _blocks(report: str) -> list[TextBlock]:
    # Markdown paragraphs and list items are the binding unit.  A bibliography
    # elsewhere in the answer therefore cannot silently support a claim.
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in re.finditer(r"(?:\r?\n){2,}", report):
        if match.start() > cursor and report[cursor:match.start()].strip():
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(report) and report[cursor:].strip():
        spans.append((cursor, len(report)))
    if not spans and report.strip():
        spans.append((0, len(report)))
    masked = _mask_urls(report)
    return [
        TextBlock(start, end, report[start:end], masked[start:end])
        for start, end in spans
    ]


def _contains(text: str, term: str) -> bool:
    # Word boundaries are helpful for simple tokens, but phrases, hyphenated
    # forms and CJK text are matched as normalized substrings.
    haystack = re.sub(r"\s+", " ", text).casefold()
    needle = re.sub(r"\s+", " ", term).casefold()
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9_]+", needle):
        return re.search(rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9_])", haystack) is not None
    return needle in haystack


def matcher_passes(text: str, matcher: TextMatcher) -> bool:
    for group in matcher.all_term_groups:
        if not any(_contains(text, term) for term in group):
            return False
    alternatives_present = bool(matcher.accepted_phrases or matcher.accepted_regex)
    if alternatives_present:
        phrase_hit = any(_contains(text, phrase) for phrase in matcher.accepted_phrases)
        regex_hit = any(
            re.search(pattern, text, re.IGNORECASE | re.DOTALL) is not None
            for pattern in matcher.accepted_regex
        )
        if not (phrase_hit or regex_hit):
            return False
    return matcher.has_contract


def matcher_passes_in_local_window(text: str, matcher: TextMatcher, window: int) -> bool:
    """Require all matcher terms to co-occur in one bounded text window."""

    if len(text) <= window:
        return matcher_passes(text, matcher)
    step = max(1, window // 2)
    starts = list(range(0, max(1, len(text) - window + 1), step))
    final_start = max(0, len(text) - window)
    if not starts or starts[-1] != final_start:
        starts.append(final_start)
    return any(matcher_passes(text[start:start + window], matcher) for start in starts)


def _citation_in_block(citation: Citation, block: TextBlock) -> bool:
    return block.start <= citation.char_offset < block.end


def _citation_window(block: TextBlock, citation: Citation, radius: int) -> str:
    start = max(block.start, citation.char_offset - radius)
    end = min(block.end, citation.char_offset + radius)
    relative_start = start - block.start
    relative_end = end - block.start
    return block.masked_text[relative_start:relative_end]


def _canonical_for_registry(registry: UrlRegistry, url: str) -> str | None:
    result = registry.classify(url)
    return result.get("canonical") if result.get("in_corpus") is True else None


def _allowed_source(
    classification: Mapping[str, Any],
    *,
    roles: Sequence[str],
    acceptable_urls: set[str],
) -> bool:
    if classification.get("in_corpus") is not True:
        return False
    if roles and classification.get("host_role") not in roles:
        return False
    if acceptable_urls and classification.get("canonical") not in acceptable_urls:
        return False
    return True


def _event_canonical(event: ObservationEvent, registry: UrlRegistry) -> str | None:
    return _canonical_for_registry(registry, event.canonical_url or event.request_url)


def _event_can_support(event: ObservationEvent, observation_mode: str) -> bool:
    if not event.observable:
        return False
    if event.event_type == "search_result":
        return observation_mode == "snippet_or_body"
    if event.event_type in {"fetch_body", "extracted_body"}:
        return event.http_status == 200
    return False


def _discovery_licensed(
    event: ObservationEvent,
    canonical_url: str,
    ledger: ObservationLedger,
    registry: UrlRegistry,
    seed_urls: set[str],
) -> bool:
    if canonical_url in seed_urls or event.event_type == "search_result":
        return True
    for prior in ledger.events:
        if prior.event_id >= event.event_id:
            break
        if prior.event_type not in {"search_result", "page_link"}:
            continue
        if _event_canonical(prior, registry) == canonical_url:
            return True
    return False


def _support_for_citation(
    citation: Citation,
    atom: Any,
    ledger: ObservationLedger,
    registry: UrlRegistry,
    seed_urls: set[str],
) -> dict[str, Any]:
    classification = registry.classify(citation.raw_url)
    acceptable_urls = {
        value
        for url in atom.evidence.acceptable_source_urls
        if (value := _canonical_for_registry(registry, url)) is not None
    }
    if not _allowed_source(
        classification,
        roles=atom.evidence.acceptable_source_roles,
        acceptable_urls=acceptable_urls,
    ):
        return {
            "supported": False,
            "source_valid": False,
            "canonical_url": classification.get("canonical"),
            "classification": classification,
            "reason": "citation_not_acceptable_source",
        }

    canonical_url = str(classification["canonical"])
    for event in ledger.events:
        if _event_canonical(event, registry) != canonical_url:
            continue
        if not _event_can_support(event, atom.evidence.observation_mode):
            continue
        text = event.visible_text(ledger.blob_loader)
        if not text or not matcher_passes_in_local_window(
            text,
            atom.evidence.relevance_contract,
            atom.evidence.evidence_window_chars,
        ):
            continue
        discovery_traced = (
            _discovery_licensed(event, canonical_url, ledger, registry, seed_urls)
            if atom.evidence.track_discovery
            else None
        )
        return {
            "supported": True,
            "source_valid": True,
            "canonical_url": canonical_url,
            "classification": classification,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "discovery_traced": discovery_traced,
            "reason": "relevant_evidence_observed",
        }
    return {
        "supported": False,
        "source_valid": True,
        "canonical_url": canonical_url,
        "classification": classification,
        "reason": "relevant_evidence_not_observed",
    }


def _coerce_ledger(
    value: ObservationLedger | str | Path,
    expected_run_id: str | None,
) -> ObservationLedger:
    if isinstance(value, ObservationLedger):
        if expected_run_id is not None and value.run_id != str(expected_run_id):
            return ObservationLedger.unavailable(
                "observation_run_id_mismatch",
                f"ledger run_id {value.run_id!r} does not match expected {expected_run_id!r}",
                run_id=value.run_id,
            )
        return value
    return load_observation_ledger(value, expected_run_id=expected_run_id)


def _withheld(
    rubric: QueryRubric,
    report: str,
    reason_codes: Iterable[str],
    *,
    run_id: str | None,
) -> dict[str, Any]:
    return {
        "result_semantics": RESULT_SEMANTICS,
        "scoring_semantics": rubric.scoring_semantics,
        "status": "withheld",
        "attributable": False,
        "reason_codes": sorted(set(reason_codes)),
        "task_id": rubric.task_id,
        "run_id": run_id,
        "rubric_sha256": rubric.content_sha256,
        "report_sha256": _sha256_text(report),
        "required_atoms": len(rubric.atoms),
        "matched_atoms": None,
        "grounded_atoms": None,
        "requirement_coverage": None,
        "grounded_requirement_coverage": None,
        "url_fabrication_rate": None,
        "integrity_clean": None,
        "acquisition_trace_coverage": None,
        "acquisition_trace_numerator": None,
        "acquisition_trace_denominator": None,
        "atom_results": [],
    }


def score_query_rubric(
    rubric_value: QueryRubric | str | Path | Mapping[str, Any],
    report: str,
    ledger_value: ObservationLedger | str | Path,
    registry: UrlRegistry,
    *,
    expected_run_id: str | None = None,
    seed_urls: Iterable[str] = (),
    require_frozen: bool = True,
    corpus_registry_hash: str | None = None,
) -> dict[str, Any]:
    """Score one report without network I/O or weighted composition."""

    rubric = rubric_value if isinstance(rubric_value, QueryRubric) else load_query_rubric(rubric_value)
    ledger = _coerce_ledger(ledger_value, expected_run_id)
    preflight: list[str] = []
    if require_frozen and rubric.status != "frozen":
        preflight.append("rubric_not_frozen")
    if require_frozen and rubric.status == "frozen":
        if corpus_registry_hash is None:
            preflight.append("corpus_registry_hash_unverified")
        elif corpus_registry_hash != rubric.corpus_registry_hash:
            preflight.append("corpus_registry_hash_mismatch")
    if not registry.loaded:
        preflight.append("url_registry_missing")
    if not ledger.complete:
        preflight.extend(ledger.withhold_reason_codes or ["observation_ledger_incomplete"])
    if preflight:
        return _withheld(rubric, report, preflight, run_id=ledger.run_id)

    citations = extract_citations(report, sandbox_only=False)
    reachability = registry.reachability_score(citation.raw_url for citation in citations)
    if reachability.get("status") == "unknown" or reachability.get("n_unknown", 0):
        return _withheld(
            rubric,
            report,
            ["url_membership_unknown"],
            run_id=ledger.run_id,
        )

    canonical_seeds = {
        value
        for url in seed_urls
        if (value := _canonical_for_registry(registry, url)) is not None
    }
    atom_results: list[dict[str, Any]] = []
    report_blocks = _blocks(report)

    for atom in rubric.atoms:
        candidate_blocks = [
            block for block in report_blocks
            if matcher_passes(block.masked_text, atom.mention)
        ]
        addressed = bool(candidate_blocks)
        response_blocks = [
            block for block in candidate_blocks
            if matcher_passes(block.masked_text, atom.response_contract)
        ]
        response_contract_pass = bool(response_blocks)
        requirement_matched = addressed and response_contract_pass
        bound: list[Citation] = []
        for block in response_blocks:
            for citation in citations:
                if not _citation_in_block(citation, block):
                    continue
                local_text = _citation_window(
                    block, citation, atom.evidence.citation_binding_window_chars
                )
                if (
                    matcher_passes(local_text, atom.mention)
                    and matcher_passes(local_text, atom.response_contract)
                ):
                    bound.append(citation)
        # Preserve order but collapse repeated parser views of the same site.
        unique_bound: list[Citation] = []
        seen_sites: set[tuple[str, int]] = set()
        for citation in bound:
            key = (citation.raw_url, citation.char_offset)
            if key not in seen_sites:
                seen_sites.add(key)
                unique_bound.append(citation)
        support_rows = [
            _support_for_citation(citation, atom, ledger, registry, canonical_seeds)
            for citation in unique_bound
        ]
        supported_sources = {
            row["canonical_url"]
            for row in support_rows
            if row.get("supported") and row.get("canonical_url")
        }
        observed_source_roles = {
            row["classification"]["host_role"]
            for row in support_rows
            if row.get("supported") and row.get("classification", {}).get("host_role")
        }
        valid_bound_sources = {
            row["canonical_url"]
            for row in support_rows
            if row.get("source_valid") and row.get("canonical_url")
        }
        traced_sources = {
            row["canonical_url"]
            for row in support_rows
            if row.get("supported") and row.get("discovery_traced") is True
        }
        required_roles_observed = set(atom.evidence.required_source_roles).issubset(
            observed_source_roles
        )
        enough_sources = (
            len(supported_sources) >= atom.evidence.minimum_distinct_sources
            and required_roles_observed
        )
        citation_bound = bool(unique_bound)
        valid_source_pass = len(valid_bound_sources) >= atom.evidence.minimum_distinct_sources
        relevant_evidence_observed = enough_sources
        passed = (
            requirement_matched
            and citation_bound
            and valid_source_pass
            and relevant_evidence_observed
        )
        discovery_trace_coverage = (
            len(traced_sources) / len(supported_sources)
            if atom.evidence.track_discovery and supported_sources
            else None
        )

        reasons: list[str] = []
        if not addressed:
            reasons.append("atom_not_addressed")
        elif not response_contract_pass:
            reasons.append("response_contract_failed")
        if not citation_bound:
            reasons.append("no_local_citation")
        if citation_bound and not relevant_evidence_observed:
            reasons.append("insufficient_relevant_evidence")
            if not required_roles_observed:
                reasons.append("required_source_roles_missing")
            reasons.extend(
                row["reason"] for row in support_rows if not row.get("supported") and row.get("reason")
            )
        atom_results.append({
            "atom_id": atom.atom_id,
            "atom_type": atom.atom_type,
            "description": atom.description,
            "topic_addressed": addressed,
            "response_contract_pass": response_contract_pass,
            "requirement_matched": requirement_matched,
            "citation_bound": citation_bound,
            "valid_source_pass": valid_source_pass,
            "relevant_evidence_observed": relevant_evidence_observed,
            "discovery_trace_coverage": discovery_trace_coverage,
            "passed": passed,
            "required_distinct_sources": atom.evidence.minimum_distinct_sources,
            "observed_distinct_sources": len(supported_sources),
            "required_source_roles": list(atom.evidence.required_source_roles),
            "observed_source_roles": sorted(observed_source_roles),
            "supported_sources": sorted(supported_sources),
            "discovery_traced_sources": sorted(traced_sources),
            "bound_citations": [
                {
                    "raw_url": citation.raw_url,
                    "char_offset": citation.char_offset,
                    "style": citation.style,
                }
                for citation in unique_bound
            ],
            "support_checks": support_rows,
            "reason_codes": sorted(set(reasons)),
        })

    total = len(atom_results)
    matched_count = sum(row["requirement_matched"] for row in atom_results)
    grounded_count = sum(row["passed"] for row in atom_results)
    n_in = int(reachability.get("n_in_corpus") or 0)
    n_fabricated = int(reachability.get("n_fabricated") or 0)
    url_denom = n_in + n_fabricated
    fabrication_rate = n_fabricated / url_denom if url_denom else None
    trace_numerator = sum(
        len(row["discovery_traced_sources"])
        for row in atom_results
        if row["discovery_trace_coverage"] is not None
    )
    trace_denominator = sum(
        row["observed_distinct_sources"]
        for row in atom_results
        if row["discovery_trace_coverage"] is not None
    )
    return {
        "result_semantics": RESULT_SEMANTICS,
        "scoring_semantics": rubric.scoring_semantics,
        "status": "ok",
        "attributable": True,
        "reason_codes": [],
        "task_id": rubric.task_id,
        "run_id": ledger.run_id,
        "rubric_sha256": rubric.content_sha256,
        "report_sha256": _sha256_text(report),
        "required_atoms": total,
        "matched_atoms": matched_count,
        "grounded_atoms": grounded_count,
        "requirement_coverage": matched_count / total,
        "grounded_requirement_coverage": grounded_count / total,
        "all_atoms_grounded": grounded_count == total,
        "url_fabrication_rate": fabrication_rate,
        "integrity_clean": (n_fabricated == 0) if url_denom else None,
        "acquisition_trace_coverage": (
            trace_numerator / trace_denominator if trace_denominator else None
        ),
        "acquisition_trace_numerator": trace_numerator,
        "acquisition_trace_denominator": trace_denominator,
        "url_integrity": reachability,
        "atom_results": atom_results,
    }


def aggregate_query_rubric_scores(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate Route A without mixing coverage and URL integrity."""

    values = list(rows)
    attributable = [row for row in values if row.get("status") == "ok" and row.get("attributable") is True]
    withheld = [row for row in values if row not in attributable]
    if not attributable:
        return {
            "result_semantics": "route_a_aggregate_v2",
            "n_runs": len(values),
            "n_attributable": 0,
            "n_withheld": len(withheld),
            "macro_grounded_requirement_coverage": None,
            "macro_requirement_coverage": None,
            "url_fabrication_rate": None,
            "integrity_clean_rate": None,
            "acquisition_trace_coverage": None,
        }
    n_in = sum(int((row.get("url_integrity") or {}).get("n_in_corpus") or 0) for row in attributable)
    n_fab = sum(int((row.get("url_integrity") or {}).get("n_fabricated") or 0) for row in attributable)
    clean_rows = [row for row in attributable if row.get("integrity_clean") is not None]
    trace_num = sum(int(row.get("acquisition_trace_numerator") or 0) for row in attributable)
    trace_den = sum(int(row.get("acquisition_trace_denominator") or 0) for row in attributable)
    return {
        "result_semantics": "route_a_aggregate_v2",
        "n_runs": len(values),
        "n_attributable": len(attributable),
        "n_withheld": len(withheld),
        "macro_grounded_requirement_coverage": sum(float(row["grounded_requirement_coverage"]) for row in attributable) / len(attributable),
        "macro_requirement_coverage": sum(float(row["requirement_coverage"]) for row in attributable) / len(attributable),
        "url_fabrication_rate": n_fab / (n_in + n_fab) if n_in + n_fab else None,
        "integrity_clean_rate": (
            sum(bool(row["integrity_clean"]) for row in clean_rows) / len(clean_rows)
            if clean_rows else None
        ),
        "acquisition_trace_coverage": trace_num / trace_den if trace_den else None,
        "acquisition_trace_numerator": trace_num,
        "acquisition_trace_denominator": trace_den,
        "n_cited_in_corpus": n_in,
        "n_cited_fabricated": n_fab,
    }


def dump_result(result: Mapping[str, Any], *, pretty: bool = False) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2 if pretty else None, sort_keys=pretty)
