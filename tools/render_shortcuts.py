#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render docs/SHORTCUTS.md from data/keybinds.default.json.

The document is generated because a hand-written shortcut table always drifts
from the session that implements the shortcuts. Since Part 5 the chain runs the
other way round than it used to:

    data/keybinds.default.json        the source of the keyboard map
      -> iarch/cli/iarch_keybinds.py  .config/hypr/generated/keybinds.lua
      -> tools/render_shortcuts.py    docs/SHORTCUTS.md

The A to Z table at the end of the document has a second source: the ``alphabet``
section of data/design/keybinds.json, which allocates all 78 letter cells of the
three layers a letter may live in. The renderer refuses to write a table that
disagrees with the map, in either direction, so the grid cannot flatter a bind
that moved.

The same record drives the generated Lua, this document, the Shortcuts page in
the settings application and -- when it ships -- the Super+H overlay, so a table
here and a bind in the session cannot disagree unless the record has been edited
and one of the renderers not re-run. `iarch-keybinds docs` runs this file.

Usage:
    python3 tools/render_shortcuts.py --write   # regenerate the document
    python3 tools/render_shortcuts.py --check   # CI: document matches the data
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "keybinds.default.json"
DESIGN = ROOT / "data" / "design" / "keybinds.json"
OUTPUT = ROOT / "docs" / "SHORTCUTS.md"
COPYRIGHT = "Copyright (C) 2026 Safari — GPL-3.0-or-later"

BANNER = (
    "<!-- GENERATED FILE - do not edit by hand.\n"
    "     Source: data/keybinds.default.json (the source iarch-keybinds renders the session from)\n"
    "             and data/design/keybinds.json -> alphabet (the A to Z allocation)\n"
    "     Regenerate: python3 tools/render_shortcuts.py --write\n"
    "     Verify: python3 tools/render_shortcuts.py --check -->"
)


def load() -> Dict[str, Any]:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def load_design() -> Dict[str, Any]:
    return json.loads(DESIGN.read_text(encoding="utf-8"))


def key_string(binding: Dict[str, Any]) -> str:
    """The combination as a person reads it: modifiers and the key joined by ' + '."""
    return " + ".join(list(binding.get("mods") or []) + [binding["key"]])


def is_bound(binding: Dict[str, Any]) -> bool:
    return bool(binding.get("enabled")) and binding["action"].get("type") != "none"


def categories_in_order(data: Dict[str, Any]) -> List[str]:
    order: List[str] = []
    for binding in data["bindings"]:
        category = binding.get("category", "General")
        if category not in order:
            order.append(category)
    return order


def what_it_does(binding: Dict[str, Any]) -> str:
    """The action, in words, for the right-hand column."""
    action = binding["action"]
    kind = action["type"]
    if kind == "exec":
        return "runs `" + " ".join(action["command"]) + "`"
    if kind == "shell":
        script = action["script"]
        shown = script if len(script) <= 64 else script[:61] + "..."
        return f"runs `{shown}` *(shell)*"
    if kind == "noctalia":
        argv = " ".join([action["verb"], *(action.get("args") or [])])
        return f"sends the shell `{argv}`"
    if kind == "iarch":
        argv = " ".join([action["cli"], *(action.get("args") or [])])
        return f"runs `{argv}`"
    if kind == "dispatch":
        return f"compositor action `{action['dispatcher'].removeprefix('hl.dsp.')}`"
    if kind == "lua":
        return "a short Lua routine"
    return ""


def alphabet_section(data: Dict[str, Any], design: Dict[str, Any]) -> List[str]:
    """The 78 letter cells of the three layers, as a grid and as a list of refusals.

    Read out of the design record and checked against the map on the way out: a cell
    that says ``bound`` has to name a binding that is enabled at exactly those keys, a
    cell that says ``declared`` has to name one that is not, and a cell that says
    ``reserved`` or ``free`` has to have nothing there at all. The check is in the
    renderer as well as in tests/test_keybinds_alphabet.py because the two answer
    different questions -- the test fails a commit, this refuses to write a document
    that would flatter a bind which moved.
    """
    def prose(text: str) -> str:
        """The record writes an ASCII dash; this document is Markdown and reads better
        with the em dash every other sentence in it already uses."""
        return text.replace(" -- ", " — ")

    alphabet = design.get("alphabet")
    if not alphabet:
        raise SystemExit(f"shortcuts: {DESIGN.relative_to(ROOT)} has no alphabet section, "
                         "so the A to Z table has no source to be rendered from")

    by_id = {b["id"]: b for b in data["bindings"]}
    occupied: Dict[str, str] = {}
    for binding in data["bindings"]:
        key = binding.get("key", "")
        if len(key) == 1 and key.isalpha():
            combo = " + ".join(list(binding.get("mods") or []) + [key.upper()])
            occupied[combo] = binding["id"]

    layers = alphabet["layers"]
    lines: List[str] = []
    lines.append("## The A to Z table")
    lines.append("")
    cells = sum(len(layer["cells"]) for layer in layers)
    counted = {2: "both", 3: "all three"}.get(len(layers), f"all {len(layers)}")
    lines.append(
        f"Every letter of {counted} layers a letter may live in — {cells} cells — "
        "each one decided before anything was bound to it. A modifier layer is a budget, "
        "and an undecided letter is where an arbitrary bind lands later, so the allocation "
        f"is written down in `{DESIGN.relative_to(ROOT)}` under `alphabet` and rendered "
        "here. `tests/test_keybinds_alphabet.py` proves the table and the map agree in "
        "both directions. It describes the shipped defaults only: your own "
        "`~/.config/iarch/keybinds.json` may use any empty cell it likes, and "
        "`iarch-keybinds check` does not consult this table, because a person's map is "
        "theirs and a checker that policed it would be policing the wrong file."
    )
    lines.append("")
    for layer in layers:
        lines.append(f"`{' + '.join(layer['mods'])}` — **{layer['name']}**. "
                     f"{prose(layer['purpose'])}")
        lines.append("")

    header = "| Letter | " + " | ".join(f"`{' + '.join(layer['mods'])}`" for layer in layers) + " |"
    lines.append(header)
    lines.append("| :--- |" + " :--- |" * len(layers))

    refusals: List[str] = []
    for letter_index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        row = [letter]
        for layer in layers:
            cell = layer["cells"][letter_index]
            if cell["key"] != letter:
                raise SystemExit(f"shortcuts: the alphabet table's {layer['name']} layer is "
                                 f"out of order at {letter}")
            combo = " + ".join(list(layer["mods"]) + [letter])
            status = cell["status"]
            if status in ("bound", "declared"):
                binding = by_id.get(cell["binding"])
                if binding is None:
                    raise SystemExit(f"shortcuts: the alphabet table gives {combo} to "
                                     f"{cell['binding']!r}, which the map does not have")
                actual = " + ".join(list(binding.get("mods") or []) + [binding["key"]])
                if actual != combo:
                    raise SystemExit(f"shortcuts: the alphabet table gives {combo} to "
                                     f"{cell['binding']!r}, but the map binds it at {actual}")
                if is_bound(binding) != (status == "bound"):
                    raise SystemExit(f"shortcuts: the alphabet table calls {cell['binding']!r} "
                                     f"{status} at {combo}, and the map says otherwise")
                row.append(binding["description"] +
                             ("" if status == "bound" else " *(not bound yet)*"))
            else:
                owner = occupied.get(combo)
                if owner:
                    raise SystemExit(f"shortcuts: the alphabet table leaves {combo} "
                                     f"{status}, but the map binds {owner} there")
                if status == "reserved":
                    row.append("*reserved*")
                    refusals.append(f"- **`{combo}`** — {prose(cell['reason'])}")
                else:
                    row.append("—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("### Why a cell is empty")
    lines.append("")
    lines.append(
        "*reserved* is a refusal with a mechanism behind it, and an em dash is a cell "
        "left empty on purpose. Every refusal is listed first, in letter order, then the "
        "reason each layer leaves the rest of its letters alone."
    )
    lines.append("")
    lines.extend(refusals)
    for layer in layers:
        lines.append(f"- *Every other letter of `{' + '.join(layer['mods'])}`* — "
                     f"{prose(layer['free_reason'])}")
    lines.append("")
    return lines


def render(data: Dict[str, Any], design: Optional[Dict[str, Any]] = None) -> str:
    bound = [b for b in data["bindings"] if is_bound(b)]
    reserved = [b for b in data["bindings"] if not is_bound(b)]
    lines: List[str] = []
    lines.append("# Keyboard shortcuts")
    lines.append("")
    lines.append(BANNER)
    lines.append("")
    lines.append(
        f"{len(bound)} shortcuts, generated from `{SOURCE.relative_to(ROOT)}`, which "
        "`iarch-keybinds` renders into `.config/hypr/generated/keybinds.lua`. The record "
        "is the source and the Lua is generated, so if this table and your session "
        "disagree, one of them is stale: run `python3 tools/render_shortcuts.py --write` "
        "for this file, or `iarch-keybinds generate --write` for the session."
    )
    lines.append("")
    lines.append(
        "`SUPER` is the Super key — the Windows key on most keyboards, Command on an "
        "Apple one. A bind marked *(mouse)* is a button or a scroll, and *(locked)* media "
        "keys keep working while the screen is locked."
    )
    lines.append("")
    lines.append("## Contents")
    lines.append("")
    for category in categories_in_order(data):
        anchor = category.lower().replace(" ", "-").replace("&", "").replace("--", "-")
        lines.append(f"- [{category}](#{anchor})")
    lines.append("- [The A to Z table](#the-a-to-z-table)")
    lines.append("")

    for category in categories_in_order(data):
        group = [b for b in data["bindings"] if b.get("category") == category]
        lines.append(f"## {category}")
        lines.append("")
        if not any(is_bound(b) for b in group):
            lines.append(
                "Declared in the record but not bound, so nothing happens when you press "
                "them. They are reserved so the keys are not reassigned by accident; the "
                "shortcut overlay `SUPER + H` opens is scheduled in "
                "[docs/ROADMAP.md](ROADMAP.md)."
            )
            lines.append("")
        lines.append("| Keys | What it does |")
        lines.append("| :--- | :--- |")
        for binding in group:
            note = binding["description"]
            if not is_bound(binding):
                note += " *(not bound yet)*"
            else:
                does = what_it_does(binding)
                if does:
                    note += f" — {does}"
            flags = binding.get("flags") or {}
            marks = " ".join(name for name in ("mouse", "locked") if flags.get(name))
            if marks:
                note += f" *({marks})*"
            lines.append(f"| `{key_string(binding)}` | {note} |")
        lines.append("")

    lines.extend(alphabet_section(data, design if design is not None else load_design()))

    if reserved:
        lines.append("## Changing a shortcut")
        lines.append("")
        lines.append(
            "Edit `~/.config/iarch/keybinds.json`, not the repository. It holds only your "
            "differences — a rebind is the id and the new key and nothing else — and "
            "`iarch-keybinds generate` renders it merged over "
            f"`{SOURCE.relative_to(ROOT)}`, stamps the result as generated, backs the "
            "previous copy up, and validates the whole map before it writes any of it. "
            "The bindings that run today are the ones in "
            "`.config/hypr/generated/keybinds.lua`, and this table documents them."
        )
        lines.append("")

    lines.append(f"<!-- {COPYRIGHT} -->")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    data = load()
    rendered = render(data, load_design())
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(rendered, encoding="utf-8")
        bound = len([b for b in data["bindings"] if is_bound(b)])
        print(f"shortcuts: wrote {OUTPUT.relative_to(ROOT)} "
              f"({bound} shortcuts, {len(categories_in_order(data))} categories)")
        return 0

    if not OUTPUT.is_file():
        print(f"shortcuts: {OUTPUT} does not exist; run python3 tools/render_shortcuts.py --write",
              file=sys.stderr)
        return 1
    if OUTPUT.read_text(encoding="utf-8") != rendered:
        print(f"shortcuts: {OUTPUT.relative_to(ROOT)} is out of date with "
              f"{SOURCE.relative_to(ROOT)} and {DESIGN.relative_to(ROOT)}; run "
              "python3 tools/render_shortcuts.py --write",
              file=sys.stderr)
        return 1
    print(f"shortcuts: {OUTPUT.relative_to(ROOT)} matches {SOURCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
