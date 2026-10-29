#!/usr/bin/env bash
# Build the UDM-Bench paper PDF.
#
# 1. Regenerates every result table from the scored run records (so the numbers
#    in the PDF can never drift from the data).
# 2. Compiles main.tex to main.pdf, preferring tectonic, then latexmk, then a
#    pdflatex+bibtex sequence.
#
# Usage: paper/build.sh   (runs from anywhere)
set -euo pipefail

PAPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$PAPER_DIR/.." && pwd)"
MAIN="main"

# Make a user-local tectonic install discoverable.
export PATH="$HOME/.local/bin:$PATH"

echo "==> Regenerating result tables from scored data"
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON="$REPO_ROOT/.venv/bin/python"
else
  PYTHON="$(command -v python3 || command -v python)"
fi
( cd "$REPO_ROOT" && "$PYTHON" paper/gen_tables.py )

cd "$PAPER_DIR"
echo "==> Compiling $MAIN.tex"
if command -v tectonic >/dev/null 2>&1; then
  tectonic --chatter minimal "$MAIN.tex"
elif command -v latexmk >/dev/null 2>&1; then
  latexmk -pdf -bibtex -interaction=nonstopmode "$MAIN.tex"
elif command -v pdflatex >/dev/null 2>&1; then
  pdflatex -interaction=nonstopmode "$MAIN.tex"
  bibtex "$MAIN" || true
  pdflatex -interaction=nonstopmode "$MAIN.tex"
  pdflatex -interaction=nonstopmode "$MAIN.tex"
else
  echo "ERROR: no LaTeX toolchain found (install tectonic or use Overleaf)." >&2
  exit 1
fi

echo "==> Built $PAPER_DIR/$MAIN.pdf"
