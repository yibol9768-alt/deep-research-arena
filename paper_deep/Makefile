PAPER = main

.PHONY: pdf clean distclean tables

pdf: tables
	pdflatex -interaction=nonstopmode $(PAPER).tex || true
	bibtex $(PAPER) || true
	pdflatex -interaction=nonstopmode $(PAPER).tex || true
	pdflatex -interaction=nonstopmode $(PAPER).tex

tables:
	python3 generate_tables.py

clean:
	rm -f $(PAPER).aux $(PAPER).log $(PAPER).bbl $(PAPER).blg \
	      $(PAPER).out $(PAPER).toc $(PAPER).synctex.gz

distclean: clean
	rm -f $(PAPER).pdf
	rm -f tables/*.tex
