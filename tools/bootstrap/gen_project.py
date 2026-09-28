#!/usr/bin/env python3
"""Generate design/ for rtk-gps-module.

A centimetre-class RTK GNSS receiver built as a solder-down module:
castellated edges plus a USB-C port so it also works standalone.

Five hierarchical sheets. Placement lives here; nets live in
wire_sheets.py. Everything except the GNSS receiver and its SAW filter is
a discrete part -- the LNA bias tee, the antenna power switch, the RX
level attenuator and the 1PPS indicator are all built from single
transistors rather than bought as a block.

Every LCSC number in SOURCING below was resolved against the live LCSC
catalogue, not recalled. See docs/bom.md for stock and pricing at the
time of resolution.

Run order:
    python3 scripts/gen_custom_symbols.py
    python3 scripts/gen_footprints.py
    python3 scripts/gen_project.py --verify   # gate, writes nothing
    python3 scripts/gen_project.py
    python3 scripts/verify_project.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import kicad_sch as ks
from kicad_sch import (
    Comp, Note, Sheet, SymbolCache, uid,
    write_sheet, write_root, write_project, write_lib_tables,
)
from calc_impedance import RF_GAP, RF_TRACE_W

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"
PROJECT = "rtk-gps-module"
REV = "A"
COMPANY = "Lucas Poulos"
ROOT_UUID = uid("root/rtk-gps-module")

FOOTPRINT_DIR = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
)
PROJECT_FP_DIR = DESIGN / "lib" / f"{PROJECT}.pretty"
PROJECT_SYM_LIB = DESIGN / "lib" / f"{PROJECT}.kicad_sym"

# A3. Notes are anchored "left bottom", so a multi-line note grows DOWNWARD
# from its y -- one placed near the bottom edge silently runs off the page
# and the PDF just clips it. check() enforces the box.
PAGE_W, PAGE_H = 420.0, 297.0
TEXT_MAX_X, TEXT_MAX_Y = 408.0, 282.0
TITLE_BLOCK = (270.0, 252.0)
LINE_PITCH = 1.7
CHAR_W = 0.70

# Closest two part origins may sit. Below this their stub labels
# start printing on top of each other.
MIN_PART_GAP = 14.0

# --------------------------------------------------------------------------
# Net classes
#
# RF is the reason this table is not the library default. The antenna path
# from the u.FL centre pin to RF_IN is a 50 ohm single-ended line and the
# LC29H datasheet says so explicitly ("50 Ohm characteristic impedance",
# Table 6, pin 11).
#
# The width is NOT a round number picked by eye -- it is imported from
# calc_impedance.py, which solves the conductor-backed CPW conformal-
# mapping model for a JLCPCB JLC04161H-3313 four-layer stackup (0.2104 mm
# prepreg, er 4.3) and a 0.2 mm coplanar gap. That gives 0.38 mm for
# 50.2 ohm. Treating the same track as plain microstrip would say 0.41 mm
# and land it near 47 ohm, which is the mistake this import exists to
# prevent. verify_project.py asserts the two still agree.
#
# The clearance is the same 0.2 mm the CPWG gap needs, so the netclass
# cannot silently widen the gap and detune the line.
# --------------------------------------------------------------------------
ks.NET_CLASSES = [
    # name, track_width, clearance, diff_pair_width, diff_pair_gap
    ("Default", 0.20, 0.20, 0.2, 0.20),
    ("RF",      RF_TRACE_W, RF_GAP, 0.2, 0.20),
    ("USB",     0.25, 0.20, 0.20, 0.13),
    ("Power",   0.50, 0.20, 0.2, 0.20),
]

# KiCad matches these with WILDCARDS, not regex -- a "/^...$/" pattern is
# accepted by the file format, shows up in the GUI, and silently matches
# nothing. Local nets also carry their sheet path ("/RF/ANT_RF"), so the
# RF entries need a leading * to catch them. Both mistakes are invisible
# until you read the exported netlist's per-net class, which is exactly
# what verify_project.py now does.
ks.NETCLASS_PATTERNS = [
    ("RF",    "*ANT_RF"),
    ("RF",    "*RF_A"),
    ("RF",    "*RF_B"),
    ("RF",    "RF_IN"),
    ("USB",   "USB_DP"),
    ("USB",   "USB_DM"),
    ("Power", "+3V3"),
    ("Power", "VBUS"),
    ("Power", "VSYS"),
    ("Power", "V_BCKP"),
    ("Power", "VEXT_5V"),
    ("Power", "VBCKP_EXT"),
    ("Power", "VDD_RF"),
    ("Power", "VDD_EXT"),
    ("Power", "*ANT_PWR"),
    ("Power", "*ANT_BIAS"),
]

# --------------------------------------------------------------------------
# Footprints
# --------------------------------------------------------------------------
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
L0402 = "Inductor_SMD:L_0402_1005Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
SOIC8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
SOD323 = "Diode_SMD:D_SOD-323"
USBC = "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12"
UFL = "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical"

LC29H_FP = f"{PROJECT}:Quectel_LC29H_LCC-24_12.2x16.0mm"
SAW_FP = f"{PROJECT}:SAW_RF360_SMD1411-5P_1.4x1.1mm"
CAST_FP = f"{PROJECT}:Castellated_1x12_P1.27mm"

# --------------------------------------------------------------------------
# Library ids
# --------------------------------------------------------------------------
LC29H = f"{PROJECT}:Quectel_LC29HDA"
SAW = f"{PROJECT}:RF360_B8389"
LDO = "Regulator_Linear:AP2112K-3.3"
USBLC6 = "Power_Protection:USBLC6-2SC6"
CH340 = "Interface_USB:CH340N"
USB_C = "Connector:USB_C_Receptacle_USB2.0_16P"
COAX = "Connector:Conn_Coaxial"
PMOS = "Transistor_FET:AO3401A"
NPN = "Transistor_BJT:MMBT3904"
BAT54C = "Diode:BAT54C"
TVS = "Device:D_TVS"
LED = "Device:LED"
CONN12 = "Connector_Generic:Conn_01x12"

# --------------------------------------------------------------------------
# Sourcing. Every Cxxxxx here was resolved against the live LCSC catalogue
# on 2026-09-28. "Basic" marks a JLCPCB basic part -- no per-part feeder
# setup fee, which is why the passives are all from that set.
#
#   refdes prefix -> (MPN, manufacturer, LCSC)
# --------------------------------------------------------------------------
SOURCING: dict[str, tuple[str, str, str]] = {
    # --- the receiver and its filter ---
    "U201": ("LC29HDAMD", "Quectel", "C20748061"),
    "FL301": ("B39162B8389P810", "Qualcomm RF360", "C5556161"),
    # --- actives ---
    "U101": ("AP2112K-3.3TRG1", "Diodes Inc.", "C23380830"),
    "U401": ("CH340N", "WCH", "C2977777"),
    "D101": ("USBLC6-2SC6", "STMicroelectronics", "C2827654"),
    "D102": ("BAT54C", "Changjiang Electronics", "C916424"),
    "D104": ("BAT54C", "Changjiang Electronics", "C916424"),
    "D103": ("SD05", "Shunsheng Electronic", "C502527"),
    "D301": ("RF1256-000", "Onsemi", "C207186"),
    "Q301": ("AO3401A", "Alpha & Omega", "C15127"),
    "Q302": ("MMBT3904", "Changjiang Electronics", "C20526"),
    "Q501": ("MMBT3904", "Changjiang Electronics", "C20526"),
    # --- connectors ---
    "J101": ("TYPE-C 16PIN 2MD(073)", "Korean Hroparts", "C2765186"),
    "J301": ("BWU.FL-IPEX1", "B&W", "C5137195"),
    # --- indicators ---
    "D105": ("KT-0603R", "Hubei KENTO", "C2286"),
    "D501": ("KT-0603G", "Hubei KENTO", "C12624"),
    # --- RF magnetics ---
    "L301": ("LQW15AN68NG00D", "muRata", "C108965"),
    "L302": ("LQW15AN5N1B00D", "muRata", "C408161"),
    "L303": ("LQW15AN5N1B00D", "muRata", "C408161"),
}

# Passives are sourced by VALUE, not by refdes -- one line per distinct
# value keeps the BOM short and the reels few.
#   (value, footprint) -> (MPN, manufacturer, LCSC)
PASSIVES: dict[tuple[str, str], tuple[str, str, str]] = {
    ("0R", R0402): ("0402WGF0000TCE", "UNI-ROYAL", "C17168"),
    ("10R", R0402): ("0402WGF100JTCE", "UNI-ROYAL", "C25077"),
    ("22R", R0402): ("0402WGF220JTCE", "UNI-ROYAL", "C25092"),
    ("1k", R0402): ("0402WGF1001TCE", "UNI-ROYAL", "C11702"),
    ("4.7k", R0402): ("0402WGF4701TCE", "UNI-ROYAL", "C25900"),
    ("5.1k", R0402): ("0402WGF5101TCE", "UNI-ROYAL", "C25905"),
    ("10k", R0402): ("0402WGF1002TCE", "UNI-ROYAL", "C25744"),
    ("100k", R0402): ("0402WGF1003TCE", "UNI-ROYAL", "C25741"),
    ("33pF", C0402): ("0402CG330J500NT", "FH", "C1562"),
    ("100pF", C0402): ("0402CG101J500NT", "FH", "C1546"),
    ("100nF", C0402): ("CL05B104KO5NNNC", "Samsung", "C1525"),
    ("4.7uF", C0603): ("CL10A475KO8NNNC", "Samsung", "C19666"),
    ("10uF", C0805): ("CL21A106KAYNNNE", "Samsung", "C15850"),
}

DATASHEETS = {
    "U201": "https://forums.quectel.com/uploads/short-url/u7fE3GaEAynRmZ3J7ihhjXrwxTF.pdf",
    "FL301": "https://datasheet.lcsc.com/datasheet/pdf/eab07ffddc7092a73be1e657f827b881.pdf",
    "U101": "https://www.diodes.com/assets/Datasheets/AP2112.pdf",
    "U401": "https://www.wch-ic.com/downloads/CH340DS1_PDF.html",
}

# Parts deliberately left unfitted. A DNP part is still a footprint, a net
# and a documented intent -- which is the entire point of putting it in the
# schematic instead of in a comment.
# Board features, not purchased parts: the castellated edges ARE the PCB.
# They carry a footprint and a netlist but nothing to order, so they are
# exempt from the LCSC requirement and excluded from the BOM.
NO_BOM = {"J501", "J502"}

DNP = {
    "C302": "pi-match shunt, antenna side -- fit only if the antenna needs it",
    "C303": "pi-match shunt, filter side -- fit only if the antenna needs it",
    "R305": "bypasses the ANT_ON switch to power the antenna unconditionally",
    "R206": "pull D_SEL1 high to select SPI/I2C instead of UART1",
    "R207": "pull D_SEL2 high to select I2C instead of UART1",
    "R208": "brings I2C_SDA out to the castellated edge",
    "R209": "brings I2C_SCL out to the castellated edge",
    "R210": "brings TXD2 (1.8 V debug UART) out to the castellated edge",
    "R211": "brings RXD2 (1.8 V debug UART) out to the castellated edge",
}


def P(ref, lib_id, value, x, y, fp=None, rot=0, unit=1, mirror=None, **props):
    """One placed part. ``fp`` is folded into the property dict."""
    if fp:
        props["Footprint"] = fp
    return Comp(ref, lib_id, value, x, y, rot, unit, props, mirror)


def R(ref, value, x, y, rot=0, tol="1%"):
    return P(ref, "Device:R", value, x, y, R0402, rot, Tolerance=tol)


def C(ref, value, x, y, rot=0, fp=C0402):
    return P(ref, "Device:C", value, x, y, fp, rot)


def L(ref, value, x, y, rot=0):
    return P(ref, "Device:L", value, x, y, L0402, rot)


# ==========================================================================
# Sheet 01 -- USB input, 5 V ORing, 3V3 LDO, backup domain
# ==========================================================================
def sheet_power() -> Sheet:
    c = [
        # USB-C. CC1/CC2 each need their own 5.1k: a single shared resistor
        # advertises the wrong source current and some chargers will not
        # enumerate at all.
        P("J101", USB_C, "USB-C 16P", 45, 95, USBC),
        R("R101", "5.1k", 95, 120, 90),
        R("R102", "5.1k", 115, 120, 90),
        P("D101", USBLC6, "USBLC6-2SC6", 150, 150, SOT236),

        # 5 V ORing: USB or the carrier board, whichever is higher.
        P("D102", BAT54C, "BAT54C", 160, 70, SOT23),
        P("D103", TVS, "SD05", 205, 90, SOD323, 90),
        C("C101", "10uF", 230, 90, 90, C0805),
        C("C102", "100nF", 250, 90, 90),

        # 3V3. AP2112K is a 600 mA LDO with 55 dB PSRR at 1 kHz; the GNSS
        # VCC pin wants "clean and steady" (LC29H HW design, Table 6) and a
        # buck's switching residue lands squarely in the GNSS band.
        P("U101", LDO, "AP2112K-3.3", 300, 80, SOT235),
        C("C103", "10uF", 350, 100, 90, C0805),
        C("C104", "100nF", 372, 100, 90),

        # Backup domain. V_BCKP must stay alive for a hot start, so it is
        # ORed from 3V3 and from an optional external cell on the edge.
        P("D104", BAT54C, "BAT54C", 160, 205, SOT23),
        C("C105", "4.7uF", 235, 225, 90, C0603),
        C("C106", "100nF", 257, 225, 90),
        C("C107", "33pF", 279, 225, 90),

        P("D105", LED, "RED", 340, 195, LED0603, 270),
        R("R103", "1k", 340, 225, 90),
    ]
    n = [
        Note("SHEET 1 - INPUT, 5 V ORING, 3V3 AND THE BACKUP DOMAIN",
             25, 30, 2.2, True),
        Note("D102 ORs USB VBUS against the carrier board's 5 V so the two\n"
             "can be present at once without either back-feeding the other.\n"
             "One BAT54C is two Schottkys; a shared cathode is exactly the\n"
             "OR. Cost of the diode drop: VSYS = 4.7 V, and the LDO needs\n"
             "only 3.62 V to hold 3.3 V at 600 mA.",
             25, 250),
        Note("D104 does the same job for the backup rail. V_BCKP holds the\n"
             "RTC and the ephemeris cache: keep it alive and the receiver\n"
             "hot-starts in ~1 s instead of cold-starting in ~30 s. With\n"
             "nothing on VBCKP_EXT it simply follows 3V3.\n"
             "C105/C106/C107 are the 4.7uF + 100nF + 33pF the LC29H\n"
             "hardware design asks for on this pin (section 3.2).",
             205, 250),
    ]
    return Sheet("01_power.kicad_sch", "Power", "2", paper="A3",
                 title="USB input, 5 V ORing, 3V3 LDO, backup domain",
                 comps=c, notes=n)


# ==========================================================================
# Sheet 02 -- the receiver
# ==========================================================================
def sheet_gnss() -> Sheet:
    c = [
        P("U201", LC29H, "LC29HDAMD", 200, 130, LC29H_FP),

        # VCC decoupling, smallest part closest to the pin. The LC29H
        # hardware design names this network exactly: 10uF + 100nF + 33pF.
        C("C201", "10uF", 105, 65, 90, C0805),
        C("C202", "100nF", 85, 65, 90),
        C("C203", "33pF", 65, 65, 90),
        C("C204", "100nF", 120, 210, 90),   # VDD_EXT

        # RESET_N: 10k pull-up so the module runs with the pin unwired, and
        # 100nF so a hot-plugged carrier cannot bounce it.
        R("R201", "10k", 90, 130, 90),
        C("C205", "100nF", 70, 155, 90),

        # WAKEUP belongs to the backup domain and must be low or open
        # before the module sleeps, so it gets a pulldown, not a pull-up.
        R("R202", "100k", 90, 185, 90),

        # 1.8 V for D_SEL. VDD_EXT is 2.8 V and D_SEL tops out at 2.1 V, so
        # the interface-select pins cannot be strapped to it directly.
        R("R203", "4.7k", 300, 205, 90),
        R("R204", "10k", 300, 245, 90),
        R("R206", "0R", 340, 205, 90),
        R("R207", "0R", 365, 205, 90),

        # RX attenuator -- see the note.
        R("R205", "1k", 330, 120),
        R("R212", "10k", 370, 140, 90),

        R("R213", "22R", 330, 95),          # TXD1 series damping

        # Contested pins, brought out only through DNP links.
        R("R208", "0R", 330, 155),
        R("R209", "0R", 330, 170),
        R("R210", "0R", 330, 250),
        R("R211", "0R", 330, 265),
    ]
    n = [
        Note("SHEET 2 - LC29H (DA) DUAL-BAND RTK RECEIVER", 25, 30, 2.2, True),
        Note("RX LEVEL. RXD1 is specified VIHmax = 3.08 V (Table 6) and the\n"
             "CH340N drives a full 3.3 V. R205/R212 divide by 10/11 -> 3.0 V,\n"
             "inside spec and still far above the 1.75 V VIHmin. The divider\n"
             "sits AT the module pin, so it protects the castellated RXD1\n"
             "pad and the USB bridge with one pair of resistors instead of\n"
             "one pair per source. Source impedance 909 R into ~15 pF is a\n"
             "14 ns edge -- negligible against a 1.09 us bit at 921600 baud.",
             25, 240),
        Note("D_SEL1/D_SEL2 pick the host interface. Both are pulled down\n"
             "internally by 75k, and 0,0 selects UART1 -- which is what this\n"
             "board wants, so the default needs no parts. R206/R207 are DNP\n"
             "links to a 1.9 V node for the other three combinations.\n"
             "The 1.9 V comes from dividing VDD_EXT 2.8 V by 4.7k/10k:\n"
             "tying D_SEL to VDD_EXT directly would exceed VIHmax = 2.1 V.",
             200, 232),
    ]
    return Sheet("02_gnss.kicad_sch", "GNSS", "3", paper="A3",
                 title="LC29H (DA) receiver, decoupling and strapping",
                 comps=c, notes=n)


# ==========================================================================
# Sheet 03 -- RF front end
# ==========================================================================
def sheet_rf() -> Sheet:
    c = [
        # The signal chain runs left to right along y=105, with every
        # shunt element dropped to y=135 so no two stub labels land on
        # the same spot.
        P("J301", COAX, "u.FL", 45, 105, UFL),
        P("D301", TVS, "RF1256-000", 85, 135,
          "Diode_SMD:D_0603_1608Metric", 90),
        L("L301", "68nH", 115, 135, 90),    # bias-tee choke
        C("C301", "100pF", 150, 105),       # DC block
        C("C302", "DNP", 185, 135, 90),     # pi shunt, antenna side
        R("R301", "0R", 220, 105),          # pi series
        C("C303", "DNP", 255, 135, 90),     # pi shunt, filter side
        L("L302", "5.1nH", 290, 135, 90),   # SAW input match
        P("FL301", SAW, "B8389", 335, 105, SAW_FP),
        L("L303", "5.1nH", 385, 135, 90),   # SAW output match

        # Antenna power switch, straight from the reference design.
        R("R302", "10R", 100, 200),         # short-circuit protection
        R("R303", "10k", 140, 175, 90),     # gate pull-up
        R("R305", "0R", 170, 160),          # DNP: antenna always on
        P("Q301", PMOS, "AO3401A", 170, 200, SOT23),
        P("Q302", NPN, "MMBT3904", 170, 255, SOT23),
        R("R304", "10k", 115, 262),         # base resistor
        C("C304", "100pF", 235, 200, 90),
        C("C305", "100nF", 265, 200, 90),
    ]
    n = [
        Note("SHEET 3 - 50 OHM ANTENNA FRONT END AND BIAS TEE",
             25, 30, 2.2, True),
        Note("The whole chain from J301 to RF_IN is a 50 ohm line. L301\n"
             "injects DC onto it without loading it: 68nH is 673 ohm at\n"
             "L1 and 502 ohm at L5, both high against 50 ohm. C301 blocks\n"
             "that DC out of the module. R301/C302/C303 are a pi network\n"
             "left as 0R + two unfitted pads -- somewhere to retune if a\n"
             "particular antenna misbehaves, at no cost if it does not.",
             25, 60),
        Note("FL301 is the dual-band SAW Quectel names in its own reference\n"
             "design. It passes 1176.45 MHz (L5/E5a/B2a) and 1559-1607 MHz\n"
             "(L1/E1/B1/G1) and rejects 20-39 dB everywhere else. An L1-ONLY\n"
             "SAW here would be a bug: it would delete the second frequency\n"
             "that makes this an RTK receiver rather than a plain GPS.\n"
             "L302/L303 are the 5.1 nH shunts the SAW needs to actually\n"
             "present 50 ohm -- its ports are 50 ohm // 5.1 nH, not 50 ohm.",
             215, 60),
        Note("Q301 switches antenna power under ANT_ON, so a shorted antenna\n"
             "cannot sit across VDD_RF forever and the antenna drops out in\n"
             "backup mode. R302 limits that fault current to ~330 mA.\n"
             "Q302 level-shifts: ANT_ON idles at 2.8 V and the PMOS gate has\n"
             "to be pulled to VDD_RF, which is 3.3 V. Fit R305 instead of\n"
             "Q301/Q302/R303 to power the antenna unconditionally.",
             25, 262),
    ]
    return Sheet("03_rf.kicad_sch", "RF", "4", paper="A3",
                 title="Antenna interface, bias tee and dual-band SAW",
                 comps=c, notes=n)


# ==========================================================================
# Sheet 04 -- USB-UART bridge
# ==========================================================================
def sheet_usb() -> Sheet:
    c = [
        P("U401", CH340, "CH340N", 180, 120, SOIC8),
        C("C401", "100nF", 120, 95, 90),    # VCC
        C("C402", "100nF", 250, 95, 90),    # V3
        R("R401", "0R", 260, 145),          # isolate the bridge from RX_BUS
    ]
    n = [
        Note("SHEET 4 - USB TO UART BRIDGE", 25, 30, 2.2, True),
        Note("CH340N needs no crystal and costs less than a dollar, which is\n"
             "why it is here rather than a CP2102 or an FT232. Running it at\n"
             "3.3 V means V3 ties to VCC (WCH datasheet section 5) and the\n"
             "TXD/RXD pair needs no level shifter -- only the 3.08 V limit on\n"
             "the receiver's RXD1, handled by the divider on sheet 2.",
             25, 190),
        Note("R401 is a fitted 0R, not a wire. Cut it and the castellated\n"
             "UART pads own the bus outright, so a carrier board's own\n"
             "host can drive RXD1 without fighting the bridge's idle-high\n"
             "TXD output. That contention is the one failure mode of having\n"
             "both a USB port and an exposed UART on the same two pins.",
             25, 240),
    ]
    return Sheet("04_usb.kicad_sch", "USB", "5", paper="A3",
                 title="CH340N USB-UART bridge",
                 comps=c, notes=n)


# ==========================================================================
# Sheet 05 -- castellated edge and indicators
# ==========================================================================
def sheet_io() -> Sheet:
    c = [
        P("J501", CONN12, "LEFT EDGE", 90, 100, CAST_FP),
        P("J502", CONN12, "RIGHT EDGE", 250, 100, CAST_FP),

        # 1PPS indicator. 1PPS is guaranteed only 2.1 V high and an LED
        # hung straight off it would be dim and would load the edge, so it
        # gets a transistor.
        P("Q501", NPN, "MMBT3904", 350, 150, SOT23),
        R("R501", "10k", 310, 155),
        P("D501", LED, "GREEN 1PPS", 355, 100, LED0603, 270),
        R("R502", "1k", 355, 70, 90),
    ]
    n = [
        Note("SHEET 5 - CASTELLATED EDGE AND INDICATORS", 25, 30, 2.2, True),
        Note("24 castellated pads on 1.27 mm, twelve per edge. Pitch chosen\n"
             "so the module drops onto 0.1 in perfboard and onto the header\n"
             "every carrier already has.\n"
             "Pads 5-8 on the right edge are the 1.8 V domain (TXD2, RXD2,\n"
             "D_SEL1, D_SEL2). They are NOT 3.3 V tolerant -- VIHmax is\n"
             "2.1 V. Each reaches the edge only through a DNP link so the\n"
             "default board cannot present them to a 3.3 V host by accident.",
             25, 200),
    ]
    return Sheet("05_io.kicad_sch", "IO", "6", paper="A3",
                 title="Castellated edge pinout and status indicators",
                 comps=c, notes=n)


# ==========================================================================

ROOT_NOTES = [
    Note("RTK GNSS MODULE - centimetre positioning from a USB stick",
         25, 215, 2.0, True),
    Note("LC29H (DA) dual-band L1+L5 RTK rover. Feed it RTCM3 over the UART\n"
         "and it resolves carrier phase to ~1-2 cm horizontal. Corrections\n"
         "come from the host -- an NTRIP client on a phone, a Pi or a PC --\n"
         "so there is no radio on the board and nothing to license.",
         25, 228),
    Note("Everything around the receiver is discrete: the bias tee, the\n"
         "antenna power switch, the RX attenuator and the 1PPS driver are\n"
         "single transistors and passives, not modules.",
         25, 258),
]


def stamp_sourcing(sheets) -> None:
    """Attach MPN / Manufacturer / LCSC / Datasheet / DNP to every part.

    Passives are matched by (value, footprint); everything else by refdes.
    A part that matches neither is left bare and check() fails on it, which
    is the only reason an unsourced part cannot reach the BOM.
    """
    for s in sheets:
        for c in s.comps:
            hit = SOURCING.get(c.ref)
            if hit is None:
                hit = PASSIVES.get((c.value, c.props.get("Footprint", "")))
            if hit:
                mpn, mfr, lcsc = hit
                c.props.setdefault("MPN", mpn)
                c.props.setdefault("Manufacturer", mfr)
                c.props.setdefault("LCSC", lcsc)
            ds = DATASHEETS.get(c.ref)
            if ds:
                c.props.setdefault("Datasheet", ds)
            if c.ref in DNP:
                c.props.setdefault("DNP", "yes")
                c.props.setdefault("Note", DNP[c.ref])


def build() -> tuple[list[Sheet], SymbolCache]:
    sheets = [sheet_power(), sheet_gnss(), sheet_rf(), sheet_usb(), sheet_io()]
    stamp_sourcing(sheets)
    cache = SymbolCache({PROJECT: PROJECT_SYM_LIB})
    import wire_sheets
    wire_sheets.wire_all(sheets, cache)
    return sheets, cache


def _fp_exists(fp: str) -> bool:
    lib, _, mod = fp.partition(":")
    if lib == PROJECT:
        return (PROJECT_FP_DIR / f"{mod}.kicad_mod").exists()
    return (FOOTPRINT_DIR / f"{lib}.pretty" / f"{mod}.kicad_mod").exists()


def check(sheets: list[Sheet], cache: SymbolCache) -> list[str]:
    """Everything that must hold before a single byte is written."""
    fails: list[str] = []
    seen_fp: dict[str, bool] = {}
    by_ref: dict[str, list[Comp]] = {}

    for s in sheets:
        for i, n in enumerate(s.notes):
            lines = n.text.split("\n")
            h = len(lines) * n.size * LINE_PITCH
            w = max(len(ln) for ln in lines) * n.size * CHAR_W
            x2, y2 = n.x + w, n.y + h
            tag = f"{s.filename}: note {i} ({lines[0][:34]!r})"
            if y2 > TEXT_MAX_Y:
                fails.append(f"{tag} runs off the bottom: "
                             f"ends at y={y2:.0f}, limit {TEXT_MAX_Y:.0f}")
            if x2 > TEXT_MAX_X:
                fails.append(f"{tag} runs off the right: "
                             f"ends at x={x2:.0f}, limit {TEXT_MAX_X:.0f}")
            if x2 > TITLE_BLOCK[0] and y2 > TITLE_BLOCK[1]:
                fails.append(f"{tag} overlaps the title block")
        for c in s.comps:
            by_ref.setdefault(c.ref, []).append(c)
            if cache.definition(c.lib_id) is None:
                fails.append(f"{s.filename}: {c.ref} lib_id {c.lib_id} not found")
            if not cache.pins(c.lib_id, c.unit):
                fails.append(f"{s.filename}: {c.ref} unit {c.unit} has no pins")
            fp = c.props.get("Footprint")
            if not fp:
                fails.append(f"{s.filename}: {c.ref} has no Footprint")
                continue
            if fp not in seen_fp:
                seen_fp[fp] = _fp_exists(fp)
            if not seen_fp[fp]:
                fails.append(f"{s.filename}: {c.ref} footprint missing: {fp}")

            # Nothing reaches the BOM without a resolved LCSC number. The
            # one thing this project must not do is invent one.
            if c.ref.startswith("#") or c.ref in NO_BOM or c.ref in DNP:
                continue
            lcsc = c.props.get("LCSC", "")
            if not lcsc:
                fails.append(f"{s.filename}: {c.ref} ({c.value}) has no LCSC "
                             f"number -- add it to SOURCING or PASSIVES")
            elif not (lcsc.startswith("C") and lcsc[1:].isdigit()):
                fails.append(f"{s.filename}: {c.ref} LCSC {lcsc!r} malformed")

    # Placement. Two parts too close together, or a part sitting under a
    # note, produces a schematic that netlists perfectly and cannot be
    # read -- which no amount of ERC will ever catch.
    for s in sheets:
        cs = s.comps
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                a, b = cs[i], cs[j]
                d = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
                if d < MIN_PART_GAP:
                    fails.append(f"{s.filename}: {a.ref} and {b.ref} are "
                                 f"{d:.1f} mm apart, minimum is "
                                 f"{MIN_PART_GAP}")
        for n in s.notes:
            lines = n.text.split("\n")
            h = len(lines) * n.size * LINE_PITCH
            w = max(len(ln) for ln in lines) * n.size * CHAR_W
            for c in cs:
                if (n.x - 6 <= c.x <= n.x + w + 6
                        and n.y - 6 <= c.y <= n.y + h + 6):
                    fails.append(f"{s.filename}: {c.ref} sits under the note "
                                 f"{lines[0][:30]!r}")

    for ref, cs in by_ref.items():
        if len({c.lib_id for c in cs}) > 1:
            fails.append(f"{ref}: units disagree on lib_id")
        if len({c.props.get('Footprint') for c in cs}) > 1:
            fails.append(f"{ref}: units disagree on footprint")
        units = [c.unit for c in cs]
        if len(units) != len(set(units)):
            fails.append(f"{ref}: duplicate unit placement {sorted(units)}")

    # Every DNP entry must name a part that exists, or the table is lying.
    placed = set(by_ref)
    for ref in DNP:
        if ref not in placed:
            fails.append(f"DNP names {ref}, which is not placed anywhere")
    for ref in SOURCING:
        if ref not in placed:
            fails.append(f"SOURCING names {ref}, which is not placed anywhere")

    return fails


def generate(verify_only: bool = False) -> int:
    sheets, cache = build()
    comps = [c for s in sheets for c in s.comps]
    by_ref = {c.ref for c in comps}
    fails = check(sheets, cache)

    if fails:
        print("refusing to write - verification failed:")
        for f in fails[:25]:
            print(f"  - {f}")
        if len(fails) > 25:
            print(f"  ... and {len(fails) - 25} more")
        return 1
    if verify_only:
        print(f"verify OK: {len(comps)} placements, {len(by_ref)} refdes, "
              f"{sum(len(s.labels) for s in sheets)} labels")
        return 0

    DESIGN.mkdir(parents=True, exist_ok=True)
    write_root(
        DESIGN / f"{PROJECT}.kicad_sch", sheets, PROJECT, ROOT_UUID,
        "RTK GNSS Module", REV, COMPANY,
        ["Top sheet - hierarchy overview",
         "LC29H dual-band L1+L5 RTK | discrete bias tee | USB-C + castellated"],
        ROOT_NOTES, cols=3, origin=(30, 60), cell=(85, 55), box=(65, 38),
    )
    pwr: dict[str, int] = {}
    for s in sheets:
        write_sheet(DESIGN / s.filename, s, cache, PROJECT, ROOT_UUID,
                    REV, COMPANY, pwr)
    write_project(DESIGN / f"{PROJECT}.kicad_pro", PROJECT, sheets, ROOT_UUID)
    write_lib_tables(
        DESIGN,
        [(PROJECT, f"${{KIPRJMOD}}/lib/{PROJECT}.kicad_sym",
          "LC29H and B8389 -- symbols no stock library provides")],
        [(PROJECT, f"${{KIPRJMOD}}/lib/{PROJECT}.pretty",
          "LC29H land pattern, SAW land pattern, castellated edge")],
    )

    print(f"wrote {len(sheets) + 1} schematics, project file and lib tables")
    print(f"  {len(comps)} placements, {len(by_ref)} reference designators")
    print(f"  {sum(len(s.labels) for s in sheets)} labels, "
          f"{sum(len(s.powers) for s in sheets)} power ports")
    return 0


def main() -> int:
    return generate(verify_only="--verify" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
