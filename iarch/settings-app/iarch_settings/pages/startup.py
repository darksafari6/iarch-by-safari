# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Startup & Default apps page: the two halves that write files other programs read.

Every other page in this application writes a file this project generated, or sends a verb
to a program that owns its own configuration. This one writes into two places other
programs have opinions about, and both halves are recorded before either is touched.

**Autostart.** ``data/design/autostart.json`` was read out of the generator a
systemd-started session actually runs rather than out of the desktop-entry specification,
because the specification says what a key means and the generator says what a session does
with it. The difference is the useful part: ``X-GNOME-Autostart-enabled`` is absent from the
key table entirely -- neither read nor recognised-and-ignored -- so a switch built on it
would sit on screen doing nothing while the entry kept starting. ``Hidden`` is the key that
actually turns an entry off, and it is what ``enabled: false`` writes.

Ownership is a file-name prefix: everything this project writes, changes or removes is
``iarch-*``. Every other file in the directory is *listed*, so the page can show what will
start, and none is touched, because a panel that can delete files it did not create is a
panel that can undo work it knows nothing about. One exception is recorded with its
evidence: an entry in a **system** directory is turned off by creating a same-named file in
the user's own directory, since the generator reads the user directory first and the first
name wins.

**Default applications.** ``data/design/xdg-defaults.json`` records that ``xdg-settings``
has exactly two properties and refuses anything else, that a write is refused outright when
no desktop environment was detected -- which is why the service calls ``xdg-mime`` directly
-- and that the file written is ``$XDG_DATA_HOME/applications/mimeapps.list``, not something
under ``~/.config``. A role is a set of mimetypes written in one call, so the browser role
cannot end up opening a page in one program and a link in another. Candidates come from the
application directories with glib's own rules behind each filter, because a list that
disagreed with the desktop's chooser would offer a program the rest of the desktop hides.

There is no association for a terminal emulator, so the record names that role under
``unsettable`` with the reason and the page shows the sentence: a dropdown with nothing
behind it is a control that lies.

One thing this page cannot do is add an autostart entry, and the reason is on the page
rather than hidden: an entry needs a name and a command at once, the list is validated as a
list, and a plan row carries one value. Editing the entries that exist is field by field;
adding one is a whole entry, which is what ``services.autostart.add()`` does and what a
dialog with two fields would do when this application has one.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..services import autostart, config_store, defaults, runner
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "startup"

SETTING = "startup.autostart"

#: The settings schema's own pattern for an entry name, which becomes the file's stem.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


# --------------------------------------------------------------------- readers


def entries() -> List[Dict[str, Any]]:
    """The autostart entries in the settings document."""
    try:
        document = config_store.document()
    except (config_store.ConfigStoreError, OSError):
        return []
    found = (document.get("startup") or {}).get("autostart")
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def entry_rows() -> List[Row]:
    """Four rows per entry that already exists: name, command, comment and the switch.

    Indexed rather than starred, because a change has to name the entry it writes. An entry
    that does not exist yet gets no rows at all -- see :func:`add_entry_text` -- since one
    field of a new entry is a half entry and the list is validated as a list.
    """
    found = entries()
    if not found:
        return [Row(
            "state", "No entry yet", icon="dialog-information-symbolic",
            source="startup.add_entry_text",
            subtitle="The directory listing below still shows everything the session would "
                     "consider, including entries other programs wrote",
            keywords=("autostart", "empty", "entries", "startup"))]
    rows: List[Row] = []
    for index, entry in enumerate(found):
        name = str(entry.get("name") or f"entry {index + 1}")
        rows.append(Row(
            "switch", f"{name} — start at login", setting=f"{SETTING}.{index}.enabled",
            icon="media-playback-start-symbolic",
            subtitle="False writes the entry with Hidden=true rather than deleting it, so "
                     "turning it back on does not need the command retyped",
            keywords=(name, "autostart", "enabled", "hidden", "login", "startup")))
        rows.append(Row(
            "entry", f"{name} — command", setting=f"{SETTING}.{index}.command",
            icon="utilities-terminal-symbolic", validator="startup.command_is_valid",
            subtitle="Written verbatim into Exec= and never executed by this application, so "
                     "it is not passed through a shell here; the session parses it the way it "
                     "parses any autostart entry",
            keywords=(name, "command", "exec", "program", "autostart")))
        rows.append(Row(
            "entry", f"{name} — file name", setting=f"{SETTING}.{index}.name",
            icon="document-save-symbolic", validator="startup.name_is_valid",
            subtitle="Becomes the file's stem, so it is restricted to characters that are "
                     "safe in a file name on every filesystem this project supports",
            keywords=(name, "file name", "stem", "autostart", "desktop")))
        rows.append(Row(
            "entry", f"{name} — comment", setting=f"{SETTING}.{index}.comment",
            icon="accessories-text-editor-symbolic",
            subtitle="Recognised and deliberately ignored by the generator, and written "
                     "anyway because it is the sentence a person reads when they open the file",
            keywords=(name, "comment", "autostart", "note")))
    return rows


def directory_summary() -> str:
    """Every file the session would consider, as one multi-line answer.

    One row rather than one per file, and the reason is the model's: a state row reads
    through a zero-argument source, so a row per entry would need a reader per entry, and
    the entries are read off a filesystem at draw time rather than known when this module is
    imported. A summary that names every file is honest about all of them; fifty rows that
    each showed the same directory sentence would not be.
    """
    found = autostart.entries()
    if not found:
        return "nothing in your autostart directory or in a system one"
    lines: List[str] = []
    for entry in found:
        where = "system" if entry.system else "yours"
        bits = [f"{entry.label or entry.name or entry.path.name} — {entry.path.name} ({where})"]
        bits.append("this project's" if entry.owned else "listed and left alone")
        if entry.masked_by is not None:
            bits.append(f"masked by {entry.masked_by.name}")
        if entry.notes:
            bits.append(entry.notes[0])
        lines.append("; ".join(bits))
    return "\n".join(lines)


def directory_text() -> str:
    """Where the entries live, and the rule about touching them."""
    return (f"{autostart.directory()}, and the system directories the generator reads after "
            f"it; only a file named {autostart.ownership_prefix()}* is ever written, changed "
            f"or removed")


def add_entry_text() -> str:
    """Why this page edits entries and does not add them."""
    return ("an entry needs a name and a command at once, and a row carries one value: the "
            "list is validated as a list, so one field of a new entry is a half entry that "
            "would be refused. The entries above are edited field by field; adding one is a "
            "whole entry, which services.autostart.add() does and which a two-field dialog "
            "would do when this application has one")


def key_counts_text() -> str:
    """How the record splits the desktop-entry keys this session's generator knows."""
    return (f"{len(autostart.writable_keys())} keys are written, "
            f"{len(autostart.read_keys())} are read by the generator, and "
            f"{len(autostart.ignored_keys())} are recognised and deliberately ignored")


def refusal_rows() -> List[Row]:
    """One row per spelling the record refuses, carrying the record's own message."""
    rows: List[Row] = []
    for refusal_id, refusal in sorted(autostart.refusals().items()):
        rows.append(Row(
            "state", str(refusal.get("spelling") or refusal_id),
            source=f"startup.refusal_{_slug(refusal_id)}",
            icon="dialog-warning-symbolic",
            subtitle=str(refusal.get("why") or ""),
            keywords=(refusal_id, str(refusal.get("spelling") or ""), "refused",
                      "autostart", "hidden")))
    return rows


def _slug(text: str) -> str:
    """An identifier-safe version of a refusal id, for a generated reader's name."""
    return "".join(character if character.isalnum() else "_"
                   for character in str(text).lower()).strip("_") or "refusal"


def _refusal_reader(refusal_id: str) -> Callable[[], str]:
    """Build the reader one refusal row shows: the sentence a person should read."""

    def read() -> str:
        return str(autostart.refusals().get(refusal_id, {}).get("message") or "")

    read.__name__ = f"refusal_{_slug(refusal_id)}"
    read.__doc__ = f"What the record says about ``{refusal_id}``, for a person."""
    return read


for _refusal_id in autostart.refusals():
    globals()[f"refusal_{_slug(_refusal_id)}"] = _refusal_reader(_refusal_id)
del _refusal_id


def activation_text() -> str:
    """Whether the session's autostart mechanism ran, in the probe's own three-way verdict."""
    state = autostart.activation()
    verdict = state.get("verdict")
    units = state.get("units") or []
    if verdict == runner.UNVERIFIED:
        return (f"unverified: {state.get('reason') or 'nothing could be asked'}. That is not "
                f"a failure and not a pass -- 'no units were found' would be a different "
                f"answer and would lead to opposite advice about an entry that did not start")
    if verdict == runner.OK:
        if not units:
            return ("the generator was asked and made no units, so nothing in the autostart "
                    "directories ran this session")
        return f"{len(units)} unit{'s' if len(units) != 1 else ''}: " + ", ".join(units)
    return f"the probe failed: {state.get('reason') or 'no reason given'}"


def activation_probe_text() -> str:
    """The command the probe runs, so the row is not a verdict from nowhere."""
    return " ".join(autostart.activation_probe())


def role_rows() -> List[Row]:
    """One row per default-application role: a dropdown, or the reason there is none.

    A dropdown only when there is something to choose and a write can be read back
    afterwards. ``xdg-mime`` exits 0 whether or not anything will honour the association, so
    the verdict is the read-back's -- and when neither tool is installed there is no
    read-back, which is unverified rather than a failure and is drawn as a sentence rather
    than as an empty control that looks like "nothing is installed".
    """
    rows: List[Row] = []
    for role_id in defaults.role_ids():
        state = defaults.state(role_id)
        label = str(state.get("label") or role_id)
        candidates = state.get("candidates") or []
        mimetypes = state.get("mimetypes") or []
        if state.get("writable") and candidates:
            rows.append(Row(
                "combo", label, action=f"startup.set_{role_id}_default",
                source=f"startup.current_{role_id}_default",
                choices=[(str(item.desktop_id),
                          str(item.values.get("Name") or item.desktop_id))
                         for item in candidates],
                icon="preferences-desktop-apps-symbolic",
                subtitle=f"one call writes {', '.join(str(item) for item in mimetypes)}, so "
                         f"a page cannot open in one program and a link in another",
                keywords=(role_id, label, "default", "mime", "association",
                          *(str(item) for item in mimetypes))))
            continue
        reason = _role_reason(state)
        rows.append(Row(
            "state", label, source=f"startup.current_{role_id}_default",
            icon="dialog-warning-symbolic", subtitle=reason,
            keywords=(role_id, label, "default", "unset", "unverified")))
    return rows


def _role_reason(state: Dict[str, Any]) -> str:
    """Why a role has no dropdown: no tool, no candidate, or no read-back."""
    current = state.get("current") or {}
    tools = state.get("tools") or {}
    if not any(tools.values()):
        missing = ", ".join(name for name, present in tools.items() if not present)
        return (f"{missing} is not installed, so nothing could be read and no write could be "
                f"verified afterwards: a missing binary is unverified rather than a failure")
    if not (state.get("candidates") or []):
        return ("no program in the application directories passed the desktop's own filters, "
                "so there is nothing to offer -- a dropdown with nothing behind it is a "
                "control that lies")
    return str(current.get("reason") or "this role cannot be written from here")


def unsettable_rows() -> List[Row]:
    """The roles the record explains instead of offering."""
    rows: List[Row] = []
    for index, item in enumerate(defaults.unsettable()):
        rows.append(Row(
            "state", str(item.get("label") or item.get("role") or "A role not offered"),
            source=f"startup.unsettable_{index}", icon="dialog-information-symbolic",
            subtitle="Recorded under `unsettable` in data/design/xdg-defaults.json",
            keywords=(str(item.get("role") or ""), str(item.get("label") or ""), "unsettable",
                      "default", "mime")))
    return rows


def _unsettable_reader(index: int) -> Callable[[], str]:
    def read() -> str:
        found = defaults.unsettable()
        return str(found[index].get("why") or "") if index < len(found) else ""

    read.__name__ = f"unsettable_{index}"
    read.__doc__ = f"Why the role at position {index} is explained instead of offered."
    return read


for _index in range(len(defaults.unsettable())):
    globals()[f"unsettable_{_index}"] = _unsettable_reader(_index)
del _index


def _role_reader(role_id: str) -> Callable[[], Optional[str]]:
    """Build the reader one role's row shows: what handles it right now."""

    def read() -> Optional[str]:
        state = defaults.state(role_id)
        current = state.get("current") or {}
        desktop_id = current.get("desktop_id")
        if desktop_id:
            return str(desktop_id)
        if current.get("verdict") == runner.UNVERIFIED:
            return None
        return "nothing is set" if current.get("verdict") == runner.OK else None

    read.__name__ = f"current_{role_id}_default"
    read.__doc__ = f"What handles the {role_id} role right now, or ``None`` if unknown."
    return read


def _role_setter(role_id: str) -> Callable[[Any], Dict[str, Any]]:
    """Build the writer one role's dropdown uses."""

    def write(value: Any) -> Dict[str, Any]:
        return defaults.set_role(role_id, str(value))

    write.__name__ = f"set_{role_id}_default"
    write.__doc__ = f"Make a program the default for the {role_id} role, and read it back."
    return write


for _role_id in defaults.role_ids():
    globals()[f"current_{_role_id}_default"] = _role_reader(_role_id)
    globals()[f"set_{_role_id}_default"] = _role_setter(_role_id)
del _role_id


def mimeapps_text() -> str:
    """Which file a default-application write lands in, and which command is not a write."""
    return ("a write goes to $XDG_DATA_HOME/applications/mimeapps.list, not to something "
            "under ~/.config, and `xdg-settings set` is not a write path at all: its generic "
            "dispatch refuses any operation but get and check")


def tools_text() -> str:
    """Whether the two xdg-utils tools are installed."""
    present = defaults.tools_present()
    return "; ".join(f"{name}: {'installed' if found else 'not installed'}"
                     for name, found in sorted(present.items()))


def entry_count_text() -> str:
    """How many entries the settings document holds, for the header."""
    found = entries()
    if not found:
        return "no autostart entry in settings.json"
    return (f"{len(found)} entr{'y' if len(found) == 1 else 'ies'}: "
            + ", ".join(str(item.get("name") or "?") for item in found))


# ------------------------------------------------------------------ validators


def name_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether an entry name can become a file name."""
    text = str(value or "").strip()
    if not text:
        return False, "an entry needs a name: it becomes the file's stem"
    if not NAME_PATTERN.match(text):
        return False, ("a name starts with a letter or a digit and holds at most 64 letters, "
                       "digits, dots, underscores and dashes, because it becomes a file name")
    return True, ""


def command_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether a command is one the session could run, per the record's Exec rules."""
    text = str(value or "").strip()
    if not text:
        return False, "an entry with no Exec is skipped with a warning rather than run"
    problems = autostart.check_command_text(text)
    if problems:
        return False, "; ".join(problems)
    return True, ""


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Startup & Default apps page, as data."""
    spec = registry_page(PAGE_ID)

    entries_group = Group(
        "What starts at login",
        Row("expander", "Your entries", rows_source="startup.entry_rows",
            icon="media-playback-start-symbolic",
            subtitle="Projected into ~/.config/autostart/ as one .desktop file per entry, "
                     "each named iarch-*",
            keywords=("autostart", "entries", "login", "startup", "desktop")),
        Row("state", "Adding an entry", icon="dialog-warning-symbolic",
            source="startup.add_entry_text",
            subtitle="The one thing this page cannot do, and the reason is a sentence rather "
                     "than a missing button",
            keywords=("add", "new entry", "dialog", "autostart")),
        Row("state", "Everything the session would consider",
            source="startup.directory_summary", icon="folder-open-symbolic",
            subtitle="Your directory and the system ones, in the generator's order, with the "
                     "file that masks a duplicate named",
            keywords=("autostart", "directory", "system", "masked", "entries", "files")),
        Row("state", "Where they live", icon="folder-open-symbolic",
            source="startup.directory_text", keywords=("directory", "ownership", "prefix")),
        Row("state", "The keys the record splits", icon="accessories-text-editor-symbolic",
            source="startup.key_counts_text",
            subtitle="Read out of the generator a systemd-started session runs, not out of "
                     "the desktop-entry specification",
            keywords=("keys", "hidden", "exec", "record", "generator")),
        description="An entry is switched off with Hidden=true, which is the key this session "
                    "reads, and never with a spelling the generator does not know.",
        style_classes=("iarch-glass-card",),
    )

    refused = Group(
        "Recorded, and refused",
        Row("expander", "Spellings this project will not write",
            rows=tuple(refusal_rows()), icon="dialog-warning-symbolic",
            subtitle="Each one looks like a switch and would change nothing",
            keywords=("refused", "x-gnome-autostart-enabled", "hidden", "autostart")),
        Row("state", "Whether the entries ran", icon="view-refresh-symbolic",
            source="startup.activation_text",
            subtitle="A read-only probe, with the runner's three-way verdict",
            keywords=("activation", "systemd", "units", "probe", "unverified")),
        Row("state", "The probe it runs", icon="utilities-terminal-symbolic",
            source="startup.activation_probe_text",
            subtitle="So the verdict above is not a sentence from nowhere",
            keywords=("systemctl", "probe", "argv", "autostart")),
        description="Whether an entry actually runs is not a property of the file, so the "
                    "record names a probe and this page reports the probe's verdict without "
                    "dressing it up.",
    )

    apps = Group(
        "Default applications",
        Row("expander", "One row per role", rows_source="startup.role_rows",
            icon="preferences-desktop-apps-symbolic",
            subtitle="A dropdown where there is something to choose and a write can be read "
                     "back, and a sentence where there is not",
            keywords=("default", "applications", "browser", "file manager", "editor", "mail",
                      "mime")),
        Row("expander", "Roles explained instead of offered", rows=tuple(unsettable_rows()),
            icon="dialog-information-symbolic",
            subtitle="A role with no standard association is a row that says so, not a "
                     "dropdown with nothing behind it",
            keywords=("unsettable", "terminal", "role", "default")),
        Row("state", "Where a write lands", icon="document-save-symbolic",
            source="startup.mimeapps_text",
            subtitle="The verdict is the read-back's, because xdg-mime exits 0 whether or not "
                     "anything will honour the association",
            keywords=("mimeapps.list", "xdg-mime", "xdg-settings", "write", "read back")),
        Row("state", "The two tools", icon="utilities-terminal-symbolic",
            source="startup.tools_text",
            subtitle="Neither installer in this repository adds xdg-utils to its package "
                     "list, so their absence is a state this page expects",
            keywords=("xdg-mime", "xdg-settings", "installed", "tools")),
        description="A role is a set of mimetypes written in one call, and the candidates are "
                    "the programs the desktop's own rules would show.",
    )

    return PagePlan(
        PAGE_ID, spec.label, entries_group, refused, apps,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("A startup command's failure is silent by construction: the generator runs "
                   "each entry as a service unit and nothing reports back to this window, "
                   "which is what SECURITY.md says about the same file.",
                   kind="warning", icon="dialog-warning-symbolic"),
            Banner("Only a file named iarch-* is ever written, changed or removed. Everything "
                   "else in the autostart directories is listed so you can see what will "
                   "start, and left alone.",
                   kind="info", icon="folder-open-symbolic"),
        ),
        header_actions=(
            Row("state", "Startup entries", icon="media-playback-start-symbolic",
                source="startup.entry_count_text", keywords=("autostart", "entries")),
        ),
    )
