#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the three ways the settings window can be started, and the copies between them.

There are three entry points and they have to be one program:

* ``scripts/iarch-settings.sh``, which a person runs from a checkout;
* ``python3 -m iarch_settings``, which is what that script execs and what a test can run
  without a shell in the way;
* the ``iarch-settings`` console script ``iarch/settings-app/pyproject.toml`` declares,
  which is what lands on PATH if the package is installed.

All three end at :func:`iarch_settings.widgets.app.main`. The desktop entry's ``Exec=``
names the third by the name :mod:`tools.iarch_brand` publishes for it, and its ``Icon=``
names the application id the package publishes -- which is also the anchored id the
compositor's window rule matches, so the icon name and the window rule cannot disagree
about which window this is. Each of those is a copy of a decision made somewhere else, and
a copy nobody checks is a copy that drifts.

Two of these tests run the real thing in a subprocess rather than reading it. That is only
safe because a machine with no toolkit exits non-zero with one sentence, and both tests
skip themselves on a machine that has one -- starting a window in a test suite would hang
it, and a suite that only passes on a machine without a desktop is a suite that has never
been run on the machine the application is for.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

import iarch_brand as brand  # noqa: E402

from iarch_settings import APP_ID, gtkenv, version  # noqa: E402

try:  # noqa: SIM105 - tomllib is 3.11+, and the suite runs on older interpreters too
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - depends on the interpreter
    tomllib = None  # type: ignore[assignment]

LAUNCHER = ROOT / "scripts" / "iarch-settings.sh"
DESKTOP = ROOT / "iarch" / "settings-app" / f"{APP_ID}.desktop"
PYPROJECT = ROOT / "iarch" / "settings-app" / "pyproject.toml"
PACKAGE_DIR = ROOT / "iarch" / "settings-app"
PRODUCT = brand.product(ROOT)
ENVIRON = dict(os.environ)
ENVIRON.pop("DISPLAY", None)
ENVIRON.pop("WAYLAND_DISPLAY", None)


def desktop_keys() -> Dict[str, str]:
    """The desktop entry's keys, from the one group it has."""
    keys: Dict[str, str] = {}
    for line in DESKTOP.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or text.startswith("["):
            continue
        name, separator, value = text.partition("=")
        if separator:
            keys[name.strip()] = value.strip()
    return keys


def run(*argv: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run something with no display in the environment, and read both streams."""
    return subprocess.run(list(argv), cwd=ROOT, capture_output=True, text=True,
                          timeout=timeout, env=ENVIRON)


class TestTheDesktopEntryAgreesWithTheNamesPublishedElsewhere(unittest.TestCase):
    """Four values, each one a copy of a decision made in another file."""

    def test_the_file_is_named_after_the_application_id(self):
        self.assertTrue(DESKTOP.is_file(), f"{DESKTOP} is not there")
        self.assertEqual(f"{APP_ID}.desktop", DESKTOP.name,
                         "a desktop entry whose filename is not the application id is not "
                         "found by the desktop when a window with that id asks for one")

    def test_the_application_id_is_the_one_the_branding_publishes(self):
        self.assertEqual(PRODUCT["IARCH_APP_ID_SETTINGS"], APP_ID,
                         "the package's APP_ID and branding/product.env disagree, and the "
                         "compositor's window rule is anchored to one of them")

    def test_exec_names_the_component_the_branding_publishes(self):
        keys = desktop_keys()
        self.assertEqual(PRODUCT["IARCH_COMPONENT_SETTINGS"], keys["Exec"],
                         "Exec= names a program the branding does not, so the menu entry "
                         "and every other place this component is named have drifted")

    def test_icon_names_the_application_id(self):
        keys = desktop_keys()
        self.assertEqual(APP_ID, keys["Icon"],
                         "Icon= is not the application id, so the icon name and the "
                         "compositor's window rule for this window are two names")

    def test_the_entry_is_an_application_that_does_not_own_a_terminal(self):
        keys = desktop_keys()
        self.assertEqual("Application", keys["Type"])
        self.assertEqual("false", keys["Terminal"],
                         "a settings window that opens a terminal has started a shell it "
                         "did not need and left it behind when it closed")
        self.assertEqual("1.5", keys["Version"], "the Desktop Entry Specification version "
                                                 "this file is written against")

    def test_the_categories_are_a_semicolon_list_that_ends_with_one(self):
        keys = desktop_keys()
        self.assertIn("Settings", keys["Categories"])
        self.assertTrue(keys["Categories"].endswith(";"),
                        "a categories list without its trailing semicolon is one category "
                        "to some implementations and a parse error to others")

    def test_it_carries_a_name_and_a_comment_a_person_can_read(self):
        keys = desktop_keys()
        self.assertTrue(keys["Name"])
        self.assertGreater(len(keys["Comment"].split()), 5,
                           "the comment is what a menu shows under the name, and one clause "
                           "does not say what this window is for")

    def test_the_header_is_a_comment_and_not_a_key(self):
        text = DESKTOP.read_text(encoding="utf-8")
        self.assertIn(PRODUCT["IARCH_COPYRIGHT_HEADER"], text.splitlines()[0])
        self.assertTrue(text.splitlines()[0].startswith("#"),
                        "a desktop entry has no other comment syntax, so a header line "
                        "without one is a key nobody asked for")


class TestTheLauncherIsTheSameProgramAsTheModule(unittest.TestCase):
    """A thin wrapper, checked by running it rather than by reading it."""

    def test_it_exists_and_is_executable(self):
        self.assertTrue(LAUNCHER.is_file())
        mode = LAUNCHER.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "the launcher is not executable, so a desktop "
                                             "entry naming it would fail to start anything")

    def test_it_parses_as_shell(self):
        result = run("bash", "-n", str(LAUNCHER))
        self.assertEqual(0, result.returncode, result.stderr)

    def test_it_ends_at_the_module_and_not_at_a_copy_of_it(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("python3 -m iarch_settings", text,
                      "the launcher does not exec the module, so the installed program and "
                      "the repository one are two code paths")
        self.assertIn("exec", text)

    def test_it_keeps_a_pythonpath_that_is_already_set(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertRegex(text, r"PYTHONPATH:\+",
                         "the launcher overwrites PYTHONPATH, which breaks a session that "
                         "put something there for a reason")

    def test_running_the_module_with_no_toolkit_is_one_sentence_and_a_status(self):
        """The behaviour that makes both entry points testable on a machine with no desktop."""
        if gtkenv.available():  # pragma: no cover - depends on the machine
            self.skipTest("a toolkit is installed here, so the window would really open")
        environ = dict(ENVIRON)
        environ["PYTHONPATH"] = str(PACKAGE_DIR)
        result = subprocess.run([sys.executable, "-m", "iarch_settings"], cwd=ROOT,
                                capture_output=True, text=True, timeout=60, env=environ)
        self.assertEqual(1, result.returncode,
                         "a machine with no toolkit did not get a non-zero status, so the "
                         "failure looks like success to anything that runs it")
        self.assertEqual("", result.stdout, "the report went to stdout, where a caller "
                                            "reads a result rather than a diagnosis")
        self.assertIn("GTK", result.stderr)
        self.assertTrue("python-gobject" in result.stderr or
                        "python3-gobject" in result.stderr,
                        f"the sentence does not name the package that provides the binding "
                        f"on either distribution: {result.stderr!r}")

    def test_describe_reports_the_version_and_the_toolkit_and_exits_non_zero(self):
        if gtkenv.available():  # pragma: no cover - depends on the machine
            self.skipTest("a toolkit is installed here, so --describe would exit 0")
        result = run("bash", str(LAUNCHER), "--describe")
        self.assertEqual(1, result.returncode,
                         "--describe is a check as well as a report, and a machine that "
                         "cannot draw the window has to say so in its status")
        self.assertIn(version.read_version(ROOT), result.stdout,
                      "the report does not say which version it is describing, which is the "
                      "first thing anybody asking for it needs")
        self.assertIn("GTK", result.stdout)

    def test_an_unknown_argument_is_a_usage_line_and_a_usage_status(self):
        result = run("bash", str(LAUNCHER), "--nonsense")
        self.assertEqual(2, result.returncode)
        self.assertIn("Usage", result.stderr)
        self.assertEqual("", result.stdout)

    def test_it_refuses_to_run_from_outside_the_repository(self):
        """The check that turns a copied script into a sentence rather than a traceback."""
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("is not the settings package", text)
        self.assertRegex(text, r"exit 70")


class TestThePackageMetadataNamesTheSameThings(unittest.TestCase):
    """The console script, the launcher and the desktop entry are one name."""

    def setUp(self):
        if tomllib is None:  # pragma: no cover - depends on the interpreter
            self.skipTest("this interpreter has no tomllib, so the metadata cannot be read")
        self.metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    def test_the_distribution_is_named_after_the_component(self):
        self.assertEqual(PRODUCT["IARCH_COMPONENT_SETTINGS"],
                         self.metadata["project"]["name"])

    def test_the_console_script_is_the_program_the_desktop_entry_names(self):
        scripts = self.metadata["project"]["scripts"]
        self.assertEqual([PRODUCT["IARCH_COMPONENT_SETTINGS"]], list(scripts),
                         "the installed program and the one Exec= names are different names")
        self.assertEqual("iarch_settings.widgets.app:main",
                         scripts[PRODUCT["IARCH_COMPONENT_SETTINGS"]],
                         "the console script does not end where the launcher ends, so an "
                         "installed iarch-settings is a different program from a "
                         "repository-local one")

    def test_the_version_is_the_repositorys_own(self):
        self.assertEqual(version.read_version(ROOT), self.metadata["project"]["version"],
                         "pyproject.toml carries a copy of the root VERSION file and the two "
                         "have drifted; setuptools cannot read a dynamic version from "
                         "outside the project directory, so the copy is checked instead")

    def test_the_licence_is_the_spdx_expression_the_header_uses(self):
        self.assertEqual(PRODUCT["IARCH_LICENSE_ID"],
                         self.metadata["project"]["license"]["text"])

    def test_the_python_floor_is_a_version_somebody_has_run(self):
        floor = self.metadata["project"]["requires-python"]
        self.assertTrue(floor.startswith(">=3."), f"unexpected floor spelling: {floor}")
        self.assertLessEqual((3, 11), tuple(int(part) for part in
                                            floor.removeprefix(">=").split(".")[:2]),
                             "the floor is above the interpreter this suite runs under, so "
                             "no test has ever run on a supported version")

    def test_no_dependency_is_declared_and_the_file_says_why(self):
        self.assertEqual([], self.metadata["project"]["dependencies"],
                         "a dependency was declared, and PyGObject is not installable from "
                         "an index: it is the distribution's own binding, built against its "
                         "own GTK and libadwaita")
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("python-gobject", text,
                      "the empty dependency list has no comment saying why, so it reads as "
                      "an omission rather than a decision")

    def test_every_package_directory_on_disk_is_listed(self):
        """A list that has to be extended by hand is a list that gets forgotten."""
        declared = set(self.metadata["tool"]["setuptools"]["packages"])
        # A directory is a package if it holds an __init__.py, so the list is read from
        # those rather than from the directories that happen to exist.
        found = {str(path.parent.relative_to(PACKAGE_DIR)).replace(os.sep, ".")
                 for path in PACKAGE_DIR.rglob("__init__.py")
                 if "__pycache__" not in path.parts}
        found.discard(".")
        self.assertEqual(found, declared,
                         "the declared packages and the directories that are packages "
                         "disagree, so a wheel would ship part of the application")

    def test_the_stylesheet_travels_with_the_package(self):
        data = self.metadata["tool"]["setuptools"]["package-data"]["iarch_settings"]
        self.assertIn("style/*.css", data,
                      "glass.css is loaded out of the installed package by paths.style_file, "
                      "and a wheel without it draws an unstyled window and reports nothing, "
                      "because GTK's CSS parsing errors are never fatal")
        self.assertTrue((PACKAGE_DIR / "iarch_settings" / "style" / "glass.css").is_file())

    def test_it_is_the_only_pyproject_in_the_repository(self):
        """One packaged component, and the file says why nothing else is packaged."""
        found = [path for path in ROOT.rglob("pyproject.toml")
                 if "legacy" not in path.parts and ".git" not in path.parts]
        self.assertEqual([PYPROJECT], found,
                         "another component grew packaging metadata, and the CLI tools are "
                         "run by path on purpose")


class TestWhatIsNotTrueYetIsWrittenDown(unittest.TestCase):
    """The entry is correct and is not yet reachable; that is a claim, not a shrug."""

    def test_neither_installer_copies_the_desktop_entry(self):
        for installer in ("install.sh", "fedora_install.sh"):
            text = (ROOT / installer).read_text(encoding="utf-8")
            with self.subTest(installer=installer):
                self.assertNotIn(DESKTOP.name, text,
                                 f"{installer} now installs the desktop entry, so "
                                 f"docs/UNVERIFIED.md SET-10 is describing a state that has "
                                 f"changed")

    def test_the_gap_is_recorded_as_set_10_and_not_left_implicit(self):
        unverified = (ROOT / "docs" / "UNVERIFIED.md").read_text(encoding="utf-8")
        self.assertIn("SET-10", unverified,
                      "the desktop entry has never been registered and nothing says so, "
                      "which is the difference between an unverified claim and a false one")
        row = next(line for line in unverified.splitlines()
                   if line.startswith("| SET-10 |"))
        self.assertIn(DESKTOP.name, row)
        self.assertIn("update-desktop-database", row,
                      "the record does not name the thing that has never been run")

    def test_the_desktop_entry_points_at_the_record_itself(self):
        text = DESKTOP.read_text(encoding="utf-8")
        self.assertIn("SET-10", text,
                      "the file does not say what is not true about it yet, so the next "
                      "reader assumes a menu entry that works")

    def test_no_icon_is_installed_under_the_application_id(self):
        found = list((ROOT / "assets").rglob(f"{APP_ID}*"))
        self.assertEqual([], found,
                         "an icon named after the application id now exists, so the note in "
                         "the desktop entry about there being none is out of date")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
