# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Rows for the shell's own configuration keys, generated from the record.

Three pages draw keys that belong to the shell rather than to this project -- the bar and
the dock, the audio section, the idle and lock-screen sections -- and all three need the
same four things decided the same way:

* which row kind a declared type becomes,
* what a row's bounds and choices are, and where they come from,
* how a key the record declares a *number* for but no *range* for is drawn, and
* what a write does after it succeeds.

Deciding those once is the difference between three pages that agree and three pages that
each invented a rule. The rule that matters most is the fourth: a ``config-set`` the shell
has not reloaded is a change nothing has read yet, so every setter here sends the set and
then the reload, and returns the reload's outcome -- a set that arrived and a reload that
did not are not the same verdict on screen.

This module is not a page and is not in :data:`iarch_settings.pages.MODULES`. It builds
:class:`~iarch_settings.pages.plan.Row` objects whose ``source`` and ``action`` names point
into the *calling* page module, and returns the callables those names need as a dictionary
the caller installs in its own globals. That indirection is deliberate: a plan resolves a
name against the modules it is allowed to resolve into, and a page's rows have to name
functions that exist in a module the resolver can reach.

Nothing here invents a key, a bound or a choice list. Every one comes out of
``data/design/noctalia.json``, which was read out of the shell's own schema at a pinned
release, and :func:`iarch_settings.services.noctalia.check_value` refuses a value the key
does not accept before a verb is sent -- because the shell clamps an out-of-range number
and reports success, and a reply that says a change worked is not a change that arrived.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..services import noctalia, runner
from .plan import Row

#: The icon a row gets when its bucket has none. A name ``data/design/adwaita.json``
#: verifies, because a plan checks every icon a row names and an icon the record does not
#: carry is an icon the theme does not ship.
FALLBACK_ICON = "applications-system-symbolic"

#: The group a key lands in when no bucket claims it. A bucket list is a guess about how
#: keys group; this is the guarantee that a key the record gains cannot disappear from the
#: page because nobody added it to a bucket.
FALLBACK_TITLE = "Other keys the record declares"


# --------------------------------------------------------------------- names


def container_prefix(container: str) -> str:
    """``bar.default`` becomes ``bar``, so a generated name stays readable."""
    return str(container).split(".")[0]


def key_name(path: str) -> str:
    """``audio.enable_sounds`` becomes ``enable_sounds``."""
    return str(path).rsplit(".", 1)[1]


def reader_name(path: str) -> str:
    """The attribute, in the calling page's module, that reads this key."""
    return f"current_{container_prefix(path)}_{key_name(path)}"


def setter_name(path: str) -> str:
    """The attribute that writes this key."""
    return f"set_{container_prefix(path)}_{key_name(path)}"


def text_setter_name(path: str) -> str:
    """The attribute that parses typed text and then writes this key."""
    return f"set_text_{container_prefix(path)}_{key_name(path)}"


def title_for(path: str) -> str:
    """A person-facing title, from the key: underscores to spaces, first word capitalised."""
    return key_name(path).replace("_", " ").capitalize()


def subtitle_for(path: str, specs: Mapping[str, Mapping[str, Any]]) -> str:
    """What the key is, in the record's own terms: name, type, range, enum, colour.

    The subtitle carries the key name as well, because a person reading the shell's
    documentation should be able to match a row to a key without guessing which of two
    words on screen is the one the shell knows.
    """
    spec = specs.get(path) or {}
    bits = [f"{key_name(path)}: {spec.get('type') or 'value'}"]
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
    note = spec.get("note")
    if note and len(bits) == 1:
        bits.append(str(note))
    return "; ".join(bits)


# --------------------------------------------------------------------- shapes


def specs(root: Optional[Any] = None) -> Dict[str, Dict[str, Any]]:
    """Every shell configuration key the record declares, by dotted path."""
    try:
        return noctalia.key_specs(root)
    except noctalia.NoctaliaError:
        return {}


def keys_of(container: str, root: Optional[Any] = None, *, direct: bool = False) -> List[str]:
    """The record's own keys for one container, sorted by key name.

    ``direct`` narrows the list to the keys that sit immediately under the container, which
    is what a page wants when the container also holds tables of its own: the shell's
    ``launcher``, ``panel``, ``session`` and ``window_switcher`` are tables with sixty leaves
    between them, and a page that drew all of them would be drawing somebody else's settings
    window. Those tables are named by :func:`table_keys` instead, so the page can say they
    exist and where they are changed.
    """
    prefix = container + "."
    found = [path for path in specs(root) if path.startswith(prefix)]
    if direct:
        found = [path for path in found if "." not in path[len(prefix):]]
    return sorted(found, key=key_name)


def table_keys(container: str, root: Optional[Any] = None) -> List[str]:
    """The tables under one container, so a page can name them instead of drawing them."""
    try:
        tables = noctalia.table_paths(root)
    except noctalia.NoctaliaError:
        return []
    prefix = container + "."
    return [path for path in tables if path.startswith(prefix)]


def array_keys(container: str, root: Optional[Any] = None) -> List[str]:
    """The container's keys whose declared type is an array.

    A page shows these and does not offer them, and the reason is the same one the bar
    page gives for its module lists: an array of strings is a list editor -- add, remove,
    reorder -- and a single entry row for it would be a control that can only ever rewrite
    the whole list from a text field. ``lockscreen.transition`` is the sharpest case, since
    the record declares an enum for its *items* and not for the key, so a dropdown built
    from that enum would offer one transition where the shell takes an ordered sequence of
    them.
    """
    table = specs(root)
    return [path for path in keys_of(container, root)
            if str((table.get(path) or {}).get("type") or "") == "array"]


def is_unbounded_number(path: str, root: Optional[Any] = None) -> bool:
    """True for a number key the record declares without a range.

    The bar's margins, padding and widget spacing are like this while the dock's
    equivalents all carry a range. The record says what it says, so a page neither borrows
    the dock's limits for the bar's keys nor invents others: the row becomes an entry with
    a validator that accepts a number and nothing else, which is a widget that cannot
    offer a spelling the shell would silently ignore and cannot claim a bound the record
    does not state.
    """
    spec = specs(root).get(path) or {}
    return str(spec.get("type") or "") in ("integer", "float") and not spec.get("range")


def bucket_for(path: str, buckets: Sequence[Sequence[Any]], fallback: str) -> str:
    """Which group a key belongs to, by name prefix, or the fallback group.

    Prefixes rather than whole names, because a container's radii and scales are families
    and listing every member is a list that goes stale the first time the record adds one.
    """
    name = key_name(path)
    for title, prefixes in buckets:
        if any(name.startswith(str(prefix)) for prefix in prefixes):
            return str(title)
    return fallback


# ------------------------------------------------------------------ callables


def make_reader(path: str) -> Callable[[], Optional[Any]]:
    """A zero-argument reader for one key: the shell's value, or ``None``."""

    def read() -> Optional[Any]:
        value, verdict, _reason = noctalia.read(path)
        return value if verdict == runner.OK else None

    read.__name__ = reader_name(path)
    read.__doc__ = f"What the shell holds for ``{path}``, or ``None`` if it did not answer."
    return read


def make_setter(path: str) -> Callable[[Any], runner.Outcome]:
    """A one-argument writer for one key: set it, then reload the shell's config.

    Two calls and not one, because the record is explicit that a ``config-set`` the shell
    has not reloaded is a change nothing has read yet. The reload's outcome is what comes
    back, so a set that arrived and a reload that did not are different verdicts.
    """

    def write(value: Any) -> runner.Outcome:
        outcome = noctalia.config_set(path, value)
        if outcome.verdict != runner.OK:
            return outcome
        return noctalia.reload()

    write.__name__ = setter_name(path)
    write.__doc__ = f"Write ``{path}`` through the shell's IPC, then reload its config."
    return write


def make_text_setter(path: str) -> Callable[[Any], runner.Outcome]:
    """A one-argument writer that parses typed text before writing the number.

    An entry hands back what a person typed, so the parse happens here rather than in the
    shell: a string that is not a number is refused with a sentence before a verb is sent,
    and the number that does get sent is the type the record declares for the key.
    """
    integer = str((specs().get(path) or {}).get("type")) == "integer"

    def write(value: Any) -> runner.Outcome:
        text = str(value).strip()
        try:
            number: Any = int(text) if integer else float(text)
        except ValueError:
            return runner.Outcome(
                [runner.NOCTALIA_BIN, "msg", "config-set", path], runner.FAILED,
                reason=f"{text!r} is not {'an integer' if integer else 'a number'}, so "
                       f"{key_name(path)} is not sent")
        return make_setter(path)(number)

    write.__name__ = text_setter_name(path)
    write.__doc__ = f"Parse the typed text and write ``{path}`` as a number."
    return write


def integer_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether typed text is a whole number, for a key with no recorded range."""
    text = str(value or "").strip()
    if not text:
        return True, ""
    try:
        int(text)
    except ValueError:
        return False, f"{text!r} is not a whole number"
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


def colour_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether a colour key's text is usable, for the entry row's validator.

    The shell's own colour field accepts a colour **role name** -- the roles in the
    record's palette section -- or a fixed hex colour, and answers anything else with an
    error that leaves the old value in place. Checking the shape here means the row says so
    while a person is typing instead of after the write failed.
    """
    text = str(value or "").strip()
    if not text:
        return True, ""
    try:
        roles = noctalia.design_record().get("color_roles") or []
    except noctalia.NoctaliaError:
        roles = []
    if text in roles:
        return True, ""
    if text.startswith("#") and len(text) in (4, 7, 9) and all(
            character in "0123456789abcdefABCDEF" for character in text[1:]):
        return True, ""
    return False, (f"{text!r} is neither one of the {len(roles)} colour role names nor a "
                   f"hex colour such as #rrggbb")


#: The validators a page has to expose for the rows this module builds, so that a name a
#: row points at exists in a module the plan's resolver can reach.
VALIDATORS: Dict[str, Callable[[Any], Tuple[bool, str]]] = {
    "integer_is_valid": integer_is_valid,
    "number_is_valid": number_is_valid,
    "colour_is_valid": colour_is_valid,
}


# ------------------------------------------------------------------- the rows


def row_for(path: str, module: str, icon: str = "",
            root: Optional[Any] = None) -> Row:
    """One row for one recorded key, of the kind the record's type implies.

    The mapping is the record's, not a designer's: a boolean is a switch; a key with an
    enum is a dropdown and never an entry, because the shell silently ignores a spelling it
    does not know; a float with a range is a scale; an integer with a range is a spin; a
    number with no range is an entry with a validator; a colour is an entry with a
    validator; and anything else is an entry, which is the honest answer for a free string
    such as a date format.
    """
    table = specs(root)
    spec = table.get(path) or {}
    kind = str(spec.get("type") or "string")
    bounds = spec.get("range") or []
    choices = spec.get("enum")
    common: Dict[str, Any] = {
        "source": f"{module}.{reader_name(path)}",
        "subtitle": subtitle_for(path, table),
        "icon": icon or FALLBACK_ICON,
        "keywords": tuple(part for part in (key_name(path), path, kind,
                                            container_prefix(path), "shell") if part),
    }
    action = f"{module}.{setter_name(path)}"

    if kind == "bool":
        return Row("switch", title_for(path), action=action, **common)
    if isinstance(choices, list) and choices:
        return Row("combo", title_for(path), action=action,
                   choices=[(str(choice), str(choice).replace("_", " ").title())
                            for choice in choices], **common)
    if kind in ("integer", "float"):
        if len(bounds) >= 2:
            low, high = float(bounds[0]), float(bounds[1])
            step = float(bounds[2]) if len(bounds) > 2 else (
                1.0 if kind == "integer" else 0.05)
            # A slider only when the record gives the key a range to slide across: a scale
            # has to be drawable, and inventing bounds would put a stop on the widget that
            # the shell does not have.
            return Row("spin" if kind == "integer" else "scale", title_for(path),
                       action=action, minimum=low, maximum=high, step=step, **common)
        return Row("entry", title_for(path),
                   action=f"{module}.{text_setter_name(path)}",
                   validator=(f"{module}.integer_is_valid" if kind == "integer"
                              else f"{module}.number_is_valid"),
                   placeholder="0" if kind == "integer" else "0.0", **common)
    if spec.get("color"):
        return Row("entry", title_for(path), action=action,
                   validator=f"{module}.colour_is_valid", placeholder="primary", **common)
    return Row("entry", title_for(path), action=action, **common)


def build(container: str, module: str, *,
          buckets: Sequence[Sequence[Any]] = (),
          only: Sequence[str] = (),
          skip: Sequence[str] = (),
          icons: Optional[Mapping[str, str]] = None,
          fallback_icon: str = FALLBACK_ICON,
          fallback_title: str = FALLBACK_TITLE,
          root: Optional[Any] = None,
          ) -> Tuple[Dict[str, List[Row]], Dict[str, Any]]:
    """Rows for one container's keys, grouped, plus the names they need installed.

    ``skip`` is the caller's own read-only list: a key the record declares without a closed
    choice list, or an array that needs a list editor, is shown by the page rather than
    offered here. ``only`` is the other half of the same decision, for a container two
    pages share: the shell declares twenty-three keys of its own, and the three about the
    clipboard and telemetry belong on the Features page while the fourteen about corners,
    borders and type belong on Appearance. Naming the ones a page wants is how the two
    pages cannot both draw the same switch, and a key neither page names is a key the plan
    walker reports as unreachable rather than one that quietly goes missing. The returned dictionary is what the page installs in its globals, so that
    every ``source``, ``action`` and ``validator`` a row names resolves -- which is the
    whole of what a plan checks.
    """
    icon_by_bucket = dict(icons or {})
    grouped: Dict[str, List[Row]] = {}
    names: Dict[str, Any] = dict(VALIDATORS)

    def full(path: str) -> str:
        """A key name or a full path, as the caller happened to write it."""
        return str(path) if str(path).startswith(container + ".") else f"{container}.{path}"

    skipped = {full(path) for path in skip}
    wanted = {full(path) for path in only}

    for path in keys_of(container, root, direct=True):
        names[reader_name(path)] = make_reader(path)
        names[setter_name(path)] = make_setter(path)
        if is_unbounded_number(path, root):
            names[text_setter_name(path)] = make_text_setter(path)
        if path in skipped or (wanted and path not in wanted):
            continue
        if str((specs(root).get(path) or {}).get("type") or "") == "array":
            # An array is a list editor and this generator is not one, so it is left for the
            # page to show: see :func:`array_keys`.
            continue
        title = bucket_for(path, buckets, fallback_title)
        grouped.setdefault(title, []).append(
            row_for(path, module, icon_by_bucket.get(title, fallback_icon), root))

    order = [str(bucket_title) for bucket_title, _prefixes in buckets] + [fallback_title]
    ordered = {title: grouped[title] for title in order if grouped.get(title)}
    return ordered, names
