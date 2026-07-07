"""FlowSearcher-DS: Memory-guided deep research agent.

Uses hierarchical memory (L1 task-level / L2 intent-level / L3 global) to
guide workflow synthesis and execution. Searches via sandbox shim, cites
sandbox URLs, produces markdown reports.

Called from run_deep_task.py as a registered runner.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.memory.hierarchical import HierarchicalMemory, classify_intent
from scripts.runners.evidence_fallback import fallback_enabled


DEFAULT_SHIM_URL = "http://localhost:8081"
DEFAULT_DS_PROXY = "http://localhost:8088/v1"
LLM_TIMEOUT = float(os.environ.get("FLOWSEARCHER_LLM_TIMEOUT", "600"))
FETCH_TIMEOUT = float(os.environ.get("FLOWSEARCHER_FETCH_TIMEOUT", "12"))
PER_PAGE_CHARS = int(os.environ.get("FLOWSEARCHER_PER_PAGE_CHARS", "3000"))
PAGES_PER_SUBGOAL = int(os.environ.get("FLOWSEARCHER_PAGES_PER_SUBGOAL", "3"))
EVIDENCE_BUDGET = 25000


# --- Endpoint precedence (Defect 1) ----------------------------------------
# The lane used to bind SHIM_URL / DS_PROXY into module constants at import,
# and split OPENAI_BASE_URL vs DS_PROXY, which could silently route this lane
# to a different backbone than the harness intended. We now resolve both
# endpoints at CALL time through one pure precedence resolver.

def _resolve_endpoint(explicit: str | None, arg: str | None,
                      fallback: str | None, default: str) -> str:
    """Pure precedence resolver: first non-empty of
    explicit env > harness-provided arg > fallback env > default.

    Pure: takes already-read values, does not touch os.environ, so it is
    deterministically unit-testable.
    """
    for cand in (explicit, arg, fallback, default):
        if cand:
            return cand
    return default


def _resolve_llm_base_url(arg_url: str | None = None) -> str:
    """LLM base URL: FLOWSEARCHER_LLM_BASE_URL > arg > DS_PROXY_URL > default."""
    return _resolve_endpoint(
        os.environ.get("FLOWSEARCHER_LLM_BASE_URL"),
        arg_url,
        os.environ.get("DS_PROXY_URL"),
        DEFAULT_DS_PROXY,
    )


def _resolve_shim_url(arg_url: str | None = None) -> str:
    """Shim URL: FLOWSEARCHER_SHIM_URL > arg > SHIM_URL > default."""
    return _resolve_endpoint(
        os.environ.get("FLOWSEARCHER_SHIM_URL"),
        arg_url,
        os.environ.get("SHIM_URL"),
        DEFAULT_SHIM_URL,
    )


def _error_stub(phase: str, reason: str) -> str:
    """Honest failure stub (Defect 2). Classified as ``stub_exception`` by
    src/eval/report_stubs so a total failure surfaces instead of laundering
    into a scored zero with meta.error null."""
    reason = " ".join(str(reason).split())[:200] or "unknown"
    return f"(flowsearcher error: {phase}: {reason})"


def _search(query: str, shim_url: str, max_results: int = 10) -> list[dict]:
    try:
        r = requests.post(
            f"{shim_url.rstrip('/')}/search",
            json={
                "query": query,
                "api_key": os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"),
                "max_results": max_results,
                "include_raw_content": False,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("results", [])
    except Exception as e:
        print(f"  [fs] search error for '{query[:60]}': {e}")
        return []


def _fetch_page(url: str, shim_url: str, max_chars: int = PER_PAGE_CHARS,
                timeout: float | None = None) -> str:
    """Fetch a page THROUGH the sandbox shim /extract endpoint (Defect 3).

    Going through the shim (not a raw requests.get to the origin) respects the
    shim/localhost sandbox allowlist contract: off-allowlist URLs are refused
    by the shim, so this cannot be used to reach the open internet. On any
    failure the caller degrades to the search snippet.
    """
    timeout = FETCH_TIMEOUT if timeout is None else timeout
    try:
        r = requests.post(
            f"{shim_url.rstrip('/')}/extract",
            json={"urls": [url]},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return ""
        text = results[0].get("raw_content") or ""
    except Exception:
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _llm_call(messages: list[dict], base_url: str,
              model: str = "deepseek-v4-flash",
              max_tokens: int = 4096, temperature: float = 0.3) -> str:
    ds_key = os.environ.get("OPENAI_API_KEY", "anything")
    for attempt in range(1, 4):
        try:
            r = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {ds_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=LLM_TIMEOUT,
            )
            if r.status_code >= 400:
                print(f"  [fs] LLM HTTP {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  [fs] LLM error attempt={attempt}: {type(e).__name__}: {e}")
            time.sleep(min(2 ** attempt, 10))
    return ""


def decompose_intent(intent: str) -> list[dict]:
    subgoals = []
    parts = re.split(r"\n\n?\(([A-Z])\)\s*", intent)
    if len(parts) < 3:
        parts = re.split(r"\(([A-Z])\)\s*", intent)

    i = 1
    while i < len(parts) - 1:
        label = parts[i]
        body = parts[i + 1].strip()
        title_match = re.match(r"^([A-Z][A-Z\s/\-]+)\s*[—–-]\s*", body)
        title = title_match.group(1).strip() if title_match else f"Section {label}"
        subgoals.append({"label": label, "title": title, "body": body})
        i += 2

    if not subgoals:
        subgoals.append({"label": "A", "title": "Full Report", "body": intent})

    return subgoals


def _build_experience_prompt(experience: dict) -> str:
    parts = []

    neighbors = experience.get("l1_neighbors", [])
    if neighbors:
        parts.append("## Prior successful workflows on similar tasks:")
        for n in neighbors[:3]:
            best = n.get("best_runs", [{}])[0]
            skel = n.get("section_skeleton", [])
            parts.append(f"\nTask {n['task_id']} (composite={best.get('composite_v2', 0):.3f}, "
                         f"cite={best.get('citation_count', 0)}):")
            if skel:
                parts.append(f"  Sections: {' → '.join(skel[:10])}")
            pats = n.get("cited_url_patterns", {})
            if pats:
                for domain, urls in pats.items():
                    if urls:
                        parts.append(f"  {domain} examples: {urls[0]}")

    l2 = experience.get("l2_intent_shape", {})
    if l2:
        parts.append(f"\n## Intent type '{l2.get('intent_type', '')}' characteristics:")
        parts.append(f"  Avg citations: {l2.get('avg_citation_count', 0):.0f}")
        parts.append(f"  Section count avg: {l2.get('section_count_avg', 0):.0f}")
        dist = l2.get("citation_distribution", {})
        if dist:
            parts.append(f"  Citation distribution: {dist}")

    l3 = experience.get("l3_globals", {})
    if l3:
        parts.append("\n## GLOBAL RULES:")
        sandbox = l3.get("sandbox_url_patterns", {})
        for domain, pattern in sandbox.items():
            parts.append(f"  {domain}: {pattern}")
        parts.append("  ONLY cite URLs matching these patterns. Do NOT fabricate URLs.")

    return "\n".join(parts)


def _synthesize_workflow(intent: str, subgoals: list[dict], experience: str,
                         model: str, base_url: str) -> list[dict]:
    subgoal_text = "\n".join(
        f"  ({sg['label']}) {sg['title']}: {sg['body'][:200]}..."
        for sg in subgoals
    )

    prompt = f"""You are a deep-research workflow planner. Given a research task and prior experience,
output a JSON array of search plans.

{experience}

## Current task subgoals:
{subgoal_text}

## Output format:
Return a JSON array. Each element:
{{
  "subgoal": "A",
  "search_queries": ["query1", "query2", ...],
  "target_domains": ["shopping", "reddit", "wiki"],
  "min_urls_to_cite": 15,
  "section_title": "Product Landscape"
}}

Generate 8-15 search queries per subgoal. For shopping queries, use product keywords.
For reddit queries, use topic + opinion keywords. For wiki queries, use technical term keywords.
Make queries specific enough to find relevant sandbox pages.

Return ONLY the JSON array, no markdown fences."""

    raw = _llm_call(
        [{"role": "user", "content": prompt}],
        base_url=base_url,
        model=model,
        max_tokens=3000,
        temperature=0.2,
    )

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        plan = json.loads(raw)
        if isinstance(plan, list):
            return plan
    except json.JSONDecodeError:
        pass

    return [
        {"subgoal": sg["label"], "search_queries": [sg["body"][:100]],
         "target_domains": ["shopping", "reddit", "wiki"],
         "min_urls_to_cite": 15, "section_title": sg["title"]}
        for sg in subgoals
    ]


def _execute_subgoal(plan_step: dict, all_found: dict[str, dict],
                     shim_url: str) -> dict[str, Any]:
    queries = plan_step.get("search_queries", [])
    section_title = plan_step.get("section_title", "Section")
    results: list[dict] = []

    for q in queries:
        hits = _search(q, shim_url, max_results=8)
        for h in hits:
            url = h.get("url", "")
            if url and url not in all_found:
                domain = "unknown"
                if ":7770" in url:
                    domain = "shopping"
                elif ":9999" in url:
                    domain = "reddit"
                elif ":8090" in url:
                    domain = "wiki"
                all_found[url] = {
                    "url": url,
                    "title": h.get("title", ""),
                    "snippet": h.get("content", "")[:300],
                    "domain": domain,
                    "query": q,
                }
                results.append(all_found[url])

    return {
        "section_title": section_title,
        "subgoal": plan_step.get("subgoal", ""),
        "n_urls_found": len(results),
        "results": results,
    }


_DOMAIN_ORDER = ("shopping", "reddit", "wiki", "unknown")


def _select_pages_for_fetch(subgoal_results: list[dict],
                            pages_per_subgoal: int = PAGES_PER_SUBGOAL) -> list[str]:
    """Deterministic pick of the top URLs to fetch full text for: up to
    ``pages_per_subgoal`` per subgoal, iterating domains in a fixed order and
    preserving discovery order within a domain. Deduped across subgoals."""
    selected: list[str] = []
    seen: set[str] = set()
    for sg in subgoal_results:
        by_domain: dict[str, list[dict]] = {d: [] for d in _DOMAIN_ORDER}
        for r in sg.get("results", []):
            by_domain.setdefault(r.get("domain", "unknown"), []).append(r)
        picked = 0
        for domain in _DOMAIN_ORDER:
            for r in by_domain.get(domain, []):
                if picked >= pages_per_subgoal:
                    break
                url = r.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    selected.append(url)
                    picked += 1
            if picked >= pages_per_subgoal:
                break
    return selected


def _fetch_evidence_pages(subgoal_results: list[dict], shim_url: str, fetch_fn,
                          per_page_chars: int = PER_PAGE_CHARS,
                          total_cap: int = EVIDENCE_BUDGET) -> dict[str, str]:
    """Fetch full page text for the selected URLs, bounded: per-page char cap
    and a hard total-chars cap (the shared evidence budget). Any fetch that
    fails or returns empty is simply skipped, so the writer degrades to the
    search snippet for that URL."""
    fetched: dict[str, str] = {}
    used = 0
    for url in _select_pages_for_fetch(subgoal_results):
        if used >= total_cap:
            break
        try:
            text = fetch_fn(url, shim_url, per_page_chars)
        except Exception:
            text = ""
        if text:
            text = text[:per_page_chars]
            fetched[url] = text
            used += len(text)
    return fetched


def _build_evidence_text(subgoal_results: list[dict], fetched: dict[str, str],
                         budget: int = EVIDENCE_BUDGET,
                         per_page_chars: int = PER_PAGE_CHARS) -> str:
    """Assemble the evidence block for the writer prompt. URLs with fetched
    full text get up to ``per_page_chars`` of body; the rest fall back to the
    300-char search snippet. Construction stops at the hard ``budget`` so the
    writer context stays within the 25000-char evidence budget."""
    parts: list[str] = []
    used = 0

    def _append(chunk: str) -> bool:
        nonlocal used
        if used + len(chunk) > budget:
            return False
        parts.append(chunk)
        used += len(chunk)
        return True

    for sg_result in subgoal_results:
        section = sg_result["section_title"]
        urls_by_domain: dict[str, list[dict]] = {d: [] for d in _DOMAIN_ORDER}
        for r in sg_result["results"]:
            urls_by_domain.setdefault(r.get("domain", "unknown"), []).append(r)

        if not _append(f"\n### {section}"):
            break
        for domain in ["shopping", "reddit", "wiki"]:
            items = urls_by_domain[domain]
            if not items:
                continue
            if not _append(f"\n**{domain.title()} sources ({len(items)}):**"):
                return "\n".join(parts)
            for item in items[:30]:
                url = item.get("url", "")
                full = fetched.get(url)
                if full:
                    line = f"- [{item['title'][:80]}]({url}):\n  {full[:per_page_chars]}"
                else:
                    line = f"- [{item['title'][:80]}]({url}): {item['snippet'][:150]}"
                if not _append(line):
                    parts.append("\n... (evidence truncated at budget)")
                    return "\n".join(parts)
    return "\n".join(parts)


def _write_report(intent: str, subgoal_results: list[dict], all_found: dict[str, dict],
                   model: str, base_url: str, shim_url: str, fetch_fn=None) -> str:
    fetch_fn = fetch_fn or _fetch_page
    fetched = _fetch_evidence_pages(subgoal_results, shim_url, fetch_fn)
    print(f"  [fs] Page-fetch: enriched {len(fetched)} URLs with full text")

    evidence_text = _build_evidence_text(subgoal_results, fetched)

    total_urls = len(all_found)
    domain_counts = {"shopping": 0, "reddit": 0, "wiki": 0}
    for info in all_found.values():
        d = info.get("domain", "")
        if d in domain_counts:
            domain_counts[d] += 1

    prompt = f"""You are a deep-research report writer. Write a comprehensive markdown report
based on the evidence below.

## Task:
{intent[:3000]}

## Evidence collected ({total_urls} unique URLs):
Domain breakdown: shopping={domain_counts['shopping']}, reddit={domain_counts['reddit']}, wiki={domain_counts['wiki']}

{evidence_text}

## CRITICAL RULES:
1. Every factual claim MUST be a markdown link `[label](url)` to a specific source URL from the evidence above.
2. Cite AT LEAST 80 distinct URLs as markdown links in the report. Spread citations across ALL evidence domains.
3. Cover ALL domains: shopping (product data), reddit (community sentiment), wiki (technical grounding).
4. Write 4000-7000 words with at least 30 paragraphs. This is a COMPREHENSIVE report — be thorough and detailed.
5. Start directly with the report content — no chain-of-thought or preamble.
6. Do NOT fabricate URLs — only use URLs from the evidence above.
7. Include cross-source synthesis as required by the task: contradictions, sentiment rankings, divergences, etc.
8. Structure the report with clear markdown headings matching the task sections (A, B, C, D).
9. For each product/thread/article, include ALL available metadata (price, rating, score, comment count, etc.).
10. In synthesis sections, provide specific evidence chains: product URL + reddit URL + wiki URL per claim.

Write the complete report now. Be comprehensive and thorough — cite as many sources as possible."""

    report = _llm_call(
        [{"role": "user", "content": prompt}],
        base_url=base_url,
        model=model,
        max_tokens=8192,
        temperature=0.3,
    )

    if report and report.strip():
        # Weak-but-real writer output is returned VERBATIM, even when it is
        # short or under any citation threshold: capture must not judge
        # quality, the scorer does. Only genuinely empty writer output falls
        # through to the honest write-phase error stub below.
        return report

    # Defect 2: no laundered sentinel. When the LLM writer fails, a benchmark
    # run must surface an honest error stub, NOT a harness-assembled evidence
    # dump written on flowsearcher's behalf (that is the same fairness violation
    # the shared evidence writer commits). The evidence-grounded fallback
    # survives only under the explicit non-benchmark EVIDENCE_FALLBACK_ENABLE
    # flag; otherwise we fall straight through to the honest error stub below.
    if fallback_enabled():
        fallback = _write_evidence_fallback_report(intent, subgoal_results, all_found)
        if fallback:
            return fallback
    if not all_found:
        return _error_stub(
            "write", "LLM writer returned empty and no sandbox evidence was collected")
    return _error_stub("write", "LLM writer returned empty after retries")


def _write_evidence_fallback_report(
    intent: str,
    subgoal_results: list[dict],
    all_found: dict[str, dict],
) -> str:
    if not all_found:
        return ""

    domain_counts = {"shopping": 0, "reddit": 0, "wiki": 0, "unknown": 0}
    for info in all_found.values():
        domain_counts[info.get("domain", "unknown")] = domain_counts.get(info.get("domain", "unknown"), 0) + 1

    lines = [
        "# FlowSearcher-DS Evidence Report",
        "",
        "This report organizes the collected sandbox evidence into a source-grounded answer with citations.",
        "",
        "## Task",
        "",
        intent.strip()[:3000],
        "",
        "## Evidence Coverage",
        "",
        f"- Total unique URLs: {len(all_found)}",
        f"- Shopping sources: {domain_counts.get('shopping', 0)}",
        f"- Reddit sources: {domain_counts.get('reddit', 0)}",
        f"- Wiki sources: {domain_counts.get('wiki', 0)}",
        "",
    ]

    for sg_result in subgoal_results:
        title = sg_result.get("section_title") or sg_result.get("subgoal") or "Research Section"
        results = sg_result.get("results", [])
        if not results:
            continue
        lines.extend([f"## {title}", ""])
        for item in results[:80]:
            snippet = item.get("snippet", "").strip()
            if len(snippet) > 260:
                snippet = snippet[:260].rsplit(" ", 1)[0] + "..."
            lines.append(
                f"- [{item.get('title', 'source')}]({item.get('url', '')}) "
                f"({item.get('domain', 'unknown')}; query: `{item.get('query', '')}`): {snippet}"
            )
        lines.append("")

    lines.extend(["## Source Inventory", ""])
    for url, info in list(all_found.items())[:160]:
        lines.append(f"- [{info.get('title', url)}]({url})")
    return "\n".join(lines)


async def run_flowsearcher(intent: str, model: str = "deepseek-v4-flash",
                           task_id: str = "", shim_url: str | None = None,
                           proxy_url: str | None = None) -> str:
    # Defect 1: resolve both endpoints at call time with clear precedence so a
    # stale module constant can never route this lane to a different backbone
    # than the harness intends.
    base_url = _resolve_llm_base_url(proxy_url)
    shim = _resolve_shim_url(shim_url)
    print(f"  [fs] FlowSearcher-DS starting, intent={len(intent)} chars; "
          f"llm={base_url}, shim={shim}")

    # Defect 2: track the current phase so a total failure surfaces an honest
    # error stub naming where it broke, instead of a laundered sentinel.
    phase = "decompose"
    try:
        # Stage 1: decompose
        subgoals = decompose_intent(intent)
        print(f"  [fs] Decomposed into {len(subgoals)} subgoals: "
              + ", ".join(sg["label"] for sg in subgoals))

        # Stage 2: memory retrieval. Fairness audit 2026-07-06 (B2): the memory
        # is mined from PRIOR SCORED RUNS ON THE SAME EVAL SET (cited URLs and
        # section skeletons of high-composite neighbors), which no other lane
        # receives; injecting it into benchmark runs is cross-task seed
        # injection. Default OFF for benchmark runs; set FLOWSEARCHER_MEMORY=1
        # only for explicitly non-benchmark experiments.
        phase = "memory"
        if os.environ.get("FLOWSEARCHER_MEMORY", "0") == "1":
            try:
                mem = HierarchicalMemory.load()
                experience = mem.retrieve(intent, task_id=task_id, top_k=3)
                exp_prompt = _build_experience_prompt(experience)
                n_l1 = len(experience.get("l1_neighbors", []))
                print(f"  [fs] Memory loaded: {n_l1} L1 neighbors, L2={bool(experience.get('l2_intent_shape'))}")
            except Exception as e:
                print(f"  [fs] Memory load failed ({e}), proceeding without memory")
                exp_prompt = ""
                experience = {}
        else:
            print("  [fs] Memory injection disabled (benchmark fairness default)")
            exp_prompt = ""
            experience = {}

        # Stage 3: workflow synthesis
        phase = "synthesize"
        print("  [fs] Synthesizing workflow...")
        plan = _synthesize_workflow(intent, subgoals, exp_prompt, model, base_url)
        total_queries = sum(len(step.get("search_queries", [])) for step in plan)
        print(f"  [fs] Plan: {len(plan)} steps, {total_queries} total queries")

        # Stage 4: execute
        phase = "search"
        all_found: dict[str, dict] = {}
        subgoal_results = []
        for step in plan:
            sg_result = _execute_subgoal(step, all_found, shim)
            subgoal_results.append(sg_result)
            print(f"  [fs] Subgoal {step.get('subgoal', '?')}: found {sg_result['n_urls_found']} new URLs "
                  f"(total={len(all_found)})")

        print(f"  [fs] Total unique URLs found: {len(all_found)}")

        # If under target, do supplementary searches
        domain_counts = {"shopping": 0, "reddit": 0, "wiki": 0}
        for info in all_found.values():
            d = info.get("domain", "")
            if d in domain_counts:
                domain_counts[d] += 1

        targets = {"shopping": 40, "reddit": 30, "wiki": 25}
        for domain, target in targets.items():
            if domain_counts[domain] < target:
                deficit = target - domain_counts[domain]
                print(f"  [fs] Supplementary search: {domain} needs {deficit} more URLs")
                kw = _extract_keywords(intent, domain)
                for q in kw[:8]:
                    hits = _search(q, shim, max_results=10)
                    for h in hits:
                        url = h.get("url", "")
                        if url and url not in all_found:
                            d = "unknown"
                            if ":7770" in url:
                                d = "shopping"
                            elif ":9999" in url:
                                d = "reddit"
                            elif ":8090" in url:
                                d = "wiki"
                            if d == domain:
                                all_found[url] = {
                                    "url": url, "title": h.get("title", ""),
                                    "snippet": h.get("content", "")[:300],
                                    "domain": d, "query": q,
                                }
                                subgoal_results[-1]["results"].append(all_found[url])

        # Recount after supplementary
        domain_counts = {"shopping": 0, "reddit": 0, "wiki": 0}
        for info in all_found.values():
            d = info.get("domain", "")
            if d in domain_counts:
                domain_counts[d] += 1
        print(f"  [fs] After supplementary: shop={domain_counts['shopping']}, "
              f"reddit={domain_counts['reddit']}, wiki={domain_counts['wiki']}, "
              f"total={len(all_found)}")

        # Stage 5: write report
        phase = "write"
        print("  [fs] Writing report...")
        report = _write_report(intent, subgoal_results, all_found, model,
                               base_url, shim)
        print(f"  [fs] Report: {len(report)} chars")
    except Exception as e:
        return _error_stub(phase, f"{type(e).__name__}: {e}")

    if not report or not report.strip():
        return _error_stub(phase, "empty report produced")
    return report


def _extract_keywords(intent: str, domain: str) -> list[str]:
    words = re.findall(r"[A-Za-z][\w'-]+", intent[:1000])
    stops = {"the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "is",
             "are", "with", "from", "by", "at", "be", "as", "that", "this", "it",
             "not", "do", "does", "must", "should", "each", "every", "all", "any",
             "produce", "report", "comprehensive", "spanning", "three", "dimensions"}
    kw = [w for w in words if w.lower() not in stops and len(w) > 2]
    seen: set[str] = set()
    unique = []
    for w in kw:
        if w.lower() not in seen:
            seen.add(w.lower())
            unique.append(w)

    queries = []
    if domain == "shopping":
        for w in unique[:12]:
            queries.append(w)
    elif domain == "reddit":
        for w in unique[:8]:
            queries.append(f"{w} discussion opinion")
    elif domain == "wiki":
        for w in unique[:10]:
            queries.append(f"{w} wikipedia")
    return queries


if __name__ == "__main__":
    import asyncio
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--model", default="deepseek-v4-flash")
    args = ap.parse_args()

    task_dir = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
    task_cfg = json.loads((task_dir / f"{args.task}.json").read_text())
    intent = task_cfg["intent"]
    for k, v in {"__SHOPPING__": "http://localhost:7770",
                 "__REDDIT__": "http://localhost:9999",
                 "__WIKIPEDIA__": "http://localhost:8090"}.items():
        intent = intent.replace(k, v)

    report = asyncio.run(run_flowsearcher(intent, args.model, task_id=args.task))
    out_path = ROOT / "data" / "results" / "deep" / f"flowsearcher-ds__{args.task}_smoke.md"
    out_path.write_text(report)
    print(f"\n[fs] Saved to {out_path}")
