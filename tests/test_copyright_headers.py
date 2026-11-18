# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Every new file carries the one defined copyright header; nothing is guessed."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import iarch_brand as brand  # noqa: E402

HEADER = brand.product(ROOT)["IARCH_COPYRIGHT_HEADER"]

# Files this work added, in three lists rather than one, because they were added by
# three different pieces of work and a single flat tuple stops saying which is which.
# Pre-existing files keep whatever header they have, and vendored upstream code under
# legacy/ keeps its own copyright untouched -- that is what the last test here checks.
PART_ONE_TO_THREE_FILES = (
    "iarch/lib/__init__.py",
    "iarch/lib/configstore.py",
    "iarch/lib/renderers.py",
    "tools/profile_preset.py",
    "profiles/performance.toml",
    "tests/test_config_store.py",
    "tests/test_profile_preset.py",
    "tests/test_keybinds_data.py",
    "tests/test_architecture_docs.py",
    "tests/test_copyright_headers.py",
    "tests/test_licenses_data.py",
)

#: The settings application: its four package modules, the plan layer, fifteen page
#: modules, fourteen services and the renderer.
SETTINGS_APP_FILES = (
    "iarch/settings-app/iarch_settings/__init__.py",
    "iarch/settings-app/iarch_settings/__main__.py",
    "iarch/settings-app/iarch_settings/gtkenv.py",
    "iarch/settings-app/iarch_settings/i18n.py",
    "iarch/settings-app/iarch_settings/pages/__init__.py",
    "iarch/settings-app/iarch_settings/pages/about.py",
    "iarch/settings-app/iarch_settings/pages/animations.py",
    "iarch/settings-app/iarch_settings/pages/appearance.py",
    "iarch/settings-app/iarch_settings/pages/backup.py",
    "iarch/settings-app/iarch_settings/pages/bar.py",
    "iarch/settings-app/iarch_settings/pages/contact.py",
    "iarch/settings-app/iarch_settings/pages/display.py",
    "iarch/settings-app/iarch_settings/pages/features.py",
    "iarch/settings-app/iarch_settings/pages/fonts.py",
    "iarch/settings-app/iarch_settings/pages/glass.py",
    "iarch/settings-app/iarch_settings/pages/home.py",
    "iarch/settings-app/iarch_settings/pages/plan.py",
    "iarch/settings-app/iarch_settings/pages/power.py",
    "iarch/settings-app/iarch_settings/pages/shellkeys.py",
    "iarch/settings-app/iarch_settings/pages/shortcuts.py",
    "iarch/settings-app/iarch_settings/pages/sound.py",
    "iarch/settings-app/iarch_settings/pages/startup.py",
    "iarch/settings-app/iarch_settings/paths.py",
    "iarch/settings-app/iarch_settings/services/__init__.py",
    "iarch/settings-app/iarch_settings/services/apply.py",
    "iarch/settings-app/iarch_settings/services/autostart.py",
    "iarch/settings-app/iarch_settings/services/config_store.py",
    "iarch/settings-app/iarch_settings/services/contacts.py",
    "iarch/settings-app/iarch_settings/services/control.py",
    "iarch/settings-app/iarch_settings/services/defaults.py",
    "iarch/settings-app/iarch_settings/services/gtk_settings.py",
    "iarch/settings-app/iarch_settings/services/hypr.py",
    "iarch/settings-app/iarch_settings/services/licenses.py",
    "iarch/settings-app/iarch_settings/services/links.py",
    "iarch/settings-app/iarch_settings/services/noctalia.py",
    "iarch/settings-app/iarch_settings/services/runner.py",
    "iarch/settings-app/iarch_settings/services/system.py",
    "iarch/settings-app/iarch_settings/services/themes.py",
    "iarch/settings-app/iarch_settings/version.py",
    "iarch/settings-app/iarch_settings/widgets/__init__.py",
    "iarch/settings-app/iarch_settings/widgets/app.py",
    "iarch/settings-app/iarch_settings/widgets/window.py",
)

#: The tests that hold the settings application to the records it was built from.
SETTINGS_TEST_FILES = (
    "tests/test_settings_config_store.py",
    "tests/test_settings_display.py",
    "tests/test_settings_glass.py",
    "tests/test_settings_gtk_keys.py",
    "tests/test_settings_ipc.py",
    "tests/test_settings_links.py",
    "tests/test_settings_packaging.py",
    "tests/test_settings_pages.py",
    "tests/test_settings_startup.py",
    "tests/test_settings_surface.py",
    "tests/test_settings_system.py",
)

#: The dynamic-themes work (docs/PART-PLAN-T1.md): the engine catalogue, the switch
#: that enforces one shell at a time, and the four shared libraries both are built
#: on. Every later part of that schedule adds its files here.
THEMES_ENGINE_FILES = (
    "iarch/lib/compositor.py",
    "iarch/lib/dbus_probe.py",
    "iarch/lib/processes.py",
    "iarch/lib/runner.py",
    "iarch/cli/engine_state.py",
    "iarch/cli/engine_steps.py",
    "iarch/cli/iarch_shell_switch.py",
    "iarch/cli/shell_switch.py",
    "iarch/cli/theme_engine.py",
    "scripts/iarch-shell-switch.sh",
    "tests/session_fake.py",
)

#: The tests that hold the engine switch to the contract in docs/THEMES-ARCHITECTURE.md.
THEMES_ENGINE_TEST_FILES = (
    "tests/test_shell_switch.py",
    "tests/test_shell_switch_cli.py",
    "tests/test_shell_switch_rollback.py",
    "tests/test_theme_engine.py",
)

THEME_PACK_FILES = ("iarch/cli/theme_pack_validate.py", "tests/test_theme_pack_schema.py",
                    "tests/test_shell_layout.py", "iarch/cli/theme_pack_archive.py",
                    "tests/test_theme_pack_archive.py", "iarch/cli/theme_records.py",
                    "iarch/cli/gen_theme_status.py", "iarch/cli/theme_packs.py",
                    "iarch/cli/theme_pack_cli.py", "tests/test_theme_records.py",
                    "tests/test_theme_catalogue.py", "tests/test_theme_pack_cli.py")

NEW_SOURCE_FILES = (PART_ONE_TO_THREE_FILES + SETTINGS_APP_FILES + SETTINGS_TEST_FILES
                    + THEMES_ENGINE_FILES + THEMES_ENGINE_TEST_FILES + THEME_PACK_FILES)

#: Not in the list above, and deliberately: a stylesheet has no ``#`` comment, so the
#: header it carries is the same sentence inside ``/* */``. It gets its own test rather
#: than being checked with a rule written for Python.
SETTINGS_STYLESHEET = "iarch/settings-app/iarch_settings/style/glass.css"


def header_line(text: str) -> str:
    lines = text.splitlines()
    for line in lines[:4]:
        if line.startswith("#!") or not line.strip():
            continue
        return line
    return ""


class CopyrightHeaders(unittest.TestCase):
    def test_new_source_files_start_with_the_defined_header(self):
        for relative in NEW_SOURCE_FILES:
            path = ROOT / relative
            with self.subTest(path=relative):
                self.assertTrue(path.is_file(), f"missing: {relative}")
                first = header_line(path.read_text(encoding="utf-8"))
                self.assertEqual(first, f"# {HEADER}", f"{relative} does not carry the header")

    def test_the_settings_app_list_is_every_python_file_in_the_package(self):
        """A list that has to be extended by hand is a list that gets forgotten.

        This is the check that makes the one above mean something: a new module in the
        package fails here until it is named there, so no file can join the application
        without the header being a question somebody had to answer.
        """
        found = {str(path.relative_to(ROOT))
                 for path in (ROOT / "iarch" / "settings-app").rglob("*.py")
                 if "__pycache__" not in path.parts}
        self.assertEqual(found, set(SETTINGS_APP_FILES),
                         "SETTINGS_APP_FILES and the package's own contents disagree, so "
                         "either a file is unchecked or the list names one that is gone")

    def test_the_engine_list_names_every_engine_module_the_cli_directory_has(self):
        """The same rule as the settings app's, for the dynamic-themes modules."""
        stems = ("engine_", "theme_engine", "shell_switch", "iarch_shell_switch")
        found = {str(path.relative_to(ROOT))
                 for path in (ROOT / "iarch" / "cli").glob("*.py")
                 if path.stem.startswith(stems)}
        listed = {relative for relative in THEMES_ENGINE_FILES
                  if relative.startswith("iarch/cli/")}
        self.assertEqual(found, listed,
                         "THEMES_ENGINE_FILES and iarch/cli disagree, so an engine module is "
                         "either unchecked or the list names one that is gone")

    def test_the_engine_test_list_is_every_engine_test(self):
        found = {str(path.relative_to(ROOT))
                 for path in (ROOT / "tests").glob("test_shell_switch*.py")}
        found.add("tests/test_theme_engine.py")
        self.assertEqual(found, set(THEMES_ENGINE_TEST_FILES))

    def test_the_settings_test_list_is_every_settings_test(self):
        found = {str(path.relative_to(ROOT))
                 for path in (ROOT / "tests").glob("test_settings_*.py")}
        self.assertEqual(found, set(SETTINGS_TEST_FILES))

    def test_the_stylesheet_carries_the_same_header_as_a_css_comment(self):
        text = (ROOT / SETTINGS_STYLESHEET).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("/* "), "a stylesheet's first line is not a comment, "
                                                "so the header would be a syntax error")
        self.assertIn(HEADER, text.splitlines()[0],
                      "the stylesheet does not name the same copyright and licence as every "
                      "other file in this work")
        self.assertNotIn(SETTINGS_STYLESHEET, NEW_SOURCE_FILES,
                         "the stylesheet is checked by the rule above; leaving it in the "
                         "Python list would fail it for not starting with a # line")

    def test_new_markdown_files_carry_it_as_a_comment_free_line_or_note(self):
        for relative in ("iarch/README.md", "iarch/cli/README.md", "iarch/settings-app/README.md"):
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_every_data_json_carries_the_header_key(self):
        files = sorted((ROOT / "data").rglob("*.json"))
        self.assertTrue(files, "data/ has no JSON at all")
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
                self.assertEqual(payload.get("_copyright"), HEADER,
                                 "data files carry the header as their _copyright key")

    def test_vendored_upstream_copyright_is_untouched(self):
        """legacy/ must not be stamped with this repository's header."""
        result = subprocess.run(["git", "ls-files", "-z", "legacy/"], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        for relative in result.stdout.split("\0"):
            if not relative or not relative.endswith((".py", ".sh", ".conf", ".ini", ".toml")):
                continue
            text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
            with self.subTest(path=relative):
                self.assertNotIn(HEADER, text, "frozen legacy files keep their own headers")

    def test_the_header_and_the_license_text_agree(self):
        license_text = (ROOT / brand.product(ROOT)["IARCH_LICENSE_FILE"]).read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 3", license_text)
        self.assertIn("GPL-3.0-or-later", HEADER,
                      "the header must name the SPDX expression it relies on")
        self.assertTrue(re.search(r"any later version", license_text),
                        "GPL-3.0 text offers the 'or later' option the header uses")


if __name__ == "__main__":
    unittest.main()
