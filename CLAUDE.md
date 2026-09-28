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

### design/ is the source of truth. Edit it in KiCad.

This project **used to** be generated from Python. It is not any more —
Lucas asked for a normal editable project on 2026-09-28. The generators
are frozen in `tools/bootstrap/` and must not be run: they would
overwrite hand edits with the design as it stood that day.

```bash
make open     # open in KiCad, edit and save freely
make check    # read-only: ERC, netlist, sourcing, impedance
make bom      # rebuild manufacturing/ after a parts change
make          # list every target
```

**Nothing in `tools/` writes to `design/`.** If you need to change the
design, change it in KiCad or edit the `.kicad_sch` directly — both are
fine now.

### Never invent an LCSC part number

Every `Cxxxxx` was resolved against the live catalogue with the `lcsc`
skill on 2026-09-28. `make check` fails if a fitted part lacks one. If
you cannot resolve a part, leave the field empty and let the check fail
— do not guess.

### A clean ERC is a claim that needs proving

`kicad-cli` writes **no report at all** when the schematic fails to
parse, and says so only on stdout — so a stale report from an earlier
run reads exactly like a pass. `check_erc()` deletes the report,
re-runs, asserts the file exists, and asserts its mtime is from this run.

Proven end-to-end by injecting a fault (removing `C204`'s ground) and
confirming ERC reported `pin_not_connected` on sheet `/GNSS/`.

### Opening the project rewrites every file

The first time eeschema saved, it reformatted all seven files
(+12045/−6893) — `generator` string and `lib_symbols` indentation — with
zero design change. That is committed as the baseline. A similar diff on
any future GUI save is normal; check the netlist, not the line count.

Opening the **Symbol Editor** on a symbol desyncs the schematic's cached
copy from `design/lib/`, which ERC reports as `lib_symbol_mismatch`.
Fix with Tools → Update Symbols from Library, or rebuild the library
from the cache.

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

`tools/calc_impedance.py` solves the conductor-backed CPW conformal-
mapping model for JLCPCB's JLC04161H-3313 stackup and exports
`RF_TRACE_W = 0.38` mm (50.19 Ω at a 0.2 mm gap). `make check` reads the
RF netclass out of the `.kicad_pro` and fails if it has drifted away from
that, or if the width no longer lands within 5 % of 50 Ω.

**The trace is CPWG, not microstrip.** The microstrip model says 0.41 mm,
which would land the line near 47 Ω. Full derivation and the PCB-stage
layout rules are in `docs/impedance.md`.

---

## The frozen generators

`tools/bootstrap/` holds the Python that built v1. Read it for the
datasheet transcription (`gen_custom_symbols.py` carries the LC29H
pinout twice, deliberately, so a typo has to be made twice to survive)
and the land-pattern derivations. **Do not run any of it.**

Note for other projects: `kicad_sch.py` and `kicad_symlib.py` are
per-project copies, not a shared library. This copy came from
`analog-pid-boiler`. `Wirer.flag()` in it ignores its `name` argument
and places an unattached `PWR_FLAG`; `wire_sheets.py` here worked around
that with local `flag_port()` / `flag_label()` helpers. That bug is still
live in every other project's copy.

## State

- [x] Parts resolved against live LCSC, every fitted part has a `Cxxxxx`
- [x] Custom symbols (LC29H, B8389) transcribed from cached datasheets
- [x] Custom footprints (LC29H LCC-24, SAW SMD1411-5P, castellated 1×12)
- [x] Five sheets placed and wired, 64 parts
- [x] ERC 0/0, proven live
- [x] Converted to a normal hand-editable project; generators frozen
- [x] `make check` (32 read-only checks) passing
- [x] BOM + JLCPCB CSV
- [ ] **PCB layout** — next phase. Start from `docs/impedance.md`.
- [ ] Fab, assemble, bring up. Nothing here is confirmed against hardware.
