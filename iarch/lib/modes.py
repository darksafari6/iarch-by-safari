# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Shared machinery behind the two mode switches, ``iarch-gamemode`` and ``iarch-focus``.

A *mode* is a named bundle of switches that already exist. Neither tool invents a
config leaf, a value outside a recorded range, or a second source of truth for
something the tokens already decide: what they add is the round trip. Each one
reads the state it is about to replace, records it, applies the bundle, asks the
session what it now runs, and can put everything back. The values themselves live
in ``data/design/tokens.json`` under ``modes``, so changing what a mode means is a
data edit that the tools, the tests and the documentation all follow.

Four rules are implemented here once rather than twice, because getting any of
them wrong in one tool and right in the other is how a desktop ends up in a state
nobody can describe:

* **A missing binary is unverified, never a failure and never a pass.** No
  ``hyprctl`` and no ``noctalia`` in a chroot, in CI or on a fresh install before
  the first login means the question could not be asked. ``run`` returns ``None``
  and every caller has to keep that apart from an answer it did not like.
* **Verification compares, it does not assume.** ``getoption`` reads a leaf back
  from the compositor and the caller compares it with the value the tokens say
  the applied state should have. A tool that printed "applied" because its own
  write succeeded would be reporting its intention.
* **hyprctl's exit status is not a verdict.** The client prints whatever the
  compositor replied and exits 7 only when that reply starts with ``error:``
  (``hyprctl/src/main.cpp:283-288`` at v0.57.2), so an unregistered command --
  which answers ``unknown request``, ``src/ipc/s1/S1.cpp:107`` -- and an ``eval``
  the Lua config manager refused both look like success by exit code alone.
  ``Reply.ok`` therefore reads the reply text, the way
  ``iarch/cli/iarch_doctor.py`` reads the shell's.
* **A rejected change leaves nothing claiming it happened.** ``write_mode`` is
  called after an apply succeeded, never before, and ``call_sibling`` reports the
  sibling's own exit code so a caller can undo what the sibling did not.

The runners live here rather than being copied a third time: ``iarch_anim.py``
has its own ``hyprctl`` helpers and ``iarch_doctor.py`` its own ``noctalia`` ones,
and both were written before there was a second tool that needed the same answer
to the same question.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from iarch.lib import configstore

ROOT = Path(__file__).resolve().parents[2]

EXIT_OK = 0
EXIT_REFUSED = 1  # a gate refused, the session rejected the result, or it was rolled back
EXIT_USAGE = 2    # bad arguments, an unknown mode value, a render or data error

HYPRCTL = "hyprctl"
NOCTALIA_BIN = "noctalia"

# Long enough for a compositor that is busy reloading eleven files, short enough
# that a hung socket does not stall the command. The hyprctl client itself gives
# the socket a five second receive timeout (hyprctl/src/main.cpp:213-215).
TIMEOUT_SECONDS = 30

SETTINGS_NAME = "settings"

# The three verdicts a comparison can reach. "unverified" is not a polite word
# for failure: it means the question could not be asked.
MATCHES = "matches"
DIFFERS = "differs"
UNVERIFIED = "unverified"

OK_REPLY = "ok"

# The keys dispatchGetOption can answer with, in the order it tests them
# (src/ipc/s1/Commands.cpp:1772-1799 at v0.57.2). Exactly one is present per
# reply, chosen by the declared type of the leaf.
VALUE_KEYS: Tuple[str, ...] = (
    "bool", "int", "float", "str", "vec2", "custom", "css", "gradient", "font_weight",
)

# Compared with a tolerance because the compositor prints a float with two
# decimals (`{:2f}`, src/ipc/s1/Commands.cpp:1776), so 0.5 comes back as 0.50
# and a token of 0.06 as 0.06.
FLOAT_TOLERANCE = 1e-6


class ModeError(RuntimeError):
    """A usage or data problem: nothing was changed, and the caller says why."""


# ---------------------------------------------------------------- one command


class Reply:
    """One command's answer, or the reason there is none.

    ``run`` returns ``None`` when the binary is not on PATH or could not be
    started at all, which is different from a Reply with a non-zero exit code:
    the first means the session could not be asked, the second means it answered
    and did not like the question.
    """

    def __init__(self, command: Sequence[str], returncode: int, stdout: str,
                 stderr: str) -> None:
        self.command = tuple(command)
        self.returncode = returncode
        self.stdout = stdout.strip()
        self.stderr = stderr.strip()

    @property
    def ok(self) -> bool:
        """The reply was the literal ``ok`` and the exit code was clean.

        Both halves matter. ``hyprctl eval`` returns ``ok`` from a Lua config
        manager that ran the code without an error (src/ipc/s1/Commands.cpp:1316-
        1330), and the Noctalia shell's msg handlers return the same word, but an
        ``eval`` whose code called ``hl.config`` with an unknown key comes back as
        ``error: ...`` *and* exit 7 (src/config/lua/ConfigManager.cpp:900-918).
        """
        return self.returncode == 0 and self.stdout == OK_REPLY

    @property
    def failed(self) -> bool:
        """The compositor or the shell said no, in words rather than in an exit code."""
        return self.stdout.startswith("error:") or self.returncode != 0

    @property
    def text(self) -> str:
        return self.stderr or self.stdout

    def as_dict(self) -> Dict[str, Any]:
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "ok": self.ok,
        }


def run(command: Sequence[str]) -> Optional[Reply]:
    """Run one command with no shell in between; ``None`` when it cannot be run.

    Nothing here is ever built from user input, and nothing is ever run through
    ``/bin/sh``: the one place this project ships a shell string is
    ``.config/hypr/hypridle.conf``, which hypridle itself runs through
    ``/bin/sh -c`` (hypridle src/core/Hypridle.cpp:286-289).
    """
    if shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run(tuple(command), check=False, capture_output=True,
                                text=True, timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    return Reply(command, result.returncode, result.stdout, result.stderr)


def hyprctl(*args: str) -> Optional[Reply]:
    return run((HYPRCTL,) + args)


def noctalia_msg(*args: str) -> Optional[Reply]:
    """``noctalia msg <args>`` — the shell's IPC verb."""
    return run((NOCTALIA_BIN, "msg") + args)


def getoption(leaf: str) -> Tuple[Optional[Any], Optional[Reply]]:
    """Read one config leaf back from the compositor.

    Returns ``(value, reply)``. ``value`` is ``None`` when the leaf could not be
    read -- no ``hyprctl``, no session, a non-zero exit, or a reply that is not
    JSON -- and the caller must then say the state is unverified rather than
    guess. An unknown leaf answers with the literal ``no such option`` even under
    ``-j`` (src/ipc/s1/Commands.cpp:1740), which is not JSON and lands here as
    ``None`` with the reply attached, so "the compositor does not have this leaf"
    stays distinguishable from "the compositor was not running" by reading
    ``reply.stdout``.

    ``decoration:dim_strength`` resolves even though the Lua config manager keys
    its values with dots: ``getConfigValue`` falls back to ``luaConfigValueName``,
    which replaces ``:`` with ``.`` and ``-`` with ``_``
    (src/config/lua/ConfigManager.cpp:1004-1025, :1114-1119).
    """
    reply = hyprctl("getoption", leaf, "-j")
    if reply is None or reply.returncode != 0:
        return None, reply
    try:
        data = json.loads(reply.stdout)
    except json.JSONDecodeError:
        return None, reply
    if not isinstance(data, dict):
        return None, reply
    for key in VALUE_KEYS:
        if key in data:
            return data[key], reply
    return None, reply


def same_value(expected: Any, actual: Any) -> bool:
    """Compare a token value with one read back, without tripping over 0.50."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(expected) == bool(actual)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= FLOAT_TOLERANCE
    return expected == actual


def configerrors() -> Optional[List[str]]:
    """The compositor's config parsing errors, or ``None`` if it cannot be asked.

    Read as lines rather than as JSON, the way ``iarch_anim.py`` reads them: the
    JSON form is assembled by hand in ``configErrorsRequest`` while the normal
    form is exactly the error lines (src/ipc/s1/Commands.cpp:2104 registration).
    Empty output is a config the compositor parsed cleanly; ``None`` is no answer.
    """
    reply = hyprctl("configerrors")
    if reply is None or reply.returncode != 0:
        return None
    return [line.strip() for line in reply.stdout.splitlines() if line.strip()]


def call_sibling(entry: Callable[[Optional[Sequence[str]]], int], argv: Sequence[str],
                 tool: str) -> Tuple[int, List[str], List[str]]:
    """Run a sibling CLI in this process and keep its output instead of printing it.

    ``iarch-gamemode`` composes ``iarch-theme`` and ``iarch-anim`` rather than
    reimplementing either: the contrast gate, the eleven render targets, the
    atomic writes, the backup rotation and the reload-then-verify-or-roll-back
    sequence all stay in the tools that own them, and a mode cannot drift away
    from what running them by hand would do.

    Returns ``(exit_code, stdout_lines, stderr_lines)``. The sibling's own exit
    code is passed through untouched, because it is the sibling that knows
    whether a gate refused (1) or the arguments were bad (2).
    """
    out, err = io.StringIO(), io.StringIO()
    code = EXIT_OK
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = entry(list(argv))
    except SystemExit as exc:  # argparse refused the arguments this tool built
        code = exc.code if isinstance(exc.code, int) else EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - a sibling's main() catches its own
        code = EXIT_USAGE
        err.write(f"{tool}: {exc}\n")
    return int(code or 0), out.getvalue().splitlines(), err.getvalue().splitlines()


def parse_json_reply(lines: Sequence[str]) -> Optional[Any]:
    """The one JSON document a sibling printed under ``--json``, or ``None``."""
    text = "\n".join(lines).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- mode state


def _raw_settings(env: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """The user's own settings file, unmerged.

    Read raw rather than through ``configstore.load``, which puts the repository
    defaults underneath: a mode that was never switched on has to stay
    distinguishable from one whose record happens to match the default.
    """
    path = configstore.user_path(SETTINGS_NAME, env)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModeError(f"{path} cannot be read as JSON: {exc}") from exc
    return data if isinstance(data, dict) else {}


def mode_state(env: Optional[Dict[str, str]], name: str) -> Dict[str, Any]:
    """What ``modes.<name>`` records, or ``{}`` when nothing does."""
    modes = _raw_settings(env).get("modes")
    if not isinstance(modes, dict):
        return {}
    block = modes.get(name)
    return dict(block) if isinstance(block, dict) else {}


def is_active(env: Optional[Dict[str, str]], name: str) -> bool:
    return bool(mode_state(env, name).get("active"))


def write_mode(env: Optional[Dict[str, str]], name: str, payload: Dict[str, Any],
               repo_root: Path = ROOT) -> Tuple[Path, bool]:
    """Record one mode's state in the user's settings; return ``(path, changed)``.

    ``configstore.load`` merges the repository defaults under the user's file, so
    saving that document back keeps every other key the person had -- the theme,
    the animation state, the other mode -- and the file written always validates
    against ``data/schemas/settings.schema.json``. Recording the same state twice
    is a no-op: no rewrite and no rotated backup, matching how the generators skip
    a file whose bytes already match.
    """
    path = configstore.user_path(SETTINGS_NAME, env)
    if path.is_file() and mode_state(env, name) == payload:
        return path, False
    settings = configstore.load(SETTINGS_NAME, repo_root, env)
    modes = dict(settings.get("modes") or {})
    modes[name] = payload
    settings["modes"] = modes
    return configstore.save(SETTINGS_NAME, settings, env), True


# ---------------------------------------------------------------- the tokens


def load_tokens(repo_root: Path = ROOT) -> Dict[str, Any]:
    path = repo_root / "data" / "design" / "tokens.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModeError(f"{path} cannot be read as JSON: {exc}") from exc


def tokens_modes(tokens: Dict[str, Any]) -> Dict[str, Any]:
    """The ``modes`` block, refusing a shape the tools cannot honour.

    The schema already checks this file in CI; the check here is for a tokens
    file somebody edited by hand after install, where the failure would otherwise
    surface as a KeyError halfway through changing a desktop.
    """
    modes = tokens.get("modes")
    if not isinstance(modes, dict):
        raise ModeError("data/design/tokens.json has no `modes` block, so neither mode "
                        "switch knows what it is supposed to apply")
    for name in ("game", "focus"):
        if not isinstance(modes.get(name), dict):
            raise ModeError(f"data/design/tokens.json modes.{name} is missing or is not an object")
    game = modes["game"]
    intensity = game.get("intensity")
    if not isinstance(intensity, str) or intensity not in tokens.get("intensities", {}):
        known = ", ".join(sorted(tokens.get("intensities", {})))
        raise ModeError(f"modes.game.intensity is {intensity!r}, which the tokens do not "
                        f"define; the intensities are {known}")
    focus = modes["focus"]
    if not isinstance(focus.get("dim_inactive"), bool):
        raise ModeError("modes.focus.dim_inactive must be a boolean")
    strength = focus.get("dim_strength")
    if not isinstance(strength, (int, float)) or isinstance(strength, bool):
        raise ModeError(f"modes.focus.dim_strength is {strength!r}, not a number")
    bounds = tokens.get("hyprland", {}).get("ranges", {}).get("decoration:dim_strength")
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        low, high = bounds
        if not low <= float(strength) <= high:
            raise ModeError(f"modes.focus.dim_strength {strength} is outside the "
                            f"{low}..{high} the compositor enforces for that leaf")
    leaves = focus.get("leaves")
    if not isinstance(leaves, list) or not leaves:
        raise ModeError("modes.focus.leaves must name at least one Hyprland leaf")
    recorded = set(tokens.get("hyprland", {}).get("leaves", []))
    for leaf in leaves:
        if leaf not in recorded:
            raise ModeError(f"modes.focus.leaves names {leaf!r}, which is not in "
                            "hyprland.leaves; a leaf that is not recorded there is one "
                            "no tool in this repository may set")
    return modes


# ---------------------------------------------------------------- reporting

_JSON_MODE = False


def set_json_mode(flag: bool) -> None:
    """``--json`` promises one object on stdout and nothing else."""
    global _JSON_MODE
    _JSON_MODE = bool(flag)


def say(message: str) -> None:
    if _JSON_MODE:
        return
    # Flushed, because warnings go to stderr and the two are read together.
    print(message, flush=True)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def new_report(command: str, mode: str) -> Dict[str, Any]:
    """The one report a run fills in, printed at the end whatever happened.

    Owned here and handed to the subcommand the way ``iarch_anim.py`` does it, so
    a refusal or a usage error still reports everything learned before it -- the
    state that was read, what each sibling said, and what the session answered.
    """
    return {
        "tool": f"iarch-{mode}",
        "command": command,
        "mode": mode,
        "ok": True,
        "applied": False,
        "dry_run": False,
        "active": None,
        "record": {},
        "previous": {},
        "steps": [],
        "checks": [],
        "verdict": UNVERIFIED,
        "warnings": [],
        "notes": [],
        "skipped": [],
        "ran": [],
        "rollback": None,
        "error": None,
        "exit": EXIT_OK,
    }


def emit(report: Dict[str, Any]) -> None:
    if _JSON_MODE:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")


def overall_verdict(checks: Sequence[Dict[str, Any]]) -> str:
    """One verdict for a list of comparisons.

    A check that differs wins over one that matches, because a desktop half in a
    mode is the state a person needs told about; unverified wins over matches
    only when nothing differs, so "I could not ask" is never printed as "all
    good". No checks at all is unverified, not clean.
    """
    verdicts = {check.get("verdict") for check in checks}
    if DIFFERS in verdicts:
        return DIFFERS
    if not verdicts or UNVERIFIED in verdicts:
        return UNVERIFIED
    return MATCHES


def exit_for_verdict(report: Dict[str, Any], reason: str,
                     keep: str = "the files and the record") -> int:
    """``EXIT_OK`` unless the session was asked and disagreed.

    A disagreement after a change that every tool accepted is *not* rolled back.
    The files and the record then describe one state and the compositor runs
    another, and rewriting the files to match a compositor that just answered
    something else would leave both sides describing a state nobody asked for --
    so the change stays, the report says exactly which leaf differs, and the exit
    code says the request did not take. ``UNVERIFIED`` is not a disagreement: a
    session that could not be asked is reported as unverified and exits 0, because
    failing on a missing binary would make this tool unusable from a script on any
    machine that is not running Hyprland right now.
    """
    if report.get("verdict") != DIFFERS:
        return EXIT_OK
    report["ok"] = False
    report["error"] = reason
    report["exit"] = EXIT_REFUSED
    report["notes"].append(f"{reason}; {keep} were left as they are, because rolling back "
                           "would make the disk disagree with the session too")
    warn(f"{reason}; {keep} were left as they are, because rolling back would make the "
         f"disk disagree with the session too. `hyprctl configerrors` says whether a key "
         f"was rejected.")
    return EXIT_REFUSED
