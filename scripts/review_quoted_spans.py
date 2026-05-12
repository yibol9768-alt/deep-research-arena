"""Interactive TUI for reviewing LLM-drafted quoted_span fields in a
deep-tier golden file.

For each triple in the input golden:
  - Show subject / predicate / object
  - Show the LLM-drafted span
  - (Optional) preview the source URL (first ~300 chars of fetched page)
  - Prompt: [k]eep / [r]eject / [e]dit / [s]kip / [p]review / [q]uit-save

The review only touches triples that already have `quoted_span != null`.
Outputs a copy of the golden where each triple gains:
  - quoted_span_meta.reviewed: true | false (false if skipped)
  - quoted_span_meta.accepted: true | false
  - quoted_span_meta.original_span: kept if user edited
  - quoted_span: replaced if edited; null if rejected

Usage:
    python3 scripts/review_quoted_spans.py \\
        --golden data/golden/deep/dr_cross_deep_0001.json \\
        --out    data/golden/deep/dr_cross_deep_0001.reviewed.json

Resume: if --out already exists, the script skips already-reviewed
triples (those with `reviewed=true` in their meta). Just re-run to pick
up where you stopped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _input(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return "q"


def _print_triple(idx: int, total: int, t: dict) -> None:
    print()
    print("─" * 70)
    print(f"  [{idx + 1} / {total}]")
    print(f"  subject:   {t.get('subject', '')[:90]}")
    print(f"  predicate: {t.get('predicate', '')}")
    print(f"  object:    {t.get('object', '')[:90]}")
    print(f"  url:       {t.get('source_url', '')[:90]}")
    span = t.get("quoted_span") or "(no span)"
    print()
    print(f"  span:      {span[:200]}")
    print()


def _preview(url: str) -> None:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("  pip install requests beautifulsoup4")
        return
    try:
        r = requests.get(url, timeout=10, allow_redirects=True,
                         headers={"User-Agent": "review-quotes/1.0"})
        if r.status_code != 200:
            print(f"  page returned {r.status_code}")
            return
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)[:600]
        print(f"  page preview ({len(text)} chars):")
        print(f"    {text}")
    except Exception as e:
        print(f"  preview failed: {type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None,
                    help="cap how many triples to review this run (resume safe)")
    args = ap.parse_args()

    golden_path = Path(args.golden)
    out_path = Path(args.out)
    golden = json.loads(golden_path.read_text())

    if out_path.exists():
        existing = json.loads(out_path.read_text())
        # resume from the partially reviewed file
        golden = existing
        print(f"resuming from {out_path}")

    triples = golden.get("triples", [])

    # only review triples that have a span and are not yet reviewed
    todo = [
        i for i, t in enumerate(triples)
        if t.get("quoted_span") and not (t.get("quoted_span_meta") or {}).get("reviewed")
    ]
    if not todo:
        print("nothing to review (all spans already reviewed or null).")
        return 0

    print(f"to review: {len(todo)} triples"
          + (f" (will stop after {args.limit})" if args.limit else ""))
    print("commands: [k]eep  [r]eject  [e]dit  [s]kip  [p]review  [q]uit&save  [b]ack")
    print()

    cursor = 0
    reviewed_this_run = 0
    while cursor < len(todo):
        if args.limit and reviewed_this_run >= args.limit:
            break
        idx = todo[cursor]
        t = triples[idx]
        _print_triple(cursor, len(todo), t)
        cmd = _input("  > ").strip().lower()

        meta = t.setdefault("quoted_span_meta", {})

        if cmd in ("q", "quit"):
            break
        elif cmd in ("b", "back"):
            cursor = max(0, cursor - 1)
            continue
        elif cmd in ("s", "skip", ""):
            cursor += 1
            continue
        elif cmd in ("p", "preview"):
            _preview(t.get("source_url", ""))
            continue  # don't advance
        elif cmd in ("k", "keep", "y", "yes"):
            meta["reviewed"] = True
            meta["accepted"] = True
            meta["needs_review"] = False
            reviewed_this_run += 1
            cursor += 1
        elif cmd in ("r", "reject", "n", "no"):
            meta["reviewed"] = True
            meta["accepted"] = False
            meta["needs_review"] = False
            meta["original_span"] = t.get("quoted_span")
            t["quoted_span"] = None
            reviewed_this_run += 1
            cursor += 1
        elif cmd in ("e", "edit"):
            new = _input("    new span (≤200 chars, blank to cancel): ").strip()
            if new:
                meta["reviewed"] = True
                meta["accepted"] = True
                meta["edited"] = True
                meta["original_span"] = t.get("quoted_span")
                meta["needs_review"] = False
                t["quoted_span"] = new[:250]
                reviewed_this_run += 1
                cursor += 1
            # else stay on current
        else:
            print(f"  unknown command: {cmd!r}")

        # save after every action
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(golden, indent=2, ensure_ascii=False))

    # final save + summary
    out_path.write_text(json.dumps(golden, indent=2, ensure_ascii=False))

    n_reviewed = sum(1 for t in triples if (t.get("quoted_span_meta") or {}).get("reviewed"))
    n_accepted = sum(1 for t in triples
                     if (t.get("quoted_span_meta") or {}).get("accepted")
                     and t.get("quoted_span"))
    n_edited = sum(1 for t in triples if (t.get("quoted_span_meta") or {}).get("edited"))
    n_rejected = sum(1 for t in triples
                     if (t.get("quoted_span_meta") or {}).get("reviewed")
                     and not (t.get("quoted_span_meta") or {}).get("accepted"))

    print()
    print(f"saved {out_path}")
    print(f"  reviewed this run: {reviewed_this_run}")
    print(f"  reviewed total:    {n_reviewed} / {len(todo) + n_reviewed - reviewed_this_run}")
    print(f"  accepted:          {n_accepted}")
    print(f"  edited:            {n_edited}")
    print(f"  rejected:          {n_rejected}")
    print()
    print("re-run the same command to continue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
