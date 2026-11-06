# Plan: from here to a board that works

Written 2026-11-06, at commit `ea214a0`.

This is the route from the current state to a verified, built, working
module. It is ordered by dependency, not by preference — each phase names
what it needs from the one before, and each gate names the thing that must
be true before moving on.

Nothing in this project has ever been confirmed against hardware. That is
the single largest fact about its status and it does not change until
Phase 5.

---

## Where this starts

**Schematic** — complete and wired, 64 parts across five sheets. ERC
reports 0 errors and 4 warnings. `tools/check.py` passes 31 of 32.

**PCB** — 4-layer JLC04161H-3313, 40.64 × 40.64 mm. All 64 footprints
placed, grouped by subsystem and then re-solved against connectivity
(ratsnest 993.6 → 574.8 mm). Board outline drawn. Three GND pours defined
on L1/L2/L4, L3 left free for routing. RF chain placed to `impedance.md`:
SAW output 2.67 mm from U201 pin 11.

**Not routed.** 152 unconnected items. Zero track segments, zero vias.

**BOM** — 29 lines, priced against LCSC on 2026-09-28 and now stale. The
receiver is no longer purchasable from LCSC.

---

## Phase 0 — Four decisions

These gate everything downstream. None of them is research; each is a
choice that only the owner can make.

### 0.1 Receiver: LC29H (DA) or (AA)

The DA has an onboard RTK engine. The AA outputs raw observables and the
host solves with RTKLIB. Pin-for-pin identical — verified against Figure 4
and Table 6 of the hardware design guide, where both sit in the same
column group — so **this does not gate layout**.

|                     | AA            | DA             |
|---------------------|---------------|----------------|
| Price, DK EU qty 1  | €14.24        | €30.58         |
| Stock               | 523           | 171            |
| RTCM input          | not supported | supported      |
| EPOC                | yes           | no             |
| VCC tracking        | 24 mA         | 30 mA          |
| V_BCKP continuous   | 93 µA         | 74 µA          |

Choosing AA saves €16.34/board, roughly 45% of the BOM, and changes what
the product *is*: it stops being "plug in, get centimetres" and becomes
"raw observables, bring your own solver". That is a documentation and
host-software job, not a board job.

Gates: BOM, README, pinout table, product description, host software.

### 0.2 USB-C mounting

`J101` currently sits fully inside the outline. Most SMD USB-C receptacles
overhang the board edge. Determine from the part whether this footprint is
edge-mount or mid-mount and place accordingly.

Gates: J101 final position, and therefore routing around the bottom edge.

### 0.3 Assembly route

The receiver being off LCSC breaks the JLCPCB-from-library assumption that
`manufacturing/bom_jlcpcb.csv` and the $39 feeder-fee figure are built on.

- **JLCPCB consigned** — ship them the receiver, they place the rest.
- **PCBWay turnkey** — they source globally by MPN. Expect a 1–2 day
  manual quote rather than instant pricing.
- **Hand-assemble the receiver** — JLCPCB does the rest; you reflow the
  LCC-24 yourself.

Gates: BOM export format (LCSC codes vs MPNs), fab ordering, cost model.

### 0.4 Surface finish

Currently HASL lead-free, which is JLCPCB's default and was chosen only
because nothing in the repo specified one. The finest pad on the board is
0.30 mm, which argues for ENIG.

Gates: fab order, stackup metadata.

**Gate out of Phase 0:** all four recorded in `CLAUDE.md`, so a later
session cannot silently re-decide them.

---

## Phase 1 — Close the schematic

Can run in parallel with Phase 2 up to the point where any of it changes a
net.

### 1.1 Resolve the four ERC warnings

| Warning | Action |
|---|---|
| `lib_symbol_mismatch` on U101 | Tools → Update Symbols from Library |
| `unconnected_wire_endpoint` @ (236.22, 121.92) | **Real** — a 2.54 mm stub. Investigate before deleting |
| `endpoint_off_grid` @ (257.77, 131.282) | Snap to grid |
| `no_connect_dangling`, Power sheet | Remove or attach the flag |

### 1.2 Fix the three real analyzer findings

- **`UC-002` — no ESD/TVS on VBUS at J101.** An exposed USB connector with
  no protection on the power pin. D101 (USBLC6-2SC6) protects the data
  lines only.
- **`UC-001` — no decoupling on VBUS at J101.** Wants bulk ≥1 µF plus
  100 nF local to the connector.
- **`RS-001` — `V1P8_SEL` has no declared source.** Likely just needs a
  PWR_FLAG; confirm it is genuinely driven first.

### 1.3 Findings to leave alone, with reasons recorded

- **`PP-001` on `V_BCKP`** — false positive. D104 is a BAT54C common-cathode
  OR; the analyzer's DC-path check does not treat diodes as conducting.
- **`PU-001` ×2, I2C pull-ups** — by design. I2C only reaches the edge
  through the DNP links R208/R209, so pull-ups belong off-board.

### 1.4 If AA was chosen in 0.1

Change MPN, LCSC code and value on U201 only — symbol and footprint are
unchanged. Then `make bom`, and rewrite the README's data-flow story:
RXD1 stops carrying corrections and carries configuration.

**Gate:** ERC 0/0 with liveness proven per the `CLAUDE.md` method, and
`tools/check.py` 32/32.

---

## Phase 2 — Finish the PCB

### 2.1 Make DRC usable as a gate

24 `copper_edge_clearance` errors are the castellation pads touching the
board edge, which is what a castellated pad is *for*. Until they are
excluded they will drown every real error that appears during routing.

Add a DRC exclusion or a custom rule in `.kicad_dru`. Verify the syntax
against KiCad's documentation rather than writing it from memory.

### 2.2 Fill the zones

Edit → Fill All Zones (`B`). The three pours carry outlines only; until
KiCad computes the filled polygons, every copper-presence check is
meaningless and `fill_ratio` reads empty.

### 2.3 Add fiducials

Three on F.Cu, `Fiducial:Fiducial_1mm_Mask2mm`, non-rotationally-symmetric
placement. Clears `FD-001`, which matters because the finest pad is
0.30 mm.

### 2.4 Route, in this order

1. **The RF path first.** 0.38 mm on F.Cu, J301 → C301 → R301 → FL301 →
   pin 11. It is short and fully specified; everything else routes around
   it. `ANT_RF` currently spans 6.43 mm against λ/20 = 5.40 mm — tighten
   D301 and L301 while drawing it.
2. **Stitching vias** along the coplanar pour either side of the RF track
   at ≤5 mm, closer near J301 and FL301 (`impedance.md` rule 2).
   Unstitched coplanar pour is a resonator, not a ground.
3. **Power** — VBUS, 5V_IN, +3V3, V_BCKP, ANT_BIAS. Width from the Power
   netclass; check against IPC-2221 for the antenna feed.
4. **USB differential pair** — `USB_DP`/`USB_DM`, currently 21.6 and
   24.0 mm with 2.4 mm skew. Acceptable at CH340N's 12 Mbps full speed,
   but route them together anyway.
5. **Everything else.**

### 2.5 Constraints that must hold while routing

- L2 (`In1.Cu`) stays solid ground under the entire RF path. No via
  antipad chains, no splits (`impedance.md` rule 1).
- No signal crosses the RF path on any layer (rule 5).
- L301 taps the RF line, it does not sit in it (rule 4).
- The u.FL ground pads get their own via cluster (rule 6).

### 2.6 Silkscreen pass

203 silkscreen warnings, mostly reference text that did not follow its
part through rotation. Cosmetic, but do it before fab so the board is
readable during bring-up.

**Gate:** DRC clean apart from accepted exclusions. Zones filled.

---

## Phase 3 — Verify before spending money

Everything here is cheap. A respin is not.

### 3.1 Full analyzer sweep

```bash
make check                       # 32 read-only project checks
python3 <kicad>/scripts/analyze_schematic.py design/rtk-gps-module.kicad_sch --analysis-dir analysis/
python3 <kicad>/scripts/analyze_pcb.py design/rtk-gps-module.kicad_pcb --full --analysis-dir analysis/
python3 <kicad>/scripts/cross_analysis.py -s ... -p ... --analysis-dir analysis/
python3 <kicad>/scripts/analyze_thermal.py -s ... -p ... --analysis-dir analysis/
```

### 3.2 EMC pre-compliance

```bash
python3 <emc>/scripts/analyze_emc.py --analysis-dir analysis/ --standard fcc-class-b --spice-enhanced
```

Expect attention on the switching antenna supply, the USB pair, and board
edge radiation. There is no radio on the board, which removes the hardest
part of compliance, but USB-C and a 1 Hz–10 Hz digital core still radiate.

### 3.3 SPICE

ngspice 47 is now installed. Re-run with PCB parasitics once routing
exists — that is the point at which simulating the match network becomes
meaningful rather than ideal.

```bash
python3 <spice>/scripts/extract_parasitics.py analysis/<run>/pcb.json --output parasitics.json
python3 <spice>/scripts/simulate_subcircuits.py --analysis-dir analysis/ --parasitics parasitics.json --monte-carlo 100
```

Known limit: SPICE cannot model the SAW or inductor self-resonance, so the
L1/L5 behaviour of the match stays unverified by simulation. Only a VNA on
a built board closes that.

### 3.4 Fix the impedance gate

`tools/calc_impedance.py` hardcodes `h = 0.2104` and takes no arguments, so
"RF impedance ok" is the model agreeing with itself. It cannot detect the
board drifting away from the stackup it assumes — which is exactly the
failure that went unnoticed until KiCad's DRC was run. Make it read the
real layer count and dielectric heights from the board file.

### 3.5 Gerber review

Export and run `analyze_gerbers.py` against the output. Check the
castellated edge specifically: the outline router must bisect the 0.6 mm
drills.

**Gate:** no unexplained findings at error severity anywhere.

---

## Phase 4 — Fabricate and assemble

1. Export gerbers, drill, CPL, BOM in the format Phase 0.3 chose.
2. Order a framed stencil with the boards.
3. Order **5 boards minimum** (assembly MOQ), and order spares of the
   0402s — they are effectively free and the rework is not.
4. Enable castellated holes in the fab options. This is not automatic and
   the board is unusable without it.
5. Check the rotation of SOT-23, SOT-223, SOIC and QFN parts against the
   assembler's convention before upload.

Non-BOM items to order alongside: a u.FL-to-SMA pigtail, a dual-band
active GNSS antenna, and a USB-C cable.

**Gate:** boards and parts in hand.

---

## Phase 5 — Bring-up

Ordered so that each step is only attempted once the one before it has
passed. Do not skip ahead; a board that fails at 5.1 will fail confusingly
at 5.4.

### 5.1 Power, before fitting the receiver

Assemble everything **except U201**. Confirm:
- 3V3 rail at 3.3 V from USB, and from carrier 5V, and from both at once.
- Neither 5 V source back-feeds the other (the BAT54C OR).
- V_BCKP present and holding with main power removed.
- No rail shorted to ground.

### 5.2 Fit the receiver

Reflow U201. Re-check 3V3 under load. Confirm VDD_EXT reads 2.8 V — and
confirm nothing on the board is driving it, because it is an output.

### 5.3 Serial

Confirm the CH340N enumerates, and that NMEA appears on TXD1 at the
expected baud. This proves the UART, the level shift and the USB path in
one step.

### 5.4 GNSS acquisition

With the active antenna connected and ANT_ON asserted:
- Confirm antenna bias voltage at the u.FL centre pin.
- Confirm satellites acquire and a standalone fix appears.
- Record C/N₀ across satellites. This is the number that tells you whether
  the RF chain works. Low but non-zero means the front end is lossy —
  suspect the match, the SAW orientation, or the 50 Ω line.

### 5.5 RTK

Feed corrections — RTCM3 into RXD1 for the DA, or raw observables into
RTKLIB on the host for the AA. Confirm float, then fixed. Record
time-to-fix and the baseline to the base station.

### 5.6 Measure what simulation could not

- VNA sweep from the u.FL to confirm the 50 Ω line and the match across
  L1 and L5.
- 1PPS jitter against a reference.
- Current draw against the datasheet's 24/30 mA.

**Gate:** a fixed RTK solution, with C/N₀ and time-to-fix recorded.

---

## Phase 6 — Release

- Update README from "schematic complete" to measured reality, with the
  bring-up numbers in place of the datasheet's.
- Record the errata. Every board has some; the first spin of this one will
  not be an exception.
- `docs/impedance.md` gets the VNA result alongside the derivation.
- Consider OSHWA certification — the project already meets most of it:
  editable sources, public repo, a licence.

---

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Receiver unobtainable or price-volatile | **High** | AA at €14.24 with 523 in stock is the hedge, same footprint |
| RF chain underperforms, low C/N₀ | **High** | Unverifiable before hardware. VNA at 5.6 is the only real check |
| Castellated edge mis-fabricated | Medium | New 0.6 mm geometry is untested. Inspect first article before assembling all five |
| L1-only SAW substituted in a later order | Medium | Already documented in the BOM; keep it there |
| Host RTK integration (if AA) | Medium | RTKLIB is proven with LC29H, but 1 Hz raw and no GLONASS phase constrain it |
| USB-C mechanical fit | Low | Resolved at 0.2 before routing |

---

## What this plan does not cover

- Enclosure, mounting, environmental sealing.
- Any regulatory testing beyond EMC pre-compliance. There is no
  intentional radiator, which keeps this small, but "small" is not "none".
- Production test fixturing. `TE-001` already notes thin test-point
  coverage; a second spin should add proper points.
- Firmware. The module is configured over UART with PAIR commands; none of
  that is written down yet.
