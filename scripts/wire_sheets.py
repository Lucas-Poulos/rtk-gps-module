#!/usr/bin/env python3
"""Nets for rtk-gps-module.

Nets are made by NAME: every pin gets a short stub and a label, and two
labels spelled the same are one net. KiCad's netlister treats that as
identical to drawn polylines.

Rail and signal names are module-level constants precisely because a
misspelled rail silently becomes a second net that looks completely normal
on screen. verify_project.py asserts the expected pin count on the nets
that matter.

Four pinout facts this file depends on, none of them guessable:

* KiCad draws diodes and LEDs with **pin 1 = cathode (K), pin 2 = anode
  (A)**. The two indicator LEDs are wired from that, not from "pin 1 is
  the anode" intuition.
* **BAT54C is a common-cathode pair**: pins 1 and 2 are the anodes and
  pin 3 is the shared cathode. Both ORing diodes on this board are one
  BAT54C each, anodes to the two sources and cathode to the rail.
* **USBLC6-2SC6 duplicates its I/O pins**: 1 and 6 are both I/O1, 3 and 4
  are both I/O2. They are one node inside the part but two pins to the
  netlister, so each pair must be wired explicitly or the data lines go
  open circuit at the connector.
* **USB-C duplicates VBUS and GND** across A4/A9/B4/B9 and
  A1/A12/B1/B12. All eight are wired; leaving the B-side open works
  right way up and fails upside down.

Stacked pins (LC29H GND and RSVD, SAW GND) share one name and one
coordinate, so wiring the name once wires every pin behind it.
"""
from __future__ import annotations

from kicad_sch import Label, PowerPort, Sheet, SymbolCache, Wirer, snap

# -- rails -----------------------------------------------------------------
GND = "GND"
V3V3 = "+3V3"

# Rails that travel as global labels rather than power-port symbols.
VBUS = "VBUS"            # raw USB 5 V
VEXT_5V = "VEXT_5V"      # 5 V offered by the carrier board
VSYS = "VSYS"            # the OR of those two, feeds the LDO
V_BCKP = "V_BCKP"        # backup domain, keeps the RTC and ephemeris alive
VBCKP_EXT = "VBCKP_EXT"  # optional external cell / supercap
VDD_RF = "VDD_RF"        # LC29H pin 9, the antenna bias source
VDD_EXT = "VDD_EXT"      # LC29H pin 7, 2.8 V / 100 mA out
V1P8_SEL = "V1P8_SEL"    # 1.9 V strap node for D_SEL1/D_SEL2

# -- signals ---------------------------------------------------------------
USB_DP = "USB_DP"
USB_DM = "USB_DM"
UART_TX = "UART_TX"      # receiver -> host (NMEA / PQTM out)
RX_BUS = "RX_BUS"        # host -> receiver (RTCM3 in), before the divider
RXD1_NET = "RXD1_NET"    # after the divider, at the module pin
PPS = "PPS"
RESET_N = "RESET_N"
WAKEUP = "WAKEUP"
ANT_ON = "ANT_ON"
RF_IN = "RF_IN"
ANT_RF = "ANT_RF"
ANT_PWR = "ANT_PWR"
ANT_BIAS = "ANT_BIAS"
D_SEL1 = "D_SEL1"
D_SEL2 = "D_SEL2"
SDA_PAD = "SDA_PAD"
SCL_PAD = "SCL_PAD"
TXD2_PAD = "TXD2_PAD"
RXD2_PAD = "RXD2_PAD"

GLOBALS = {
    VBUS, VEXT_5V, VSYS, V_BCKP, VBCKP_EXT, VDD_RF, VDD_EXT,
    USB_DP, USB_DM, UART_TX, RX_BUS, PPS, RESET_N, WAKEUP, ANT_ON, RF_IN,
    D_SEL1, D_SEL2, SDA_PAD, SCL_PAD, TXD2_PAD, RXD2_PAD,
}


def net(w: Wirer, name: str, *pins) -> None:
    """One net. Global if the name is a declared cross-sheet signal."""
    w.net(name, *pins, kind="global" if name in GLOBALS else "local")


def rail(w: Wirer, sym: str, *pins) -> None:
    for spec in pins:
        ref, ident, *rest = spec
        w.power(ref, ident, sym, rest[0] if rest else None)


def flag_port(w: Wirer, sym: str, x: float, y: float) -> None:
    """A power-port symbol and a PWR_FLAG sharing one point.

    Both symbols carry their single pin at the symbol origin, so placing
    them at the same coordinate connects them. Without this the rail has
    no pin KiCad recognises as a source and ERC calls every power input
    on the board undriven.
    """
    x, y = snap(x), snap(y)
    w.sheet.powers.append(PowerPort(sym, x, y, 0))
    w.sheet.powers.append(PowerPort("PWR_FLAG", x, y, 180))


def flag_label(w: Wirer, name: str, x: float, y: float) -> None:
    """A global label and a PWR_FLAG sharing one point."""
    x, y = snap(x), snap(y)
    w.sheet.powers.append(PowerPort("PWR_FLAG", x, y, 0))
    w.sheet.labels.append(Label(name, x, y, 0, "global"))


# ==========================================================================
# Sheet 01 -- input, ORing, 3V3, backup
# ==========================================================================
def wire_power(w: Wirer) -> None:
    # USB-C. Both sides of every duplicated pin, so the cable works either
    # way up.
    net(w, VBUS, ("J101", "A4"), ("J101", "A9"),
        ("J101", "B4"), ("J101", "B9"), ("D101", "5"), ("D102", "1"))
    rail(w, GND, ("J101", "A1"), ("J101", "A12"),
         ("J101", "B1"), ("J101", "B12"), ("J101", "SH"), ("D101", "2"))

    # One 5.1k per CC line. A single shared resistor advertises the wrong
    # source current and some hosts then refuse to enumerate.
    net(w, "CC1", ("J101", "A5"), ("R101", "1"))
    net(w, "CC2", ("J101", "B5"), ("R102", "1"))
    rail(w, GND, ("R101", "2"), ("R102", "2"))

    # Data pair through the ESD array. Pins 1/6 and 3/4 are each one node
    # inside the part but two pins to the netlister.
    net(w, USB_DP, ("J101", "A6"), ("J101", "B6"),
        ("D101", "1"), ("D101", "6"))
    net(w, USB_DM, ("J101", "A7"), ("J101", "B7"),
        ("D101", "3"), ("D101", "4"))
    w.no_connect("J101", "A8")
    w.no_connect("J101", "B8")

    # 5 V ORing, then the LDO.
    net(w, VEXT_5V, ("D102", "2"))
    net(w, VSYS, ("D102", "3"), ("D103", "A1"), ("C101", "1"),
        ("C102", "1"), ("U101", "VIN"), ("U101", "EN"))
    rail(w, GND, ("D103", "A2"), ("C101", "2"), ("C102", "2"),
         ("U101", "GND"))
    w.no_connect("U101", "NC")
    rail(w, V3V3, ("U101", "VOUT"), ("C103", "1"), ("C104", "1"),
         ("D104", "1"))
    rail(w, GND, ("C103", "2"), ("C104", "2"))

    # Backup domain: 3V3 ORed with an optional external cell.
    net(w, VBCKP_EXT, ("D104", "2"))
    net(w, V_BCKP, ("D104", "3"), ("C105", "1"), ("C106", "1"),
        ("C107", "1"))
    rail(w, GND, ("C105", "2"), ("C106", "2"), ("C107", "2"))

    # Power LED.
    rail(w, V3V3, ("D105", "A"))
    net(w, "LED_PWR_K", ("D105", "K"), ("R103", "1"))
    rail(w, GND, ("R103", "2"))

    # VBUS, VSYS and V_BCKP all arrive through passive parts, and GND
    # through a connector shell, so none of them has a pin KiCad counts as
    # a driver. 3V3 does -- the LDO's VOUT is a power_out.
    flag_port(w, GND, 60, 265)
    flag_label(w, VBUS, 100, 265)
    flag_label(w, VSYS, 140, 265)
    flag_label(w, V_BCKP, 180, 265)


# ==========================================================================
# Sheet 02 -- the receiver
# ==========================================================================
def wire_gnss(w: Wirer) -> None:
    # Supplies. GND is stacked across pins 10/12/13/24, so naming it once
    # wires all four.
    rail(w, V3V3, ("U201", "VCC"), ("C201", "1"), ("C202", "1"),
         ("C203", "1"))
    rail(w, GND, ("U201", "GND"), ("C201", "2"), ("C202", "2"),
         ("C203", "2"))
    net(w, V_BCKP, ("U201", "V_BCKP"))

    # VDD_EXT is a 2.8 V OUTPUT. It is decoupled, offered on the edge, and
    # divided down for the strap node -- never driven.
    net(w, VDD_EXT, ("U201", "VDD_EXT"), ("C204", "1"), ("R203", "1"))
    rail(w, GND, ("C204", "2"))
    net(w, V1P8_SEL, ("R203", "2"), ("R204", "1"),
        ("R206", "1"), ("R207", "1"))
    rail(w, GND, ("R204", "2"))

    # Interface select. Default 0,0 = UART1 via the internal 75k
    # pulldowns, so the fitted board needs no parts here at all.
    net(w, D_SEL1, ("U201", "D_SEL1"), ("R206", "2"))
    net(w, D_SEL2, ("U201", "D_SEL2"), ("R207", "2"))

    # Reset and wake.
    net(w, RESET_N, ("U201", "RESET_N"), ("R201", "2"), ("C205", "1"))
    rail(w, V3V3, ("R201", "1"))
    rail(w, GND, ("C205", "2"))
    net(w, WAKEUP, ("U201", "WAKEUP"), ("R202", "1"))
    rail(w, GND, ("R202", "2"))

    net(w, PPS, ("U201", "1PPS"))
    net(w, VDD_RF, ("U201", "VDD_RF"))
    net(w, ANT_ON, ("U201", "ANT_ON"))
    net(w, RF_IN, ("U201", "RF_IN"))

    # UART1. TXD1 leaves through 22R of series damping; RXD1 arrives
    # through the 1k/10k divider that holds it under its 3.08 V VIHmax.
    net(w, "TXD1_RAW", ("U201", "TXD1"), ("R213", "1"))
    net(w, UART_TX, ("R213", "2"))
    net(w, RX_BUS, ("R205", "1"))
    net(w, RXD1_NET, ("R205", "2"), ("R212", "1"), ("U201", "RXD1"))
    rail(w, GND, ("R212", "2"))

    # Pins whose existence on the (DA) variant the hardware design guide
    # contradicts itself about. Each reaches the edge only through a DNP
    # link, so the default build leaves them N/C either way.
    net(w, "SDA_INT", ("U201", "I2C_SDA"), ("R208", "1"))
    net(w, SDA_PAD, ("R208", "2"))
    net(w, "SCL_INT", ("U201", "I2C_SCL"), ("R209", "1"))
    net(w, SCL_PAD, ("R209", "2"))
    net(w, "TXD2_INT", ("U201", "TXD2"), ("R210", "1"))
    net(w, TXD2_PAD, ("R210", "2"))
    net(w, "RXD2_INT", ("U201", "RXD2"), ("R211", "1"))
    net(w, RXD2_PAD, ("R211", "2"))

    # Pins 2, 4 and 17. Table 6: "must be left N/C and cannot be connected
    # to power or GND".
    w.no_connect("U201", "RSVD")


# ==========================================================================
# Sheet 03 -- RF front end
# ==========================================================================
def wire_rf(w: Wirer) -> None:
    # Antenna node: connector, ESD clamp, bias injection, DC block.
    net(w, ANT_RF, ("J301", "In"), ("D301", "A1"), ("L301", "2"),
        ("C301", "1"))
    rail(w, GND, ("J301", "Ext"), ("D301", "A2"))

    # Pi network. R301 fitted at 0R, both shunts unfitted -- a place to
    # retune for a particular antenna at no cost if it is not needed.
    net(w, "RF_A", ("C301", "2"), ("C302", "1"), ("R301", "1"))
    rail(w, GND, ("C302", "2"))
    net(w, "RF_B", ("R301", "2"), ("C303", "1"), ("L302", "1"),
        ("FL301", "IN"))
    rail(w, GND, ("C303", "2"), ("L302", "2"))

    # The SAW's ports are 50 ohm // 5.1 nH, so L302 and L303 are part of
    # the impedance, not optional extras.
    net(w, RF_IN, ("FL301", "OUT"), ("L303", "1"))
    rail(w, GND, ("FL301", "GND"), ("L303", "2"))

    # Bias tee supply. R302 caps the current if the antenna is shorted.
    net(w, VDD_RF, ("R302", "1"))
    net(w, ANT_PWR, ("R302", "2"), ("Q301", "S"), ("R303", "1"),
        ("R305", "1"))
    net(w, "PGATE", ("Q301", "G"), ("R303", "2"), ("Q302", "C"))
    net(w, ANT_ON, ("R304", "1"))
    net(w, "ANT_ON_B", ("R304", "2"), ("Q302", "B"))
    rail(w, GND, ("Q302", "E"))

    net(w, ANT_BIAS, ("Q301", "D"), ("R305", "2"), ("L301", "1"),
        ("C304", "1"), ("C305", "1"))
    rail(w, GND, ("C304", "2"), ("C305", "2"))


# ==========================================================================
# Sheet 04 -- USB-UART bridge
# ==========================================================================
def wire_usb(w: Wirer) -> None:
    net(w, USB_DP, ("U401", "UD+"))
    net(w, USB_DM, ("U401", "UD-"))
    rail(w, GND, ("U401", "GND"), ("C401", "2"), ("C402", "2"))

    # At 3.3 V the internal regulator is bypassed: V3 ties to VCC.
    rail(w, V3V3, ("U401", "VCC"), ("U401", "V3"),
         ("C401", "1"), ("C402", "1"))

    net(w, UART_TX, ("U401", "RXD"))
    net(w, "CH_TXD", ("U401", "TXD"), ("R401", "1"))
    net(w, RX_BUS, ("R401", "2"))
    w.no_connect("U401", "~{RTS}")


# ==========================================================================
# Sheet 05 -- castellated edge and indicators
# ==========================================================================
#
# Left edge, J501 -- power and the signals a host actually needs.
# Right edge, J502 -- antenna control, and the 1.8 V domain behind DNP
# links. Pads 5-8 on the right edge are NOT 3.3 V tolerant.

J501_MAP = [
    ("Pin_1", GND), ("Pin_2", VEXT_5V), ("Pin_3", V3V3),
    ("Pin_4", VBCKP_EXT), ("Pin_5", GND), ("Pin_6", UART_TX),
    ("Pin_7", RX_BUS), ("Pin_8", PPS), ("Pin_9", RESET_N),
    ("Pin_10", WAKEUP), ("Pin_11", VDD_EXT), ("Pin_12", GND),
]

J502_MAP = [
    ("Pin_1", GND), ("Pin_2", ANT_ON), ("Pin_3", SDA_PAD),
    ("Pin_4", SCL_PAD), ("Pin_5", TXD2_PAD), ("Pin_6", RXD2_PAD),
    ("Pin_7", D_SEL1), ("Pin_8", D_SEL2), ("Pin_9", GND),
    ("Pin_10", None), ("Pin_11", None), ("Pin_12", GND),
]


def wire_io(w: Wirer) -> None:
    for ref, mapping in (("J501", J501_MAP), ("J502", J502_MAP)):
        for pin, sig in mapping:
            if sig is None:
                w.no_connect(ref, pin)
            elif sig in (GND, V3V3):
                rail(w, sig, (ref, pin))
            else:
                net(w, sig, (ref, pin))

    # 1PPS indicator. 1PPS is guaranteed only 2.1 V high, so it drives a
    # transistor rather than the LED directly.
    net(w, PPS, ("R501", "1"))
    net(w, "PPS_B", ("R501", "2"), ("Q501", "B"))
    rail(w, GND, ("Q501", "E"))
    net(w, "PPS_LED_K", ("Q501", "C"), ("D501", "K"))
    net(w, "PPS_LED_A", ("D501", "A"), ("R502", "2"))
    rail(w, V3V3, ("R502", "1"))


# ==========================================================================

WIRERS = {
    "01_power.kicad_sch": wire_power,
    "02_gnss.kicad_sch": wire_gnss,
    "03_rf.kicad_sch": wire_rf,
    "04_usb.kicad_sch": wire_usb,
    "05_io.kicad_sch": wire_io,
}


def wire_all(sheets: list[Sheet], cache: SymbolCache) -> None:
    for s in sheets:
        fn = WIRERS.get(s.filename)
        if fn is None:
            raise KeyError(f"no wiring function for {s.filename}")
        fn(Wirer(s, cache))
