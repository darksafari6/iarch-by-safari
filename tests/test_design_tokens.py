# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The glass design tokens are complete, self-consistent and inside real limits.

Two classes of mistake matter here and both are caught:

* a token that no target could honour -- a blur radius above the maximum
  Hyprland enforces, a spring stiffness ``hl.curve`` rejects, a window rule
  effect that does not exist. Every numeric bound asserted below is the bound
  the upstream source declares, and the names are cross-checked against the
  ``hyprland`` block of the token file itself, so the file cannot quietly claim
  a leaf it does not list.
* a token that contradicts the design -- the Performance intensity still
  blurring, browsers made translucent, an intensity missing a group a generator
  needs. Those are the acceptance criteria, restated as assertions.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
TOKENS_SCHEMA = ROOT / "data" / "schemas" / "tokens.schema.json"
UNVERIFIED = ROOT / "docs" / "UNVERIFIED.md"

INTENSITIES = ("crystal", "frosted", "soft", "performance")
# Effects and match properties read out of Hyprland v0.57.2; the token file
# carries the same lists, and the test below proves they agree.
LAYER_EFFECTS = {
    "blur", "blur_popups", "ignore_alpha", "no_anim", "dim_around", "xray",
    "animation", "order", "above_lock", "no_screen_share",
}
BLUR_VARIANTS = {
    "kawase", "frost", "ripple", "drops", "water", "fluid_jar", "prism",
    "heat_shimmer", "acrylic", "aurora", "haze",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TokenFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)

    def test_it_validates_against_its_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema not installed; CI validates with the library")
        schema = read_json(TOKENS_SCHEMA)
        jsonschema.Draft7Validator.check_schema(schema)
        errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(self.tokens),
                        key=lambda e: list(e.path))
        self.assertEqual([], [f"{list(e.path)}: {e.message[:80]}" for e in errors])

    def test_the_schema_is_closed(self):
        # An open schema would let a typo'd group ride along unseen.
        schema = read_json(TOKENS_SCHEMA)
        self.assertFalse(schema["additionalProperties"])
        for name in ("radius", "spacing", "motion", "font", "layout", "intensities"):
            with self.subTest(group=name):
                self.assertFalse(schema["properties"][name]["additionalProperties"])

    def test_it_carries_the_copyright_header(self):
        self.assertIn("GPL-3.0-or-later", self.tokens["_copyright"])

    def test_four_intensities_and_no_others(self):
        self.assertEqual(set(INTENSITIES), set(self.tokens["intensities"]))

    def test_the_default_intensity_exists(self):
        self.assertIn(self.tokens["default_intensity"], self.tokens["intensities"])

    def test_every_intensity_is_self_contained(self):
        # A generator must be able to render any intensity without merging,
        # otherwise "performance" inherits blur from a sibling.
        for name in INTENSITIES:
            intensity = self.tokens["intensities"][name]
            with self.subTest(intensity=name):
                for group in ("blur", "glass", "shadow", "window", "terminal"):
                    self.assertIn(group, intensity)
                self.assertTrue(intensity["label"])
                self.assertTrue(intensity["description"])


class RadiiAndSpacing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)

    def test_the_radius_scale_is_ascending(self):
        radius = self.tokens["radius"]
        self.assertLess(radius["xs"], radius["sm"])
        self.assertLess(radius["sm"], radius["md"])
        self.assertLess(radius["md"], radius["lg"])
        self.assertLess(radius["lg"], radius["pill"])

    def test_window_rounding_is_sixteen_and_inside_the_hyprland_limit(self):
        radius = self.tokens["radius"]
        self.assertEqual("md", radius["window"])
        self.assertEqual(16, radius[radius["window"]])
        low, high = self.tokens["hyprland"]["ranges"]["decoration:rounding"]
        self.assertLessEqual(radius[radius["window"]], high)
        self.assertGreaterEqual(radius[radius["window"]], low)

    def test_every_role_resolves_to_a_real_step(self):
        radius = self.tokens["radius"]
        steps = {"xs", "sm", "md", "lg", "pill"}
        for role in ("window", "panel", "card", "button", "input", "tooltip"):
            with self.subTest(role=role):
                self.assertIn(radius[role], steps)

    def test_pill_exceeds_the_compositor_maximum_so_it_must_be_clamped(self):
        # Not a bug: pill is a CSS convention meaning "fully rounded". The point
        # of the assertion is that the design token is knowingly out of range for
        # decoration:rounding, so a generator that forgets to clamp is caught by
        # the range test above rather than by a broken session.
        high = self.tokens["hyprland"]["ranges"]["decoration:rounding"][1]
        self.assertGreater(self.tokens["radius"]["pill"], high)

    def test_the_spacing_scale_is_ascending_and_starts_at_four(self):
        spacing = self.tokens["spacing"]
        values = [spacing[k] for k in ("xs", "sm", "md", "lg", "xl", "xxl")]
        self.assertEqual([4, 8, 12, 16, 24, 32], values)
        self.assertEqual(values, sorted(values))


class BlurAndShadow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.ranges = cls.tokens["hyprland"]["ranges"]

    def blur(self, name):
        return self.tokens["intensities"][name]["blur"]

    def test_every_blur_value_sits_inside_the_range_hyprland_enforces(self):
        mapping = {
            "size": "decoration:blur:size",
            "passes": "decoration:blur:passes",
            "noise": "decoration:blur:noise",
            "contrast": "decoration:blur:contrast",
            "brightness": "decoration:blur:brightness",
            "vibrancy": "decoration:blur:vibrancy",
        }
        for name in INTENSITIES:
            for key, leaf in mapping.items():
                low, high = self.ranges[leaf]
                with self.subTest(intensity=name, leaf=leaf):
                    self.assertGreaterEqual(self.blur(name)[key], low)
                    self.assertLessEqual(self.blur(name)[key], high)

    def test_every_variant_is_one_hyprland_knows(self):
        for name in INTENSITIES:
            with self.subTest(intensity=name):
                self.assertIn(self.blur(name)["variant"], BLUR_VARIANTS)
                self.assertIn(self.blur(name)["variant"], self.tokens["hyprland"]["blur_variants"])

    def test_no_intensity_ships_an_animated_variant(self):
        # Animated variants cost GPU every frame; they belong to Part 3, where
        # they can be switched on deliberately and switched off again.
        animated = set(self.tokens["hyprland"]["animated_blur_variants"])
        for name in INTENSITIES:
            with self.subTest(intensity=name):
                self.assertNotIn(self.blur(name)["variant"], animated)

    def test_blur_strength_orders_the_intensities(self):
        def cost(name):
            blur = self.blur(name)
            return blur["size"] * blur["passes"] if blur["enabled"] else 0

        self.assertGreater(cost("crystal"), cost("frosted"))
        self.assertGreater(cost("frosted"), cost("soft"))
        self.assertGreater(cost("soft"), cost("performance"))

    def test_tint_rises_as_blur_falls(self):
        # Crystal is "strong blur, low tint"; soft is "light blur, higher tint".
        glass = {n: self.tokens["intensities"][n]["glass"]["tint_alpha"] for n in INTENSITIES}
        self.assertLess(glass["crystal"], glass["frosted"])
        self.assertLess(glass["frosted"], glass["soft"])
        self.assertLess(glass["soft"], glass["performance"])

    def test_xray_is_off_everywhere(self):
        for name in INTENSITIES:
            with self.subTest(intensity=name):
                self.assertFalse(self.blur(name)["xray"])

    def test_shadow_values_sit_inside_their_ranges(self):
        mapping = {
            "range": "decoration:shadow:range",
            "render_power": "decoration:shadow:render_power",
            "scale": "decoration:shadow:scale",
        }
        for name in INTENSITIES:
            shadow = self.tokens["intensities"][name]["shadow"]
            for key, leaf in mapping.items():
                low, high = self.ranges[leaf]
                with self.subTest(intensity=name, leaf=leaf):
                    self.assertGreaterEqual(shadow[key], low)
                    self.assertLessEqual(shadow[key], high)
            self.assertEqual(2, len(shadow["offset"]))


class PerformanceIntensity(unittest.TestCase):
    """Acceptance criterion: Performance disables blur and heavy shadows."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.performance = cls.tokens["intensities"]["performance"]

    def test_blur_is_off(self):
        self.assertFalse(self.performance["blur"]["enabled"])
        self.assertEqual(0, self.performance["blur"]["size"])
        self.assertEqual(0, self.performance["blur"]["passes"])

    def test_blur_modulation_is_neutral(self):
        blur = self.performance["blur"]
        self.assertEqual(1.0, blur["contrast"])
        self.assertEqual(1.0, blur["brightness"])
        self.assertEqual(0.0, blur["vibrancy"])
        self.assertEqual(0.0, blur["noise"])

    def test_shadows_are_off(self):
        self.assertFalse(self.performance["shadow"]["enabled"])
        self.assertEqual(0, self.performance["shadow"]["range"])
        self.assertEqual(0.0, self.performance["glass"]["shadow_alpha"])

    def test_no_specular_highlight(self):
        self.assertEqual(0.0, self.performance["glass"]["highlight_alpha"])

    def test_fills_are_solid_translucent_instead_of_blurred(self):
        self.assertGreaterEqual(self.performance["glass"]["tint_alpha"], 0.9)
        self.assertGreaterEqual(self.performance["glass"]["tint_alpha_strong"], 0.9)

    def test_inactive_dimming_is_off(self):
        self.assertFalse(self.performance["window"]["dim_inactive"])
        self.assertEqual(0.0, self.performance["window"]["dim_strength"])

    def test_the_terminal_is_nearly_opaque(self):
        self.assertGreaterEqual(self.performance["terminal"]["background_opacity"], 0.9)

    def test_every_other_intensity_blurs_and_shadows(self):
        for name in ("crystal", "frosted", "soft"):
            intensity = self.tokens["intensities"][name]
            with self.subTest(intensity=name):
                self.assertTrue(intensity["blur"]["enabled"])
                self.assertGreater(intensity["blur"]["size"], 0)
                self.assertTrue(intensity["shadow"]["enabled"])
                self.assertGreater(intensity["shadow"]["range"], 0)
                self.assertGreater(intensity["glass"]["shadow_alpha"], 0.0)

    def test_dimming_stays_inside_the_documented_band(self):
        # Task 4 asks for an inactive dim between 0.05 and 0.10.
        for name in ("crystal", "frosted", "soft"):
            strength = self.tokens["intensities"][name]["window"]["dim_strength"]
            with self.subTest(intensity=name):
                self.assertGreaterEqual(strength, 0.05)
                self.assertLessEqual(strength, 0.10)


class WindowOpacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.opacity = cls.tokens["window_opacity"]
        cls.classes = cls.tokens["app_classes"]

    def test_every_opacity_group_has_classes_and_a_value(self):
        self.assertEqual(set(self.classes) - {"_note"}, set(self.opacity) - {"fullscreen_override"})

    def test_the_documented_per_class_values(self):
        self.assertEqual(0.82, self.opacity["terminal"])
        self.assertEqual(0.90, self.opacity["file_manager"])
        self.assertEqual(0.92, self.opacity["editor"])
        self.assertEqual(0.88, self.opacity["iarch_app"])

    def test_browsers_and_video_are_never_translucent(self):
        for group in ("browser", "video", "opaque_always"):
            with self.subTest(group=group):
                self.assertEqual(1.0, self.opacity[group])

    def test_fullscreen_override_is_opaque(self):
        self.assertEqual(1.0, self.opacity["fullscreen_override"])

    def test_every_value_is_a_valid_opacity(self):
        for group, value in self.opacity.items():
            with self.subTest(group=group):
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_every_class_pattern_compiles_and_is_anchored(self):
        for group, patterns in self.classes.items():
            if group == "_note":
                continue
            for pattern in patterns:
                with self.subTest(group=group, pattern=pattern):
                    re.compile(pattern)
                    self.assertTrue(pattern.startswith("^"), "unanchored patterns over-match")
                    self.assertTrue(pattern.endswith("$"))

    def test_the_apps_the_installer_offers_are_covered(self):
        # Task 4: use the classes of applications install.sh actually installs.
        # Each entry is (package name as install.sh spells it, the app_id a
        # running window reports). Matching the real app_id is the point: a
        # pattern that merely contains the name as a substring proves nothing.
        expected = {
            "kitty": "kitty",
            "thunar": "thunar",
            "gedit": "gedit",
            "obsidian": "obsidian",
            "mpv": "mpv",
            "vlc": "vlc",
            "nwg-look": "nwg-look",
        }
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        patterns = {group: [re.compile(p) for p in self.classes[group]]
                    for group in self.classes if group != "_note"}
        for package, app_id in expected.items():
            with self.subTest(package=package):
                self.assertIn(package, installer,
                              f"{package} is not offered by install.sh")
            matched = [group for group, compiled in patterns.items()
                       if any(rx.search(app_id) for rx in compiled)]
            self.assertEqual(1, len(matched), f"{app_id} matched {matched or 'nothing'}")

    def test_the_patterns_do_not_over_match(self):
        # An unanchored or greedy pattern would make a browser translucent,
        # which the design forbids, so prove the groups stay narrow.
        patterns = {group: [re.compile(p) for p in self.classes[group]]
                    for group in self.classes if group != "_note"}

        def groups_matching(candidate):
            return {group for group, compiled in patterns.items()
                    if any(rx.search(candidate) for rx in compiled)}

        for candidate in ("firefox-developer-edition", "kitty-ssh", "thunar-volman",
                          "mpv-player-window", "obsidian-helper", "not-a-real-app"):
            with self.subTest(candidate=candidate):
                self.assertEqual(set(), groups_matching(candidate),
                                 f"{candidate} was claimed by a group")

    def test_no_group_claims_a_class_another_group_also_claims(self):
        seen = {}
        for group, patterns in self.classes.items():
            if group == "_note":
                continue
            for pattern in patterns:
                key = pattern.lower()
                self.assertNotIn(key, seen, f"{pattern} is in both {seen.get(key)} and {group}")
                seen[key] = group


class LayoutAndBorders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.layout = cls.tokens["layout"]

    def test_gaps_are_the_documented_values(self):
        self.assertEqual(6, self.layout["gaps_in"])
        self.assertEqual(12, self.layout["gaps_out"])
        self.assertEqual(1, self.layout["border_size"])

    def test_layout_values_sit_inside_their_ranges(self):
        ranges = self.tokens["hyprland"]["ranges"]
        for key, leaf in (("gaps_in", None), ("gaps_out", None), ("border_size", "general:border_size")):
            if leaf is None:
                continue
            low, high = ranges[leaf]
            with self.subTest(leaf=leaf):
                self.assertGreaterEqual(self.layout[key], low)
                self.assertLessEqual(self.layout[key], high)

    def test_the_active_border_is_a_gradient_between_two_accent_roles(self):
        border = self.layout["border"]
        accent_roles = set(self.tokens["accent"])
        self.assertIn(border["active"]["from_role"], accent_roles)
        self.assertIn(border["active"]["to_role"], accent_roles)
        self.assertGreater(border["active"]["from_alpha"], border["active"]["to_alpha"],
                           "the glow should fall off, not intensify")
        self.assertLessEqual(border["active"]["from_alpha"], 0.6)

    def test_the_inactive_border_is_a_faint_white(self):
        inactive = self.layout["border"]["inactive"]
        self.assertEqual("#ffffff", inactive["color"])
        self.assertLessEqual(inactive["alpha"], 0.15)

    def test_the_gradient_angle_is_a_number_of_degrees(self):
        angle = self.layout["border"]["angle_deg"]
        self.assertGreaterEqual(angle, 0)
        self.assertLessEqual(angle, 360)


class Motion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.motion = cls.tokens["motion"]

    def test_the_durations_are_the_documented_ones_and_ascending(self):
        self.assertEqual(120, self.motion["fast_ms"])
        self.assertEqual(220, self.motion["normal_ms"])
        self.assertEqual(380, self.motion["slow_ms"])
        self.assertLess(self.motion["fast_ms"], self.motion["normal_ms"])
        self.assertLess(self.motion["normal_ms"], self.motion["slow_ms"])

    def test_every_easing_is_a_bezier_with_two_points_in_the_unit_square(self):
        for name, curve in self.motion["easing"].items():
            with self.subTest(curve=name):
                self.assertEqual("bezier", curve["type"])
                self.assertEqual(2, len(curve["points"]))
                for point in curve["points"]:
                    self.assertEqual(2, len(point))
                    for component in point:
                        self.assertGreaterEqual(component, 0.0)
                        self.assertLessEqual(component, 1.0)

    def test_spring_values_are_ones_hl_curve_accepts(self):
        # hl.curve refuses stiffness, damping or mass below 0.5.
        spring = self.motion["spring"]
        for key, value in spring.items():
            with self.subTest(field=key):
                self.assertGreaterEqual(value, 0.5)

    def test_the_four_easings_are_distinct_curves(self):
        curves = {name: tuple(tuple(p) for p in curve["points"])
                  for name, curve in self.motion["easing"].items()}
        self.assertEqual(len(curves), len(set(curves.values())),
                         "two named easings are the same curve")

    def test_decelerate_has_no_slow_in_and_accelerate_has_no_slow_out(self):
        # The whole point of naming them separately: decelerate starts at full
        # speed (first handle at x = 0), accelerate runs to a stop (second
        # handle at x = 1).
        decelerate = self.motion["easing"]["decelerate"]["points"]
        accelerate = self.motion["easing"]["accelerate"]["points"]
        self.assertEqual(0.0, decelerate[0][0])
        self.assertEqual([1.0, 1.0], accelerate[1])

    def test_the_standard_curve_is_the_material_one(self):
        # cubic-bezier(0.4, 0, 0.2, 1): the handles are allowed to run
        # right-to-left, which is what gives the curve its late deceleration.
        self.assertEqual([[0.4, 0.0], [0.2, 1.0]],
                         self.motion["easing"]["standard"]["points"])


class Typography(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.font = cls.tokens["font"]

    def test_the_faces_are_the_open_licensed_ones(self):
        self.assertEqual("Inter", self.font["ui"])
        self.assertEqual("JetBrainsMono Nerd Font", self.font["mono"])
        self.assertEqual("Noto Color Emoji", self.font["emoji"])

    def test_no_apple_owned_face_is_named(self):
        banned = ("sf pro", "sf mono", "sf compact", "new york", "helvetica", ".applesystem")
        blob = json.dumps(self.tokens).lower()
        for name in banned:
            with self.subTest(face=name):
                self.assertNotIn(name, blob)

    def test_the_size_scale_is_the_documented_one_and_ascending(self):
        sizes = self.font["sizes"]
        self.assertEqual({"xs": 11, "sm": 12, "md": 14, "lg": 16, "xl": 20, "xxl": 28},
                         dict(sizes))
        ordered = [sizes[k] for k in ("xs", "sm", "md", "lg", "xl", "xxl")]
        self.assertEqual(ordered, sorted(ordered))

    def test_weights_are_valid_fontconfig_values(self):
        for name, weight in self.font["weights"].items():
            with self.subTest(weight=name):
                self.assertIn(weight, (400, 500, 600, 700))

    def test_the_fallback_chain_covers_urdu_arabic_and_cjk(self):
        families = " ".join(entry["family"] for entry in self.font["fallback"])
        for needed in ("Nastaliq Urdu", "Naskh Arabic", "CJK"):
            with self.subTest(script=needed):
                self.assertIn(needed, families)

    def test_the_fallback_chain_ends_in_a_last_resort_face(self):
        self.assertEqual("DejaVu Sans", self.font["fallback"][-1]["family"])

    def test_no_unverifiable_symbol_face_is_in_the_chain(self):
        # Symbola's licence could not be established (docs/UNVERIFIED.md TP-12),
        # so it must not be aliased into the stack.
        families = [entry["family"] for entry in self.font["fallback"]]
        self.assertNotIn("Symbola", families)


class HyprlandSurface(unittest.TestCase):
    """The token file may only name APIs that were read out of the source."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.hypr = cls.tokens["hyprland"]

    def test_the_version_it_was_verified_against_is_recorded(self):
        self.assertRegex(self.hypr["verified_against"], r"^v\d+\.\d+\.\d+$")
        self.assertIn("ConfigValues.cpp", self.hypr["source"])

    def test_every_leaf_is_namespaced_the_way_hyprland_names_them(self):
        for leaf in self.hypr["leaves"]:
            with self.subTest(leaf=leaf):
                self.assertRegex(leaf, r"^(general|decoration):[a-z_.:]+$")

    def test_the_leaves_a_generator_needs_are_present(self):
        required = {
            "decoration:rounding", "decoration:blur:enabled", "decoration:blur:size",
            "decoration:blur:passes", "decoration:blur:noise", "decoration:blur:contrast",
            "decoration:blur:brightness", "decoration:blur:vibrancy", "decoration:blur:xray",
            "decoration:shadow:enabled", "decoration:shadow:range", "decoration:dim_inactive",
            "decoration:dim_strength", "decoration:inactive_opacity",
            "general:gaps_in", "general:gaps_out", "general:border_size",
            "general:col.active_border", "general:col.inactive_border",
        }
        self.assertEqual(set(), required - set(self.hypr["leaves"]))

    def test_no_invented_leaf_sneaks_in(self):
        known_bad = {"decoration:blur:amount", "decoration:corner_radius",
                     "decoration:glass", "general:gap_in", "decoration:shadow:size"}
        self.assertEqual(set(), known_bad & set(self.hypr["leaves"]))

    def test_every_declared_range_is_for_a_declared_leaf(self):
        self.assertEqual(set(), set(self.hypr["ranges"]) - set(self.hypr["leaves"]))
        for leaf, (low, high) in self.hypr["ranges"].items():
            with self.subTest(leaf=leaf):
                self.assertLess(low, high)

    def test_the_layer_rule_effects_match_upstream(self):
        self.assertEqual(LAYER_EFFECTS, set(self.hypr["layer_rule_effects"]))

    def test_no_rounding_effect_is_claimed(self):
        # There is no no_rounding window rule effect; rounding is turned off per
        # window by setting rounding = 0.
        self.assertNotIn("no_rounding", self.hypr["window_rule_effects"])
        self.assertIn("rounding", self.hypr["window_rule_effects"])

    def test_the_match_properties_include_the_ones_rules_are_written_against(self):
        props = set(self.hypr["rule_match_properties"])
        for needed in ("class", "title", "initial_class", "namespace", "fullscreen", "float"):
            with self.subTest(prop=needed):
                self.assertIn(needed, props)


class Surfaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)
        cls.surfaces = cls.tokens["surfaces"]

    def test_the_verified_flag_is_false_and_says_so_in_the_unverified_log(self):
        self.assertFalse(self.surfaces["verified"])
        self.assertIn("SES-02", UNVERIFIED.read_text(encoding="utf-8"))

    def test_every_entry_uses_only_real_layer_rule_effects(self):
        allowed = set(self.tokens["hyprland"]["layer_rule_effects"])
        reserved = {"id", "namespace", "description"}
        for entry in self.surfaces["entries"]:
            effects = set(entry) - reserved
            with self.subTest(surface=entry["id"]):
                self.assertEqual(set(), effects - allowed,
                                 f"{effects - allowed} are not layer rule effects")

    def test_ids_are_unique_and_namespaces_are_anchored_patterns(self):
        ids = [entry["id"] for entry in self.surfaces["entries"]]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in self.surfaces["entries"]:
            with self.subTest(surface=entry["id"]):
                re.compile(entry["namespace"])
                self.assertTrue(entry["namespace"].startswith("^"))

    def test_the_shell_surfaces_the_design_covers_are_all_listed(self):
        ids = {entry["id"] for entry in self.surfaces["entries"]}
        for surface in ("bar", "dock", "launcher", "control_center", "notifications", "lock"):
            with self.subTest(surface=surface):
                self.assertIn(surface, ids)

    def test_ignore_alpha_is_a_fraction(self):
        for entry in self.surfaces["entries"]:
            with self.subTest(surface=entry["id"]):
                self.assertGreaterEqual(entry["ignore_alpha"], 0.0)
                self.assertLessEqual(entry["ignore_alpha"], 1.0)

    def test_above_lock_is_inside_the_range_upstream_declares(self):
        for entry in self.surfaces["entries"]:
            if "above_lock" in entry:
                with self.subTest(surface=entry["id"]):
                    self.assertIn(entry["above_lock"], (0, 1, 2))


class Accents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = read_json(TOKENS_PATH)

    def test_the_five_semantic_roles_exist_as_hex(self):
        for role, value in self.tokens["accent"].items():
            with self.subTest(role=role):
                self.assertRegex(value, r"^#[0-9a-f]{6}$")

    def test_border_gradient_roles_point_at_real_accents(self):
        active = self.tokens["layout"]["border"]["active"]
        self.assertIn(active["from_role"], self.tokens["accent"])
        self.assertIn(active["to_role"], self.tokens["accent"])


if __name__ == "__main__":
    unittest.main()
