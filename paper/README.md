# Paper build

LaTeX source for the UDM-Bench paper. Every results table is **auto-generated
from the scored run records** — never hand-edited — so the numbers cannot drift
from the data.

## Regenerate the tables

From the repo root (with the project venv active):

```bash
python paper/gen_tables.py
```

This reads the scored `scorecards.jsonl` files and the committed analysis snapshot
(`analysis/data/`) and writes `paper/tables/*.tex`:

| Table | Source scoring dir(s) |
| --- | --- |
| `detection_gpt5.tex`     | `scoring_results_phase4_gpt5_ab` (A,B) + `scoring_results_phase4_gpt5_cg` (C,G) |
| `detection_mini.tex`     | `scoring_results_phase4` (A,B) + `scoring_results_phase4_v4` (C,G) |
| `cross_vendor.tex`       | gpt-5 multi-vendor faulty missions |
| `per_fault.tex`          | `analysis/data/` — faults found per fault type, with the evidence ceiling |
| `evidence_restricted.tex`| `analysis/data/` — detection on the 16 evidence-bearing faults |
| `paired.tex`             | `analysis/data/` — McNemar (Holm) and paired-bootstrap comparisons |

If the scoring dirs are missing, re-score first, e.g.:

```bash
python -m scoring.score --runs runs_live --results results_phase4_gpt5_ab \
  --out scoring_results_phase4_gpt5_ab
```

## Compile the PDF

Two options:

1. **Overleaf** (no install): upload `paper/` and compile `main.tex`.
2. **tectonic** (single self-contained binary):

   ```bash
   make -C paper        # if tectonic is installed
   ```

## Build with `make`

`make` uses `tectonic` if present, else falls back to `latexmk`/`pdflatex`.
Run `python paper/gen_tables.py` first (or `make tables`).

## Status

Complete draft. Related work is filled in; the related-work and statistics entries
in `references.bib` were added from knowledge of these well-known works and their
page numbers and DOIs should be checked before camera-ready. The single-vs-multi
composition table was dropped from the paper because the two mission sets do not
share a fault mix (see `analysis/multi_vendor_delta.md`).
