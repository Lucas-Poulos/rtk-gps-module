# rtk-gps-module

A cheap, solder-down **RTK GNSS module** that gets you centimetre-level
position. Dual-band L1 + L5, castellated edges, and a USB-C port so it also
works on its own with nothing but a cable.

**Status: schematic complete and verified. PCB layout is the next phase.**

```
    ┌──── u.FL ────┐
    │ active       │   50 Ω CPWG, 0.38 mm
    │ dual-band    ├──► ESD ─► bias tee ─► DC block ─► π ─► SAW ─┐
    │ antenna      │    0.25pF   68 nH      100 pF    0R   L1+L5 │
    └──────────────┘        ▲                                    ▼
                            │                            ┌───────────────┐
                    ANT_ON ─┴─ PMOS switch               │   LC29H (DA)  │
                                                         │  dual-band    │
    USB-C ─► ESD ─► BAT54C OR ─► AP2112K 3V3 ────────────┤  RTK rover    │
      │                ▲                                 │               │
      │             5V_IN (carrier)                      │  UART1  1PPS  │
      └─► CH340N ──────────────────────────── UART ──────┤               │
                                        1k/10k divider   └───────┬───────┘
                                                                 │
                              24 castellated pads, 1.27 mm ──────┘
```

## What it does

Feed it **RTCM3 corrections** over the UART — from an NTRIP client on a
phone, a Raspberry Pi or a PC — and it resolves carrier phase to **1–2 cm
horizontal**, versus the 2–3 m you get from ordinary GPS.

Corrections come from the host, so there is **no radio on the board**:
nothing to license, nothing to certify, and one less thing to pay for.

| | |
|---|---|
| Receiver | Quectel LC29H (DA), dual-band RTK rover |
| Bands | L1 / E1 / B1 / G1 **and** L5 / E5a / B2a |
| Constellations | GPS, GLONASS, Galileo, BeiDou, QZSS, SBAS |
| RTK accuracy | ~1–2 cm CEP, open sky, within 1 km of the base |
| Update rate | up to 10 Hz |
| Corrections in | RTCM3 over UART1 |
| Timing out | 1PPS, rising-edge synchronised |
| Supply | 5 V from USB-C **or** 5 V from the carrier board |
| Logic | 3.3 V (plus a 1.8 V debug domain, see below) |
| Interface | USB-C (CH340N) and 24 castellated pads on 1.27 mm |
| **Parts cost** | **$27.10** per board at qty 1 |

The receiver is **88 % of the bill**. Everything else together is $1.56.
Nothing but the receiver is worth cost-optimising.

## Everything else is discrete

There is no way to make an RTK receiver from discrete components — carrier
phase needs a correlator ASIC. So the receiver and its SAW filter are ICs
and *everything around them* is built from single transistors and passives
rather than bought as a block:

- **Antenna bias tee** — a 68 nH choke, a 100 pF block, and a PMOS/NPN pair
  switched by `ANT_ON`, with a 10 Ω resistor limiting a shorted antenna to
  ~330 mA.
- **5 V ORing** — one BAT54C, anodes to USB and to the carrier's 5 V,
  cathode to the LDO. USB and carrier power can both be present and neither
  back-feeds the other.
- **Backup domain** — a second BAT54C ORs 3V3 with an optional external
  cell on `VBCKP_EXT`, so the ephemeris cache survives and the module
  hot-starts in ~1 s instead of cold-starting in ~30 s.
- **RX level shift** — a 1 k / 10 k divider, because `RXD1` is specified
  VIHmax **3.08 V** and a 3.3 V host would exceed it.
- **1PPS indicator** — one MMBT3904, because 1PPS is guaranteed only 2.1 V
  high and would drive an LED dimly while loading the edge.

## The impedance work

Fully derived rather than asserted — see **[docs/impedance.md](docs/impedance.md)**.
Short version:

- The antenna line is a **conductor-backed CPWG**, not microstrip. Solving
  the conformal-mapping model for JLCPCB's 4-layer JLC04161H-3313 stackup
  gives **0.38 mm at 0.2 mm gap → 50.19 Ω**. Treating it as microstrip
  would say 0.41 mm and land it near 47 Ω.
- The SAW's ports are **50 Ω ∥ 5.1 nH**, not 50 Ω, so `L302`/`L303` are
  part of the impedance, not optional.
- The ESD diode is **0.25 pF**. An ordinary ESD part at 10–50 pF would
  shunt the antenna signal away.
- The number lives in `tools/calc_impedance.py`, and `make check` fails
  if the project's RF netclass drifts away from it.

## Pinout

24 castellated pads on 1.27 mm — drops onto 0.1 in perfboard.

**Left edge (J501)**

| Pad | Name | Notes |
|---:|---|---|
| 1 | GND | |
| 2 | 5V_IN | ORed with USB VBUS |
| 3 | 3V3 | LDO output |
| 4 | VBCKP_EXT | optional backup cell / supercap |
| 5 | GND | |
| 6 | TXD1 | receiver → host, NMEA / PQTM |
| 7 | RXD1 | host → receiver, RTCM3 in |
| 8 | 1PPS | rising edge |
| 9 | RESET_N | active low, pulled up on-board |
| 10 | WAKEUP | needs ≥ 3.0 V to wake |
| 11 | VDD_EXT | 2.8 V out, **100 mA max** |
| 12 | GND | |

**Right edge (J502)**

| Pad | Name | Notes |
|---:|---|---|
| 1 | GND | |
| 2 | ANT_ON | antenna switch control |
| 3 | I2C_SDA | via DNP link |
| 4 | I2C_SCL | via DNP link |
| 5 | TXD2 | **1.8 V domain**, via DNP link |
| 6 | RXD2 | **1.8 V domain**, via DNP link |
| 7 | D_SEL1 | **1.8 V domain**, via DNP link |
| 8 | D_SEL2 | **1.8 V domain**, via DNP link |
| 9 | GND | |
| 10–11 | — | spare |
| 12 | GND | |

> **Pads 5–8 on the right edge are not 3.3 V tolerant.** VIHmax is 2.1 V.
> Each reaches the edge only through an unfitted link, so a default board
> cannot present them to a 3.3 V host by accident.

`D_SEL1 = D_SEL2 = 0` selects UART1 and is the on-chip default via 75 kΩ
pulldowns, so the fitted board needs no strapping parts at all.

## Repository layout

```
design/        THE PROJECT. Open it in KiCad, edit it, save it.
  lib/         the two symbols and three footprints stock KiCad lacks
tools/         helpers that READ design/ -- none of them write to it
  check.py             ERC + netlist + sourcing + impedance
  gen_bom.py           BOM, read from the schematic
  calc_impedance.py    the 50 Ω derivation
  fetch_datasheets.py  pulls the vendor PDFs (not committed)
  bootstrap/           the generators that built v1 -- NOT authoritative
Makefile       run `make` to list every target
.githooks/     optional pre-commit hook, ERC errors only
manufacturing/ BOM.md, BOM-dnp.md, bom_jlcpcb.csv
docs/          editing.md, impedance.md, schematic.pdf
datasheets/    README + fetch script; the PDFs are not ours to redistribute
analysis/      ERC report and netlist (gitignored, regenerated on demand)
```

**`design/` is a normal KiCad project.** Edit it directly. Nothing
regenerates it, and nothing in `tools/` writes to it.

## Working on it

```bash
make open       # open in KiCad -- edit and save freely
make check      # ERC + netlist + sourcing + impedance, all read-only
make bom        # rebuild manufacturing/ after a parts change
make            # list every target
```

Read **[docs/editing.md](docs/editing.md)** before changing the RF path
or anything on the LC29H — there are four traps on this board that KiCad
will not warn you about (a 3.08 V limit on `RXD1`, a 1.8 V pin domain,
two supply pins that are outputs, and three pins that must float).

`make check` reads `design/` and never writes to it. It exports a fresh
netlist and a fresh ERC report and asserts against those:

- **ERC** — must be clean *and* the report must be newly written. A stale
  report from an earlier run reads exactly like a pass, and `kicad-cli`
  writes no report at all when the schematic fails to parse. Verified by
  injecting a deliberate fault and confirming ERC caught it on the right
  sub-sheet.
- **Netclass** — the exported per-net class is read back, because KiCad
  accepts a netclass pattern that matches nothing without complaining and
  a 50 Ω line silently falls back to the default track width. *(This
  caught a real bug: `/regex/` patterns are accepted by the file format
  and match nothing — KiCad uses wildcards, and local nets carry their
  sheet path.)*
- **Critical nets** — the RF chain, the bias tee and the RXD1 divider are
  asserted pin by pin, so none of them gets rerouted by accident. Rewire
  one on purpose and it tells you exactly what changed.
- **LC29H pin rules** — grounds grounded, the three RESERVED pins still
  floating, `VDD_EXT` never tied to 3V3.
- **Sourcing** — every fitted part must carry a resolved `Cxxxxx`.
- **Impedance** — the RF netclass width must still match what
  `tools/calc_impedance.py` derives, and still land within 5 % of 50 Ω.

## Building one

The BOM is in [manufacturing/BOM.md](manufacturing/BOM.md), with
`bom_jlcpcb.csv` ready for JLCPCB assembly and
[BOM-dnp.md](manufacturing/BOM-dnp.md) listing the unfitted options.

Prices and stock were read from LCSC on 2026-09-28 and frozen for
traceability — **re-check before ordering.** LC29H stock in particular was
thin (22 pcs). `LC29HBS` (`C21385845`) is the RTK *base station* variant and
`LC29HAA` (`C22403415`) has no RTK engine; both share the footprint, so
check you are buying the one you mean.

You also need an **active dual-band L1+L5 antenna** with NF < 1.5 dB, gain
< 17 dB, and its SAW ahead of its LNA.

## Caveats

- **Not built yet.** The schematic is verified; no board has been
  fabricated, so nothing here is confirmed against hardware.
- **The LC29H (DA) pinout is contested by its own datasheet.** Figure 4
  and Table 6 disagree about pins 15–19. The V1.3 revision history settles
  it in Table 6's favour (the changes applied only to the EA variant), and
  the design follows Table 6 — but those four pins reach the edge only
  through unfitted links, so the board is correct either way.
- Prices are a snapshot, not a quote.

## Licence

Hardware under [CERN-OHL-P v2](LICENSE); the scripts under the same terms.
Permissive — do what you like, no reciprocity required.
