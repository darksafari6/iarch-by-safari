# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The wallpaper generator renders what the presets promise, and nothing stale.

The art ships in the repository, so these tests are about the contract rather
than about pixels: every preset resolves to a file that exists, generated art is
4K WebP inside the 600 KB budget, bundled art is left where it always was, and a
render is byte-identical to a second render of the same preset -- which is what
lets anyone confirm the committed WebP came from the committed JSON.

Rendering needs Pillow; without it the suite says so and skips instead of
failing a checkout that has no imaging library.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_wallpapers as gw  # noqa: E402  (repo-root import by design)

BUDGET = 600 * 1024


def have_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


class GradientMaths(unittest.TestCase):
    """The pieces that are pure maths need no imaging library at all."""

    def test_ramp_ends_are_the_first_and_last_stops(self):
        stops = [(0, 0, 0), (128, 128, 128), (255, 255, 255)]
        self.assertEqual((0, 0, 0), gw.ramp(stops, 0.0))
        self.assertEqual((255, 255, 255), gw.ramp(stops, 1.0))

    def test_ramp_midpoint_is_the_middle_stop(self):
        stops = [(0, 0, 0), (120, 60, 30), (255, 255, 255)]
        self.assertEqual((120, 60, 30), gw.ramp(stops, 0.5))

    def test_ramp_clamps_outside_the_unit_interval(self):
        stops = [(10, 20, 30), (40, 50, 60)]
        self.assertEqual((10, 20, 30), gw.ramp(stops, -3.0))
        self.assertEqual((40, 50, 60), gw.ramp(stops, 7.0))

    def test_ramp_interpolates_linearly_between_stops(self):
        stops = [(0, 0, 0), (100, 100, 100)]
        self.assertEqual((25, 25, 25), gw.ramp(stops, 0.25))

    def test_a_single_stop_is_a_solid_field(self):
        self.assertEqual((9, 9, 9), gw.ramp([(9, 9, 9)], 0.4))

    def test_an_empty_ramp_is_refused(self):
        with self.assertRaises(gw.WallpaperError):
            gw.ramp([], 0.5)

    def test_hex_parsing_accepts_six_digits_only(self):
        self.assertEqual((139, 149, 255), gw.parse_hex("#8b95ff", "test"))
        for bad in ("8b95ff", "#8b95", "#8b95ff00", "#gggggg", "rgba(1,2,3,4)"):
            with self.subTest(value=bad):
                with self.assertRaises(gw.WallpaperError):
                    gw.parse_hex(bad, "test")

    def test_smoothstep_is_monotone_and_bounded(self):
        previous = 0.0
        for step in range(101):
            value = gw.smoothstep(step / 100.0)
            self.assertGreaterEqual(value, previous - 1e-9)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
            previous = value

    def test_value_noise_stays_in_the_unit_interval(self):
        import random
        layer = gw.value_noise(24, 16, random.Random(7), 4, 3)
        self.assertEqual(24 * 16, len(layer))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in layer))

    def test_fractal_noise_is_not_constant(self):
        import random
        layer = gw.fractal_noise(32, 20, random.Random(11), octaves=3)
        self.assertGreater(max(layer) - min(layer), 0.2,
                           "a constant field would render as a flat wash")


@unittest.skipUnless(have_pillow(), "Pillow is not installed; rendering is skipped")
class RenderedArt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.presets = gw.load_presets()

    def test_every_generated_preset_renders_inside_the_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            for preset in self.presets:
                if preset["wallpaper"]["kind"] != "generated":
                    continue
                destination = Path(tmp) / f"{preset['id']}.webp"
                with self.subTest(preset=preset["id"]):
                    result = gw.render_preset(preset, destination, BUDGET, 86)
                    self.assertLessEqual(result["size"], BUDGET)
                    self.assertEqual(gw.TARGET, result["dimensions"])

    def test_a_render_is_byte_identical_to_a_second_render(self):
        preset = gw.load_presets("midnight-glass")[0]
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.webp"
            second = Path(tmp) / "second.webp"
            gw.render_preset(preset, first, BUDGET, 86)
            gw.render_preset(preset, second, BUDGET, 86)
            self.assertEqual(first.read_bytes(), second.read_bytes(),
                             "the same preset must render the same file, or the "
                             "committed art cannot be traced to its JSON")

    def test_different_seeds_render_different_files(self):
        preset = json.loads(json.dumps(gw.load_presets("mono-ice")[0]))
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.webp"
            gw.render_preset(preset, first, BUDGET, 86)
            preset["wallpaper"]["generate"]["seed"] += 1
            second = Path(tmp) / "second.webp"
            gw.render_preset(preset, second, BUDGET, 86)
            self.assertNotEqual(first.read_bytes(), second.read_bytes())

    def test_an_unknown_style_is_refused(self):
        preset = json.loads(json.dumps(gw.load_presets("aurora")[0]))
        preset["wallpaper"]["generate"]["style"] = "confetti"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gw.WallpaperError):
                gw.render_preset(preset, Path(tmp) / "x.webp", BUDGET, 86)

    def test_a_single_stop_is_refused(self):
        preset = json.loads(json.dumps(gw.load_presets("aurora")[0]))
        preset["wallpaper"]["generate"]["stops"] = ["#123456"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gw.WallpaperError):
                gw.render_preset(preset, Path(tmp) / "x.webp", BUDGET, 86)

    def test_seven_stops_are_refused(self):
        preset = json.loads(json.dumps(gw.load_presets("aurora")[0]))
        preset["wallpaper"]["generate"]["stops"] = ["#111111"] * 7
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gw.WallpaperError):
                gw.render_preset(preset, Path(tmp) / "x.webp", BUDGET, 86)

    def test_a_non_hex_stop_is_refused(self):
        preset = json.loads(json.dumps(gw.load_presets("aurora")[0]))
        preset["wallpaper"]["generate"]["stops"] = ["#111111", "rgb(1,2,3)"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(gw.WallpaperError):
                gw.render_preset(preset, Path(tmp) / "x.webp", BUDGET, 86)


@unittest.skipUnless(have_pillow(), "Pillow is not installed; checking is skipped")
class ShippedArt(unittest.TestCase):
    """What is in the repository right now, not what a fresh render produces."""

    def test_check_passes_on_the_checkout(self):
        self.assertEqual([], gw.check(BUDGET))

    def test_generated_art_is_four_k_webp_inside_the_budget(self):
        from PIL import Image

        for path in sorted((ROOT / "assets" / "wallpapers" / "generated").glob("*.webp")):
            with self.subTest(path=path.name):
                self.assertLessEqual(path.stat().st_size, BUDGET)
                with Image.open(path) as image:
                    self.assertEqual(gw.TARGET, image.size)
                    self.assertEqual("WEBP", image.format)

    def test_bundled_art_is_untouched_by_the_generator(self):
        bundled = {ROOT / p["wallpaper"]["path"] for p in gw.load_presets()
                   if p["wallpaper"]["kind"] == "bundled"}
        generated = ROOT / "assets" / "wallpapers" / "generated"
        self.assertTrue(bundled, "expected two presets to reuse shipped art")
        for path in bundled:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertNotIn(generated, path.parents,
                                 "bundled art must not live in the generated directory")

    def test_an_orphan_file_in_the_output_directory_is_reported(self):
        original = gw.GENERATED_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                stray = Path(tmp) / "forgotten.webp"
                stray.write_bytes(b"\x00")
                gw.GENERATED_DIR = Path(tmp)
                problems = gw.check(BUDGET)
            self.assertTrue(any("orphan" in problem for problem in problems), problems)
        finally:
            gw.GENERATED_DIR = original

    def test_a_missing_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            preset = json.loads(json.dumps(gw.load_presets("aurora")[0]))
            preset["wallpaper"]["path"] = "assets/wallpapers/generated/nope.webp"
            original = gw.PRESET_DIR
            try:
                shadow = Path(tmp)
                (shadow / "aurora.json").write_text(json.dumps(preset), encoding="utf-8")
                gw.PRESET_DIR = shadow
                problems = gw.check(BUDGET)
            finally:
                gw.PRESET_DIR = original
            self.assertTrue(any("does not exist" in problem for problem in problems), problems)

    def test_the_cli_reports_zero_on_a_good_checkout(self):
        self.assertEqual(0, gw.main(["--check"]))

    def test_the_cli_refuses_an_unknown_preset(self):
        self.assertEqual(2, gw.main(["--preset", "no-such-preset"]))

    def test_dry_run_writes_nothing(self):
        before = {p.name: p.stat().st_size
                  for p in (ROOT / "assets" / "wallpapers" / "generated").glob("*.webp")}
        self.assertEqual(0, gw.main(["--dry-run"]))
        after = {p.name: p.stat().st_size
                 for p in (ROOT / "assets" / "wallpapers" / "generated").glob("*.webp")}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
