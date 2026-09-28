# rtk-gps-module
#
# This is a normal KiCad project. design/ is the source of truth --
# open it, edit it, save it. Nothing here regenerates or overwrites it.
#
# The targets below are conveniences: run the checks, rebuild the BOM
# from the schematic, re-plot the PDF.

PY    := python3
SCH   := design/rtk-gps-module.kicad_sch
PRO   := design/rtk-gps-module.kicad_pro
KICAD := /Applications/KiCad

.DEFAULT_GOAL := help
.PHONY: help open check erc netlist bom pdf impedance datasheets \
        status hooks unhook clean

help:  ## show this help
	@echo "rtk-gps-module -- a normal KiCad project. Edit design/ directly."
	@echo
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) \
	  | sed 's/:.*##/\t/' | awk -F'\t' '{printf "  \033[1m%-12s\033[0m %s\n",$$1,$$2}'
	@echo
	@echo "  Edit in KiCad, save, then 'make check'."
	@echo "  Nothing in this Makefile writes to design/."

# --------------------------------------------------------------------------
# Working on it
# --------------------------------------------------------------------------

open:  ## open the project in KiCad -- edit and save freely
	@open -a "$(KICAD)/KiCad.app" $(PRO)

check:  ## ERC + netlist + sourcing + impedance. Read-only.
	@$(PY) tools/check.py

bom:  ## rebuild manufacturing/ from the schematic
	@$(PY) tools/gen_bom.py

pdf:  ## re-plot docs/schematic.pdf from the schematic
	@kicad-cli sch export pdf -o docs/schematic.pdf $(SCH) 2>/dev/null >/dev/null
	@echo "  wrote docs/schematic.pdf"

# --------------------------------------------------------------------------
# Looking at it
# --------------------------------------------------------------------------

erc:  ## run ERC and print the report
	@mkdir -p analysis
	@rm -f analysis/erc.rpt
	@kicad-cli sch erc --output analysis/erc.rpt --severity-all \
	  --exit-code-violations $(SCH) 2>/dev/null | tail -2 || true
	@echo "---"; grep -v '^$$' analysis/erc.rpt | tail -20

netlist:  ## print every net with its netclass and pin count
	@mkdir -p analysis
	@kicad-cli sch export netlist --format kicadsexpr \
	  -o analysis/netlist.net $(SCH) >/dev/null 2>&1
	@$(PY) -c "import re; \
t=open('analysis/netlist.net').read(); i=t.index('(nets'); \
rows=[(re.search(r'\(name \"([^\"]*)\"\)',b).group(1), \
       re.search(r'\(class \"([^\"]*)\"\)',b).group(1), \
       len(re.findall(r'\(ref \"', b))) \
      for b in re.split(r'\n\t\t\(net\n', t[i:])[1:]]; \
print(f'{len(rows)} nets'); \
[print(f'  {c:<8} {n:<26} {p:2d} pins') for n,c,p in sorted(rows)]"

impedance:  ## the 50 ohm derivation and its tolerance sweep
	@$(PY) tools/calc_impedance.py

datasheets:  ## fetch the vendor PDFs (not committed -- not ours to ship)
	@$(PY) tools/fetch_datasheets.py

status:  ## git state and whether KiCad has it open
	@git status --short || true
	@echo "locks:  $$(ls design/ 2>/dev/null | grep -c lck) (non-zero = open in KiCad)"
	@echo "synced: $$( [ "$$(git rev-parse HEAD)" = "$$(git rev-parse @{u} 2>/dev/null)" ] \
	  && echo 'yes, matches origin' || echo 'NO -- unpushed or behind' )"

# --------------------------------------------------------------------------

hooks:  ## install a light pre-commit hook (ERC errors only)
	@git config core.hooksPath .githooks
	@chmod +x .githooks/pre-commit
	@echo "  installed. It blocks only on ERC ERRORS, never on warnings."
	@echo "  Remove it any time with 'make unhook'."

unhook:  ## remove the pre-commit hook
	@git config --unset core.hooksPath || true
	@echo "  hook removed; commits are unchecked now."

clean:  ## remove regenerated analysis output and caches
	@rm -rf analysis __pycache__ tools/__pycache__ \
	        tools/bootstrap/__pycache__ design/.history
	@echo "  cleaned. design/ is untouched -- it is the source of truth."
