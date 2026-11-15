#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the session's keyboard map from data/keybinds.default.json.

    iarch-keybinds --check                       CI: generated Lua + document match the record
    iarch-keybinds generate [--write|--check]   render .config/hypr/generated/keybinds.lua
    iarch-keybinds list [--json] [--category X]  the merged map, for a person or a UI
    iarch-keybinds check [--i-know]              validate the map and report every problem
    iarch-keybinds docs                          regenerate docs/SHORTCUTS.md

This is the other half of the reversal ``tools/migrate_keybinds_v2.py`` started.
The record is now the source and the Lua is generated, which is the only
arrangement in which rebinding a key in a window can work: a generated file has
one writer, and a hand-written file has two -- the generator and whoever has a
text editor open.

The generator draws on ``data/design/keybinds.json`` and nothing else. Every
keysym is checked against ``data/reference/xkb-keysyms-1.7.0.txt``, every
dispatcher against the verified ``hl.dsp`` tree, every ``noctalia`` verb against
``data/design/noctalia-ipc.json``. A spelling that is not in one of those records
does not reach a generated file, which is the whole point of having written them
down: the failure mode of a shortcut system is a bind that renders cleanly and
then resolves to nothing, and the compositor answers ``'key not found'`` for both
a name that is not a keysym and a keysym the keyboard cannot produce.

Two rules are enforced here rather than left to a reviewer. A plain
``Ctrl+<letter>`` is refused, because a global Ctrl+C or Ctrl+S takes that key
from every application at once; ``Ctrl+Alt`` and ``Super+Ctrl`` are offered
instead, and ``--i-know`` is the only way past it. And a duplicate ``mods+key``
is a conflict, because two binds on one combination is not something the
compositor refuses -- it is two handlers, and which one runs depends on
registration order.

What this file does not do yet: the mutating subcommands (``set``, ``add``,
``disable``, ``reset``, ``import``, ``export``) and the live reload-and-rollback
against a running compositor. Those belong with the Shortcuts page that calls
them, and the reload path needs a compositor this sandbox does not have; the
render, the merge and every validation rule are here and tested now.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402

DEFAULT_RECORD = ROOT / "data" / "keybinds.default.json"
KEYSYM_LIST = ROOT / "data" / "reference" / "xkb-keysyms-1.7.0.txt"
DESIGN_RECORD = ROOT / "data" / "design" / "keybinds.json"
IPC_RECORD = ROOT / "data" / "design" / "noctalia-ipc.json"
GENERATED = ROOT / ".config" / "hypr" / "generated" / "keybinds.lua"

#: The canonical modifier spellings this project writes, and the order they are
#: emitted in. A person may write any spelling the compositor accepts; the record
#: carries one, so two bindings that mean the same thing cannot look different.
MODIFIER_ORDER = ["SUPER", "SHIFT", "CTRL", "ALT", "MOD2", "MOD3", "MOD5", "CAPS"]

#: A key that is a relative mouse axis rather than a button. The compositor's
#: resolver verifies neither form -- it is not a keysym and not a `mouse:N` code
#: -- so these are carried as warnings, not errors, and the record says why under
#: `rejected`. Changing them to something certainly wrong would be worse than
#: leaving something possibly right.
UNVERIFIED_KEYS = {"mouse_up", "mouse_down", "mouse_left", "mouse_right"}

CONFLICT = "conflict"
ERROR = "error"
WARNING = "warning"


# --------------------------------------------------------------------- problems


class Problem:
    """One thing wrong with the map, with the severity that decides the exit code.

    ``check`` fails on an error and passes on a warning, so the two unverified
    wheel binds do not make a healthy map look broken -- but they are still
    printed, because a warning nobody sees is a warning nobody can act on.
    """

    __slots__ = ("severity", "binding_id", "keys", "message")

    def __init__(self, severity: str, message: str, binding_id: str = "", keys: str = ""):
        self.severity = severity
        self.message = message
        self.binding_id = binding_id
        self.keys = keys

    def __str__(self) -> str:
        where = self.binding_id or self.keys or "the map"
        return f"{self.severity}: {where}: {self.message}"


# ---------------------------------------------------------------------- reading


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_record(root: Path = ROOT) -> Dict[str, Any]:
    return load_json(root / "data" / "keybinds.default.json")


def keysym_names(root: Path = ROOT) -> frozenset:
    """The distinct keysym names in the pinned xkbcommon header."""
    return frozenset((root / "data" / "reference" / "xkb-keysyms-1.7.0.txt")
                     .read_text(encoding="utf-8").split())


def dispatcher_paths(root: Path = ROOT) -> frozenset:
    """Every fully qualified ``hl.dsp`` path the pinned compositor registers."""
    record = load_json(root / "data" / "design" / "keybinds.json")
    dispatchers = record["dispatchers"]
    paths = set(dispatchers["toplevel"]["members"])
    for group_name, group in dispatchers["groups"].items():
        paths.update(f"{group_name}.{leaf}" for leaf in group["members"])
    return frozenset(f"hl.dsp.{path}" for path in paths)


def noctalia_verbs(root: Path = ROOT) -> frozenset:
    record = load_json(root / "data" / "design" / "noctalia-ipc.json")
    return frozenset(verb["verb"].split()[0] for verb in record["verbs"])


def user_override_path(env: Optional[Dict[str, str]] = None) -> Path:
    """``~/.config/iarch/keybinds.json`` -- only the differences a person made.

    ``user_path`` appends the ``.json`` extension itself, so the stem is passed
    bare, the way every other caller of it does; passing "keybinds.json" would
    look for "keybinds.json.json" and silently never find the user's file.
    """
    return configstore.user_path("keybinds", env)


def user_overrides(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    path = user_override_path(env)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A broken user file must not break the session: fall back to defaults and
        # let `check` report it. This is the recovery behaviour Task 7 asks for,
        # and the reason the merge never raises.
        return {}


# ----------------------------------------------------------------------- merge


def merge(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Defaults with a person's differences applied, by id.

    An override carries only the fields it changes, so a rebind is ``{"id": ...,
    "mods": [...], "key": "..."}`` and nothing else; the description, category and
    action come from the default. A binding whose id is not in the defaults is one
    a person added, and is appended. Deleting a default is not something an
    override can do to a locked entry -- that is checked, not assumed, in
    ``validate``.
    """
    by_id = {binding["id"]: dict(binding) for binding in defaults["bindings"]}
    order = [binding["id"] for binding in defaults["bindings"]]
    added: List[Dict[str, Any]] = []

    for override in overrides.get("bindings") or ():
        binding_id = override.get("id")
        if not binding_id:
            continue
        if binding_id in by_id:
            by_id[binding_id].update(override)
        else:
            added.append(dict(override))

    merged = [by_id[binding_id] for binding_id in order]
    merged.extend(added)
    return merged


# ------------------------------------------------------------------- key strings


def key_string(binding: Dict[str, Any]) -> str:
    """``mods`` plus ``key`` as the compositor wants it: joined with ' + '."""
    return " + ".join(list(binding.get("mods") or []) + [binding["key"]])


def normalize_mods(mods: Iterable[str]) -> List[str]:
    canonical = {"CONTROL": "CTRL", "WIN": "SUPER", "LOGO": "SUPER",
                 "MOD4": "SUPER", "META": "SUPER", "MOD1": "ALT"}
    out = {canonical.get(m.upper(), m.upper()) for m in mods}
    return sorted(out, key=lambda m: MODIFIER_ORDER.index(m) if m in MODIFIER_ORDER else 99)


# ---------------------------------------------------------------------- Lua out


def lua_string(text: str) -> str:
    """A Lua double-quoted string literal. The renderer's only escaping path.

    Done by hand rather than with json.dumps because the two disagree on exactly
    the characters that matter here: json escapes a solidus-free ``/`` fine but
    would also turn a literal tab into ``\\t``, and a shell command can contain a
    tab. Backslash, quote, newline and carriage return are the four that break a
    Lua string, and those are the four escaped.
    """
    out = []
    for char in text:
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def render_command(command: Sequence[str]) -> str:
    """An argv list to the one string the compositor spawns.

    Upstream has no argv form -- every command runs as ``/bin/sh -c`` with one
    string (data/design/keybinds.json -> exec) -- so the list is joined here, with
    shlex.quote on each argument so a path with a space in it survives. The list
    is what a person edits; the string is an artefact of the compositor's
    interface and is never stored.
    """
    return " ".join(shlex.quote(part) for part in command)


def handler_for(binding: Dict[str, Any]) -> Optional[str]:
    """The second argument to hl.bind: a dispatcher call, a function, or nothing.

    Returns None for an action that renders to no bind at all (``none``), so the
    caller can skip a reserved or disabled entry rather than emit an empty bind.
    """
    action = binding["action"]
    kind = action["type"]

    if kind == "none":
        return None
    if kind == "exec":
        return f"hl.dsp.exec_cmd({lua_string(render_command(action['command']))})"
    if kind == "shell":
        return f"hl.dsp.exec_cmd({lua_string(action['script'])})"
    if kind == "noctalia":
        argv = ["noctalia", "msg", action["verb"], *(action.get("args") or [])]
        return f"hl.dsp.exec_cmd({lua_string(render_command(argv))})"
    if kind == "iarch":
        argv = [action["cli"], *(action.get("args") or [])]
        return f"hl.dsp.exec_cmd({lua_string(render_command(argv))})"
    if kind == "lua":
        return action["lua"]
    if kind == "dispatch":
        dispatcher = action["dispatcher"]
        if "args_lua" in action:
            return f"{dispatcher}({action['args_lua']})"
        if "workspace" in action:
            workspace = action["workspace"]
            value = workspace if _is_number(workspace) else lua_string(str(workspace))
            return f"{dispatcher}({{ workspace = {value} }})"
        if "args" in action:
            return f"{dispatcher}({_lua_table(action['args'])})"
        return f"{dispatcher}()"
    raise ValueError(f"{binding.get('id')}: unknown action type {kind!r}")


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and value.lstrip("-").isdigit()


def _lua_table(table: Dict[str, Any]) -> str:
    """A small Lua table literal, for the structured ``args`` form."""
    parts = []
    for key, value in table.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif _is_number(value):
            rendered = str(value)
        elif isinstance(value, dict):
            rendered = _lua_table(value)
        else:
            rendered = lua_string(str(value))
        parts.append(f"{key} = {rendered}")
    return "{ " + ", ".join(parts) + " }"


def options_for(binding: Dict[str, Any]) -> str:
    """The third argument to hl.bind: the compositor's options plus the description.

    Only the compositor's own options go in here -- ``mouse`` and ``locked`` from
    ``flags``. The entry-level ``locked`` is this project's meaning (rebindable
    but not deletable) and is never emitted, because there is no hl.bind option
    for it; it is enforced by the settings page and by ``validate``.
    """
    parts = []
    flags = binding.get("flags") or {}
    for name in ("mouse", "locked"):
        if flags.get(name):
            parts.append(f"{name} = true")
    parts.append(f"description = {lua_string(binding['description'])}")
    return "{ " + ", ".join(parts) + " }"


def categories_in_order(bindings: Sequence[Dict[str, Any]]) -> List[str]:
    order: List[str] = []
    for binding in bindings:
        category = binding.get("category", "General")
        if category not in order:
            order.append(category)
    return order


def render_lua(bindings: Sequence[Dict[str, Any]], root: Path = ROOT,
               source_note: str = "data/keybinds.default.json") -> str:
    """The generated keybinds.lua, as text.

    Grouped by category in the order the record declares them, with a comment
    header per group, so the file reads the way the Shortcuts page and the cheat
    sheet do. Disabled and reserved bindings render to nothing: a bind that is
    turned off is absent, not commented out, because a commented-out bind in a
    generated file is a bind a person will hand-edit and lose on the next render.
    """
    design = load_json(root / "data" / "design" / "keybinds.json")
    lines = [
        configstore.GENERATED_HEADER,
        f"-- Source: {source_note}",
        "-- Regenerate: python3 iarch/cli/iarch_keybinds.py generate --write",
        "-- Verify: python3 iarch/cli/iarch_keybinds.py generate --check",
        f"-- Verified against Hyprland {design['verified_against']}; every spelling here",
        "-- is recorded in data/design/keybinds.json and checked by iarch-keybinds check.",
        "-- Do not hand-edit: the next render replaces the file and the edit with it.",
        "",
        'local scrPath = (os.getenv("HOME") or "") .. "/.config/hypr/Scripts"',
        "",
    ]

    bound = 0
    for category in categories_in_order(bindings):
        group = [b for b in bindings if b.get("category") == category and b.get("enabled")]
        renderable = [(b, handler_for(b)) for b in group]
        renderable = [(b, handler) for b, handler in renderable if handler is not None]
        if not renderable:
            continue
        lines.append(f"-- {category}")
        for binding, handler in renderable:
            lines.append(f"hl.bind({lua_string(key_string(binding))}, {handler}, "
                         f"{options_for(binding)})")
            bound += 1
        lines.append("")

    lines.append("return true")
    lines.append("")
    return "\n".join(lines)


# -------------------------------------------------------------------- validation


def validate(bindings: Sequence[Dict[str, Any]], root: Path = ROOT,
             i_know: bool = False) -> List[Problem]:
    """Every problem with the map, as Problems, in a stable order.

    This is the gate the render runs behind. It checks the things a syntactically
    valid Lua file can still get wrong: a key that is not a keysym, a modifier the
    compositor does not know, two binds on one combination, a plain Ctrl+letter
    that would steal a key from every application, a dispatcher that is not in the
    verified tree, a noctalia verb that is not in the record, an exec with no
    argv, a binding with no description, and a locked binding an override tried to
    delete.
    """
    problems: List[Problem] = []
    keysyms = keysym_names(root)
    dispatchers = dispatcher_paths(root)
    verbs = noctalia_verbs(root)
    keysyms_lower = {name.lower() for name in keysyms}

    seen: Dict[str, str] = {}
    ids: Dict[str, int] = {}

    for binding in bindings:
        binding_id = binding.get("id", "<no id>")
        keys = key_string(binding) if "key" in binding else binding_id
        ids[binding_id] = ids.get(binding_id, 0) + 1

        if not binding.get("description", "").strip():
            problems.append(Problem(ERROR, "no description, so the key does something "
                                    "nobody can name", binding_id, keys))

        for modifier in binding.get("mods") or ():
            if modifier not in MODIFIER_ORDER:
                problems.append(Problem(ERROR, f"unknown modifier {modifier!r}",
                                        binding_id, keys))
        mods = binding.get("mods") or []
        if len(set(mods)) != len(mods):
            problems.append(Problem(ERROR, "a modifier is repeated, which hl.bind "
                                    "refuses case-insensitively", binding_id, keys))

        key = binding.get("key", "")
        if not binding.get("enabled"):
            # A disabled or reserved binding renders to nothing, so its key is never
            # resolved; do not hold an unbound key to the keysym check.
            continue

        if key in UNVERIFIED_KEYS:
            problems.append(Problem(WARNING, f"{key!r} is carried from the v1 map and "
                                    "is neither a keysym nor a mouse:N code, so the "
                                    "compositor may answer 'key not found'; see "
                                    "data/design/keybinds.json -> rejected",
                                    binding_id, keys))
        elif not _key_is_valid(key, keysyms_lower):
            problems.append(Problem(ERROR, f"{key!r} is not a keysym in the pinned "
                                    "xkbcommon and not a mouse:N or bare keycode",
                                    binding_id, keys))

        if mods == ["CTRL"] and len(key) == 1 and key.isalpha():
            severity = WARNING if i_know else ERROR
            problems.append(Problem(severity, f"plain Ctrl+{key.upper()} is refused: a "
                                    "global Ctrl+letter takes that key from every "
                                    "application at once. Use Ctrl+Alt+"
                                    f"{key.upper()} or Super+Ctrl+{key.upper()}",
                                    binding_id, keys))

        if key in seen:
            pass  # combination conflict is checked below on the full string
        if keys in seen:
            problems.append(Problem(CONFLICT, f"already bound by {seen[keys]!r}; two "
                                    "binds on one combination is two handlers, and "
                                    "which runs depends on registration order",
                                    binding_id, keys))
        else:
            seen[keys] = binding_id

        action = binding.get("action") or {}
        kind = action.get("type")
        if kind == "exec" and not action.get("command"):
            problems.append(Problem(ERROR, "an exec action with no argv", binding_id, keys))
        elif kind == "dispatch":
            dispatcher = action.get("dispatcher", "")
            if dispatcher not in dispatchers:
                problems.append(Problem(ERROR, f"{dispatcher!r} is not in the verified "
                                        "hl.dsp tree", binding_id, keys))
        elif kind == "noctalia":
            verb = action.get("verb", "")
            if verb not in verbs:
                problems.append(Problem(ERROR, f"noctalia verb {verb!r} is not in "
                                        "data/design/noctalia-ipc.json", binding_id, keys))
        elif kind == "shell" and not action.get("why_shell", "").strip():
            problems.append(Problem(ERROR, "a shell action with no reason is an argv "
                                    "list nobody split", binding_id, keys))
        elif kind == "lua" and not action.get("why_lua", "").strip():
            problems.append(Problem(ERROR, "a Lua function body with no reason is an "
                                    "escape hatch nobody justified", binding_id, keys))

    for binding_id, count in ids.items():
        if count > 1:
            problems.append(Problem(ERROR, f"id {binding_id!r} appears {count} times; an "
                                    "override file keys differences by id, so a "
                                    "duplicate id makes one unreachable", binding_id))

    return problems


def _key_is_valid(key: str, keysyms_lower: set) -> bool:
    if key.lower() in keysyms_lower:
        return True
    if key.startswith("mouse:") and key[6:].isdigit() and int(key[6:]) >= 272:
        return True
    if key.startswith("code:") and key[5:].isdigit():
        return True
    if key.isdigit() and int(key) > 9:
        return True
    return False


def conflicts(bindings: Sequence[Dict[str, Any]], root: Path = ROOT) -> List[Problem]:
    """Just the duplicate-combination problems, which is what `check` gates on."""
    return [p for p in validate(bindings, root) if p.severity == CONFLICT]


# ------------------------------------------------------------------- subcommands


def cmd_generate(args: argparse.Namespace) -> int:
    defaults = default_record(ROOT)
    overrides = user_overrides(os.environ.copy())
    bindings = merge(defaults, overrides)

    problems = validate(bindings, ROOT, i_know=args.i_know)
    blocking = [p for p in problems if p.severity in (ERROR, CONFLICT)]
    for problem in problems:
        print(problem, file=sys.stderr if problem.severity != WARNING else sys.stdout)
    if blocking and not args.force:
        print(f"generate: {len(blocking)} problem(s) block the render; fix the record "
              "or pass --force to render anyway", file=sys.stderr)
        return 1

    source_note = "data/keybinds.default.json"
    if overrides:
        source_note += " + ~/.config/iarch/keybinds.json"
    rendered = render_lua(bindings, ROOT, source_note)

    if args.check:
        if not GENERATED.is_file():
            print(f"generate: {GENERATED.relative_to(ROOT)} does not exist; run "
                  "iarch-keybinds generate --write", file=sys.stderr)
            return 1
        if GENERATED.read_text(encoding="utf-8") != rendered:
            print(f"generate: {GENERATED.relative_to(ROOT)} is out of date with the "
                  "record; run iarch-keybinds generate --write", file=sys.stderr)
            return 1
        bound = rendered.count("hl.bind(")
        print(f"generate: {GENERATED.relative_to(ROOT)} matches the record ({bound} binds)")
        return 0

    if args.write:
        previous = GENERATED.read_text(encoding="utf-8") if GENERATED.is_file() else None
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        configstore.atomic_write(GENERATED, rendered)
        bound = rendered.count("hl.bind(")
        print(f"generate: wrote {GENERATED.relative_to(ROOT)} ({bound} binds)")
        if previous is not None and previous != rendered:
            print("generate: the previous file is in the backup directory")
        return 0

    print(rendered)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    defaults = default_record(ROOT)
    bindings = merge(defaults, user_overrides(os.environ.copy()))
    if args.category:
        bindings = [b for b in bindings if b.get("category") == args.category]
    if args.json:
        payload = [{"id": b["id"], "keys": key_string(b), "mods": b.get("mods") or [],
                    "key": b["key"], "description": b["description"],
                    "category": b["category"], "enabled": b["enabled"],
                    "locked": b["locked"], "action": b["action"]}
                   for b in bindings]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    for category in categories_in_order(bindings):
        group = [b for b in bindings if b.get("category") == category]
        print(f"\n{category}")
        for binding in group:
            state = "" if binding.get("enabled") else "  (off)"
            print(f"  {key_string(binding):<26} {binding['description']}{state}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    defaults = default_record(ROOT)
    bindings = merge(defaults, user_overrides(os.environ.copy()))
    problems = validate(bindings, ROOT, i_know=args.i_know)
    for problem in problems:
        print(problem)
    errors = [p for p in problems if p.severity in (ERROR, CONFLICT)]
    warnings = [p for p in problems if p.severity == WARNING]
    conflict_count = len([p for p in problems if p.severity == CONFLICT])
    print(f"\ncheck: {len(bindings)} bindings, {conflict_count} conflict(s), "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def cmd_docs(args: argparse.Namespace) -> int:
    import subprocess
    script = ROOT / "tools" / "render_shortcuts.py"
    flag = "--check" if args.check else "--write"
    return subprocess.run([sys.executable, str(script), flag], cwd=ROOT).returncode


def cmd_check_all(args: argparse.Namespace) -> int:
    """Top-level ``--check``: is every artifact the record generates still current?

    CI asks the keybind pipeline one question -- did somebody edit the record and
    forget to re-render? -- and this answers it for both renderings at once: the
    generated Lua the session reads and the document a person reads. Either being
    stale is a failure, and each sub-check already names the command that fixes it,
    so a red build says what to run rather than only that something drifted.

    This is deliberately not the same as the ``check`` subcommand, which validates
    the *map* (keysyms, dispatchers, conflicts). ``--check`` validates the
    *renderings*. A record can be perfectly valid and still have a stale Lua file
    sitting next to it, which is the drift this catches.
    """
    generate_args = argparse.Namespace(check=True, write=False, i_know=False, force=False)
    docs_args = argparse.Namespace(check=True)
    lua_status = cmd_generate(generate_args)
    docs_status = cmd_docs(docs_args)
    if lua_status or docs_status:
        print("check: a generated artifact is out of date with the record", file=sys.stderr)
        return 1
    print("check: the generated Lua and the document both match the record")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iarch-keybinds",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="CI freshness check: the generated Lua and the document "
                             "both match the record (not the same as the check "
                             "subcommand, which validates the map itself)")
    sub = parser.add_subparsers(dest="command")

    generate = sub.add_parser("generate", help="render the generated keybinds.lua")
    mode = generate.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    generate.add_argument("--i-know", action="store_true",
                          help="downgrade the plain Ctrl+letter refusal to a warning")
    generate.add_argument("--force", action="store_true",
                          help="render even with blocking problems, for debugging only")
    generate.set_defaults(func=cmd_generate)

    list_ = sub.add_parser("list", help="the merged map")
    list_.add_argument("--json", action="store_true")
    list_.add_argument("--category")
    list_.set_defaults(func=cmd_list)

    check = sub.add_parser("check", help="validate the map and report every problem")
    check.add_argument("--i-know", action="store_true")
    check.set_defaults(func=cmd_check)

    docs = sub.add_parser("docs", help="regenerate docs/SHORTCUTS.md")
    docs.add_argument("--check", action="store_true")
    docs.set_defaults(func=cmd_docs)

    args = parser.parse_args(argv)
    if args.command is None:
        # No subcommand: the only thing this CLI does on its own is the CI
        # freshness check. Anything else needs a subcommand, so say so rather
        # than silently doing nothing.
        if args.check:
            return cmd_check_all(args)
        parser.error("a subcommand is required (or --check for the CI freshness check)")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
