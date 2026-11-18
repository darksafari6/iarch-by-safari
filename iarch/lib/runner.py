# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""One way to ask another program a question, with an answer that cannot crash us.

Purpose
    Every place in this project that runs an external command — the compositor,
    the shell engines, ``pgrep``, ``dbus-send`` — goes through here, so that the
    three rules the repository states in docs/ARCHITECTURE.md are stated once:
    argument lists instead of shell strings, a timeout on every call, and a
    missing binary reported as "could not be asked" rather than as a clean answer.

Inputs
    An argument list (``("hyprctl", "reload")``), a timeout in seconds, and an
    optional environment mapping. Never a string handed to a shell.

Outputs
    ``Answer`` — the command, its exit status, its captured output, and whether it
    timed out — or ``None`` when the program is not installed. ``None`` and a
    non-zero exit are different facts and callers must not confuse them: a probe
    that could not run says so instead of reporting success.

Dependencies
    Standard library only: ``dataclasses``, ``shutil``, ``subprocess``, ``typing``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

#: Every external call gets a timeout. A command that hangs must not hang the
#: desktop, and a caller that wants a different budget says so explicitly.
DEFAULT_TIMEOUT_SECONDS = 30.0

#: The type of the injectable runner. Tests pass a fake with the same signature,
#: which is what makes the theme apply pipeline and the engine switch testable
#: without a compositor, a shell or a bus in the room.
Runner = Callable[..., Optional["Answer"]]


@dataclass(frozen=True)
class Answer:
    """What an external program said, or how it failed to say anything."""

    command: Tuple[str, ...]
    returncode: Optional[int]
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    note: Optional[str] = field(default=None)

    @property
    def ok(self) -> bool:
        """True only for a command that ran and exited zero."""
        return self.returncode == 0

    @property
    def ran(self) -> bool:
        """True when the program was reached at all, whatever it answered."""
        return self.timed_out or self.returncode is not None

    def lines(self) -> List[str]:
        """Standard output as stripped, non-empty lines."""
        return [line.strip() for line in self.stdout.splitlines() if line.strip()]

    def as_json(self) -> Any:
        """Standard output parsed as JSON, or ``None`` if it is not JSON."""
        if not self.ok:
            return None
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError:
            return None

    def as_dict(self) -> Dict[str, Any]:
        """This answer as a report fragment, for ``--json`` output."""
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "note": self.note,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }

    def describe(self) -> str:
        """A sentence a person can act on: what ran, and why it did not answer."""
        text = " ".join(self.command)
        if self.timed_out:
            return f"`{text}` did not finish in time"
        if self.returncode is None:
            return f"`{text}` could not be run" + (f": {self.note}" if self.note else "")
        if self.returncode != 0:
            detail = (self.stderr or self.stdout).strip().splitlines()
            tail = f": {detail[-1]}" if detail else ""
            return f"`{text}` exited {self.returncode}{tail}"
        return f"`{text}` answered"


def which(binary: str) -> Optional[str]:
    """The path of an installed program, or ``None`` when it is not on PATH."""
    return shutil.which(binary)


def run(command: Sequence[str], timeout: float = DEFAULT_TIMEOUT_SECONDS,
        env: Optional[Mapping[str, str]] = None) -> Optional[Answer]:
    """Run one command and capture it. ``None`` means the program is not installed.

    The command is passed as an argument list, so no shell parses it and nothing in
    it can be expanded by one. Output is captured rather than inherited: a probe
    that prints into the user's terminal is a probe whose result nobody can read.
    """
    args: Tuple[str, ...] = tuple(command)
    if not args:
        return None
    if which(args[0]) is None:
        return None
    try:
        result = subprocess.run(list(args), check=False, capture_output=True, text=True,
                                timeout=timeout, env=dict(env) if env is not None else None)
    except subprocess.TimeoutExpired as exc:
        return Answer(args, None, str(exc.stdout or ""), str(exc.stderr or ""), timed_out=True,
                      note=f"timed out after {timeout:g}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return Answer(args, None, "", str(exc), note=f"could not be started: {exc}")
    return Answer(args, result.returncode, result.stdout, result.stderr)


def run_json(command: Sequence[str], timeout: float = DEFAULT_TIMEOUT_SECONDS,
             env: Optional[Mapping[str, str]] = None) -> Tuple[Optional[Any], Optional[Answer]]:
    """Run a command for its JSON answer.

    Returns the parsed value and the answer it came from, so a caller can tell
    "the program said nothing parseable" apart from "the program is not here".
    """
    answer = run(command, timeout=timeout, env=env)
    if answer is None:
        return None, None
    return answer.as_json(), answer


def run_lines(command: Sequence[str], timeout: float = DEFAULT_TIMEOUT_SECONDS,
              env: Optional[Mapping[str, str]] = None) -> Tuple[Optional[List[str]], Optional[Answer]]:
    """Run a command for its output lines. ``None`` means it could not be asked."""
    answer = run(command, timeout=timeout, env=env)
    if answer is None or not answer.ok:
        return None, answer
    return answer.lines(), answer
