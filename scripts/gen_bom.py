#!/usr/bin/env python3
"""Generate manufacturing/BOM.md and the JLCPCB assembly CSV.

Reads the exported netlist rather than a hand-maintained list, so the BOM
cannot drift from the schematic. Groups by LCSC part number, aggregates
quantities and records which sheets each line appears on.

PRICES ARE A SNAPSHOT. Every figure in PRICES below was read off LCSC on
the date in PRICE_DATE and is recorded so the cost claim in the README is
traceable, not so it stays true. Refresh before ordering:

    python3 ~/.claude/skills/lcsc/scripts/search_lcsc.py <Cxxxxx> --details

Usage
-----
    python3 scripts/gen_bom.py
    python3 scripts/gen_bom.py --stdout
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_SCH = REPO_ROOT / "design" / "rtk-gps-module.kicad_sch"
OUT_MD = REPO_ROOT / "manufacturing" / "BOM.md"
OUT_CSV = REPO_ROOT / "manufacturing" / "bom_jlcpcb.csv"
OUT_DNP = REPO_ROOT / "manufacturing" / "BOM-dnp.md"

PRICE_DATE = "2026-09-28"

# LCSC -> (unit price USD at qty 1-10, LCSC stock, JLCPCB basic?)
PRICES: dict[str, tuple[float, int, bool]] = {
    "C20748061": (23.9364, 22, False),     # LC29HDAMD
    "C5556161": (1.6036, 130, False),      # B39162B8389P810 SAW
    "C2977777": (0.5701, 14211, False),    # CH340N
    "C23380830": (0.1089, 31470, False),   # AP2112K-3.3
    "C2827654": (0.0446, 90097, False),    # USBLC6-2SC6
    "C916424": (0.0072, 1002652, False),   # BAT54C
    "C502527": (0.0305, 858741, False),    # SD05
    "C207186": (0.0794, 8172, False),      # RF1256-000
    "C15127": (0.0716, 715902, True),      # AO3401A
    "C20526": (0.0108, 2033567, True),     # MMBT3904
    "C2765186": (0.0742, 1171811, False),  # USB-C 16P
    "C5137195": (0.0398, 704735, False),   # u.FL
    "C2286": (0.0073, 8154450, True),      # red LED
    "C12624": (0.0122, 366908, False),     # green LED
    "C108965": (0.0638, 59343, False),     # 68nH
    "C408161": (0.0386, 16817, False),     # 5.1nH
    "C17168": (0.00046, 18421967, True),   # 0R
    "C25077": (0.00047, 4398696, True),    # 10R
    "C25092": (0.00056, 4094909, True),    # 22R
    "C11702": (0.00050, 12617545, True),   # 1k
    "C25900": (0.00049, 9379077, True),    # 4.7k
    "C25905": (0.00044, 8446095, True),    # 5.1k
    "C25744": (0.00049, 20674699, True),   # 10k
    "C25741": (0.00050, 15436416, True),   # 100k
    "C1562": (0.0049, 690617, True),       # 33pF
    "C1546": (0.0078, 266701, True),       # 100pF
    "C1525": (0.0060, 16407331, True),     # 100nF
    "C19666": (0.0236, 1373603, True),     # 4.7uF
    "C15850": (0.0773, 3505306, True),     # 10uF
}

# Lines worth calling out: thin stock, or a choice that constrains the build.
NOTES = {
    "C20748061": "THE cost and THE stock risk. LC29HBS (C21385845, RTK base) "
                 "and LC29HAA (C22403415, no RTK engine) share the footprint",
    "C5556161": "dual-band L1+L5. Do NOT substitute an L1-only SAW -- it "
                "deletes the second band RTK depends on",
    "C408161": "5.1nH is the SAW's specified port match, not a rounding of 5nH",
    "C108965": "wirewound, >=68nH per the Quectel reference. A ferrite bead "
               "here would eat the antenna signal",
    "C207186": "0.25pF junction capacitance. The LC29H guide caps this at "
               "0.6pF -- an ordinary ESD diode detunes the antenna",
}

NOISE = re.compile(r"fontconfig|invalid (attribute|constant)", re.I)


def netlist() -> str:
    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as fh:
        tmp = Path(fh.name)
    r = subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
         "-o", str(tmp), str(ROOT_SCH)],
        capture_output=True, text=True)
    if not tmp.exists() or tmp.stat().st_size == 0:
        sys.exit(f"netlist export failed:\n{r.stdout}\n{r.stderr}")
    return tmp.read_text()


def parse(text: str) -> list[dict]:
    """One dict per placed component, from the netlist's (components ...)."""
    body = text[text.index("(components"):text.index("(libparts")]
    comps = []
    for blk in re.split(r"\n\t\t\(comp\n", body)[1:]:
        def f(name: str) -> str:
            # Read the (property (name X) (value Y)) form, not (field ...).
            # The field form leaves the value unquoted on the same line, so
            # an MPN containing a bracket -- "TYPE-C 16PIN 2MD(073)" -- gets
            # silently truncated at the bracket.
            m = re.search(
                r'\(property\s*\n\s*\(name "%s"\)\s*\n\s*\(value "([^"]*)"\)'
                % re.escape(name), blk)
            return (m.group(1).strip() if m else "")

        ref = re.search(r'\(ref "([^"]+)"\)', blk)
        val = re.search(r'\(value "([^"]*)"\)', blk)
        fp = re.search(r'\(footprint "([^"]*)"\)', blk)
        sheet = re.search(r'\(sheetpath\s*\n\s*\(names "([^"]*)"\)', blk)
        if not ref:
            continue
        comps.append({
            "ref": ref.group(1),
            "value": val.group(1) if val else "",
            "fp": fp.group(1) if fp else "",
            "sheet": (sheet.group(1) if sheet else "/").strip("/") or "root",
            "mpn": f("MPN"), "mfr": f("Manufacturer"),
            "lcsc": f("LCSC"), "dnp": f("DNP"),
        })
    return comps


def refsort(ref: str):
    m = re.match(r"([A-Za-z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def build() -> tuple[str, str, str]:
    comps = [c for c in parse(netlist()) if not c["ref"].startswith("#")]

    fitted = [c for c in comps if not c["dnp"] and c["lcsc"]]
    dnp = [c for c in comps if c["dnp"]]
    nobom = [c for c in comps if not c["dnp"] and not c["lcsc"]]

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in fitted:
        groups[c["lcsc"]].append(c)

    rows = []
    total = 0.0
    unpriced = []
    for lcsc, cs in groups.items():
        qty = len(cs)
        price, stock, basic = PRICES.get(lcsc, (None, None, None))
        if price is None:
            unpriced.append(lcsc)
            ext = 0.0
        else:
            ext = price * qty
            total += ext
        rows.append({
            "lcsc": lcsc, "qty": qty,
            "refs": ", ".join(sorted((c["ref"] for c in cs), key=refsort)),
            "value": cs[0]["value"], "mpn": cs[0]["mpn"], "mfr": cs[0]["mfr"],
            "fp": cs[0]["fp"].split(":")[-1],
            "price": price, "stock": stock, "basic": basic, "ext": ext,
            "sheets": ", ".join(sorted({c["sheet"] for c in cs})),
        })
    rows.sort(key=lambda r: -r["ext"])

    n_basic = sum(r["qty"] for r in rows if r["basic"])
    n_ext = sum(r["qty"] for r in rows if r["basic"] is False)
    feeder = sum(1 for r in rows if r["basic"] is False) * 3.0

    md = [
        "# Bill of Materials",
        "",
        f"`rtk-gps-module` rev A. Generated by `scripts/gen_bom.py` from the",
        f"schematic netlist -- do not edit by hand.",
        "",
        f"- **{len(fitted)} fitted parts** in **{len(rows)} lines**",
        f"- **{len(dnp)} not fitted** (see `BOM-dnp.md`)",
        f"- Prices and stock read from LCSC on **{PRICE_DATE}** and frozen "
        f"here for traceability. Re-check before ordering.",
        "",
        f"## Cost",
        "",
        f"| | |",
        f"|---|---|",
        f"| Parts, one board, qty-1 pricing | **${total:.2f}** |",
        f"| of which the LC29H receiver | "
        f"${PRICES['C20748061'][0]:.2f} ({PRICES['C20748061'][0] / total * 100:.0f} %) |",
        f"| of which the dual-band SAW | ${PRICES['C5556161'][0]:.2f} |",
        f"| everything else | "
        f"${total - PRICES['C20748061'][0] - PRICES['C5556161'][0]:.2f} |",
        f"| JLCPCB basic parts / extended | {n_basic} / {n_ext} |",
        f"| JLCPCB extended-part feeder fees | ${feeder:.2f} one-off |",
        "",
        "The receiver is 90 % of the bill. Nothing else on the board is worth",
        "optimising until that changes.",
        "",
        "## Fitted",
        "",
        "| Qty | Refs | Value | MPN | LCSC | Pkg | Unit $ | Ext $ | Stock |",
        "|----:|---|---|---|---|---|----:|----:|----:|",
    ]
    for r in rows:
        pr = f"{r['price']:.4f}" if r["price"] is not None else "?"
        ex = f"{r['ext']:.3f}" if r["price"] is not None else "?"
        st = f"{r['stock']:,}" if r["stock"] is not None else "?"
        md.append(
            f"| {r['qty']} | {r['refs']} | {r['value']} | {r['mpn']} | "
            f"[{r['lcsc']}](https://www.lcsc.com/search?q={r['lcsc']}) | "
            f"{r['fp']} | {pr} | {ex} | {st} |")

    md += ["", "## Notes", ""]
    for lcsc, note in NOTES.items():
        hit = next((r for r in rows if r["lcsc"] == lcsc), None)
        if hit:
            md.append(f"- **{hit['mpn']}** (`{lcsc}`, {hit['refs']}) -- {note}")

    if nobom:
        md += ["", "## Not purchased", "",
               "Board features that carry a footprint but nothing to order.",
               ""]
        for c in sorted(nobom, key=lambda c: refsort(c["ref"])):
            md.append(f"- `{c['ref']}` {c['value']} -- "
                      f"{c['fp'].split(':')[-1]}")

    if unpriced:
        md += ["", f"> Unpriced lines: {', '.join(unpriced)}"]

    # --- DNP sheet --------------------------------------------------------
    dmd = [
        "# Not-fitted parts",
        "",
        "Footprints deliberately left unpopulated. Each is a documented",
        "option, not an omission -- fitting one changes a behaviour the",
        "default build does not want.",
        "",
        "| Ref | Value | Pkg | Why it exists |",
        "|---|---|---|---|",
    ]
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import gen_project as gp
    for c in sorted(dnp, key=lambda c: refsort(c["ref"])):
        dmd.append(f"| `{c['ref']}` | {c['value']} | "
                   f"{c['fp'].split(':')[-1]} | "
                   f"{gp.DNP.get(c['ref'], '')} |")

    # --- JLCPCB assembly CSV ---------------------------------------------
    csv = ["Comment,Designator,Footprint,LCSC Part #"]
    for r in rows:
        csv.append(f'"{r["value"]}","{r["refs"]}","{r["fp"]}","{r["lcsc"]}"')

    return "\n".join(md) + "\n", "\n".join(dmd) + "\n", "\n".join(csv) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    md, dmd, csv = build()
    if args.stdout:
        print(md)
        return 0
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md)
    OUT_DNP.write_text(dmd)
    OUT_CSV.write_text(csv)
    for p in (OUT_MD, OUT_DNP, OUT_CSV):
        print(f"  wrote {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
