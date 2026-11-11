#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the Qt/Kvantum renderer, ``iarch/cli/render_kvantum.py``.

Kvantum hides its mistakes the way GTK and Noctalia do: QSettings parses a key
``ThemeConfig.cpp`` never asks for and the engine simply ignores it, and an
integer outside its documented bound is clamped and continues. Neither is an
error the user ever sees. So these tests assert against the upstream surface in
``data/design/kvantum.json`` rather than a frozen snapshot of the theme:

* every key the theme writes is one ``ThemeConfig.cpp`` reads, in the section it
  reads it from, with the type the documentation gives it;
* every integer is inside its recorded bound and every enum value inside its set;
* the translucency numbers are derived from the intensity's ``qt`` opacities, and
  the sizing numbers are Kvantum's own verified defaults -- nothing is a value
  the renderer chose for its own sake;
* the two decisions that come from running under Hyprland rather than KDE
  (no Kvantum blurring, no second popup shadow) are written and recorded;
* all 28 colours follow the active palette, so a light preset is not shipped a
  dark theme;
* a refused render writes nothing, and a failed write restores every byte.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import render_kvantum as kv  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS = kv.load_tokens()
SURFACE = kv.load_surface()
PRESET_IDS = sorted(path.stem for path in kv.PRESET_DIR.glob("*.json"))
INTENSITIES = sorted(TOKENS["intensities"])
COMBINATIONS = [(p, i) for p in PRESET_IDS for i in INTENSITIES]
GENERAL = SURFACE["sections"]["%General"]["keys"]
COLORS = SURFACE["sections"]["GeneralColors"]["keys"]


def theme(preset_id: str = "midnight-glass", intensity: str = "frosted") -> Dict[str, Any]:
    return kv.build_theme(TOKENS, kv.load_preset(preset_id), intensity, SURFACE)


def ini_lines(text: str) -> List[str]:
    """The theme's content lines: no comments, no blanks."""
    return [ln for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith(";")]


# --------------------------------------------------------------- the surface


class SurfaceIsTheVocabularyKvantumReads(unittest.TestCase):
    def test_the_counts_match_the_parser_call_sites(self):
        self.assertEqual(89, SURFACE["counts"]["general"])
        self.assertEqual(28, SURFACE["counts"]["general_colors"])
        self.assertEqual(23, SURFACE["counts"]["hacks"])
        self.assertEqual(140, SURFACE["counts"]["total"])

    def test_the_surface_is_pinned_to_a_release_tag_not_a_branch(self):
        self.assertRegex(SURFACE["verified_against"], r"^V?\d+\.\d+\.\d+$")
        self.assertIn("ThemeConfig.cpp", SURFACE["source"])

    def test_every_general_color_has_a_palette_role(self):
        for key, spec in COLORS.items():
            with self.subTest(color=key):
                self.assertEqual("color", spec["type"])
                self.assertTrue(spec["palette_role"])

    def test_the_color_roles_all_resolve_in_every_preset(self):
        for preset_id in PRESET_IDS:
            palette = kv.load_preset(preset_id)["palette"]
            for key, spec in COLORS.items():
                with self.subTest(preset=preset_id, color=key):
                    self.assertRegex(kv.palette_color(palette, spec["palette_role"]),
                                     r"^#[0-9a-f]{6}$")

    def test_activation_is_through_qt6ct_not_an_environment_variable(self):
        self.assertEqual(["kvantum", "kvantum-dark"], SURFACE["activation"]["style_names"])
        self.assertEqual("theme", SURFACE["activation"]["pointer_key"])
        self.assertIn("QT_STYLE_OVERRIDE", SURFACE["activation"]["mechanism"])
        self.assertIn("remove", SURFACE["activation"]["mechanism"])

    def test_the_compositor_decisions_are_recorded_with_their_reasons(self):
        comp = SURFACE["compositor"]
        self.assertIn("KDE", comp["blurring"])
        self.assertIn("decoration:shadow", comp["shadowless_popup"])
        self.assertIn("reduce_window_opacity", comp["translucency_without_svg"])
        self.assertIn("artifact", comp["menu_blur_radius"])

    def test_diagnostics_explain_why_a_typo_is_not_enough(self):
        self.assertIn("ignored", SURFACE["diagnostics"]["unknown_key"])
        self.assertIn("clamp", SURFACE["diagnostics"]["out_of_range"])


# --------------------------------------------------------------- the vocabulary


class EveryEmittedKeyIsOneKvantumReads(unittest.TestCase):
    def test_no_combination_emits_an_unknown_key(self):
        for preset_id, intensity in COMBINATIONS:
            with self.subTest(preset=preset_id, intensity=intensity):
                doc = theme(preset_id, intensity)
                self.assertEqual([], kv.validate(doc, SURFACE))

    def test_the_general_section_only_uses_general_keys(self):
        for key in theme()["%General"]:
            self.assertIn(key, GENERAL)

    def test_the_color_section_is_exactly_the_28_keys(self):
        self.assertEqual(set(COLORS), set(theme()["GeneralColors"]))

    def test_booleans_are_written_as_python_bools_not_strings(self):
        for key, spec in GENERAL.items():
            if spec["type"] != "bool":
                continue
        general = theme()["%General"]
        for key in ("composite", "blurring", "popup_blurring", "shadowless_popup",
                    "translucent_windows", "animate_states"):
            with self.subTest(key=key):
                self.assertIsInstance(general[key], bool)

    def test_an_invented_key_is_refused(self):
        doc = theme()
        doc["%General"]["glassiness"] = 5
        problems = kv.validate(doc, SURFACE)
        self.assertTrue(any("glassiness" in p for p in problems))

    def test_a_key_in_the_wrong_section_is_refused(self):
        doc = theme()
        # window.color is a GeneralColors key, not a [%General] one
        doc["%General"]["window.color"] = "#000000"
        self.assertTrue(any("window.color" in p for p in kv.validate(doc, SURFACE)))

    def test_an_out_of_range_integer_is_refused(self):
        doc = theme()
        doc["%General"]["reduce_window_opacity"] = 95  # the bound is 90
        self.assertTrue(any("above the maximum" in p for p in kv.validate(doc, SURFACE)))

    def test_a_negative_integer_is_refused(self):
        doc = theme()
        doc["%General"]["scroll_width"] = -1
        self.assertTrue(any("below the minimum" in p for p in kv.validate(doc, SURFACE)))

    def test_an_invalid_enum_value_is_refused(self):
        doc = theme()
        doc["%General"]["dialog_button_layout"] = 9  # the set is 0-5
        self.assertTrue(any("not one of" in p for p in kv.validate(doc, SURFACE)))

    def test_a_non_hex_color_is_refused(self):
        doc = theme()
        doc["GeneralColors"]["window.color"] = "black"
        self.assertTrue(any("#rrggbb" in p for p in kv.validate(doc, SURFACE)))

    def test_a_boolean_where_an_integer_belongs_is_refused(self):
        doc = theme()
        doc["%General"]["scroll_width"] = True
        self.assertTrue(any("must be an integer" in p for p in kv.validate(doc, SURFACE)))


# --------------------------------------------------------------- nothing invented


class NothingIsANumberTheRendererInvented(unittest.TestCase):
    def test_the_opacity_reduction_is_derived_from_the_intensity(self):
        for intensity in INTENSITIES:
            qt = TOKENS["intensities"][intensity]["qt"]
            general = kv.build_general(TOKENS, intensity)
            with self.subTest(intensity=intensity):
                self.assertEqual(kv.reduce_opacity(qt["window"]),
                                 general["reduce_window_opacity"])
                self.assertEqual(kv.reduce_opacity(qt["menu"]),
                                 general["reduce_menu_opacity"])

    def test_the_reduction_is_a_percentage_of_what_is_removed(self):
        # a surface kept at 88% fill becomes a 12% reduction, clamped to 0-90
        self.assertEqual(12, kv.reduce_opacity(0.88))
        self.assertEqual(0, kv.reduce_opacity(1.0))
        self.assertEqual(90, kv.reduce_opacity(0.0))
        self.assertEqual(90, kv.reduce_opacity(-1.0))  # clamped, never negative

    def test_the_sizing_keys_are_kvantum_verified_defaults(self):
        general = theme()["%General"]
        for key in ("menu_separator_height", "scroll_width", "slider_width",
                    "check_size", "layout_margin"):
            with self.subTest(key=key):
                self.assertEqual(GENERAL[key]["range"]["default"], general[key])

    def test_the_corner_blur_is_the_documented_anti_artifact_value(self):
        general = theme()["%General"]
        self.assertEqual(2, general["menu_blur_radius"])
        self.assertEqual(2, general["tooltip_blur_radius"])
        self.assertLessEqual(general["menu_blur_radius"], GENERAL["menu_blur_radius"]["range"]["max"])

    def test_layout_spacing_stays_inside_its_bound(self):
        general = theme()["%General"]
        bounds = GENERAL["layout_spacing"]["range"]
        self.assertGreaterEqual(general["layout_spacing"], bounds["min"])
        self.assertLessEqual(general["layout_spacing"], bounds["max"])

    def test_every_integer_is_inside_its_recorded_bound(self):
        general = theme()["%General"]
        for key, spec in GENERAL.items():
            if spec["type"] not in ("int", "int_or_string") or key not in general:
                continue
            bounds = spec.get("range", {})
            value = general[key]
            with self.subTest(key=key):
                self.assertGreaterEqual(value, bounds.get("min", value))
                self.assertLessEqual(value, bounds.get("max", value))

    def test_dialog_button_layout_follows_the_platform(self):
        self.assertEqual(0, theme()["%General"]["dialog_button_layout"])


# --------------------------------------------------------------- the compositor decisions


class TheHyprlandDecisionsAreWritten(unittest.TestCase):
    def test_kvantum_blurring_is_off_because_hyprland_has_no_kde_blur(self):
        general = theme()["%General"]
        self.assertFalse(general["blurring"])
        self.assertFalse(general["popup_blurring"])

    def test_the_compositor_owns_the_popup_shadow(self):
        general = theme()["%General"]
        self.assertTrue(general["shadowless_popup"])
        self.assertEqual(0, general["menu_shadow_depth"])
        self.assertEqual(0, general["tooltip_shadow_depth"])

    def test_composite_is_on_because_wayland_is_always_composited(self):
        self.assertTrue(theme()["%General"]["composite"])

    def test_translucency_tracks_whether_anything_is_translucent(self):
        for intensity in INTENSITIES:
            general = kv.build_general(TOKENS, intensity)
            with self.subTest(intensity=intensity):
                self.assertEqual(general["reduce_window_opacity"] > 0,
                                 general["translucent_windows"])

    def test_performance_is_fully_opaque(self):
        general = kv.build_general(TOKENS, "performance")
        self.assertEqual(0, general["reduce_window_opacity"])
        self.assertEqual(0, general["reduce_menu_opacity"])
        self.assertFalse(general["translucent_windows"])

    def test_the_translucent_intensities_get_progressively_more_opaque(self):
        order = ["crystal", "frosted", "soft"]
        reductions = [kv.build_general(TOKENS, i)["reduce_window_opacity"] for i in order]
        self.assertEqual(sorted(reductions, reverse=True), reductions)


# --------------------------------------------------------------- colours


class ColorsFollowTheActivePalette(unittest.TestCase):
    def test_every_color_equals_its_palette_role(self):
        for preset_id in PRESET_IDS:
            preset = kv.load_preset(preset_id)
            colors = kv.build_colors(preset, SURFACE)
            for key, spec in COLORS.items():
                with self.subTest(preset=preset_id, color=key):
                    self.assertEqual(kv.palette_color(preset["palette"], spec["palette_role"]),
                                     colors[key])

    def test_the_accent_drives_the_highlight(self):
        for preset_id in PRESET_IDS:
            preset = kv.load_preset(preset_id)
            colors = kv.build_colors(preset, SURFACE)
            with self.subTest(preset=preset_id):
                self.assertEqual(preset["palette"]["accent"]["primary"], colors["highlight.color"])
                self.assertEqual(preset["palette"]["on_accent"]["primary"],
                                 colors["highlight.text.color"])

    def test_the_window_and_text_come_from_the_background_roles(self):
        colors = kv.build_colors(kv.load_preset("midnight-glass"), SURFACE)
        palette = kv.load_preset("midnight-glass")["palette"]
        self.assertEqual(palette["background"], colors["window.color"])
        self.assertEqual(palette["on_surface"], colors["text.color"])
        self.assertEqual(palette["shadow"], colors["shadow.color"])

    def test_a_light_preset_is_not_shipped_a_dark_window(self):
        dark = kv.build_colors(kv.load_preset("midnight-glass"), SURFACE)["window.color"]
        light = kv.build_colors(kv.load_preset("frosted-light"), SURFACE)["window.color"]
        self.assertNotEqual(dark, light)
        self.assertGreater(int(light[1:3], 16), 0x80)  # a light window is bright
        self.assertLess(int(dark[1:3], 16), 0x80)      # and a dark one is not
        self.assertLess(int(dark[1:3], 16), int(light[1:3], 16))

    def test_every_color_is_a_six_digit_hex(self):
        for key, value in theme()["GeneralColors"].items():
            with self.subTest(color=key):
                self.assertRegex(value, r"^#[0-9a-f]{6}$")


# --------------------------------------------------------------- writing


class RefusesToWriteUnlessEverythingIsValid(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, "IARCH_STATE_DIR": str(self.root / "state")}
        # patch.dict restores the environment exactly on stop. Clearing and
        # re-updating by hand is wrong here: cleanups run last-in-first-out, so
        # a clear() registered before the restore runs after it and leaves
        # later tests with no PATH at all.
        patcher = unittest.mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_theme_that_fails_validation_is_refused_before_any_write(self):
        original = kv.validate
        kv.validate = lambda doc, surface: ["[%General] glassiness is invented"]
        try:
            with self.assertRaises(kv.KvantumError) as caught:
                kv.targets_for(TOKENS, SURFACE, kv.load_preset("midnight-glass"),
                               "frosted", self.root / "Kvantum")
        finally:
            kv.validate = original
        self.assertIn("not valid", str(caught.exception))
        self.assertEqual([], list((self.root / "Kvantum").rglob("*"))
                         if (self.root / "Kvantum").exists() else [])

    def test_a_failure_part_way_through_leaves_the_filesystem_as_it_was(self):
        good = self.root / "Kvantum" / "kvantum.kvconfig"
        good.parent.mkdir(parents=True)
        good.write_text("; previous\ntheme=old\n", encoding="utf-8")
        blocked = self.root / "blocked" / "iarch.kvconfig"
        blocked.parent.mkdir(parents=True)
        os.chmod(blocked.parent, 0o500)
        self.addCleanup(os.chmod, blocked.parent, 0o700)
        with self.assertRaises(OSError):
            kv.write_all([(good, "theme=iarch"), (blocked, "x")], self.env)
        self.assertEqual("; previous\ntheme=old\n", good.read_text(encoding="utf-8"))
        self.assertFalse(blocked.exists())

    def test_an_existing_theme_keeps_its_mode_and_gains_a_backup(self):
        target = self.root / "iarch.kvconfig"
        target.write_text("; previous\n", encoding="utf-8")
        os.chmod(target, 0o640)
        kv.write_all([(target, "theme=iarch")], self.env)
        self.assertEqual(0o640, target.stat().st_mode & 0o777)
        self.assertTrue([p for p in (self.root / "state" / "backups").rglob("*") if p.is_file()])

    def test_an_unknown_preset_is_reported_with_its_reason(self):
        with self.assertRaises(kv.KvantumError):
            kv.load_preset("no-such-preset")

    def test_an_unknown_intensity_is_reported_and_lists_the_real_ones(self):
        with self.assertRaises(kv.KvantumError) as caught:
            kv.resolve_intensity(TOKENS, kv.load_preset("midnight-glass"), "ultra")
        self.assertIn("frosted", str(caught.exception))

    def test_a_palette_missing_a_role_is_reported_not_crashed(self):
        with self.assertRaises(kv.KvantumError):
            kv.palette_color({"surface": "#000000"}, "accent.primary")


# --------------------------------------------------------------- the shipped payload


class ShippedPayload(unittest.TestCase):
    def tmp_stage(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = Path(tmp.name) / "stage"
        dest.mkdir()
        return dest

    def test_both_files_ship_and_validate(self):
        for path in (kv.REPO_POINTER, kv.REPO_THEME):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), path)
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith(configstore.header_for(path)))

    def test_the_shipped_theme_is_the_default_preset_at_the_default_intensity(self):
        expected = kv.rendered_text(
            kv.REPO_THEME,
            kv.emit_theme(theme("midnight-glass", TOKENS["default_intensity"]),
                          kv.provenance(kv.load_preset("midnight-glass"), SURFACE,
                                        TOKENS["default_intensity"])))
        self.assertEqual(expected, kv.REPO_THEME.read_text(encoding="utf-8"))

    def test_the_pointer_names_the_theme_that_ships_beside_it(self):
        text = kv.REPO_POINTER.read_text(encoding="utf-8")
        self.assertIn(f"theme={kv.THEME_NAME}", text)
        self.assertTrue(kv.REPO_THEME.is_file())

    def test_the_shipped_files_are_readable_and_staged(self):
        for path in (kv.REPO_POINTER, kv.REPO_THEME):
            with self.subTest(path=path.name):
                self.assertTrue(path.stat().st_mode & 0o044)
        staged = subprocess.run(["bash", str(ROOT / "lib" / "stage-v5-config.sh"),
                                 str(ROOT / ".config"), str(self.tmp_stage())],
                                capture_output=True, text=True)
        self.assertEqual(0, staged.returncode, staged.stderr)


# --------------------------------------------------------------- the INI itself


class TheIniIsWhatQtSettingsReads(unittest.TestCase):
    def test_the_header_is_a_semicolon_comment_not_a_hash(self):
        # Qt's INI format comments with ';'. A '#' line would be parsed as a key
        # before any section, which is the same class of bug the CSS header had.
        self.assertEqual("; ", configstore._COMMENT_PREFIX[".kvconfig"])
        self.assertTrue(configstore.header_for(kv.REPO_THEME).startswith("; "))
        self.assertTrue(configstore.is_header_line(configstore.header_for(kv.REPO_THEME)))

    def test_no_content_line_starts_with_a_hash(self):
        for path in (kv.REPO_POINTER, kv.REPO_THEME):
            with self.subTest(path=path.name):
                for line in path.read_text(encoding="utf-8").splitlines():
                    self.assertFalse(line.lstrip().startswith("#"), line)

    def test_the_theme_has_exactly_the_two_sections(self):
        text = kv.REPO_THEME.read_text(encoding="utf-8")
        self.assertEqual(["[%General]", "[GeneralColors]"],
                         [ln for ln in text.splitlines() if ln.startswith("[")])

    def test_the_pointer_has_no_section_only_a_top_level_key(self):
        text = kv.REPO_POINTER.read_text(encoding="utf-8")
        self.assertEqual([], [ln for ln in text.splitlines() if ln.startswith("[")])
        self.assertTrue(any(ln == f"theme={kv.THEME_NAME}" for ln in text.splitlines()))

    def test_booleans_are_lowercase_true_and_false(self):
        text = kv.REPO_THEME.read_text(encoding="utf-8")
        self.assertIn("composite=true", text)
        self.assertIn("blurring=false", text)
        self.assertNotRegex(text, r"=(True|False)\b")

    def test_every_content_line_is_a_section_a_key_or_a_comment(self):
        text = kv.emit_theme(theme(), kv.provenance(kv.load_preset("midnight-glass"),
                                                    SURFACE, "frosted"))
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("["):
                continue
            self.assertRegex(stripped, r"^[A-Za-z%_][A-Za-z0-9_.]*=", line)


# --------------------------------------------------------------- the command line


class CommandLine(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "iarch" / "cli" / "render_kvantum.py"),
                               *args], capture_output=True, text=True, cwd=str(ROOT))

    def test_print_writes_the_theme_to_stdout(self):
        result = self.run_cli("--print")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("[%General]", result.stdout)
        self.assertIn("[GeneralColors]", result.stdout)
        self.assertIn("reduce_window_opacity=", result.stdout)

    def test_print_honours_the_preset_and_intensity(self):
        crystal = self.run_cli("--print", "--preset", "aurora", "--intensity", "crystal")
        self.assertEqual(0, crystal.returncode, crystal.stderr)
        self.assertEqual(20, self._reduce(crystal.stdout, "reduce_window_opacity"))

    def test_an_unknown_preset_exits_two(self):
        result = self.run_cli("--preset", "no-such-preset", "--print")
        self.assertEqual(2, result.returncode)
        self.assertIn("no-such-preset", result.stderr)

    def test_an_unknown_intensity_exits_two_and_lists_the_real_ones(self):
        result = self.run_cli("--intensity", "ultra", "--print")
        self.assertEqual(2, result.returncode)
        self.assertIn("frosted", result.stderr)

    def test_output_dir_writes_both_files_where_it_was_told(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "Kvantum"
            result = self.run_cli("--output-dir", str(dest))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((dest / "kvantum.kvconfig").is_file())
            self.assertTrue((dest / "iarch" / "iarch.kvconfig").is_file())
            self.assertTrue((dest / "iarch" / "iarch.kvconfig").read_text()
                            .startswith(configstore.header_for(dest / "iarch" / "iarch.kvconfig")))

    def test_check_passes_on_the_shipped_payload(self):
        result = self.run_cli("--check")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("match a fresh render", result.stdout)

    def test_help_lists_every_flag(self):
        result = self.run_cli("--help")
        self.assertEqual(0, result.returncode, result.stderr)
        for flag in ("--preset", "--intensity", "--print", "--write-repo-default",
                     "--check", "--output-dir"):
            self.assertIn(flag, result.stdout)

    @staticmethod
    def _reduce(text: str, key: str) -> int:
        match = re.search(rf"^{key}=(\d+)$", text, re.M)
        return int(match.group(1)) if match else -1


if __name__ == "__main__":
    unittest.main()
