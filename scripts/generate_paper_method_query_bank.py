#!/usr/bin/env python3
"""Generate and source-probe the DRA paper-method 336-Query candidate bank.

This is deliberately a candidate-bank builder, not a formal-release compiler.
It follows the public side of the construction method described in the paper:

1. probe the frozen Magento, Postmill, and Kiwix world for each topic angle;
2. construct a public GeneratorView;
3. render a natural high-level Query from GeneratorView only;
4. run deterministic public-query checks.

The script never fabricates Evidence Graph nodes, human span approvals, hidden
answerability proofs, blind-review decisions, or formal-release eligibility.
Those remain mandatory downstream gates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import itertools
import json
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "data"
    / "query_candidates"
    / "paper_method_336_20260730"
    / "topic_packs.json"
)
DEFAULT_OUT = DEFAULT_INPUT.parent
REGISTRY = ROOT / "data" / "golden" / "url_registry.json"

STRUCTURES = (
    "constraint_match_and_select",
    "mechanism_to_case_application",
    "evidence_reconciliation",
)
FORBIDDEN_PUBLIC_TERMS = re.compile(
    r"(?i)\b(?:step[_ -]?id|required[_ -]?proof[_ -]?steps?|"
    r"source[_ -]?url|gold[_ -]?answer|oracle|scorer|"
    r"acceptable[_ -]?conclusions?|formal[_ -]?bindings)\b"
)
URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://")
PROCEDURAL_QUOTA_RE = re.compile(
    r"(?i)(?:at least|minimum(?: of)?|no fewer than|>=)\s*\d+\s*"
    r"(?:sources?|citations?|urls?|pages?|searches?|words?)\b"
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _http_text(url: str, timeout: int) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "dra-paper-method-query-probe/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), body, ""
    except urllib.error.HTTPError as exc:
        return int(exc.code), "", str(exc)
    except Exception as exc:  # network errors are recorded, never promoted to gold
        return 0, "", f"{type(exc).__name__}: {exc}"


def _probe_shopping(base: str, query: str, timeout: int) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/catalogsearch/result/?q={urllib.parse.quote(query)}"
    status, body, error = _http_text(url, timeout)
    product_links = set(
        re.findall(
            r'class="product-item-link"\s+href="([^"]+)"|'
            r'href="([^"]+)"\s+class="product-item-link"',
            body,
        )
    )
    flattened = {left or right for left, right in product_links if left or right}
    return {
        "kind": "shopping",
        "query": query,
        "url": url,
        "http_status": status,
        "first_page_product_count": len(flattened),
        "passed": status == 200 and len(flattened) >= 3,
        "error": error,
    }


def _focused_query_fallbacks(query: str) -> list[str]:
    """Return progressively broader but still topic-linked discovery queries."""
    words = re.findall(r"[A-Za-z0-9]+", query)
    candidates = [query]
    for size in range(min(3, len(words)), 1, -1):
        candidates.extend(" ".join(parts) for parts in itertools.combinations(words, size))
    seen: set[str] = set()
    return [
        item
        for item in candidates
        if not (item.casefold() in seen or seen.add(item.casefold()))
    ]


def _probe_community_once(base: str, query: str, timeout: int) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/search?q={urllib.parse.quote(query)}"
    status, body, error = _http_text(url, timeout)
    match = re.search(r"<h2>\s*([0-9,]+)\s+results?\s+for", body, re.I)
    count = int(match.group(1).replace(",", "")) if match else 0
    thread_links = {
        html.unescape(item)
        for item in re.findall(r'href="(/f/[^"]+)"', body)
        if re.search(r"/f/[^/]+/\d+/", item)
    }
    if count == 0:
        count = len(thread_links)
    return {
        "query": query,
        "url": url,
        "http_status": status,
        "reported_result_count": count,
        "first_page_thread_count": len(thread_links),
        "passed": status == 200 and count >= 5 and len(thread_links) >= 3,
        "error": error,
    }


def _probe_community(base: str, query: str, timeout: int) -> dict[str, Any]:
    attempts = []
    for candidate in _focused_query_fallbacks(query):
        result = _probe_community_once(base, candidate, timeout)
        attempts.append(result)
        if result["passed"]:
            return {
                "kind": "community",
                "query": query,
                "resolved_query": candidate,
                **{key: value for key, value in result.items() if key != "query"},
                "fallback_used": candidate.casefold() != query.casefold(),
                "attempts": attempts,
            }
    best = max(
        attempts,
        key=lambda row: (
            row["first_page_thread_count"],
            row["reported_result_count"],
            len(row["query"].split()),
        ),
    )
    return {
        "kind": "community",
        "query": query,
        "resolved_query": best["query"],
        **{key: value for key, value in best.items() if key != "query"},
        "fallback_used": best["query"].casefold() != query.casefold(),
        "attempts": attempts,
    }


def _probe_wiki_once(
    base: str, book: str, query: str, timeout: int
) -> dict[str, Any]:
    encoded_query = urllib.parse.quote(query)
    encoded_book = urllib.parse.quote(book)
    url = (
        f"{base.rstrip('/')}/search?books.name={encoded_book}"
        f"&pattern={encoded_query}"
    )
    status, body, error = _http_text(url, timeout)
    article_links = {
        html.unescape(item)
        for item in re.findall(r'href="(/content/[^"]+)"', body)
    }
    return {
        "query": query,
        "url": url,
        "http_status": status,
        "first_page_article_count": len(article_links),
        "passed": status == 200 and len(article_links) >= 5,
        "error": error,
    }


def _probe_wiki(base: str, book: str, query: str, timeout: int) -> dict[str, Any]:
    attempts = []
    for candidate in _focused_query_fallbacks(query):
        result = _probe_wiki_once(base, book, candidate, timeout)
        attempts.append(result)
        if result["passed"]:
            return {
                "kind": "wiki",
                "query": query,
                "resolved_query": candidate,
                **{key: value for key, value in result.items() if key != "query"},
                "fallback_used": candidate.casefold() != query.casefold(),
                "attempts": attempts,
            }
    best = max(
        attempts,
        key=lambda row: (
            row["first_page_article_count"],
            len(row["query"].split()),
        ),
    )
    return {
        "kind": "wiki",
        "query": query,
        "resolved_query": best["query"],
        **{key: value for key, value in best.items() if key != "query"},
        "fallback_used": best["query"].casefold() != query.casefold(),
        "attempts": attempts,
    }


def _forum_counts() -> tuple[dict[str, int], str]:
    registry = _read_json(REGISTRY)
    counts = Counter(registry["submissions"].values())
    return dict(sorted(counts.items())), str(registry["version"])


def _probe_all(
    config: dict[str, Any],
    *,
    shopping_base: str,
    community_base: str,
    wiki_base: str,
    wiki_book: str,
    timeout: int,
    workers: int,
    cached_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    forum_counts, registry_version = _forum_counts()
    requests: list[tuple[str, str, str]] = []
    cached: dict[tuple[str, str, str], dict[str, Any]] = {}
    if cached_report:
        for cached_pack in cached_report.get("packs", []):
            for kind in ("shopping", "community", "wiki"):
                for row in cached_pack.get(kind, []):
                    if row.get("passed") is True:
                        cached[
                            (kind, cached_pack["pack_id"], row["query"])
                        ] = row
    for pack in config["packs"]:
        pack_id = pack["pack_id"]
        requests.extend(
            ("shopping", pack_id, query) for query in pack["shopping_queries"]
        )
        requests.extend(
            ("community", pack_id, query) for query in pack["community_queries"]
        )
        requests.extend(("wiki", pack_id, query) for query in pack["wiki_queries"])

    results: dict[tuple[str, str, str], dict[str, Any]] = {
        identity: cached[identity] for identity in requests if identity in cached
    }
    pending_requests = [identity for identity in requests if identity not in cached]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {}
        for kind, pack_id, query in pending_requests:
            if kind == "shopping":
                future = pool.submit(
                    _probe_shopping, shopping_base, query, timeout
                )
            elif kind == "community":
                future = pool.submit(
                    _probe_community, community_base, query, timeout
                )
            else:
                future = pool.submit(
                    _probe_wiki, wiki_base, wiki_book, query, timeout
                )
            futures[future] = (kind, pack_id, query)
        for future in as_completed(futures):
            identity = futures[future]
            try:
                results[identity] = future.result()
            except Exception as exc:
                kind, _, query = identity
                results[identity] = {
                    "kind": kind,
                    "query": query,
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }

    packs: list[dict[str, Any]] = []
    for pack in config["packs"]:
        pack_id = pack["pack_id"]
        shopping = [
            results[("shopping", pack_id, query)]
            for query in pack["shopping_queries"]
        ]
        community = [
            results[("community", pack_id, query)]
            for query in pack["community_queries"]
        ]
        wiki = [
            results[("wiki", pack_id, query)] for query in pack["wiki_queries"]
        ]
        forums = [
            {
                "forum": forum,
                "registered_submissions": forum_counts.get(forum, 0),
                "passed": forum_counts.get(forum, 0) >= 100,
            }
            for forum in pack["forums"]
        ]
        passed = all(
            row["passed"]
            for row in [*shopping, *community, *wiki, *forums]
        )
        packs.append(
            {
                "pack_id": pack_id,
                "label": pack["label"],
                "shopping": shopping,
                "community": community,
                "wiki": wiki,
                "forums": forums,
                "passed": passed,
            }
        )

    return {
        "schema_version": "dra_paper_method_source_probe_v1",
        "world_snapshot": config["world_snapshot"],
        "registry_version": registry_version,
        "bases": {
            "shopping": shopping_base,
            "community": community_base,
            "wiki": wiki_base,
            "wiki_book": wiki_book,
        },
        "thresholds": {
            "shopping_first_page_products": 3,
            "community_reported_results": 5,
            "community_first_page_threads": 3,
            "wiki_first_page_articles": 5,
            "forum_registered_submissions": 100,
        },
        "probe_execution": {
            "network_requests": len(pending_requests),
            "passed_probe_rows_reused": len(results) - len(pending_requests),
        },
        "packs": packs,
    }


def _reuse_probe_report(
    config: dict[str, Any],
    report_path: Path,
) -> dict[str, Any]:
    """Reuse network probes only when every configured discovery query matches."""
    report = _read_json(report_path)
    previous = {row["pack_id"]: row for row in report["packs"]}
    forum_counts, registry_version = _forum_counts()
    refreshed_packs = []
    for pack in config["packs"]:
        old = previous.get(pack["pack_id"])
        if old is None:
            raise SystemExit(f"probe cache missing pack {pack['pack_id']}")
        expected = {
            "shopping": pack["shopping_queries"],
            "community": pack["community_queries"],
            "wiki": pack["wiki_queries"],
        }
        for kind, queries in expected.items():
            cached_queries = [row["query"] for row in old[kind]]
            if cached_queries != queries:
                raise SystemExit(
                    f"probe cache query mismatch for {pack['pack_id']}:{kind}"
                )
        forums = [
            {
                "forum": forum,
                "registered_submissions": forum_counts.get(forum, 0),
                "passed": forum_counts.get(forum, 0) >= 100,
            }
            for forum in pack["forums"]
        ]
        refreshed = {
            **old,
            "label": pack["label"],
            "forums": forums,
        }
        refreshed["passed"] = all(
            row["passed"]
            for row in (
                *refreshed["shopping"],
                *refreshed["community"],
                *refreshed["wiki"],
                *forums,
            )
        )
        refreshed_packs.append(refreshed)
    report["registry_version"] = registry_version
    report["packs"] = refreshed_packs
    return report


def _join_natural(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def _render_query(
    structure: str,
    *,
    profile: str,
    options: list[str],
    constraints: list[str],
    mechanism: str,
    conflict: str,
    decision: str,
    variant: int,
) -> str:
    option_text = _join_natural(options)
    constraint_text = _join_natural(constraints)
    if structure == "constraint_match_and_select":
        templates = (
            (
                "{profile} I am choosing among {options}. The decision has to satisfy "
                "{constraints}. Please compare the options as complete routes rather "
                "than as isolated specifications, explain the trade-offs that matter "
                "in this situation, and {decision}. If none satisfies everything, "
                "identify the least damaging compromise instead of forcing a winner."
            ),
            (
                "{profile} The realistic choices seem to be {options}, and I keep "
                "finding advice aimed at very different users. My hard requirements "
                "are {constraints}. Work out which choices genuinely remain after "
                "those requirements are applied, show what each surviving choice "
                "gives up, and {decision}. I would rather hear that a requirement is "
                "incompatible than get a generic best-of list."
            ),
            (
                "{profile} Before I spend money, I need a decision among {options}. "
                "Please treat {constraints} as real constraints, not preferences that "
                "can quietly disappear. Compare how the options behave in the stated "
                "use case, separate meaningful differences from marketing language, "
                "and {decision}. Explain why the excluded options fail or require a "
                "specific compromise."
            ),
            (
                "{profile} I can see plausible arguments for {options}, which is why "
                "simple ratings are not helping. I need {constraints}. Build the "
                "comparison around those needs. Compare the ownership and usability "
                "trade-offs where they affect the decision, then {decision}. If the "
                "answer depends on a condition I have not considered, make that "
                "condition explicit rather than assuming it away."
            ),
        )
    elif structure == "mechanism_to_case_application":
        templates = (
            (
                "{profile} I am comparing {options}, but I do not want to choose from "
                "labels alone. Explain the decision-relevant effects of {mechanism} "
                "in this case. Apply that explanation to these requirements: "
                "{constraints}. Compare where each option benefits or runs into a "
                "limit, and {decision}. Keep the "
                "mechanism tied to the decision rather than turning the answer into "
                "a general technical overview."
            ),
            (
                "{profile} The options are {options}, and the technical explanations "
                "I encounter keep mentioning {mechanism}. I need to understand which "
                "parts of that mechanism are actually decision-relevant. My "
                "requirements are {constraints}. Trace the practical consequences for each option, "
                "including any condition that reverses the comparison, and "
                "{decision}. Do not assume the most advanced-sounding design is "
                "automatically the best fit."
            ),
            (
                "{profile} I need to decide among {options} while meeting "
                "{constraints}. Please start from the underlying issue of {mechanism} "
                "and show how it plays out in the specific use case: what it improves, "
                "what it cannot solve, and what new trade-off it creates. Then compare "
                "the options on that basis and {decision}, with a conditional answer "
                "if the evidence supports more than one sensible route."
            ),
            (
                "{profile} Product descriptions make {options} sound easy to compare, "
                "but the result seems to depend on {mechanism}. Explain that mechanism "
                "in enough depth to evaluate the options against these requirements: "
                "{constraints}. Use it "
                "to distinguish a real advantage from a specification that may not "
                "matter here, and {decision}. I am looking for a scenario-specific "
                "conclusion, not a universal ranking."
            ),
        )
    else:
        templates = (
            (
                "{profile} I am trying to choose among {options}, but the evidence "
                "appears to disagree: {conflict_clause}. Reconcile the disagreement by "
                "checking whether the sources concern different users, conditions, "
                "measurements, time periods, or meanings. Then apply the result under "
                "these requirements: {constraints}. Finally, {decision}. Preserve uncertainty where the "
                "available evidence does not support one general conclusion."
            ),
            (
                "{profile} Advice about {options} is pulling me in opposite directions. "
                "{conflict_sentence}. Please determine whether this is a true contradiction or "
                "a scope difference, and explain which evidence should carry weight "
                "for my case. Use these requirements as the boundary of the decision: "
                "{constraints}. Then {decision}. Do not average incompatible claims into a false "
                "consensus."
            ),
            (
                "{profile} I need a decision among {options}, yet {conflict_clause}. Investigate "
                "why the claims diverge, including differences in product version, "
                "population, usage, measurement, and evidence attribution where "
                "relevant. After resolving what can be resolved, evaluate the choices "
                "against these requirements: {constraints}. Then {decision}. If the conflict remains bounded, "
                "state exactly what is still unknown."
            ),
            (
                "{profile} Simple ratings are not enough for {options} because "
                "{conflict_clause}. Separate claims that can coexist under different "
                "conditions from claims that genuinely cannot both be right. Then use "
                "these requirements to decide which evidence applies to me: "
                "{constraints}. Finally, {decision}. "
                "I want an explanation of the exclusions and remaining uncertainty, "
                "not a popularity vote."
            ),
        )
    return templates[variant % len(templates)].format(
        profile=profile,
        options=option_text,
        constraints=constraint_text,
        mechanism=mechanism,
        conflict_clause=conflict[:1].lower() + conflict[1:],
        conflict_sentence=conflict[:1].upper() + conflict[1:],
        decision=decision,
    )


def _hard_checks(
    query: str,
    *,
    options: list[str],
    constraints: list[str],
) -> dict[str, Any]:
    lowered = query.casefold()
    missing_options = [item for item in options if item.casefold() not in lowered]
    missing_constraints = [
        item for item in constraints if item.casefold() not in lowered
    ]
    word_count = len(re.findall(r"\b[\w'-]+\b", query))
    checks = {
        "option_coverage": not missing_options,
        "constraint_coverage": not missing_constraints,
        "no_url": URL_RE.search(query) is None,
        "no_evaluator_terms": FORBIDDEN_PUBLIC_TERMS.search(query) is None,
        "no_procedural_quota": PROCEDURAL_QUOTA_RE.search(query) is None,
        "natural_length_75_170_words": 75 <= word_count <= 170,
        "multi_branch_language": sum(
            token in lowered
            for token in (
                "compare",
                "trade-off",
                "explain",
                "reconcile",
                "condition",
                "evidence",
                "decision",
                "choose",
                "choices",
                "requirements",
                "each",
                "gives up",
            )
        )
        >= 2,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "word_count": word_count,
        "character_count": len(query),
        "missing_options": missing_options,
        "missing_constraints": missing_constraints,
    }


def _token_set(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.casefold()))


def _similarity_audit(items: list[dict[str, Any]]) -> dict[str, Any]:
    tokens = [_token_set(item["query"]) for item in items]
    high_pairs: list[dict[str, Any]] = []
    max_similarity = 0.0
    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            union = tokens[left] | tokens[right]
            similarity = (
                len(tokens[left] & tokens[right]) / len(union) if union else 1.0
            )
            max_similarity = max(max_similarity, similarity)
            if similarity >= 0.78:
                high_pairs.append(
                    {
                        "left": items[left]["candidate_id"],
                        "right": items[right]["candidate_id"],
                        "jaccard": round(similarity, 4),
                    }
                )
    return {
        "metric": "lowercased_alphanumeric_token_set_jaccard",
        "threshold": 0.78,
        "maximum": round(max_similarity, 4),
        "high_similarity_pair_count": len(high_pairs),
        "high_similarity_pairs": sorted(
            high_pairs, key=lambda row: row["jaccard"], reverse=True
        ),
    }


def _build_items(
    config: dict[str, Any],
    probe_report: dict[str, Any],
) -> list[dict[str, Any]]:
    probe_by_pack = {row["pack_id"]: row for row in probe_report["packs"]}
    items: list[dict[str, Any]] = []
    serial = 1
    for pack in config["packs"]:
        pack_probe = probe_by_pack[pack["pack_id"]]
        for angle_index, angle in enumerate(pack["angles"]):
            (
                angle_id,
                profile,
                options,
                constraints,
                mechanism,
                conflict,
                decision,
            ) = angle
            source_probe = {
                "shopping": pack_probe["shopping"][angle_index],
                "community": pack_probe["community"][angle_index],
                "wiki": pack_probe["wiki"][angle_index],
                "forums": pack_probe["forums"],
            }
            angle_probe_pass = all(
                row["passed"]
                for row in (
                    source_probe["shopping"],
                    source_probe["community"],
                    source_probe["wiki"],
                    *source_probe["forums"],
                )
            )
            # The paper selects exactly one of the three structures for a graph.
            # Twelve angles per pack make this deterministic assignment balanced
            # (four independent scenarios per structure in every topic pack).
            structure_index = angle_index % len(STRUCTURES)
            structure = STRUCTURES[structure_index]
            query = _render_query(
                structure,
                profile=profile,
                options=options,
                constraints=constraints,
                mechanism=mechanism,
                conflict=conflict,
                decision=decision,
                variant=(angle_index + structure_index) % 4,
            )
            target = {
                "constraint_match_and_select": (
                    f"Compare {', '.join(options)} under all stated constraints; "
                    f"{decision}; explain exclusions and unavoidable trade-offs."
                ),
                "mechanism_to_case_application": (
                    f"Explain {mechanism}, apply it to {', '.join(options)} under "
                    f"the stated constraints, and {decision}."
                ),
                "evidence_reconciliation": (
                    f"Reconcile this apparent conflict: {conflict}; determine the "
                    f"applicable scope, compare {', '.join(options)}, and {decision}."
                ),
            }[structure]
            generator_view = {
                "scenario": profile,
                "constraints": constraints,
                "candidate_actions": options,
                "target": target,
            }
            hard_rules = _hard_checks(
                query,
                options=options,
                constraints=constraints,
            )
            candidate_id = f"dra_paper_qc_{serial:04d}"
            status = (
                "source_probed_query_candidate"
                if angle_probe_pass and hard_rules["passed"]
                else "candidate_requires_revision"
            )
            items.append(
                {
                    "schema_version": "dra_paper_method_query_candidate_v1",
                    "candidate_id": candidate_id,
                    "world_snapshot": config["world_snapshot"],
                    "pack_id": pack["pack_id"],
                    "pack_label": pack["label"],
                    "family": pack["family"],
                    "angle_id": angle_id,
                    "task_structure": structure,
                    "task_structure_status": (
                        "provisional_pending_verified_evidence_graph"
                    ),
                    "generator_view": generator_view,
                    "query": query,
                    "query_sha256": hashlib.sha256(
                        query.encode("utf-8")
                    ).hexdigest(),
                    "generator_view_sha256": _canonical_sha256(generator_view),
                    "source_probe": source_probe,
                    "source_probe_passed": angle_probe_pass,
                    "public_query_hard_rules": hard_rules,
                    "status": status,
                    "formal_eligible": False,
                    "downstream_requirements": [
                        "construct_query_specific_evidence_graph",
                        "verify_exact_support_spans_with_two_independent_annotators",
                        "confirm_one_task_structure_from_verified_evidence_graph",
                        "compile_hidden_answerability_proof",
                        "render_with_version_pinned_registered_model_and_frozen_few_shots",
                        "blind_review_generator_view_and_query",
                        "discard_after_repeated_failure",
                    ],
                }
            )
            serial += 1
    return items


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(
                json.dumps(item, ensure_ascii=False, allow_nan=False, sort_keys=True)
                + "\n"
            )


def _write_csv(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            lineterminator="\n",
            fieldnames=[
                "candidate_id",
                "family",
                "pack_id",
                "pack_label",
                "angle_id",
                "task_structure",
                "status",
                "word_count",
                "query",
            ],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "candidate_id": item["candidate_id"],
                    "family": item["family"],
                    "pack_id": item["pack_id"],
                    "pack_label": item["pack_label"],
                    "angle_id": item["angle_id"],
                    "task_structure": item["task_structure"],
                    "status": item["status"],
                    "word_count": item["public_query_hard_rules"]["word_count"],
                    "query": item["query"],
                }
            )


def _summary(
    config: dict[str, Any],
    items: list[dict[str, Any]],
    probe_report: dict[str, Any],
    similarity: dict[str, Any],
) -> str:
    structures = Counter(item["task_structure"] for item in items)
    families = Counter(item["family"] for item in items)
    statuses = Counter(item["status"] for item in items)
    words = [item["public_query_hard_rules"]["word_count"] for item in items]
    failed_packs = [row["pack_id"] for row in probe_report["packs"] if not row["passed"]]
    failed_queries = [
        item["candidate_id"]
        for item in items
        if not item["public_query_hard_rules"]["passed"]
    ]
    community_probes = [
        row for pack in probe_report["packs"] for row in pack["community"]
    ]
    wiki_probes = [row for pack in probe_report["packs"] for row in pack["wiki"]]
    lines = [
        "# DRA paper-method 336-Query candidate bank",
        "",
        "## Release meaning",
        "",
        "This directory contains source-probed Query candidates produced from public GeneratorViews.",
        "It does **not** contain completed Evidence Graphs, independent human span approvals, hidden",
        "answerability proofs, blind-review approvals, or formal-release certificates. Every row has",
        "`formal_eligible=false` until those paper-required stages are completed.",
        "",
        "## Relationship to the paper method",
        "",
        "This bank implements the public-query candidate stage of the paper's old method:",
        "",
        "1. Every angle has live discovery roots in frozen Magento, Postmill, and Kiwix.",
        "2. Every candidate is compiled from a public `GeneratorView` containing only scenario,",
        "   constraints, candidate actions, and target.",
        "3. The bank is balanced across the paper's three structures: constraint match and select,",
        "   mechanism-to-case application, and evidence reconciliation.",
        "4. Deterministic checks enforce option/constraint preservation, natural length, multi-branch",
        "   language, and the absence of URLs, evaluator vocabulary, and procedural source quotas.",
        "",
        "The paper requires Evidence Records and a verified Evidence Graph before formal generation.",
        "Because those human-verified assets do not yet exist for these new angles, these rows are",
        "intake candidates for that pipeline, not claims of formal paper-compliant release. Each",
        "candidate has one provisional structure; the verified graph must confirm or replace it.",
        "",
        "## Inventory",
        "",
        f"- Topic packs: {len(config['packs'])}",
        f"- Independent scenarios/angles: {sum(len(pack['angles']) for pack in config['packs'])}",
        f"- Query candidates: {len(items)}",
        f"- Passed source probe and public hard rules: {statuses.get('source_probed_query_candidate', 0)}",
        f"- Requires revision: {statuses.get('candidate_requires_revision', 0)}",
        "",
        "### Task structures",
        "",
    ]
    lines.extend(
        f"- `{name}`: {structures[name]}" for name in STRUCTURES
    )
    lines.extend(["", "### Families", ""])
    lines.extend(f"- `{name}`: {count}" for name, count in sorted(families.items()))
    lines.extend(
        [
            "",
            "### Topic coverage",
            "",
            "| Topic pack | Family | Twelve independent research angles | Queries |",
            "|---|---|---|---:|",
        ]
    )
    for pack in config["packs"]:
        angle_names = ", ".join(f"`{angle[0]}`" for angle in pack["angles"])
        lines.append(
            f"| {pack['label']} | `{pack['family']}` | {angle_names} | "
            f"{len(pack['angles'])} |"
        )
    lines.extend(
        [
            "",
            "## Public-query audit",
            "",
            f"- Word count: min {min(words)}, median {statistics.median(words):.1f}, "
            f"mean {statistics.mean(words):.1f}, max {max(words)}",
            f"- Hard-rule failures: {len(failed_queries)}",
            f"- High-similarity pairs at Jaccard >= {similarity['threshold']}: "
            f"{similarity['high_similarity_pair_count']}",
            f"- Maximum pairwise Jaccard: {similarity['maximum']}",
            "",
            "## Frozen-world source probe",
            "",
            f"- Packs passing all shopping/community/wiki/forum probes: "
            f"{len(config['packs']) - len(failed_packs)}/{len(config['packs'])}",
            f"- Failed packs: {', '.join(failed_packs) if failed_packs else 'none'}",
            f"- Magento discovery probes passed: "
            f"{sum(row['passed'] for pack in probe_report['packs'] for row in pack['shopping'])}/"
            f"{sum(len(pack['shopping']) for pack in probe_report['packs'])}",
            f"- Postmill discovery probes passed: "
            f"{sum(row['passed'] for row in community_probes)}/{len(community_probes)}",
            f"- Kiwix discovery probes passed: "
            f"{sum(row['passed'] for row in wiki_probes)}/{len(wiki_probes)}",
            f"- Postmill probes using a recorded focused fallback: "
            f"{sum(row['fallback_used'] for row in community_probes)}",
            f"- Shortest resolved Postmill discovery query: "
            f"{min(len(row['resolved_query'].split()) for row in community_probes)} words",
            f"- Kiwix probes using a recorded focused fallback: "
            f"{sum(row['fallback_used'] for row in wiki_probes)}",
            "",
            "Probe success proves only that each angle has live discovery roots and a sufficiently",
            "populated source neighborhood in the frozen world. It is not a substitute for exact",
            "fact-span verification or an answerability proof.",
            "",
            "## Required promotion path",
            "",
            "1. Build query-specific Evidence Records and a verified Evidence Graph for each angle.",
            "2. Obtain two independent approvals for exact support spans and adjudicate disagreements.",
            "3. Compile a fresh GeneratorView from the approved graph and render with the registered,",
            "   version-pinned generator and the three frozen human-approved few-shots.",
            "4. Run the blind GeneratorView-plus-Query review; regenerate failures and discard repeated",
            "   failures.",
            "5. Freeze only the surviving subset as formal tasks with hidden answerability proofs.",
            "",
            "## Files",
            "",
            "- `queries.jsonl`: full candidate records and private construction probes.",
            "- `queries.csv`: review-friendly flat export.",
            "- `source_probe_report.json`: live Magento/Postmill/Kiwix and registry checks.",
            "- `audit_report.json`: distributions, hard-rule failures, and similarity audit.",
            "- `topic_packs.json`: the 28-pack, 336-angle construction matrix.",
            "- `manifest.json`: content hashes for this deterministic candidate-bank build.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--shopping", default="http://localhost:7770")
    parser.add_argument("--community", default="http://localhost:9999")
    parser.add_argument("--wiki", default="http://localhost:8090")
    parser.add_argument("--wiki-book", default="wikipedia_en_all_nopic")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument(
        "--reuse-probes",
        action="store_true",
        help="reuse the existing report after verifying all network query identities",
    )
    parser.add_argument(
        "--incremental-probes",
        action="store_true",
        help="reuse passing rows whose pack, source, and discovery query are unchanged",
    )
    args = parser.parse_args()

    config = _read_json(args.input)
    if len(config["packs"]) != 28:
        raise SystemExit("topic matrix must contain exactly 28 packs")
    if any(len(pack["angles"]) != 12 for pack in config["packs"]):
        raise SystemExit("every topic pack must contain exactly twelve angles")
    for pack in config["packs"]:
        for field in ("shopping_queries", "community_queries", "wiki_queries"):
            if len(pack[field]) != len(pack["angles"]):
                raise SystemExit(
                    f"{pack['pack_id']}:{field} must align one-to-one with angles"
                )
        angle_ids = [angle[0] for angle in pack["angles"]]
        if len(angle_ids) != len(set(angle_ids)):
            raise SystemExit(f"{pack['pack_id']} contains duplicate angle ids")
    scenarios = [
        angle[1] for pack in config["packs"] for angle in pack["angles"]
    ]
    if len(scenarios) != len(set(scenarios)):
        raise SystemExit("all 336 scenario texts must be unique")

    probe_path = args.out_dir / "source_probe_report.json"
    if args.reuse_probes:
        probe_report = _reuse_probe_report(config, probe_path)
    else:
        cached_report = (
            _read_json(probe_path)
            if args.incremental_probes and probe_path.exists()
            else None
        )
        probe_report = _probe_all(
            config,
            shopping_base=args.shopping,
            community_base=args.community,
            wiki_base=args.wiki,
            wiki_book=args.wiki_book,
            timeout=args.timeout,
            workers=args.workers,
            cached_report=cached_report,
        )
    items = _build_items(config, probe_report)
    if len(items) != 336:
        raise SystemExit(f"expected 336 candidates, got {len(items)}")
    similarity = _similarity_audit(items)
    audit = {
        "schema_version": "dra_paper_method_query_bank_audit_v1",
        "inventory": {
            "packs": len(config["packs"]),
            "angles": sum(len(pack["angles"]) for pack in config["packs"]),
            "queries": len(items),
            "unique_angle_keys": len(
                {(item["pack_id"], item["angle_id"]) for item in items}
            ),
            "unique_scenarios": len(
                {item["generator_view"]["scenario"] for item in items}
            ),
        },
        "structure_distribution": dict(
            sorted(Counter(item["task_structure"] for item in items).items())
        ),
        "family_distribution": dict(
            sorted(Counter(item["family"] for item in items).items())
        ),
        "status_distribution": dict(
            sorted(Counter(item["status"] for item in items).items())
        ),
        "word_counts": {
            "min": min(item["public_query_hard_rules"]["word_count"] for item in items),
            "median": statistics.median(
                item["public_query_hard_rules"]["word_count"] for item in items
            ),
            "mean": statistics.mean(
                item["public_query_hard_rules"]["word_count"] for item in items
            ),
            "max": max(item["public_query_hard_rules"]["word_count"] for item in items),
        },
        "hard_rule_failures": [
            {
                "candidate_id": item["candidate_id"],
                "hard_rules": item["public_query_hard_rules"],
            }
            for item in items
            if not item["public_query_hard_rules"]["passed"]
        ],
        "probe_failed_packs": [
            row for row in probe_report["packs"] if not row["passed"]
        ],
        "similarity": similarity,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.out_dir / "source_probe_report.json", probe_report)
    _write_jsonl(args.out_dir / "queries.jsonl", items)
    _write_csv(args.out_dir / "queries.csv", items)
    _write_json(args.out_dir / "audit_report.json", audit)
    (args.out_dir / "SUMMARY.md").write_text(
        _summary(config, items, probe_report, similarity),
        encoding="utf-8",
    )
    artifact_names = (
        "topic_packs.json",
        "source_probe_report.json",
        "queries.jsonl",
        "queries.csv",
        "audit_report.json",
        "SUMMARY.md",
    )
    manifest = {
        "schema_version": "dra_paper_method_query_bank_manifest_v1",
        "world_snapshot": config["world_snapshot"],
        "inventory": audit["inventory"],
        "formal_eligible": False,
        "generator": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "artifacts": {
            name: {
                "sha256": hashlib.sha256((args.out_dir / name).read_bytes()).hexdigest(),
                "bytes": (args.out_dir / name).stat().st_size,
            }
            for name in artifact_names
        },
    }
    _write_json(args.out_dir / "manifest.json", manifest)

    print(
        json.dumps(
            {
                "ok": not audit["hard_rule_failures"],
                "queries": len(items),
                "status_distribution": audit["status_distribution"],
                "probe_failed_packs": [
                    row["pack_id"] for row in audit["probe_failed_packs"]
                ],
                "hard_rule_failures": len(audit["hard_rule_failures"]),
                "high_similarity_pairs": similarity["high_similarity_pair_count"],
                "out_dir": str(args.out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if not audit["hard_rule_failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
