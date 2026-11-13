#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the GTK renderer, ``iarch/cli/render_gtk_css.py``.

GTK hides its mistakes: an unknown property warns and is dropped, a selector
that matches nothing is kept and never applies, and a transition naming a
property that is not GTK_STYLE_PROPERTY_ANIMATED interpolates nothing. So these
tests assert against the upstream surface recorded in ``data/design/gtk.json``
rather than against a frozen snapshot of the CSS:

* every property, shorthand, at-rule, pseudo-class, function, node name and
  style class a sheet uses is one that version of GTK parses;
* ``transition-property`` names only animatable properties, and never a
  shorthand, which carries no animated flag of its own;
* nothing a sheet writes is a number the renderer chose: radii, opacities,
  durations, easings and border widths all come from the tokens;
* the two versions get what they can actually parse, so a GTK 4-only property
  cannot leak into the GTK 3 sheet;
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

from iarch.cli import render_gtk_css as gtk  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS = gtk.load_tokens()
SURFACE = gtk.load_surface()
PRESET_IDS = sorted(path.stem for path in gtk.PRESET_DIR.glob("*.json"))
INTENSITIES = sorted(TOKENS["intensities"])
COMBINATIONS = [(p, i, v) for p in PRESET_IDS for i in INTENSITIES for v in gtk.VERSIONS]

try:
    import jinja2  # noqa: F401
    HAVE_JINJA = True
except ImportError:
    HAVE_JINJA = False


def sheet(preset_id: str = "midnight-glass", intensity: str = "frosted",
          version: str = "4", reduce_motion: bool = False) -> str:
    context = gtk.build_context(TOKENS, gtk.load_preset(preset_id), SURFACE,
                                intensity, version, reduce_motion=reduce_motion)
    return gtk.render_sheet(version, context)


def declarations(text: str) -> List[tuple]:
    """Every (selector, property, value) triple in a sheet."""
    clean = gtk.strip_comments(text)
    clean = re.sub(r"@define-color\s+[a-zA-Z0-9_-]+\s+[^;]+;", " ", clean)
    out = []
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", clean):
        selector = " ".join(rule.group(1).split())
        for decl in re.finditer(r"([a-zA-Z-][a-zA-Z0-9_-]*)\s*:\s*([^;]+);", rule.group(2)):
            out.append((selector, decl.group(1), " ".join(decl.group(2).split())))
    return out


requires_jinja = unittest.skipUnless(HAVE_JINJA, "Jinja2 is not installed")


class VerifiedSurface(unittest.TestCase):
    """The recorded surface has to be internally consistent to gate anything."""

    def test_both_versions_are_recorded_against_a_release(self):
        verified = SURFACE["verified_against"]
        self.assertRegex(verified["gtk4"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(verified["gtk3"], r"^3\.\d+\.\d+$")
        self.assertTrue(verified["gtk4"].startswith("4."))
        self.assertRegex(verified["libadwaita"], r"^\d+\.\d+\.\d+$")

    def test_the_versions_recorded_are_different_languages(self):
        g4, g3 = SURFACE["gtk4"], SURFACE["gtk3"]
        # GTK 3 has no filter or transform support at all: the value parsers do
        # not exist at that tag, so the sheet must not ask for them.
        self.assertIn("backdrop-filter", g4["properties"])
        self.assertIn("filter", g4["properties"])
        self.assertIn("transform", g4["properties"])
        self.assertNotIn("filter", g3["properties"])
        self.assertNotIn("backdrop-filter", g3["properties"])
        self.assertNotIn("transform", g3["properties"])
        self.assertEqual([], g3["filter_functions"])
        self.assertEqual([], g3["transform_functions"])
        self.assertTrue(g4["filter_functions"])
        self.assertTrue(g4["transform_functions"])
        self.assertIn("media", g4["at_rules"])
        self.assertNotIn("media", g3["at_rules"])
        self.assertIn("binding-set", g3["at_rules"])
        self.assertNotIn("binding-set", g4["at_rules"])

    def test_focus_and_state_pseudo_classes_differ_between_versions(self):
        self.assertIn("focus-visible", SURFACE["gtk4"]["pseudo_classes"])
        self.assertNotIn("focus-visible", SURFACE["gtk3"]["pseudo_classes"])
        for legacy in ("prelight", "insensitive"):
            self.assertIn(legacy, SURFACE["gtk3"]["pseudo_classes"])
        # GTK 3 registers :dir() with its argument as one token, "dir(ltr)".
        self.assertIn("dir", SURFACE["gtk3"]["pseudo_classes"])
        self.assertIn("dir", SURFACE["gtk4"]["pseudo_classes"])

    def test_animated_properties_are_a_subset_of_the_real_ones(self):
        for version in gtk.VERSIONS:
            spec = SURFACE[f"gtk{version}"]
            with self.subTest(version=version):
                self.assertTrue(set(spec["animated_properties"]) <= set(spec["properties"]))
                self.assertIn("background-color", spec["animated_properties"])
                self.assertIn("box-shadow", spec["animated_properties"])
                self.assertIn("outline-color", spec["animated_properties"])

    def test_no_shorthand_is_animatable(self):
        """A shorthand expands at parse time and carries no animated flag."""
        for version in gtk.VERSIONS:
            spec = SURFACE[f"gtk{version}"]
            with self.subTest(version=version):
                self.assertEqual(set(), set(spec["shorthands"]) & set(spec["animated_properties"]))
                self.assertIn("border-color", spec["shorthands"])

    def test_gtk4_has_no_decoration_node_and_gtk3_does(self):
        self.assertNotIn("decoration", SURFACE["gtk4"]["node_names"])
        self.assertIn("decoration", SURFACE["gtk3"]["node_names"])

    def test_the_gtk4_class_gap_is_recorded_rather_than_hidden(self):
        self.assertIn("gtk4_style_classes", SURFACE["diagnostics"])
        self.assertIn("gtkstylecontext.h", SURFACE["diagnostics"]["gtk4_style_classes"])

    def test_no_important_anywhere_because_gtk_has_none(self):
        self.assertIn("important", SURFACE["diagnostics"])
        # The templates say in prose why GTK has no !important; what matters is
        # that no rendered declaration uses it.
        for version in gtk.VERSIONS:
            with self.subTest(version=version):
                self.assertNotIn("important", gtk.strip_comments(sheet(version=version)))


@requires_jinja
class EveryCombinationIsValid(unittest.TestCase):
    def test_every_preset_intensity_and_version_validates(self):
        self.assertEqual(48, len(COMBINATIONS))
        for preset, intensity, version in COMBINATIONS:
            with self.subTest(preset=preset, intensity=intensity, version=version):
                self.assertEqual([], gtk.validate_sheet(sheet(preset, intensity, version),
                                                        SURFACE, version))

    def test_every_sheet_is_well_formed_css(self):
        for preset, intensity, version in COMBINATIONS:
            body = sheet(preset, intensity, version)
            with self.subTest(preset=preset, intensity=intensity, version=version):
                self.assertEqual(body.count("{"), body.count("}"), "unbalanced braces")
                self.assertNotIn("!important", body)
                self.assertTrue(body.endswith("}"))
                # every declaration inside a rule ends with a semicolon
                for rule in re.finditer(r"\{([^{}]*)\}", gtk.strip_comments(body)):
                    inner = rule.group(1).strip()
                    if inner:
                        self.assertTrue(inner.endswith(";"), inner[-40:])

    def test_an_invented_property_is_refused(self):
        body = sheet() + "\nwindow { glassiness: 0.5; }\n"
        problems = gtk.validate_sheet(body, SURFACE, "4")
        self.assertTrue(any("no such property" in line for line in problems), problems)

    def test_a_gtk4_only_property_cannot_leak_into_the_gtk3_sheet(self):
        body = sheet(version="3") + "\nwindow { backdrop-filter: blur(8px); }\n"
        problems = gtk.validate_sheet(body, SURFACE, "3")
        self.assertTrue(any("backdrop-filter" in line for line in problems), problems)

    def test_a_dead_selector_is_refused(self):
        for version, bogus in (("4", "frobnicator"), ("3", "frobnicator")):
            with self.subTest(version=version):
                body = sheet(version=version) + f"\n{bogus} {{ color: #ffffff; }}\n"
                problems = gtk.validate_sheet(body, SURFACE, version)
                self.assertTrue(any("not a node name" in line for line in problems), problems)

    def test_an_unverified_style_class_is_refused(self):
        body = sheet() + "\nbutton.iarch-invented { color: #ffffff; }\n"
        problems = gtk.validate_sheet(body, SURFACE, "4")
        self.assertTrue(any("not a style class" in line for line in problems), problems)

    def test_an_attribute_selector_is_refused(self):
        body = sheet() + "\ntab[selected] { color: #ffffff; }\n"
        problems = gtk.validate_sheet(body, SURFACE, "4")
        self.assertTrue(any("attribute selector" in line for line in problems), problems)

    def test_transitioning_a_shorthand_is_refused(self):
        """border-color is not animated, so this transition does nothing."""
        body = sheet() + ("\nbutton { transition-property: background-color, border-color;"
                          " transition-duration: 120ms; }\n")
        problems = gtk.validate_sheet(body, SURFACE, "4")
        self.assertTrue(any("GTK_STYLE_PROPERTY_ANIMATED" in line for line in problems), problems)

    def test_an_unparsable_at_rule_is_refused(self):
        body = sheet() + "\n@supports (backdrop-filter: blur(2px)) { }\n"
        problems = gtk.validate_sheet(body, SURFACE, "3")
        self.assertTrue(any("@supports" in line for line in problems), problems)


@requires_jinja
class ValuesComeFromTokens(unittest.TestCase):
    def setUp(self):
        self.context = gtk.build_context(TOKENS, gtk.load_preset("midnight-glass"),
                                         SURFACE, "frosted", "4")
        self.intensity = TOKENS["intensities"]["frosted"]

    def test_opacities_are_the_intensity_gtk_block(self):
        for name, value in self.intensity["gtk"].items():
            with self.subTest(surface=name):
                self.assertEqual(value, self.context["o"][name])

    def test_radii_are_the_token_radii_resolved_through_their_roles(self):
        radius = TOKENS["radius"]
        for role in ("window", "card", "button", "input", "tooltip"):
            with self.subTest(role=role):
                size = radius[role]
                if isinstance(size, str):
                    size = radius[size]
                self.assertEqual(int(size), self.context["r"][role])
        self.assertEqual(int(radius["check"]), self.context["r"]["check"])

    def test_the_pill_radius_is_clamped_rather_than_emitted_as_999(self):
        # radius.pill is 999, which is a design value for a compositor rule, not
        # a corner GTK should be asked to draw on a 26px control.
        self.assertLess(self.context["r"]["pill_clamped"], TOKENS["radius"]["pill"])
        self.assertEqual(min(TOKENS["radius"]["pill"], gtk.SHAPE["circular_min"]),
                         self.context["r"]["pill_clamped"])

    def test_durations_and_easings_are_the_motion_tokens(self):
        motion = TOKENS["motion"]
        self.assertEqual(int(motion["fast_ms"]), self.context["m"]["fast"])
        self.assertEqual(int(motion["normal_ms"]), self.context["m"]["normal"])
        self.assertEqual(int(motion["slow_ms"]), self.context["m"]["slow"])
        for name in ("standard", "emphasized", "decelerate", "accelerate"):
            points = motion["easing"][name]["points"]
            expected = "cubic-bezier(" + ", ".join(
                f"{float(x):g}" for point in points for x in point) + ")"
            with self.subTest(easing=name):
                self.assertEqual(expected, self.context["m"][name])

    def test_border_width_is_the_layout_token(self):
        self.assertEqual(float(TOKENS["layout"]["border_size"]), self.context["border"])
        body = sheet()
        self.assertIn(f"0 0 0 {self.context['border']:g}px", body)

    def test_colours_are_the_presets_own_palette(self):
        preset = gtk.load_preset("midnight-glass")
        palette = preset["palette"]
        self.assertEqual(palette["background"], self.context["c"]["background"])
        self.assertEqual(palette["surface_variant"], self.context["c"]["surface_variant"])
        self.assertEqual(palette["accent"]["primary"], self.context["c"]["accent"])
        self.assertEqual(palette["accent"]["danger"], self.context["c"]["danger"])
        self.assertEqual(palette["on_accent"]["primary"], self.context["c"]["on_accent"])

    def test_blur_follows_the_intensity_and_disappears_when_it_is_off(self):
        self.assertTrue(self.context["blur_enabled"])
        self.assertEqual(int(self.intensity["blur"]["size"]), self.context["blur_px"])
        self.assertIn("backdrop-filter: blur(", sheet(intensity="frosted"))
        for version in gtk.VERSIONS:
            with self.subTest(version=version):
                self.assertNotIn("backdrop-filter", sheet(intensity="performance",
                                                          version=version))

    def test_performance_sets_every_surface_opaque(self):
        context = gtk.build_context(TOKENS, gtk.load_preset("midnight-glass"),
                                    SURFACE, "performance", "4")
        for name, value in context["o"].items():
            with self.subTest(surface=name):
                self.assertEqual(1.0, value)

    def test_every_transition_property_is_animatable(self):
        for version in gtk.VERSIONS:
            animated = set(SURFACE[f"gtk{version}"]["animated_properties"])
            body = sheet(version=version)
            seen = 0
            for _, prop, value in declarations(body):
                if prop != "transition-property":
                    continue
                seen += 1
                for name in (item.strip() for item in value.split(",")):
                    with self.subTest(version=version, name=name):
                        self.assertIn(name, animated)
            self.assertGreater(seen, 10, "the sheet barely transitions anything")

    def test_a_sidebar_is_never_more_translucent_than_its_window(self):
        for intensity in INTENSITIES:
            block = TOKENS["intensities"][intensity]["gtk"]
            with self.subTest(intensity=intensity):
                self.assertGreaterEqual(block["sidebar"], block["window"])

    def test_every_shape_constant_the_renderer_owns_is_documented(self):
        source = Path(gtk.__file__).read_text(encoding="utf-8")
        block = source[source.index("SHAPE = OrderedDict("):]
        block = block[:block.index("\n)\n")]
        for key in gtk.SHAPE:
            with self.subTest(constant=key):
                self.assertIn(key, block)
        # the comment above the table is what makes these auditable
        self.assertIn("Values with no token equivalent", source)


@requires_jinja
class CoverageOfEveryStateAndSurface(unittest.TestCase):
    """The brief is a sheet that covers every control in every state."""

    STATES = {
        "4": (":hover", ":active", ":focus-visible", ":disabled", ":checked", ":backdrop"),
        "3": (":hover", ":active", ":focus", ":disabled", ":checked", ":backdrop"),
    }

    def test_every_required_state_appears(self):
        for version in gtk.VERSIONS:
            body = sheet(version=version)
            for state in self.STATES[version]:
                with self.subTest(version=version, state=state):
                    self.assertIn(state, body)

    def test_gtk3_also_carries_the_older_spellings(self):
        body = sheet(version="3")
        for state in (":prelight", ":insensitive", ":inconsistent"):
            with self.subTest(state=state):
                self.assertIn(state, body)

    def test_every_surface_the_brief_names_is_styled(self):
        common = ("window.background", "headerbar", ".sidebar", "button", "entry",
                  "switch", "check", "radio", "scale", "progressbar", "scrollbar",
                  "notebook", "list", "row", "popover", "menubar", "tooltip",
                  "separator", "frame", "textview", "spinner", "link")
        for version in gtk.VERSIONS:
            body = sheet(version=version)
            for selector in common:
                with self.subTest(version=version, selector=selector):
                    self.assertIn(selector, body)

    def test_version_specific_surfaces_go_to_the_version_that_has_them(self):
        gtk4 = sheet(version="4")
        gtk3 = sheet(version="3")
        self.assertIn("toast", gtk4)
        self.assertIn("banner", gtk4)
        self.assertIn("prefers-reduced-motion", gtk4)
        self.assertIn("menuitem", gtk3)
        self.assertIn("toolbar", gtk3)
        self.assertIn("decoration", gtk3)
        self.assertNotIn("prefers-reduced-motion", gtk3)  # GTK 3 cannot parse @media
        self.assertNotIn("menuitem", gtk4)

    def test_buttons_carry_the_accent_and_destructive_treatments(self):
        for version in gtk.VERSIONS:
            body = sheet(version=version)
            for selector in ("button.suggested-action", "button.destructive-action",
                             "button.flat", "button.circular", ".linked > button"):
                with self.subTest(version=version, selector=selector):
                    self.assertIn(selector, body)
            # the suggested action glows with the accent, not with a second shadow
            self.assertIn("box-shadow: 0 0", body)

    def test_inputs_get_a_focus_ring_and_a_muted_placeholder(self):
        for version in gtk.VERSIONS:
            body = sheet(version=version)
            with self.subTest(version=version):
                self.assertIn("outline-color:", body)
                self.assertIn("outline-offset:", body)
                self.assertIn("caret-color:", body)
        self.assertIn("placeholder", sheet(version="4"))

    def test_translucent_surfaces_use_alpha_not_a_baked_hex(self):
        for version in gtk.VERSIONS:
            body = sheet(version=version)
            with self.subTest(version=version):
                self.assertGreater(body.count("alpha("), 40,
                                   "the sheet hard-codes colours instead of tinting them")
                self.assertIn("linear-gradient(to bottom", body)


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

    @requires_jinja
    def test_a_sheet_that_fails_validation_is_refused_before_any_write(self):
        original = gtk.validate_sheet
        gtk.validate_sheet = lambda text, surface, version: ["button: glassiness is invented"]
        try:
            with self.assertRaises(gtk.GtkError) as caught:
                gtk.targets_for("4", TOKENS, gtk.load_preset("midnight-glass"), SURFACE,
                                "frosted", self.root / "gtk-4.0")
        finally:
            gtk.validate_sheet = original
        self.assertIn("does not have", str(caught.exception))
        self.assertEqual([], list((self.root / "gtk-4.0").rglob("*"))
                         if (self.root / "gtk-4.0").exists() else [])

    @requires_jinja
    def test_a_failure_part_way_through_leaves_the_filesystem_as_it_was(self):
        good = self.root / "gtk-4.0" / "gtk.css"
        good.parent.mkdir(parents=True)
        good.write_text("/* previous */\n", encoding="utf-8")
        blocked = self.root / "blocked" / "gtk.css"
        blocked.parent.mkdir(parents=True)
        os.chmod(blocked.parent, 0o500)
        self.addCleanup(os.chmod, blocked.parent, 0o700)
        with self.assertRaises(OSError):
            gtk.write_all([(good, "window { color: #fff; }"), (blocked, "x")], self.env)
        self.assertEqual("/* previous */\n", good.read_text(encoding="utf-8"))
        self.assertFalse(blocked.exists())

    @requires_jinja
    def test_an_existing_sheet_keeps_its_mode_and_gains_a_backup(self):
        target = self.root / "gtk.css"
        target.write_text("/* previous */\n", encoding="utf-8")
        os.chmod(target, 0o640)
        gtk.write_all([(target, "window { color: #fff; }")], self.env)
        self.assertEqual(0o640, target.stat().st_mode & 0o777)
        self.assertTrue([p for p in (self.root / "state" / "backups").rglob("*") if p.is_file()])

    def test_a_missing_template_is_reported_not_crashed(self):
        with unittest.mock.patch.object(gtk, "TEMPLATE_DIR", self.root / "nowhere"):
            with self.assertRaises(gtk.GtkError) as caught:
                gtk.render_sheet("4", {})
        self.assertIn("missing template", str(caught.exception))

    def test_an_unknown_version_is_refused(self):
        with self.assertRaises(gtk.GtkError):
            gtk.render_sheet("2", {})

    def test_a_missing_radius_role_is_reported_with_its_reason(self):
        tokens = json.loads(json.dumps(TOKENS))
        del tokens["radius"]["check"]
        with self.assertRaises(gtk.GtkError) as caught:
            gtk.build_context(tokens, gtk.load_preset("midnight-glass"), SURFACE,
                              "frosted", "4")
        self.assertIn("check", str(caught.exception))

    def test_a_broken_easing_token_is_refused(self):
        tokens = json.loads(json.dumps(TOKENS))
        tokens["motion"]["easing"]["standard"]["points"] = [[0.4, 0.0], [1.4, 1.0]]
        with self.assertRaises(gtk.GtkError):
            gtk.build_context(tokens, gtk.load_preset("midnight-glass"), SURFACE,
                              "frosted", "4")


@requires_jinja
@requires_jinja
class HoverPressAndFocusAnswerInsideOneBand(unittest.TestCase):
    """Task 3: a control answers hover, press and focus in 120-180ms, or not at all.

    Two upstream facts decide what is assertable here. Only properties flagged
    GTK_STYLE_PROPERTY_ANIMATED interpolate, so a transition is worth nothing
    unless it names them (``ValuesComeFromTokens`` and ``VerifiedSurface`` already
    prove that). And GTK 3 has no ``media`` in its at-rule list, so it cannot hear
    ``prefers-reduced-motion`` at all — which is why the reduce-motion story has
    two halves, a media query for GTK 4 and a render-time zero for both.
    """

    LOW, HIGH = 120, 180

    def triples(self, version: str, reduce_motion: bool = False) -> List[tuple]:
        return declarations(sheet(version=version, reduce_motion=reduce_motion))

    def durations(self, version: str, reduce_motion: bool = False) -> List[int]:
        # Only the durations of rules that actually transition something. The
        # reduce-motion block declares a 0ms duration on `*` with no property
        # list, and split_at_blocks keeps the inner rules of an @media in the
        # body, so counting it here would put a deliberate 0 in the band.
        triples = self.triples(version, reduce_motion)
        animated = {sel for sel, prop, _ in triples if prop == "transition-property"}
        return [int(value[:-2]) for sel, prop, value in triples
                if prop == "transition-duration" and sel in animated]

    def test_every_duration_a_widget_wears_is_inside_the_band(self):
        for version in gtk.VERSIONS:
            for value in self.durations(version):
                with self.subTest(version=version, ms=value):
                    self.assertTrue(self.LOW <= value <= self.HIGH,
                                    f"{value}ms is outside the {self.LOW}-{self.HIGH}ms "
                                    f"band hover, press and focus must answer in")

    def test_the_band_is_one_token_wide_and_the_template_never_chooses_a_number(self):
        # Every transition in both sheets carries motion.fast_ms and nothing else,
        # so the band holds or fails as one decision rather than rule by rule.
        fast = TOKENS["motion"]["fast_ms"]
        self.assertTrue(self.LOW <= fast <= self.HIGH,
                        f"motion.fast_ms = {fast} is outside the band the sheets are "
                        f"required to stay inside")
        for version in gtk.VERSIONS:
            with self.subTest(version=version):
                self.assertEqual({fast}, set(self.durations(version)))

    def test_the_tokens_slow_duration_belongs_to_the_compositor_not_to_a_widget(self):
        # motion.slow_ms is a workspace-slide duration. A hover that took 380ms
        # would feel broken rather than calm, so no sheet may reach for it.
        slow = TOKENS["motion"]["slow_ms"]
        self.assertGreater(slow, self.HIGH)
        for version in gtk.VERSIONS:
            with self.subTest(version=version):
                self.assertNotIn(slow, self.durations(version))

    def test_a_focus_ring_fades_in_instead_of_appearing(self):
        # The ring is set by a :focus-visible rule (GTK 4) or a :focus rule
        # (GTK 3), but a transition has to be declared on the *base* rule to
        # animate into that state. Naming outline-color only in the ring group
        # would leave the ring snapping while everything beside it faded.
        for version in gtk.VERSIONS:
            pseudo = ":focus-visible" if version == "4" else ":focus"
            triples = self.triples(version)
            transitioning = {sel: value for sel, prop, value in triples
                             if prop == "transition-property"}
            ringed = {sel for sel, prop, _ in triples
                      if prop == "outline-color" and pseudo in sel}
            self.assertTrue(ringed, f"GTK {version} sheet draws no focus ring at all")
            for selector in sorted(ringed):
                # A ring rule usually names several controls, and each one has its
                # own base rule: `check:focus-visible, radio:focus-visible` belongs
                # to `check, radio`, while `scale:focus-visible slider` belongs to
                # the `scale slider` rule.
                for part in selector.split(","):
                    part = part.strip()
                    if pseudo not in part:
                        continue
                    base = " ".join(part.replace(pseudo, "").split())
                    owners = [sel for sel in transitioning
                              if base in [p.strip() for p in sel.split(",")]]
                    with self.subTest(version=version, ring=part, base=base):
                        self.assertTrue(
                            owners,
                            f"{base} wears a focus ring but no rule transitions it")
                        for owner in owners:
                            props = [p.strip() for p in transitioning[owner].split(",")]
                            self.assertIn("outline-color", props,
                                          f"{owner} does not transition the ring colour")
                            self.assertIn("outline-width", props,
                                          f"{owner} does not transition the ring width")

    def test_the_window_focus_hairline_fades_rather_than_snapping(self):
        # Focus moves an inset hairline between two alphas, and that hairline is a
        # box-shadow. GTK 4 draws it on window.background; GTK 3 puts the whole
        # client-side decoration -- hairline and drop shadow -- on the decoration
        # node instead. Transitioning only background-color left the one focus cue
        # every window in the session shares jumping between the two.
        cue = {"4": ("window.background:backdrop", "window.background"),
               "3": ("decoration:backdrop", "decoration")}
        for version in gtk.VERSIONS:
            backdrop_selector, owner_part = cue[version]
            triples = self.triples(version)
            backdrop = {value for sel, prop, value in triples
                        if sel == backdrop_selector and prop == "box-shadow"}
            transitioning = {sel: value for sel, prop, value in triples
                             if prop == "transition-property"}
            owners = [sel for sel in transitioning
                      if owner_part in [p.strip() for p in sel.split(",")]]
            with self.subTest(version=version):
                self.assertTrue(backdrop,
                                f"GTK {version} has no {backdrop_selector} hairline")
                self.assertTrue(owners,
                                f"no rule transitions {owner_part}, which is where "
                                f"GTK {version} draws the focus hairline")
                for owner in owners:
                    self.assertIn("box-shadow",
                                  [p.strip() for p in transitioning[owner].split(",")],
                                  f"{owner} transitions its fill but not the hairline "
                                  f"that actually changes on focus")

    def test_gtk_4_answers_the_desktop_preference_with_a_universal_selector(self):
        # An enumerated list of controls silently misses whatever is added next,
        # and this one already had: spinbutton, .titlebar, listview > row and the
        # three menu-item selectors all transitioned while none of them was named
        # in the reduce-motion block, so a user who asked for less motion still
        # got a fading menu.
        text = sheet(version="4")
        block = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}",
                          gtk.strip_comments(text), re.S)
        self.assertIsNotNone(block, "the GTK 4 sheet dropped its reduce-motion block")
        inner = block.group(1)
        self.assertRegex(inner, r"\*\s*\{")
        self.assertIn("transition-duration: 0ms", inner)
        self.assertIn("transition-delay: 0ms", inner)
        # A delayed transition is motion the user still waits for.
        self.assertNotRegex(inner, r"\b(window|button|entry)\b",
                            "the reduce-motion block went back to naming controls")

    def test_the_reduce_motion_block_leaves_application_animations_alone(self):
        # This sheet emits no keyframe animation at all, so every animation in a
        # session belongs to the application's own theme -- usually a spinner.
        # Zeroing animation-duration would not reduce motion so much as hide the
        # fact that something is still working.
        inner = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}",
                          gtk.strip_comments(sheet(version="4")), re.S).group(1)
        self.assertNotIn("animation-", inner)
        for version in gtk.VERSIONS:
            with self.subTest(version=version):
                self.assertNotIn("animation-duration",
                                 [prop for _, prop, _ in self.triples(version)])

    def test_gtk_3_has_no_media_query_because_it_cannot_parse_one(self):
        self.assertNotIn("media", SURFACE["gtk3"]["at_rules"])
        self.assertIn("media", SURFACE["gtk4"]["at_rules"])
        self.assertNotIn("@media", sheet(version="3"))

    def test_a_reduce_motion_render_zeroes_every_duration_in_both_sheets(self):
        # The only lever GTK 3 has, and the one the iArch setting pulls for both.
        for version in gtk.VERSIONS:
            values = self.durations(version, reduce_motion=True)
            with self.subTest(version=version):
                self.assertTrue(values)
                self.assertEqual({0}, set(values))

    def test_a_reduce_motion_render_changes_nothing_but_the_durations(self):
        # Same selectors, same properties, same colours: a user who asks for less
        # motion must not lose the focus ring or the glass along with it.
        for version in gtk.VERSIONS:
            plain = [(s, p) for s, p, _ in self.triples(version)]
            quiet = [(s, p) for s, p, _ in self.triples(version, reduce_motion=True)]
            with self.subTest(version=version):
                self.assertEqual(plain, quiet)

    def test_the_reduce_motion_flag_refuses_to_become_the_shipped_payload(self):
        # The shipped payload is the state a fresh install starts in; a
        # reduce-motion sheet written there would make every later --check --repo
        # report drift for a file nobody asked to change.
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp)
            with unittest.mock.patch.dict(os.environ, env, clear=True):
                code = gtk.main(["--reduce-motion", "--write-repo-default"])
            self.assertEqual(2, code)

    def test_the_reduce_motion_flag_renders_when_writing_to_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = gtk.main(["--reduce-motion", "--output-dir", tmp])
            self.assertEqual(0, code)
            for version in gtk.VERSIONS:
                text = (Path(tmp) / f"gtk-{version}.0" / "gtk.css").read_text()
                values = [int(v) for v in
                          re.findall(r"transition-duration:\s*(\d+)ms", text)]
                with self.subTest(version=version):
                    self.assertTrue(values)
                    self.assertEqual({0}, set(values))


class ShippedPayload(unittest.TestCase):
    def test_both_sheets_ship_and_validate(self):
        for version in gtk.VERSIONS:
            path = gtk.REPO_CONFIG / f"gtk-{version}.0" / "gtk.css"
            with self.subTest(version=version):
                self.assertTrue(path.is_file(), path)
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith(configstore.header_for(path)))
                self.assertEqual([], gtk.validate_sheet(text, SURFACE, version))

    def test_the_shipped_sheets_are_the_default_preset_at_the_default_intensity(self):
        for version in gtk.VERSIONS:
            path = gtk.REPO_CONFIG / f"gtk-{version}.0" / "gtk.css"
            with self.subTest(version=version):
                expected = gtk.rendered_text(path, sheet("midnight-glass",
                                                         TOKENS["default_intensity"], version))
                self.assertEqual(expected, path.read_text(encoding="utf-8"))

    def test_the_shipped_sheets_are_readable_and_staged(self):
        for version in gtk.VERSIONS:
            path = gtk.REPO_CONFIG / f"gtk-{version}.0" / "gtk.css"
            with self.subTest(version=version):
                self.assertTrue(path.stat().st_mode & 0o044)
        staged = subprocess.run(["bash", str(ROOT / "lib" / "stage-v5-config.sh"),
                                 str(ROOT / ".config"), str(self.tmp_stage())],
                                capture_output=True, text=True)
        self.assertEqual(0, staged.returncode, staged.stderr)

    def tmp_stage(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = Path(tmp.name) / "stage"
        dest.mkdir()
        return dest


@requires_jinja
class CommandLine(unittest.TestCase):
    def run_cli(self, argv: List[str]):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gtk.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_print_writes_both_sheets_to_stdout(self):
        code, out, err = self.run_cli(["--print"])
        self.assertEqual(0, code, err)
        self.assertIn("gtk-4.0/gtk.css", out)
        self.assertIn("gtk-3.0/gtk.css", out)
        self.assertIn("window.background", out)

    def test_one_version_can_be_rendered_alone(self):
        code, out, err = self.run_cli(["--gtk", "3", "--print"])
        self.assertEqual(0, code, err)
        self.assertIn("gtk-3.0/gtk.css", out)
        self.assertNotIn("gtk-4.0/gtk.css", out)

    def test_an_unknown_preset_exits_two(self):
        code, _, err = self.run_cli(["--preset", "vaporwave", "--print"])
        self.assertEqual(2, code)
        self.assertIn("vaporwave", err)

    def test_an_unknown_intensity_exits_two_and_lists_the_real_ones(self):
        code, _, err = self.run_cli(["--intensity", "ultra", "--print"])
        self.assertEqual(2, code)
        for intensity in INTENSITIES:
            self.assertIn(intensity, err)

    def test_output_dir_writes_both_sheets_where_it_was_told(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.run_cli(["--output-dir", tmp])
            self.assertEqual(0, code, err + out)
            for version in gtk.VERSIONS:
                path = Path(tmp) / f"gtk-{version}.0" / "gtk.css"
                self.assertTrue(path.is_file(), path)
                self.assertEqual([], gtk.validate_sheet(path.read_text(encoding="utf-8"),
                                                        SURFACE, version))

    def test_check_passes_on_the_shipped_payload(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "iarch" / "cli" / "render_gtk_css.py"),
             "--check", "--repo"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("match a fresh render", result.stdout)

    def test_without_jinja_the_renderer_says_so_instead_of_raising(self):
        real = sys.modules.pop("jinja2", None)
        sys.modules["jinja2"] = None  # an import of None raises ImportError
        try:
            with self.assertRaises(gtk.GtkError) as caught:
                gtk.render_sheet("4", gtk.build_context(
                    TOKENS, gtk.load_preset("midnight-glass"), SURFACE, "frosted", "4"))
        finally:
            del sys.modules["jinja2"]
            if real is not None:
                sys.modules["jinja2"] = real
        self.assertIn("Jinja2 is required", str(caught.exception))
        self.assertIn("TP-16", str(caught.exception))

    def test_help_lists_every_flag(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "iarch" / "cli" / "render_gtk_css.py"), "--help"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(0, result.returncode, result.stderr)
        for flag in ("--preset", "--intensity", "--gtk", "--print", "--check",
                     "--output-dir", "--write-repo-default", "--repo"):
            self.assertIn(flag, result.stdout)


if __name__ == "__main__":
    unittest.main()
