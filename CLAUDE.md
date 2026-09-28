# rtk-gps-module — Session Briefing

## What this is

A cheap solder-down RTK GNSS module: Quectel **LC29H (DA)** dual-band
L1+L5 RTK rover, a fully discrete 50 Ω antenna front end, USB-C via CH340N,
and 24 castellated pads on 1.27 mm. Corrections (RTCM3) arrive from the
host over UART1 — **there is no radio on the board**.

**Schematic is complete, wired, ERC-clean at 0 violations with ERC proven
live on the sub-sheets. PCB layout has not started.**

| Item | Choice | Why |
|---|---|---|
| Receiver | `LC29HDAMD` (`C20748061`) | cheapest LCSC part with a real onboard RTK engine |
| SAW | `B39162B8389P810` (`C5556161`) | **dual-band** L1+L5, the one Quectel's own reference names |
| LDO | `AP2112K-3.3` (`C23380830`) | 55 dB PSRR; a buck's ripple lands in the GNSS band |
| USB | `CH340N` (`C2977777`) | no crystal, < $0.60 |
| ORing | 2 × `BAT54C` | one part = two Schottkys = one OR, for 5 V and for backup |
| Ant. switch | `AO3401A` + `MMBT3904` | ANT_ON is 2.8 V, the PMOS gate needs 3.3 V |
| Ant. ESD | `RF1256-000` (`C207186`) | **0.25 pF** — an ordinary ESD diode shunts the antenna away |

Cost: **$27.10/board at qty 1**, of which the receiver is **88 %**.
Nothing else is worth optimising.

---

## Ground rules

### design/ is generated — edit the scripts, not the output

```bash
make all      # regen + bom + pdf + gate. This is the whole loop.
make verify   # the gate alone -- ALWAYS finish with this
make          # list every target
```

`make regen` depends on `guard`, which refuses to write while **this**
project has lock files in `design/`. A bare `pgrep kicad` is too coarse —
it also fires when the GUI has some other project open, which is harmless.

`.githooks/pre-commit` (install with `make hooks`) runs the gate on any
commit touching `scripts/` or `design/`, then blocks if regeneration
changed `design/` — so the tree pushed always matches the scripts pushed.
Recipes for common edits are in `docs/making-changes.md`.

Generators use `uuid5`, so re-running produces byte-identical files.
**Opening the project read-only is fine. Saving from the GUI is not.**

### Never invent an LCSC part number

Every `Cxxxxx` in `gen_project.py`'s `SOURCING` / `PASSIVES` was resolved
against the live catalogue with the `lcsc` skill on 2026-09-28.
`gen_project.check()` refuses to write if a fitted part lacks one, and
`verify_project.py` re-checks. If you cannot resolve a part, leave it
absent and let the gate fail — do not guess.

### A clean ERC is a claim that needs proving

`kicad-cli` writes **no report at all** when the schematic fails to parse,
and says so only on stdout — so a stale report from an earlier run reads
exactly like a pass. `check_erc()` deletes the report, re-runs, asserts the
file exists, and asserts its mtime is from this run.

This was proven end-to-end by injecting a fault (removing `C204`'s ground)
and confirming ERC reported `pin_not_connected` on sheet `/GNSS/`. If you
change the wiring substantially, do that again.

---

## Things that are easy to get wrong here

### The LC29H (DA) pinout contradicts itself in its own datasheet

Figure 4 (page 25) groups `(AA, AI, BS, DA)` in a column showing pins 15–19
as RESERVED. Table 6's RESERVED row says in prose that for
`(AA, AI, BA, BS, CA, DA)` those pins **are** D_SEL1/2, TXD2/RXD2 and I2C.

The V1.3 revision history settles it: its only pin change is seven pins
moved to RESERVED **for LC29H (EA) only**. The tell is pin 20, printed
`TXD1/SPI_MISO  TXD1/SPI_MISO  TXD1` — the revision history proves the
bare `TXD1` is the EA entry, so the figure's label columns are *mirrored*
on the right-hand edge (outermost column = EA on both sides).

The symbol follows Table 6. Because the reading is contested, pins 15, 16,
18 and 19 reach the castellated edge **only through DNP links**, so the
board is right either way. Do not "clean that up".

### Pin 7 (VDD_EXT) and pin 9 (VDD_RF) are OUTPUTS

Table 6 types them `PO`. Both are typed `power_out` in the symbol so ERC
rejects driving them. VDD_EXT is **2.8 V, 100 mA max** — tying it to 3V3
would be a short between two regulators. `verify_project.py` asserts
`U201.7` is not on `+3V3`.

### D_SEL1/D_SEL2 are a 1.8 V domain

VIHmax is **2.1 V**. They cannot be strapped to VDD_EXT (2.8 V) or 3V3.
The default `0,0` selects UART1 via internal 75 kΩ pulldowns, which is what
this board wants, so the fitted build has no strapping parts. `R206`/`R207`
are DNP links to a 1.9 V node divided from VDD_EXT by 4.7 k/10 k.

### RXD1 tops out at 3.08 V

A 3.3 V host exceeds it. `R205`/`R212` (1 k/10 k) divide to 3.0 V. The
divider sits **at the module pin**, not at each source, so it protects the
castellated pad and the CH340N with one pair of resistors.

### Pins 2, 4, 17 are RESERVED and must float

Table 6: *"must be left N/C and cannot be connected to power or GND."*
Typed `no_connect` so ERC enforces it; `verify_project.py` asserts each
lands on its own `unconnected-` net.

### Duplicated pins that the netlister does not merge for you

- **USBLC6-2SC6**: pins 1 **and** 6 are `I/O1`; 3 **and** 4 are `I/O2`.
  One node in silicon, two pins to KiCad. Wire both or the data lines go
  open at the connector.
- **USB-C**: VBUS is A4/A9/B4/B9 and GND is A1/A12/B1/B12. All eight are
  wired — leaving the B side open works right way up and fails inverted.
- **BAT54C**: pins 1 and 2 are the anodes, **pin 3 is the common cathode**.
- **LEDs and diodes**: KiCad draws **pin 1 = cathode**.

### KiCad netclass patterns are wildcards, not regex

`/^(ANT_RF|RF_A)$/` is accepted by the file format, shows up in the GUI,
and **matches nothing** — the 50 Ω line silently falls back to the default
track width. Local nets also carry their sheet path (`/RF/ANT_RF`), so
those patterns need a leading `*`.

This bit this project once already. `verify_project.py` now reads the
**exported per-net class** back and asserts it, which is the only way to
catch it.

### An L1-only SAW would delete the RTK

Most 1575.42 MHz GNSS SAWs on LCSC are single-band and look like drop-in
substitutes. Fitting one removes L5 and with it the dual-frequency
ionosphere cancellation. Same trap on the ESD diode: the part is chosen for
its **0.25 pF**, not its clamp voltage.

### The SAW's ports are 50 Ω ∥ 5.1 nH

Not 50 Ω. `L302`/`L303` are the shunt inductors that make that true.
Omitting them leaves the filter mismatched at both ports — it still passes
signal, so the mistake survives bring-up and shows up only as lost
sensitivity.

---

## The impedance number is derived, not chosen

`scripts/calc_impedance.py` solves the conductor-backed CPW conformal-
mapping model for JLCPCB's JLC04161H-3313 stackup and exports
`RF_TRACE_W = 0.38` mm (50.19 Ω at a 0.2 mm gap). `gen_project.py` imports
it into the RF netclass; `verify_project.py` asserts the two agree and that
the width still lands within 5 % of 50 Ω.

**The trace is CPWG, not microstrip.** The microstrip model says 0.41 mm,
which would land the line near 47 Ω. Full derivation and the PCB-stage
layout rules are in `docs/impedance.md`.

---

## The generator libraries are copied, not shared

`kicad_sch.py` and `kicad_symlib.py` are per-project copies. This project's
`kicad_sch.py` came from `analog-pid-boiler` (the most recently fixed copy
— it has the `esc()` newline fix and the `_merge_extends()` parent-first
fix). A fix made here does **not** propagate to the other projects, and
vice versa.

`flag_port()` / `flag_label()` in `wire_sheets.py` are local additions:
`Wirer.flag()` in the shared library places a bare `PWR_FLAG` and ignores
its `name` argument, so it does not actually attach the flag to a rail.
These helpers place the power port and the flag at the same coordinate,
which does.

---

## State

- [x] Parts resolved against live LCSC, every fitted part has a `Cxxxxx`
- [x] Custom symbols (LC29H, B8389) transcribed from cached datasheets
- [x] Custom footprints (LC29H LCC-24, SAW SMD1411-5P, castellated 1×12)
- [x] Five sheets placed and wired, 64 parts
- [x] ERC 0/0, proven live
- [x] 146-check gate passing
- [x] BOM + JLCPCB CSV
- [ ] **PCB layout** — next phase. Start from `docs/impedance.md`.
- [ ] Fab, assemble, bring up. Nothing here is confirmed against hardware.
