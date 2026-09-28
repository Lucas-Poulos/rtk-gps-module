#!/usr/bin/env python3
"""Derive the 50 ohm antenna trace geometry.

The LC29H datasheet specifies RF_IN as a 50 ohm port (Table 6, pin 11)
and the hardware design guide asks for a 50 ohm controlled-impedance
track to it. This script is where that width comes from, so the number in
gen_project.py's RF netclass is derived rather than asserted --
verify_project.py imports RF_TRACE_W from here and compares.

Model
-----
Conductor-backed coplanar waveguide (CPWG): a signal track with coplanar
ground pours either side AND a ground plane underneath. That is what the
antenna trace actually is on a four-layer board with a solid L2, and it
is NOT the same as plain microstrip -- the coplanar gaps add capacitance,
so a CPWG needs a *narrower* track than a microstrip for the same
impedance. Treating it as microstrip gives 0.41 mm, which would land the
line near 47 ohm.

Closed form via conformal mapping (Simons, "Coplanar Waveguide Circuits,
Components and Systems", ch. 3):

    a  = W/2                     half the strip width
    b  = W/2 + G                 half the strip plus one gap
    k1 = a/b
    k2 = tanh(pi*a / 2h) / tanh(pi*b / 2h)

    eeff = (1 + er * R2/R1) / (1 + R2/R1)          R = K(k)/K(k')
    Z0   = 60*pi / sqrt(eeff) / (R1 + R2)

K is the complete elliptic integral of the first kind, evaluated by AGM.

Stackup
-------
JLCPCB four-layer 1.6 mm, JLC04161H-3313 -- their default, and the one
the board is costed against. The antenna track runs on L1 over a solid
ground on L2:

    L1   35 um copper
    ---- 0.2104 mm prepreg (7628x1)    <- this is h
    L2   ground plane

er = 4.3 is Shengyi S1000-2M at ~1.5 GHz. The datasheet quotes 4.4 at
1 MHz and it falls with frequency; the sensitivity sweep below shows the
answer barely moves across 4.1-4.5, so the exact figure is not critical.

Usage
-----
    python3 scripts/calc_impedance.py
"""
from __future__ import annotations

import math

# --- stackup ---------------------------------------------------------------
H_PREPREG = 0.2104      # mm, L1 to L2
ER = 4.3                # at ~1.5 GHz
GAP = 0.20              # mm, coplanar gap -- JLCPCB's cheap-tier minimum
TARGET_Z0 = 50.0        # ohm

# --- the answer, rounded to something a fab can actually hold --------------
RF_TRACE_W = 0.38       # mm
RF_GAP = GAP


def _K(k: float) -> float:
    """Complete elliptic integral of the first kind, by AGM."""
    a, b = 1.0, math.sqrt(max(0.0, 1.0 - k * k))
    for _ in range(60):
        a, b = (a + b) / 2.0, math.sqrt(a * b)
    return math.pi / (2.0 * a)


def _ratio(k: float) -> float:
    """K(k) / K(k')."""
    return _K(k) / _K(math.sqrt(max(0.0, 1.0 - k * k)))


def cbcpw(w: float, g: float = GAP, h: float = H_PREPREG,
          er: float = ER) -> tuple[float, float]:
    """Conductor-backed CPW. Returns (Z0 in ohm, effective permittivity)."""
    a, b = w / 2.0, w / 2.0 + g
    k1 = a / b
    k2 = math.tanh(math.pi * a / (2 * h)) / math.tanh(math.pi * b / (2 * h))
    r1, r2 = _ratio(k1), _ratio(k2)
    eeff = (1.0 + er * r2 / r1) / (1.0 + r2 / r1)
    z0 = 60.0 * math.pi / math.sqrt(eeff) / (r1 + r2)
    return z0, eeff


def microstrip(w: float, h: float = H_PREPREG,
               er: float = ER) -> tuple[float, float]:
    """Hammerstad-Jensen microstrip, for the comparison in the docstring."""
    u = w / h
    a = (1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49
         + math.log(1 + (u / 18.1) ** 3) / 18.7)
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    f = 6 + (2 * math.pi - 6) * math.exp(-((30.666 / u) ** 0.7528))
    z0 = 60 / math.sqrt(eeff) * math.log(f / u + math.sqrt(1 + (2 / u) ** 2))
    return z0, eeff


def solve_width(target: float, fn) -> float:
    """Bisect for the width that hits `target` ohm. Z0 falls as W grows."""
    lo, hi = 0.05, 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if fn(mid)[0] > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def main() -> int:
    print("50 ohm antenna trace -- JLCPCB 4-layer JLC04161H-3313")
    print(f"  h = {H_PREPREG} mm prepreg, er = {ER}, coplanar gap = {GAP} mm\n")

    w_ms = solve_width(TARGET_Z0, lambda w: microstrip(w))
    w_cp = solve_width(TARGET_Z0, lambda w: cbcpw(w))
    print(f"  plain microstrip needs W = {w_ms:.3f} mm")
    print(f"  CPWG             needs W = {w_cp:.3f} mm   <- the real case")
    print(f"  chosen and built  W = {RF_TRACE_W} mm\n")

    z0, eeff = cbcpw(RF_TRACE_W)
    print(f"  at W = {RF_TRACE_W} mm:  Z0 = {z0:.2f} ohm, eeff = {eeff:.3f}")
    err = abs(z0 - TARGET_Z0) / TARGET_Z0 * 100
    print(f"  error vs 50 ohm: {err:.2f} %  "
          f"(JLCPCB hold +/-10 % on controlled impedance)\n")

    print("  sensitivity to er:")
    for er in (4.1, 4.2, 4.3, 4.4, 4.5):
        z, _ = cbcpw(RF_TRACE_W, er=er)
        print(f"    er={er}  ->  {z:.2f} ohm")
    print("\n  sensitivity to etch tolerance (+/-0.02 mm):")
    for dw in (-0.02, 0.0, 0.02):
        z, _ = cbcpw(RF_TRACE_W + dw)
        print(f"    W={RF_TRACE_W + dw:.2f} mm  ->  {z:.2f} ohm")

    lam = 300.0 / math.sqrt(eeff) / 1.57542
    print(f"\n  guided wavelength at L1 (1575.42 MHz): {lam:.1f} mm")
    print(f"  keep the antenna track under lambda/20 = {lam / 20:.1f} mm "
          f"to make its length irrelevant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
