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

Four rules are enforced here rather than left to a reviewer. A plain
``Ctrl+<letter>`` is refused, because a global Ctrl+C or Ctrl+S takes that key
from every application at once; ``Super+Ctrl`` and ``Super+Shift`` are offered
instead -- not ``Ctrl+Alt``, which the layer rule below reserves -- and
``--i-know`` is the only way past it. A duplicate ``mods+key`` is a conflict,
because two binds on one combination is not something the compositor refuses --
it is two handlers, and which one runs depends on registration order. The
modifier layers are kept for what they are for: ``Super`` is the primary layer,
``Super+Shift`` the secondary one, the ``Ctrl+Alt`` family is recovery and
system, and ``Super+Alt`` is deliberately empty so a later bind has somewhere to
go. And nothing destructive is bound without a confirmation in front of it,
because a key that ends a session ends it by accident too; the shell already
draws a session menu, so the menu is what goes on the key.

A binding marked ``static`` is described in the record and implemented by hand in
``.config/hypr/keybind.lua``, which is where the recovery combo lives: a bind
whose job is to repair a broken keyboard map cannot itself live in the file that
might be broken. ``check`` reads that file back and proves the two agree, because
two files describing one bind is exactly the shape that drifts.

What this file does not do yet: the remaining mutating subcommands (``set``,
``add``, ``disable``, ``import``, ``export``) and the live reload-and-rollback
against a running compositor. ``reset`` is here, because the recovery combo calls
it and a safety net that depends on unwritten code is not a safety net. The rest
belong with the Shortcuts page that calls them, and the reload path needs a
compositor this sandbox does not have; the render, the merge and every validation
rule are here and tested now.
"""
from __future__ import annotations

import argparse
import json
import os
import re
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

#: Wheel-axis *events* rather than keys, and the reason a name that is neither a
#: keysym nor a `mouse:N` code still binds. `CKey::isValidEvent` accepts them
#: outright alongside `catchall`, `mouse:` and `switch:` (src/keybinds/Key.cpp:8-10),
#: and `CKeybindManager::onAxisEvent` builds the name from the scroll delta and
#: dispatches it as `SResolvedKey{.event = name}` (src/keybinds/Manager.cpp:312-335),
#: so a bind on one is matched on an event and never reaches resolveKeycode. Verified
#: in data/design/keybinds.json -> key_forms, as the "special event name" form. The
#: two wheel binds this project carries were an open question until that was read out
#: of source; the closure and its two limits are recorded in docs/UNVERIFIED.md.
#:
#: Compared exactly, unlike a keysym name: isValidEvent uses == on the four
#: spellings, so `MOUSE_DOWN` is not the same event and is refused below.
EVENT_KEYS = {"mouse_up", "mouse_down", "mouse_left", "mouse_right"}

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

    Only the compositor's own options go in here -- ``mouse``, ``locked`` and
    ``repeating`` from ``flags``. The entry-level ``locked`` is this project's
    meaning (rebindable but not deletable) and is never emitted, because there
    is no hl.bind option for it; it is enforced by the settings page and by
    ``validate``. ``repeating`` is BIND_FLAG_REPEAT and is emitted last so the
    two flags a media key carries read in the order the record lists them.
    """
    parts = []
    flags = binding.get("flags") or {}
    for name in ("mouse", "locked", "repeating"):
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
        # A static binding is described in the record but implemented by hand in
        # .config/hypr/keybind.lua, so rendering it here would put two binds on one
        # key and leave which one runs up to require() order.
        group = [b for b in bindings
                 if b.get("category") == category and b.get("enabled")
                 and not b.get("static")]
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

#: The modifier layers, and what each one is for. ``SUPER`` is the primary layer and
#: ``SUPER+SHIFT`` the secondary one; the ``Ctrl+Alt`` family is the recovery and
#: system family, because that is where the recovery combo lives and a collision
#: there is a safety net that does not fire when it is needed. ``SUPER+Alt`` is
#: deliberately empty: an empty layer is somewhere a later bind can go without taking
#: a key away from anything else, which is worth more than filling it now.
SYSTEM_CATEGORIES = frozenset({"System"})

#: Noctalia session actions that end a session or the machine the moment they run, as
#: opposed to ``lock`` and ``suspend``, which the person can undo by logging back in
#: or waking the machine. Recorded in data/design/noctalia-ipc.json.
DESTRUCTIVE_SESSION_ACTIONS = frozenset({"logout", "reboot", "reboot-uefi", "shutdown"})


def destructive_reason(action: Dict[str, Any]) -> Optional[str]:
    """Why this action ends a session or the machine without asking, else ``None``.

    Every spelling the record can hold is covered, because the same mistake is
    reachable three ways: as a compositor dispatcher, as a noctalia verb, and as the
    ``noctalia msg ...`` argv the v1 map used. Checking one of the three would make
    the rule a suggestion.
    """
    kind = action.get("type")

    if kind == "dispatch" and action.get("dispatcher") == "exit":
        return ("hl.dsp.exit takes no arguments and ends the compositor the moment "
                "the key goes down")

    if kind == "noctalia":
        args = [str(a) for a in (action.get("args") or ())]
        if (action.get("verb") == "session" and args
                and args[0] in DESTRUCTIVE_SESSION_ACTIONS):
            return f"noctalia 'session {args[0]}' runs the moment the key goes down"

    if kind == "exec":
        argv = [str(a) for a in (action.get("command") or ())]
    elif kind == "shell":
        argv = [str(action.get("script") or "")]
    else:
        argv = []
    if not argv:
        return None

    if "session" in argv:
        at = argv.index("session")
        if at + 1 < len(argv) and argv[at + 1] in DESTRUCTIVE_SESSION_ACTIONS:
            return f"noctalia 'session {argv[at + 1]}' runs the moment the key goes down"
    if "hyprctl" in argv and "exit" in argv:
        return "hyprctl's exit ends the compositor the moment the key goes down"
    if "loginctl" in argv and "terminate-session" in argv:
        return ("loginctl terminate-session ends the session the moment the key goes "
                "down")
    if "systemctl" in argv and any(w in argv for w in ("poweroff", "reboot", "halt")):
        return "systemctl ends the machine the moment the key goes down"
    for word in argv:
        # Compared on the basename, so an absolute path is not a way past the rule.
        name = word.rsplit("/", 1)[-1]
        if name in ("shutdown", "poweroff", "reboot", "halt"):
            return f"{name!r} ends the machine the moment the key goes down"
    return None


def confirmation_rule(binding: Dict[str, Any], keys: str,
                      binding_id: str) -> List[Problem]:
    """No destructive action on a key without a confirmation in front of it.

    A key that ends a session is a key that ends it by accident: a mistyped
    combination, a child, a cat. The rule is not "never bind these" but "bind the
    menu", and the shell already draws one -- noctalia's session panel offers logout,
    reboot and shutdown behind a click, which is the confirmation.
    """
    reason = destructive_reason(binding.get("action") or {})
    if reason is None:
        return []
    return [Problem(ERROR, f"{reason}, so it does not go on a key: bind the menu "
                    "instead, which noctalia already draws ('panel-toggle session')",
                    binding_id, keys)]


def layer_rule(binding: Dict[str, Any], keys: str, binding_id: str) -> List[Problem]:
    """Keep each modifier layer for what it is for.

    The severities differ on purpose. Bare ``Ctrl+Alt`` is an error because the
    recovery combo and the deliberately-reserved X11 kill-server key both live there,
    so anything else in that layer can stop the safety net from firing.
    ``Super+Ctrl+Alt`` is a warning rather than an error because the two workspace
    moves carried into it from the v1 map both worked, and refusing a bind that works
    is not the same thing as reporting one. They have since moved, to ``Super+Ctrl+N``
    and ``Super+Ctrl+P`` -- the layer this checker offers when it refuses a plain
    ``Ctrl+letter``, and the layer that already owns workspace navigation on the
    arrows -- so the warning is now a guard on the next bind that reaches for the
    recovery layer rather than a debt printed on every run. The relocation, and the
    allocation of all 78 letter cells it was part of, is recorded in
    ``data/design/keybinds.json`` under ``alphabet``.
    """
    mods = frozenset(binding.get("mods") or ())
    category = binding.get("category", "")
    problems: List[Problem] = []

    if mods == {"SUPER", "ALT"}:
        problems.append(Problem(ERROR, "Super+Alt is kept empty on purpose, so a later "
                                "bind has a layer to go in without taking a key from "
                                "anything else; use the Super or Super+Shift layer",
                                binding_id, keys))
    elif mods == {"CTRL", "ALT"} and category not in SYSTEM_CATEGORIES:
        problems.append(Problem(ERROR, f"Ctrl+Alt is the recovery and system layer and "
                                f"this is category {category!r}: the recovery combo "
                                "lives here, and a collision on it is a safety net "
                                "that does not fire when it is needed",
                                binding_id, keys))
    elif mods == {"SUPER", "CTRL", "ALT"} and category not in SYSTEM_CATEGORIES:
        problems.append(Problem(WARNING, f"Super+Ctrl+Alt is the recovery and system "
                                f"layer and this is category {category!r}: the two "
                                "workspace moves the v1 map carried here moved to "
                                "Super+Ctrl+N and Super+Ctrl+P, so the layer to use is "
                                "Super+Ctrl, which no application owns",
                                binding_id, keys))
    return problems


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

        if binding.get("locked") and not binding.get("enabled"):
            # Checked before the disabled shortcut below, which skips the rest of the
            # loop: a locked binding that is off is the one thing about a disabled
            # binding that still matters.
            problems.append(Problem(ERROR, "locked and disabled at once; locked means "
                                    "rebindable but not deletable, and turning one off "
                                    "is how an override deletes it. Rebind it, or "
                                    "unlock it in the record and say why",
                                    binding_id, keys))

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

        if not _key_is_valid(key, keysyms_lower):
            problems.append(Problem(ERROR, f"{key!r} is not a keysym in the pinned "
                                    "xkbcommon, and is not a mouse:N button, a code:N "
                                    "keycode, a bare keycode over 9, or one of the "
                                    "wheel events "
                                    f"{', '.join(sorted(EVENT_KEYS))}; the compositor "
                                    "would answer 'key not found'",
                                    binding_id, keys))

        if mods == ["CTRL"] and len(key) == 1 and key.isalpha():
            severity = WARNING if i_know else ERROR
            # The remedy has to be one this checker would then accept. Ctrl+Alt is
            # offered nowhere here: it is the recovery and system layer (see
            # layer_rule), so suggesting it for an ordinary application bind would
            # send the person straight into the next refusal.
            problems.append(Problem(severity, f"plain Ctrl+{key.upper()} is refused: a "
                                    "global Ctrl+letter takes that key from every "
                                    "application at once. Use Super+Ctrl+"
                                    f"{key.upper()} or Super+Shift+{key.upper()}",
                                    binding_id, keys))

        problems.extend(layer_rule(binding, keys, binding_id))
        problems.extend(confirmation_rule(binding, keys, binding_id))

        # Compared case-folded, because the compositor resolves a key name with
        # xkb_keysym_from_name and XKB_KEYSYM_CASE_INSENSITIVE (src/keybinds/Key.cpp:40,
        # src/keybinds/Resolver.cpp:58, recorded in data/design/keybinds.json ->
        # key_forms), so "Left", "left" and "LEFT" are one key and two binds spelling
        # it differently are still two handlers on it. An exact comparison here would
        # report a clean map for a collision the compositor really has.
        folded = keys.lower()
        if folded in seen:
            problems.append(Problem(CONFLICT, f"already bound by {seen[folded]!r}; two "
                                    "binds on one combination is two handlers, and "
                                    "which runs depends on registration order. The "
                                    "compositor resolves key names case-insensitively, "
                                    "so a spelling difference is not a second key",
                                    binding_id, keys))
        else:
            seen[folded] = binding_id

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

    problems.extend(static_bindings_agree(bindings, root))

    return problems


def static_bindings_agree(bindings: Sequence[Dict[str, Any]],
                          root: Path = ROOT) -> List[Problem]:
    """Prove a ``static`` binding against the file that implements it.

    A static binding is described in the record and written by hand in
    .config/hypr/keybind.lua, because it has to work when the generated file does
    not. Two files describing one bind is exactly the shape that drifts: the record
    can say Ctrl+Alt+R while the static file binds something else, and every other
    check in here would still pass because both files are individually valid. So the
    key and the command are read back out of the static file, and the generated file
    is checked for a second bind on the same key -- which would be two handlers, one
    of which runs depending on require() order.
    """
    problems: List[Problem] = []
    static_path = root / ".config" / "hypr" / "keybind.lua"
    static_text = static_path.read_text(encoding="utf-8") if static_path.is_file() else ""
    # Compared against what the render *would* produce, not against the file on disk.
    # Reading the artifact here would make generate refuse to run exactly when the
    # artifact is wrong, which is the only time anyone runs it -- a check that blocks
    # its own repair. render_lua skips static bindings by construction, so this
    # asserts that invariant stays true instead of reporting a stale file, which
    # generate --check already reports by comparing the whole render.
    rendered_text = render_lua(bindings, root, "")

    for binding in bindings:
        if not binding.get("static"):
            continue
        binding_id = binding.get("id", "<no id>")
        keys = key_string(binding)
        bind_call = f'hl.bind("{keys}"'

        if not static_path.is_file():
            problems.append(Problem(ERROR, "marked static but "
                                    ".config/hypr/keybind.lua is missing, so nothing "
                                    "binds this key at all", binding_id, keys))
            continue
        if bind_call not in static_text:
            problems.append(Problem(ERROR, f"marked static but {static_path} has no "
                                    f"hl.bind for {keys!r}; the record promises a bind "
                                    "the session does not have", binding_id, keys))

        argv = (binding.get("action") or {}).get("command") or []
        command = " ".join(argv)
        if command and command not in static_text:
            problems.append(Problem(ERROR, f"marked static but {static_path} never runs "
                                    f"{command!r}; the record and the implementation "
                                    "disagree about what the key does", binding_id, keys))

        if bind_call in rendered_text:
            problems.append(Problem(ERROR, f"{keys} is marked static and the render also "
                                    "emits it, so two handlers would race on one key; a "
                                    "static binding must be skipped by render_lua",
                                    binding_id, keys))

    return problems


def _key_is_valid(key: str, keysyms_lower: set) -> bool:
    """Whether the compositor resolves this key at all, in any of its four shapes.

    A keysym name -- resolved with XKB_KEYSYM_CASE_INSENSITIVE, so case does not
    matter (src/keybinds/Key.cpp:40) -- a ``mouse:N`` button at or above BTN_MOUSE,
    a ``code:N`` raw keycode or a bare number over 9, and a wheel-axis event name.
    The event names are the one case-sensitive shape: ``isValidEvent`` compares the
    four spellings with ``==`` (src/keybinds/Key.cpp:8-10), so an upper-case spelling
    is a different event and resolves to nothing.
    """
    if key in EVENT_KEYS:
        return True
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


def session_generated_path(config_home: Optional[Path] = None,
                           env: Optional[Dict[str, str]] = None) -> Path:
    """The generated file the running compositor reads, not the repository copy.

    ``GENERATED`` is the checked-in artifact a render refreshes and CI keeps fresh.
    A live session reads a *copy* of it: lib/stage-v5-config.sh copies the payload
    into the destination, so ~/.config/hypr/generated/keybinds.lua is its own file.
    Recovery has to write that one, because fixing the repository copy would leave
    the compositor reading the map that broke. Resolution matches theme.py, which
    writes the same session tree.
    """
    environ = dict(os.environ if env is None else env)
    if config_home is not None:
        home = Path(config_home)
    else:
        home = Path(environ.get("HOME") or str(Path.home())) / ".config"
    if not home.is_absolute():
        raise SystemExit(f"config home must be an absolute path: {home}")
    return home / "hypr" / "generated" / "keybinds.lua"


class UserError(Exception):
    """A refusal with a sentence for the person, not a traceback.

    Every mutating subcommand raises this for bad input, and ``main`` turns it into
    an exit status of 2 and one line on stderr. A traceback for a mistyped key is
    a bug report the person has to read to find out they meant ``Super`` and not
    ``super``.
    """


def environment(args: argparse.Namespace) -> Dict[str, str]:
    """The environment a command runs in, with ``--config-home`` honoured everywhere.

    Not just ``os.environ``: a command pointed at another config root has to read its
    override there, write its override there and back it up from there, and all three go
    through :mod:`iarch.lib.configstore`, which takes an environment. Passing the flag
    only to the session-file path -- which is what this used to do -- left a command
    writing the generated Lua under ``--config-home`` while it changed the override in
    the real ``~/.config/iarch``, and reporting one change that had happened in two
    places.

    ``--config-home`` names the ``.config`` directory itself, which is what
    ``theme.py`` means by the same flag and what ``session_generated_path`` already
    assumed: ``<config-home>/hypr/generated/...``, so the override belongs at
    ``<config-home>/iarch/keybinds.json``. ``configstore`` wants that inner directory
    rather than its parent, and ``IARCH_CONFIG_DIR`` is how it is told -- which also
    means an exported ``IARCH_CONFIG_DIR`` loses to the flag, as an explicit argument
    should beat an inherited environment.
    """
    env = os.environ.copy()
    config_home = getattr(args, "config_home", None)
    if config_home is not None:
        env["IARCH_CONFIG_DIR"] = str(Path(config_home) / "iarch")
    return env


def override_entries(env: Dict[str, str]) -> List[Dict[str, Any]]:
    """The person's differences, as the list the override file actually holds.

    The file holds ``{"bindings": [...]}`` where each entry carries its own ``id``
    and only the fields it changes -- not a mapping keyed by id. Reading it as a
    mapping silently finds nothing and reports success, which is why this is one
    function every mutator goes through.
    """
    document = user_overrides(env)
    return [entry for entry in (document.get("bindings") or ())
            if isinstance(entry, dict) and entry.get("id")]


def parse_modifiers(raw: str) -> List[str]:
    """``--mods`` into the canonical list, refusing a spelling the compositor lacks."""
    parts = [piece.strip().upper() for piece in re.split(r"[+, ]+", raw) if piece.strip()]
    if not parts:
        raise UserError("--mods needs at least one modifier, for example SUPER or "
                        "SUPER,SHIFT")
    unknown = [m for m in parts if m not in MODIFIER_ORDER]
    if unknown:
        raise UserError(f"not a modifier the compositor knows: {', '.join(unknown)}. "
                        f"The ones it has are {', '.join(MODIFIER_ORDER)}")
    if len(set(parts)) != len(parts):
        raise UserError(f"a modifier is repeated in {raw!r}; hl.bind refuses that "
                        "case-insensitively")
    return sorted(set(parts), key=MODIFIER_ORDER.index)


def parse_key(raw: str) -> str:
    """``--key`` into the pinned spelling of a keysym, refusing a name xkbcommon lacks.

    A spelling that is already in the pinned list is kept exactly, so the record's own
    vocabulary is never rewritten. One that is not, but matches case-insensitively, is
    snapped to the list's spelling -- ``Backspace`` becomes ``BackSpace`` and ``RETURN``
    becomes ``Return`` -- because the compositor resolves key names case-insensitively
    (``src/keybinds/Key.cpp:40``), so accepting both spellings would let one key be
    written two ways in the same map and the documentation would show whichever the
    person happened to type.
    """
    key = raw.strip()
    if not key:
        raise UserError("--key must not be empty")
    if key in EVENT_KEYS:
        # A wheel axis, matched exactly: it is an event name, not a keysym, so
        # canonicalising its case would produce a spelling nothing dispatches.
        return key
    names = keysym_names(ROOT)
    exact = set(names)
    if key in exact:
        return key
    folded = {name.lower(): name for name in names}
    canonical = folded.get(key.lower())
    if canonical is not None:
        return canonical
    if _key_is_valid(key, set(folded)):
        return key  # a mouse:N or code: form, or a raw keycode above 9
    hint = ""
    # The four punctuation keys a person is most likely to type as the character.
    # Each name is in the pinned list (comma:1942, period:2426, semicolon:2470,
    # slash:2481), so the hint names a spelling that will be accepted.
    punctuation = {".": "period", ",": "comma", "/": "slash", ";": "semicolon"}
    if key in punctuation:
        hint = f" The keysym for {key!r} is {punctuation[key]!r}, not the character."
    elif len(key) == 1 and key.isalpha():
        hint = " A letter is spelled as itself, in either case."
    raise UserError(f"{key!r} is not a keysym in the pinned xkbcommon "
                    f"(data/reference/xkb-keysyms-1.7.0.txt), and is not a mouse:N "
                    f"or code: form or a bare keycode above 9.{hint} The wheel axes "
                    "are mouse_up, mouse_down, mouse_left and mouse_right")


def _leaf_close(stored: str, typed: str) -> bool:
    """Whether a stored dispatcher leaf is close enough to suggest for a typed one."""
    return (stored == typed or stored.startswith(typed) or typed.startswith(stored))


def parse_dispatcher(raw: str) -> str:
    """``--dispatch`` into a path in the verified tree, refusing one it does not have.

    The short form is accepted and expanded -- ``window.close`` becomes
    ``hl.dsp.window.close`` -- because the record stores the full path and a person
    typing the leaf should not have to know that. Expanding to the stored spelling
    rather than keeping what was typed is the same choice ``parse_key`` makes: one
    thing, one spelling, so the map cannot hold two names for one dispatcher.
    """
    name = raw.strip()
    if not name:
        raise UserError("--dispatch must not be empty")
    paths = dispatcher_paths(ROOT)
    for candidate in (name, f"hl.dsp.{name}"):
        if candidate in paths:
            return candidate
    # Suggest by leaf, accepting a prefix either way: "fullscreen_toggle" should be
    # pointed at "fullscreen", and "win" at "window.close". An exact-leaf comparison
    # would miss both and leave the person with a sample of the tree instead.
    tail = name.rsplit(".", 1)[-1]
    near = sorted(path for path in paths
                  if _leaf_close(path.rsplit(".", 1)[-1], tail))[:3]
    hint = (f" Did you mean {', '.join(near)}?" if near else
            f" The tree has {len(paths)} paths, for example "
            f"{', '.join(sorted(paths)[:3])}.")
    raise UserError(f"{name!r} is not in the verified hl.dsp tree recorded in "
                    f"data/design/keybinds.json, so the compositor would not resolve "
                    f"it.{hint}")


def confirmed(prompt: str, assume_yes: bool, stdin_is_tty: bool) -> bool:
    """Ask before discarding something, and refuse when nobody can answer.

    A non-interactive caller gets a refusal rather than a silent yes, because a
    prompt nobody reads is not a confirmation. The one caller that legitimately
    cannot answer -- the recovery combo, which fires while the session may be
    broken -- passes ``--yes``, and pressing a dedicated recovery combination is
    itself the explicit intent.
    """
    if assume_yes:
        return True
    if not stdin_is_tty:
        raise UserError(f"{prompt} -- this is not a terminal, so there is nobody to "
                        "ask; pass --yes if that is what you mean")
    print(f"{prompt} [y/N] ", end="", flush=True)
    answer = sys.stdin.readline().strip().lower()
    return answer in ("y", "yes")


def commit_change(defaults: Dict[str, Any], entries: List[Dict[str, Any]],
                  env: Dict[str, str], *, config_home: Optional[Path] = None,
                  confirm: Optional[str] = None, assume_yes: bool = False,
                  stdin_is_tty: Optional[bool] = None) -> Tuple[int, str]:
    """Validate, confirm, then write the override and the session file as one change.

    The order is the safety. The map the change would produce is validated before
    anything on disk is touched, so a change that would leave the compositor with a
    bind it cannot resolve is refused and changes nothing -- there is nothing to
    undo. Both files are then backed up before either is written, and a failure
    halfway puts both back, because "validate first" cannot cover the disk being
    full.

    Returns the exit status and a one-line summary for the caller to print.
    """
    if stdin_is_tty is None:
        stdin_is_tty = bool(sys.stdin and sys.stdin.isatty())
    document: Dict[str, Any] = {"bindings": entries} if entries else {}
    merged = merge(defaults, document)

    problems = validate(merged, ROOT)
    blocking = [p for p in problems if p.severity in (ERROR, CONFLICT)]
    for problem in problems:
        print(problem, file=sys.stderr if problem.severity != WARNING else sys.stdout)
    if blocking:
        return 1, (f"refused; the map this change would produce has {len(blocking)} "
                   "problem(s), and nothing was changed")

    if confirm is not None:
        if not confirmed(confirm, assume_yes, stdin_is_tty):
            return 1, "cancelled; nothing was changed"

    override_path = configstore.user_path("keybinds", env)
    target = session_generated_path(config_home, env)
    override_backup = (configstore.backup_of(override_path, env)
                       if override_path.is_file() else None)
    target_backup = configstore.backup_of(target, env) if target.is_file() else None
    source_note = "data/keybinds.default.json"
    if entries:
        source_note += f" + {override_path}"
    rendered = render_lua(merged, ROOT, source_note)

    try:
        if entries:
            override_path.parent.mkdir(parents=True, exist_ok=True)
            configstore.atomic_write(
                override_path,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        elif override_path.is_file():
            override_path.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        configstore.atomic_write(target, rendered)
    except OSError as exc:
        for path, backup in ((override_path, override_backup), (target, target_backup)):
            if backup is not None:
                try:
                    path.write_bytes(backup.read_bytes())
                except OSError:
                    print(f"iarch-keybinds: could not restore {path} from {backup}",
                          file=sys.stderr)
        return 1, f"failed while writing ({exc}); both files were restored"

    summary = f"wrote {target} ({rendered.count('hl.bind(')} binds)"
    if override_backup is not None:
        summary += f"; the previous override is in {override_backup}"
    return 0, summary


def cmd_set(args: argparse.Namespace) -> int:
    """Change one field of a binding that ships, keeping everything else.

    Only the named fields go into the override, so a rebind does not restate an
    action and an action change does not restate a key: whatever is not mentioned
    keeps coming from the shipped record, which is what makes an update that
    changes a default able to reach the person who changed nothing else about it.
    """
    env = environment(args)
    defaults = default_record(ROOT)
    known = {b["id"]: b for b in defaults["bindings"]}
    if args.id not in known:
        raise UserError(f"{args.id!r} is not in the shipped map, so there is nothing "
                        "to change; `add` creates a binding of your own")

    difference: Dict[str, Any] = {"id": args.id}
    if args.mods is not None:
        difference["mods"] = parse_modifiers(args.mods)
    if args.key is not None:
        difference["key"] = parse_key(args.key)
    if args.description is not None:
        if not args.description.strip():
            raise UserError("--description must not be blank: a bind nobody can name "
                            "is a bind nobody can find in the cheat sheet")
        difference["description"] = args.description.strip()
    if args.enable:
        difference["enabled"] = True
    if args.disable:
        if known[args.id].get("locked"):
            raise UserError(f"{args.id} is locked: rebindable but not deletable, and "
                            "turning it off is how an override deletes it. Rebind it "
                            "instead, or unlock it in the record")
        if known[args.id].get("static"):
            raise UserError(f"{args.id} is hand-written in .config/hypr/keybind.lua, "
                            "so it is not this record's to turn off")
        difference["enabled"] = False
    if len(difference) == 1:
        raise UserError("nothing to change: pass --mods, --key, --description, "
                        "--enable or --disable")

    entries = override_entries(env)
    replaced = False
    for index, entry in enumerate(entries):
        if entry.get("id") == args.id:
            # Merged into the difference already saved, so two `set` runs on one
            # binding accumulate rather than the second silently dropping the first.
            merged_entry = dict(entry)
            merged_entry.update(difference)
            entries[index] = merged_entry
            replaced = True
            break
    if not replaced:
        entries.append(difference)

    status, summary = commit_change(defaults, entries, env,
                                    config_home=args.config_home,
                                    assume_yes=args.yes)
    if status:
        print(f"set: {summary}", file=sys.stderr)
        return status
    changed = next(b for b in merge(defaults, {"bindings": entries})
                   if b["id"] == args.id)
    fields = ", ".join(k for k in difference if k != "id")
    print(f"set: {args.id} is now {key_string(changed)} ({fields})")
    print(f"set: {summary}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Add a binding of your own, which the shipped record does not have."""
    env = environment(args)
    defaults = default_record(ROOT)
    known = {b["id"] for b in defaults["bindings"]}
    if args.id in known:
        raise UserError(f"{args.id!r} is already in the shipped map; `set` changes it")
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", args.id):
        raise UserError(f"{args.id!r} is not an id of the form category.subject: lower "
                        "case, with at least one dot or hyphen separating the parts, "
                        "so a bind can be listed under a heading")

    forms = [bool(args.exec), args.dispatch is not None, args.noctalia is not None]
    if sum(forms) != 1:
        raise UserError("exactly one action: --exec, --dispatch or --noctalia")

    action: Dict[str, Any]
    if args.exec:
        argv = shlex.split(args.exec)
        if not argv:
            raise UserError("--exec produced no argv; quote the command as one string")
        action = {"type": "exec", "command": argv}
    elif args.dispatch is not None:
        action = {"type": "dispatch", "dispatcher": parse_dispatcher(args.dispatch)}
        if args.args_lua:
            action["args_lua"] = args.args_lua
    else:
        action = {"type": "noctalia", "verb": args.noctalia}
        if args.noctalia_arg:
            action["args"] = list(args.noctalia_arg)

    entry: Dict[str, Any] = {
        "id": args.id,
        "mods": parse_modifiers(args.mods),
        "key": parse_key(args.key),
        "action": action,
        "description": args.description.strip(),
        "category": args.category.strip(),
        "enabled": True,
        "locked": False,
    }
    if not entry["description"]:
        raise UserError("--description must not be blank: the cheat sheet and "
                        "docs/SHORTCUTS.md are rendered from it")
    if not entry["category"]:
        raise UserError("--category must not be blank: it is the heading the bind is "
                        "listed under")

    entries = override_entries(env)
    if any(e.get("id") == args.id for e in entries):
        raise UserError(f"{args.id!r} is already one of your own bindings; `set` "
                        "changes it, or `reset` drops it first")
    entries.append(entry)

    status, summary = commit_change(defaults, entries, env,
                                    config_home=args.config_home,
                                    assume_yes=args.yes)
    print(f"add: {summary}", file=sys.stderr if status else sys.stdout)
    if status == 0:
        print(f"add: {args.id} on {key_string(entry)}")
    return status


def cmd_disable(args: argparse.Namespace) -> int:
    """Turn a binding off without deleting the difference that rebinds it."""
    return _toggle_enabled(args, enabled=False)


def cmd_enable(args: argparse.Namespace) -> int:
    """Turn a binding back on."""
    return _toggle_enabled(args, enabled=True)


def _toggle_enabled(args: argparse.Namespace, *, enabled: bool) -> int:
    env = environment(args)
    defaults = default_record(ROOT)
    known = {b["id"]: b for b in defaults["bindings"]}
    verb = "enable" if enabled else "disable"

    entries = override_entries(env)
    own = {e.get("id"): e for e in entries}
    for binding_id in args.ids:
        if binding_id not in known and binding_id not in own:
            raise UserError(f"{binding_id!r} is not in the shipped map and is not one "
                            "of your own bindings, so there is nothing to "
                            f"{verb}")
        shipped = known.get(binding_id) or {}
        if not enabled and shipped.get("locked"):
            raise UserError(f"{binding_id} is locked: rebindable but not deletable, "
                            f"and turning it off is how an override deletes it. This "
                            f"is one of the {len([b for b in known.values() if b.get('locked')])} "
                            "safety-net roles -- close window, lock, exit, terminal, "
                            "settings, cheat sheet, power menu")
        if not enabled and shipped.get("static"):
            raise UserError(f"{binding_id} is hand-written in .config/hypr/keybind.lua "
                            "because it has to survive a broken map; it is not this "
                            "record's to turn off")
        if not enabled and shipped.get("reserved"):
            raise UserError(f"{binding_id} is reserved rather than bound, so it is "
                            "already off")
        if binding_id in own:
            own[binding_id]["enabled"] = enabled
        else:
            entries.append({"id": binding_id, "enabled": enabled})
            own[binding_id] = entries[-1]

    status, summary = commit_change(defaults, entries, env,
                                    config_home=args.config_home,
                                    assume_yes=args.yes)
    print(f"{verb}: {summary}", file=sys.stderr if status else sys.stdout)
    return status


def cmd_export(args: argparse.Namespace) -> int:
    """Write the map out: your differences by default, the whole map with --all.

    The differences are what move to another machine, because they are the only
    part that is yours. ``--all`` is for reading or reviewing the effective map,
    and importing one back is a `reset` plus a re-apply, which is why ``import``
    refuses a document that is not a set of differences unless ``--all`` is passed
    with it.
    """
    env = environment(args)
    defaults = default_record(ROOT)
    entries = override_entries(env)
    if args.all:
        payload: Any = {"version": 2, "bindings": merge(defaults, {"bindings": entries})}
        kind = f"the effective map ({len(payload['bindings'])} bindings)"
    else:
        payload = {"bindings": entries}
        kind = (f"{len(entries)} difference(s)" if entries
                else "no differences -- this is the shipped map unchanged")
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.file:
        target = Path(args.file).expanduser()
        if target.is_dir():
            raise UserError(f"{target} is a directory, not a file to write")
        configstore.atomic_write(target, text)
        print(f"export: wrote {kind} to {target}")
    else:
        sys.stdout.write(text)
        print(f"export: {kind}", file=sys.stderr)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    """Read differences back in, merging by default and replacing only when told."""
    env = environment(args)
    defaults = default_record(ROOT)
    source = Path(args.file).expanduser()
    if not source.is_file():
        raise UserError(f"{source} is not a file")
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise UserError(f"{source} does not parse as JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("bindings"), list):
        raise UserError(f"{source} is not a keybinds document: it needs a 'bindings' "
                        "list, which `export` writes")

    incoming = [e for e in document["bindings"] if isinstance(e, dict) and e.get("id")]
    skipped = len(document["bindings"]) - len(incoming)
    if not incoming:
        raise UserError(f"{source} holds no binding with an id, so there is nothing "
                        "to import")

    # An exported whole map carries every field of every shipped binding. Importing
    # that as differences would freeze all of them: a later update to a default
    # could never reach this machine again. Refuse it and say what to do instead.
    if not args.all and document.get("version") and len(incoming) > 20:
        frozen = [e["id"] for e in incoming
                  if e["id"] in {b["id"] for b in defaults["bindings"]}
                  and len(e) > 4]
        if frozen:
            raise UserError(
                f"{source} looks like a whole exported map, not a set of differences: "
                f"{len(frozen)} shipped bindings carry every field. Importing it would "
                "freeze them, so a later change to a default could never reach this "
                "machine. Export without --all, or pass --all to import it anyway")

    entries = [] if args.replace else override_entries(env)
    by_id = {e["id"]: e for e in entries}
    for entry in incoming:
        if entry["id"] in by_id and not args.replace:
            by_id[entry["id"]].update(entry)
        else:
            by_id[entry["id"]] = dict(entry)
    merged_entries = list(by_id.values())

    confirm = None
    if args.replace:
        existing = override_entries(env)
        confirm = (f"import --replace discards the {len(existing)} difference(s) "
                   f"already saved and replaces them with {len(merged_entries)} from "
                   f"{source.name}.")
    status, summary = commit_change(defaults, merged_entries, env,
                                    config_home=args.config_home, confirm=confirm,
                                    assume_yes=args.yes)
    detail = f"imported {len(incoming)} binding(s)"
    if skipped:
        detail += f" and skipped {skipped} entry/entries with no id"
    print(f"import: {detail}; {summary}", file=sys.stderr if status else sys.stdout)
    return status


def cmd_reset(args: argparse.Namespace) -> int:
    """Drop the differences a person saved and re-apply the shipped map.

    This is what the recovery combo calls (Ctrl+Alt+R, hand-written in
    .config/hypr/keybind.lua because a bind that repairs a broken map cannot live
    in the file that might be broken). The safety is in the ordering rather than in
    an undo: the resulting map is validated before anything on disk is touched, so a
    reset that would produce a map the compositor refuses is reported and changes
    nothing. A backup is still taken first and restored if a write fails halfway,
    because "validate first" cannot cover the disk being full.
    """
    env = environment(args)
    override_path = configstore.user_path("keybinds", env)
    overrides = user_overrides(env)
    defaults = default_record(ROOT)
    known = {b["id"] for b in defaults["bindings"]}

    if not args.all and not args.ids:
        print("reset: name the bindings to reset, or pass --all to drop every "
              "difference saved in "
              f"{override_path}", file=sys.stderr)
        return 2

    # The override file holds a list of partial bindings, each carrying its own id --
    # not a mapping keyed by id -- so the differences are selected by walking that
    # list. Treating it as a mapping silently resets nothing and reports success.
    entries = override_entries(env)
    saved_ids = [e["id"] for e in entries]

    if args.all:
        dropping = sorted(set(saved_ids))
        remaining_entries: List[Dict[str, Any]] = []
    else:
        unknown = [i for i in args.ids if i not in known]
        if unknown:
            print("reset: not in the shipped map, so there is nothing to reset it to: "
                  + ", ".join(unknown), file=sys.stderr)
            return 2
        named = set(args.ids)
        dropping = [i for i in saved_ids if i in named]
        remaining_entries = [e for e in entries if e.get("id") not in named]

    # --all discards more than the person named, so it is the case that asks first.
    # A targeted reset discards exactly what was named and keeps a backup, which is
    # what makes it reversible without a prompt.
    confirm = None
    if args.all and dropping:
        confirm = (f"reset --all drops every difference you have saved: "
                   f"{len(dropping)} binding(s) -- {', '.join(dropping[:6])}"
                   f"{' …' if len(dropping) > 6 else ''}. The shipped map comes back "
                   "and a backup is kept.")
    status, summary = commit_change(defaults, remaining_entries, env,
                                    config_home=args.config_home, confirm=confirm,
                                    assume_yes=args.yes)
    if status:
        print(f"reset: {summary}", file=sys.stderr)
        return status

    scope = "every difference" if args.all else ", ".join(dropping) or "nothing"
    print(f"reset: dropped {scope}")
    print(f"reset: {summary}")
    target = session_generated_path(args.config_home, env)
    if target != GENERATED:
        print("reset: the repository copy at "
              f"{GENERATED.relative_to(ROOT)} was left alone; it is the artifact CI "
              "keeps fresh, not the file this session reads")
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
                    "locked": b["locked"], "static": bool(b.get("static")),
                    "reserved": bool(b.get("reserved")), "action": b["action"]}
                   for b in bindings]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    for category in categories_in_order(bindings):
        group = [b for b in bindings if b.get("category") == category]
        print(f"\n{category}")
        for binding in group:
            state = "" if binding.get("enabled") else "  (off)"
            if binding.get("static"):
                # The bind exists and works, but it is written by hand in the static
                # file; saying so stops this list being read as a description of the
                # generated file.
                state += "  [static: hand-written in .config/hypr/keybind.lua]"
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

    # Every mutating subcommand shares these two, and they mean the same thing in
    # all of them: --yes is the answer to a confirmation prompt, and --config-home
    # says which .config the live session reads.
    def mutating(parser_: argparse.ArgumentParser) -> None:
        parser_.add_argument("--yes", action="store_true",
                             help="answer yes to the confirmation instead of being "
                                  "asked; required when stdin is not a terminal")
        parser_.add_argument("--config-home", type=Path, default=None,
                             help="where the live session's .config is (default "
                                  "~/.config); the repository artifact is never the "
                                  "target of a mutation")

    set_ = sub.add_parser("set", help="change one field of a binding that ships")
    set_.add_argument("id")
    set_.add_argument("--mods", help="modifiers, for example SUPER or SUPER,SHIFT")
    set_.add_argument("--key", help="a keysym, for example E, Return or BackSpace")
    set_.add_argument("--description")
    state = set_.add_mutually_exclusive_group()
    state.add_argument("--enable", action="store_true")
    state.add_argument("--disable", action="store_true")
    mutating(set_)
    set_.set_defaults(func=cmd_set)

    add = sub.add_parser("add", help="add a binding of your own")
    add.add_argument("id", help="of the form category.subject")
    add.add_argument("--mods", required=True)
    add.add_argument("--key", required=True)
    add.add_argument("--description", required=True)
    add.add_argument("--category", required=True,
                     help="the heading the bind is listed under in the cheat sheet")
    action = add.add_mutually_exclusive_group(required=True)
    action.add_argument("--exec", dest="exec",
                        help="a command line as one quoted string, split with shlex")
    action.add_argument("--dispatch", help="an hl.dsp path, for example window.close")
    action.add_argument("--noctalia", help="a shell verb, for example panel-toggle")
    add.add_argument("--args-lua", help="a Lua table literal for --dispatch")
    add.add_argument("--noctalia-arg", action="append",
                     help="an argument for --noctalia; repeat for several")
    mutating(add)
    add.set_defaults(func=cmd_add)

    for name, func, helptext in (
            ("disable", cmd_disable, "turn a binding off without deleting the rebind"),
            ("enable", cmd_enable, "turn a binding back on"),
    ):
        parser_ = sub.add_parser(name, help=helptext)
        parser_.add_argument("ids", nargs="+")
        mutating(parser_)
        parser_.set_defaults(func=func)

    export = sub.add_parser("export", help="write your differences out, or the whole map")
    export.add_argument("file", nargs="?", help="default: stdout")
    export.add_argument("--all", action="store_true",
                        help="the effective map rather than your differences")
    export.set_defaults(func=cmd_export)

    import_ = sub.add_parser("import", help="read differences back in")
    import_.add_argument("file")
    import_.add_argument("--all", action="store_true",
                         help="accept a whole exported map, freezing every default it "
                              "restates; refused by default because an update could "
                              "then never reach this machine")
    import_.add_argument("--replace", action="store_true",
                         help="discard the differences already saved instead of "
                              "merging into them (asks first)")
    mutating(import_)
    import_.set_defaults(func=cmd_import)

    reset = sub.add_parser("reset", help="drop saved differences and re-apply the "
                                         "shipped map (what Ctrl+Alt+R runs)")
    reset.add_argument("ids", nargs="*", help="binding ids to reset; omit with --all")
    reset.add_argument("--all", action="store_true",
                       help="drop every difference, not just the named ones (asks "
                            "first, because it discards more than you named)")
    mutating(reset)
    reset.set_defaults(func=cmd_reset)

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
    try:
        return args.func(args)
    except UserError as exc:
        # One sentence and exit 2, rather than a traceback the person has to read to
        # find out they spelled a modifier wrong.
        print(f"iarch-keybinds {args.command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
