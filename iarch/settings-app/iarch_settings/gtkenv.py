# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The one place that talks to PyGObject.

Every module that builds a widget imports the namespaces from here instead of
calling :func:`gi.require_version` itself, so three things stay true at once:

* the namespaces are requested with the versions ``data/design/adwaita.json``
  records, in one place, rather than being spelled per file where they can drift;
* importing this module never raises, which is what lets a page's *definition* be
  read -- and tested -- on a machine with no GTK at all;
* a machine with no GTK gets one clear sentence naming the packages to install,
  instead of an ``ImportError`` from inside a widget constructor.

``gi.require_version`` raises :class:`ValueError` when the typelib is absent and
:func:`gi.require_version` itself is missing when PyGObject is not installed, so
both are caught: on a minimal system either can be the first thing to fail.
"""
from __future__ import annotations

from typing import Any, Tuple

#: The introspection versions, each with the upstream ref it was read from in
#: ``data/design/adwaita.json``: Gtk and Gdk 4.0 (GNOME/gtk@4.10.0:meson.build:88)
#: and Adw 1 (GNOME/libadwaita@1.7.12:meson.build:19). Gio needs no
#: ``require_version`` because it has exactly one ABI version.
NAMESPACES: Tuple[Tuple[str, str], ...] = (
    ("Gtk", "4.0"),
    ("Gdk", "4.0"),
    ("Adw", "1"),
)

#: The floor this record argues for, repeated here so the error message a user
#: sees on an older system names a number rather than a mystery.
MINIMUM_GTK = "4.10"
MINIMUM_ADWAITA = "1.6"

AVAILABLE = False
MISSING: Tuple[str, ...] = ()

Gtk: Any = None
Gdk: Any = None
Adw: Any = None
Gio: Any = None
GLib: Any = None
GObject: Any = None
Pango: Any = None


class UiUnavailable(RuntimeError):
    """GTK or libadwaita could not be loaded, with the packages to install named."""


def _load() -> bool:
    """Request the recorded versions and bind the namespaces. Never raises."""
    global AVAILABLE, MISSING, Gtk, Gdk, Adw, Gio, GLib, GObject, Pango
    try:
        import gi
    except ImportError:
        MISSING = ("PyGObject (Arch: python-gobject, Fedora: python3-gobject)",)
        return False

    missing = []
    try:
        for namespace, version in NAMESPACES:
            gi.require_version(namespace, version)
    except ValueError as exc:
        # "Namespace Adw not available" and friends: the typelib is not installed
        # or is older than the version requested above.
        missing.append(str(exc))
    if missing:
        MISSING = tuple(missing) + (
            f"libadwaita >= {MINIMUM_ADWAITA} (Arch: libadwaita, Fedora: libadwaita)",
            f"GTK >= {MINIMUM_GTK} (Arch: gtk4, Fedora: gtk4)",
        )
        return False

    from gi.repository import Adw as _Adw, Gdk as _Gdk, Gio as _Gio  # noqa: PLC0415
    from gi.repository import GLib as _GLib, GObject as _GObject, Gtk as _Gtk  # noqa: PLC0415
    from gi.repository import Pango as _Pango  # noqa: PLC0415

    Gtk, Gdk, Adw, Gio, GLib, GObject, Pango = _Gtk, _Gdk, _Adw, _Gio, _GLib, _GObject, _Pango
    AVAILABLE = True
    return True


_LOADED = _load()


def available() -> bool:
    """True when GTK, Gdk and libadwaita could all be loaded."""
    return AVAILABLE


def missing() -> Tuple[str, ...]:
    """Why :func:`available` is false, as lines a person can act on."""
    return MISSING


def ensure() -> None:
    """Raise :class:`UiUnavailable` unless the interface can be built.

    Called at the top of every ``build`` function, so the failure happens once,
    early, and with an actionable message -- rather than deep inside a widget
    constructor as an ``AttributeError`` on ``None``.
    """
    if not AVAILABLE:
        raise UiUnavailable(
            "This part of iArch by Safari needs a graphical toolkit that is not "
            "installed here:\n  - " + "\n  - ".join(missing() or ("GTK 4",))
            + "\nThe settings themselves are still editable by hand in "
            "~/.config/iarch/settings.json, and every one of them has a command "
            "line tool: see iarch/cli/README.md.")


def describe() -> str:
    """One line naming the loaded versions, for the About page's debug info.

    Both version getters are verified in the record: ``gtk_get_major_version``
    (GNOME/gtk@4.10.0:gtk/gtkversion.c) and ``adw_get_major_version``
    (GNOME/libadwaita@1.7.12:src/adw-version.h.in). A binding that cannot answer
    is reported as unknown rather than guessed, because a debug block that
    invents a version is worse than one that admits a gap.
    """
    if not AVAILABLE:
        return "GTK: unavailable (" + "; ".join(missing()[:1]) + ")"
    parts = []
    for label, module in (("GTK", Gtk), ("libadwaita", Adw)):
        try:
            parts.append(
                f"{label} {module.get_major_version()}."
                f"{module.get_minor_version()}.{module.get_micro_version()}")
        except Exception:  # noqa: BLE001 - a binding without the getter says so
            parts.append(f"{label} unknown")
    return ", ".join(parts)
