#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""iarch-focus — one switch for "leave me alone", and an honest account of it.

Focus mode does three things, and each one is a mechanism that already exists:

* **Do Not Disturb on**, through the shell's own IPC verb
  ``notification-dnd-set`` (Noctalia v5.4.1, ``src/cli/schema_msg.h``). This is
  the same call the control centre's ``notification`` tile makes, and unlike
  caffeine its state can be read back with ``notification-dnd-status``, which
  prints exactly ``on`` or ``off`` (``src/app/application_ipc.cpp:158-159``).
  ``iarch/cli/iarch_doctor.py`` already parses both, and this tool calls that
  code rather than writing a third parser.
* **Caffeine on**, through ``caffeine-enable``, which holds an idle inhibitor so
  the shell's own ``[idle.behavior.*]`` timers neither dim nor lock nor suspend
  (``src/idle/idle_inhibitor.cpp:175-212``). The handler is idempotent and
  answers ``error: caffeine protocol unavailable`` when neither
  ``zwp_idle_inhibit_manager_v1`` nor logind inhibition is there.
* **Every window that is not focused dimmed**, through the compositor. The value
  is not invented here: ``data/design/tokens.json`` records ``modes.focus`` as
  ``dim_inactive = true`` and ``dim_strength = 0.5``, and 0.5 is Hyprland's own
  default for that leaf (``MS<Float>("decoration:dim_strength", ..., 0.5, {.min =
  0, .max = 1})``, ``src/config/values/ConfigValues.cpp:228`` at v0.57.2). This
  profile lowers that default to a whisper -- 0.06 at crystal, 0.08 at frosted,
  0.10 at soft -- and switches dimming off entirely at performance, so focusing
  means handing the compositor its stock value back.

The compositor half goes through ``hyprctl eval`` because that is the only
mechanism this compositor has. ``hyprctl keyword`` cannot be used: nothing
registers a keyword command at v0.57.2 (only a plugin may,
``src/plugins/PluginAPI.cpp:357``), an unregistered request answers
``unknown request`` (``src/ipc/s1/S1.cpp:107``) and hyprctl still exits 0 because
that reply does not start with ``error:`` (``hyprctl/src/main.cpp:283-288``). The
manual says as much -- keyword "will not work if your config provider is lua
(refer to eval)" (``docs/hyprctl.1.rst:36-40``) -- and this session's config is
Lua. So the call is ``hyprctl eval 'hl.config({ decoration = { ... } })'``, the
idiom the same manual gives at :49-57. ``hl.config`` walks the table into dotted
keys, refuses one it does not know with ``unknown config key``, refuses a value
the leaf's parser rejects, and on success schedules exactly the refresh that leaf
declares (``src/config/lua/bindings/LuaBindingsConfigRules.cpp:943-991``); both
dim leaves declare ``REFRESH_WINDOW_STATES`` (``ConfigValues.cpp:227-228``) and an
eval is a dynamic parse (``src/config/lua/ConfigManager.cpp:1326-1328``), so the
dim changes with no reload and no flicker. A failure comes back as a reply
starting with ``error:`` *and* exit 7
(``src/config/lua/ConfigManager.cpp:900-918``), which is what makes it checkable.

**Focus mode is runtime state, and this tool says so instead of implying
otherwise.** It writes no file. The dim lives in the compositor until something
reloads the config -- ``hyprctl reload``, ``iarch-theme apply``, ``iarch-anim
set``, a relogin -- at which point the generated ``glass.lua`` puts the
intensity's own dim values back. Do Not Disturb and caffeine live in the shell
and die with it. ``iarch-focus status`` therefore *compares* the record with what
the shell and the compositor actually answer, and reports drift rather than
repeating what it wrote earlier; when focus mode is off it compares against the
dim values the current intensity renders, which is how it can tell "off" from
"off, but the compositor is still dimming at 0.5".

What it cannot do:

* **Caffeine has no status verb.** ``schema_msg.h`` registers enable, disable and
  toggle and nothing that reports the state, so ``off`` disables caffeine
  outright: a caffeine you had on before focusing is off afterwards. ``--no-
  caffeine`` leaves it alone entirely, and the report says which happened.
* **It does not quiet the shell's own continuous motion.** The media visualizer
  follows ``intensity.motion.enabled``, which belongs to the theme; ``iarch-
  gamemode`` is the switch that turns it off.
* **It does not survive a relogin.** Nothing is written to disk, so a new session
  starts unfocused. That is deliberate: a mode that silently re-armed itself at
  login would suppress notifications nobody asked it to suppress.

Usage:
    python3 iarch/cli/iarch_focus.py status
    python3 iarch/cli/iarch_focus.py on
    python3 iarch/cli/iarch_focus.py off
    python3 iarch/cli/iarch_focus.py toggle

Every subcommand takes ``--no-caffeine``, ``--dry-run`` and ``--json``; ``off``
also takes ``--forget``, which clears a record it cannot honour instead of
applying it. There is no ``--config-home`` and no ``--no-reload``: this tool
writes no file and asks for no reload.

Exit codes: 0 on success, 1 when the compositor or the shell refused and the
change was undone, 2 on a usage or data error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore, modes  # noqa: E402  (repo-root import by design)
from iarch.cli import iarch_doctor as doctor  # noqa: E402
from iarch.cli import theme as theme_cli  # noqa: E402

MODE = "focus"
TOOL = "iarch-focus"

EXIT_OK = modes.EXIT_OK
EXIT_REFUSED = modes.EXIT_REFUSED
EXIT_USAGE = modes.EXIT_USAGE

# A leaf's value lives in the tokens under the leaf's own last segment, so the
# tokens stay the single source of truth: `decoration:dim_strength` is set from
# `modes.focus.dim_strength` and a leaf with no recorded value is refused rather
# than guessed at.
CAFFEINE_ENABLE = ("caffeine-enable",)
CAFFEINE_DISABLE = ("caffeine-disable",)


class FocusError(RuntimeError):
    """A usage or data problem: nothing was changed."""


# ---------------------------------------------------------------- the lua call


def _is_lua_name(text: str) -> bool:
    return bool(text) and (text[0].isalpha() or text[0] == "_") and all(
        character.isalnum() or character == "_" for character in text)


def lua_string(text: str) -> str:
    """A Lua string literal, quoted and escaped.

    Only needed for a table key that is not a Lua name. No leaf this repository
    records has one -- ``leaf_tree`` already turns ``-`` into ``_`` the way
    ``luaConfigValueName`` does -- so this is the branch that keeps a general
    formatter from crashing rather than a path a mode reaches today.
    """
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def lua_value(value: Any) -> str:
    """A JSON scalar as a Lua literal, refusing anything Lua cannot hold here."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # repr() is the shortest string that round-trips, and Lua reads both
        # `0.5` and `1e-05` as numbers.
        return repr(float(value))
    raise FocusError(f"{value!r} is not a number or a boolean, so it cannot be set "
                     "through hl.config")


def lua_table(tree: Dict[str, Any]) -> str:
    """A nested Lua table literal, keys sorted so the string is reproducible."""
    parts: List[str] = []
    for key in sorted(tree):
        value = tree[key]
        rendered = lua_table(value) if isinstance(value, dict) else lua_value(value)
        name = key if _is_lua_name(key) else f"[{lua_string(key)}]"
        parts.append(f"{name} = {rendered}")
    return "{ " + ", ".join(parts) + " }"


def leaf_tree(values: Dict[str, Any]) -> Dict[str, Any]:
    """``{"decoration:dim_strength": 0.5}`` as the nested table ``hl.config`` walks.

    ``hl.config`` joins each level with a dot and looks the result up in the
    compositor's value map (``LuaBindingsConfigRules.cpp:955-975``), which is keyed
    the same way -- ``luaConfigValueName`` replaces ``:`` with ``.`` and ``-`` with
    ``_`` (``src/config/lua/ConfigManager.cpp:1114-1119``).
    """
    tree: Dict[str, Any] = {}
    for leaf, value in values.items():
        parts = leaf.replace(":", ".").replace("-", "_").split(".")
        node = tree
        for part in parts[:-1]:
            existing = node.setdefault(part, {})
            if not isinstance(existing, dict):
                raise FocusError(f"{leaf!r} collides with a value already set for {part!r}")
            node = existing
        node[parts[-1]] = value
    return tree


def eval_code(values: Dict[str, Any]) -> str:
    """The Lua source ``hyprctl eval`` is asked to run."""
    return f"hl.config({lua_table(leaf_tree(values))})"


# ---------------------------------------------------------------- the tokens


def focus_tokens(tokens: Dict[str, Any]) -> Dict[str, Any]:
    """``modes.focus``, with each recorded leaf matched to its recorded value."""
    focus = modes.tokens_modes(tokens)["focus"]
    values: Dict[str, Any] = {}
    for leaf in focus["leaves"]:
        key = leaf.split(":")[-1]
        if key not in focus:
            raise FocusError(f"modes.focus.leaves names {leaf!r} but the tokens record no "
                             f"{key!r} value for it, so there is nothing to apply")
        values[leaf] = focus[key]
    return {"leaves": list(focus["leaves"]), "values": values,
            "note": focus.get("_note", "")}


def intensity_dim(tokens: Dict[str, Any], intensity: str) -> Dict[str, Any]:
    """The dim values the current intensity renders, for comparing when focus is off."""
    window = tokens["intensities"][intensity]["window"]
    return {
        "decoration:dim_inactive": bool(window["dim_inactive"]),
        "decoration:dim_strength": float(window["dim_strength"]),
    }


# ---------------------------------------------------------------- one part


def _record_check(report: Dict[str, Any], what: str, expected: Any, actual: Any,
                  detail: str, verdict: str) -> Dict[str, Any]:
    entry = {"check": what, "expected": expected, "actual": actual,
             "verdict": verdict, "detail": detail}
    report["checks"].append(entry)
    if verdict == modes.MATCHES:
        modes.say(f"  verified:    {what} = {_show(actual)}")
    elif verdict == modes.DIFFERS:
        modes.warn(f"{what} is {detail}")
    else:
        modes.warn(f"{what} could not be checked: {detail}")
    return entry


def _show(value: Any) -> str:
    if value is None:
        return "no answer"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def read_leaves(leaves: Sequence[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Read each leaf back; returns ``(values, replies)`` with ``None`` where unread."""
    values: Dict[str, Any] = {}
    replies: Dict[str, Any] = {}
    for leaf in leaves:
        value, reply = modes.getoption(leaf)
        values[leaf] = value
        replies[leaf] = reply.as_dict() if reply is not None else None
    return values, replies


def apply_leaves(values: Dict[str, Any], report: Dict[str, Any],
                 label: str) -> Tuple[bool, Optional[modes.Reply]]:
    """Set the leaves in one ``hl.config`` call, so they change together or not at all.

    TODO(verify) MODE-02 in docs/UNVERIFIED.md: the call, the refresh both leaves
    declare and the exact Lua string are all verified against the pinned release
    and asserted by tests/test_focus.py, but no dim has ever been seen.
    """
    code = eval_code(values)
    command = (modes.HYPRCTL, "eval", code)
    report["steps"].append({"tool": "hyprctl", "argv": list(command), "label": label,
                            "lua": code})
    modes.say(f"  compositor:  hyprctl eval '{code}'")
    reply = modes.run(command)
    if reply is None:
        report["skipped"].append(" ".join(command[:2]) + f" ({modes.HYPRCTL} not on PATH)")
        modes.warn(f"{modes.HYPRCTL} not found on PATH; the dim was not set and could not "
                   "be read (is the session running?)")
        return False, None
    report["ran"].append(" ".join(command[:2]))
    if reply.ok:
        return True, reply
    # An eval that fails leaves its errors in the compositor's list, so the report
    # carries what the compositor said about it rather than only the reply line.
    report.setdefault("configerrors", {})["after_failed_eval"] = modes.configerrors()
    modes.warn(f"`hyprctl eval` did not answer ok (exit {reply.returncode}): "
               f"{reply.text or 'no reply'}")
    return False, reply


# ---------------------------------------------------------------- subcommands


def _previous(env: Dict[str, str], report: Dict[str, Any], leaves: Sequence[str],
              target: Dict[str, Any]) -> Dict[str, Any]:
    """Read the state focus mode is about to replace."""
    dnd, dnd_reply = doctor.dnd_status()
    values, replies = read_leaves(leaves)
    report["before"] = {"do_not_disturb": dnd,
                        "do_not_disturb_reply": dnd_reply.as_dict() if dnd_reply else None,
                        "leaves": values, "leaf_replies": replies}
    modes.say(f"  before:      do not disturb {_show(dnd)}, "
              + ", ".join(f"{leaf.split(':')[-1]} {_show(value)}"
                          for leaf, value in values.items()))
    return {"do_not_disturb": dnd, "leaves": values}


def cmd_on(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    tokens = modes.load_tokens()
    focus = focus_tokens(tokens)
    leaves, target = focus["leaves"], focus["values"]
    record = modes.mode_state(env, MODE)
    already = bool(record.get("active"))

    report["target"] = {"do_not_disturb": True, "caffeine": not args.no_caffeine,
                        "leaves": target}
    report["active"] = True
    modes.say(f"iArch by Safari — focus mode {'still on' if already else 'on'}")

    previous = _previous(env, report, leaves, target)
    if already:
        # The state read now is the state focus mode itself wrote, so keeping the
        # recorded restore point is the only way `off` can still undo anything.
        recorded = record.get("previous")
        if isinstance(recorded, dict):
            previous = {"do_not_disturb": recorded.get("do_not_disturb"),
                        "leaves": recorded.get("leaves") or previous["leaves"]}
        report["notes"].append("focus mode was already recorded as on, so the previous "
                               "state on record was kept rather than replaced")

    if args.dry_run:
        report["dry_run"] = True
        report["previous"] = previous
        # Listed in the order it would really be sent: the compositor first,
        # because that is the half that can refuse a value, and refusing early
        # means there is nothing to undo.
        modes.say(f"[dry-run] would send `hyprctl eval '{eval_code(target)}'`, "
                  f"`noctalia msg notification-dnd-set on`"
                  + (", and `noctalia msg caffeine-enable`" if not args.no_caffeine
                     else ", and would leave caffeine alone")
                  + "; nothing was sent")
        return EXIT_OK

    # The compositor first: it is the half that can refuse a value, and refusing
    # before anything else changed means there is nothing to undo.
    applied, reply = apply_leaves(target, report, "apply the focus dim")
    if reply is not None and not applied:
        report["ok"] = False
        report["error"] = ("the compositor refused the dim, so Do Not Disturb and caffeine "
                           "were left alone")
        report["exit"] = EXIT_REFUSED
        return EXIT_REFUSED

    dnd_answer = doctor.dnd_set(True)
    report["steps"].append({"tool": doctor.NOCTALIA_BIN, "verb": "notification-dnd-set on",
                            "reply": dnd_answer.as_dict() if dnd_answer else None})
    if dnd_answer is None:
        modes.warn(f"{doctor.NOCTALIA_BIN} not found on PATH; Do Not Disturb was not set "
                   "and could not be read")
    elif dnd_answer.ok:
        modes.say("  shell:       Do Not Disturb on")
    else:
        modes.warn(f"`notification-dnd-set on` did not answer ok: "
                   f"{dnd_answer.error_text or f'exit {dnd_answer.returncode}'}")
        # The shell refused, so undo the dim and stop *before* enabling caffeine: a
        # caffeine nobody asked for would be the one part of this half-applied mode
        # that nothing records and nothing switches back off.
        restore = {leaf: value for leaf, value in previous["leaves"].items()
                   if value is not None}
        if restore:
            apply_leaves(restore, report, "undo the focus dim")
        report["rollback"] = {"reason": "notification-dnd-set on was refused",
                              "leaves_restored": sorted(restore),
                              "caffeine_sent": False}
        report["ok"] = False
        report["error"] = ("the shell refused Do Not Disturb, so the dim was put back and "
                           "focus mode was not recorded as on")
        modes.warn("the dim was put back and caffeine was never enabled, so the session is "
                   "as it was and nothing was recorded")
        report["exit"] = EXIT_REFUSED
        return EXIT_REFUSED

    caffeine: Optional[Any] = None
    if args.no_caffeine:
        report["skipped"].append("caffeine-enable (--no-caffeine)")
        modes.say("  shell:       caffeine left alone (--no-caffeine)")
    else:
        caffeine = modes.noctalia_msg(*CAFFEINE_ENABLE)
        report["steps"].append({"tool": modes.NOCTALIA_BIN, "verb": CAFFEINE_ENABLE[0],
                                "reply": caffeine.as_dict() if caffeine else None})
        # TODO(verify) MODE-03 in docs/UNVERIFIED.md: the reply is the only
        # evidence caffeine exists, because upstream registers no verb that reports
        # the state -- so "ok" here means "the handler did not refuse", not "an
        # inhibitor is held".
        if caffeine is None:
            modes.warn(f"{modes.NOCTALIA_BIN} not found on PATH; caffeine was not enabled")
        elif caffeine.ok:
            modes.say("  shell:       caffeine on (idle and sleep held off)")
        else:
            modes.warn(f"`{CAFFEINE_ENABLE[0]}` did not answer ok: "
                       f"{caffeine.text or f'exit {caffeine.returncode}'}")

    report["applied"] = True
    _verify(report, tokens, leaves, target, expect_dnd=True)
    report["previous"] = previous
    payload: Dict[str, Any] = {"active": True, "previous": previous}
    if args.no_caffeine:
        payload["no_caffeine"] = True
    path, changed = modes.write_mode(env, MODE, payload)
    report["settings"] = {"path": _display(path), "changed": changed}
    modes.say(f"  settings: {'recorded' if changed else 'already recorded'} modes.focus in "
              f"{_display(path)}")
    for note in _limitations(args, caffeine):
        report["notes"].append(note)
        modes.say(f"  note:        {note}")
    modes.say(_closing(report, "on", " It is runtime state: a reload, a relogin or an "
                                     "`iarch-theme apply` ends the dim, and `iarch-focus "
                                     "status` will say so."))
    return modes.exit_for_verdict(
        report, "focus mode was applied but the session does not run it",
        keep="the dim, Do Not Disturb and the record")


def _limitations(args: argparse.Namespace, caffeine: Optional[Any]) -> List[str]:
    notes: List[str] = []
    if args.no_caffeine:
        notes.append("caffeine was left alone, so the shell's idle timers still run; "
                     "the screen can still dim and lock while focusing")
    else:
        notes.append("the shell has no verb that reports caffeine, so its state is taken "
                     "from the reply and cannot be read back; `iarch-focus off` disables it "
                     "outright, including a caffeine you had on before focusing")
    if caffeine is not None and not caffeine.ok:
        notes.append(f"caffeine-enable answered {caffeine.text or caffeine.returncode!r}, "
                     "so idle and sleep may not be held off")
    return notes


def cmd_off(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    tokens = modes.load_tokens()
    focus = focus_tokens(tokens)
    leaves = focus["leaves"]
    record = modes.mode_state(env, MODE)
    previous = record.get("previous") if isinstance(record.get("previous"), dict) else None
    report["record"] = record
    report["active"] = False

    if args.forget:
        if not record:
            modes.say("iArch by Safari — focus mode off")
            modes.say("  nothing recorded: modes.focus is not in settings.json")
            return EXIT_OK
        path, changed = modes.write_mode(env, MODE, {"active": False})
        report["settings"] = {"path": _display(path), "changed": changed}
        report["notes"].append("--forget cleared the record without sending anything")
        modes.say("iArch by Safari — focus mode record forgotten")
        modes.say(f"  settings: modes.focus cleared in {_display(path)}; nothing was sent "
                  "to the shell or the compositor")
        return EXIT_OK

    modes.say("iArch by Safari — focus mode off")
    if not record.get("active"):
        modes.say("  already off: modes.focus is not recorded as active")
        report["notes"].append("focus mode was not recorded as on, so nothing was restored")
        _verify(report, tokens, leaves, _expected_when_off(tokens, env), expect_dnd=None)
        return EXIT_OK

    if not previous:
        report["ok"] = False
        report["error"] = (
            "modes.focus says focus mode is on but records no previous state, so there is "
            "nothing to restore. `iarch-focus off --forget` clears the record without "
            "sending anything, and `iarch-focus status` shows what the session runs now.")
        report["exit"] = EXIT_USAGE
        modes.warn(report["error"])
        return EXIT_USAGE

    restore_leaves = {leaf: value for leaf, value in (previous.get("leaves") or {}).items()
                      if value is not None}
    unreadable = [leaf for leaf in leaves if leaf not in restore_leaves]
    dnd_before = previous.get("do_not_disturb")
    report["target"] = {"do_not_disturb": dnd_before, "leaves": restore_leaves,
                        "leaves_not_restored": unreadable}

    modes.say(f"  restoring:   do not disturb {_show(dnd_before)}, "
              + (", ".join(f"{leaf.split(':')[-1]} {_show(value)}"
                           for leaf, value in restore_leaves.items()) or "no readable dim"))
    if unreadable:
        modes.warn(f"{', '.join(unreadable)} could not be read before focus mode was "
                   "switched on, so it is left as it is")
        report["notes"].append("a leaf that could not be read before cannot be restored "
                               "after: " + ", ".join(unreadable))
    if dnd_before is None:
        modes.warn("Do Not Disturb could not be read before focus mode was switched on, so "
                   "it is being turned off rather than restored")
        report["notes"].append("the prior Do Not Disturb state was never read, so off means "
                               "off rather than whatever it was")

    if args.dry_run:
        report["dry_run"] = True
        modes.say("[dry-run] would send "
                  + (f"`hyprctl eval '{eval_code(restore_leaves)}'`, " if restore_leaves
                     else "no compositor call, ")
                  + f"`noctalia msg notification-dnd-set {'on' if dnd_before else 'off'}`"
                  + (", and `noctalia msg caffeine-disable`" if not args.no_caffeine
                     else ", and would leave caffeine alone")
                  + "; nothing was sent")
        return EXIT_OK

    if restore_leaves:
        applied, reply = apply_leaves(restore_leaves, report, "restore the previous dim")
        if reply is not None and not applied:
            report["ok"] = False
            report["error"] = ("the compositor refused to put the previous dim back, so the "
                               "shell half was left alone and the record was kept")
            report["exit"] = EXIT_REFUSED
            return EXIT_REFUSED
    else:
        report["skipped"].append("hyprctl eval (no readable dim to restore)")

    dnd_answer = doctor.dnd_set(bool(dnd_before))
    report["steps"].append({"tool": doctor.NOCTALIA_BIN,
                            "verb": f"notification-dnd-set {'on' if dnd_before else 'off'}",
                            "reply": dnd_answer.as_dict() if dnd_answer else None})
    if dnd_answer is None:
        modes.warn(f"{doctor.NOCTALIA_BIN} not found on PATH; Do Not Disturb was not "
                   "restored")
    elif dnd_answer.ok:
        modes.say(f"  shell:       Do Not Disturb {'on' if dnd_before else 'off'}")
    else:
        modes.warn(f"`notification-dnd-set` did not answer ok: "
                   f"{dnd_answer.error_text or f'exit {dnd_answer.returncode}'}")

    if args.no_caffeine or record.get("no_caffeine"):
        report["skipped"].append("caffeine-disable (--no-caffeine)")
        modes.say("  shell:       caffeine left alone (--no-caffeine)")
    else:
        caffeine = modes.noctalia_msg(*CAFFEINE_DISABLE)
        report["steps"].append({"tool": modes.NOCTALIA_BIN, "verb": CAFFEINE_DISABLE[0],
                                "reply": caffeine.as_dict() if caffeine else None})
        if caffeine is None:
            modes.warn(f"{modes.NOCTALIA_BIN} not found on PATH; caffeine was not disabled")
        elif caffeine.ok:
            modes.say("  shell:       caffeine off")
            note = ("caffeine was disabled outright: the shell has no verb that reports it, "
                    "so a caffeine that was already on before focusing is off now")
            report["notes"].append(note)
            modes.say(f"  note:        {note}")
        else:
            modes.warn(f"`{CAFFEINE_DISABLE[0]}` did not answer ok: "
                       f"{caffeine.text or f'exit {caffeine.returncode}'}")

    report["applied"] = True
    _verify(report, tokens, leaves, restore_leaves or _expected_when_off(tokens, env),
            expect_dnd=bool(dnd_before))
    path, changed = modes.write_mode(env, MODE, {"active": False})
    report["settings"] = {"path": _display(path), "changed": changed}
    modes.say(f"  settings: {'cleared' if changed else 'already cleared'} modes.focus in "
              f"{_display(path)}")
    for note in report["notes"][-2:]:
        if note.startswith("a leaf that could not be read") or note.startswith(
                "the prior Do Not Disturb"):
            modes.say(f"  note:        {note}")
    modes.say(_closing(report, "off"))
    return modes.exit_for_verdict(
        report, "the previous state was sent but the session does not run it",
        keep="the session and the cleared record")


def _current_intensity(tokens: Dict[str, Any], env: Dict[str, str]) -> str:
    """The intensity the theme tool would itself resolve, and render the dim from.

    A settings file that cannot be read is not this command's error to report --
    ``iarch-theme`` owns that message -- so the tokens' default intensity is what
    a broken or missing file falls back to here, and the comparison says which it
    used.
    """
    try:
        _tokens, _preset, _colour, intensity = theme_cli._resolve(None, None, env)
    except (theme_cli.ThemeError, configstore.ConfigError, OSError, ValueError):
        return str(tokens.get("default_intensity", "frosted"))
    return intensity


def _expected_when_off(tokens: Dict[str, Any], env: Dict[str, str]) -> Dict[str, Any]:
    """The dim the current intensity renders, which is what an unfocused session runs."""
    return intensity_dim(tokens, _current_intensity(tokens, env))


def cmd_toggle(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    """On when off, off when on, filling in the same report either half would."""
    active = modes.is_active(env, MODE)
    report["toggled_from"] = active
    report["command"] = f"toggle ({'off' if active else 'on'})"
    return cmd_off(args, env, report) if active else cmd_on(args, env, report)


def cmd_status(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    """Report the record and the session, and always exit 0.

    A status command that exits non-zero because the session disagrees would be
    indistinguishable from one that could not run, and its siblings --
    ``iarch-theme current`` (theme.py:594) and ``iarch-anim current``
    (iarch_anim.py:827) -- both exit 0 whatever they find. The disagreement is in
    the prose and in ``report["verdict"]``, which is what a script should read.
    """
    tokens = modes.load_tokens()
    focus = focus_tokens(tokens)
    leaves = focus["leaves"]
    record = modes.mode_state(env, MODE)
    active = bool(record.get("active"))
    previous = record.get("previous") if isinstance(record.get("previous"), dict) else {}
    expected = focus["values"] if active else _expected_when_off(tokens, env)

    report["record"] = record
    report["active"] = active
    report["previous"] = previous
    report["target"] = {"leaves": expected,
                        "do_not_disturb": True if active else None}
    report["settings"] = {"path": _display(configstore.user_path(modes.SETTINGS_NAME, env))}

    modes.say("iArch by Safari — focus mode status")
    modes.say(f"  recorded:      {'on' if active else 'off'}")
    if active and previous:
        modes.say(f"  saved state:   do not disturb {_show(previous.get('do_not_disturb'))}, "
                  + ", ".join(f"{leaf.split(':')[-1]} {_show(value)}"
                              for leaf, value in (previous.get("leaves") or {}).items()))
    shown = ", ".join(f"{leaf.split(':')[-1]} {_show(value)}" for leaf, value in expected.items())
    if active:
        modes.say(f"  expected now:  {shown} (modes.focus in the tokens)")
    else:
        intensity = _current_intensity(tokens, env)
        modes.say(f"  expected now:  {shown} (what the {intensity} intensity renders, so "
                  "this is how a dim left behind shows up)")

    dnd, dnd_reply = doctor.dnd_status()
    report["do_not_disturb"] = dnd
    report["do_not_disturb_reply"] = dnd_reply.as_dict() if dnd_reply else None
    if active:
        _record_check(report, "do not disturb", True, dnd,
                      "off, but focus mode is recorded as on" if dnd is False
                      else ("on" if dnd else "the shell could not be asked"),
                      modes.MATCHES if dnd is True
                      else (modes.DIFFERS if dnd is False else modes.UNVERIFIED))
    else:
        modes.say(f"  shell:         do not disturb {_show(dnd)}")

    values, replies = read_leaves(leaves)
    report["leaves"] = values
    report["leaf_replies"] = replies
    for leaf in leaves:
        want, actual = expected.get(leaf), values[leaf]
        reply = replies[leaf]
        if reply is None:
            verdict, detail = modes.UNVERIFIED, f"{modes.HYPRCTL} is not on PATH"
        elif actual is None:
            verdict = modes.UNVERIFIED
            detail = (f"the compositor answered {reply['stdout']!r}" if reply.get("stdout")
                      else "`hyprctl getoption` gave no usable answer")
        elif modes.same_value(want, actual):
            verdict, detail = modes.MATCHES, f"{_show(actual)} as expected"
        else:
            verdict = modes.DIFFERS
            detail = (f"{_show(actual)}, expected {_show(want)}"
                      + (" — focus mode is recorded as on but the compositor is not "
                         "dimming, which is what a reload does" if active else
                         " — focus mode is recorded as off but the compositor is still "
                         "dimming at the focus value"))
        _record_check(report, leaf, want, actual, detail, verdict)

    # TODO(verify) MODE-04 in docs/UNVERIFIED.md: this comparison is how the drift
    # a reload causes is meant to surface, and tests/test_focus.py proves the
    # comparison; nobody has watched the sequence on a real desktop.
    verdict = modes.overall_verdict(report["checks"])
    report["verdict"] = verdict
    if verdict == modes.MATCHES:
        modes.say(f"  focus mode is {'on' if active else 'off'} and the session agrees")
    elif verdict == modes.DIFFERS:
        modes.say(f"  focus mode is recorded {'on' if active else 'off'} and the session "
                  "disagrees; `iarch-focus on` re-applies it and `off --forget` clears a "
                  "record that no longer describes anything")
    else:
        modes.say(f"  focus mode is recorded {'on' if active else 'off'}; the session did "
                  "not answer for everything above, so this is unverified rather than "
                  "confirmed")
    report["exit"] = EXIT_OK
    return EXIT_OK


# ---------------------------------------------------------------- verification


def _verify(report: Dict[str, Any], tokens: Dict[str, Any], leaves: Sequence[str],
            expected: Dict[str, Any], expect_dnd: Optional[bool]) -> None:
    """Compare what the session now answers with what was just asked for."""
    if expect_dnd is not None:
        dnd, reply = doctor.dnd_status()
        if reply is None:
            _record_check(report, "do not disturb", expect_dnd, dnd,
                          f"{doctor.NOCTALIA_BIN} is not on PATH", modes.UNVERIFIED)
        elif dnd == expect_dnd:
            _record_check(report, "do not disturb", expect_dnd, dnd,
                          _show(dnd), modes.MATCHES)
        else:
            _record_check(report, "do not disturb", expect_dnd, dnd,
                          f"{_show(dnd)}, expected {_show(expect_dnd)}",
                          modes.DIFFERS if dnd is not None else modes.UNVERIFIED)
    values, replies = read_leaves(leaves)
    report["leaves"] = values
    report["leaf_replies"] = replies
    for leaf in leaves:
        want, actual = expected.get(leaf), values[leaf]
        reply = replies[leaf]
        if leaf not in expected:
            # A leaf whose value before focus mode was never read is a leaf this run
            # deliberately left alone, so it has no expected value to differ from.
            # Reporting it as a difference would blame the session for the one thing
            # the tool told the person it could not do.
            _record_check(report, leaf, None, actual,
                          "left as it is: its value before focus mode was never read, so "
                          "there was nothing to restore", modes.UNVERIFIED)
        elif reply is None:
            _record_check(report, leaf, want, actual, f"{modes.HYPRCTL} is not on PATH",
                          modes.UNVERIFIED)
        elif actual is None:
            _record_check(report, leaf, want, actual,
                          (f"the compositor answered {reply['stdout']!r}"
                           if reply.get("stdout") else "no usable answer"),
                          modes.UNVERIFIED)
        elif modes.same_value(want, actual):
            _record_check(report, leaf, want, actual, _show(actual), modes.MATCHES)
        else:
            _record_check(report, leaf, want, actual,
                          f"{_show(actual)}, expected {_show(want)}", modes.DIFFERS)
    report["verdict"] = modes.overall_verdict(report["checks"])


def _closing(report: Dict[str, Any], state: str, tail: str = "") -> str:
    """The last line a person reads, phrased by what was actually confirmed.

    "focus mode is on" is a claim about a session, not about a record, so it is
    only said plainly when the session was asked and agreed. A verdict this tool
    could not reach has to sound like one: the difference between "on" and "on as
    far as this tool could tell" is the whole point of reading the leaves back.
    """
    verdict = report.get("verdict")
    if verdict == modes.MATCHES:
        return f"focus mode is {state} and the session agrees.{tail}"
    if verdict == modes.DIFFERS:
        return (f"focus mode is recorded {state} but the session does not run it; "
                "`iarch-focus status` shows which part differs.")
    return (f"focus mode is {state} as far as this tool could tell: the session did not "
            f"answer for everything, so nothing above is confirmed.{tail}")


def _display(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL, description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--no-caffeine", action="store_true",
                        help="leave the shell's idle inhibitor alone, for a caffeine you "
                             "switched on yourself and want to keep")
        sp.add_argument("--dry-run", action="store_true",
                        help="report what would be sent and what is recorded now; send "
                             "nothing and change no settings")
        sp.add_argument("--json", action="store_true",
                        help="print one machine-readable object instead of prose")

    for name, help_text, func in (
            ("status", "what is recorded, and what the shell and compositor answer now",
             cmd_status),
            ("on", "Do Not Disturb, caffeine and a dimmed background, saving what they were",
             cmd_on),
            ("toggle", "on when off, off when on", cmd_toggle)):
        sub_parser = sub.add_parser(name, help=help_text)
        common(sub_parser)
        sub_parser.set_defaults(func=func, forget=False)

    off_parser = sub.add_parser(
        "off", help="restore the Do Not Disturb flag and the dim that were saved")
    common(off_parser)
    off_parser.add_argument("--forget", action="store_true",
                            help="clear the record without sending anything, for a record "
                                 "that cannot be honoured")
    off_parser.set_defaults(func=cmd_off)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    modes.set_json_mode(bool(args.json))
    env = os.environ
    report = modes.new_report(getattr(args, "command", "?"), MODE)
    report["tool"] = TOOL
    args.report = report
    try:
        code = args.func(args, env, report)
    except (FocusError, modes.ModeError, configstore.ConfigError, OSError) as exc:
        report.update(ok=False, error=str(exc), exit=EXIT_USAGE)
        modes.emit(report)
        if not args.json:
            print(f"{TOOL}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    report["ok"] = code == EXIT_OK
    report["exit"] = code
    modes.emit(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
