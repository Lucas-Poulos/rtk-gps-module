# rtk-gps-module
#
# design/ is GENERATED. The source of truth is scripts/.
# Everything you need day to day is a target here -- `make` on its own
# lists them.

PY      := python3
SCH     := design/rtk-gps-module.kicad_sch
PRO     := design/rtk-gps-module.kicad_pro
SCRIPTS := scripts
KICAD   := /Applications/KiCad

# Sheets are all written by one generator run, so they share a stamp file
# rather than each claiming to be an independent target.
GENERATED := $(SCH) $(PRO) design/sym-lib-table design/fp-lib-table
SOURCES   := $(SCRIPTS)/gen_project.py $(SCRIPTS)/wire_sheets.py \
             $(SCRIPTS)/kicad_sch.py $(SCRIPTS)/calc_impedance.py
SYMS      := design/lib/rtk-gps-module.kicad_sym
FPS       := design/lib/rtk-gps-module.pretty

.DEFAULT_GOAL := help
.PHONY: help all regen syms fps sch bom pdf verify erc netlist \
        open status clean hooks guard impedance datasheets

# --------------------------------------------------------------------------

help:  ## show this help
	@echo "rtk-gps-module -- design/ is generated, edit scripts/ instead"
	@echo
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) \
	  | sed 's/:.*##/\t/' | awk -F'\t' '{printf "  \033[1m%-12s\033[0m %s\n",$$1,$$2}'
	@echo
	@echo "  Typical loop:  edit scripts/  ->  make  ->  read the diff"
	@echo "  Before committing, the pre-commit hook runs 'make verify'."
	@echo "  Install it once with 'make hooks'."

all: regen bom pdf verify  ## regenerate everything and run the gate

# --------------------------------------------------------------------------
# Guard: refuse to write under a GUI that has the project open.
#
# A bare `pgrep kicad` is too coarse -- it also fires when the GUI has some
# *other* project open, which is harmless. Only this project's lock files
# mean the design is actually held.
# --------------------------------------------------------------------------
guard:
	@if ls design/*.lck design/~*.lck >/dev/null 2>&1; then \
	  echo "REFUSING: this project is open in KiCad."; \
	  echo "  Close it first -- regenerating underneath the GUI means the"; \
	  echo "  next GUI save writes stale content back over the output."; \
	  ls design/*.lck design/~*.lck 2>/dev/null | sort -u | sed 's/^/    /'; \
	  exit 1; \
	fi

# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

syms: guard  ## rebuild the LC29H and SAW symbols
	@$(PY) $(SCRIPTS)/gen_custom_symbols.py

fps: guard  ## rebuild the LC29H, SAW and castellated footprints
	@$(PY) $(SCRIPTS)/gen_footprints.py

sch: guard  ## rebuild the schematic sheets, placement and wiring
	@$(PY) $(SCRIPTS)/gen_project.py

regen: syms fps sch  ## rebuild all of design/ from scripts/

bom:  ## rebuild manufacturing/BOM.md and the JLCPCB CSV
	@$(PY) $(SCRIPTS)/gen_bom.py

pdf:  ## re-plot docs/schematic.pdf
	@kicad-cli sch export pdf -o docs/schematic.pdf $(SCH) 2>/dev/null \
	  | grep -v '^$$' || true
	@echo "  wrote docs/schematic.pdf"

impedance:  ## show the 50 ohm derivation and its tolerance sweep
	@$(PY) $(SCRIPTS)/calc_impedance.py

datasheets:  ## fetch the vendor PDFs (not committed -- not ours to ship)
	@$(PY) $(SCRIPTS)/fetch_datasheets.py

# --------------------------------------------------------------------------
# Checking
# --------------------------------------------------------------------------

verify:  ## THE GATE -- 146 checks. Run this before every commit.
	@$(PY) $(SCRIPTS)/verify_project.py

erc:  ## run ERC alone and print the report
	@mkdir -p analysis
	@rm -f analysis/erc.rpt
	@kicad-cli sch erc --output analysis/erc.rpt --severity-all \
	  --exit-code-violations $(SCH) 2>/dev/null | tail -2 || true
	@echo "---"; grep -v '^$$' analysis/erc.rpt | tail -20

netlist:  ## export the netlist and print every net with its netclass
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

status:  ## is design/ in step with scripts/ ?
	@echo "git:"
	@git status --short || true
	@echo "locks:  $$(ls design/ 2>/dev/null | grep -c lck) (0 means nothing has it open)"
	@echo "synced: $$( [ "$$(git rev-parse HEAD)" = "$$(git rev-parse @{u} 2>/dev/null)" ] \
	  && echo 'yes, matches origin' || echo 'NO -- unpushed or behind' )"

# --------------------------------------------------------------------------
# Working in the GUI (read-only)
# --------------------------------------------------------------------------

open:  ## open the schematic in KiCad -- READ ONLY, do not save
	@echo "Opening read-only. design/ is generated:"
	@echo "  a GUI save is overwritten by the next 'make regen'."
	@echo "  To change something, edit scripts/ -- see docs/making-changes.md"
	@open -a "$(KICAD)/Schematic Editor.app" $(SCH)

# --------------------------------------------------------------------------

hooks:  ## install the pre-commit hook (runs the gate)
	@git config core.hooksPath .githooks
	@chmod +x .githooks/pre-commit
	@echo "  core.hooksPath -> .githooks"
	@echo "  'git commit' now runs 'make verify' first."

clean:  ## remove regenerated analysis output and caches
	@rm -rf analysis __pycache__ $(SCRIPTS)/__pycache__ design/.history
	@echo "  cleaned analysis/, __pycache__/, design/.history/"
	@echo "  design/ itself is NOT touched -- 'make regen' rebuilds it."
