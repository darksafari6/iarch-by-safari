#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""shell_switch — the sequence that runs one shell engine and never two.

Purpose
    D-T1-01 in docs/DECISIONS.md says exactly one engine runs. This module is the
    order the steps happen in, and the rollback that keeps that promise true when a
    step fails: snapshot, stop the engine that has to give way, start the one that
    was asked for, prove it is up inside the budget, and put the session back the
    way it was if any of that fails. It renders no theme and edits no configuration
    file; the records it writes are the two ``iarch.cli.engine_state`` owns.

Inputs
    A target engine id, an environment mapping, and injectable ``run``, ``spawn``,
    ``clock`` and ``sleep``, so the whole sequence is testable without a compositor,
    a shell or a wall clock.

Outputs
    A report dict — what was running before, every step with its own verdict, the
    rollback when there was one, and a verdict of ``switched``, ``already``,
    ``dry-run`` or ``rolled-back``. ``RefusedError`` carries both the sentence a
    person reads and the report of what was undone; ``SwitchError`` is a usage or
    data problem that changed nothing.

Dependencies
    ``iarch.cli.theme_engine`` (catalogue), ``iarch.cli.engine_state`` (records and
    probes), ``iarch.cli.engine_steps`` (stop, start, prove), ``iarch.lib.processes``
    (terminating a half-started engine), ``iarch.lib.runner`` (the default runner).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from iarch.cli import engine_state, engine_steps, theme_engine as engines
from iarch.lib import processes, runner

#: The rollback contract: stop, start and prove all finish inside this, or the
#: session goes back. Ten seconds is also the window Quickshell's own crash handler
#: uses before it refuses to restart a shell, so an engine that cannot come up in
#: ten seconds is one its own toolkit would not retry either (src/launch/main.cpp).
BUDGET_SECONDS = engines.SWITCH_BUDGET_SECONDS

Spawner = engine_steps.Spawner


class SwitchError(RuntimeError):
    """A usage or data problem: an unknown engine, an unreadable snapshot."""


class RefusedError(RuntimeError):
    """The switch did not complete, and the session was put back as it was.

    ``report`` carries the steps that did run, so a caller can show what was
    stopped, what was started and what the rollback did — not only why.
    """

    def __init__(self, message: str, report: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message)
        self.report: Optional[Mapping[str, Any]] = report


def switch(target_id: str, env: Optional[Mapping[str, str]] = None, *,
           run: Optional[runner.Runner] = None, spawn: Optional[Spawner] = None,
           clock: Optional[Callable[[], float]] = None,
           sleep: Optional[Callable[[float], None]] = None, budget: float = BUDGET_SECONDS,
           grace: float = engine_steps.STOP_GRACE_SECONDS,
           dry_run: bool = False) -> Dict[str, Any]:
    """Switch the running engine, or refuse and leave the session as it was."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    target = engines.engine(target_id)
    if target is None:
        raise SwitchError(f"unknown engine '{target_id}'; the engines are "
                          + ", ".join(f"{key} ({value})"
                                      for key, value in sorted(engines.engine_names().items())))
    before = engine_state.state(env, run=run)
    report: Dict[str, Any] = {
        "command": "to", "target": target.id, "target_name": target.name,
        "dry_run": dry_run, "budget_seconds": budget, "before": before, "steps": [],
        "rollback": None, "verdict": "dry-run" if dry_run else "refused",
        "record_path": str(engines.engine_record_path(env)),
    }
    alive = engine_state.running_ids(before)
    if len(alive) > 1:
        # Two engines running is the state this command exists to end, but guessing
        # which one to kill would guess which one the person wants to keep.
        raise RefusedError("more than one shell engine is running (" + ", ".join(alive)
                           + "), so there is no single previous engine to restore. Stop one of "
                             "them, then run this command again.", report)
    previous = engines.engine(alive[0]) if alive else (
        engines.engine(before["record"]["engine"]) or engines.default_engine())
    previous_pids = before["engines"].get(previous.id, {}).get("pids", [])

    if alive == [target.id]:
        report["verdict"] = "already"
        report["steps"].append({"step": "already-running", "engine": target.id,
                                "pids": previous_pids,
                                "record_agreed": before["record"]["engine"] == target.id})
        if before["record"]["engine"] != target.id:
            engine_state.write_engine_record(target.id, before["record"]["engine"], env=env)
            report["steps"].append({"step": "record", "engine": target.id,
                                    "note": "the record named another engine and was corrected"})
        return report

    # 0. Preflight, before anything is stopped: an engine whose binary is missing,
    #    or whose QML entry point was never installed, cannot come up, and finding
    #    that out after stopping a working shell is how a session ends up with none.
    missing = _preflight(target, env)
    if missing:
        report["verdict"] = "refused"
        report["steps"].append({"step": "preflight", "engine": target.id, "missing": missing})
        raise RefusedError(f"{target.name} cannot run: {missing}. Nothing was stopped and the "
                           f"session is still running {previous.name}.", report)

    if dry_run:
        report["steps"] = [
            {"step": "stop", "engine": previous.id, "pids": previous_pids,
             "command": list(previous.stop_command) if previous.stop_command else None,
             "by_signal": previous.stops_by_signal},
            {"step": "start", "engine": target.id, "command": list(target.start_command)},
            {"step": "verify", "within_seconds": budget},
        ]
        return report

    started = clock()
    deadline = started + max(0.0, budget)
    # 1. Snapshot before anything is touched: this is what `rollback` restores.
    report["steps"].append({
        "step": "snapshot",
        "path": str(engine_state.write_switch_snapshot(previous.id, previous_pids,
                                                       before["record"], budget, env))})

    # 2. Stop the engine that has to give way. Nothing is started until it is gone.
    stop = engine_steps.stop(previous, previous_pids, run=run, grace=grace, clock=clock,
                             sleep=sleep)
    report["steps"].append(dict(stop, step="stop"))
    if not stop["stopped"]:
        raise RefusedError(f"{previous.name} could not be stopped, so {target.name} was not "
                           f"started and the session is still running {previous.name}: "
                           + str(stop.get("note")), report)

    # 3. Start the engine that was asked for.
    start = engine_steps.start(target, spawn=spawn)
    report["steps"].append(dict(start, step="start"))
    if not start["started"]:
        _undo(previous, target, start, start["note"], env, run, spawn, clock, sleep,
              deadline, report)
        raise RefusedError(f"{target.name} could not be started ({start['note']}), so "
                           f"{previous.name} was started again and the session is running the "
                           "engine it was running before", report)

    # 4. Prove it is up inside the budget, or put the session back.
    verify = engine_steps.is_up(target, run=run, deadline=deadline, clock=clock, sleep=sleep)
    report["steps"].append(dict(verify, step="verify"))
    if not verify["up"]:
        reason = verify.get("note") or f"proved only as {verify.get('how')}"
        _undo(previous, target, start, reason, env, run, spawn, clock, sleep, deadline, report)
        raise RefusedError(f"{target.name} was not up within {budget:g} seconds ({reason}), so "
                           f"it was stopped, {previous.name} was started again and the recorded "
                           "engine was left as it was", report)

    # 5. It is up, so the choice is recorded and the snapshot stays for `rollback`.
    engine_state.write_engine_record(target.id, previous.id, env=env)
    report["verdict"] = "switched"
    report["after"] = engine_state.state(env, run=run)
    report["steps"].append({"step": "record", "engine": target.id,
                            "path": report["record_path"]})
    return report


def _preflight(record: engines.Engine, env: Optional[Mapping[str, str]]) -> Optional[str]:
    """Why an engine could not run, or ``None`` when nothing is missing."""
    if runner.which(record.binary) is None:
        return f"`{record.binary}` is not installed"
    entry = engines.shell_entry(record.id, env)
    if entry is not None and not Path(entry).is_file():
        return (f"its entry point {entry} does not exist, so the engine has nothing to load "
                "(the installer puts it there)")
    if entry is not None:
        try:
            if 'IARCH_SHELL_SKELETON_NOT_READY' in Path(entry).read_text(encoding='utf-8'):
                return 'the installed dynamic shell is only a skeleton and is not ready to run'
        except (OSError, UnicodeError):
            return f'cannot read shell entry point {entry}'
    return None


def _undo(previous: engines.Engine, target: engines.Engine, start: Mapping[str, Any],
          reason: Optional[str], env: Optional[Mapping[str, str]],
          run: Optional[runner.Runner], spawn: Optional[Spawner],
          clock: Callable[[], float], sleep: Callable[[float], None], deadline: float,
          report: Dict[str, Any]) -> None:
    """Stop the half-started engine, bring the previous one back, restore the record."""
    launch = spawn or processes.spawn
    undo: Dict[str, Any] = {"reason": reason, "steps": []}
    if start.get("pid"):
        stopped = processes.terminate([int(start["pid"])], clock=clock, sleep=sleep)
        undo["steps"].append({"step": "stop-half-started", "engine": target.id,
                              "exited": stopped["exited"], "killed": stopped["killed"],
                              "survivors": stopped.get("survivors", [])})
    stray = engines.running(target, run=run)
    if stray.running:
        stopped = processes.terminate(stray.pids, clock=clock, sleep=sleep)
        undo["steps"].append({"step": "stop-target", "engine": target.id,
                              "survivors": stopped.get("survivors", [])})
    restarted = engine_steps.start(previous, spawn=launch)
    undo["steps"].append(dict(restarted, step="restart-previous"))
    if restarted["started"]:
        # The budget for coming back is whatever is left of the switch budget, and
        # never less than the grace a stopped process is given: a rollback that
        # gives up sooner than the switch did would report a failure it caused.
        back = engine_steps.is_up(previous, run=run,
                                  deadline=max(deadline, clock() + engine_steps.STOP_GRACE_SECONDS),
                                  clock=clock, sleep=sleep)
        undo["steps"].append(dict(back, step="verify-previous"))
        undo["previous_is_up"] = back["up"]
    else:
        undo["previous_is_up"] = False
        undo["note"] = (f"{previous.name} could not be started again, so the session has no "
                        "shell until one is started by hand")
    undo["record_restored"] = previous.id
    engine_state.write_engine_record(previous.id, engine_state.engine_record(env).get("previous"),
                                     env=env)
    report["rollback"] = undo
    report["verdict"] = "rolled-back"


def rollback(env: Optional[Mapping[str, str]] = None, *,
             run: Optional[runner.Runner] = None, spawn: Optional[Spawner] = None,
             clock: Optional[Callable[[], float]] = None,
             sleep: Optional[Callable[[float], None]] = None,
             budget: float = BUDGET_SECONDS) -> Dict[str, Any]:
    """Restore the engine the last switch snapshotted, and stop the other one."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    snapshot = engine_state.switch_record(env)
    if not snapshot:
        raise SwitchError(f"there is no switch to roll back: {engines.switch_record_path(env)} "
                          "is absent or unreadable")
    previous = engines.engine(str(snapshot.get("previous_engine") or ""))
    if previous is None:
        raise SwitchError("the switch snapshot names an engine this build does not know: "
                          f"{snapshot.get('previous_engine')!r}")
    report: Dict[str, Any] = {"command": "rollback", "target": previous.id,
                              "target_name": previous.name, "steps": [], "verdict": "refused",
                              "snapshot": snapshot,
                              "record_path": str(engines.engine_record_path(env))}
    scan = engines.running(previous, run=run)
    if scan.running:
        report["steps"].append({"step": "already-running", "pids": list(scan.pids)})
    else:
        started = engine_steps.start(previous, spawn=spawn)
        report["steps"].append(dict(started, step="restart-previous"))
        if not started["started"]:
            raise RefusedError(f"{previous.name} could not be started ({started['note']})", report)
        verify = engine_steps.is_up(previous, run=run, deadline=clock() + max(0.0, budget),
                                    clock=clock, sleep=sleep)
        report["steps"].append(dict(verify, step="verify"))
        if not verify["up"]:
            raise RefusedError(f"{previous.name} did not come up within {budget:g} seconds "
                               f"({verify.get('note')})", report)
    for other in engines.ENGINES:
        if other.id == previous.id:
            continue
        stray = engines.running(other, run=run)
        if stray.running:
            stopped = processes.terminate(stray.pids, clock=clock, sleep=sleep)
            report["steps"].append({"step": "stop-other", "engine": other.id,
                                    "survivors": stopped.get("survivors", [])})
    engine_state.write_engine_record(previous.id, None, env=env)
    report["verdict"] = "rolled-back"
    report["after"] = engine_state.state(env, run=run)
    return report
