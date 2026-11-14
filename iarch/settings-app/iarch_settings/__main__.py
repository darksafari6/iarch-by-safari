#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""``python -m iarch_settings``: the same entry point the launcher script uses.

The launcher installed as ``iarch-settings`` and this module are one code path, and this
file is the whole of it: :func:`iarch_settings.widgets.app.main` answers an exit status and
this turns it into the process's. Keeping the two entry points identical is what makes the
launcher testable -- a test can run this module in a subprocess and read the status, and
nothing about the installed script is on a path no test reaches.

A machine with no usable toolkit exits non-zero with one sentence on stderr naming the
typelib that is missing and the package that provides it, rather than with a traceback:
:func:`~iarch_settings.gtkenv.describe` is that sentence, and ``main`` is what prints it.
"""
from __future__ import annotations

import sys

from .widgets.app import main

if __name__ == "__main__":
    sys.exit(main())
