#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the compositor's monitor module from a record of what it accepts.

``.config/hypr/monitors.lua`` is the one payload where a mistake can leave a
person with no readable display. A decoration that is wrong is ugly; a scale that
is wrong is a screen full of pixels too small to read, and a monitor that is
disabled is a screen with nothing on it at all -- and in both cases the dialog
that offers to undo the change is being drawn on the display that stopped
working. So this generator refuses more than the compositor does, and refuses
earlier:

* a field the pinned release does not have. ``hl.monitor`` answers an unknown key
  with ``hl.monitor: unknown field '<key>'``
  (``src/config/lua/bindings/LuaBindingsConfigRules.cpp:1118-1122`` in v0.57.2),
  which is a config error the person logging in sees rather than the person
  editing. ``data/design/monitors.json`` is the closed field list, and a key that
  is not in it -- or is in it but marked as one this project refuses to write --
  is refused here;
* a mode nobody listed. A resolution string is only accepted when it is one of
  the spellings ``parseMode`` recognises
  (``src/config/shared/monitor/Parser.cpp:112-145``). The Display page goes
  further and only offers modes it read out of ``hyprctl -j monitors`` ->
  ``availableModes``, because a mode the compositor listed is a mode the
  compositor can drive and one typed by hand is a guess;
* a scale below 0.25, which ``parseScale`` refuses and resets to 1
  (``Parser.cpp:205-208``). Resetting to 1 silently is the wrong outcome for a
  person who asked for a fraction, so it is an error here;
* a scale written as a number. ``MONITOR_FIELDS`` builds this field with
  ``CLuaConfigString`` (``LuaBindingsConfigRules.cpp:86``), so ``scale = 1`` is a
  parse error, not a scale of one. The render always quotes it;
* disabling the last enabled monitor. There is no dialog to undo that one, so it
  is not offered;
* two entries for one output. ``hl.monitor`` merges into an existing rule for the
  same output (``LuaBindingsConfigRules.cpp:1098-1100``), so the second would win
  field by field and the file would no longer say which value is live.

What it does not do is read the hardware. Everything here comes from the user's
own ``display.monitors`` list in ``~/.config/iarch/settings.json``; the page that
fills that list is the one that asks the compositor what is plugged in. An empty
list renders the identity rule -- an empty ``output`` matches every output -- so a
machine with no saved monitor state behaves exactly as a fresh install does.

Usage:
    python3 iarch/cli/gen_monitors_lua.py                      # write into the config dir
    python3 iarch/cli/gen_monitors_lua.py --print              # the render, to stdout
    python3 iarch/cli/gen_monitors_lua.py --write-repo-default # refresh the shipped payload
    python3 iarch/cli/gen_monitors_lua.py --check              # shipped payload matches a render
    python3 iarch/cli/gen_monitors_lua.py --monitors-json f.json  # an explicit list, for tests

--check and --write-repo-default always render from data/settings.default.json, never from
~/.config/iarch/settings.json, so the committed payload does not depend on whose machine
generated it. A plain run renders from the user's own display.monitors.
    python3 iarch/cli/gen_monitors_lua.py --output ~/.config/hypr/monitors.lua
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

RECORD_PATH = ROOT / "data" / "design" / "monitors.json"
REPO_DEFAULT = ROOT / ".config" / "hypr" / "monitors.lua"
MODULE_NAME = "monitors"
RECORD_LABEL = "data/design/monitors.json"

COMMENT_WIDTH = 88

#: The identity rule: an empty output name matches every output, which is what a
#: fresh install needs, because nobody has looked at its hardware yet.
IDENTITY_RULE = {"output": "", "mode": "preferred", "position": "auto", "scale": "1"}

#: The fields this generator will emit, in the order it emits them. A field in the
#: record that is not marked written_by_this_project is refused below, so this list
#: is only about order and about which ones are always written.
FIELD_ORDER = ("output", "mode", "position", "scale", "transform", "disabled")

MODE_PREFIXES = ("pref", "highrr", "highres", "maxwidth")
AUTO_POSITIONS = ("auto", "auto-right", "auto-left", "auto-up", "auto-down",
                  "auto-center-right", "auto-center-left", "auto-center-up",
                  "auto-center-down")
# The optional Hz suffix is there because availableModes prints `WxH@RR.RRHz`
# (src/ipc/s1/Commands.cpp:112-125) and parseMode reads the refresh rate with stof,
# which stops at the first character that is not part of a number. A mode copied out
# of the compositor's own answer therefore has to be accepted verbatim.
_RESOLUTION = re.compile(r"^[0-9]{1,5}x[0-9]{1,5}(@[0-9]{1,6}(\.[0-9]{1,3})?(Hz)?)?$")
_OFFSET = re.compile(r"^-?[0-9]{1,6}x-?[0-9]{1,6}$")
_SCALE = re.compile(r"^[0-9]{1,3}(\.[0-9]{1,3})?$")
MINIMUM_SCALE = 0.25


class MonitorsError(RuntimeError):
    """Raised when the record, the settings, or the render cannot be trusted."""


def label(path: Path) -> str:
    """A path for a message: repository-relative when it is inside the repository."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def load_record(path: Path = RECORD_PATH) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitorsError(f"{label(path)}: {exc}") from exc


# ------------------------------------------------------------------ the record


def writable_fields(record: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The record's write fields this project is allowed to emit, by name."""
    allowed = {}
    for field in record["write"]["fields"]:
        if field["written_by_this_project"]:
            allowed[field["name"]] = field
    if not allowed:
        raise MonitorsError(f"{RECORD_LABEL} marks no field as written_by_this_project, "
                            "so there is nothing this generator may emit")
    return allowed


def refused_names(record: Dict[str, Any]) -> List[str]:
    """Every field the record lists but this project refuses to write."""
    return [field["name"] for field in record["write"]["fields"]
            if not field["written_by_this_project"]]


# ------------------------------------------------------------------ validation


def check_mode(value: Any, where: str, problems: List[str]) -> None:
    if not isinstance(value, str):
        problems.append(f"{where}: mode must be a string, not {type(value).__name__}")
        return
    if value == "" or value.startswith(MODE_PREFIXES):
        return
    if _RESOLUTION.match(value):
        return
    problems.append(
        f"{where}: mode {value!r} is not a spelling parseMode accepts "
        "(the empty string, pref*, highrr*, highres, maxwidth, or WxH[@RR.RRHz]); "
        "src/config/shared/monitor/Parser.cpp:126-141 refuses one with no 'x' in it")


def check_position(value: Any, where: str, problems: List[str]) -> None:
    if not isinstance(value, str):
        problems.append(f"{where}: position must be a string, not {type(value).__name__}")
        return
    if value == "" or value in AUTO_POSITIONS:
        return
    if _OFFSET.match(value):
        return
    problems.append(
        f"{where}: position {value!r} is not one of {', '.join(AUTO_POSITIONS)} or an "
        "XxY offset; Parser.cpp:167-179 refuses both an unlisted auto-* spelling and an "
        "offset with no 'x'")


def check_scale(value: Any, where: str, problems: List[str]) -> None:
    if not isinstance(value, str):
        problems.append(
            f"{where}: scale must be a string, not {type(value).__name__} -- "
            "MONITOR_FIELDS builds the field with CLuaConfigString "
            "(src/config/lua/bindings/LuaBindingsConfigRules.cpp:86), so an unquoted "
            "number is a parse error rather than a scale")
        return
    if value == "" or value.startswith("auto"):
        return
    if not _SCALE.match(value):
        problems.append(f"{where}: scale {value!r} is not 'auto' or a number")
        return
    if float(value) < MINIMUM_SCALE:
        problems.append(
            f"{where}: scale {value!r} is below {MINIMUM_SCALE}, which parseScale refuses "
            "and resets to 1 (src/config/shared/monitor/Parser.cpp:205-208); silently "
            "becoming 1 is not what was asked for, so this generator refuses it instead")


def check_entry(entry: Any, index: int, allowed: Dict[str, Dict[str, Any]],
                problems: List[str]) -> None:
    """One monitor entry against the record. Appends every problem it finds."""
    where = f"display.monitors[{index}]"
    if not isinstance(entry, dict):
        problems.append(f"{where} is {type(entry).__name__}, not an object")
        return

    for key in sorted(entry):
        if key not in allowed:
            problems.append(
                f"{where} names {key!r}, which {RECORD_LABEL} does not mark as "
                f"written_by_this_project; hl.monitor answers an unknown field with a "
                f"config error (LuaBindingsConfigRules.cpp:1118-1122)")

    output = entry.get("output")
    if not isinstance(output, str) or not output:
        problems.append(f"{where}: output is required and must be a non-empty string "
                        "(LuaBindingsConfigRules.cpp:1088-1092)")

    if "mode" in entry:
        check_mode(entry["mode"], where, problems)
    if "position" in entry:
        check_position(entry["position"], where, problems)
    if "scale" in entry:
        check_scale(entry["scale"], where, problems)

    if "transform" in entry:
        field = allowed.get("transform", {})
        value = entry["transform"]
        low, high = field.get("minimum", 0), field.get("maximum", 7)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            problems.append(f"{where}: transform must be an integer in {low}..{high}, "
                            f"got {value!r}")
    if "disabled" in entry and not isinstance(entry["disabled"], bool):
        problems.append(f"{where}: disabled must be a boolean, got "
                        f"{entry['disabled']!r}")


def check_list(entries: Sequence[Any], allowed: Dict[str, Dict[str, Any]]) -> List[str]:
    """Every refusal this generator makes before it renders anything."""
    problems: List[str] = []
    for index, entry in enumerate(entries):
        check_entry(entry, index, allowed, problems)
    if problems:
        return problems

    seen: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        output = entry["output"]
        if output in seen:
            problems.append(
                f"display.monitors[{seen[output]}] and [{index}] both configure {output!r}; "
                "hl.monitor merges a second rule for one output into the first "
                "(LuaBindingsConfigRules.cpp:1098-1100), so the file would no longer say "
                "which value is live")
        seen[output] = index

    if entries and all(entry.get("disabled") for entry in entries):
        problems.append(
            "every entry in display.monitors is disabled, which would leave the session "
            "with no output at all; the dialog that offers to undo that is drawn on a "
            "display that is switched off")
    return problems


# ------------------------------------------------------------------ the render


def lua_string(value: str) -> str:
    """A Lua double-quoted string. The output name is the only free text here."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = "".join(ch if ch >= " " and ch != "\x7f" else f"\\{ord(ch):03d}"
                      for ch in escaped)
    return f'"{escaped}"'


def lua_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return lua_string(str(value))


def comment(text: str, indent: str = "") -> List[str]:
    import textwrap

    # break_on_hyphens off: a command line flag such as --write-repo-default must not be
    # split across two comment lines, because the reader is meant to be able to copy it.
    lines = textwrap.wrap(" ".join(text.split()), width=COMMENT_WIDTH - len(indent) - 3,
                          break_on_hyphens=False)
    return [f"{indent}-- {line}" for line in lines] or [f"{indent}--"]


def render_call(entry: Dict[str, Any]) -> List[str]:
    """One hl.monitor call, fields in FIELD_ORDER, strings quoted."""
    out = ["hl.monitor({"]
    for name in FIELD_ORDER:
        if name not in entry:
            continue
        value = entry[name]
        out.append(f"    {name} = {lua_scalar(value)},")
    out.append("})")
    return out


def header_lines(record: Dict[str, Any], count: int) -> List[str]:
    release = record["verified_against"]
    lines = comment(
        f"Source: {RECORD_LABEL}, verified against Hyprland {release}. Required by "
        f".config/hypr/hyprland.lua; a field, a spelling or a bound that record does not "
        f"carry is refused by the generator rather than emitted for the compositor to "
        f"answer with a config error at login.")
    if count:
        lines += comment(
            f"{count} monitor{'s' if count != 1 else ''} configured in "
            f"display.monitors. Fields this project refuses to write -- colour management, "
            f"HDR, luminance, mirroring and the reserved area -- are listed in that record "
            f"under refused_by_this_project, with the reason for each.")
    else:
        lines += comment(
            "No monitor is configured, so this is the identity rule: an empty output name "
            "matches every output, the preferred mode, an automatic position and a scale of "
            "one. A machine with nothing saved behaves exactly as a fresh install does.")
    lines += comment(
        "Edit display.monitors in ~/.config/iarch/settings.json -- the Display page in "
        "iArch Settings writes it -- then run python3 iarch/cli/gen_monitors_lua.py "
        "--write-repo-default to refresh the shipped payload, or without that flag to write "
        "the live session.")
    return lines


def render(entries: Sequence[Dict[str, Any]], record: Dict[str, Any]) -> str:
    allowed = writable_fields(record)
    problems = check_list(entries, allowed)
    if problems:
        raise MonitorsError("; ".join(problems))

    effective = list(entries) if entries else [dict(IDENTITY_RULE)]
    out = header_lines(record, len(entries))
    out.append("")
    for index, entry in enumerate(effective):
        if index:
            out.append("")
        out += render_call(entry)
    out.append("")
    return "\n".join(out).rstrip("\n")


# ------------------------------------------------------------------ the source


def monitors_from_settings(env: Optional[Dict[str, str]] = None) -> List[Any]:
    """``display.monitors`` out of the user's settings.json, defaults underneath."""
    settings = configstore.load("settings", ROOT, env)
    display = settings.get("display")
    if not isinstance(display, dict):
        raise MonitorsError("settings.json has no display object")
    entries = display.get("monitors")
    if not isinstance(entries, list):
        raise MonitorsError("display.monitors is not a list")
    return entries


def monitors_from_repo_defaults() -> List[Any]:
    """``display.monitors`` out of ``data/settings.default.json``.

    --check and --write-repo-default render from this, never from the developer's
    own settings.json. A shipped payload that depended on whose machine generated
    it could not be checked in CI, and a monitor list is exactly the kind of state
    that differs between two machines: the committed default is the identity rule
    because the repository has no hardware, and that is the whole point of it.
    """
    path = ROOT / "data" / "settings.default.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitorsError(f"{label(path)}: {exc}") from exc
    entries = document.get("display", {}).get("monitors")
    if not isinstance(entries, list):
        raise MonitorsError(f"{label(path)} has no display.monitors list")
    return entries


def monitors_from_file(path: Path) -> List[Any]:
    """An explicit list, so a test can render without a config directory."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitorsError(f"{label(path)}: {exc}") from exc
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        for key in (("display", "monitors"), ("monitors",)):
            node: Any = document
            for part in key:
                node = node.get(part) if isinstance(node, dict) else None
            if isinstance(node, list):
                return node
    raise MonitorsError(f"{label(path)} holds neither a list nor a display.monitors list")


# ------------------------------------------------------------------ targets


def target_path(env: Optional[Dict[str, str]] = None) -> Path:
    return configstore.config_dir(env) / "hypr" / f"{MODULE_NAME}.lua"


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated will put on disk for ``body``."""
    return f"{configstore.header_for(path)}\n{body}\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="gen-monitors-lua",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--record", type=Path, default=RECORD_PATH,
                        help=f"the monitor record (default {label(RECORD_PATH)})")
    parser.add_argument("--monitors-json", type=Path,
                        help="read the monitor list from this file instead of settings.json")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the render to stdout instead of a file")
    parser.add_argument("--write-repo-default", action="store_true",
                        help=f"refresh {label(REPO_DEFAULT)}")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed default matches a fresh render")
    parser.add_argument("--output", type=Path,
                        help="explicit destination (overrides the config dir); "
                             "~/.config/hypr/monitors.lua is the live session")
    args = parser.parse_args(argv)

    try:
        record = load_record(args.record)
        if args.monitors_json:
            entries = monitors_from_file(args.monitors_json)
        elif args.check or args.write_repo_default:
            entries = monitors_from_repo_defaults()
        else:
            entries = monitors_from_settings()
        source = render(entries, record)
    except MonitorsError as exc:
        print(f"monitors-lua: {exc}", file=sys.stderr)
        return 2

    if args.to_stdout:
        sys.stdout.write(rendered_text(REPO_DEFAULT, source))
        return 0

    if args.check:
        if not REPO_DEFAULT.is_file():
            print(f"monitors-lua: {label(REPO_DEFAULT)} is missing", file=sys.stderr)
            return 1
        current = REPO_DEFAULT.read_text(encoding="utf-8")
        expected = rendered_text(REPO_DEFAULT, source)
        if current != expected:
            print("monitors-lua: the committed default does not match a fresh render; run "
                  "--write-repo-default", file=sys.stderr)
            return 1
        print(f"monitors-lua: {label(REPO_DEFAULT)} matches a fresh render")
        return 0

    destination = args.output or (REPO_DEFAULT if args.write_repo_default else target_path())
    try:
        written = configstore.write_generated(destination, source)
    except (OSError, configstore.ConfigError) as exc:
        print(f"monitors-lua: {exc}", file=sys.stderr)
        return 1
    print(f"monitors-lua: wrote {written} ({len(entries) or 1} monitor rule"
          f"{'s' if (len(entries) or 1) != 1 else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
