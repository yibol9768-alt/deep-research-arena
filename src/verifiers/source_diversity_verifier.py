"""SourceDiversityVerifier -- 零 LLM 的来源多样性 pillar (v4 新增).

motivation
~~~~~~~~~~
我们已有 7 个 pillar 集中刻画「引文是否真实 + 任务是否完成 + 报告是否好读」,
没有一项专门测「引文是否在不同信息源 / 不同实体 / 不同子版块上分散」。这是
DRACO 的 objectivity 维度与 LiveResearchBench 的 Factual & Logical Consistency
轴里都暗含的一根独立坐标轴 —— 一边倒堆 shopping URL 凑数的报告,在
url_coverage 上能拿到高分 (因为命中了一些黄金 URL),但实际多样性极差。

本 verifier 用四个**完全确定性**子指标合成一个 [0, 1] 分数,**零 LLM 调用**,
跑两次给同样的结果,没有判官脆弱性。

dimensions
~~~~~~~~~~
1. domain_entropy        归一化 Shannon 熵 H / log(K) ∈ [0, 1]
                         三域均匀 ≈ 1.0,全集中在一个域 ≈ 0
2. top1_share            最大单一域的引文占比 (低则好)
                         占比 ≥ 0.60 → 0;占比 ≤ 0.35 → 1;线性插值
3. type_balance          shopping / reddit / wiki 三类各自的引用占比与
                         任务规范 min_d 比较,取最弱填充率的 sigmoid
4. subforum_diversity    Postmill URL 含 /f/<forum>/ 子版标识,要求引用
                         ≥ min_subforums 个不同子版 (沙盒友好)

得分 = 0.35·domain_entropy + 0.25·top1_share + 0.25·type_balance + 0.15·subforum_diversity

集成
~~~~
* 仅依赖 `extract_citations` 与 `urlparse`,无外部网络调用,无 LLM 调用。
* sandbox_hosts 复用 url_reachability 的解析,任务 spec 没显式给则用默认
  三沙盒 host:port。
* `min_subforums` 默认 3 (与典型任务的 reddit ≥ 20 引用 / ≥ 4 子版要求一致),
  可在 task_config["source_diversity"]["min_subforums"] 覆盖。
"""

from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse

from .base import VerifierResult
from .citation_format import extract_citations, host_in_set


_DEFAULT_SANDBOX = ["localhost:7770", "localhost:9999", "localhost:8090"]
# Magento ports the WebArena onestopmarket image binds (7770);
# Postmill -> 9999; Kiwix -> 8090. type_map below uses host:port equality.
_HOST_TYPE = {
    "localhost:7770": "shopping",
    "localhost:9999": "reddit",
    "localhost:8090": "wiki",
}

_SUBFORUM_RE = re.compile(r"/f/([A-Za-z0-9_\-]+)/")


def _host_port(url: str) -> str:
    """Return canonical "host:port" string for a URL, lowercased.

    Falls back to lowercased hostname when no port is present (open-net
    URLs that slipped past sandbox filtering).
    """
    try:
        p = urlparse(url)
    except Exception:
        return ""
    host = (p.hostname or "").lower()
    try:
        port = p.port
    except (TypeError, ValueError):
        port = None
    if not host:
        return ""
    return f"{host}:{port}" if port else host


def _classify_type(host_port: str) -> str:
    """Map host:port to one of {shopping, reddit, wiki, other}."""
    return _HOST_TYPE.get(host_port, "other")


def _normalized_entropy(counts: dict[str, int]) -> float:
    """Shannon entropy H = -Σ p log p, normalized to [0, 1] by log(K)
    where K is the number of distinct keys. Returns 0 when ≤1 key."""
    n = sum(counts.values())
    if n == 0 or len(counts) <= 1:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / n
        h -= p * math.log(p)
    # log(K) is the max entropy for K equiprobable bins.
    return h / math.log(len(counts))


def _top1_share_score(counts: dict[str, int]) -> tuple[float, float]:
    """Return (score, raw_top1_share).

    score: 1 when top1 ≤ 0.35 (perfectly balanced), 0 when top1 ≥ 0.60
    (over-concentrated), linear in between. Choosing 0.35 as the
    "balanced" anchor reflects three sandbox domains: ideal is
    (0.33, 0.33, 0.33) so the largest domain should naturally land
    near 0.35 (with 1-2 pct of jitter from typical task quotas).
    """
    n = sum(counts.values())
    if n == 0:
        return 0.0, 0.0
    top1 = max(counts.values()) / n
    if top1 <= 0.35:
        return 1.0, top1
    if top1 >= 0.60:
        return 0.0, top1
    return (0.60 - top1) / (0.60 - 0.35), top1


def _type_balance(type_counts: dict[str, int], min_per_type: dict[str, int]) -> tuple[float, dict[str, float]]:
    """Per-type fill-ratio min, mirroring url_coverage.domain_balance but
    measuring **proportional** fill rather than absolute counts.

    For each of shopping / reddit / wiki, we compute
        fill_d = min(1, observed_d / min_d)
    where min_d is the task's per-domain minimum. Final score is the
    min across the three (weakest type drags the score down).

    If a task spec doesn't define per-type minimums, falls back to
    (shopping=20, reddit=15, wiki=10) — defaults broadly typical for
    cross-site deep tasks.
    """
    defaults = {"shopping": 20, "reddit": 15, "wiki": 10}
    fills: dict[str, float] = {}
    for t in ("shopping", "reddit", "wiki"):
        target = max(1, int(min_per_type.get(t, defaults[t])))
        observed = int(type_counts.get(t, 0))
        fills[t] = min(1.0, observed / target)
    return min(fills.values()) if fills else 0.0, fills


def _subforum_diversity(urls: list[str], min_subforums: int) -> tuple[float, list[str]]:
    """Count distinct Postmill /f/<forum>/ subforums in the cited URL set.

    Postmill URLs look like ``http://localhost:9999/f/headphones/comments/...``
    or ``http://localhost:9999/f/technology/...``. We extract the forum
    slug after `/f/` and dedupe. Returns (score, sorted_subforums) where
    score = min(1, distinct / min_subforums) with min_subforums defaulting
    to 3 (mirrors task spec typical "≥ 3 subforums" Reddit requirement).
    """
    seen: set[str] = set()
    for u in urls:
        m = _SUBFORUM_RE.search(u)
        if m:
            seen.add(m.group(1).lower())
    distinct = len(seen)
    target = max(1, int(min_subforums))
    return min(1.0, distinct / target), sorted(seen)


class SourceDiversityVerifier:
    """Zero-LLM source-diversity pillar (v4 new).

    Constructor takes no required arguments. ``verify`` reads
    task_config.url_coverage.per_domain_minimum (if present, mapping
    {shopping, reddit, wiki} -> int) and
    task_config.source_diversity.min_subforums (default 3) to set
    thresholds. Otherwise it falls back to reasonable cross-site-deep
    defaults so it works out of the box on any task.
    """

    kind = "source_diversity"

    def verify(self, *, task_config: dict[str, Any], answer: str = "", page: Any = None) -> VerifierResult:
        cfg = task_config.get("source_diversity") or {}
        sandbox_hosts: list[str] = (
            task_config.get("sandbox_hosts")
            or cfg.get("sandbox_hosts")
            or _DEFAULT_SANDBOX
        )
        min_subforums = int(cfg.get("min_subforums", 3))

        # Per-type minimums prefer url_coverage.per_domain_minimum (task spec
        # already encodes these for the citation-policy gate) so the two
        # pillars stay aligned.
        per_dom = (task_config.get("url_coverage") or {}).get("per_domain_minimum") or {}
        # url_coverage uses keys like __SHOPPING__ / __REDDIT__ / __WIKIPEDIA__;
        # canonicalize so source_diversity can read either.
        alias_map = {
            "__SHOPPING__": "shopping",
            "__REDDIT__": "reddit",
            "__WIKIPEDIA__": "wiki",
            "shopping": "shopping",
            "reddit": "reddit",
            "wiki": "wiki",
            "wikipedia": "wiki",
        }
        min_per_type: dict[str, int] = {}
        for raw_key, v in per_dom.items():
            t = alias_map.get(str(raw_key))
            if t is None:
                continue
            try:
                min_per_type[t] = int(v)
            except Exception:
                pass

        citations = extract_citations(answer or "", sandbox_hosts, sandbox_only=False)
        cited_raw = [c.raw_url for c in citations]
        # Only count *sandbox* URLs for diversity: open-net URLs that slipped
        # past dragged down the entropy calculation and rewarded the
        # citation-fabrication that v2's reach gate already punishes. The
        # diversity question is about distribution *within* the sandbox.
        sandbox_set = {h.lower() for h in sandbox_hosts}
        sandbox_urls = [u for u in cited_raw if host_in_set(u, sandbox_set)]

        if not sandbox_urls:
            return VerifierResult(
                score=0.0,
                passed=False,
                details={
                    "reason": "no sandbox citations",
                    "total_citations": len(cited_raw),
                    "sandbox_citations": 0,
                    "subscores": {
                        "domain_entropy": 0.0,
                        "top1_share_score": 0.0,
                        "top1_share_raw": 0.0,
                        "type_balance": 0.0,
                        "subforum_diversity": 0.0,
                    },
                },
            )

        # Domain counts (host:port granularity).
        dom_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        for u in sandbox_urls:
            hp = _host_port(u)
            if not hp:
                continue
            dom_counts[hp] = dom_counts.get(hp, 0) + 1
            t = _classify_type(hp)
            type_counts[t] = type_counts.get(t, 0) + 1

        ent = _normalized_entropy(dom_counts)
        top1_score, top1_raw = _top1_share_score(dom_counts)
        type_score, type_fills = _type_balance(type_counts, min_per_type)
        subforum_score, subforum_list = _subforum_diversity(sandbox_urls, min_subforums)

        score = (
            0.35 * ent
            + 0.25 * top1_score
            + 0.25 * type_score
            + 0.15 * subforum_score
        )

        # Pass gate: score ≥ 0.5 (mirrors how url_coverage gates on its
        # composite). This is intentionally lenient because the score is
        # already an aggregate of 4 subscores; setting the gate lower means
        # a single weak subscore doesn't auto-fail an otherwise diverse
        # report.
        passed = score >= float(cfg.get("min_score", 0.50))

        return VerifierResult(
            score=round(float(score), 4),
            passed=bool(passed),
            details={
                "total_citations": len(cited_raw),
                "sandbox_citations": len(sandbox_urls),
                "distinct_domains": len(dom_counts),
                "subforums_cited": subforum_list,
                "type_counts": type_counts,
                "type_fills": type_fills,
                "min_per_type": min_per_type,
                "min_subforums": min_subforums,
                "subscores": {
                    "domain_entropy":     round(ent, 4),
                    "top1_share_score":   round(top1_score, 4),
                    "top1_share_raw":     round(top1_raw, 4),
                    "type_balance":       round(type_score, 4),
                    "subforum_diversity": round(subforum_score, 4),
                },
                "weights": {
                    "domain_entropy":     0.35,
                    "top1_share":         0.25,
                    "type_balance":       0.25,
                    "subforum_diversity": 0.15,
                },
                "min_score_gate": float(cfg.get("min_score", 0.50)),
            },
        )
