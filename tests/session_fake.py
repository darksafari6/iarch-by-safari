# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""A session that is not there: the fakes every engine and theme pipeline test uses.

Purpose
    The switch, the doctor's shell check and the dynamic apply pipeline all talk to
    a compositor, a shell engine and a session bus. None of the three exists in the
    development sandbox or in CI, and a test that skips when they are missing is a
    test that never runs. This module is the substitute: one process table, one
    command log, one virtual clock, and the three module attributes patched so the
    production code paths run unchanged against them.

Inputs
    Keyword arguments describing the session to pretend to be: which binaries are
    installed, which processes are running, what each command replies, whether a
    spawned process appears in the table, and how the bus answers.

Outputs
    A ``FakeSession`` whose ``run`` and ``spawn`` are passed to the code under test
    as the injectable runner and spawner, whose ``calls`` records every command in
    order, and whose ``clock``/``sleep`` drive a virtual ten-second budget without
    ever waiting.

Dependencies
    ``iarch.lib.runner`` (the ``Answer`` shape and the ``which`` it patches),
    ``iarch.lib.processes`` (the ``is_alive`` and ``_signal`` it patches), and the
    standard library. It imports no test module and asserts nothing itself.
"""
from __future__ import annotations

import contextlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from unittest import mock

from iarch.lib import processes, runner
from iarch.lib.runner import Answer

#: What a session has installed unless a test says otherwise. Every name here is
#: probed through the patched ``which``, so removing one is how a test proves the
#: "could not be asked" branch rather than the "answered" one.
DEFAULT_BINARIES: Tuple[str, ...] = (
    "pgrep", "hyprctl", "noctalia", "quickshell", "dbus-send", "notify-send",
)

#: Spawn policies: ``appears`` is a process the table then shows, ``invisible`` is a
#: pid that was returned but never shows up (an engine that starts and dies), and
#: ``fails`` is a spawn that returns no pid at all.
APPEARS = "appears"
INVISIBLE = "invisible"
FAILS = "fails"


class FakeSession:
    """One controllable session: processes, commands, replies and a clock."""

    def __init__(self, running: Optional[Dict[str, List[int]]] = None,
                 binaries: Sequence[str] = DEFAULT_BINARIES,
                 spawn_policy: Optional[Dict[str, str]] = None,
                 config_errors: Optional[List[str]] = None,
                 instances_ok: bool = True, ipc_ok: bool = True,
                 notification_owner: Optional[Tuple[str, int]] = None,
                 replies: Optional[Dict[Tuple[str, ...], Any]] = None,
                 protected: Sequence[int] = ()) -> None:
        self.binaries = set(binaries)
        self.running: Dict[str, List[int]] = {key: list(value)
                                              for key, value in (running or {}).items()}
        self.spawn_policy = dict(spawn_policy or {})
        self.config_errors = list(config_errors or [])
        self.instances_ok = instances_ok
        self.ipc_ok = ipc_ok
        self.notification_owner = notification_owner
        self.replies: Dict[Tuple[str, ...], Any] = dict(replies or {})
        #: Pids that ignore a signal, so a test can stage an engine that will not stop.
        self.protected = set(protected)
        self.calls: List[Tuple[str, ...]] = []
        self.spawned: List[Tuple[str, ...]] = []
        self.next_pid = 4000
        self.now = 0.0
        self.sleeps: List[float] = []

    # --- the injected runner -------------------------------------------

    def run(self, command: Sequence[str], timeout: float = 30.0,
            env: Optional[Dict[str, str]] = None) -> Optional[Answer]:
        args = tuple(command)
        self.calls.append(args)
        if not args or args[0] not in self.binaries:
            return None  # exactly what the real runner returns for a missing binary
        for prefix, reply in self.replies.items():
            if args[:len(prefix)] == tuple(prefix):
                return self._reply(args, reply)
        return self._default(args)

    def _reply(self, args: Tuple[str, ...], reply: Any) -> Answer:
        if isinstance(reply, Answer):
            return Answer(args, reply.returncode, reply.stdout, reply.stderr, reply.timed_out)
        if isinstance(reply, Exception):
            return Answer(args, None, "", str(reply), note=str(reply))
        if isinstance(reply, tuple):
            code, out = reply
            return Answer(args, code, out, "" if code == 0 else out)
        return Answer(args, 0, str(reply), "")

    def _default(self, args: Tuple[str, ...]) -> Answer:
        name = args[0]
        if name == "pgrep":
            return self._pgrep(args)
        if name == "quickshell":
            return self._quickshell(args)
        if name == "hyprctl":
            if args[1] == "configerrors":
                return Answer(args, 0, "".join(f"{line}\n" for line in self.config_errors), "")
            return Answer(args, 0, "ok\n", "")
        if name == "dbus-send":
            return self._dbus(args)
        if name == "noctalia":
            return Answer(args, 0, "ok\n", "")
        return Answer(args, 0, "", "")

    def _pgrep(self, args: Tuple[str, ...]) -> Answer:
        """``pgrep -x -l NAME`` — and, since ``-x`` still takes an ERE, ``A|B|C``."""
        wanted = args[-1]
        lines = []
        for name in wanted.split("|"):
            lines.extend(f"{pid} {name}\n" for pid in self.running.get(name, []))
        return Answer(args, 0 if lines else 1, "".join(lines), "")

    def _quickshell(self, args: Tuple[str, ...]) -> Answer:
        verb = args[1] if len(args) > 1 else ""
        if verb == "list":
            if not self.instances_ok:
                return Answer(args, 1, "", "no instance answered")
            pids = self.running.get("quickshell", [])
            return Answer(args, 0, json.dumps([{"pid": pid, "config": "iarch"} for pid in pids]), "")
        if verb == "kill":
            self.running["quickshell"] = []
            return Answer(args, 0, "killed\n", "")
        if verb == "ipc":
            if not self.ipc_ok:
                return Answer(args, 1, "", "no such target")
            return Answer(args, 0, "ok\n", "")
        return Answer(args, 0, "", "")

    def _dbus(self, args: Tuple[str, ...]) -> Answer:
        method = next((arg for arg in args if arg.startswith("org.freedesktop.DBus.")), "")
        if method.endswith("GetNameOwner"):
            if self.notification_owner is None:
                return Answer(args, 1, "",
                              "org.freedesktop.DBus.Error.NameHasNoOwner: "
                              "Could not get an owner for this name")
            return Answer(args, 0, f'      string "{self.notification_owner[0]}"\n', "")
        if method.endswith("GetConnectionUnixProcessID"):
            if self.notification_owner is None:
                return Answer(args, 1, "", "no such connection")
            return Answer(args, 0, f"   uint32 {self.notification_owner[1]}\n", "")
        return Answer(args, 0, "", "")

    # --- the injected spawner ------------------------------------------

    def spawn(self, command: Sequence[str]) -> Optional[int]:
        args = tuple(command)
        self.spawned.append(args)
        if not args or args[0] not in self.binaries:
            return None
        policy = self.spawn_policy.get(args[0], APPEARS)
        if policy == FAILS:
            return None
        self.next_pid += 1
        if policy == APPEARS:
            self.running.setdefault(args[0], []).append(self.next_pid)
        return self.next_pid

    # --- the patched process table -------------------------------------

    def which(self, binary: str) -> Optional[str]:
        return f"/usr/bin/{binary}" if binary in self.binaries else None

    def is_alive(self, pid: int) -> bool:
        return any(pid in pids for pids in self.running.values())

    def signal(self, pid: int, sig: int) -> Optional[str]:
        """A signal that lands, unless the pid is one a test made unstopable."""
        if pid in self.protected:
            return f"pid {pid} ignored signal {sig}"
        for pids in self.running.values():
            if pid in pids:
                pids.remove(pid)
        return None

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    # --- what a test asks of it ----------------------------------------

    def pids(self, binary: str) -> List[int]:
        return list(self.running.get(binary, []))

    def commands(self, name: str) -> List[Tuple[str, ...]]:
        return [call for call in self.calls if call and call[0] == name]

    def called(self, *prefix: str) -> bool:
        wanted = tuple(prefix)
        return any(call[:len(wanted)] == wanted for call in self.calls)

    def start(self, binary: str, pid: int) -> None:
        """Put a process in the table the way a session would have it."""
        self.running.setdefault(binary, []).append(pid)


@contextlib.contextmanager
def session(**kwargs: Any) -> Iterator[FakeSession]:
    """A ``FakeSession`` with every production lookup pointed at it.

    Patching the module defaults rather than only accepting injection is what lets a
    test drive a *command line* — ``iarch-doctor shell``, ``iarch-shell-switch to`` —
    through the same fake, because those reach the runner and the spawner by their
    default path and there is nowhere to pass one in.
    """
    fake = FakeSession(**kwargs)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(runner, "which", fake.which))
        stack.enter_context(mock.patch.object(runner, "run", fake.run))
        stack.enter_context(mock.patch.object(processes, "spawn", fake.spawn))
        stack.enter_context(mock.patch.object(processes, "is_alive", fake.is_alive))
        stack.enter_context(mock.patch.object(processes, "_signal", fake.signal))
        yield fake


def install_shell(env: Dict[str, str], body: str = "// iArch Shell — entry point\n") -> Path:
    """Put the dynamic engine's entry point where the toolkit would look for it.

    The switch refuses to start an engine whose ``shell.qml`` is missing, which is
    the right behaviour on a desktop and an obstacle in a test, so every test that
    means to get past the preflight installs one.
    """
    from iarch.cli import theme_engine as engines

    entry = engines.shell_entry("dynamic", env)
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(body, encoding="utf-8")
    return entry


@contextlib.contextmanager
def virtual_time() -> Iterator[List[float]]:
    """A clock that only moves when the code under test sleeps.

    The switch's ten second budget is real time on a desktop and would be ten real
    seconds in every test that stages a failure, so the two functions the production
    code reads are patched: ``monotonic`` returns the virtual now, ``sleep`` advances
    it. A test that polls a budget therefore costs nothing and still proves the
    polling happened.
    """
    now = [0.0]

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with mock.patch.object(time, "monotonic", clock), mock.patch.object(time, "sleep", sleep):
        yield now


@contextlib.contextmanager
def environment() -> Iterator[Dict[str, str]]:
    """A throwaway ``HOME`` with the two iArch directories inside it."""
    with tempfile.TemporaryDirectory() as home:
        root = Path(home)
        yield {"HOME": str(root),
               "IARCH_CONFIG_DIR": str(root / ".config" / "iarch"),
               "IARCH_STATE_DIR": str(root / ".local" / "state" / "iarch"),
               "XDG_CONFIG_HOME": str(root / ".config")}
