# Paper build. Regenerates data tables, then compiles with tectonic if available,
# else latexmk, else a pdflatex+bibtex sequence. Run from repo root or paper/.
MAIN := main
TABLES := tables/detection_gpt5.tex tables/detection_mini.tex \
          tables/cross_vendor.tex tables/per_fault.tex \
          tables/evidence_restricted.tex tables/paired.tex

.PHONY: all tables clean

all: $(MAIN).pdf

# Auto-generate result tables from the scored run records.
tables:
	cd .. && python paper/gen_tables.py

$(MAIN).pdf: $(MAIN).tex references.bib tables
	@if command -v tectonic >/dev/null 2>&1; then \
		echo "==> building with tectonic"; \
		tectonic $(MAIN).tex; \
	elif command -v latexmk >/dev/null 2>&1; then \
		echo "==> building with latexmk"; \
		latexmk -pdf -bibtex $(MAIN).tex; \
	elif command -v pdflatex >/dev/null 2>&1; then \
		echo "==> building with pdflatex+bibtex"; \
		pdflatex -interaction=nonstopmode $(MAIN).tex; \
		bibtex $(MAIN); \
		pdflatex -interaction=nonstopmode $(MAIN).tex; \
		pdflatex -interaction=nonstopmode $(MAIN).tex; \
	else \
		echo "No LaTeX toolchain found. Install tectonic or use Overleaf."; \
		exit 1; \
	fi

clean:
	rm -f $(MAIN).pdf $(MAIN).aux $(MAIN).log $(MAIN).bbl $(MAIN).blg \
	      $(MAIN).out $(MAIN).fdb_latexmk $(MAIN).fls
