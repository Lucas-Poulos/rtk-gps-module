#!/usr/bin/env python3
"""Fetch the vendor datasheets this design was transcribed from.

They are not committed -- they belong to Quectel and Qualcomm. Everything
the design actually depends on is transcribed into the generators with a
citation, so the repo is self-contained without them; you need these only
to check that transcription yourself.

Usage
-----
    python3 tools/fetch_datasheets.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "datasheets"

DOCS = {
    "LC29H_Hardware_Design_V1.3.pdf":
        "https://forums.quectel.com/uploads/short-url/"
        "u7fE3GaEAynRmZ3J7ihhjXrwxTF.pdf",
    "SAW_B39162B8389P810.pdf":
        "https://datasheet.lcsc.com/datasheet/pdf/"
        "eab07ffddc7092a73be1e657f827b881.pdf?productCode=C5556161",
}

UA = {"User-Agent": "Mozilla/5.0"}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    bad = 0
    for name, url in DOCS.items():
        dest = OUT / name
        if dest.exists():
            print(f"  have    {name}")
            continue
        try:
            req = urllib.request.Request(url, headers=UA)
            data = urllib.request.urlopen(req, timeout=60).read()
        except Exception as exc:
            print(f"  FAILED  {name}: {exc}")
            bad += 1
            continue
        if not data.startswith(b"%PDF"):
            print(f"  FAILED  {name}: not a PDF (got {data[:16]!r})")
            bad += 1
            continue
        dest.write_bytes(data)
        print(f"  fetched {name}  ({len(data) / 1e6:.1f} MB)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
