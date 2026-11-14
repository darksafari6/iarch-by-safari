# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Contact page: one link, five channels deliberately not shown, and the rule behind both.

``data/contacts.default.json`` carries six kinds of channel and a value for one of them. The
other five are empty, and the record's own note about the portfolio is the reason: every
social link and every contact detail is on the portfolio, so a second copy of an address in a
settings window would be a second place for it to go stale. This page therefore draws one
link and explains the five, rather than drawing five empty rows that look like a form nobody
filled in.

Two rules make a link safe to put on screen, and both are enforced in
:mod:`iarch_settings.services.links` rather than here:

* **The scheme is on an allowlist.** ``https``, ``mailto`` and ``tel`` are allowed; ``http``,
  ``javascript``, ``file``, ``data``, ``exec``, ``ftp``, ``ssh``, ``smb`` and ``vnc`` are
  refused outright. A settings window that opened whatever URI its data file happened to
  contain would be a way to run something by editing a JSON document.
* **The text is checked, not trusted.** A host is matched against the shape a hostname has,
  an address against the shape an email address has, a number against the shape a telephone
  number has, and a control character or a length past the recorded limits refuses the row.
  The verdict arrives with a reason, so a refused row can say why instead of disappearing.

A person's own copy of the file wins over the repository's, which is how the page can be
somebody else's contact page without this project storing anything about them: the same
merge rule the settings file uses, from :mod:`iarch.lib.configstore`.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from ..services import contacts, links
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "contact"


# --------------------------------------------------------------------- readers


def data() -> Dict[str, Any]:
    """Everything the page needs before it draws a row."""
    try:
        return contacts.available()
    except contacts.ContactsError:
        return {}


def display_name() -> str:
    """Whose page this is."""
    return str(data().get("display_name") or contacts.display_name())


def role_text() -> str:
    """What they made."""
    return str(data().get("role") or contacts.role())


def portfolio_uri() -> str:
    """The one address this page opens."""
    return str(data().get("portfolio", {}).get("url") or links.portfolio_url())


def portfolio_note() -> Optional[str]:
    """The record's own sentence about why one link is enough."""
    note = (data().get("portfolio") or {}).get("note")
    return str(note) if note else None


def portfolio_button_text() -> str:
    """The label the record gives the button, so the page does not invent one."""
    return str((data().get("portfolio") or {}).get("button_label") or "Visit the portfolio")


def source_text() -> str:
    """Where the rows came from, and whose copy wins."""
    return (f"{data().get('source') or 'data/contacts.default.json'}, and a copy of your own "
            f"in the configuration directory wins over it -- the same merge rule the "
            f"settings file uses")


def policy_text() -> str:
    """The scheme allowlist, as one sentence."""
    return ("a link row may only be " + ", ".join(links.ALLOWED_SCHEMES) + "; "
            + ", ".join(links.REFUSED_SCHEMES) + " are refused outright, because a settings "
            "window that opened whatever its data file happened to contain would be a way to "
            "run something by editing a JSON document")


def checks_text() -> str:
    """What is checked about a link besides its scheme."""
    return ("the host is matched against the shape a hostname has, an address against the "
            "shape an email address has and a number against the shape a telephone number "
            "has; a control character, or a length past the recorded limits, refuses the row "
            "-- and the refusal arrives with a reason, so a row can say why instead of "
            "disappearing")


def problems_text() -> Optional[str]:
    """Anything the record's own load complained about."""
    found = data().get("problems") or []
    return "; ".join(str(item) for item in found) if found else None


def shown_count_text() -> str:
    """How many channels are shown, hidden and refused."""
    found = data()
    return (f"{len(found.get('shown') or [])} shown, "
            f"{len(found.get('hidden') or [])} hidden and "
            f"{len(found.get('refused') or [])} refused")


def _hidden_reader(kind: str) -> Callable[[], str]:
    """Build the reader one hidden channel's row shows."""

    def read() -> str:
        for row in data().get("hidden") or []:
            if row.get("kind") == kind:
                reason = str(row.get("reason") or "")
                if reason:
                    return reason
                return ("the record holds no value for this channel, and the portfolio "
                        "carries every social link and contact detail -- so a second copy "
                        "here would be a second place for it to go stale")
        return "this channel is not in the record"

    read.__name__ = f"hidden_{kind}"
    read.__doc__ = f"Why the {kind} channel is not shown."
    return read


def hidden_rows() -> List[Row]:
    """One row per channel the record hides, with the reason."""
    rows: List[Row] = []
    for row in data().get("hidden") or []:
        kind = str(row.get("kind") or "")
        if not kind:
            continue
        rows.append(Row(
            "state", str(row.get("label") or kind.title()),
            source=f"contact.hidden_{kind}",
            icon=str(row.get("icon") or "view-conceal-symbolic"),
            subtitle="Hidden, not missing: the row says why rather than leaving a gap",
            keywords=(kind, str(row.get("label") or ""), "hidden", "contact", "channel")))
    if not rows:
        rows.append(Row(
            "state", "Nothing hidden", source="contact.shown_count_text",
            icon="object-select-symbolic",
            subtitle="Every channel in the record is shown",
            keywords=("hidden", "none", "channels")))
    return rows


def refused_rows() -> List[Row]:
    """One row per channel the record shows but the link rules refuse."""
    rows: List[Row] = []
    for row in data().get("refused") or []:
        kind = str(row.get("kind") or "")
        rows.append(Row(
            "state", str(row.get("label") or kind.title()),
            source=f"contact.refused_{kind or 'row'}", icon="dialog-warning-symbolic",
            subtitle="Shown as refused, because a row that vanished would look like a "
                     "channel this project never had",
            keywords=(kind, "refused", "scheme", "link")))
    return rows


def _refused_reader(kind: str) -> Callable[[], str]:
    def read() -> str:
        for row in data().get("refused") or []:
            if row.get("kind") == kind:
                return str(row.get("reason") or "the link rules refused this address")
        return "the link rules refused this address"

    read.__name__ = f"refused_{kind}"
    read.__doc__ = f"Why the {kind} row is refused."
    return read


for _row in contacts.hidden_rows():
    globals()[f"hidden_{_row.get('kind')}"] = _hidden_reader(str(_row.get("kind")))
for _row in contacts.refused_rows():
    globals()[f"refused_{_row.get('kind')}"] = _refused_reader(str(_row.get("kind")))
del _row


# ------------------------------------------------------------------- the action


def open_portfolio() -> bool:
    """Open the one address, through the same rule every link in this product is checked by.

    A link row's action takes nothing -- the row *is* the whole request -- so the address is
    read here rather than passed in, and :func:`links.open_uri` refuses it again on the way
    out: a URI that was allowed when the plan was built is checked once more when it is
    opened, because the data file can change while the window is up.
    """
    return links.open_uri(portfolio_uri())


def copy_portfolio() -> str:
    """Put the one address on the clipboard, and say what was copied.

    A page-local zero-argument wrapper, because :func:`contacts.copy_value` takes the row
    and a button's action takes nothing: which row is this page's decision, not the person's.
    """
    shown = data().get("shown") or []
    return contacts.copy_value(shown[0]) if shown else ""


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Contact page, as data."""
    spec = registry_page(PAGE_ID)
    refused = refused_rows()

    who = Group(
        "Who made this",
        Row("state", "Name", icon="avatar-default-symbolic", source="contact.display_name",
            keywords=("name", "safari", "author", "maintainer", "contact")),
        Row("state", "Role", icon="user-info-symbolic", source="contact.role_text",
            keywords=("role", "creator", "iarch", "contact")),
        Row("link", portfolio_button_text(), uri_source="contact.portfolio_uri",
            action="contact.open_portfolio", icon="web-browser-symbolic",
            subtitle="The one address this page opens, and the reason there is only one",
            keywords=("portfolio", "website", "link", "contact", "social", "https")),
        Row("button", "Copy the address", action="contact.copy_portfolio",
            icon="edit-copy-symbolic",
            subtitle="For a person who would rather paste it somewhere than open it",
            keywords=("copy", "clipboard", "address", "portfolio")),
        Row("state", "Why one link", icon="dialog-information-symbolic",
            source="contact.portfolio_note",
            subtitle="The record's own sentence, not a paraphrase of it",
            keywords=("portfolio", "note", "social links", "contact details")),
        description="One link, five channels deliberately not shown, and a rule that decides "
                    "which is which.",
        style_classes=("iarch-glass-card",),
    )

    channels = Group(
        "Channels not shown",
        Row("expander", "Five, and why", rows=tuple(hidden_rows()),
            icon="view-conceal-symbolic",
            subtitle="Hidden rather than absent, so the page does not look like a form "
                     "nobody filled in",
            keywords=("hidden", "email", "github", "instagram", "tiktok", "whatsapp",
                      "channels")),
        Row("state", "The count", icon="dialog-information-symbolic",
            source="contact.shown_count_text",
            keywords=("shown", "hidden", "refused", "count")),
        description="A channel the record marks hidden is one this page must not draw, and a "
                    "channel it refuses is one this page must say it refuses.",
    )

    groups: List[Group] = [who, channels]
    if refused:
        groups.append(Group(
            "Refused",
            Row("expander", "Shown as refused", rows=tuple(refused),
                icon="dialog-warning-symbolic",
                subtitle="A row that vanished would look like a channel this project never had",
                keywords=("refused", "scheme", "link", "contact")),
            description="The link rules refused these, and the refusal is drawn rather than "
                        "swallowed.",
        ))

    groups.append(Group(
        "The rules behind a link",
        Row("state", "Which schemes are allowed", icon="insert-link-symbolic",
            source="contact.policy_text", keywords=("scheme", "https", "mailto", "tel",
                                                    "allowlist", "refused")),
        Row("state", "What else is checked", icon="object-select-symbolic",
            source="contact.checks_text",
            subtitle="Enforced in services/links.py, not here, so a second window that opens "
                     "a link is checked by the same rule",
            keywords=("host", "email", "tel", "control character", "length", "verdict")),
        Row("state", "Where the rows come from", icon="document-save-symbolic",
            source="contact.source_text", keywords=("contacts.default.json", "source",
                                                    "merge", "your copy")),
        Row("state", "Anything the load complained about", icon="dialog-warning-symbolic",
            source="contact.problems_text", keywords=("problems", "load", "record")),
        description="A link is data, and data that opens something is checked in one place.",
    ))

    return PagePlan(
        PAGE_ID, spec.label, *groups,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("Every social link and contact detail is on the portfolio: this page "
                   "carries one address on purpose, because a second copy of an address is a "
                   "second place for it to go stale.",
                   kind="info", icon="dialog-information-symbolic"),
        ),
        header_actions=(
            Row("state", "Channels", icon="avatar-default-symbolic",
                source="contact.shown_count_text", keywords=("channels", "contact")),
        ),
    )
