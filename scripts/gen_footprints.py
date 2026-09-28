#!/usr/bin/env python3
"""Generate the footprints no stock KiCad 10 library provides.

Three footprints:

``Quectel_LC29H_LCC-24_12.2x16.0mm``
    The LC29H land pattern, from Quectel ``LC29H_Series_Hardware_Design``
    V1.3 (2024-07-30) Figure 19 "Recommended Footprint", page 47.
    Cached at ``datasheets/LC29H_Hardware_Design_V1.3.pdf``.

``SAW_RF360_SMD1411-5P_1.4x1.1mm``
    The B8389 GNSS L1/L5 SAW filter land pattern, from the Qualcomm RF360
    data sheet V2.1 (2022-11-15) Figure 2, "Land pattern THRU VIEW",
    page 5. Cached at ``datasheets/SAW_B39162B8389P810.pdf``.

``Castellated_1x12_P1.27mm``
    The module's own edge pads. Half-vias on a 1.27 mm pitch, the pitch
    every carrier board already has a 0.1" header for. Twelve per edge,
    two edges, 24 signals -- see gen_project.py CASTELLATED.

Usage
-----
    python3 scripts/gen_footprints.py
    python3 scripts/gen_footprints.py --verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "design" / "lib" / "rtk-gps-module.pretty"

SILK_W = 0.12
FAB_W = 0.10
CRT_W = 0.05
RRATIO = 0.25


def f(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


# ==========================================================================
# LC29H -- 24-pin LCC, Figure 19
# ==========================================================================
#
# Read off Figure 19 directly:
#
#   module body        12.2 (X) x 16.0 (Y)
#   pad                2.5 long (X) x 0.8 wide (Y)
#   pitch              1.1
#   overall pad span   15.1 in X  ->  pads reach 1.45 beyond each body edge
#   pin 1              top-left, numbering runs DOWN the left edge to 12,
#                      then 13 at bottom-right and UP the right edge to 24
#
# The 24 pads are not evenly spaced. Each edge carries two groups split by
# a 3.0 mm gap: seven pads (1-7 / 24-18) then five (8-12 / 17-13). Figure 19
# dimensions the groups as 6*1.1=6.6 and 4*1.1=4.4, and 6.6 + 3.0 + 4.4
# = 14.0 mm centre-to-centre from pin 1 to pin 12, which centres inside the
# 16.0 mm body with 1.0 mm top and bottom -- so the pattern is symmetric
# about y=0 and pin 1 sits at y=+7.0.
#
# The same gap is visible in Figure 4's pin map as the break between
# VDD_EXT (7) and RESET_N (8), and between I2C_SDA (18) and pin 17.

LC29H_NAME = "Quectel_LC29H_LCC-24_12.2x16.0mm"
LC29H_BODY_X, LC29H_BODY_Y = 12.2, 16.0
LC29H_PAD_X, LC29H_PAD_Y = 2.5, 0.8
LC29H_PITCH = 1.1
LC29H_SPAN_X = 15.1
LC29H_GROUP_GAP = 3.0
LC29H_N_UPPER = 7          # pads 1-7 on the left edge, 24-18 on the right
LC29H_N_LOWER = 5          # pads 8-12 on the left edge, 17-13 on the right


def lc29h_pin_y() -> list[float]:
    """Centre y of pads 1..12, top to bottom. Symmetric about y=0."""
    ys = []
    y = (LC29H_N_UPPER - 1) * LC29H_PITCH  # 6.6
    y += LC29H_GROUP_GAP                   # 9.6
    y += (LC29H_N_LOWER - 1) * LC29H_PITCH  # 14.0 total span
    top = y / 2.0                          # +7.0
    for i in range(LC29H_N_UPPER):
        ys.append(top - i * LC29H_PITCH)
    nxt = top - (LC29H_N_UPPER - 1) * LC29H_PITCH - LC29H_GROUP_GAP
    for i in range(LC29H_N_LOWER):
        ys.append(nxt - i * LC29H_PITCH)
    return ys


def build_lc29h() -> str:
    ys = lc29h_pin_y()
    assert len(ys) == 12, ys
    # pad centre |x|: outer edge at SPAN_X/2, pad is PAD_X long
    px = LC29H_SPAN_X / 2.0 - LC29H_PAD_X / 2.0     # 6.3
    hx, hy = LC29H_BODY_X / 2.0, LC29H_BODY_Y / 2.0

    out = [
        f'(footprint "{LC29H_NAME}"\n',
        '\t(version 20240108)\n',
        '\t(generator "rtk-gps-module/scripts/gen_footprints.py")\n',
        '\t(generator_version "10.0")\n',
        '\t(layer "F.Cu")\n',
        '\t(descr "Quectel LC29H series GNSS module, 24-pin LCC, '
        '12.2x16.0x2.5mm. Land pattern from LC29H_Series_Hardware_Design '
        'V1.3 Figure 19.")\n',
        '\t(tags "Quectel LC29H GNSS RTK LCC-24 module")\n',
        '\t(attr smd)\n',
    ]
    # reference / value
    out.append(
        f'\t(property "Reference" "U**"\n\t\t(at 0 {f(-hy - 1.2)} 0)\n'
        '\t\t(layer "F.SilkS")\n\t\t(uuid "00000000-0000-0000-0000-000000000001")\n'
        '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n'
        '\t\t\t)\n\t\t)\n\t)\n'
    )
    out.append(
        f'\t(property "Value" "{LC29H_NAME}"\n\t\t(at 0 {f(hy + 1.2)} 0)\n'
        '\t\t(layer "F.Fab")\n\t\t(uuid "00000000-0000-0000-0000-000000000002")\n'
        '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n'
        '\t\t\t)\n\t\t)\n\t)\n'
    )

    # Fab outline = true body, with a pin-1 chamfer
    ch = 1.0
    out.append(
        '\t(fp_poly\n\t\t(pts\n'
        f'\t\t\t(xy {f(-hx + ch)} {f(-hy)}) (xy {f(hx)} {f(-hy)}) '
        f'(xy {f(hx)} {f(hy)}) (xy {f(-hx)} {f(hy)}) (xy {f(-hx)} {f(-hy + ch)})\n'
        '\t\t)\n'
        f'\t\t(stroke\n\t\t\t(width {f(FAB_W)})\n\t\t\t(type solid)\n\t\t)\n'
        '\t\t(fill no)\n\t\t(layer "F.Fab")\n'
        '\t\t(uuid "00000000-0000-0000-0000-000000000003")\n\t)\n'
    )

    # Silk: short segments along the top and bottom edges only -- the side
    # edges are wall-to-wall pads, so silk there would print on copper.
    uid = 16
    for sy in (-hy, hy):
        for sx in (-1, 1):
            x1 = sx * hx
            x2 = sx * (hx - 3.0)
            out.append(
                f'\t(fp_line\n\t\t(start {f(x1)} {f(sy)})\n\t\t(end {f(x2)} {f(sy)})\n'
                f'\t\t(stroke\n\t\t\t(width {f(SILK_W)})\n\t\t\t(type solid)\n\t\t)\n'
                f'\t\t(layer "F.SilkS")\n'
                f'\t\t(uuid "00000000-0000-0000-0000-{uid:012d}")\n\t)\n'
            )
            uid += 1
    # pin-1 dot, clear of the pad field
    out.append(
        f'\t(fp_circle\n\t\t(center {f(-hx - 1.9)} {f(ys[0])})\n'
        f'\t\t(end {f(-hx - 1.6)} {f(ys[0])})\n'
        f'\t\t(stroke\n\t\t\t(width {f(SILK_W)})\n\t\t\t(type solid)\n\t\t)\n'
        '\t\t(fill solid)\n\t\t(layer "F.SilkS")\n'
        f'\t\t(uuid "00000000-0000-0000-0000-{uid:012d}")\n\t)\n'
    )
    uid += 1

    # Courtyard: pads are the widest feature in X, body in Y. 0.25 margin.
    cx, cy = LC29H_SPAN_X / 2.0 + 0.25, hy + 0.25
    out.append(
        '\t(fp_poly\n\t\t(pts\n'
        f'\t\t\t(xy {f(-cx)} {f(-cy)}) (xy {f(cx)} {f(-cy)}) '
        f'(xy {f(cx)} {f(cy)}) (xy {f(-cx)} {f(cy)})\n'
        '\t\t)\n'
        f'\t\t(stroke\n\t\t\t(width {f(CRT_W)})\n\t\t\t(type solid)\n\t\t)\n'
        '\t\t(fill no)\n\t\t(layer "F.CrtYd")\n'
        f'\t\t(uuid "00000000-0000-0000-0000-{uid:012d}")\n\t)\n'
    )
    uid += 1

    # Pads 1-12 down the left edge, 13-24 up the right edge.
    for i, y in enumerate(ys):
        out.append(_pad(i + 1, -px, y, LC29H_PAD_X, LC29H_PAD_Y, uid))
        uid += 1
    for i, y in enumerate(reversed(ys)):
        out.append(_pad(i + 13, px, y, LC29H_PAD_X, LC29H_PAD_Y, uid))
        uid += 1

    out.append(')\n')
    return "".join(out)


def _pad(num: int, x: float, y: float, sx: float, sy: float, uid: int) -> str:
    return (
        f'\t(pad "{num}" smd roundrect\n'
        f'\t\t(at {f(x)} {f(y)})\n'
        f'\t\t(size {f(sx)} {f(sy)})\n'
        '\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n'
        f'\t\t(roundrect_rratio {f(RRATIO)})\n'
        f'\t\t(uuid "00000000-0000-0000-0000-{uid:012d}")\n\t)\n'
    )


# ==========================================================================
# B8389 SAW -- SMD1411-5P, data sheet Figure 2 "Land pattern THRU VIEW"
# ==========================================================================
#
# Land pattern (not the package pads -- the recommended land):
#
#   pad          0.3 (X) x 0.375 (Y), five of them
#   pitch        0.5 in X, 0.575 in Y (2 x 0.2875 either side of centre)
#   body         1.4 x 1.1
#
# Pin 1 (Input) sits alone on the left edge at y=0. The other four are a
# 2x2 block: TOP VIEW has 5 upper-left, 4 upper-right, 2 lower-left,
# 3 lower-right. Pin 4 is Output; 2, 3 and 5 are Ground.

SAW_NAME = "SAW_RF360_SMD1411-5P_1.4x1.1mm"
SAW_BODY_X, SAW_BODY_Y = 1.4, 1.1
SAW_PAD_X, SAW_PAD_Y = 0.3, 0.375
SAW_DX = 0.5 / 2.0        # +/-0.25 about centre
SAW_DY = 0.2875

# (pad number, x, y) in TOP VIEW
SAW_PADS = [
    ("1", -0.55, 0.0),
    ("5", -SAW_DX, SAW_DY),
    ("4", SAW_DX, SAW_DY),
    ("2", -SAW_DX, -SAW_DY),
    ("3", SAW_DX, -SAW_DY),
]


def build_saw() -> str:
    hx, hy = SAW_BODY_X / 2.0, SAW_BODY_Y / 2.0
    out = [
        f'(footprint "{SAW_NAME}"\n',
        '\t(version 20240108)\n',
        '\t(generator "rtk-gps-module/scripts/gen_footprints.py")\n',
        '\t(generator_version "10.0")\n',
        '\t(layer "F.Cu")\n',
        '\t(descr "Qualcomm RF360 B8389 GNSS L1/L5 SAW filter, SMD1411-5P, '
        '1.4x1.1x0.45mm. Land pattern from RF360 B8389 data sheet V2.1 '
        'Figure 2. Pin 1 In, pin 4 Out, pins 2/3/5 Ground.")\n',
        '\t(tags "SAW filter GNSS L1 L5 RF360 B8389")\n',
        '\t(attr smd)\n',
        f'\t(property "Reference" "FL**"\n\t\t(at 0 {f(-hy - 0.9)} 0)\n'
        '\t\t(layer "F.SilkS")\n\t\t(uuid "00000000-0000-0000-0001-000000000001")\n'
        '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 0.6 0.6)\n\t\t\t\t(thickness 0.1)\n'
        '\t\t\t)\n\t\t)\n\t)\n',
        f'\t(property "Value" "{SAW_NAME}"\n\t\t(at 0 {f(hy + 0.9)} 0)\n'
        '\t\t(layer "F.Fab")\n\t\t(uuid "00000000-0000-0000-0001-000000000002")\n'
        '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 0.6 0.6)\n\t\t\t\t(thickness 0.1)\n'
        '\t\t\t)\n\t\t)\n\t)\n',
        '\t(fp_poly\n\t\t(pts\n'
        f'\t\t\t(xy {f(-hx)} {f(-hy)}) (xy {f(hx)} {f(-hy)}) '
        f'(xy {f(hx)} {f(hy)}) (xy {f(-hx)} {f(hy)})\n'
        '\t\t)\n'
        f'\t\t(stroke\n\t\t\t(width {f(FAB_W)})\n\t\t\t(type solid)\n\t\t)\n'
        '\t\t(fill no)\n\t\t(layer "F.Fab")\n'
        '\t\t(uuid "00000000-0000-0000-0001-000000000003")\n\t)\n',
        # pin-1 marker outside the courtyard-critical zone
        f'\t(fp_circle\n\t\t(center {f(-hx - 0.4)} 0)\n\t\t(end {f(-hx - 0.28)} 0)\n'
        f'\t\t(stroke\n\t\t\t(width {f(SILK_W)})\n\t\t\t(type solid)\n\t\t)\n'
        '\t\t(fill solid)\n\t\t(layer "F.SilkS")\n'
        '\t\t(uuid "00000000-0000-0000-0001-000000000004")\n\t)\n',
    ]
    cx = max(hx, 0.55 + SAW_PAD_X / 2.0) + 0.2
    cy = max(hy, SAW_DY + SAW_PAD_Y / 2.0) + 0.2
    out.append(
        '\t(fp_poly\n\t\t(pts\n'
        f'\t\t\t(xy {f(-cx)} {f(-cy)}) (xy {f(cx)} {f(-cy)}) '
        f'(xy {f(cx)} {f(cy)}) (xy {f(-cx)} {f(cy)})\n'
        '\t\t)\n'
        f'\t\t(stroke\n\t\t\t(width {f(CRT_W)})\n\t\t\t(type solid)\n\t\t)\n'
        '\t\t(fill no)\n\t\t(layer "F.CrtYd")\n'
        '\t\t(uuid "00000000-0000-0000-0001-000000000005")\n\t)\n'
    )
    uid = 16
    for num, x, y in SAW_PADS:
        out.append(
            f'\t(pad "{num}" smd roundrect\n'
            f'\t\t(at {f(x)} {f(y)})\n'
            f'\t\t(size {f(SAW_PAD_X)} {f(SAW_PAD_Y)})\n'
            '\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n'
            f'\t\t(roundrect_rratio {f(RRATIO)})\n'
            f'\t\t(uuid "00000000-0000-0000-0001-{uid:012d}")\n\t)\n'
        )
        uid += 1
    out.append(')\n')
    return "".join(out)


# ==========================================================================
# Castellated edge pads -- 1x12 at 1.27 mm
# ==========================================================================
#
# Plated half-vias. Drawn as a through-hole pad with an oval copper shape
# straddling the board edge: the drill is what the router cuts through, so
# the pad is placed with its centre ON the edge line. x=0 is the board
# edge; the pads run along y.
#
# 1.27 mm pitch is deliberate -- it drops onto 0.1" perfboard with a
# two-row offset, and every carrier board already has the header for it.

CAST_NAME = "Castellated_1x12_P1.27mm"
CAST_N = 12
CAST_PITCH = 1.27
CAST_DRILL = 0.9
CAST_PAD = 1.4


def build_castellated() -> str:
    span = (CAST_N - 1) * CAST_PITCH
    y0 = -span / 2.0
    out = [
        f'(footprint "{CAST_NAME}"\n',
        '\t(version 20240108)\n',
        '\t(generator "rtk-gps-module/scripts/gen_footprints.py")\n',
        '\t(generator_version "10.0")\n',
        '\t(layer "F.Cu")\n',
        '\t(descr "12-way castellated edge pads, 1.27mm pitch, plated '
        'half-vias. Pad centres sit on the board edge; the outline router '
        'bisects the 0.9mm drill.")\n',
        '\t(tags "castellated module edge half-via")\n',
        '\t(attr through_hole)\n',
        f'\t(property "Reference" "J**"\n\t\t(at -2 {f(y0 - 1.4)} 0)\n'
        '\t\t(layer "F.SilkS")\n\t\t(uuid "00000000-0000-0000-0002-000000000001")\n'
        '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n'
        '\t\t\t)\n\t\t)\n\t)\n',
        f'\t(property "Value" "{CAST_NAME}"\n\t\t(at -2 {f(-y0 + 1.4)} 0)\n'
        '\t\t(layer "F.Fab")\n\t\t(uuid "00000000-0000-0000-0002-000000000002")\n'
        '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n'
        '\t\t\t)\n\t\t)\n\t)\n',
    ]
    uid = 16
    for i in range(CAST_N):
        y = y0 + i * CAST_PITCH
        shape = "rect" if i == 0 else "oval"
        out.append(
            f'\t(pad "{i + 1}" thru_hole {shape}\n'
            f'\t\t(at 0 {f(y)})\n'
            f'\t\t(size {f(CAST_PAD)} {f(CAST_PAD)})\n'
            f'\t\t(drill {f(CAST_DRILL)})\n'
            '\t\t(layers "*.Cu" "*.Mask")\n'
            f'\t\t(uuid "00000000-0000-0000-0002-{uid:012d}")\n\t)\n'
        )
        uid += 1
    cy = span / 2.0 + CAST_PAD / 2.0 + 0.25
    out.append(
        '\t(fp_poly\n\t\t(pts\n'
        f'\t\t\t(xy -1 {f(-cy)}) (xy 1 {f(-cy)}) (xy 1 {f(cy)}) (xy -1 {f(cy)})\n'
        '\t\t)\n'
        f'\t\t(stroke\n\t\t\t(width {f(CRT_W)})\n\t\t\t(type solid)\n\t\t)\n'
        '\t\t(fill no)\n\t\t(layer "F.CrtYd")\n'
        f'\t\t(uuid "00000000-0000-0000-0002-{uid:012d}")\n\t)\n'
    )
    out.append(')\n')
    return "".join(out)


# ==========================================================================

BUILDERS = {
    LC29H_NAME: build_lc29h,
    SAW_NAME: build_saw,
    CAST_NAME: build_castellated,
}


def verify() -> int:
    """Re-derive the numbers that came off the drawings and check them."""
    bad = 0
    ys = lc29h_pin_y()

    def chk(cond: bool, msg: str) -> None:
        nonlocal bad
        if not cond:
            print(f"  FAIL  {msg}")
            bad += 1

    chk(len(ys) == 24 // 2, f"LC29H has 12 pads per edge, got {len(ys)}")
    chk(abs(ys[0] - 7.0) < 1e-9, f"LC29H pin 1 at y=+7.0, got {ys[0]}")
    chk(abs(ys[-1] + 7.0) < 1e-9, f"LC29H pin 12 at y=-7.0, got {ys[-1]}")
    chk(abs((ys[0] - ys[-1]) - 14.0) < 1e-9,
        f"LC29H pin1..pin12 span 14.0, got {ys[0] - ys[-1]}")
    chk(abs((ys[0] - ys[6]) - 6.6) < 1e-9,
        f"LC29H upper group spans 6.6, got {ys[0] - ys[6]}")
    chk(abs((ys[6] - ys[7]) - 3.0) < 1e-9,
        f"LC29H group gap is 3.0, got {ys[6] - ys[7]}")
    chk(abs((ys[7] - ys[11]) - 4.4) < 1e-9,
        f"LC29H lower group spans 4.4, got {ys[7] - ys[11]}")
    # pads must stay inside the 16.0 body in Y and reach 1.45 past it in X
    chk(ys[0] + LC29H_PAD_Y / 2.0 <= LC29H_BODY_Y / 2.0,
        "LC29H pad 1 overhangs the body in Y")
    chk(abs((LC29H_SPAN_X - LC29H_BODY_X) / 2.0 - 1.45) < 1e-9,
        "LC29H pads should reach 1.45mm beyond the body edge")

    nums = [n for n, _, _ in SAW_PADS]
    chk(sorted(nums) == ["1", "2", "3", "4", "5"], f"SAW pads {nums}")
    top = {n for n, _, y in SAW_PADS if y > 0}
    chk(top == {"5", "4"}, f"SAW top-view upper row should be 5,4 got {top}")

    for name, fn in BUILDERS.items():
        text = fn()
        chk(text.count("(pad ") > 0, f"{name} has no pads")
        chk(text.startswith("(footprint "), f"{name} bad header")
        chk(text.rstrip().endswith(")"), f"{name} unbalanced")
        chk(text.count("(") == text.count(")"),
            f"{name} paren mismatch {text.count('(')}/{text.count(')')}")
    n_pads = build_lc29h().count("(pad ")
    chk(n_pads == 24, f"LC29H should have 24 pads, got {n_pads}")
    n_pads = build_castellated().count("(pad ")
    chk(n_pads == 12, f"castellated should have 12 pads, got {n_pads}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    bad = verify()
    if bad:
        print(f"gen_footprints: {bad} check(s) failed")
        return 1
    if args.verify:
        print(f"gen_footprints: {len(BUILDERS)} footprints, all checks passed")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in BUILDERS.items():
        (OUT_DIR / f"{name}.kicad_mod").write_text(fn(), encoding="utf-8")
        print(f"  wrote {name}.kicad_mod")
    return 0


if __name__ == "__main__":
    sys.exit(main())
