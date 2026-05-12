"""Comprehensive fairness audit of the deep_v3/ corpus.

Sections:

1. Per-agent statistics — mean / median / std of composite_v2, plus per-pillar
   means (url_cov, reach, checklist_pass_rate, citation_alignment, analysis_depth,
   presentation, qm, nli). Surfaces any agent where one pillar is outlier-low.

2. Distribution of must_cite_hit — to see if golden URL recall is meaningful
   (>0 for legitimate runs) or systematically zero (citation extraction broken
   for that agent's style).

3. Citation-style detection — which agents emit `[N]` numbered refs (storm/ldr)
   vs ``[label](url)`` markdown links. A reach=0 outcome on numbered-ref agents
   is a measurement artifact, not a quality artifact — flag it.

4. Spot-check top-3 and bottom-3 of each agent — show composite_v2 with the
   markdown report's first 200 chars, so you can eyeball whether the score
   reflects the answer.

5. Sanity check on composite math — recompute composite_v2 from pillars and
   compare to the recorded value. Drift>0.001 means something writes a wrong
   value somewhere.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path("/opt/deep_reserch/data/results/deep_v3")
DEEP_DIR = Path("/opt/deep_reserch/data/results/deep")
RUNNER_FAIL_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s\s*,\s*exit\s*=\s*\d+\s*\)",
    re.IGNORECASE,
)
NUMBERED_REF_RE = re.compile(r"^\s*\[(\d{1,3})\]\s*\.?\s*(?:[-:.]\s*)?http", re.MULTILINE)
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(http[^)]+\)")


def _gp(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _is_clean(d) -> bool:
    """Same predicate as the leaderboard's _looks_degenerate (inverted)."""
    chars = d.get("answer_chars", 0) or 0
    if chars < 100:
        return False
    ans_path = d.get("answer_path")
    if isinstance(ans_path, str):
        a = Path(ans_path)
        if not a.is_absolute():
            a = Path("/opt/deep_reserch") / a
        if a.exists():
            head = a.read_text(encoding="utf-8", errors="replace")[:300]
            if RUNNER_FAIL_RE.match(head.lstrip()):
                return False
    return True


def main() -> None:
    files = sorted(ROOT.glob("*_matrix.score.json"))
    by_agent: dict[str, list[dict]] = defaultdict(list)
    NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d{4})_matrix\.score\.json$")
    for fp in files:
        m = NAME_RE.match(fp.name)
        if not m:
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not _is_clean(d):
            continue
        d["_agent"] = m.group(1)
        d["_task"] = m.group(2)
        d["_path"] = str(fp)
        by_agent[m.group(1)].append(d)

    # === Section 1: per-agent statistics ===
    print("=" * 80)
    print("SECTION 1: per-agent composite_v2 + pillar statistics (clean rows only)")
    print("=" * 80)
    print(f"{'agent':<18} {'n':>3} {'v2 mean':>8} {'v2 med':>8} {'uc':>6} "
          f"{'reach':>6} {'cl_pass':>8} {'cita':>6} {'ad':>6} {'pres':>6}")
    print("-" * 78)
    for agent in sorted(by_agent.keys()):
        rows = by_agent[agent]
        v2 = [_gp(r, "composite", "composite_v2", default=0.0) or 0.0 for r in rows]
        uc = [_gp(r, "url_coverage", "score", default=0.0) or 0.0 for r in rows]
        reach = [_gp(r, "url_reachability", "score", default=0.0) or 0.0 for r in rows]
        cl = [_gp(r, "checklist", "pass_rate", default=0.0) or 0.0 for r in rows]
        cita = [_gp(r, "citation_alignment", "score", default=0.0) or 0.0 for r in rows]
        ad = [_gp(r, "analysis_depth", "score", default=0.0) or 0.0 for r in rows]
        pres = [_gp(r, "presentation", "score", default=0.0) or 0.0 for r in rows]
        print(f"{agent:<18} {len(rows):>3} "
              f"{statistics.mean(v2):>8.4f} {statistics.median(v2):>8.4f} "
              f"{statistics.mean(uc):>6.3f} {statistics.mean(reach):>6.3f} "
              f"{statistics.mean(cl):>8.3f} {statistics.mean(cita):>6.3f} "
              f"{statistics.mean(ad):>6.3f} {statistics.mean(pres):>6.3f}")

    # === Section 2: must_cite_hit distribution ===
    print()
    print("=" * 80)
    print("SECTION 2: must_cite_hit distribution per agent (golden-URL recall)")
    print("=" * 80)
    print(f"{'agent':<18} {'mean_hits':>10} {'max_hits':>10} {'pairs_with_hits':>18}")
    print("-" * 60)
    for agent in sorted(by_agent.keys()):
        rows = by_agent[agent]
        hits = [_gp(r, "url_coverage", "details", "must_cite_hit", default=0) or 0 for r in rows]
        with_hits = sum(1 for h in hits if h > 0)
        print(f"{agent:<18} {statistics.mean(hits):>10.2f} {max(hits):>10} "
              f"{with_hits:>10}/{len(rows):<5}")

    # === Section 3: citation style detection ===
    print()
    print("=" * 80)
    print("SECTION 3: citation style (numbered-ref vs markdown-link) — flags")
    print("           reach-gate measurement artifacts on numbered-ref agents")
    print("=" * 80)
    print(f"{'agent':<18} {'pairs':>5} {'numbered':>9} {'markdown':>9} {'pred_style':>12}")
    print("-" * 60)
    for agent in sorted(by_agent.keys()):
        rows = by_agent[agent]
        n_numbered = 0
        n_markdown = 0
        for r in rows:
            ans_path = r.get("answer_path")
            if not ans_path:
                continue
            a = Path(ans_path)
            if not a.is_absolute():
                a = Path("/opt/deep_reserch") / a
            if not a.exists():
                continue
            text = a.read_text(encoding="utf-8", errors="replace")
            n_numbered += len(NUMBERED_REF_RE.findall(text))
            n_markdown += len(MD_LINK_RE.findall(text))
        # Predict style based on which dominates
        style = "markdown" if n_markdown > n_numbered * 1.5 else (
                "numbered" if n_numbered > n_markdown * 1.5 else "mixed")
        flag = "  ← reach-gate artifact possible" if style == "numbered" else ""
        print(f"{agent:<18} {len(rows):>5} {n_numbered:>9} {n_markdown:>9} "
              f"{style:>12}{flag}")

    # === Section 4: spot-check extremes ===
    print()
    print("=" * 80)
    print("SECTION 4: spot-check top-1 and bottom-1 per agent (sanity-eyeball)")
    print("=" * 80)
    for agent in sorted(by_agent.keys()):
        rows = sorted(
            by_agent[agent],
            key=lambda r: _gp(r, "composite", "composite_v2", default=0.0) or 0.0,
        )
        if not rows:
            continue
        bot = rows[0]
        top = rows[-1]
        for label, r in (("BOT", bot), ("TOP", top)):
            ans_path = r.get("answer_path")
            head = ""
            if ans_path:
                a = Path(ans_path)
                if not a.is_absolute():
                    a = Path("/opt/deep_reserch") / a
                if a.exists():
                    head = a.read_text(encoding="utf-8", errors="replace")[:120].replace("\n", " ")
            v2 = _gp(r, "composite", "composite_v2", default=0.0) or 0.0
            chars = r.get("answer_chars", 0)
            cited = _gp(r, "url_reachability", "details", "cited_total", default=0)
            mh = _gp(r, "url_coverage", "details", "must_cite_hit", default=0)
            print(f"  [{label}] {agent:<15} {r['_task']}  "
                  f"v2={v2:.4f} chars={chars} cited={cited} mh={mh}")
            print(f"        head: {head[:100]}")

    # === Section 5: composite math sanity ===
    print()
    print("=" * 80)
    print("SECTION 5: composite_v2 recomputation (drift>0.001 = bug)")
    print("=" * 80)
    drift_count = 0
    max_drift = 0.0
    for agent, rows in by_agent.items():
        for r in rows:
            uc = _gp(r, "url_coverage", "score", default=0.0) or 0.0
            reach = _gp(r, "url_reachability", "score", default=0.0) or 0.0
            cl = _gp(r, "checklist", "pass_rate", default=0.0) or 0.0
            qm = _gp(r, "quote_match", "score", default=0.0) or 0.0
            nli = _gp(r, "claim_nli", "score", default=0.0) or 0.0
            spec = r.get("markdown_spec") or {}
            spec_pass = sum(
                bool(spec.get(k)) for k in ("words_ok", "citations_ok", "paragraphs_ok")
            ) / 3.0
            quality = 0.4 * uc + 0.4 * cl + 0.2 * spec_pass
            qm_factor = 0.5 + 0.5 * qm
            nli_factor = 0.5 + 0.5 * nli
            truth = reach * qm_factor * nli_factor
            v2_calc = round(truth * quality, 4)
            v2_recorded = round(_gp(r, "composite", "composite_v2", default=0.0) or 0.0, 4)
            drift = abs(v2_calc - v2_recorded)
            if drift > 0.001:
                drift_count += 1
                if drift > max_drift:
                    max_drift = drift
                if drift_count <= 5:
                    print(f"  DRIFT {agent} {r['_task']}: recorded={v2_recorded:.4f} "
                          f"calc={v2_calc:.4f} (Δ={drift:.4f})")
    print(f"  total drifts: {drift_count} / {sum(len(v) for v in by_agent.values())} "
          f"(max drift = {max_drift:.4f})")


if __name__ == "__main__":
    main()
