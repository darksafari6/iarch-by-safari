# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Finding processes by name, and stopping only the ones we were asked to stop.

Purpose
    The engine switch has to answer two questions about a live session — is this
    shell running, and did it stop when we asked — without a compositor, a shell
    or a display in the room while it is being tested. This module is the whole of
    that: a read-only scan of the process table through ``pgrep``, and a guarded
    terminate that signals pids one at a time with a grace period before anything
    stronger. Nothing here removes a package, edits a unit or starts a desktop.

Inputs
    A process name (the basename an engine runs as), a budget in seconds, and —
    for tests — an injectable runner, clock and sleep.

Outputs
    ``ProcessScan`` for a lookup, which keeps "nothing found" and "nothing looked"
    apart through its ``searched`` flag, and a report dict for a terminate.

Dependencies
    ``iarch.lib.runner`` for command execution, plus ``os``, ``signal``,
    ``subprocess`` and ``time`` from the standard library. No shell is involved.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from iarch.lib import runner as default_runner
from iarch.lib.runner import Answer, Runner

#: ``pgrep -x -l NAME`` matches a process name exactly and prints pid and name.
#: The same binary and the same flags the notification-daemon probe in
#: ``iarch/cli/iarch_doctor.py`` uses, so both read one process table one way.
PGREP_BIN = "pgrep"
PGREP_TIMEOUT_SECONDS = 10.0

#: How long a stopped process gets to exit on its own before it is killed. Short
#: on purpose: the switch has a ten second budget for the whole round trip, and a
#: shell that ignores SIGTERM is not going to answer it later.
DEFAULT_GRACE_SECONDS = 3.0
POLL_INTERVAL_SECONDS = 0.25


@dataclass(frozen=True)
class ProcessScan:
    """What the process table said about one name."""

    name: str
    pids: Tuple[int, ...] = ()
    searched: bool = False
    note: Optional[str] = None
    answer: Optional[Answer] = field(default=None, compare=False)

    @property
    def running(self) -> bool:
        return bool(self.pids)

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "pids": list(self.pids), "searched": self.searched,
                "note": self.note}


def pids_named(name: str, run: Optional[Runner] = None) -> ProcessScan:
    """The pids of every process called exactly ``name``.

    ``searched`` is false when ``pgrep`` is missing or refused to answer, because an
    empty list from a probe that never ran is not evidence that nothing is running.
    """
    execute = run or default_runner.run
    answer = execute((PGREP_BIN, "-x", "-l", name), PGREP_TIMEOUT_SECONDS)
    if answer is None:
        return ProcessScan(name, searched=False,
                           note=f"{PGREP_BIN} is not installed, so the process table was not searched")
    if answer.timed_out or answer.returncode not in (0, 1):
        # pgrep exits 1 when nothing matched; anything else means it could not say.
        return ProcessScan(name, searched=False, note=answer.describe(), answer=answer)
    found: List[int] = []
    for line in answer.lines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1] == name and parts[0].isdigit():
            found.append(int(parts[0]))
    return ProcessScan(name, pids=tuple(sorted(set(found))), searched=True, answer=answer)


def is_alive(pid: int) -> bool:
    """Whether a pid still exists. Signal 0 asks without touching the process."""
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists and belongs to somebody else; that is still "alive".
        return True
    except OSError:
        return False
    return True


def wait_gone(pids: Sequence[int], budget: float,
              clock: Optional[Callable[[], float]] = None,
              sleep: Optional[Callable[[float], None]] = None) -> Tuple[List[int], List[int]]:
    """Wait up to ``budget`` seconds for pids to exit. Returns (gone, remaining).

    The clock and the sleep are resolved when called rather than bound as defaults,
    so a test that patches ``time`` is testing the code and not the import order.
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    remaining = [pid for pid in pids if pid > 1]
    gone: List[int] = []
    deadline = clock() + max(0.0, budget)
    while remaining and clock() < deadline:
        still = [pid for pid in remaining if is_alive(pid)]
        gone.extend(pid for pid in remaining if pid not in still)
        remaining = still
        if remaining:
            sleep(min(POLL_INTERVAL_SECONDS, max(0.0, deadline - clock())))
    gone.extend(pid for pid in remaining if not is_alive(pid))
    remaining = [pid for pid in remaining if is_alive(pid)]
    return gone, remaining


def _signal(pid: int, sig: int) -> Optional[str]:
    """Send one signal. Returns ``None`` on success, or why it could not be sent."""
    if pid <= 1:
        return "refused: pid 1 and below are never signalled"
    if pid in (os.getpid(), os.getppid()):
        return "refused: this process or its parent is not a target"
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return None  # already gone, which is the outcome we wanted
    except PermissionError:
        return f"permission denied signalling {pid}"
    except OSError as exc:
        return f"could not signal {pid}: {exc}"
    return None


def spawn(command: Sequence[str], env: Optional[Mapping[str, str]] = None) -> Optional[int]:
    """Start a program that outlives this one. Returns its pid, or ``None``.

    ``start_new_session`` puts the child in its own session, so a shell started by a
    command line is not taken down when that command line exits or when its
    controlling terminal goes away. ``stdin`` is detached for the same reason: a
    child that inherits a closed descriptor can die on its first read.
    """
    args = tuple(command)
    if not args or default_runner.which(args[0]) is None:
        return None
    try:
        process = subprocess.Popen(  # noqa: S603 - an argument list, never a shell
            list(args), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
            env=dict(env) if env is not None else None, close_fds=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return process.pid


def terminate(pids: Sequence[int], grace: float = DEFAULT_GRACE_SECONDS,
              clock: Optional[Callable[[], float]] = None,
              sleep: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    """Ask pids to exit, then kill the ones that did not.

    The report says which pid was asked, which exited on its own, which needed
    SIGKILL and which could not be touched at all — because "the engine stopped"
    and "we could not stop the engine" have to be different sentences.
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    targets = [pid for pid in pids if pid > 1 and pid not in (os.getpid(), os.getppid())]
    refused = [pid for pid in pids if pid not in targets]
    report: Dict[str, Any] = {
        "asked": list(targets),
        "refused": list(refused),
        "exited": [],
        "killed": [],
        "errors": [],
        "grace_seconds": grace,
    }
    for pid in targets:
        error = _signal(pid, signal.SIGTERM)
        if error:
            report["errors"].append(error)
    gone, remaining = wait_gone(targets, grace, clock=clock, sleep=sleep)
    report["exited"] = gone
    for pid in remaining:
        error = _signal(pid, signal.SIGKILL)
        if error:
            report["errors"].append(error)
        else:
            report["killed"].append(pid)
    gone_after, still = wait_gone(remaining, grace, clock=clock, sleep=sleep)
    report["exited"] = sorted(set(report["exited"]) | set(gone_after))
    report["survivors"] = still
    return report
