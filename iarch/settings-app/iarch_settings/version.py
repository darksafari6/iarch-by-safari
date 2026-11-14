# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The version and the build date, read rather than repeated.

The About page shows a version, and the work order is explicit that it comes from
one ``VERSION`` file: a string pasted into a Python module and into a desktop
entry and into documentation is three strings that will disagree. So
``VERSION`` at the repository root is the only place the number is written, and
everything else -- the About dialog, the desktop entry's version comment, the
debug block a bug report carries -- reads it through here.

The build date is the date of the commit the checkout is on, because that is the
one date this repository can state truthfully: there is no build server, so a
timestamp baked at packaging time would describe a build that never happened. When
the checkout is not a git repository (an exported tarball) the answer is
``unknown``, not a guess.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Mapping, Optional

from . import paths

VERSION_FILE = "VERSION"
"""The one file that states the version, at the repository root."""

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?$")
"""A version this project accepts: three numbers, with an optional suffix.

Deliberately not semantic versioning in the strict sense -- ``CHANGELOG.md`` says
versions follow the six-part plan because nothing here is a library anyone links
against -- but still machine-checkable, so a stray edit is caught by a test
instead of appearing in the About dialog.
"""

UNKNOWN = "unknown"

#: Long enough for a git command on a cold checkout, short enough that a hung
#: filesystem does not stall the About page.
GIT_TIMEOUT_SECONDS = 5


class VersionError(RuntimeError):
    """The version could not be read, or does not look like one."""


def version_path(root: Optional[Path] = None) -> Path:
    return (root or paths.repo_root()) / VERSION_FILE


def read_version(root: Optional[Path] = None) -> str:
    """The version string from :data:`VERSION_FILE`.

    Raises :class:`VersionError` when the file is missing or its content is not a
    version. A missing version is a packaging fault and is reported as one: the
    alternative is an About dialog that says something invented.
    """
    path = version_path(root)
    if not path.is_file():
        raise VersionError(f"{path} is missing; the version is not recorded anywhere else")
    text = path.read_text(encoding="utf-8").strip()
    if not VERSION_PATTERN.fullmatch(text):
        raise VersionError(
            f"{path} does not hold a version: {text!r}. "
            f"Expected something like 0.4.0 (pattern {VERSION_PATTERN.pattern}).")
    return text


def build_date(root: Optional[Path] = None, env: Optional[Mapping[str, str]] = None) -> str:
    """The date of the commit this checkout is on, or :data:`UNKNOWN`.

    ``git`` is called with a list of arguments and no shell, and a checkout that
    is not a repository -- or a machine with no git -- answers ``unknown`` rather
    than failing: the About page is not allowed to break because a date is
    unavailable.
    """
    resolved = root or paths.repo_root()
    environ = dict(os.environ if env is None else env)
    try:
        completed = subprocess.run(
            ["git", "-C", str(resolved), "log", "-1", "--format=%cs"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
            check=False, env=environ, shell=False)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    date = completed.stdout.strip()
    return date if completed.returncode == 0 and date else UNKNOWN


def facts(root: Optional[Path] = None, env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Everything the About page states about this build, as flat strings."""
    from . import gtkenv  # imported late: it probes the toolkit

    resolved = root or paths.repo_root()
    facts_: Dict[str, str] = {
        "product": "iArch by Safari",
        "version": read_version(resolved),
        "build_date": build_date(resolved, env),
        "revision": revision(resolved, env),
        "python": platform.python_version(),
        "system": f"{platform.system()} {platform.release()}",
        "toolkit": gtkenv.describe(),
        "checkout": str(resolved),
    }
    return facts_


def revision(root: Optional[Path] = None, env: Optional[Mapping[str, str]] = None) -> str:
    """The short commit id, or :data:`UNKNOWN`."""
    resolved = root or paths.repo_root()
    environ = dict(os.environ if env is None else env)
    try:
        completed = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
            check=False, env=environ, shell=False)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else UNKNOWN


def debug_info(root: Optional[Path] = None, env: Optional[Mapping[str, str]] = None) -> str:
    """The block a bug report carries, including where this user's state lives.

    Paths are included because "it did not apply" is usually a question about
    which ``~/.config`` was written to, and the compositor's presence is included
    because a missing ``hyprctl`` explains a page full of *unverified* rows.
    """
    from . import gtkenv, services  # imported late: services probes the session

    items = facts(root, env)
    lines = [f"{key.replace('_', ' ')}: {value}" for key, value in items.items()]
    try:
        lines.append(f"config dir: {paths.config_dir(env)}")
        lines.append(f"state dir: {paths.state_dir(env)}")
    except paths.PathError as exc:
        lines.append(f"config dir: {exc}")
    lines.append(f"settings schema: {'jsonschema ' + _jsonschema_version()}"
                 if _jsonschema_version() else "settings schema: not validated (jsonschema missing)")
    lines.append(f"compositor: {services.hyprctl_present() and 'hyprctl on PATH' or 'hyprctl not on PATH'}")
    lines.append(f"shell: {services.noctalia_present() and 'noctalia on PATH' or 'noctalia not on PATH'}")
    lines.append(f"interface: {'available' if gtkenv.available() else 'unavailable'}")
    return "\n".join(lines)


def _jsonschema_version() -> str:
    try:
        from importlib.metadata import version
    except ImportError:  # pragma: no cover - Python 3.7 and older
        return ""
    try:
        return version("jsonschema")
    except Exception:  # noqa: BLE001 - a broken distribution says "not validated"
        return ""


if __name__ == "__main__":  # pragma: no cover - a convenience, not an interface
    print(read_version())
    sys.exit(0)
