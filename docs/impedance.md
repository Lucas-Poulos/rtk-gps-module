# Impedance and the RF path

Everything on this board that matters at 1.2–1.6 GHz, and why each number
is what it is. The numbers here are not prose — `tools/calc_impedance.py`
derives them, and `make check` fails if the project's RF netclass drifts
away from what the model says.

```
make impedance
```

## Why the receiver cares

The LC29H hardware design guide types pin 11 (`RF_IN`) as an analog input
with **"50 Ω characteristic impedance"** (Table 6) and asks for the track to
it to be controlled and short. A GNSS signal arrives at roughly −130 dBm.
There is no margin to give away: every dB lost between the antenna and the
correlator is a dB of carrier-to-noise, and RTK needs carrier *phase*, which
degrades faster than pseudorange does as C/N₀ falls.

## The line

The antenna track is a **conductor-backed coplanar waveguide** (CPWG): a
signal trace on L1 with coplanar ground pour either side *and* a solid
ground plane on L2 underneath. That is not the same thing as microstrip,
and the difference is not small — the coplanar gaps add capacitance, so a
CPWG needs a **narrower** trace than a microstrip for the same impedance.

| Model | Width for 50 Ω |
|---|---|
| Plain microstrip (wrong here) | 0.410 mm |
| CPWG, 0.2 mm gap (correct) | 0.382 mm |
| **Built** | **0.38 mm** → 50.19 Ω |

Building the microstrip number on a board that is actually CPWG would land
the line near 47 Ω. That is inside most fab tolerances and would probably
still work — which is exactly why it is worth getting right on purpose
rather than by luck.

### Stackup

JLCPCB four-layer 1.6 mm, **JLC04161H-3313** — their default, and the one
this board is costed against.

```
L1   35 µm copper        <- antenna track here
     0.2104 mm prepreg   <- h
L2   ground plane        <- solid, unbroken under the whole RF path
     1.065 mm core
L3
     0.2104 mm prepreg
L4   35 µm copper
```

`εr = 4.3` for Shengyi S1000-2M around 1.5 GHz. The datasheet quotes 4.4 at
1 MHz and it falls with frequency.

### The model

Conformal mapping, per Simons, *Coplanar Waveguide Circuits, Components and
Systems*, ch. 3:

```
a  = W/2
b  = W/2 + G
k1 = a/b
k2 = tanh(πa/2h) / tanh(πb/2h)
R  = K(k)/K(k')          K = complete elliptic integral, 1st kind

εeff = (1 + εr·R2/R1) / (1 + R2/R1)
Z0   = 60π / √εeff / (R1 + R2)
```

### Tolerance

| Variation | Z₀ |
|---|---|
| εr = 4.1 | 51.25 Ω |
| εr = 4.3 (nominal) | 50.19 Ω |
| εr = 4.5 | 49.19 Ω |
| W − 0.02 mm (etch) | 51.76 Ω |
| W + 0.02 mm (etch) | 48.72 Ω |

Worst case lands inside ±4 %. JLCPCB hold ±10 % on controlled impedance, so
the design is not the limiting factor.

### Length

εeff = 3.107, so the guided wavelength at L1 (1575.42 MHz) is **108 mm**.
Keep the antenna track under λ/20 = **5.4 mm** and its length stops
mattering — no tuning, no stub effects, nothing to model. The u.FL connector
should sit directly beside the SAW, and the SAW directly beside pin 11.

## Layout rules for the PCB stage

Not yet built — the PCB is the next phase — but these follow from the above
and should be treated as constraints, not preferences.

1. **L2 is solid ground under the entire RF path.** A split or a via
   antipad chain under the track changes the return path, and the impedance
   with it. This is the single easiest way to ruin the work above.
2. **Stitch the coplanar pours** either side of the track with vias to L2 at
   ≤ λ/20 ≈ 5 mm — closer near the connector and the SAW. Unstitched
   coplanar pour is a resonator, not a ground.
3. **Keep the chain short and straight**: u.FL → ESD → bias tee tap →
   DC block → π → SAW → RF_IN. Quectel's guide asks for the SAW close to
   pin 11 specifically.
4. **L301 (the bias choke) taps the line, it does not sit in it.** Route the
   proximal pad of L301 onto the RF trace; the DC side goes away from it.
5. **No other signal crosses the RF path on any layer.** The switching
   antenna supply, the USB pair and the UART all stay clear.
6. **The u.FL ground pads want their own via cluster**, not a thin neck to
   the pour.

## The rest of the RF chain

### Bias tee

`L301` = 68 nH wirewound (Murata LQW15AN68NG00D). Quectel specify ≥ 68 nH.
The point of the choke is to be a high impedance across both bands while
passing DC:

| Band | f | \|Z\| of 68 nH |
|---|---|---|
| L5 / E5a / B2a | 1176.45 MHz | 502 Ω |
| L1 / E1 / B1 | 1575.42 MHz | 673 Ω |

Both are ≫ 50 Ω, so the tap costs a small fraction of a dB. A **ferrite
bead must not be substituted here** — a bead is deliberately lossy at these
frequencies, which is the opposite of what a bias tee needs.

`C301` = 100 pF C0G blocks that DC out of the receiver. At 1.5 GHz its
reactance is ~1 Ω, invisible in a 50 Ω line.

### ESD

`D301` = RF1256-000, **0.25 pF** junction capacitance. The LC29H guide caps
this at 0.6 pF. An ordinary ESD diode at 10–50 pF would sit across the
antenna node as a shunt of a few ohms at L1 and simply short the signal
away. This is a case where the "equivalent part" is not equivalent at all.

### The SAW, and its matching

`FL301` = Qualcomm RF360 **B39162B8389P810**, the dual-band part Quectel
names in their own reference design.

| | Band 1 | Band 2 |
|---|---|---|
| Centre | 1176.45 MHz | 1583 MHz |
| Pass | 1166.22–1186.68 | 1559–1607 |
| Insertion loss (typ) | 1.0 dB | 1.8 dB |
| Covers | L5, E5a, B2a | L1, E1, B1, G1 |

Out-of-band rejection is 20–39 dB, which is the point: it keeps LTE band 3
and the ISM bands out of the front end.

**An L1-only SAW here would be a design bug, not a cost saving.** Most
1575.42 MHz GNSS SAWs on LCSC are single-band; dropping one in deletes L5
entirely, and with it the dual-frequency ionosphere cancellation that makes
this an RTK receiver rather than a plain GPS.

The datasheet gives the port impedance as **50 Ω ∥ 5.1 nH**, not 50 Ω.
`L302` and `L303` are those two shunt inductors. Omitting them leaves the
filter mismatched at both ports — it still passes signal, so the mistake
survives bring-up and shows up only as unexplained lost sensitivity.

### π network

`R301` fitted at 0 Ω, `C302` and `C303` unfitted. Somewhere to retune if a
particular antenna turns out to want it, at the cost of two empty pads.

## Antenna requirements

From the LC29H guide, for RTK specifically:

- Active antenna, **noise figure < 1.5 dB**, **total gain < 17 dB**
- The antenna's own **SAW must be in front of its LNA**, not behind it.
  Quectel are explicit: *"DO NOT place the LNA in the front."* An
  LNA-first antenna amplifies every out-of-band transmitter nearby into
  compression before anything has filtered it.
- Dual-band L1+L5. A single-band antenna makes the whole L5 path pointless.

The board supplies the antenna from `VDD_RF` (= VCC, 3.3 V) through the
switch on sheet 3, current-limited to ~330 mA by `R302`.
