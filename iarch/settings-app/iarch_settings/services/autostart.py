# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Startup entries: what this session will start at login, and who owns each file.

Every rule in here is read out of ``data/design/autostart.json``, which was read
out of the autostart generator a systemd-started session actually runs (systemd
v257.1, ``src/xdg-autostart-generator/``). Three consequences of that record
shape this module:

* **``Hidden=true`` is the off switch, and it is the only one.** The key a panel
  would reach for, ``X-GNOME-Autostart-enabled``, is not in the generator's key
  table at all -- neither read nor recognised-and-ignored -- so writing it would
  put a switch on screen that does nothing while the entry kept starting. The
  record's ``rejected`` list says this, and :func:`set_enabled` writes ``Hidden``.
* **A file this project does not own is listed and never touched.** Everything it
  writes, changes or removes is named ``iarch-*``, the ownership marker in the
  record. The one exception is also in the record: to turn off an entry that lives
  in a *system* directory, a same-named file is created in the user's directory,
  because the generator reads that directory first and the first name wins. No
  file outside the user's own directory is ever opened for writing.
* **An entry whose program cannot be found is refused, not written.** The
  generator resolves the first word of ``Exec`` with ``find_executable`` and
  generates no unit when nothing is found, so writing it would put a row on screen
  saying "starts at login" about a program that never will.

Reading is tolerant and writing is strict, in that order, because this directory
holds files other programs wrote: this module has to be able to describe them
without being able to break them.
"""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import paths
from . import runner

RECORD_NAME = "autostart.json"
"""``data/design/autostart.json`` -- the record every rule below comes from."""

SECTION = "Desktop Entry"
"""The one section the generator reads (record: ``parsing.sections``)."""

SUFFIX = ".desktop"
AUTOSTART_DIR = "autostart"
DEFAULT_XDG_CONFIG_DIRS = "/etc/xdg"

#: The keys a file this project writes contains, in the order they are written.
#: ``Comment`` comes first because it is the sentence a person reads when they open
#: the file; the rest follow the record's own key order. Each one is a key the
#: record marks ``written_by_this_project``, and :func:`check_values` refuses any
#: other.
RENDER_ORDER = ("Comment", "Name", "Type", "Exec", "Hidden")

#: The XDG field codes the generator removes from an argument list before it writes
#: the unit (record: ``exec_line.field_codes``, xdg-autostart-service.c:418-445).
#: An entry cannot be handed a file or a URL, so a command containing one of these
#: would run with the argument missing.
FIELD_CODES = ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%i", "%c", "%k",
               "%v", "%m")

#: The six escapes the file parser accepts (record: ``exec_line.quoting``,
#: xdg-autostart-service.c:94-144). Any other escape is a hard error that fails the
#: parse of the whole file, which the generator then treats as hidden *and* as
#: masking a system entry of the same name -- so the writer never emits one, and
#: refuses the characters that would need it.
ESCAPES = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\", ";": ";"}

#: Characters that survive into a unit name unchanged (record:
#: ``activation.escaping``, src/basic/unit-name.c:24-27). ``-`` and ``\\`` are in
#: this set and are escaped anyway, because do_escape tests for them first.
UNIT_VALID_CHARS = ("0123456789"
                    + "".join(chr(code) for code in range(65, 91))
                    + "".join(chr(code) for code in range(97, 123))
                    + ":-_.\\")

#: The spellings systemd's boolean parser accepts, case-insensitively (record:
#: ``parsing.booleans``, src/basic/parse-util.c). Anything else is reported and then
#: left at its default, which for both boolean keys is false.
TRUE_SPELLINGS = ("1", "yes", "y", "true", "t", "on")
FALSE_SPELLINGS = ("0", "no", "n", "false", "f", "off")

#: Shells whose ``-c`` form the record rejects (``rejected`` id ``shell-wrapper``):
#: wrapping a command in one turns the generator's check on the program into a check
#: on the shell, and puts a string from a user-editable file one step closer to being
#: parsed as a command.
SHELLS = ("sh", "bash", "dash", "zsh", "ksh", "fish", "csh", "tcsh")

#: Characters an argument may contain without being quoted in an Exec line.
EXEC_SAFE_CHARS = "_./:@%+=,-"

MAX_NAME_LENGTH = 200

#: What ``systemctl --user`` prints when there is no user manager to ask. Matched as
#: a substring rather than as an exit code, because the exit code is 1 in both this
#: case and a genuine error, and the two mean opposite things to a page: one is
#: "nothing could be checked" and the other is "the check failed".
NO_USER_MANAGER = "Failed to connect to bus"


class AutostartError(RuntimeError):
    """A key, a value or a file this module refuses. The message is the reason."""


# ------------------------------------------------------------------ the record

_RECORD_CACHE: Dict[str, Dict[str, Any]] = {}


def record(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/design/autostart.json``, parsed and cached per repository root."""
    key = str(root) if root else ""
    if key not in _RECORD_CACHE:
        path = paths.design_file(RECORD_NAME, root)
        try:
            _RECORD_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AutostartError(f"no autostart record at {path}") from exc
        except json.JSONDecodeError as exc:
            raise AutostartError(f"{path} is not valid JSON: {exc}") from exc
    return _RECORD_CACHE[key]


def key_table(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Every desktop-entry key the record names, by key."""
    return {row["key"]: dict(row) for row in record(root)["keys"]}


def writable_keys(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The keys a file this project writes, in the record's own order."""
    return tuple(row["key"] for row in record(root)["keys"]
                 if row.get("written_by_this_project"))


def read_keys(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The keys the generator parses into a field, and therefore acts on."""
    return tuple(row["key"] for row in record(root)["keys"] if row.get("read"))


def ignored_keys(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The keys the generator recognises and deliberately ignores."""
    return tuple(row["key"] for row in record(root)["keys"] if not row.get("read"))


def refusals(root: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """The spellings the record rejects, by their stable id."""
    return {row["id"]: dict(row) for row in record(root)["rejected"]}


def ownership_prefix(root: Optional[Path] = None) -> str:
    """The file-name prefix that marks a file this project owns."""
    return str(record(root)["ownership"]["prefix"])


def marker(root: Optional[Path] = None) -> str:
    """The first line of a file this project wrote."""
    return str(record(root)["ownership"]["marker"])


def activation_probe(root: Optional[Path] = None) -> List[str]:
    """The read-only command that answers whether the generator ran at all."""
    return [str(part) for part in record(root)["activation"]["probe"]]


# --------------------------------------------------------------- directories


def _config_home(config_home: Optional[Path], env: Optional[Mapping[str, str]]) -> Path:
    if config_home is not None:
        return Path(config_home)
    environment = os.environ if env is None else env
    value = environment.get("XDG_CONFIG_HOME")
    if value:
        return Path(value).expanduser()
    return Path(environment.get("HOME") or os.path.expanduser("~")) / ".config"


def directory(config_home: Optional[Path] = None,
              env: Optional[Mapping[str, str]] = None) -> Path:
    """``~/.config/autostart``: the directory the session reads first.

    This is one of the few places this project writes outside its own
    ``~/.config/iarch/``, and it has to be: the generator looks here and nowhere
    else in the user's home (record: ``directory.user``).
    """
    return _config_home(config_home, env) / AUTOSTART_DIR


def system_directories(env: Optional[Mapping[str, str]] = None) -> List[Path]:
    """Every system autostart directory, in the order the generator reads them."""
    environment = os.environ if env is None else env
    value = environment.get("XDG_CONFIG_DIRS") or DEFAULT_XDG_CONFIG_DIRS
    return [Path(part) / AUTOSTART_DIR for part in value.split(":") if part]


def directories(config_home: Optional[Path] = None,
                env: Optional[Mapping[str, str]] = None) -> List[Path]:
    """The user directory first, then the system ones -- the generator's order."""
    return [directory(config_home, env), *system_directories(env)]


# ------------------------------------------------------------------- parsing


def unescape(value: str) -> Tuple[str, Optional[str]]:
    """Apply the six escapes the file parser accepts.

    Returns the text and, when the value holds an escape the parser does not
    accept, the problem: such a value is a hard error upstream and the whole file
    is then treated as hidden. Reporting it is the difference between a page that
    says "off" and a page that says "this file will not be read".
    """
    out: List[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        following = value[index + 1:index + 2]
        if following not in ESCAPES:
            return "".join(out), f"the escape \\{following} is not one the session accepts"
        out.append(ESCAPES[following])
        index += 2
    return "".join(out), None


def split_list(value: str) -> List[str]:
    """A string-list value as its elements (record: ``parsing.string_lists``)."""
    text, _ = unescape(value)
    return [part.strip() for part in text.split(";") if part.strip()]


def bool_value(value: Optional[str]) -> Optional[bool]:
    """A ``Hidden``-style value as a boolean; ``None`` when nothing recognises it.

    ``None`` means the session leaves the key at its default of false, and the
    caller says so rather than guessing (record: ``parsing.booleans``).
    """
    if value is None:
        return None
    text = value.strip().lower()
    if text in TRUE_SPELLINGS:
        return True
    if text in FALSE_SPELLINGS:
        return False
    return None


def split_exec(value: str) -> Tuple[List[str], Optional[str]]:
    """An ``Exec`` value as arguments, for display.

    The generator splits with ``EXTRACT_UNQUOTE | EXTRACT_RELAX``, which is close
    enough to POSIX shell quoting for reading that :func:`shlex.split` is the
    honest tool -- and a value it cannot parse is reported instead of raising,
    because a file another program wrote is something this module describes.
    """
    text, problem = unescape(value)
    if problem:
        return text.split(), problem
    try:
        return shlex.split(text, posix=True, comments=False), None
    except ValueError as exc:
        return text.split(), f"the Exec line cannot be read as quoted arguments: {exc}"


def parse(text: str, *, marker_line: Optional[str] = None,
          keep_localized: bool = False) -> Dict[str, Any]:
    """A desktop file as values, notes and a flag saying whether we wrote it.

    The notes are the record's parsing rules turned into sentences about *this*
    file: a translation the session will not read, a key defined twice, a key
    outside ``[Desktop Entry]``, an escape that fails the parse. A page shows them
    under the row, because each one is a reason the file does not do what it looks
    like it does.

    ``keep_localized`` is for the other reader of this file format. The autostart
    generator ignores a key with a bracket in it, so by default one is reported and
    dropped; glib's desktop-file loader reads ``Name[ur]`` in preference to
    ``Name``, so :mod:`iarch_settings.services.defaults` asks for those keys to be
    kept. Same parser, two documented behaviours, because the two readers really do
    disagree and a page that guessed would be wrong half the time.
    """
    values: Dict[str, str] = {}
    order: List[str] = []
    notes: List[str] = []
    localized: Dict[str, Dict[str, str]] = {}
    noted_localized: List[str] = []
    ours = False
    in_section = False
    sections: List[str] = []
    outside_noted = False

    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", ";")):
            if number == 1 and marker_line and stripped == marker_line:
                ours = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip()
            sections.append(name)
            in_section = name == SECTION
            continue
        if "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        value = raw.strip()
        if not in_section:
            if not outside_noted:
                notes.append(f"{key} is outside [{SECTION}], which the session does not read")
                outside_noted = True
            continue
        if "[" in key:
            base, _, tag = key.partition("[")
            tag = tag.rstrip("]").strip()
            base = base.strip()
            if keep_localized:
                translations = localized.setdefault(base, {})
                if tag and tag not in translations:
                    translations[tag] = value
                continue
            if key not in noted_localized:
                noted_localized.append(key)
                notes.append(f"{key} is a translation; the session reads only {base}")
            continue
        if key in values:
            notes.append(f"{key} is defined more than once; the session reads the first one")
            continue
        values[key] = value
        order.append(key)

    exec_value = values.get("Exec")
    if exec_value is not None:
        _, problem = split_exec(exec_value)
        if problem:
            notes.append(problem)

    return {"values": values, "order": order, "notes": notes, "ours": ours,
            "sections": sections, "localized": localized}


class Entry:
    """One autostart file, read.

    ``system`` says the file lives in a system directory, which is what decides
    whether it may be shadowed; ``masked_by`` names the file that beats this one,
    because the generator stops at the first name it sees.
    """

    __slots__ = ("path", "values", "order", "notes", "ours", "system", "masked_by")

    def __init__(self, path: Path, parsed: Mapping[str, Any], *, system: bool = False,
                 masked_by: Optional[Path] = None) -> None:
        self.path = Path(path)
        self.values: Dict[str, str] = dict(parsed["values"])
        self.order: List[str] = list(parsed["order"])
        self.notes: List[str] = list(parsed["notes"])
        self.ours = bool(parsed["ours"])
        self.system = bool(system)
        self.masked_by = Path(masked_by) if masked_by else None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"Entry({self.path.name!r}, name={self.name!r}, "
                f"enabled={self.enabled!r}, system={self.system!r})")

    @property
    def stem(self) -> str:
        name = self.path.name
        return name[: -len(SUFFIX)] if name.endswith(SUFFIX) else name

    @property
    def owned(self) -> bool:
        """True when the file name carries this project's prefix."""
        return self.path.name.startswith(ownership_prefix())

    @property
    def name(self) -> str:
        return self.values.get("Name", "")

    @property
    def label(self) -> str:
        """What a row shows: the entry's Name, or its file name."""
        return self.name or self.stem

    @property
    def comment(self) -> str:
        return self.values.get("Comment", "")

    @property
    def entry_type(self) -> str:
        return self.values.get("Type", "")

    @property
    def exec_value(self) -> str:
        return self.values.get("Exec", "")

    @property
    def exec_argv(self) -> List[str]:
        argv, _ = split_exec(self.exec_value)
        return argv

    @property
    def try_exec(self) -> str:
        return self.values.get("TryExec", "")

    @property
    def working_directory(self) -> str:
        return self.values.get("Path", "")

    @property
    def only_show_in(self) -> List[str]:
        return split_list(self.values.get("OnlyShowIn", ""))

    @property
    def not_show_in(self) -> List[str]:
        return split_list(self.values.get("NotShowIn", ""))

    @property
    def gnome_phase(self) -> str:
        return self.values.get("X-GNOME-Autostart-Phase", "")

    @property
    def hidden(self) -> bool:
        """``Hidden`` as the session reads it: an odd spelling counts as false."""
        raw = self.values.get("Hidden")
        value = bool_value(raw)
        if value is None and raw is not None:
            note = (f"Hidden={raw} is not a boolean the session accepts, so it is read "
                    f"as false and the entry still starts")
            if note not in self.notes:
                self.notes.append(note)
            return False
        return bool(value)

    @property
    def systemd_skip(self) -> bool:
        return bool(bool_value(self.values.get("X-systemd-skip")))

    @property
    def enabled(self) -> bool:
        """The switch a row shows: on unless the session would generate no unit."""
        return self.outcome()[0]

    @property
    def unit_name(self) -> str:
        """The unit this entry becomes, escaped the way systemd escapes it."""
        return unit_name(self.path.name)

    def as_dict(self) -> dict:
        """The stable shape a page reads. Every key exists."""
        will_run, reason = self.outcome()
        return {
            "path": str(self.path),
            "file_name": self.path.name,
            "stem": self.stem,
            "label": self.label,
            "name": self.name,
            "comment": self.comment,
            "type": self.entry_type,
            "exec": self.exec_value,
            "argv": self.exec_argv,
            "try_exec": self.try_exec,
            "working_directory": self.working_directory,
            "only_show_in": self.only_show_in,
            "not_show_in": self.not_show_in,
            "gnome_phase": self.gnome_phase,
            "hidden": self.hidden,
            "enabled": will_run,
            "reason": reason,
            "owned": self.owned,
            "ours": self.ours,
            "system": self.system,
            "masked_by": str(self.masked_by) if self.masked_by else None,
            "unit_name": self.unit_name,
            "notes": list(self.notes),
        }

    def outcome(self) -> Tuple[bool, str]:
        """Whether a unit is generated for this entry, and why or why not.

        The tests run in the generator's own order, so the reason a person reads is
        the reason the session stopped. This answers *unit generation* only: whether
        the mechanism ran at all is :func:`activation`, and the two are kept apart
        because a correct entry under a generator that never ran still does nothing.
        """
        if self.masked_by is not None:
            return False, (f"masked by {self.masked_by}: the session reads the first "
                           f"file of this name and stops")
        if self.hidden:
            return False, "Hidden is true, so no unit is generated"
        if self.systemd_skip:
            return False, "X-systemd-skip is true, so no unit is generated"
        entry_type = self.entry_type
        if entry_type and entry_type != "Application":
            return False, f"Type={entry_type} is not Application, so no unit is generated"
        if not self.exec_value.strip():
            return False, "there is no Exec line, so no unit is generated"
        try_exec = self.try_exec
        if try_exec and resolve_program(try_exec) is None:
            return False, f"TryExec={try_exec} was not found, so no unit is generated"
        argv = [word for word in self.exec_argv if word not in FIELD_CODES]
        if not argv:
            return False, ("the Exec line holds only field codes, which the session "
                           "removes, so no unit is generated")
        if resolve_program(argv[0]) is None:
            return False, (f"{argv[0]} was not found, so no unit is generated: the "
                           f"session resolves the first word of Exec and skips the "
                           f"entry when nothing is found")
        if self.gnome_phase:
            only = self.only_show_in
            if only and set(only) == {"GNOME"}:
                return False, (f"X-GNOME-Autostart-Phase={self.gnome_phase} and GNOME is "
                               f"the only desktop listed, so the session leaves the entry "
                               f"to GNOME and generates nothing")
            return True, (f"X-GNOME-Autostart-Phase={self.gnome_phase}: the session does "
                          f"not implement GNOME's phases, so the unit is marked "
                          f"NotShowIn=GNOME and the rest is left to GNOME")
        return True, f"a unit named {self.unit_name} is generated"


# ------------------------------------------------------------- reading files


def read_entry(path: Path, *, system: bool = False,
               root: Optional[Path] = None) -> Entry:
    """One file as an :class:`Entry`. A file that cannot be read is still an entry.

    An unreadable file is reported with a note rather than dropped, because the
    generator would still let its name mask a system entry of the same name: a row
    that vanished from the list would hide the one thing worth knowing about it.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        parsed = {"values": {}, "order": [], "notes": [f"could not be read: {exc}"],
                  "ours": False, "sections": []}
        return Entry(path, parsed, system=system)
    return Entry(path, parse(text, marker_line=marker(root)), system=system)


def entries(config_home: Optional[Path] = None, env: Optional[Mapping[str, str]] = None,
            root: Optional[Path] = None) -> List[Entry]:
    """Every entry the session would consider, in the generator's order.

    A name seen twice yields one row: the file that wins, with ``masked_by`` naming
    the one that lost. Sorting is by label then file name, so the list is stable
    between reads and does not depend on the order a filesystem hands back.
    """
    user_dir = directory(config_home, env)
    found: Dict[str, Entry] = {}
    order: List[str] = []

    def add(path: Path, *, system: bool) -> None:
        if not path.is_file():
            return  # only regular files are considered
        name = path.name
        if name in found:
            found[name].masked_by = path
            return
        found[name] = read_entry(path, system=system, root=root)
        order.append(name)

    if user_dir.is_dir():
        for path in sorted(user_dir.iterdir(), key=lambda item: item.name):
            add(path, system=False)
    for system_dir in system_directories(env):
        if not system_dir.is_dir():
            continue
        for path in sorted(system_dir.iterdir(), key=lambda item: item.name):
            add(path, system=True)

    listed = [found[name] for name in order]
    listed.sort(key=lambda entry: (entry.label.lower(), entry.path.name))
    return listed


def ours(config_home: Optional[Path] = None, env: Optional[Mapping[str, str]] = None,
         root: Optional[Path] = None) -> List[Entry]:
    """Only the entries this project owns, which are the only ones it changes."""
    return [entry for entry in entries(config_home, env, root) if entry.owned]


# ------------------------------------------------------------ writing files


def unit_escape(name: str) -> str:
    """Escape a file name into a unit instance the way systemd does.

    Reimplemented from ``do_escape`` rather than asked of systemd, because asking
    would mean running a command to describe a file, and the rule is four lines and
    recorded with its citation. A multi-byte character becomes one ``\\xHH`` per
    byte, which is what the C code does by iterating over bytes.
    """
    out: List[str] = []
    rest = name
    if rest.startswith("."):
        out.append(_hex_escape("."))
        rest = rest[1:]
    for char in rest:
        if char == "/":
            out.append("-")
        elif char in "-\\" or char not in UNIT_VALID_CHARS:
            out.append(_hex_escape(char))
        else:
            out.append(char)
    return "".join(out)


def _hex_escape(char: str) -> str:
    return "".join(f"\\x{byte:02x}" for byte in char.encode("utf-8"))


def unit_name(file_name: str) -> str:
    """``app-<escaped name>@autostart.service`` for a file name."""
    stem = file_name[: -len(SUFFIX)] if file_name.endswith(SUFFIX) else file_name
    return f"app-{unit_escape(stem)}@autostart.service"


def slug(label: str) -> str:
    """A label as the middle of a file name: lowercase, alphanumerics and dashes."""
    text = "".join(char.lower() if char.isalnum() else "-" for char in label.strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "entry"


def free_name(label: str, config_home: Optional[Path] = None,
              env: Optional[Mapping[str, str]] = None,
              root: Optional[Path] = None) -> str:
    """A file name that is not taken anywhere the generator will look.

    A name already in use is a name already taken: the generator reads the first
    file of a name only, so writing over another program's entry would silently
    replace what it starts. The counter keeps going until the name is free in the
    user directory *and* in every system directory.
    """
    prefix = ownership_prefix(root)
    stem = slug(label)
    candidate = f"{prefix}{stem}{SUFFIX}"
    taken = set()
    for directory_path in directories(config_home, env):
        if directory_path.is_dir():
            taken.update(path.name for path in directory_path.iterdir())
    counter = 2
    while candidate in taken:
        candidate = f"{prefix}{stem}-{counter}{SUFFIX}"
        counter += 1
    return candidate


def quote_exec(argv: Sequence[str]) -> str:
    """An argument list as an ``Exec`` value.

    Only double quotes are emitted, and only around an argument that needs them.
    :func:`check_command` has already refused the characters that would need an
    escape, so this function cannot produce one -- which matters, because an escape
    the file parser does not accept fails the parse of the whole file.
    """
    parts: List[str] = []
    for word in argv:
        if word and all(char.isalnum() or char in EXEC_SAFE_CHARS for char in word):
            parts.append(word)
        else:
            parts.append(f'"{word}"')
    return " ".join(parts)


def resolve_program(word: str) -> Optional[str]:
    """The absolute path of a command's first word, or ``None``.

    The same question the generator asks with ``find_executable``, asked here so an
    entry that would never start is refused when it is added rather than discovered
    at the next login.
    """
    if not word:
        return None
    if os.sep in word:
        candidate = Path(word).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return runner.which(word)


def check_command(argv: Sequence[str], root: Optional[Path] = None) -> List[str]:
    """Every reason a command may not be written into an entry. Empty means fine."""
    words = [str(word) for word in argv]
    if not words or not words[0].strip():
        return ["a startup entry needs a command"]

    for word in words:
        if "\x00" in word:
            return ["a command argument contains a NUL byte"]
        if "\n" in word or "\r" in word:
            return ["a command argument contains a line break"]
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in word):
            return ["a command argument contains a control character"]

    problems: List[str] = []
    first = words[0]
    if first.startswith("-"):
        problems.append(f"the program name cannot begin with '-': {first}")
    if Path(first).name in SHELLS and any(word == "-c" for word in words[1:]):
        rejection = refusals(root).get("shell-wrapper")
        problems.append(rejection["message"] if rejection else
                        "a startup command is run directly, never through a shell")
    for word in words:
        if '"' in word:
            problems.append(f"a command argument cannot contain a double quote: {word}")
        if "\\" in word:
            problems.append(f"a command argument cannot contain a backslash: {word}")
        if word.startswith("~"):
            problems.append(f"a command argument cannot begin with '~', because the "
                            f"session expands it against your home directory: {word}")
        if word in FIELD_CODES:
            problems.append(f"the session removes {word} from a startup command, so it "
                            f"would run without it")
    if problems:
        return problems

    if resolve_program(first) is None:
        problems.append(
            f"no such program: {first}. The session resolves the first word of Exec and "
            f"generates no unit when nothing is found, so this entry would sit in the "
            f"list and never start.")
    return problems


def check_values(values: Mapping[str, Any], root: Optional[Path] = None) -> List[str]:
    """Every reason a set of desktop-entry values may not be written."""
    problems: List[str] = []
    allowed = set(writable_keys(root))
    table = key_table(root)
    for key in values:
        if key in allowed:
            continue
        row = table.get(key)
        if row is None:
            problems.append(f"{key} is not a key the session's generator reads")
        elif not row.get("read"):
            problems.append(f"{key} is recognised and ignored by the session, so writing "
                            f"it would change nothing")
        else:
            problems.append(f"{key} is read by the session but this project does not "
                            f"write it")
    if problems:
        return problems

    exec_value = values.get("Exec")
    if isinstance(exec_value, (list, tuple)):
        problems.extend(check_command([str(word) for word in exec_value], root))
    elif isinstance(exec_value, str):
        problems.extend(check_command_text(exec_value, root))
    else:
        problems.append("an entry without Exec is skipped by the session, so it would "
                        "never start")

    for key, value in values.items():
        if key == "Exec":
            continue  # checked above, where the argument rules live
        text = "" if value is None else str(value)
        if "\n" in text or "\r" in text:
            problems.append(f"{key} contains a line break")
        if "\\" in text:
            # A backslash is the one character that can cost the whole file: the parser
            # accepts six escapes and treats any other one as a hard error, after which
            # the file is read as hidden and still masks a system entry of its name.
            problems.append(f"{key} contains a backslash, and the only escapes the session "
                            f"accepts are \\s \\n \\t \\r \\\\ and \\;")
        row = table[key]
        if row.get("type") == "boolean" and bool_value(text) is None:
            problems.append(f"{key}={text} is not a boolean the session accepts; use "
                            f"true or false")
        choices = row.get("values")
        if choices and text not in choices:
            problems.append(f"{key}={text} is not one of {', '.join(choices)}")
    return problems


def render(values: Mapping[str, Any], root: Optional[Path] = None) -> str:
    """The text of an entry this project writes.

    The marker comment is the first line, so a later version of this application can
    recognise a file it wrote even under a name it did not choose. Keys go out in
    :data:`RENDER_ORDER` and nothing else is emitted: a key the record does not mark
    as written here does not belong in the file.
    """
    lines = [marker(root), f"[{SECTION}]"]
    for key in RENDER_ORDER:
        if key not in values:
            continue
        value = values[key]
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif key == "Exec" and isinstance(value, (list, tuple)):
            text = quote_exec(value)
        else:
            text = str(value)
        lines.append(f"{key}={text}")
    return "\n".join(lines) + "\n"


def set_hidden_line(text: str, hidden: bool, root: Optional[Path] = None) -> str:
    """``text`` with its ``Hidden`` line replaced, or one added to the section.

    A line edit rather than a rewrite, so a comment, a blank line, a key this
    project does not write and a key it has no opinion about all survive a switch
    being flipped. The record says the first definition of a key is the one read
    (``parsing.duplicate_keys``), which is why the line is found and replaced
    instead of a second one being appended.
    """
    lines = text.splitlines()
    value = "true" if hidden else "false"
    in_section = False
    section_at: Optional[int] = None
    section_end = 0
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped[1:-1].strip() == SECTION
            if in_section and section_at is None:
                section_at = number
                section_end = number + 1
            continue
        if not in_section:
            continue
        section_end = number + 1
        key, _, _ = stripped.partition("=")
        if key.strip() == "Hidden":
            lines[number] = f"Hidden={value}"
            return "\n".join(lines) + "\n"
    if section_at is None:
        lines = [f"[{SECTION}]", f"Hidden={value}", *lines]
        return "\n".join(lines) + "\n"
    lines[section_end:section_end] = [f"Hidden={value}"]
    return "\n".join(lines) + "\n"


def _require_owned(path: Path, root: Optional[Path] = None) -> None:
    """Refuse a path this project does not own, before anything is written.

    One check, called by both writers, so there is no route to a file that skips it.
    The single exception is a shadow, which is created under a name another program
    chose, on purpose: the record allows exactly that and only for a file in a system
    directory, and :func:`set_enabled` is the only caller that asks for it.
    """
    prefix = ownership_prefix(root)
    if not Path(path).name.startswith(prefix):
        raise AutostartError(
            f"{Path(path).name} does not start with {prefix}, so this application will "
            f"not write it: a file it does not own belongs to whatever wrote it")


def _write_text(path: Path, text: str, *, owned: bool = True,
                root: Optional[Path] = None,
                env: Optional[Mapping[str, str]] = None) -> Path:
    """Back up, then write atomically. ``configstore`` does both, so this does neither."""
    if owned:
        _require_owned(path, root)
    paths.add_repo_to_path()
    from iarch.lib import configstore  # noqa: PLC0415

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        configstore.backup_of(path, env)
    # atomic_write refuses to write through a symlink, so a link planted in the
    # autostart directory cannot be used to reach a file outside it.
    configstore.atomic_write(path, text)
    return path


def write(path: Path, values: Mapping[str, Any], *, root: Optional[Path] = None,
          env: Optional[Mapping[str, str]] = None) -> Path:
    """Write one entry, backing up whatever was there. Returns the path written.

    The mode comes from :func:`iarch.lib.configstore.atomic_write`: carried over
    from the file being replaced, or 0666-less-umask for a new one. An autostart
    entry holds no secret, and tightening or loosening a mode somebody else set is
    not this module's decision to make.
    """
    path = Path(path)
    problems = check_values(values, root)
    if problems:
        raise AutostartError("; ".join(problems))
    return _write_text(path, render(values, root), root=root, env=env)


def add(label: str, argv: Sequence[str], *, comment: str = "",
        config_home: Optional[Path] = None, env: Optional[Mapping[str, str]] = None,
        root: Optional[Path] = None) -> Entry:
    """Create a startup entry for a program and return what was written.

    The name is derived from the label and carries this project's prefix, so the
    entry can be found again, changed and removed without ever touching a file
    somebody else wrote.
    """
    words = [str(word) for word in argv]
    problems = check_command(words, root)
    if problems:
        raise AutostartError("; ".join(problems))
    text = str(label).strip()
    if not text:
        raise AutostartError("a startup entry needs a name")
    if len(text) > MAX_NAME_LENGTH:
        raise AutostartError(f"a startup entry name is at most {MAX_NAME_LENGTH} characters")

    target = directory(config_home, env)
    path = target / free_name(text, config_home, env, root)
    values: Dict[str, Any] = {"Name": text, "Type": "Application", "Exec": words,
                              "Hidden": False}
    if comment.strip():
        values["Comment"] = comment.strip()
    write(path, values, root=root, env=env)

    entry = read_entry(path, system=False, root=root)
    if entry.notes:
        raise AutostartError(f"{path.name} was written but reads back oddly: "
                             f"{'; '.join(entry.notes)}")
    return entry


def set_enabled(entry: Entry, enabled: bool, *, config_home: Optional[Path] = None,
                env: Optional[Mapping[str, str]] = None,
                root: Optional[Path] = None) -> Path:
    """Turn an entry on or off. Returns the file that was written or removed.

    Three cases, and only the first two write anything:

    * an entry this project owns is edited in place -- its ``Hidden`` line and
      nothing else, so every other line in a file it wrote survives;
    * an entry in a *system* directory is shadowed by a same-named file in the user
      directory, because the generator reads that directory first and the first name
      wins. Turning it back on removes the shadow, which restores the system file
      exactly;
    * an entry in the user directory that this project does not own is refused: that
      file is another program's own record of what it should start.
    """
    entry = entry if isinstance(entry, Entry) else read_entry(Path(entry), root=root)
    prefix = ownership_prefix(root)

    if entry.owned:
        try:
            text = entry.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise AutostartError(f"{entry.path} could not be read: {exc}") from exc
        return _write_text(entry.path, set_hidden_line(text, not enabled, root),
                           root=root, env=env)

    if not entry.system:
        raise AutostartError(
            f"{entry.path.name} was not written by this application, so it is listed "
            f"but not changed. Its own program owns that file: {entry.path}")

    shadow = directory(config_home, env) / entry.path.name
    if enabled:
        if not shadow.is_file():
            raise AutostartError(
                f"{entry.path.name} is not switched off by this application: there is "
                f"no shadow file at {shadow}")
        existing = read_entry(shadow, root=root)
        if not existing.ours and not shadow.name.startswith(prefix):
            raise AutostartError(
                f"{shadow} exists but was not written by this application, so it is "
                f"not removed")
        paths.add_repo_to_path()
        from iarch.lib import configstore  # noqa: PLC0415

        configstore.backup_of(shadow, env)
        shadow.unlink()
        return shadow

    argv = entry.exec_argv or ([entry.exec_value] if entry.exec_value else [])
    problems = check_command(argv, root)
    if problems:
        raise AutostartError(
            f"{entry.path.name} cannot be switched off by this application: "
            f"{'; '.join(problems)}")
    values: Dict[str, Any] = {
        "Comment": f"Switched off in iarch-settings; shadows {entry.path}.",
        "Name": entry.name or entry.stem,
        "Type": "Application",
        "Exec": argv,
        "Hidden": True,
    }
    # A shadow is created under the system file's own name, on purpose and for a
    # system file only: the generator reads the user directory first and the first
    # name wins, so this is the one way to switch such an entry off without editing
    # a file nobody owns. The values have been checked, so the ownership check that
    # `write` would apply is the one thing deliberately skipped here.
    problems = check_values(values, root)
    if problems:
        raise AutostartError(f"{entry.path.name} cannot be switched off: "
                             f"{'; '.join(problems)}")
    return _write_text(shadow, render(values, root), owned=False, root=root, env=env)


def remove(entry: Entry, *, env: Optional[Mapping[str, str]] = None,
           root: Optional[Path] = None) -> Optional[Path]:
    """Delete an entry this project owns, keeping a backup. Returns the backup.

    Anything else is refused. A file another program wrote is that program's to
    remove, and this application has no way to know what it would be undoing.
    """
    entry = entry if isinstance(entry, Entry) else read_entry(Path(entry), root=root)
    if not entry.owned:
        raise AutostartError(
            f"{entry.path.name} was not written by this application, so it is not "
            f"removed. Delete it yourself if that is what you want: {entry.path}")
    paths.add_repo_to_path()
    from iarch.lib import configstore  # noqa: PLC0415

    backup = configstore.backup_of(entry.path, env)
    entry.path.unlink()
    return backup


# ------------------------------------------------- the settings.json projection

#: ``data/schemas/settings.schema.json`` restricts an entry's name to characters
#: that are safe in a file name on every filesystem this project supports, so the
#: stem needs no slug and no escaping: the name in the file is the name the user
#: typed, and a person looking for it in ~/.config/autostart finds it.
SETTINGS_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

SETTINGS_ENTRY_KEYS = ("name", "command", "enabled", "comment")


def entry_file_name(name: str, root: Optional[Path] = None) -> str:
    """The file a settings entry becomes: ``iarch-<name>.desktop``."""
    return f"{ownership_prefix(root)}{name}{SUFFIX}"


def check_entry(entry: Mapping[str, Any], root: Optional[Path] = None) -> List[str]:
    """Every reason one ``startup.autostart`` entry may not be projected.

    The list is checked before any file is written, so an invalid entry costs a
    refusal and not a half-written directory: :func:`project` answers FAILED without
    touching anything, which is the only way the apply pipeline's rollback has
    nothing to undo.
    """
    problems: List[str] = []
    if not isinstance(entry, Mapping):
        return ["a startup entry is an object with a name and a command"]
    name = entry.get("name")
    if not isinstance(name, str) or not re.fullmatch(SETTINGS_NAME_PATTERN, name):
        problems.append(f"{name!r} is not a name this project can make a file out of: "
                        f"it starts with a letter or a digit and holds at most 64 "
                        f"letters, digits, dots, underscores and dashes")
    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        problems.append("a startup entry needs a command")
    else:
        problems.extend(check_command_text(command, root))
    enabled = entry.get("enabled", True)
    if not isinstance(enabled, bool):
        problems.append(f"enabled={enabled!r} is not true or false")
    comment = entry.get("comment", "")
    if not isinstance(comment, str):
        problems.append(f"comment={comment!r} is not text")
    elif "\n" in comment or "\r" in comment:
        problems.append("a comment cannot contain a line break")
    unknown = sorted(set(entry) - set(SETTINGS_ENTRY_KEYS))
    if unknown:
        problems.append(f"{', '.join(unknown)} is not a key a startup entry has")
    return problems


def check_command_text(text: str, root: Optional[Path] = None) -> List[str]:
    """Check an ``Exec`` line as text, which is how settings.json stores one.

    The line is split the way the session splits it and each argument is then
    checked, so a command that would run is a command that can be written. One check
    belongs to the file rather than to the arguments: a backslash anywhere in the
    line, because the file parser accepts six escapes and any other one is a hard
    error that makes the session drop the whole file -- and still let its name mask a
    system entry of the same name.
    """
    if "\\" in text:
        return ["a startup command cannot contain a backslash: the session accepts only "
                "the escapes \\s \\n \\t \\r \\\\ and \\;, and any other one makes it drop "
                "the whole file"]
    try:
        words = shlex.split(text, posix=True, comments=False)
    except ValueError as exc:
        return [f"the command cannot be read as a quoted argument list: {exc}"]
    return check_command(words, root)


def entry_values(entry: Mapping[str, Any]) -> Dict[str, Any]:
    """One settings entry as the desktop-entry values to write."""
    values: Dict[str, Any] = {
        "Name": str(entry.get("name", "")),
        "Type": "Application",
        "Exec": str(entry.get("command", "")),
        # enabled is optional and means true, so an entry written before the key
        # existed still starts: a default of false would silently switch off every
        # program somebody had added by hand.
        "Hidden": not bool(entry.get("enabled", True)),
    }
    comment = str(entry.get("comment", "")).strip()
    if comment:
        values["Comment"] = comment
    return values


def projection_problems(entries: Sequence[Any],
                        root: Optional[Path] = None) -> List[str]:
    """Every way a settings list cannot be projected, as sentences.

    The same pass :func:`project` runs before it writes anything, published on its own
    so a caller can refuse *before* building a change rather than after: an entry with
    no command is a mistake somebody made in a row, and the place to say so is the
    dialog that was about to be confirmed, not the report of a change that has already
    backed up three files.
    """
    problems: List[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, Mapping):
            problems.append(f"entry {index}: a startup entry is an object with a name "
                            f"and a command")
            continue
        for problem in check_entry(entry, root):
            problems.append(f"entry {index}: {problem}")
    names = [str(entry.get("name")) for entry in entries if isinstance(entry, Mapping)]
    for name in sorted({name for name in names if names.count(name) > 1}):
        problems.append(f"two entries are both named {name}, and one file cannot be both")
    return problems


def project(entries: Sequence[Mapping[str, Any]], *, config_home: Optional[Path] = None,
            env: Optional[Mapping[str, str]] = None,
            root: Optional[Path] = None) -> runner.Outcome:
    """Make ``~/.config/autostart`` match a settings list. Returns an outcome.

    This is the callable an :class:`iarch_settings.services.apply.Change` carries:
    the settings document is the source of truth for the entries this project owns,
    and projecting it is what turns a list of rows into files a session reads. Every
    entry is checked first, then every file is written, then any owned file the list
    no longer names is backed up and removed -- so a program the user deleted from
    the page stops starting, and a file this project wrote is never left behind.

    Files this project does not own are not touched, listed or removed, whatever the
    settings document says: the ownership rule in the record is the reason the
    projection can be run twice without eating somebody else's entry.
    """
    argv = ["iarch-settings", "autostart", "project", f"{len(entries)} entries"]
    rows = [dict(entry) if isinstance(entry, Mapping) else entry for entry in entries]

    problems = projection_problems(rows, root)
    if problems:
        return runner.Outcome(argv, runner.FAILED, reason="; ".join(problems[:6]))

    target = directory(config_home, env)
    lines: List[str] = []
    wanted: Dict[str, Path] = {}
    try:
        for entry in rows:
            name = entry_file_name(str(entry["name"]), root)
            path = target / name
            wanted[name] = path
            existed = path.is_file()
            write(path, entry_values(entry), root=root, env=env)
            lines.append(f"{'updated' if existed else 'wrote'} {name}"
                         + ("" if entry.get("enabled", True) else " (Hidden=true)"))

        prefix = ownership_prefix(root)
        for path in sorted(target.iterdir(), key=lambda item: item.name) if target.is_dir() else []:
            if not path.is_file() or not path.name.startswith(prefix):
                continue
            if path.name in wanted:
                continue
            entry = read_entry(path, root=root)
            backup = remove(entry, env=env, root=root)
            lines.append(f"removed {path.name}"
                         + (f" (kept as {backup.name})" if backup else ""))
    except (AutostartError, OSError) as exc:
        return runner.Outcome(argv, runner.FAILED, stdout="\n".join(lines),
                              reason=str(exc))
    return runner.Outcome(argv, runner.OK, stdout="\n".join(lines) or "nothing to write")


# ------------------------------------------------------------------ activation


def activation(root: Optional[Path] = None,
               timeout: float = runner.DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Whether the session's autostart mechanism ran, and which units it made.

    A read-only probe, with the runner's three-way verdict: no ``systemctl`` and no
    user manager is *unverified*, not a failure. The environment is inherited rather
    than supplied, because the probe needs the session's own ``PATH`` and
    ``XDG_RUNTIME_DIR`` to find anything. The Startup page shows the difference
    honestly, since "no units were found" and "nothing could be asked" lead to
    opposite conclusions about an entry that did not start.
    """
    argv = activation_probe(root)
    binary, *args = argv
    outcome = runner.run(binary, args, timeout=timeout)
    units: List[str] = []
    for line in outcome.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        name = fields[0]
        if name.startswith("app-") and name.endswith("@autostart.service"):
            units.append(name)
    verdict = outcome.verdict
    reason = outcome.reason
    if verdict == runner.FAILED and NO_USER_MANAGER in outcome.stderr:
        # systemctl exists and ran, but there was no user manager to ask. That is the
        # same situation as systemctl not being installed: the question went
        # unanswered, and "no units were found" would be a different answer.
        verdict = runner.UNVERIFIED
        reason = ("no systemd user manager is running, so the autostart generator "
                  "could not be asked")
    if verdict == runner.FAILED and not reason:
        reason = f"{binary} reported an error"
    return {
        "verdict": verdict,
        "argv": list(outcome.argv),
        "units": sorted(set(units)),
        "reason": reason,
        "generator": str(record(root)["activation"]["generator"]),
        "note": str(record(root)["activation"]["probe_note"]),
    }


def unit_is_listed(entry: Entry, state: Mapping[str, Any]) -> Optional[bool]:
    """Whether this entry's unit appears in a probe result; ``None`` when unknown."""
    if state.get("verdict") != runner.OK:
        return None
    return entry.unit_name in list(state.get("units") or [])


# -------------------------------------------------------------------- summary


def available(config_home: Optional[Path] = None, env: Optional[Mapping[str, str]] = None,
              root: Optional[Path] = None) -> Dict[str, Any]:
    """What the Startup page needs before it draws a single row."""
    target = directory(config_home, env)
    return {
        "directory": str(target),
        "exists": target.is_dir(),
        "writable": target.is_dir() and os.access(target, os.W_OK),
        "system_directories": [str(path) for path in system_directories(env)
                               if path.is_dir()],
        "prefix": ownership_prefix(root),
        "marker": marker(root),
        "writable_keys": list(writable_keys(root)),
        "read_keys": list(read_keys(root)),
        "ignored_keys": list(ignored_keys(root)),
        "refusals": [dict(row) for row in refusals(root).values()],
        "entries": [entry.as_dict() for entry in entries(config_home, env, root)],
        "activation": activation(root),
        "verified_against": str(record(root)["verified_against"]),
    }
