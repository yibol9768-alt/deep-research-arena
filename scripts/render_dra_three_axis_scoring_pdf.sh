#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/docs/DRA_THREE_AXIS_SCORING_REDESIGN_2026-07-22.md"
OUTPUT="$ROOT/docs/DRA_THREE_AXIS_SCORING_REDESIGN_2026-07-22.pdf"
ASSETS="$ROOT/docs/pdf"
BUILD_DIR="${DRA_THREE_AXIS_PDF_BUILD_DIR:-/tmp/dra-three-axis-pdf-build}"

for command in python3 xelatex pdfinfo; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 1
  fi
done

mkdir -p "$BUILD_DIR"
rm -f \
  "$BUILD_DIR/dra_three_axis_scoring_pdf.aux" \
  "$BUILD_DIR/dra_three_axis_scoring_pdf.log" \
  "$BUILD_DIR/dra_three_axis_scoring_pdf.out" \
  "$BUILD_DIR/dra_three_axis_scoring_pdf.toc" \
  "$BUILD_DIR/dra_three_axis_scoring_pdf.pdf" \
  "$BUILD_DIR/dra-three-axis-input.md"

cp "$ASSETS/dra_three_axis_scoring_pdf.tex" "$BUILD_DIR/"
cp "$ASSETS/dra-three-axis-architecture.tex" "$BUILD_DIR/"
cp "$ASSETS/dra-three-axis-census.tex" "$BUILD_DIR/"
cp "$ASSETS/dra-three-axis-denominators.tex" "$BUILD_DIR/"

python3 "$ROOT/scripts/build_dra_three_axis_pdf_input.py" \
  --source "$SOURCE" \
  --output "$BUILD_DIR/dra-three-axis-input.md"

export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1784678400}"

for _ in 1 2; do
  (
    cd "$BUILD_DIR"
    xelatex \
      -interaction=nonstopmode \
      -halt-on-error \
      -file-line-error \
      -shell-escape \
      dra_three_axis_scoring_pdf.tex
  )
done

cp "$BUILD_DIR/dra_three_axis_scoring_pdf.pdf" "$OUTPUT"
pdfinfo "$OUTPUT" | sed -n '1,16p'
