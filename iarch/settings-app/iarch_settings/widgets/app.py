#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The application object: one window, one id, and the actions that are not rows.

An :class:`Adw.Application` exists here for three reasons that are not "because GTK wants
one". It owns the application id, which is what the compositor's window rule for
``dev.safari.iarch.settings`` matches and what makes the blur behind this window the
compositor's rather than the widget's. It owns the single-instance behaviour, so a second
launch focuses the window that is open instead of drawing a second one over it -- two
windows writing one settings file is two writers of one decision. And it owns the actions
that belong to no page: quit, the about dialog, and the accelerator that focuses search.

Everything a person changes is a row on a page, and a row is data. So the actions here are
only the ones that have no row, and the about dialog is deliberately thin: the About page
already carries the version, the licence counts and the debug information, and a second
copy of those facts in a dialog would be a second place for them to go stale. The dialog
names the application and points at the page.

``main`` is the whole entry point. It returns the application's exit status rather than
raising :class:`SystemExit` itself, so a caller -- the launcher script, a test, another
tool -- decides what to do with the number, and a machine with no toolkit gets the sentence
from :mod:`iarch_settings.gtkenv` on stderr and a non-zero status instead of a traceback.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from .. import APP_ID
from .. import gtkenv, i18n, version
from ..gtkenv import Adw, Gio, Gtk
from .window import Window

__all__ = ("Application", "Window", "main", "ACTION_ABOUT", "ACTION_FOCUS_SEARCH",
           "ACTION_QUIT", "SEARCH_ACCELS", "WEBSITE", "application_base")

#: The three actions that belong to the application rather than to a page. Each is a
#: ``app.`` name, which is what an accelerator has to point at.
ACTION_ABOUT = "app.about"
ACTION_FOCUS_SEARCH = "app.focus-search"
ACTION_QUIT = "app.quit"

#: ``<Control>f`` is the accelerator ``data/design/adwaita.json:api`` records for
#: ``gtk_application_set_accels_for_action``, and it is the one a person already has in
#: every other application that has a search field.
SEARCH_ACCELS: Sequence[str] = ("<Control>f",)

#: The address the about dialog links to. It is the same string
#: :data:`iarch_settings.services.links.PORTFOLIO_URL` validates, and
#: ``tests/test_settings_links.py`` asserts the two agree, so the link in the dialog is a
#: link that module would open.
WEBSITE = "https://safari-official.vercel.app"


#: The base class is chosen at import time, and the reason is that this package has to be
#: importable on a machine with no toolkit at all. The plan layer is data a test reads and
#: the renderer's decision methods run headless, so an import that raised here would make
#: both of them untestable everywhere except a desktop. With no libadwaita typelib
#: :data:`gtkenv.Adw` is ``None``, so the class inherits from ``object`` and can be defined
#: but not used -- and :meth:`Application.__init__` calls ``gtkenv.ensure()`` first, which
#: is what turns "cannot be used" into a sentence naming the missing typelib.
_BASE: Any = Adw.Application if Adw is not None else object


class Application(_BASE):
    """The application. One window, built on activation and not before."""

    def __init__(self, *, root: Optional[Any] = None,
                 env: Optional[dict] = None) -> None:
        gtkenv.ensure()
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.root = root
        self.env = dict(env) if env else None
        self.window: Optional[Window] = None
        self._problems: List[str] = []

    # ------------------------------------------------------------------- the lifetime

    def do_startup(self) -> None:  # noqa: N802 - GObject vfunc spelling
        """Install the catalogue and check the toolkit before anything is drawn.

        ``gtkenv.ensure()`` is called here rather than in ``main`` so that a subclass or a
        test that activates the application directly meets the same check, and the sentence
        it raises names the typelib that is missing rather than the import that failed.
        """
        _BASE.do_startup(self)
        gtkenv.ensure()
        # The environment is passed through so the catalogue is chosen by the same
        # LANGUAGE and LC_* the rest of the application reads, and not by a second
        # reading of the process environment taken at a different moment.
        i18n.install(env=self.env)
        self._add_actions()

    def do_activate(self) -> None:  # noqa: N802 - GObject vfunc spelling
        """Build the window the first time and present it every time."""
        if self.window is None:
            self.window = Window(self, root=self.root, env=self.env)
            self.window.build()
        self.window.window.present()

    # --------------------------------------------------------------------- the actions

    def _add_actions(self) -> None:
        """The three actions that belong here, and the accelerator for one of them."""
        for name, handler in ((ACTION_QUIT, self._on_quit),
                              (ACTION_ABOUT, self._on_about)):
            action = Gio.SimpleAction.new(name.split(".", 1)[1], None)
            action.connect("activate", handler)
            self.add_action(action)
        self.set_accels_for_action(ACTION_FOCUS_SEARCH, list(SEARCH_ACCELS))

    def _on_quit(self, _action: Any, _parameter: Any) -> None:
        self.quit()

    def _on_about(self, _action: Any, _parameter: Any) -> None:
        self.show_about()

    def show_about(self) -> Any:
        """The thin dialog: what this is, what version, and where the detail lives."""
        facts = version.facts(self.root, self.env)
        dialog = Adw.AboutDialog.new()
        dialog.set_application_name(i18n._("iArch by Safari Settings"))
        dialog.set_application_icon(APP_ID)
        dialog.set_developer_name("Safari")
        dialog.set_version(str(facts.get("version") or version.UNKNOWN))
        dialog.set_copyright(i18n._("Copyright (C) 2026 Safari"))
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.set_comments(i18n._(
            "The About page in this window carries the version facts, the licence count "
            "and the debug information; this dialog only says which application is open."))
        dialog.set_website(WEBSITE)
        revision = str(facts.get("revision") or "").strip()
        if revision:
            dialog.set_version(f"{facts.get('version')} ({revision})")
        debug = version.debug_info(self.root, self.env)
        if debug:
            dialog.set_debug_info(debug)
        if self.window is not None and self.window.window is not None:
            dialog.present(self.window.window)
        return dialog


def main(argv: Optional[Sequence[str]] = None, *, root: Optional[Any] = None,
         env: Optional[dict] = None) -> int:
    """Run the application, answering its exit status.

    A machine with no usable toolkit gets one sentence on stderr and a non-zero status.
    The sentence is :func:`iarch_settings.gtkenv.describe`, which names the typelib that
    is missing and the package that provides it on each of the two distributions this
    project installs on, because "cannot import gi" tells a person nothing they can act on.
    """
    import sys  # noqa: PLC0415  (late: only the failure path writes to a stream)

    if not gtkenv.available():
        print(gtkenv.describe(), file=sys.stderr)
        return 1
    application = Application(root=root, env=env)
    return int(application.run(list(argv) if argv is not None else None))


if __name__ == "__main__":  # pragma: no cover - the launcher is __main__.py
    raise SystemExit(main())


def application_base() -> Any:
    """The class :class:`Application` inherited from, which is the toolkit's answer to
    "is libadwaita importable".

    Exposed because a test on a machine with no toolkit has to be able to say which of the
    two cases it is in: ``object`` means the class is a placeholder that cannot be
    instantiated, and anything else means a real application class was built.
    """
    return _BASE
