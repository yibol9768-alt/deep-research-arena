"""Run the same fairness verifier across the historical score JSONs at
``data/results/deep/`` (the 354 files that feed the current LEADERBOARD_DEEP).

Goals:
  * Confirm every existing pair's must_cite_hit recomputation matches what
    the scorer recorded (no DRIFT)
  * Surface any near-miss URL pairs (potential SUSPECT) — these mean the
    canonicaliser missed a legitimate citation

Output per agent:
  agent_name : N pairs, F fair, S suspect, D drift, E error
  example DRIFTs / SUSPECTs flagged inline.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path("/opt/deep_reserch/data/results/deep")
GOLDEN_DIR = Path("/opt/deep_reserch/data/golden/deep")
PAIR_NAME_RE = re.compile(r"^([A-Za-z0-9_\-]+?)__dr_cross_deep_(\d{4})_matrix\.score\.json$")

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<url>https?://[^\s)]+)\)")
_BARE_URL_RE = re.compile(r"(?<![(\[])(https?://[^\s<>\"']+)")
_KIWIX_HOSTS = {"localhost:8090"}


def _kiwix_normalize_path(path: str) -> str:
    idx = path.rfind("/A/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 3:].lower()}"
    idx = path.rfind("/wiki/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 6:].lower()}"
    return path


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
        path = p.path or "/"
        if host in _KIWIX_HOSTS:
            path = _kiwix_normalize_path(path)
        path = path.rstrip("/") or "/"
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
        return {"error": "bad-filename", "name": score_path.name}
    agent, task = name_m.group(1), name_m.group(2)
    full_task = f"dr_cross_deep_{task}"
    try:
        data = json.loads(score_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"agent": agent, "task": task, "error": f"json-parse: {exc}"}

    # Compute answer path: prefer score's answer_path, fall back to convention
    ans = data.get("answer_path")
    if ans:
        a = Path(ans)
        if not a.is_absolute():
            a = Path("/opt/deep_reserch") / a
    else:
        a = score_path.with_suffix("").with_suffix(".md")
    if not a.exists():
        return {"agent": agent, "task": task, "error": f"answer not on disk"}

    answer_md = a.read_text(encoding="utf-8", errors="replace")
    cited_canon = _extract_cited_urls(answer_md)

    golden_path = GOLDEN_DIR / f"{full_task}.json"
    if not golden_path.exists():
        return {"agent": agent, "task": task, "error": "no golden"}
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    must_entries = golden.get("must_cite_urls") or []
    golden_canon = {_canonical(e["url"]): e for e in must_entries}

    direct_hits = cited_canon & set(golden_canon.keys())
    scorer_hit = ((data.get("url_coverage") or {}).get("details") or {}).get("must_cite_hit", 0)

    cited_stems = {_path_stem(u): u for u in cited_canon}
    golden_stems = {_path_stem(u): u for u in golden_canon.keys()}
    near_miss_keys = set(cited_stems.keys()) & set(golden_stems.keys())
    near_misses = []
    for k in near_miss_keys:
        if cited_stems[k] != golden_stems[k]:
            near_misses.append((cited_stems[k], golden_stems[k]))

    if scorer_hit != len(direct_hits):
        verdict = "DRIFT"
    elif not direct_hits and near_misses:
        verdict = "SUSPECT"
    else:
        verdict = "FAIR"
    return {
        "agent": agent,
        "task": task,
        "verdict": verdict,
        "scorer_hit": scorer_hit,
        "hits_recomp": len(direct_hits),
        "near_miss_n": len(near_misses),
        "near_miss_examples": near_misses[:2],
    }


def main() -> int:
    files = sorted(ROOT.glob("*_matrix.score.json"))
    print(f"verifying fairness on {len(files)} historical pairs in {ROOT}\n")

    by_agent: dict[str, dict[str, int]] = defaultdict(lambda: {"FAIR": 0, "SUSPECT": 0, "DRIFT": 0, "ERR": 0})
    drift_examples: list[dict] = []
    suspect_examples: list[dict] = []
    err_examples: list[dict] = []

    for fp in files:
        r = verify(fp)
        if "error" in r:
            agent = r.get("agent", "?")
            by_agent[agent]["ERR"] += 1
            err_examples.append(r)
            continue
        by_agent[r["agent"]][r["verdict"]] += 1
        if r["verdict"] == "DRIFT":
            drift_examples.append(r)
        elif r["verdict"] == "SUSPECT":
            suspect_examples.append(r)

    print(f"{'agent':<22}  {'FAIR':>6} {'SUSPECT':>8} {'DRIFT':>6} {'ERR':>5}")
    print("-" * 56)
    for agent in sorted(by_agent.keys()):
        c = by_agent[agent]
        print(f"{agent:<22}  {c['FAIR']:>6} {c['SUSPECT']:>8} {c['DRIFT']:>6} {c['ERR']:>5}")

    print()
    if drift_examples:
        print(f"=== {len(drift_examples)} DRIFT (scorer != recomputation) ===")
        for r in drift_examples[:10]:
            print(f"  {r['agent']} {r['task']}: scorer={r['scorer_hit']} recomp={r['hits_recomp']}")
        if len(drift_examples) > 10:
            print(f"  ... (+{len(drift_examples)-10} more)")
    else:
        print("DRIFT: 0 — every recorded must_cite_hit matches recomputation")

    print()
    if suspect_examples:
        print(f"=== {len(suspect_examples)} SUSPECT (near-miss with no direct hits) ===")
        for r in suspect_examples[:10]:
            print(f"  {r['agent']} {r['task']}: near_miss={r['near_miss_n']}")
            for am, gm in r["near_miss_examples"]:
                print(f"    agent  : {am}")
                print(f"    golden : {gm}")
        if len(suspect_examples) > 10:
            print(f"  ... (+{len(suspect_examples)-10} more)")
    else:
        print("SUSPECT: 0 — no near-miss URLs the canonicaliser failed to match")

    print()
    if err_examples:
        print(f"=== {len(err_examples)} ERR ===")
        for r in err_examples[:5]:
            print(f"  {r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
