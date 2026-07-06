# Render the Graphviz diagrams to SVG, in a light and a dark theme.
#   make            # render all *.dot -> *.svg (light) and *-dark.svg (dark)
#   make clean      # remove generated SVGs
#
# The dark theme is derived from the same .dot via sed: only the "chrome"
# (page background, cluster backgrounds, borders, floating label colors)
# changes; the coloured node fills stay the same.
DOTS  := $(wildcard *.dot)
LIGHT := $(DOTS:.dot=.svg)
DARK  := $(DOTS:.dot=-dark.svg)

all: $(LIGHT) $(DARK)

%.svg: %.dot
	dot -Tsvg $< -o $@

%-dark.svg: %.dot
	sed -e 's/bgcolor="white"/bgcolor="#0d1117"/' \
	    -e 's/bgcolor="#fbfbfb"/bgcolor="#161b22"/' \
	    -e 's/color="#b0bec5"/color="#30363d"; fontcolor="#adbac7"/' \
	    -e 's/color="#78909c"/color="#8b949e", fontcolor="#adbac7"/' \
	    -e 's/fontcolor="#607d8b"/fontcolor="#8b949e"/' $< | dot -Tsvg -o $@

clean:
	rm -f *.svg

.PHONY: all clean
