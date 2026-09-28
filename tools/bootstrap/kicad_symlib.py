#!/usr/bin/env python3
"""Shared primitives for emitting KiCad 10 symbol libraries.

Used by ``gen_mpu_symbol.py`` (derives a multi-unit MPU symbol from KiCad's
stock library) and ``gen_custom_symbols.py`` (builds symbols that no stock
library provides). Both write into the same project library, so the
insert-or-replace logic lives here and is shared.

Pin placement model
-------------------
Pins are given as ``Pin`` records grouped into sides (``left``, ``right``,
``bottom``). The emitter lays each side out on a 2.54 mm grid, sizes the body
rectangle to fit, and returns the resulting coordinates so callers can dump a
pin map for the wiring pass.

Pins that share a name and are marked stackable land on a single coordinate.
KiCad treats overlapping pins as one electrical node, so a single wire drives
the whole stack while every pad number still appears in the netlist. This is
what makes a 448-ball MPU or a 153-ball eMMC drawable by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

GRID = 2.54
PIN_LEN = 5.08
FONT = 1.27

# Fixed, not the name of the calling script: three generators write into
# this one library, and recording whichever ran last would make the file
# depend on invocation order.
LIB_GENERATOR = "rtk-gps-module/scripts"

LIB_HEADER = (
    "(kicad_symbol_lib\n"
    "\t(version 20251024)\n"
    f'\t(generator "{LIB_GENERATOR}")\n'
    '\t(generator_version "10.0")\n'
)


@dataclass
class Pin:
    """One schematic pin. ``number`` is the package pad or ball designator."""

    name: str
    number: str
    etype: str = "passive"
    stack: bool = False


@dataclass
class Unit:
    """One symbol unit: a body rectangle with pins on up to three sides."""

    left: list[Pin] = field(default_factory=list)
    right: list[Pin] = field(default_factory=list)
    bottom: list[Pin] = field(default_factory=list)
    min_half_width: float = 25.4


def fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _effects(indent: str) -> str:
    i2 = indent + "\t"
    return (
        f"{indent}(effects\n{i2}(font\n{i2}\t(size {fmt(FONT)} {fmt(FONT)})\n"
        f"{i2})\n{indent})\n"
    )


def emit_pin(p: Pin, x: float, y: float, angle: int, indent: str) -> str:
    i2, i3 = indent + "\t", indent + "\t\t"
    return (
        f"{indent}(pin {p.etype} line\n"
        f"{i2}(at {fmt(x)} {fmt(y)} {angle})\n"
        f"{i2}(length {fmt(PIN_LEN)})\n"
        f'{i2}(name "{esc(p.name)}"\n{_effects(i3)}{i2})\n'
        f'{i2}(number "{esc(p.number)}"\n{_effects(i3)}{i2})\n'
        f"{indent})\n"
    )


def emit_property(
    name: str,
    value: str,
    x: float = 0,
    y: float = 0,
    hide: bool = True,
    justify: str | None = None,
) -> str:
    out = [
        f'\t\t(property "{name}" "{esc(value)}"\n',
        f"\t\t\t(at {fmt(x)} {fmt(y)} 0)\n",
        "\t\t\t(show_name no)\n",
        "\t\t\t(do_not_autoplace no)\n",
    ]
    if hide:
        out.append("\t\t\t(hide yes)\n")
    out.append("\t\t\t(effects\n\t\t\t\t(font\n")
    out.append(f"\t\t\t\t\t(size {fmt(FONT)} {fmt(FONT)})\n")
    out.append("\t\t\t\t)\n")
    if justify:
        out.append(f"\t\t\t\t(justify {justify})\n")
    out.append("\t\t\t)\n\t\t)\n")
    return "".join(out)


def stack_slots(pins: list[Pin]) -> list[list[Pin]]:
    """Collapse same-named stackable pins into one slot each, order preserved."""
    slots: list[list[Pin]] = []
    seen: dict[str, list[Pin]] = {}
    for p in pins:
        if p.stack and p.name in seen:
            seen[p.name].append(p)
            continue
        group = [p]
        if p.stack:
            seen[p.name] = group
        slots.append(group)
    return slots


def _name_width(pins: list[Pin]) -> float:
    longest = max((len(p.name) for p in pins), default=0)
    return longest * FONT * 0.62


def emit_unit(
    symbol_name: str, index: int, unit: Unit
) -> tuple[str, dict[str, tuple[float, float, str]]]:
    """Return (unit s-expression, {pin name: (x, y, side)}).

    Coordinates are library coordinates (Y up), relative to the unit origin.
    """
    left = stack_slots(unit.left)
    right = stack_slots(unit.right)
    bottom = stack_slots(unit.bottom)

    rows = max(len(left), len(right), 1)
    half_h = ((rows - 1) * GRID) / 2 + GRID
    if bottom:
        half_h = max(half_h, GRID * 2)

    flat_l = [p for g in left for p in g]
    flat_r = [p for g in right for p in g]
    half_w = max(
        unit.min_half_width,
        (_name_width(flat_l) + _name_width(flat_r)) / 2 + 3 * GRID,
        ((len(bottom) - 1) * GRID) / 2 + 2 * GRID if bottom else 0,
    )
    half_w = round(half_w / GRID) * GRID

    out = [
        f'\t\t(symbol "{symbol_name}_{index}_1"\n',
        "\t\t\t(rectangle\n",
        f"\t\t\t\t(start {fmt(-half_w)} {fmt(half_h)})\n",
        f"\t\t\t\t(end {fmt(half_w)} {fmt(-half_h)})\n",
        "\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n",
        "\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n",
        "\t\t\t)\n",
    ]

    pinmap: dict[str, tuple[float, float, str]] = {}
    top = ((rows - 1) * GRID) / 2

    for i, group in enumerate(left):
        y = top - i * GRID
        x = -half_w - PIN_LEN
        for p in group:
            out.append(emit_pin(p, x, y, 0, "\t\t\t"))
        pinmap[group[0].name] = (x, y, "L")

    for i, group in enumerate(right):
        y = top - i * GRID
        x = half_w + PIN_LEN
        for p in group:
            out.append(emit_pin(p, x, y, 180, "\t\t\t"))
        pinmap[group[0].name] = (x, y, "R")

    bx0 = -((len(bottom) - 1) * GRID) / 2
    for i, group in enumerate(bottom):
        x = bx0 + i * GRID
        y = -half_h - PIN_LEN
        for p in group:
            out.append(emit_pin(p, x, y, 90, "\t\t\t"))
        pinmap[group[0].name] = (x, y, "B")

    out.append("\t\t)\n")
    return "".join(out), pinmap


def emit_symbol(
    name: str,
    units: list[Unit],
    properties: dict[str, str],
    ref_prefix: str = "U",
) -> tuple[str, dict[int, dict[str, tuple[float, float, str]]]]:
    """Build a complete (symbol ...) block. Returns (text, {unit: pinmap})."""
    rows = max((max(len(u.left), len(u.right)) for u in units), default=1)
    label_y = ((rows - 1) * GRID) / 2 + GRID * 2

    out = [
        f'\t(symbol "{name}"\n',
        "\t\t(pin_names\n\t\t\t(offset 1.016)\n\t\t)\n",
        "\t\t(exclude_from_sim no)\n",
        "\t\t(in_bom yes)\n",
        "\t\t(on_board yes)\n",
        "\t\t(in_pos_files yes)\n",
        "\t\t(duplicate_pin_numbers_are_jumpers no)\n",
        emit_property("Reference", ref_prefix, -25.4, label_y, False, "left"),
        emit_property("Value", name, 5.08, label_y, False, "left"),
    ]
    for key in ("Footprint", "Datasheet", "Description"):
        out.append(emit_property(key, properties.get(key, ""), 0, 0, True))
    for key, val in properties.items():
        if key not in ("Footprint", "Datasheet", "Description"):
            out.append(emit_property(key, val, 0, 0, True))

    pinmaps = {}
    for i, unit in enumerate(units, start=1):
        text, pinmap = emit_unit(name, i, unit)
        out.append(text)
        pinmaps[i] = pinmap
    out.append("\t)\n")
    return "".join(out), pinmaps


def split_symbols(lib_text: str) -> dict[str, str]:
    """Return {symbol name: raw text} for a library, order preserved."""
    out: dict[str, str] = {}
    for m in re.finditer(r'^\t\(symbol "([^"]+)"', lib_text, re.M):
        name = m.group(1)
        nxt = lib_text.find('\n\t(symbol "', m.end())
        if nxt < 0:
            body = lib_text[m.start() :]
            close = body.rfind(")")          # library's own closing paren
            body = body[:close].rstrip() + "\n"
        else:
            body = lib_text[m.start() : nxt + 1]
        out[name] = body
    return out


def upsert(lib_path: Path, symbol_text: str, symbol_name: str,
           generator: str = LIB_GENERATOR) -> None:
    """Insert or replace one symbol, leaving the others intact.

    Symbols are always written back in name order. Three separate
    generators write into this one library, so without a canonical order
    the file's contents depend on which script ran last -- regenerating
    would produce a 4000-line reordering diff and destroy the idempotency
    that deterministic UUIDs are there to provide.
    """
    symbols: dict[str, str] = {}
    if lib_path.exists():
        symbols = split_symbols(lib_path.read_text())
    symbols[symbol_name] = symbol_text

    body = "".join(symbols[k] for k in sorted(symbols))
    lib_path.parent.mkdir(parents=True, exist_ok=True)
    lib_path.write_text(LIB_HEADER + body + ")\n")


def sorted_symbol_names(lib_path: Path) -> list[str]:
    if not lib_path.exists():
        return []
    return re.findall(r'^\t\(symbol "([^"_]+(?:[^"]*)?)"', lib_path.read_text(),
                      re.M)
