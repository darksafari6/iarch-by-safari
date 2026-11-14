# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Everything the interface does to the machine, behind one directory.

A page never runs a command, writes a file or opens a link itself: it asks a
service, and the service is where the rules live. That split is what makes this
package testable with no display and no session, and it is the same split
``iarch/lib/modes.py`` already draws between deciding and doing.

The rules every service here follows:

* **A command is a list of arguments.** No service calls a shell, and none of
  them passes ``shell=True``: a value from a user-editable JSON file that reaches
  a shell is an injection, not a feature. ``services/links.py`` does not even
  import :mod:`subprocess`, and a test asserts that it still does not.
* **A missing binary is unverified.** No ``hyprctl`` and no ``noctalia`` means
  the question could not be asked, which is neither a pass nor a failure. Every
  probe here returns ``None`` for that case and the caller says so, exactly as
  ``iarch/lib/modes.py`` does.
* **A value another program owns is not copied here.** The shell's bar, dock,
  audio, idle and wallpaper keys are read and written through its IPC
  (``data/design/noctalia-ipc.json``), the compositor's leaves through hyprctl
  (``data/design/tokens.json``) and the power profile through the shell's UPower
  verb. ``~/.config/iarch/settings.json`` holds only what this project owns, so
  there is no second copy to disagree with the first.
* **A write is atomic and backed up.** Both come from
  :mod:`iarch.lib.configstore`, which already does temp-file, fsync, rename and
  a five-backup rotation; nothing here reimplements either.
"""
from __future__ import annotations

from .runner import (  # noqa: F401  (re-exported: a page asks this package, not runner)
    BINARIES,
    HYPRCTL,
    NOCTALIA_BIN,
    hyprctl_present,
    noctalia_present,
    presence,
    which,
)

__all__ = [
    "BINARIES",
    "HYPRCTL",
    "NOCTALIA_BIN",
    "hyprctl_present",
    "noctalia_present",
    "presence",
    "which",
]
