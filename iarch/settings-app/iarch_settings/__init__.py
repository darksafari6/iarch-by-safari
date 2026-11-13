# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""iArch by Safari settings application.

A GTK 4 and libadwaita control panel for the whole desktop: every switch Parts 1
to 3 introduced, reachable from one window, editing the same
``~/.config/iarch/settings.json`` the command line tools edit and calling the same
generators in ``iarch/cli/`` they call.

Two rules shape this package, and both are testable without a display:

* **Nothing here invents an API.** Every widget, style class, named colour, CSS
  property and icon name the interface uses is listed in
  ``data/design/adwaita.json`` with the upstream ref it was read from, and
  ``tests/test_settings_surface.py`` fails when the code and that record drift.
  GTK is not installed in this repository's CI, so a widget that does not exist
  would not fail here -- it would fail on somebody's desktop.
* **The logic does not import GTK.** Page definitions, the config store, the
  search index, the link validator, the apply pipeline and every service are
  plain Python, so they are unit tested as a normal user with no display. The
  widgets import ``gi`` inside the function that builds them, never at module
  level, which is what keeps a page's definition readable in a test.

The application id is :data:`APP_ID`. It is deliberately *not* the session's
``dev.safari.iarch`` from ``branding/product.env``: a Wayland compositor matches
window rules on the application id, and the glass rule that makes this window
translucent has to name one window rather than every window the session owns.
Both ids are recorded in ``data/design/adwaita.json`` and in
``data/design/tokens.json`` under ``app_classes.iarch_app``.
"""
from __future__ import annotations

APP_ID = "dev.safari.iarch.settings"
"""The Wayland/GTK application id, and the window class the compositor blurs."""

DOMAIN = "iarch-settings"
"""The gettext domain. Catalogues live in ``po/`` next to this package."""

DEFAULT_WIDTH = 1100
DEFAULT_HEIGHT = 720
MIN_WIDTH = 760
MIN_HEIGHT = 560

__all__ = [
    "APP_ID",
    "DOMAIN",
    "DEFAULT_WIDTH",
    "DEFAULT_HEIGHT",
    "MIN_WIDTH",
    "MIN_HEIGHT",
]
