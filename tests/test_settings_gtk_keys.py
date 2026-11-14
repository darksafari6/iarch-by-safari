#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the GtkSettings keys this project writes, and the two it refuses to.

``data/design/gtk-settings.json`` records eleven keys with the value domain GTK itself
accepts for each. Nine are written into ``~/.config/gtk-4.0/settings.ini`` and, for the
five GTK 3 also has, into the GTK 3 file. Two are recorded and deliberately not written,
and both refusals are a decision about having one mechanism per intention:

* ``gtk-theme-name``, because the theme is applied by ``iarch-theme`` through the
  generated sheets and the installer's package choice, so a second writer would be a
  second source of truth for the same decision;
* ``gtk-enable-animations``, because reduce motion here is ``animation.reduce_motion``,
  which ``iarch-anim`` owns and which renders every transition at 0 ms -- setting this
  key as well would give one intention two mechanisms that can disagree.

The value domains matter more than the key list, and the reason is in the record's own
note: an unrecognised ``gtk-xft-hintstyle`` or ``gtk-xft-rgba`` spelling is compared with
``strcmp`` against a closed list and, when it does not match, leaves the setting at
Cairo's default **without raising**. A text entry for such a key is therefore a control
that can silently do nothing, which is why every one of them is a dropdown built from the
recorded spellings and never an entry.

The cursor size is the opposite shape: the record gives it a *range* rather than a list,
because a range read as a list of choices would be a dropdown with one hundred and
twenty-nine items in it. And two keys carry a closed list of *numbers* rather than
spellings, where ``-1`` means "the system default" -- the same thing as not writing the
key at all, which is why this project never writes it.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings.pages import fonts as fonts_page  # noqa: E402
from iarch_settings.services import gtk_settings  # noqa: E402

RECORD = json.loads((ROOT / "data" / "design" / "gtk-settings.json").read_text(
    encoding="utf-8"))
KEYS: Dict[str, Any] = RECORD["keys"]
GTK3 = [entry["key"] for entry in RECORD["gtk3_keys"]["keys"]]
FILES = [entry["path"] for entry in RECORD["files"]]


class TestTheKeyList(unittest.TestCase):
    """A key that is not listed here is not written, and the code agrees."""

    def test_the_record_carries_eleven_keys_and_the_code_writes_nine(self):
        self.assertEqual(11, len(KEYS))
        self.assertEqual(9, len(gtk_settings.writable_keys()))
        self.assertEqual(2, len(gtk_settings.refused_keys()))
        self.assertEqual(sorted(KEYS), sorted(set(gtk_settings.writable_keys())
                                              | set(gtk_settings.refused_keys())),
                         "the writable list and the refused list do not add up to the "
                         "record, so a key is either written and unrecorded or recorded "
                         "and neither")

    def test_the_two_refused_keys_are_the_two_with_a_second_mechanism(self):
        refused = gtk_settings.refused_keys()
        self.assertEqual({"gtk-theme-name", "gtk-enable-animations"}, set(refused))
        for key, reason in refused.items():
            with self.subTest(key=key):
                self.assertGreater(len(reason.split()), 12,
                                   "a refusal copied out of a record's `why` field is a "
                                   "citation; a row shows this to a person")
                self.assertIn(key, RECORD["keys"],
                              f"{key} is refused by the code and absent from the record, so "
                              f"the record cannot say it exists at all")

    def test_a_refused_key_is_never_written_by_the_projection(self):
        values = gtk_settings.values_from_settings(
            {"ui_family": "Inter", "size_pt": 11, "antialias": "rgba", "hinting": True,
             "hint_style": "hintslight", "subpixel": "rgb", "icon_theme": "Adwaita",
             "cursor_theme": "Bibata-Modern-Classic", "cursor_size": 24},
            colour_mode="dark")
        for key in gtk_settings.refused_keys():
            with self.subTest(key=key):
                self.assertNotIn(key, values,
                                 f"{key} is recorded as refused and the projection wrote it")

    def test_every_writable_key_is_in_the_record(self):
        for key in gtk_settings.writable_keys():
            with self.subTest(key=key):
                self.assertIn(key, KEYS)

    def test_the_gtk3_subset_is_exactly_the_five_the_frozen_payload_writes(self):
        self.assertEqual(5, len(gtk_settings.gtk3_keys()))
        self.assertEqual(sorted(GTK3), sorted(gtk_settings.gtk3_keys()))
        for key in gtk_settings.gtk3_keys():
            with self.subTest(key=key):
                self.assertIn(key, gtk_settings.writable_keys(),
                              "a key written to the GTK 3 file and not to the GTK 4 one "
                              "would be a key only classic applications see")

    def test_the_record_says_why_the_gtk3_evidence_is_weaker(self):
        note = RECORD["gtk3_keys"]["_note"]
        self.assertIn("SET-05", note,
                      "the GTK 3 property table was not read out of a pinned 3.24 ref, and "
                      "the record has to say so rather than present the five keys as "
                      "verified the same way")


class TestTheValueDomains(unittest.TestCase):
    """An unrecognised spelling is silently ignored, so a domain is a list or a range."""

    def test_a_key_with_a_closed_list_offers_exactly_that_list(self):
        """Two shapes share the field name ``values``, and only one of them is a choice."""
        for key in ("gtk-xft-hintstyle", "gtk-xft-rgba"):
            recorded = KEYS[key]["values"]
            with self.subTest(key=key):
                self.assertIsInstance(recorded, list)
                self.assertTrue(all(isinstance(item, str) for item in recorded),
                                f"{key}'s values are spellings GTK compares with strcmp")
                self.assertEqual(sorted(recorded),
                                 sorted(gtk_settings.accepted_values(key) or []),
                                 f"{key}'s dropdown and the record disagree")

    def test_an_int_key_with_a_closed_list_is_a_choice_and_never_minus_one(self):
        """``-1`` means "the system default", and not writing the key means the same thing."""
        for key in ("gtk-xft-antialias", "gtk-xft-hinting"):
            recorded = KEYS[key]["values"]
            with self.subTest(key=key):
                self.assertEqual([-1, 0, 1], recorded)
                self.assertEqual(["-1", "0", "1"],
                                 sorted(gtk_settings.accepted_values(key) or [],
                                        key=lambda text: int(text)),
                                 "an ini file has no int type, so the accepted spellings "
                                 "are strings and the record's numbers are rendered as such")
                self.assertIn("never -1", KEYS[key]["value_note"],
                              "the reason -1 is not written has to be in the record, or the "
                              "next reader offers it as a third choice")

    def test_a_key_with_a_range_is_not_offered_as_a_list_of_choices(self):
        """The cursor size carries ``range``, not ``values``, and the two are different fields."""
        bounds = gtk_settings.key_range("gtk-cursor-theme-size")
        self.assertEqual((0, 128), bounds)
        self.assertIn("range", KEYS["gtk-cursor-theme-size"])
        self.assertNotIn("values", KEYS["gtk-cursor-theme-size"],
                         "a key cannot carry both a range and a closed list, and a reader "
                         "that checks `values` first would render 129 dropdown items")
        self.assertIsNone(gtk_settings.accepted_values("gtk-cursor-theme-size"),
                          "a range is not a closed list, so accepted_values says so with "
                          "None rather than with two items")

    def test_a_boolean_key_carries_neither_a_list_nor_a_range(self):
        for key, spec in KEYS.items():
            if spec["type"] != "bool":
                continue
            with self.subTest(key=key):
                self.assertNotIn("values", spec)
                self.assertNotIn("range", spec)
                self.assertIsNone(gtk_settings.accepted_values(key))
                self.assertIsNone(gtk_settings.key_range(key))

    def test_a_free_string_key_has_no_domain_to_offer(self):
        for key in ("gtk-font-name", "gtk-icon-theme-name", "gtk-cursor-theme-name"):
            with self.subTest(key=key):
                self.assertIsNone(gtk_settings.accepted_values(key))
                self.assertIsNone(gtk_settings.key_range(key))

    def test_every_key_carries_the_line_it_was_read_from(self):
        for key, spec in KEYS.items():
            with self.subTest(key=key):
                self.assertTrue(str(spec.get("evidence") or "").strip(),
                                f"{key} has no evidence line, so nobody can check it")
                self.assertIn("gtksettings.c", str(spec["evidence"]),
                              f"{key}'s evidence does not name the file the property table "
                              f"lives in")
                self.assertIn(str(spec.get("type") or ""), ("string", "bool", "int"),
                              f"{key} has a type this project does not know how to render")

    def test_a_key_that_is_silently_ignored_says_so_in_the_record(self):
        """The behaviour that makes a text entry dangerous has to be written down."""
        note = str(KEYS["gtk-xft-hintstyle"].get("value_note") or "")
        self.assertIn("strcmp", note)
        self.assertTrue("default" in note or "ignored" in note.lower(),
                        "the record does not say what GTK does with an unrecognised "
                        "spelling, which is the reason the row is a dropdown")


class TestTheProjectionIntoSettingsIni(unittest.TestCase):
    """What the page's settings become in the file GTK reads."""

    def test_the_two_halves_of_the_font_become_one_key(self):
        values = gtk_settings.values_from_settings(
            {"ui_family": "Inter", "size_pt": 11}, colour_mode="dark")
        self.assertEqual("Inter 11", values["gtk-font-name"],
                         "gtk-font-name is one string of the form 'Family Size'")

    def test_a_family_nobody_chose_does_not_pin_the_key(self):
        """An empty family means 'whatever the session already has', not 'Sans 10'."""
        values = gtk_settings.values_from_settings(
            {"ui_family": "", "size_pt": 0}, colour_mode="dark")
        self.assertNotIn("gtk-font-name", values,
                         "pinning a font the user never chose would stop the session's own "
                         "font change from reaching GTK applications")

    def test_the_colour_mode_becomes_the_dark_theme_key(self):
        dark = gtk_settings.values_from_settings({}, colour_mode="dark")
        light = gtk_settings.values_from_settings({}, colour_mode="light")
        self.assertIn(gtk_settings.DARK_KEY, dark)
        self.assertIn(gtk_settings.DARK_KEY, light)
        self.assertNotEqual(dark[gtk_settings.DARK_KEY], light[gtk_settings.DARK_KEY])

    def test_a_boolean_setting_is_written_the_way_an_ini_file_reads_it(self):
        values = gtk_settings.values_from_settings({"hinting": True}, colour_mode="dark")
        self.assertIn(values["gtk-xft-hinting"], ("1", "0", "true", "false"),
                      "an ini file has no boolean type, so the spelling has to be one GTK "
                      "parses")

    def test_check_values_refuses_a_spelling_gtk_would_ignore(self):
        problems = gtk_settings.check_values({"gtk-xft-hintstyle": "hintish"})
        self.assertTrue(problems, "an unrecognised hint style was accepted, and GTK would "
                                  "leave the setting at Cairo's default without raising")
        self.assertEqual([], gtk_settings.check_values({"gtk-xft-hintstyle": "hintslight"}))

    def test_check_values_refuses_a_number_outside_the_recorded_range(self):
        self.assertTrue(gtk_settings.check_values({"gtk-cursor-theme-size": "999"}))
        self.assertTrue(gtk_settings.check_values({"gtk-cursor-theme-size": "-4"}))
        self.assertEqual([], gtk_settings.check_values({"gtk-cursor-theme-size": "24"}))

    def test_check_values_refuses_a_key_the_record_does_not_have(self):
        problems = gtk_settings.check_values({"gtk-invented-key": "1"})
        self.assertTrue(problems)
        self.assertIn("gtk-invented-key", " ".join(problems))

    def test_the_targets_are_the_two_files_the_record_names(self):
        paths = gtk_settings.target_paths(Path("/tmp/fake-config"))
        self.assertEqual({"gtk4", "gtk3"}, set(paths),
                         "GTK 4 and GTK 3 are the two files, and a third would be a file "
                         "nothing reads")
        # The record's paths are relative to a home directory; target_paths takes the
        # configuration directory itself, so the comparison puts .config back on.
        written = sorted(f".config/{path.relative_to(Path('/tmp/fake-config'))}"
                         for path in paths.values())
        self.assertEqual(sorted(FILES), written,
                         "the files written and the files recorded are two lists of one "
                         "decision")

    def test_neither_target_is_a_generated_file(self):
        """A user-owned file carries no GENERATED header, because it holds their choices."""
        for entry in RECORD["files"]:
            with self.subTest(path=entry["path"]):
                self.assertFalse(entry["generated"],
                                 f"{entry['path']} is the user's own file and is marked "
                                 f"generated, which would license overwriting it")


class TestThePageOffersWhatTheRecordWrites(unittest.TestCase):
    """The Fonts & Icons page and the record are two copies of one list."""

    def test_the_page_offers_nine_settings_and_the_record_writes_nine_keys(self):
        self.assertEqual(9, len(fonts_page.OFFERED))
        self.assertEqual(9, len(gtk_settings.writable_keys()))

    def test_every_offered_setting_maps_to_a_key_or_is_a_half_of_the_font(self):
        halves = set(gtk_settings.FONT_NAME_SETTINGS)
        for setting in fonts_page.OFFERED:
            with self.subTest(setting=setting):
                self.assertTrue(setting in halves or setting in gtk_settings.KEY_BY_SETTING,
                                f"{setting} is offered by the page and projects to no key")

    def test_the_page_refuses_the_same_two_keys_on_screen(self):
        """A refused key is shown with its reason, not simply absent."""
        from iarch_settings.pages import build
        from iarch_settings.pages.plan import default_context

        plan = build("fonts", default_context())
        text = " ".join(
            " ".join(part for part in (row.title, row.subtitle or "",
                                       " ".join(str(keyword) for keyword in row.keywords)))
            for row in plan.walk()).lower()
        for key in gtk_settings.refused_keys():
            with self.subTest(key=key):
                self.assertIn(key, text,
                              f"the Fonts page does not name {key} anywhere, so a person "
                              f"looking for it finds neither a control nor an explanation")

    def test_the_read_and_diff_helpers_answer_without_a_desktop(self):
        read = gtk_settings.read(Path("/tmp/does-not-exist"))
        self.assertIsInstance(read, dict)
        diff = gtk_settings.diff({}, {})
        self.assertIsInstance(diff, (dict, list, tuple))
        self.assertTrue(gtk_settings.available() is not None)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
