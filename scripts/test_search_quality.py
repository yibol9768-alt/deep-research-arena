#!/usr/bin/env python3
"""Run the small human-reviewed DRA search-quality gate against a live shim."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "data/search_quality/basic_v1.json"


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError(f"non-object JSON from {url}")
    return value


def _contains_all(value: str, needles: list[str]) -> bool:
    folded = value.casefold()
    return all(str(needle).casefold() in folded for needle in needles)


def _grade(case: dict[str, Any], results: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    titles = [str(row.get("title") or "") for row in results]
    urls = [str(row.get("url") or "") for row in results]

    if case.get("expected_empty") is True and results:
        failures.append(f"expected empty, got {len(results)} result(s)")
    if len(results) < int(case.get("min_results", 0)):
        failures.append(
            f"expected at least {case['min_results']} result(s), got {len(results)}"
        )
    if "max_results" in case and len(results) > int(case["max_results"]):
        failures.append(
            f"expected at most {case['max_results']} result(s), got {len(results)}"
        )
    if case.get("top_title_all"):
        if not titles or not _contains_all(titles[0], case["top_title_all"]):
            failures.append(
                f"top title did not contain {case['top_title_all']!r}: "
                f"{titles[0] if titles else '(none)'}"
            )
    if case.get("top_url_contains"):
        needle = str(case["top_url_contains"]).casefold()
        if not urls or needle not in urls[0].casefold():
            failures.append(
                f"top URL did not contain {case['top_url_contains']!r}: "
                f"{urls[0] if urls else '(none)'}"
            )
    for forbidden in case.get("forbidden_title_contains", []):
        bad = [title for title in titles if str(forbidden).casefold() in title.casefold()]
        if bad:
            failures.append(f"forbidden title phrase {forbidden!r}: {bad[0]}")
    alternatives = case.get("required_any_title_all") or []
    if alternatives and not any(
        _contains_all(title, required)
        for required in alternatives
        for title in titles
    ):
        failures.append(
            f"no title satisfied any required term group {alternatives!r}"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    failures = 0
    latencies: list[float] = []
    for case in suite["cases"]:
        payload = {
            "query": case["query"],
            "max_results": int(case.get("request_max_results", 5)),
        }
        if case.get("include_domains"):
            payload["include_domains"] = case["include_domains"]
        started = time.monotonic()
        try:
            response = _post_json(
                args.base_url.rstrip("/") + "/search",
                payload,
                args.timeout,
            )
            elapsed = time.monotonic() - started
            latencies.append(elapsed)
            results = response.get("results") or []
            problems = _grade(case, results)
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            elapsed = time.monotonic() - started
            problems = [f"{type(exc).__name__}: {exc}"]
            results = []
        status = "PASS" if not problems else "FAIL"
        print(
            f"{status}\t{case['id']}\t{elapsed:.3f}s\t"
            f"{len(results)} result(s)"
        )
        for problem in problems:
            print(f"  {problem}")
        failures += bool(problems)

    ordered = sorted(latencies)
    median = ordered[len(ordered) // 2] if ordered else 0.0
    print(
        f"SUMMARY\t{len(suite['cases']) - failures}/{len(suite['cases'])} "
        f"passed\tmedian={median:.3f}s"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
