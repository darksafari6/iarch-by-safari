#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Set one boolean in one table of a TOML file, and change nothing else.

`install.sh` deploys a configuration file this repository renders, and then one
step of the run needs to turn a single switch on in the deployed copy: DDC/CI
monitor brightness, which is a per-machine choice rather than a profile, so the
shipped file does not carry it. The key is Noctalia's own, read at v5.4.1 out of
`src/config/schema/config_sections.cpp:61` (`makeSection("brightness", ...)`) and
`src/config/schema/config_schema.cpp:488` (`field(&BrightnessConfig::enableDdcutil,
"enable_ddcutil")`), whose type is `bool enableDdcutil = false` at
`src/config/config_types.h:1594`.

Why this is a tool and not a `sed -i`:

* Python's `tomllib` reads TOML and cannot write it, so the obvious library is
  only half of the job. Rewriting a file by parsing it loses every comment, and
  the file this one edits is generated with a comment above most of its keys.
* `sed` cannot tell which table a key is in. `[brightness] minimum_brightness`
  and a `[lockscreen] minimum_brightness` are different keys to a person and the
  same string to a pattern, and an installer that edits the wrong one reports
  success.

So this works on lines, inside one table, and refuses rather than guesses:

* a table that appears twice, or a key that appears twice inside it, is a file
  this tool does not understand well enough to edit;
* an existing value that is not `true` or `false` is somebody else's decision,
  and overwriting a string or a number with a boolean is not a flag change;
* anything it cannot find, it appends or inserts rather than rewrites, so the
  rest of the file survives byte for byte.

Exit status: 0 when the file now says what was asked (including when it already
did, which is why a second run changes nothing), 1 on a refusal, 2 on a usage
error. `--check` never writes: it exits 0 when the file already carries the
value, 1 when it does not, and 2 when the question cannot be answered at all.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple


class Refusal(Exception):
    """A file this tool will not edit, with the reason."""


def table_bounds(lines: List[str], table: str) -> Tuple[int, int]:
    """The half-open line range of a top-level table's body, and its header index.

    A subtable header such as ``[brightness.monitor.dell]`` does not match
    ``brightness``: the brackets have to close immediately after the name.
    """
    header = re.compile(r"^\[" + re.escape(table) + r"\]\s*(#.*)?$")
    found = [index for index, line in enumerate(lines) if header.match(line)]
    if len(found) > 1:
        raise Refusal(f"[{table}] appears {len(found)} times, at lines "
                      f"{' and '.join(str(i + 1) for i in found)}, so there is no "
                      f"single place to put a key")
    if not found:
        raise KeyError(table)
    start = found[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("["):
            end = index
            break
    return start, end


def key_line(lines: List[str], start: int, end: int, key: str) -> Optional[int]:
    pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
    found = [index for index in range(start + 1, end) if pattern.match(lines[index])]
    if len(found) > 1:
        raise Refusal(f"{key} appears {len(found)} times inside [{lines[start].strip()}] "
                      f"(lines {' and '.join(str(i + 1) for i in found)}), which is not a "
                      f"file this tool will edit")
    return found[0] if found else None


def boolean_of(line: str, key: str) -> bool:
    _, _, rest = line.partition("=")
    value = rest.split("#", 1)[0].strip()
    if value == "true":
        return True
    if value == "false":
        return False
    raise Refusal(f"{key} is already in that table as {value!r}, which is not a boolean; "
                  f"turning somebody else's value into a flag is not this tool's decision")


def indent_of(lines: List[str], start: int, end: int) -> str:
    """The indentation the table's own keys use, so a new key matches its siblings."""
    for index in range(start + 1, end):
        line = lines[index]
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            return line[:len(line) - len(line.lstrip())]
    return ""


def set_flag(text: str, table: str, key: str, value: bool) -> Tuple[str, str]:
    """The edited text and what happened: ``unchanged``, ``replaced``, ``inserted``,
    ``appended``. Everything but the one line is copied through untouched."""
    lines = text.split("\n")
    wanted = "true" if value else "false"
    try:
        start, end = table_bounds(lines, table)
    except KeyError:
        block = [f"[{table}]", f"{key} = {wanted}"]
        body = [line for line in lines]
        while body and not body[-1].strip():
            body.pop()
        if not body:
            return "\n".join(block) + "\n", "appended"
        # Keep the blank line between tables that the rest of the file uses.
        return "\n".join(body + [""] + block) + "\n", "appended"

    index = key_line(lines, start, end, key)
    if index is not None:
        if boolean_of(lines[index], key) is value:
            return text, "unchanged"
        before, _, rest = lines[index].partition("=")
        comment = ""
        if "#" in rest:
            comment = "  #" + rest.split("#", 1)[1]
        lines[index] = f"{before}= {wanted}{comment}"
        return "\n".join(lines), "replaced"

    indent = indent_of(lines, start, end)
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, f"{indent}{key} = {wanted}")
    return "\n".join(lines), "inserted"


def has_flag(text: str, table: str, key: str, value: bool) -> bool:
    lines = text.split("\n")
    try:
        start, end = table_bounds(lines, table)
    except KeyError:
        return False
    index = key_line(lines, start, end, key)
    return index is not None and boolean_of(lines[index], key) is value


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", help="the TOML file to edit")
    parser.add_argument("table", help="a top-level table name, without brackets")
    parser.add_argument("key", help="the boolean key inside that table")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--true", dest="value", action="store_true", default=True,
                       help="the value to set (the default)")
    group.add_argument("--false", dest="value", action="store_false",
                       help="set the key to false instead")
    parser.add_argument("--check", action="store_true",
                        help="report whether the file already carries the value; never writes")
    args = parser.parse_args(argv)

    path = Path(args.file)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"toml-set-flag: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    try:
        if args.check:
            if has_flag(text, args.table, args.key, args.value):
                print(f"toml-set-flag: {path} already carries [{args.table}] "
                      f"{args.key} = {'true' if args.value else 'false'}")
                return 0
            print(f"toml-set-flag: {path} does not carry [{args.table}] "
                  f"{args.key} = {'true' if args.value else 'false'}", file=sys.stderr)
            return 1
        edited, what = set_flag(text, args.table, args.key, args.value)
    except Refusal as exc:
        print(f"toml-set-flag: refused: {exc}", file=sys.stderr)
        return 1

    if what == "unchanged":
        print(f"toml-set-flag: {path} already carries [{args.table}] {args.key} = "
              f"{'true' if args.value else 'false'}; nothing written")
        return 0
    try:
        path.write_text(edited, encoding="utf-8")
    except OSError as exc:
        print(f"toml-set-flag: cannot write {path}: {exc}", file=sys.stderr)
        return 1
    print(f"toml-set-flag: {path} [{args.table}] {args.key} = "
          f"{'true' if args.value else 'false'} ({what})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
