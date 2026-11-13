# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Opening a link safely, and the one place the portfolio URL is written.

The Contact page hands this module a string that came from a JSON file a person
can edit, and asks for it to be opened. Everything in here exists to make that
request safe:

* **Three schemes, nothing else.** ``https``, ``mailto`` and ``tel``. A
  ``javascript:`` URI, a ``file:`` URI, an ``exec:`` URI and a scheme-relative
  ``//host/path`` are all refused with a reason, because the desktop's own handler
  resolution -- which is what this project delegates to -- would otherwise decide
  what a hand-edited string is allowed to do.
* **ASCII only.** An internationalised host arrives as punycode or not at all. A
  contact value containing a homoglyph, a bidi override or a zero-width character
  is refused rather than normalised, because normalising it would mean this module
  deciding what the person meant.
* **No shell, ever.** The module does not import :mod:`subprocess` at all, and
  ``tests/test_settings_links.py`` asserts that it does not: a URL that reached a
  shell would be an injection, and the only call used to open one is
  ``Gio.AppInfo.launch_default_for_uri`` (GNOME/glib@main:gio/gappinfo.h:279),
  which takes a URI and a context and nothing else.
* **A refusal is a value, not an exception, until it has to be.** :func:`check_uri`
  returns a :class:`Verdict` so a page can disable a row and say why;
  :func:`require_uri` raises, and is what the click handler calls.

``PORTFOLIO_URL`` is the constant the work order asks for: the portfolio address
lives here, in ``data/contacts.default.json``, and in ``README.md``, and a test
asserts all three agree. Changing it is a one-line edit in this file plus a
regeneration of the defaults.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional
from urllib.parse import urlsplit

#: The portfolio address. One constant, referenced by the Contact page, by the
#: shipped defaults in ``data/contacts.default.json`` and by ``README.md``.
PORTFOLIO_URL = "https://safari-official.vercel.app"

#: The schemes this project will hand to the desktop. Everything else is refused.
ALLOWED_SCHEMES = ("https", "mailto", "tel")

#: Refused explicitly, so the reason a person sees names the scheme they tried.
#: ``http`` is not here on purpose: a contact link that is not TLS is not worth
#: the risk of a downgrade, and every real target here has an ``https`` address.
REFUSED_SCHEMES = ("http", "javascript", "file", "data", "exec", "ftp", "ssh", "smb", "vnc")

#: A URI longer than this is refused. No real contact link approaches it, and an
#: unbounded string is a way to make a handler do something expensive.
MAX_URI_LENGTH = 2048

#: One DNS label, and the whole host, kept inside the documented limits so a
#: pathological value is refused here instead of by a resolver.
MAX_LABEL_LENGTH = 63
MAX_HOST_LENGTH = 253

_HOSTNAME = re.compile(r"^(?=.{1,%d}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
                       r"(\.([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?))+$" % MAX_HOST_LENGTH)
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")
_TEL = re.compile(r"^\+[0-9]{1,15}$|^[0-9]{3,15}$")

#: Characters that must not appear anywhere in a URI this module accepts.
_CONTROL = re.compile(r"[\x00-\x20\x7f]")


class LinkError(ValueError):
    """A link that this project refuses to open. The message is the reason."""


class Verdict:
    """Whether a URI may be opened, and the reason it may not.

    A small class rather than a NamedTuple so the reason can be a sentence: the
    Contact page shows it as a disabled row's subtitle, and "invalid" is not a
    sentence anyone can act on.
    """

    __slots__ = ("allowed", "scheme", "reason", "uri")

    def __init__(self, allowed: bool, scheme: str, reason: str, uri: str = "") -> None:
        self.allowed = allowed
        self.scheme = scheme
        self.reason = reason
        self.uri = uri

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Verdict(allowed={self.allowed}, scheme={self.scheme!r}, reason={self.reason!r})"

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "scheme": self.scheme, "reason": self.reason,
                "uri": self.uri}


REFUSED = Verdict(False, "", "no value")


def _refused(reason: str, scheme: str = "", uri: str = "") -> Verdict:
    return Verdict(False, scheme, reason, uri)


def _allowed(scheme: str, uri: str) -> Verdict:
    return Verdict(True, scheme, "", uri)


def check_uri(text: object) -> Verdict:
    """Decide whether ``text`` may be opened, and say why it may not.

    Never raises. A value that is not a string is refused rather than coerced,
    because a JSON file can hold a number or a list where a person meant a link,
    and inventing a URI out of ``str(value)`` is how a row ends up opening
    something nobody wrote.
    """
    if not isinstance(text, str):
        return _refused(f"a link has to be text; this value is {type(text).__name__}")

    raw = text
    stripped = raw.strip()
    if not stripped:
        return _refused("the link is empty")
    if len(stripped) > MAX_URI_LENGTH:
        return _refused(f"the link is longer than {MAX_URI_LENGTH} characters")
    if stripped != raw:
        # Leading and trailing whitespace is tolerated (a pasted value often has
        # it); whitespace anywhere else is not, because a space inside a URI is
        # where a handler's own parsing starts to guess.
        raw = stripped
    if _CONTROL.search(raw):
        return _refused("the link contains a space or a control character")
    for index, character in enumerate(raw):
        if ord(character) > 127:
            name = unicodedata.name(character, "unnamed character")
            return _refused(
                f"the link contains a non-ASCII character at position {index} "
                f"({name!r}); an internationalised address has to be written as "
                f"punycode")
    if "\\" in raw:
        return _refused("the link contains a backslash")

    scheme, separator, rest = raw.partition(":")
    scheme_lower = scheme.lower()
    if not separator:
        return _refused("the link has no scheme; write https://, mailto: or tel:")
    if scheme_lower not in ALLOWED_SCHEMES and not rest:
        # A bare word with a colon is not a scheme anybody registered, and saying
        # "no scheme" would be the wrong sentence: it has one, it is just not ours.
        return _refused(f"the {scheme_lower}: scheme is not one of "
                        f"{', '.join(ALLOWED_SCHEMES)}", scheme_lower, raw)
    if not rest:
        return _refused(f"the {scheme_lower}: link has nothing after the scheme",
                        scheme_lower, raw)
    if scheme_lower in REFUSED_SCHEMES:
        return _refused(f"the {scheme_lower}: scheme is not one this project opens",
                        scheme_lower, raw)
    if scheme_lower not in ALLOWED_SCHEMES:
        return _refused(
            f"the {scheme_lower}: scheme is not one of "
            f"{', '.join(ALLOWED_SCHEMES)}", scheme_lower, raw)

    parts = urlsplit(raw)
    if scheme_lower == "https":
        return _check_https(parts, raw)
    if scheme_lower == "mailto":
        address = parts.path or raw[len("mailto:"):]
        if not _EMAIL.fullmatch(address):
            return _refused("the mailto: address is not one this project recognises",
                            scheme_lower, raw)
        return _allowed(scheme_lower, raw)
    number = parts.path or raw[len("tel:"):]
    if not _TEL.fullmatch(number):
        return _refused(
            "the tel: number may hold digits, a leading +, and nothing else",
            scheme_lower, raw)
    return _allowed(scheme_lower, raw)


def _check_https(parts, raw: str) -> Verdict:
    """The https half: a host that resolves to one place, and no embedded user."""
    if not parts.netloc:
        return _refused("the https: link has no host", "https", raw)
    if "@" in parts.netloc:
        return _refused(
            "the https: link carries a username or password; a link this project "
            "ships does not", "https", raw)
    host = parts.hostname or ""
    if not host:
        return _refused("the https: link has an empty host", "https", raw)
    if host.startswith(".") or host.endswith("."):
        return _refused(f"the host {host!r} starts or ends with a dot", "https", raw)
    if any(len(label) > MAX_LABEL_LENGTH for label in host.split(".")):
        return _refused(f"the host {host!r} has a label longer than "
                        f"{MAX_LABEL_LENGTH} characters", "https", raw)
    if not _HOSTNAME.fullmatch(host):
        return _refused(
            f"the host {host!r} is not a hostname this project accepts: letters, "
            f"digits, hyphens and dots, at least two labels", "https", raw)
    for segment_name, segment in (("path", parts.path), ("query", parts.query),
                                  ("fragment", parts.fragment)):
        if _CONTROL.search(segment):
            return _refused(f"the {segment_name} contains a space or control character",
                            "https", raw)
    return _allowed("https", raw)


def require_uri(text: object) -> str:
    """Return the URI to open, or raise :class:`LinkError` naming the reason."""
    verdict = check_uri(text)
    if not verdict.allowed:
        raise LinkError(verdict.reason)
    return verdict.uri


def is_empty(text: object) -> bool:
    """True for the placeholder rows the shipped defaults leave blank.

    A row whose value is empty is hidden rather than shown disabled: the defaults
    file ships five kinds with nothing in them so Safari can fill in the ones he
    uses, and a Contact page full of grey rows he cannot click is not a page.
    """
    return not isinstance(text, str) or not text.strip()


#: The signature an opener has: ``opener(uri) -> bool``.
Opener = Callable[[str], bool]


def _gio_opener(uri: str) -> bool:
    """Hand the URI to the desktop's own handler resolution.

    ``Gio.AppInfo.launch_default_for_uri`` is the call the work order names and
    the only one this project uses (GNOME/glib@main:gio/gappinfo.h:279). It takes
    a URI and an optional launch context; it does not take a shell, a program
    name or an argument list, so there is no way for the value to become a
    command.
    """
    try:
        from gi.repository import Gio  # imported here: no display needed to validate
    except (ImportError, ValueError) as exc:
        raise LinkError(
            "cannot open a link without a graphical toolkit: "
            f"{exc}. Copy it instead -- the Contact page has a button for that."
        ) from exc
    try:
        return bool(Gio.AppInfo.launch_default_for_uri(uri, None))
    except Exception as exc:  # noqa: BLE001 - GLib.Error and friends, all reported alike
        raise LinkError(f"the desktop refused to open {uri!r}: {exc}") from exc


def open_uri(text: object, opener: Optional[Opener] = None) -> bool:
    """Validate, then open. Returns True when the desktop accepted it.

    ``opener`` is injectable so a test can prove the validation happens before
    anything is handed over, and prove that what is handed over is exactly the
    validated string and not a value that was assembled on the way.
    """
    uri = require_uri(text)
    use = opener or _gio_opener
    return bool(use(uri))


def portfolio_url() -> str:
    """The portfolio address, validated like any other link.

    Validating the constant costs nothing and catches the one failure that would
    be embarrassing: an edit here that turns the primary button into a refused
    link. ``tests/test_settings_links.py`` calls this, so a broken constant fails
    the build rather than the click.
    """
    return require_uri(PORTFOLIO_URL)
