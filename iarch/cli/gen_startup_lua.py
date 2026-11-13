#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the compositor's startup module from a record of what it may do.

``.config/hypr/startup.lua`` is the one file in the payload that runs programs.
Everything else this repository renders describes how the session looks; this one
decides what is running in it, and a mistake here is quiet in a way a mistake in
a decoration is not: the executor forks ``/bin/sh -c`` with the child's stdout and
stderr redirected to ``/dev/null`` (``Executor.cpp:198-205`` in Hyprland v0.57.2),
so a command that fails leaves nothing behind, and a command that was never
needed looks exactly like one that worked.

So the file is rendered from ``data/design/startup.json``, which carries the
reason beside every variable and every command, the three bindings a startup
module is allowed to use, and the event names ``hl.on`` accepts. What this module
adds on top of that record is refusal:

* an event name outside the recorded list is refused here rather than discovered
  as a config error at login. Hyprland does refuse it too -- ``hl.on`` answers
  with a message listing every known event (``LuaBindingsToplevel.cpp:355-364``)
  -- but it refuses the whole configuration, and the person who sees that is the
  one logging in, not the one editing;
* a command that begins with ``[`` is refused, because ``spawnWithRules`` parses a
  leading ``[rule]`` prefix out of the string
  (``Executor.cpp:101-114``) and would spawn something else;
* a repeated environment variable is refused, since the second ``hl.env`` would
  silently win and the record would no longer say which one did;
* the two lines both installers rewrite with ``sed`` are checked *after* the
  render, in the rendered text: ``local enable_nvidia_optional = false`` has to be
  a whole line on its own (``install.sh:1047-1049``,
  ``fedora_install.sh:845-847``), and the polkit agent command has to appear on
  exactly one line, because Fedora's rewrite replaces every line containing it
  with a quoted table entry (``fedora_install.sh:834``). A comment naming the
  agent would be replaced too, and the result would not parse.

Two things the hand-written file did that this render does not, both recorded:

* the environment variables are exported with ``hl.env``'s own third argument
  rather than by two shell commands kept in a list beside the NVIDIA variables.
  Upstream builds ``systemctl --user import-environment`` and
  ``dbus-update-activation-environment`` itself and queues them as an exec-once on
  the first parse (``LuaBindingsConfigRules.cpp:531-541``), which is the same work
  the v4 file did by hand (``legacy/config/hypr/startup.conf:20-21``) -- and in the
  v5 file it was gated behind an NVIDIA flag, so a default install never ran it.
  ``WAYLAND_DISPLAY`` still has to be a command: the compositor sets it in each
  spawned child (``Executor.cpp:194``), never in its own environment at parse time,
  so there is no value for ``hl.env`` to export;
* nothing reloads the compositor at startup. The v4 session carried
  ``exec-once = hyprctl reload &`` and the first v5 file kept it as a shell-out two
  seconds after ``hyprland.start``. The configuration is parsed completely before
  that event is dispatched, so there was nothing left to pick up, and the reload
  was not free: it re-registers every bind and window rule and discards runtime
  state no file records -- a focus mode switched on at login would have its dim
  undone two seconds later, because the generated ``glass.lua`` carries the
  intensity's own ``decoration:dim_inactive``.

Usage:
    python3 iarch/cli/gen_startup_lua.py                     # write into the config dir
    python3 iarch/cli/gen_startup_lua.py --print             # the render, to stdout
    python3 iarch/cli/gen_startup_lua.py --write-repo-default  # refresh the shipped payload
    python3 iarch/cli/gen_startup_lua.py --check             # shipped payload matches a render
    python3 iarch/cli/gen_startup_lua.py --output ~/.config/hypr/startup.lua  # the live session
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

RECORD_PATH = ROOT / "data" / "design" / "startup.json"
REPO_DEFAULT = ROOT / ".config" / "hypr" / "startup.lua"
MODULE_NAME = "startup"

# Where a reader goes for the reason behind a line. The render is deliberately
# short: a startup file is read at 07:00 by somebody whose session did not come
# up, and the record is where the explanation lives.
RECORD_LABEL = "data/design/startup.json"

COMMENT_WIDTH = 88


class StartupError(RuntimeError):
    """Raised when the record, or what rendering it would produce, cannot be trusted."""


# ------------------------------------------------------------------ inputs


def load_record(path: Path = RECORD_PATH) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StartupError(f"{label(path)}: {exc}") from exc


def label(path: Path) -> str:
    """A path for a message: repository-relative when it is inside the repository."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


# ------------------------------------------------------------------ refusals


def check_record(record: Dict[str, Any]) -> None:
    """Refuse a record that would render a module Hyprland or an installer chokes on.

    Every check here is one Hyprland cannot make for us at parse time, or one it
    makes by refusing the entire configuration at login -- which is the wrong
    place and the wrong time to find out.
    """
    problems: List[str] = []

    known = set(record["events"]["known"])
    for event in record["events"]["used"]:
        if event not in known:
            problems.append(
                f"hl.on({event!r}) is not in the recorded event list; Hyprland "
                f"{record['verified_against']} would refuse the whole config and list "
                f"the {len(known)} names it does know")

    seen: Dict[str, str] = {}
    groups = [("the session environment", record["env"])]
    groups += [(f"the {group['name']} group", group["env"])
               for group in record["optional_groups"]]
    for where, entries in groups:
        for entry in entries:
            name = entry["name"]
            if name in seen:
                problems.append(f"{name} is exported twice ({seen[name]} and {where}); "
                                f"the second hl.env would win and the record would not "
                                f"say so")
            seen[name] = where

    for entry in record["exec_once"]:
        command = entry["command"]
        if not command.strip():
            problems.append("an exec_once entry is empty; hl.exec_cmd refuses one "
                            "with a config error")
        if command.startswith("["):
            problems.append(
                f"exec_once {command[:40]!r} starts with '[': spawnWithRules parses a "
                f"leading [rule] prefix out of the string (Executor.cpp:101-114) and "
                f"would spawn something else")
        if "\n" in command:
            problems.append(f"exec_once {command[:40]!r} contains a newline, which the "
                            f"executor would pass to /bin/sh as two commands")

    for group in record["optional_groups"]:
        if group["enabled_by_default"]:
            problems.append(
                f"the {group['name']} group is recorded as enabled by default; an "
                f"optional group is optional, and the installers flip the flag")

    if problems:
        raise StartupError("; ".join(problems))


def check_anchors(record: Dict[str, Any], text: str) -> None:
    """Prove, in the rendered text, that both installers can still rewrite it.

    This runs after the render rather than on the record because the constraint is
    on the file the installers sed, not on the data: a renderer that restructured
    the module -- a table of commands turned into calls, a reason quoted in a
    comment -- would leave the record valid and the installers broken. Fedora's
    rewrite is the sharp one: ``sed -i '/polkit-gnome-authentication-agent-1/c\\…'``
    replaces *every* line containing that string with a quoted table entry, so a
    second mention anywhere, comment included, produces a file that does not parse.
    """
    lines = text.splitlines()
    problems: List[str] = []
    for anchor in record["installer_anchors"]:
        needle = anchor["anchor"]
        if anchor["whole_line"]:
            hits = [number for number, line in enumerate(lines, 1) if line == needle]
            kind = "as a whole line"
        else:
            hits = [number for number, line in enumerate(lines, 1) if needle in line]
            kind = "on any line containing it"
        if len(hits) != 1:
            problems.append(
                f"{anchor['file']}:{anchor['lines']} rewrites {needle!r} {kind}, and the "
                f"render carries it {len(hits)} times"
                + (f" (lines {hits})" if hits else "")
                + f"; {anchor['why']}")
    if problems:
        raise StartupError("; ".join(problems))


# ------------------------------------------------------------------ render


def lua_string(value: str) -> str:
    """A Lua string literal: double-quoted, with the characters that would end it escaped."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{escaped}"'


def env_call(entry: Dict[str, Any]) -> str:
    """One hl.env call. The third argument is only passed when the record asks for it.

    ``hl.env`` treats a missing third argument as false (``lua_isnoneornil`` at
    ``LuaBindingsConfigRules.cpp:521``), so an explicit ``false`` would be a value
    that only restates what the binding already does.
    """
    call = f"hl.env({lua_string(entry['name'])}, {lua_string(entry['value'])}"
    if entry.get("dbus"):
        call += ", true"
    return call + ")"


def comment(text: str, indent: str = "", prefix: str = "-- ") -> List[str]:
    """Wrap prose into comment lines, so a derived sentence stays readable."""
    wrapped = textwrap.wrap(text, width=COMMENT_WIDTH - len(indent),
                            initial_indent=indent + prefix,
                            subsequent_indent=indent + prefix)
    return wrapped or [indent + prefix.rstrip()]


def render(record: Dict[str, Any]) -> str:
    """The module body, without the GENERATED header ``write_generated`` puts on top."""
    check_record(record)
    version = record["verified_against"]
    entry_point = record["entry_point"]
    executor = record["executor"]

    out: List[str] = []
    out += comment(f"Source: {RECORD_LABEL}, verified against Hyprland {version}. "
                   f"Required by {entry_point['required_by'].split(':')[0]}; every variable "
                   f"and every command below has a reason recorded there, and nothing is "
                   f"emitted that is not.")
    out += comment("Edit the record, then run python3 iarch/cli/gen_startup_lua.py "
                   "--write-repo-default.")
    out.append("")

    out += comment("Session environment, exported at parse time. hl.env's third argument "
                   "is upstream's own export into the systemd user environment and the "
                   "dbus activation environment, queued as an exec-once on the first "
                   "parse (LuaBindingsConfigRules.cpp:531-541).")
    for entry in record["env"]:
        out.append(env_call(entry))
    out.append("")

    out += comment(f"Commands the session starts once, when the compositor reports "
                   f"{record['events']['used'][0]}. Each runs as {executor['shell']} in a "
                   f"forked child with its output discarded (Executor.cpp:173-213), so "
                   f"shell operators work and a failure is invisible: "
                   f"scripts/iarch-healthcheck.sh is what reports a service that did not "
                   f"come up.")
    out.append("local exec_once = {")
    for entry in record["exec_once"]:
        if entry.get("provenance") or entry.get("note"):
            out += comment(entry.get("note") or entry["provenance"], indent="    ")
        out.append(f"    {lua_string(entry['command'])},")
    out.append("}")
    out.append("")

    for group in record["optional_groups"]:
        flippers = " and ".join(group["installer_flips_the_flag"])
        out += comment(f"Optional {group['name']} environment, off unless an installer was "
                       f"asked for it: {flippers} flip the next line, and nothing else may.")
        out.append(f"local {group['flag']} = "
                   f"{'true' if group['enabled_by_default'] else 'false'}")
        out.append("")
        out.append(f"if {group['flag']} then")
        for entry in group["env"]:
            out.append("    " + env_call(entry))
        out.append("end")
        out.append("")

    out.append(f"hl.on({lua_string(record['events']['used'][0])}, function()")
    out.append("    for _, cmd in ipairs(exec_once) do")
    out.append("        hl.exec_cmd(cmd)")
    out.append("    end")
    out.append("end)")
    out.append("")

    for removed in record["removed"]:
        legacy = removed["legacy"].split(" ")[0]
        out += comment(f"Removed: {removed['what']} ({legacy}). The reason, and what it "
                       f"cost, is in {RECORD_LABEL} under removed.")
    out.append("")
    out.append("return true")

    text = "\n".join(out) + "\n"
    check_anchors(record, text)
    return text.rstrip("\n")


# ------------------------------------------------------------------ targets


def target_path(env: Optional[Dict[str, str]] = None) -> Path:
    return configstore.config_dir(env) / "hypr" / f"{MODULE_NAME}.lua"


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated will put on disk for ``body``.

    Kept as one expression so --check cannot drift from the write path: the two
    must disagree only when the render changed, never because one of them forgot a
    header or a newline.
    """
    return f"{configstore.header_for(path)}\n{body}\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="gen-startup-lua",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--record", type=Path, default=RECORD_PATH,
                        help=f"the startup record (default {label(RECORD_PATH)})")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the render to stdout instead of a file")
    parser.add_argument("--write-repo-default", action="store_true",
                        help=f"refresh {label(REPO_DEFAULT)}")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed default matches a fresh render")
    parser.add_argument("--output", type=Path,
                        help="explicit destination (overrides the config dir); "
                             "~/.config/hypr/startup.lua is the live session")
    args = parser.parse_args(argv)

    try:
        record = load_record(args.record)
        source = render(record)
    except StartupError as exc:
        print(f"startup-lua: {exc}", file=sys.stderr)
        return 2

    if args.to_stdout:
        sys.stdout.write(rendered_text(REPO_DEFAULT, source))
        return 0

    if args.check:
        if not REPO_DEFAULT.is_file():
            print(f"startup-lua: {label(REPO_DEFAULT)} is missing", file=sys.stderr)
            return 1
        current = REPO_DEFAULT.read_text(encoding="utf-8")
        expected = rendered_text(REPO_DEFAULT, source)
        if current != expected:
            print("startup-lua: the committed default does not match a fresh render of "
                  f"{label(args.record)}; run --write-repo-default", file=sys.stderr)
            return 1
        print(f"startup-lua: {label(REPO_DEFAULT)} matches a fresh render")
        return 0

    destination = args.output or (REPO_DEFAULT if args.write_repo_default else target_path())
    try:
        written = configstore.write_generated(destination, source)
    except (OSError, configstore.ConfigError) as exc:
        print(f"startup-lua: {exc}", file=sys.stderr)
        return 1
    print(f"startup-lua: wrote {written} ({len(record['env'])} variables, "
          f"{len(record['exec_once'])} commands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
