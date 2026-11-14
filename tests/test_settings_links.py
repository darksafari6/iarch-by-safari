#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the one module that hands a string to something outside this application.

``services/links.py`` is the only place in the settings application where a value that came
from a JSON file, a shell key or a record ends up being given to another program to act on.
Everything else writes a file this project owns or sends a verb to a socket. So the rules
here are the rules that matter, and ``docs/UNVERIFIED.md`` SET-04 names this file as the
proof of two of them: that the URI is validated before it is handed over, and that the
validated string is the string passed.

Four properties, each asserted in the direction it is written:

* **It is an allowlist.** Three schemes are opened -- ``https``, ``mailto``, ``tel`` -- and
  nine are named as refused. The nine are not the rule; the rule is that anything not in
  the three is refused, so a scheme nobody thought of is refused by default. A test that
  only walked the nine would pass on a tenth.
* **It never raises to answer a question.** ``check_uri`` returns a verdict, because a page
  has to be able to ask "may I draw this row as a link?" for every contact on every
  refresh, and an exception in a draw path is a window that does not open.
* **It raises to refuse an action.** ``open_uri`` goes through ``require_uri``, so a refused
  URI cannot reach an opener at all. That is the difference between a row that is disabled
  and a row that is enabled and does nothing.
* **It runs no program of its own.** The module imports no ``subprocess``, ``os``, ``pty``
  and ``shlex``, checked by reading its import list out of its syntax tree. Handing a URI to
  ``Gio.AppInfo.launch_default_for_uri`` is the desktop's own mechanism; building a command
  line out of a URI would be this project inventing a second one.

The reason strings are asserted too, and not only the booleans, because a refusal a person
cannot read is a refusal that looks like a bug. ``None`` and a string of spaces are both
empty and get *different* sentences: one says the value is not text, the other says the link
is empty, and a page that showed the same sentence for both would be wrong about one of them.
"""
from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings.services import contacts, links  # noqa: E402

MODULE_PATH = (ROOT / "iarch" / "settings-app" / "iarch_settings" / "services" / "links.py")
TREE = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
CONTACTS_RECORD = json.loads((ROOT / "data" / "contacts.default.json").read_text(
    encoding="utf-8"))

#: A scheme nobody listed. The point of an allowlist is that this is refused too.
UNLISTED_SCHEMES = ("gopher", "irc", "magnet", "ws", "chrome-extension", "about", "view-source")


class TestTheModuleRunsNoProgramOfItsOwn(unittest.TestCase):
    """The cheapest property to lose and the one everything else rests on."""

    def test_no_module_that_can_run_a_command_is_imported(self):
        imported = set()
        for node in ast.walk(TREE):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("subprocess", "os", "pty", "shlex", "commands", "popen2"):
            with self.subTest(module=banned):
                self.assertNotIn(banned, imported,
                                 f"links.py imports {banned}, and a URI handed to a command "
                                 f"line is a URI this project parsed into arguments")

    def test_the_only_way_out_is_the_desktops_own_mechanism(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("launch_default_for_uri", source,
                      "the module no longer uses the desktop's own handler, so it has "
                      "invented a second way to open a link")
        self.assertNotIn("system(", source)
        self.assertNotIn("Popen", source)


class TestItIsAnAllowlistAndNotADenylist(unittest.TestCase):
    """Three schemes are opened; everything else is refused, listed or not."""

    def test_exactly_three_schemes_are_allowed(self):
        self.assertEqual(("https", "mailto", "tel"), links.ALLOWED_SCHEMES)

    def test_the_nine_named_refusals_are_each_refused_with_a_readable_reason(self):
        self.assertEqual(9, len(links.REFUSED_SCHEMES))
        for scheme in links.REFUSED_SCHEMES:
            verdict = links.check_uri(f"{scheme}:something")
            with self.subTest(scheme=scheme):
                self.assertFalse(verdict.allowed, f"{scheme}: was allowed")
                self.assertEqual(scheme, verdict.scheme)
                self.assertIn(scheme, verdict.reason,
                              f"the reason for refusing {scheme}: does not name it, so a "
                              f"person cannot tell which link was the problem")
                self.assertTrue(verdict.reason.endswith("this project opens") or
                                "not one" in verdict.reason,
                                f"the reason is not a sentence a disabled row can show: "
                                f"{verdict.reason}")

    def test_a_scheme_nobody_listed_is_refused_by_default(self):
        """The nine are examples, not the rule."""
        for scheme in UNLISTED_SCHEMES:
            verdict = links.check_uri(f"{scheme}:something")
            with self.subTest(scheme=scheme):
                self.assertFalse(verdict.allowed,
                                 f"{scheme}: was opened, and it is in neither list, so the "
                                 f"allowlist has become a denylist")

    def test_a_uri_with_no_scheme_at_all_is_refused(self):
        for text in ("example.com", "not a uri", "/etc/passwd", "//host/path"):
            verdict = links.check_uri(text)
            with self.subTest(text=text):
                self.assertFalse(verdict.allowed)
                self.assertTrue(verdict.reason.strip(), "a refusal with no reason is a shrug")

    def test_http_is_refused_and_https_is_not(self):
        self.assertIn("http", links.REFUSED_SCHEMES)
        self.assertFalse(links.check_uri("http://example.com").allowed)
        self.assertTrue(links.check_uri("https://example.com").allowed)

    def test_the_scheme_is_compared_in_lower_case_but_the_uri_is_not_rewritten(self):
        verdict = links.check_uri("HTTPS://Example.COM/Path?q=1#frag")
        self.assertTrue(verdict.allowed)
        self.assertEqual("https", verdict.scheme, "the scheme was not folded, so an "
                                                  "upper-case HTTPS was refused")
        self.assertEqual("HTTPS://Example.COM/Path?q=1#frag", verdict.uri,
                         "the URI was rewritten on the way through, so what the desktop "
                         "opens is not what the record says")


class TestCheckNeverRaisesAndOpenAlwaysDoes(unittest.TestCase):
    """A question is answered; an action is refused out loud."""

    def test_check_uri_answers_for_every_input_including_the_impossible_ones(self):
        for text in (None, "", "   ", 0, [], "https://x", "javascript:x", "a" * 5000,
                     "\x00", "mailto:", "tel:"):
            with self.subTest(text=repr(text)[:24]):
                verdict = links.check_uri(text)
                self.assertIsInstance(verdict.allowed, bool)
                self.assertIsInstance(verdict.reason, str)
                self.assertIsInstance(verdict.uri, str)
                self.assertIsInstance(verdict.scheme, str)

    def test_not_text_and_empty_text_are_different_sentences(self):
        nothing = links.check_uri(None)
        blank = links.check_uri("   ")
        self.assertFalse(nothing.allowed)
        self.assertFalse(blank.allowed)
        self.assertNotEqual(nothing.reason, blank.reason,
                            "a value that is not text and a link that is empty are different "
                            "problems, and one sentence for both is wrong about one of them")
        self.assertIn("empty", blank.reason)

    def test_the_empty_verdict_is_a_sentinel_and_not_rebuilt_each_time(self):
        self.assertFalse(links.REFUSED.allowed)
        self.assertEqual("", links.REFUSED.scheme)
        self.assertTrue(links.REFUSED.reason)

    def test_is_empty_agrees_with_check_uri_about_what_is_empty(self):
        for text in (None, "", "   ", "\t\n"):
            with self.subTest(text=repr(text)):
                self.assertTrue(links.is_empty(text))
                self.assertFalse(links.check_uri(text).allowed)
        self.assertFalse(links.is_empty("x"))

    def test_whitespace_is_stripped_before_the_check_and_not_after(self):
        verdict = links.check_uri("  https://example.com  ")
        self.assertTrue(verdict.allowed, "surrounding whitespace from a JSON file made a "
                                         "good link unusable")
        self.assertEqual("https://example.com", verdict.uri,
                         "the whitespace reached the desktop, so what opens is not what was "
                         "checked")

    def test_whitespace_inside_a_uri_is_a_refusal_and_not_a_strip(self):
        verdict = links.check_uri("https://example.com/a b")
        self.assertFalse(verdict.allowed,
                         "a space inside a URI was stripped, which changes what the link "
                         "points at rather than refusing it")
        self.assertTrue("space" in verdict.reason or "control" in verdict.reason)

    def test_a_control_character_is_refused(self):
        for text in ("https://example.com/\x00", "https://example.com/a\nb",
                     "https://example.com/\x1b[31m"):
            with self.subTest(text=repr(text)):
                self.assertFalse(links.check_uri(text).allowed)

    def test_the_length_limit_is_the_recorded_one_and_has_its_own_sentence(self):
        self.assertEqual(2048, links.MAX_URI_LENGTH)
        long_uri = "https://example.com/" + "a" * links.MAX_URI_LENGTH
        verdict = links.check_uri(long_uri)
        self.assertFalse(verdict.allowed)
        self.assertIn(str(links.MAX_URI_LENGTH), verdict.reason,
                      "the limit is not in the sentence, so a person cannot tell how much "
                      "too long is")
        self.assertTrue(links.check_uri("https://example.com/" +
                                        "a" * (links.MAX_URI_LENGTH - 64)).allowed,
                        "a URI well inside the limit was refused")

    def test_require_uri_raises_where_check_uri_answers(self):
        with self.assertRaises(links.LinkError):
            links.require_uri("javascript:alert(1)")
        with self.assertRaises(links.LinkError):
            links.require_uri(None)
        self.assertEqual("https://example.com", links.require_uri("https://example.com"))

    def test_open_uri_raises_for_refused_input_before_an_opener_can_be_reached(self):
        reached: List[str] = []
        for text in ("javascript:alert(1)", "file:///etc/passwd", None, "   ",
                     "http://example.com"):
            with self.subTest(text=repr(text)[:24]):
                with self.assertRaises(links.LinkError):
                    links.open_uri(text, opener=reached.append)
        self.assertEqual([], reached,
                         "an opener was reached with a refused URI, so the allowlist is "
                         "checked after the hand-over rather than before")

    def test_an_opener_is_given_the_string_that_was_validated(self):
        """SET-04: the validated string is the string passed."""
        reached: List[str] = []

        def opener(uri: str) -> bool:
            reached.append(uri)
            return True

        # A recording opener has to return True itself: open_uri reports what the opener
        # said, so a bare list.append would answer None and look like a refused open.
        self.assertTrue(links.open_uri("  https://example.com/x  ", opener=opener))
        self.assertEqual(["https://example.com/x"], reached,
                         "the opener received something other than the checked URI")

    def test_an_opener_that_says_no_gives_a_false_result_and_not_an_exception(self):
        self.assertFalse(links.open_uri("mailto:a@b.co", opener=lambda uri: False),
                         "a desktop with no mail handler was reported as an error, and "
                         "'nothing is registered to open this' is not a failure of the link")

    def test_the_default_opener_says_what_to_do_instead_when_there_is_no_toolkit(self):
        with self.assertRaises(links.LinkError) as caught:
            links._gio_opener("mailto:a@b.co")
        message = str(caught.exception)
        self.assertIn("Copy it instead", message,
                      "a machine with no toolkit was told the link could not be opened and "
                      "not told what to do about it")
        self.assertTrue("toolkit" in message or "gi" in message.lower(),
                        f"the sentence does not say why: {message}")


class TestTheVerdictIsTheWholeAnswer(unittest.TestCase):
    """One object carries everything a disabled row needs to explain itself."""

    def test_the_verdict_has_exactly_the_four_fields_a_row_reads(self):
        verdict = links.check_uri("https://example.com")
        self.assertEqual({"allowed", "scheme", "reason", "uri"}, set(verdict._fields)
                         if hasattr(verdict, "_fields") else
                         {name for name in dir(verdict)
                          if not name.startswith("_") and not callable(getattr(verdict, name))})

    def test_an_allowed_verdict_has_no_reason_because_there_is_nothing_to_explain(self):
        self.assertEqual("", links.check_uri("https://example.com").reason)

    def test_every_refusal_has_a_reason_and_no_allowance_has_one(self):
        for text in ("javascript:x", "file:///x", "nope", None, "  ", "https://x/" + "a" * 3000):
            verdict = links.check_uri(text)
            with self.subTest(text=repr(text)[:20]):
                if verdict.allowed:
                    self.assertEqual("", verdict.reason)
                else:
                    self.assertTrue(verdict.reason.strip(),
                                    "a refusal with no reason cannot be shown on a disabled "
                                    "row, so the row would look broken")


class TestThePortfolioAddressAgreesEverywhereItIsWritten(unittest.TestCase):
    """Validating the constant costs nothing and catches the embarrassing edit."""

    def test_the_constant_is_a_link_this_module_would_open(self):
        verdict = links.check_uri(links.PORTFOLIO_URL)
        self.assertTrue(verdict.allowed,
                        f"{links.PORTFOLIO_URL} is refused by this module's own rules, so "
                        f"the Contact page's primary button is a disabled row")
        self.assertEqual("https", verdict.scheme)

    def test_portfolio_url_returns_the_constant(self):
        self.assertEqual(links.PORTFOLIO_URL, links.portfolio_url())

    def test_the_address_agrees_in_the_three_places_it_is_written(self):
        """The constant, the record's contact, and the record's own portfolio row."""
        record_url = CONTACTS_RECORD["portfolio"]["url"]
        row_value = next(row["value"] for row in CONTACTS_RECORD["rows"]
                         if row.get("kind") == "portfolio")
        self.assertEqual(links.PORTFOLIO_URL, record_url,
                         "the module's constant and the contact record disagree, so which "
                         "one the button opens depends on which one the code read")
        self.assertEqual(links.PORTFOLIO_URL, row_value)

    def test_the_subtitle_is_the_address_without_the_scheme(self):
        row = next(row for row in CONTACTS_RECORD["rows"] if row.get("kind") == "portfolio")
        self.assertEqual(links.PORTFOLIO_URL.removeprefix("https://"), row["subtitle"],
                         "the row shows one address and opens another")

    def test_the_record_agrees_with_the_unverified_claim_about_it(self):
        unverified = (ROOT / "docs" / "UNVERIFIED.md").read_text(encoding="utf-8")
        self.assertIn(links.PORTFOLIO_URL, unverified,
                      "SET-04 records what cannot be verified about this button and no "
                      "longer names the address it is about")


class TestEveryContactRowIsCheckedBeforeItIsDrawn(unittest.TestCase):
    """The page does not decide what is a link; this module does."""

    def test_every_visible_row_carries_a_verdict_alongside_its_value(self):
        rows = contacts.visible_rows()
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(kind=row.get("kind")):
                for field in ("kind", "value", "allowed", "scheme"):
                    self.assertIn(field, row,
                                  f"a contact row has no {field}, so the page would have to "
                                  f"ask this module again while drawing")
                self.assertIsInstance(row["allowed"], bool)

    def test_a_row_that_is_shown_is_a_row_that_is_allowed(self):
        for row in contacts.visible_rows():
            with self.subTest(kind=row.get("kind"), value=str(row.get("value"))[:40]):
                if row.get("shown"):
                    self.assertTrue(row["allowed"],
                                    "a row is drawn as a link this module refuses, so it is "
                                    "either a disabled row with no reason or a link that "
                                    "does nothing")

    def test_the_verdict_a_row_carries_agrees_with_asking_again(self):
        for row in contacts.visible_rows():
            verdict = links.check_uri(row["value"])
            with self.subTest(value=str(row["value"])[:40]):
                self.assertEqual(verdict.allowed, row["allowed"],
                                 "the contact record was checked with different rules than "
                                 "this module applies, so the two can drift")
                self.assertEqual(verdict.scheme, row["scheme"])

    def test_a_refused_contact_is_kept_and_explained_rather_than_dropped(self):
        refused = contacts.refused_rows()
        for row in refused:
            with self.subTest(value=str(row.get("value"))[:40]):
                self.assertFalse(row["allowed"])
                self.assertTrue(str(row.get("reason") or "").strip(),
                                "a contact this project will not open is hidden with no "
                                "explanation, so it looks like the record lost it")

    def test_every_row_has_a_copy_action_because_copying_needs_no_toolkit(self):
        for row in contacts.visible_rows():
            with self.subTest(kind=row.get("kind")):
                self.assertTrue(row.get("copy_action"),
                                "a row with no copy action gives a person on a machine with "
                                "no toolkit nothing to do with the value")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
