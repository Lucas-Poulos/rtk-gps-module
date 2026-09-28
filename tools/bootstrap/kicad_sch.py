#!/usr/bin/env python3
"""Emit KiCad 10 hierarchical schematics, project files and library tables.

Used by ``gen_project.py``. Kept separate so the board definition stays
readable data rather than string formatting.

Things this module knows that are easy to get wrong
---------------------------------------------------
* ``lib_symbols`` entries carry the **qualified** name (``Device:C``), while
  the unit sub-symbols nested inside them keep the **bare** name (``C_1_1``).
  Get this wrong and KiCad silently drops every component: the file opens,
  the title block renders, and the netlist comes out empty.
* Symbol library coordinates have **Y up**; schematic coordinates have
  **Y down**. Placing a symbol negates the pin Y offsets.
* A multi-unit symbol is several ``(symbol ...)`` blocks sharing one
  reference designator, each with its own ``(unit N)`` and its own
  ``instances`` path. Units may live on different sheets.
* Instance paths are ``/<root-uuid>`` for a symbol on the root sheet and
  ``/<root-uuid>/<sheet-symbol-uuid>`` for one inside a sub-sheet.
* ``(project "NAME")`` inside ``instances`` must match the ``.kicad_pro``
  file stem, or the instance is ignored.
* A pin's ``(at x y angle)`` is its **connection point**; ``(length L)``
  runs from there *towards* the body along ``angle``. So the outward
  direction a wire stub should leave on is ``angle + 180``.
* Nets are joined by **name**, not by geometry. Every pin gets a short
  stub and a label; two labels spelled the same are one net. This is the
  only tractable way to wire a 448-ball BGA.

UUIDs are derived with uuid5 from stable seed strings, so regenerating the
project produces byte-identical files and git diffs stay meaningful.
"""

from __future__ import annotations

import json
import re
import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path

STOCK_SYMBOLS = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
)
NS = _uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

SCH_HEADER = (
    "(kicad_sch\n"
    "\t(version 20260306)\n"
    '\t(generator "gen_project.py")\n'
    '\t(generator_version "10.0")\n'
)


def uid(seed: str) -> str:
    return str(_uuid.uuid5(NS, seed))


def fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def esc(s: str) -> str:
    """Escape a string for a quoted s-expression atom.

    The newline case is load-bearing. KiCad stores a multi-line text object
    as a **single-line quoted string containing ``\\n`` escapes**; a literal
    newline inside the quotes makes the file parse-fail outright, and
    ``kicad-cli`` reports nothing more useful than "Failed to load
    schematic" -- no file, no line, no object. Every sheet fails at once,
    which makes it look like a library-wide problem rather than one note.
    """
    return (s.replace("\\", "\\\\")
             .replace('"', '\\"')
             .replace("\n", "\\n"))


# ==========================================================================
# Component and sheet records
# ==========================================================================


# KiCad's schematic pin grid. Symbol pins sit at multiples of 2.54 mm from
# the symbol origin, so snapping origins to this grid puts every pin
# endpoint on grid -- which is what lets wires snap to pins when the
# schematic is wired by hand. Placing on a decimal-millimetre grid instead
# produces an `endpoint_off_grid` ERC violation per component and makes
# every pin slightly unclickable.
GRID_MM = 2.54


def snap(v: float) -> float:
    return round(v / GRID_MM) * GRID_MM


@dataclass
class Comp:
    """One placed component instance. Position snaps to the pin grid."""

    ref: str
    lib_id: str
    value: str
    x: float
    y: float
    rot: int = 0
    unit: int = 1
    props: dict[str, str] = field(default_factory=dict)
    mirror: str | None = None

    def __post_init__(self) -> None:
        self.x = snap(self.x)
        self.y = snap(self.y)


@dataclass
class Note:
    text: str
    x: float
    y: float
    size: float = 1.27
    bold: bool = False


@dataclass
class Wire:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Junction:
    x: float
    y: float


@dataclass
class NoConnect:
    x: float
    y: float


@dataclass
class Label:
    """A net name attached at a point.

    ``kind`` selects the scope KiCad gives it:

    ``local``       this sheet only
    ``global``      the whole hierarchy, no sheet pin needed
    ``hierarchical`` this sheet, exported through a matching sheet pin

    Power rails use ``global`` so a rail crosses sheets without threading a
    pin through the root sheet for every one of them.
    """

    text: str
    x: float
    y: float
    rot: int = 0
    kind: str = "local"
    shape: str = "passive"


@dataclass
class PowerPort:
    """A power/ground port symbol -- ``power:GND``, ``power:+3V3``, ...

    Reference designators are assigned ``#PWR0NNN`` at emit time. KiCad
    treats the leading ``#`` as "not a real part", which keeps these out of
    the BOM and off the board.
    """

    sym: str
    x: float
    y: float
    rot: int = 0


@dataclass
class Sheet:
    filename: str
    name: str
    page: str
    paper: str = "A2"
    title: str = ""
    comps: list[Comp] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    junctions: list[Junction] = field(default_factory=list)
    no_connects: list[NoConnect] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    powers: list[PowerPort] = field(default_factory=list)

    @property
    def uuid(self) -> str:
        """UUID of the sheet *symbol* on the root sheet."""
        return uid(f"sheet-symbol/{self.filename}")

    @property
    def own_uuid(self) -> str:
        """UUID of the sheet file itself."""
        return uid(f"sheet-file/{self.filename}")


# ==========================================================================
# Symbol definition harvesting
# ==========================================================================


@dataclass(frozen=True)
class PinGeom:
    """One pin as the symbol library draws it. Symbol space, Y up."""

    number: str
    name: str
    etype: str
    x: float
    y: float
    angle: float
    length: float


def _xform(dx: float, dy: float, rot: int, mirror: str | None
           ) -> tuple[float, float]:
    """Map a symbol-space offset onto schematic space.

    Symbol libraries are Y-up, schematics are Y-down, so the Y offset is
    negated first. ``rot`` is counter-clockwise on screen, matching the R
    key in eeschema.

    **Rotation is applied before mirroring**, which is the order KiCad
    uses, and the order is not a detail: a reflection conjugates a rotation
    into its inverse, so doing it the other way round is equivalent to
    negating the angle. That agrees for 0 deg and 180 deg and is wrong for
    90 deg and 270 deg -- a component mirrored and turned a quarter-turn
    gets its pins swapped, on a schematic that looks entirely normal.
    ``verify_wiring_geometry.py`` exists because of this bug and caught it.
    """
    sx, sy = dx, -dy
    r = rot % 360
    if r == 90:
        sx, sy = sy, -sx
    elif r == 180:
        sx, sy = -sx, -sy
    elif r == 270:
        sx, sy = -sy, sx
    if mirror == "x":
        sy = -sy
    elif mirror == "y":
        sx = -sx
    return sx, sy


# Direction a stub leaves a pin on, as a screen-space unit vector.
def _outward(g: PinGeom, rot: int, mirror: str | None) -> tuple[float, float]:
    import math

    a = math.radians(g.angle + 180.0)
    vx, vy = _xform(math.cos(a), math.sin(a), rot, mirror)
    # snap to the axis -- symbol pins are always orthogonal
    if abs(vx) > abs(vy):
        return (1.0 if vx > 0 else -1.0), 0.0
    return 0.0, (1.0 if vy > 0 else -1.0)


class SymbolCache:
    """Pulls (symbol ...) definitions out of source libraries on demand."""

    def __init__(self, project_libs: dict[str, Path]):
        self.project_libs = project_libs
        self._libs: dict[str, str] = {}
        self._defs: dict[str, str] = {}
        self._extents: dict[tuple[str, int], float] = {}
        self._pins: dict[tuple[str, int], dict[str, PinGeom]] = {}
        self.missing: list[str] = []

    def _lib_text(self, lib: str) -> str | None:
        if lib in self._libs:
            return self._libs[lib]
        path = self.project_libs.get(lib) or (STOCK_SYMBOLS / f"{lib}.kicad_sym")
        if not path.exists():
            return None
        self._libs[lib] = path.read_text()
        return self._libs[lib]

    def body_half_height(self, lib_id: str, unit: int) -> float:
        """Half-height of a unit's body rectangle, in mm.

        Used to place the reference and value labels clear of the body.
        Symbols drawn without a rectangle (KiCad's capacitor, for instance)
        report 0 and fall back to a default offset.
        """
        import re

        key = (lib_id, unit)
        if key in self._extents:
            return self._extents[key]
        text = self.definition(lib_id) or ""
        _, _, name = lib_id.partition(":")
        half = 0.0
        m = re.search(r'\(symbol "%s_%d_1"' % (re.escape(name), unit), text)
        if m:
            nxt = text.find('(symbol "%s_' % name, m.end())
            block = text[m.start() : nxt if nxt > 0 else len(text)]
            for r in re.finditer(
                r"\(rectangle\s*\(start ([-\d.]+) ([-\d.]+)\)\s*"
                r"\(end ([-\d.]+) ([-\d.]+)\)", block):
                half = max(half, abs(float(r.group(2))), abs(float(r.group(4))))
        self._extents[key] = half
        return half

    def pins(self, lib_id: str, unit: int) -> dict[str, "PinGeom"]:
        """Every pin of one unit, keyed by pin number.

        Coordinates are symbol-space (Y up) and are the pin's *connection*
        point, which is what a wire must touch. Units draw their pins in
        sub-symbols named ``<bare>_<unit>_<style>``; the style digit varies
        (1 for the common body, 0 for de Morgan) so both are collected.

        **Unit 0 is collected as well as the unit asked for.** KiCad uses
        unit 0 for graphics and pins common to every unit, and a symbol may
        put *all* of its pins there -- ``Switch:SW_Push`` does. Matching
        only ``_<unit>_`` silently returns no pins for those symbols, and a
        pin that cannot be found is a net that never gets drawn.
        """
        import re

        key = (lib_id, unit)
        if key in self._pins:
            return self._pins[key]
        text = self.definition(lib_id) or ""
        _, _, name = lib_id.partition(":")
        found: dict[str, PinGeom] = {}
        for m in re.finditer(
            r'\(symbol "%s_(?:0|%d)_\d+"' % (re.escape(name), unit), text
        ):
            end = _sexp_end(text, m.start())
            for pm in re.finditer(
                r"\(pin\s+(\S+)\s+\S+\s*"
                r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)\s*"
                r"\(length ([-\d.]+)\)"
                r'(?:.*?\(name "((?:[^"\\]|\\.)*)")?'
                r'(?:.*?\(number "((?:[^"\\]|\\.)*)")?',
                text[m.start():end], re.S,
            ):
                etype, px, py, ang, ln, pname, pnum = pm.groups()
                if pnum is None:
                    continue
                found[pnum] = PinGeom(
                    number=pnum, name=pname or "~", etype=etype,
                    x=float(px), y=float(py),
                    angle=float(ang or 0), length=float(ln),
                )
        self._pins[key] = found
        return found

    def pin_by_name(self, lib_id: str, unit: int, name: str) -> list[str]:
        """Pin numbers carrying a given pin name, in file order.

        Stacked supply pins share one name and one coordinate, so this
        returns many numbers for ``VSS``. Wiring any one of them wires all
        of them -- they are the same point.
        """
        return [g.number for g in self.pins(lib_id, unit).values()
                if g.name == name]

    def definition(self, lib_id: str) -> str | None:
        """Return the qualified (symbol "Lib:Name" ...) text for a lib_id."""
        if lib_id in self._defs:
            return self._defs[lib_id]
        lib, _, name = lib_id.partition(":")
        text = self._lib_text(lib)
        if text is None:
            self.missing.append(f"{lib_id} (library {lib!r} not found)")
            return None

        start = text.find(f'(symbol "{name}"')
        if start < 0:
            self.missing.append(f"{lib_id} (symbol not in {lib}.kicad_sym)")
            return None
        nxt = text.find('\n\t(symbol "', start + 10)
        chunk = text[start : nxt if nxt > 0 else text.rfind(")")].rstrip()

        # A derived symbol (extends) needs its parent's graphics inlined.
        ext = _extends_of(chunk)
        if ext:
            parent = self.definition(f"{lib}:{ext}")
            if parent:
                chunk = _merge_extends(chunk, parent, name, ext)

        chunk = chunk.replace(
            f'(symbol "{name}"', f'(symbol "{esc(lib_id)}"', 1
        )
        self._defs[lib_id] = chunk
        return chunk


def _extends_of(chunk: str) -> str | None:
    import re

    m = re.search(r'\(extends "([^"]*)"\)', chunk)
    return m.group(1) if m else None


def _sexp_end(text: str, open_idx: int) -> int:
    """Index just past the ')' that closes the '(' at open_idx."""
    depth = 0
    in_str = False
    i = open_idx
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced s-expression")


def _sym_children(block: str) -> tuple[str, list[str]]:
    """Split ``(symbol "X" ...)`` into its header and top-level children."""
    depth = 0
    in_str = False
    esc_ = False
    kids: list[str] = []
    start: int | None = None
    header_end: int | None = None
    for i, ch in enumerate(block):
        if esc_:
            esc_ = False
            continue
        if ch == "\\":
            esc_ = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "(":
            depth += 1
            if depth == 2:
                start = i
                if header_end is None:
                    header_end = i
        elif ch == ")":
            if depth == 2 and start is not None:
                kids.append(block[start:i + 1])
                start = None
            depth -= 1
            if depth == 0:
                break
    return block[:header_end if header_end is not None else len(block)], kids


def _prop_name(expr: str) -> str | None:
    m = re.match(r'\(property\s+"((?:[^"\\]|\\.)*)"', expr.lstrip())
    return m.group(1) if m else None


def _merge_extends(child: str, parent: str, child_name: str,
                   parent_name: str) -> str:
    """Flatten a derived symbol the way KiCad's ``LIB_SYMBOL::Flatten`` does.

    KiCad resolves ``extends`` against the library at load time, but an
    embedded ``lib_symbols`` definition has no library to resolve against,
    so the parent has to be inlined.

    **The parent is the base, not the child.** Flatten copies the whole
    parent and then overlays the child's properties -- so everything the
    child does not restate is inherited: ``pin_names``, ``in_bom``,
    ``on_board``, ``exclude_from_sim``, ``in_pos_files``,
    ``duplicate_pin_numbers_are_jumpers``, and parent-only properties such
    as ``ki_locked``.

    Building it the other way round -- starting from the child and
    appending the parent's unit graphics -- produces a symbol that
    netlists perfectly and draws perfectly, and that ERC then reports as
    ``lib_symbol_mismatch`` on every single instance, because the cached
    copy is missing attributes the library symbol has. That is 21 warnings
    on this board and it is why this function is written backwards from
    the obvious direction.

    The units must also be nested *inside* the symbol. An earlier version
    appended them after the closing paren: the file still balanced, so a
    paren check passed, but KiCad rejected the whole sheet and the
    hierarchy silently lost every component on it.
    """
    p_head, p_kids = _sym_children(parent)
    _, c_kids = _sym_children(child)
    if not p_kids:
        return child

    c_props: dict[str, str] = {}
    c_order: list[str] = []
    for k in c_kids:
        n = _prop_name(k)
        if n is not None:
            c_props[n] = k
            c_order.append(n)

    out: list[str] = []
    used: set[str] = set()
    unit_re = re.compile(r'\(symbol\s+"%s_\d+_\d+"' % re.escape(parent_name))
    for k in p_kids:
        if k.lstrip().startswith("(extends"):
            continue
        n = _prop_name(k)
        if n is not None and n in c_props:
            out.append(c_props[n])
            used.add(n)
            continue
        if unit_re.match(k.lstrip()):
            k = k.replace(f'(symbol "{parent_name}_',
                          f'(symbol "{child_name}_', 1)
        out.append(k)

    # Properties the child adds that the parent never had.
    extra = [c_props[n] for n in c_order if n not in used]
    if extra:
        last = max((i for i, k in enumerate(out) if _prop_name(k)),
                   default=len(out) - 1)
        out[last + 1:last + 1] = extra

    head = re.sub(r'\(symbol\s+"(?:[^"\\]|\\.)*"',
                  f'(symbol "{child_name}"', p_head.rstrip(), count=1)
    body = "".join(f"\n\t\t{k}" for k in out)
    return f"{head}{body}\n\t)"


def _effects(indent: str, size: float = 1.27, hide: bool = False,
             justify: str | None = None, bold: bool = False) -> str:
    i2 = indent + "\t"
    out = [f"{indent}(effects\n{i2}(font\n{i2}\t(size {fmt(size)} {fmt(size)})\n"]
    if bold:
        out.append(f"{i2}\t(bold yes)\n")
    out.append(f"{i2})\n")
    if justify:
        out.append(f"{i2}(justify {justify})\n")
    if hide:
        out.append(f"{i2}(hide yes)\n")
    out.append(f"{indent})\n")
    return "".join(out)


PROP_ORDER = ["Reference", "Value", "Footprint", "Datasheet", "Description"]


def emit_comp(c: Comp, project: str, path: str,
              body_half_height: float = 0.0) -> str:
    hidden = {"Footprint", "Datasheet", "Description"}
    keys = PROP_ORDER + [k for k in c.props if k not in PROP_ORDER]

    # Reference above the body, value below. A fixed +/-2.54 mm offset puts
    # both labels *inside* the body of anything larger than a passive -- on
    # the PMIC and the MPU units they landed on top of the pin names.
    label_off = max(2.54, body_half_height + 2.54)

    out = [
        "\t(symbol\n",
        f'\t\t(lib_id "{esc(c.lib_id)}")\n',
        f"\t\t(at {fmt(c.x)} {fmt(c.y)} {c.rot})\n",
    ]
    if c.mirror:
        out.append(f"\t\t(mirror {c.mirror})\n")
    out += [
        f"\t\t(unit {c.unit})\n",
        "\t\t(exclude_from_sim no)\n",
        "\t\t(in_bom yes)\n",
        "\t\t(on_board yes)\n",
        "\t\t(dnp no)\n",
        f'\t\t(uuid "{uid(f"comp/{path}/{c.ref}/{c.unit}")}")\n',
    ]

    # Reference above, value below; other fields hidden at the origin.
    for i, key in enumerate(keys):
        if key == "Reference":
            val, px, py, hide = c.ref, c.x, c.y - label_off, False
        elif key == "Value":
            val, px, py, hide = c.value, c.x, c.y + label_off, False
        else:
            val = c.props.get(key, "")
            px, py, hide = c.x, c.y, True
        out.append(f'\t\t(property "{key}" "{esc(val)}"\n')
        out.append(f"\t\t\t(at {fmt(px)} {fmt(py)} 0)\n")
        out.append(_effects("\t\t\t", hide=hide or key in hidden))
        out.append("\t\t)\n")

    out += [
        "\t\t(instances\n",
        f'\t\t\t(project "{esc(project)}"\n',
        f'\t\t\t\t(path "{path}"\n',
        f'\t\t\t\t\t(reference "{esc(c.ref)}")\n',
        f"\t\t\t\t\t(unit {c.unit})\n",
        "\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n",
    ]
    return "".join(out)


def emit_wire(w: Wire, seed: str) -> str:
    return (
        "\t(wire\n"
        f"\t\t(pts\n\t\t\t(xy {fmt(w.x1)} {fmt(w.y1)}) "
        f"(xy {fmt(w.x2)} {fmt(w.y2)})\n\t\t)\n"
        "\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n"
        f'\t\t(uuid "{uid(seed)}")\n'
        "\t)\n"
    )


def emit_junction(j: Junction, seed: str) -> str:
    return (
        "\t(junction\n"
        f"\t\t(at {fmt(j.x)} {fmt(j.y)})\n"
        "\t\t(diameter 0)\n"
        "\t\t(color 0 0 0 0)\n"
        f'\t\t(uuid "{uid(seed)}")\n'
        "\t)\n"
    )


def emit_no_connect(n: NoConnect, seed: str) -> str:
    return (
        "\t(no_connect\n"
        f"\t\t(at {fmt(n.x)} {fmt(n.y)})\n"
        f'\t\t(uuid "{uid(seed)}")\n'
        "\t)\n"
    )


_LABEL_KW = {
    "local": "label",
    "global": "global_label",
    "hierarchical": "hierarchical_label",
}


def emit_label(lb: Label, seed: str) -> str:
    kw = _LABEL_KW[lb.kind]
    # Text reads away from the pin, so left-pointing labels are right
    # justified. Without this the text runs back over the component.
    justify = "left" if lb.rot in (0, 90) else "right"
    out = [f'\t({kw} "{esc(lb.text)}"\n']
    if lb.kind != "local":
        out.append(f"\t\t(shape {lb.shape})\n")
    out.append(f"\t\t(at {fmt(lb.x)} {fmt(lb.y)} {lb.rot})\n")
    out.append(_effects("\t\t", justify=justify))
    out.append(f'\t\t(uuid "{uid(seed)}")\n\t)\n')
    return "".join(out)


def emit_power(pp: PowerPort, project: str, path: str, idx: int) -> str:
    # KiCad's own convention: PWR_FLAG annotates as #FLG, rails as #PWR.
    prefix = "#FLG" if pp.sym == "PWR_FLAG" else "#PWR"
    ref = f"{prefix}{idx:04d}"
    lib_id = f"power:{pp.sym}"
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{esc(lib_id)}")\n'
        f"\t\t(at {fmt(pp.x)} {fmt(pp.y)} {pp.rot})\n"
        "\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n"
        "\t\t(in_bom yes)\n"
        "\t\t(on_board yes)\n"
        "\t\t(dnp no)\n"
        f'\t\t(uuid "{uid(f"pwr/{path}/{prefix}/{idx}")}")\n'
        f'\t\t(property "Reference" "{ref}"\n'
        f"\t\t\t(at {fmt(pp.x)} {fmt(pp.y)} 0)\n"
        + _effects("\t\t\t", hide=True)
        + "\t\t)\n"
        f'\t\t(property "Value" "{esc(pp.sym)}"\n'
        f"\t\t\t(at {fmt(pp.x)} {fmt(pp.y + 3.81)} 0)\n"
        + _effects("\t\t\t")
        + "\t\t)\n"
        '\t\t(property "Footprint" ""\n'
        f"\t\t\t(at {fmt(pp.x)} {fmt(pp.y)} 0)\n"
        + _effects("\t\t\t", hide=True)
        + "\t\t)\n"
        "\t\t(instances\n"
        f'\t\t\t(project "{esc(project)}"\n'
        f'\t\t\t\t(path "{path}"\n'
        f'\t\t\t\t\t(reference "{ref}")\n'
        "\t\t\t\t\t(unit 1)\n"
        "\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n"
    )


def emit_note(n: Note, seed: str) -> str:
    return (
        f'\t(text "{esc(n.text)}"\n'
        "\t\t(exclude_from_sim yes)\n"
        f"\t\t(at {fmt(n.x)} {fmt(n.y)} 0)\n"
        + _effects("\t\t", size=n.size, justify="left bottom", bold=n.bold)
        + f'\t\t(uuid "{uid(seed)}")\n'
        "\t)\n"
    )


def emit_title_block(title: str, rev: str, company: str,
                     comments: list[str]) -> str:
    out = ["\t(title_block\n", f'\t\t(title "{esc(title)}")\n',
           f'\t\t(rev "{esc(rev)}")\n', f'\t\t(company "{esc(company)}")\n']
    for i, c in enumerate(comments, start=1):
        out.append(f'\t\t(comment {i} "{esc(c)}")\n')
    out.append("\t)\n")
    return "".join(out)


def write_sheet(path: Path, sheet: Sheet, cache: SymbolCache, project: str,
                root_uuid: str, rev: str, company: str,
                pwr_counters: dict[str, int] | None = None) -> None:
    """``pwr_counters`` must be ONE dict shared by every sheet in the
    project. Power-symbol references have to be unique project-wide, not
    per sheet -- numbering each sheet from 1 gives six #PWR0001s, which
    KiCad reports as an annotation error and which breaks "Update PCB from
    Schematic", since that keys on the reference designator."""
    if pwr_counters is None:
        pwr_counters = {}
    inst_path = f"/{root_uuid}/{sheet.uuid}"

    lib_ids = sorted({c.lib_id for c in sheet.comps}
                     | {f"power:{p.sym}" for p in sheet.powers})
    defs = [d for d in (cache.definition(i) for i in lib_ids) if d]

    out = [SCH_HEADER, f'\t(uuid "{sheet.own_uuid}")\n',
           f'\t(paper "{sheet.paper}")\n']
    out.append(emit_title_block(
        sheet.title or sheet.name, rev, company,
        [f"Sheet {sheet.page}: {sheet.name}",
         "Wired" if sheet.wires else
         "Nets not yet drawn - components placed with sourcing data"],
    ))

    out.append("\t(lib_symbols\n")
    for d in defs:
        out.append("\n".join("\t" + ln for ln in d.split("\n")) + "\n")
    out.append("\t)\n")

    for i, n in enumerate(sheet.notes):
        out.append(emit_note(n, f"note/{sheet.filename}/{i}"))
    for c in sheet.comps:
        out.append(emit_comp(c, project, inst_path,
                             cache.body_half_height(c.lib_id, c.unit)))
    for pp in sheet.powers:
        key = "#FLG" if pp.sym == "PWR_FLAG" else "#PWR"
        pwr_counters[key] = pwr_counters.get(key, 0) + 1
        out.append(emit_power(pp, project, inst_path, pwr_counters[key]))
    for i, w in enumerate(sheet.wires):
        out.append(emit_wire(w, f"wire/{sheet.filename}/{i}"))
    for i, j in enumerate(sheet.junctions):
        out.append(emit_junction(j, f"junction/{sheet.filename}/{i}"))
    for i, nc in enumerate(sheet.no_connects):
        out.append(emit_no_connect(nc, f"nc/{sheet.filename}/{i}"))
    for i, lb in enumerate(sheet.labels):
        out.append(emit_label(lb, f"label/{sheet.filename}/{i}"))

    out.append(f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "{sheet.page}")'
               "\n\t\t)\n\t)\n)\n")
    path.write_text("".join(out))


def emit_sheet_symbol(s: Sheet, project: str, root_uuid: str,
                      x: float, y: float, w: float, h: float) -> str:
    return (
        "\t(sheet\n"
        f"\t\t(at {fmt(x)} {fmt(y)})\n"
        f"\t\t(size {fmt(w)} {fmt(h)})\n"
        "\t\t(fields_autoplaced yes)\n"
        "\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n"
        "\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n"
        f'\t\t(uuid "{s.uuid}")\n'
        f'\t\t(property "Sheetname" "{esc(s.name)}"\n'
        f"\t\t\t(at {fmt(x)} {fmt(y - 1.5)} 0)\n"
        + _effects("\t\t\t", justify="left bottom")
        + "\t\t)\n"
        f'\t\t(property "Sheetfile" "{esc(s.filename)}"\n'
        f"\t\t\t(at {fmt(x)} {fmt(y + h + 1.5)} 0)\n"
        + _effects("\t\t\t", justify="left top")
        + "\t\t)\n"
        "\t\t(instances\n"
        f'\t\t\t(project "{esc(project)}"\n'
        f'\t\t\t\t(path "/{root_uuid}"\n'
        f'\t\t\t\t\t(page "{s.page}")\n'
        "\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n"
    )


def write_root(path: Path, sheets: list[Sheet], project: str, root_uuid: str,
               title: str, rev: str, company: str, comments: list[str],
               notes: list[Note], cols: int = 3,
               origin: tuple[float, float] = (30, 40),
               cell: tuple[float, float] = (75, 55),
               box: tuple[float, float] = (60, 35)) -> None:
    out = [SCH_HEADER, f'\t(uuid "{root_uuid}")\n', '\t(paper "A2")\n']
    out.append(emit_title_block(title, rev, company, comments))
    out.append("\t(lib_symbols)\n")
    for i, n in enumerate(notes):
        out.append(emit_note(n, f"note/root/{i}"))
    for i, s in enumerate(sheets):
        x = origin[0] + (i % cols) * cell[0]
        y = origin[1] + (i // cols) * cell[1]
        out.append(emit_sheet_symbol(s, project, root_uuid, x, y, *box))
    out.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n)\n')
    path.write_text("".join(out))


# ==========================================================================
# Project file and library tables
# ==========================================================================

NET_CLASSES = [
    # name, track_width, clearance, diff_pair_width, diff_pair_gap
    ("Default", 0.25, 0.15, 0.2, 0.25),
    ("Power", 0.5, 0.2, 0.2, 0.25),
    ("DDR3", 0.1, 0.1, 0.1, 0.1),
    ("DDR3_DIFF", 0.1, 0.1, 0.1, 0.13),
    ("USB_HS", 0.2, 0.2, 0.2, 0.13),
    ("Ethernet", 0.2, 0.2, 0.2, 0.15),
]

# Nets are put into classes by name rather than by hand, so a net added
# later lands in the right class without anyone remembering to assign it.
# The rules in design/*.kicad_dru are written against these class names, so
# a net that matches nothing falls to Default and is routed to Default's
# far looser limits -- which is exactly how a DDR trace ends up 0.25 mm
# wide and out of impedance.
#
# Patterns are evaluated in order; the first match wins.
NETCLASS_PATTERNS = [
    # Differential pairs must be matched before the broader bus patterns,
    # or DDR_CK would be swallowed by the DDR3 rule below.
    ("DDR3_DIFF", "/^DDR_(CK|DQS)/"),
    ("DDR3", "/^DDR_/"),
    ("USB_HS", "/^(OTG|USB[0-9]*)_D[PM]$/"),
    ("Ethernet", "/^(RMII|ETH)_/"),
    ("Ethernet", "/^TD[PN]$|^RD[PN]$/"),
    # Power rails. GND is deliberately absent: it is poured as plane copper,
    # not routed, so a track width for it is meaningless.
    ("Power", "VDDCORE"),
    ("Power", "VDD_DDR"),
    ("Power", "VDD"),
    ("Power", "V3V3"),
    ("Power", "V3V3_AUX"),
    ("Power", "V1V8"),
    ("Power", "V1V2"),
    ("Power", "VDDA"),
    ("Power", "VDD_USB"),
    ("Power", "VTT_DDR"),
    ("Power", "BST_5V"),
    ("Power", "VBUS_IN"),
    ("Power", "VIN_5V"),
    ("Power", "VBUS_OTG"),
    ("Power", "VBUS_SW"),
    # VREF_DDR carries no current and is high impedance. It stays on
    # Default so it is not widened into a low-impedance rail by accident;
    # its real constraint is the isolation rule in the .kicad_dru.
]


def write_project(path: Path, project: str, sheets: list[Sheet],
                  root_uuid: str) -> None:
    classes = []
    for name, tw, cl, dw, dg in NET_CLASSES:
        classes.append({
            "bus_width": 12,
            "clearance": cl,
            "diff_pair_gap": dg,
            "diff_pair_via_gap": 0.25,
            "diff_pair_width": dw,
            "line_style": 0,
            "microvia_diameter": 0.3,
            "microvia_drill": 0.1,
            "name": name,
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": tw,
            "via_diameter": 0.6,
            "via_drill": 0.3,
            "wire_width": 6,
        })

    doc = {
        "board": {
            "design_settings": {
                "defaults": {},
                "diff_pair_dimensions": [],
                "drc_exclusions": [],
                "rules": {},
                "track_widths": [],
                "via_dimensions": [],
            }
        },
        "boards": [],
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{project}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": classes,
            "meta": {"version": 4},
            "netclass_patterns": [
                {"netclass": nc, "pattern": pat}
                for nc, pat in NETCLASS_PATTERNS
            ],
        },
        "pcbnew": {"page_layout_descr_file": ""},
        "schematic": {
            "annotate_start_num": 0,
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            "net_format_name": "",
            "page_layout_descr_file": "",
            "plot_directory": "",
            "subpart_first_id": 65,
            "subpart_id_separator": 0,
        },
        "sheets": [[root_uuid, "Root"]]
        + [[s.uuid, s.name] for s in sheets],
        "text_variables": {},
    }
    path.write_text(json.dumps(doc, indent=2) + "\n")


def write_lib_tables(design_dir: Path, sym_libs: list[tuple[str, str, str]],
                     fp_libs: list[tuple[str, str, str]]) -> None:
    def table(kind: str, entries: list[tuple[str, str, str]]) -> str:
        out = [f"({kind}_lib_table\n", '  (version 7)\n']
        for name, uri, descr in entries:
            out.append(
                f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")'
                f'(options "")(descr "{descr}"))\n'
            )
        out.append(")\n")
        return "".join(out)

    (design_dir / "sym-lib-table").write_text(table("sym", sym_libs))
    (design_dir / "fp-lib-table").write_text(table("fp", fp_libs))


# ==========================================================================
# Wiring
# ==========================================================================


# Symbols whose body should point along the stub, so the glyph sits clear of
# the wire instead of on top of it.
_PWR_PIN_ANGLE = {"GND": 270.0}


class Wirer:
    """Draws nets onto one sheet.

    Nets are made by **name**: every pin gets a short stub and a label, and
    identically spelled labels are one net. Drawing 448 BGA balls as wire
    polylines is not tractable by hand or by generator, and KiCad treats the
    two forms as equivalent, so this is the form used throughout.

    Pins are addressed as ``("U101", "PGND1")`` -- reference plus either a
    pin *name* or a pin *number*. Names are tried first because they are what
    the datasheet talks about. A name shared by several balls (``VSS``, 83 of
    them) resolves to the stack, which is one point, so one label wires all
    of them.
    """

    STUB = 2.54          # one grid square, enough to hang a label off

    def __init__(self, sheet: Sheet, cache: SymbolCache):
        self.sheet = sheet
        self.cache = cache
        self._by_ref: dict[str, list[Comp]] = {}
        for c in sheet.comps:
            self._by_ref.setdefault(c.ref, []).append(c)

    # -- geometry ---------------------------------------------------------

    def _comp(self, ref: str, unit: int | None = None) -> Comp:
        try:
            cands = self._by_ref[ref]
        except KeyError:
            raise KeyError(
                f"{self.sheet.filename}: no component {ref!r} on this sheet"
            ) from None
        if unit is not None:
            for c in cands:
                if c.unit == unit:
                    return c
            raise KeyError(f"{ref} has no unit {unit} on {self.sheet.filename}")
        if len(cands) > 1:
            units = ", ".join(str(c.unit) for c in cands)
            raise KeyError(
                f"{ref} is on this sheet as units {units} -- name one"
            )
        return cands[0]

    def _geom(self, ref: str, ident: str, unit: int | None = None
              ) -> tuple[Comp, PinGeom]:
        c = self._comp(ref, unit)
        pins = self.cache.pins(c.lib_id, c.unit)
        if not pins:
            raise KeyError(f"{ref}: no pins found for {c.lib_id} unit {c.unit}")
        by_name = [g for g in pins.values() if g.name == ident]
        if by_name:
            return c, by_name[0]
        if ident in pins:
            return c, pins[ident]
        known = ", ".join(sorted({g.name for g in pins.values()})[:12])
        raise KeyError(
            f"{ref} ({c.lib_id} unit {c.unit}) has no pin {ident!r}. "
            f"Names include: {known}"
        )

    def pin_xy(self, ref: str, ident: str, unit: int | None = None
               ) -> tuple[float, float]:
        """Absolute position of a pin's connection point, in mm."""
        c, g = self._geom(ref, ident, unit)
        dx, dy = _xform(g.x, g.y, c.rot, c.mirror)
        return c.x + dx, c.y + dy

    # -- primitives -------------------------------------------------------

    def stub(self, ref: str, ident: str, length: float | None = None,
             unit: int | None = None) -> tuple[float, float, int]:
        """Run a wire outward from a pin. Returns the free end and its angle."""
        c, g = self._geom(ref, ident, unit)
        dx, dy = _xform(g.x, g.y, c.rot, c.mirror)
        px, py = c.x + dx, c.y + dy
        ox, oy = _outward(g, c.rot, c.mirror)
        ln = self.STUB if length is None else length
        ex, ey = px + ox * ln, py + oy * ln
        if ln:
            self.sheet.wires.append(Wire(px, py, ex, ey))
        rot = {(1.0, 0.0): 0, (0.0, -1.0): 90,
               (-1.0, 0.0): 180, (0.0, 1.0): 270}[(ox, oy)]
        return ex, ey, rot

    def label(self, ref: str, ident: str, name: str, kind: str = "local",
              unit: int | None = None, length: float | None = None) -> None:
        """Stub a pin and name the net at the free end."""
        ex, ey, rot = self.stub(ref, ident, length, unit)
        self.sheet.labels.append(Label(name, ex, ey, rot, kind))

    def net(self, name: str, *pins, kind: str = "local") -> None:
        """Put every listed pin on one net.

        ``pins`` are ``(ref, ident)`` or ``(ref, ident, unit)``.
        """
        for spec in pins:
            ref, ident, *rest = spec
            self.label(ref, ident, name, kind, rest[0] if rest else None)

    def rail(self, name: str, *pins) -> None:
        """A net that crosses sheets. Same as ``net`` but global."""
        self.net(name, *pins, kind="global")

    def power(self, ref: str, ident: str, sym: str = "GND",
              unit: int | None = None) -> None:
        """Hang a power/ground port symbol straight off a pin."""
        ex, ey, rot = self.stub(ref, ident, unit=unit)
        body = {0: (1.0, 0.0), 90: (0.0, -1.0),
                180: (-1.0, 0.0), 270: (0.0, 1.0)}[rot]
        a0 = _PWR_PIN_ANGLE.get(sym, 90.0)
        import math
        for prot in (0, 90, 180, 270):
            v = _xform(math.cos(math.radians(a0)),
                       math.sin(math.radians(a0)), prot, None)
            v = (round(v[0]), round(v[1]))
            if v == (round(body[0]), round(body[1])):
                break
        self.sheet.powers.append(PowerPort(sym, ex, ey, prot))

    def gnd(self, *pins) -> None:
        """Ground every listed pin with a ``power:GND`` port."""
        for spec in pins:
            ref, ident, *rest = spec
            self.power(ref, ident, "GND", rest[0] if rest else None)

    def no_connect(self, ref: str, ident: str, unit: int | None = None
                   ) -> None:
        x, y = self.pin_xy(ref, ident, unit)
        self.sheet.no_connects.append(NoConnect(x, y))

    def flag(self, name: str, x: float, y: float) -> None:
        """Drop a PWR_FLAG on a rail so ERC stops calling it undriven.

        Needed once per rail that is generated on this board rather than
        arriving through a component KiCad recognises as a source.
        """
        x, y = snap(x), snap(y)
        self.sheet.powers.append(PowerPort("PWR_FLAG", x, y, 0))
        self.sheet.labels.append(Label(name, x, y, 90, "global"))
