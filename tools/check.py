#!/usr/bin/env python3
"""Read-only checks on design/.

This does NOT regenerate anything. design/ is the source of truth now --
you edit it in KiCad and save, and this tells you whether what you saved
still holds together.

Four things worth checking automatically, because all four fail silently:

1.  ERC must be clean, and the report must be from this run. kicad-cli
    writes NO report when the schematic fails to parse and says so only
    on stdout, so a stale report from an earlier run reads exactly like
    a pass.
2.  Every fitted part needs a resolved LCSC number, or it quietly drops
    out of the BOM at order time.
3.  The RF nets must be on the RF netclass. KiCad accepts a netclass
    pattern that matches nothing without complaining, and the 50 ohm
    antenna line silently falls back to the default track width.
4.  A handful of nets whose exact wiring is load-bearing.

Number 4 is the one that can get in your way. If you deliberately rewire
something it lists, the fix is to edit CRITICAL_NETS below -- the check
exists to make sure a rewire is a decision, not an accident.

Usage
-----
    python3 tools/check.py          (or: make check)
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"
ANALYSIS = ROOT / "analysis"
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
# 1. ERC
# ==========================================================================
def check_erc() -> None:
    ANALYSIS.mkdir(exist_ok=True)
    rpt = ANALYSIS / "erc.rpt"
    if rpt.exists():
        rpt.unlink()

    t0 = time.time()
    r = run(["kicad-cli", "sch", "erc", "--output", str(rpt),
             "--severity-all", "--exit-code-violations", str(SCH)])

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
    _, errors, warnings = (int(g) for g in m.groups())
    chk(errors == 0, f"ERC reports {errors} error(s) -- run 'make erc'")
    chk(warnings == 0, f"ERC reports {warnings} warning(s) -- run 'make erc'")


# ==========================================================================
# 2-4. Netlist
# ==========================================================================
def netlist() -> tuple[dict, dict, list]:
    out = ANALYSIS / "netlist.net"
    ANALYSIS.mkdir(exist_ok=True)
    r = run(["kicad-cli", "sch", "export", "netlist",
             "--format", "kicadsexpr", "-o", str(out), str(SCH)])
    if not chk(out.exists(), f"netlist export failed:\n{r.stdout}{r.stderr}"):
        return {}, {}, []
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
        nets[name.group(1)] = {f"{a}.{b}" for a, b in nodes}
        classes[name.group(1)] = cls.group(1) if cls else ""

    comps = []
    cbody = text[text.index("(components"):text.index("(libparts")]
    for blk in re.split(r"\n\t\t\(comp\n", cbody)[1:]:
        def f(name: str) -> str:
            m = re.search(
                r'\(property\s*\n\s*\(name "%s"\)\s*\n\s*\(value "([^"]*)"\)'
                % re.escape(name), blk)
            return m.group(1).strip() if m else ""
        ref = re.search(r'\(ref "([^"]+)"\)', blk)
        val = re.search(r'\(value "([^"]*)"\)', blk)
        if not ref:
            continue
        comps.append({"ref": ref.group(1),
                      "value": val.group(1) if val else "",
                      "lcsc": f("LCSC"), "dnp": f("DNP")})
    return nets, classes, comps


# Nets whose exact wiring is load-bearing. Rewire one on purpose and
# update it here; the check is here so it cannot happen by accident.
CRITICAL_NETS: dict[str, set[str]] = {
    # the 50 ohm chain, antenna to receiver
    "/RF/ANT_RF": {"J301.1", "D301.1", "L301.2", "C301.1"},
    "RF_IN": {"FL301.4", "L303.1", "U201.11"},
    # the RXD1 attenuator -- without it a 3.3V host exceeds VIHmax 3.08V
    "/GNSS/RXD1_NET": {"R205.2", "R212.1", "U201.21"},
    # the antenna bias switch
    "/RF/ANT_BIAS": {"Q301.3", "R305.2", "L301.1", "C304.1", "C305.1"},
}

EXPECT_CLASS = {
    "/RF/ANT_RF": "RF", "/RF/RF_A": "RF", "/RF/RF_B": "RF", "RF_IN": "RF",
    "USB_DP": "USB", "USB_DM": "USB",
    "+3V3": "Power", "VBUS": "Power", "VSYS": "Power", "V_BCKP": "Power",
}

# Board features, not purchased parts -- the castellated edges ARE the PCB.
NO_BOM = {"J501", "J502"}


def check_netlist() -> None:
    nets, classes, comps = netlist()
    if not nets:
        return

    for name, want in CRITICAL_NETS.items():
        got = nets.get(name)
        if got is None:
            chk(False, f"net {name!r} no longer exists. If you renamed it "
                       f"on purpose, update CRITICAL_NETS in tools/check.py")
            continue
        chk(got == want,
            f"net {name!r} was rewired:\n"
            f"       missing {sorted(want - got)}\n"
            f"       extra   {sorted(got - want)}\n"
            f"       If that was deliberate, update CRITICAL_NETS in "
            f"tools/check.py")

    for name, want in EXPECT_CLASS.items():
        got = classes.get(name)
        chk(got == want,
            f"net {name!r} is netclass {got!r}, expected {want!r}. KiCad "
            f"netclass patterns are WILDCARDS, not regex, and local nets "
            f"carry their sheet path -- see docs/editing.md")

    # LC29H grounds and the RESERVED pins that must float (Table 6).
    gnd = nets.get("GND", set())
    for pin in ("U201.10", "U201.12", "U201.13", "U201.24"):
        chk(pin in gnd, f"LC29H {pin} must be grounded (datasheet Table 6)")
    for pin in ("U201.2", "U201.4", "U201.17"):
        holders = [n for n, p in nets.items() if pin in p]
        chk(len(holders) == 1 and holders[0].startswith("unconnected-"),
            f"LC29H {pin} is RESERVED and must be left N/C, "
            f"but is on {holders}")
    chk("U201.7" not in nets.get("+3V3", set()),
        "LC29H VDD_EXT (pin 7) is a 2.8 V OUTPUT and must not be tied "
        "to +3V3")

    # Sourcing.
    unsourced = [c for c in comps
                 if not c["dnp"] and c["ref"] not in NO_BOM
                 and not re.fullmatch(r"C\d+", c["lcsc"])]
    for c in unsourced:
        chk(False, f"{c['ref']} ({c['value']}) has no resolved LCSC number. "
                   f"Set its LCSC field in KiCad, or mark it DNP.")
    chk(len(comps) > 40, f"only {len(comps)} components found -- "
                         f"did the netlist export properly?")


# ==========================================================================
def check_impedance() -> None:
    """The RF netclass must still be the width the model derives."""
    sys.path.insert(0, str(ROOT / "tools"))
    import json
    import calc_impedance as ci

    pro = json.loads((DESIGN / "rtk-gps-module.kicad_pro").read_text())
    rf = next((c for c in pro["net_settings"]["classes"]
               if c["name"] == "RF"), None)
    if not chk(rf is not None, "there is no RF netclass in the project file"):
        return
    chk(abs(rf["track_width"] - ci.RF_TRACE_W) < 1e-9,
        f"RF track width is {rf['track_width']} mm but calc_impedance "
        f"derives {ci.RF_TRACE_W} mm. Change one to match the other -- "
        f"see docs/impedance.md")
    z0, _ = ci.cbcpw(rf["track_width"])
    chk(abs(z0 - 50.0) / 50.0 < 0.05,
        f"an RF track of {rf['track_width']} mm is {z0:.1f} ohm, "
        f"more than 5% off 50")


def main() -> int:
    print("checking design/ (read-only -- nothing is regenerated)\n")
    for name, fn in (("ERC", check_erc),
                     ("netlist, netclasses, sourcing", check_netlist),
                     ("RF impedance", check_impedance)):
        n0 = len(FAILS)
        fn()
        print(f"  {name:<32} {'ok' if len(FAILS) == n0 else 'FAILED'}")

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
