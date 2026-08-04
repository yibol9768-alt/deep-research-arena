#!/usr/bin/env python3
"""Prepare the DRA precision-recall decision document for XeLaTeX."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from build_dra_pdf_input import TABLE_BLOCK, escape_plain, render_table


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    ROOT / "docs" / "DRA_SCORING_PRECISION_RECALL_DECISION_2026-08-02.md"
)
DEFAULT_OUTPUT = Path("/tmp/dra-pr-decision-input.md")
MERMAID_BLOCK = re.compile(r"```mermaid\n.*?\n```", re.S)


def breakable_code(value: str) -> str:
    """Render a path-like code span with safe, visible break opportunities."""
    chunks: list[str] = []
    for char in value:
        chunks.append(escape_plain(char))
        if char in "/_.-":
            chunks.append(r"\allowbreak{}")
    return r"\texttt{" + "".join(chunks) + "}"


def preprocess(source: Path, output: Path) -> dict[str, int]:
    text = source.read_text(encoding="utf-8")
    # The installed markdown package enables dollar-math, but treats TeX's
    # \(...\) and \[...\] delimiters as ordinary escaped punctuation.  Normalize
    # those delimiters before Markdown parsing so formulas remain intact.
    text = re.sub(
        r"\\\[(.*?)\\\]",
        lambda match: "$$\n" + match.group(1).strip() + "\n$$",
        text,
        flags=re.S,
    )
    text = re.sub(
        r"\\\(([^\n]*?)\\\)",
        lambda match: "$" + match.group(1) + "$",
        text,
    )
    mermaid_count = len(MERMAID_BLOCK.findall(text))
    if mermaid_count != 1:
        raise ValueError(f"Expected exactly one Mermaid diagram, found {mermaid_count}")
    text = MERMAID_BLOCK.sub(r"\\input{dra-pr-decision-flow.tex}", text)

    table_index = 0

    def replace_table(match):
        nonlocal table_index
        table_index += 1
        return render_table(match.group(0), table_index)

    text = TABLE_BLOCK.sub(replace_table, text)
    # Long reproducibility identifiers are intentionally verbatim in Markdown,
    # but ordinary code spans cannot line-break in TeX. Give paths and hashes
    # breakable PDF renderers without changing the source document.
    text = re.sub(
        r"`([0-9a-f]{64})`",
        lambda match: r"\texttt{\seqsplit{" + match.group(1) + "}}",
        text,
    )
    text = re.sub(
        r"`([^`\n]*(?:/|\.md|\.tsv)[^`\n]*)`",
        lambda match: breakable_code(match.group(1)),
        text,
    )
    # Hybrid Markdown passes ordinary percent signs through to TeX, where they
    # start comments and can swallow list terminators. Tables are already
    # escaped by render_table; protect any remaining prose percentages here.
    text = text.replace("%", r"\char37{}")
    output.write_text(text, encoding="utf-8")
    return {
        "diagrams": mermaid_count,
        "tables": table_index,
        "lines": len(text.splitlines()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(preprocess(args.source, args.output))


if __name__ == "__main__":
    main()
