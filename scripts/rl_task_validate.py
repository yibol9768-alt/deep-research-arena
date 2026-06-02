#!/usr/bin/env python3
"""Offline validator for authored AgentRL training tasks.

Loads an RL task JSON EXACTLY as the GRPO pilot pipeline does
(``scripts/train_grpo_pilot.py``), then drives the SAME reward path the
trainer uses (``ArenaEvaluator(task_id, mode="fast"); ev._task_config = cfg;
ev._rl_strict = True`` with default WEIGHTS_RL).

Given the loaded task it parametrically synthesises five graded rollouts
tailored to THIS task's golden-seed URLs / domains / checklist keywords /
markdown_spec thresholds, scores each through ``evaluate_rollout`` in fast
mode, and emits a PASS/FAIL readiness verdict on:

  * headroom        competent composite >= 0.45
  * gradient        competent > mediocre > shallow, each gap >= 0.04
  * balance_bites   one_sided composite < competent
  * no_perverse     fabricated == 0.0 (nullified) AND shallow > 0.0
  * variance        population std of the 5 composites > 0.05
  * feasible        every numeric threshold fits an 8-tool-call budget

Exit 0 if READY (all checks pass), else 1.

Usage:
    python3 scripts/rl_task_validate.py <path-to-task.json> [--json]

No sandbox / GPU / network / LLM needed: fast mode is fully deterministic.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.dont_write_bytecode = True

from src.eval.evaluator import ArenaEvaluator
from src.eval.rollout import Rollout
from src.verifiers.citation_format import canonicalize_url


logging.getLogger("src.eval.evaluator").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Loader — replicate scripts/train_grpo_pilot.py:main() task-load semantics.
# ---------------------------------------------------------------------------

_ALIAS_TO_HOST = {
    "__SHOPPING__": "localhost:7770",
    "__REDDIT__": "localhost:9999",
    "__WIKIPEDIA__": "localhost:8090",
}
_HOST_TO_ALIAS = {v: k for k, v in _ALIAS_TO_HOST.items()}


def _prompt_from_task(task_config: dict[str, Any]) -> str:
    """Verbatim copy of train_grpo_pilot._prompt_from_task."""
    prompt = str(
        task_config.get("prompt")
        or task_config.get("intent")
        or task_config.get("question")
        or ""
    )
    substitutions = {
        "__SHOPPING__": os.environ.get("SHOPPING", "http://localhost:7770"),
        "__REDDIT__": os.environ.get("REDDIT", "http://localhost:9999"),
        "__WIKIPEDIA__": os.environ.get("WIKIPEDIA", "http://localhost:8090"),
    }
    for needle, replacement in substitutions.items():
        prompt = prompt.replace(needle, replacement)
    lang = str(task_config.get("language", "en") or "en").lower()
    if lang == "zh":
        return prompt + "\n\n请用中文撰写完整的研究报告。"
    if lang == "bilingual":
        return (
            prompt
            + "\n\nProvide the full research report in BOTH English and Chinese "
            "(中英双语,两种语言都要完整)."
        )
    return prompt


def load_task(task_file: Path, max_tool_calls: int = 8) -> dict[str, Any]:
    """Load task JSON exactly as the RL pipeline does (dict used directly)."""
    task_config = json.loads(task_file.read_text(encoding="utf-8"))
    task_config.setdefault("task_id", task_config.get("id") or task_file.stem)
    task_config["prompt"] = _prompt_from_task(task_config)
    task_config["max_tool_calls"] = int(max_tool_calls)
    return task_config


# ---------------------------------------------------------------------------
# Golden-seed resolution.
# ---------------------------------------------------------------------------

def _resolve_golden_path(task_config: dict[str, Any]) -> Path | None:
    cov = task_config.get("url_coverage") or {}
    raw = cov.get("golden_pool_path")
    if not raw:
        return None
    p = Path(str(raw))
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def _host_for_alias(task_config: dict[str, Any], alias: str) -> str:
    aliases = task_config.get("domain_aliases") or {}
    hosts = aliases.get(alias)
    if hosts:
        return str(hosts[0])
    return _ALIAS_TO_HOST.get(alias, "localhost:8090")


def _synth_seed_url(host: str, alias: str, idx: int) -> str:
    """Construct a plausible sandbox URL for a domain when no golden file
    exists. Real golden files MUST be committed for live training; this is a
    last-resort so the validator can still exercise the reward path offline.
    """
    if "8090" in host:  # wikipedia / kiwix
        slug = ["Headphones", "Active_noise_control", "Lithium-ion_battery",
                "Bluetooth", "Sound"][idx % 5]
        return f"http://{host}/content/wikipedia_en_all_nopic/A/{slug}"
    if "9999" in host:  # reddit / postmill
        forum = ["audio", "headphones", "gadgets", "technology", "buyitforlife"][idx % 5]
        return f"http://{host}/f/{forum}/comments/thread-{idx}"
    if "7770" in host:  # shopping / magento
        slug = ["alpha-pro", "beta-max", "gamma-elite", "delta-travel", "epsilon-anc"][idx % 5]
        return f"http://{host}/{slug}.html"
    return f"http://{host}/page-{idx}"


@dataclass
class GoldenSeeds:
    must_cite: list[str]          # raw URLs from the golden file (or synthesised)
    by_alias: dict[str, list[str]]  # alias -> [raw URLs], grouped by sandbox host
    used_aliases: list[str]       # aliases that have >=1 seed, in policy order
    golden_path: Path             # path written/used for url_coverage
    synthesised: bool             # True if we fabricated a temp golden file


def resolve_seeds(task_config: dict[str, Any], tmp_dir: Path) -> GoldenSeeds:
    """Prefer the committed golden file; else synthesise one from the task's
    declared domains so coverage scores offline.
    """
    cov = task_config.get("url_coverage") or {}
    policy = task_config.get("citation_policy") or {}
    must_domains: list[str] = list(policy.get("must_be_in_domain") or [])
    # Fall back to whichever aliases appear in per_domain_minimum / sandbox_hosts.
    if not must_domains:
        pdm = (policy.get("per_domain_minimum") or {})
        must_domains = [a for a in pdm if a in _ALIAS_TO_HOST]
    if not must_domains:
        must_domains = ["__WIKIPEDIA__", "__REDDIT__"]

    golden_path = _resolve_golden_path(task_config)
    must_cite: list[str] = []
    synthesised = False

    if golden_path and golden_path.exists():
        data = json.loads(golden_path.read_text(encoding="utf-8"))
        must_cite = [str(e["url"]) for e in (data.get("must_cite_urls") or []) if e.get("url")]
        used_golden_path = golden_path

    if not must_cite:
        # Synthesise one seed URL per declared domain (>=2 entries per domain so
        # per_domain_minimum can be satisfied), write a temp golden file.
        synthesised = True
        per_dom_min = (cov.get("per_domain_minimum") or policy.get("per_domain_minimum") or {})
        for alias in must_domains:
            host = _host_for_alias(task_config, alias)
            # how many seeds this domain needs (at least 2 for headroom)
            need = 2
            for key in (alias, _alias_canon(alias)):
                if key in per_dom_min:
                    try:
                        need = max(need, int(per_dom_min[key]))
                    except (TypeError, ValueError):
                        pass
            for i in range(need):
                must_cite.append(_synth_seed_url(host, alias, i))
        used_golden_path = tmp_dir / "synth_golden.json"
        used_golden_path.write_text(
            json.dumps(
                {
                    "must_cite_urls": [{"url": u, "weight": 1.0} for u in must_cite],
                    "expected_pool_urls": [{"url": u} for u in must_cite],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        # Point the in-memory config at the temp golden so URLCoverageVerifier
        # finds it (the on-disk JSON is unchanged).
        task_config.setdefault("url_coverage", {})
        task_config["url_coverage"]["golden_pool_path"] = str(used_golden_path)

    # Group seeds by alias (sandbox host).
    by_alias: dict[str, list[str]] = {}
    for u in must_cite:
        alias = _classify_alias(u)
        if alias is None:
            continue
        by_alias.setdefault(alias, []).append(u)
    used_aliases = [a for a in must_domains if a in by_alias] or list(by_alias.keys())

    return GoldenSeeds(
        must_cite=must_cite,
        by_alias=by_alias,
        used_aliases=used_aliases,
        golden_path=used_golden_path,
        synthesised=synthesised,
    )


def _alias_canon(alias: str) -> str:
    return {"__SHOPPING__": "shopping", "__REDDIT__": "reddit", "__WIKIPEDIA__": "wiki"}.get(alias, alias)


def _classify_alias(url: str) -> str | None:
    low = url.lower()
    for host, alias in _HOST_TO_ALIAS.items():
        if host in low:
            return alias
    return None


# ---------------------------------------------------------------------------
# Checklist keyword extraction (used to thread keywords into competent report).
# ---------------------------------------------------------------------------

def _checklist_keywords(task_config: dict[str, Any]) -> list[str]:
    """Best-effort keyword list to weave into the competent report so that a
    full-mode rubric (if later enabled) and the longform density both bite.
    Reads inline checklist items if present; otherwise harvests salient words
    from the intent. Fast mode ignores the rubric, so this is purely cosmetic
    for the deterministic spine, but keeps the synthetic report on-topic.
    """
    words: list[str] = []
    raw_items = task_config.get("checklist") or task_config.get("checklist_items") or []
    for raw in raw_items:
        txt = raw.get("criterion") if isinstance(raw, dict) else str(raw)
        if txt:
            words.extend(w for w in str(txt).split() if len(w) > 3)
    if not words:
        intent = str(task_config.get("intent") or task_config.get("question") or "")
        # strip alias tokens
        for a in _ALIAS_TO_HOST:
            intent = intent.replace(a, " ")
        words = [w.strip(".,;:()[]") for w in intent.split() if len(w) > 4][:12]
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        k = w.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(w)
    return out[:12]


def _entities(task_config: dict[str, Any]) -> list[str]:
    pb = task_config.get("perspective_balance") or {}
    ents = pb.get("evaluated_entities") or task_config.get("evaluated_entities") or []
    return [str(e) for e in ents if str(e).strip()]


# ---------------------------------------------------------------------------
# Report synthesis.
# ---------------------------------------------------------------------------

def _md_link(label: str, url: str) -> str:
    return f"[{label}]({url})"


def _filler_sentence(idx: int, zh: bool) -> str:
    if zh:
        # Interleave a short English clause: the deterministic perspective /
        # longform guards count whitespace-separated Latin tokens, and a zh
        # report grounds on the English sandbox corpus, so carrying some
        # English in the body is on-spec and clears the >=50-token guard.
        return (
            f"补充说明第{idx}句进一步阐述了背景、权衡与不同人群的适配情况以确保篇幅与论证密度;"
            f" supporting note {idx} cross-checks the evidence and reconciles "
            "conflicting source claims."
        )
    return (
        f"Supporting analysis sentence {idx} elaborates the tradeoffs, buyer "
        "segments, and evidence reconciliation so the section reads as a "
        "developed argument rather than a list."
    )


def _pad_to(text_parts: list[str], target_words: int, zh: bool) -> list[str]:
    """Append developed filler sentences until the body reaches ~target words."""
    def wc(parts: list[str]) -> int:
        joined = " ".join(parts)
        if zh:
            return sum(1 for ch in joined if "一" <= ch <= "鿿") + len(
                [t for t in joined.split() if any(c.isalnum() for c in t)]
            )
        return len([t for t in joined.split() if any(c.isalnum() for c in t)])

    idx = 1
    guard = 0
    while wc(text_parts) < target_words and guard < 400:
        text_parts.append(_filler_sentence(idx, zh))
        idx += 1
        guard += 1
    return text_parts


def _make_report(
    *,
    seeds: GoldenSeeds,
    keywords: list[str],
    entity: str | None,
    target_words: int,
    style: str,
    zh: bool,
) -> tuple[str, list[str]]:
    """Return (report_md, cited_urls) for one graded variant.

    style in {competent, mediocre, shallow, one_sided, fabricated}.
    """
    all_seeds = list(seeds.must_cite)
    alias_order = seeds.used_aliases or list(seeds.by_alias.keys())

    def one_per_domain(domains: list[str]) -> list[str]:
        """One seed URL from each named domain, in order."""
        out: list[str] = []
        for alias in domains:
            urls = seeds.by_alias.get(alias, [])
            if urls:
                out.append(urls[0])
        return out

    def single_domain(n: int) -> list[str]:
        """Up to n seed URLs all from the FIRST domain (collapses diversity)."""
        if not alias_order:
            return all_seeds[:n]
        urls = list(seeds.by_alias.get(alias_order[0], []))
        if len(urls) < n:
            urls = urls + [u for u in all_seeds if u not in urls]
        return urls[:n]

    ent = entity or ("该推荐项" if zh else "the recommended option")
    kw = ", ".join(keywords[:6]) if keywords else ("关键因素" if zh else "key factors")

    # Sentence builders that keep the entity ADJACENT to one pro and one con so
    # the deterministic perspective Tier-A window (+/-100 chars) captures both
    # with a balanced pos:neg ratio (<=5:1) — required for pb to score 1.0.
    # The deterministic perspective Tier-A lexicon is ENGLISH-ONLY, so even a
    # zh report must keep a few English sentiment anchors next to the entity
    # for the dimension to register pros/cons. This is realistic: the sandbox
    # WIKIPEDIA corpus is English, so a zh report grounds on English sources
    # and naturally carries English evaluative terms near product names.
    def pro_sentence(url: str | None) -> str:
        link = (" " + _md_link("strength", url)) if url else ""
        if zh:
            return (
                f"在评测来源中,{ent} 被认为可靠且舒适,音质均衡 "
                f"(reliable, comfortable, balanced)。{link}"
            )
        return f"Across sources, {ent} is reliable and comfortable with balanced sound.{link}"

    def con_sentence(url: str | None) -> str:
        link = (" " + _md_link("limitation", url)) if url else ""
        if zh:
            return (
                f"但 {ent} 也有明显缺点:价格偏高、长时间使用发热,维修支持存在问题 "
                f"(overpriced, runs hot, a repair problem)。{link}"
            )
        return (
            f"However, {ent} has drawbacks: it is overpriced, runs hot in long "
            f"sessions, and has a real repair-support problem.{link}"
        )

    head_map = {
        "competent": "# 研究报告" if zh else "# Research Report",
        "mediocre": "# 研究简报" if zh else "# Research Brief",
        "shallow": "# 浅层报告" if zh else "# Shallow Note",
        "one_sided": "# 一边倒推荐" if zh else "# One-Sided Recommendation",
        "fabricated": "# 伪造证据报告" if zh else "# Report (fabricated)",
    }
    head = head_map[style]

    # ---- fabricated: cite real seeds, but caller leaves fetched_urls empty ----
    if style == "fabricated":
        cited = one_per_domain(alias_order) or all_seeds[:3]
        links = " ".join(_md_link(f"source {i+1}", u) for i, u in enumerate(cited))
        body = pro_sentence(None) + " " + con_sentence(None) + " " + links
        parts = [head, f"## {'结论' if zh else 'Conclusion'}\n{body}"]
        parts = _pad_to(parts, target_words, zh)
        return "\n\n".join(parts), cited

    # ---- shallow: single domain, thin, missing keywords, ONE-SIDED-ish ----
    if style == "shallow":
        cited = single_domain(3)
        kw_short = ", ".join(keywords[:1]) if keywords else ("要点" if zh else "a basic point")
        link_lines = " ".join(_md_link("source", u) for u in cited)
        # Mention only a pro near the entity (no con) -> pb fails, but report
        # still grounded and short so composite stays > 0.
        body = (
            f"{ent} 涉及 {kw_short}。{ent} 看起来不错。{link_lines}" if zh
            else f"{ent} relates to {kw_short}. {ent} looks good. {link_lines}"
        )
        parts = [head, f"## {'要点' if zh else 'Points'}\n{body}"]
        parts = _pad_to(parts, max(60, int(target_words * 0.70)), zh)
        return "\n\n".join(parts), cited

    # ---- one_sided: full coverage + diversity, but NO cons near the entity ----
    if style == "one_sided":
        cited = one_per_domain(alias_order) or all_seeds[:3]
        praise = (
            f"{ent} 表现优秀、可靠、舒适、均衡且性价比突出,是几乎所有买家的最佳选择。"
            if zh else
            f"{ent} is excellent, reliable, comfortable, balanced, and great value; "
            f"it is the best and safest choice for almost every buyer."
        )
        endorse = (
            f"所有来源一致称赞 {ent},强烈推荐购买,毫无保留。"
            if zh else
            f"Every source praises {ent} without reservation and strongly recommends buying it."
        )
        links_a = " ".join(_md_link(f"praise {i+1}", u) for i, u in enumerate(cited))
        s1 = f"## {'推荐' if zh else 'Recommendation'}\n{praise} {links_a}"
        s2 = f"## {'支持证据' if zh else 'Supportive Evidence'}\n{endorse}"
        parts = [head, s1, s2]
        parts = _pad_to(parts, target_words, zh)
        return "\n\n".join(parts), cited

    # ---- competent & mediocre: structured, both pros AND cons ----
    if style == "competent":
        # All declared domains -> domain_balance = 1.0, high recall/diversity.
        cited = one_per_domain(alias_order) or all_seeds[:3]
    else:  # mediocre: drop the last domain -> domain_balance < 1, thinner.
        domains = alias_order[:-1] if len(alias_order) > 1 else alias_order
        cited = one_per_domain(domains) or all_seeds[:2]

    n = len(cited)
    summary_links = " ".join(_md_link(f"evidence {i+1}", u) for i, u in enumerate(cited))
    s1 = (
        f"## {'摘要' if zh else 'Executive Summary'}\n"
        + (f"本报告综合多源证据评估 {ent},涉及 {kw}。{summary_links}"
           if zh else
           f"This report weighs multi-source evidence on {ent}, covering {kw}. {summary_links}")
    )
    # Strengths section: entity + pro, with one link per cited seed split here.
    s2 = (
        f"## {'优点' if zh else 'Strengths'}\n"
        + pro_sentence(cited[0] if n > 0 else None)
    )
    # Limitations section: entity + con, with the remaining links.
    extra_con_links = " ".join(
        _md_link(f"limitation {i+1}", u) for i, u in enumerate(cited[1:])
    )
    s3 = (
        f"## {'缺点与权衡' if zh else 'Limitations and Tradeoffs'}\n"
        + con_sentence(None) + (" " + extra_con_links if extra_con_links else "")
    )
    closing = (
        f"## {'结论' if zh else 'Conclusion'}\n"
        + (f"综合优缺点,{ent} 适合重视上述因素的买家,但价格敏感者应谨慎权衡。"
           if zh else
           f"Taken together, {ent} suits buyers who value the factors above, while "
           "price-sensitive readers should weigh the downsides before committing.")
    )
    if style == "competent":
        parts = [head, s1, s2, s3, closing]
    else:  # mediocre: thinner, drop the dedicated closing synthesis
        parts = [head, s1, s2, s3]
    parts = _pad_to(parts, target_words if style == "competent" else int(target_words * 0.92), zh)
    return "\n\n".join(parts), cited


# ---------------------------------------------------------------------------
# Rollout construction (mirrors tier0_probe.build_rollout).
# ---------------------------------------------------------------------------

def _snippet_for(url: str, keywords: list[str], entity: str | None, zh: bool) -> str:
    ent = entity or "the option"
    kw = " ".join(keywords[:4])
    base = (
        f"页面内容讨论了 {ent},涉及 {kw},并同时给出正面评价与具体缺点(如价格、发热、维修)。"
        if zh else
        f"This fetched page discusses {ent} covering {kw}; it reports concrete "
        "strengths as well as specific limitations such as price, heat, and repair."
    )
    return base


def build_rollout(
    task_id: str,
    report_md: str,
    cited_urls: list[str],
    *,
    grounded: bool,
    keywords: list[str],
    entity: str | None,
    zh: bool,
    queries: list[str],
) -> Rollout:
    if grounded:
        fetched = list(cited_urls)
    else:
        fetched = []  # fabricated: no proof-of-fetch
    snippets = {
        canonicalize_url(u): _snippet_for(u, keywords, entity, zh)
        for u in fetched
    }
    tool_calls = [
        {"endpoint": "/search", "query": q, "n_results": max(1, min(6, len(fetched) or 1)), "ok": True}
        for q in queries
    ]
    return Rollout(
        task_id=task_id,
        report_md=report_md,
        retrieved_snippets=snippets,
        fetched_urls=fetched,
        tool_calls=tool_calls,
        step_count=len(tool_calls),
    )


# ---------------------------------------------------------------------------
# Evaluation.
# ---------------------------------------------------------------------------

_DIMS = (
    "coverage", "source_diversity", "longform_quality", "perspective_balance",
    "spec", "bilingual", "checklist", "depth", "rigor", "style",
)

VARIANTS = ("competent", "mediocre", "shallow", "one_sided", "fabricated")


@dataclass
class Row:
    variant: str
    composite: float
    per_dim: dict[str, float]
    nullify: bool


def evaluate_all(task_config: dict[str, Any], seeds: GoldenSeeds) -> list[Row]:
    task_id = str(task_config["task_id"])
    lang = str(task_config.get("language", "en") or "en").lower()
    zh = lang in {"zh", "bilingual"}
    spec = task_config.get("markdown_spec") or {}
    target_words = int(spec.get("target_words") or spec.get("min_words") or 350)
    keywords = _checklist_keywords(task_config)
    ents = _entities(task_config)
    entity = ents[0] if ents else None
    queries = [
        f"{(entity or 'topic')} evidence",
        f"{(entity or 'topic')} pros and cons",
        f"{(entity or 'topic')} reference context",
        f"{(entity or 'topic')} community reports",
    ]

    rows: list[Row] = []
    # Build a fresh evaluator per variant — exactly the trainer's factory.
    for variant in VARIANTS:
        report_md, cited = _make_report(
            seeds=seeds,
            keywords=keywords,
            entity=entity,
            target_words=target_words,
            style=variant,
            zh=zh,
        )
        grounded = variant != "fabricated"
        rollout = build_rollout(
            task_id, report_md, cited,
            grounded=grounded, keywords=keywords, entity=entity, zh=zh,
            queries=queries,
        )
        ev = ArenaEvaluator(task_id, mode="fast")
        ev._task_config = dict(task_config)
        ev._rl_strict = True
        result = ev.evaluate_rollout(rollout, rubric_snapshot={"rubric_match": 1.0})
        penalties = result.reward_terms.get("penalties", {})
        rows.append(Row(
            variant=variant,
            composite=float(result.composite),
            per_dim={d: float(result.per_dim.get(d, 0.0)) for d in _DIMS},
            nullify=bool(penalties.get("nullify")),
        ))
    return rows


# ---------------------------------------------------------------------------
# Checks.
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _budget_checks(task_config: dict[str, Any]) -> list[Check]:
    """Static feasibility of every numeric threshold vs an 8-tool-call budget:
    pages<=6, citations<=6, words<=900, recall<=0.5, per-domain mins sum<=6.
    """
    spec = task_config.get("markdown_spec") or {}
    cov = task_config.get("url_coverage") or {}
    policy = task_config.get("citation_policy") or {}
    checks: list[Check] = []

    def add(name: str, value: Any, ok: bool, limit: str) -> None:
        checks.append(Check(name, ok, f"{value} ({limit})"))

    min_words = int(spec.get("min_words", 0) or 0)
    add("min_words", min_words, min_words <= 900, "<=900")

    min_cit = int(spec.get("min_citations", 0) or 0)
    add("min_citations", min_cit, min_cit <= 6, "<=6")

    min_pages = int(spec.get("min_pages_browsed", 0) or 0)
    add("min_pages_browsed", min_pages, min_pages <= 6, "<=6")

    mub = int(cov.get("min_unique_urls_browsed", 0) or 0)
    add("min_unique_urls_browsed", mub, mub <= 6, "<=6")

    muc = int(cov.get("min_unique_urls_cited", 0) or 0)
    add("min_unique_urls_cited", muc, muc <= 6, "<=6")

    recall = float(cov.get("min_must_cite_recall", 0.0) or 0.0)
    add("min_must_cite_recall", recall, recall <= 0.5, "<=0.5")

    # per_domain_minimum sum (citations across domains) must fit citation budget.
    pdm = cov.get("per_domain_minimum") or policy.get("per_domain_minimum") or {}
    try:
        pdm_sum = sum(int(v) for v in pdm.values())
    except (TypeError, ValueError):
        pdm_sum = 0
    add("per_domain_minimum_sum", pdm_sum, pdm_sum <= 6, "<=6")

    return checks


def build_checks(rows: list[Row], task_config: dict[str, Any]) -> tuple[list[Check], list[Check], bool]:
    by = {r.variant: r for r in rows}
    comp = {r.variant: r.composite for r in rows}
    behavioural: list[Check] = []

    headroom_ok = comp["competent"] >= 0.45
    behavioural.append(Check(
        "headroom", headroom_ok,
        f"competent={comp['competent']:.4f} (>=0.45)",
    ))

    g1 = comp["competent"] - comp["mediocre"]
    g2 = comp["mediocre"] - comp["shallow"]
    gradient_ok = g1 >= 0.04 and g2 >= 0.04
    behavioural.append(Check(
        "gradient", gradient_ok,
        f"competent={comp['competent']:.4f} > mediocre={comp['mediocre']:.4f} "
        f"(gap {g1:+.4f}) > shallow={comp['shallow']:.4f} (gap {g2:+.4f}); each gap>=0.04",
    ))

    balance_ok = comp["one_sided"] < comp["competent"]
    behavioural.append(Check(
        "balance_bites", balance_ok,
        f"one_sided={comp['one_sided']:.4f} < competent={comp['competent']:.4f} "
        f"(pb dim: one_sided={by['one_sided'].per_dim['perspective_balance']:.3f} "
        f"competent={by['competent'].per_dim['perspective_balance']:.3f})",
    ))

    no_perverse_ok = (
        by["fabricated"].composite == 0.0 and by["fabricated"].nullify
        and by["shallow"].composite > 0.0
    )
    behavioural.append(Check(
        "no_perverse", no_perverse_ok,
        f"fabricated={comp['fabricated']:.4f} nullify={by['fabricated'].nullify}; "
        f"shallow={comp['shallow']:.4f} (>0)",
    ))

    vals = [r.composite for r in rows]
    std = statistics.pstdev(vals)
    variance_ok = std > 0.05
    behavioural.append(Check(
        "variance", variance_ok,
        f"pstd={std:.4f} over {[round(v,3) for v in vals]} (>0.05)",
    ))

    budget = _budget_checks(task_config)
    feasible_ok = all(c.passed for c in budget)
    behavioural.append(Check(
        "feasible", feasible_ok,
        "all thresholds within 8-tool-call budget" if feasible_ok
        else "one or more thresholds exceed budget (see thresholds table)",
    ))

    ready = all(c.passed for c in behavioural)
    return behavioural, budget, ready


# ---------------------------------------------------------------------------
# Rendering.
# ---------------------------------------------------------------------------

def _table(headers: list[str], rows: list[list[str]]) -> str:
    cols = [[h] + [r[i] for r in rows] for i, h in enumerate(headers)]
    widths = [max(len(c) for c in col) for col in cols]
    def line(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    out = [line(headers), "| " + " | ".join("-" * w for w in widths) + " |"]
    out += [line(r) for r in rows]
    return "\n".join(out)


def render(
    task_config: dict[str, Any],
    seeds: GoldenSeeds,
    rows: list[Row],
    behavioural: list[Check],
    budget: list[Check],
    ready: bool,
) -> str:
    dims_show = ("coverage", "source_diversity", "longform_quality",
                 "perspective_balance", "spec", "bilingual")
    headers = ["variant", "composite"] + [d[:9] for d in dims_show] + ["nullify"]
    body = [
        [r.variant, f"{r.composite:.4f}"]
        + [f"{r.per_dim[d]:.3f}" for d in dims_show]
        + ["yes" if r.nullify else "no"]
        for r in rows
    ]
    ranking = " > ".join(
        f"{r.variant}({r.composite:.3f})"
        for r in sorted(rows, key=lambda x: x.composite, reverse=True)
    )
    check_rows = [["PASS" if c.passed else "FAIL", c.name, c.detail] for c in behavioural]
    thresh_rows = [["PASS" if c.passed else "FAIL", c.name, c.detail] for c in budget]

    lines = [
        f"# RL Task Validation: {task_config.get('task_id')}",
        "",
        f"- language: {task_config.get('language', 'en')}",
        f"- golden: {seeds.golden_path}" + ("  [SYNTHESISED — commit a real golden before training]" if seeds.synthesised else "  [committed]"),
        f"- seed URLs: {len(seeds.must_cite)} across domains {seeds.used_aliases}",
        "",
        "## Reward curve (fast mode, WEIGHTS_RL, _rl_strict=True)",
        "",
        _table(headers, body),
        "",
        f"Ranking: {ranking}",
        "",
        "## Readiness checks",
        "",
        _table(["status", "check", "detail"], check_rows),
        "",
        "## Budget feasibility (8-tool-call envelope)",
        "",
        _table(["status", "threshold", "value"], thresh_rows),
        "",
        f"READY: {'YES' if ready else 'NO'}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("task_file", help="Path to the authored RL task JSON")
    p.add_argument("--json", action="store_true", help="Emit a JSON report instead of markdown")
    p.add_argument("--max-tool-calls", type=int, default=8)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    task_file = Path(args.task_file)
    if not task_file.exists():
        print(f"ERROR: task file not found: {task_file}", file=sys.stderr)
        return 1

    task_config = load_task(task_file, max_tool_calls=args.max_tool_calls)

    with tempfile.TemporaryDirectory(prefix="rl_task_validate_") as td:
        seeds = resolve_seeds(task_config, Path(td))
        rows = evaluate_all(task_config, seeds)
        behavioural, budget, ready = build_checks(rows, task_config)

        if args.json:
            out = {
                "task_id": task_config.get("task_id"),
                "ready": ready,
                "golden_synthesised": seeds.synthesised,
                "golden_path": str(seeds.golden_path),
                "curve": [
                    {
                        "variant": r.variant,
                        "composite": round(r.composite, 6),
                        "nullify": r.nullify,
                        "per_dim": {k: round(v, 6) for k, v in r.per_dim.items()},
                    }
                    for r in rows
                ],
                "checks": {c.name: {"pass": c.passed, "detail": c.detail} for c in behavioural},
                "budget": {c.name: {"pass": c.passed, "value": c.detail} for c in budget},
            }
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print(render(task_config, seeds, rows, behavioural, budget, ready))

    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
