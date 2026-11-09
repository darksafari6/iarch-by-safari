"""Tests for the branding lint: extractors, levels and detection.

The lint is the guard that keeps the everyday UI saying "iArch by Safari".
These tests check both directions: a clean repository reports nothing, and a
planted violation is caught.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("branding_lint", ROOT / "tools" / "branding_lint.py")
lint = importlib.util.module_from_spec(spec)
sys.modules["branding_lint"] = lint
spec.loader.exec_module(lint)


class Extractors(unittest.TestCase):
    def test_lua_extracts_descriptions_not_commands(self):
        text = (
            'hl.bind("SUPER + I", hl.dsp.exec_cmd("noctalia msg panel-toggle control-center"), '
            '{ description = "Open Control Center" })\n'
            'local TERMINAL = "kitty"\n'
        )
        self.assertEqual(lint.lua_descriptions(text), ["Open Control Center"])

    def test_desktop_fields_ignore_marker_and_paths(self):
        text = (
            "[Desktop Entry]\n"
            "# Managed by minimaLinux session installer\n"
            "Name=iArch by Safari (isolated session)\n"
            "Name[de]=iArch by Safari (isolierte Sitzung)\n"
            "Comment=Hyprland desktop\n"
            "Exec=/usr/local/bin/minimalinux-session\n"
            "TryExec=/usr/local/bin/minimalinux-session\n"
        )
        self.assertEqual(
            lint.desktop_display_fields(text),
            ["iArch by Safari (isolated session)", "iArch by Safari (isolierte Sitzung)", "Hyprland desktop"],
        )

    def test_fastfetch_display_ignores_schema_url(self):
        text = (
            '{\n'
            '    "$schema": "https://github.com/fastfetch-cli/fastfetch/raw/dev/doc/json_schema.json",\n'
            '    "display": { "separator": " -> " },\n'
            '    "modules": [ { "type": "os", "key": "OS   ", "format": "{} x64" } ]\n'
            '}\n'
        )
        self.assertEqual(lint.fastfetch_display(text), ["OS   ", "{} x64"])

    def test_toml_values_and_invalid_input(self):
        self.assertEqual(lint.toml_string_values('[a]\nb = "x"\nc = ["y"]\n'), ["x", "y"])
        self.assertEqual(lint.toml_string_values("not toml at all ==="), [])

    def test_shell_output_lines_only(self):
        text = (
            "#!/usr/bin/env bash\n"
            "# minimaLinux is only a comment here\n"
            "printf '\\niArch by Safari desktop health check\\n'\n"
            "noctalia msg panel-toggle launcher\n"
            "info 'Nothing to do'\n"
        )
        found = lint.shell_printed_strings(text)
        self.assertIn("iArch by Safari desktop health check", found)
        self.assertIn("Nothing to do", found)
        self.assertNotIn("noctalia msg panel-toggle launcher", found)

    def test_gtk_ui_strings_pick_widget_copy(self):
        text = (
            "backend.ipc('settings', 'toggle')\n"
            "super().__init__(title='iArch by Safari · Customize')\n"
            "self.label(box, 'The shell must be running.')\n"
        )
        found = lint.gtk_ui_strings(text)
        self.assertIn("iArch by Safari · Customize", found)
        self.assertIn("The shell must be running.", found)


class Detection(unittest.TestCase):
    def test_repository_surfaces_are_clean(self):
        self.assertEqual(lint.scan(ROOT), [])

    def test_levels_differ_on_upstream_shell_name(self):
        self.assertIn("Noctalia", lint.LEVELS["product"])
        self.assertNotIn("Noctalia", lint.LEVELS["identity"])
        for level in lint.LEVELS:
            self.assertIn("minimaLinux", lint.LEVELS[level])

    def test_planted_violation_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "branding").mkdir()
            shutil.copy2(ROOT / "branding" / "product.env", root / "branding" / "product.env")
            hypr = root / ".config" / "hypr"
            hypr.mkdir(parents=True)
            (hypr / "keybind.lua").write_text(
                'hl.bind("SUPER + I", f, { description = "Open minimaOS Control Center" })\n',
                encoding="utf-8",
            )
            findings = lint.scan(root)
            tokens = {(f.surface_id, f.token) for f in findings}
            self.assertIn(("keybind-descriptions", "minimaOS"), tokens)

    def test_missing_required_product_name_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "branding").mkdir()
            shutil.copy2(ROOT / "branding" / "product.env", root / "branding" / "product.env")
            fish = root / ".config" / "fish"
            fish.mkdir(parents=True)
            (fish / "config.fish").write_text('set -g fish_greeting "Welcome"\n', encoding="utf-8")
            findings = [f for f in lint.scan(root) if f.level == "required"]
            self.assertTrue(findings)
            self.assertEqual(findings[0].surface_id, "terminal-greeting")

    def test_report_and_cli(self):
        self.assertIn("0 finding(s)", lint.report([]))
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "branding_lint.py"), "--json"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout), [])

        surfaces = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "branding_lint.py"), "--surfaces"],
            capture_output=True, text=True,
        )
        self.assertEqual(surfaces.returncode, 0)
        self.assertIn("keybind-descriptions", surfaces.stdout)
        self.assertIn("Not scanned:", surfaces.stdout)

    def test_every_declared_surface_exists_in_the_repository(self):
        for surface in lint.SURFACES:
            self.assertTrue(lint.surface_files(surface, ROOT), f"no files match {surface.pattern}")
            self.assertIn(surface.level, lint.LEVELS)


if __name__ == "__main__":
    unittest.main()
