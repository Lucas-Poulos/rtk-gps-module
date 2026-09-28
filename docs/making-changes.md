# Making changes

`design/` is generated. Editing a `.kicad_sch` in the GUI works right up
until the next `make regen`, which silently overwrites it. So every change
below is a change to `scripts/`.

**The loop is always the same:**

```bash
make            # list targets
$EDITOR scripts/gen_project.py
make all        # regenerate + BOM + PDF + gate
git diff        # read what actually changed
git commit      # the pre-commit hook re-runs the gate
```

If you have not installed the hook yet: `make hooks`, once.

---

## Recipe: change a component value

Say the power LED is too bright and you want 2.2 kΩ instead of 1 kΩ.

**1. Change the placement.** `scripts/gen_project.py`, in `sheet_power()`:

```python
R("R103", "1k", 340, 225, 90),      # before
R("R103", "2.2k", 340, 225, 90),    # after
```

**2. Make sure the new value is sourced.** `PASSIVES`
(`gen_project.py:189`) is keyed by `(value, footprint)` and only holds
values the board actually uses. A value that is not in it has no LCSC
number, and the gate stops you:

```
R103 (2.2k) has no LCSC number -- add it to SOURCING or PASSIVES
```

That is the system working. Resolve the real part before adding it:

```bash
python3 ~/.claude/skills/lcsc/scripts/search_lcsc.py "0402 2.2k" --details
```

then add the line:

```python
("2.2k", R0402): ("0402WGF2201TCE", "UNI-ROYAL", "C25879"),
```

**Never invent a `Cxxxxx`.** It is the one rule that cannot be checked
automatically, because a made-up number looks exactly like a real one.

---

## Recipe: add a part

**1. Place it** in the right `sheet_*()` function. Keep ≥ 14 mm from its
neighbours — `MIN_PART_GAP` (`gen_project.py:60`) enforces it, because
closer than that the stub labels print on top of each other.

```python
C("C108", "1uF", 300, 225, 90),
```

**2. Wire it** in the matching `wire_*()` in `scripts/wire_sheets.py`:

```python
net(w, VSYS, ("C108", "1"))
rail(w, GND, ("C108", "2"))
```

**3. Source it** — `PASSIVES` if it is a passive, `SOURCING`
(`gen_project.py:159`) if it needs its own line.

**4. Run `make all`.** The gate will tell you if you missed a step.

### Pin names vs pin numbers

`("C108", "1")` resolves **by name first, then by number**. For most parts
either works. Use **numbers** when a symbol repeats a pin name — the
USBLC6 has two pins called `I/O1`, and addressing by name silently wires
only the first. The traps are listed in the `wire_sheets.py` docstring.

---

## Recipe: change a net

All connectivity is in `scripts/wire_sheets.py`, one function per sheet.
Nets are made **by name** — two labels spelled the same are one net.

Rail and signal names are module-level constants at the top of the file on
purpose: a typo'd string is a brand-new net that looks completely normal
on screen. Use the constant, not a literal.

```python
net(w, RX_BUS, ("R205", "1"))       # good
net(w, "RX_BUS", ("R205", "1"))     # works, but nothing catches a typo
```

**If you change a net that matters, update the gate too.** `EXPECT_NETS`
(`verify_project.py:165`) pins down exact membership for the RF chain, the
RXD1 divider and the supplies. It will fail loudly and tell you the
difference:

```
net '/RF/ANT_RF' membership changed:
       missing ['L301.2']
       extra   ['L301.1']
```

That failure is the point — decide whether you meant it, then update
`EXPECT_NETS` to match.

---

## Recipe: add a not-fitted (DNP) option

Add the part normally, then add it to `DNP` (`gen_project.py:220`) with a
reason:

```python
"C108": "extra VSYS bulk if the carrier's 5 V is noisy",
```

That reason is not decoration — it is printed into
`manufacturing/BOM-dnp.md`, and the gate fails if `DNP` names a part that
is not placed anywhere. DNP parts are exempt from the LCSC requirement,
since there is nothing to buy.

---

## Recipe: change the impedance target or the stackup

Do **not** edit the netclass width by hand. It is imported:

```python
from calc_impedance import RF_GAP, RF_TRACE_W       # gen_project.py
("RF", RF_TRACE_W, RF_GAP, 0.2, 0.20),              # ks.NET_CLASSES
```

Edit `scripts/calc_impedance.py` instead — `H_PREPREG`, `ER`, `GAP`,
`TARGET_Z0` — then:

```bash
make impedance     # prints the solve and a tolerance sweep
```

Set `RF_TRACE_W` (`calc_impedance.py:62`) to the width it derives, rounded
to something a fab can hold. The gate re-solves and fails if the netclass
and the model disagree, or if the width drifts more than 5 % off 50 Ω.

**If you move to a 2-layer board the model changes**, not just the number:
the prepreg height becomes the full core, and `cbcpw()` will want a much
wider trace. At that point read `docs/impedance.md` rather than just
turning the crank.

---

## Recipe: change the castellated pinout

`J501_MAP` and `J502_MAP` at the bottom of `scripts/wire_sheets.py`. They
are plain lists of `(pin, signal)`; `None` means leave the pad unconnected.

```python
("Pin_10", None),          # spare
("Pin_10", VDD_EXT),       # now carries 2.8 V
```

Update the pinout tables in `README.md` in the same commit — nothing
checks those automatically, which makes them the easiest thing in the repo
to leave wrong.

---

## Recipe: swap the receiver variant

The LC29H family shares one 24-pin footprint across parts that do **not**
share a pinout. `LC29HBS` is the RTK *base station*; `LC29HAA` has no RTK
engine at all.

Changing variant means:

1. `SOURCING["U201"]` — new MPN and LCSC number.
2. `scripts/gen_custom_symbols.py` — re-check every pin against that
   variant's Table 6. The `expect` dict in its `verify()` is a second,
   independent transcription; both must change, which is deliberate.
3. `scripts/gen_bom.py` — `PRICES` entry.
4. `README.md` and `CLAUDE.md` — the claims about bands and accuracy.

Read the "contested pinout" section in `CLAUDE.md` first.

---

## When the gate fails

`make verify` runs 146 checks in five groups. What each failure means:

| Message | What happened |
|---|---|
| `design/ was stale: [...]` | You edited `scripts/` and did not regenerate. Run `make regen`, commit the output too. |
| `generators are NOT deterministic` | Two identical runs differ. A real bug — usually a `set` or `dict` iterated in nondeterministic order, or a timestamp leaking in. |
| `ERC wrote no report` | The schematic failed to parse. `kicad-cli` says so only on stdout and writes nothing, so this check exists to stop a missing file reading as a pass. |
| `ERC reports N error(s)` | Run `make erc` to see them with locations. |
| `net 'X' membership changed` | You rewired something the gate pins down. Intended? Update `EXPECT_NETS`. |
| `net 'X' is netclass 'Default', expected 'RF'` | A netclass pattern stopped matching. They are **wildcards, not regex**, and local nets carry a sheet path — see `CLAUDE.md`. |
| `has no LCSC number` | Source the part, or mark it DNP. |
| `RXD1 divider gives ...` | You changed `R205`/`R212` and broke the 3.08 V limit. |
| `RF netclass track width != derived` | Edit `calc_impedance.py`, not the netclass. |
| `A and B are N mm apart` | Placement too tight; labels would collide. |

To see a failure without touching anything, break something on purpose and
revert — that is how the ERC path was validated in the first place.

---

## Working in the KiCad GUI

```bash
make open        # schematic editor, read-only in spirit
```

Browsing, zooming, inspecting nets and running ERC from the GUI are all
fine. **Do not save.** If you do:

```bash
git status       # see what KiCad touched
make regen       # rebuild over it
make verify      # confirm 146/146
```

Nothing is lost — that is the whole reason `design/` is generated and
committed.

Two specific GUI hazards, both seen on this project already:

- Opening the **PCB editor** creates an auto-populated board and will
  happily save `design/rtk-gps-module.kicad_pcb` — an unplaced pile that
  no generator produced and nothing can reproduce. PCB layout should come
  from a `gen_pcb.py` when it starts.
- KiCad 10 writes `design/.history/` beside the design. Gitignored.

`make regen` refuses to run while lock files exist in `design/`, so you
cannot regenerate underneath an open GUI by accident.

---

## Things nothing checks

Worth knowing where the automation stops:

- **The pinout tables in `README.md`** — hand-maintained against
  `J501_MAP`/`J502_MAP`.
- **Prices in `gen_bom.py`** — a snapshot from 2026-09-28, deliberately
  frozen for traceability. Refresh before ordering, not on a schedule.
- **Whether the design actually works.** No board has been fabricated.
  ERC proves the netlist is self-consistent; it says nothing about whether
  the circuit is correct.
