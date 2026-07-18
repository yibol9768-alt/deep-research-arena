#!/usr/bin/env python3
"""Prepare the DRA design Markdown for stable XeLaTeX rendering.

The LaTeX markdown package is good at prose and code blocks, but Markdown
tables become hard to read in a long Chinese document.  This preprocessor
therefore replaces pipe tables with breakable LaTeX longtables and replaces
the three Mermaid diagrams with maintained TikZ equivalents.
"""

from __future__ import annotations

import argparse
import math
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "docs" / "DRA_SANDBOX_NATIVE_SCORING_DESIGN_2026-07-17.md"
DEFAULT_OUT = Path("/tmp/dra-input.md")


def escape_plain(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        # Avoid Markdown consuming TeX's one-character escape before hybrid
        # blocks reach LaTeX (a literal ampersand would become a table tab).
        "&": r"\char38{}",
        "%": r"\char37{}",
        "#": r"\char35{}",
        "_": r"\char95{}",
        "{": r"\char123{}",
        "}": r"\char125{}",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def latex_url(url: str) -> str:
    """Make a URL safe without interpreting percent signs or underscores."""
    return r"\detokenize{" + url.replace("}", "%7D") + "}"


def latex_inline(text: str) -> str:
    """Render the small Markdown subset used inside tables."""
    protected: list[str] = []

    def hold(value: str) -> str:
        key = f"@@DRATOKEN{len(protected)}@@"
        protected.append(value)
        return key

    def code_span(value: str) -> str:
        return r"\texttt{" + escape_plain(value) + "}"

    # Protect constructs before escaping ordinary LaTeX characters.
    text = re.sub(r"`([^`]+)`", lambda m: hold(code_span(m.group(1))), text)
    text = re.sub(r"\$([^$\n]+)\$", lambda m: hold("$" + m.group(1) + "$"), text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: hold(
            r"\href{" + latex_url(m.group(2)) + "}{" + escape_plain(m.group(1)) + "}"
        ),
        text,
    )
    text = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda m: hold(r"\textbf{" + escape_plain(m.group(1)) + "}"),
        text,
    )
    text = escape_plain(text).replace("<br>", r"\newline ")
    for i, value in enumerate(protected):
        text = text.replace(f"@@DRATOKEN{i}@@", value)
    return text


def visual_width(text: str) -> float:
    """Approximate typeset width for allocating fixed longtable columns."""
    # Remove lightweight Markdown decorations before estimating.
    text = re.sub(r"[`*$]", "", text)
    width = 0.0
    for char in text:
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            width += 2.0
        elif char.isspace():
            width += 0.55
        else:
            width += 1.0
    return width


def split_pipe_row(line: str) -> list[str]:
    """Split a pipe-table row, preserving escaped vertical bars."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith(r"\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [cell.strip().replace(r"\|", "|") for cell in cells]


def table_column_widths(rows: list[list[str]], total_cm: float) -> list[float]:
    """Choose readable, bounded widths from the actual table contents."""
    ncols = len(rows[0])
    scores: list[float] = []
    for col in range(ncols):
        values = sorted(visual_width(row[col]) for row in rows)
        p75 = values[min(len(values) - 1, math.floor(0.75 * (len(values) - 1)))]
        peak = values[-1]
        # Square-root compression prevents one prose-heavy cell monopolising a page.
        score = math.sqrt(max(8.0, 0.65 * p75 + 0.35 * peak))
        scores.append(min(13.0, max(3.5, score)))

    widths = [total_cm * score / sum(scores) for score in scores]
    # Keep labels usable and prose columns from becoming slivers.
    min_width = 2.15 if ncols >= 5 else 2.8
    for _ in range(5):
        deficits = [max(0.0, min_width - width) for width in widths]
        deficit = sum(deficits)
        if deficit < 0.01:
            break
        donors = [max(0.0, width - min_width) for width in widths]
        donor_total = sum(donors)
        if donor_total <= deficit:
            break
        widths = [
            max(min_width, width)
            - (deficit * donor / donor_total if donor else 0.0)
            for width, donor in zip(widths, donors)
        ]
    # Correct accumulated rounding in the final column.
    rounded = [round(width, 2) for width in widths]
    rounded[-1] = round(total_cm - sum(rounded[:-1]), 2)
    return rounded


def render_table(block: str, table_number: int) -> str:
    lines = [line for line in block.strip().splitlines() if line.strip()]
    rows = [split_pipe_row(line) for line in lines]
    if len(rows) < 2:
        raise ValueError(f"Table {table_number}: fewer than two rows")
    header = rows[0]
    separator = rows[1]
    data = rows[2:]
    ncols = len(header)
    if not all(len(row) == ncols for row in rows):
        raise ValueError(f"Table {table_number}: inconsistent column count")
    if not all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in separator):
        raise ValueError(f"Table {table_number}: malformed Markdown separator row")
    if not 2 <= ncols <= 9:
        raise ValueError(f"Table {table_number}: unsupported {ncols}-column table")

    # Four-column comparison tables remain readable in portrait.  Very short
    # five/six-column scorecards also fit after wrapping and should not consume
    # an almost empty landscape page; denser wide tables switch to landscape.
    short_scorecard = ncols <= 6 and len(data) <= 3
    landscape = ncols >= 5 and not short_scorecard
    # 23.8 cm leaves room for inter-column padding inside the 26.1 cm
    # landscape text block even for nine-column scorecards.
    total_cm = 23.8 if landscape else (15.75 if ncols >= 5 else 16.25)
    widths = table_column_widths([header, *data], total_cm)
    columns = " ".join(
        rf">{{\raggedright\arraybackslash}}p{{{width:.2f}cm}}" for width in widths
    )

    def row(cells: list[str]) -> str:
        # Markdown treats a trailing double backslash as a hard line break.
        # The explicit command survives the Markdown-to-TeX pass unchanged.
        return " & ".join(latex_inline(cell) for cell in cells) + r" \tabularnewline"

    size = r"\scriptsize" if ncols >= 6 else (r"\footnotesize" if ncols >= 4 else r"\small")
    body = [
        r"\begingroup",
        size,
        r"\setlength{\tabcolsep}{3.5pt}",
        r"\renewcommand{\arraystretch}{1.23}",
        r"\setlength{\LTpre}{0.45\baselineskip}",
        r"\setlength{\LTpost}{0.55\baselineskip}",
    ]
    if landscape:
        body.append(r"\begin{landscape}")
    body.extend(
        [
            rf"\begin{{longtable}}{{{columns}}}",
            r"\toprule",
            row([f"**{cell}**" for cell in header]),
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            row([f"**{cell}**" for cell in header]),
            r"\midrule",
            r"\endhead",
            r"\midrule",
            rf"\multicolumn{{{ncols}}}{{r}}{{\scriptsize 接下页}} \tabularnewline",
            r"\endfoot",
            r"\bottomrule",
            r"\endlastfoot",
        ]
    )
    body.extend(row(cells) for cells in data)
    body.append(r"\end{longtable}")
    if landscape:
        body.append(r"\end{landscape}")
    body.append(r"\endgroup")
    return "\n".join(body)


TABLE_BLOCK = re.compile(r"(?m)(?:^\|.*\|[ \t]*\n){2,}")
MERMAID_BLOCK = re.compile(r"```mermaid\n.*?\n```", re.S)


def preprocess(source: Path, output: Path) -> dict[str, int]:
    text = source.read_text(encoding="utf-8")

    diagram_inputs = [
        r"\input{dra-diagram-world.tex}",
        r"\input{dra-diagram-conflict.tex}",
        r"\input{dra-diagram-state.tex}",
    ]
    diagram_index = 0

    def replace_diagram(_: re.Match[str]) -> str:
        nonlocal diagram_index
        if diagram_index >= len(diagram_inputs):
            raise ValueError(
                "The Markdown contains more Mermaid diagrams than maintained TikZ replacements"
            )
        replacement = diagram_inputs[diagram_index]
        diagram_index += 1
        return replacement

    text = MERMAID_BLOCK.sub(replace_diagram, text)
    if diagram_index != len(diagram_inputs):
        raise ValueError(
            f"Expected {len(diagram_inputs)} Mermaid diagrams, found {diagram_index}"
        )

    table_index = 0

    def replace_table(match: re.Match[str]) -> str:
        nonlocal table_index
        table_index += 1
        return render_table(match.group(0), table_index)

    text = TABLE_BLOCK.sub(replace_table, text)
    output.write_text(text, encoding="utf-8")
    return {
        "diagrams": diagram_index,
        "tables": table_index,
        "lines": len(text.splitlines()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(preprocess(args.source, args.output))


if __name__ == "__main__":
    main()
