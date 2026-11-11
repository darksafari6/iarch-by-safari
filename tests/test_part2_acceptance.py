# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Part 2 acceptance, proven mechanically.

docs/ROADMAP.md accepts Part 2 on three criteria:

1. every effect has a named switch;
2. the Performance preset measurably lowers work, or PERF-01 stays open;
3. no effect is applied to a surface whose rule could not be verified against
   the compositor release in use.

Each renderer's own test file proves its surface in detail. This file proves the
three *cross-cutting* claims, so a future change that drops a switch, ships a
Performance preset that still animates, or reads a surface with no recorded
provenance fails here rather than silently eroding the acceptance. It needs no
third-party package: the animation render it inspects is pure Python.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_animations_lua  # noqa: E402

DATA = ROOT / "data"
DESIGN = DATA / "design"
UNVERIFIED = ROOT / "docs" / "UNVERIFIED.md"

# The design surfaces extracted from a pinned upstream release. Each renderer
# refuses to write past its surface, so an effect only reaches a toolkit whose
# rules were read out of that release. tokens.json and the legacy
# glass.tokens.json are the design's own source, not an upstream surface, so they
# are not in this list.
UPSTREAM_SURFACES = ("animations.json", "fontconfig.json", "gtk.json", "kvantum.json", "noctalia.json")

# The intensities the tokens define, from most glass to least work.
INTENSITIES = ("crystal", "frosted", "soft", "performance")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Criterion1NamedSwitches(unittest.TestCase):
    """Every effect the glass session applies has a named switch."""

    def setUp(self):
        self.schema = read_json(DATA / "schemas" / "settings.schema.json")
        self.tokens = read_json(DESIGN / "tokens.json")

    def test_the_four_effect_toggles_are_named_booleans(self):
        effects = self.schema["properties"]["effects"]["properties"]
        for name in ("blur", "transparency", "animations", "shadows"):
            self.assertIn(name, effects, f"effect {name!r} has no named switch in settings.effects")
            self.assertEqual(effects[name]["type"], "boolean", f"{name} switch is not a boolean")

    def test_a_coarse_performance_master_switch_is_named(self):
        self.assertIn("performance", self.schema["properties"]["preset"]["enum"],
                      "settings.preset must offer a performance master switch")

    def test_intensity_is_a_named_switch_with_a_performance_step(self):
        enum = self.schema["properties"]["theme"]["properties"]["intensity"]["enum"]
        for name in INTENSITIES:
            self.assertIn(name, enum, f"intensity {name!r} is not a selectable switch")

    def test_the_intensity_switch_names_exactly_what_the_tokens_define(self):
        # A switch can never name an intensity the renderers do not have, nor hide
        # one they do: the settings enum and the tokens are the same set.
        enum = set(self.schema["properties"]["theme"]["properties"]["intensity"]["enum"])
        self.assertEqual(enum, set(self.tokens["intensities"]))

    def test_every_intensity_carries_a_motion_switch(self):
        for name, body in self.tokens["intensities"].items():
            self.assertIn("motion", body, f"intensity {name!r} has no motion block")
            self.assertIn("enabled", body["motion"], f"intensity {name!r} has no motion.enabled switch")


class Criterion2PerformanceLowersWork(unittest.TestCase):
    """The Performance intensity verifiably disables motion; PERF-01 stays open."""

    def setUp(self):
        self.tokens = read_json(DESIGN / "tokens.json")
        self.surface = gen_animations_lua.load_surface()

    def test_performance_turns_motion_off_and_the_others_leave_it_on(self):
        self.assertFalse(self.tokens["intensities"]["performance"]["motion"]["enabled"])
        for name in ("crystal", "soft", "frosted"):
            self.assertTrue(self.tokens["intensities"][name]["motion"]["enabled"],
                            f"{name} is a glass intensity and should still animate")

    def test_the_rendered_performance_set_emits_the_master_off_and_no_leaves(self):
        lua = gen_animations_lua.build(self.tokens, self.surface, "performance")
        self.assertIn("enabled = false", lua, "the master animations switch must be off")
        self.assertEqual(0, lua.count("hl.animation("), "no animation leaf is emitted when motion is off")
        self.assertEqual(0, lua.count("hl.curve("), "no curve is registered when motion is off")

    def test_a_glass_intensity_emits_real_per_frame_work(self):
        # The contrast that makes the Performance reduction measurable by inspection:
        # frosted registers curves and animation leaves; performance registers none.
        lua = gen_animations_lua.build(self.tokens, self.surface, "frosted")
        self.assertGreater(lua.count("hl.animation("), 0, "frosted animates, so it emits leaves")
        self.assertGreater(lua.count("hl.curve("), 0, "frosted animates, so it registers curves")
        self.assertNotIn("enabled = false", lua)

    def test_performance_emits_strictly_less_than_a_glass_intensity(self):
        performance = gen_animations_lua.build(self.tokens, self.surface, "performance")
        frosted = gen_animations_lua.build(self.tokens, self.surface, "frosted")
        self.assertLess(len(performance), len(frosted),
                        "the Performance render is smaller: it drops every leaf and curve")

    def test_the_frame_timing_measurement_is_still_recorded_open(self):
        # The off switch is provable by inspection; the frame-timing, blur-cost and
        # input-latency measurement on real hardware is not, and stays PERF-01.
        self.assertIn("PERF-01", UNVERIFIED.read_text(encoding="utf-8"))


class Criterion3NoUnverifiedSurface(unittest.TestCase):
    """No effect lands on a surface whose rule was not verified against a release."""

    def test_every_upstream_surface_records_its_provenance(self):
        for name in UPSTREAM_SURFACES:
            surface = read_json(DESIGN / name)
            self.assertIn("verified_against", surface, f"{name} does not record the release it was read from")
            self.assertIn("source", surface, f"{name} does not record where the surface came from")
            self.assertIn("_copyright", surface, f"{name} has no copyright header")

    def test_the_live_session_caveats_are_recorded(self):
        # What no sandbox could observe is written down rather than claimed: a live
        # Hyprland/Noctalia run, the shell's own validator, and the icon-theme gap.
        text = UNVERIFIED.read_text(encoding="utf-8")
        for item in ("TP-10", "TP-19", "SES-02", "UI-05"):
            self.assertIn(item, text, f"{item} is an open Part-2 caveat and must stay recorded")


if __name__ == "__main__":
    unittest.main()
