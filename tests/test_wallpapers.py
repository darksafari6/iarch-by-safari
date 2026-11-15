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



class TheDesktopSet(unittest.TestCase):
    """Six wallpapers that belong to no preset: what they promise on paper.

    A preset's wallpaper is part of that preset's identity; these are the
    pictures a person picks from the shell's wallpaper folder, and
    ``install.sh`` copies them into the directory the picker reads. They are
    described beside the code that renders them so there is one art pipeline in
    this repository, not two.
    """

    def test_there_are_six_and_their_ids_are_unique(self):
        ids = [str(entry["id"]) for entry in gw.DESKTOP_WALLPAPERS]
        self.assertEqual(6, len(ids), f"the set is {ids}")
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_entry_is_a_gradient_the_renderer_accepts(self):
        for entry in gw.DESKTOP_WALLPAPERS:
            with self.subTest(wallpaper=entry["id"]):
                self.assertIn(entry["style"], gw.STYLES)
                stops = entry["stops"]
                self.assertTrue(2 <= len(stops) <= 6, stops)
                for stop in stops:
                    gw.parse_hex(str(stop), f"{entry['id']}.stops")
                self.assertIsInstance(entry["seed"], int)
                self.assertGreaterEqual(float(entry["grain"]), 0.0)
                self.assertTrue(0.0 <= float(entry["vignette"]) <= 1.0)

    def test_the_seeds_are_distinct_so_the_frames_are_not_the_same_picture(self):
        seeds = [entry["seed"] for entry in gw.DESKTOP_WALLPAPERS]
        self.assertEqual(len(seeds), len(set(seeds)), seeds)

    def test_every_style_in_the_renderer_is_used_by_at_least_one_wallpaper(self):
        used = {str(entry["style"]) for entry in gw.DESKTOP_WALLPAPERS}
        self.assertEqual(set(gw.STYLES), used,
                         "a style exists that the dark set never exercises, so a "
                         "regression in it would ship untested")

    def test_every_entry_credits_the_generator_and_no_third_party_art(self):
        for entry in gw.DESKTOP_WALLPAPERS:
            with self.subTest(wallpaper=entry["id"]):
                self.assertIn("gen_wallpapers.py", str(entry["credit"]))
                self.assertIn("No third-party artwork", str(entry["credit"]))

    def test_the_path_is_the_id_and_the_directory_is_the_desktop_one(self):
        for entry in gw.DESKTOP_WALLPAPERS:
            path = gw.desktop_path(entry)
            self.assertEqual(gw.DESKTOP_DIR, path.parent)
            self.assertEqual(f"{entry['id']}.webp", path.name)

    def test_the_installer_deploys_the_desktop_directory(self):
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("assets/wallpapers/desktop/*.webp", installer,
                      "the installer stopped copying the desktop set, so the "
                      "picker would offer nothing this repository shipped")

    def test_the_document_lists_every_one_of_them(self):
        document = (ROOT / "docs" / "WALLPAPERS.md").read_text(encoding="utf-8")
        for entry in gw.DESKTOP_WALLPAPERS:
            with self.subTest(wallpaper=entry["id"]):
                self.assertIn(str(entry["id"]), document)
        self.assertIn("MAX_MEAN_LUMINANCE", document,
                      "the darkness ceiling is a number, and the document that "
                      "explains the art has to say so")


@unittest.skipUnless(have_pillow(), "Pillow is not installed; rendering is skipped")
class RenderedDesktopArt(unittest.TestCase):
    """The committed files, measured rather than admired."""

    def test_the_shipped_set_is_4k_webp_inside_the_budget_and_dark(self):
        from PIL import Image

        for entry in gw.DESKTOP_WALLPAPERS:
            path = gw.desktop_path(entry)
            with self.subTest(wallpaper=entry["id"]):
                self.assertTrue(path.is_file(), f"{path} is not committed")
                with Image.open(path) as image:
                    self.assertEqual(gw.TARGET, image.size)
                    self.assertEqual("WEBP", image.format)
                self.assertLessEqual(path.stat().st_size, BUDGET)
                self.assertLessEqual(gw.mean_luminance(path), gw.MAX_MEAN_LUMINANCE)

    def test_a_render_is_byte_identical_to_a_second_render(self):
        entry = gw.DESKTOP_WALLPAPERS[0]
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.webp"
            second = Path(tmp) / "second.webp"
            gw.render_preset(gw.as_preset(entry), first, BUDGET, gw.DEFAULT_QUALITY)
            gw.render_preset(gw.as_preset(entry), second, BUDGET, gw.DEFAULT_QUALITY)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_changing_the_seed_changes_the_picture(self):
        entry = dict(gw.DESKTOP_WALLPAPERS[0])
        other = dict(entry, seed=int(entry["seed"]) + 1)
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.webp"
            second = Path(tmp) / "second.webp"
            gw.render_preset(gw.as_preset(entry), first, BUDGET, gw.DEFAULT_QUALITY)
            gw.render_preset(gw.as_preset(other), second, BUDGET, gw.DEFAULT_QUALITY)
            self.assertNotEqual(first.read_bytes(), second.read_bytes())

    def test_check_refuses_a_desktop_wallpaper_that_is_not_dark(self):
        """The ceiling has to be load-bearing, not decorative."""
        ceiling = gw.MAX_MEAN_LUMINANCE
        gw.MAX_MEAN_LUMINANCE = 0.001
        try:
            problems = gw.check(BUDGET)
        finally:
            gw.MAX_MEAN_LUMINANCE = ceiling
        self.assertTrue(any("mean luminance" in problem for problem in problems),
                        "a bright frame passed --check, so the darkness promise is "
                        "not actually enforced")

    def test_check_refuses_a_file_the_desktop_set_does_not_describe(self):
        stray = gw.DESKTOP_DIR / "not-described-anywhere.webp"
        stray.write_bytes(b"")
        try:
            problems = gw.check(BUDGET)
        finally:
            stray.unlink()
        self.assertTrue(any(problem.startswith("orphan:") and
                            "not-described-anywhere" in problem
                            for problem in problems), problems)

    def test_check_is_clean_for_what_ships(self):
        self.assertEqual([], gw.check(BUDGET))


if __name__ == "__main__":
    unittest.main()
