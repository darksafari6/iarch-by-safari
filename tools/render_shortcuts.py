#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render docs/SHORTCUTS.md from data/keybinds.default.json.

The document is generated because a hand-written shortcut table always drifts
from the session that implements the shortcuts. The chain is:

    .config/hypr/keybind.lua          what the session actually binds
      -> tools/extract_keybinds.py    data/keybinds.default.json
        -> tools/render_shortcuts.py  docs/SHORTCUTS.md (and, in Part 7, the
                                      in-session overlay the same data drives)

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
OUTPUT = ROOT / "docs" / "SHORTCUTS.md"
COPYRIGHT = "Copyright (C) 2026 Safari — GPL-3.0-or-later"

BANNER = (
    "<!-- GENERATED FILE - do not edit by hand.\n"
    "     Source: data/keybinds.default.json (extracted from .config/hypr/keybind.lua)\n"
    "     Regenerate: python3 tools/render_shortcuts.py --write\n"
    "     Verify: python3 tools/render_shortcuts.py --check -->"
)


def load() -> Dict[str, Any]:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def keys_in_order(data: Dict[str, Any]) -> List[str]:
    """Categories in the order the Lua file declares them."""
    order: List[str] = []
    for binding in data["bindings"]:
        if binding["category"] not in order:
            order.append(binding["category"])
    return order


def render(data: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Keyboard shortcuts")
    lines.append("")
    lines.append(BANNER)
    lines.append("")
    lines.append(
        f"{len([b for b in data['bindings'] if b['status'] == 'bound'])} shortcuts, "
        f"generated from `{SOURCE.relative_to(ROOT)}`, which "
        f"`tools/extract_keybinds.py` reads out of `{data['source_file']}`. "
        "If this table and your session disagree, the session is right and this file is stale: "
        "run `python3 tools/render_shortcuts.py --write`."
    )
    lines.append("")
    lines.append(
        f"`{data['modifier']}` is the Super key — the Windows key on most keyboards, "
        "Command on an Apple one. Mouse bindings are listed with their button, "
        "and `locked` media keys keep working while the screen is locked."
    )
    lines.append("")
    lines.append("## Contents")
    lines.append("")
    for category in keys_in_order(data):
        anchor = category.lower().replace(" ", "-").replace("&", "").replace("--", "-")
        lines.append(f"- [{category}](#{anchor})")
    lines.append("")

    for category in keys_in_order(data):
        group = [b for b in data["bindings"] if b["category"] == category]
        lines.append(f"## {category}")
        lines.append("")
        if category == "Planned":
            lines.append(
                "Defined in the session configuration but not bound yet, so nothing happens when "
                "you press them. They are reserved for the in-session shortcut overlay, which "
                "[docs/ROADMAP.md](ROADMAP.md) schedules as Part 7. This table lists them so the "
                "keys are not reassigned by accident in the meantime."
            )
            lines.append("")
        lines.append("| Keys | What it does |")
        lines.append("| :--- | :--- |")
        for binding in group:
            note = binding["description"]
            if binding["status"] == "reserved":
                note += " *(not bound yet)*"
            elif binding["action"]["kind"] == "exec" and binding["action"].get("command"):
                command = binding["action"]["command"]
                shown = command if len(command) <= 60 else command[:57] + "..."
                note += f" — runs `{shown}`"
            options = binding.get("options", {})
            flags = " ".join(flag for flag in ("mouse", "locked") if options.get(flag))
            if flags:
                note += f" *({flags})*"
            lines.append(f"| `{binding['keys']}` | {note} |")
        lines.append("")

    lines.append("## Changing a shortcut")
    lines.append("")
    lines.append(
        "Edit `~/.config/iarch/keybinds.json`, not the repository. The generators described in "
        "[docs/ARCHITECTURE.md](ARCHITECTURE.md) render the session configuration from your file "
        "merged over `data/keybinds.default.json`, stamp it as generated, back the previous copy "
        "up, and reload. Until that generator ships, the binding that runs today is the one in "
        f"`{data['source_file']}` and this table documents it."
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
    rendered = render(data)
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(rendered, encoding="utf-8")
        print(f"shortcuts: wrote {OUTPUT.relative_to(ROOT)} "
              f"({len(data['bindings'])} shortcuts, {len(keys_in_order(data))} categories)")
        return 0

    if not OUTPUT.is_file():
        print(f"shortcuts: {OUTPUT} does not exist; run python3 tools/render_shortcuts.py --write",
              file=sys.stderr)
        return 1
    if OUTPUT.read_text(encoding="utf-8") != rendered:
        print(f"shortcuts: {OUTPUT.relative_to(ROOT)} is out of date with "
              f"{SOURCE.relative_to(ROOT)}; run python3 tools/render_shortcuts.py --write",
              file=sys.stderr)
        return 1
    print(f"shortcuts: {OUTPUT.relative_to(ROOT)} matches {SOURCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
