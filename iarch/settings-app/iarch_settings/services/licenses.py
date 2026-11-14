# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The licenses, and the one source the About page and the notices document share.

The chain is deliberately short and every link in it is checked by something:

``branding/notices.json`` --(``python3 tools/notices.py --write``)-->
``THIRD_PARTY_NOTICES.md`` **and** ``data/licenses.json`` --(this module)-->
the About dialog's legal sections.

Part 4's acceptance asks that the About page and ``THIRD_PARTY_NOTICES.md`` come
from one source, and the strongest form of that is not a shared constant but a
shared *text*: :func:`notices_sections` reads the component blocks out of the
notices document itself, so the words in the dialog are the words in the document.
When a component has no block there, the section says so instead of quietly
rendering a second version -- a disagreement between the two files is a packaging
fault, and the sentence that names it is more useful than a paragraph nobody would
compare. :func:`check` runs ``tools/notices.py --check``, which is the command CI
runs, so the dialog can show whether the three files agree on this machine right
now.

The other half is the license *type* each section carries. ``Gtk.License`` has
eighteen members and the SPDX identifiers in ``data/licenses.json`` are not all
among them, so ``data/design/adwaita.json`` records both halves of that: which
identifier maps to which member, and which have no member and are shown as
``CUSTOM``. Mapping an identifier GTK does not name onto the nearest one it does
would state something false about somebody else's terms, and a license is the one
place where an approximation is not a simplification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import paths, version
from . import runner

NAME = "licenses.json"
"""The generated document in ``data/`` that lists every component."""

NOTICES_DOCUMENT = "THIRD_PARTY_NOTICES.md"
"""The document a person reads, rendered from the same source as :data:`NAME`."""

NOTICES_SOURCE = "branding/notices.json"
"""The one source both of the above are rendered from."""

CHECK_TOOL = "tools/notices.py"
"""The tool whose ``--check`` proves the three files agree."""

STYLE_RECORD = "adwaita.json"
"""Where the SPDX identifier to ``Gtk.License`` mapping is recorded."""

UNVERIFIED_DOCUMENT = "docs/UNVERIFIED.md"

_UNVERIFIED_ROW = re.compile(r"^\|\s*([A-Z]{2,6}-[0-9]{2})\s*\|")

#: A row whose item is struck through has been answered since it was written; the
#: document keeps it so the answer stays findable, but it is no longer unverified.
_ANSWERED = re.compile(r"^~~(.*?)~~\s*(.*)$", re.DOTALL)


class LicensesError(RuntimeError):
    """A license document this module cannot read. The message is the reason."""


# ------------------------------------------------------------------- records

_CACHE: Dict[str, Any] = {}


def _cached(key: str, load) -> Any:
    if key not in _CACHE:
        _CACHE[key] = load()
    return _CACHE[key]


def record(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/licenses.json``, parsed."""
    path = paths.data_file(NAME, root)

    def load() -> Dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LicensesError(
                f"{path} is missing; it is generated from {NOTICES_SOURCE} by "
                f"python3 {CHECK_TOOL} --write") from exc
        except json.JSONDecodeError as exc:
            raise LicensesError(f"{path} is not valid JSON: {exc}") from exc

    return _cached(f"licenses:{path}", load)


def mapping(root: Optional[Path] = None) -> Dict[str, Any]:
    """The ``licenses`` block of ``data/design/adwaita.json``."""
    path = paths.design_file(STYLE_RECORD, root)

    def load() -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))["licenses"]

    return _cached(f"mapping:{path}", load)


def product(root: Optional[Path] = None) -> Dict[str, Any]:
    """The product's own entry: name, license, maintainer, repository."""
    return dict(record(root)["product"])


def components(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every listed component, in the document's order."""
    return [dict(row) for row in record(root)["components"]]


def component(component_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """One component by id. Refuses an id the document does not list."""
    for row in components(root):
        if row.get("id") == component_id:
            return row
    raise LicensesError(
        f"{component_id} is not a component in {NAME}; the document lists "
        f"{len(components(root))}")


# ---------------------------------------------------------------- the mapping


def license_kind(identifier: str, root: Optional[Path] = None) -> str:
    """``mapped``, ``custom`` or ``composite``: how an identifier is shown.

    ``mapped`` means GTK names this license and supplies its own text. ``custom``
    means the license is real and single but GTK has no member for it, so the
    section carries this project's own text. ``composite`` means the identifier is a
    sentence rather than a license -- two licenses, a parenthetical, ``Varies per
    package``, or a ``TODO(verify)`` -- and it is quoted verbatim rather than
    paraphrased, because paraphrasing a statement about somebody else's terms
    replaces it with a guess.
    """
    table = mapping(root)
    text = str(identifier)
    if text in table["names"]:
        return "mapped"
    if text in table["custom_for"]:
        return "custom"
    return "composite"


def license_type(identifier: str, root: Optional[Path] = None) -> str:
    """The ``Gtk.License`` member an identifier is shown as, spelled for PyGObject."""
    table = mapping(root)
    text = str(identifier)
    if text in table["names"]:
        return str(table["names"][text])
    if text in table["custom_for"]:
        return str(table["custom"])
    # A composite identifier is not a license GTK can name, and UNKNOWN would claim
    # no license was specified when one was -- just not one of the eighteen.
    return str(table["custom"])


def unmapped_identifiers(root: Optional[Path] = None) -> List[str]:
    """Every identifier in the document that GTK has no member for.

    Returned so the About page can say how many sections carry their own text, and
    so a test can assert the set is the one the record describes rather than one
    that grew because somebody added a component with a new license.
    """
    return sorted({str(row["license"]) for row in components(root)
                   if license_kind(row["license"], root) != "mapped"})


# ------------------------------------------------------------------ sections


def notices_path(root: Optional[Path] = None) -> Path:
    """``THIRD_PARTY_NOTICES.md`` at the repository root."""
    return (root or paths.repo_root()) / NOTICES_DOCUMENT


def notices_text(root: Optional[Path] = None) -> str:
    """The notices document, verbatim."""
    path = notices_path(root)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LicensesError(f"{path} could not be read: {exc}") from exc


def notices_sections(root: Optional[Path] = None) -> Dict[str, str]:
    """The document's per-component blocks, keyed by component name.

    A block is everything from one ``### name`` heading to the next heading of the
    same level, which is the shape ``tools/notices.py`` renders. Reading the document
    rather than re-rendering it is what makes "one source" literal: the words in the
    dialog are the words in the file, and there is no second renderer to drift.
    """
    text = notices_text(root)
    found: Dict[str, str] = {}
    name: Optional[str] = None
    lines: List[str] = []
    for line in text.splitlines():
        if line.startswith("### "):
            if name is not None:
                found[name] = "\n".join(lines).strip()
            name = line[4:].strip()
            lines = []
            continue
        if line.startswith("## ") and name is not None:
            found[name] = "\n".join(lines).strip()
            name = None
            lines = []
            continue
        if name is not None:
            lines.append(line)
    if name is not None:
        found[name] = "\n".join(lines).strip()
    return found


def section_for(row: Mapping[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    """One component as an ``add_legal_section`` call's four arguments.

    The text is the notices document's own block for that component. When the
    document has no block, the section says so and carries the record's fields
    instead, because a dialog that showed nothing at all would hide the disagreement
    and a dialog that invented a paragraph would be the second renderer this design
    exists to avoid.
    """
    name = str(row.get("name") or row.get("id") or "")
    identifier = str(row.get("license") or "")
    blocks = notices_sections(root)
    text = blocks.get(name, "")
    missing = not text
    if missing:
        text = (f"{NOTICES_DOCUMENT} has no section for {name}, so this text comes from "
                f"{NAME} instead and the two files disagree.\n\n"
                f"License: {identifier}\n"
                f"Copyright: {row.get('copyright') or 'not recorded'}\n"
                f"Upstream: {row.get('upstream') or 'not recorded'}\n"
                f"Purpose: {row.get('purpose') or 'not recorded'}")
    open_items = [str(item) for item in row.get("open_items") or []]
    if open_items:
        text += ("\n\nOpen verification items: " + ", ".join(open_items)
                 + f" in {UNVERIFIED_DOCUMENT}")
    return {
        "title": name,
        "copyright": str(row.get("copyright") or ""),
        "license_type": license_type(identifier, root),
        "license": text,
        "identifier": identifier,
        "kind": license_kind(identifier, root),
        "unverified": bool(row.get("unverified")),
        "component_id": str(row.get("id") or ""),
        "upstream": str(row.get("upstream") or ""),
        "used_by": [str(item) for item in row.get("used_by") or []],
        "open_items": open_items,
        "from_notices_document": not missing,
    }


def legal_sections(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The product's own license first, then every component.

    Order matters here the way it does in the notices document: what this project is
    licensed under is the first thing a person is entitled to know, and the
    components it is built from follow.
    """
    own = product(root)
    identifier = str(own.get("license") or "")
    license_file = (root or paths.repo_root()) / str(own.get("license_file") or "LICENSE.txt")
    try:
        text = license_file.read_text(encoding="utf-8")
    except OSError:
        text = (f"{license_file} could not be read, so this section names the license "
                f"instead of quoting it: {identifier}")
    first = {
        "title": str(own.get("name") or ""),
        "copyright": str(record(root).get("_copyright") or ""),
        "license_type": license_type(identifier, root),
        "license": text,
        "identifier": identifier,
        "kind": license_kind(identifier, root),
        "unverified": False,
        "component_id": "product",
        "upstream": str(own.get("repository") or ""),
        "used_by": [],
        "open_items": [],
        "from_notices_document": False,
    }
    return [first, *[section_for(row, root) for row in components(root)]]


# --------------------------------------------------------------------- check


def check_argv(root: Optional[Path] = None) -> List[str]:
    """The command that proves the three files agree."""
    return [str((root or paths.repo_root()) / CHECK_TOOL), "--check"]


def check(root: Optional[Path] = None,
          timeout: float = runner.DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Run ``tools/notices.py --check`` and report what it said.

    A read-only check of generated files, run with the current interpreter through
    :func:`runner.python_tool` because the tools in this repository are not installed
    binaries yet. The verdict is the runner's three-way one, so a checkout without a
    working interpreter answers *unverified* rather than claiming the files agree.
    """
    tool = (root or paths.repo_root()) / CHECK_TOOL
    outcome = runner.python_tool(tool, ["--check"], timeout=timeout)
    detail = (outcome.stdout + "\n" + outcome.stderr).strip()
    lines = [line for line in detail.splitlines() if line.strip()]
    reason = outcome.reason or (lines[-1] if lines else "")
    return {
        "verdict": outcome.verdict,
        "argv": [str(part) for part in outcome.argv],
        "reason": reason,
        "detail": detail,
        "source": NOTICES_SOURCE,
        "documents": [NOTICES_DOCUMENT, NAME],
    }


def agree(root: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """Whether every component has a block in the notices document.

    This is the half of "one source" that does not need a subprocess: it compares the
    names in ``data/licenses.json`` with the headings in ``THIRD_PARTY_NOTICES.md`` and
    returns the names that are in one and not the other.
    """
    blocks = notices_sections(root)
    names = [str(row.get("name") or "") for row in components(root)]
    return (all(name in blocks for name in names),
            [name for name in names if name not in blocks])


# ---------------------------------------------------------------- unverified


def unverified_rows(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The claims this build could not verify, read out of the document that lists them.

    The About page shows how many are still open and names a few, because an
    application that has been honest about its own limits everywhere else should not
    become vague in the one dialog that asks what it is.

    A row whose item is struck through has been answered since it was written; the
    document keeps it so the answer stays findable. It comes back with ``answered``
    true and is not counted as open, because counting an answered claim as a limit of
    this build would be the opposite of the honesty the document exists for.
    """
    path = (root or paths.repo_root()) / UNVERIFIED_DOCUMENT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        match = _UNVERIFIED_ROW.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        item = cells[1] if len(cells) > 1 else ""
        struck = _ANSWERED.match(item)
        rows.append({
            "id": match.group(1),
            "claim": struck.group(1).strip() if struck else item,
            "answer": struck.group(2).strip() if struck else "",
            "answered": struck is not None,
            "why": cells[2] if len(cells) > 2 else "",
            "blocking": cells[3] if len(cells) > 3 else "",
        })
    return rows


def unverified_ids(root: Optional[Path] = None, include_answered: bool = False) -> List[str]:
    """The open ids, in the document's order.

    ``include_answered`` also returns the ids whose rows have been struck through, for
    a caller that wants the whole file rather than the part that still binds.
    """
    return [row["id"] for row in unverified_rows(root)
            if include_answered or not row["answered"]]


def open_items(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The rows that still bind this build."""
    return [row for row in unverified_rows(root) if not row["answered"]]


# ------------------------------------------------------------------- summary


def available(root: Optional[Path] = None,
              env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Everything the About page needs, including what it could not check."""
    own = product(root)
    agreed, missing = agree(root)
    return {
        "product": own,
        "version": version.read_version(root),
        "facts": version.facts(root, env),
        "components": len(components(root)),
        "sections": legal_sections(root),
        "unmapped": unmapped_identifiers(root),
        "notices_document": str(notices_path(root)),
        "notices_source": NOTICES_SOURCE,
        "agrees_with_document": agreed,
        "missing_from_document": missing,
        "unverified": open_items(root),
        "unverified_answered": [row for row in unverified_rows(root) if row["answered"]],
        "debug_info": version.debug_info(root, env),
    }
