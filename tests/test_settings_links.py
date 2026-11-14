#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the link rules, which are the only thing between a data file and a browser.

``services/links.py`` decides what this application is allowed to open. It is a small
module and the reason it exists at all is that the Contact page's rows come from a
JSON file a person can edit, so a window that handed whatever it found to the desktop
would be a way to run something by editing a document.

Four properties are asserted here, and each one is a rule the module's own docstring
claims:

* **The scheme is on an allowlist.** ``https``, ``mailto`` and ``tel`` are allowed;
  ``http``, ``javascript``, ``file``, ``data``, ``exec``, ``ftp``, ``ssh``, ``smb`` and
  ``vnc`` are refused with a reason. Not "everything except the dangerous ones" -- the
  other way round, so a scheme nobody thought about is refused by default.
* **No shell, ever.** The module does not import :mod:`subprocess` at all, and the only
  call it makes to open anything is ``Gio.AppInfo.launch_default_for_uri``, which takes
  a URI and a context and nothing else. This is checked by reading the module's own
  import list, because a test that ran the opener would need a desktop.
* **ASCII only, and checked rather than normalised.** A homoglyph, a bidi override or a
  zero-width character is refused, not cleaned up: normalising it would mean this module
  deciding what the person meant.
* **A refusal is a value until it has to be an exception.** :func:`check_uri` returns a
  verdict so a page can disable a row and say why; :func:`require_uri` raises, and is
  what a click handler calls.

:func:`portfolio_url` is called by a test on purpose. Validating the constant costs
nothing and catches the one failure that would be embarrassing: an edit that turns the
Contact page's primary button into a refused link. ``docs/UNVERIFIED.md`` SET-04 records
what still cannot be checked here, which is whether a browser opens.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings.services import contacts, links  # noqa: E402

MODULE_PATH = ROOT / "iarch" / "settings-app" / "iarch_settings" / "services" / "links.py"
CONTACTS_RECORD = json.loads((ROOT / "data" / "contacts.default.json").read_text(
    encoding="utf-8"))
CONTACTS_SCHEMA = json.loads((ROOT / "data" / "schemas" / "contacts.schema.json").read_text(
    encoding="utf-8"))


def module_imports() -> List[str]:
    """Every module ``links.py`` imports, read out of its syntax tree."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    found: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


class TestNoShellEver(unittest.TestCase):
    """The strongest property in the module, and the cheapest one to lose."""

    def test_the_module_does_not_import_a_way_to_run_a_command(self):
        imported = module_imports()
        for forbidden in ("subprocess", "os", "pty", "shlex", "commands"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported,
                                 f"links.py imports {forbidden}, so a URI could reach a "
                                 f"command line")

    def test_the_source_never_mentions_a_shell_keyword(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        for spelling in ("shell=True", "os.system", "popen", "execv", "spawn"):
            with self.subTest(spelling=spelling):
                self.assertNotIn(spelling, text.lower(),
                                 f"links.py contains {spelling!r}")

    def test_the_only_opener_is_the_desktops_own_uri_handler(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("launch_default_for_uri", text,
                      "the module has to open a URI through the desktop's own handler "
                      "resolution, which is the call GLib documents for exactly this")

    def test_the_record_rejects_a_subprocess_call_that_interprets_a_uri(self):
        record = json.loads((ROOT / "data" / "design" / "adwaita.json").read_text(
            encoding="utf-8"))
        rejected = [entry["spelling"] for entry in record["rejected"]]
        self.assertTrue(any("shell=True" in spelling for spelling in rejected),
                        "the surface record does not refuse a shell call, so nothing "
                        "records why links.py has no subprocess import")


class TestTheSchemeAllowlist(unittest.TestCase):
    """Allowed means listed, and everything else is refused by default."""

    def test_every_allowed_scheme_is_accepted(self):
        cases = {
            "https": "https://safari-official.vercel.app",
            "mailto": "mailto:somebody@example.com",
            "tel": "tel:+15551234567",
        }
        for scheme, uri in cases.items():
            with self.subTest(scheme=scheme):
                verdict = links.check_uri(uri)
                self.assertTrue(verdict.allowed, verdict.reason)
                self.assertEqual(scheme, verdict.scheme)

    def test_every_refused_scheme_is_refused_with_a_reason(self):
        cases = {
            "http": "http://example.com",
            "javascript": "javascript:alert(1)",
            "file": "file:///etc/passwd",
            "data": "data:text/html,<script>alert(1)</script>",
            "exec": "exec:/bin/sh",
            "ftp": "ftp://example.com/file",
            "ssh": "ssh://user@host",
            "smb": "smb://server/share",
            "vnc": "vnc://host:5900",
        }
        self.assertEqual(sorted(cases), sorted(links.REFUSED_SCHEMES),
                         "the record of refused schemes and the list the module enforces "
                         "are two copies of one decision")
        for scheme, uri in cases.items():
            with self.subTest(scheme=scheme):
                verdict = links.check_uri(uri)
                self.assertFalse(verdict.allowed, f"{scheme} was accepted")
                self.assertTrue(verdict.reason.strip(),
                                f"{scheme} was refused with no reason, so a row could not "
                                f"say why it is disabled")

    def test_a_scheme_nobody_listed_is_refused_by_default(self):
        for uri in ("gopher://example.com", "chrome://settings", "about:blank",
                    "ws://example.com", "magnet:?xt=urn:btih:abc", "irc://example.com"):
            with self.subTest(uri=uri):
                self.assertFalse(links.check_uri(uri).allowed,
                                 "an allowlist that accepts an unlisted scheme is not an "
                                 "allowlist")

    def test_a_uri_with_no_scheme_is_refused_rather_than_assumed(self):
        for uri in ("safari-official.vercel.app", "//example.com/path", "/etc/passwd",
                    "example.com", "somebody@example.com"):
            with self.subTest(uri=uri):
                verdict = links.check_uri(uri)
                self.assertFalse(verdict.allowed,
                                 "a scheme-relative or bare string would let the desktop's "
                                 "handler resolution decide what it means")

    def test_the_scheme_is_read_case_insensitively_but_not_loosely(self):
        self.assertTrue(links.check_uri("HTTPS://safari-official.vercel.app").allowed)
        self.assertFalse(links.check_uri("https:/example.com").allowed)
        self.assertFalse(links.check_uri("httpsx://example.com").allowed)


class TestTheShapeOfEachAllowedScheme(unittest.TestCase):
    """A scheme on the allowlist is not a free pass for the rest of the string."""

    def test_an_https_uri_needs_a_host_that_looks_like_one(self):
        for uri in ("https://", "https:///", "https://-bad.example.com",
                    "https://bad-.example.com", "https://exa mple.com",
                    "https://example..com"):
            with self.subTest(uri=uri):
                self.assertFalse(links.check_uri(uri).allowed, uri)

    def test_a_very_long_host_is_refused(self):
        host = ".".join(["a" * 60] * 6)
        verdict = links.check_uri(f"https://{host}/")
        self.assertFalse(verdict.allowed, "a host past the recorded length limit was "
                                          "accepted")

    def test_an_email_address_needs_the_shape_of_one(self):
        self.assertTrue(links.check_uri("mailto:a@b.co").allowed)
        for uri in ("mailto:", "mailto:@example.com", "mailto:somebody@",
                    "mailto:some one@example.com", "mailto:a@@b.co"):
            with self.subTest(uri=uri):
                self.assertFalse(links.check_uri(uri).allowed, uri)

    def test_a_telephone_number_needs_the_shape_of_one(self):
        self.assertTrue(links.check_uri("tel:+15551234567").allowed)
        for uri in ("tel:", "tel:++15551234567", "tel:1555-CALL-NOW",
                    "tel:" + "1" * 40):
            with self.subTest(uri=uri):
                self.assertFalse(links.check_uri(uri).allowed, uri)

    def test_non_ascii_is_refused_rather_than_normalised(self):
        for uri in ("https://exämple.com", "mailto:sömébody@example.com",
                    "https://example.com/\u202epath", "https://\u0435xample.com"):
            with self.subTest(uri=repr(uri)):
                self.assertFalse(links.check_uri(uri).allowed,
                                 "an internationalised or bidi-override string was "
                                 "accepted; normalising it would mean this module deciding "
                                 "what the person meant")

    def test_a_control_character_is_refused(self):
        for uri in ("https://example.com/a\nb", "https://example.com/\x00",
                    "https://example.com/ path", "https://example.com/\x1b[31m"):
            with self.subTest(uri=repr(uri)):
                self.assertFalse(links.check_uri(uri).allowed)

    def test_a_uri_past_the_length_limit_is_refused(self):
        long_uri = "https://example.com/" + "a" * links.MAX_URI_LENGTH
        self.assertFalse(links.check_uri(long_uri).allowed,
                         "the recorded length limit is not enforced")


class TestAVerdictIsAValue(unittest.TestCase):
    """A page disables a row and says why; only a click handler raises."""

    def test_check_never_raises(self):
        for value in (None, "", 0, [], {}, object(), "   ", "\x00", "https://example.com"):
            with self.subTest(value=repr(value)):
                verdict = links.check_uri(value)
                self.assertIsInstance(verdict.allowed, bool)
                self.assertIsInstance(verdict.reason, str)

    def test_require_raises_on_a_refused_uri_and_returns_the_validated_string(self):
        self.assertEqual("https://safari-official.vercel.app",
                         links.require_uri("https://safari-official.vercel.app"))
        for value in ("", None, "javascript:alert(1)", "http://example.com"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(links.LinkError):
                    links.require_uri(value)

    def test_an_empty_value_is_distinguishable_from_a_refused_one(self):
        """An empty row is hidden; a refused one is shown disabled and says why."""
        self.assertTrue(links.is_empty(None))
        self.assertTrue(links.is_empty("   "))
        self.assertFalse(links.is_empty("https://example.com"))
        self.assertFalse(links.check_uri(None).allowed)
        self.assertFalse(links.check_uri("   ").allowed)
        self.assertNotEqual(links.check_uri(None).reason, links.check_uri("  ").reason,
                            "a value that is not text and a value that is blank text are "
                            "different mistakes and a row should not describe them alike")

    def test_the_verdict_carries_the_uri_it_judged(self):
        verdict = links.check_uri("https://safari-official.vercel.app/path")
        self.assertEqual("https://safari-official.vercel.app/path", verdict.uri)
        refused = links.check_uri("javascript:alert(1)")
        self.assertFalse(refused.allowed)
        self.assertEqual("javascript", refused.scheme,
                         "a refusal that does not name the scheme cannot explain itself")


class TestTheOpenerGetsTheValidatedString(unittest.TestCase):
    """SET-04's checkable half: what is validated is what is handed over."""

    def test_the_opener_receives_exactly_the_validated_uri(self):
        seen: List[str] = []
        links.open_uri("https://safari-official.vercel.app", opener=seen.append)
        self.assertEqual(["https://safari-official.vercel.app"], seen)

    def test_a_refused_uri_raises_before_it_can_reach_the_opener(self):
        """``open_uri`` validates through ``require_uri``, which is the raising half."""
        seen: List[str] = []

        def record(uri: str) -> bool:
            seen.append(uri)
            return True

        for uri in ("javascript:alert(1)", "file:///etc/passwd", "http://example.com",
                    "", "not a uri", None):
            with self.subTest(uri=repr(uri)):
                with self.assertRaises(links.LinkError):
                    links.open_uri(uri, opener=record)
        self.assertEqual([], seen, "a refused URI reached the opener")

    def test_surrounding_whitespace_is_stripped_before_the_check_not_after(self):
        seen: List[str] = []

        def record(uri: str) -> bool:
            seen.append(uri)
            return True

        self.assertTrue(links.open_uri("  https://example.com  ", opener=record))
        self.assertEqual(["https://example.com"], seen,
                         "the opener got a string with whitespace on it, so what was "
                         "validated and what was opened are not the same string")

    def test_whitespace_inside_the_uri_is_refused_rather_than_stripped(self):
        for uri in ("https://exa mple.com", "https://example.com/a b",
                    "https://example.com/\npath"):
            with self.subTest(uri=repr(uri)):
                self.assertFalse(links.check_uri(uri).allowed,
                                 "a space inside a URI is where a handler's own parsing "
                                 "starts to guess")

    def test_an_opener_that_fails_is_reported_as_a_failure_not_a_success(self):
        def refuses(_uri: str) -> bool:
            return False

        self.assertFalse(links.open_uri("https://example.com", opener=refuses))

    def test_the_default_opener_turns_a_missing_toolkit_into_a_sentence(self):
        """SET-04's other half: what a person sees when there is no desktop to ask.

        The toolkit is absent in this sandbox, which is the same answer CI gets, so the
        branch that matters most is the one that can actually be exercised here.
        """
        try:
            import gi  # noqa: F401
            have_toolkit = True
        except ImportError:
            have_toolkit = False
        if have_toolkit:
            self.skipTest("a graphical toolkit is installed, so the refusal branch cannot "
                          "be reached")
        with self.assertRaises(links.LinkError) as caught:
            links._gio_opener("https://safari-official.vercel.app")
        message = str(caught.exception)
        self.assertIn("copy", message.lower(),
                      "the sentence has to offer the alternative the Contact page has a "
                      "button for, not just report the failure")


class TestTheAddressAgreesEverywhereItIsWritten(unittest.TestCase):
    """One address, three places, and no way to change one of them alone."""

    def test_the_constant_the_record_and_the_row_all_carry_the_same_address(self):
        record_url = CONTACTS_RECORD["portfolio"]["url"]
        row_url = next(row["value"] for row in CONTACTS_RECORD["rows"]
                       if row["kind"] == "portfolio")
        self.assertEqual(links.PORTFOLIO_URL, record_url)
        self.assertEqual(links.PORTFOLIO_URL, row_url)
        self.assertEqual(links.PORTFOLIO_URL, links.portfolio_url())

    def test_the_schema_pattern_accepts_the_address_and_refuses_a_downgrade(self):
        pattern = CONTACTS_SCHEMA["properties"]["portfolio"]["properties"]["url"]["pattern"]
        self.assertRegex(links.PORTFOLIO_URL, pattern)
        self.assertNotRegex("http://safari-official.vercel.app", pattern,
                            "the schema pattern would accept a plain-http address")

    def test_the_contact_page_shows_the_row_the_constant_describes(self):
        visible = contacts.visible_rows()
        self.assertEqual(1, len(visible))
        self.assertEqual(links.PORTFOLIO_URL, visible[0]["value"])
        self.assertTrue(visible[0]["allowed"])
        self.assertEqual(links.ALLOWED_SCHEMES[0], visible[0]["scheme"])

    def test_portfolio_url_validates_the_constant_so_an_edit_fails_the_build(self):
        """The one failure that would be embarrassing: a primary button that is refused."""
        self.assertEqual(links.PORTFOLIO_URL, links.portfolio_url())
        self.assertTrue(links.check_uri(links.PORTFOLIO_URL).allowed)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
