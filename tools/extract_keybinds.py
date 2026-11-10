#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Extract the shipped keyboard map into data/keybinds.default.json.

The Lua configuration is the source of truth for what a key does today; the
JSON file is the default the future settings app and shortcut overlay read.
Nothing here is typed by hand: every entry is parsed out of
`.config/hypr/keybind.lua`, including the workspace loop, which is expanded the
same way Lua expands it at runtime.

Usage:
    python3 tools/extract_keybinds.py --write   # regenerate the JSON
    python3 tools/extract_keybinds.py --check   # CI: JSON matches the Lua
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".config" / "hypr" / "keybind.lua"
OUTPUT = ROOT / "data" / "keybinds.default.json"
COPYRIGHT = "Copyright (C) 2026 Safari — GPL-3.0-or-later"

# Keys the Lua file defines but never binds yet; reserved for later parts.
RESERVED = (
    ("CHEATSHEET_TOGGLE", "Shortcut overlay (Part 7)"),
    ("CHEATSHEET_REFRESH", "Refresh the shortcut overlay (Part 7)"),
    ("HYPR_KEYS_PANEL", "Hyprland key panel (Part 7)"),
)


class Bind(NamedTuple):
    keys: str
    description: str
    action: Dict[str, str]
    options: Dict[str, bool]
    status: str = "bound"


def split_args(text: str, start: int) -> List[str]:
    """Split a Lua call's arguments at top-level commas, quote and paren aware."""
    args: List[str] = []
    depth = 0
    quote: Optional[str] = None
    buf: List[str] = []
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "({[":
            depth += 1
            buf.append(ch)
        elif ch in ")}]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        elif ch == "-" and text[i:i + 2] == "--":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        args.append(tail)
    return args


def parse_key_table(text: str) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    block = re.search(r"local KEY = \{(.*?)\n\}", text, re.S)
    assert block, "KEY table not found in keybind.lua"
    for name, fmt in re.findall(r"(\w+)\s*=\s*\(\"([^\"]*)\"\):format\(mainMod\)", block.group(1)):
        keys[name] = fmt.replace("%s", "SUPER").replace("%d", "{digit}")
    return keys


LOCAL_COMMANDS = {
    "TERMINAL": "kitty",
    "EDITOR": "code",
    "EXPLORER": "thunar",
    "BROWSER": "~/.config/hypr/Scripts/browser-launcher.sh",
}


def parse_action(raw: str) -> Dict[str, str]:
    raw = raw.strip()
    ident = re.fullmatch(r'hl\.dsp\.exec_cmd\(\s*(\w+)\s*\)', raw)
    if ident and ident.group(1) in LOCAL_COMMANDS:
        return {"kind": "exec", "command": LOCAL_COMMANDS[ident.group(1)], "lua": raw}
    exec_match = re.fullmatch(r'hl\.dsp\.exec_cmd\(\s*"((?:[^"\\]|\\.)*)"\s*\)', raw)
    if exec_match:
        command = exec_match.group(1).replace('\\"', '"')
        return {"kind": "exec", "command": command, "lua": raw}
    if raw.startswith("function"):
        return {"kind": "lua-function", "lua": re.sub(r"\s+", " ", raw)}
    return {"kind": "dispatcher", "lua": raw}


def parse_options(raw: str) -> Dict[str, bool]:
    options = {}
    for flag in ("mouse", "locked"):
        if re.search(rf"\b{flag}\s*=\s*true\b", raw):
            options[flag] = True
    return options


def parse_description(raw: str) -> str:
    match = re.search(r'description\s*=\s*"((?:[^"\\]|\\.)*)"', raw)
    return match.group(1).replace('\\"', '"') if match else ""


def expand(text: str, keys: Dict[str, str]) -> List[Bind]:
    binds: List[Bind] = []
    for match in re.finditer(r"hl\.bind\(", text):
        args = split_args(text, match.end())
        if len(args) < 3:
            continue
        key_expr, action_expr, opts_expr = args[0], args[1], args[2]
        description = parse_description(opts_expr)
        options = parse_options(opts_expr)
        action = parse_action(action_expr)

        literal = re.fullmatch(r'"([^"]*)"', key_expr)
        named = re.fullmatch(r"KEY\.(\w+)", key_expr)
        loop_focus = re.fullmatch(r'focusKey', key_expr)
        loop_move = re.fullmatch(r"moveKey", key_expr)
        formatted = re.fullmatch(r'\("%s \+ ([^"]+)"\):format\(mainMod\)', key_expr)

        if loop_focus or loop_move:
            for digit in range(1, 10):  # the Lua loop: for i = 1, 9 do
                prefix = "SUPER + SHIFT + " if loop_move else "SUPER + "
                # Lua renders `"Workspace " .. i` into "Workspace 3" and so on.
                binds.append(Bind(
                    keys=f"{prefix}{digit}",
                    description=f"{description}{digit}",
                    action={**action, "workspace": str(digit)},
                    options=options,
                ))
            continue
        if literal:
            key = literal.group(1)
        elif named:
            key = keys.get(named.group(1), named.group(1))
        elif formatted:
            key = f"SUPER + {formatted.group(1)}"
        else:
            continue
        binds.append(Bind(keys=key, description=description, action=action, options=options))
    return binds


def build() -> Dict[str, object]:
    text = SOURCE.read_text(encoding="utf-8")
    keys = parse_key_table(text)
    binds = expand(text, keys)
    for name, why in RESERVED:
        binds.append(Bind(keys=keys[name], description=why, action={"kind": "reserved"},
                          options={}, status="reserved"))
    return {
        "_copyright": COPYRIGHT,
        "generated_by": "tools/extract_keybinds.py --write",
        "source_file": ".config/hypr/keybind.lua",
        "version": 1,
        "modifier": "SUPER",
        "bindings": [
            {
                "keys": b.keys,
                "description": b.description,
                "action": b.action,
                **({"options": b.options} if b.options else {}),
                "status": b.status,
            }
            for b in binds
        ],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    data = build()
    if args.write:
        OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {OUTPUT.relative_to(ROOT)} with {len(data['bindings'])} bindings")
        return 0
    current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if current != data:
        print(f"{OUTPUT.relative_to(ROOT)} is out of date with {SOURCE.relative_to(ROOT)}; "
              "run python3 tools/extract_keybinds.py --write", file=sys.stderr)
        return 1
    print(f"{OUTPUT.relative_to(ROOT)} matches {SOURCE.relative_to(ROOT)} "
          f"({len(data['bindings'])} bindings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
