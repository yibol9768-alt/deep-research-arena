#!/usr/bin/env python3
"""CNV-style three-dimension citation verification (arXiv 2605.06635).

Replicates the evaluation framework of "Cited but Not Verified" (Onweller
et al., 2026; no code release, reimplemented from the paper's definitions)
against our frozen sandbox:

  1. Link Works        deterministic: cached HTTP status of the cited URL
                       (200 = works; 4xx = fabricated in a closed world)
  2. Relevant Content  LLM judge: is the cited page topically aligned with
                       the claim? (binary)
  3. Fact Check        LLM judge: are the facts, numbers, dates, and
                       assertions in the claim supported by the page?
                       SUPPORTED -> 1; CONTRADICTED / ABSENT / UNCERTAIN -> 0

Differences from the paper, by design:
  - Sources come from the frozen sandbox page cache
    (data/results/sandbox_cache.json), not live retrieval, so every
    judgment is replayable byte-for-byte.
  - The judge is a locally served open-weight model (temperature 0),
    no paid API.
  - Backward attribution is simplified: the claim text for a citation is
    the sentence containing it plus up to two preceding uncited sentences
    (capped), which matches the paper's rule for end-of-passage citations.

Usage:
  # verify (produces one JSONL row per citation-claim pair)
  python3 scripts/cnv_citation_verifier.py verify \
      --reports 'data/results/deep/*_matrix.md' \
      --cache data/results/sandbox_cache.json \
      --model local-a-qwen3-8b --out data/results/real/cnv_pairs.jsonl \
      [--max-pairs-per-report 40] [--workers 4] [--limit-reports N]

  # aggregate (per-agent three-dimension table)
  python3 scripts/cnv_citation_verifier.py aggregate \
      --pairs data/results/real/cnv_pairs.jsonl

Checkpointing: rows are appended per pair; resume skips completed
(agent, task, url, claim-hash) keys, tolerating a truncated tail line.
"""

import argparse
import collections
import glob
import hashlib
import html as html_mod
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

NAME_RE = re.compile(r"([^/]+?)__(.+?)_matrix\.md$")
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
SENT_SPLIT = re.compile(r"(?<=[.!?。!?])\s+")
SOURCE_CAP = 5000   # chars of page text shown to the judge (paper: 5,000)
CLAIM_CAP = 700     # chars of claim context

RELEVANT_SYS = (
    "You judge whether a cited web page is topically relevant to a claim "
    "from a research report. Answer with exactly one word: YES if the page "
    "content is about the same subject as the claim, NO otherwise."
)
FACT_SYS = (
    "You fact-check one claim from a research report against the text of "
    "the page it cites. Examine the facts, numbers, dates, names, and "
    "assertions in the claim. Answer with exactly one word:\n"
    "SUPPORTED if the page's content supports or is consistent with the "
    "claim;\nCONTRADICTED if the page disagrees with the claim;\n"
    "ABSENT if the page does not contain the claimed information;\n"
    "UNCERTAIN if you cannot tell."
)


def strip_html(text):
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text or "")
    return WS_RE.sub(" ", html_mod.unescape(TAG_RE.sub(" ", text))).strip()


def claim_for(md, window_start, link_start, link_label):
    """Backward attribution: the citation applies to the sentence carrying
    it plus preceding UNCITED sentences, so the window opens right after
    the previous citation (or 1200 chars back, whichever is nearer)."""
    window = md[max(window_start, link_start - 1200):link_start]
    window = WS_RE.sub(" ", window)
    sents = SENT_SPLIT.split(window)
    keep = sents[-3:] if len(sents) >= 3 else sents
    claim = (" ".join(keep) + " " + link_label).strip()
    return claim[-CLAIM_CAP:]


def extract_pairs(md_text):
    """(claim, url) pairs from a markdown report, deduplicated."""
    seen = set()
    out = []
    prev_end = 0
    for m in LINK_RE.finditer(md_text):
        label, url = m.group(1), m.group(2).rstrip(".,;")
        claim = claim_for(md_text, prev_end, m.start(), label)
        prev_end = m.end()
        key = (url, hashlib.md5(claim.encode()).hexdigest()[:12])
        if key in seen:
            continue
        seen.add(key)
        out.append({"claim": claim, "url": url, "claim_hash": key[1]})
    return out


def judge_env(base_url):
    os.environ["JUDGE_PROVIDER"] = "openai"
    os.environ["OPENAI_BASE_URL"] = base_url
    os.environ["OPENAI_API_KEY"] = "local"
    os.environ.pop("JUDGE_BASE_URL", None)
    os.environ.pop("DASHSCOPE_API_KEY", None)


def one_word(text, allowed):
    for w in allowed:
        if re.search(rf"\b{w}\b", text or "", re.I):
            return w
    return None


def cmd_verify(args):
    judge_env(args.base_url)
    from src.verifiers.judge_client import call_judge

    cache = json.loads(Path(args.cache).read_text())
    reports = sorted(glob.glob(args.reports))
    if args.limit_reports:
        reports = reports[: args.limit_reports]

    done = set()
    outp = Path(args.out)
    if outp.exists():
        for line in open(outp):
            try:
                r = json.loads(line)
                done.add((r["agent"], r["task"], r["url"], r["claim_hash"]))
            except Exception:
                pass

    # probe the judge before spending any work
    t, err = call_judge("Health check.", "Reply with the word OK.",
                        model=args.model, max_tokens=8)
    if t is None:
        print(f"FATAL: judge probe failed: {err}")
        sys.exit(2)

    todo = []
    for path in reports:
        m = NAME_RE.search(path)
        if not m:
            continue
        agent, task = m.group(1), m.group(2)
        pairs = extract_pairs(Path(path).read_text(errors="replace"))
        if args.max_pairs_per_report and len(pairs) > args.max_pairs_per_report:
            # deterministic thinning: stable stride sample keeps head+tail
            step = len(pairs) / args.max_pairs_per_report
            pairs = [pairs[int(i * step)] for i in range(args.max_pairs_per_report)]
        for p in pairs:
            if (agent, task, p["url"], p["claim_hash"]) not in done:
                todo.append((agent, task, p))
    print(f"reports={len(reports)} pairs todo={len(todo)} done={len(done)}")

    lock = threading.Lock()
    fout = open(outp, "a")
    n = [0]

    def work(item):
        agent, task, p = item
        entry = cache.get(p["url"]) or {}
        status = int(entry.get("status") or 0)
        row = {"agent": agent, "task": task, "url": p["url"],
               "claim_hash": p["claim_hash"], "claim": p["claim"][:300],
               "link_works": 1 if status == 200 else 0, "status": status,
               "relevant": None, "fact": None, "fact_raw": None}
        if status == 200:
            page = strip_html(entry.get("text") or "")[:SOURCE_CAP]
            if page:
                user = f"CLAIM:\n{p['claim']}\n\nPAGE CONTENT:\n{page}"
                r1, _ = call_judge(RELEVANT_SYS, user, model=args.model, max_tokens=8)
                row["relevant"] = 1 if one_word(r1, ["YES", "NO"]) == "YES" else (
                    0 if one_word(r1, ["YES", "NO"]) == "NO" else None)
                r2, _ = call_judge(FACT_SYS, user, model=args.model, max_tokens=8)
                v = one_word(r2, ["SUPPORTED", "CONTRADICTED", "ABSENT", "UNCERTAIN"])
                row["fact_raw"] = v
                row["fact"] = 1 if v == "SUPPORTED" else (0 if v else None)
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, it) for it in todo]
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception as e:
                continue
            with lock:
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                n[0] += 1
                if n[0] % 100 == 0:
                    print(f"{n[0]}/{len(todo)}", flush=True)
    print(f"verify done: {n[0]} new pairs")


def cmd_aggregate(args):
    rows = []
    for line in open(args.pairs):
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    by_agent = collections.defaultdict(list)
    for r in rows:
        by_agent[r["agent"]].append(r)
    print(f"{'agent':26s} {'pairs':>6s} {'link%':>7s} {'relev%':>7s} "
          f"{'fact%':>7s} {'contra':>6s} {'absent':>6s}")
    for agent in sorted(by_agent):
        rs = by_agent[agent]
        link = sum(r["link_works"] for r in rs) / len(rs)
        rel = [r["relevant"] for r in rs if r["relevant"] is not None]
        fac = [r["fact"] for r in rs if r["fact"] is not None]
        raw = collections.Counter(r.get("fact_raw") for r in rs)
        print(f"{agent:26s} {len(rs):6d} {100*link:6.1f}% "
              f"{100*sum(rel)/len(rel) if rel else float('nan'):6.1f}% "
              f"{100*sum(fac)/len(fac) if fac else float('nan'):6.1f}% "
              f"{raw.get('CONTRADICTED', 0):6d} {raw.get('ABSENT', 0):6d}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--reports", required=True, help="glob of *_matrix.md")
    v.add_argument("--cache", required=True)
    v.add_argument("--model", required=True)
    v.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    v.add_argument("--out", required=True)
    v.add_argument("--workers", type=int, default=4)
    v.add_argument("--max-pairs-per-report", type=int, default=0)
    v.add_argument("--limit-reports", type=int, default=0)
    a = sub.add_parser("aggregate")
    a.add_argument("--pairs", required=True)
    args = ap.parse_args()
    if args.cmd == "verify":
        cmd_verify(args)
    else:
        cmd_aggregate(args)


if __name__ == "__main__":
    main()
