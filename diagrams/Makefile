# Render the Graphviz diagrams to SVG.
#   make            # render all *.dot -> *.svg
#   make clean      # remove generated SVGs
DOTS := $(wildcard *.dot)
SVGS := $(DOTS:.dot=.svg)

all: $(SVGS)

%.svg: %.dot
	dot -Tsvg $< -o $@

clean:
	rm -f $(SVGS)

.PHONY: all clean
