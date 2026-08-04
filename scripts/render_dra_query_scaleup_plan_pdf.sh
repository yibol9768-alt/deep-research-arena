#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/docs/DRA_QUERY_AND_SANDBOX_SCALEUP_PLAN_2026-07-30.md"
OUTPUT="$ROOT/docs/DRA_QUERY_AND_SANDBOX_SCALEUP_PLAN_2026-07-30.pdf"
TEMPLATE="$ROOT/docs/pdf/dra_query_scaleup_plan.tex"
BUILD_DIR="${DRA_QUERY_SCALEUP_PDF_BUILD_DIR:-/tmp/dra-query-scaleup-pdf-build}"

for command in xelatex pdfinfo pdftotext; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 1
  fi
done

mkdir -p "$BUILD_DIR"
rm -f \
  "$BUILD_DIR/dra_query_scaleup_plan.aux" \
  "$BUILD_DIR/dra_query_scaleup_plan.log" \
  "$BUILD_DIR/dra_query_scaleup_plan.out" \
  "$BUILD_DIR/dra_query_scaleup_plan.toc" \
  "$BUILD_DIR/dra_query_scaleup_plan.pdf" \
  "$BUILD_DIR/dra-query-scaleup-input.md" \
  "$BUILD_DIR/dra_query_scaleup_plan.tex"

cp "$SOURCE" "$BUILD_DIR/dra-query-scaleup-input.md"
cp "$TEMPLATE" "$BUILD_DIR/dra_query_scaleup_plan.tex"

export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1785369600}"

for _ in 1 2; do
  (
    cd "$BUILD_DIR"
    xelatex \
      -interaction=nonstopmode \
      -halt-on-error \
      -file-line-error \
      -shell-escape \
      dra_query_scaleup_plan.tex
  )
done

cp "$BUILD_DIR/dra_query_scaleup_plan.pdf" "$OUTPUT"

pdfinfo "$OUTPUT" | sed -n '1,16p'
pdftotext "$OUTPUT" - | sed -n '1,80p'
