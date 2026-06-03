#!/usr/bin/env python3
"""Build a persisted RAG index from a JSONL corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

# Make ``src`` importable when run as a script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.rl.tools_rag import build_rag_index, build_sparse_rag_index


def iter_jsonl(path: Path) -> Iterable[tuple[str, str]]:
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            url = str(row.get("url") or row.get("doc_url") or row.get("id") or "").strip()
            text = str(row.get("text") or row.get("content") or row.get("raw_content") or "")
            if not url:
                raise ValueError(f"{path}:{line_no}: missing url")
            yield url, text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-jsonl", required=True, help="JSONL rows with url/text fields")
    parser.add_argument("--out", required=True, help="Output index directory")
    parser.add_argument("--model", default=None, help="SentenceTransformer model for dense builds")
    parser.add_argument("--chunk-words", type=int, default=220)
    parser.add_argument("--chunk-overlap", type=int, default=40)
    parser.add_argument("--no-dense", action="store_true", help="Build BM25-only chunks/meta, no heavy deps")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    corpus = list(iter_jsonl(Path(args.corpus_jsonl)))
    if args.no_dense:
        out = build_sparse_rag_index(
            corpus,
            args.out,
            chunk_words=args.chunk_words,
            chunk_overlap=args.chunk_overlap,
        )
    else:
        out = build_rag_index(
            corpus,
            args.out,
            model_name=args.model,
            chunk_words=args.chunk_words,
            chunk_overlap=args.chunk_overlap,
        )
    meta_path = Path(out) / "meta.json"
    meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
    print(json.dumps({"out": str(out), **meta}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
