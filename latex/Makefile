TEX     := findings
BIB     := refs
BUILD   := build
LATEX   := pdflatex -interaction=nonstopmode -halt-on-error -output-directory=$(BUILD)
BIBTEX  := bibtex
TABLES  := tables/length.tex tables/halluc.tex tables/irt.tex

.PHONY: pdf clean tables all distclean

pdf: $(TEX).pdf

all: tables pdf

tables:
	python3 generate_tables.py

$(BUILD):
	mkdir -p $(BUILD)

$(TABLES): generate_tables.py
	python3 generate_tables.py

$(TEX).pdf: $(TEX).tex $(BIB).bib $(TABLES) | $(BUILD)
	$(LATEX) $(TEX).tex
	cd $(BUILD) && BIBINPUTS=..: $(BIBTEX) $(TEX) || true
	$(LATEX) $(TEX).tex
	$(LATEX) $(TEX).tex
	cp $(BUILD)/$(TEX).pdf ./

clean:
	rm -rf $(BUILD)

distclean: clean
	rm -f $(TEX).pdf tables/*.tex

# Fast incremental: assumes no bib changes
quick: | $(BUILD)
	$(LATEX) $(TEX).tex
	cp $(BUILD)/$(TEX).pdf ./
