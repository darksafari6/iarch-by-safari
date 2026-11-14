# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""What the compositor is doing right now, and what it refuses.

Everything here composes :mod:`iarch.lib.modes`, which already knows the four
things a caller has to get right about ``hyprctl`` and which this module does not
restate:

* an **exit code is not a verdict**. An unregistered subcommand exits 0; only a
  reply that starts with ``error:`` exits 7. So a probe reads the reply text;
* ``getoption`` on a leaf the compositor does not have answers the literal
  ``no such option`` even under ``-j``, which is not JSON. That is *the compositor
  does not have this leaf*, and it is a different answer from *the compositor was
  not running*. Both come back as ``None`` from :func:`modes.getoption`, and the
  reply is attached so the two stay distinguishable;
* a **missing binary is unverified**, never a failure;
* ``configerrors`` is read as lines, not as JSON, the way ``iarch_anim.py`` reads
  it: empty output is a configuration the compositor parsed cleanly, ``None`` is
  no answer at all.

What this module adds is the two questions the settings pages ask that the mode
switches never needed: what monitors are connected (:func:`monitors`), and whether
this process is talking to a session at all (:func:`session_signature`).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .. import paths
from . import runner

SIGNATURE_VARIABLE = "HYPRLAND_INSTANCE_SIGNATURE"
"""The environment variable the compositor sets in every child it spawns.

Its presence is what makes a probe meaningful: ``hyprctl`` on PATH in a chroot, a
container or an X11 session is a binary with nothing to talk to, and its reply
would be a socket error rather than an answer about this desktop.
"""

CONFIGERRORS = "configerrors"
RELOAD = "reload"
MONITORS = "monitors"


class HyprError(RuntimeError):
    """The compositor answered, and the answer was a refusal."""


def _modes():
    """``iarch.lib.modes``, imported late so this module loads without a checkout."""
    paths.add_repo_to_path()
    from iarch.lib import modes  # noqa: PLC0415

    return modes


def session_signature(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The running session's signature, or ``None`` when there is no session.

    ``None`` means every probe below is unverified, which is the honest state in
    CI and on a machine that is not running this compositor. It is not an error
    and it is not a failure.
    """
    env = os.environ if env is None else env
    value = env.get(SIGNATURE_VARIABLE, "").strip()
    return value or None


def in_session(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when there is a compositor to ask and a client to ask it with."""
    return session_signature(env) is not None and runner.which(runner.HYPRCTL) is not None


def available(env: Optional[Mapping[str, str]] = None) -> str:
    """A one-line description of what can and cannot be asked, for a status page."""
    if session_signature(env) is None:
        return (f"no {SIGNATURE_VARIABLE} in this environment: nothing can be read from "
                "or written to a compositor, so every live value below is unverified")
    if runner.which(runner.HYPRCTL) is None:
        return ("this looks like a compositor session but hyprctl is not on PATH: nothing "
                "can be asked, so every live value below is unverified")
    return "a compositor session is running and hyprctl is on PATH"


# ------------------------------------------------------------------ reading


def get_option(leaf: str) -> Tuple[Optional[Any], str]:
    """Read one config leaf back, as ``(value, verdict)``.

    ``verdict`` is ``ok`` when the compositor answered with a value, ``unverified``
    when it could not be asked, and ``failed`` when it answered that it has no
    such leaf -- which is a real answer about this compositor, not an absence of
    one, and it means the record in ``data/design/tokens.json`` and the installed
    release disagree.
    """
    modes = _modes()
    value, reply = modes.getoption(leaf)
    if value is not None:
        return value, runner.OK
    if reply is None:
        return None, runner.UNVERIFIED
    if "no such option" in (reply.stdout or "").lower():
        return None, runner.FAILED
    if reply.returncode != 0:
        return None, runner.FAILED
    return None, runner.UNVERIFIED


def config_errors() -> Tuple[Optional[List[str]], str]:
    """The compositor's parse errors as ``(lines, verdict)``.

    ``([], ok)`` is a configuration the compositor parsed cleanly, which is what
    the apply pipeline requires after a reload. ``(None, unverified)`` is no
    compositor to ask.
    """
    lines = _modes().configerrors()
    if lines is None:
        return None, runner.UNVERIFIED
    return lines, runner.OK


def reload() -> runner.Outcome:
    """``hyprctl reload``: re-parse the configuration and answer ``ok``.

    Synchronous, which is what makes the verify step after it meaningful -- a leaf
    read after a reload is the state now running, not the state that was running
    when the file was written.
    """
    return runner.run(runner.HYPRCTL, [RELOAD])


def monitors(include_disabled: bool = False) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """The connected outputs, parsed from ``hyprctl -j monitors``.

    ``include_disabled`` adds the literal ``all`` argument, which is the only way
    to see an output a rule has switched off
    (``src/ipc/s1/Commands.cpp:385-386``). A page that offers to turn one back on
    has to ask for it, or the monitor is not in the list being shown.

    Every key of every entry is one ``data/design/monitors.json`` records; nothing
    here invents a field, and a field the installed release does not print is
    simply absent from the dictionary rather than defaulted to a guess.
    """
    argv = ["-j", MONITORS] + (["all"] if include_disabled else [])
    outcome = runner.run(runner.HYPRCTL, argv)
    if not outcome.ran:
        return None, runner.UNVERIFIED
    if not outcome.ok:
        return None, runner.FAILED
    text = outcome.stdout.strip()
    if not text:
        return None, runner.FAILED
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        # The text form is what a compositor too old for -j answers with. Saying
        # so is more useful than an empty list, which would read as "no monitors".
        return None, runner.FAILED
    if not isinstance(document, list):
        return None, runner.FAILED
    return [entry for entry in document if isinstance(entry, dict)], runner.OK


def enabled_monitors() -> Tuple[List[Dict[str, Any]], str]:
    """The outputs that are on, for the Display page's last-monitor guard."""
    entries, verdict = monitors(include_disabled=True)
    if entries is None:
        return [], verdict
    return [entry for entry in entries if not entry.get("disabled")], verdict


# ------------------------------------------------------------------ writing


def eval_leaves(values: Mapping[str, Any]) -> runner.Outcome:
    """Change compositor leaves while the session runs, through ``hl.config``.

    ``hyprctl keyword`` cannot be used: this session's configuration is Lua, and
    the compositor answers a keyword request against a Lua config with
    ``unknown request`` while hyprctl still exits 0. ``hyprctl eval`` is the only
    mechanism, and the Lua source is built by ``iarch.cli.iarch_focus`` -- the
    module that already encodes a leaf name and a scalar into the nested table
    ``hl.config`` walks -- so there is one encoder in this repository rather than
    two that can drift.

    The values are handed over as one argv element. No shell is involved at any
    point, so a leaf name or a number cannot escape into one; and a leaf name that
    is not in the record's table is refused by ``hl.config`` itself, which answers
    ``unknown config key`` as a reply starting with ``error:`` and hyprctl exit 7.
    """
    paths.add_repo_to_path()
    from iarch.cli import iarch_focus  # noqa: PLC0415

    try:
        code = iarch_focus.eval_code(dict(values))
    except iarch_focus.FocusError as exc:
        raise HyprError(str(exc)) from exc
    return runner.run(runner.HYPRCTL, ["eval", code])
