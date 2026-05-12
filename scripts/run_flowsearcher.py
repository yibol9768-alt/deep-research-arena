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


SHIM_URL = os.environ.get("SHIM_URL", "http://localhost:8081")
DS_PROXY = os.environ.get("DS_PROXY_URL", "http://localhost:8088/v1")
DS_KEY = os.environ.get("OPENAI_API_KEY", "anything")


def _search(query: str, max_results: int = 10) -> list[dict]:
    try:
        r = requests.post(
            f"{SHIM_URL}/search",
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


def _fetch_page(url: str, max_chars: int = 8000) -> str:
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        text = r.text[:max_chars]
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


def _llm_call(messages: list[dict], model: str = "deepseek-v4-flash",
              max_tokens: int = 4096, temperature: float = 0.3) -> str:
    try:
        r = requests.post(
            f"{DS_PROXY}/chat/completions",
            headers={
                "Authorization": f"Bearer {DS_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [fs] LLM error: {e}")
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
                         model: str) -> list[dict]:
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


def _execute_subgoal(plan_step: dict, all_found: dict[str, dict]) -> dict[str, Any]:
    queries = plan_step.get("search_queries", [])
    section_title = plan_step.get("section_title", "Section")
    results: list[dict] = []

    for q in queries:
        hits = _search(q, max_results=8)
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


def _write_report(intent: str, subgoal_results: list[dict], all_found: dict[str, dict],
                   model: str) -> str:
    evidence_parts = []
    for sg_result in subgoal_results:
        section = sg_result["section_title"]
        urls_by_domain: dict[str, list[dict]] = {"shopping": [], "reddit": [], "wiki": [], "unknown": []}
        for r in sg_result["results"]:
            urls_by_domain[r["domain"]].append(r)

        evidence_parts.append(f"\n### {section}")
        for domain in ["shopping", "reddit", "wiki"]:
            items = urls_by_domain[domain]
            if items:
                evidence_parts.append(f"\n**{domain.title()} sources ({len(items)}):**")
                for item in items[:30]:
                    evidence_parts.append(f"- [{item['title'][:80]}]({item['url']}): {item['snippet'][:150]}")

    evidence_text = "\n".join(evidence_parts)
    if len(evidence_text) > 25000:
        evidence_text = evidence_text[:25000] + "\n... (truncated)"

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
        model=model,
        max_tokens=8192,
        temperature=0.3,
    )

    return report or "(empty flowsearcher report)"


async def run_flowsearcher(intent: str, model: str = "deepseek-v4-flash",
                           task_id: str = "") -> str:
    print(f"  [fs] FlowSearcher-DS starting, intent={len(intent)} chars")

    # Stage 1: decompose
    subgoals = decompose_intent(intent)
    print(f"  [fs] Decomposed into {len(subgoals)} subgoals: "
          + ", ".join(sg["label"] for sg in subgoals))

    # Stage 2: memory retrieval
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

    # Stage 3: workflow synthesis
    print("  [fs] Synthesizing workflow...")
    plan = _synthesize_workflow(intent, subgoals, exp_prompt, model)
    total_queries = sum(len(step.get("search_queries", [])) for step in plan)
    print(f"  [fs] Plan: {len(plan)} steps, {total_queries} total queries")

    # Stage 4: execute
    all_found: dict[str, dict] = {}
    subgoal_results = []
    for step in plan:
        sg_result = _execute_subgoal(step, all_found)
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
                hits = _search(q, max_results=10)
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
    print("  [fs] Writing report...")
    report = _write_report(intent, subgoal_results, all_found, model)
    print(f"  [fs] Report: {len(report)} chars")

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
