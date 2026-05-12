"""Audit a single ``*_matrix.score.json`` for bugs AND fairness.

Used by the polling watcher (``watch_pair_bugs.sh``) that fires once per new
pair landing during the bulk Elo run.

Two checks run per pair:

A. Structural bugs — JSON parses, composite_v2 in [0,1], non-empty answer,
   no <think>/Thinking-Process leak in answer.md, no judge_error in any
   sub-judge, no 21/21-unclear, no reach=passed-but-zero-cited.

B. Fairness — re-extract the agent's URLs with the same canonicaliser the
   scorer uses, intersect with the golden must_cite set. If the scorer
   recorded N hits but recomputation finds M != N, that's a verifier bug
   (DRIFT). If recomputation finds 0 direct hits but there ARE near-misses
   (URLs sharing the same path stem but differing by case / slash / query),
   that's a normalisation bug (SUSPECT).

Prints one line:
    OK   <agent> <task> composite_v2=X cited=N golden=K hits=H verdict=FAIR
    BUG  <agent> <task>: <reason1>; <reason2>

Exit code is always 0 (a bug-printer that crashed would be useless).
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
THINK_LEAK_RE = re.compile(r"(<think>|Thinking Process:|</think>)", re.IGNORECASE)


def _gp(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


# === Inline copy of the deployed scorer's URL canonicaliser ===
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<url>https?://[^\s)]+)\)")
_BARE_URL_RE = re.compile(r"(?<![(\[])(https?://[^\s<>\"']+)")
_KIWIX_HOSTS = {"localhost:8090"}
_RUNNER_FAIL_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s\s*,\s*exit\s*=\s*\d+\s*\)",
    re.IGNORECASE,
)


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


def _structural_bugs(data: dict, ans_path: Path | None) -> list[str]:
    errs: list[str] = []
    c2 = _gp(data, "composite", "composite_v2")
    if not isinstance(c2, (int, float)):
        errs.append(f"composite_v2 not numeric ({type(c2).__name__})")
    elif not (0.0 <= c2 <= 1.0):
        errs.append(f"composite_v2={c2} out of [0,1]")

    chars = data.get("answer_chars", 0)
    if not isinstance(chars, (int, float)) or chars < 100:
        errs.append(f"answer_chars={chars} (effectively empty)")

    cited_total = _gp(data, "url_reachability", "details", "cited_total", default=0)
    reach_score = _gp(data, "url_reachability", "score", default=0.0) or 0.0
    if (isinstance(c2, (int, float)) and c2 == 0.0
            and isinstance(chars, (int, float)) and chars > 5000
            and isinstance(cited_total, int) and cited_total > 0
            and isinstance(reach_score, (int, float)) and reach_score > 0):
        # True bug: agent cited URLs, those URLs DO resolve (reach>0), but
        # composite_v2 still went to 0. Most likely a verifier crash or
        # null-pillar bug. Skipping cases where reach=0 (correctly killed
        # by multiplicative gate, not a bug — agent fabricated URLs) and
        # cited=0 (ungrounded report, correctly scored 0).
        errs.append(
            f"composite_v2=0 with chars={chars}, cited={cited_total}, "
            f"reach={reach_score} (scoring may have errored)"
        )

    cl = data.get("checklist") or {}
    verdicts = cl.get("verdicts") or []
    unclear = cl.get("unclear_count", 0)
    if verdicts and unclear == len(verdicts):
        errs.append(f"checklist {unclear}/{len(verdicts)} unclear")

    for path in (
        ("checklist", "judge_error"),
        ("analysis_depth", "details", "judge_error"),
        ("presentation", "details", "judge_error"),
        ("citation_alignment", "details", "judge", "error"),
    ):
        v = _gp(data, *path)
        if v:
            errs.append(f"{'.'.join(path)}={v}")

    rp = _gp(data, "url_reachability", "passed")
    cited = _gp(data, "url_reachability", "details", "cited_total", default=0)
    if rp is True and cited == 0:
        errs.append("reach.passed=True but cited_total=0")

    if ans_path and ans_path.exists():
        head = ans_path.read_text(encoding="utf-8", errors="replace")[:8000]
        mleak = THINK_LEAK_RE.search(head)
        if mleak:
            errs.append(f"answer.md leaks '{mleak.group(0)}' at offset {mleak.start()}")
    return errs


def _fairness_verdict(data: dict, ans_path: Path, task: str) -> tuple[str, dict]:
    """Returns (verdict, details). Verdict = FAIR/SUSPECT/DRIFT/SKIP."""
    if not ans_path.exists():
        return "SKIP", {"reason": "no answer.md"}
    answer_md = ans_path.read_text(encoding="utf-8", errors="replace")
    cited_canon = _extract_cited_urls(answer_md)

    golden_path = GOLDEN_DIR / f"dr_cross_deep_{task}.json"
    if not golden_path.exists():
        return "SKIP", {"reason": "no golden"}
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    must_entries = golden.get("must_cite_urls") or []
    golden_canon = {_canonical(e["url"]): e for e in must_entries}
    direct_hits = cited_canon & set(golden_canon.keys())

    scorer_hit = _gp(data, "url_coverage", "details", "must_cite_hit", default=0)

    cited_stems = {_path_stem(u): u for u in cited_canon}
    golden_stems = {_path_stem(u): u for u in golden_canon.keys()}
    near_miss_keys = set(cited_stems.keys()) & set(golden_stems.keys())
    near_misses = []
    for k in near_miss_keys:
        if cited_stems[k] != golden_stems[k]:
            near_misses.append((cited_stems[k], golden_stems[k]))

    details = {
        "agent_canon_n": len(cited_canon),
        "golden_must_cite_n": len(golden_canon),
        "hits_recomputed": len(direct_hits),
        "scorer_hit": scorer_hit,
        "near_miss_n": len(near_misses),
        "near_miss_examples": near_misses[:2],
    }
    if scorer_hit != len(direct_hits):
        return "DRIFT", details
    if not direct_hits and near_misses:
        return "SUSPECT", details
    return "FAIR", details


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: audit_one_pair.py <score.json>")
        return 0
    arg = sys.argv[1]
    p = Path(arg)
    if not p.is_absolute():
        p = ROOT / p.name
    if not p.exists():
        print(f"BUG missing-file: {p}")
        return 0

    m = PAIR_NAME_RE.match(p.name)
    if not m:
        print(f"BUG schema-name: {p.name}")
        return 0
    agent, task = m.group(1), m.group(2)

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"BUG  {agent} {task}: json-parse {exc}")
        return 0

    ans_path_str = data.get("answer_path")
    ans_path = None
    if isinstance(ans_path_str, str):
        a = Path(ans_path_str)
        if not a.is_absolute():
            a = Path("/opt/deep_reserch") / a
        ans_path = a

    bugs = _structural_bugs(data, ans_path)
    verdict, fdet = _fairness_verdict(data, ans_path, task) if ans_path else ("SKIP", {})

    c2 = _gp(data, "composite", "composite_v2", default=0.0)
    chars = data.get("answer_chars", 0)
    cited = _gp(data, "url_reachability", "details", "cited_total", default=0)
    cl = data.get("checklist") or {}

    runner_failed = False
    if ans_path and ans_path.exists():
        head = ans_path.read_text(encoding="utf-8", errors="replace")[:300]
        if _RUNNER_FAIL_RE.match(head.lstrip()):
            runner_failed = True

    if bugs:
        print(f"BUG  {agent} {task}: " + "; ".join(bugs))
    elif runner_failed:
        c2 = _gp(data, "composite", "composite_v2", default=0.0)
        chars = data.get("answer_chars", 0)
        print(
            f"SKIP {agent} {task}  RUNNER-FAILED  composite_v2={c2:.4f}  chars={chars}  "
            f"(filtered from Elo by leaderboard's _looks_degenerate)"
        )
    elif verdict in ("SUSPECT", "DRIFT"):
        head = (
            f"BUG  {agent} {task}: fairness={verdict} "
            f"hits_recomp={fdet.get('hits_recomputed')} "
            f"scorer_says={fdet.get('scorer_hit')} "
            f"near_miss={fdet.get('near_miss_n')}"
        )
        print(head)
        for am, gm in fdet.get("near_miss_examples", []):
            print(f"    near-miss  agent={am}  golden={gm}")
    else:
        line = (
            f"OK   {agent} {task}  composite_v2={c2:.4f}  chars={chars}  cited={cited}  "
            f"check={cl.get('pass_count', 0)}P/{cl.get('fail_count', 0)}F/{cl.get('unclear_count', 0)}U  "
            f"fair={verdict}({fdet.get('hits_recomputed', 0)}/{fdet.get('golden_must_cite_n', 0)})"
        )
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
