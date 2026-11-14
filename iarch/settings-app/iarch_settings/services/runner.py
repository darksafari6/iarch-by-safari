# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""How this application talks to other programs.

One rule, stated once so no service has to restate it: **a command is a list of
arguments and there is no shell.** :func:`subprocess.run` is called with a list,
never with a string, and never with ``shell=True``. A settings value, a path from
a file picker or a link from a JSON file the user can edit all end up as argv
elements here, and an argv element cannot escape itself -- the shell is what
would let one escape.

The second rule is about honesty. A command that cannot be started because the
program is not installed is not a failure and not a success: it is *unverified*,
and :class:`Outcome` says so with its own verdict instead of borrowing an exit
code. ``iarch/lib/modes.py`` already draws this line for the mode switches, and
every probe in this package follows it, because "the compositor said 0" and "there
was no compositor" lead to opposite decisions in the apply pipeline.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

HYPRCTL = "hyprctl"
NOCTALIA_BIN = "noctalia"

#: The binaries a service may look for. Each one is a probe, never a promise: a
#: page that needs one asks first and shows what it could not check. ``systemctl``
#: is here for one read-only question -- whether the session's autostart generator
#: ran at all -- and a missing one is unverified, not a failure.
BINARIES = (HYPRCTL, NOCTALIA_BIN, "xdg-mime", "xdg-settings", "systemctl",
            "fc-list", "git")

#: Every command this application runs is given a wall-clock limit. A hung
#: compositor client must not hang the interface with it.
DEFAULT_TIMEOUT = 10.0

#: Verdicts, in the order the apply pipeline reads them.
OK = "ok"
FAILED = "failed"
UNVERIFIED = "unverified"


class RunnerError(RuntimeError):
    """A command was refused before it could run."""


class Outcome:
    """What one command did.

    ``verdict`` is the only field a caller should branch on. ``exit_code`` is
    kept for the report and for nothing else: an unregistered hyprctl subcommand
    exits 0, and a shell verb that answers ``ok`` can still have done nothing, so
    neither an exit code nor a reply string is a verdict on its own.
    """

    __slots__ = ("argv", "verdict", "exit_code", "stdout", "stderr", "reason")

    def __init__(
        self,
        argv: Sequence[str],
        verdict: str,
        exit_code: Optional[int] = None,
        stdout: str = "",
        stderr: str = "",
        reason: str = "",
    ) -> None:
        if verdict not in (OK, FAILED, UNVERIFIED):
            raise RunnerError(f"unknown verdict {verdict!r}")
        self.argv = list(argv)
        self.verdict = verdict
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"Outcome(argv={self.argv!r}, verdict={self.verdict!r}, "
                f"exit_code={self.exit_code!r}, reason={self.reason!r})")

    @property
    def ok(self) -> bool:
        return self.verdict == OK

    @property
    def ran(self) -> bool:
        """True when the program existed and was started at all."""
        return self.verdict != UNVERIFIED

    def as_dict(self) -> dict:
        """The stable report shape. Every key a caller may read exists."""
        return {
            "argv": list(self.argv),
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "reason": self.reason,
        }


def which(binary: str) -> Optional[str]:
    """The absolute path of ``binary``, or ``None`` when it is not on PATH."""
    return shutil.which(binary)


def hyprctl_present() -> bool:
    """True when the compositor's client is on PATH and can be asked anything."""
    return which(HYPRCTL) is not None


def noctalia_present() -> bool:
    """True when the shell's binary is on PATH and can be sent a verb."""
    return which(NOCTALIA_BIN) is not None


def presence() -> dict:
    """Every probe at once, for the About page's debug information."""
    return {name: which(name) is not None for name in BINARIES}


def _argv(binary: str, args: Sequence[str]) -> List[str]:
    argv = [binary, *[str(arg) for arg in args]]
    if any("\x00" in part for part in argv):
        raise RunnerError("a command argument contains a NUL byte")
    return argv


def run(
    binary: str,
    args: Sequence[str] = (),
    *,
    timeout: float = DEFAULT_TIMEOUT,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
) -> Outcome:
    """Run ``binary`` with ``args`` and classify the result.

    Returns :data:`UNVERIFIED` when the program is not on PATH or cannot be
    started, :data:`FAILED` when it ran and reported a non-zero exit or timed
    out, and :data:`OK` otherwise. Never raises for a missing program, because
    every caller wants the same three-way answer.
    """
    argv = _argv(binary, args)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=env,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return Outcome(argv, UNVERIFIED, reason=f"{binary} is not installed")
    except PermissionError:
        return Outcome(argv, UNVERIFIED, reason=f"{binary} is not executable")
    except subprocess.TimeoutExpired:
        return Outcome(argv, FAILED, reason=f"{binary} did not answer in {timeout:g}s")
    except OSError as exc:
        return Outcome(argv, UNVERIFIED, reason=f"{binary} could not be started: {exc}")
    verdict = OK if completed.returncode == 0 else FAILED
    reason = "" if completed.returncode == 0 else f"{binary} exited {completed.returncode}"
    return Outcome(argv, verdict, completed.returncode, completed.stdout,
                   completed.stderr, reason)


def python_tool(path: Path, args: Sequence[str] = (), **kwargs) -> Outcome:
    """Run one of this repository's own tools with the current interpreter.

    The tools in ``iarch/cli/`` are not installed binaries yet (Part 6), so the
    honest invocation is ``python3 iarch/cli/<tool>.py``, which is what the
    documentation, the doctor and the installers already say. Using
    ``sys.executable`` rather than the literal ``python3`` keeps the child on the
    same interpreter as the parent, which matters when a distribution ships more
    than one.
    """
    import sys

    if not Path(path).is_file():
        return Outcome([str(path)], UNVERIFIED, reason=f"no such tool: {path}")
    return run(sys.executable, [str(path), *args], **kwargs)
