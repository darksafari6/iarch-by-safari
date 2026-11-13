#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""iarch-doctor — ask the running desktop whether iArch's settings really took.

A theme that renders is not a theme that works. This tool exists for the checks
that only mean something next to a live session: is the shell answering IPC, is
Do Not Disturb swallowing the toasts, does a notification actually arrive, and is
some *other* daemon holding ``org.freedesktop.Notifications`` so that Noctalia's
own never claimed it.

Part 3 gives it two subjects; Part 5 adds the rest of the session to the same
command (docs/ARCHITECTURE.md schedules it there).

Notifications
-------------
iArch never runs a notification daemon of its own. Noctalia's built-in one is
claimed with ``[notification] enable_daemon = true`` in the generated
``config.toml``, so ``notify-test`` talks to that daemon and to nothing else:

* three internal probes through ``noctalia msg notification-show`` — low, normal
  and critical — carrying the JSON payload form documented at
  docs/user/ipc/media-and-ui.mdx (``app_name``, ``summary``, ``body``,
  ``urgency``, ``timeout_ms``);
* one optional external probe through ``notify-send`` when it is installed, which
  is the only way to prove the daemon owns the D-Bus name rather than merely
  answering its own IPC socket.

The critical probe asks for ``timeout_ms = 0`` on purpose. Noctalia v5.4.1 has no
setting that makes critical toasts persistent: ``normalizeNotifyExpireTimeout()``
(src/notification/notification_manager.h:39) maps 0 to persistent and a negative
value to ``kDefaultNotificationTimeout = 6000`` regardless of urgency, so a
critical toast lives exactly as long as its sender asked. Asking for 0 shows the
one path that does keep a toast on screen, and the body says so out loud rather
than letting anyone conclude that urgency alone did it.

Do Not Disturb is IPC-only in v5.4.1 — ``notification-dnd-set on|off``,
``notification-dnd-toggle``, ``notification-dnd-status`` — and there is no
schedule or quiet-hours key anywhere in ``notificationSchema()``
(src/config/config_schema.cpp:292). ``notify-test`` therefore reports the DND
state before sending and, when it is on, declines to send unless ``--force``
says otherwise: a test nobody can see is not a passed test.

The contract, shared with iarch-anim and iarch-theme:

* never mutate state a diagnostic was not asked to mutate — ``dnd`` changes
  Do Not Disturb because that is the command; ``notify-test`` only ever sends
  toasts, and refuses to send them into a suppressed session without ``--force``;
* never start a desktop: a missing ``noctalia``, ``notify-send`` or ``pgrep`` is
  reported as something that could not be checked, never as a failure;
* no ``shell=True``, no pipelines — every probe is an argument vector;
* exit 0 when the checks ran (including when they could not be run), 1 when the
  shell answered with an error, 2 on a usage error.

Usage:
    python3 iarch/cli/iarch_doctor.py notify-test [--force] [--dry-run] [--json]
    python3 iarch/cli/iarch_doctor.py dnd on|off|toggle|status [--json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

EXIT_OK = 0
EXIT_FAILED = 1     # the shell answered, and its answer was an error
EXIT_USAGE = 2      # bad arguments, or an unusable probe definition

NOCTALIA_BIN = "noctalia"
NOTIFY_SEND_BIN = "notify-send"
PGREP_BIN = "pgrep"

# Long enough for a shell that is busy drawing a wallpaper transition, short
# enough that a hung IPC socket does not stall a login script.
IPC_TIMEOUT_SECONDS = 10

# Upstream's own default, so a probe that does not set a timeout and one that
# sets this value behave identically: src/notification/notification_manager.h:31
# ``constexpr int32_t kDefaultNotificationTimeout = 6000;``
DEFAULT_TIMEOUT_MS = 6000

# Process names of the daemons that claim org.freedesktop.Notifications on a
# Linux desktop. This is a heuristic and it is used read-only: nothing here is
# ever stopped, disabled or removed. A daemon whose process name is not in this
# list is simply not reported, which is why the wording says "none seen".
KNOWN_NOTIFICATION_DAEMONS: Tuple[str, ...] = (
    "dunst",
    "mako",
    "swaync",
    "fnott",
    "notify-osd",
    "notification-daemon",
    "xfce4-notifyd",
)

APP_NAME = "iArch"


class DoctorError(RuntimeError):
    """A usage or data problem: nothing was sent, and the caller should say why."""


# --------------------------------------------------------------- shell answers


class Answer:
    """One IPC reply, or the reason there is none.

    ``None`` from the runners means "could not be asked" — no binary, no socket,
    a timeout — which is different from an empty reply, and every caller has to
    keep those apart the way iarch-anim keeps "no answer" apart from "clean".
    """

    def __init__(self, command: Tuple[str, ...], returncode: int, stdout: str,
                 stderr: str) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout.strip()
        self.stderr = stderr.strip()

    @property
    def ok(self) -> bool:
        """Upstream's handlers return the literal ``ok`` on success."""
        return self.returncode == 0 and self.stdout == "ok"

    @property
    def error_text(self) -> str:
        return self.stderr or self.stdout

    def as_dict(self) -> Dict[str, Any]:
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "ok": self.ok,
        }


def _run(command: Tuple[str, ...]) -> Optional[Answer]:
    """Run one command with no shell in between; None when it cannot be run."""
    if shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True,
                                timeout=IPC_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    return Answer(command, result.returncode, result.stdout, result.stderr)


def msg(*args: str) -> Optional[Answer]:
    """``noctalia msg <args>`` — the shell's IPC verb."""
    return _run((NOCTALIA_BIN, "msg") + args)


# --------------------------------------------------------------- do not disturb


def dnd_status() -> Tuple[Optional[bool], Optional[Answer]]:
    """Read Do Not Disturb. (None, None) means the shell could not be asked.

    ``notification-dnd-status`` prints exactly ``on`` or ``off``
    (src/app/application_ipc.cpp:158-159), so anything else is treated as no
    answer rather than guessed at.
    """
    answer = msg("notification-dnd-status")
    if answer is None or answer.returncode != 0:
        return None, answer
    text = answer.stdout.lower()
    if text == "on":
        return True, answer
    if text == "off":
        return False, answer
    return None, answer


def dnd_set(state: bool) -> Optional[Answer]:
    return msg("notification-dnd-set", "on" if state else "off")


def dnd_toggle() -> Optional[Answer]:
    return msg("notification-dnd-toggle")


# --------------------------------------------------------------- other daemons


def competing_daemons() -> Dict[str, Any]:
    """Other notification daemons in the process table.

    ``searched`` keeps "nothing found" and "nothing looked" apart: without
    ``pgrep`` the list is empty *and* ``searched`` is false, and the caller must
    not print the empty list as a clean bill of health. The check is read-only —
    nothing here is ever stopped, disabled or removed.
    """
    if shutil.which(PGREP_BIN) is None:
        return {"names": [], "searched": False,
                "note": f"{PGREP_BIN} is not installed, so the process table was not searched"}
    pattern = "|".join(KNOWN_NOTIFICATION_DAEMONS)
    answer = _run((PGREP_BIN, "-x", "-l", pattern))
    if answer is None or answer.returncode not in (0, 1):
        # pgrep exits 1 when nothing matched; anything else means it could not answer.
        return {"names": [], "searched": False,
                "note": f"{PGREP_BIN} gave no usable answer "
                        f"(exit {answer.returncode if answer else 'n/a'})"}
    found: List[str] = []
    for line in answer.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1] in KNOWN_NOTIFICATION_DAEMONS:
            found.append(parts[1])
    return {
        "names": sorted(set(found)),
        "searched": True,
        "note": ("only these process names were looked for: "
                 + ", ".join(KNOWN_NOTIFICATION_DAEMONS)) if not found else None,
    }


# --------------------------------------------------------------- probes


def internal_probes(timeout_ms: int) -> List[Dict[str, Any]]:
    """The three internal probes, as JSON payloads for ``notification-show``.

    ``summary`` is the only required field in JSON mode; ``urgency`` accepts low,
    normal and critical; ``timeout_ms = 0`` keeps a toast until it is dismissed
    (src/app/application_ipc.cpp:209-333).
    """
    return [
        {
            "id": "low",
            "required": True,
            "payload": {
                "app_name": APP_NAME,
                "summary": "iArch notification test — low",
                "body": ("Low urgency: the dimmest of the three styles. It should still "
                         "arrive, and hovering the card should pause its countdown."),
                "urgency": "low",
                "timeout_ms": timeout_ms,
            },
        },
        {
            "id": "normal",
            "required": True,
            "payload": {
                "app_name": APP_NAME,
                "summary": "iArch notification test — normal",
                "body": (f"Normal urgency, {timeout_ms} ms. Watch the top-right margin, the "
                         "slide in, and the progress accent draining along the top edge."),
                "urgency": "normal",
                "timeout_ms": timeout_ms,
            },
        },
        {
            "id": "critical",
            "required": True,
            "payload": {
                "app_name": APP_NAME,
                "summary": "iArch notification test — critical",
                "body": ("Critical urgency: a red edge at least 3 px wide. This one stays "
                         "until you dismiss it because the probe asked for timeout_ms = 0 — "
                         "Noctalia has no setting that makes critical toasts persistent on "
                         "its own."),
                "urgency": "critical",
                "timeout_ms": 0,
            },
        },
    ]


def external_probe(timeout_ms: int) -> Dict[str, Any]:
    """The D-Bus probe, sent through notify-send rather than the shell's own IPC."""
    return {
        "id": "external",
        "required": False,
        "command": (
            NOTIFY_SEND_BIN,
            f"--app-name={APP_NAME}",
            "--urgency=critical",
            f"--expire-time={timeout_ms}",
            "iArch notification test — external",
            ("Sent over org.freedesktop.Notifications instead of the shell's IPC socket. "
             "If this arrives, Noctalia's daemon owns the bus. It should time out like any "
             "critical notification from an application: urgency does not make it sticky."),
        ),
    }


def send_internal(probe: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.dumps(probe["payload"], ensure_ascii=False)
    answer = msg("notification-show", payload)
    return _probe_result(probe, answer, ("notification-show", payload))


def send_external(probe: Dict[str, Any]) -> Dict[str, Any]:
    answer = _run(probe["command"])
    return _probe_result(probe, answer, probe["command"])


def _probe_result(probe: Dict[str, Any], answer: Optional[Answer],
                  command: Sequence[str]) -> Dict[str, Any]:
    if answer is None:
        verdict = "not-run"
        detail = f"{command[0]} is not installed or did not answer"
    elif answer.ok or (answer.returncode == 0 and not answer.stdout.startswith("error")):
        # notify-send prints nothing on success; the shell's handlers print "ok".
        verdict = "sent"
        detail = answer.stdout or "no output"
    else:
        verdict = "error"
        detail = answer.error_text or f"exit {answer.returncode}"
    return {
        "id": probe["id"],
        "required": probe["required"],
        "command": list(command),
        "verdict": verdict,
        "detail": detail,
        "answer": answer.as_dict() if answer is not None else None,
    }


# --------------------------------------------------------------- notify-test


def cmd_notify_test(args: argparse.Namespace) -> int:
    report: Dict[str, Any] = {
        "check": "notify-test",
        "app_name": APP_NAME,
        "shell_ipc": None,
        "do_not_disturb": None,
        "competing_daemons": [],
        "competing_daemons_searched": False,
        "competing_daemons_note": None,
        "probes": [],
        "verdict": "not-run",
        "notes": [
            "internal probes are toast-only: Noctalia does not store its own "
            "notifications in history, so this test cannot exercise the history panel",
        ],
    }

    # The process-table check runs first and runs whether or not the shell
    # answers, so "other daemons: none seen" is always a statement about a search
    # that actually happened rather than a search that was skipped.
    daemons = competing_daemons()
    report["competing_daemons"] = daemons["names"]
    report["competing_daemons_searched"] = daemons["searched"]
    report["competing_daemons_note"] = daemons["note"]
    if daemons["names"]:
        report["notes"].append(
            "another notification daemon is running: whichever claimed "
            "org.freedesktop.Notifications first keeps it, so iArch's settings may be "
            "describing a daemon that is not the one on screen. Nothing was stopped.")

    state, status_answer = dnd_status()
    shell_present = shutil.which(NOCTALIA_BIN) is not None
    if status_answer is not None:
        report["shell_ipc"] = status_answer.as_dict()
    elif shell_present:
        # On PATH but silent: no session, no socket, or a shell that hung.
        report["shell_ipc"] = f"{NOCTALIA_BIN} is installed but gave no answer"
    else:
        report["shell_ipc"] = f"{NOCTALIA_BIN} is not installed"
    report["do_not_disturb"] = state
    if status_answer is None:
        report["verdict"] = "not-run"
        report["notes"].append(
            f"{report['shell_ipc']}, so no probe was sent and Do Not Disturb could not be "
            "read; this needs a running session to mean anything")
        return _finish_notify_test(report, args)

    if state is True and not args.force and not args.dry_run:
        report["verdict"] = "blocked"
        report["notes"].append(
            "Do Not Disturb is on, so toasts are suppressed while history keeps filling. "
            "Nothing was sent. Turn it off (iarch-doctor dnd off) or pass --force.")
        return _finish_notify_test(report, args)
    if state is True and args.dry_run:
        # A dry run sends nothing either way, so suppression does not stop it
        # building the probes -- it only has to say that a real run would be blocked.
        report["notes"].append(
            "Do Not Disturb is on: a real run would be blocked and send nothing unless "
            "--force is given")
    elif state is True:
        report["notes"].append(
            "--force: sending into a suppressed session, so the toasts will not appear")
    if state is None:
        report["notes"].append(
            "the DND state could not be read; sending anyway, and a missing toast may be "
            "suppression rather than a broken daemon")

    probes = internal_probes(args.timeout_ms)
    if shutil.which(NOTIFY_SEND_BIN) is not None:
        probes.append(external_probe(args.timeout_ms))
    else:
        report["notes"].append(
            f"{NOTIFY_SEND_BIN} is not installed, so the external D-Bus probe was skipped "
            "and only the shell's own IPC path was exercised")

    if args.dry_run:
        report["probes"] = [
            {
                "id": probe["id"],
                "required": probe["required"],
                "command": list(probe.get("command")
                                or [NOCTALIA_BIN, "msg", "notification-show",
                                    json.dumps(probe["payload"], ensure_ascii=False)]),
                "verdict": "dry-run",
                "detail": "not sent",
                "answer": None,
            }
            for probe in probes
        ]
        report["verdict"] = "dry-run"
        return _finish_notify_test(report, args)

    sent = 0
    failed: List[str] = []
    warnings: List[str] = []
    for index, probe in enumerate(probes):
        result = send_external(probe) if "command" in probe else send_internal(probe)
        report["probes"].append(result)
        if result["verdict"] == "sent":
            sent += 1
        elif result["verdict"] == "error":
            # Only the shell's own probes can fail the test. The external one runs
            # a third-party binary whose flags differ between distributions, so a
            # refusal there is information about that binary, not proof that the
            # notification path is broken.
            (failed if probe["required"] else warnings).append(
                f"{probe['id']}: {result['detail']}")
        # A visible stack needs a beat between cards; collapse_on_dismiss and
        # max_visible only mean something when more than one toast is on screen.
        if index + 1 < len(probes):
            time.sleep(args.delay)

    report["sent"] = sent
    if warnings:
        report["warnings"] = warnings
        report["notes"].append(
            "an auxiliary probe was refused; the shell's own notification path is what "
            "this test judges, so that alone does not fail it")
    if failed:
        report["verdict"] = "error"
        report["errors"] = failed
    elif sent == 0:
        report["verdict"] = "not-run"
    else:
        report["verdict"] = "sent"
    return _finish_notify_test(report, args)


def _finish_notify_test(report: Dict[str, Any], args: argparse.Namespace) -> int:
    if args.json:
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        _print_notify_test(report)
    if report["verdict"] == "error":
        return EXIT_FAILED
    return EXIT_OK


def _print_notify_test(report: Dict[str, Any]) -> None:
    ipc = report["shell_ipc"]
    if isinstance(ipc, dict):
        shell = (f"{NOCTALIA_BIN} answered" if ipc.get("returncode") == 0
                 else f"{NOCTALIA_BIN} replied with exit {ipc.get('returncode')}")
    else:
        shell = str(ipc)
    dnd = report["do_not_disturb"]
    dnd_text = {True: "on — toasts are suppressed", False: "off",
                None: "unknown"}[dnd]
    daemons = report["competing_daemons"]
    print("iarch-doctor: notification test")
    print(f"  shell IPC       {shell}")
    print(f"  do not disturb  {dnd_text}")
    if daemons:
        print(f"  other daemons   {', '.join(daemons)}")
    elif report["competing_daemons_searched"]:
        print("  other daemons   none seen")
    else:
        # Saying "none" here would claim a search that never happened.
        print("  other daemons   not searched")
    if report["competing_daemons_note"]:
        print(f"                  ({report['competing_daemons_note']})")
    for probe in report["probes"]:
        marker = {"sent": "OK", "error": "FAIL", "not-run": "SKIP",
                  "dry-run": "DRY"}.get(probe["verdict"], probe["verdict"].upper())
        kind = "external" if probe["id"] == "external" else "internal"
        print(f"  [{marker}] {probe['id']:<9} {kind:<8} {probe['detail']}")
    if report["verdict"] == "sent":
        print(f"  {report.get('sent', 0)} probe(s) acknowledged by the shell")
        print("  look for: the top-right margin, the slide in, the progress accent,")
        print("            hover pausing the countdown, and the critical card's red edge")
    for note in report["notes"]:
        print(f"  note: {note}")


# --------------------------------------------------------------- dnd


def cmd_dnd(args: argparse.Namespace) -> int:
    action = args.action
    if action == "status":
        state, answer = dnd_status()
    else:
        answer = dnd_toggle() if action == "toggle" else dnd_set(action == "on")
        state = None
        if answer is not None and answer.ok:
            # Read the state back instead of assuming the shell did what it was
            # asked: the handlers answer "ok" without echoing the new value, and
            # "is now on" should be something this tool observed.
            state, _ = dnd_status()

    if answer is None:
        installed = shutil.which(NOCTALIA_BIN) is not None
        detail = (f"{NOCTALIA_BIN} is installed but gave no answer" if installed
                  else f"{NOCTALIA_BIN} is not installed")
        detail += ", so Do Not Disturb could not be read or set"
        payload = {"check": "dnd", "action": action, "state": None, "verdict": "not-run",
                   "detail": detail}
        if args.json:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")
        elif action == "status":
            # `status` is the one action other tools read: stdout stays a single
            # word a script can branch on, and the reason goes to stderr.
            print("unknown")
            print(f"iarch-doctor: {detail}", file=sys.stderr)
        else:
            print(f"iarch-doctor: {detail}")
        return EXIT_OK

    verdict = "ok" if (answer.ok or (action == "status" and answer.returncode == 0)) else "error"
    payload = {
        "check": "dnd",
        "action": action,
        "state": state,
        "verdict": verdict,
        "detail": answer.stdout or answer.error_text,
        "answer": answer.as_dict(),
        "note": ("v5.4.1 has no DND schedule: the state is IPC-only, so anything that wants "
                 "quiet hours has to call this command itself"),
    }
    if args.json:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        if verdict == "error":
            print(f"iarch-doctor: dnd {action} failed: {payload['detail']}")
        elif action == "status":
            print("on" if state else "off")
        else:
            print(f"iarch-doctor: do not disturb is now {'on' if state else 'off'}")
    return EXIT_OK if verdict == "ok" else EXIT_FAILED


# --------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iarch-doctor",
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    test = sub.add_parser(
        "notify-test",
        help="send test notifications through Noctalia's own daemon",
        description="Send low, normal and critical probes through the shell's built-in "
                    "notification daemon, after reporting Do Not Disturb and any other "
                    "daemon in the process table. Sends nothing when Do Not Disturb is on "
                    "unless --force is given.",
    )
    test.add_argument("--force", action="store_true",
                      help="send even when Do Not Disturb is on (the toasts will be suppressed)")
    test.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS,
                      help=f"timeout for the low and normal probes (default {DEFAULT_TIMEOUT_MS})")
    test.add_argument("--delay", type=float, default=0.8,
                      help="seconds between probes, so the cards stack visibly (default 0.8)")
    test.add_argument("--dry-run", action="store_true",
                      help="print the commands without sending anything")
    test.add_argument("--json", action="store_true", help="print one JSON object and nothing else")
    test.set_defaults(func=cmd_notify_test)

    dnd = sub.add_parser(
        "dnd",
        help="read or set Do Not Disturb (IPC-only upstream; there is no schedule)",
    )
    dnd.add_argument("action", choices=("on", "off", "toggle", "status"))
    dnd.add_argument("--json", action="store_true", help="print one JSON object and nothing else")
    dnd.set_defaults(func=cmd_dnd)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "timeout_ms", None) is not None and args.timeout_ms < 0:
        print("iarch-doctor: --timeout-ms cannot be negative", file=sys.stderr)
        return EXIT_USAGE
    if getattr(args, "delay", None) is not None and args.delay < 0:
        print("iarch-doctor: --delay cannot be negative", file=sys.stderr)
        return EXIT_USAGE
    try:
        return args.func(args)
    except DoctorError as exc:
        print(f"iarch-doctor: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"iarch-doctor: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
