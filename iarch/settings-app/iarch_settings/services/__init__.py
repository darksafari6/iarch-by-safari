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

# The submodules are imported here so a page can write
# ``from ..services import autostart`` and get the module rather than an
# AttributeError, and so ``services.<name>`` is one namespace to list when asking
# what this application is capable of. None of them does work at import time --
# no probe, no read, no subprocess -- so importing the package costs an
# :mod:`ast`-shaped handful of module objects and nothing else.
from . import (  # noqa: F401  (re-exported: the package is the interface)
    apply,
    autostart,
    config_store,
    contacts,
    control,
    defaults,
    gtk_settings,
    hypr,
    licenses,
    links,
    noctalia,
    runner,
    system,
    themes,
)
from .runner import (  # noqa: F401  (re-exported: a page asks this package, not runner)
    BINARIES,
    HYPRCTL,
    NOCTALIA_BIN,
    hyprctl_present,
    noctalia_present,
    presence,
    which,
)

#: The service modules, in the order the pages meet them. ``MODULES`` is what a
#: :class:`iarch_settings.pages.plan.Context` is allowed to resolve into, so a plan
#: cannot point a row at anything outside this list -- which is the mechanism, not
#: the convention, that keeps a page from reaching into the machine by itself.
MODULES = (
    "apply",
    "autostart",
    "config_store",
    "contacts",
    "control",
    "defaults",
    "gtk_settings",
    "hypr",
    "licenses",
    "links",
    "noctalia",
    "runner",
    "system",
    "themes",
)

__all__ = [
    "BINARIES",
    "HYPRCTL",
    "MODULES",
    "NOCTALIA_BIN",
    "apply",
    "autostart",
    "config_store",
    "contacts",
    "control",
    "defaults",
    "gtk_settings",
    "hypr",
    "hyprctl_present",
    "licenses",
    "links",
    "noctalia",
    "noctalia_present",
    "presence",
    "runner",
    "system",
    "themes",
    "which",
]
