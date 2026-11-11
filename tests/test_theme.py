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
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List
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

# The eleven surfaces one apply renders, relative to --config-home. The last two
# sit in hypr/ itself rather than hypr/generated/, because hyprlock and hypridle
# each search for their own fixed filename ($XDG_CONFIG_HOME/hypr/<tool>.conf) and
# have no include mechanism to point at a generated directory.
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
    "hypr/hyprlock.conf",
    "hypr/hypridle.conf",
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
class ReduceMotionReachesEverySurfaceItGoverns(unittest.TestCase):
    """One accessibility switch, two renderers, and no silent disagreement.

    ``iarch-anim`` owns the switch and the compositor half of it. ``iarch-theme``
    renders the other half, because GTK 3 cannot parse an @media query at all and
    so has no way to hear the desktop's preference: the only lever is the sheet
    itself. These tests are about the seam between the two commands.
    """

    def setUp(self):
        self.base = ThemeBase()
        self.base.setUp()
        self.addCleanup(self.base._clean)
        for name in ("home", "env", "tmp"):
            setattr(self, name, getattr(self.base, name))

    def run_cli(self, argv):
        return self.base.run_cli(argv)

    def apply(self, *extra):
        return self.run_cli(self.base.apply_argv("--no-reload", *extra))

    def durations(self, version: str) -> List[int]:
        text = (self.home / f"gtk-{version}.0" / "gtk.css").read_text(encoding="utf-8")
        return [int(value) for value in
                re.findall(r"transition-duration:\s*(\d+)ms", text)]

    def animations(self) -> str:
        return (self.home / "hypr" / "generated" / "animations.lua").read_text(encoding="utf-8")

    def test_the_flag_zeroes_both_gtk_sheets(self):
        code, _out, _err = self.apply("--reduce-motion", "on")
        self.assertEqual(theme.EXIT_OK, code)
        for version in ("4", "3"):
            values = self.durations(version)
            with self.subTest(version=version):
                self.assertTrue(values, "the sheet stopped transitioning anything at all")
                self.assertEqual({0}, set(values))

    def test_the_flag_renders_the_forced_preset_on_the_compositor_side_too(self):
        # A theme apply that zeroed the GTK sheets while restoring 380ms workspace
        # slides in the compositor would be worse than either half alone.
        code, _out, _err = self.apply("--reduce-motion", "on")
        self.assertEqual(theme.EXIT_OK, code)
        body = self.animations()
        self.assertIn("animations/minimal.json", body)
        speeds = [float(v) for v in re.findall(r"speed = ([\d.]+)", body)]
        self.assertTrue(speeds)
        # speed = duration_ms / 100, so the 90ms cap is a speed of 0.9.
        self.assertLessEqual(max(speeds), 0.9)

    def test_apply_follows_the_switch_iarch_anim_recorded(self):
        self.base.write_user_settings({"animation": {"reduce_motion": True}})
        code, out, _err = self.apply()
        self.assertEqual(theme.EXIT_OK, code)
        self.assertIn("reduce motion:   on", out)
        self.assertEqual({0}, set(self.durations("3")))
        self.assertIn("animations/minimal.json", self.animations())

    def test_the_flag_overrides_what_was_recorded(self):
        self.base.write_user_settings({"animation": {"reduce_motion": True}})
        code, out, _err = self.apply("--reduce-motion", "off")
        self.assertEqual(theme.EXIT_OK, code)
        self.assertNotIn("reduce motion:", out)
        self.assertNotIn(0, self.durations("3"))
        # The recorded switch is the user's; overriding it for one render must not
        # rewrite it behind their back.
        self.assertTrue(self.base.read_user_settings()["animation"]["reduce_motion"])

    def test_motion_stays_on_when_nothing_was_recorded(self):
        code, _out, _err = self.apply()
        self.assertEqual(theme.EXIT_OK, code)
        fast = theme.gen_animations_lua.load_tokens()["motion"]["fast_ms"]
        self.assertIn(fast, self.durations("4"))
        self.assertNotIn("animations/minimal.json", self.animations())

    def test_reduce_motion_changes_nothing_it_does_not_govern(self):
        # The glass, the shell config and the palette are colour and blur
        # decisions. An accessibility switch must not quietly re-decorate them.
        # Keyed by relative path, not file name: both sheets are called gtk.css.
        def snapshot():
            return {str(path.relative_to(self.home)): path.read_bytes()
                    for path in sorted(self.home.rglob("*")) if path.is_file()}

        self.apply()
        before = snapshot()
        self.apply("--reduce-motion", "on")
        after = snapshot()
        self.assertEqual(sorted(before), sorted(after),
                         "reduce-motion added or removed a file")
        changed = sorted(name for name in before if before[name] != after[name])
        self.assertEqual(sorted(["hypr/generated/animations.lua",
                                 "gtk-3.0/gtk.css", "gtk-4.0/gtk.css"]), changed,
                         f"reduce-motion rewrote {changed}")

    def test_a_recorded_animation_block_survives_a_theme_apply(self):
        recorded = {"preset": "bouncy", "speed": 1.5, "reduce_motion": True,
                    "event_overrides": {"borderangle": False}}
        self.base.write_user_settings({"animation": recorded})
        code, _out, _err = self.apply()
        self.assertEqual(theme.EXIT_OK, code)
        self.assertEqual(recorded, self.base.read_user_settings()["animation"])

    def test_apply_names_the_animation_state_it_is_about_to_overwrite(self):
        self.base.write_user_settings({"animation": {
            "preset": "bouncy", "speed": 1.5,
            "event_overrides": {"borderangle": False, "fadeDim": False}}})
        code, _out, err = self.apply()
        self.assertEqual(theme.EXIT_OK, code)
        self.assertIn("animation.preset='bouncy'", err)
        self.assertIn("animation.speed=1.5", err)
        self.assertIn("2 per-event override(s)", err)
        self.assertIn("iarch-anim", err, "the warning must name the command that owns it")

    def test_no_divergence_is_reported_when_the_states_agree(self):
        self.base.write_user_settings({"animation": {"preset": "smooth", "speed": 1.0,
                                                     "event_overrides": {}}})
        code, _out, err = self.apply()
        self.assertEqual(theme.EXIT_OK, code)
        self.assertNotIn("iarch-anim recorded", err)

    def test_no_divergence_is_reported_when_nothing_was_recorded(self):
        code, _out, err = self.apply()
        self.assertEqual(theme.EXIT_OK, code)
        self.assertNotIn("iarch-anim recorded", err)

    def test_a_malformed_settings_file_is_reported_not_traced(self):
        # The settings file is hand-editable by design, so a stray comma is an
        # expected event: it has to name the file and say what to do, and it must
        # not escape as a JSONDecodeError traceback out of main().
        path = self.base.write_user_settings({})
        path.write_text("{not json", encoding="utf-8")
        code, _out, err = self.apply()
        self.assertEqual(theme.EXIT_USAGE, code)
        self.assertIn(str(path), err)
        self.assertIn("not valid JSON", err)
        self.assertIn("repository defaults", err)
        self.assertNotIn("Traceback", err)
        # Nothing was written on the strength of a file nobody could read.
        self.assertFalse((self.home / "gtk-4.0" / "gtk.css").exists())

    def test_current_says_where_the_switch_came_from(self):
        code, out, _err = self.run_cli(["current", "--config-home", str(self.home)])
        self.assertEqual(theme.EXIT_OK, code)
        self.assertIn("reduce motion: off", out)
        self.assertIn("no animation.reduce_motion recorded", out)
        # "repository default" is what current says about a theme value nobody
        # chose; reusing it here would leave that line ambiguous.
        self.assertNotIn("reduce motion: off   (repository default)", out)

        self.base.write_user_settings({"animation": {"reduce_motion": True}})
        code, out, _err = self.run_cli(["current", "--config-home", str(self.home)])
        self.assertEqual(theme.EXIT_OK, code)
        self.assertIn("reduce motion: on", out)
        self.assertIn("settings.json animation.reduce_motion", out)


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
        # Counted from EXPECTED_TARGETS rather than spelled out, so adding a
        # surface cannot leave a stale number asserting the old one.
        self.assertIn(f"wrote 0, unchanged {len(EXPECTED_TARGETS)}", out)
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
