#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The one window: fifteen pages in a sidebar beside the page that is showing.

This is the only module in the application that constructs widgets other than rows, and
it holds three decisions that are worth stating before the code.

**The window owns the toolkit and the renderer owns the decisions.** A
:class:`~iarch_settings.widgets.Renderer` answers every question a row raises -- what it
shows, where its value goes, whether it may be pressed, whether the person has agreed --
and this module only draws the answers. So the same plan renders identically here and in a
test that has no toolkit at all, and a bug in what a row *does* is findable without a
display.

**Nothing here is stacked that is not meant to be stepped through.** All fifteen pages are
built once and ``add``ed to the :class:`Adw.NavigationView`; choosing one ``replace``s the
visible page rather than pushing it. The difference is the back button: with a push per
visit, a person who has looked at six pages has six back steps through pages they have
already left, and the sidebar stops being the way to move around. The split view still
collapses to one pane below its fold threshold, and in that state ``replace`` is what makes
a chosen page the only page.

**The sizes come from the record, not from here.** ``1100x720`` and the ``760x560`` minimum
are what ``data/design/adwaita.json`` records for :class:`Adw.ApplicationWindow`. The
sidebar's width is left at libadwaita's own default, because ``tokens.json`` has no sidebar
measurement and inventing one here would put a design number in the one file that is not
checked against a token. The gap between a sidebar row's icon and its label *is* a token:
``spacing.sm``, read out of ``tokens.json`` at build time.

What is not here yet, deliberately: the search field. :meth:`PagePlan.search_entries`
already answers the index for all fifteen pages, and ``adwaita.json:api`` records the
``app.focus-search`` accelerator, but the field itself needs a widget the record does not
carry yet, and adding a widget to the record is a claim about an upstream header that has
to be checked rather than assumed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import APP_ID
from .. import i18n, paths
from ..gtkenv import Adw, Gdk, Gio, GLib, Gtk
from ..pages import DEFAULT_PAGE, PAGES
from ..pages import build as build_page
from ..pages.plan import RESPONSE_CANCEL, RESPONSE_CONFIRM, Context
from ..services import config_store, gtk_settings
from . import Renderer

__all__ = ("Window", "WINDOW_WIDTH", "WINDOW_HEIGHT", "MINIMUM_WIDTH", "MINIMUM_HEIGHT",
           "STYLE_PROVIDER_PRIORITY", "REDUCE_MOTION_CLASS", "SIDEBAR_CLASS",
           "HIGHLIGHT_CLASS", "ANIMATIONS_KEY", "sidebar_spacing")

#: The window's default and minimum size, from ``data/design/adwaita.json``'s entry for
#: ``Adw.ApplicationWindow`` rather than from a number chosen in this file.
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720
MINIMUM_WIDTH = 760
MINIMUM_HEIGHT = 560

#: ``GTK_STYLE_PROVIDER_PRIORITY_APPLICATION``, declared at
#: ``GNOME/gtk@4.10.0:gtk/gtkstyleprovider.h:73``. It is below ``PRIORITY_USER`` (800),
#: which is where GTK itself puts ``~/.config/gtk-4.0/gtk.css``
#: (``gtk/gtksettings.c:1037``), so a sheet this project ships cannot outrank one the
#: person can edit. ``style/glass.css`` styles only ``iarch-`` classes, so nothing is lost
#: by staying below it.
STYLE_PROVIDER_PRIORITY = 600

#: The class ``glass.css`` defines for a session that asked for less motion, and the two
#: switches that put it on the window. It is a class and not an ``@media`` query because
#: GTK's own property document puts media queries at "Since GTK 4.20" and this application
#: argues for a 4.10 floor; the evidence is in ``adwaita.json:rejected``.
REDUCE_MOTION_CLASS = "iarch-reduce-motion"
SIDEBAR_CLASS = "iarch-glass-sidebar"
HIGHLIGHT_CLASS = "iarch-highlight"

#: The desktop's own animation switch, one of the eleven keys
#: ``data/design/gtk-settings.json`` records. It is read out of the person's
#: ``settings.ini`` rather than out of ``Gtk.Settings``, so this module needs no GObject
#: the record does not carry and the reading is the same one the Fonts page shows.
ANIMATIONS_KEY = "gtk-enable-animations"

_TOKENS: Optional[Dict[str, Any]] = None


def sidebar_spacing(root: Optional[Path] = None) -> int:
    """The gap between a sidebar row's icon and its label: ``tokens.json:spacing.sm``.

    Read out of the token file rather than written here, because ``glass.css`` is held to
    the rule that it contains no number it chose and a Python file is not exempt from it.
    """
    global _TOKENS
    if _TOKENS is None:
        try:
            _TOKENS = json.loads(paths.design_file("tokens.json", root).read_text(
                encoding="utf-8"))
        except (OSError, ValueError):
            _TOKENS = {}
    spacing = ((_TOKENS.get("spacing") or {}).get("sm"))
    return int(spacing) if spacing is not None else 0


def animations_disabled(read: Optional[Dict[str, Any]] = None) -> bool:
    """Whether the person's own ``settings.ini`` asks for no animations.

    The key is recorded as ``bool``, so the file can hold ``0``, ``1``, ``false`` or
    ``true``; anything else -- an absent file, an absent key, a spelling GTK itself would
    ignore -- means no opinion, and no opinion is not a request for less motion.
    """
    values = (read or {}).get("gtk4") or {}
    raw = values.get(ANIMATIONS_KEY)
    if raw is None:
        return False
    return str(raw).strip().lower() in ("0", "false", "no", "off")


class Window:
    """The window, its sidebar and the page that is showing.

    :param application: the :class:`Adw.Application` this window belongs to.
    :param context: the plan context. Built here when not given, from the open
        :class:`~iarch_settings.services.config_store.Store`, so the pages draw the
        person's own settings rather than the repository's defaults.
    """

    def __init__(self, application: Any = None, *, context: Optional[Context] = None,
                 root: Optional[Path] = None,
                 env: Optional[Dict[str, str]] = None) -> None:
        self.application = application
        self.root = root
        self.env = dict(env) if env else None
        self.context = context if context is not None else self._open_context()
        self.renderer = Renderer(self.context, toast=self.toast, confirm=self.confirm)
        #: The CSS providers this window attached. A provider with no Python reference
        #: left pointing at it is collected, and a collected provider stops styling, so
        #: the list is what keeps ``glass.css`` applied for as long as the window lives.
        self.providers: List[Any] = []
        self.buttons: Dict[str, Any] = {}
        self.pages: Dict[str, Any] = {}
        self.window: Any = None
        self.view: Any = None
        self.overlay: Any = None
        self.split: Any = None
        self.toolbar: Any = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Window({len(self.pages)} pages, page={self.current_page()!r})"

    # ------------------------------------------------------------------ the context

    def _open_context(self) -> Context:
        """A context holding the person's own settings file, or the defaults behind it.

        The store is opened here rather than in the application because it is the window
        that draws it, and a window built with no store would draw defaults while writing
        nowhere -- which is the state :meth:`Renderer.write` reports as "no settings file
        is open".
        """
        store = None
        settings: Dict[str, Any] = {}
        try:
            store = config_store.Store(root=self.root, env=self.env)
            settings = store.load()
        except Exception:  # noqa: BLE001 - a window opens even when the file does not
            store = None
            settings = {}
        return Context(root=self.root, env=self.env, settings=settings, store=store)

    # ------------------------------------------------------------------- the widgets

    def build(self) -> Any:
        """The window and everything in it."""
        self.renderer.ensure()
        self.load_style()
        self.overlay = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView()
        self.view = Adw.NavigationView()
        self._build_pages()
        self.split.set_sidebar(Adw.NavigationPage.new(self.sidebar(), i18n._("Pages")))
        self.split.set_content(Adw.NavigationPage.new(self.view, i18n._("Settings")))
        self.overlay.set_child(self.split)
        self.toolbar = Adw.ToolbarView()
        self.toolbar.add_top_bar(self.header_bar())
        self.toolbar.set_content(self.overlay)
        self.window = Adw.ApplicationWindow(application=self.application) \
            if self.application is not None else Adw.ApplicationWindow()
        self.window.set_content(self.toolbar)
        self.window.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.apply_reduce_motion()
        self.show_page(self.start_page())
        return self.window

    def header_bar(self) -> Any:
        """The bar across the top.

        Returned bare, with no title widget: the page's own title is already the
        :class:`Adw.PreferencesPage` title underneath it, and a second copy of the same
        sentence in the bar would be the same words twice on one screen. The bar is here
        for the window's own controls, which the application adds.
        """
        return Adw.HeaderBar()

    def sidebar(self) -> Any:
        """The column of page buttons, one per page, grouped so one is down at a time.

        The buttons are :class:`Gtk.ToggleButton` in a group, which is the radio behaviour
        without a radio widget: ``gtk_toggle_button_set_group`` is still available at 4.10
        and ``set_active`` on one button is what moves the selection, so the sidebar's
        state and the visible page cannot disagree.
        """
        spacing = sidebar_spacing(self.root)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        self.renderer.add_class(column, SIDEBAR_CLASS)
        first: Any = None
        for spec in PAGES:
            button = self._sidebar_button(spec, spacing, first)
            if first is None:
                first = button
            column.append(button)
        return column

    def _sidebar_button(self, spec: Any, spacing: int, group: Any) -> Any:
        button = Gtk.ToggleButton()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
        if str(spec.icon or ""):
            row.append(Gtk.Image.new_from_icon_name(str(spec.icon)))
        label = Gtk.Label.new(str(spec.label))
        # Wrapped rather than ellipsised: a page name that is cut off is a page a person
        # cannot identify, and the sidebar is at its narrowest exactly when the window is.
        label.set_wrap(True)
        label.set_xalign(0.0)
        row.append(label)
        button.set_child(row)
        if group is not None:
            button.set_group(group)
        button.set_tooltip_text(str(spec.description or spec.label))
        button.set_active(spec.id == DEFAULT_PAGE)
        # The signal, not the method: gtk_toggle_button_toggled() is deprecated at 4.10
        # and exists only to emit the signal by hand.
        button.connect("toggled", self._on_sidebar_button, spec.id)
        self.buttons[spec.id] = button
        return button

    def _build_pages(self) -> None:
        """Build all fifteen pages once and add them without pushing any of them."""
        for spec in PAGES:
            plan = build_page(spec.id, self.context)
            widget = self.renderer.preferences_page(plan)
            page = Adw.NavigationPage.new_with_tag(widget, str(plan.title), str(spec.id))
            self.view.add(page)
            self.pages[spec.id] = page

    # --------------------------------------------------------------------- the style

    def load_style(self) -> Optional[Path]:
        """Attach ``style/glass.css`` to the display, answering the path it loaded.

        Loaded from the file and not from a string, because
        ``gtk_css_provider_load_from_data`` takes ``(data, length)`` at GTK 4.10 and
        ``(bytes)`` at 4.12 and later -- the spelling that works on both is the file one,
        which is what ``adwaita.json:portability`` records. Parsing errors are never fatal
        in GTK, so a sheet that fails to parse still loads and simply does nothing; the
        sheet is checked at build time instead, against ``data/design/gtk.json``.
        """
        path = paths.style_file()
        if not path.is_file():
            self.renderer.say(f"{path} is not there, so the window is drawn without it")
            return None
        display = Gdk.Display.get_default()
        if display is None:
            self.renderer.say("there is no display to attach a stylesheet to")
            return None
        provider = Gtk.CssProvider()
        provider.load_from_file(Gio.File.new_for_path(str(path)))
        Gtk.StyleContext.add_provider_for_display(display, provider,
                                                 STYLE_PROVIDER_PRIORITY)
        self.providers.append(provider)
        return path

    def apply_reduce_motion(self) -> bool:
        """Put ``iarch-reduce-motion`` on the window when either switch asks for it.

        Two readings and not one, and they stay separate: ``animation.reduce_motion`` in
        this project's own settings file, and the desktop's ``gtk-enable-animations``. A
        person who asked their desktop for no motion gets no motion from this window
        whatever the settings file says, which is the point of reading both.
        """
        wanted = bool(self.context.value("animation.reduce_motion"))
        try:
            desktop = animations_disabled(gtk_settings.read(paths.config_dir(self.env)))
        except Exception:  # noqa: BLE001 - an unreadable ini is not a request for motion
            desktop = False
        if wanted or desktop:
            self.renderer.add_class(self.window, REDUCE_MOTION_CLASS)
            return True
        return False

    # ------------------------------------------------------------------- navigation

    def start_page(self) -> str:
        """The page to open on: the last one this window closed, if it still exists.

        ``app.last_page`` is a free string in the schema, so it can name a page that has
        since gone; an unknown id falls back to :data:`DEFAULT_PAGE` rather than to an
        empty pane.
        """
        remembered = str(self.context.value("app.last_page") or "").strip()
        if remembered in self.pages:
            return remembered
        return DEFAULT_PAGE

    def show_page(self, page_id: str) -> bool:
        """Make one page the visible one, replacing rather than pushing."""
        page = self.pages.get(str(page_id))
        if page is None:
            self.renderer.say(f"{page_id} is not a page this window has")
            return False
        self.view.replace(page)
        store = getattr(self.context, "store", None)
        if store is not None:
            store.set("app.last_page", str(page_id))
        return True

    def current_page(self) -> Optional[str]:
        """The tag of the visible page, which is the page id it was built with."""
        if self.view is None:
            return None
        return self.view.get_visible_page_tag()

    def _on_sidebar_button(self, button: Any, page_id: str) -> None:
        if not button.get_active():
            return
        self.show_page(page_id)

    # ------------------------------------------------------- sentences and questions

    def toast(self, message: str) -> None:
        """Show one sentence the way the shell shows one."""
        if self.overlay is None:
            return
        toast = Adw.Toast.new(str(message))
        self.overlay.add_toast(toast)

    def confirm(self, question: str, body: str = "") -> bool:
        """Ask one question and wait for the answer.

        Synchronous, and the reason is that a row's confirmation is a gate on a write the
        caller goes on to do or not do in the same breath. GTK 4 removed the synchronous
        dialog run, so this re-enters the main loop for the duration of one dialog and
        quits it from the response callback. That is safe here because this window owns
        the only dialog in the application and nothing else opens one while it is up; it
        would not be safe as a general way to ask a question.

        With no window built yet -- a headless run, or a test -- the answer is ``True``,
        which is :meth:`Renderer.ask`'s own rule for a run with nobody to ask.
        """
        if self.window is None:
            return True
        dialog = Adw.AlertDialog.new(str(question), str(body or ""))
        dialog.add_response(RESPONSE_CANCEL, i18n._("Cancel"))
        dialog.add_response(RESPONSE_CONFIRM, i18n._("Continue"))
        dialog.set_default_response(RESPONSE_CANCEL)
        dialog.set_close_response(RESPONSE_CANCEL)
        dialog.set_response_appearance(RESPONSE_CONFIRM,
                                       Adw.ResponseAppearance.SUGGESTED)
        answers: List[bool] = []
        loop = GLib.MainLoop()

        def answered(_dialog: Any, response: str) -> None:
            answers.append(str(response) == RESPONSE_CONFIRM)
            if loop.is_running():
                loop.quit()

        dialog.choose(self.window, None, answered)
        loop.run()
        return bool(answers and answers[0])
