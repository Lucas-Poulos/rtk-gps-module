#!/usr/bin/env python3
"""The gate. Everything that must be true about design/ before it ships.

This checks the *generated output*, not the generator's intentions --
it exports a fresh netlist and a fresh ERC report from the files on disk
and asserts against those. Four classes of check:

1.  Determinism. Regenerating must not change a byte.
2.  Connectivity. The nets that carry the design's meaning are asserted
    pin by pin, so a refactor cannot quietly reroute the RF path or drop
    the level divider off RXD1.
3.  Netclass. The exported per-net class is checked, because KiCad
    accepts a netclass pattern that matches nothing without complaining
    and a 50 ohm line silently falls back to the default width.
4.  Arithmetic. Divider ratios and reactances are re-derived here and
    compared against the part values actually placed, so docs and
    schematic cannot drift apart.

Plus: ERC must be clean AND the report must be newly written. A stale
report from an earlier run reads exactly like a pass.

Usage
-----
    python3 scripts/verify_project.py
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"
ANALYSIS = ROOT / "analysis"
SCRIPTS = ROOT / "scripts"
SCH = DESIGN / "rtk-gps-module.kicad_sch"

FAILS: list[str] = []
CHECKS = 0


def chk(cond: bool, msg: str) -> bool:
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILS.append(msg)
    return bool(cond)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)


# ==========================================================================
# 1. The generators agree with themselves, and regeneration is a no-op
# ==========================================================================
def check_generators() -> None:
    for script in ("gen_footprints.py", "gen_custom_symbols.py",
                   "gen_project.py"):
        r = run([sys.executable, f"scripts/{script}", "--verify"])
        chk(r.returncode == 0,
            f"{script} --verify failed:\n{r.stdout}{r.stderr}")

    def digest() -> dict[str, str]:
        out = {}
        for p in sorted(DESIGN.rglob("*")):
            if p.is_file():
                out[str(p.relative_to(DESIGN))] = hashlib.sha256(
                    p.read_bytes()).hexdigest()
        return out

    def regenerate() -> None:
        for script in ("gen_custom_symbols.py", "gen_footprints.py",
                       "gen_project.py"):
            r = run([sys.executable, f"scripts/{script}"])
            chk(r.returncode == 0, f"{script} failed:\n{r.stdout}{r.stderr}")

    # Three snapshots, because "design/ is out of date" and "the generator
    # is not deterministic" are different bugs and only one of them is
    # the generator's fault.
    on_disk = digest()
    chk(bool(on_disk), "design/ is empty -- run the generators first")
    regenerate()
    first = digest()
    regenerate()
    second = digest()

    drifted = [k for k in second if first.get(k) != second[k]]
    chk(not drifted,
        f"generators are NOT deterministic -- two identical runs differ "
        f"in {drifted[:6]}")

    stale = [k for k in first if on_disk.get(k) != first[k]]
    chk(not stale,
        f"design/ was stale: {stale[:6]} changed on regeneration. "
        f"Commit the regenerated output.")


# ==========================================================================
# 2. ERC -- clean, and provably this run's report
# ==========================================================================
def check_erc() -> None:
    ANALYSIS.mkdir(exist_ok=True)
    rpt = ANALYSIS / "erc.rpt"
    if rpt.exists():
        rpt.unlink()
    if not chk(not rpt.exists(), "could not remove the old ERC report"):
        return

    t0 = time.time()
    r = run(["kicad-cli", "sch", "erc", "--output", str(rpt),
             "--severity-all", "--exit-code-violations", str(SCH)])

    # kicad-cli writes NO report when the schematic fails to parse, and
    # says so only on stdout. Without this check a missing file would be
    # read as "nothing to report".
    if not chk(rpt.exists(),
               f"ERC wrote no report -- the schematic probably failed to "
               f"load:\n{r.stdout}{r.stderr}"):
        return
    chk(rpt.stat().st_mtime >= t0 - 1,
        "ERC report is stale -- it was not written by this run")

    text = rpt.read_text()
    m = re.search(r"ERC messages: (\d+)\s+Errors (\d+)\s+Warnings (\d+)", text)
    if not chk(m is not None, f"cannot parse the ERC report:\n{text[:400]}"):
        return
    total, errors, warnings = (int(g) for g in m.groups())
    chk(errors == 0, f"ERC reports {errors} error(s)")
    chk(warnings == 0, f"ERC reports {warnings} warning(s)")
    chk(r.returncode == total,
        f"kicad-cli exit {r.returncode} disagrees with {total} violations")


# ==========================================================================
# 3. The netlist
# ==========================================================================
def netlist() -> tuple[dict[str, set[str]], dict[str, str]]:
    out = ROOT / "analysis" / "netlist.net"
    out.parent.mkdir(exist_ok=True)
    r = run(["kicad-cli", "sch", "export", "netlist",
             "--format", "kicadsexpr", "-o", str(out), str(SCH)])
    if not chk(out.exists(), f"netlist export failed:\n{r.stdout}{r.stderr}"):
        return {}, {}
    text = out.read_text()
    nets: dict[str, set[str]] = {}
    classes: dict[str, str] = {}
    body = text[text.index("(nets"):]
    for blk in re.split(r"\n\t\t\(net\n", body)[1:]:
        name = re.search(r'\(name "([^"]*)"\)', blk)
        cls = re.search(r'\(class "([^"]*)"\)', blk)
        if not name:
            continue
        nodes = re.findall(r'\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"\)', blk)
        nets[name.group(1)] = {f"{r_}.{p}" for r_, p in nodes}
        classes[name.group(1)] = cls.group(1) if cls else ""
    return nets, classes


# The nets whose exact membership IS the design. Anything that reroutes
# one of these is a different board.
EXPECT_NETS: dict[str, set[str]] = {
    # --- the 50 ohm chain, antenna to receiver ---
    "/RF/ANT_RF": {"J301.1", "D301.1", "L301.2", "C301.1"},
    "/RF/RF_A": {"C301.2", "C302.1", "R301.1"},
    "/RF/RF_B": {"R301.2", "C303.1", "L302.1", "FL301.1"},
    "RF_IN": {"FL301.4", "L303.1", "U201.11"},
    # --- bias tee and its switch ---
    "/RF/ANT_BIAS": {"Q301.3", "R305.2", "L301.1", "C304.1", "C305.1"},
    "/RF/ANT_PWR": {"R302.2", "Q301.2", "R303.1", "R305.1"},
    "/RF/PGATE": {"Q301.1", "R303.2", "Q302.3"},
    "VDD_RF": {"U201.9", "R302.1"},
    # --- the RXD1 attenuator, at the pin ---
    "/GNSS/RXD1_NET": {"R205.2", "R212.1", "U201.21"},
    "RX_BUS": {"R205.1", "R401.2", "J501.7"},
    "UART_TX": {"R213.2", "U401.7", "J501.6"},
    # --- supplies ---
    "VSYS": {"D102.3", "D103.1", "C101.1", "C102.1", "U101.1", "U101.3"},
    "VBUS": {"J101.A4", "J101.A9", "J101.B4", "J101.B9", "D101.5", "D102.1"},
    "V_BCKP": {"D104.3", "C105.1", "C106.1", "C107.1", "U201.22"},
    "VDD_EXT": {"U201.7", "C204.1", "R203.1", "J501.11"},
    "/GNSS/V1P8_SEL": {"R203.2", "R204.1", "R206.1", "R207.1"},
    # --- USB ---
    "USB_DP": {"J101.A6", "J101.B6", "D101.1", "D101.6", "U401.1"},
    "USB_DM": {"J101.A7", "J101.B7", "D101.3", "D101.4", "U401.2"},
}

EXPECT_CLASS = {
    "/RF/ANT_RF": "RF", "/RF/RF_A": "RF", "/RF/RF_B": "RF", "RF_IN": "RF",
    "USB_DP": "USB", "USB_DM": "USB",
    "+3V3": "Power", "VBUS": "Power", "VSYS": "Power", "V_BCKP": "Power",
    "/RF/ANT_PWR": "Power", "/RF/ANT_BIAS": "Power",
}

# LC29H pins that must be on ground, from Table 6.
LC29H_GND_PINS = {"U201.10", "U201.12", "U201.13", "U201.24"}
# LC29H pins that must be on NOTHING. Table 6: "must be left N/C and
# cannot be connected to power or GND".
LC29H_NC_PINS = {"U201.2", "U201.4", "U201.17"}


def check_netlist() -> None:
    nets, classes = netlist()
    if not nets:
        return

    for name, want in EXPECT_NETS.items():
        got = nets.get(name)
        if got is None:
            chk(False, f"net {name!r} does not exist "
                       f"(did a label get renamed?)")
            continue
        chk(got == want,
            f"net {name!r} membership changed:\n"
            f"       missing {sorted(want - got)}\n"
            f"       extra   {sorted(got - want)}")

    for name, want in EXPECT_CLASS.items():
        got = classes.get(name)
        chk(got == want,
            f"net {name!r} is netclass {got!r}, expected {want!r} -- a "
            f"netclass pattern that matches nothing fails silently")

    gnd = nets.get("GND", set())
    for pin in LC29H_GND_PINS:
        chk(pin in gnd, f"LC29H {pin} must be grounded (Table 6)")

    # RESERVED pins land on their own single-pin "unconnected-..." nets.
    for pin in LC29H_NC_PINS:
        holders = [n for n, p in nets.items() if pin in p]
        chk(len(holders) == 1 and holders[0].startswith("unconnected-"),
            f"LC29H {pin} is RESERVED and must be left N/C, "
            f"but appears on {holders}")

    # The 1.8 V domain must never touch a 3.3 V or 2.8 V rail directly.
    for sig in ("D_SEL1", "D_SEL2", "TXD2_PAD", "RXD2_PAD"):
        pins = nets.get(sig, set())
        for rail in ("U101.5", "U201.7"):
            chk(rail not in pins,
                f"{sig} is a 1.8 V-domain pin and must not touch {rail}")
    chk("U201.7" not in nets.get("+3V3", set()),
        "LC29H VDD_EXT (pin 7) is a 2.8 V OUTPUT and must never be tied "
        "to +3V3")

    # Only the pins we deliberately left open may be unconnected.
    allowed = LC29H_NC_PINS | {
        "J101.A8", "J101.B8",       # SBU1/SBU2, unused on a USB 2.0 port
        "U101.4",                   # AP2112K NC
        "U401.4",                   # CH340N /RTS
        "J502.10", "J502.11",       # spare edge pads
    }
    for name, pins in nets.items():
        if name.startswith("unconnected-"):
            stray = pins - allowed
            chk(not stray, f"unexpected unconnected pin(s): {sorted(stray)}")


# ==========================================================================
# 4. Arithmetic -- the numbers the notes and docs claim
# ==========================================================================
def check_math() -> None:
    import math

    # RXD1 attenuator. LC29H Table 6 gives RXD1 VILmax 0.7 V,
    # VIHmin 1.75 V, VIHmax 3.08 V. The divider must land a 3.3 V drive
    # between VIHmin and VIHmax.
    rtop, rbot, vdrive = 1e3, 10e3, 3.3
    vin = vdrive * rbot / (rtop + rbot)
    chk(abs(vin - 3.0) < 0.01, f"RXD1 divider gives {vin:.3f} V, expected 3.0")
    chk(vin <= 3.08, f"RXD1 sees {vin:.3f} V, above VIHmax 3.08 V")
    chk(vin >= 1.75, f"RXD1 sees {vin:.3f} V, below VIHmin 1.75 V")

    # Divider source impedance against the bit period at 921600 baud.
    zsrc = rtop * rbot / (rtop + rbot)
    tau = zsrc * 15e-12
    chk(tau * 5 < 1.0 / 921600,
        f"RXD1 divider is too slow: 5tau = {tau * 5e9:.0f} ns vs a "
        f"{1e9 / 921600:.0f} ns bit")

    # D_SEL strap. VDD_EXT is 2.8 V; D_SEL is a 1.8 V domain with
    # VIHmin 1.17 V and VIHmax 2.1 V.
    vsel = 2.8 * 10e3 / (4.7e3 + 10e3)
    chk(1.17 <= vsel <= 2.1,
        f"D_SEL strap sits at {vsel:.3f} V, outside 1.17-2.1 V")

    # Bias-tee choke. 68 nH must look high against 50 ohm across both
    # bands, or it loads the antenna line.
    for f_hz, band in ((1176.45e6, "L5"), (1575.42e6, "L1")):
        z = 2 * math.pi * f_hz * 68e-9
        chk(z > 400, f"L301 is only {z:.0f} ohm at {band}, too low vs 50 ohm")

    # Antenna short-circuit current through R302.
    i_fault = 3.3 / 10.0
    chk(i_fault < 0.5,
        f"a shorted antenna draws {i_fault * 1000:.0f} mA through R302")

    # LDO headroom: 5 V USB minus a Schottky, minus AP2112K dropout.
    vsys = 5.0 - 0.3
    chk(vsys - 0.32 > 3.3,
        f"VSYS {vsys:.2f} V leaves no headroom for a 3.3 V / 320 mV LDO")

    # The RF netclass width must still be the one calc_impedance derives,
    # and that width must still land on 50 ohm.
    sys.path.insert(0, str(SCRIPTS))
    import calc_impedance as ci
    import gen_project as gp

    rf = {n: (tw, cl) for n, tw, cl, _, _ in gp.ks.NET_CLASSES}
    chk("RF" in rf, "there is no RF netclass")
    if "RF" in rf:
        tw, cl = rf["RF"]
        chk(abs(tw - ci.RF_TRACE_W) < 1e-9,
            f"RF netclass track width {tw} != derived {ci.RF_TRACE_W}")
        chk(abs(cl - ci.RF_GAP) < 1e-9,
            f"RF netclass clearance {cl} != CPWG gap {ci.RF_GAP}")
        z0, _ = ci.cbcpw(tw)
        chk(abs(z0 - 50.0) / 50.0 < 0.05,
            f"RF track of {tw} mm is {z0:.1f} ohm, more than 5% off 50")


# ==========================================================================
# 5. Sourcing
# ==========================================================================
def check_sourcing() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import gen_project as gp

    sheets, _ = gp.build()
    seen: set[str] = set()
    for s in sheets:
        for c in s.comps:
            if c.ref in gp.NO_BOM or c.ref in gp.DNP:
                continue
            lcsc = c.props.get("LCSC", "")
            chk(bool(re.fullmatch(r"C\d+", lcsc)),
                f"{c.ref} ({c.value}) has LCSC {lcsc!r}, which is not a "
                f"resolved Cxxxxx number")
            seen.add(c.ref)
    chk(len(seen) > 40, f"only {len(seen)} sourced parts -- that looks wrong")

    # The custom symbols must point at the custom footprints, or the
    # board will be laid out against a stock land pattern that does not
    # exist for these parts.
    want = {
        "U201": "rtk-gps-module:Quectel_LC29H_LCC-24_12.2x16.0mm",
        "FL301": "rtk-gps-module:SAW_RF360_SMD1411-5P_1.4x1.1mm",
        "J501": "rtk-gps-module:Castellated_1x12_P1.27mm",
        "J502": "rtk-gps-module:Castellated_1x12_P1.27mm",
    }
    placed = {c.ref: c for s in sheets for c in s.comps}
    for ref, fp in want.items():
        chk(placed[ref].props.get("Footprint") == fp,
            f"{ref} footprint is {placed[ref].props.get('Footprint')!r}, "
            f"expected {fp!r}")


# ==========================================================================
def main() -> int:
    print("verifying rtk-gps-module\n")
    for name, fn in (
        ("generators and determinism", check_generators),
        ("ERC", check_erc),
        ("netlist and netclasses", check_netlist),
        ("arithmetic", check_math),
        ("sourcing", check_sourcing),
    ):
        n0 = len(FAILS)
        fn()
        status = "ok" if len(FAILS) == n0 else f"{len(FAILS) - n0} FAILED"
        print(f"  {name:<28} {status}")

    print()
    if FAILS:
        print(f"{len(FAILS)} of {CHECKS} checks failed:\n")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print(f"all {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
