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
    ``Super+Ctrl+Alt`` is a warning: the two workspace moves in it are carried from
    the v1 map and every sensible destination key is already taken, so relocating
    them belongs with the next laying-out of the default map rather than with this
    check -- but the debt is printed every run instead of being quietly accepted.
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
                                f"layer and this is category {category!r}; carried "
                                "from the v1 map, and it should move when the default "
                                "map is next laid out",
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
                                    "data/design/keybinds.json -> rejected, "
                                    "TODO(verify) KB-04",
                                    binding_id, keys))
        elif not _key_is_valid(key, keysyms_lower):
            problems.append(Problem(ERROR, f"{key!r} is not a keysym in the pinned "
                                    "xkbcommon and not a mouse:N or bare keycode",
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
    env = os.environ.copy()
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
    entries = [e for e in (overrides.get("bindings") or ()) if isinstance(e, dict)]
    saved_ids = [e["id"] for e in entries if e.get("id")]

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

    remaining: Dict[str, Any] = {"bindings": remaining_entries} if remaining_entries else {}

    # Validate the map the reset would produce, before writing any of it.
    problems = validate(merge(defaults, remaining), ROOT)
    blocking = [p for p in problems if p.severity in (ERROR, CONFLICT)]
    for problem in problems:
        print(problem, file=sys.stderr if problem.severity != WARNING else sys.stdout)
    if blocking:
        print(f"reset: refused; the map this reset would produce has {len(blocking)} "
              "problem(s), and nothing was changed", file=sys.stderr)
        return 1

    target = session_generated_path(args.config_home, env)
    backup = configstore.backup_of(override_path, env) if override_path.is_file() else None
    try:
        if remaining:
            configstore.save("keybinds", remaining, env)
        elif override_path.is_file():
            override_path.unlink()
        source_note = "data/keybinds.default.json"
        if remaining:
            source_note += f" + {override_path}"
        rendered = render_lua(merge(defaults, remaining), ROOT, source_note)
        target.parent.mkdir(parents=True, exist_ok=True)
        configstore.atomic_write(target, rendered)
    except OSError as exc:
        if backup is not None:
            override_path.write_bytes(backup.read_bytes())
            print(f"reset: failed while writing ({exc}); the override was restored "
                  f"from {backup}", file=sys.stderr)
        else:
            print(f"reset: failed while writing ({exc})", file=sys.stderr)
        return 1

    scope = "every difference" if args.all else ", ".join(dropping) or "nothing"
    print(f"reset: dropped {scope}")
    if backup is not None:
        print(f"reset: the override as it was is in {backup}")
    print(f"reset: wrote {target} ({rendered.count('hl.bind(')} binds)")
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

    reset = sub.add_parser("reset", help="drop saved differences and re-apply the "
                                         "shipped map (what Ctrl+Alt+R runs)")
    reset.add_argument("ids", nargs="*", help="binding ids to reset; omit with --all")
    reset.add_argument("--all", action="store_true",
                       help="drop every difference, not just the named ones")
    reset.add_argument("--config-home", type=Path, default=None,
                       help="where the live session's .config is (default ~/.config)")
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
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
