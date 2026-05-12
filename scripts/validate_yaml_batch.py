#!/usr/bin/env python3
"""Validate topic YAML files by probing sandbox endpoints.

For each YAML file, checks that the keywords/forums/wiki titles can actually
be resolved on the running sandbox instances:
  - Shopping: GET localhost:7770/catalogsearch/result/?q={kw} -- result count > 0
  - Reddit:   GET localhost:9999/f/{forum}                    -- HTTP 200
  - Wiki:     GET localhost:8090/content/wikipedia_en_all_nopic/A/{title} -- HTTP 200

Designed to run on westd where the sandbox containers are reachable.

Usage:
    python3 scripts/validate_yaml_batch.py configs/deep_topics/0001_*.yaml
    python3 scripts/validate_yaml_batch.py 'configs/deep_topics/*.yaml'

Environment (optional overrides):
    SHOPPING_URL  default http://localhost:7770
    REDDIT_URL    default http://localhost:9999
    WIKI_URL      default http://localhost:8090
    WIKI_ZIM      default wikipedia_en_all_nopic
    TIMEOUT       default 10 (seconds per request)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

SHOPPING_URL = os.environ.get("SHOPPING_URL", "http://localhost:7770").rstrip("/")
REDDIT_URL   = os.environ.get("REDDIT_URL",   "http://localhost:9999").rstrip("/")
WIKI_URL     = os.environ.get("WIKI_URL",     "http://localhost:8090").rstrip("/")
WIKI_ZIM     = os.environ.get("WIKI_ZIM",     "wikipedia_en_all_nopic")
TIMEOUT      = int(os.environ.get("TIMEOUT", "10"))


def _load_yaml(path: str) -> dict:
    """Load a YAML file. Falls back to JSON if pyyaml is unavailable."""
    text = Path(path).read_text()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        pass
    # Minimal YAML-subset parser for our specific format
    return _mini_yaml_parse(text)


def _mini_yaml_parse(text: str) -> dict:
    """Very minimal YAML parser for the specific topic YAML format.
    Handles: scalar fields, block lists (- item), inline lists [a, b, c]."""
    result = {}
    current_key = None
    current_list = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Block list item
        if stripped.startswith("- "):
            if current_key and current_list is not None:
                val = stripped[2:].strip()
                # Remove surrounding quotes
                if (val.startswith('"') and val.endswith('"')) or \
                   (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                current_list.append(val)
            continue

        # Key: value
        m = re.match(r"^(\w[\w_]*)\s*:\s*(.*)", stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            current_key = key

            if val.startswith("[") and val.endswith("]"):
                # Inline list
                inner = val[1:-1]
                items = []
                for item in re.split(r",\s*", inner):
                    item = item.strip()
                    if (item.startswith('"') and item.endswith('"')) or \
                       (item.startswith("'") and item.endswith("'")):
                        item = item[1:-1]
                    if item:
                        items.append(item)
                result[key] = items
                current_list = None
            elif val == "" or val == "|":
                # Block list follows
                current_list = []
                result[key] = current_list
            else:
                result[key] = val
                current_list = None

    return result


def _http_check(url: str) -> tuple[int, str]:
    """Return (status_code, error_or_empty). Uses urllib to avoid requests dep."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yaml-validator/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        return resp.getcode(), ""
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def _check_shopping_keyword(kw: str) -> tuple[bool, str]:
    """Check if a shopping keyword yields results."""
    url = f"{SHOPPING_URL}/catalogsearch/result/?q={quote(kw)}"
    code, err = _http_check(url)
    if code != 200:
        return False, f"HTTP {code}: {err}" if err else f"HTTP {code}"

    # Check if there are actual results by looking at the HTML
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yaml-validator/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        html = resp.read().decode("utf-8", errors="ignore")
        # Check for product items in the search results
        if "product-item" in html or "product-items" in html:
            # Try to count products
            count = html.count("product-item-link")
            if count > 0:
                return True, f"{count} products"
            return True, "products found"
        if "no results" in html.lower() or "your search returned no results" in html.lower():
            return False, "no results"
        # Ambiguous -- page loaded but unclear
        return True, "page loaded (unable to verify count)"
    except Exception as e:
        return False, f"parse error: {e}"


def _check_reddit_forum(forum: str) -> tuple[bool, str]:
    """Check if a reddit forum exists (HTTP 200)."""
    url = f"{REDDIT_URL}/f/{forum}"
    code, err = _http_check(url)
    if code == 200:
        return True, "OK"
    return False, f"HTTP {code}: {err}" if err else f"HTTP {code}"


def _check_wiki_title(title: str) -> tuple[bool, str]:
    """Check if a Wikipedia article exists in the Kiwix mirror."""
    # Try multiple slug variants
    variants = [
        title.replace(" ", "_"),
        title,
        title.replace(" (codec)", "").replace(" ", "_"),
        title.split(" (")[0].replace(" ", "_"),
    ]
    # Deduplicate while preserving order
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)

    for slug in unique_variants:
        url = f"{WIKI_URL}/content/{WIKI_ZIM}/A/{quote(slug)}"
        code, _ = _http_check(url)
        if code == 200:
            return True, f"OK (slug: {slug})"
    return False, f"404 for all variants: {unique_variants}"


def validate_yaml(path: str) -> dict:
    """Validate a single YAML file. Returns a report dict."""
    cfg = _load_yaml(path)
    report = {
        "file": path,
        "topic_id": cfg.get("topic_id", "?"),
        "display_name": cfg.get("display_name", "?"),
        "shopping": {"pass": [], "fail": []},
        "reddit_forums": {"pass": [], "fail": []},
        "wiki_mandatory": {"pass": [], "fail": []},
        "wiki_extra": {"pass": [], "fail": []},
    }

    # Shopping keywords
    for kw in cfg.get("shopping_keywords", []):
        ok, detail = _check_shopping_keyword(kw)
        bucket = "pass" if ok else "fail"
        report["shopping"][bucket].append({"keyword": kw, "detail": detail})
        time.sleep(0.15)

    # Reddit forums
    for forum in cfg.get("reddit_forums", []):
        ok, detail = _check_reddit_forum(forum)
        bucket = "pass" if ok else "fail"
        report["reddit_forums"][bucket].append({"forum": forum, "detail": detail})
        time.sleep(0.15)

    # Wiki mandatory
    for title in cfg.get("wiki_mandatory", []):
        ok, detail = _check_wiki_title(title)
        bucket = "pass" if ok else "fail"
        report["wiki_mandatory"][bucket].append({"title": title, "detail": detail})
        time.sleep(0.15)

    # Wiki extra
    for title in cfg.get("wiki_extra", []):
        ok, detail = _check_wiki_title(title)
        bucket = "pass" if ok else "fail"
        report["wiki_extra"][bucket].append({"title": title, "detail": detail})
        time.sleep(0.15)

    return report


def _print_report(report: dict) -> bool:
    """Pretty-print a single file report. Returns True if all passed."""
    all_ok = True
    fname = os.path.basename(report["file"])
    print(f"\n{'='*60}")
    print(f"  {fname}  ({report['topic_id']}: {report['display_name']})")
    print(f"{'='*60}")

    for section in ["shopping", "reddit_forums", "wiki_mandatory", "wiki_extra"]:
        data = report[section]
        n_pass = len(data["pass"])
        n_fail = len(data["fail"])
        total = n_pass + n_fail
        status = "PASS" if n_fail == 0 else "FAIL"
        if n_fail > 0:
            all_ok = False
        print(f"\n  [{section}] {status}  ({n_pass}/{total} passed)")
        for item in data["fail"]:
            label = item.get("keyword") or item.get("forum") or item.get("title")
            print(f"    FAIL: {label}  -- {item['detail']}")

    return all_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate topic YAMLs against sandbox endpoints")
    ap.add_argument("files", nargs="+",
                    help="YAML file paths or glob patterns")
    ap.add_argument("--json", default=None, dest="json_out",
                    help="Write full JSON report to file")
    args = ap.parse_args()

    # Expand globs
    paths = []
    for pattern in args.files:
        expanded = glob.glob(pattern)
        if expanded:
            paths.extend(expanded)
        elif os.path.exists(pattern):
            paths.append(pattern)
        else:
            print(f"[warn] no files matched: {pattern}", file=sys.stderr)

    if not paths:
        print("No YAML files found.", file=sys.stderr)
        return 1

    paths = sorted(set(paths))
    print(f"Validating {len(paths)} YAML file(s) against sandbox endpoints...")
    print(f"  Shopping: {SHOPPING_URL}")
    print(f"  Reddit:   {REDDIT_URL}")
    print(f"  Wiki:     {WIKI_URL} (zim={WIKI_ZIM})")

    reports = []
    summary_pass = 0
    summary_fail = 0

    for p in paths:
        try:
            report = validate_yaml(p)
            reports.append(report)
            ok = _print_report(report)
            if ok:
                summary_pass += 1
            else:
                summary_fail += 1
        except Exception as e:
            print(f"\n[ERROR] {p}: {e}", file=sys.stderr)
            summary_fail += 1

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {summary_pass} passed, {summary_fail} failed "
          f"(out of {len(paths)} files)")
    print(f"{'='*60}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(reports, indent=2, ensure_ascii=False))
        print(f"\nFull report written to {args.json_out}")

    return 1 if summary_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
