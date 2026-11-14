# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Default applications: which program opens a link, a folder, a text file, a mail.

Everything here is read out of ``data/design/xdg-defaults.json``, which was read out
of the two tools that own this setting (``xdg-mime``, ``xdg-settings``) and out of
glib's desktop-file loader, because glib is what every application chooser on this
desktop uses and a list that disagreed with it would be wrong in a way a person
could see.

Four decisions from that record shape this module:

* **``xdg-mime``, never ``xdg-settings``, for a write.** ``xdg-settings set`` only
  works when a desktop environment was detected; with none, it refuses outright.
  This session is not GNOME, KDE or XFCE, so the generic path is the one that runs,
  and the write it would perform is ``xdg-mime``'s anyway. Calling the tool that
  does the work is more honest than calling a wrapper that may decline to.
* **A role is a set of mimetypes written in one call.** The browser role sets
  ``text/html`` and both ``http`` scheme handlers together, so a page cannot end up
  opening in one program and a link in another.
* **A write is read back.** ``xdg-mime`` can exit 0 having written a line that does
  not take effect -- upstream's own ``set_browser_mime`` reads the value back and
  restores the original when it disagrees. :func:`set_role` does the same check,
  because "the command succeeded" and "the default changed" are different claims.
* **A role nobody can set is named, not offered.** There is no association for a
  terminal emulator, so the record lists it under ``unsettable`` with the reason,
  and the page shows that sentence instead of a dropdown that would write a file
  nothing reads.

Candidates come from the application directories rather than from Gio, so the whole
page is testable with no display server and no PyGObject installed. Every filter
that decides whether a program is offered has a citation in the record.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import i18n, paths
from . import autostart, runner

RECORD_NAME = "xdg-defaults.json"
"""``data/design/xdg-defaults.json`` -- the record every rule below comes from."""

MIME_TOOL = "xdg-mime"
SETTINGS_TOOL = "xdg-settings"

APPLICATIONS_DIR = "applications"
DESKTOP_SUFFIX = ".desktop"
DEFAULT_XDG_DATA_HOME = ".local/share"
DEFAULT_XDG_DATA_DIRS = "/usr/local/share:/usr/share"

#: The most rows a role's dropdown will carry. A directory full of desktop files is
#: a real thing, and a list that grows without a limit is a page that stops
#: answering; the current association is always among the rows returned.
MAX_CANDIDATES = 200


class DefaultsError(RuntimeError):
    """A role, a file name or a tool this module refuses. The message is the reason."""


# ------------------------------------------------------------------ the record

_RECORD_CACHE: Dict[str, Dict[str, Any]] = {}


def record(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/design/xdg-defaults.json``, parsed and cached per repository root."""
    key = str(root) if root else ""
    if key not in _RECORD_CACHE:
        path = paths.design_file(RECORD_NAME, root)
        try:
            _RECORD_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DefaultsError(f"no default-applications record at {path}") from exc
        except json.JSONDecodeError as exc:
            raise DefaultsError(f"{path} is not valid JSON: {exc}") from exc
    return _RECORD_CACHE[key]


def roles(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Every role the page may offer, by id."""
    return {row["role"]: dict(row) for row in record(root)["roles"]}


def role_ids(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The role ids, in the record's order, which is the page's order."""
    return tuple(row["role"] for row in record(root)["roles"])


def role(role_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """One role's record. Refuses an id the record does not name."""
    table = roles(root)
    if role_id not in table:
        raise DefaultsError(
            f"{role_id} is not a default-application role this project sets; the "
            f"record names {', '.join(table)}")
    return table[role_id]


def unsettable(root: Optional[Path] = None) -> List[Dict[str, str]]:
    """The roles the page names and then explains, instead of offering."""
    return [dict(row) for row in record(root)["unsettable"]]


def candidate_rules(root: Optional[Path] = None) -> Dict[str, Any]:
    """The ``candidates`` block: how a program becomes an offerable row."""
    return dict(record(root)["candidates"])


def read_order(root: Optional[Path] = None) -> Dict[str, Any]:
    """Where ``xdg-mime query default`` looks, in the order it looks."""
    return dict(record(root)["mime_tool"]["read_order"])


def refusals(root: Optional[Path] = None) -> List[Dict[str, str]]:
    """What ``xdg-settings`` refuses, and why the page does not call it."""
    return [dict(row) for row in record(root)["settings_tool"]["refusals"]]


def settings_properties(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The only two properties ``xdg-settings`` has."""
    return tuple(row["property"] for row in record(root)["settings_tool"]["properties"])


# --------------------------------------------------------------- directories


def data_directories(env: Optional[Mapping[str, str]] = None) -> List[Path]:
    """The user's data directory first, then the system ones."""
    environment = os.environ if env is None else env
    home = environment.get("XDG_DATA_HOME")
    if home:
        first = Path(home).expanduser()
    else:
        base = environment.get("HOME") or os.path.expanduser("~")
        first = Path(base) / DEFAULT_XDG_DATA_HOME
    system = environment.get("XDG_DATA_DIRS") or DEFAULT_XDG_DATA_DIRS
    return [first, *[Path(part) for part in system.split(":") if part]]


def application_directories(env: Optional[Mapping[str, str]] = None) -> List[Path]:
    """Every ``applications`` directory, in the order ``xdg-mime`` reads them."""
    return [path / APPLICATIONS_DIR for path in data_directories(env)]


def tools_present() -> Dict[str, bool]:
    """Whether each tool is installed. A missing one is unverified, not a failure."""
    return {name: runner.which(name) is not None for name in (MIME_TOOL, SETTINGS_TOOL)}


# ------------------------------------------------------------------ desktop ids


def desktop_id(path: Path) -> str:
    """A file's name, which is how an association refers to it."""
    return Path(path).name


def check_desktop_id(value: str) -> List[str]:
    """Every reason a file name may not be written into an association."""
    problems: List[str] = []
    text = str(value)
    if not text.strip():
        return ["a default application needs a .desktop file name"]
    if not text.endswith(DESKTOP_SUFFIX):
        problems.append(f"{text} is not a .desktop file name, and xdg-mime refuses "
                        f"anything else")
    if "/" in text or os.sep in text:
        problems.append(f"{text} contains a path separator; an association names a "
                        f"file, not a location")
    if ".." in text:
        problems.append(f"{text} contains '..'")
    if text.startswith("-"):
        problems.append(f"{text} begins with '-', which would be read as an option")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        problems.append(f"{text} contains a control character")
    return problems


def find_desktop_file(value: str,
                      env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """The first application directory holding a file of that name, or ``None``."""
    problems = check_desktop_id(value)
    if problems:
        return None
    for directory in application_directories(env):
        candidate = directory / value
        if candidate.is_file():
            return candidate
    return None


# ------------------------------------------------------------------- parsing


def localized(values: Mapping[str, Dict[str, str]], key: str,
              tags: Optional[Sequence[str]] = None,
              env: Optional[Mapping[str, str]] = None) -> str:
    """A localised desktop-file value, most specific tag first.

    The tag is reduced -- ``ur_PK.UTF-8@euro`` to ``ur_PK.UTF-8`` to ``ur_PK`` to
    ``ur`` -- and the unlocalised key is the fallback, so an inexact reduction costs
    a label in the wrong language rather than no label. glib reads these keys as
    localised strings (record: ``candidates.localised_names``), which is the opposite
    of the autostart generator, where a bracketed key is ignored.
    """
    translations = values.get(key) or {}
    if not translations:
        return ""
    if tags is None:
        tags = i18n.language_tags(env)
    for tag in tags:
        for candidate in _tag_reductions(str(tag)):
            if candidate in translations:
                return translations[candidate]
    return ""


def _tag_reductions(tag: str) -> List[str]:
    """A locale tag and the shorter forms of it, most specific first."""
    forms: List[str] = []
    text = tag.strip()
    while text:
        if text not in forms:
            forms.append(text)
        if "@" in text:
            text = text.split("@", 1)[0]
        elif "." in text:
            text = text.split(".", 1)[0]
        elif "_" in text:
            text = text.split("_", 1)[0]
        else:
            break
    return forms


class Candidate:
    """One program that could be offered for a role, and why it is or is not.

    ``path`` is ``None`` for the one row that has no file behind it: an association
    currently in force that names a file no application directory holds. That row
    exists because it is the reason links of this type do not open, and a list that
    quietly dropped it would leave the person with a dropdown and no explanation.
    """

    __slots__ = ("path", "desktop_id", "values", "localized_values", "role",
                 "current", "kept", "reason", "tags")

    def __init__(self, path: Optional[Path], parsed: Mapping[str, Any], *,
                 role_id: str, current: bool = False, kept: bool = True,
                 reason: str = "", tags: Optional[Sequence[str]] = None) -> None:
        self.path = Path(path) if path else None
        self.desktop_id = str(parsed.get("desktop_id") or
                              (Path(path).name if path else ""))
        self.values: Dict[str, str] = dict(parsed["values"])
        self.localized_values: Dict[str, Dict[str, str]] = dict(parsed.get("localized") or {})
        self.role = role_id
        self.current = bool(current)
        self.kept = bool(kept)
        self.reason = reason
        self.tags = list(tags) if tags else []

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"Candidate({self.desktop_id!r}, role={self.role!r}, "
                f"kept={self.kept!r}, current={self.current!r})")

    @property
    def label(self) -> str:
        """The name to show: localised if there is one, then Name, then the file."""
        text = localized(self.localized_values, "Name", self.tags)
        return text or self.values.get("Name") or self.desktop_id[:-len(DESKTOP_SUFFIX)]

    @property
    def generic_name(self) -> str:
        return localized(self.localized_values, "GenericName", self.tags) or \
            self.values.get("GenericName", "")

    @property
    def comment(self) -> str:
        return localized(self.localized_values, "Comment", self.tags) or \
            self.values.get("Comment", "")

    @property
    def mime_types(self) -> List[str]:
        return autostart.split_list(self.values.get("MimeType", ""))

    @property
    def exec_value(self) -> str:
        return self.values.get("Exec", "")

    @property
    def try_exec(self) -> str:
        return self.values.get("TryExec", "")

    @property
    def icon(self) -> str:
        return self.values.get("Icon", "")

    @property
    def terminal(self) -> bool:
        return bool(autostart.bool_value(self.values.get("Terminal")))

    @property
    def hidden(self) -> bool:
        return bool(autostart.bool_value(self.values.get("Hidden")))

    @property
    def no_display(self) -> bool:
        return bool(autostart.bool_value(self.values.get("NoDisplay")))

    def as_dict(self) -> dict:
        """The stable shape a page reads. Every key exists."""
        return {
            "desktop_id": self.desktop_id,
            "path": str(self.path) if self.path else None,
            "label": self.label,
            "generic_name": self.generic_name,
            "comment": self.comment,
            "icon": self.icon,
            "exec": self.exec_value,
            "try_exec": self.try_exec,
            "mime_types": self.mime_types,
            "terminal": self.terminal,
            "role": self.role,
            "current": self.current,
            "kept": self.kept,
            "reason": self.reason,
        }


def _keep(candidate: Candidate, wanted: Sequence[str]) -> Tuple[bool, str]:
    """Apply the record's filters, in the record's order, and say which one decided."""
    if candidate.hidden:
        return False, "Hidden is true, so the desktop does not index this program"
    if candidate.no_display:
        return False, "NoDisplay is true, so no application chooser offers this program"
    try_exec = candidate.try_exec
    if try_exec and autostart.resolve_program(try_exec) is None:
        return False, f"TryExec={try_exec} was not found, so this program is not installed"
    if not candidate.exec_value.strip():
        return False, "there is no Exec line, so this program cannot be launched"
    claimed = set(candidate.mime_types)
    if not claimed.intersection(set(wanted)):
        return False, ("its MimeType line does not claim this type, so offering it would "
                       "ask a program to open something it never said it could")
    if not candidate.label:
        return False, "it has no Name in any language, so there is nothing to show"
    return True, ""


def candidates(role_id: str, env: Optional[Mapping[str, str]] = None,
               root: Optional[Path] = None,
               current_id: Optional[str] = None) -> List[Candidate]:
    """The programs a role's dropdown may offer.

    One row per file name, from the first directory that holds it, because that is
    the file an association of that name resolves to. A program filtered out is not
    returned unless it is the association currently in force, in which case it comes
    back marked, with the reason -- a dropdown that cannot show the current value
    looks unset and invites a pointless change (record: ``candidates.always_listed``).
    """
    wanted = [str(item) for item in role(role_id, root)["mimetypes"]]
    tags = i18n.language_tags(env)
    seen: Dict[str, Candidate] = {}
    order: List[str] = []

    for directory in application_directories(env):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if not path.is_file() or not path.name.endswith(DESKTOP_SUFFIX):
                continue
            if path.name in seen:
                continue  # an earlier directory wins, exactly as it does for the tool
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue  # a file that cannot be read cannot be offered
            parsed = autostart.parse(text, keep_localized=True)
            candidate = Candidate(path, parsed, role_id=role_id, tags=tags)
            kept, reason = _keep(candidate, wanted)
            candidate.kept = kept
            candidate.reason = reason
            seen[path.name] = candidate
            order.append(path.name)

    if current_id and current_id in seen:
        seen[current_id].current = True
    elif current_id and not check_desktop_id(current_id):
        path = find_desktop_file(current_id, env)
        if path is None:
            # The association names a file that is not there. That is worth a row of
            # its own: it is the reason links of this type do not open.
            seen[current_id] = Candidate(
                None, {"values": {"Name": current_id}, "localized": {},
                       "desktop_id": current_id},
                role_id=role_id, current=True, kept=False,
                reason="the association names a file that is not in any application "
                       "directory, so nothing can be launched for this type",
                tags=tags)
            order.append(current_id)

    listed = [seen[name] for name in order]
    kept = [item for item in listed if item.kept]
    kept.sort(key=lambda item: (not item.current, item.label.lower(), item.desktop_id))
    refused = [item for item in listed if not item.kept and item.current]
    return (kept + refused)[:MAX_CANDIDATES]


# ------------------------------------------------------------------ the tool


def query_argv(role_id: str, root: Optional[Path] = None) -> List[str]:
    """The read command for a role: ``xdg-mime query default <first mimetype>``."""
    wanted = role(role_id, root)
    return [MIME_TOOL, "query", "default", str(wanted["mimetypes"][0])]


def default_argv(role_id: str, desktop_file: str,
                 root: Optional[Path] = None) -> List[str]:
    """The write command for a role, with every mimetype it means in one call."""
    wanted = role(role_id, root)
    return [MIME_TOOL, "default", desktop_file,
            *[str(item) for item in wanted["mimetypes"]]]


def current(role_id: str, root: Optional[Path] = None,
            timeout: float = runner.DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """What handles a role right now, and how sure this module is of the answer.

    An empty answer from a successful query means nothing is set, which is a real
    state and not a failure. A missing ``xdg-mime`` is unverified, so the page says
    "could not be read" rather than showing an empty dropdown that looks like a
    choice.
    """
    argv = query_argv(role_id, root)
    outcome = runner.run(argv[0], argv[1:], timeout=timeout)
    value = outcome.stdout.strip().splitlines()[0].strip() if outcome.stdout.strip() else ""
    reason = outcome.reason
    if outcome.verdict == runner.OK and not value:
        reason = f"nothing is set as the default {role(role_id, root)['label'].lower()}"
    return {
        "role": role_id,
        "label": str(role(role_id, root)["label"]),
        "mimetypes": [str(item) for item in role(role_id, root)["mimetypes"]],
        "desktop_id": value,
        "verdict": outcome.verdict,
        "argv": list(outcome.argv),
        "reason": reason,
    }


def read_back(role_id: str, desktop_file: str, root: Optional[Path] = None,
              timeout: float = runner.DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Every mimetype of a role, queried after a write.

    Upstream's own ``set_browser_mime`` reads the association back and restores the
    original when the read-back disagrees (record: ``mime_tool.verify_and_restore``).
    This checks all of a role's mimetypes rather than one, because a write that took
    effect for ``text/html`` and not for ``x-scheme-handler/https`` leaves a page
    opening in one program and a link in another.
    """
    wanted = role(role_id, root)
    answers: Dict[str, str] = {}
    verdicts: Dict[str, str] = {}
    for mimetype in wanted["mimetypes"]:
        mimetype = str(mimetype)
        outcome = runner.run(MIME_TOOL, ["query", "default", mimetype], timeout=timeout)
        verdicts[mimetype] = outcome.verdict
        answers[mimetype] = outcome.stdout.strip() if outcome.verdict == runner.OK else ""
    agreed = [key for key, value in answers.items() if value == desktop_file]
    disagreed = {key: value for key, value in answers.items() if value != desktop_file}
    if disagreed and all(value == runner.UNVERIFIED for value in verdicts.values()):
        verdict = runner.UNVERIFIED
        reason = f"{MIME_TOOL} is not installed, so the change could not be read back"
    elif disagreed:
        verdict = runner.FAILED
        detail = ", ".join(f"{key} is still handled by {value or 'nothing'}"
                           for key, value in disagreed.items())
        reason = f"{MIME_TOOL} reported success but {detail}"
    else:
        verdict = runner.OK
        reason = f"{desktop_file} now handles {', '.join(agreed)}"
    return {"verdict": verdict, "reason": reason, "answers": answers,
            "verdicts": verdicts, "agreed": agreed, "disagreed": disagreed}


def set_role(role_id: str, desktop_file: str, root: Optional[Path] = None,
             env: Optional[Mapping[str, str]] = None,
             timeout: float = runner.DEFAULT_TIMEOUT,
             verify: bool = True) -> Dict[str, Any]:
    """Make ``desktop_file`` the default for a role, and read the result back.

    The verdict is the read-back's, not the command's: ``xdg-mime`` writes a line
    into ``~/.local/share/applications/mimeapps.list`` and exits 0 whether or not
    anything will honour it. A file name that is not in any application directory is
    refused before the command runs, because an association pointing at a missing
    file makes every link of that type fail to open -- and the tool would write it
    happily, since it only checks the name's form.
    """
    problems = check_desktop_id(desktop_file)
    if problems:
        raise DefaultsError("; ".join(problems))
    if find_desktop_file(desktop_file, env) is None:
        raise DefaultsError(
            f"{desktop_file} is not in any application directory, so this project will "
            f"not make it a default: the association would name a file the desktop "
            f"cannot find, and every link of this type would fail to open")

    argv = default_argv(role_id, desktop_file, root)
    outcome = runner.run(argv[0], argv[1:], timeout=timeout)
    result: Dict[str, Any] = {
        "role": role_id,
        "label": str(role(role_id, root)["label"]),
        "desktop_id": desktop_file,
        "argv": list(outcome.argv),
        "outcome": outcome.as_dict(),
        "verdict": outcome.verdict,
        "reason": outcome.reason,
        "readback": None,
    }
    if outcome.verdict == runner.FAILED:
        result["reason"] = outcome.reason or f"{MIME_TOOL} reported an error"
        return result
    if outcome.verdict == runner.UNVERIFIED:
        # There is nothing to read back with: the same tool does both halves.
        result["reason"] = outcome.reason
        return result
    if not verify:
        result["verdict"] = runner.UNVERIFIED
        result["reason"] = (f"{MIME_TOOL} exited 0 but the association was not read "
                            f"back, so this is unverified")
        return result

    back = read_back(role_id, desktop_file, root, timeout)
    result["readback"] = back
    result["verdict"] = back["verdict"]
    result["reason"] = back["reason"]
    return result


# -------------------------------------------------------------------- summary


def state(role_id: str, env: Optional[Mapping[str, str]] = None,
          root: Optional[Path] = None,
          timeout: float = runner.DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Everything the page needs for one row: the current value and the choices."""
    wanted = role(role_id, root)
    now = current(role_id, root, timeout)
    listed = candidates(role_id, env, root, current_id=now["desktop_id"] or None)
    return {
        "role": role_id,
        "label": str(wanted["label"]),
        "why": str(wanted["why"]),
        "evidence": str(wanted["evidence"]),
        "mimetypes": [str(item) for item in wanted["mimetypes"]],
        "current": now,
        "candidates": [item.as_dict() for item in listed],
        "refused_candidates": [item.as_dict() for item in listed if not item.kept],
        "tools": tools_present(),
        "query_argv": query_argv(role_id, root),
        "write_argv_example": default_argv(role_id, "<application>.desktop", root),
        "writable": tools_present()[MIME_TOOL],
    }


def summary(env: Optional[Mapping[str, str]] = None, root: Optional[Path] = None,
            timeout: float = runner.DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Every role at once, plus the roles the page explains instead of offering."""
    return {
        "roles": [state(role_id, env, root, timeout) for role_id in role_ids(root)],
        "unsettable": unsettable(root),
        "refusals": refusals(root),
        "settings_properties": list(settings_properties(root)),
        "read_order": read_order(root),
        "candidate_rules": candidate_rules(root),
        "tools": tools_present(),
        "verified_against": str(record(root)["verified_against"]),
    }
