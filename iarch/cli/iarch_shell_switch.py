#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""iarch-shell-switch — run one shell engine, and never two.

Purpose
    The command line over ``iarch.cli.shell_switch``: report which engine is
    running and who owns the notification server, switch to the other engine with
    a rollback that fits inside ten seconds, and undo the last switch by hand.

Inputs
    ``status [--json]``, ``to <classic|dynamic> [--budget S] [--dry-run] [--json]``
    and ``rollback [--json]``, plus the environment (``HOME``, ``XDG_CONFIG_HOME``,
    ``IARCH_CONFIG_DIR``, ``IARCH_STATE_DIR``).

Outputs
    A step-by-step report on standard output, warnings on standard error, and one
    of three exit statuses: 0 when the session is running the engine that was asked
    for, 1 when the switch was refused or rolled back, 2 on a usage or data error.

Dependencies
    ``iarch.cli.shell_switch`` for the pipeline, ``iarch.cli.theme_engine`` for the
    catalogue, ``iarch.cli.iarch_doctor`` for the read-only notification-daemon
    probe it already ships.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.cli import (  # noqa: E402  (repo-root import by design)
    engine_state,
    iarch_doctor,
    shell_switch,
    theme_engine as engines,
)

EXIT_OK = 0
EXIT_REFUSED = 1  # refused, or rolled back: the session is running what it was
EXIT_USAGE = 2    # unknown engine, unreadable snapshot, bad arguments

_JSON_MODE = False


def _say(message: str) -> None:
    if not _JSON_MODE:
        print(message)


def _warn(message: str) -> None:
    if not _JSON_MODE:
        print(f"warning: {message}", file=sys.stderr)


def _label(engine_id: str) -> str:
    record = engines.engine(engine_id)
    return record.name if record else engine_id


def _emit(report: Dict[str, Any]) -> None:
    if _JSON_MODE:
        print(json.dumps(report, indent=2, default=str))


def _print_state(report: Dict[str, Any]) -> None:
    _say("iArch by Safari — shell engine")
    for engine_id, scan in sorted(report["engines"].items()):
        pids = scan.get("pids") or []
        state = "running" if pids else ("not running" if scan.get("searched") else "unknown")
        detail = f" (pid {', '.join(str(pid) for pid in pids)})" if pids else ""
        _say(f"  {_label(engine_id):<12} {state}{detail}")
        if not scan.get("searched") and scan.get("note"):
            _warn(f"{_label(engine_id)}: {scan['note']}")
    selected = report["record"]["engine"]
    origin = "recorded" if report["record"]["stored"] else "repository default"
    _say(f"  selected:    {_label(selected)} ({selected}, {origin})")
    notification = report["notification"]
    if not notification.get("searched"):
        _warn(f"the notification server could not be asked: {notification.get('note')}")
    elif notification.get("unique_name") is None:
        _say("  notifications: no process owns org.freedesktop.Notifications")
    else:
        owner = _label(notification["engine"]) if notification.get("engine") else (
            f"pid {notification['pid']}" if notification.get("pid") else notification["unique_name"])
        _say(f"  notifications: {owner} owns org.freedesktop.Notifications")
    for daemon in report.get("daemons", {}).get("names", []):
        _warn(f"another notification daemon is running: {daemon}")
    for violation in report["violations"]:
        _warn(violation)


def _print_steps(report: Dict[str, Any]) -> None:
    """Print the steps of a report — a plan (dry run) or a result, both shapes."""
    for step in report.get("steps", []):
        name = step.get("step") or ""
        label = _label(step["engine"]) if step.get("engine") else ""
        if name == "snapshot":
            _say(f"  snapshot     {step.get('path')}")
        elif name == "preflight":
            _warn(f"{label or 'the target engine'} cannot run: {step.get('missing')}")
        elif name == "stop":
            how = "asked" if step.get("command") else ("would signal" if report.get("dry_run")
                                                       else "signalled")
            _say(f"  stop         {label} ({how}, {len(step.get('pids') or step.get('asked') or [])}"
                 " pid)")
        elif name == "start":
            pid = step.get("pid")
            _say(f"  start        {label}" + (f" as pid {pid}" if pid else
                                              f" would run {' '.join(step.get('command') or [])}"))
        elif name == "verify":
            if step.get("up") is None:
                _say(f"  verify       within {step.get('within_seconds', 0):g}s")
            else:
                _say(f"  verify       {label} is up after {step.get('elapsed', 0):.2f}s, "
                     f"proved by {step.get('how')}")
        elif name == "record":
            _say(f"  record       {label} written to {step.get('path', report.get('record_path'))}"
                 + (f" ({step['note']})" if step.get("note") else ""))
        elif name == "already-running":
            _say(f"  already      {label} is the only engine running")
        else:
            _say(f"  {name:<12} {json.dumps(step, default=str)}")
    undo = report.get("rollback")
    if undo:
        _warn(f"rolled back: {undo.get('reason')}")
        for step in undo.get("steps", []):
            _say(f"  undo         {step.get('step')} {_label(step.get('engine', ''))}")
        if not undo.get("previous_is_up", True):
            _warn(undo.get("note") or "the previous engine is not running")


def cmd_status(args: argparse.Namespace) -> int:
    report = engine_state.state(os.environ)
    report["command"] = "status"
    report["daemons"] = iarch_doctor.competing_daemons()
    report["verdict"] = "violations" if report["violations"] else "one-shell"
    global _JSON_MODE
    _JSON_MODE = bool(args.json)
    _print_state(report)
    _emit(report)
    return EXIT_OK if not report["violations"] else EXIT_REFUSED


def cmd_to(args: argparse.Namespace) -> int:
    global _JSON_MODE
    _JSON_MODE = bool(args.json)
    budget = args.budget
    if not math.isfinite(budget) or budget <= 0:
        raise shell_switch.SwitchError(f"--budget must be positive and finite, not {budget:g}")
    if budget > engines.SWITCH_BUDGET_SECONDS:
        _warn(f"--budget {budget:g}s is longer than the {engines.SWITCH_BUDGET_SECONDS:g}s the "
              "switch is designed to roll back inside; a rollback may not finish in time")
    _say(f"iArch by Safari — switching the shell engine to {_label(args.engine)}")
    daemons = iarch_doctor.competing_daemons()
    for daemon in daemons.get('names', []):
        _warn(f"another notification daemon could claim the bus name: {daemon}")
    report = shell_switch.verified_switch(args.engine, os.environ, budget=budget, dry_run=args.dry_run)
    report['daemons'] = daemons
    _print_steps(report)
    if args.dry_run:
        _say("  dry run: nothing was stopped, started or written")
    else:
        _say(f"  verdict      {report['verdict']}")
    _emit(report)
    return EXIT_OK


def cmd_rollback(args: argparse.Namespace) -> int:
    global _JSON_MODE
    _JSON_MODE = bool(args.json)
    _say("iArch by Safari — rolling the shell engine back")
    snapshot = engine_state.switch_record(os.environ)
    if snapshot and snapshot.get('schema_version') == 2:
        if snapshot.get('phase') != 'VERIFIED':
            raise shell_switch.SwitchError('handoff is not in VERIFIED state; use recover')
        report = shell_switch.verified_switch(snapshot.get('previous_engine', ''), os.environ)
        report['verdict'] = 'rolled-back'
    elif snapshot and snapshot.get('schema_version') == 1:
        report = shell_switch.verified_switch(snapshot.get('previous_engine', ''), os.environ)
        report['verdict'] = 'rolled-back'
    else:
        raise shell_switch.SwitchError('no switch to roll back or unsupported switch snapshot')
    _print_steps(report)
    _say(f"  verdict      {report['verdict']}")
    _emit(report)
    return EXIT_OK


def cmd_recover(args: argparse.Namespace) -> int:
    from iarch.cli import shell_handoff
    global _JSON_MODE
    _JSON_MODE = bool(args.json)
    try:
        report = shell_handoff.recover(env=os.environ)
    except shell_handoff.HandoffError as exc:
        _emit({'command': 'recover', 'error': str(exc), 'state': exc.state})
        print(f'iarch-shell-switch: {exc}', file=sys.stderr)
        return EXIT_REFUSED
    _emit(report)
    _say(f"  recovery     {report['phase']}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iarch-shell-switch",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    names = ", ".join(f"{key} ({value})" for key, value in sorted(engines.engine_names().items()))

    status_p = sub.add_parser("status", help="report the running engine and the notification server")
    status_p.add_argument("--json", action="store_true", help="print the report as JSON only")
    status_p.set_defaults(func=cmd_status)

    to_p = sub.add_parser("to", help="stop the running engine and start another one")
    to_p.add_argument("engine", choices=engines.engine_ids(),
                      metavar="ENGINE", help=f"the engine to run: {names}")
    to_p.add_argument("--budget", type=float, default=engines.SWITCH_BUDGET_SECONDS,
                      help=f"seconds to prove the new engine is up before rolling back "
                           f"(default {engines.SWITCH_BUDGET_SECONDS:g})")
    to_p.add_argument("--dry-run", action="store_true",
                      help="print the steps without stopping, starting or writing anything")
    to_p.add_argument("--json", action="store_true", help="print the report as JSON only")
    to_p.set_defaults(func=cmd_to)

    back_p = sub.add_parser("rollback", help="restore the engine the last switch snapshotted")
    back_p.add_argument("--json", action="store_true", help="print the report as JSON only")
    back_p.set_defaults(func=cmd_rollback)

    recover_p = sub.add_parser("recover", help="recover an interrupted notification handoff")
    recover_p.add_argument("--json", action="store_true", help="print the report as JSON only")
    recover_p.set_defaults(func=cmd_recover)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        return args.func(args)
    except shell_switch.RefusedError as exc:
        # The report already knows whether it refused before touching the session or
        # rolled the session back; only a report with no verdict gets the default.
        refused = dict(exc.report or {})
        refused.setdefault("verdict", "refused")
        refused.update({"command": args.command, "error": str(exc)})
        _emit(refused)
        print(f"iarch-shell-switch: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except (shell_switch.SwitchError, ValueError, OSError) as exc:
        print(f"iarch-shell-switch: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
