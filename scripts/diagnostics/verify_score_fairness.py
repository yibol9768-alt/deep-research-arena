"""Per-pair score-fairness verification.

For each ``*_matrix.score.json``, re-run the URL canonicalisation that the
DEPLOYED scorer (``/opt/deep_reserch/src/verifiers/url_coverage_verifier.py``)
uses, then compare:

    agent_canon  =  canonicalize(every URL in answer.md)
    golden_canon =  canonicalize(every must_cite_url for this task)

We then look for *near-misses* — URLs that share the same domain + path stem
but differ in case / trailing slash / query — which would indicate a missed
match, i.e. a scoring bug. If the canonicaliser is doing its job, the match
set after canon should be a strict superset of the raw match set, and any
near-miss should have been resolved.

Suspect pairs are flagged for human review with the exact mismatch.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path("/opt/deep_reserch/data/results/deep_v3")
GOLDEN_DIR = Path("/opt/deep_reserch/data/golden/deep")
PAIR_NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d{4})_matrix\.score\.json$")


# === Inline copy of the deployed scorer's URL canonicaliser ===
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<url>https?://[^\s)]+)\)")
_BARE_URL_RE = re.compile(r"(?<![(\[])(https?://[^\s<>\"']+)")


def _canonical(url: str) -> str:
    s = url.strip().rstrip("`'\"\\)>,;:.")
    try:
        p = urlparse(s)
        host = (p.hostname or "").lower()
        try:
            port = p.port
        except (ValueError, TypeError):
            port = None
        if port and port not in (80, 443):
            host = f"{host}:{port}"
        path = (p.path or "").rstrip("/") or "/"
        qs = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
        return urlunparse((p.scheme.lower() or "http", host, path, "", qs, ""))
    except Exception:
        return s.lower()


def _extract_cited_urls(md: str) -> set[str]:
    raw = []
    for m in _MD_LINK_RE.finditer(md):
        raw.append(m.group("url"))
    stripped = _MD_LINK_RE.sub("", md)
    for m in _BARE_URL_RE.finditer(stripped):
        raw.append(m.group(1).rstrip(").,;:"))
    return {_canonical(r) for r in raw}


def _path_stem(url: str) -> str:
    """Domain + last 2 path segments, lowercased. Coarse near-miss key."""
    m = re.match(r"https?://([^/]+)(/[^?#]*)?", url)
    if not m:
        return ""
    host = m.group(1).lower()
    path = (m.group(2) or "").rstrip("/")
    parts = path.split("/")
    tail = "/".join(parts[-2:]) if len(parts) >= 2 else path
    return f"{host}{tail}".lower()


def verify(score_path: Path) -> dict:
    name_m = PAIR_NAME_RE.match(score_path.name)
    if not name_m:
        return {"error": "bad-filename"}
    agent, task = name_m.group(1), name_m.group(2)
    full_task = f"dr_cross_deep_{task}"

    data = json.loads(score_path.read_text(encoding="utf-8"))
    composite_v2 = (data.get("composite") or {}).get("composite_v2", 0.0)
    must_cite_hit = ((data.get("url_coverage") or {}).get("details") or {}).get("must_cite_hit", 0)
    must_cite_total = ((data.get("url_coverage") or {}).get("details") or {}).get("must_cite_total", 0)

    ans_path_str = data.get("answer_path")
    if not ans_path_str:
        return {"agent": agent, "task": task, "error": "no answer_path"}
    ans_path = Path(ans_path_str)
    if not ans_path.is_absolute():
        ans_path = Path("/opt/deep_reserch") / ans_path
    if not ans_path.exists():
        return {"agent": agent, "task": task, "error": f"answer not on disk: {ans_path}"}

    answer_md = ans_path.read_text(encoding="utf-8", errors="replace")
    cited_canon = _extract_cited_urls(answer_md)

    golden_path = GOLDEN_DIR / f"{full_task}.json"
    if not golden_path.exists():
        return {"agent": agent, "task": task, "error": "no golden"}
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    must_entries = golden.get("must_cite_urls") or []
    golden_canon = {_canonical(e["url"]): e for e in must_entries}

    direct_hits = cited_canon & set(golden_canon.keys())

    cited_stems = {_path_stem(u): u for u in cited_canon}
    golden_stems = {_path_stem(u): u for u in golden_canon.keys()}
    near_miss_keys = set(cited_stems.keys()) & set(golden_stems.keys())
    near_misses = []
    for k in near_miss_keys:
        agent_u = cited_stems[k]
        golden_u = golden_stems[k]
        if agent_u != golden_u:
            near_misses.append((agent_u, golden_u))

    if near_misses and direct_hits == set():
        verdict = "SUSPECT"
    elif must_cite_hit != len(direct_hits):
        verdict = "DRIFT"
    else:
        verdict = "FAIR"

    sandbox_pat = re.compile(r"localhost:(7770|9999|8090)")
    sandbox_cited = sum(1 for u in cited_canon if sandbox_pat.search(u))

    return {
        "agent": agent,
        "task": task,
        "composite_v2": composite_v2,
        "agent_cited_canon_n": len(cited_canon),
        "agent_cited_sandbox_n": sandbox_cited,
        "golden_must_cite_n": len(golden_canon),
        "scorer_must_cite_hit": must_cite_hit,
        "scorer_must_cite_total": must_cite_total,
        "direct_hits_recomputed": len(direct_hits),
        "near_misses_n": len(near_misses),
        "near_miss_examples": near_misses[:3],
        "verdict": verdict,
    }


def main() -> int:
    files = sorted(ROOT.glob("*_matrix.score.json"))
    if not files:
        print("no score files yet")
        return 0
    suspects = []
    drifts = []
    print(f"verifying fairness on {len(files)} pairs\n")
    for fp in files:
        r = verify(fp)
        if "error" in r:
            print(f"ERR  {fp.name}: {r['error']}")
            continue
        line = (
            f"{r['verdict']:8s} {r['agent']} {r['task']}  "
            f"composite_v2={r['composite_v2']:.4f}  "
            f"agent_canon={r['agent_cited_canon_n']} "
            f"(sandbox={r['agent_cited_sandbox_n']})  "
            f"hits_recomp={r['direct_hits_recomputed']}/{r['golden_must_cite_n']}  "
            f"scorer_says={r['scorer_must_cite_hit']}/{r['scorer_must_cite_total']}  "
            f"near_miss={r['near_misses_n']}"
        )
        print(line)
        if r["verdict"] == "SUSPECT":
            for am, gm in r["near_miss_examples"]:
                print(f"    NEAR-MISS  agent={am}\n               golden={gm}")
            suspects.append(r)
        elif r["verdict"] == "DRIFT":
            print(
                f"    DRIFT  scorer recorded {r['scorer_must_cite_hit']} hits but "
                f"recomputation finds {r['direct_hits_recomputed']}"
            )
            drifts.append(r)
    print(f"\nsuspects (potential normalisation bug): {len(suspects)}")
    print(f"drifts (scorer disagrees with recomputation): {len(drifts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
