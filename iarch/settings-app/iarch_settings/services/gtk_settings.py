# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""``settings.ini``: the file GTK itself reads, written from a record of its keys.

Fonts, the icon theme, the cursor theme and the light/dark preference are not
this project's state -- they are GTK's. ``GtkSettings`` reads one ``[Settings]``
INI section out of ``~/.config/gtk-4.0/settings.ini`` (and GTK 3 applications read
the file of the same name beside them), so that is where a font choice has to go,
and a font choice written anywhere else is a font choice nothing reads.

Three rules follow from the file being somebody else's format:

* **Only keys ``data/design/gtk-settings.json`` records are written**, and only
  the ones it marks writable. That record was read out of ``gtk/gtksettings.c`` at
  a pinned ref, key by key, with the line each value domain came from. Two keys it
  records are refused on purpose: ``gtk-theme-name``, which ``iarch-theme`` owns,
  and ``gtk-enable-animations``, which is the one mechanism reduce motion already
  uses -- writing it from here too would give one intention two switches that can
  disagree.
* **Everything else in the file is preserved.** It is user-owned: it carries no
  GENERATED header, it is not rendered from tokens, and a person may have set a key
  this project has no opinion about. The writer replaces the values of the keys it
  manages and leaves every other line -- including comments and other sections --
  exactly as it found them.
* **A value that is not offered is not writable.** ``gtk-xft-hintstyle`` and
  ``gtk-xft-rgba`` are compared with ``strcmp`` against a closed list and an
  unrecognised spelling is *silently ignored* rather than refused, so the page
  offers a dropdown and this module refuses a value outside the recorded list
  instead of writing something that quietly does nothing.

Writing to the GTK 3 file is limited to the five keys the record lists under
``gtk3_keys``. GTK 3's own property table was not read at a pinned ref -- that is
docs/UNVERIFIED.md SET-05 -- so the evidence for those five is this repository's
own frozen payload, which has written them since before Part 1. A key GTK 4 added
later is not written there, because a key nothing reads is worse than no key.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import paths

SECTION = "Settings"
"""The one INI section GtkSettings reads."""

FILE_NAME = "settings.ini"
GTK4_DIR = "gtk-4.0"
GTK3_DIR = "gtk-3.0"

#: settings.json's fonts section, mapped to the GtkSettings key it projects into.
#: A key is only written when its value is not empty and not zero, so a font the
#: user never chose is not pinned -- pinning one would stop the session's own font
#: change from reaching GTK applications.
FONTS_TO_KEYS = {
    "font_name": "gtk-font-name",
    "antialias": "gtk-xft-antialias",
    "hinting": "gtk-xft-hinting",
    "hint_style": "gtk-xft-hintstyle",
    "subpixel": "gtk-xft-rgba",
    "icon_theme": "gtk-icon-theme-name",
    "cursor_theme": "gtk-cursor-theme-name",
    "cursor_size": "gtk-cursor-theme-size",
}

DARK_KEY = "gtk-application-prefer-dark-theme"


class GtkSettingsError(RuntimeError):
    """A key or a value the record does not allow."""


# ------------------------------------------------------------------ the record


def record(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/design/gtk-settings.json``, parsed."""
    try:
        return json.loads(paths.design_file("gtk-settings.json", root)
                          .read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GtkSettingsError(f"the GtkSettings record cannot be read: {exc}") from exc


def key_table(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    return record(root)["keys"]


def writable_keys(root: Optional[Path] = None) -> List[str]:
    """The recorded keys this project may write, in the record's own order."""
    return [name for name, entry in key_table(root).items()
            if entry.get("written_by_this_project") is not False]


def refused_keys(root: Optional[Path] = None) -> Dict[str, str]:
    """The recorded keys this project refuses to write, with the reason for each."""
    return {name: str(entry.get("note", ""))
            for name, entry in key_table(root).items()
            if entry.get("written_by_this_project") is False}


def gtk3_keys(root: Optional[Path] = None) -> List[str]:
    """The subset also written to the GTK 3 file."""
    return [entry["key"] for entry in record(root)["gtk3_keys"]["keys"]]


def accepted_values(key: str, root: Optional[Path] = None) -> Optional[List[str]]:
    """The closed choice list a key's value must come from, or ``None`` if it is open.

    ``values`` in the record is a choice list -- the spellings a string property is
    compared against with strcmp, or the discrete integers an int property accepts.
    A key whose spec declares bounds instead carries ``range``, which
    :func:`key_range` reads; the two are mutually exclusive in the schema, because
    a record that said both would not know which it meant.
    """
    entry = key_table(root).get(key) or {}
    values = entry.get("values")
    return [str(value) for value in values] if values else None


def key_range(key: str, root: Optional[Path] = None) -> Optional[Tuple[int, int]]:
    """An int key's inclusive ``(minimum, maximum)``, or ``None``."""
    bounds = (key_table(root).get(key) or {}).get("range")
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        return int(bounds[0]), int(bounds[1])
    return None


def key_type(key: str, root: Optional[Path] = None) -> str:
    return str((key_table(root).get(key) or {}).get("type", "string"))


# ------------------------------------------------------------------ values


def check_values(values: Mapping[str, Any], root: Optional[Path] = None) -> List[str]:
    """Every way ``values`` disagrees with the record."""
    table = key_table(root)
    writable = set(writable_keys(root))
    problems: List[str] = []
    for key, value in values.items():
        if key not in table:
            problems.append(f"{key} is not in data/design/gtk-settings.json, so it is not "
                            "written: GtkSettings ignores a property it does not declare")
            continue
        if key not in writable:
            problems.append(f"{key} is recorded and refused: "
                            f"{refused_keys(root).get(key, 'see the record')}")
            continue
        kind = key_type(key, root)
        accepted = accepted_values(key, root)
        if accepted is not None and str(value) not in accepted:
            problems.append(f"{key}={value!r} is not one of {', '.join(accepted)}, which "
                            "GtkSettings would ignore silently rather than refuse")
            continue
        bounds = key_range(key, root)
        if kind == "int":
            try:
                number = int(str(value))
            except (TypeError, ValueError):
                problems.append(f"{key}={value!r} is not an integer")
                continue
            if bounds is not None and not bounds[0] <= number <= bounds[1]:
                problems.append(f"{key}={number} is outside {bounds[0]}..{bounds[1]}, the "
                                "range the property spec declares")
        elif kind == "bool":
            if str(value) not in ("0", "1", "true", "false", "True", "False"):
                problems.append(f"{key}={value!r} is not a boolean GtkSettings reads")
    return problems


def bool_value(value: Any) -> str:
    """A boolean as the ``1``/``0`` GtkSettings reads."""
    if isinstance(value, str):
        return "1" if value.strip().lower() in ("1", "true", "yes") else "0"
    return "1" if value else "0"


#: Which ``fonts.*`` setting becomes which GtkSettings key. Written down as a table
#: rather than left implicit in :func:`values_from_settings` because three callers
#: need it and only one of them is the projection: the Fonts page needs it to say
#: what a row writes, :mod:`iarch_settings.services.control` needs it to check one
#: value before building a change, and a test needs it to assert that every key in
#: the table is one ``data/design/gtk-settings.json`` says is writable.
#:
#: ``ui_family`` and ``size_pt`` are both absent on purpose: they are the two halves
#: of the single ``gtk-font-name`` string, so neither maps to a key on its own and
#: :func:`values_from_settings` builds the pair.
KEY_BY_SETTING: Dict[str, str] = {
    "antialias": "gtk-xft-antialias",
    "hinting": "gtk-xft-hinting",
    "hint_style": "gtk-xft-hintstyle",
    "subpixel": "gtk-xft-rgba",
    "icon_theme": "gtk-icon-theme-name",
    "cursor_theme": "gtk-cursor-theme-name",
    "cursor_size": "gtk-cursor-theme-size",
}

#: The two halves of ``gtk-font-name``, which is one string of the form "Family Size".
FONT_NAME_SETTINGS = ("ui_family", "size_pt")


def key_for_setting(setting: str) -> str:
    """The GtkSettings key a ``fonts.*`` setting becomes, or ``""``.

    ``""`` is the answer for ``ui_family`` and ``size_pt``, and for anything that is
    not a fonts setting at all: the caller then knows there is no single key to check
    a value against, which is not the same as knowing the value is fine.
    """
    return KEY_BY_SETTING.get(str(setting).rpartition(".")[2], "")


def values_from_settings(fonts: Mapping[str, Any],
                         colour_mode: str = "dark",
                         root: Optional[Path] = None) -> Dict[str, str]:
    """Project settings.json's ``fonts`` section into GtkSettings keys.

    An empty string or a zero means "do not write this key", which leaves the
    system default in place. ``font_name`` is built from the family and the point
    size when both are given, because ``gtk-font-name`` is one string of the form
    ``Family Size``; a family alone is written without a size, which GTK accepts
    and resolves with its own default.

    ``colour_mode`` becomes ``gtk-application-prefer-dark-theme`` for ``dark`` and
    ``light`` and is not written at all for ``auto``, because that key has no third
    value: following the system is what not writing it means.
    """
    values: Dict[str, str] = {}
    family = str(fonts.get("ui_family") or "").strip()
    size = fonts.get("size_pt") or 0
    if family:
        try:
            size_value = float(size)
        except (TypeError, ValueError):
            size_value = 0.0
        if size_value > 0:
            rendered = f"{size_value:g}"
            values["gtk-font-name"] = f"{family} {rendered}"
        else:
            values["gtk-font-name"] = family

    if "antialias" in fonts:
        values["gtk-xft-antialias"] = bool_value(fonts["antialias"])
    if "hinting" in fonts:
        values["gtk-xft-hinting"] = bool_value(fonts["hinting"])
    if str(fonts.get("hint_style") or ""):
        values["gtk-xft-hintstyle"] = str(fonts["hint_style"])
    if str(fonts.get("subpixel") or ""):
        values["gtk-xft-rgba"] = str(fonts["subpixel"])
    if str(fonts.get("icon_theme") or ""):
        values["gtk-icon-theme-name"] = str(fonts["icon_theme"])
    if str(fonts.get("cursor_theme") or ""):
        values["gtk-cursor-theme-name"] = str(fonts["cursor_theme"])
    cursor_size = fonts.get("cursor_size") or 0
    try:
        if int(cursor_size) > 0:
            values["gtk-cursor-theme-size"] = str(int(cursor_size))
    except (TypeError, ValueError):
        pass

    if colour_mode in ("dark", "light"):
        values[DARK_KEY] = "1" if colour_mode == "dark" else "0"

    problems = check_values(values, root)
    if problems:
        raise GtkSettingsError("; ".join(problems))
    return values


def gtk3_subset(values: Mapping[str, str], root: Optional[Path] = None) -> Dict[str, str]:
    """The GTK 3 half of a value set."""
    allowed = set(gtk3_keys(root))
    return {key: value for key, value in values.items() if key in allowed}


# ------------------------------------------------------------------ the file


def target_paths(config_home: Optional[Path] = None) -> Dict[str, Path]:
    """``{"gtk4": ..., "gtk3": ...}`` under ``config_home`` (default ``~/.config``).

    ``config_home`` and not ``~/.config/iarch``: this is GTK's own file, in GTK's
    own directory, and a copy under this project's directory would be read by
    nothing.
    """
    home = config_home or (Path.home() / ".config")
    return {"gtk4": home / GTK4_DIR / FILE_NAME, "gtk3": home / GTK3_DIR / FILE_NAME}


def parse(text: str) -> Tuple[List[str], Dict[str, int], Optional[int]]:
    """An INI file as ``(lines, key -> line index, index of the [Settings] line)``.

    Parsing to line indexes rather than to a dictionary is what makes preservation
    possible: a comment, a blank line, a key in another section and a key this
    project has no opinion about all survive because their lines are never touched.
    """
    lines = text.splitlines()
    indexes: Dict[str, int] = {}
    section_at: Optional[int] = None
    in_section = False
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip()
            if section_at is None and name == SECTION:
                section_at = number
            in_section = name == SECTION
            continue
        if not in_section or not stripped or stripped.startswith(("#", ";")):
            continue
        if "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key and key not in indexes:
            indexes[key] = number
    return lines, indexes, section_at


def render(existing: str, values: Mapping[str, str]) -> str:
    """``existing`` with ``values`` written into its ``[Settings]`` section.

    A managed key that is already in the file keeps its line and its position; one
    that is not is appended to the end of that section. Nothing else moves.
    """
    lines, indexes, section_at = parse(existing)
    if not lines:
        lines = [f"[{SECTION}]"]
        section_at = 0
        indexes = {}
    if section_at is None:
        # A file with no [Settings] section is not a GtkSettings file, but it might
        # be somebody's; the section is added at the top rather than the keys being
        # written into whatever section happened to be there.
        lines = [f"[{SECTION}]", *lines]
        section_at = 0
        indexes = {key: number + 1 for key, number in indexes.items()}

    pending: List[str] = []
    for key, value in values.items():
        if key in indexes:
            number = indexes[key]
            lines[number] = f"{key}={value}"
        else:
            pending.append(f"{key}={value}")

    if pending:
        insert_at = _section_end(lines, section_at)
        lines[insert_at:insert_at] = pending
    return "\n".join(lines) + "\n"


def _section_end(lines: Sequence[str], section_at: int) -> int:
    """The index just past the last line of the section starting at ``section_at``."""
    for number in range(section_at + 1, len(lines)):
        stripped = lines[number].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return number
    return len(lines)


def read(config_home: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """What both files currently say, for the keys this project manages.

    A file that does not exist contributes nothing, which is the state of a fresh
    install and is not an error.
    """
    found: Dict[str, Dict[str, str]] = {"gtk4": {}, "gtk3": {}}
    managed = set(writable_keys()) | set(refused_keys())
    for name, path in target_paths(config_home).items():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _lines, indexes, _section = parse(text)
        current = text.splitlines()
        for key, number in indexes.items():
            if key not in managed:
                continue
            line = current[number]
            found[name][key] = line.split("=", 1)[1].strip()
    return found


def write(values: Mapping[str, str], config_home: Optional[Path] = None,
          env: Optional[Mapping[str, str]] = None) -> List[Path]:
    """Write both files, backing each one up first. Returns what was written.

    The GTK 3 file gets the recorded subset only. Both writes go through
    :func:`iarch.lib.configstore.atomic_write` -- a temp file in the destination
    directory, an fsync, a rename, the previous mode carried over -- and neither
    gets a GENERATED header, because this is a user-owned file holding the user's
    choices rather than a preset's output.
    """
    problems = check_values(values)
    if problems:
        raise GtkSettingsError("; ".join(problems))
    paths.add_repo_to_path()
    from iarch.lib import configstore  # noqa: PLC0415

    written: List[Path] = []
    payloads = {"gtk4": dict(values), "gtk3": gtk3_subset(values)}
    for name, path in target_paths(config_home).items():
        payload = payloads[name]
        if not payload:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if path.is_file():
            existing = path.read_text(encoding="utf-8", errors="replace")
            configstore.backup_of(path, env)
        configstore.atomic_write(path, render(existing, payload))
        written.append(path)
    return written


def diff(config_home: Optional[Path] = None,
         values: Optional[Mapping[str, str]] = None) -> Dict[str, List[Tuple[str, str, str]]]:
    """What would change, as ``key -> (current, wanted)`` triples per file.

    A page shows this before applying, and the apply pipeline can compare it
    afterwards: a change that reports nothing to do is a change that should not be
    offered as one.
    """
    wanted = values if values is not None else {}
    current = read(config_home)
    payloads = {"gtk4": dict(wanted), "gtk3": gtk3_subset(wanted)}
    changes: Dict[str, List[Tuple[str, str, str]]] = {}
    for name, payload in payloads.items():
        rows = []
        for key, value in sorted(payload.items()):
            before = current.get(name, {}).get(key, "")
            if before != value:
                rows.append((key, before, value))
        changes[name] = rows
    return changes


def available(config_home: Optional[Path] = None) -> str:
    """A one-line description of the state of both files, for a status row."""
    found = target_paths(config_home)
    present = [name for name, path in found.items() if path.is_file()]
    if not present:
        return (f"neither {found['gtk4']} nor {found['gtk3']} exists yet, so GTK is using "
                "its own defaults and the first change creates them")
    return f"{', '.join(str(found[name]) for name in present)} exist and will be updated"
