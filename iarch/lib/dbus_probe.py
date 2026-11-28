# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Who owns a name on the session bus, and which process is behind it.

Purpose
    Two shells must not both run a notification server, and the only way to know
    which one won is to ask the bus who owns ``org.freedesktop.Notifications`` and
    then ask which pid that owner is. This module is those two questions and
    nothing else; it never claims a name, never releases one and never sends a
    notification.

Inputs
    A bus name, and an injectable runner. The default asks ``dbus-send`` on the
    session bus.

Outputs
    ``BusOwner``: the unique name (``:1.42``), the pid behind it when the bus will
    say, whether the lookup happened at all, and a note when it did not. A lookup
    that could not run says so — an empty result from a probe that never ran is not
    evidence that no server is registered.

Dependencies
    ``iarch.lib.runner``. The two methods used are the standard ones every session
    bus implements: ``org.freedesktop.DBus.GetNameOwner`` and
    ``org.freedesktop.DBus.GetConnectionUnixProcessID``.
    TODO(verify) ENG-05 in docs/UNVERIFIED.md: neither call could be made from the
    development sandbox, which has no bus and no ``dbus-send``, so the reply
    parsing below is written against the documented reply shapes and marked
    unverified rather than asserted to work.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from iarch.lib import runner as default_runner
from iarch.lib.runner import Answer, Runner

DBUS_SEND_BIN = "dbus-send"
BUS_OBJECT = "/org/freedesktop/DBus"
BUS_INTERFACE = "org.freedesktop.DBus"
DBUS_TIMEOUT_SECONDS = 10.0

NOTIFICATION_BUS_NAME = "org.freedesktop.Notifications"

#: ``string ":1.42"`` and ``uint32 1234`` are the two reply shapes parsed here.
_UNIQUE_NAME = re.compile(r'string\s+"(:[\d.A-Za-z_-]+)"')
_UNIX_PID = re.compile(r'uint32\s+(\d+)')


@dataclass(frozen=True)
class BusOwner:
    """What the bus said about one well-known name."""

    name: str
    unique_name: Optional[str] = None
    pid: Optional[int] = None
    searched: bool = False
    note: Optional[str] = None
    answer: Optional[Answer] = None

    @property
    def owned(self) -> bool:
        return self.unique_name is not None

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "unique_name": self.unique_name, "pid": self.pid,
                "searched": self.searched, "note": self.note}


def _call(method: str, argument: str, run: Runner) -> Optional[Answer]:
    """One ``dbus-send`` call for its printed reply."""
    return run((DBUS_SEND_BIN, "--session", "--print-reply",
                f"--dest={BUS_INTERFACE}", BUS_OBJECT,
                f"{BUS_INTERFACE}.{method}", argument), DBUS_TIMEOUT_SECONDS)


def owner_of(name: str, run: Optional[Runner] = None) -> BusOwner:
    """The unique name holding ``name`` on the session bus, and its pid if stated."""
    execute = run or default_runner.run
    answer = _call("GetNameOwner", f"string:{name}", execute)
    if answer is None:
        return BusOwner(name, searched=False,
                        note=f"{DBUS_SEND_BIN} is not installed, so the session bus was not asked")
    if answer.timed_out or not answer.ok:
        # A name nobody owns makes GetNameOwner exit non-zero with
        # org.freedesktop.DBus.Error.NameHasNoOwner; that is an answer, not a failure
        # to ask, and it is reported as "not owned" rather than as "not searched".
        text = (answer.stderr or "") + (answer.stdout or "")
        if "NameHasNoOwner" in text:
            return BusOwner(name, searched=True, note="no process owns this name",
                            answer=answer)
        return BusOwner(name, searched=False, note=answer.describe(), answer=answer)
    match = _UNIQUE_NAME.search(answer.stdout)
    if match is None:
        # A successful but malformed reply does not prove the name is free.
        return BusOwner(name, searched=False, note="the bus answered without a unique name",
                        answer=answer)
    unique = match.group(1)
    pid_answer = _call("GetConnectionUnixProcessID", f"string:{unique}", execute)
    pid: Optional[int] = None
    if pid_answer is not None and pid_answer.ok:
        pid_match = _UNIX_PID.search(pid_answer.stdout)
        if pid_match:
            pid = int(pid_match.group(1))
    return BusOwner(name, unique_name=unique, pid=pid, searched=True,
                    note=None if pid is not None else "the bus did not state a process id",
                    answer=answer)


def notification_server(run: Optional[Runner] = None) -> BusOwner:
    """Who is running the desktop notification server right now."""
    return owner_of(NOTIFICATION_BUS_NAME, run=run)
