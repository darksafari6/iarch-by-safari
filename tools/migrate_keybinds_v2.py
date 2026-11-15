#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Migrate the extracted keybind record to the shape the generator renders from.

    python3 tools/migrate_keybinds_v2.py            # print what it would write
    python3 tools/migrate_keybinds_v2.py --write    # write data/keybinds.default.json

This is a **one-way door and it is deliberate**. Until now the direction of travel
was Lua to JSON: ``.config/hypr/keybind.lua`` was written by hand and
``tools/extract_keybinds.py`` read it into ``data/keybinds.default.json``, so the
JSON was a report about a file. A report cannot be edited, because the next
extract overwrites the edit, which is why the Shortcuts page in the settings
application was read-only and said so on the page.

Part 5 reverses it. The record becomes the source and the Lua becomes generated,
which is the only arrangement in which rebinding a key in a settings window can
work at all: a generated file has one writer, and a hand-written file has two --
the generator and whoever has a text editor open.

So this script runs once. It reads the v1 extract, which is still the faithful
record of what the shipped Lua does, and writes the v2 record the generator
consumes. After it has run, ``keybind.lua`` stops being a source and
``extract_keybinds.py`` stops being part of the pipeline; both stay in the tree
because the v1 extract is the evidence that nothing was lost, and a test reads
that evidence rather than trusting this script.

What it changes beyond the shape
---------------------------------
Eight binds cannot work on the pinned compositor and are rewritten here rather
than carried across, because carrying them would put a known-broken line into a
generated file where it would look maintained. They reach for pre-Lua dispatcher
names through ``hyprctl dispatch``, and on a Lua config that text is evaluated as
``hl.dispatch(resizeactive 30 0)``, which is not Lua. The replacements and their
argument tables are recorded in ``data/design/keybinds.json`` under ``rejected``.

Three keys were declared in the Lua and never bound, and are listed in v1 with
the status ``reserved`` so that nothing would reassign them by accident. One of
them, ``SUPER + H``, is the shortcut overlay this part exists to build, so it
becomes a real binding here; the other two stay reserved.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "keybinds.default.json"
OUTPUT = ROOT / "data" / "keybinds.default.json"
COPYRIGHT = "Copyright (C) 2026 Safari — GPL-3.0-or-later"

#: The modifier spellings the pinned compositor accepts, read out of
#: src/keybinds/Resolver.cpp:17-20 and recorded in data/design/keybinds.json.
#: A token that is not in here is a key, not a modifier.
MODIFIERS = {
    "SHIFT", "CAPS", "CTRL", "CONTROL", "ALT", "MOD1", "MOD2", "MOD3",
    "SUPER", "WIN", "LOGO", "MOD4", "META", "MOD5",
}

#: The spelling this project writes for each modifier it uses. A person may write
#: any accepted spelling; the record carries one, so that two entries meaning the
#: same thing cannot look different in the generated file.
CANONICAL = {"CONTROL": "CTRL", "WIN": "SUPER", "LOGO": "SUPER", "MOD4": "SUPER",
             "META": "SUPER", "MOD1": "ALT"}

#: The order modifiers are written in. Fixed rather than alphabetical so that a
#: key reads the way a person says it: Super first, then Shift, then Ctrl, then Alt.
MODIFIER_ORDER = ["SUPER", "SHIFT", "CTRL", "ALT", "MOD2", "MOD3", "MOD5", "CAPS"]

# --------------------------------------------------------------------- the fixes
#
# Each of these replaces a bind that reaches for a dispatcher name the pinned
# release does not have, through a shell command, in a Lua function body. The
# replacement is a call into the verified dispatcher tree, and the argument table
# for each was read out of source; see data/design/keybinds.json -> rejected.

RESIZE_FIX = {
    # keys: (x, y) -- relative, so 30 means "30 more", not "30 wide"
    "SUPER + SHIFT + right": (30, 0),
    "SUPER + SHIFT + left": (-30, 0),
    "SUPER + SHIFT + up": (0, -30),
    "SUPER + SHIFT + down": (0, 30),
}

MOVE_SWAP_FIX = {
    # keys: (dx, dy, direction word)
    "SUPER + SHIFT + CTRL + left": (-30, 0, "left"),
    "SUPER + SHIFT + CTRL + right": (30, 0, "right"),
    "SUPER + SHIFT + CTRL + up": (0, -30, "up"),
    "SUPER + SHIFT + CTRL + down": (0, 30, "down"),
}

#: The overlay this part exists to build. Bind it to the launcher the overlay
#: ships with and mark the overlay itself unverified, rather than binding a key
#: to a window nobody has drawn: docs/UNVERIFIED.md UI-02 carries the row.
CHEATSHEET = {
    "id": "overlay.cheatsheet",
    "action": {"type": "exec", "command": ["iarch-cheatsheet"]},
    "description": "Shortcut overlay",
    "category": "System",
    "locked": True,
    "unverified": "The overlay itself is not built. Binding the key is what makes it reachable the moment it is, and iarch-keybinds check reports the missing program rather than failing silently.",
}


def split_keys(keys: str) -> Tuple[List[str], str]:
    """``'SUPER + SHIFT + right'`` -> ``(['SUPER', 'SHIFT'], 'right')``.

    Modifiers are canonicalised and put in a fixed order. The key keeps the
    spelling it was written with, because a keysym name resolves
    case-insensitively (src/keybinds/Resolver.cpp:58) and rewriting it would make
    the record disagree with the file it came from for no gain.
    """
    parts = [part.strip() for part in keys.split("+")]
    if not parts or not parts[-1]:
        raise ValueError(f"{keys!r} has no key in it")
    mods, rest = [], []
    for part in parts:
        upper = part.upper()
        (mods if upper in MODIFIERS else rest).append(upper if upper in MODIFIERS else part)
    if len(rest) != 1:
        raise ValueError(f"{keys!r} has {len(rest)} non-modifier parts: {rest}")
    mods = [CANONICAL.get(mod, mod) for mod in mods]
    if len(set(mods)) != len(mods):
        raise ValueError(f"{keys!r} repeats a modifier, which hl.bind refuses "
                         "case-insensitively (LuaBindingsToplevel.cpp:50-59)")
    mods.sort(key=lambda m: MODIFIER_ORDER.index(m) if m in MODIFIER_ORDER else 99)
    return mods, rest[0]


#: Words that carry no identity. Stripping them is what turns
#: "Move Window Across Workspaces / Move window to next workspace" into
#: ``workspaces.move-next`` instead of ``move.window.across``.
FILLER = {
    "a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "with",
    "across", "window", "windows", "workspace", "workspaces", "mode", "toggle",
    "open", "opens", "run", "runs", "launch", "launches", "start", "starts",
    "show", "shows", "hide", "management", "navigation", "layout", "switching",
    "move", "moving", "mouse", "keyboard", "shortcut", "shortcuts",
}


def slugify(category: str, description: str) -> str:
    """A stable id for a binding, as ``category.subject``.

    Built from the category and the description rather than from the keys, so
    that rebinding a key does not change the identity of the binding -- which is
    the whole point of an override file that stores differences by id. Filler
    words are dropped and the two that survive are hyphenated, so a category of
    "Move Window Across Workspaces" and a description of "Move window to next
    workspace" give ``workspaces.next`` rather than four words of noise.

    The category contributes one word and the description contributes up to two,
    because a category is a shelf and a description is the thing on it. Ids are
    not guaranteed unique by this function; the caller makes them unique with a
    numeric suffix, which is deterministic because the record's order is.
    """
    def words_of(text: str, drop_filler: bool) -> List[str]:
        out = []
        for token in text.replace("&", " ").replace("-", " ").replace("/", " ").split():
            token = "".join(ch for ch in token.lower() if ch.isalnum())
            if not token:
                continue
            if drop_filler and token in FILLER:
                continue
            if token not in out:
                out.append(token)
        return out

    shelf = words_of(category, True) or words_of(category, False)
    subject = words_of(description, True) or words_of(description, False)
    head = shelf[0] if shelf else "bind"
    tail = "-".join(subject[:2]) if subject else head
    return f"{head}.{tail}"


def action_for(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Map a v1 action onto a v2 one, applying the fixes above."""
    keys = entry["keys"]
    kind = entry["action"]["kind"]

    if keys in RESIZE_FIX:
        x, y = RESIZE_FIX[keys]
        return {"type": "dispatch",
                "dispatcher": "hl.dsp.window.resize",
                "args": {"x": x, "y": y, "relative": True}}
    if keys in MOVE_SWAP_FIX:
        dx, dy, direction = MOVE_SWAP_FIX[keys]
        return {"type": "lua",
                "lua": (
                    "function()\n"
                    "    local window = hl.get_active_window()\n"
                    "    if not window then\n"
                    "        return\n"
                    "    end\n"
                    "    if window.floating then\n"
                    f"        hl.dispatch(hl.dsp.window.move({{ x = {dx}, y = {dy}, relative = true }}))\n"
                    "    else\n"
                    f"        hl.dispatch(hl.dsp.window.swap({{ direction = \"{direction}\" }}))\n"
                    "    end\n"
                    "end"
                ),
                "why_lua": ("Asks the compositor whether the focused window is floating and "
                            "picks one of two dispatchers. The v1 bind answered the same "
                            "question by running `hyprctl activewindow -j | jq -r .floating` "
                            "through bash and grepping for the string true, which needed two "
                            "external programs to ask a yes-or-no question the Lua API "
                            "answers with a boolean field "
                            "(LuaBindingsQuery.cpp:129-138, LuaWindow.cpp:101-102).")
                }

    if kind == "exec":
        return command_action(entry["action"]["command"])
    if kind == "dispatcher":
        lua = entry["action"]["lua"]
        return {"type": "dispatch", **parse_dispatcher(lua, entry)}
    if kind == "lua-function":
        # Only the eight fixed binds were lua-function; anything else here is a
        # bind this migration does not understand, and guessing is worse than
        # stopping.
        raise ValueError(f"{keys}: a lua-function this migration has no verified "
                         f"replacement for: {entry['action']['lua'][:80]}")
    if kind == "reserved":
        return {"type": "none"}
    raise ValueError(f"{keys}: unknown action kind {kind!r}")


#: What makes a command a shell pipeline rather than an argv list. A command
#: carrying any of these is stored as ``type: shell`` with the string intact,
#: because splitting it on whitespace would produce an argv that means something
#: else entirely -- ``["grim", "-g", "$(slurp)", "-", "|", "satty"]`` is not a
#: program with six arguments, it is two programs and a pipe.
SHELL_TOKENS = ("|", "&&", "||", ">", "<", "$(", "${", ";", "`")


def command_action(command: str) -> Dict[str, Any]:
    """Decide between an argv list and a shell string, and say which it chose.

    This is the decision the whole ``exec`` / ``shell`` split exists to make
    visible. Upstream spawns one string through ``/bin/sh -c`` whatever the
    record says (data/design/keybinds.json -> exec), so the split is not about
    what the compositor receives; it is about what a person edits and what a
    validator can check. An argv list cannot carry a quoting mistake and can be
    checked argument by argument. A pipeline cannot be checked at all, so it is
    marked ``shell`` and the settings page marks it advanced.
    """
    import shlex
    if any(token in command for token in SHELL_TOKENS):
        return {"type": "shell", "script": command,
                "why_shell": "A pipeline or a substitution, so it is one string by "
                             "necessity and not by choice."}
    try:
        parts = shlex.split(command)
    except ValueError as error:
        return {"type": "shell", "script": command,
                "why_shell": f"Not splittable as an argv list: {error}"}
    if not parts:
        raise ValueError(f"empty command: {command!r}")
    return {"type": "exec", "command": parts}


def parse_dispatcher(lua: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """``hl.dsp.focus({ workspace = i })`` -> dispatcher plus its argument table."""
    import re
    match = re.match(r"^(hl\.dsp\.[a-z_.]+)\((.*)\)$", lua.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"{entry['keys']}: not a dispatcher call: {lua[:60]}")
    name, inner = match.group(1), match.group(2).strip()
    if "workspace" in entry["action"]:
        return {"dispatcher": name, "workspace": entry["action"]["workspace"]}
    if not inner:
        return {"dispatcher": name}
    return {"dispatcher": name, "args_lua": inner}


def migrate(v1: Dict[str, Any]) -> Dict[str, Any]:
    seen: Dict[str, int] = {}
    bindings: List[Dict[str, Any]] = []

    for entry in v1["bindings"]:
        keys = entry["keys"]
        if keys == "SUPER + H":
            record = dict(CHEATSHEET)
            mods, key = split_keys(keys)
            record.update({"mods": mods, "key": key, "enabled": True})
            bindings.append(record)
            continue

        mods, key = split_keys(keys)
        slug = slugify(entry["category"], entry["description"])
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 1

        options = entry.get("options") or {}
        record: Dict[str, Any] = {
            "id": slug,
            "mods": mods,
            "key": key,
            "action": action_for(entry),
            "description": entry["description"],
            "category": entry["category"],
            "enabled": entry["status"] == "bound",
            "locked": bool(options.get("locked")),
        }
        if options.get("mouse"):
            record["flags"] = {"mouse": True}
        if entry["status"] == "reserved":
            record["reserved"] = True
        bindings.append(record)

    return {
        "_copyright": COPYRIGHT,
        "_note": (
            "The keyboard map this session ships, and the single source of it. "
            "iarch-keybinds renders .config/hypr/generated/keybinds.lua from this "
            "file plus the differences a person has saved in "
            "~/.config/iarch/keybinds.json, so a bind is written here or in that "
            "file and nowhere else. Until Part 5 the direction was the other way "
            "round -- tools/extract_keybinds.py read this record out of "
            ".config/hypr/keybind.lua -- and the reversal is the point: a report "
            "about a file cannot be edited, because the next extract overwrites "
            "the edit, which is why the Shortcuts page was read-only. Every "
            "spelling a bind here may use is recorded in data/design/keybinds.json "
            "against the pinned compositor, and iarch-keybinds check validates "
            "this file against that record rather than against an assumption."
        ),
        "version": 2,
        "migrated_from": {
            "version": 1,
            "by": "tools/migrate_keybinds_v2.py",
            "source": "the v1 extract of .config/hypr/keybind.lua, kept in git history",
            "bindings": len(v1["bindings"]),
            "rewritten": sorted(key.lower()
                                for key in list(RESIZE_FIX) + list(MOVE_SWAP_FIX)),
            "rewritten_note": (
                "Written in the lower-case spelling the v1 record used for the key "
                "part of a combination -- it spelled modifiers upper-case and some "
                "keys lower-case, so `SUPER + SHIFT + right` and `SUPER + tab` sat "
                "side by side. A key name resolves case-insensitively "
                "(src/keybinds/Resolver.cpp:58), so both spellings bind the same "
                "key; the record normalises on one rather than carrying two."
            ),
            "why_rewritten": (
                "Each reached for a pre-Lua dispatcher name through `hyprctl "
                "dispatch`, which on a Lua config is evaluated as "
                "`hl.dispatch(resizeactive 30 0)` and is not Lua. The replacements "
                "and their argument tables are in data/design/keybinds.json."
            ),
            "bound_here": ["SUPER + H"],
            "why_bound_here": (
                "SUPER + H, SUPER + SHIFT + H and SUPER + K were declared in the "
                "Lua and never bound, and v1 carried them with the status reserved "
                "so nothing would reassign them by accident. SUPER + H is the "
                "shortcut overlay this part exists to build, so it is bound; the "
                "other two stay reserved."
            ),
        },
        "bindings": bindings,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true",
                        help="write the v2 record over data/keybinds.default.json")
    args = parser.parse_args(argv)

    v1 = json.loads(SOURCE.read_text(encoding="utf-8"))
    if v1.get("version") != 1:
        # Named rather than made relative to the repo root: a refusal is a message
        # a person has to be able to read, and relative_to() raises on a path
        # outside the tree, which is exactly where a test points this.
        print(f"{SOURCE} is already version {v1.get('version')}; "
              "this migration runs once and only from v1", file=sys.stderr)
        return 1

    v2 = migrate(v1)
    text = json.dumps(v2, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        OUTPUT.write_text(text, encoding="utf-8")
        bound = sum(1 for b in v2["bindings"] if b["enabled"])
        print(f"wrote {OUTPUT.relative_to(ROOT)}: version 2, {len(v2['bindings'])} "
              f"entries, {bound} enabled")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
