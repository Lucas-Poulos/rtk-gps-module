# Bootstrap generators — not authoritative

**Do not run these.** They produced the first version of `design/`, and
that is all they are for now. `design/` is the source of truth: it is
hand-edited in KiCad, and re-running `gen_project.py` would overwrite
your work with the design as it stood on 2026-09-28.

They are kept because two of them contain work that is hard to redo and
worth reading:

| File | What is worth keeping |
|---|---|
| `gen_custom_symbols.py` | The LC29H pinout, transcribed pin by pin from the hardware design guide's Table 6, with the electrical type of each pin justified in comments. Its `verify()` holds a **second, independent transcription** of the same table — they were written to disagree loudly if either was typed wrong. Also the reasoning that settles the (DA) variant's contradictory pinout. |
| `gen_footprints.py` | The LC29H land pattern derived from Figure 19, including why the 24 pads are in two uneven groups, and the B8389 land pattern from its Figure 2. |
| `gen_project.py` | The parts catalogue: every LCSC number resolved against the live catalogue on 2026-09-28, with the JLCPCB basic/extended split. |
| `wire_sheets.py` | The connectivity, plus a docstring listing the pin traps — duplicated `I/O1` pins on the USBLC6, BAT54C's common cathode on pin 3, KiCad's cathode-is-pin-1 convention. |
| `verify_project.py` | The old 146-check gate. Superseded by `tools/check.py`, which checks the same design without regenerating it. |

If you need any of that, read it. The live equivalents are:

- `tools/check.py` — the checks, read-only
- `tools/gen_bom.py` — the BOM, read from the schematic
- `tools/calc_impedance.py` — the 50 Ω derivation, still used and still
  checked against the project's RF netclass

## If you ever do want to run one

You would be replacing `design/` wholesale. Take a branch first:

```bash
git switch -c regenerate
python3 tools/bootstrap/gen_project.py
git diff --stat design/       # this will be enormous
```

Expect a large diff even with no design change, because KiCad has since
rewritten every file in its own canonical format.
