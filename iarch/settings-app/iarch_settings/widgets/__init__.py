#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Turn a page plan into widgets, and do nothing else.

A plan is data: :class:`~iarch_settings.pages.plan.Row` has no callback field and no
widget field, so it cannot smuggle behaviour past the checks in
:mod:`iarch_settings.pages.plan`. This module is the only place in the application where a
row's ``action`` string becomes a call, and it is deliberately the *only* place, for three
reasons that each show up as a rule below.

**One way to reach the machine.** Every name is resolved through
:meth:`~iarch_settings.pages.plan.Context.resolve`, which accepts a name only when its
module is in :data:`iarch_settings.services.MODULES`,
:data:`iarch_settings.pages.MODULES` or :data:`iarch_settings.pages.plan.PACKAGE_MODULES`.
A renderer with its own import table would be a second way in, and the second way in is
always the one nobody checks. :meth:`Renderer.call` raises :class:`RendererError` rather
than :class:`~iarch_settings.pages.plan.PlanError` so the sentence can name the list it
checked against, but the check itself is the context's.

**Nothing is drawn that a test cannot read.** Every sentence this module would put on
screen -- a toast, a confirmation question, a refusal, "nothing was written" -- is also
appended to :attr:`Renderer.messages`. So the whole behaviour of a click can be asserted on
a machine with no toolkit at all, which is every machine this repository's tests run on.
The widget methods are separate from the decision methods for exactly that reason: the
decisions are testable, the widgets are not, and mixing them would make both untestable.

**An unanswered question is shown as unanswered.** :data:`UNANSWERED` is what a row shows
when its ``source`` answered ``None``, and ``None`` is what every reader in
:mod:`iarch_settings.services` returns when the machine could not answer -- an absent
binary, an unreadable file, a compositor that is not running. Drawing that as "off" or as
an empty string would be a guess, and a guess about a switch is a lie about the state of
the machine.

``read_source`` prefers ``row.source`` over the settings document on purpose. A glass leaf
row shows the value the current intensity produces, while ``write`` puts an *override* into
the settings file on top of it: the row and the write are two different questions, and
answering both from the document would hide the intensity's own value behind an override
nobody has set.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple

from ..gtkenv import Adw, Gtk
from ..gtkenv import ensure as _ensure_toolkit
from ..pages import plan as plan_module
from ..services import MODULES as SERVICE_MODULES

__all__ = ("Renderer", "RendererError", "UNANSWERED", "TOOLKIT_WIDGETS", "TOOLKIT_CALLS")

#: What a row shows when the machine could not answer. A sentence rather than a dash or an
#: empty string, because a person has to be able to tell "this is off" from "nobody knows".
UNANSWERED = "not available"

#: Every widget this module constructs. Each one is in ``data/design/adwaita.json`` with
#: the header it was read out of, and :mod:`tests.test_settings_surface` fails the suite if
#: the source names one that is not -- so this tuple is a statement about the record as
#: much as about the code.
TOOLKIT_WIDGETS: Tuple[str, ...] = (
    "Adw.ActionRow",
    "Adw.Banner",
    "Adw.ButtonRow",
    "Adw.ComboRow",
    "Adw.EntryRow",
    "Adw.ExpanderRow",
    "Adw.HeaderBar",
    "Adw.PreferencesGroup",
    "Adw.PreferencesPage",
    "Adw.SpinRow",
    "Adw.SwitchRow",
    "Gtk.FlowBox",
    "Gtk.Scale",
    "Gtk.StringList",
)

#: The C calls behind the constructions that are not obvious from the Python name. They are
#: recorded in the same file's ``api`` block, and two of them exist only because the
#: obvious spelling is wrong: a :class:`Gtk.StringList` model shows a GObject repr instead
#: of a string unless an expression is set on the combo row, and
#: ``GtkStyleContext`` -- the way a style class used to be applied -- is deprecated in
#: GTK 4 with ``gtk_widget_add_css_class`` as its replacement.
TOOLKIT_CALLS: Tuple[str, ...] = (
    "adw_combo_row_set_expression",
    "adw_combo_row_set_model",
    "adw_spin_row_new_with_range",
    "gtk_widget_add_css_class",
)

#: The row kind and the widget it becomes. ``state`` and ``link`` share a widget with
#: ``expander``'s children because all three are an :class:`Adw.ActionRow`: what differs is
#: whether the row is pressable and what pressing it does, and that is the plan's business
#: rather than the widget's.
WIDGET_BY_KIND: Tuple[Tuple[str, str], ...] = (
    ("switch", "Adw.SwitchRow"),
    ("combo", "Adw.ComboRow"),
    ("spin", "Adw.SpinRow"),
    ("scale", "Gtk.Scale"),
    ("entry", "Adw.EntryRow"),
    ("button", "Adw.ButtonRow"),
    ("expander", "Adw.ExpanderRow"),
    ("flow", "Gtk.FlowBox"),
    ("state", "Adw.ActionRow"),
    ("link", "Adw.ActionRow"),
)


class RendererError(RuntimeError):
    """A name a plan gave that this application cannot call.

    Raised rather than returned, because the caller is a click handler and a click handler
    that silently did nothing is indistinguishable from a broken button. The sentence names
    the list the name was checked against, which is the part that makes it actionable.
    """


class Renderer:
    """One plan's worth of decisions, and the widgets they become.

    :param context: the :class:`~iarch_settings.pages.plan.Context` holding the settings
        document, the open :class:`~iarch_settings.services.config_store.Store` if there is
        one, the environment and the language.
    :param toast: called with one sentence to show it the way the shell shows one. Optional:
        with no toast the sentence still lands in :attr:`messages`, which is what a test
        reads.
    :param confirm: called with ``(question, body)`` and answering a bool. With no confirm
        callback :meth:`ask` answers ``True``, so a headless run applies what a windowed run
        would have applied after the person pressed the button -- and a test that wants to
        see the refusal passes a callback that answers ``False``.
    :param on_changed: called with ``(row, value)`` after a write that changed something, so
        a window can redraw the rows that depend on it.
    """

    def __init__(self, context: plan_module.Context, *,
                 toast: Optional[Callable[[str], Any]] = None,
                 confirm: Optional[Callable[[str, str], bool]] = None,
                 on_changed: Optional[Callable[[Any, Any], Any]] = None) -> None:
        self.context = context
        self.toast = toast
        self.confirm = confirm
        self.on_changed = on_changed
        self.messages: List[str] = []

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Renderer({len(self.messages)} messages)"

    # ------------------------------------------------------------------ sentences

    def say(self, message: str) -> str:
        """Record a sentence and show it if there is somewhere to show it.

        Returns the sentence, so a caller can ``return self.say(...)`` from a method whose
        contract is to answer with what it told the person.
        """
        text = str(message or "").strip()
        if not text:
            return ""
        self.messages.append(text)
        if self.toast is not None:
            self.toast(text)
        return text

    def ask(self, question: str, body: str = "") -> bool:
        """Ask before doing something that cannot be undone by pressing the button again.

        With no ``confirm`` callback the answer is ``True``. That is not a shortcut around
        the question: the callback is the dialog, and a run with no dialog has nobody to
        ask, so the action the person requested is the action that happens. A test that
        wants the refusal passes a callback answering ``False`` and reads
        :attr:`messages` for the sentence.
        """
        text = str(question or "").strip()
        if not text:
            return True
        if self.confirm is None:
            return True
        return bool(self.confirm(text, str(body or "").strip()))

    # -------------------------------------------------------------------- calling

    def resolve(self, dotted: str) -> Optional[Callable[..., Any]]:
        """The callable a ``module.function`` name refers to, or ``None``.

        Delegated to the context on purpose: the lists a name may resolve into are the
        context's, and a second list here would be a second way into the machine.
        """
        return self.context.resolve(dotted)

    def call(self, dotted: str, *args: Any) -> Any:
        """Resolve a name and call it, raising :class:`RendererError` if it does not resolve.

        The sentence names :data:`iarch_settings.services.MODULES` because that is the list
        an action name has to be in, and "does not name a function" without the list is a
        dead end for whoever reads it next.
        """
        try:
            return self.context.call(dotted, *args)
        except plan_module.PlanError as error:
            raise RendererError(
                f"{dotted} does not name a function this application may call: an action "
                f"resolves into a module listed in iarch_settings.services.MODULES "
                f"({', '.join(SERVICE_MODULES)}), into one of the page modules, or into "
                f"paths, i18n, version and gtkenv. {error}"
            ) from error

    def maybe(self, dotted: Optional[str], *args: Any) -> Any:
        """Call a reader if it resolves; answer ``None`` rather than raising if it does not.

        This is :meth:`call` for the reading side, and the difference in behaviour is the
        point. A row whose ``source`` cannot be resolved is a page with a missing answer,
        which :data:`UNANSWERED` already has a sentence for; a row whose ``action`` cannot
        be resolved is a button that cannot work, which has to be loud.
        """
        name = str(dotted or "").strip()
        if not name:
            return None
        function = self.resolve(name)
        if function is None:
            self.say(f"{name} does not name a function in this application, so there is "
                     f"nothing to read")
            return None
        return function(*args)

    # -------------------------------------------------------------------- reading

    def read_source(self, row: Any) -> str:
        """The sentence a row shows, from its ``source`` if it has one.

        ``source`` wins over the settings document. A glass leaf row shows what the current
        intensity produces, and the document holds an override on top of that which is
        usually absent; reading the document first would show nothing where the intensity
        has an answer.

        ``None`` becomes :data:`UNANSWERED` rather than an empty string, and a value that is
        not text becomes its own ``str``, because a row shows a sentence and a number is not
        one yet.
        """
        source = str(getattr(row, "source", "") or "").strip()
        if source:
            answer = self.maybe(source)
            if answer is None:
                return UNANSWERED
            return answer if isinstance(answer, str) else str(answer)
        value = self.value_of(row)
        if value is None:
            return UNANSWERED
        return value if isinstance(value, str) else str(value)

    def value_of(self, row: Any) -> Any:
        """The value a row's control starts at: the document first, then the row's own.

        The document wins because it is what the person chose last time; ``row.value`` is
        the fallback for a row that reads something the document does not hold, and for a
        plan built with no settings file open at all.
        """
        setting = str(getattr(row, "setting", "") or "").strip()
        if setting:
            found = self.context.value(setting)
            if found is not None:
                return found
        return getattr(row, "value", None)

    def choices_of(self, row: Any) -> List[Tuple[Any, str]]:
        """A row's choices as ``(value, label)`` pairs.

        ``choices`` is a closed list written in the plan; ``choices_source`` is a name
        called with nothing that answers one, for the lists that depend on the machine --
        the monitors plugged in, the intensity ids, the backups that exist. A pair with one
        element is a choice whose label is its value, which is what a list of plain strings
        from a service is.
        """
        raw: Sequence[Any] = tuple(getattr(row, "choices", ()) or ())
        source = str(getattr(row, "choices_source", "") or "").strip()
        if source:
            answer = self.maybe(source)
            if isinstance(answer, (list, tuple)):
                raw = tuple(answer)
        pairs: List[Tuple[Any, str]] = []
        for choice in raw:
            if isinstance(choice, (list, tuple)):
                if not choice:
                    continue
                value = choice[0]
                label = str(choice[1]) if len(choice) > 1 else str(value)
            else:
                value = choice
                label = str(choice)
            pairs.append((value, label))
        return pairs

    def rows_of(self, row: Any) -> List[Any]:
        """An expander's children: the plan's own list, or one a service answers."""
        children = list(getattr(row, "rows", ()) or ())
        source = str(getattr(row, "rows_source", "") or "").strip()
        if source:
            answer = self.maybe(source)
            if isinstance(answer, (list, tuple)):
                children.extend(answer)
        return children

    def settings_paths(self) -> List[str]:
        """Every settings path a plan may name, from the plan module rather than a copy."""
        return list(plan_module.settings_paths(self.context.root))

    # ------------------------------------------------------------------- deciding

    def check(self, row: Any, text: str) -> Tuple[bool, str]:
        """Run a row's validator over what a person typed, answering ``(ok, reason)``.

        The validator is called with the text and nothing else, which is the contract
        :class:`~iarch_settings.pages.plan.Row` states, and it answers ``(True, "")`` or
        ``(False, "the reason")``. A validator that answers a bare bool is accepted and its
        reason is empty, because a plan that only says no is still a plan that says no.
        """
        name = str(getattr(row, "validator", "") or "").strip()
        if not name:
            return True, ""
        answer = self.maybe(name, text)
        if isinstance(answer, (list, tuple)) and len(answer) >= 2:
            return bool(answer[0]), str(answer[1] or "")
        return bool(answer), ""

    def sensitive(self, row: Any) -> bool:
        """Whether a row can be pressed right now.

        ``sensitive_when`` is called with nothing and answers a bool; a row without one is
        always sensitive. The name is resolved through the context like every other, so a
        plan cannot disable a row by pointing at something outside the lists.
        """
        name = str(getattr(row, "sensitive_when", "") or "").strip()
        if not name:
            return True
        return bool(self.maybe(name))

    def visible(self, row: Any) -> bool:
        """Whether a row is drawn at all.

        A row that is not visible is not merely hidden: its value is not written and its
        action cannot be activated, because nothing drew it for the person to press.
        """
        name = str(getattr(row, "visible_when", "") or "").strip()
        if not name:
            return True
        return bool(self.maybe(name))

    # -------------------------------------------------------------------- writing

    def write(self, row: Any, value: Any) -> bool:
        """Put a value where the row says it goes, answering whether anything changed.

        Three places, and a row has at most one of them:

        * ``setting`` -- a path in the settings document, written through the open
          :class:`~iarch_settings.services.config_store.Store`. With no store open there is
          nowhere to put it, and the sentence says so rather than pretending.
        * ``action`` -- a function called with the new value and only with it. A row cannot
          pass a second argument, which is why
          :data:`iarch_settings.services.noctalia.PAGE_VERBS` spells each verb out as its
          own zero-argument function.
        * neither -- a row that only reads, and writing to it is a plan bug rather than
          something to recover from.

        ``risky`` and ``confirm`` are the gate. A row that carries either is asked about
        first, and a ``False`` answer leaves everything as it was and says so, because
        "kept as it was" and "changed" have to be different sentences on screen.
        """
        if not self.visible(row):
            self.say(f"{row.title} is not shown right now, so nothing was written")
            return False
        if getattr(row, "risky", False) or str(getattr(row, "confirm", "") or "").strip():
            question = str(getattr(row, "confirm", "") or "").strip() or (
                f"Change {row.title}?")
            body = str(getattr(row, "confirm_body", "") or "").strip()
            if not self.ask(question, body):
                self.say(f"{row.title} was kept as it was")
                return False
        setting = str(getattr(row, "setting", "") or "").strip()
        action = str(getattr(row, "action", "") or "").strip()
        if setting:
            store = getattr(self.context, "store", None)
            if store is None:
                self.say("no settings file is open, so nothing was written")
                return False
            store.set(setting, value)
        elif action:
            self.call(action, value)
        else:
            raise RendererError(
                f"{row.title} has neither a setting nor an action, so there is nowhere to "
                f"put a value; a row that only reads is a 'state' row and is not written to")
        if self.on_changed is not None:
            self.on_changed(row, value)
        return True

    def activate(self, row: Any) -> bool:
        """Do the one thing a pressable row does, answering whether it did anything.

        A button's ``action`` is called with nothing: the row *is* the request. A link row
        opens its ``uri_source``, and the URI goes through
        :func:`iarch_settings.services.links.open_uri` rather than through ``Gio`` here, so
        the allowlist that decides which schemes this project opens lives in one module and
        is tested in one file.
        """
        if not self.visible(row):
            self.say(f"{row.title} is not shown right now, so nothing was opened")
            return False
        if not self.sensitive(row):
            self.say(f"{row.title} cannot be used right now")
            return False
        if getattr(row, "risky", False) or str(getattr(row, "confirm", "") or "").strip():
            question = str(getattr(row, "confirm", "") or "").strip() or (
                f"{row.title}?")
            body = str(getattr(row, "confirm_body", "") or "").strip()
            if not self.ask(question, body):
                self.say(f"{row.title} was not done")
                return False
        uri_source = str(getattr(row, "uri_source", "") or "").strip()
        action = str(getattr(row, "action", "") or "").strip()
        if uri_source:
            uri = self.maybe(uri_source)
            if not uri:
                self.say(f"{row.title} has no address to open")
                return False
            return self.open_uri(str(uri))
        if action:
            self.call(action)
            return True
        self.say(f"{row.title} does nothing: it has no action and no address")
        return False

    def open_uri(self, uri: str) -> bool:
        """Hand a validated URI to the desktop, through the module that validates URIs.

        Imported late, inside the method: :mod:`iarch_settings.services.links` is what
        decides which schemes this project opens, and importing it at module scope would put
        that decision one step away from the call that depends on it. ``open_uri`` raises
        :class:`~iarch_settings.services.links.LinkError` for a refused URI, and this method
        turns that into a sentence, because a refused link on a page is a disabled row with
        an explanation and not an exception in a click handler.
        """
        from ..services import links  # noqa: PLC0415  (late: the allowlist lives there)

        try:
            opened = links.open_uri(uri)
        except links.LinkError as error:
            self.say(str(error))
            return False
        if not opened:
            self.say(f"{uri} could not be opened: nothing on this desktop is registered "
                     f"for it")
            return False
        return True

    # -------------------------------------------------------------------- widgets

    @staticmethod
    def ensure() -> None:
        """Raise :class:`~iarch_settings.gtkenv.UiUnavailable` unless the toolkit imported.

        Called at the top of every method that constructs a widget and nowhere else, so the
        decision methods above keep working on a machine with no toolkit and the widget
        methods fail with the sentence that says which typelib is missing.
        """
        _ensure_toolkit()

    @staticmethod
    def add_class(widget: Any, name: str) -> None:
        """Add one style class, through the call that replaced ``GtkStyleContext``."""
        text = str(name or "").strip()
        if text:
            widget.add_css_class(text)

    @classmethod
    def add_classes(cls, widget: Any, names: Sequence[str]) -> None:
        """Add every style class a row or a group carries."""
        for name in names or ():
            cls.add_class(widget, name)

    def header_bar(self) -> Any:
        """The bar across the top of a page.

        Returned bare. Its title widget is set by the window rather than here, because the
        title is a label built from the plan's own title and this module has no reason to
        know which of the two bars in a split view it is building.
        """
        self.ensure()
        return Adw.HeaderBar()

    def preferences_page(self, plan: Any) -> Any:
        """A whole page: its groups, its banners and the style classes it carries."""
        self.ensure()
        page = Adw.PreferencesPage()
        page.set_title(str(plan.title or ""))
        if str(getattr(plan, "icon", "") or ""):
            page.set_icon_name(str(plan.icon))
        self.add_classes(page, tuple(getattr(plan, "styles", ()) or ()))
        for banner in tuple(getattr(plan, "banners", ()) or ()):
            if not self.visible_banner(banner):
                continue
            page.add(self.banner_widget(banner))
        for group in tuple(getattr(plan, "groups", ()) or ()):
            page.add(self.group_widget(group))
        return page

    def group_widget(self, group: Any) -> Any:
        """One group: a title, an optional description and its rows."""
        self.ensure()
        widget = Adw.PreferencesGroup()
        widget.set_title(str(group.title or ""))
        if str(group.description or ""):
            widget.set_description(str(group.description))
        self.add_classes(widget, tuple(group.style_classes or ()))
        for row in tuple(group.rows or ()):
            built = self.row_widget(row)
            if built is not None:
                widget.add(built)
        return widget

    def visible_banner(self, banner: Any) -> bool:
        """Whether a banner's ``when`` is true right now."""
        name = str(getattr(banner, "when", "") or "").strip()
        if not name:
            return True
        return bool(self.maybe(name))

    def banner_widget(self, banner: Any) -> Any:
        """A strip for a message that is not an error dialog."""
        self.ensure()
        widget = Adw.Banner()
        widget.set_title(str(banner.text or ""))
        if str(getattr(banner, "icon", "") or ""):
            widget.set_icon_name(str(banner.icon))
        # A banner's `action` is not wired here: AdwBanner draws its button only once a
        # label is set on it, and a :class:`~iarch_settings.pages.plan.Banner` carries no
        # label -- the sentence for a response id comes from the catalogue, which the window
        # has and this module does not. So the strip is drawn with its text and the window
        # decides whether it also gets a button.
        return widget

    def row_widget(self, row: Any) -> Any:
        """One row as the widget its kind names, or ``None`` when it is not visible.

        The dispatch is over :data:`WIDGET_BY_KIND`, which is a written-down table rather
        than a chain of conditionals, so the mapping a plan can ask for and the mapping this
        module can draw are the same list and a new kind fails here loudly.
        """
        if not self.visible(row):
            return None
        kind = str(row.kind or "")
        if kind == "switch":
            return self._switch_row(row)
        if kind == "combo":
            return self._combo_row(row)
        if kind == "spin":
            return self._spin_row(row)
        if kind == "scale":
            return self._scale_row(row)
        if kind == "entry":
            return self._entry_row(row)
        if kind == "button":
            return self._button_row(row)
        if kind == "expander":
            return self._expander_row(row)
        if kind == "flow":
            return self._flow_row(row)
        if kind in ("state", "link"):
            return self._action_row(row)
        raise RendererError(
            f"{row.title} has the row kind {kind!r}, which has no widget in this renderer; "
            f"the kinds are {', '.join(name for name, _ in WIDGET_BY_KIND)}")

    def _labelled(self, widget: Any, row: Any) -> Any:
        """Give a widget the row's title, subtitle, icon, classes and sensitivity."""
        if hasattr(widget, "set_title"):
            widget.set_title(str(row.title or ""))
        subtitle = str(getattr(row, "subtitle", "") or "").strip()
        if subtitle and hasattr(widget, "set_subtitle"):
            widget.set_subtitle(subtitle)
        icon = str(getattr(row, "icon", "") or "").strip()
        if icon and hasattr(widget, "set_icon_name"):
            widget.set_icon_name(icon)
        self.add_classes(widget, tuple(getattr(row, "style_classes", ()) or ()))
        widget.set_sensitive(self.sensitive(row))
        return widget

    def _switch_row(self, row: Any) -> Any:
        self.ensure()
        widget = Adw.SwitchRow()
        self._labelled(widget, row)
        widget.set_active(bool(self.value_of(row)))
        return widget

    def _combo_row(self, row: Any) -> Any:
        self.ensure()
        choices = self.choices_of(row)
        labels = [label for _, label in choices]
        widget = Adw.ComboRow()
        self._labelled(widget, row)
        # A StringList model shows a GObject repr instead of the string unless an
        # expression tells the row which property to read: adw_combo_row_set_expression.
        widget.set_model(Gtk.StringList.new(labels))
        widget.set_expression(Gtk.PropertyExpression.new(str, None, "string"))
        current = self.value_of(row)
        for index, (value, _) in enumerate(choices):
            if value == current:
                widget.set_selected(index)
                break
        return widget

    def _spin_row(self, row: Any) -> Any:
        self.ensure()
        minimum = float(row.minimum or 0.0)
        maximum = float(row.maximum or 0.0)
        step = float(row.step or 1.0)
        widget = Adw.SpinRow.new_with_range(minimum, maximum, step)
        self._labelled(widget, row)
        value = self.value_of(row)
        widget.set_value(float(value) if value is not None else minimum)
        return widget

    def _scale_row(self, row: Any) -> Any:
        self.ensure()
        minimum = float(row.minimum or 0.0)
        maximum = float(row.maximum or 0.0)
        step = float(row.step or 1.0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minimum, maximum, step)
        value = self.value_of(row)
        scale.set_value(float(value) if value is not None else minimum)
        holder = Adw.ActionRow()
        self._labelled(holder, row)
        holder.add_suffix(scale)
        return holder

    def _entry_row(self, row: Any) -> Any:
        self.ensure()
        widget = Adw.EntryRow()
        self._labelled(widget, row)
        # An AdwEntryRow has one text slot: its title, which floats above the entry. A
        # plan's `placeholder` fills that slot when the row has no title of its own, and
        # otherwise the title wins -- two strings competing for one slot would be a guess
        # about which of them the person was meant to read.
        placeholder = str(getattr(row, "placeholder", "") or "").strip()
        if placeholder and not str(row.title or "").strip():
            widget.set_title(placeholder)
        value = self.value_of(row)
        widget.set_text("" if value is None else str(value))
        return widget

    def _button_row(self, row: Any) -> Any:
        self.ensure()
        widget = Adw.ButtonRow()
        self._labelled(widget, row)
        return widget

    def _expander_row(self, row: Any) -> Any:
        self.ensure()
        widget = Adw.ExpanderRow()
        self._labelled(widget, row)
        for child in self.rows_of(row):
            built = self.row_widget(child)
            if built is not None:
                widget.add_row(built)
        return widget

    def _flow_row(self, row: Any) -> Any:
        self.ensure()
        box = Gtk.FlowBox()
        # One tile is selected at a time: a flow row chooses a value, so BROWSE and SINGLE
        # both fit and MULTIPLE would let a row hold two values where the setting holds one.
        box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.add_classes(box, tuple(getattr(row, "style_classes", ()) or ()))
        source = str(getattr(row, "tiles_source", "") or "").strip()
        tiles = self.maybe(source) if source else list(getattr(row, "rows", ()) or ())
        for tile in tiles or ():
            if not isinstance(tile, (list, tuple)) or len(tile) < 2:
                continue
            button = Adw.ButtonRow()
            button.set_title(str(tile[1]))
            box.append(button)
        return box

    def _action_row(self, row: Any) -> Any:
        self.ensure()
        widget = Adw.ActionRow()
        self._labelled(widget, row)
        # A read-only row shows what the machine answered; a link row shows the address it
        # would open, so a person can read it on a machine that cannot open it.
        answer = self.read_source(row)
        if answer and answer != UNANSWERED:
            widget.set_subtitle(answer)
        elif answer == UNANSWERED:
            widget.set_subtitle(UNANSWERED)
        return widget
