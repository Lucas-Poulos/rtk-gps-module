# Editing this project

It is a normal KiCad 10 project. Open it, change it, save it.

```bash
make open        # or just double-click design/rtk-gps-module.kicad_pro
```

There is no generator to fight, no regeneration step, and nothing that
overwrites your edits. `design/` is the source of truth.

After you save:

```bash
make check       # ERC + netlist + sourcing + impedance, all read-only
make bom         # rebuild manufacturing/ if you changed parts
make pdf         # re-plot docs/schematic.pdf
```

`make check` never writes to `design/`.

---

## Adding or changing a part

Do it in KiCad. The one thing to remember: **set the `LCSC` field**, or
the part silently vanishes from the BOM at order time. `make check`
catches it:

```
R103 (2.2k) has no resolved LCSC number. Set its LCSC field in KiCad,
or mark it DNP.
```

Resolve the real number first — never invent one:

```bash
python3 ~/.claude/skills/lcsc/scripts/search_lcsc.py "0402 2.2k" --details
```

Then in KiCad: select the symbol, `E`, and set the fields the BOM reads:

| Field | Example | Used for |
|---|---|---|
| `LCSC` | `C25879` | ordering, JLCPCB CSV |
| `MPN` | `0402WGF2201TCE` | the BOM line |
| `Manufacturer` | `UNI-ROYAL` | the BOM line |
| `DNP` | `yes` | excludes it from the fitted BOM |

For a not-fitted part, also add its reason to `DNP_REASON` in
`tools/gen_bom.py` so `BOM-dnp.md` explains why the footprint exists.

Prices live in `PRICES` in `tools/gen_bom.py` — a frozen snapshot from
2026-09-28, kept for traceability rather than accuracy. Refresh before
ordering.

---

## Four things that will bite you

These are all real, all specific to this board, and none of them are
things KiCad warns about.

### 1. `RXD1` cannot take 3.3 V

The LC29H specifies `RXD1` VIHmax **3.08 V**. `R205`/`R212` (1 k/10 k)
divide a 3.3 V host down to 3.0 V, and the divider sits **at the module
pin** so it protects the castellated pad and the USB bridge with one
pair of resistors. Delete it and you are over spec on a $24 part.

### 2. `D_SEL1`/`D_SEL2`, `TXD2`/`RXD2` are a 1.8 V domain

VIHmax is **2.1 V**. They cannot be strapped to `VDD_EXT` (2.8 V) or
3V3. The default `0,0` selects UART1 via internal 75 kΩ pulldowns, which
is what this board wants, so the fitted build needs no strapping parts.

### 3. `VDD_EXT` (pin 7) and `VDD_RF` (pin 9) are OUTPUTS

Typed `power_out` so ERC rejects driving them. `VDD_EXT` is 2.8 V at
100 mA max — tying it to 3V3 shorts two regulators together.

### 4. Pins 2, 4, 17 must float

Datasheet Table 6: *"must be left N/C and cannot be connected to power
or GND."* Typed `no_connect`; `make check` asserts each still lands on
its own unconnected net.

---

## The RF path

If you touch anything between `J301` and `U201` pin 11, read
[impedance.md](impedance.md) first. Three specifics:

- The antenna line is **50 Ω CPWG at 0.38 mm** with a 0.2 mm gap, derived
  in `tools/calc_impedance.py`. If you change the width in the RF
  netclass, `make check` fails until the model agrees.
- The SAW's ports are **50 Ω ∥ 5.1 nH**. `L302`/`L303` are part of the
  impedance, not optional decoration.
- `D301` is chosen for **0.25 pF**, not its clamp voltage. A normal ESD
  diode at 10–50 pF shunts the antenna signal away.

`make check` pins down the exact wiring of the RF chain, the bias tee and
the RXD1 divider. If you rewire one deliberately, it tells you what
changed and where to update the expectation:

```
net '/RF/ANT_RF' was rewired:
       missing ['L301.2']
       extra   ['L301.1']
       If that was deliberate, update CRITICAL_NETS in tools/check.py
```

---

## Netclasses are wildcards, not regex

If `make check` says a net fell back to `Default`, this is why. KiCad's
netclass patterns use `*` and `?` — a pattern written `/^ANT_RF$/` is
accepted by the file format, displays correctly in the GUI, and **matches
nothing**. Local nets also carry their sheet path (`/RF/ANT_RF`), so a
pattern for one needs a leading `*`.

This already bit the project once: the 50 Ω antenna line was silently on
the default track width. That is the only reason `make check` reads the
exported per-net class back.

---

## The pre-commit hook

`make hooks` installs one. It blocks on **ERC errors only** — never on
warnings, never on formatting, and it skips entirely while KiCad has the
project open. `make unhook` removes it; `git commit --no-verify` bypasses
it once.

---

## What nothing checks

- **The pinout tables in `README.md`** — hand-maintained. If you change
  `J501`/`J502`, change them too.
- **Whether the design works.** No board has been fabricated. ERC proves
  the netlist is self-consistent; it says nothing about whether the
  circuit is correct.

---

## Where the old generators went

`tools/bootstrap/`. They built the first version of `design/` and are no
longer authoritative — see the README there. Worth reading for the
datasheet transcription and the reasoning about the LC29H's
self-contradictory pinout, but do not run them: they would overwrite
your edits with the design as it stood on 2026-09-28.
