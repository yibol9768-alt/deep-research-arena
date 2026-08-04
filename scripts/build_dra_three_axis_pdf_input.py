#!/usr/bin/env python3
"""Prepare the standalone DRA three-axis design Markdown for XeLaTeX.

The shared renderer already contains robust conversion of Markdown pipe tables
to breakable LaTeX longtables.  This entry point deliberately performs no
Mermaid substitution: the new document embeds maintained TikZ assets directly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from build_dra_pdf_input import TABLE_BLOCK, render_table


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "DRA_THREE_AXIS_SCORING_REDESIGN_2026-07-22.md"
DEFAULT_OUTPUT = Path("/tmp/dra-three-axis-input.md")


def preprocess(source: Path, output: Path) -> dict[str, int]:
    text = source.read_text(encoding="utf-8")
    table_index = 0

    def replace_table(match):
        nonlocal table_index
        table_index += 1
        return render_table(match.group(0), table_index)

    text = TABLE_BLOCK.sub(replace_table, text)
    output.write_text(text, encoding="utf-8")
    return {"tables": table_index, "lines": len(text.splitlines())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(preprocess(args.source, args.output))


if __name__ == "__main__":
    main()
