#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/docs/DRA_SCORING_PRECISION_RECALL_DECISION_2026-08-02.md"
OUTPUT="$ROOT/docs/DRA_SCORING_PRECISION_RECALL_DECISION_2026-08-02.pdf"
ASSETS="$ROOT/docs/pdf"
BUILD_DIR="${DRA_PR_DECISION_PDF_BUILD_DIR:-/tmp/dra-pr-decision-pdf-build}"

for command in python3 xelatex pdfinfo; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 1
  fi
done

mkdir -p "$BUILD_DIR"
rm -f \
  "$BUILD_DIR/dra_pr_decision_pdf.aux" \
  "$BUILD_DIR/dra_pr_decision_pdf.log" \
  "$BUILD_DIR/dra_pr_decision_pdf.out" \
  "$BUILD_DIR/dra_pr_decision_pdf.toc" \
  "$BUILD_DIR/dra_pr_decision_pdf.pdf" \
  "$BUILD_DIR/dra-pr-decision-input.md"

cp "$ASSETS/dra_pr_decision_pdf.tex" "$BUILD_DIR/"
cp "$ASSETS/dra-pr-decision-flow.tex" "$BUILD_DIR/"

python3 "$ROOT/scripts/build_dra_pr_decision_pdf_input.py" \
  --source "$SOURCE" \
  --output "$BUILD_DIR/dra-pr-decision-input.md"

export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1785657600}"

for _ in 1 2; do
  (
    cd "$BUILD_DIR"
    xelatex \
      -interaction=nonstopmode \
      -halt-on-error \
      -file-line-error \
      -shell-escape \
      dra_pr_decision_pdf.tex
  )
done

cp "$BUILD_DIR/dra_pr_decision_pdf.pdf" "$OUTPUT"
pdfinfo "$OUTPUT" | sed -n '1,16p'
