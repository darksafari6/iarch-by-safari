#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""engine_steps — the three actions a shell switch is made of: stop, start, prove.

Purpose
    Each action is a small function that takes an engine record and an injectable
    runner, spawner, clock and sleep, and returns a report dict that says what it
    did and how sure it is. They are separate from the sequence in
    ``iarch.cli.shell_switch`` so that a test can prove one action without staging
    a whole switch, and so the sequence reads as a list of steps rather than as
    subprocess calls.

Inputs
    An ``Engine`` from ``iarch.cli.theme_engine``, the pids a scan found, a budget
    or a deadline, and the injectables above.

Outputs
    ``stop()`` — whether the engine gave way, by command, by signal, or not at all;
    ``start()`` — the pid of the engine that was started, or why there is none;
    ``is_up()`` — whether the engine is running, how that was proved (its own
    instance list, or only the process table), and how long it took.

Dependencies
    ``iarch.cli.theme_engine`` for the catalogue, ``iarch.lib.processes`` for the
    process table and for signalling, ``iarch.lib.runner`` for commands.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Sequence

from iarch.cli import theme_engine as engines
from iarch.lib import processes, runner

#: How often "is it up yet" is asked while the budget lasts.
POLL_INTERVAL_SECONDS = 0.25
#: How long a stopped engine gets to exit on its own before it is killed.
STOP_GRACE_SECONDS = 3.0

Spawner = Callable[[Sequence[str]], Optional[int]]


def is_up(record: engines.Engine, run: Optional[runner.Runner] = None,
          deadline: Optional[float] = None, clock: Optional[Callable[[], float]] = None,
          sleep: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    """Ask until the engine is up, the deadline passes, or it cannot be asked.

    ``how`` keeps the strength of the proof visible: ``instances`` means the engine
    listed itself, ``process-only`` means it could be asked but did not list itself,
    ``process`` means only the process table was available, and ``unsearchable``
    means not even that. A caller must not report ``unsearchable`` as "up".
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    limit = clock() if deadline is None else deadline
    attempts = 0
    started = clock()
    while True:
        attempts += 1
        scan = engines.running(record, run=run)
        if not scan.searched:
            return {"up": False, "attempts": attempts, "elapsed": clock() - started,
                    "how": "unsearchable", "note": scan.note}
        if scan.running:
            listed, answer = engines.instances(record, run=run)
            how = "instances" if listed else ("process-only" if answer is not None else "process")
            return {"up": True, "attempts": attempts, "elapsed": clock() - started,
                    "how": how, "pids": list(scan.pids)}
        if clock() >= limit:
            return {"up": False, "attempts": attempts, "elapsed": clock() - started,
                    "how": "not-running",
                    "note": f"{record.name} was not running when the budget ended"}
        sleep(min(POLL_INTERVAL_SECONDS, max(0.0, limit - clock())))


def stop(record: engines.Engine, pids: Sequence[int],
         run: Optional[runner.Runner] = None, grace: float = STOP_GRACE_SECONDS,
         clock: Optional[Callable[[], float]] = None,
         sleep: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    """Ask an engine to exit, then signal the pids that are still there.

    The classic engine has no verified exit command (see ``theme_engine``), so for
    it this is a signal to the pids the process table named; for the dynamic engine
    its own ``kill`` subcommand is asked first and the signal is the fallback.
    """
    report: Dict[str, Any] = {"engine": record.id, "asked": list(pids), "command": None,
                              "terminate": None}
    if not pids:
        report.update(stopped=True, note=f"{record.name} was not running")
        return report
    if record.stop_command is not None:
        answer = (run or runner.run)(record.stop_command, processes.PGREP_TIMEOUT_SECONDS)
        report["command"] = None if answer is None else answer.describe()
    report["terminate"] = processes.terminate(pids, grace=grace, clock=clock, sleep=sleep)
    survivors = report["terminate"].get("survivors") or []
    report["stopped"] = not survivors
    if survivors:
        report["note"] = (f"{record.name} kept running as pid "
                          + ", ".join(str(pid) for pid in survivors))
    return report


def start(record: engines.Engine, spawn: Optional[Spawner] = None) -> Dict[str, Any]:
    """Start an engine detached from this process. ``pid`` is ``None`` on failure."""
    launch = spawn or processes.spawn
    pid = launch(record.start_command)
    if pid is not None:
        return {"engine": record.id, "command": list(record.start_command), "pid": pid,
                "started": True, "note": None}
    note = (f"`{record.binary}` is not installed, so {record.name} could not be started"
            if runner.which(record.binary) is None
            else f"{record.name} could not be started")
    return {"engine": record.id, "command": list(record.start_command), "pid": None,
            "started": False, "note": note}
