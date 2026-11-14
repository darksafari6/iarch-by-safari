# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""What a page contains, written down before anything is drawn.

A page in this application is two things: a **plan**, which is data, and a
**rendering**, which is widgets. Only the rendering needs GTK, so only the
rendering is untestable in a sandbox with no display -- and docs/UNVERIFIED.md
SET-02 says exactly that. Everything a plan can be checked for is checked here or
in ``tests/test_settings_pages.py``:

* a row names a setting that exists in ``data/settings.default.json``, or a service
  function that exists in this package, and never an invented one;
* a dropdown's choices come from a record or from a function that resolves;
* a number row carries the bounds it is rendered with, so a page cannot offer a
  value the generator behind it would refuse;
* every icon name and every style class is one ``data/design/adwaita.json``
  verified against a pinned upstream release.

The plan is also the source of the search index and of the acceptance claim that
every visual switch in the product is reachable: a test walks the settings document
and asks which page owns each path, so a switch that no page offers fails the build
instead of shipping as a value only a text editor can change.

Nothing here imports GTK, and nothing here runs a command. Reading a plan is safe
on any machine, which is the only reason it can be required to be complete.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .. import paths

ROW_KINDS = (
    "switch",     # AdwSwitchRow: one boolean
    "combo",      # AdwComboRow: a closed list of choices
    "spin",       # AdwSpinRow: a number with bounds, typed in
    "scale",      # Gtk.Scale: a number with bounds, dragged, with a live preview
    "entry",      # AdwEntryRow: text, validated before it is written
    "button",     # AdwButtonRow: one action, no value
    "expander",   # AdwExpanderRow: a row that opens onto a list of rows
    "flow",       # Gtk.FlowBox: a grid of tiles, one of which is selected
    "state",      # AdwActionRow, read only: a value the machine reports
    "link",       # AdwActionRow that opens something elsewhere
)

#: The row kinds that hold a value the user changes, and therefore must say where
#: the value goes.
VALUE_KINDS = ("switch", "combo", "spin", "scale", "entry", "flow")

#: The kinds that do one thing when activated.
ACTION_KINDS = ("button", "link")

#: What a row may point at. ``setting`` is a path in settings.json, ``action`` is a
#: callable in this package, and ``none`` is a row that only reads.
TARGET_KINDS = ("setting", "action", "none")

STYLE_RECORD = "adwaita.json"
SETTINGS_NAME = "settings.default.json"
SETTINGS_SCHEMA = "settings.schema.json"

#: The settings paths whose keys are not enumerable from the defaults file, each with
#: the kind the schema gives it and the record that defines the keys.
#:
#: ``data/settings.default.json`` ships all five empty -- an override nobody has set,
#: a monitor list that only a session can fill, an autostart list that starts with
#: nothing in it -- so a literal walk of that file cannot say whether
#: ``display.monitors.output`` is a real path. Rather than let a plan name whatever it
#: likes, the shape of each container's items comes from a record that is checked by
#: something else: the compositor's leaves from ``data/design/tokens.json``, the
#: animation leaves from ``data/design/animations.json``, the monitor fields from
#: ``data/design/monitors.json``, the autostart keys from
#: ``data/design/autostart.json``, and the per-window opacity pair from the schema's
#: own ``items``. ``tests/test_settings_pages.py`` asserts that each path here is the
#: kind claimed in ``data/schemas/settings.schema.json`` and that the record named
#: beside it exists, so the table cannot drift into being a way to skip a check.
DYNAMIC_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("glass.leaves", "object", "data/design/tokens.json"),
    ("animation.event_overrides", "object", "data/design/animations.json"),
    ("glass.per_app_opacity", "array", "data/schemas/settings.schema.json"),
    ("display.monitors", "array", "data/design/monitors.json"),
    ("startup.autostart", "array", "data/design/autostart.json"),
)

#: The response ids a confirmation dialog uses. They are ids, not labels: the
#: renderer turns them into buttons and the catalogue into sentences.
RESPONSE_KEEP = "keep"
RESPONSE_REVERT = "revert"
RESPONSE_CANCEL = "cancel"
RESPONSE_CONFIRM = "confirm"


PACKAGE_MODULES: Tuple[str, ...] = ("paths", "i18n", "version", "gtkenv")
"""The non-service, non-plan modules of this package a plan may name.

All four read rather than act: where the files are, what the catalogue says, what
this build is, and whether the toolkit is importable. Nothing that writes is in
this list, because writing belongs to a service.
"""

#: What a *plan* module may define for its own rows to name, which is the reason
#: :meth:`Context.resolve` accepts ``pages.<module>`` at all.
#:
#: A row's ``source`` and ``choices_source`` are called with no arguments, and a lot
#: of what a page shows needs one: ``gtk_settings.accepted_values("gtk-xft-hintstyle")``
#: is the right question but is not a zero-argument function, and
#: ``system.format_uptime(system.uptime_seconds())`` is two calls that only mean
#: anything together. So a plan module wraps those into a zero-argument reader, and
#: that wrapper is the only code a plan module may own. The rule it has to keep:
#:
#: * it reads, and reading only -- no command, no write, no link opened, because
#:   those belong to a service and a service is where the rules about them live;
#: * it returns something drawable: a string, a number, a bool, ``None`` for "the
#:   question could not be answered", or a list of ``(id, label)`` pairs for a
#:   dropdown;
#: * it takes its facts from a service or from a record, never from a literal, so a
#:   choice list cannot disagree with the file that defines the choices.
#:
#: A button's ``action`` is *not* one of these: an action does something, so it names
#: a service function and a plan module that defined one would be the place the
#: "a page never touches the machine" rule stopped being true.
PLAN_HELPERS = "read-only, zero-argument, drawable"


class PlanError(RuntimeError):
    """A plan that does not describe something this application can do."""


# ------------------------------------------------------------------- context


class Context:
    """What a page needs to build its plan, and nothing it does not.

    ``settings`` is the document a plan reads current values from, so a plan built
    against the repository defaults is a plan that describes the default state --
    which is what a test builds, and what a first run shows. ``store`` is the live
    :class:`iarch_settings.services.config_store.Store` when there is one, and
    ``None`` otherwise, because a plan is readable without a configuration
    directory existing at all.
    """

    __slots__ = ("root", "env", "settings", "store", "language", "extra")

    def __init__(self, root: Optional[Path] = None,
                 env: Optional[Mapping[str, str]] = None,
                 settings: Optional[Mapping[str, Any]] = None,
                 store: Any = None, language: str = "en",
                 extra: Optional[Mapping[str, Any]] = None) -> None:
        self.root = Path(root) if root else None
        self.env = dict(env) if env else None
        self.settings: Dict[str, Any] = dict(settings) if settings else {}
        self.store = store
        self.language = language
        self.extra: Dict[str, Any] = dict(extra) if extra else {}

    def value(self, dotted: str) -> Any:
        """``theme.intensity`` as the value at that path, or ``None``."""
        node: Any = self.settings
        for part in str(dotted).split("."):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return node

    def resolve(self, dotted: str) -> Optional[Callable[..., Any]]:
        """A ``module.function`` name in this application as the callable, or ``None``.

        Resolution is restricted to two written-down lists, and this is a mechanism
        rather than a convention:

        * ``iarch_settings.services.<name>`` only when ``<name>`` is in
          :data:`iarch_settings.services.MODULES` -- the services the package
          re-exports, which are the only modules allowed to touch the machine;
        * ``iarch_settings.pages.<name>`` only when ``<name>`` is in
          :data:`iarch_settings.pages.MODULES` -- the fifteen plan modules;
        * ``iarch_settings.<name>`` only for the four modules of this package that
          are not services or plans: :mod:`~iarch_settings.paths`,
          :mod:`~iarch_settings.i18n`, :mod:`~iarch_settings.version` and
          :mod:`~iarch_settings.gtkenv`.

        A plan is data a test reads, so a name that could resolve anywhere would be
        a name no test could check, and a row that could call anything would make
        the plan layer the one place the "a page never touches the machine itself"
        rule is not enforced by something.
        """
        from .. import services  # noqa: PLC0415  (late: services imports this package's paths)
        from . import MODULES as PAGE_MODULES  # noqa: PLC0415

        text = str(dotted)
        if "." not in text:
            return None
        module_name, _, attribute = text.rpartition(".")
        candidates: Tuple[str, ...] = ()
        if module_name in services.MODULES:
            candidates += (f"iarch_settings.services.{module_name}",)
        if module_name in PAGE_MODULES:
            candidates += (f"iarch_settings.pages.{module_name}",)
        if module_name in PACKAGE_MODULES:
            candidates += (f"iarch_settings.{module_name}",)
        for name in candidates:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            found = getattr(module, attribute, None)
            if callable(found):
                return found
        return None

    def call(self, dotted: str, *args: Any, **kwargs: Any) -> Any:
        """Resolve a name and call it. Raises when the name does not resolve."""
        function = self.resolve(dotted)
        if function is None:
            raise PlanError(f"{dotted} does not name a function in this application")
        return function(*args, **kwargs)


def default_context(root: Optional[Path] = None,
                    env: Optional[Mapping[str, str]] = None) -> Context:
    """A context holding the repository's own defaults.

    This is what a test builds a plan with, and what the window builds one with
    before the user's settings file has been read, so the two are the same object
    shape and a plan that works in one works in the other.
    """
    import json  # noqa: PLC0415

    path = paths.data_file(SETTINGS_NAME, root)
    settings = json.loads(path.read_text(encoding="utf-8"))
    return Context(root=root, env=env, settings=settings)


def settings_paths(root: Optional[Path] = None) -> List[str]:
    """Every dotted path in the default settings document.

    A list rather than a dict walk on demand, because three things need the same
    answer: a plan row that names a setting, the test that says every switch is
    reachable, and the coverage report that says which paths no page offers.
    """
    import json  # noqa: PLC0415

    document = json.loads(paths.data_file(SETTINGS_NAME, root).read_text(encoding="utf-8"))
    found: List[str] = []

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, Mapping):
            if not node:
                # An empty object is a setting in its own right: `glass.leaves` with
                # nothing in it is still the place an override goes, and a page that
                # offers no row for it would leave a switch only a text editor can
                # reach, which is what the coverage test exists to catch.
                found.append(prefix)
                return
            for key, value in node.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                walk(value, path)
            return
        if isinstance(node, list):
            if not node:
                found.append(prefix)  # and the same for an empty list
                return
            for index, value in enumerate(node):
                walk(value, f"{prefix}.{index}" if prefix else str(index))
            return
        found.append(prefix)

    walk(document, "")
    return found


def dynamic_container(dotted: str) -> Optional[Tuple[str, str, str]]:
    """The :data:`DYNAMIC_CONTAINERS` entry a path is inside, or ``None``.

    ``display.monitors.0.output`` is inside ``display.monitors``; ``theme.intensity``
    is inside nothing, because that path is a leaf the defaults file already names.
    """
    text = str(dotted)
    for entry in DYNAMIC_CONTAINERS:
        container = entry[0]
        if text == container or text.startswith(f"{container}."):
            return entry
    return None


# ------------------------------------------------------------------- records


_NAMES_CACHE: Dict[Tuple[str, str], Tuple[str, ...]] = {}


def record_names(block: str, root: Optional[Path] = None) -> Tuple[str, ...]:
    """One verified vocabulary out of ``data/design/adwaita.json``.

    ``block`` is ``icons``, ``style_classes``, ``named_colors``, ``css_properties``
    or ``pseudo_classes``. The record's ``icons`` block is a mapping of name to the
    sentence saying what it is for and the rest are lists, so both shapes are
    flattened to names here and a plan checks against names only.

    Cached per block and per repository root, because a page holds dozens of rows and
    every one of them asks the same question.
    """
    import json  # noqa: PLC0415

    key = (block, str(root) if root else "")
    if key not in _NAMES_CACHE:
        record = json.loads(paths.design_file(STYLE_RECORD, root).read_text(encoding="utf-8"))
        names = record[block]["names"]
        _NAMES_CACHE[key] = tuple(names) if isinstance(names, Mapping) else \
            tuple(str(name) for name in names)
    return _NAMES_CACHE[key]


# ---------------------------------------------------------------------- rows


class Row:
    """One row of a page.

    A row says what it shows, what it changes and how it is drawn, and it is
    deliberately unable to say anything else: there is no callback field and no
    widget field, so a plan cannot smuggle behaviour past the checks below. The
    renderer in :mod:`iarch_settings.widgets` is what turns ``action`` into a call.

    **How a name is called.** A row carries names, not arguments, so the contract is
    fixed and the renderer has no choice in it:

    * ``source`` is called with nothing and its return value is what the row shows.
      ``None`` means the question could not be answered, and the row says so instead
      of showing a guess.
    * ``choices_source``, ``rows_source``, ``tiles_source`` and ``uri_source`` are
      called with nothing and return a list of ``(id, label)`` pairs, a list of rows,
      a list of tiles, or one string.
    * ``validator`` is called with the text a person typed and returns ``(True, "")``
      or ``(False, "the reason")``.
    * ``sensitive_when`` and ``visible_when`` are called with nothing and return a
      bool.
    * ``action`` on a **button or link** row is called with nothing: the row is the
      whole request, which is why :data:`iarch_settings.services.noctalia.PAGE_VERBS`
      spells each verb out as its own zero-argument function.
    * ``action`` on a **value** row -- a switch, a dropdown, a number, a tile -- is
      called with the new value, and only with it. A row cannot pass a second
      argument, so anything that needs one is a different function.

    Anything an action needs beyond that has to come from the service's own reading of
    the machine, which is the point: the plan says *what* and the service decides
    *how*, and neither can reach into the other.
    """

    __slots__ = ("kind", "title", "subtitle", "icon", "setting", "action", "source",
                 "value", "choices", "choices_source", "minimum", "maximum", "step",
                 "unit", "placeholder", "validator", "rows", "rows_source",
                 "tiles_source", "uri_source", "style_classes", "keywords", "risky",
                 "confirm", "confirm_body", "sensitive_when", "visible_when")

    def __init__(self, kind: str, title: str, *, subtitle: str = "", icon: str = "",
                 setting: Optional[str] = None, action: Optional[str] = None,
                 source: Optional[str] = None, value: Any = None,
                 choices: Optional[Sequence[Sequence[str]]] = None,
                 choices_source: Optional[str] = None,
                 minimum: Optional[float] = None, maximum: Optional[float] = None,
                 step: Optional[float] = None, unit: str = "",
                 placeholder: str = "", validator: Optional[str] = None,
                 rows: Optional[Sequence["Row"]] = None,
                 rows_source: Optional[str] = None,
                 tiles_source: Optional[str] = None,
                 uri_source: Optional[str] = None,
                 style_classes: Sequence[str] = (), keywords: Sequence[str] = (),
                 risky: bool = False, confirm: str = "", confirm_body: str = "",
                 sensitive_when: Optional[str] = None,
                 visible_when: Optional[str] = None) -> None:
        if kind not in ROW_KINDS:
            raise PlanError(f"{kind} is not a row kind; the kinds are {', '.join(ROW_KINDS)}")
        self.kind = kind
        self.title = title
        self.subtitle = subtitle
        self.icon = icon
        self.setting = setting
        self.action = action
        self.source = source
        self.value = value
        self.choices = tuple(tuple(item) for item in choices) if choices else ()
        self.choices_source = choices_source
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.unit = unit
        self.placeholder = placeholder
        self.validator = validator
        self.rows = tuple(rows) if rows else ()
        self.rows_source = rows_source
        self.tiles_source = tiles_source
        self.uri_source = uri_source
        self.style_classes = tuple(style_classes)
        self.keywords = tuple(keywords)
        self.risky = bool(risky)
        self.confirm = confirm
        self.confirm_body = confirm_body
        self.sensitive_when = sensitive_when
        self.visible_when = visible_when

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Row({self.kind!r}, {self.title!r})"

    @property
    def target(self) -> str:
        """``setting``, ``action`` or ``none``: what this row changes."""
        if self.setting:
            return "setting"
        if self.action:
            return "action"
        return "none"

    def choices_list(self, context: Context) -> List[Tuple[str, str]]:
        """The choices to show, from the plan or from the function it names."""
        if self.choices:
            return [(str(item[0]), str(item[1])) for item in self.choices]
        if self.choices_source:
            resolved = context.call(self.choices_source)
            return [(str(item[0]), str(item[1])) for item in resolved]
        return []

    def rows_list(self, context: Context) -> List["Row"]:
        """The child rows, from the plan or from the function it names."""
        if self.rows:
            return list(self.rows)
        if self.rows_source:
            return list(context.call(self.rows_source))
        return []

    def current(self, context: Context) -> Any:
        """The value this row shows right now.

        A setting row reads the settings document; a row with a ``source`` asks a
        service, which is how a page shows what the session reports rather than what
        this project last wrote. ``None`` means the question could not be answered,
        and the renderer shows that instead of guessing a value.
        """
        if self.source:
            try:
                return context.call(self.source)
            except PlanError:
                return None
        if self.setting:
            return context.value(self.setting)
        return self.value

    def as_dict(self, context: Optional[Context] = None) -> dict:
        """The stable shape the search index and the tests read.

        Values that need a context -- a choices list from a function, a child list
        from a function -- are included only when one is given, so a plan can be
        dumped without resolving anything.
        """
        data: Dict[str, Any] = {
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "icon": self.icon,
            "target": self.target,
            "setting": self.setting,
            "action": self.action,
            "source": self.source,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "unit": self.unit,
            "choices": [list(item) for item in self.choices],
            "choices_source": self.choices_source,
            "rows_source": self.rows_source,
            "tiles_source": self.tiles_source,
            "uri_source": self.uri_source,
            "style_classes": list(self.style_classes),
            "keywords": list(self.keywords),
            "risky": self.risky,
            "confirm": self.confirm,
            "rows": [row.as_dict(context) for row in self.rows],
        }
        if context is not None:
            data["value"] = self.current(context)
            if not data["choices"] and self.choices_source:
                try:
                    data["choices"] = [list(item) for item in self.choices_list(context)]
                except PlanError:
                    data["choices"] = []
            if not data["rows"] and self.rows_source:
                try:
                    data["rows"] = [row.as_dict(context) for row in self.rows_list(context)]
                except PlanError:
                    data["rows"] = []
        return data

    def walk(self) -> Iterable["Row"]:
        """This row and every row beneath it, depth first."""
        yield self
        for row in self.rows:
            for nested in row.walk():
                yield nested

    def problems(self, context: Optional[Context] = None,
                 root: Optional[Path] = None) -> List[str]:
        """Every way this row fails to describe something drawable."""
        found: List[str] = []
        where = f"{self.kind} row {self.title!r}"
        if not self.title.strip():
            found.append(f"{where} has no title")

        if self.kind in VALUE_KINDS and self.target == "none":
            found.append(f"{where} changes nothing: it names neither a setting nor an action")
        if self.setting and self.action:
            found.append(f"{where} names a setting and an action; a row writes to one place")
        if self.kind in ACTION_KINDS and not self.action:
            found.append(f"{where} has no action")
        if self.kind == "state" and not self.source:
            found.append(f"{where} reads nothing: a state row needs a source")
        if self.kind == "link" and not self.uri_source and not self.action:
            found.append(f"{where} opens nothing: it needs a uri_source or an action")
        if self.kind == "expander" and not self.rows and not self.rows_source:
            found.append(f"{where} opens onto nothing: it needs rows or a rows_source")
        if self.kind == "flow" and not self.tiles_source and not self.rows:
            found.append(f"{where} has no tiles")

        if self.setting and context is not None:
            if _lookup(context.settings, self.setting) is _MISSING:
                found.append(f"{where} names {self.setting}, which is not in "
                             f"{SETTINGS_NAME}")
        for name in (self.action, self.source, self.choices_source, self.rows_source,
                     self.tiles_source, self.uri_source, self.validator,
                     self.sensitive_when, self.visible_when):
            if name and context is not None and context.resolve(name) is None:
                found.append(f"{where} names {name}, which is not a function in this "
                             f"application")

        if self.kind == "combo":
            choices = self.choices_list(context) if context else list(self.choices)
            if not choices:
                found.append(f"{where} offers no choices")
            for item in choices:
                if len(item) != 2:
                    found.append(f"{where} has a choice that is not an id and a label")
        if self.kind in ("spin", "scale"):
            if self.minimum is None or self.maximum is None:
                found.append(f"{where} has no bounds, so it could offer a value the "
                             f"generator behind it refuses")
            elif self.minimum > self.maximum:
                found.append(f"{where} has a minimum above its maximum")
            if self.step is not None and self.step <= 0:
                found.append(f"{where} has a step that is not positive")
        if self.risky and not self.confirm:
            found.append(f"{where} is marked risky but has no confirmation heading")

        if self.icon:
            icons = record_names("icons", root)
            if self.icon not in icons:
                found.append(f"{where} uses the icon {self.icon}, which "
                             f"{STYLE_RECORD} does not verify")
        classes = record_names("style_classes", root)
        for name in self.style_classes:
            if name not in classes:
                found.append(f"{where} uses the style class {name}, which "
                             f"{STYLE_RECORD} does not verify")

        for row in self.rows:
            found.extend(row.problems(context, root))
        return found


class _Missing:
    """The sentinel a path lookup returns when the path is not there."""


_MISSING = _Missing()


def _lookup(document: Mapping[str, Any], dotted: str) -> Any:
    """``theme.intensity`` in a document, or :data:`_MISSING`.

    A list index in the path is accepted, because ``display.monitors`` is a list of
    records and a row may point at a field of its items with a ``*`` in place of the
    index. ``None`` is a value a setting may legitimately hold, so it cannot be the
    answer for "not there".

    A path inside one of :data:`DYNAMIC_CONTAINERS` whose container exists is not
    missing either: the defaults file ships those five empty, so the walk above runs
    out of document before it runs out of path. The container is looked up instead,
    and finding it is the answer -- the keys inside are checked against the record
    named beside the container, which is a check with an authority behind it rather
    than one against a file that happens to be empty today.
    """
    found = _walk(document, dotted)
    if found is not _MISSING:
        return found
    parts = str(dotted).split(".")
    for position in range(len(parts) - 1, 0, -1):
        container = ".".join(parts[:position])
        if dynamic_container(container) is None:
            continue
        if _walk(document, container) is not _MISSING:
            return _walk(document, container)
    return _MISSING


def _walk(document: Mapping[str, Any], dotted: str) -> Any:
    """The literal walk :func:`_lookup` tries first."""
    node: Any = document
    parts = str(dotted).split(".")
    for position, part in enumerate(parts):
        if part == "*":
            if not isinstance(node, list) or not node:
                return _MISSING
            rest = ".".join(parts[position + 1:])
            if not rest:
                return node
            for item in node:
                if _lookup(item, rest) is not _MISSING:
                    return item
            return _MISSING
        if isinstance(node, Mapping) and part in node:
            node = node[part]
            continue
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
            continue
        return _MISSING
    return node


# -------------------------------------------------------------------- groups


class Group:
    """A card-shaped set of rows with a title and a description."""

    __slots__ = ("title", "description", "rows", "style_classes", "icon")

    def __init__(self, title: str, *rows: Row, description: str = "",
                 style_classes: Sequence[str] = (), icon: str = "") -> None:
        self.title = title
        self.description = description
        self.rows = tuple(rows)
        self.style_classes = tuple(style_classes)
        self.icon = icon

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Group({self.title!r}, {len(self.rows)} rows)"

    def as_dict(self, context: Optional[Context] = None) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "style_classes": list(self.style_classes),
            "rows": [row.as_dict(context) for row in self.rows],
        }

    def walk(self) -> Iterable[Row]:
        for row in self.rows:
            for nested in row.walk():
                yield nested

    def problems(self, context: Optional[Context] = None,
                 root: Optional[Path] = None) -> List[str]:
        found: List[str] = []
        if not self.title.strip():
            found.append("a group has no title")
        if not self.rows:
            found.append(f"the group {self.title!r} has no rows")
        classes = record_names("style_classes", root)
        for name in self.style_classes:
            if name not in classes:
                found.append(f"the group {self.title!r} uses the style class {name}, "
                             f"which {STYLE_RECORD} does not verify")
        for row in self.rows:
            found.extend(row.problems(context, root))
        return found


class Banner:
    """A persistent strip that is not an error dialog.

    ``text`` is the English source string and ``when`` names a function returning
    bool, so a banner that only appears when a tool is missing says so in the plan
    rather than in a branch inside a widget callback.
    """

    __slots__ = ("text", "kind", "icon", "when", "action")

    KINDS = ("info", "warning", "error")

    def __init__(self, text: str, *, kind: str = "info", icon: str = "",
                 when: Optional[str] = None, action: Optional[str] = None) -> None:
        if kind not in self.KINDS:
            raise PlanError(f"{kind} is not a banner kind; the kinds are "
                            f"{', '.join(self.KINDS)}")
        self.text = text
        self.kind = kind
        self.icon = icon
        self.when = when
        self.action = action

    def as_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind, "icon": self.icon,
                "when": self.when, "action": self.action}

    def shown(self, context: Context) -> bool:
        if not self.when:
            return True
        return bool(context.call(self.when))

    def problems(self, context: Optional[Context] = None,
                 root: Optional[Path] = None) -> List[str]:
        found: List[str] = []
        if not self.text.strip():
            found.append("a banner has no text")
        for name in (self.when, self.action):
            if name and context is not None and context.resolve(name) is None:
                found.append(f"a banner names {name}, which is not a function in this "
                             f"application")
        if self.icon:
            icons = record_names("icons", root)
            if self.icon not in icons:
                found.append(f"a banner uses the icon {self.icon}, which {STYLE_RECORD} "
                             f"does not verify")
        return found


class PagePlan:
    """One page, completely described.

    ``header_actions`` are the buttons in the page's own title bar, which is where
    an action that belongs to the whole page goes -- reset to defaults, re-read what
    the session reports -- rather than being buried in a group.
    """

    __slots__ = ("page_id", "title", "description", "icon", "groups", "banners",
                 "header_actions", "styles", "keywords")

    def __init__(self, page_id: str, title: str, *groups: Group, description: str = "",
                 icon: str = "", banners: Sequence[Banner] = (),
                 header_actions: Sequence[Row] = (), styles: Sequence[str] = (),
                 keywords: Sequence[str] = ()) -> None:
        self.page_id = page_id
        self.title = title
        self.description = description
        self.icon = icon
        self.groups = tuple(groups)
        self.banners = tuple(banners)
        self.header_actions = tuple(header_actions)
        self.styles = tuple(styles)
        self.keywords = tuple(keywords)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PagePlan({self.page_id!r}, {len(self.groups)} groups)"

    def as_dict(self, context: Optional[Context] = None) -> dict:
        """The whole page as data, which is what the search index is built from."""
        return {
            "page": self.page_id,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "keywords": list(self.keywords),
            "styles": list(self.styles),
            "banners": [banner.as_dict() for banner in self.banners],
            "header_actions": [row.as_dict(context) for row in self.header_actions],
            "groups": [group.as_dict(context) for group in self.groups],
        }

    def walk(self) -> Iterable[Row]:
        """Every row on the page, including header buttons and nested rows."""
        for row in self.header_actions:
            for nested in row.walk():
                yield nested
        for group in self.groups:
            for nested in group.walk():
                yield nested

    def settings_touched(self) -> Tuple[str, ...]:
        """Every settings.json path this page writes, in the order the rows appear."""
        return tuple(row.setting for row in self.walk() if row.setting)

    def actions_used(self) -> Tuple[str, ...]:
        """Every function name this page calls, read or written."""
        names: List[str] = []
        for row in self.walk():
            for name in (row.action, row.source, row.choices_source, row.rows_source,
                         row.tiles_source, row.uri_source, row.validator,
                         row.sensitive_when, row.visible_when):
                if name and name not in names:
                    names.append(name)
        for banner in self.banners:
            for name in (banner.when, banner.action):
                if name and name not in names:
                    names.append(name)
        return tuple(names)

    def search_entries(self, context: Optional[Context] = None) -> List[Dict[str, Any]]:
        """One entry per row, which is what the search index is made of.

        The text a person types is matched against the title, the subtitle, the
        group's title and the row's keywords, and the result is the page and the row
        to scroll to. Nothing here is translated: the index is built from the
        definitions and translated when it is rendered, so a plan stays readable
        without a catalogue installed.
        """
        entries: List[Dict[str, Any]] = []
        for group in self.groups:
            for row in group.walk():
                entries.append({
                    "page": self.page_id,
                    "row": row.title,
                    "group": group.title,
                    "kind": row.kind,
                    "text": " ".join(part for part in (
                        self.title, group.title, row.title, row.subtitle,
                        " ".join(row.keywords), " ".join(self.keywords)) if part),
                    "setting": row.setting,
                    "action": row.action,
                })
        for row in self.header_actions:
            entries.append({
                "page": self.page_id,
                "row": row.title,
                "group": "",
                "kind": row.kind,
                "text": " ".join(part for part in (self.title, row.title, row.subtitle,
                                                   " ".join(row.keywords)) if part),
                "setting": row.setting,
                "action": row.action,
            })
        return entries

    def problems(self, context: Optional[Context] = None,
                 root: Optional[Path] = None) -> List[str]:
        """Every way this page fails to describe something drawable."""
        from . import page as registry_page  # noqa: PLC0415

        found: List[str] = []
        spec = None
        try:
            spec = registry_page(self.page_id)
        except Exception as exc:  # noqa: BLE001 - the message is the finding
            found.append(f"page {self.page_id!r} is not in the registry: {exc}")
        if spec is not None:
            if self.title != spec.label:
                found.append(f"page {self.page_id!r} is titled {self.title!r} but the "
                             f"registry calls it {spec.label!r}")
            if self.icon and self.icon != spec.icon:
                found.append(f"page {self.page_id!r} uses the icon {self.icon} but the "
                             f"registry gives it {spec.icon}")
        if not self.groups:
            found.append(f"page {self.page_id!r} has no groups")

        classes = record_names("style_classes", root)
        for name in self.styles:
            if name not in classes:
                found.append(f"page {self.page_id!r} uses the style class {name}, which "
                             f"{STYLE_RECORD} does not verify")
        for banner in self.banners:
            found.extend(banner.problems(context, root))
        for row in self.header_actions:
            found.extend(row.problems(context, root))
        for group in self.groups:
            found.extend(group.problems(context, root))
        return found
