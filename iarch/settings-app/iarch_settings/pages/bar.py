# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Bar, Dock & Panels page: every key the shell declares, and only those.

Nothing on this page is in ``~/.config/iarch/settings.json``. The shell owns its bar
and its dock, it reads them from its own ``config.toml``, and the default file's own
note says so outright -- a second copy here would be a value that can disagree with
the one being drawn. So every row reads and writes through the shell's IPC
(:mod:`iarch_settings.services.noctalia`), and every write is followed by
``config-reload``, because a set that is not reloaded is a change nothing has read
yet.

The rows are generated from ``data/design/noctalia.json`` rather than typed out, and
that is the point of the page: the record was read out of the shell's own schema at a
pinned release, key by key, with the type, the range and the enum each key declares.
Generating from it means three things hold at once:

* **A key the record does not carry cannot be sent.** :func:`noctalia.check_path`
  refuses it before a process starts, so a typo is a sentence rather than the shell's
  ``warning: unknown setting`` coming back looking like a value.
* **A value the key does not accept cannot be sent either.** The shell *clamps* an
  out-of-range number and reports success, which is the worst possible reply, so
  :func:`noctalia.check_value` refuses the number here instead.
* **A key added to the record appears on this page.** The groups below match keys by
  prefix and every key that matches nothing lands in the last group, so the page
  cannot silently drop one -- which is what makes "every visual switch is reachable"
  a property of the record instead of a promise somebody has to keep by hand.

Two things are deliberately *not* switches here. ``bar.default.position`` is a real
key -- the record notes it is keyed outside the field schema, as a container level --
but the record declares no enum for it, and a dropdown of four guesses would be a
choice list this project invented. So it is shown, with the shell's own window offered
as the way to change it. The three module arrays (``start``, ``center``, ``end``) are
shown as counts for the same reason: reordering modules is a list editor, and shipping
a half list editor is worse than pointing at the one that exists.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..services import noctalia, runner
from . import page as registry_page
from . import shellkeys
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "bar"

#: The two containers this page draws. ``bar.default`` is the bar whose own ``name``
#: key is ``default``; the record's section name is already the dotted config prefix.
BAR = "bar.default"
DOCK = "dock"

#: Keys shown but not written, each with the reason in the page's own words. A key the
#: record declares without a closed choice list is not a key this project guesses one
#: for, and an array is not a switch.
READ_ONLY: Dict[str, str] = {
    f"{BAR}.position":
        "A real key, and keyed outside the bar's field schema as a container level -- "
        "but the record declares no enum for it, so this page shows it rather than "
        "offering four guesses. The shell's own window changes it.",
    f"{BAR}.start":
        "The modules at the start of the bar. Reordering them is a list editor, and "
        "this page does not ship half of one.",
    f"{BAR}.center":
        "The modules in the centre of the bar. Reordering them is a list editor, and "
        "this page does not ship half of one.",
    f"{BAR}.end":
        "The modules at the end of the bar. Reordering them is a list editor, and "
        "this page does not ship half of one.",
}

#: Group membership by key-name prefix, in order. Anything a bucket does not claim
#: falls through to the last group of its container, so a key the record gains cannot
#: disappear from the page: see :func:`bucket_for`.
BAR_BUCKETS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Where the bar sits", ("position", "enabled", "auto_hide", "reserve_space",
                            "thickness", "scale", "font_scale")),
    ("Its surface", ("background_opacity", "compositor_blur", "border", "shadow",
                     "contact_shadow", "radius_", "margin_", "padding",
                     "widget_spacing")),
    ("Capsules", ("capsule",)),
)

DOCK_BUCKETS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Where the dock sits", ("enabled", "position", "layer", "active_monitor_only",
                             "auto_hide", "reserve_space", "show_running")),
    ("How the dock looks", ("icon_size", "main_axis_padding", "cross_axis_padding",
                            "item_spacing", "background_opacity", "compositor_blur",
                            "border", "shadow", "radius", "margin_", "active_scale",
                            "inactive_scale", "magnification")),
)

#: One icon per bucket, and every name is one ``data/design/adwaita.json`` verifies.
#: A plan checks this and it is right to: an icon the record does not carry is an icon
#: the theme does not ship, and the renderer draws that as a missing image rather than
#: as a slightly different picture. So these are the obvious-looking names that exist
#: -- a bar is a sidebar, a dock is an app grid, a surface is appearance -- and not the
#: ones that would have been nicer.
ICON_BY_BUCKET = {
    "Where the bar sits": "sidebar-show-symbolic",
    "Its surface": "preferences-desktop-appearance-symbolic",
    "Capsules": "preferences-desktop-appearance-symbolic",
    "Where the dock sits": "view-app-grid-symbolic",
    "How the dock looks": "preferences-desktop-appearance-symbolic",
}

FALLBACK_ICON = "applications-system-symbolic"


# --------------------------------------------------------------------- readers


def specs() -> Dict[str, Dict[str, Any]]:
    """Every shell configuration key the record declares, by dotted path."""
    try:
        return noctalia.key_specs()
    except noctalia.NoctaliaError:
        return {}


def container(container_name: str) -> List[str]:
    """The record's own keys for one container, in the record's own order."""
    found = [path for path in specs() if path.startswith(container_name + ".")]
    return sorted(found, key=lambda path: path.rsplit(".", 1)[1])


def key_name(path: str) -> str:
    """``bar.default.background_opacity`` becomes ``background_opacity``."""
    return path.rsplit(".", 1)[1]


def title_for(path: str) -> str:
    """A person-facing title, from the key: underscores to spaces, first word capitalised."""
    return key_name(path).replace("_", " ").capitalize()


def subtitle_for(path: str) -> str:
    """What the key is, in the record's own terms: type, range, enum, colour.

    The subtitle carries the key name as well, because a person reading the shell's
    documentation should be able to match a row to a key without guessing.
    """
    spec = specs().get(path) or {}
    kind = str(spec.get("type") or "value")
    bits = [f"{key_name(path)}: {kind}"]
    bounds = spec.get("range") or []
    if len(bounds) >= 2:
        step = bounds[2] if len(bounds) > 2 else None
        bits.append(f"the shell accepts {float(bounds[0]):g} to {float(bounds[1]):g}"
                    + (f" in steps of {float(step):g}" if step else ""))
    choices = spec.get("enum")
    if isinstance(choices, list) and choices:
        bits.append("one of " + ", ".join(str(choice) for choice in choices))
    if spec.get("color"):
        bits.append("a colour role name or a fixed hex colour")
    return "; ".join(bits)


def bucket_for(path: str, buckets: Sequence[Sequence[Any]], fallback: str) -> str:
    """Which group a key belongs to, by prefix, or the fallback group.

    Prefixes rather than whole names because the bar's four corner radii and the
    dock's two scales are families, and listing each member is a list that goes stale
    the first time the record adds one.
    """
    name = key_name(path)
    for title, prefixes in buckets:
        if any(name.startswith(prefix) for prefix in prefixes):
            return str(title)
    return fallback


def is_unbounded_number(path: str) -> bool:
    """True for a number key the record declares without a range.

    Four of the bar's keys are like this -- its margins, its padding and the space
    between its widgets -- while the dock's equivalents all carry one. The record says
    what it says, so the page does not borrow the dock's limits for the bar's keys and
    does not invent others. What it does instead is draw an entry with a validator that
    accepts a number and nothing else: the widget then cannot offer a spelling the
    shell would silently ignore, and the shell's own validation stays the only limit.
    """
    spec = specs().get(path) or {}
    return str(spec.get("type") or "") in ("integer", "float") and not spec.get("range")


def _reader(path: str) -> Callable[[], Optional[Any]]:
    """Build the reader one row shows: the shell's own value for this key."""

    def read() -> Optional[Any]:
        value, verdict, _reason = noctalia.read(path)
        return value if verdict == runner.OK else None

    read.__name__ = f"current_{key_name(path)}"
    read.__doc__ = f"What the shell holds for ``{path}``, or ``None`` if it did not answer."
    return read


def _setter(path: str) -> Callable[[Any], runner.Outcome]:
    """Build the writer one row uses: set the key, then reload the shell's config.

    Two calls and not one, because the record is explicit that a ``config-set`` the
    shell has not reloaded is a change nothing has read yet. The reload's outcome is
    what comes back, so a set that arrived and a reload that did not are not the same
    verdict on screen.
    """

    def write(value: Any) -> runner.Outcome:
        outcome = noctalia.config_set(path, value)
        if outcome.verdict != runner.OK:
            return outcome
        return noctalia.reload()

    write.__name__ = f"set_{key_name(path)}"
    write.__doc__ = f"Write ``{path}`` through the shell's IPC, then reload its config."
    return write


def _text_setter(path: str) -> Callable[[Any], runner.Outcome]:
    """Build the writer an entry row uses: parse the text, then write the number.

    An entry hands back what a person typed, so the parse is here rather than in the
    shell: a string that is not a number is refused with a sentence before a verb is
    sent, and the number that does get sent is a real one, which is what the record's
    type for the key asks for.
    """
    spec = specs().get(path) or {}
    integer = str(spec.get("type")) == "integer"

    def write(value: Any) -> runner.Outcome:
        text = str(value if not isinstance(value, str) else value).strip()
        try:
            number: Any = int(text) if integer else float(text)
        except ValueError:
            return runner.Outcome(
                [runner.NOCTALIA_BIN, "msg", "config-set", path], runner.FAILED,
                reason=f"{text!r} is not {'an integer' if integer else 'a number'}, so "
                       f"{key_name(path)} is not sent")
        return _setter(path)(number)

    write.__name__ = f"set_text_{key_name(path)}"
    write.__doc__ = f"Parse the typed text and write ``{path}`` as a number."
    return write


def _register(paths: Sequence[str]) -> None:
    """Make one reader and one writer per path a module attribute.

    Built in a loop because the set comes from the record and a hand-written list of
    fifty names would drift the first time the shell adds a key; each is still a real
    module attribute, which is what a plan row resolves.
    """
    for path in paths:
        name = key_name(path).replace(".", "_")
        short = f"{path.split('.')[0]}_{name}"
        globals()[f"current_{short}"] = _reader(path)
        globals()[f"set_{short}"] = _setter(path)
        if is_unbounded_number(path):
            globals()[f"set_text_{short}"] = _text_setter(path)


OFFERED: Tuple[str, ...] = tuple(container(BAR)) + tuple(container(DOCK))
_register(OFFERED)


def reader_name(path: str) -> str:
    """The module attribute that reads ``path``."""
    return f"bar.current_{path.split('.')[0]}_{key_name(path).replace('.', '_')}"


def setter_name(path: str) -> str:
    """The module attribute that writes ``path``.

    A number the record gives no range for is written through the text setter, because
    the row that offers it is an entry and an entry hands back a string.
    """
    prefix = "set_text_" if is_unbounded_number(path) else "set_"
    return (f"bar.{prefix}{path.split('.')[0]}_"
            f"{key_name(path).replace('.', '_')}")


def integer_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether typed text is an integer, for the four keys with no recorded range."""
    text = str(value or "").strip()
    if not text:
        return True, ""
    try:
        int(text)
    except ValueError:
        return False, f"{text!r} is not a whole number of pixels"
    return True, ""


def number_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether typed text is a number, for a float key with no recorded range."""
    text = str(value or "").strip()
    if not text:
        return True, ""
    try:
        float(text)
    except ValueError:
        return False, f"{text!r} is not a number"
    return True, ""


def state_sentence() -> str:
    """Whether the shell can be asked at all, in its own words."""
    return noctalia.available()


def unreadable_text() -> Optional[str]:
    """Which keys the shell did not answer for, or ``None`` when it answered all.

    One row for the whole page rather than one per key, because a switch whose value
    could not be read still has to be drawn, and the honest place to say so is a
    sentence that names every key at once.
    """
    if not shell_reachable():
        # No binary on PATH: every read is unknown, and saying so fifty times is noise
        # where one row and one banner will do.
        return None
    missing = [path for path in OFFERED if noctalia.read(path)[1] != runner.OK]
    if not missing:
        return None
    return (f"{len(missing)} of {len(OFFERED)} keys did not answer: "
            + ", ".join(key_name(path) for path in missing[:8])
            + ("…" if len(missing) > 8 else ""))


def array_rows() -> List[Row]:
    """One read-only row per key this page shows and does not write."""
    rows: List[Row] = []
    for path in sorted(READ_ONLY):
        value, verdict, _reason = noctalia.read(path)
        text = title_for(path)
        if verdict == runner.OK and isinstance(value, list):
            text = f"{title_for(path)}: {len(value)} module{'s' if len(value) != 1 else ''}"
        rows.append(Row(
            "state", text, source=reader_name(path), icon="dialog-warning-symbolic",
            subtitle=READ_ONLY[path], keywords=(key_name(path), path, "read-only",
                                                "not written")))
    return rows


def colour_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether a colour key's text is usable, for the entry row's validator.

    The shell's own field accepts a colour **role name** -- the 28 roles in the
    record's palette section -- or a fixed hex colour, and answers a bad one with an
    error that leaves the old value in place. Checking the shape here means the row
    says so while a person is typing instead of after the write failed.
    """
    text = str(value or "").strip()
    if not text:
        return True, ""
    roles = noctalia.design_record().get("color_roles") or []
    if text in roles:
        return True, ""
    if text.startswith("#") and len(text) in (4, 7, 9) and all(
            character in "0123456789abcdefABCDEF" for character in text[1:]):
        return True, ""
    return False, (f"{text!r} is neither one of the {len(roles)} colour role names nor "
                   f"a hex colour such as #rrggbb")


def row_for(path: str) -> Row:
    """One row for one recorded key, of the kind the record's type implies.

    The mapping is the record's, not a designer's: a boolean is a switch, a key with
    an enum is a dropdown (never an entry, because the shell silently ignores a
    spelling it does not know), a float with a range is a scale, an integer with a
    range is a spin, a colour is an entry with a validator, and anything else is an
    entry -- which is the honest answer for a free string such as a date format.
    """
    spec = specs().get(path) or {}
    kind = str(spec.get("type") or "string")
    bounds = spec.get("range") or []
    choices = spec.get("enum")
    name = key_name(path)
    common: Dict[str, Any] = {
        "source": reader_name(path),
        "subtitle": subtitle_for(path),
        "icon": ICON_BY_BUCKET.get(
            bucket_for(path, BAR_BUCKETS if path.startswith(BAR) else DOCK_BUCKETS, ""),
            FALLBACK_ICON),
        "keywords": tuple(part for part in (name, path, kind, "bar" if path.startswith(BAR)
                                            else "dock", "shell") if part),
    }
    if kind == "bool":
        return Row("switch", title_for(path), action=setter_name(path), **common)
    if isinstance(choices, list) and choices:
        return Row("combo", title_for(path), action=setter_name(path),
                   choices=[(str(choice), str(choice).replace("_", " ").title())
                            for choice in choices], **common)
    if kind in ("integer", "float"):
        if len(bounds) >= 2:
            low, high = float(bounds[0]), float(bounds[1])
            step = float(bounds[2]) if len(bounds) > 2 else (
                1.0 if kind == "integer" else 0.05)
            # A slider only when the record gives the key a range to slide across: a
            # scale has to be drawable, and inventing bounds would put a stop on the
            # widget that the shell does not have.
            return Row("spin" if kind == "integer" else "scale", title_for(path),
                       action=setter_name(path), minimum=low, maximum=high, step=step,
                       **common)
        # A number the record declares no range for: an entry with a validator, so the
        # widget cannot offer a spelling the shell would ignore and cannot claim a
        # bound the record does not state. See :func:`is_unbounded_number`.
        return Row("entry", title_for(path), action=setter_name(path),
                   validator=("bar.integer_is_valid" if kind == "integer"
                              else "bar.number_is_valid"),
                   placeholder="0" if kind == "integer" else "0.0", **common)
    if spec.get("color"):
        return Row("entry", title_for(path), action=setter_name(path),
                   validator="bar.colour_is_valid", placeholder="primary", **common)
    return Row("entry", title_for(path), action=setter_name(path), **common)


def group_rows(container_name: str, buckets: Sequence[Sequence[Any]]) -> Dict[str, List[Row]]:
    """The container's writable rows, grouped, with a catch-all group last."""
    fallback = "Other keys the record declares"
    grouped: Dict[str, List[Row]] = {}
    for path in container(container_name):
        if path in READ_ONLY:
            continue
        grouped.setdefault(bucket_for(path, buckets, fallback), []).append(row_for(path))
    order = [str(title) for title, _prefixes in buckets] + [fallback]
    return {title: grouped[title] for title in order if grouped.get(title)}


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Bar, Dock & Panels page, as data."""
    spec = registry_page(PAGE_ID)
    bar_groups = group_rows(BAR, BAR_BUCKETS)
    dock_groups = group_rows(DOCK, DOCK_BUCKETS)

    groups: List[Group] = []
    for title, rows in bar_groups.items():
        groups.append(Group(
            title, *rows,
            description="Every key below is the shell's own, read from the record of "
                        "its schema: the range or the choice list in each subtitle is "
                        "the one the shell enforces."
            if title == "Where the bar sits" else "",
            style_classes=("iarch-glass-card",) if title == "Where the bar sits" else (),
        ))
    for title, rows in dock_groups.items():
        groups.append(Group(title, *rows))

    groups.append(Group(
        "Shown, not written",
        Row("expander", "Keys this page does not change", rows=tuple(array_rows()),
            icon="dialog-warning-symbolic",
            subtitle="A key with no recorded choice list, and the three module arrays",
            keywords=("read-only", "position", "start", "center", "end", "modules")),
        Row("state", "Can the shell be asked?", icon="utilities-terminal-symbolic",
            source="bar.state_sentence", keywords=("ipc", "noctalia", "available")),
        Row("state", "Keys that did not answer", icon="dialog-warning-symbolic",
            source="bar.unreadable_text",
            subtitle="A switch still has to be drawn when its value could not be read, "
                     "so this says which ones",
            keywords=("unread", "unknown", "verdict")),
        Row("button", "Open this in the shell's own window",
            action="noctalia.open_shell_settings", icon="go-next-symbolic",
            subtitle="The escape hatch the record describes: for a key this project "
                     "has not verified a range for, the shell's own settings window is "
                     "the one that has",
            keywords=("shell", "settings", "open", "escape hatch")),
        description="Nothing here is stored twice. The shell's bar, dock, audio, idle "
                    "and wallpaper keys are read and written through its IPC, and "
                    "settings.json never holds a copy that could disagree.",
    ))

    groups.append(Group(
        "The control centre, named and not written",
        Row("expander", "Eleven keys", rows=tuple(_CONTROL_CENTRE_ROWS),
            icon="view-conceal-symbolic",
            subtitle="Named so that nothing the shell declares is unreachable, and changed in "
                     "the shell's own window",
            keywords=("control center", "control centre", "shell", "named", "not written",
                      "calendar", "media", "sidebar")),
        Row("state", "Why they are not controls here", icon="dialog-information-symbolic",
            source="bar.control_centre_why",
            keywords=("control centre", "why", "surface")),
        description=CONTROL_CENTRE_WHY,
    ))

    return PagePlan(
        PAGE_ID, spec.label, *groups,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("Every write here goes to the shell over its IPC and is followed by "
                   "a config reload: this application never edits the shell's own "
                   "config.toml.",
                   kind="info", icon="utilities-terminal-symbolic"),
            Banner("A number outside the range the shell accepts is refused here, "
                   "because the shell clamps it and reports success -- and a reply "
                   "that says the change worked is not a change that arrived.",
                   kind="info", icon="dialog-warning-symbolic",
                   when="bar.shell_reachable"),
        ),
        header_actions=(
            Row("state", "Keys on this page", icon="applications-system-symbolic",
                source="bar.key_count_text", keywords=("keys", "count", "bar", "dock")),
        ),
    )


#: The control centre's own keys, named here and not written here.
#:
#: The Bar, Dock & Panels page writes the shell's bar and dock keys, and the control centre is
#: the third surface in that record. Its keys are named with the shape the record gives each
#: one, because a key no page mentions is unreachable -- and the reason they are not controls
#: is that this page has not verified what changing one does to a surface it does not draw.
CONTROL_CENTRE_WHY = (
    "the control centre is a surface this page does not draw: its keys are named so that "
    "nothing the shell declares is unreachable, and they are changed in the shell's own "
    "settings window, which is the button below")

_CONTROL_CENTRE_ROWS, _CONTROL_CENTRE_NAMES = shellkeys.named_rows(
    "control_center", PAGE_ID, why=CONTROL_CENTRE_WHY)
globals().update(_CONTROL_CENTRE_NAMES)


def control_centre_why() -> str:
    """Why the control centre's keys are named here and not drawn here."""
    return CONTROL_CENTRE_WHY


def key_count_text() -> str:
    """How many of the record's keys this page offers, for the title bar."""
    writable = len([path for path in OFFERED if path not in READ_ONLY])
    return f"{writable} shell keys written here, {len(READ_ONLY)} shown and not written"


def shell_reachable() -> bool:
    """Whether the shell's binary is on PATH, so a verb could be sent at all.

    :func:`noctalia.available` returns a sentence for a person, and both of its
    sentences begin the same way, so it cannot be used as the predicate: this asks the
    question the sentence answers. The banner about clamped numbers only matters when
    a number can be sent, and a warning about a thing that cannot happen is noise on a
    machine without the shell.
    """
    return runner.which(runner.NOCTALIA_BIN) is not None
