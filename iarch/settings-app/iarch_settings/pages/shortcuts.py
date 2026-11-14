# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Shortcuts page: the table, and a plain statement that it is a table.

The shortcut *system* -- the overlay behind ``Super+H``, searchable, in glass -- is
Part 7 of this project, and ``docs/ROADMAP.md:205-211`` says so. What exists today is
the truth that overlay will be drawn from: ``.config/hypr/keybind.lua`` binds keys to
dispatchables and gives each one a ``description``, ``tools/extract_keybinds.py`` reads
those binds into ``data/keybinds.default.json``, and ``tools/render_shortcuts.py``
renders that JSON into ``docs/SHORTCUTS.md``. One source, two renderings.

So this page is a third rendering of the same data and it is **read-only**, for a
reason worth stating on the page rather than only here: the binds live in a Lua file
the compositor reads at startup, and a settings window that edited it would be a second
writer of a file whose only other writer is a person with a text editor. Editing a
keybind also means choosing a key that is not already taken, which is the collision
check Part 7's single source of truth exists to make -- so until that exists, this page
shows what is bound and does not offer to change it.

Nothing is parsed out of the Lua file at draw time. The page reads the JSON the
extractor wrote, which is the same file the documentation is rendered from, so a table
here and a table in ``docs/SHORTCUTS.md`` cannot disagree unless the extractor has not
been run -- and the row that names the source file names the command that fixes it.

The bindings the record carries with a status other than ``bound`` get their own group.
Those are the keys the documentation reserves so that Part 7 does not reassign one by
accident, and showing them next to the real binds, marked as planned, is what stops a
person looking for ``Super+H`` and concluding it is broken.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import paths
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "shortcuts"

RECORD = "keybinds.default.json"
DOCUMENT = "docs/SHORTCUTS.md"
SOURCE = ".config/hypr/keybind.lua"

#: A status the record gives a binding that is not ``bound``. Read out of the data
#: rather than assumed, so a status this page has not seen still gets a group.
BOUND = "bound"


# --------------------------------------------------------------------- readers


def record() -> Dict[str, Any]:
    """``data/keybinds.default.json``, parsed."""
    try:
        return json.loads(paths.data_file(RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bindings() -> List[Dict[str, Any]]:
    """Every binding the record carries, in the record's own order."""
    found = record().get("bindings")
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def bound_bindings() -> List[Dict[str, Any]]:
    """The bindings that are really bound in the session."""
    return [item for item in bindings() if str(item.get("status") or BOUND) == BOUND]


def planned_bindings() -> List[Dict[str, Any]]:
    """The bindings the record reserves but the session does not have yet."""
    return [item for item in bindings() if str(item.get("status") or BOUND) != BOUND]


def categories() -> List[str]:
    """The record's own categories, in the order they first appear.

    Ordered by first appearance rather than sorted, because the extractor writes them
    in the order the Lua file declares its sections and that order is the one the
    documentation prints -- so this page, the document and the source file all read the
    same way down.
    """
    found: List[str] = []
    for item in bound_bindings():
        category = str(item.get("category") or "Other")
        if category not in found:
            found.append(category)
    return found


def modifier_text() -> str:
    """What the record says the main modifier is, in words a person can find on a keyboard."""
    modifier = str(record().get("modifier") or "SUPER")
    return (f"{modifier} is the Super key -- the Windows key on most keyboards, Command "
            f"on an Apple one")


def action_text(item: Dict[str, Any]) -> str:
    """What a binding does, from the record's own action object."""
    action = item.get("action") or {}
    if not isinstance(action, dict):
        return str(action)
    kind = str(action.get("kind") or "")
    command = str(action.get("command") or "")
    lua = str(action.get("lua") or "")
    if command:
        return f"{kind}: runs {command}" if kind else f"runs {command}"
    if lua:
        return f"{kind}: {lua}" if kind else lua
    return kind or "no action recorded"


def _slug(text: str) -> str:
    """An identifier-safe version of a description, for a generated reader's name."""
    return "".join(character if character.isalnum() else "_"
                   for character in str(text).lower()).strip("_") or "binding"


def _keys_reader(item: Dict[str, Any]) -> Callable[[], str]:
    """Build the reader one binding's row shows: the keys it is bound to."""

    def read() -> str:
        return str(item.get("keys") or "")

    read.__doc__ = f"The keys for {item.get('description') or item.get('keys')!r}."
    return read


#: One reader per binding, by the index the record gives it. A state row reads
#: something rather than carrying a literal, which is the plan's rule and the right
#: one: a row whose value is baked into the plan is a row that cannot be re-read when
#: the record is regenerated while the window is open. The names are slugs of the
#: descriptions so a plan dump is readable, and :data:`READER_NAMES` is what the rows
#: resolve through, so a duplicated description cannot make two rows read one key.
READER_NAMES: Dict[int, str] = {}


def _register() -> None:
    used: set = set()
    for index, item in enumerate(bindings()):
        base = _slug(item.get("description") or item.get("keys") or index)
        name = f"keys_{base}"
        counter = 2
        while name in used:
            name = f"keys_{base}_{counter}"
            counter += 1
        used.add(name)
        READER_NAMES[index] = name
        reader = _keys_reader(item)
        reader.__name__ = name
        globals()[name] = reader


_register()


def reader_for(index: int) -> str:
    """The module attribute that reads one binding's keys."""
    return f"shortcuts.{READER_NAMES.get(index, 'keys_binding')}"


def binding_rows(category: str) -> List[Row]:
    """One row per bound binding in a category: the description, and the keys.

    The description is the row's title and the key combination is its value, because
    that is the order a person reads a shortcut table in -- what it does, then what to
    press -- and it is the order ``docs/SHORTCUTS.md`` prints.
    """
    rows: List[Row] = []
    for index, item in enumerate(bindings()):
        if str(item.get("status") or BOUND) != BOUND:
            continue
        if str(item.get("category") or "Other") != category:
            continue
        rows.append(Row(
            "state", str(item.get("description") or item.get("keys") or "An undescribed bind"),
            source=reader_for(index),
            icon="preferences-desktop-keyboard-shortcuts-symbolic",
            subtitle=action_text(item),
            keywords=tuple(part for part in (str(item.get("keys") or ""), category,
                                             str(item.get("description")),
                                             str((item.get("action") or {}).get("command")))
                           if part)))
    return rows


def nothing_reserved_text() -> str:
    """The sentence the reserved group shows when the record reserves nothing."""
    return f"all {len(bindings())} bindings the record carries are bound in the session"


def planned_rows() -> List[Row]:
    """The reserved keys, marked as what they are."""
    rows: List[Row] = []
    for index, item in enumerate(bindings()):
        if str(item.get("status") or BOUND) == BOUND:
            continue
        rows.append(Row(
            "state", str(item.get("description") or item.get("keys") or "A reserved key"),
            source=reader_for(index), icon="dialog-information-symbolic",
            subtitle=f"planned, not bound: {action_text(item)}",
            keywords=(str(item.get("keys") or ""), "planned", "reserved", "part 7",
                      str(item.get("description") or ""))))
    if not rows:
        rows.append(Row(
            "state", "Nothing reserved", source="shortcuts.nothing_reserved_text",
            icon="object-select-symbolic",
            subtitle="Every binding the record carries is bound in the session",
            keywords=("planned", "reserved", "none")))
    return rows


def category_groups() -> List[Group]:
    """One group per category, in the record's order."""
    groups: List[Group] = []
    for category in categories():
        rows = binding_rows(category)
        groups.append(Group(
            category,
            Row("expander", f"{len(rows)} shortcut{'s' if len(rows) != 1 else ''}",
                rows=tuple(rows), icon="preferences-desktop-keyboard-shortcuts-symbolic",
                subtitle=category, keywords=(category, "shortcuts", "keys", "binds")),
            style_classes=("iarch-glass-card",) if not groups else (),
        ))
    return groups


def count_text() -> str:
    """How many shortcuts the record carries, for the header."""
    found = bound_bindings()
    return (f"{len(found)} shortcut{'s' if len(found) != 1 else ''} in "
            f"{len(categories())} categories")


def source_text() -> str:
    """Where the table comes from, naming the commands that keep it true."""
    data = record()
    return (f"{data.get('source_file') or SOURCE}, extracted by "
            f"{data.get('generated_by') or 'tools/extract_keybinds.py --write'}")


def document_text() -> str:
    """The other rendering of the same data, and the command that checks it."""
    return (f"{DOCUMENT} is rendered from the same JSON by "
            f"tools/render_shortcuts.py, and --check says whether it is stale")


def stale_text() -> Optional[str]:
    """Whether the record and the Lua file disagree, if the extractor can be asked.

    A read that runs the tool rather than trusting the file's timestamp, because the
    question a person has on this page is whether the table in front of them is the
    table the session has. ``None`` means the check could not be run, which is a
    different answer from "it is current" and is drawn as such.
    """
    from ..services import runner  # noqa: PLC0415

    if runner.which("python3") is None:
        return None
    root = paths.repo_root()
    outcome = runner.run("python3", [str(root / "tools" / "extract_keybinds.py"), "--check"],
                         cwd=root, timeout=runner.DEFAULT_TIMEOUT)
    if outcome.verdict == runner.UNVERIFIED:
        return None
    if outcome.verdict == runner.OK:
        return "the record and the Lua file agree"
    return ("the record is stale: run python3 tools/extract_keybinds.py --write and then "
            "python3 tools/render_shortcuts.py --write")


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Shortcuts page, as data."""
    spec = registry_page(PAGE_ID)

    groups: List[Group] = [Group(
        "Every shortcut",
        Row("state", "What the table is", icon="preferences-desktop-keyboard-shortcuts-symbolic",
            source="shortcuts.count_text",
            subtitle="One source, three renderings: the Lua file the compositor reads, "
                     "the document a person reads, and this page",
            keywords=("shortcuts", "count", "categories", "table")),
        Row("state", "The modifier", icon="input-keyboard-symbolic",
            source="shortcuts.modifier_text",
            subtitle="Mouse bindings are listed with their button, and locked media "
                     "keys keep working while the screen is locked",
            keywords=("super", "modifier", "windows key", "command", "mouse", "locked")),
        description="Grouped the way the source file is, so this page and "
                    "docs/SHORTCUTS.md read the same way down.",
        style_classes=("iarch-glass-card",),
    )]
    groups.extend(category_groups())
    groups.append(Group(
        "Planned and reserved",
        Row("expander", "Keys that are not bound yet", rows=tuple(planned_rows()),
            icon="dialog-information-symbolic",
            subtitle="Reserved in the record so that the overlay behind Super+H does "
                     "not reassign one by accident when it arrives",
            keywords=("planned", "reserved", "super+h", "cheatsheet", "part 7")),
        description="The shortcut system -- the searchable glass overlay -- is Part 7. "
                    "Until then these keys are reserved and nothing opens them.",
    ))
    groups.append(Group(
        "Where this comes from",
        Row("state", "The source", icon="accessories-text-editor-symbolic",
            source="shortcuts.source_text",
            subtitle="Read out of the description fields the binds already carry; a "
                     "bind without a description is a bind this table cannot show",
            keywords=("keybind.lua", "extract_keybinds", "source", "descriptions")),
        Row("state", "The document", icon="document-save-symbolic",
            source="shortcuts.document_text",
            subtitle="If the document and the session disagree, the session is right "
                     "and the document is stale",
            keywords=("SHORTCUTS.md", "render_shortcuts", "check", "stale")),
        Row("state", "Is it current?", icon="view-refresh-symbolic",
            source="shortcuts.stale_text",
            subtitle="Asked of the extractor, not of a timestamp",
            keywords=("stale", "check", "extract", "current")),
        description="This page is read-only, and the reason is on the page: the binds "
                    "live in a Lua file the compositor reads at startup, and choosing a "
                    "key that is not already taken is the collision check Part 7's "
                    "single source of truth exists to make.",
    ))

    return PagePlan(
        PAGE_ID, spec.label, *groups,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("Nothing on this page can be changed here: it is the table the "
                   "shortcut overlay will be drawn from, and the overlay is Part 7.",
                   kind="info", icon="dialog-information-symbolic"),
        ),
        header_actions=(
            Row("state", "Shortcuts", icon="preferences-desktop-keyboard-shortcuts-symbolic",
                source="shortcuts.count_text", keywords=("shortcuts", "count")),
        ),
    )
