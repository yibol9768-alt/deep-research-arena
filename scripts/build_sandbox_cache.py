#!/usr/bin/env python3
"""Build a frozen snapshot of every cited sandbox page, once.

Scoring fetches each cited sandbox URL many times across ~900 reports, which
overloads Magento. This fetches every DISTINCT cited sandbox URL exactly once
(redirects followed, gentle concurrency) and writes a {url: {status, text}}
cache that src/verifiers/sandbox_http_cache.py serves during scoring. The cache
is a reproducibility artifact: re-scoring reads pages from it, no live Magento.

  python3 scripts/build_sandbox_cache.py            # build/extend the cache
  python3 scripts/build_sandbox_cache.py --workers 6 --timeout 5

Run ON the box with the sandbox up. Resumable: already-cached URLs are skipped.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "results" / "deep"
OUT = ROOT / "data" / "results" / "sandbox_cache.json"
_URL_RE = re.compile(r'https?://localhost:\d+/[^\s)\]"\'>]+')
_LOCK = threading.Lock()


def _kiwix_variant(url: str) -> str | None:
    try:
        from src.verifiers.citation_format import canonicalize_url
        c = canonicalize_url(url)
        return c if c and c != url else None
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--max-text", type=int, default=40000)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    import requests
    sys.path.insert(0, str(ROOT))

    # distinct cited sandbox URLs across all reports
    urls: set[str] = set()
    for md in glob.glob(str(REPORTS / "*__dr_cross_deep_*_matrix.md")):
        try:
            txt = Path(md).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for u in _URL_RE.findall(txt):
            urls.add(u.rstrip(".,;"))
    print(f"distinct sandbox URLs cited: {len(urls)}")

    outp = Path(args.out)
    cache: dict[str, dict] = {}
    if outp.exists():
        try:
            cache = json.loads(outp.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    todo = [u for u in urls if u not in cache]
    print(f"already cached: {len(cache)}; to fetch: {len(todo)}")

    done = [0]
    t0 = time.time()

    def fetch(u: str):
        try:
            r = requests.get(u, timeout=args.timeout, allow_redirects=True,
                             headers={"User-Agent": "dra-cache/1.0"})
            status, text = r.status_code, (r.text or "")[: args.max_text]
            r.close()
            # kiwix /wiki/<id> -> /content/... canonical retry on non-200
            if status != 200:
                v = _kiwix_variant(u)
                if v:
                    r2 = requests.get(v, timeout=args.timeout, allow_redirects=True,
                                      headers={"User-Agent": "dra-cache/1.0"})
                    if r2.status_code == 200:
                        status, text = 200, (r2.text or "")[: args.max_text]
                    r2.close()
        except Exception:
            status, text = 0, ""
        with _LOCK:
            cache[u] = {"status": int(status), "text": text}
            done[0] += 1
            if done[0] % 250 == 0:
                outp.write_text(json.dumps(cache), encoding="utf-8")
                print(f"  {done[0]}/{len(todo)} fetched, {time.time()-t0:.0f}s, cache={len(cache)}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(fetch, todo))

    outp.write_text(json.dumps(cache), encoding="utf-8")
    codes = {}
    for v in cache.values():
        codes[v["status"]] = codes.get(v["status"], 0) + 1
    print(f"wrote {outp} ({len(cache)} urls). status histogram: {dict(sorted(codes.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
