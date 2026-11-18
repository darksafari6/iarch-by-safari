#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""One boolean in one table, everything else byte for byte.

The file this tool exists for is `.config/noctalia/config.toml`, which this
repository generates and `install.sh` deploys -- so the tests run against the real
shipped file and not only against fixtures, and they ask `tomllib` to parse the
result. A line editor that produces a file the standard library cannot read has
failed whatever it was for, and that is a check worth more than counting lines.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import toml_set_flag  # noqa: E402

SHIPPED = ROOT / ".config" / "noctalia" / "config.toml"


def run(*argv: str) -> Tuple[int, str, str]:
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "toml_set_flag.py"), *argv],
                          capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def write(tmp: str, name: str, text: str) -> Path:
    path = Path(tmp) / name
    path.write_text(text, encoding="utf-8")
    return path


class TheShippedFile(unittest.TestCase):
    """The real target: a table the shipped profile does not carry."""

    def setUp(self) -> None:
        self.text = SHIPPED.read_text(encoding="utf-8")
        self.parsed = tomllib.loads(self.text)

    def test_the_shipped_profile_does_not_carry_the_switch(self):
        self.assertNotIn("brightness", self.parsed,
                         "the shipped profile grew a [brightness] table, so the installer "
                         "step this tool exists for has nothing left to turn on and the "
                         "test below is editing a file that already says yes")

    def test_appending_the_table_keeps_every_other_byte(self):
        edited, what = toml_set_flag.set_flag(self.text, "brightness", "enable_ddcutil", True)
        self.assertEqual("appended", what)
        self.assertEqual(self.text.rstrip("\n") + "\n\n[brightness]\nenable_ddcutil = true\n",
                         edited,
                         "the appended table is the whole of the change: one blank line, the "
                         "header and the key, with the file before it copied through")

    def test_the_result_still_parses_and_says_what_was_asked(self):
        edited, _ = toml_set_flag.set_flag(self.text, "brightness", "enable_ddcutil", True)
        parsed = tomllib.loads(edited)
        self.assertIs(True, parsed["brightness"]["enable_ddcutil"])

    def test_every_other_key_survives_the_edit(self):
        edited, _ = toml_set_flag.set_flag(self.text, "brightness", "enable_ddcutil", True)
        after: Dict[str, Any] = tomllib.loads(edited)
        before = dict(self.parsed)
        after.pop("brightness")
        self.assertEqual(before, after,
                         "a line editor that loses a key, a comment-bound value or a whole "
                         "table has changed more than the flag it was asked about")

    def test_a_second_run_writes_nothing(self):
        edited, _ = toml_set_flag.set_flag(self.text, "brightness", "enable_ddcutil", True)
        again, what = toml_set_flag.set_flag(edited, "brightness", "enable_ddcutil", True)
        self.assertEqual("unchanged", what)
        self.assertEqual(edited, again)

    def test_the_shipped_file_itself_is_never_edited_by_these_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = write(tmp, "config.toml", self.text)
            code, out, _ = run(str(copy), "brightness", "enable_ddcutil")
            self.assertEqual(0, code)
            self.assertIn("appended", out)
            self.assertEqual(self.text, SHIPPED.read_text(encoding="utf-8"),
                             "a test edited the repository's own shipped profile")


class AnExistingTable(unittest.TestCase):
    def test_a_key_goes_inside_its_table_and_not_at_the_end_of_the_file(self):
        text = ("[theme]\nmode = \"dark\"\n\n[brightness]\nminimum_brightness = 0.0\n\n"
                "[dock]\nenabled = true\n")
        edited, what = toml_set_flag.set_flag(text, "brightness", "enable_ddcutil", True)
        self.assertEqual("inserted", what)
        self.assertEqual(
            "[theme]\nmode = \"dark\"\n\n[brightness]\nminimum_brightness = 0.0\n"
            "enable_ddcutil = true\n\n[dock]\nenabled = true\n", edited,
            "the key has to land inside its own table, above the blank line that separates "
            "it from the next one -- at the end of the file it would belong to [dock]")
        self.assertEqual({"minimum_brightness": 0.0, "enable_ddcutil": True},
                         tomllib.loads(edited)["brightness"])
        self.assertEqual({"enabled": True}, tomllib.loads(edited)["dock"],
                         "the key landed in the table after the one it was asked for")

    def test_the_new_key_takes_the_indentation_of_its_siblings(self):
        text = "[brightness]\n    minimum_brightness = 0.0\n[dock]\n"
        edited, _ = toml_set_flag.set_flag(text, "brightness", "enable_ddcutil", True)
        self.assertIn("\n    enable_ddcutil = true\n", edited)

    def test_a_table_of_comments_only_still_gets_an_unindented_key(self):
        text = "[brightness]\n# a table with nothing in it yet\n[dock]\n"
        edited, _ = toml_set_flag.set_flag(text, "brightness", "enable_ddcutil", False)
        self.assertIn("[brightness]\n# a table with nothing in it yet\nenable_ddcutil = false\n",
                      edited)

    def test_replacing_a_value_keeps_the_comment_beside_it(self):
        text = "[brightness]\nenable_ddcutil = false  # off until ddcutil is set up\n"
        edited, what = toml_set_flag.set_flag(text, "brightness", "enable_ddcutil", True)
        self.assertEqual("replaced", what)
        self.assertEqual("[brightness]\nenable_ddcutil = true  # off until ddcutil is set up\n",
                         edited)

    def test_a_subtable_with_the_same_prefix_is_not_the_table(self):
        text = "[brightness.monitor.dell]\nbackend = \"ddcutil\"\n\n[brightness]\n"
        edited, what = toml_set_flag.set_flag(text, "brightness", "enable_ddcutil", True)
        self.assertEqual("inserted", what)
        self.assertEqual('[brightness.monitor.dell]\nbackend = "ddcutil"\n\n[brightness]\n'
                         'enable_ddcutil = true\n', edited)
        self.assertEqual({"monitor": {"dell": {"backend": "ddcutil"}},
                          "enable_ddcutil": True}, tomllib.loads(edited)["brightness"],
                         "a subtable that shares a prefix is not the table, and the key "
                         "must not land inside it")

    def test_a_key_in_another_table_is_not_found_and_not_touched(self):
        text = "[lockscreen]\nenable_ddcutil = false\n\n[brightness]\n"
        edited, _ = toml_set_flag.set_flag(text, "brightness", "enable_ddcutil", True)
        self.assertEqual("[lockscreen]\nenable_ddcutil = false\n\n[brightness]\n"
                         "enable_ddcutil = true\n", edited)


class Refusals(unittest.TestCase):
    def refuse(self, text: str, needle: str, table: str = "brightness",
               key: str = "enable_ddcutil") -> None:
        with self.subTest(text=text):
            with self.assertRaises(toml_set_flag.Refusal) as caught:
                toml_set_flag.set_flag(text, table, key, True)
            self.assertIn(needle, str(caught.exception))

    def test_a_table_that_appears_twice_has_no_single_place_for_a_key(self):
        self.refuse("[brightness]\na = 1\n\n[brightness]\nb = 2\n", "appears 2 times")

    def test_a_key_that_appears_twice_in_its_table_is_not_a_file_it_understands(self):
        self.refuse("[brightness]\nenable_ddcutil = false\nenable_ddcutil = true\n",
                    "appears 2 times")

    def test_a_value_that_is_not_a_boolean_is_somebody_elses_decision(self):
        self.refuse('[brightness]\nenable_ddcutil = "yes"\n', "not a boolean")
        self.refuse("[brightness]\nenable_ddcutil = 1\n", "not a boolean")

    def test_the_command_line_says_why_it_refused_and_leaves_the_file_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.toml", "[brightness]\nenable_ddcutil = 3\n")
            code, out, err = run(str(path), "brightness", "enable_ddcutil")
            self.assertEqual(1, code)
            self.assertIn("refused", err)
            self.assertEqual("", out.strip(), "a refusal is not a success to report on stdout")
            self.assertEqual("[brightness]\nenable_ddcutil = 3\n",
                             path.read_text(encoding="utf-8"))


class OddFiles(unittest.TestCase):
    def test_an_empty_file_gets_the_table_and_nothing_else(self):
        edited, what = toml_set_flag.set_flag("", "brightness", "enable_ddcutil", True)
        self.assertEqual("appended", what)
        self.assertEqual("[brightness]\nenable_ddcutil = true\n", edited)

    def test_a_file_with_no_trailing_newline_gains_one_rather_than_a_joined_line(self):
        edited, _ = toml_set_flag.set_flag("[theme]\nmode = \"dark\"", "brightness",
                                           "enable_ddcutil", True)
        self.assertEqual("[theme]\nmode = \"dark\"\n\n[brightness]\nenable_ddcutil = true\n",
                         edited)
        self.assertEqual({"brightness": {"enable_ddcutil": True}},
                         {k: v for k, v in tomllib.loads(edited).items() if k == "brightness"})

    def test_a_missing_file_is_a_usage_error_not_a_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run(str(Path(tmp) / "nope.toml"), "brightness", "enable_ddcutil")
            self.assertEqual(2, code)
            self.assertIn("cannot read", err)


class TheCommandLine(unittest.TestCase):
    def test_check_answers_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.toml", "[brightness]\nenable_ddcutil = false\n")
            code, _, err = run(str(path), "brightness", "enable_ddcutil", "--check")
            self.assertEqual(1, code, "a file that says false does not carry true")
            self.assertIn("does not carry", err)
            self.assertEqual("[brightness]\nenable_ddcutil = false\n",
                             path.read_text(encoding="utf-8"))
            code, out, _ = run(str(path), "brightness", "enable_ddcutil", "--false", "--check")
            self.assertEqual(0, code)
            self.assertIn("already carries", out)

    def test_false_is_a_value_and_not_the_absence_of_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.toml", "[brightness]\nenable_ddcutil = true\n")
            code, out, _ = run(str(path), "brightness", "enable_ddcutil", "--false")
            self.assertEqual(0, code)
            self.assertIn("replaced", out)
            self.assertEqual("[brightness]\nenable_ddcutil = false\n",
                             path.read_text(encoding="utf-8"))

    def test_true_and_false_are_one_choice_and_not_two_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.toml", "[brightness]\n")
            code, _, err = run(str(path), "brightness", "enable_ddcutil", "--true", "--false")
            self.assertEqual(2, code, "argparse accepts a contradiction it should refuse")
            self.assertIn("not allowed with argument", err)

    def test_has_flag_reads_the_same_way_the_edit_writes(self):
        text = "[brightness]\nenable_ddcutil = true\n"
        self.assertTrue(toml_set_flag.has_flag(text, "brightness", "enable_ddcutil", True))
        self.assertFalse(toml_set_flag.has_flag(text, "brightness", "enable_ddcutil", False))
        self.assertFalse(toml_set_flag.has_flag(text, "dock", "enable_ddcutil", True))
        self.assertFalse(toml_set_flag.has_flag("[theme]\nmode = \"dark\"\n", "brightness",
                                                "enable_ddcutil", True))


if __name__ == "__main__":
    unittest.main()
