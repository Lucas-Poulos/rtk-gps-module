#!/usr/bin/env python3
"""Build the two symbols no stock KiCad 10 library provides.

``Quectel_LC29HDA`` -- 24-pin LCC dual-band RTK GNSS module. Pin numbers,
  names and directions from Quectel ``LC29H_Series_Hardware_Design`` V1.3
  (2024-07-30), Table 6 "Pin Description" (pages 26-28) and Figure 4 "Pin
  Assignment" (page 25). Cached at
  ``datasheets/LC29H_Hardware_Design_V1.3.pdf``.

``RF360_B8389`` -- GNSS L1/L5 SAW filter. Pin configuration from the
  Qualcomm RF360 B8389 data sheet V2.1 (2022-11-15) section 4, page 5.
  Cached at ``datasheets/SAW_B39162B8389P810.pdf``.

WHICH VARIANT THIS SYMBOL IS
----------------------------
The LC29H family shares one 24-pin package across variants that do NOT
share a pinout, and the hardware design guide contradicts itself about
which pins the (DA) part actually has. Figure 4 groups (AA, AI, BS, DA)
into a column showing pins 15-19 as RESERVED, while Table 6's RESERVED row
says in prose:

    "For LC29H (AA, AI, BA, BS, CA, DA), pins 5, 6, 15, 16, 18 and 19 are
     D_SEL1, D_SEL2, TXD2, RXD2, I2C_SDA/SPI_CS, and I2C_SCL/SPI_CLK
     respectively."

The V1.3 revision history settles it. Its only pin change is a list of
seven pins moved to RESERVED *for LC29H (EA) only* -- pins 5, 6, 15, 16,
18, 19 and the SPI alternates on 20/21. So (DA) keeps them, and Figure 4's
column ordering is simply mirrored on the right-hand edge: the check is
pin 20, printed "TXD1/SPI_MISO  TXD1/SPI_MISO  TXD1", where the revision
history proves the bare "TXD1" is the (EA) entry -- i.e. last, not first.

This symbol therefore follows Table 6. Because the reading is contested,
pins 15, 16, 18 and 19 are brought out through DNP resistors in the
schematic (see wire_sheets.sheet_gnss) so the board is correct under
either interpretation: unmounted, they are N/C, which is what Table 6
demands of a RESERVED pin.

Usage
-----
    python3 scripts/gen_custom_symbols.py
    python3 scripts/gen_custom_symbols.py --verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kicad_symlib import Pin, Unit, emit_symbol, upsert  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_LIB = REPO_ROOT / "design" / "lib" / "rtk-gps-module.kicad_sym"

HW_GUIDE = "https://forums.quectel.com/uploads/short-url/u7fE3GaEAynRmZ3J7ihhjXrwxTF.pdf"
SAW_DS = "https://datasheet.lcsc.com/datasheet/pdf/eab07ffddc7092a73be1e657f827b881.pdf"

# ==========================================================================
# LC29H (DA) -- Table 6, pages 26-28
# ==========================================================================
#
# Electrical types, and the reasoning where it is not the obvious choice:
#
#   VCC, V_BCKP            power_in    Table 6 types them PI
#   VDD_EXT, VDD_RF        power_out   Table 6 types them PO. VDD_EXT is a
#       2.8 V / 100 mA regulator output and VDD_RF is VCC passed through --
#       neither may be driven, and typing them power_out makes ERC say so.
#   GND                    power_in    KiCad convention for grounds
#   RF_IN                  passive     Table 6 types it AI, but an analog
#       50 ohm port has no digital direction and typing it `input` would
#       make ERC demand a driver on a net whose driver is an antenna.
#   1PPS, TXD1, TXD2,
#   ANT_ON                 output
#   WAKEUP, RESET_N,
#   D_SEL1, D_SEL2,
#   RXD1, RXD2, I2C_SCL    input
#   I2C_SDA                bidirectional
#   pins 2, 4, 17          no_connect  Table 6: "They must be left N/C and
#       cannot be connected to power or GND." no_connect makes ERC enforce
#       exactly that.

LC29H_LEFT = [
    Pin("VCC", "23", "power_in"),
    Pin("V_BCKP", "22", "power_in"),
    Pin("VDD_EXT", "7", "power_out"),
    Pin("VDD_RF", "9", "power_out"),
    Pin("RF_IN", "11", "passive"),
    Pin("RESET_N", "8", "input"),
    Pin("WAKEUP", "1", "input"),
    Pin("D_SEL1", "5", "input"),
    Pin("D_SEL2", "6", "input"),
]

LC29H_RIGHT = [
    Pin("TXD1", "20", "output"),
    Pin("RXD1", "21", "input"),
    Pin("1PPS", "3", "output"),
    Pin("ANT_ON", "14", "output"),
    Pin("I2C_SDA", "18", "bidirectional"),
    Pin("I2C_SCL", "19", "input"),
    Pin("TXD2", "15", "output"),
    Pin("RXD2", "16", "input"),
]

LC29H_BOTTOM = [
    Pin("GND", "10", "power_in", stack=True),
    Pin("GND", "12", "power_in", stack=True),
    Pin("GND", "13", "power_in", stack=True),
    Pin("GND", "24", "power_in", stack=True),
    Pin("RSVD", "2", "no_connect", stack=True),
    Pin("RSVD", "4", "no_connect", stack=True),
    Pin("RSVD", "17", "no_connect", stack=True),
]

# ==========================================================================
# B8389 SAW -- data sheet section 4, page 5
# ==========================================================================
#
# "1 Input / 4 Output / 2, 3, 5 Ground". Both ports are 50 ohm // 5.1 nH
# (section 6, page 7) -- the shunt inductors that make that true are
# discrete parts on the RF sheet, not part of this symbol.

SAW_LEFT = [Pin("IN", "1", "passive")]
SAW_RIGHT = [Pin("OUT", "4", "passive")]
SAW_BOTTOM = [
    Pin("GND", "2", "passive", stack=True),
    Pin("GND", "3", "passive", stack=True),
    Pin("GND", "5", "passive", stack=True),
]

SYMBOLS = [
    {
        "name": "Quectel_LC29HDA",
        "ref": "U",
        "units": [Unit(left=LC29H_LEFT, right=LC29H_RIGHT,
                       bottom=LC29H_BOTTOM, min_half_width=30.48)],
        "props": {
            "Footprint": "rtk-gps-module:Quectel_LC29H_LCC-24_12.2x16.0mm",
            "Datasheet": HW_GUIDE,
            "Description": (
                "Quectel LC29H (DA) dual-band L1+L5 RTK GNSS rover module, "
                "24-pin LCC 16.0x12.2mm. Onboard RTK engine, RTCM3 input "
                "over UART1, 1PPS output."
            ),
            "MPN": "LC29HDAMD",
            "Manufacturer": "Quectel",
            "LCSC": "C20748061",
        },
        "expect_pins": 24,
    },
    {
        "name": "RF360_B8389",
        "ref": "FL",
        "units": [Unit(left=SAW_LEFT, right=SAW_RIGHT,
                       bottom=SAW_BOTTOM, min_half_width=12.7)],
        "props": {
            "Footprint": "rtk-gps-module:SAW_RF360_SMD1411-5P_1.4x1.1mm",
            "Datasheet": SAW_DS,
            "Description": (
                "Qualcomm RF360 B8389 dual-band GNSS SAW filter. "
                "Pass band 1 1176.45MHz (L5/E5a/B2a), pass band 2 1583MHz "
                "(L1/E1/B1/G1). 1.0/1.8dB insertion loss. 50ohm // 5.1nH."
            ),
            "MPN": "B39162B8389P810",
            "Manufacturer": "Qualcomm RF360",
            "LCSC": "C5556161",
        },
        "expect_pins": 5,
    },
]


def verify() -> int:
    bad = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal bad
        if not cond:
            print(f"  FAIL  {msg}")
            bad += 1

    # --- LC29H: every pad 1..24 present exactly once -----------------
    allpins = LC29H_LEFT + LC29H_RIGHT + LC29H_BOTTOM
    nums = sorted(int(p.number) for p in allpins)
    chk(nums == list(range(1, 25)),
        f"LC29H pin numbers must be 1..24 exactly once, got {nums}")

    # --- the pin map that the whole design hangs on ------------------
    # Transcribed independently from Table 6 as a second pass, so a typo
    # in the symbol tables above has to be made twice to survive.
    expect = {
        "1": ("WAKEUP", "input"), "3": ("1PPS", "output"),
        "5": ("D_SEL1", "input"), "6": ("D_SEL2", "input"),
        "7": ("VDD_EXT", "power_out"), "8": ("RESET_N", "input"),
        "9": ("VDD_RF", "power_out"), "11": ("RF_IN", "passive"),
        "14": ("ANT_ON", "output"), "15": ("TXD2", "output"),
        "16": ("RXD2", "input"), "18": ("I2C_SDA", "bidirectional"),
        "19": ("I2C_SCL", "input"), "20": ("TXD1", "output"),
        "21": ("RXD1", "input"), "22": ("V_BCKP", "power_in"),
        "23": ("VCC", "power_in"),
        "10": ("GND", "power_in"), "12": ("GND", "power_in"),
        "13": ("GND", "power_in"), "24": ("GND", "power_in"),
        "2": ("RSVD", "no_connect"), "4": ("RSVD", "no_connect"),
        "17": ("RSVD", "no_connect"),
    }
    got = {p.number: (p.name, p.etype) for p in allpins}
    for num, want in expect.items():
        chk(got.get(num) == want,
            f"LC29H pin {num}: expected {want}, symbol has {got.get(num)}")

    # RESERVED pins must be no_connect so ERC rejects any connection --
    # Table 6 forbids tying them even to GND.
    for num in ("2", "4", "17"):
        chk(got[num][1] == "no_connect",
            f"LC29H pin {num} is RESERVED and must be typed no_connect")
    # Supply outputs must never be typed power_in, or ERC will happily
    # let the schematic drive 3V3 onto a 2.8V regulator output.
    for num in ("7", "9"):
        chk(got[num][1] == "power_out",
            f"LC29H pin {num} is a supply OUTPUT (Table 6 'PO')")

    # --- SAW ---------------------------------------------------------
    sawpins = SAW_LEFT + SAW_RIGHT + SAW_BOTTOM
    snums = sorted(int(p.number) for p in sawpins)
    chk(snums == [1, 2, 3, 4, 5], f"SAW pins must be 1..5, got {snums}")
    sgot = {p.number: p.name for p in sawpins}
    chk(sgot["1"] == "IN", "SAW pin 1 is Input")
    chk(sgot["4"] == "OUT", "SAW pin 4 is Output")
    for n in ("2", "3", "5"):
        chk(sgot[n] == "GND", f"SAW pin {n} is Ground")

    # --- every symbol builds, and carries a resolved LCSC number -----
    for spec in SYMBOLS:
        text, pinmaps = emit_symbol(
            spec["name"], spec["units"], spec["props"], spec["ref"])
        n = text.count("(pin ")
        chk(n == spec["expect_pins"],
            f"{spec['name']} emitted {n} pins, expected {spec['expect_pins']}")
        chk(text.count("(") == text.count(")"),
            f"{spec['name']} paren mismatch")
        lcsc = spec["props"].get("LCSC", "")
        chk(lcsc.startswith("C") and lcsc[1:].isdigit(),
            f"{spec['name']} LCSC field {lcsc!r} is not a Cxxxxx number")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    bad = verify()
    if bad:
        print(f"gen_custom_symbols: {bad} check(s) failed")
        return 1
    if args.verify:
        print(f"gen_custom_symbols: {len(SYMBOLS)} symbols, all checks passed")
        return 0

    for spec in SYMBOLS:
        text, _ = emit_symbol(
            spec["name"], spec["units"], spec["props"], spec["ref"])
        upsert(OUT_LIB, text, spec["name"], "gen_custom_symbols.py")
        print(f"  upserted {spec['name']}")
    print(f"wrote {OUT_LIB.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
