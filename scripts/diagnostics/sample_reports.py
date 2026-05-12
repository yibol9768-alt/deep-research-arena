"""Sample 3 reports per agent (highest composite_v2, median, lowest) and
print enough of each so a human can eyeball whether the score matches the
report's quality.

For each pair we show:
  - composite_v2 + pillar breakdown (uc, reach, checklist, citation_alignment, ad, pres)
  - First 400 chars of the report (Title + opening of body)
  - Last 200 chars of the report (closing / references)
"""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path("/opt/deep_reserch/data/results/deep_v3")
RUNNER_FAIL_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s\s*,\s*exit\s*=\s*\d+\s*\)",
    re.IGNORECASE,
)


def _gp(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _is_clean(d) -> bool:
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


def _read_report(d):
    p = d.get("answer_path")
    if not p:
        return ""
    a = Path(p)
    if not a.is_absolute():
        a = Path("/opt/deep_reserch") / a
    if not a.exists():
        return ""
    return a.read_text(encoding="utf-8", errors="replace")


NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d{4})_matrix\.score\.json$")
files = sorted(ROOT.glob("*_matrix.score.json"))
by_agent = defaultdict(list)
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
    by_agent[m.group(1)].append(d)


def fmt_pillars(d):
    return (
        f"v2={_gp(d, 'composite', 'composite_v2', default=0.0):.4f}  "
        f"uc={_gp(d, 'url_coverage', 'score', default=0.0):.3f}  "
        f"reach={_gp(d, 'url_reachability', 'score', default=0.0):.3f}  "
        f"cl={_gp(d, 'checklist', 'pass_rate', default=0.0):.3f}  "
        f"cita={_gp(d, 'citation_alignment', 'score', default=0.0):.3f}  "
        f"ad={_gp(d, 'analysis_depth', 'score', default=0.0):.3f}  "
        f"pres={_gp(d, 'presentation', 'score', default=0.0):.3f}"
    )


def fmt_summary(d):
    chars = d.get("answer_chars", 0)
    cited = _gp(d, "url_reachability", "details", "cited_total", default=0)
    mh = _gp(d, "url_coverage", "details", "must_cite_hit", default=0)
    mt = _gp(d, "url_coverage", "details", "must_cite_total", default=0)
    cl = d.get("checklist") or {}
    return (
        f"chars={chars}  cited={cited}  must_cite={mh}/{mt}  "
        f"checklist={cl.get('pass_count', 0)}P/{cl.get('fail_count', 0)}F/{cl.get('unclear_count', 0)}U"
    )


for agent in sorted(by_agent.keys()):
    rows = sorted(by_agent[agent], key=lambda r: _gp(r, "composite", "composite_v2", default=0.0))
    if len(rows) < 3:
        continue
    bot = rows[0]
    med = rows[len(rows) // 2]
    top = rows[-1]
    print("=" * 90)
    print(f"AGENT: {agent}  ({len(rows)} clean pairs)")
    print("=" * 90)
    for label, r in (("BOTTOM", bot), ("MEDIAN", med), ("TOP", top)):
        print(f"\n--- [{label}] task {r['_task']} ---")
        print(f"  pillars: {fmt_pillars(r)}")
        print(f"  summary: {fmt_summary(r)}")
        rpt = _read_report(r)
        head = rpt[:400].replace("\n", " ")
        tail = rpt[-200:].replace("\n", " ") if len(rpt) > 600 else ""
        print(f"  head[400]: {head}")
        if tail:
            print(f"  tail[200]: {tail}")
