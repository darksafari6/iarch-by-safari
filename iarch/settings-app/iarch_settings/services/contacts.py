# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Contact page's data: who made this, and how to reach them.

The document is ``data/contacts.default.json``, which the installer copies the shape
of and the user edits -- every row below the first ships with an empty value on
purpose, so the person who installs this fills in the ones they use and the page
hides the rest. Three rules follow from that, and they are the whole module:

* **An empty value is not a row.** :func:`visible_rows` drops it, so a shipped
  placeholder never becomes a button that opens nothing.
* **A value that is present is checked, not trusted.** Every one goes through
  :func:`iarch_settings.services.links.check_uri`, which allows ``https``, ``mailto``
  and ``tel`` and refuses everything else with a sentence. A refused row is *shown*,
  with that sentence as its subtitle and its action disabled, because a row that
  vanished would leave a person wondering whether the value they typed was saved.
* **The portfolio address is read, with one fallback.** It lives in the document, in
  :data:`iarch_settings.services.links.PORTFOLIO_URL` and in ``README.md``, and a test
  asserts the three agree; the constant is the fallback for a document that has no
  ``portfolio.url``, so the button always has something honest to open.

This module does not validate the document against ``data/schemas/contacts.schema.json``
at runtime. CI validates the shipped default against it, and what a hand-edited copy
needs at runtime is narrower: the shape the page reads, plus the link check that is
the only part of this data that can hurt anybody.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .. import paths
from . import links

NAME = "contacts"
"""The name :mod:`iarch.lib.configstore` uses: ``data/contacts.default.json`` for the
shipped defaults and ``~/.config/iarch/contacts.json`` for the user's copy. The
suffix is added by configstore, so naming it here would double it."""

DEFAULTS_NAME = f"{NAME}.default.json"
"""The shipped document in ``data/``, which the user's copy is merged over."""

#: The row kinds the shipped document uses, in the order the page lists them. A kind
#: is not a whitelist: an edited document may add one, and the page shows it with the
#: icon the row names.
KINDS = ("portfolio", "email", "github", "instagram", "tiktok", "whatsapp")

#: What a row's action is, by kind. ``open`` hands the value to the desktop through
#: :func:`links.open_uri`; ``copy`` puts it on the clipboard and says so, which is what
#: an address that is not a link is for.
#: Both name a function in *this* module, which is how a plan row points at something
#: a service does rather than at a string only the renderer knows. A
#: :class:`iarch_settings.pages.plan.Context` resolves a ``module.function`` name only
#: inside :data:`iarch_settings.services.MODULES`, so an action that named a widget or
#: the application object would not resolve at all -- and a row whose action does not
#: resolve is a row :meth:`Row.problems` reports.
ROW_ACTIONS = {"open": "contacts.open_row", "copy": "contacts.copy_value"}


class ContactsError(RuntimeError):
    """A contacts document this module cannot read. The message is the reason."""


# ------------------------------------------------------------------- loading


def load(root: Optional[Path] = None,
         env: Optional[Mapping[str, str]] = None) -> Tuple[Dict[str, Any], List[str]]:
    """The document, and every problem found reading it.

    Repository defaults with the user's file merged on top, through
    :func:`iarch.lib.configstore.load` -- the same merge the settings document gets,
    so a person who edits one row keeps the rest. A file that is not valid JSON is a
    problem naming the file and the line, because that file is hand-edited by design
    and a stray comma is an expected event; the page shows the sentence in a banner
    and falls back to the defaults rather than opening with no Contact page at all.
    """
    paths.add_repo_to_path()
    from iarch.lib import configstore  # noqa: PLC0415

    problems: List[str] = []
    try:
        document = configstore.load(NAME, paths.repo_root(), env)
    except configstore.ConfigError as exc:
        problems.append(str(exc))
        document = _defaults(root)
    except OSError as exc:
        problems.append(f"the contacts document could not be read: {exc}")
        document = _defaults(root)
    if not isinstance(document, Mapping):
        problems.append("the contacts document is not an object")
        document = _defaults(root)
    rows = document.get("rows")
    if rows is not None and not isinstance(rows, list):
        problems.append("contacts.rows is not a list, so no contact row can be shown")
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, Mapping):
            problems.append(f"contacts.rows[{index}] is not an object")
    return dict(document), problems


def _defaults(root: Optional[Path] = None) -> Dict[str, Any]:
    """The shipped document, read directly. Used when the user's copy cannot be."""
    import json  # noqa: PLC0415

    path = paths.data_file(DEFAULTS_NAME, root)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"display_name": "", "role": "", "rows": [],
                "portfolio": {"url": links.PORTFOLIO_URL, "button_label": "", "note": ""}}


def document(root: Optional[Path] = None,
             env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """The document alone, for a caller that reports problems itself."""
    return load(root, env)[0]


# -------------------------------------------------------------------- fields


def display_name(data: Optional[Mapping[str, Any]] = None,
                 root: Optional[Path] = None,
                 env: Optional[Mapping[str, str]] = None) -> str:
    """The name the page's header shows."""
    data = data if data is not None else document(root, env)
    return str(data.get("display_name") or "")


def role(data: Optional[Mapping[str, Any]] = None, root: Optional[Path] = None,
         env: Optional[Mapping[str, str]] = None) -> str:
    """The one-line description under the name."""
    data = data if data is not None else document(root, env)
    return str(data.get("role") or "")


def portfolio(data: Optional[Mapping[str, Any]] = None, root: Optional[Path] = None,
              env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """The portfolio block, with the constant as the address's fallback."""
    data = data if data is not None else document(root, env)
    block = data.get("portfolio")
    block = dict(block) if isinstance(block, Mapping) else {}
    url = str(block.get("url") or "").strip() or links.PORTFOLIO_URL
    return {
        "url": url,
        "button_label": str(block.get("button_label") or ""),
        "note": str(block.get("note") or ""),
    }


def portfolio_url(data: Optional[Mapping[str, Any]] = None,
                  root: Optional[Path] = None,
                  env: Optional[Mapping[str, str]] = None) -> str:
    """The address the portfolio button opens."""
    return portfolio(data, root, env)["url"]


# ---------------------------------------------------------------------- rows


def row_verdict(row: Mapping[str, Any]) -> Dict[str, Any]:
    """One row's link check as data: allowed, scheme, reason."""
    verdict = links.check_uri(row.get("value"))
    return {"allowed": bool(verdict.allowed), "scheme": verdict.scheme,
            "reason": verdict.reason, "uri": verdict.uri}


def rows(data: Optional[Mapping[str, Any]] = None, root: Optional[Path] = None,
         env: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """Every row in the document, checked, whether or not it will be shown.

    ``shown`` is false for an empty value, which is what the shipped placeholders
    are. ``action`` is empty for a row whose value was refused, which is how the
    renderer knows to draw it disabled: a row with no action is a row that explains
    itself rather than one that pretends to work.
    """
    data = data if data is not None else document(root, env)
    listed: List[Dict[str, Any]] = []
    for row in data.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        value = str(row.get("value") or "").strip()
        empty = links.is_empty(value)
        verdict = row_verdict(row) if not empty else {
            "allowed": False, "scheme": "", "reason": "", "uri": ""}
        listed.append({
            "kind": str(row.get("kind") or ""),
            "label": str(row.get("label") or row.get("kind") or ""),
            "subtitle": str(row.get("subtitle") or ""),
            "icon": str(row.get("icon") or ""),
            "value": value,
            "shown": not empty,
            "allowed": (not empty) and bool(verdict["allowed"]),
            "reason": "" if empty or verdict["allowed"] else verdict["reason"],
            "scheme": verdict["scheme"],
            "action": "" if empty or not verdict["allowed"] else ROW_ACTIONS["open"],
            "copy_action": "" if empty else ROW_ACTIONS["copy"],
        })
    return listed


def visible_rows(data: Optional[Mapping[str, Any]] = None,
                 root: Optional[Path] = None,
                 env: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """The rows the page draws: everything with a value, refused ones included."""
    return [row for row in rows(data, root, env) if row["shown"]]


def hidden_rows(data: Optional[Mapping[str, Any]] = None,
                root: Optional[Path] = None,
                env: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """The rows the page leaves out, so it can say how many and why."""
    return [row for row in rows(data, root, env) if not row["shown"]]


def refused_rows(data: Optional[Mapping[str, Any]] = None,
                 root: Optional[Path] = None,
                 env: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """The rows shown with a reason instead of an action."""
    return [row for row in visible_rows(data, root, env) if not row["allowed"]]


def open_row(row: Mapping[str, Any]) -> bool:
    """Open one row's value, or refuse. Returns whether the desktop was asked.

    The value is checked again here rather than trusted from the plan, because the
    document is a file a person edits while the application runs and the check that
    decided a row was clickable is not the check that should decide what is opened.
    """
    return links.open_uri(row.get("value"))


def copy_value(row: Mapping[str, Any]) -> str:
    """The string a copy action puts on the clipboard.

    Returning it rather than writing it is deliberate: the clipboard lives in GDK, and
    this module does not import GTK. The widget layer does the writing and shows the
    toast; a test can check the string without a display.
    """
    return str(row.get("value") or "")


def available(root: Optional[Path] = None,
              env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Everything the Contact page needs before it draws a row."""
    data, problems = load(root, env)
    listed = rows(data, root, env)
    return {
        "display_name": str(data.get("display_name") or ""),
        "role": str(data.get("role") or ""),
        "portfolio": portfolio(data, root, env),
        "rows": listed,
        "shown": [row for row in listed if row["shown"]],
        "hidden": [row for row in listed if not row["shown"]],
        "refused": [row for row in listed if row["shown"] and not row["allowed"]],
        "problems": problems,
        "kinds": list(KINDS),
        "source": str(paths.data_file("contacts.default.json", root)),
    }
