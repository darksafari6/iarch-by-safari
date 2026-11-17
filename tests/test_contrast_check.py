# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The contrast gate measures WCAG correctly, and every preset clears it.

Two things are proven here. First the arithmetic: the ratios are checked against
published reference values, because a gate that computes the wrong number and
passes everything is worse than no gate. Second the data: every preset in
data/design/presets/ passes, and a deliberately broken palette does not -- the
negative control is what stops this file from going green on a checker that
silently evaluates zero pairs.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import contrast_check as cc  # noqa: E402  (repo-root import by design)

PRESET_DIR = ROOT / "data" / "design" / "presets"
PRESET_SCHEMA = ROOT / "data" / "schemas" / "preset.schema.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class WcagArithmetic(unittest.TestCase):
    """Reference values from WCAG 2.1 and the well-known grey boundary cases."""

    def test_black_on_white_is_twenty_one(self):
        self.assertAlmostEqual(cc.contrast_ratio("#ffffff", "#000000"), 21.0, places=2)

    def test_ratio_is_symmetric(self):
        forward = cc.contrast_ratio("#8b95ff", "#141829")
        backward = cc.contrast_ratio("#141829", "#8b95ff")
        self.assertAlmostEqual(forward, backward, places=9)

    def test_same_colour_is_one(self):
        self.assertAlmostEqual(cc.contrast_ratio("#123456", "#123456"), 1.0, places=9)

    def test_the_classic_passing_and_failing_greys(self):
        # #767676 on white is the lightest grey that still reaches 4.5:1; one
        # step darker in the other direction, #777777, is the canonical failure.
        self.assertGreaterEqual(cc.contrast_ratio("#767676", "#ffffff"), 4.5)
        self.assertLess(cc.contrast_ratio("#777777", "#ffffff"), 4.5)

    def test_relative_luminance_of_the_primaries(self):
        self.assertAlmostEqual(cc.relative_luminance((255, 255, 255)), 1.0, places=6)
        self.assertAlmostEqual(cc.relative_luminance((0, 0, 0)), 0.0, places=6)
        # WCAG coefficients: green dominates, blue contributes least.
        self.assertGreater(cc.relative_luminance((0, 255, 0)), cc.relative_luminance((255, 0, 0)))
        self.assertGreater(cc.relative_luminance((255, 0, 0)), cc.relative_luminance((0, 0, 255)))

    def test_low_channels_use_the_linear_segment(self):
        # Below the 0.04045 knee the transfer function is linear, not a power.
        self.assertAlmostEqual(cc.relative_luminance((10, 10, 10)), 0.0030352, places=6)


class HexParsing(unittest.TestCase):
    def test_six_digit(self):
        self.assertEqual(cc.parse_hex("#8b95ff"), (0x8b, 0x95, 0xff))

    def test_three_digit_expands(self):
        self.assertEqual(cc.parse_hex("#abc"), (0xaa, 0xbb, 0xcc))

    def test_eight_digit_drops_alpha(self):
        self.assertEqual(cc.parse_hex("#8b95ff80"), (0x8b, 0x95, 0xff))

    def test_uppercase_and_lowercase_agree(self):
        self.assertEqual(cc.parse_hex("#AABBCC"), cc.parse_hex("#aabbcc"))

    def test_rejects_junk(self):
        for bad in ("8b95ff", "#12345", "#gggggg", "", "#1234567", None, 42):
            with self.subTest(value=bad):
                with self.assertRaises(cc.ContrastError):
                    cc.parse_hex(bad)


class Blending(unittest.TestCase):
    def test_half_way_between_black_and_white(self):
        self.assertEqual(cc.blend("#ffffff", "#000000", 0.5), "#808080")

    def test_zero_alpha_is_the_background(self):
        self.assertEqual(cc.blend("#ff0000", "#00ff00", 0.0), "#00ff00")

    def test_full_alpha_is_the_foreground(self):
        self.assertEqual(cc.blend("#ff0000", "#00ff00", 1.0), "#ff0000")

    def test_a_glass_tint_over_a_dark_surface_loses_contrast(self):
        # The reason blend() exists: text measured against the tint colour alone
        # looks readable, but the composited surface is what is really behind it.
        solid = cc.contrast_ratio("#e6e9f8", "#8b95ff")
        tinted = cc.blend("#8b95ff", "#0b0e1a", 0.34)
        composited = cc.contrast_ratio("#e6e9f8", tinted)
        self.assertGreater(composited, solid)
        self.assertNotEqual(tinted, "#8b95ff")

    def test_rejects_alpha_outside_the_unit_interval(self):
        for alpha in (-0.1, 1.1):
            with self.subTest(alpha=alpha):
                with self.assertRaises(cc.ContrastError):
                    cc.blend("#ffffff", "#000000", alpha)


class EveryPresetPasses(unittest.TestCase):
    def setUp(self):
        self.paths = sorted(PRESET_DIR.glob("*.json"))
        self.assertTrue(self.paths, "no presets found -- the suite would pass vacuously")

    def test_six_presets_ship(self):
        ids = {read_json(p)["id"] for p in self.paths}
        self.assertEqual(
            {"midnight-glass", "frosted-light", "aurora", "crimson-plasma",
             "tokyo-night-glass", "mono-ice"},
            ids,
        )

    def test_every_preset_clears_the_text_and_ui_floors(self):
        for path in self.paths:
            preset = read_json(path)
            with self.subTest(preset=preset["id"]):
                results = cc.evaluate(preset)
                failed = [r for r in results if not r.passed]
                self.assertEqual([], [(r.label, round(r.ratio, 2)) for r in failed])

    def test_every_preset_actually_checks_text_pairs(self):
        # Guards against a palette shape that makes the checker skip its work.
        for path in self.paths:
            preset = read_json(path)
            with self.subTest(preset=preset["id"]):
                results = cc.evaluate(preset)
                text_pairs = [r for r in results if r.kind == "text"]
                self.assertGreaterEqual(len(text_pairs), 20)
                for result in text_pairs:
                    self.assertGreaterEqual(result.ratio, cc.MIN_TEXT_RATIO, result.label)

    def test_text_pairs_reach_four_five_with_margin(self):
        # A preset that sits 0.01 above the floor breaks the moment anyone nudges
        # a colour, so require a little headroom on every text pair.
        for path in self.paths:
            preset = read_json(path)
            with self.subTest(preset=preset["id"]):
                for result in cc.evaluate(preset):
                    if result.kind == "text":
                        self.assertGreaterEqual(result.ratio, 4.6, result.label)

    def test_ui_pairs_reach_three_with_margin(self):
        for path in self.paths:
            preset = read_json(path)
            with self.subTest(preset=preset["id"]):
                for result in cc.evaluate(preset):
                    if result.kind == "ui":
                        self.assertGreaterEqual(result.ratio, 3.4, result.label)

    def test_informational_pairs_are_reported_but_never_fail(self):
        for path in self.paths:
            preset = read_json(path)
            with self.subTest(preset=preset["id"]):
                info = [r for r in cc.evaluate(preset) if r.kind == "info"]
                self.assertTrue(info, "expected the hairline and ANSI black pair")
                for result in info:
                    self.assertTrue(result.passed)

    def test_every_preset_validates_against_its_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema not installed; CI validates with the library")
        schema = read_json(PRESET_SCHEMA)
        jsonschema.Draft7Validator.check_schema(schema)
        for path in self.paths:
            with self.subTest(preset=path.name):
                jsonschema.validate(read_json(path), schema)


class TheGateActuallyBites(unittest.TestCase):
    """Negative controls: each one breaks a preset the way a real mistake would."""

    def preset(self):
        return read_json(PRESET_DIR / "midnight-glass.json")

    def failing(self, preset):
        return [r for r in cc.evaluate(preset) if not r.passed]

    def test_low_contrast_body_text_is_caught(self):
        preset = self.preset()
        preset["palette"]["on_surface"] = "#2a2f45"
        failed = self.failing(preset)
        self.assertTrue(failed)
        self.assertIn("body text on surface", [r.label for r in failed])

    def test_a_too_bright_accent_on_a_light_surface_is_caught(self):
        preset = read_json(PRESET_DIR / "frosted-light.json")
        preset["palette"]["accent"]["primary"] = "#c7d2fe"
        failed = self.failing(preset)
        self.assertTrue(failed, "a pale accent on a light surface must not pass as text")

    def test_white_label_on_a_bright_accent_fill_is_caught(self):
        preset = self.preset()
        preset["palette"]["accent"]["warning"] = "#fde68a"
        preset["palette"]["on_accent"]["warning"] = "#ffffff"
        failed = self.failing(preset)
        self.assertTrue(failed)
        self.assertIn("label on accent.warning fill", [r.label for r in failed])

    def test_a_washed_out_focus_ring_is_caught(self):
        preset = self.preset()
        preset["palette"]["outline"] = "#232842"
        failed = self.failing(preset)
        self.assertTrue(failed, "a ring below 3:1 against the surface must fail")

    def test_raising_the_floor_with_min_fails_the_shipped_presets(self):
        # --min 7.0 is stricter than the design intends, so it must produce
        # failures: proof the floor is honoured rather than ignored.
        results = cc.evaluate(self.preset(), minimum=7.0)
        self.assertTrue([r for r in results if not r.passed])

    def test_a_missing_colour_role_raises_instead_of_passing(self):
        preset = self.preset()
        del preset["palette"]["on_surface_variant"]
        with self.assertRaises(cc.ContrastError):
            cc.evaluate(preset)

    def test_a_missing_palette_raises(self):
        with self.assertRaises(cc.ContrastError):
            cc.evaluate({"id": "broken"})

    def test_a_non_hex_colour_raises(self):
        preset = self.preset()
        preset["palette"]["surface"] = "rgb(20,24,41)"
        with self.assertRaises(cc.ContrastError):
            cc.evaluate(preset)


class CommandLine(unittest.TestCase):
    """The CLI contract: 0 when every preset passes, 1 on a contrast failure,
    2 when the input itself cannot be read."""

    def run_cli(self, argv):
        """Run main() with both streams captured, returning (code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cc.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_passing_directory_exits_zero(self):
        code, _, _ = self.run_cli(["--quiet", "--directory", str(PRESET_DIR)])
        self.assertEqual(0, code)

    def test_single_preset_exits_zero(self):
        code, _, _ = self.run_cli(["--quiet", "--preset", "aurora"])
        self.assertEqual(0, code)

    def test_a_stricter_floor_exits_one_and_says_why(self):
        code, _, err = self.run_cli(["--quiet", "--min", "12.0"])
        self.assertEqual(1, code)
        self.assertIn("below the required ratio", err)

    def test_an_unknown_preset_exits_two(self):
        code, _, err = self.run_cli(["--preset", "no-such-preset"])
        self.assertEqual(2, code)
        self.assertIn("no-such-preset", err)

    def test_a_missing_directory_exits_two(self):
        code, _, _ = self.run_cli(["--directory", str(PRESET_DIR / "nope")])
        self.assertEqual(2, code)

    def test_a_report_names_the_offending_pair(self):
        code, out, _ = self.run_cli(["--min", "20.0"])
        self.assertEqual(1, code)
        self.assertIn("FAIL", out)
        self.assertIn("body text on background", out)

    def test_json_output_reports_every_preset(self):
        code, out, _ = self.run_cli(["--json"])
        self.assertEqual(0, code)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(6, len(payload["presets"]))
        for entry in payload["presets"].values():
            self.assertEqual(0, len(entry["failures"]))
            self.assertGreater(entry["gated"], 0)
            self.assertGreater(entry["lowest_gated"], 3.0)

    def test_discover_finds_all_presets_and_filters_by_id(self):
        self.assertEqual(6, len(cc.discover(PRESET_DIR)))
        self.assertEqual(1, len(cc.discover(PRESET_DIR, "mono-ice")))
        self.assertEqual(1, len(cc.discover(PRESET_DIR, "mono-ice.json")))
        with self.assertRaises(cc.ContrastError):
            cc.discover(PRESET_DIR, "absent")


if __name__ == "__main__":
    unittest.main()
