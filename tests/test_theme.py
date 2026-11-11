# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Prove iarch-theme applies one choice across every surface, safely.

These tests never start a desktop and never touch a real home: the live config
root is a temporary ``--config-home``, user state is a temporary
``IARCH_CONFIG_DIR``, and the reload commands are stubbed at ``shutil.which`` and
``subprocess.run``. Rendering the GTK sheets needs Jinja2, so the tests that
actually render are guarded the same way ``test_gtk_css`` guards them; the
pure-logic tests (resolution, the contrast gate, the cursor and icon reports,
argument errors) run everywhere.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import theme  # noqa: E402
from iarch.cli import contrast_check  # noqa: E402
from iarch.lib import configstore  # noqa: E402

try:
    import jinja2  # noqa: F401
    HAVE_JINJA = True
except ImportError:
    HAVE_JINJA = False

try:
    import jsonschema  # noqa: F401
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

requires_jinja = unittest.skipUnless(HAVE_JINJA, "Jinja2 is not installed")
requires_jsonschema = unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema is not installed")

# The nine surfaces one apply renders, relative to --config-home.
EXPECTED_TARGETS = (
    "hypr/generated/glass.lua",
    "hypr/generated/animations.lua",
    "gtk-4.0/gtk.css",
    "gtk-3.0/gtk.css",
    "Kvantum/kvantum.kvconfig",
    "Kvantum/iarch/iarch.kvconfig",
    "fontconfig/fonts.conf",
    "noctalia/config.toml",
    "noctalia/palettes/iarch-midnight.json",
)


class ThemeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._clean)
        self.home = self.tmp / "config-home"   # the live ~/.config stand-in
        self.home.mkdir()
        self.env = {
            "IARCH_CONFIG_DIR": str(self.tmp / "iarch-config"),
            "IARCH_STATE_DIR": str(self.tmp / "iarch-state"),
        }

    def _clean(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, argv, env=None):
        """Run theme.main with our state dirs in the environment; capture output."""
        merged = dict(os.environ)
        merged.update(self.env if env is None else env)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, merged, clear=True):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = theme.main(argv)
        return code, out.getvalue(), err.getvalue()

    def apply_argv(self, *extra):
        return ["apply", *extra, "--config-home", str(self.home)]

    def write_user_settings(self, payload):
        path = configstore.user_path("settings", self.env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def read_user_settings(self):
        path = configstore.user_path("settings", self.env)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


class Resolution(ThemeBase):
    """Which colour preset and intensity an apply settles on, and why."""

    def test_defaults_to_midnight_glass_at_the_preset_intensity(self):
        _tokens, preset, colour, intensity = theme._resolve(None, None, self.env)
        self.assertEqual(colour, "midnight-glass")
        self.assertEqual(intensity, preset.get("default_intensity"))
        self.assertEqual(preset["id"], "midnight-glass")

    def test_command_line_wins_over_everything(self):
        self.write_user_settings({"theme": {"colour_preset": "aurora", "intensity": "soft"}})
        _tokens, _preset, colour, intensity = theme._resolve("mono-ice", "crystal", self.env)
        self.assertEqual((colour, intensity), ("mono-ice", "crystal"))

    def test_user_settings_win_over_the_preset_default(self):
        self.write_user_settings({"theme": {"colour_preset": "aurora", "intensity": "performance"}})
        _tokens, _preset, colour, intensity = theme._resolve(None, None, self.env)
        self.assertEqual((colour, intensity), ("aurora", "performance"))

    def test_intensity_falls_back_to_the_preset_not_the_repo_default(self):
        # A user who recorded only a colour preset still gets that preset's own
        # default_intensity, not the repository default, until they choose one.
        self.write_user_settings({"theme": {"colour_preset": "aurora"}})
        _tokens, preset, colour, intensity = theme._resolve(None, None, self.env)
        self.assertEqual(colour, "aurora")
        self.assertEqual(intensity, preset.get("default_intensity"))

    def test_unknown_preset_is_a_usage_error(self):
        code, _out, err = self.run_cli(self.apply_argv("not-a-preset", "--dry-run"))
        self.assertEqual(code, theme.EXIT_USAGE)
        self.assertIn("unknown colour preset", err)
        self.assertIn("midnight-glass", err, "the message lists the valid ids")

    def test_unknown_intensity_is_a_usage_error(self):
        code, _out, err = self.run_cli(self.apply_argv("midnight-glass", "--intensity", "sparkle",
                                                       "--dry-run"))
        self.assertEqual(code, theme.EXIT_USAGE)
        self.assertIn("unknown intensity", err)
        self.assertIn("frosted", err)

    def test_relative_config_home_is_refused(self):
        code, _out, err = self.run_cli(["apply", "midnight-glass", "--config-home", "relative/dir",
                                        "--dry-run"])
        self.assertEqual(code, theme.EXIT_USAGE)
        self.assertIn("absolute", err)


class ContrastGate(ThemeBase):
    """The gate runs before any render or write and refuses on exit 1."""

    def test_a_preset_below_the_floor_is_refused_and_writes_nothing(self):
        failing = [contrast_check.Result("body text on background", "#000000", "#000000",
                                         1.0, 4.5, "text")]
        with mock.patch.object(theme.contrast_check, "evaluate", return_value=failing):
            code, _out, err = self.run_cli(self.apply_argv("midnight-glass"))
        self.assertEqual(code, theme.EXIT_REFUSED)
        self.assertIn("contrast gate refused", err)
        self.assertEqual([], list(self.home.rglob("*")), "nothing was written under --config-home")
        self.assertIsNone(self.read_user_settings(), "settings were not touched")

    def test_an_info_pair_below_its_floor_does_not_refuse(self):
        # contrast_check marks decorative/terminal-dim pairs "info": measured, never
        # gated. A low info ratio must not block an otherwise-passing preset.
        results = [
            contrast_check.Result("body text on background", "#ffffff", "#000000", 21.0, 4.5, "text"),
            contrast_check.Result("terminal dim", "#333333", "#000000", 1.2, 1.0, "info"),
        ]
        with mock.patch.object(theme.contrast_check, "evaluate", return_value=results):
            gated, lowest = theme._contrast_gate("midnight-glass", {})
        self.assertEqual(gated, 1)
        self.assertAlmostEqual(lowest, 21.0)


class CursorAndIcon(ThemeBase):
    """The cursor is verified against the static export; the icon is reported only."""

    def setUp(self):
        super().setUp()
        self.preset = json.loads(
            (ROOT / "data" / "design" / "presets" / "midnight-glass.json").read_text())

    def test_agreeing_cursor_is_reported_as_unchanged(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            theme._report_cursor(self.preset)
        self.assertIn("Bibata-Modern-Classic", out.getvalue())
        self.assertIn("unchanged", out.getvalue())
        self.assertEqual("", err.getvalue(), "an agreeing cursor is not a warning")

    def test_a_divergent_cursor_warns_without_inventing_a_switch(self):
        with mock.patch.object(theme, "_cursor_in_theme_lua", return_value=("SomeOther", 32)):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                theme._report_cursor(self.preset)
        self.assertIn("does not switch the cursor at runtime", err.getvalue())
        self.assertIn("SomeOther", err.getvalue())

    def test_the_static_cursor_matches_every_shipped_preset(self):
        static_theme, static_size = theme._cursor_in_theme_lua()
        self.assertEqual((static_theme, static_size), ("Bibata-Modern-Classic", 24))
        for path in sorted((ROOT / "data" / "design" / "presets").glob("*.json")):
            cursor = json.loads(path.read_text())["cursor"]
            self.assertEqual((cursor["theme"], cursor["size"]), (static_theme, static_size),
                             f"{path.name} would make the cursor check warn")

    def test_icon_theme_is_reported_with_its_todo_id(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            theme._report_icon(self.preset)
        text = out.getvalue()
        self.assertIn("Papirus-Dark", text)
        self.assertIn("not applied", text)
        self.assertIn("TP-19", text)
        self.assertIn("TODO(verify)", text)


class CurrentCommand(ThemeBase):
    def test_current_reports_the_effective_theme_without_rendering(self):
        code, out, _err = self.run_cli(["current", "--config-home", str(self.home)])
        self.assertEqual(code, theme.EXIT_OK)
        self.assertIn("iArch by Safari", out)
        self.assertIn("midnight-glass", out)
        self.assertIn("frosted", out)
        self.assertIn("repository default", out, "no user settings yet")

    def test_current_reflects_recorded_settings(self):
        self.write_user_settings({"theme": {"colour_preset": "aurora", "intensity": "crystal"}})
        code, out, _err = self.run_cli(["current", "--config-home", str(self.home)])
        self.assertEqual(code, theme.EXIT_OK)
        self.assertIn("aurora", out)
        self.assertIn("crystal", out)
        self.assertNotIn("repository default", out)


@requires_jinja
class ApplyDryRun(ThemeBase):
    def test_dry_run_renders_but_writes_nothing(self):
        code, out, _err = self.run_cli(self.apply_argv("midnight-glass", "--dry-run"))
        self.assertEqual(code, theme.EXIT_OK)
        self.assertIn("would write", out)
        self.assertIn("no settings change, no reload", out)
        self.assertEqual([], list(self.home.rglob("*")), "dry run left --config-home empty")
        self.assertIsNone(self.read_user_settings(), "dry run did not create settings.json")

    def test_dry_run_still_gates_on_contrast(self):
        failing = [contrast_check.Result("outline against surface", "#000000", "#010101",
                                         1.0, 3.0, "ui")]
        with mock.patch.object(theme.contrast_check, "evaluate", return_value=failing):
            code, _out, err = self.run_cli(self.apply_argv("midnight-glass", "--dry-run"))
        self.assertEqual(code, theme.EXIT_REFUSED)
        self.assertIn("contrast gate refused", err)


@requires_jinja
class ApplyWrites(ThemeBase):
    def test_apply_writes_every_surface_under_the_live_config_home(self):
        code, out, _err = self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        self.assertEqual(code, theme.EXIT_OK)
        for relative in EXPECTED_TARGETS:
            path = self.home / relative
            self.assertTrue(path.is_file(), f"{relative} was not written")
        # The Hyprland files land where hyprland.lua reads them, not in iarch's dir.
        self.assertTrue((self.home / "hypr" / "generated" / "glass.lua").is_file())
        self.assertFalse((Path(self.env["IARCH_CONFIG_DIR"]) / "hypr").exists(),
                         "apply must not write the glass payload into ~/.config/iarch")
        self.assertIn("applied 'midnight-glass'", out)

    def test_every_written_file_carries_the_generated_header(self):
        self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        for relative in EXPECTED_TARGETS:
            path = self.home / relative
            first = path.read_text(encoding="utf-8").splitlines()[0]
            if path.suffix == ".json":
                blob = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(blob.get("_generated"), configstore.GENERATED_HEADER, relative)
            else:
                self.assertTrue(configstore.is_header_line(first),
                                f"{relative} line 1 is not a GENERATED header: {first!r}")

    def test_second_apply_changes_nothing(self):
        self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        code, out, _err = self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        self.assertEqual(code, theme.EXIT_OK)
        self.assertIn("wrote 0, unchanged 9", out)
        self.assertNotIn("  write  ", out)

    def test_apply_records_the_theme_in_settings(self):
        self.run_cli(self.apply_argv("midnight-glass", "--intensity", "soft", "--no-reload"))
        settings = self.read_user_settings()
        self.assertEqual(settings["theme"], {"colour_preset": "midnight-glass", "intensity": "soft"})

    def test_apply_preserves_legacy_settings_keys(self):
        self.write_user_settings({
            "version": 1, "preset": "performance",
            "effects": {"blur": False, "transparency": False, "animations": False, "shadows": False},
        })
        self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        settings = self.read_user_settings()
        self.assertEqual(settings["preset"], "performance", "the Part-1 master switch is untouched")
        self.assertFalse(settings["effects"]["animations"], "the effect toggles are untouched")
        self.assertEqual(settings["theme"]["colour_preset"], "midnight-glass")

    def test_reapplying_the_same_theme_does_not_rotate_a_settings_backup(self):
        self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        backup_dir = configstore.backup_dir(self.env)
        before = len(list(backup_dir.iterdir())) if backup_dir.is_dir() else 0
        self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        after = len(list(backup_dir.iterdir())) if backup_dir.is_dir() else 0
        self.assertEqual(before, after, "an idempotent re-apply must not churn backups")


@requires_jinja
class Reload(ThemeBase):
    def test_apply_runs_both_verified_reload_commands(self):
        with mock.patch("shutil.which", return_value="/usr/bin/found"), \
                mock.patch("subprocess.run") as run:
            code, out, _err = self.run_cli(self.apply_argv("midnight-glass"))
        self.assertEqual(code, theme.EXIT_OK)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(("hyprctl", "reload"), commands)
        self.assertIn(("noctalia", "msg", "config-reload"), commands)
        self.assertIn("ran `hyprctl reload`", out)

    def test_no_reload_never_shells_out(self):
        with mock.patch("shutil.which", return_value="/usr/bin/found"), \
                mock.patch("subprocess.run") as run:
            code, out, _err = self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        self.assertEqual(code, theme.EXIT_OK)
        run.assert_not_called()
        self.assertIn("reload: skipped (--no-reload)", out)

    def test_a_missing_reload_binary_is_a_warning_not_a_failure(self):
        with mock.patch("shutil.which", return_value=None), \
                mock.patch("subprocess.run") as run:
            code, _out, err = self.run_cli(self.apply_argv("midnight-glass"))
        self.assertEqual(code, theme.EXIT_OK, "a desktop without hyprctl still applies")
        run.assert_not_called()
        self.assertIn("hyprctl not found on PATH", err)
        self.assertIn("noctalia not found on PATH", err)

    def test_a_failing_reload_command_is_nonfatal(self):
        with mock.patch("shutil.which", return_value="/usr/bin/found"), \
                mock.patch("subprocess.run", side_effect=OSError("boom")):
            code, _out, err = self.run_cli(self.apply_argv("midnight-glass"))
        self.assertEqual(code, theme.EXIT_OK)
        self.assertIn("failed: boom", err)


@requires_jinja
class Rollback(ThemeBase):
    def test_a_write_that_fails_part_way_puts_every_file_back(self):
        real = configstore.write_generated

        def flaky(path, body, env=None):
            if "gtk-4.0" in str(path):
                raise OSError("simulated write failure")
            return real(path, body, env)

        with mock.patch.object(theme.configstore, "write_generated", side_effect=flaky):
            code, _out, err = self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))
        self.assertEqual(code, theme.EXIT_USAGE)
        self.assertIn("simulated write failure", err)
        # glass.lua and animations.lua are written before gtk-4.0; both must be gone.
        self.assertFalse((self.home / "hypr" / "generated" / "glass.lua").exists())
        self.assertFalse((self.home / "hypr" / "generated" / "animations.lua").exists())
        self.assertFalse((self.home / "gtk-4.0" / "gtk.css").exists())

    def test_rollback_restores_a_file_it_overwrote(self):
        # Pre-seed glass.lua with sentinel content, then fail a later write; the
        # sentinel must come back byte for byte.
        glass = self.home / "hypr" / "generated" / "glass.lua"
        glass.parent.mkdir(parents=True, exist_ok=True)
        glass.write_text("SENTINEL\n", encoding="utf-8")
        real = configstore.write_generated

        def flaky(path, body, env=None):
            if "gtk-4.0" in str(path):
                raise OSError("simulated write failure")
            return real(path, body, env)

        with mock.patch.object(theme.configstore, "write_generated", side_effect=flaky):
            code = self.run_cli(self.apply_argv("midnight-glass", "--no-reload"))[0]
        self.assertEqual(code, theme.EXIT_USAGE)
        self.assertEqual(glass.read_text(encoding="utf-8"), "SENTINEL\n")


@requires_jsonschema
class SettingsSchema(unittest.TestCase):
    """The additive theme block keeps a pre-Part-2 settings.json valid."""

    def setUp(self):
        self.schema = json.loads((ROOT / "data" / "schemas" / "settings.schema.json").read_text())

    def test_the_shipped_default_validates(self):
        default = json.loads((ROOT / "data" / "settings.default.json").read_text())
        jsonschema.validate(default, self.schema)
        self.assertEqual(default["theme"], {"colour_preset": "midnight-glass", "intensity": "frosted"})

    def test_a_legacy_settings_file_without_theme_still_validates(self):
        legacy = {"version": 1, "preset": "glass",
                  "effects": {"blur": True, "transparency": True, "animations": True, "shadows": True}}
        jsonschema.validate(legacy, self.schema)

    def test_a_bad_intensity_is_rejected(self):
        bad = {"version": 1, "preset": "glass",
               "effects": {"blur": True, "transparency": True, "animations": True, "shadows": True},
               "theme": {"colour_preset": "midnight-glass", "intensity": "sparkle"}}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, self.schema)

    def test_theme_is_optional_at_the_top_level(self):
        self.assertNotIn("theme", self.schema["required"])


if __name__ == "__main__":
    unittest.main()
