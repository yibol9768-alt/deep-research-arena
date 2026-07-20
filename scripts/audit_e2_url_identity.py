#!/usr/bin/env python3
"""Audit source and served-URL identity before an E2 content build.

This pass reads only ZIM directory entries.  It deliberately does not read
article bodies, so a bad identity projection is rejected before an expensive
W100K, W1M, or Wfull compilation starts.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compile_e2_wikimedia_backbone import (
    selected_for_view,
    view_contract,
)
from scripts.export_e1_shard_sources import (
    DEFAULT_SNAPSHOT,
    DEFAULT_ZIM,
    WIKI_URL_IDENTITY_VERSION,
    wiki_canonical_url,
)
from src.world_index.e1 import canonical_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zim", type=Path, default=DEFAULT_ZIM)
    parser.add_argument(
        "--view", choices=("w100k", "w1m", "wfull"), default="wfull"
    )
    parser.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--scan-limit", type=int)
    parser.add_argument("--max-examples", type=int, default=20)
    parser.add_argument("--progress-every", type=int, default=1_000_000)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.scan_limit is not None and args.scan_limit <= 0:
        raise SystemExit("--scan-limit must be positive")
    if args.max_examples < 0:
        raise SystemExit("--max-examples must be non-negative")
    if args.progress_every <= 0:
        raise SystemExit("--progress-every must be positive")

    try:
        from libzim.reader import Archive
    except ImportError as exc:
        raise SystemExit("python3-libzim is required") from exc

    archive = Archive(args.zim.resolve())
    namespace_scheme = bool(archive.has_new_namespace_scheme)
    population = int(archive.entry_count)
    scan_end = population
    if args.scan_limit is not None:
        scan_end = min(scan_end, args.scan_limit)
    contract = view_contract(args.view, population)

    source_seen: dict[str, int] = {}
    url_seen: dict[str, tuple[int, str]] = {}
    source_collisions = 0
    url_collisions = 0
    selected = 0
    examples: list[dict[str, Any]] = []
    path_shapes: Counter[str] = Counter()

    for index in range(scan_end):
        entry = archive._get_entry_by_id(index)
        path = str(entry.path)
        if not selected_for_view(
            snapshot_id=args.snapshot_id,
            source_id=path,
            contract=contract,
        ):
            continue
        selected += 1
        if path.startswith("-/"):
            path_shapes["leading_dash_prefix"] += 1
        elif len(path) >= 2 and path[1] == "/":
            path_shapes["explicit_prefix"] += 1
        elif path.startswith("/"):
            path_shapes["leading_slash"] += 1
        else:
            path_shapes["unprefixed"] += 1

        previous_source = source_seen.get(path)
        if previous_source is not None:
            source_collisions += 1
            if len(examples) < args.max_examples:
                examples.append({
                    "kind": "source_id",
                    "identity": path,
                    "first": {"index": previous_source},
                    "second": {
                        "index": index,
                        "path": path,
                        "title": str(entry.title),
                    },
                })
        else:
            source_seen[path] = index

        url = wiki_canonical_url(
            path,
            has_new_namespace_scheme=namespace_scheme,
        )
        previous_url = url_seen.get(url)
        if previous_url is not None:
            url_collisions += 1
            if len(examples) < args.max_examples:
                first_index, first_path = previous_url
                examples.append({
                    "kind": "canonical_url",
                    "identity": url,
                    "first": {
                        "index": first_index,
                        "path": first_path,
                    },
                    "second": {
                        "index": index,
                        "path": path,
                        "title": str(entry.title),
                    },
                })
        else:
            url_seen[url] = (index, path)

        if (index + 1) % args.progress_every == 0:
            print(
                f"[e2-identity] scanned={index + 1}/{scan_end} "
                f"selected={selected} url_collisions={url_collisions}",
                file=sys.stderr,
                flush=True,
            )

    result = {
        "schema": "dra_e2_url_identity_audit_v1",
        "zim": str(args.zim.resolve()),
        "zim_uuid": str(archive.uuid),
        "has_new_namespace_scheme": namespace_scheme,
        "url_identity_version": WIKI_URL_IDENTITY_VERSION,
        "view": contract.as_dict(),
        "scan_end": scan_end,
        "selected": selected,
        "unique_source_ids": len(source_seen),
        "unique_canonical_urls": len(url_seen),
        "source_id_collisions": source_collisions,
        "canonical_url_collisions": url_collisions,
        "path_shapes": dict(sorted(path_shapes.items())),
        "examples": examples,
        "passed": source_collisions == 0 and url_collisions == 0,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(canonical_json(result))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
